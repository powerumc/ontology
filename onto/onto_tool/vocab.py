"""공통 어휘와 JSON-LD context. 둘 다 `onto/vocab/`에 있고, 이 도구와 함께 지식 저장소에 `.onto/vocab/`로 복사된다."""

import json
from pathlib import Path

from rdflib import Graph

VOCAB_DIR = Path(__file__).resolve().parents[1] / "vocab"


def load_vocab(graph: Graph) -> None:
    """공통 어휘(클래스와 관계의 정의)를 `graph`에 싣는다. 어휘가 선언한 접두사도 `graph`에 묶인다."""
    graph.parse(VOCAB_DIR / "onto.ttl", format="turtle")


def load_context() -> dict:
    """frontmatter 키를 RDF에 대응시키는 JSON-LD context. `@context`의 내용(용어 정의)을 돌려준다."""
    return json.loads((VOCAB_DIR / "context.jsonld").read_text(encoding="utf-8"))["@context"]


def relation_keys(context: dict) -> frozenset[str]:
    """값이 다른 엔티티를 가리키는 frontmatter 키. context에서 값의 종류를 `@id`로 정한 용어다."""
    return frozenset(
        term for term, definition in context.items() if isinstance(definition, dict) and definition.get("@type") == "@id"
    )
