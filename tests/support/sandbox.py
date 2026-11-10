"""한 테스트가 쓰는 임시 작업 영역과, 사용자 환경에서 격리된 git 실행 환경.

테스트 받침이 지키는 약속:

- 네트워크를 쓰지 않는다. 원격은 모두 임시 디렉토리의 로컬 bare 저장소다.
- 사용자의 전역 git 설정을 읽지도 바꾸지도 않는다. 전역 설정 자리에 임시 파일을 끼운다.
- 로컬 경로를 원격으로 하는 서브모듈 전송은 최근 git이 기본으로 막는다. 이 환경 안에서만 허용한다.
- 루트 저장소는 이 저장소의 추적 파일을 임시 디렉토리로 복사해 만든다.
  이 저장소의 `Justfile`을 직접 가리켜 실행하면 등록 명령이 이 작업 사본에 서브모듈을 만들기 때문이다.
- 임시 디렉토리 밖에서는 명령을 실행하지 않는다.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

# 이 저장소의 작업 사본. 추적 파일을 복사하는 원본으로만 쓰고, 여기서 명령을 실행하지 않는다.
SOURCE_REPO = Path(__file__).resolve().parents[2]

# 루트 저장소가 도구 확인에서 찾는 것들.
REQUIRED_TOOLS = ("git", "just", "uv")

_GITCONFIG = """\
[user]
	name = Test User
	email = test@example.invalid
[init]
	defaultBranch = main
[commit]
	gpgsign = false
[protocol "file"]
	allow = always
