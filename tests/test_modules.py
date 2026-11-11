"""just 모듈 뼈대: `git`, `repo`, `onto` 모듈을 인식하고, 명령은 어느 디렉토리에서 불러도 루트 저장소를 기준으로 돈다."""

import json
from pathlib import Path

import pytest

MODULES = ["git", "repo", "onto"]


def test_just가_git_repo_onto_모듈을_루트의_같은_이름_디렉토리에서_인식한다(sandbox):
    root = sandbox.root().work

    dump = sandbox.just("--dump", "--dump-format", "json", cwd=root, check=True).stdout
    modules = json.loads(dump)["modules"]

    assert sorted(modules) == sorted(MODULES)
    for name in MODULES:
        assert Path(modules[name]["source"]).resolve() == (root / name / "Justfile").resolve()


@pytest.mark.parametrize("module", MODULES)
def test_모듈의_명령은_어느_디렉토리에서_불러도_루트_저장소를_기준으로_돈다(sandbox, module):
    """뼈대 모듈에는 아직 명령이 없다. 모듈 파일 끝에 현재 디렉토리를 찍는 명령을 붙여 확인한다."""
    root = sandbox.root().work
    with (root / module / "Justfile").open("a", encoding="utf-8") as f:
        f.write("\n_where:\n    @pwd -P\n")
    (root / "docs" / "deeper").mkdir(parents=True)
    elsewhere = sandbox.new_dir("elsewhere", "any")

    from_root = sandbox.just(module, "_where", cwd=root)
    from_subdirectory = sandbox.just(module, "_where", cwd=root / "docs" / "deeper")
    from_other_directory = sandbox.just(module, "_where", cwd=elsewhere, justfile=root / "Justfile")

    for result in (from_root, from_subdirectory, from_other_directory):
        assert result.returncode == 0, result.stderr
        assert Path(result.stdout.strip()) == root.resolve()


def test_인자_없이_just_repo만_부르면_오류_없이_모듈의_명령_목록을_보여_준다(sandbox):
    root = sandbox.root().work

    result = sandbox.just("repo", cwd=root)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "add" in result.stdout and "remove" in result.stdout
