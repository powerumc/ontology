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
import signal
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

# 테스트용 `ssh`. 접속하지 않고, `ssh -G <호스트>`에는 `sandbox.ssh_alias`로 적어 둔 별칭 표로 `hostname`을 알려 준다.
# 사용자의 `~/.ssh/config`를 읽지 않으므로 테스트가 개발자의 ssh 설정에 따라 달라지지 않는다.
_SSH_STUB = """\
#!/bin/sh
here=$(dirname "$0")
if [ "${1:-}" != "-G" ]; then
    echo "테스트에서는 ssh로 접속하지 않는다" >&2
    exit 255
fi
shift
if [ "${1:-}" = "--" ]; then
    shift
fi
host=$1
real=$host
if [ -f "$here/aliases" ]; then
    while read -r alias target; do
        if [ "$alias" = "$host" ]; then
            real=$target
        fi
    done <"$here/aliases"
fi
echo "host $host"
echo "hostname $real"
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
        self._ssh_dir = config_dir / "bin"
        self._ssh_dir.mkdir()
        ssh = self._ssh_dir / "ssh"
        ssh.write_text(_SSH_STUB, encoding="utf-8")
        ssh.chmod(0o755)
        env["PATH"] = os.pathsep.join([str(self._ssh_dir), _path_without_virtualenv(env.get("PATH", ""))])
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
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """임시 디렉토리 안에서 명령을 실행한다. 출력은 텍스트로 모은다.

        `timeout`(초)을 넘기면 명령과 그 자손을 모두 죽이고 `subprocess.TimeoutExpired`를 던진다. `subprocess.run(timeout=…)`은 직접 자식(예: `uv run`)만 죽여서
        그 아래의 도구 프로세스가 CPU를 쓰며 남는다. 그래서 시간 상한을 준 명령은 새 프로세스 그룹에서 띄워 그룹째 죽인다.
        """
        cwd = Path(cwd).resolve()
        argv = [str(a) for a in args]
        for path in [cwd, *(cwd / p for p in _path_arguments(argv))]:  # 절대 경로 앞에서는 cwd가 무시된다
            if not path.resolve().is_relative_to(self.base):
                raise AssertionError(f"임시 디렉토리 밖에서는 실행하지 않는다: {path}")
        run_env = self.env if env is None else env
        if timeout is None:
            return subprocess.run(argv, cwd=cwd, env=run_env, capture_output=True, text=True, check=check)
        with subprocess.Popen(
            argv, cwd=cwd, env=run_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True
        ) as process:
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except BaseException:  # 시간 초과, 키보드 인터럽트: 자손까지 남기지 않는다
                _kill_group(process)
                process.communicate()
                raise
        if check and process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, argv, stdout, stderr)
        return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)

    def git(self, *args: str | Path, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
        return self.run(["git", *args], cwd=cwd, check=check)

    def head(self, repo: Path) -> str:
        """`repo`의 HEAD 커밋 해시."""
        return self.git("rev-parse", "HEAD", cwd=repo).stdout.strip()

    def branch(self, repo: Path) -> str | None:
        """`repo`가 체크아웃한 브랜치 이름. detached HEAD이면 `None`."""
        result = self.git("symbolic-ref", "--quiet", "--short", "HEAD", cwd=repo, check=False)
        return result.stdout.strip() if result.returncode == 0 else None

    def ssh_alias(self, alias: str, hostname: str) -> None:
        """테스트용 `ssh -G <alias>`가 `hostname`을 알려 주게 한다. ssh 설정의 `Host`·`HostName`에 해당한다."""
        with (self._ssh_dir / "aliases").open("a", encoding="utf-8") as f:
            f.write(f"{alias} {hostname}\n")

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

    def root(self, *, name: str = "root", source: Path = SOURCE_REPO, push_gate: bool = True) -> RootRepo:
        """루트 저장소를 만든다. `source`(기본은 이 저장소)의 추적 파일을 복사해 커밋하고 bare 원격에 푸시한다.

        한 테스트에서 둘 이상 만들려면 `name`을 달리 준다. `push_gate=False`이면 루트 기본 규칙(`onto/rules.yaml`)의 푸시 관문을
        끈 채로 첫 커밋을 만든다. 푸시 관문이 켜져 있으면 푸시 전에 스크립트 검사(컴파일과 구조 제약 검사)를 돌려 시간이 들고, 온톨로지 층이
        없는 견본은 검사에 막힌다. 관문과 상관없는 푸시 테스트가 그런 것을 치르지 않게 한다. 꺼 둬도 푸시는 꺼졌는지를 도구(`onto rules`)로 읽으므로
        도구의 가상환경은 만들어진다. 아끼는 것은 검사 한 번이다.
        """
        return RootRepo(self, name, source, push_gate=push_gate)


def _kill_group(process: subprocess.Popen[str]) -> None:
    """`process`가 이끄는 프로세스 그룹(`start_new_session`으로 띄운 것)을 모두 죽인다. 이미 끝났으면 아무것도 하지 않는다."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


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

    def commit(self, *, branch: str = "main", files: dict[str, str] | None = None) -> str:
        """`branch`에 커밋 하나를 쌓아 원격에 푸시하고 그 해시를 돌려준다.

        브랜치가 없으면 `main`의 끝에서 만든다. `files`(경로: 내용)를 주면 그 파일을 쓰거나 고친다.
        주지 않으면 매번 새 메모 파일(`docs/note-<n>.md`)을 더한다.
        """
        git = self._sandbox.git
        known = git("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", cwd=self.seed, check=False)
        if known.returncode == 0:
            git("checkout", branch, cwd=self.seed)
        else:
            git("checkout", "-b", branch, "main", cwd=self.seed)
        self._n += 1
        for rel, text in (files or {f"docs/note-{self._n}.md": f"# 메모 {self._n}\n"}).items():
            _write(self.seed / rel, text)
        git("add", "-A", cwd=self.seed)
        git("commit", "-m", f"note {self._n} on {branch}", cwd=self.seed)
        git("push", "origin", branch, cwd=self.seed)
        return git("rev-parse", "HEAD", cwd=self.seed).stdout.strip()


