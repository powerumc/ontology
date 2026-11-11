"""컴파일: 지식 저장소의 페이지를 하나의 RDF 그래프로 바꾼다.

페이지의 frontmatter를 JSON-LD context(`vocab/context.jsonld`)로 RDF에 대응시킨다.
같은 입력에서는 같은 그래프가 나온다. 파일을 이름 순으로 읽고, 트리플을 정렬해 싣는다.

루트 저장소에서는 여러 지식 저장소가 하나의 그래프로 합쳐진다. 지식 저장소 안에서는 그 저장소 하나만 컴파일하고(`workspace.Within`),
보고하는 파일 경로도 그 저장소 기준이다. 루트 저장소나 다른 지식 저장소는 읽지 않는다.
관계의 값은 같은 저장소의 식별자이거나, 다른 저장소의 엔티티를 가리키는 교차 참조(`<저장소 이름>:<식별자>`)이고,
가리키는 엔티티가 있는지는 따지지 않는다. 모든 엔티티에는 온 지식 저장소의 이름을
`onto:repository`로 적는다. 저장소는 `ontology.yaml`의 `classes`로 자기 하위 클래스를 선언할 수 있다.
페이지의 `derivedFrom`은 항목(원본 문서의 경로와 해시)마다 `Source` 엔티티가 되어 페이지가 `onto:derivedFrom`으로 가리킨다.
`Source`는 페이지가 없어 `onto:repository`를 적지 않고, 구조 제약의 대상 엔티티가 아니다. 파일은 `Compiled.source_files`가 알려 준다.
추론(하위 클래스, 역관계, 추이 관계)은 여기서 하지 않는다. `inference.infer`가 이 그래프에 적용한다.
인덱스 파일은 만들지 않고 지금 있는 글자만 읽어 둔다(`RepositoryRecord.index_text`). 인덱스는 `index`가 컴파일한 결과에서 만든다.
"""

import json
import re
from collections.abc import Collection, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDFS

from . import vocab
from .errors import OntoError
from .graphs import canonical
from .iri import UNRESOLVED_BASE, class_iri, entity_iri, resolve_reference, source_iri, unresolved_iri
from .keys import CLASS_DECLARATION_KEYS, CLASSES_KEY, PAGE_KEYS, PROJECT_KEYS, RELATION_KEYS, RULES_KEY, SCOPE_KEY, SOURCE_KEY
from .ontology_yaml import OntologyYamlError, read_ontology_yaml, undefined_keys_message
from .pages import (
    INDEX_FILE,
    FrontmatterError,
    ValueKindError,
    find_dangling_page_links,
    find_misnamed_pages,
    find_pages,
    page_values,
    read_page,
    scalar_values,
)
from .sources import SourceEntry, document_hashes, parse_entries, read_skipped
from .workspace import ONTOLOGY_DIR, ONTOLOGY_YAML, PROJECTS_DIR, SKIPPED_YAML, Repository, Within, Workspace

PROJECT_IDENTIFIER = "project"
# 지식 저장소가 선언하는 클래스의 이름. 공통 어휘의 클래스 이름처럼 영어로 쓰고 대문자로 시작한다.
CLASS_NAME = re.compile(r"[A-Z][A-Za-z0-9]*")
# 페이지로 서술하지 않는 공통 클래스와 그 이유. 하위 클래스를 선언해 페이지가 이 클래스의 엔티티가 되게 할 수 없다.
UNPAGED_CLASSES = {
    "Project": "별도 페이지 없이 ontology.yaml에서만 만들어지는 클래스",
    "Source": "페이지를 따로 갖지 않는 클래스",
}

