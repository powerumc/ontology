"""인덱스: 지식 저장소의 페이지 목록을 페이지에서 생성한다.

인덱스는 지식 저장소를 따로 클론한 사람과 에이전트가 온톨로지 층에서 처음 여는 파일이라(진입점) 지식 저장소의 `docs/ontology/index.md`로
커밋한다(ADR 0006). 페이지를 클래스별로 묶어 제목, 링크, 한 줄 설명을 보여 준다. 링크는 인덱스 파일 기준 상대 경로라
복사된 기능 없이 클론한 저장소에서도 열린다.

같은 페이지에서는 글자 하나 다르지 않은 인덱스가 나온다. 시각, 기기, 작업 사본의 경로를 싣지 않고, 순서는 클래스 목록의 순서와
식별자 순서로 정한다. 지식 저장소 하나의 인덱스는 그 저장소의 페이지만 다룬다. 루트 저장소나 다른 지식 저장소는 나오지 않는다.

모든 지식 저장소를 모은 전체 인덱스(`render_all`)는 빌드 산출물이라 커밋하지 않는다.

생성은 컴파일한 결과(`Compiled`)에서 한다. 어긋난 인덱스를 잡는 스크립트 검사도 같은 함수로 있어야 할 글자를 만들어 파일과 비교한다.
"""

import posixpath
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import quote

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, RDF

from . import vocab
from .classes import ClassIndex
from .compiler import PROJECT_IDENTIFIER, Compiled
from .iri import entity_iri
from .keys import PAGE_CLASS_DIRECTORIES
from .labels import class_label

# 클래스에 닿지 못해 어느 클래스 묶음에도 들지 못한 페이지의 묶음. 인덱스에서 페이지가 조용히 빠지지 않게 한다.
UNCLASSIFIED = "분류되지 않음"

GENERATED_NOTICE = "이 파일은 `onto build`가 페이지에서 만든 생성물이다. 손으로 고치지 않는다. 페이지를 고친 뒤 다시 만든다."
GENERATED_NOTICE_ALL = (
    "이 파일은 `onto build`가 모든 지식 저장소의 페이지에서 만든 빌드 산출물이다. 커밋하지 않는다. 손으로 고치지 않는다."
)

Link = Callable[[str], str]  # 루트 저장소 기준 파일 경로 -> 인덱스에 적을 링크


@dataclass(frozen=True)
class Entry:
    """인덱스의 항목 하나: 페이지 하나."""

    identifier: str
    file: str  # 루트 저장소 기준 경로
    title: str  # 제목. 없으면 식별자
    description: str  # 한 줄 설명. 없으면 빈 글자
    labels: tuple[str, ...]  # 묶음의 클래스와 다른 클래스의 이름(선언한 하위 클래스 등). 묶음이 클래스가 아니면 적힌 클래스 전부


@dataclass(frozen=True)
class Section:
    heading: str  # 클래스 이름, 또는 `UNCLASSIFIED`
    entries: tuple[Entry, ...]  # 식별자 순


@dataclass(frozen=True)
class RepositoryIndex:
    """지식 저장소 하나의 인덱스에 들어갈 내용."""

    name: str
    index_file: str  # 루트 저장소 기준, 이 인덱스를 두는 파일의 경로
    title: str  # `Project`의 제목. 없으면 빈 글자
    description: str  # `Project`의 설명. 없으면 빈 글자
    sections: tuple[Section, ...]  # 비어 있지 않은 묶음만


