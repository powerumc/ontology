"""추론: 하위 클래스, 역관계, 추이 관계 세 규칙만 rdflib 위에서 직접 적용한다.

OWL 2 RL 전체 규칙과 owlrl은 쓰지 않는다(페이지 3,000개에서 전체 추론은 11.3초, 세 규칙만 적용하면 1.1초였다).
어떤 클래스와 관계에 어느 규칙을 적용할지는 그래프에 실린 공통 어휘의 선언이 정한다.

- 하위 클래스: `rdfs:subClassOf`. 하위 클래스의 엔티티는 상위 클래스의 엔티티이기도 하다.
- 역관계: `owl:inverseOf`. `A p B`이면 `B q A`다(`p`와 `q`는 서로의 역).
- 추이 관계: `owl:TransitiveProperty`. `A p B`이고 `B p C`이면 `A p C`다.

추이 관계를 먼저 닫고 그 결과에 역관계를 적용한다. 그래서 `partOf`가 이어진 만큼 `hasPart`도 이어진다.
입력의 그래프는 고치지 않는다. 그래프에 적힌 사실(교차 참조를 포함한 페이지의 사실)과 추론된 사실을 구분해야 하는
검사는 입력의 그래프를 그대로 쓰고, 질의와 컴파일 결과의 파일은 추론한 그래프를 쓴다.
"""

from collections import defaultdict
from collections.abc import Mapping

from rdflib import Graph, Literal
from rdflib.namespace import OWL, RDF, RDFS
from rdflib.term import Node

from .graphs import canonical

Triple = tuple[Node, Node, Node]


def infer(graph: Graph) -> Graph:
    """`graph`의 사실에 세 규칙을 적용해, 추론된 사실을 더한 새 그래프를 돌려준다."""
    derived = _subclasses(graph) | _transitive(graph)
    derived |= _inverses(graph, derived)
    return canonical(graph, derived)


def _subclasses(graph: Graph) -> set[Triple]:
    superclasses = _reachable(_edges(graph, RDFS.subClassOf))
    derived: set[Triple] = {
        (cls, RDFS.subClassOf, ancestor) for cls, ancestors in superclasses.items() for ancestor in ancestors
    }
    for entity, cls in graph.subject_objects(RDF.type):
        derived.update((entity, RDF.type, ancestor) for ancestor in superclasses.get(cls, ()))
    return derived


def _transitive(graph: Graph) -> set[Triple]:
    derived: set[Triple] = set()
    for relation in graph.subjects(RDF.type, OWL.TransitiveProperty):
        for source, targets in _reachable(_edges(graph, relation)).items():
            derived.update((source, relation, target) for target in targets)
    return derived


def _inverses(graph: Graph, derived: set[Triple]) -> set[Triple]:
    """역관계로 뒤집은 사실. `derived`에 이미 있는 추이 관계의 사실도 함께 뒤집는다."""
    inverse_of: dict[Node, set[Node]] = defaultdict(set)
    for relation, inverse in graph.subject_objects(OWL.inverseOf):
        inverse_of[relation].add(inverse)
        inverse_of[inverse].add(relation)  # owl:inverseOf는 대칭이라 어느 쪽에 적었는지는 묻지 않는다

    result: set[Triple] = set()
    for relation, inverses in inverse_of.items():
        facts = {*graph.triples((None, relation, None)), *(t for t in derived if t[1] == relation)}
        for source, _, target in facts:
            if not isinstance(target, Literal):  # 리터럴은 주어가 될 수 없다
                result.update((target, inverse, source) for inverse in inverses)
    return result


def _edges(graph: Graph, relation: Node) -> dict[Node, set[Node]]:
    edges: dict[Node, set[Node]] = defaultdict(set)
    for source, target in graph.subject_objects(relation):
        edges[source].add(target)
    return edges


def _reachable(edges: Mapping[Node, set[Node]]) -> dict[Node, set[Node]]:
    """각 노드에서 간선을 따라 닿는 노드의 집합. 순환이 있어도 끝나고, 순환에 든 노드는 자기 자신에도 닿는다."""
    reachable: dict[Node, set[Node]] = {}
    for start in edges:
        seen: set[Node] = set()
        pending = list(edges[start])
        while pending:
            node = pending.pop()
            if node not in seen:
                seen.add(node)
                pending.extend(edges.get(node, ()))
        reachable[start] = seen
    return reachable
