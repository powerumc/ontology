"""검사 항목과 그 결과의 모양."""

from dataclasses import dataclass
from enum import Enum


class Severity(Enum):
    ERROR = "오류"  # 반드시 고친다. 푸시 관문이 막는다.
    WARNING = "경고"  # 참고한다.

    @classmethod
    def from_rule(cls, text: str) -> "Severity":
        """규칙 파일이 적는 심각도(`error`, `warning`)."""
        return {"error": cls.ERROR, "warning": cls.WARNING}[text]


@dataclass(frozen=True)
class Check:
    """스크립트 검사의 검사 항목 하나. 이름으로 가리킨다. 켬/끔과 심각도는 규칙(`rules.yaml`)이 항목마다 정한다."""

    name: str
    summary: str  # 무엇을 잡는지 한 줄로
    # 루트 전용 항목. 루트 기본 규칙만 켬/끔과 심각도를 정하고, 지식 저장소의 `rules`가 덮어쓰려 하면 오류다(공유 범위 검사).
    root_only: bool = False
    # 여러 지식 저장소에 걸친 검사(교차 참조, 공유 범위, 저장소 간 중복). 지식 저장소 안에서는 그 저장소만 다루므로 건너뛴다.
    # 루트 저장소에서 전체를 합쳐 검사한다. 새 항목이 여러 저장소를 가로지르면 이 값을 켠다.
    across_repositories: bool = False


@dataclass(frozen=True)
class Issue:
    """검사 항목이 찾은 문제 하나. 심각도는 규칙이 정하므로 여기에 없다."""

    check: Check
    file: str  # 문제가 있는 페이지나 파일. 작업 공간 기준 경로(루트 저장소에서는 루트 기준, 지식 저장소 안에서는 그 저장소 기준)
    message: str


@dataclass(frozen=True)
class Finding:
    """보고하는 문제 하나."""

    severity: Severity
    repository: str  # 지식 저장소(서브모듈 디렉토리 이름)
    file: str
    check: str  # 검사 항목의 이름
    message: str
