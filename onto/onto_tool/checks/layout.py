"""페이지의 위치: 클래스별 디렉토리, 페이지로 읽히지 않는 파일.

식별자는 온톨로지 층 기준 상대 경로이고 페이지는 클래스별 디렉토리에 둔다. 그래서 식별자의 첫 조각이 그 페이지의 클래스를 드러낸다.
`implements: decision/auth`로 쓴 참조는 `decision/auth`에 있는 페이지가 `Decision`이라는 약속에 기댄다. 페이지가 다른 디렉토리에 있으면
참조가 엉뚱하게 깨져 원인을 찾기 어렵다.
"""

import re
from collections.abc import Iterator

from rdflib import URIRef

from .. import vocab
from ..compiler import Compiled
from ..iri import entity_iri
from ..keys import PAGE_CLASS_DIRECTORIES
from ..rules import RuleSet
from .catalog import MISNAMED_PAGE, MISPLACED_PAGE
from .classes import ClassIndex
from .labels import class_label
from .model import Issue


def find(compiled: Compiled, rules: RuleSet) -> Iterator[Issue]:
    namespace = vocab.onto_namespace(compiled.graph)
    directory_of = {URIRef(namespace + name): directory for name, directory in PAGE_CLASS_DIRECTORIES.items()}
    classes = ClassIndex(compiled.graph)
    for record in compiled.records:
        identifier_form = re.compile(rules.of(record.directory).language.identifier_pattern)
        for file in record.misnamed_pages:
            yield Issue(MISNAMED_PAGE, file, "페이지처럼 보이지만 확장자가 `.md`가 아니라 페이지로 읽히지 않았다")
        if record.name is None:
            continue
        for page in record.pages:
            iri = entity_iri(record.name, page.identifier)
            # 컴파일이 그래프에 올린 페이지만 본다. 클래스를 알 수 없는 페이지는 클래스 문제가 따로 보고된다.
            if compiled.files.get(iri) != page.file:
                continue
            # 디렉토리 이름 순. 집합을 도는 순서는 프로세스마다 달라 설명이 실행마다 바뀐다.
            page_classes = dict(
                sorted(((cls, directory_of[cls]) for cls in classes.roots(URIRef(iri)) if cls in directory_of), key=lambda item: item[1])
            )
            expected = set(page_classes.values())
            actual = page.identifier.partition("/")[0] if "/" in page.identifier else None
            if not expected or expected == {actual}:
                continue
            # 대소문자만 다른 디렉토리(`Plan/`)가 식별자 형식에도 어긋나면 식별자 형식 항목이 이미 보고한다. 디렉토리 이름 하나를
            # 고치면 둘 다 사라지므로 겹쳐 알리지 않는다. 저장소의 규칙이 그 이름을 식별자로 허용하면 이 항목만 남는다.
            if actual is not None and {actual.lower()} == expected and not identifier_form.fullmatch(actual):
                continue
            where = f"`{actual}/` 아래" if actual else "온톨로지 층 최상위"
            if len(expected) > 1:
                shown = ", ".join(f"`{class_label(cls)}`(`{directory}/`)" for cls, directory in page_classes.items())
                message = f"클래스가 둘 이상이면 클래스별 디렉토리 하나에 둘 수 없다: {shown}"
            else:
                (directory,) = expected
                (cls,) = page_classes
                message = f"클래스 `{class_label(cls)}`의 페이지는 `{directory}/` 아래에 둔다. 이 페이지는 {where}에 있다"
            yield Issue(MISPLACED_PAGE, page.file, message)
