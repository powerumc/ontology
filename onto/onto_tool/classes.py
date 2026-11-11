"""엔티티의 클래스를 공통 어휘의 클래스로 환원한다. 스크립트 검사(`checks`)와 인덱스(`index`)가 쓴다.

하위 클래스의 엔티티는 상위 클래스로도 질의되고 집계된다. 그래서 클래스를 비교하는 검사(중복, 클래스별 디렉토리)는
적힌 클래스가 아니라, 상위 클래스를 따라가 닿는 공통 어휘의 클래스로 비교한다. 지식 저장소마다 선언한 하위 클래스의 IRI가
따로라, 적힌 클래스로 비교하면 저장소가 달라지는 순간 같은 종류의 엔티티가 다른 클래스가 된다.
"""

from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS

from . import vocab
from .keys import PAGE_CLASS_DIRECTORIES


class ClassIndex:
    """컴파일한 그래프의 클래스를 공통 어휘의 클래스로 환원한다. 컴파일된 그래프마다 하나를 만들어 함께 쓴다(`Compiled.class_index`).

    그래프는 컴파일이 끝난 뒤 바뀌지 않으므로, 클래스마다 환원한 결과를 한 번만 계산해 둔다. 엔티티가 수천 개여도 클래스는 수십 개라, 엔티티마다
    상위 클래스를 다시 따라가지 않는다.
    """

    def __init__(self, graph: Graph) -> None:
        self._graph = graph
        namespace = vocab.onto_namespace(graph)
        self._common = set(vocab.common_classes(graph).values())
        self._allowed = {URIRef(namespace + name) for name in (*PAGE_CLASS_DIRECTORIES, "Project")}
        self._roots_of_class: dict[object, frozenset[URIRef]] = {}

    def roots(self, entity: object) -> set[URIRef]:
        """엔티티의 적힌 클래스마다, 상위 클래스를 따라가 닿는 공통 어휘의 클래스.

        공통 어휘의 클래스에 닿지 않는 클래스(풀리지 않은 클래스)는 그대로 돌려준다. 같은 풀리지 않은 클래스끼리는 같은 클래스다.
        """
        result: set[URIRef] = set()
        for cls in self._graph.objects(entity, RDF.type):
            result |= self._reduced(cls)
        return result

    def _reduced(self, cls: object) -> frozenset[URIRef]:
        """클래스 `cls`가 상위 클래스를 따라가 닿는 공통 어휘의 클래스. 없으면 `cls` 자신이다."""
        if cls not in self._roots_of_class:
            reached = set(self._graph.transitive_objects(cls, RDFS.subClassOf))  # cls 자신을 포함한다
            self._roots_of_class[cls] = frozenset((reached & self._common) or {cls})
        return self._roots_of_class[cls]

    def has_allowed_class(self, entity: object) -> bool:
        """페이지로 서술하는 공통 클래스(또는 그 하위 클래스)나 Project의 엔티티다. 클래스가 없거나 풀리지 않으면 거짓이다."""
        return bool(self.roots(entity) & self._allowed)