# 읽을 수 없는 파일을 스크립트 검사의 어느 검사 항목이 보고하는지. 항목의 이름이다(`checks.catalog`가 같은 이름으로 항목을 정의한다).
UNREADABLE_FILE = "unreadable-file"  # YAML 문법 오류, frontmatter 없음, UTF-8이 아님
INVALID_VALUE = "invalid-value"  # 읽을 수는 있지만 값의 종류가 맞지 않음
INVALID_CLASS_DECLARATION = "invalid-class-declaration"  # `ontology.yaml`의 `classes`가 틀림
INVALID_IDENTIFIER = "invalid-identifier"  # 페이지로 쓸 수 없는 식별자
# `ontology.yaml` 자체의 문제: 최상위의 정의되지 않은 키, `Project`가 되는 속성(`title`, `description`, `aliases`)의 값의 종류.
# 규칙을 담은 파일이라 이 항목은 루트 전용이다. 저장소의 `rules`가 자기 파일의 오타를 끄거나 낮추지 못하게 한다.
# 페이지의 같은 문제(`undefined-key`, `invalid-value`)는 저장소가 규칙으로 조정할 수 있는 별개의 항목이다.
INVALID_ONTOLOGY_YAML = "invalid-ontology-yaml"
# 서로 다른 지식 저장소가 같은 `name`을 쓴다. 엔티티의 IRI가 `name`으로 만들어져 두 저장소의 엔티티가 하나로 합쳐진다.
# 한 저장소의 제목이 다른 저장소의 커밋되는 인덱스에 들어가는 길이라, 읽을 수 없는 파일처럼 `build`와 `query`를 멈춘다.
# 겹친 저장소를 가려내는 것은 컴파일이라, 이 항목도 루트 전용이다.
DUPLICATE_REPOSITORY_NAME = "duplicate-repository-name"
# 페이지 파일이 지식 저장소 밖의 파일을 가리키는 심볼릭 링크다. 읽지 않는다. 페이지 본문의 링크가 저장소 밖을 가리키는 문제와 같은 항목이다.
# 다른 저장소의 페이지를 링크로 가져오면 그 제목이 이 저장소의 그래프와 커밋되는 인덱스에 실리고 링크가 다른 저장소의 경로를 담는다. 루트 전용이다.
OUTSIDE_LINK = "outside-link"


@dataclass(frozen=True)
class Problem:
    """읽을 수 없는 파일 하나와 이유. 스크립트 검사는 `check`로 검사 항목을, `file`로 지식 저장소와 페이지를 가린다."""

    file: str  # 루트 저장소 기준 경로
    message: str  # 이유
    check: str  # 이 문제를 보고하는 검사 항목의 이름

    def __str__(self) -> str:
        return f"{self.file}: {self.message}"


@dataclass(frozen=True)
class PageRecord:
    """지식 저장소에서 찾은 페이지 파일 하나."""

    identifier: str  # 온톨로지 층 기준 상대 경로에서 확장자를 뺀 것
    file: str  # 루트 저장소 기준 경로
    meta: dict[str, object] | None  # 읽은 frontmatter 그대로(정의되지 않은 키와 값의 종류가 틀린 값도 든다). 읽을 수 없으면 None
    sources: tuple[SourceEntry, ...] = ()  # `derivedFrom`의 항목. 없거나 모양이 틀렸으면 비어 있다(틀린 것은 문제로 따로 모인다)
    body: str = ""  # frontmatter 뒤의 본문. 읽을 수 없으면 비어 있다

    def relations(self) -> Iterator[tuple[str, str]]:
        """페이지가 쓴 관계의 `(키, 값)`. 키마다 같은 값은 한 번만 낸다. 문자열이 아닌 값은 값의 종류가 맞지 않다고 컴파일이 이미 알렸으므로 뺀다."""
        for key in RELATION_KEYS:
            value = (self.meta or {}).get(key)
            targets = value if isinstance(value, list) else [value]
            for target in dict.fromkeys(t for t in targets if isinstance(t, str)):
                yield key, target


