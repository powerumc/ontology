"""그래프의 IRI를 사람이 읽을 이름으로 바꾼다. 검사 결과의 설명에 쓴다."""

from urllib.parse import unquote

from ..iri import CLASS_BASE, ENTITY_BASE, UNRESOLVED_BASE


def class_label(iri: object) -> str:
    """클래스의 IRI를 frontmatter에 쓰는 이름으로. 선언한 하위 클래스는 이름만, 풀리지 않은 클래스는 쓴 값 그대로다."""
    text = str(iri)
    if text.startswith(UNRESOLVED_BASE):
        return unquote(text[len(UNRESOLVED_BASE) :]) or "(빈 값)"
    if text.startswith(CLASS_BASE):
        return unquote(text[len(CLASS_BASE) :]).partition("/")[2]
    return text.rpartition("#")[2] if "#" in text else text


def entity_label(iri: object) -> str:
    """엔티티의 IRI를 식별자로. 다른 지식 저장소의 엔티티는 교차 참조(`<저장소 이름>:<식별자>`)의 모양이다."""
    text = str(iri)
    if text.startswith(ENTITY_BASE):
        repository, _, identifier = unquote(text[len(ENTITY_BASE) :]).partition("/")
        return f"{repository}:{identifier}"
    return text