"""


class Sandbox:
    """임시 디렉토리 하나와 그 안에서만 도는 격리된 git 환경."""

    def __init__(self, base: Path) -> None:
        self.base = base.resolve()
        self._counter = 0

        config_dir = self.base / "_env"
        config_dir.mkdir()
        gitconfig = config_dir / "gitconfig"
        gitconfig.write_text(_GITCONFIG, encoding="utf-8")

        # 상위 프로세스가 물려준 GIT_*(예: GIT_DIR), JUST_* 는 모두 버린다.
        env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "JUST_"))}
        env.update(
            GIT_CONFIG_GLOBAL=str(gitconfig),  # ~/.gitconfig 와 XDG 전역 설정을 대신한다
            GIT_CONFIG_NOSYSTEM="1",
            XDG_CONFIG_HOME=str(config_dir / "xdg"),  # ~/.config/git/ignore 같은 전역 파일도 읽지 않는다
            GIT_TERMINAL_PROMPT="0",
        )
        self.env = env

    # --- 실행 -----------------------------------------------------------------

    def run(
        self,
        args: list[str | Path],
        *,
        cwd: Path,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """임시 디렉토리 안에서 명령을 실행한다. 출력은 텍스트로 모은다."""
        cwd = Path(cwd).resolve()
        if not cwd.is_relative_to(self.base):
            raise AssertionError(f"임시 디렉토리 밖에서는 실행하지 않는다: {cwd}")
        return subprocess.run(
            [str(a) for a in args],
            cwd=cwd,
            env=self.env if env is None else env,
            capture_output=True,
            text=True,
            check=check,
        )

    def git(self, *args: str | Path, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
        return self.run(["git", *args], cwd=cwd, check=check)

    def head(self, repo: Path) -> str:
        """`repo`의 HEAD 커밋 해시."""
        return self.git("rev-parse", "HEAD", cwd=repo).stdout.strip()

    def branch(self, repo: Path) -> str | None:
        """`repo`가 체크아웃한 브랜치 이름. detached HEAD이면 `None`."""
        result = self.git("symbolic-ref", "--quiet", "--short", "HEAD", cwd=repo, check=False)
        return result.stdout.strip() if result.returncode == 0 else None

    def just(
        self,
        *args: str | Path,
        cwd: Path,
        justfile: Path | None = None,
        without: tuple[str, ...] = (),
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        """`just`를 실행한다. 종료 코드를 보는 테스트가 많아 기본으로 예외를 던지지 않는다.

        `justfile`을 주면 `--justfile`로 그 파일을 가리킨다(다른 디렉토리에서 부르는 경우).
        `without`에 도구 이름을 주면 PATH에서 그 도구만 빠진 환경에서 실행한다.
        """
        just_bin = _which_or_fail("just")
        command: list[str | Path] = [just_bin]
        if justfile is not None:
            command += ["--justfile", justfile]
        command += list(args)
        env = self.env
        if without:
            env = {**self.env, "PATH": str(self._path_without(without))}
        return self.run(command, cwd=cwd, check=check, env=env)

    def _path_without(self, without: tuple[str, ...]) -> Path:
        """PATH에서 지정한 도구만 빠진 디렉토리를 만든다. 쉘(sh)과 나머지 필수 도구만 이어 둔다."""
        unknown = set(without) - set(REQUIRED_TOOLS)
        if unknown:
            raise ValueError(f"알 수 없는 도구: {sorted(unknown)}")
        self._counter += 1
        bin_dir = self.base / "_bin" / str(self._counter)
        bin_dir.mkdir(parents=True)
        for tool in ("sh", *[t for t in REQUIRED_TOOLS if t not in without]):
            (bin_dir / tool).symlink_to(_which_or_fail(tool))
        return bin_dir

    # --- 저장소 꾸리기 --------------------------------------------------------

    def new_dir(self, kind: str, name: str) -> Path:
        path = self.base / kind / name
        path.mkdir(parents=True, exist_ok=False)
        return path

    def knowledge_remote(
        self, name: str, *, files: dict[str, str] | None = None
    ) -> KnowledgeRemote:
        """가짜 지식 저장소와 그 로컬 bare 원격을 만든다. 기본 브랜치는 `main`이다."""
        return KnowledgeRemote(self, name, files)

    def root(self) -> RootRepo:
        """루트 저장소를 만든다. 이 저장소의 추적 파일을 복사해 커밋하고 bare 원격에 푸시한다."""
        return RootRepo(self)


def _which_or_fail(tool: str) -> str:
    found = shutil.which(tool)
    if found is None:
        raise RuntimeError(f"테스트에 필요한 도구가 없다: {tool}")
    return found


class KnowledgeRemote:
    """가짜 지식 저장소. `url`이 bare 원격이고, `seed`는 그 원격에 커밋을 쌓는 작업 사본이다.

    서브모듈로 붙는 쪽은 `url`만 쓴다. 테스트는 `commit`으로 원격의 이력을 앞으로 보내거나
    브랜치를 만든다.
    """

    def __init__(self, sandbox: Sandbox, name: str, files: dict[str, str] | None) -> None:
        self._sandbox = sandbox
        self.name = name
        self._n = 0
        self.url = sandbox.new_dir("remotes", f"{name}.git")
        self.seed = sandbox.new_dir("seeds", name)

        sandbox.git("init", "--bare", "--initial-branch=main", self.url, cwd=self.url)
        sandbox.git("init", "--initial-branch=main", cwd=self.seed)
        sandbox.git("remote", "add", "origin", self.url, cwd=self.seed)
        for rel, text in (files or {"README.md": f"# {name}\n", "docs/design.md": "# 설계\n"}).items():
            _write(self.seed / rel, text)
        sandbox.git("add", "-A", cwd=self.seed)
        sandbox.git("commit", "-m", "init", cwd=self.seed)
        sandbox.git("push", "origin", "main", cwd=self.seed)

    def commit(self, *, branch: str = "main") -> str:
        """`branch`에 커밋 하나를 쌓아 원격에 푸시하고 그 해시를 돌려준다.

        브랜치가 없으면 `main`의 끝에서 만든다.
        """
        git = self._sandbox.git
        known = git("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", cwd=self.seed, check=False)
        if known.returncode == 0:
            git("checkout", branch, cwd=self.seed)
        else:
            git("checkout", "-b", branch, "main", cwd=self.seed)
        self._n += 1
        _write(self.seed / "docs" / f"note-{self._n}.md", f"# 메모 {self._n}\n")
        git("add", "-A", cwd=self.seed)
        git("commit", "-m", f"note {self._n} on {branch}", cwd=self.seed)
        git("push", "origin", branch, cwd=self.seed)
        return git("rev-parse", "HEAD", cwd=self.seed).stdout.strip()


class RootRepo:
    """루트 저장소와 그 bare 원격. `work`는 소유자의 작업 사본이고 `origin`이 원격이다.

    새로 클론한 상태를 만들려면 `clone()`을 쓴다. 서브모듈 등록은 이 임시 저장소에서만 한다.
    """

    def __init__(self, sandbox: Sandbox) -> None:
        self._sandbox = sandbox
        self._clones = 0
        self.origin = sandbox.new_dir("remotes", "root.git")
        self.work = sandbox.new_dir("author", "root")

        sandbox.git("init", "--bare", "--initial-branch=main", self.origin, cwd=self.origin)
        sandbox.git("init", "--initial-branch=main", cwd=self.work)
        _copy_tracked_files(sandbox, SOURCE_REPO, self.work)
        sandbox.git("remote", "add", "origin", self.origin, cwd=self.work)
        sandbox.git("add", "-A", cwd=self.work)
        sandbox.git("commit", "-m", "init", cwd=self.work)
        sandbox.git("push", "origin", "main", cwd=self.work)

    def register(
        self, remote: KnowledgeRemote, *, name: str | None = None, branch: str | None = None
    ) -> str:
        """`projects/<이름>/`에 서브모듈로 등록하고 커밋·푸시한다. 루트가 기록한 커밋 해시를 돌려준다.

        `branch`를 주면 그 브랜치를 추적 브랜치로 기록한다(`git submodule add -b`).
        """
        name = name or remote.name
        git = self._sandbox.git
        args = ["submodule", "add"]
        if branch is not None:
            args += ["-b", branch]
        git(*args, remote.url, f"projects/{name}", cwd=self.work)
        return self._commit_pointer(name, f"add {name}")

    def point_at(self, name: str, rev: str) -> str:
        """서브모듈 `name`이 가리키는 커밋을 `rev`로 바꿔 커밋·푸시한다. 기록된 커밋 해시를 돌려준다."""
        sub = self.work / "projects" / name
        self._sandbox.git("fetch", "origin", cwd=sub)
        self._sandbox.git("checkout", "--detach", rev, cwd=sub)
        return self._commit_pointer(name, f"point {name} at {rev}")

    def _commit_pointer(self, name: str, message: str) -> str:
        git = self._sandbox.git
        git("add", "-A", cwd=self.work)
        git("commit", "-m", message, cwd=self.work)
        git("push", "origin", "main", cwd=self.work)
        return git("rev-parse", f"HEAD:projects/{name}", cwd=self.work).stdout.strip()

    def clone(self) -> Path:
        """원격에서 새로 클론한다. 서브모듈은 초기화하지 않는다. 새 기기에서 받은 직후의 상태다."""
        self._clones += 1
        dest = self._sandbox.base / "clones" / f"root-{self._clones}"
        dest.parent.mkdir(exist_ok=True)
        self._sandbox.git("clone", self.origin, dest, cwd=dest.parent)
        return dest


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _copy_tracked_files(sandbox: Sandbox, src: Path, dest: Path) -> None:
    """`src` 저장소가 추적하는 파일만 `dest`로 복사한다. 작업 트리의 현재 내용을 복사한다."""
    # 이 저장소의 작업 사본을 읽을 뿐이므로 임시 디렉토리 검사를 거치지 않고 격리된 환경으로 직접 실행한다.
    listing = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=src,
        env=sandbox.env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for rel in filter(None, listing.split("\0")):
        source = src / rel
        if not (source.exists() or source.is_symlink()):
            continue  # 지워졌지만 아직 스테이지하지 않은 파일
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            target.symlink_to(os.readlink(source))
        else:
            shutil.copy2(source, target)