@dataclass
class RepositoryRecord:
    """다루는 지식 저장소 후보 하나(루트 저장소에서는 `projects/` 아래의 것). 컴파일이 무엇을 읽었는지 스크립트 검사가 되짚는 데 쓴다.

    경로는 작업 공간 기준이다. 루트 저장소에서는 루트 기준(`projects/billing/…`), 지식 저장소 안에서는 그 저장소 기준(`docs/…`)이다.
    """

    directory: str  # 서브모듈 디렉토리 이름
    path: str  # 작업 공간 기준 디렉토리 경로. 지식 저장소 안에서는 저장소 자신이라 `.`이다
    yaml_file: str  # 작업 공간 기준 `ontology.yaml` 경로
    index_file: str  # 작업 공간 기준 인덱스(`index.md`)의 경로. 파일이 없어도 있어야 할 자리다
    has_layer: bool  # `ontology.yaml`이 있다. 없으면 컴파일이 건너뛴다
    name: str | None = None  # `ontology.yaml`의 `name`. 파일이 없거나 읽을 수 없으면 알 수 없다
    rules: object = None  # `ontology.yaml`의 `rules` 값 그대로. 규칙을 읽고 검증하는 것은 스크립트 검사의 몫이다. 없으면 None
    # `ontology.yaml`의 `scope`(공유 범위) 값 그대로. 읽고 검증하는 것은 공유 범위 검사의 몫이다. 적지 않았으면 `scope_declared`가 False다
    scope: object = None
    scope_declared: bool = False
    pages: list[PageRecord] = field(default_factory=list)
    misnamed_pages: list[str] = field(default_factory=list)  # 페이지처럼 보이지만 확장자가 `.md`가 아니라 읽지 않은 파일의 경로
    index_text: str | None = None  # 지금 인덱스 파일의 글자(줄바꿈은 `\n`으로 통일). 파일이 없거나 읽지 않았으면 None
    # 인덱스 경로를 읽지도 쓰지도 않는 이유. 심볼릭 링크, 일반 파일이 아닌 것, 지식 저장소 밖을 가리키는 경로다. 문제가 없으면 None
    index_problem: str | None = None
    skipped: list[SourceEntry] = field(default_factory=list)  # 넘긴 문서의 목록(`skipped.yaml`)의 항목. 파일이 없거나 읽을 수 없으면 비어 있다
    # 페이지와 넘긴 문서의 목록이 가리키는 원본 문서의 경로 -> 지금 작업 트리에 있는 내용의 해시. 없거나 읽을 수 없는 문서는 None이다.
    document_hashes: dict[str, str | None] = field(default_factory=dict)

    @property
    def skipped_file(self) -> str:
        """작업 공간 기준 넘긴 문서의 목록(`skipped.yaml`)의 경로. 파일이 없어도 있어야 할 자리다."""
        return self.under(SKIPPED_YAML.as_posix())

    @property
    def label(self) -> str:
        """메시지 머리에 둘 이름. 루트 저장소에서는 루트 기준 디렉토리 경로이고, 지식 저장소 안에서는 저장소 이름이다."""
        return self.directory if self.path == "." else self.path

    def under(self, relative: str) -> str:
        """이 지식 저장소 안의 경로 `relative`를 작업 공간 기준 경로로 바꾼다."""
        return relative if self.path == "." else f"{self.path}/{relative}"


@dataclass
class Compiled:
    graph: Graph  # 읽을 수 있었던 파일의 사실만 담는다. 추론은 하지 않은, 적힌 그대로의 사실이다.
    files: dict[str, str]  # 엔티티 IRI -> 작업 공간 기준 파일 경로. 질의 결과에서 엔티티를 파일로 보여 준다.
    repositories: list[str]  # 컴파일한 지식 저장소의 이름
    warnings: list[str]
    problems: list[Problem] = field(default_factory=list)  # 읽을 수 없는 파일과 이유
    records: list[RepositoryRecord] = field(default_factory=list)  # 지식 저장소 후보마다 하나. 디렉토리 이름 순
    # `Source` 엔티티 IRI -> 작업 공간 기준 원본 문서의 경로. 질의 결과에서 `Source`를 원본 문서의 파일로 보여 준다.
    # `files`에 섞지 않는다: `files`의 키는 페이지가 있는 엔티티(`onto:repository`를 가진 것)이고 검사가 그렇게 읽는다.
    source_files: dict[str, str] = field(default_factory=dict)
    notices: list[str] = field(default_factory=list)  # 알릴 것(원본 문서의 해시를 git으로 내지 못했다). 검사 항목이 따로 보고하지 않는다
    within: Within = Within.ROOT  # 어디 안에서 컴파일했는지(루트 저장소 또는 지식 저장소 안). 공유 범위와 무관하다
    root: Path | None = None  # 컴파일한 작업 공간의 루트. 레코드의 `path`가 이 위치 기준이다. 파일을 직접 읽어야 하는 검사 항목이 쓴다

    def repository_of(self, file: str) -> str:
        """`file`(작업 공간 기준 경로)이 속한 지식 저장소의 이름(서브모듈 디렉토리 이름). 어느 저장소의 것도 아니면 빈 글자다.

        루트 저장소에서는 `projects/<지식 저장소>/…`의 가운데 조각이다. 지식 저장소 안에서는 경로가 저장소 기준이라 접두어가 없고,
        모든 파일이 그 저장소의 것이다.
        """
        if self.within is Within.REPOSITORY:
            return self.records[0].directory
        parts = file.split("/")
        return parts[1] if len(parts) > 1 and parts[0] == PROJECTS_DIR else ""


