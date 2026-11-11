"""컴파일: 지식 저장소의 페이지를 하나의 RDF 그래프로 바꾼다.

페이지의 frontmatter를 JSON-LD context(`vocab/context.jsonld`)로 RDF에 대응시킨다.
같은 입력에서는 같은 그래프가 나온다. 파일을 이름 순으로 읽고, 트리플을 정렬해 싣는다.
"""

import json
from dataclasses import dataclass

from rdflib import Graph

from . import vocab
from .errors import OntoError
from .iri import entity_iri
from .ontology_yaml import OntologyYamlError, read_ontology_yaml
from .pages import FrontmatterError, find_pages, read_page, scalar_values
from .workspace import ONTOLOGY_YAML, Repository, Workspace

PROJECT_IDENTIFIER = "project"
# `ontology.yaml`에서 `Project` 엔티티의 사실이 되는 키. 그 밖의 키(`name`, 공유 범위, 규칙)는 엔티티를 서술하지 않는다.
PROJECT_KEYS = ("title", "description", "aliases")


@dataclass
class Compiled:
    graph: Graph
    files: dict[str, str]  # 엔티티 IRI -> 루트 저장소 기준 파일 경로. 질의 결과에서 엔티티를 파일로 보여 준다.
    repositories: list[str]  # 컴파일한 지식 저장소의 이름
    warnings: list[str]


def compile_workspace(workspace: Workspace) -> Compiled:
    """루트 저장소의 `projects/` 아래 지식 저장소를 모두 컴파일한다.

    읽을 수 없는 파일이 있으면 모두 모아 `OntoError`로 알린다. 일부만 컴파일한 그래프는 내놓지 않는다.
    """
    context = vocab.load_context()
    relations = vocab.relation_keys(context)
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
        try:
            name, repository_nodes, repository_files = _read_repository(workspace, repository, relations)
        except OntoError as exc:
            problems += exc.messages
            continue
        names.append(name)
        nodes += repository_nodes
        files.update(repository_files)
    if problems:
        raise OntoError(*problems)

    raw = Graph(bind_namespaces="none")
    vocab.load_vocab(raw)
    raw.parse(data=json.dumps({"@context": context, "@graph": nodes}), format="json-ld")
    return Compiled(_canonical(raw), files, names, warnings)


def _read_repository(
    workspace: Workspace, repository: Repository, relations: frozenset[str]
) -> tuple[str, list[dict], dict[str, str]]:
    """지식 저장소 하나를 JSON-LD 객체로 읽는다. 읽을 수 없는 파일은 모두 모아 `OntoError`로 알린다."""
    yaml_path = repository.path / ONTOLOGY_YAML
    yaml_file = workspace.relative(yaml_path)
    try:
        data = read_ontology_yaml(yaml_path)
    except OntologyYamlError as exc:
        raise OntoError(f"{yaml_file}: {exc}") from exc
    name = str(data["name"])

    nodes: list[dict] = []
    files: dict[str, str] = {}
    problems: list[str] = []

    def add(identifier: str, meta: dict[str, object], file: str) -> None:
        node = _node(name, identifier, meta, relations)
        nodes.append(node)
        files[node["@id"]] = file

    try:
        project = scalar_values({key: data[key] for key in PROJECT_KEYS if key in data})
        add(PROJECT_IDENTIFIER, {"class": "Project", **project}, yaml_file)
    except FrontmatterError as exc:
        problems.append(f"{yaml_file}: {exc}")

    for identifier, path in find_pages(repository.ontology_dir):
        file = workspace.relative(path)
        try:
            add(identifier, read_page(identifier, path).meta, file)
        except FrontmatterError as exc:
            problems.append(f"{file}: frontmatter를 읽을 수 없다: {exc}")
    if problems:
        raise OntoError(*problems)
    return name, nodes, files


def _node(repository: str, identifier: str, meta: dict[str, object], relations: frozenset[str]) -> dict:
    """엔티티 하나의 JSON-LD 객체. 키는 context가 RDF에 대응시킨다. `@`로 시작하는 키는 JSON-LD의 예약어라 버린다."""
    node: dict = {"@id": entity_iri(repository, identifier)}
    for key, value in meta.items():
        if key.startswith("@"):
            continue
        node[key] = _references(repository, key, value) if key in relations else value
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
