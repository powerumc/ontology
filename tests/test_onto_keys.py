"""`onto/onto_tool/keys.py`(코드가 아는 키의 집합)와 `onto/vocab/context.jsonld`(키와 RDF의 대응)가 어긋나지 않는다.

두 파일은 같은 키를 서로 다른 곳에서 정의한다. 한쪽에만 키를 더하면, 더한 키가 컴파일에서 조용히 버려지거나
(`keys.py`에만 있을 때: context가 풀지 못한 키는 그래프에 들어가지 않는다) 쓸 수 없는 키가 그래프에 들어간다
(`context.jsonld`에만 있을 때: 컴파일은 `keys.py`에 있는 키만 옮긴다).

이 테스트는 명령을 실행해 결과를 보는 대신 두 정의 파일을 직접 대조한다. 지켜야 하는 것이 두 파일 사이의 약속이기 때문이다.
`keys.py`는 의존성 없이 읽히는 파일이라 도구의 가상환경 없이 실행해 상수만 꺼낸다. 도구는 이 저장소의 추적 파일 사본에서 돈다.
"""

import json
import runpy
from pathlib import Path

import pytest


@pytest.fixture
def keys(onto_tool_dir: Path) -> dict[str, object]:
    return runpy.run_path(str(onto_tool_dir / "onto_tool" / "keys.py"))


@pytest.fixture
def context(onto_tool_dir: Path) -> dict[str, object]:
    return json.loads((onto_tool_dir / "vocab" / "context.jsonld").read_text(encoding="utf-8"))["@context"]


def is_prefix(value: object) -> bool:
    """접두사 선언(`"onto": "https://…#"`)인가. 키의 뜻을 정하는 용어가 아니다."""
    return isinstance(value, str) and value.endswith(("#", "/"))


def property_terms(context: dict[str, object]) -> dict[str, object]:
    """context에서 frontmatter 키의 뜻을 정하는 용어. 클래스 이름(대문자로 시작), `class`, 접두사는 뺀다."""
    return {
        term: definition
        for term, definition in context.items()
        if term != "class" and not term[0].isupper() and not is_prefix(definition)
    }


def test_페이지_키는_class를_빼고_context의_용어와_정확히_같다(keys, context):
    page_keys = set(keys["PAGE_KEYS"]) - {"class"}

    terms = set(property_terms(context))

    assert page_keys - terms == set(), "keys.py에만 있는 키: context.jsonld가 풀지 못해 그래프에서 조용히 사라진다"
    assert terms - page_keys == set(), "context.jsonld에만 있는 키: 컴파일이 옮기지 않아 쓸 수 없다"


def test_class는_엔티티의_종류를_뜻하는_키로_둘_다_정의되어_있다(keys, context):
    assert "class" in keys["PAGE_KEYS"]
    assert context["class"] == "@type"


def test_관계_키는_값을_IRI로_푸는_용어고_다른_키는_아니다(keys, context):
    terms = property_terms(context)
    relation_keys = set(keys["RELATION_KEYS"])

    resolved_as_iri = {term for term, definition in terms.items() if isinstance(definition, dict) and definition.get("@type") == "@id"}

    assert resolved_as_iri == relation_keys


def test_Project의_키는_페이지의_키와_같은_이름이고_context가_정의한다(keys, context):
    project_keys = set(keys["PROJECT_KEYS"])

    assert project_keys <= set(keys["PAGE_KEYS"])
    assert project_keys <= set(property_terms(context))


def test_ontology_yaml의_키는_이름_Project의_키_그리고_클래스_선언이다(keys, context):
    assert keys["ONTOLOGY_YAML_KEYS"] == {*keys["ONTOLOGY_YAML_REQUIRED_KEYS"], *keys["PROJECT_KEYS"], keys["CLASSES_KEY"]}
    # 클래스 선언은 엔티티의 사실이 아니라 어휘의 선언이라 context에 대응이 없다.
    assert keys["CLASSES_KEY"] not in context
    assert not set(keys["ONTOLOGY_YAML_REQUIRED_KEYS"]) & set(context)
