"""고아 페이지: 다른 엔티티와의 관계가 들어오는 것도 나가는 것도 없는 페이지.

컴파일한 그래프의 적힌 사실로 판단한다. 추론한 그래프에는 역관계가 더해져, 관계를 적은 쪽과 받은 쪽이 서로 이어진 것처럼 보인다.
세는 관계는 `keys.RELATION_KEYS`의 것뿐이다. `derivedFrom`(근거가 된 원본 문서)은 다른 엔티티와의 관계가 아니라 세지 않는다.
자기 자신을 가리키는 관계도 세지 않는다. 자기 자신은 다른 엔티티가 아니다.
"""

from collections.abc import Iterator

from rdflib import URIRef

from .. import vocab
from ..compiler import PROJECT_IDENTIFIER, Compiled
from ..iri import entity_iri
from ..keys import RELATION_KEYS
from .catalog import ORPHAN_PAGE
from .model import Issue


def find(compiled: Compiled) -> Iterator[Issue]:
    namespace = vocab.onto_namespace(compiled.graph)
    connected: set[object] = set()
    for key in RELATION_KEYS:
        for source, target in compiled.graph.subject_objects(URIRef(namespace + key)):
            if source != target:
                connected.update((source, target))

    for record in compiled.records:
        if record.name is None:
            continue
        for page in record.pages:
            iri = entity_iri(record.name, page.identifier)
            # 컴파일이 그래프에 올린 페이지만 본다. `project` 식별자는 Project 엔티티의 것이라 페이지가 아니다.
            if page.identifier != PROJECT_IDENTIFIER and compiled.files.get(iri) == page.file and URIRef(iri) not in connected:
                yield Issue(ORPHAN_PAGE, page.file, "다른 엔티티와의 관계가 들어오는 것도 나가는 것도 없다")