@dataclass
class _RepositoryRead:
    record: RepositoryRecord
    nodes: list[dict] = field(default_factory=list)  # 엔티티와, 선언한 하위 클래스와, `Source` 엔티티
    files: dict[str, str] = field(default_factory=dict)
    source_files: dict[str, str] = field(default_factory=dict)
    problems: list[Problem] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)  # 알릴 것(원본 문서의 해시를 git으로 내지 못했다). 검사 항목이 따로 보고하지 않는다


def compile_workspace(workspace: Workspace) -> Compiled:
    """작업 공간의 지식 저장소를 모두 컴파일한다(루트 저장소에서는 `projects/` 아래 전부, 지식 저장소 안에서는 그 저장소 하나).

    읽을 수 없는 파일은 `problems`에 모은다.
    """
    context = vocab.load_context()
    raw = Graph(bind_namespaces="none")
    vocab.load_vocab(raw)
    common_classes = vocab.common_classes(raw)
    nodes: list[dict] = []
    files: dict[str, str] = {}
    source_files: dict[str, str] = {}
    names: list[str] = []
    problems: list[Problem] = []
    warnings: list[str] = []
    notices: list[str] = []
    records: list[RepositoryRecord] = []
    reads: list[_RepositoryRead] = []

    for repository in workspace.repositories():
        if not (repository.path / ONTOLOGY_YAML).is_file():
            record = _record(workspace, repository, has_layer=False)
            warnings.append(f"{record.label}: 온톨로지 층({ONTOLOGY_YAML.as_posix()})이 없어 건너뛰었다")
            records.append(record)
            continue
        read = _read_repository(workspace, repository, context, common_classes)
        records.append(read.record)
        reads.append(read)

    duplicates = _duplicate_names(records)
    # 다른 저장소의 `name`을 베낀 저장소의 엔티티는 그래프에 올리지 않는다. 엔티티의 IRI가 `name`으로 만들어져 두 저장소의 엔티티가
    # 하나로 합쳐지고, 그러면 한쪽의 제목이 다른 쪽 페이지의 문제(값이 둘인 `title` 등)로 보고되어 고칠 곳이 흐려진다.
    # 고칠 곳은 베낀 쪽의 `name`이고 그것은 `duplicate-repository-name`이 알린다.
    copiers = {problem.file for problem in duplicates}
    for read in reads:
        problems += read.problems
        if read.record.name is not None:
            names.append(read.record.name)
        if read.record.yaml_file not in copiers:
            nodes += read.nodes
            files.update(read.files)
            source_files.update(read.source_files)
        notices += read.notices

    problems += duplicates
    raw.parse(data=json.dumps({"@context": context, "@graph": nodes}), format="json-ld", base=UNRESOLVED_BASE)
    return Compiled(canonical(raw), files, names, warnings, problems, records, source_files, notices, workspace.within, workspace.root)


def _duplicate_names(records: list[RepositoryRecord]) -> list[Problem]:
    """같은 `name`을 쓰는 지식 저장소가 있으면, 그 가운데 `name`이 서브모듈 디렉토리 이름과 다른 저장소마다 문제 하나를 만든다.

    디렉토리 이름은 서로 다르므로 겹친 저장소 가운데 적어도 하나는 `name`이 디렉토리 이름과 다르다. 그것이 고칠 곳이다.
    """
    by_name: dict[str, list[RepositoryRecord]] = {}
    for record in records:
        if record.name is not None:
            by_name.setdefault(record.name, []).append(record)
    return [
        Problem(
            record.yaml_file,
            f"name `{name}`이 다른 지식 저장소({', '.join(f'`{o.directory}`' for o in group if o is not record)})와 같다. "
            "name은 지식 저장소마다 고유하고 서브모듈 디렉토리 이름과 같아야 한다",
            DUPLICATE_REPOSITORY_NAME,
        )
        for name, group in by_name.items()
        if len(group) > 1
        for record in group
        if record.name != record.directory
    ]


