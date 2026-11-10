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
    ],
)
def test_gitignore가_빌드_산출물과_claude_config를_제외한다(sandbox, path):
    root = sandbox.root().work

    assert _ignored(sandbox, root, path)


def test_gitignore가_envrc를_건드리지_않는다(sandbox):
    root = sandbox.root().work

    assert not _ignored(sandbox, root, ".envrc")
