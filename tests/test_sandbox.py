"""테스트 받침 자체의 약속: 격리된 환경, 임시 디렉토리 안의 저장소, 이 저장소를 건드리지 않음."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from support.sandbox import SOURCE_REPO, Sandbox, copy_tracked_files


def _git_at(sandbox, repo: Path, *args: str) -> str:
    """이 저장소처럼 임시 디렉토리 밖에 있는 저장소를 읽기만 한다(받침의 실행 검사를 거치지 않는다)."""
    return subprocess.run(
        ["git", *args], cwd=repo, env=sandbox.env, capture_output=True, text=True, check=True
    ).stdout


def _tracked_files(sandbox, repo: Path) -> set[str]:
    return {p for p in _git_at(sandbox, repo, "ls-files", "-z").split("\0") if p}


def _registration_state(sandbox, repo: Path) -> dict:
    """서브모듈 등록의 흔적. 등록을 하면 어느 하나는 바뀐다."""
    gitmodules = repo / ".gitmodules"
    config = subprocess.run(
        ["git", "config", "--local", "--get-regexp", r"^submodule\."],
        cwd=repo, env=sandbox.env, capture_output=True, text=True,
    ).stdout
    return {
        "index": _git_at(sandbox, repo, "ls-files", "--stage"),
        "gitmodules": gitmodules.read_text(encoding="utf-8") if gitmodules.exists() else None,
        "config": config,
        "projects": sorted(p.name for p in (repo / "projects").iterdir()) if (repo / "projects").exists() else None,
    }


# --- 격리된 환경 ------------------------------------------------------------


def test_테스트의_git은_사용자의_전역_설정과_시스템_설정을_읽지_않는다(sandbox):
    work = sandbox.root().work

    effective_global = sandbox.git("config", "--global", "--list", cwd=work).stdout
    test_config = sandbox.git("config", "--list", "--file", sandbox.base / "_env" / "gitconfig", cwd=work).stdout
    scopes = {
        line.split("\t", 1)[0] for line in sandbox.git("config", "--list", "--show-scope", cwd=work).stdout.splitlines()
    }

    assert effective_global == test_config  # 전역 설정 자리에 있는 것은 테스트가 쓴 파일뿐이다
    assert scopes <= {"global", "local"}  # 시스템 설정은 없다


def test_테스트의_git은_로컬_경로_원격으로_서브모듈을_붙일_수_있다(sandbox):
    root = sandbox.root()
    knowledge = sandbox.knowledge_remote("billing")

    root.register(knowledge)

    assert (root.work / "projects" / "billing" / "README.md").is_file()


@pytest.mark.parametrize("url", ["https://example.invalid/team/repo.git", "git@example.invalid:team/repo.git"])
def test_네트워크_원격은_접속을_시도하기_전에_거부된다(sandbox, url):
    """로컬 파일 전송만 허용한다. 실수로 쓴 https·ssh 주소가 실제 네트워크로 나가지 않는다."""
    result = sandbox.git("ls-remote", url, cwd=sandbox.base, check=False)

    assert result.returncode != 0
    assert "not allowed" in result.stderr


def test_테스트_환경에는_이_저장소의_가상환경이_새지_않는다(sandbox):
    """샌드박스에서 `python3`를 직접 부르는 명령이 이 저장소의 `.venv`로 돌면 테스트가 거짓으로 통과한다."""
    leaked = {"VIRTUAL_ENV", "UV", "UV_RUN_RECURSION_DEPTH"} & set(sandbox.env)
    in_venv = sys.prefix != sys.base_prefix
    path_entries = [Path(p).resolve() for p in sandbox.env["PATH"].split(os.pathsep) if p]

    assert not leaked
    if in_venv:
        assert (Path(sys.prefix) / "bin").resolve() not in path_entries


# --- 임시 디렉토리 안에서만 -------------------------------------------------


def test_루트_저장소는_이_저장소의_추적_파일을_복사해_만든다(sandbox):
    work = sandbox.root().work

    assert _tracked_files(sandbox, work) == _tracked_files(sandbox, SOURCE_REPO)
    assert (work / "Justfile").read_bytes() == (SOURCE_REPO / "Justfile").read_bytes()


def test_추적_파일_복사는_하위_디렉토리만_접두어를_떼고_복사하고_심볼릭_링크와_지워진_파일을_다룬다(sandbox):
    """`onto/`를 지식 저장소의 `.onto/`로 복사하는 것과 같은 복사. 루트 복사와 같은 함수를 쓴다."""
    work = sandbox.root().work
    (work / "onto" / "link").symlink_to("Justfile")
    (work / "onto" / "gone.txt").write_text("지울 파일\n", encoding="utf-8")
    sandbox.git("add", "onto/link", "onto/gone.txt", cwd=work)
    (work / "onto" / "gone.txt").unlink()  # 지웠지만 아직 스테이지하지 않았다
    dest = sandbox.new_dir("copies", "onto")

    copy_tracked_files(sandbox, work, dest, under="onto")

    assert (dest / "Justfile").read_bytes() == (work / "onto" / "Justfile").read_bytes()
    assert (dest / "link").is_symlink() and os.readlink(dest / "link") == "Justfile"
    assert not (dest / "gone.txt").exists()
    assert not (dest / "onto").exists() and not (dest / "tests").exists()  # 접두어를 떼고, 그 밖의 파일은 복사하지 않는다


def test_서브모듈_등록은_임시_저장소에서만_일어나고_이_저장소에는_남지_않는다(sandbox):
    before = _registration_state(sandbox, SOURCE_REPO)

    sandbox.root().register(sandbox.knowledge_remote("billing"))

    assert _registration_state(sandbox, SOURCE_REPO) == before


def test_받아_쓰는_루트처럼_서브모듈_등록이_커밋된_저장소에서도_등록_없는_깨끗한_루트를_만든다(sandbox):
    """ADR 0007: 받아 쓰는 루트는 같은 코드에 서브모듈 등록을 커밋한다. 그 등록을 샌드박스로 가져오면 안 된다."""
    adopted = sandbox.root(name="adopted")
    adopted.register(sandbox.knowledge_remote("billing"))

    copy = sandbox.root(name="copy", source=adopted.work)

    state = _registration_state(sandbox, copy.work)
    assert (copy.work / "Justfile").is_file()
    assert state["gitmodules"] is None
    assert state["config"] == ""
    assert state["projects"] is None
    assert "160000" not in {line.split()[0] for line in state["index"].splitlines()}


@pytest.mark.parametrize(
    "args",
    [
        ["-C", SOURCE_REPO, "status"],
        [f"--git-dir={SOURCE_REPO / '.git'}", "status"],
        ["--work-tree", SOURCE_REPO, "status"],
        ["-c", "core.pager=cat", "-C", SOURCE_REPO, "status"],
    ],
)
def test_임시_디렉토리_밖을_가리키는_git_인자를_거부한다(sandbox, args):
    with pytest.raises(AssertionError):
        sandbox.git(*args, cwd=sandbox.base)


@pytest.mark.parametrize(
    "options",
    [
        ["--justfile", SOURCE_REPO / "Justfile"],
        [f"--justfile={SOURCE_REPO / 'Justfile'}"],
        ["-f", SOURCE_REPO / "Justfile"],
        ["--working-directory", SOURCE_REPO],
        ["-d", SOURCE_REPO],
    ],
)
def test_임시_디렉토리_밖을_가리키는_just_인자를_거부한다(sandbox, options):
    """just는 `--justfile`을 받으면 그 파일의 디렉토리에서 레시피를 실행한다. cwd가 임시 디렉토리여도 소용없다."""
    with pytest.raises(AssertionError):
        sandbox.just(*options, "--evaluate", cwd=sandbox.base)


def test_justfile_인자로_이_저장소의_Justfile을_넘겨도_거부한다(sandbox):
    with pytest.raises(AssertionError):
        sandbox.just("--evaluate", cwd=sandbox.base, justfile=SOURCE_REPO / "Justfile")


def test_임시_디렉토리_안을_가리키는_인자는_허용한다(sandbox):
    work = sandbox.root().work

    toplevel = sandbox.git("-C", work, "rev-parse", "--show-toplevel", cwd=sandbox.base)
    listing = sandbox.just("--list", cwd=sandbox.base, justfile=work / "Justfile")

    assert Path(toplevel.stdout.strip()) == work.resolve()
    assert listing.returncode == 0, listing.stderr


def test_임시_디렉토리_밖에서는_명령을_실행하지_않는다(sandbox):
    """이 저장소의 `Justfile`을 직접 가리켜 실행하면 등록 명령이 이 작업 사본에 서브모듈을 만든다."""
    with pytest.raises(AssertionError):
        sandbox.just("--list", cwd=SOURCE_REPO)


def test_임시_디렉토리를_이_저장소_안에_만들_수_없다(sandbox):
    """`--basetemp`를 저장소 안으로 주면 `just`가 위로 찾아 올라가 이 저장소의 `Justfile`을 쓰게 된다."""
    inside = SOURCE_REPO / "tests" / "_sandbox_must_not_exist"

    with pytest.raises(AssertionError):
        Sandbox(inside)

    assert not inside.exists()


def test_저장소가_없는_디렉토리에서_위로_찾아_올라가_바깥_저장소를_쓰지_않는다(sandbox):
    outer = sandbox.base / "outer"
    sandbox.git("init", outer, cwd=sandbox.base)
    inner_base = outer / "inner"
    inner_base.mkdir()
    inner = Sandbox(inner_base)
    plain = inner_base / "plain"
    plain.mkdir()

    result = inner.git("rev-parse", "--show-toplevel", cwd=plain, check=False)

    assert result.returncode != 0
