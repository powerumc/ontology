"""이름이 같은 엔티티의 중복: 같은 클래스 안에서 제목과 별칭을 대소문자와 공백을 무시하고 비교한다.

같은 대상이 여러 페이지로 갈라져 집계가 틀어지는 것을 잡는다. 같은 지식 저장소 안의 중복은 한 저장소가 스스로 고칠 수 있는
오류이고, 지식 저장소 사이의 중복은 같은 대상을 다른 저장소가 각자 다룰 수도 있어 경고다.
클래스는 상위 클래스를 따라가 닿는 공통 어휘의 클래스다(`checks.classes`). 질의가 하위 클래스의 엔티티도 상위 클래스로 집계하므로,
하위 클래스의 엔티티와 상위 클래스의 엔티티, 서로 다른 저장소가 선언한 하위 클래스의 엔티티끼리도 같은 클래스에서 비교한다.

이름을 비교하는 방법(어느 속성을, 대소문자와 공백을 구분하는지)은 규칙의 `duplicates`다. 엔티티마다 그 엔티티가 있는 지식 저장소의
규칙을 따르고, 저장소가 규칙을 덮어쓰면 그 저장소의 엔티티가 상대를 찾는 방법만 달라진다.
"""

from collections import defaultdict
from collections.abc import Iterator

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, SKOS

from .. import vocab
from ..compiler import Compiled
from ..rules import Duplicates, RuleSet
from .catalog import DUPLICATE_ENTITY, DUPLICATE_ENTITY_ACROSS_REPOSITORIES
from .classes import ClassIndex
from .labels import class_label
from .model import Issue
from .model import repository_of as directory_of

_NAME_PREDICATES = {"title": DCTERMS.title, "aliases": SKOS.altLabel}


def find(compiled: Compiled, rules: RuleSet) -> Iterator[Issue]:
    graph = compiled.graph
    repository = URIRef(vocab.onto_namespace(graph) + "repository")
    entities = [URIRef(iri) for iri in compiled.files]
    repository_of = {entity: str(graph.value(entity, repository)) for entity in entities}
    index = ClassIndex(graph)
    classes = {entity: index.roots(entity) for entity in entities}
    settings = {entity: rules.of(directory_of(compiled.files[str(entity)])).duplicates for entity in entities}

    # 비교 방법마다 한 번씩: 엔티티 -> 이름(비교하는 형태 -> 쓴 그대로의 표기), (클래스, 비교하는 형태) -> 그 이름을 가진 엔티티
    indexes: dict[Duplicates, tuple[dict[URIRef, dict[str, str]], dict[tuple[object, str], list[URIRef]]]] = {}

    def indexed(method: Duplicates):
        if method not in indexes:
            names = {entity: _names(graph, entity, method) for entity in entities}
            owners: dict[tuple[object, str], list[URIRef]] = defaultdict(list)
            for entity in entities:
                for cls in classes[entity]:
                    for normalized in names[entity]:
                        owners[cls, normalized].append(entity)
            indexes[method] = names, owners
        return indexes[method]

    for entity in entities:
        names, owners = indexed(settings[entity])
        # 겹치는 상대 엔티티 -> (클래스, 겹친 이름의 이 엔티티 쪽 표기)
        same: dict[URIRef, tuple[object, str]] = {}
        for cls in sorted(classes[entity], key=str):
            for normalized, written in names[entity].items():
                for other in owners[cls, normalized]:
                    if other != entity:
                        same.setdefault(other, (cls, written))
        for across, check in ((False, DUPLICATE_ENTITY), (True, DUPLICATE_ENTITY_ACROSS_REPOSITORIES)):
            group = {o: v for o, v in same.items() if (repository_of[o] != repository_of[entity]) == across}
            if group:
                where = ", ".join(
                    f"{compiled.files[str(other)]}(클래스 `{class_label(cls)}`, 이름 `{written}`)"
                    for other, (cls, written) in sorted(group.items(), key=lambda item: compiled.files[str(item[0])])
                )
                yield Issue(check, compiled.files[str(entity)], f"같은 클래스에서 이름이 같은 엔티티가 있다: {where}")


def _names(graph: Graph, entity: URIRef, method: Duplicates) -> dict[str, str]:
    """엔티티의 이름(`method.compare`의 속성 값). 비교하는 형태(규칙이 정한 만큼 대소문자와 공백을 없앤 것) -> 쓴 그대로의 표기."""
    result: dict[str, str] = {}
    for name in method.compare:
        for value in graph.objects(entity, _NAME_PREDICATES[name]):
            if isinstance(value, Literal):
                written = str(value)
                normalized = "".join(written.split()) if method.ignore_whitespace else written
                if method.ignore_case:
                    normalized = normalized.casefold()
                if normalized.strip():
                    result.setdefault(normalized, written)
    return result
