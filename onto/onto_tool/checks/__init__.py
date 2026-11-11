"""스크립트 검사: 컴파일한 결과를 검사 항목마다 훑어 문제를 모은다. 결과가 항상 같은 기계적 검사다.

검사 항목은 `catalog`에 이름과 기본 심각도로 정의되어 있고, 같은 패키지의 모듈이 항목을 돌려 `Issue`를 찾는다.
`validate`가 문제마다 항목의 심각도(규칙이 덮어쓰면 그 값)를 붙여 보고할 목록을 만든다. 어떤 파일도 고치지 않는다.
"""

from collections.abc import Collection, Mapping
from types import MappingProxyType

from ..compiler import Compiled
from . import duplicates, frontmatter, layout, orphans, problems, references, repositories, structure
from .catalog import BY_NAME, CHECKS
from .model import Check, Finding, Severity, repository_of

__all__ = ["BY_NAME", "CHECKS", "Check", "Finding", "Severity", "validate"]

# 검사를 돌리는 모듈. 모듈마다 `find(compiled)`가 문제를 찾는다.
_MODULES = (problems, repositories, frontmatter, layout, references, orphans, duplicates, structure)


def validate(
    compiled: Compiled,
    *,
    severities: Mapping[str, Severity] = MappingProxyType({}),
    disabled: Collection[str] = (),
) -> list[Finding]:
    """`compiled`를 모든 검사 항목으로 검사해 보고할 문제를 돌려준다.

    `severities`는 항목 이름 -> 심각도로 기본 심각도를 덮어쓰고, `disabled`에 든 이름의 항목은 보고하지 않는다.
    규칙 파일은 이 두 값을 채워 넘긴다. 문제는 지식 저장소, 페이지, 검사 항목, 설명 순으로 정렬한다.
    """
    findings: set[Finding] = set()
    for module in _MODULES:
        for issue in module.find(compiled):
            if issue.check.name in disabled:
                continue
            severity = severities.get(issue.check.name, issue.check.severity)
            findings.add(Finding(severity, repository_of(issue.file), issue.file, issue.check.name, issue.message))
    return sorted(findings, key=lambda f: (f.repository, f.file, f.check, f.message))
