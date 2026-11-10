from pathlib import Path

import pytest

from support.sandbox import Sandbox


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    """테스트마다 새 임시 디렉토리와 격리된 git 환경을 준다."""
    return Sandbox(tmp_path)
