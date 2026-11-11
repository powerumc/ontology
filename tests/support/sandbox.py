"""한 테스트가 쓰는 임시 작업 영역과, 사용자 환경에서 격리된 git 실행 환경.

테스트 받침이 지키는 약속:

- 네트워크를 쓰지 않는다. 원격은 모두 임시 디렉토리의 로컬 bare 저장소이고, 로컬 파일 전송 말고는
  전부 거부한다(실수로 쓴 https·ssh 주소가 접속을 시도하지 않고 바로 실패한다).
- 사용자의 전역 git 설정을 읽지도 바꾸지도 않는다. 전역 설정 자리에 임시 파일을 끼운다.
- 로컬 경로를 원격으로 하는 서브모듈 전송은 최근 git이 기본으로 막는다. 이 환경 안에서만 허용한다.
- 루트 저장소는 이 저장소의 추적 파일을 임시 디렉토리로 복사해 만든다.
  이 저장소의 `Justfile`을 직접 가리켜 실행하면 등록 명령이 이 작업 사본에 서브모듈을 만들기 때문이다.
- 임시 디렉토리 밖에서는 명령을 실행하지 않는다. 실행 위치(`cwd`)뿐 아니라 `git -C`, `--git-dir`,
  `--work-tree`, `just --justfile`, `--working-directory`가 가리키는 경로도 검사한다.
  임시 디렉토리 자체를 이 저장소 안에 만드는 것도 거부한다.
- 이 저장소의 가상환경(`uv run`이 남기는 `VIRTUAL_ENV`와 PATH 항목)이 샌드박스에 새지 않는다.
  샌드박스에서 `python3`를 직접 부르는 명령이 이 저장소의 의존성으로 도는 일을 막는다.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
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
[protocol]
	allow = never
[protocol "file"]
	allow = always
"""

# `uv run`이 실행 중인 환경을 알리려고 남기는 변수. 샌드박스 안의 명령에는 필요 없다.
_RUNNER_STATE_VARS = ("VIRTUAL_ENV", "UV", "UV_RUN_RECURSION_DEPTH")

# 경로를 받는 명령줄 인자. 실행 위치(`cwd`)와 별개로 명령이 일하는 곳을 바꾼다.
_GIT_PATH_OPTIONS = ("-C", "--git-dir", "--work-tree")
_JUST_PATH_OPTIONS = ("--justfile", "-f", "--working-directory", "-d")


