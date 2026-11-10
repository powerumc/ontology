"""테스트 받침 자체의 약속: 격리된 환경, 임시 디렉토리 안의 저장소, 이 저장소를 건드리지 않음."""

import subprocess
from pathlib import Path

import pytest

from support.sandbox import SOURCE_REPO


def _tracked_files(sandbox, repo: Path) -> set[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=repo, env=sandbox.env, capture_output=True, text=True, check=True
    ).stdout
    return {p for p in out.split("\0") if p}


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


def test_루트_저장소는_이_저장소의_추적_파일을_복사해_만든다(sandbox):
    work = sandbox.root().work

    assert _tracked_files(sandbox, work) == _tracked_files(sandbox, SOURCE_REPO)
    assert (work / "Justfile").read_bytes() == (SOURCE_REPO / "Justfile").read_bytes()


def test_서브모듈_등록은_임시_저장소에서만_일어나고_이_저장소에는_남지_않는다(sandbox):
    sandbox.root().register(sandbox.knowledge_remote("billing"))

    assert not (SOURCE_REPO / ".gitmodules").exists()
    assert not (SOURCE_REPO / "projects").exists()
    staged = subprocess.run(
        ["git", "ls-files", "--stage"], cwd=SOURCE_REPO, env=sandbox.env, capture_output=True, text=True, check=True
    ).stdout
    assert "160000" not in {line.split()[0] for line in staged.splitlines()}  # 서브모듈(gitlink)이 없다


def test_임시_디렉토리_밖에서는_명령을_실행하지_않는다(sandbox):
    """이 저장소의 `Justfile`을 직접 가리켜 실행하면 등록 명령이 이 작업 사본에 서브모듈을 만든다."""
    with pytest.raises(AssertionError):
        sandbox.just("--list", cwd=SOURCE_REPO)
