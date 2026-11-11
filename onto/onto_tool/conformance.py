"""최신화 뒤의 구조 제약 보고: 공통 어휘가 바뀐 뒤 어긋나게 된 페이지를 알린다.

최신화는 지식 저장소의 도구와 공통 어휘(`.onto/vocab/`)를 루트의 것으로 바꾼다. 어휘를 올리면 이전에 통과한 페이지가 새 구조 제약에 걸릴 수 있다
(필수 속성이 늘었다, 관계의 도메인이 좁아졌다, 키가 없어졌다). 페이지는 저장소 소유 파일이라 최신화가 고치지 않고, 고칠 곳을 알린다.

보고하는 것은 공통 어휘와 구조 제약(`vocab/shapes.ttl`)이 정하는 검사 항목(`VOCABULARY_CHECKS`)의 문제뿐이다. 낡음이나 인덱스처럼 어휘와 무관한
문제는 `validate`가 알린다. 저장소의 규칙이 끈 항목은 보고하지 않고 심각도는 규칙을 따른다(`checks.validate`와 같다). 어떤 파일도 고치지 않는다.
검사는 최신화한 지식 저장소만 컴파일해서 한다. 루트의 도구가 루트의 공통 어휘로 검사하는 것이므로 지식 저장소에 막 복사한 사본과 같은 어휘다.
"""

from collections.abc import Collection

from .checks import Finding, validate
from .checks.catalog import (
    DISALLOWED_CLASS,
    INVALID_VALUE,
    MISSING_PROPERTY,
    RELATION_DOMAIN,
    RELATION_RANGE,
    REVERSE_RELATION,
    UNDEFINED_KEY,
)
from .compiler import compile_workspace
from .rules import Rules
from .workspace import SubsetWorkspace, Workspace

# 공통 어휘와 구조 제약이 정하는 검사 항목. 어휘를 올리면 이전에 통과한 페이지가 걸릴 수 있는 것이다.
VOCABULARY_CHECKS = frozenset(
    check.name for check in (MISSING_PROPERTY, INVALID_VALUE, DISALLOWED_CLASS, RELATION_DOMAIN, RELATION_RANGE, UNDEFINED_KEY, REVERSE_RELATION)
)


def nonconforming(workspace: Workspace, directories: Collection[str], root_rules: Rules) -> list[Finding]:
    """`directories`(서브모듈 디렉토리 이름)의 지식 저장소에서 구조 제약에 어긋난 페이지의 문제. 지식 저장소, 파일, 검사 항목 순이다."""
    compiled = compile_workspace(SubsetWorkspace(workspace, directories))
    return [finding for finding in validate(compiled, root_rules) if finding.check in VOCABULARY_CHECKS]