def _read_index(repository: Repository, record: RepositoryRecord) -> None:
    """인덱스 파일의 글자를 읽어 `record`에 둔다. 읽거나 쓰면 안 되는 경로면 이유만 둔다.

    인덱스는 지식 저장소가 커밋하는 파일이라 그 저장소의 작성자가 정한 모양일 수 있다. 심볼릭 링크를 따라가면 `build`가 저장소 밖의
    파일을 덮어쓰고 `validate`가 그 내용을 보여 주게 된다. 일반 파일이 아닌 것(디렉토리)은 읽을 수 없고, `docs/`나 `docs/ontology/`가
    링크라 저장소 밖으로 나가는 경로도 쓰지 않는다.
    """
    path = repository.ontology_dir / INDEX_FILE
    if path.is_symlink():
        record.index_problem = "심볼릭 링크라 따라가지 않는다"
    elif path.exists() and not path.is_file():
        record.index_problem = "일반 파일이 아니다"
    elif not path.parent.resolve().is_relative_to(repository.path.resolve()):
        record.index_problem = "경로가 지식 저장소 밖을 가리킨다"
    elif path.is_file():
        try:
            # 깨진 글자가 있어도 읽는다. 생성한 인덱스와 다른 글자가 되어 어긋난 인덱스로 보고될 뿐이다.
            record.index_text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            record.index_problem = f"읽을 수 없다({exc.strerror})"


def _record(workspace: Workspace, repository: Repository, *, has_layer: bool) -> RepositoryRecord:
    return RepositoryRecord(
        directory=repository.directory,
        path=workspace.relative(repository.path),
        yaml_file=workspace.relative(repository.path / ONTOLOGY_YAML),
        index_file=workspace.relative(repository.path / ONTOLOGY_DIR / INDEX_FILE),
        has_layer=has_layer,
    )


