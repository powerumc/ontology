"""컴파일: 지식 저장소의 페이지를 하나의 RDF 그래프로 바꾼다.

페이지의 frontmatter를 JSON-LD context(`vocab/context.jsonld`)로 RDF에 대응시킨다.
같은 입력에서는 같은 그래프가 나온다. 파일을 이름 순으로 읽고, 트리플을 정렬해 싣는다.
"""

import json
from dataclasses import dataclass, field

from rdflib import Graph

from . import vocab
from .errors import OntoError
from .iri import UNRESOLVED_BASE, entity_iri
from .keys import PAGE_KEYS, PROJECT_KEYS, RELATION_KEYS
from .ontology_yaml import OntologyYamlError, read_ontology_yaml
from .pages import FrontmatterError, find_pages, read_page, scalar_values
from .workspace import ONTOLOGY_YAML, Repository, Workspace

PROJECT_IDENTIFIER = "project"


@dataclass
class Compiled:
    graph: Graph  # 읽을 수 있었던 파일의 사실만 담는다
    files: dict[str, str]  # 엔티티 IRI -> 루트 저장소 기준 파일 경로. 질의 결과에서 엔티티를 파일로 보여 준다.
    repositories: list[str]  # 컴파일한 지식 저장소의 이름
    warnings: list[str]
    problems: list[str] = field(default_factory=list)  # 읽을 수 없는 파일과 이유. 메시지마다 파일 이름으로 시작한다.

    def ensure_valid(self) -> None:
        """읽을 수 없는 파일이 있으면 모두 모아 `OntoError`로 알린다.

        일부만 컴파일한 그래프를 내놓지 않는 것은 부르는 명령(`build`, `query`)의 정책이다.
        모든 문제를 모아 심각도별로 보고하는 검사는 `problems`를 그대로 쓴다.
        """
        if self.problems:
            raise OntoError(*self.problems)


@dataclass
class _RepositoryRead:
    name: str | None = None  # `ontology.yaml`을 읽을 수 없으면 알 수 없다
    nodes: list[dict] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def compile_workspace(workspace: Workspace) -> Compiled:
    """루트 저장소의 `projects/` 아래 지식 저장소를 모두 컴파일한다. 읽을 수 없는 파일은 `problems`에 모은다."""
    context = vocab.load_context()
    nodes: list[dict] = []
    files: dict[str, str] = {}
    names: list[str] = []
    problems: list[str] = []
    warnings: list[str] = []

    for repository in workspace.repositories():
        if not (repository.path / ONTOLOGY_YAML).is_file():
            warnings.append(
                f"{workspace.relative(repository.path)}: 온톨로지 층({ONTOLOGY_YAML.as_posix()})이 없어 건너뛰었다"
            )
            continue
        read = _read_repository(workspace, repository)
        problems += read.problems
        if read.name is not None:
            names.append(read.name)
        nodes += read.nodes
        files.update(read.files)

    raw = Graph(bind_namespaces="none")
    vocab.load_vocab(raw)
    raw.parse(data=json.dumps({"@context": context, "@graph": nodes}), format="json-ld", base=UNRESOLVED_BASE)
    return Compiled(_canonical(raw), files, names, warnings, problems)


def _read_repository(workspace: Workspace, repository: Repository) -> _RepositoryRead:
    """지식 저장소 하나를 JSON-LD 객체로 읽는다. 읽을 수 없는 파일은 모아 두고 나머지를 계속 읽는다."""
    read = _RepositoryRead()
    yaml_path = repository.path / ONTOLOGY_YAML
    yaml_file = workspace.relative(yaml_path)
    try:
        data = read_ontology_yaml(yaml_path)
    except OntologyYamlError as exc:
        read.problems.append(f"{yaml_file}: {exc}")
        return read
    name = read.name = str(data["name"])

    def add(identifier: str, meta: dict[str, object], file: str) -> None:
        node = _node(name, identifier, meta)
        read.nodes.append(node)
        read.files[node["@id"]] = file

    try:
        project = scalar_values({key: data[key] for key in PROJECT_KEYS if key in data})
        add(PROJECT_IDENTIFIER, {"class": "Project", **project}, yaml_file)
    except FrontmatterError as exc:
        read.problems.append(f"{yaml_file}: {exc}")

    for identifier, path in find_pages(repository.ontology_dir):
        file = workspace.relative(path)
        if identifier == PROJECT_IDENTIFIER:
            # 같은 IRI라서 두 파일이 제목과 클래스가 둘인 엔티티 하나로 조용히 합쳐진다.
            read.problems.append(
                f"{file}: 식별자 `{PROJECT_IDENTIFIER}`는 {yaml_file}에서 만드는 Project 엔티티의 것이라 페이지로 쓸 수 없다"
            )
            continue
        try:
            add(identifier, read_page(identifier, path).meta, file)
        except FrontmatterError as exc:
            read.problems.append(f"{file}: frontmatter를 읽을 수 없다: {exc}")
    return read


def _node(repository: str, identifier: str, meta: dict[str, object]) -> dict:
    """엔티티 하나의 JSON-LD 객체. `keys.PAGE_KEYS`에 있는 키만 옮기고, 키의 뜻은 context가 정한다.

    다른 키는 버린다. JSON-LD에 그대로 넘기면 `foo:bar` 같은 키가 술어가 되고, `@`로 시작하는 키는 예약어로 읽힌다.
    """
    node: dict = {"@id": entity_iri(repository, identifier)}
    for key, value in meta.items():
        if key in PAGE_KEYS:
            node[key] = _references(repository, key, value) if key in RELATION_KEYS else value
    return node


def _references(repository: str, key: str, value: object) -> object:
    """관계의 값(같은 지식 저장소 안의 식별자)을 엔티티의 IRI로 바꾼다."""
    targets = value if isinstance(value, list) else [value]
    if not all(isinstance(target, str) for target in targets):
        raise FrontmatterError(f"`{key}`의 값이 식별자 문자열이 아니다")
    iris = [entity_iri(repository, target.strip()) for target in targets]
    return iris if isinstance(value, list) else iris[0]


def _canonical(graph: Graph) -> Graph:
    """트리플을 정렬해 새 그래프에 싣는다. 같은 사실이면 저장 순서도 같아 질의 결과의 순서도 같다."""
    result = Graph(bind_namespaces="none")
    for prefix, namespace in sorted(graph.namespaces()):
        result.bind(prefix, namespace)
    for triple in sorted(graph):
        result.add(triple)
    return result
