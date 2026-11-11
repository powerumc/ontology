"""스크립트 검사: 컴파일한 결과를 검사 항목마다 훑어 문제를 모은다. 결과가 항상 같은 기계적 검사다.

검사 항목은 `catalog`에 이름으로 정의되어 있고, 같은 패키지의 모듈이 항목을 돌려 `Issue`를 찾는다.
`validate`가 문제마다 규칙(`rules.yaml`, 지식 저장소가 덮어쓰면 그 값)이 정한 켬/끔과 심각도를 붙여 보고할 목록을 만든다.
어떤 파일도 고치지 않는다.
"""

from collections.abc import Collection
from pathlib import Path

from .. import rules
from ..compiler import Compiled
from ..rules import RuleSet, Rules
from . import duplicates, frontmatter, indexes, layout, orphans, overrides, problems, references, repositories, structure
from .catalog import BY_NAME, CHECKS
from .model import Check, Finding, Severity, repository_of

__all__ = ["BY_NAME", "CHECKS", "Check", "Finding", "Severity", "load_root_rules", "rule_set", "validate"]

# 검사를 돌리는 모듈. 모듈마다 `find(compiled, rule_set)`가 문제를 찾는다.
_MODULES = (problems, repositories, overrides, frontmatter, layout, indexes, references, orphans, duplicates, structure)

# 지식 저장소의 규칙이 덮어쓸 수 없는 검사 항목
ROOT_ONLY_CHECKS: Collection[str] = tuple(check.name for check in CHECKS if check.root_only)


def load_root_rules(path: Path) -> Rules:
    """루트 기본 규칙 파일을 읽는다. 모든 검사 항목이 파일에 있어야 한다. 틀리면 `rules.RulesError`다."""
    return rules.load_root_rules(path, known_checks=BY_NAME)


def rule_set(root: Rules, overrides_by_repository: dict[str, object]) -> RuleSet:
    """루트 기본 규칙과 지식 저장소(서브모듈 디렉토리 이름)별 `rules` 값으로 저장소마다 적용할 규칙을 만든다."""
    return rules.build_rule_set(root, overrides_by_repository, known_checks=BY_NAME, root_only_checks=ROOT_ONLY_CHECKS)


def validate(compiled: Compiled, root_rules: Rules) -> list[Finding]:
    """`compiled`를 모든 검사 항목으로 검사해 보고할 문제를 돌려준다.

    문제의 켬/끔과 심각도는 그 문제가 있는 지식 저장소의 규칙을 따른다. 저장소의 `ontology.yaml`이 덮어쓰지 않은 값은
    `root_rules`다. 꺼진 항목의 문제는 보고하지 않는다. 문제는 지식 저장소, 페이지, 검사 항목, 설명 순으로 정렬한다.
    """
    applied = rule_set(root_rules, {record.directory: record.rules for record in compiled.records if record.rules is not None})
    findings: set[Finding] = set()
    for module in _MODULES:
        for issue in module.find(compiled, applied):
            repository = repository_of(issue.file)
            rule = applied.of(repository).checks[issue.check.name]
            if rule.enabled:
                findings.add(Finding(Severity.from_rule(rule.severity), repository, issue.file, issue.check.name, issue.message))
    return sorted(findings, key=lambda f: (f.repository, f.file, f.check, f.message))
