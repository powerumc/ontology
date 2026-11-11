""".gitignore: 빌드 산출물과 `.claude_config/`를 제외하고, `.envrc`는 건드리지 않는다."""

import pytest


def _ignored(sandbox, root, path):
    return sandbox.git("check-ignore", "--quiet", path, cwd=root, check=False).returncode == 0


@pytest.mark.parametrize(
    "path",
    [
        ".claude_config/settings.json",
        ".venv/bin/python",
        "tests/__pycache__/conftest.cpython-313.pyc",
        "tests/support/module.pyc",
        ".pytest_cache/README.md",
        "dist/ontology.whl",
        "build/lib/x.py",
        "onto.egg-info/PKG-INFO",
        "onto/.build/graph.ttl",
        "onto/.venv/bin/python",
    ],
)
def test_gitignore가_빌드_산출물과_claude_config를_제외한다(sandbox, path):
    root = sandbox.root().work

    assert _ignored(sandbox, root, path)


def test_gitignore가_envrc를_건드리지_않는다(sandbox):
    root = sandbox.root().work

    assert not _ignored(sandbox, root, ".envrc")


def test_gitignore가_디렉토리가_아닌_심볼릭_링크_claude_config도_제외한다(sandbox):
    """실제 작업 사본의 `.claude_config`는 디렉토리가 아니라 설정 디렉토리를 가리키는 심볼릭 링크다."""
    root = sandbox.root().work
    (root / ".claude_config").symlink_to(sandbox.new_dir("elsewhere", "claude-profile"))

    assert _ignored(sandbox, root, ".claude_config")
    assert ".claude_config" not in sandbox.git("status", "--porcelain", cwd=root).stdout


@pytest.mark.parametrize("path", ["onto/build/x.py", "onto/dist/x.py", "tests/build/x.py"])
def test_gitignore는_build와_dist를_루트에서만_제외한다(sandbox, path):
    """하위 디렉토리의 `build/`는 코드일 수 있다. 조용히 무시되면 `onto sync`가 오류 없이 빠뜨린다."""
    root = sandbox.root().work

    assert not _ignored(sandbox, root, path)
