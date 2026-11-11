from pathlib import Path

import pytest

from support.onto_cli import OntoCli, install_tool
from support.sandbox import Sandbox


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    """테스트마다 새 임시 디렉토리와 격리된 git 환경을 준다."""
    return Sandbox(tmp_path)


@pytest.fixture(scope="session")
def onto_tool_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """온톨로지 도구의 사본과 가상환경. 테스트 세션마다 한 번 만든다."""
    return install_tool(Sandbox(tmp_path_factory.mktemp("onto-tool")))


@pytest.fixture
def onto_cli(sandbox: Sandbox, onto_tool_dir: Path) -> OntoCli:
    """온톨로지 도구의 명령줄 진입점을 견본 페이지 디렉토리에 대고 실행한다."""
    return OntoCli(sandbox, onto_tool_dir)
