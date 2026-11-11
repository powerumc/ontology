"""관계의 값(참조)을 훑는 검사 항목: 깨진 참조와 등록되지 않은 지식 저장소.

그래프가 아니라 페이지의 frontmatter 원문에서 본다. 등록되지 않은 저장소 이름을 쓴 교차 참조는 컴파일에서 오류 없이
그 문자열 그대로의 IRI가 되어 그래프만으로는 깨진 참조와 구별되지 않기 때문이다. 참조를 엔티티의 IRI로 바꾸는 규칙은
컴파일과 같은 `iri.resolve_reference`를 쓴다.

가리키는 쪽의 사정으로 엔티티를 알 수 없을 때는 그 원인이 따로 보고되므로 참조를 문제 삼지 않는다.
- 읽을 수 없는 페이지: 있는 페이지로 친다(읽을 수 없는 파일로 한 번만 보고된다).
- `ontology.yaml`을 읽을 수 없는 지식 저장소: `name`을 몰라 엔티티의 IRI를 만들 수 없다. 그 저장소로 가는 참조는 건너뛴다.
"""

from collections.abc import Iterator

from ..compiler import PROJECT_IDENTIFIER, Compiled
from ..iri import entity_iri, resolve_reference
from ..keys import RELATION_KEYS
from ..rules import RuleSet
from .catalog import BROKEN_REFERENCE, UNREGISTERED_REPOSITORY
from .model import Issue


def find(compiled: Compiled, rules: RuleSet) -> Iterator[Issue]:
    records = compiled.records
    # 지식 저장소는 `name`으로도 서브모듈 디렉토리 이름으로도 가리킬 수 있다. 둘이 다르면 그 문제는 따로 보고한다.
    registered = {name for record in records for name in (record.directory, record.name) if name}
    unreadable = {record.directory for record in records if record.has_layer and record.name is None}
    without_layer = {record.directory for record in records if not record.has_layer}
    entities = {
        entity_iri(record.name, identifier)
        for record in records
        if record.name is not None
        for identifier in (PROJECT_IDENTIFIER, *(page.identifier for page in record.pages))
    }
    for record in records:
        if record.name is None:
            continue
        for page in record.pages:
            for key in RELATION_KEYS:
                value = (page.meta or {}).get(key)
                targets = value if isinstance(value, list) else [value]
                # 문자열이 아닌 값은 값의 종류가 맞지 않다고 컴파일이 이미 알렸다.
                for target in dict.fromkeys(t for t in targets if isinstance(t, str)):
                    where = f"`{key}`의 값 `{target}`"
                    repository, separator, _ = target.partition(":")
                    repository = repository.strip()
                    if separator and repository not in registered:
                        yield Issue(
                            UNREGISTERED_REPOSITORY,
                            page.file,
                            f"{where}: 등록되지 않은 지식 저장소를 가리킨다(저장소 이름: `{repository}`)",
                        )
                    elif separator and repository in unreadable:
                        continue
                    elif separator and repository in without_layer:
                        yield Issue(BROKEN_REFERENCE, page.file, f"{where}: 지식 저장소 `{repository}`에 온톨로지 층이 없다")
                    elif resolve_reference(record.name, target) not in entities:
                        yield Issue(BROKEN_REFERENCE, page.file, f"{where}: 가리키는 엔티티가 없다")
