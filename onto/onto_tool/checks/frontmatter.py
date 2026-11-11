"""페이지의 frontmatter를 훑는 검사 항목: 정의되지 않은 키, 역방향 관계, 식별자 형식.

컴파일은 정의된 키만 그래프로 옮기고 나머지를 조용히 버린다. 그래서 그래프가 아니라 페이지에서 읽은 frontmatter 원문을 본다.
식별자 형식도 같다. 공백이나 한글이 든 경로의 페이지는 그래프에 올라가지만 알아보기 어려운 IRI가 되므로, 파일 경로에서 따진다.
"""

from collections.abc import Iterator

from ..compiler import Compiled, PageRecord
from ..keys import PAGE_KEYS, PAGE_PROPERTY_KEYS, RELATION_KEYS, REVERSE_RELATION_KEYS
from ..pages import IDENTIFIER_SEGMENT
from .catalog import INVALID_IDENTIFIER, REVERSE_RELATION, UNDEFINED_KEY
from .model import Issue

DEFINED_KEYS = (*PAGE_PROPERTY_KEYS, *RELATION_KEYS)


def find(compiled: Compiled) -> Iterator[Issue]:
    for record in compiled.records:
        for page in record.pages:
            yield from _identifier(page)
            yield from _keys(page)


def _identifier(page: PageRecord) -> Iterator[Issue]:
    bad = [segment for segment in page.identifier.split("/") if not IDENTIFIER_SEGMENT.fullmatch(segment)]
    if bad:
        shown = ", ".join(f"`{segment}`" for segment in bad)
        yield Issue(
            INVALID_IDENTIFIER,
            page.file,
            f"식별자 `{page.identifier}`의 경로 조각 {shown}에 영어 소문자, 숫자, 하이픈이 아닌 글자가 있다",
        )


def _keys(page: PageRecord) -> Iterator[Issue]:
    for key in page.meta or {}:
        if key in PAGE_KEYS:
            continue
        if key in REVERSE_RELATION_KEYS:
            forward = REVERSE_RELATION_KEYS[key]
            yield Issue(
                REVERSE_RELATION,
                page.file,
                f"역방향 관계 `{key}`: 페이지에 쓸 수 없다. 추론이 만든다. 가리키는 쪽 페이지에 `{forward}`로 쓴다",
            )
        else:
            yield Issue(UNDEFINED_KEY, page.file, f"정의되지 않은 키 `{key}`(쓸 수 있는 키: {', '.join(DEFINED_KEYS)})")
