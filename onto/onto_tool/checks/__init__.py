"""스크립트 검사: 컴파일한 결과를 검사 항목마다 훑어 문제를 모은다. 결과가 항상 같은 기계적 검사다.

검사 항목은 `catalog`에 이름으로 정의되어 있고, 같은 패키지의 모듈이 항목을 돌려 `Issue`를 찾는다.
`validate`가 문제마다 규칙(`rules.yaml`, 지식 저장소가 덮어쓰면 그 값)이 정한 켬/끔과 심각도를 붙여 보고할 목록을 만든다.
어떤 파일도 고치지 않는다.

지식 저장소 안에서 돌리면(`workspace.Scope.REPOSITORY`) 그 저장소만 검사한다. 여러 지식 저장소에 걸친 검사 항목(`Check.across_repositories`: 교차 참조,
공유 범위, 저장소 간 중복)은 건너뛴다. 교차 참조의 대상은 다른 저장소에 있어 이 저장소만으로는 알 수 없기 때문이다. 루트 저장소가 전체를 합쳐 검사한다.
"""

from collections.abc import Collection
from pathlib import Path

from .. import rules
from ..compiler import Compiled, Problem
from ..rules import RuleSet, Rules
from ..workspace import Scope
from . import (
    duplicates,
    freshness,
    frontmatter,
    indexes,
    layout,
    links,
    orphans,
    overrides,
    problems,
    references,
    repositories,
    scopes,
    structure,
)
from .catalog import BY_NAME, CHECKS
from .model import Check, Finding, Severity

__all__ = [
    "ACROSS_REPOSITORIES_CHECKS",
    "BY_NAME",
    "CHECKS",
    "Check",
    "Finding",
    "Severity",
    "applied_rules",
    "load_root_rules",
    "rule_set",
    "split_problems",
    "validate",
]

# 검사를 돌리는 모듈. 모듈마다 `find(compiled, rule_set)`가 문제를 찾는다.
_MODULES = (
    problems,
    repositories,
    overrides,
    frontmatter,
    layout,
    indexes,
    references,
    scopes,
    links,
    orphans,
    duplicates,
    freshness,
    structure,
)

# 지식 저장소의 규칙이 덮어쓸 수 없는 검사 항목
ROOT_ONLY_CHECKS: Collection[str] = tuple(check.name for check in CHECKS if check.root_only)

# 여러 지식 저장소에 걸친 검사 항목. 지식 저장소 안에서는 건너뛴다.
ACROSS_REPOSITORIES_CHECKS: tuple[str, ...] = tuple(check.name for check in CHECKS if check.across_repositories)


def load_root_rules(path: Path) -> Rules:
    """루트 기본 규칙 파일을 읽는다. 모든 검사 항목이 파일에 있어야 한다. 틀리면 `rules.RulesError`다."""
    return rules.load_root_rules(path, known_checks=BY_NAME)


def rule_set(root: Rules, overrides_by_repository: dict[str, object]) -> RuleSet:
    """루트 기본 규칙과 지식 저장소(서브모듈 디렉토리 이름)별 `rules` 값으로 저장소마다 적용할 규칙을 만든다."""
    return rules.build_rule_set(root, overrides_by_repository, known_checks=BY_NAME, root_only_checks=ROOT_ONLY_CHECKS)


def applied_rules(compiled: Compiled, root_rules: Rules) -> RuleSet:
    """지식 저장소마다 적용할 규칙. 저장소의 `ontology.yaml`이 덮어쓰지 않은 값은 `root_rules`다. 틀린 덮어쓰기는 `problems`에 든다."""
    return rule_set(root_rules, {record.directory: record.rules for record in compiled.records if record.rules is not None})


def split_problems(compiled: Compiled, applied: RuleSet) -> tuple[list[Problem], list[Problem]]:
    """컴파일이 읽지 못한 파일의 문제를 `(멈추게 하는 것, 건너뛰는 것)`으로 나눈다.

    멈추게 하는 것은 그 문제가 있는 지식 저장소의 규칙에서 검사 항목이 켜져 있고 심각도가 오류인 문제다. 루트 전용 항목은 루트 기본
    규칙의 값이다. `build`, `query`, `status`가 쓴다. 경고이거나 꺼진 항목의 문제는 건너뛴다. 컴파일은 읽을 수 없는 파일을 이미 그래프에서
    뺐으므로 건너뛴다는 것은 멈추지 않는다는 뜻이다. `validate`는 켜진 오류가 하나라도 있으면 0이 아닌 종료 코드로 끝나므로,
    `validate`가 0으로 끝나는 지식 저장소의 읽기 문제로 `build`가 멈추는 일은 없다(켜진 오류의 읽기 문제가 있으면 둘 다 멈춘다).
    """
    blocking: list[Problem] = []
    skipped: list[Problem] = []
    for problem in compiled.problems:
        rule = applied.of(compiled.repository_of(problem.file)).checks[problem.check]
        (blocking if rule.stops_build else skipped).append(problem)
    return blocking, skipped


def validate(compiled: Compiled, root_rules: Rules) -> list[Finding]:
    """`compiled`를 모든 검사 항목으로 검사해 보고할 문제를 돌려준다.

    문제의 켬/끔과 심각도는 그 문제가 있는 지식 저장소의 규칙을 따른다. 저장소의 `ontology.yaml`이 덮어쓰지 않은 값은
    `root_rules`다. 꺼진 항목의 문제는 보고하지 않는다. 문제는 지식 저장소, 페이지, 검사 항목, 설명 순으로 정렬한다.
    지식 저장소 안에서는 여러 지식 저장소에 걸친 검사 항목(`ACROSS_REPOSITORIES_CHECKS`)의 문제를 보고하지 않는다.
    """
    applied = applied_rules(compiled, root_rules)
    findings: set[Finding] = set()
    for module in _MODULES:
        for issue in module.find(compiled, applied):
            if compiled.scope is Scope.REPOSITORY and issue.check.across_repositories:
                continue
            repository = compiled.repository_of(issue.file)
            rule = applied.of(repository).checks[issue.check.name]
            if rule.enabled:
                findings.add(Finding(Severity.from_rule(rule.severity), repository, issue.file, issue.check.name, issue.message))
    return sorted(findings, key=lambda f: (f.repository, f.file, f.check, f.message))
