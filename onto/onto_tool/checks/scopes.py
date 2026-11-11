"""공유 범위(`ontology.yaml`의 `scope`)를 훑는 검사 항목: 값이 맞는지, 교차 참조가 더 좁은 범위나 다른 팀의 저장소를 가리키지 않는지.

공유 범위를 지키는 안전장치라 이 모듈의 항목은 모두 루트 전용이다. 지식 저장소의 규칙이 끄거나 심각도를 바꿀 수 없다.

- 공유 범위를 적지 않은 지식 저장소는 가장 좁은 `private`으로 본다.
- 값이 틀린 지식 저장소는 범위를 알 수 없어, 그 저장소가 가리키거나 가리켜지는 참조는 비교하지 않는다. 값 오류가 따로 보고된다.
- 참조가 가리키는 엔티티가 있는지는 따지지 않는다. 없는 엔티티를 가리켜도 참조에 적은 저장소 이름이 드러나기 때문이다.
- 참조는 `name`으로 가리키는 저장소를 찾는다(엔티티의 IRI가 `name`으로 만들어진다). 같은 `name`을 쓰는 저장소가 여럿이면 모두와 비교한다.
- `ontology.yaml`을 읽을 수 없거나 온톨로지 층이 없는 저장소는 범위를 알 수 없어 건너뛴다. 그 문제가 따로 보고된다.
"""

from collections.abc import Iterator

from .. import scope
from ..compiler import Compiled
from ..rules import RuleSet
from ..scope import Scope, ScopeError
from .catalog import INVALID_SCOPE, SCOPE_VIOLATION
from .model import Issue


def find(compiled: Compiled, rules: RuleSet) -> Iterator[Issue]:
    scopes: dict[str, Scope] = {}  # 지식 저장소의 서브모듈 디렉토리 이름 -> 공유 범위. 범위를 알 수 없는 저장소는 없다
    for record in compiled.records:
        if not record.has_layer or record.name is None:
            continue
        if not record.scope_declared:
            scopes[record.directory] = scope.DEFAULT
            continue
        try:
            scopes[record.directory] = scope.parse(record.scope)
        except ScopeError as exc:
            yield Issue(
                INVALID_SCOPE,
                record.yaml_file,
                f"`scope`의 값 `{record.scope}`가 공유 범위가 아니다: {exc}. {scope.FORMS} 중 하나로 적는다",
            )

    by_name: dict[str, list[str]] = {}  # `name` -> 그 `name`을 쓰는 저장소의 디렉토리 이름
    for record in compiled.records:
        if record.directory in scopes and record.name is not None:
            by_name.setdefault(record.name, []).append(record.directory)

    for record in compiled.records:
        source = scopes.get(record.directory)
        if source is None:
            continue
        for page in record.pages:
            for key, target in page.relations():
                repository, separator, _ = target.partition(":")
                if not separator:
                    continue
                for directory in by_name.get(repository.strip(), ()):
                    if problem := source.problem_referencing(scopes[directory]):
                        yield Issue(SCOPE_VIOLATION, page.file, f"`{key}`의 값 `{target}`: 지식 저장소 `{directory}`는 {problem}")
