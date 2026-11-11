"""지식 저장소의 규칙 덮어쓰기(`ontology.yaml`의 `rules`)가 틀린 경우: 정의되지 않은 키, 값의 종류, 루트 전용 규칙을 덮어쓰려는 시도.

틀린 덮어쓰기는 통째로 쓰지 않는다. 그 저장소는 루트 기본 규칙으로 검사하고, 틀린 곳은 이유마다 문제 하나로 보고한다.
"""

from collections.abc import Iterator

from ..compiler import Compiled
from ..rules import RuleSet
from .catalog import INVALID_RULES
from .model import Issue


def find(compiled: Compiled, rules: RuleSet) -> Iterator[Issue]:
    for record in compiled.records:
        for reason in rules.problems.get(record.directory, ()):
            yield Issue(INVALID_RULES, record.yaml_file, reason)