def _read_repository(
    workspace: Workspace, repository: Repository, context: dict, common_classes: dict[str, URIRef]
) -> _RepositoryRead:
    """지식 저장소 하나를 JSON-LD 객체로 읽는다. 읽을 수 없는 파일은 모아 두고 나머지를 계속 읽는다."""
    read = _RepositoryRead(_record(workspace, repository, has_layer=True))
    yaml_file = read.record.yaml_file
    try:
        data = read_ontology_yaml(repository.path / ONTOLOGY_YAML)
    except OntologyYamlError as exc:
        read.problems.append(Problem(yaml_file, str(exc), UNREADABLE_FILE))
        return read
    name = read.record.name = str(data["name"])
    read.record.rules = data.get(RULES_KEY)
    read.record.scope, read.record.scope_declared = data.get(SCOPE_KEY), SCOPE_KEY in data
    if undefined := undefined_keys_message(data):
        read.problems.append(Problem(yaml_file, undefined, INVALID_ONTOLOGY_YAML))

    declarations, declared = _declare_classes(name, data.get(CLASSES_KEY), context, common_classes, yaml_file)
    read.nodes += declarations.nodes
    read.problems += declarations.problems

    def add(identifier: str, meta: dict[str, object], file: str, sources: tuple[SourceEntry, ...] = ()) -> None:
        node = _node(name, identifier, meta, declared, common_classes.keys())
        if sources:
            node[SOURCE_KEY] = [_source(read, name, entry) for entry in sources]
        read.nodes.append(node)
        read.files[node["@id"]] = file

    try:
        project = scalar_values({key: data[key] for key in PROJECT_KEYS if key in data})
        add(PROJECT_IDENTIFIER, {"class": "Project", **project}, yaml_file)
    except FrontmatterError as exc:
        read.problems.append(Problem(yaml_file, str(exc), INVALID_ONTOLOGY_YAML))

    read.record.misnamed_pages = [workspace.relative(path) for path in find_misnamed_pages(repository.ontology_dir)]
    _read_index(repository, read.record)
    repository_root = repository.path.resolve()
    for path in find_dangling_page_links(repository.ontology_dir):
        # 가리키는 파일이 없어 읽을 것은 없지만, 링크 파일이 담은 대상(다른 저장소의 이름, 절대 경로)은 지식 저장소를 단독으로 열어도 남는다.
        if not _inside(path, repository_root):
            read.problems.append(
                Problem(
                    workspace.relative(path),
                    "페이지 파일이 지식 저장소 밖을 가리키는 심볼릭 링크다(가리키는 파일은 없다). 링크 자체가 다른 저장소의 위치를 담는다. 다른 저장소의 지식은 교차 참조로 가리킨다",
                    OUTSIDE_LINK,
                )
            )
    for identifier, path in find_pages(repository.ontology_dir):
        file = workspace.relative(path)
        if not _inside(path, repository_root):
            read.problems.append(
                Problem(file, "페이지 파일이 지식 저장소 밖의 파일을 가리키는 심볼릭 링크라 읽지 않는다. 다른 저장소의 지식은 교차 참조로 가리킨다", OUTSIDE_LINK)
            )
            continue
        meta: dict[str, object] | None
        body = ""
        values: dict[str, object] = {}
        sources: tuple[SourceEntry, ...] = ()
        failure: Problem | None = None
        try:
            meta, body = read_page(path)
        except FrontmatterError as exc:
            meta = None
            failure = Problem(file, f"frontmatter를 읽을 수 없다: {exc}", _kind(exc))
        else:
            try:
                values = page_values(meta)
            except ValueKindError as exc:
                failure = Problem(file, f"frontmatter를 읽을 수 없다: {exc}", _kind(exc))
            try:
                sources = tuple(parse_entries(meta.get(SOURCE_KEY), f"`{SOURCE_KEY}`"))
            except ValueKindError as exc:
                failure = failure or Problem(file, f"frontmatter를 읽을 수 없다: {exc}", _kind(exc))
        # 값의 종류가 틀려도 읽은 frontmatter는 남긴다. 같은 페이지의 다른 문제(정의되지 않은 키, 깨진 참조)가 가려지지 않게 한다.
        read.record.pages.append(PageRecord(identifier, file, meta, sources, body))
        if identifier == PROJECT_IDENTIFIER:
            # 같은 IRI라서 두 파일이 제목과 클래스가 둘인 엔티티 하나로 조용히 합쳐진다.
            read.problems.append(
                Problem(
                    file,
                    f"식별자 `{PROJECT_IDENTIFIER}`는 {yaml_file}에서 만드는 Project 엔티티의 것이라 페이지로 쓸 수 없다",
                    INVALID_IDENTIFIER,
                )
            )
            continue
        if failure is not None:
            read.problems.append(failure)
            continue
        try:
            add(identifier, values, file, sources)
        except FrontmatterError as exc:
            read.problems.append(Problem(file, f"frontmatter를 읽을 수 없다: {exc}", _kind(exc)))

    try:
        read.record.skipped = read_skipped(repository.path / SKIPPED_YAML)
    except FrontmatterError as exc:
        read.problems.append(Problem(read.record.skipped_file, f"넘긴 문서의 목록을 읽을 수 없다: {exc}", _kind(exc)))
    referenced = {entry.path for page in read.record.pages for entry in page.sources} | {entry.path for entry in read.record.skipped}
    read.record.document_hashes, notice = document_hashes(repository.path, referenced)
    if notice:
        read.notices.append(f"{read.record.label}: {notice}")
    return read


def _inside(path: Path, root: Path) -> bool:
    """`path`가 심볼릭 링크를 모두 따라간 곳이 `root`(지식 저장소의 실제 경로) 안인가. 따라갈 수 없으면 안이 아니다."""
    try:
        return path.resolve().is_relative_to(root)
    except (OSError, RuntimeError):
        return False


def _source(read: _RepositoryRead, repository: str, entry: SourceEntry) -> str:
    """원본 문서의 기록 하나를 `Source` 엔티티로 싣고 그 IRI를 돌려준다. 같은 경로와 해시는 하나로 합쳐진다."""
    iri = source_iri(repository, entry.path, entry.hash)
    if iri not in read.source_files:
        read.source_files[iri] = read.record.under(entry.path)
        read.nodes.append({"@id": iri, "class": "Source", "onto:sourcePath": entry.path, "onto:sourceHash": entry.hash})
    return iri