class Sandbox:
    """임시 디렉토리 하나와 그 안에서만 도는 격리된 git 환경."""

    def __init__(self, base: Path) -> None:
        self.base = base.resolve()
        if self.base.is_relative_to(SOURCE_REPO):
            # just와 git은 위로 찾아 올라가 이 저장소의 Justfile과 .git을 쓰게 된다.
            raise AssertionError(f"임시 디렉토리는 이 저장소 밖에 있어야 한다: {self.base}")
        self._counter = 0

        config_dir = self.base / "_env"
        config_dir.mkdir()
        gitconfig = config_dir / "gitconfig"
        gitconfig.write_text(_GITCONFIG, encoding="utf-8")

        # 상위 프로세스가 물려준 GIT_*(예: GIT_DIR), JUST_* 와 실행 중인 가상환경의 흔적은 모두 버린다.
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("GIT_", "JUST_")) and k not in _RUNNER_STATE_VARS
        }
        env["PATH"] = _path_without_virtualenv(env.get("PATH", ""))
        env.update(
            GIT_CONFIG_GLOBAL=str(gitconfig),  # ~/.gitconfig 와 XDG 전역 설정을 대신한다
            GIT_CONFIG_NOSYSTEM="1",
            XDG_CONFIG_HOME=str(config_dir / "xdg"),  # ~/.config/git/ignore 같은 전역 파일도 읽지 않는다
            GIT_CEILING_DIRECTORIES=str(self.base),  # 저장소가 없는 샌드박스 디렉토리에서 위의 저장소를 찾지 않는다
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
        argv = [str(a) for a in args]
        for path in [cwd, *(cwd / p for p in _path_arguments(argv))]:  # 절대 경로 앞에서는 cwd가 무시된다
            if not path.resolve().is_relative_to(self.base):
                raise AssertionError(f"임시 디렉토리 밖에서는 실행하지 않는다: {path}")
        return subprocess.run(
            argv,
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

    def snapshot(self, repo: Path) -> dict[str, object]:
        """저장소가 바뀐 흔적을 모은다. 앞뒤의 스냅샷이 같으면 그 사이에 아무것도 바뀌지 않은 것이다.

        HEAD, 인덱스, 작업 트리 상태(추적하지 않는 파일 포함), `.gitmodules`, 로컬 서브모듈 설정,
        `.git/modules` 안의 서브모듈 저장소, `projects/`의 항목을 본다. 서브모듈 안의 상태는 보지 않는다.
        """
        git_dir = Path(self.git("rev-parse", "--absolute-git-dir", cwd=repo).stdout.strip())
        gitmodules = repo / ".gitmodules"
        modules_dir = git_dir / "modules"
        return {
            "head": self.head(repo),
            "index": self.git("ls-files", "--stage", cwd=repo).stdout,
            "status": self.git("status", "--porcelain", "--untracked-files=all", cwd=repo, check=False).stdout,
            "gitmodules": gitmodules.read_text(encoding="utf-8") if gitmodules.exists() else None,
            "config": self.git("config", "--local", "--get-regexp", r"^submodule\.", cwd=repo, check=False).stdout,
            "modules": sorted(  # 서브모듈 저장소마다 HEAD와 objects가 함께 있다
                str(p.parent.relative_to(git_dir))
                for p in modules_dir.rglob("HEAD")
                if (p.parent / "objects").is_dir()
            ),
            "projects": sorted(p.name for p in (repo / "projects").iterdir()) if (repo / "projects").exists() else None,
        }

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

    def root(self, *, name: str = "root", source: Path = SOURCE_REPO) -> RootRepo:
        """루트 저장소를 만든다. `source`(기본은 이 저장소)의 추적 파일을 복사해 커밋하고 bare 원격에 푸시한다.

        한 테스트에서 둘 이상 만들려면 `name`을 달리 준다.
        """
        return RootRepo(self, name, source)


def _which_or_fail(tool: str) -> str:
    found = shutil.which(tool)
    if found is None:
        raise RuntimeError(f"테스트에 필요한 도구가 없다: {tool}")
    return found


def _path_without_virtualenv(path: str) -> str:
    """PATH에서 지금 도는 가상환경의 `bin`을 뺀다. 가상환경 밖에서 돌 때는 그대로 둔다(`/usr/bin`을 뺄 수 없다)."""
    if sys.prefix == sys.base_prefix:
        return path
    venv_bin = (Path(sys.prefix) / "bin").resolve()
    return os.pathsep.join(p for p in path.split(os.pathsep) if not p or Path(p).resolve() != venv_bin)


def _path_arguments(argv: list[str]) -> list[str]:
    """명령줄에서 명령이 일할 위치를 바꾸는 경로 인자를 찾는다. git은 서브커맨드 앞의 전역 옵션만 본다."""
    found: list[str] = []
    tool = Path(argv[0]).name
    if tool == "git":
        i = 1
        while i < len(argv) and argv[i].startswith("-"):
            name, has_value, value = argv[i].partition("=")
            if name in _GIT_PATH_OPTIONS:
                if has_value:
                    found.append(value)
                elif i + 1 < len(argv):
                    found.append(argv[i + 1])
                    i += 1
            elif name == "-c" and not has_value:
                i += 1  # `-c <이름=값>`의 값은 건너뛴다
            i += 1
    elif tool == "just":
        for i, arg in enumerate(argv[1:], start=1):
            name, has_value, value = arg.partition("=")
            if name in _JUST_PATH_OPTIONS:
                if has_value:
                    found.append(value)
                elif i + 1 < len(argv):
                    found.append(argv[i + 1])
            elif arg[:2] in ("-f", "-d") and not arg.startswith("--") and len(arg) > 2:
                found.append(arg[2:])  # `-fJustfile`처럼 붙여 쓴 경우
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

    def set_default_branch(self, branch: str) -> None:
        """원격의 기본 브랜치(HEAD가 가리키는 브랜치)를 바꾼다. 그 브랜치는 이미 있어야 한다."""
        self._sandbox.git("symbolic-ref", "HEAD", f"refs/heads/{branch}", cwd=self.url)

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

    def __init__(self, sandbox: Sandbox, name: str, source: Path) -> None:
        self._sandbox = sandbox
        self._name = name
        self._clones = 0
        self.origin = sandbox.new_dir("remotes", f"{name}.git")
        self.work = sandbox.new_dir("author", name)

        sandbox.git("init", "--bare", "--initial-branch=main", self.origin, cwd=self.origin)
        sandbox.git("init", "--initial-branch=main", cwd=self.work)
        copy_tracked_files(sandbox, source, self.work)
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
        dest = self._sandbox.base / "clones" / f"{self._name}-{self._clones}"
        dest.parent.mkdir(exist_ok=True)
        self._sandbox.git("clone", self.origin, dest, cwd=dest.parent)
        return dest


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def copy_tracked_files(sandbox: Sandbox, src: Path, dest: Path, *, under: str | None = None) -> None:
    """`src` 저장소가 추적하는 파일을 `dest`로 복사한다. 작업 트리의 현재 내용을 복사한다.

    `under`를 주면 그 디렉토리 아래의 파일만, 그 경로를 뗀 위치에 복사한다(예: `under="onto"`이면 `onto/x`가 `dest/x`가 된다).

    서브모듈 등록(gitlink와 `.gitmodules`)은 복사하지 않는다. 받아 쓰는 루트는 자기 지식 저장소의
    등록을 커밋해 두는데(ADR 0007), 이를 가져오면 샌드박스가 실제 원격으로 나가려 한다.
    샌드박스 루트는 등록이 없는 깨끗한 루트다.

    `git add`하지 않은 새 파일은 추적 파일이 아니라서 복사되지 않는다.
    """
    # `src`를 읽기만 하므로 임시 디렉토리 검사를 거치지 않고 격리된 환경으로 직접 실행한다.
    listing = subprocess.run(
        ["git", "ls-files", "--stage", "-z"],
        cwd=src,
        env=sandbox.env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for entry in filter(None, listing.split("\0")):
        meta, rel = entry.split("\t", 1)
        if meta.split()[0] == "160000" or rel == ".gitmodules":
            continue
        if under is not None and not rel.startswith(f"{under}/"):
            continue
        source = src / rel
        if not (source.exists() or source.is_symlink()):
            continue  # 지워졌지만 아직 스테이지하지 않은 파일
        target = dest / (rel if under is None else rel[len(under) + 1 :])
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            target.symlink_to(os.readlink(source))
        else:
            shutil.copy2(source, target)
