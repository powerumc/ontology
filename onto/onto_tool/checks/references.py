"""관계의 값(참조)을 훑는 검사 항목: 깨진 참조와 등록되지 않은 지식 저장소.

그래프가 아니라 페이지의 frontmatter 원문에서 본다. 등록되지 않은 저장소 이름을 쓴 교차 참조는 컴파일에서 오류 없이
그 문자열 그대로의 IRI가 되어 그래프만으로는 깨진 참조와 구별되지 않기 때문이다. 참조를 엔티티의 IRI로 바꾸는 규칙은
컴파일과 같은 `iri.resolve_reference`를 쓴다.
"""

from collections.abc import Iterator

from ..compiler import PROJECT_IDENTIFIER, Compiled
from ..iri import entity_iri, resolve_reference
from ..keys import RELATION_KEYS
from .catalog import BROKEN_REFERENCE, UNREGISTERED_REPOSITORY
from .model import Issue


def find(compiled: Compiled) -> Iterator[Issue]:
    # 지식 저장소는 `name`으로도 서브모듈 디렉토리 이름으로도 가리킬 수 있다. 둘이 다르면 그 문제는 따로 보고한다.
    registered = {name for record in compiled.records if record.has_layer for name in (record.directory, record.name) if name}
    # 읽을 수 없는 페이지도 있는 페이지다. 그 문제는 읽을 수 없는 파일로 한 번만 보고한다.
    entities = {
        entity_iri(record.name, identifier)
        for record in compiled.records
        if record.name is not None
        for identifier in (PROJECT_IDENTIFIER, *(page.identifier for page in record.pages))
    }
    for record in compiled.records:
        if record.name is None:
            continue
        for page in record.pages:
            for key in RELATION_KEYS:
                value = (page.meta or {}).get(key)
                targets = value if isinstance(value, list) else [value]
                # 문자열이 아닌 값은 값의 종류가 맞지 않다고 컴파일이 이미 알렸다.
                for target in dict.fromkeys(t for t in targets if isinstance(t, str)):
                    repository, separator, _ = target.partition(":")
                    if separator and repository.strip() not in registered:
                        yield Issue(
                            UNREGISTERED_REPOSITORY,
                            page.file,
                            f"`{key}`의 값 `{target}`: 등록되지 않은 지식 저장소를 가리킨다(저장소 이름: `{repository.strip()}`)",
                        )
                    elif resolve_reference(record.name, target) not in entities:
                        yield Issue(BROKEN_REFERENCE, page.file, f"`{key}`의 값 `{target}`: 가리키는 엔티티가 없다")