def _kind(exc: FrontmatterError) -> str:
    """읽을 수 없는 이유가 값의 종류인지, 파일 자체인지에 따라 보고할 검사 항목을 가른다."""
    return INVALID_VALUE if isinstance(exc, ValueKindError) else UNREADABLE_FILE


def _node(
    repository: str, identifier: str, meta: dict[str, object], declared_classes: set[str], common_class_names: Collection[str]
) -> dict:
    """엔티티 하나의 JSON-LD 객체. `keys.PAGE_KEYS`에 있는 키만 옮기고, 키의 뜻은 context가 정한다.

    다른 키는 버린다. JSON-LD에 그대로 넘기면 `foo:bar` 같은 키가 술어가 되고, `@`로 시작하는 키는 예약어로 읽힌다.
    엔티티가 어느 지식 저장소에서 왔는지(`onto:repository`)는 페이지가 아니라 컴파일이 적는다. 페이지의 키로는 속일 수 없다.
    """
    node: dict = {"@id": entity_iri(repository, identifier), "onto:repository": repository}
    for key, value in meta.items():
        if key == "class":
            node[key] = _classes(repository, value, declared_classes, common_class_names)
        elif key in PAGE_KEYS:
            node[key] = _references(repository, key, value) if key in RELATION_KEYS else value
    return node


def _classes(repository: str, value: object, declared_classes: set[str], common_class_names: Collection[str]) -> object:
    """`class`의 값 가운데 이 지식 저장소가 선언한 클래스의 이름을 그 클래스의 IRI로 바꾼다. 공통 어휘의 클래스 이름은 context가 푼다.

    클래스는 이름으로만 쓴다. 이 저장소가 선언한 이름도 공통 어휘의 클래스 이름도 아닌 값은 JSON-LD에 넘기지 않고
    어느 클래스도 가리키지 않는 풀리지 않은 클래스로 남긴다. 넘기면 JSON-LD가 IRI로 읽어 어느 클래스든 가리킬 수 있어
    (`https://…`, `onto:Component`, 그리고 base 밖으로 나가는 `/class/shop/Secret`, `../vocab#Component`),
    다른 저장소가 선언한 클래스를 이름만으로는 못 끌어 쓰는 제한을 우회한다. 알 수 없는 클래스를 오류로 알리는 것은 스크립트 검사의 몫이다.
    """

    def resolve(name: object) -> object:
        if isinstance(name, str) and name in declared_classes:
            return class_iri(repository, name)
        if isinstance(name, str) and name in common_class_names:
            return name
        # 문자열이 아닌 값(`class: 5`, `class: yes`)도 같다. 그대로 넘기면 리터럴이 클래스 자리에 들어간다.
        return unresolved_iri(str(name))

    names = value if isinstance(value, list) else [value]
    resolved = [resolve(name) for name in names]
    return resolved if isinstance(value, list) else resolved[0]


def _references(repository: str, key: str, value: object) -> object:
    """관계의 값(식별자 또는 `<저장소 이름>:<식별자>` 교차 참조)을 엔티티의 IRI로 바꾼다."""
    targets = value if isinstance(value, list) else [value]
    if not all(isinstance(target, str) for target in targets):
        raise ValueKindError(f"`{key}`의 값이 식별자 문자열이 아니다")
    iris = [resolve_reference(repository, target) for target in targets]
    return iris if isinstance(value, list) else iris[0]


@dataclass
class _Declarations:
    nodes: list[dict] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)


