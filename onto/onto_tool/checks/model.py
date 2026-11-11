"""검사 항목과 그 결과의 모양."""

from dataclasses import dataclass
from enum import Enum

from ..workspace import PROJECTS_DIR


class Severity(Enum):
    ERROR = "오류"  # 반드시 고친다. 푸시 관문이 막는다.
    WARNING = "경고"  # 참고한다.


@dataclass(frozen=True)
class Check:
    """스크립트 검사의 검사 항목 하나. 이름으로 가리키고, 심각도를 항목마다 바꿀 수 있다."""

    name: str
    severity: Severity  # 기본 심각도. 규칙이 항목별로 덮어쓴다.
    summary: str  # 무엇을 잡는지 한 줄로


@dataclass(frozen=True)
class Issue:
    """검사 항목이 찾은 문제 하나. 심각도는 항목과 규칙이 정하므로 여기에 없다."""

    check: Check
    file: str  # 문제가 있는 페이지나 파일. 루트 저장소 기준 경로
    message: str


@dataclass(frozen=True)
class Finding:
    """보고하는 문제 하나."""

    severity: Severity
    repository: str  # 지식 저장소(서브모듈 디렉토리 이름)
    file: str
    check: str  # 검사 항목의 이름
    message: str


def repository_of(file: str) -> str:
    """`projects/<지식 저장소>/…` 경로가 속한 지식 저장소의 이름. 서브모듈 디렉토리 이름이다."""
    parts = file.split("/")
    return parts[1] if len(parts) > 1 and parts[0] == PROJECTS_DIR else ""