class RootRepo:
    """루트 저장소와 그 bare 원격. `work`는 소유자의 작업 사본이고 `origin`이 원격이다.

    새로 클론한 상태를 만들려면 `clone()`을 쓴다. 서브모듈 등록은 이 임시 저장소에서만 한다.
    """

    def __init__(self, sandbox: Sandbox, name: str, source: Path, *, push_gate: bool = True) -> None:
        self._sandbox = sandbox
        self._name = name
        self._clones = 0
        self.origin = sandbox.new_dir("remotes", f"{name}.git")
        self.work = sandbox.new_dir("author", name)

        sandbox.git("init", "--bare", "--initial-branch=main", self.origin, cwd=self.origin)
        sandbox.git("init", "--initial-branch=main", cwd=self.work)
        copy_tracked_files(sandbox, source, self.work)
        if not push_gate:
            _disable_push_gate(self.work / "onto" / "rules.yaml")
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

    def leave_gitmodules_unmerged(self, other: KnowledgeRemote) -> None:
        """작업 사본의 인덱스에서 `.gitmodules`를 병합 충돌 상태(스테이지 2·3)로 만든다. 커밋하지 않는다.

        두 브랜치가 따로 지식 저장소를 붙였다가 병합하면 생기는 상태다. `other`를 옆 브랜치에서 붙여 병합하고,
        작업 트리의 충돌 표시는 양쪽 내용을 이어 붙여 지우지만 `git add`는 하지 않는다. 현재 브랜치에는 다른 저장소가
        이미 등록되어 있어야 한다.
        """
        git = self._sandbox.git
        main = self._sandbox.branch(self.work)
        assert main is not None
        first = git("rev-list", "--max-parents=0", "HEAD", cwd=self.work).stdout.split()[0]  # 등록이 하나도 없던 커밋
        git("checkout", "-b", "side", first, cwd=self.work)
        git("submodule", "add", other.url, f"projects/{other.name}", cwd=self.work)
        git("commit", "-m", f"add {other.name} on side", cwd=self.work)
        git("checkout", main, cwd=self.work)
        git("merge", "side", cwd=self.work, check=False)
        ours = git("show", ":2:.gitmodules", cwd=self.work).stdout
        theirs = git("show", ":3:.gitmodules", cwd=self.work).stdout
        (self.work / ".gitmodules").write_text(ours + theirs, encoding="utf-8")

    def commit(self, files: dict[str, str]) -> str:
        """소유자의 작업 사본에서 `files`(경로: 내용)를 쓰거나 고친 커밋 하나를 쌓아 `main`을 푸시하고 그 해시를 돌려준다."""
        git = self._sandbox.git
        for rel, text in files.items():
            _write(self.work / rel, text)
        git("add", "-A", cwd=self.work)
        git("commit", "-m", f"edit {', '.join(files)}", cwd=self.work)
        git("push", "origin", "main", cwd=self.work)
        return self._sandbox.head(self.work)

    def clone(self) -> Path:
        """원격에서 새로 클론한다. 서브모듈은 초기화하지 않는다. 새 기기에서 받은 직후의 상태다."""
        self._clones += 1
        dest = self._sandbox.base / "clones" / f"{self._name}-{self._clones}"
        dest.parent.mkdir(exist_ok=True)
        self._sandbox.git("clone", self.origin, dest, cwd=dest.parent)
        return dest

    def set_up_clone(self) -> Path:
        """원격에서 새로 클론하고 `just setup`까지 돌린다. 서브모듈이 추적 브랜치에 체크아웃된, 쓸 수 있는 작업 사본이다."""
        dest = self.clone()
        self._sandbox.just("setup", cwd=dest, check=True)
        return dest


def _disable_push_gate(rules_file: Path) -> None:
    """루트 기본 규칙 파일의 푸시 관문을 끈다."""
    text = rules_file.read_text(encoding="utf-8")
    gate_on = "push-gate:\n  enabled: true\n"
    assert gate_on in text, "루트 기본 규칙에서 푸시 관문을 찾지 못했다"
    rules_file.write_text(text.replace(gate_on, "push-gate:\n  enabled: false\n"), encoding="utf-8")


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
