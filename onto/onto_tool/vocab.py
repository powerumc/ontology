"""공통 어휘, JSON-LD context, 구조 제약. 모두 `onto/vocab/`에 있고, 이 도구와 함께 지식 저장소에 `.onto/vocab/`로 복사된다."""

import json

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from .keys import PAGE_KEYS
from .paths import VOCAB_DIR


def load_vocab(graph: Graph) -> None:
    """공통 어휘(클래스와 관계의 정의)를 `graph`에 싣는다. 어휘가 선언한 접두사도 `graph`에 묶인다."""
    graph.parse(VOCAB_DIR / "onto.ttl", format="turtle")


def load_shapes() -> Graph:
    """구조 제약(SHACL 도형). 공통 어휘와 따로 파일에 있고, 스크립트 검사가 컴파일한 그래프에 돌린다."""
    shapes = Graph()
    shapes.parse(VOCAB_DIR / "shapes.ttl", format="turtle")
    return shapes


def load_context() -> dict:
    """frontmatter 키를 RDF에 대응시키는 JSON-LD context. `@context`의 내용(용어 정의)을 돌려준다."""
    return json.loads((VOCAB_DIR / "context.jsonld").read_text(encoding="utf-8"))["@context"]


def onto_namespace(graph: Graph) -> str:
    """`load_vocab`으로 어휘를 실은 `graph`에 묶인 `onto` 접두사의 네임스페이스."""
    return str(dict(graph.namespaces())["onto"])


def common_classes(graph: Graph) -> dict[str, URIRef]:
    """`load_vocab`으로 어휘를 실은 `graph`에서 공통 어휘의 클래스를 `{이름: IRI}`로 꺼낸다. 이름은 IRI에서 네임스페이스를 뗀 것이다."""
    namespace = onto_namespace(graph)
    return {
        str(cls)[len(namespace) :]: cls
        for cls in graph.subjects(RDF.type, OWL.Class)
        if isinstance(cls, URIRef) and str(cls).startswith(namespace)
    }


def property_keys(context: dict) -> dict[str, str]:
    """페이지의 frontmatter 키가 그래프에서 되는 술어의 IRI -> 키. `class`는 `rdf:type`이다. 검사 결과가 술어를 키 이름으로 보여 주는 데 쓴다."""
    result: dict[str, str] = {}
    for key in PAGE_KEYS:
        term = context[key]
        iri = term["@id"] if isinstance(term, dict) else term
        if iri == "@type":
            result[str(RDF.type)] = key
        else:
            prefix, _, local = iri.partition(":")
            result[str(context[prefix]) + local] = key
    return result