def _declare_classes(
    repository: str, declarations: object, context: dict, common_classes: dict[str, URIRef], yaml_file: str
) -> tuple[_Declarations, set[str]]:
    """`ontology.yaml`의 `classes`를 클래스 선언의 JSON-LD 객체로 바꾼다. 선언된 클래스 이름의 집합도 돌려준다.

    선언 하나는 `{이름: {subClassOf: 상위 클래스 이름}}`이다. 상위 클래스는 공통 어휘의 클래스이거나 같은 `classes`에 선언한
    클래스다. 틀린 선언은 `problems`에 모으고 그 클래스를 선언하지 않은 것으로 하며, 나머지 선언은 계속 읽는다.
    """
    result = _Declarations()

    def problem(message: str) -> None:
        result.problems.append(Problem(yaml_file, message, INVALID_CLASS_DECLARATION))

    if declarations is None:
        return result, set()
    if not isinstance(declarations, dict):
        problem(f"`{CLASSES_KEY}`가 클래스 이름과 선언의 목록이 아니다")
        return result, set()

    superclasses: dict[str, str] = {}  # 형식이 맞는 선언의 이름 -> 상위 클래스 이름
    for key, declaration in declarations.items():
        name = str(key)
        where = f"`{CLASSES_KEY}.{name}`"
        if not isinstance(key, str):
            # YAML 1.1은 따옴표 없는 No, Yes, On, Off, Null, 숫자를 문자열이 아닌 값으로 읽는다. str()로 바꾸면 다른 이름이 된다.
            problem(
                f"{where}: 클래스 이름은 문자열이어야 한다. YAML은 따옴표 없는 `No`, `Yes`, `On`, `Off`, `Null`, 숫자를 "
                f"문자열로 읽지 않으니 따옴표로 감싼다(읽힌 값: `{key!r}`)"
            )
        elif not CLASS_NAME.fullmatch(name):
            problem(f"{where}: 클래스 이름은 영어 대문자로 시작하고 영어와 숫자만 쓴다(예: `Invoice`)")
        elif name in context:
            problem(f"{where}: 공통 어휘의 용어라 하위 클래스 이름으로 쓸 수 없다")
        elif not isinstance(declaration, dict):
            problem(f"{where}: 선언이 키와 값의 목록이 아니다(예: `subClassOf: Component`)")
        elif unknown := sorted(str(k) for k in declaration if k not in CLASS_DECLARATION_KEYS):
            allowed = ", ".join(CLASS_DECLARATION_KEYS)
            problem(f"{where}: 정의되지 않은 키 {', '.join(f'`{k}`' for k in unknown)}가 있다(쓸 수 있는 키: {allowed})")
        elif not isinstance(declaration.get("subClassOf"), str) or not declaration["subClassOf"].strip():
            problem(f"{where}: `subClassOf`에 상위 클래스 이름 하나를 문자열로 적어야 한다")
        else:
            superclasses[name] = declaration["subClassOf"].strip()

    declared = set(superclasses)
    for name, superclass in superclasses.items():
        where = f"`{CLASSES_KEY}.{name}`"
        if superclass not in declared and superclass not in common_classes:
            problem(f"{where}의 상위 클래스 `{superclass}`가 공통 어휘에도 이 지식 저장소의 `{CLASSES_KEY}`에도 없다")
            continue
        root, cyclic = _root(name, superclasses, common_classes)
        if cyclic:
            problem(f"{where}: 상위 클래스를 따라가면 순환해 공통 어휘의 클래스에 닿지 않는다")
            continue
        if root is None:
            continue  # 상위 클래스를 따라가다 없는 이름을 만났다. 그 선언이 이미 문제로 알려진다.
        if root in UNPAGED_CLASSES:
            problem(
                f"{where}: 상위 클래스를 따라가면 `{root}`에 닿는데, `{root}`는 {UNPAGED_CLASSES[root]}라 하위 클래스를 선언할 수 없다"
            )
            continue
        super_iri = class_iri(repository, superclass) if superclass in declared else str(common_classes[superclass])
        result.nodes.append(
            {
                "@id": class_iri(repository, name),
                "@type": str(OWL.Class),
                str(RDFS.label): {"@value": name, "@language": "en"},
                str(RDFS.subClassOf): {"@id": super_iri},
                # 엔티티의 출처(`onto:repository`)와 구분한다. 엔티티를 지식 저장소로 묻는 질의에 클래스 선언이 섞이지 않는다.
                "onto:declaredIn": repository,
            }
        )
    return result, declared


def _root(name: str, superclasses: dict[str, str], common_classes: dict[str, URIRef]) -> tuple[str | None, bool]:
    """선언한 클래스 `name`의 상위 클래스를 따라가 닿는 공통 어휘의 클래스 이름과, 순환했는지를 돌려준다.

    순환하면 `(None, True)`다. 선언에도 공통 어휘에도 없는 이름에서 끊기면 `(None, False)`다.
    """
    seen: set[str] = set()
    while name in superclasses:
        if name in seen:
            return None, True
        seen.add(name)
        name = superclasses[name]
    return (name, False) if name in common_classes else (None, False)
