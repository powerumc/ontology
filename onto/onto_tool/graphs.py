"""그래프를 같은 모양으로 싣는 작은 도구."""

from collections.abc import Iterable

from rdflib import Graph
from rdflib.term import Node


def canonical(graph: Graph, extra: Iterable[tuple[Node, Node, Node]] = ()) -> Graph:
    """`graph`의 트리플과 `extra`를 정렬해 새 그래프에 싣는다.

    같은 사실이면 저장 순서도 같아 질의 결과의 순서도 같다. 집합을 거치는 과정(컴파일의 읽기 순서, 추론)에서 생기는
    순서의 흔들림이 결과에 남지 않게 하려는 것이다.
    """
    result = Graph(bind_namespaces="none")
    for prefix, namespace in sorted(graph.namespaces()):
        result.bind(prefix, namespace)
    for triple in sorted({*graph, *extra}):
        result.add(triple)
    return result