def collect(compiled: Compiled) -> list[RepositoryIndex]:
    """컴파일한 지식 저장소마다 인덱스에 들어갈 내용을 모은다. `ontology.yaml`을 읽지 못해 이름을 모르는 저장소는 뺀다.

    그래프에 오른 페이지만 싣는다. 읽을 수 없는 페이지는 스크립트 검사가 따로 보고한다. 다른 지식 저장소와 `name`이 겹치는 저장소는 뺀다.
    엔티티의 IRI가 `name`으로 만들어져 두 저장소의 엔티티가 하나로 합쳐지므로, 한 저장소의 제목이 다른 저장소의 인덱스에 들 수 있다. 페이지의 클래스는 상위 클래스를 따라가 닿는
    공통 어휘의 클래스로 묶는다(`checks.classes`). 그래서 하위 클래스의 페이지도 공통 클래스의 묶음에 들고, 하위 클래스의 이름은 항목에 붙는다.
    """
    graph = compiled.graph
    classes = ClassIndex(graph)
    namespace = vocab.onto_namespace(graph)
    common = {URIRef(namespace + name): name for name in PAGE_CLASS_DIRECTORIES}

    shared = Counter(record.name for record in compiled.records if record.name is not None)

    result: list[RepositoryIndex] = []
    for record in compiled.records:
        if record.name is None or shared[record.name] > 1:
            continue
        grouped: dict[str, list[Entry]] = {name: [] for name in PAGE_CLASS_DIRECTORIES}
        grouped[UNCLASSIFIED] = []
        for page in sorted(record.pages, key=lambda p: p.identifier):
            iri = URIRef(entity_iri(record.name, page.identifier))
            if compiled.files.get(str(iri)) != page.file:  # 그래프에 오르지 않은 페이지
                continue
            written = sorted({class_label(cls) for cls in graph.objects(iri, RDF.type)})
            headings = [common[cls] for cls in classes.roots(iri) if cls in common] or [UNCLASSIFIED]
            for heading in headings:
                labels = written if heading == UNCLASSIFIED else [label for label in written if label != heading]
                entry = Entry(
                    identifier=page.identifier,
                    file=page.file,
                    title=_text(graph, iri, DCTERMS.title) or page.identifier,
                    description=_text(graph, iri, DCTERMS.description),
                    labels=tuple(labels),
                )
                grouped[heading].append(entry)

        project = URIRef(entity_iri(record.name, PROJECT_IDENTIFIER))
        sections = tuple(Section(heading, tuple(entries)) for heading, entries in grouped.items() if entries)
        result.append(
            RepositoryIndex(
                name=record.name,
                index_file=record.index_file,
                title=_text(graph, project, DCTERMS.title),
                description=_text(graph, project, DCTERMS.description),
                sections=sections,
            )
        )
    return result


def render(content: RepositoryIndex) -> str:
    """지식 저장소 하나의 인덱스 파일의 글자. 링크는 그 인덱스 파일 기준 상대 경로다."""
    directory = posixpath.dirname(content.index_file)

    def link(file: str) -> str:
        return posixpath.relpath(file, directory)

    lines = [f"# {content.title or content.name} 인덱스", "", f"> {GENERATED_NOTICE}", ""]
    if content.description:
        lines += [content.description, ""]
    lines += _body(content, link, level=2)
    return "\n".join(lines).rstrip("\n") + "\n"


def render_all(contents: Iterable[RepositoryIndex], link: Link) -> str:
    """모든 지식 저장소를 모은 전체 인덱스의 글자. `link`가 파일 경로를 이 인덱스 파일 기준 링크로 바꾼다."""
    lines = ["# 전체 인덱스", "", f"> {GENERATED_NOTICE_ALL}", ""]
    contents = list(contents)
    if not contents:
        lines += ["지식 저장소가 없다.", ""]
    for content in contents:
        heading = f"{content.title} ({content.name})" if content.title else content.name
        lines += [f"## {heading}", ""]
        if content.description:
            lines += [content.description, ""]
        lines += _body(content, link, level=3)
    return "\n".join(lines).rstrip("\n") + "\n"


def _body(content: RepositoryIndex, link: Link, *, level: int) -> list[str]:
    if not content.sections:
        return ["페이지가 아직 없다.", ""]
    lines: list[str] = []
    for section in content.sections:
        lines += [f"{'#' * level} {section.heading}", ""]
        lines += [_line(entry, link) for entry in section.entries]
        lines.append("")
    return lines


def _line(entry: Entry, link: Link) -> str:
    text = _escape(entry.title)
    # 링크의 괄호와 공백이 마크다운을 깨지 않도록 퍼센트 인코딩한다. 식별자가 형식을 지킨 페이지는 그대로다.
    line = f"- [{text}]({quote(link(entry.file), safe='/')})"
    if entry.labels:
        line += f" ({', '.join(entry.labels)})"
    if entry.description:
        line += f" — {entry.description}"
    return line


def _escape(title: str) -> str:
    """링크의 글자에서 마크다운 문법이 될 글자를 막는다."""
    return title.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _text(graph: Graph, subject: URIRef, predicate: URIRef) -> str:
    """엔티티의 속성 값 하나를 공백을 하나로 줄인 한 줄로. 값이 여럿이면 글자 순으로 첫 번째, 없거나 비면 빈 글자."""
    values = sorted(str(value) for value in graph.objects(subject, predicate) if isinstance(value, Literal))
    for value in values:
        text = " ".join(value.split())
        if text:
            return text
    return ""
