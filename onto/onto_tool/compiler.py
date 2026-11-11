"""컴파일: 지식 저장소의 페이지를 하나의 RDF 그래프로 바꾼다.

페이지의 frontmatter를 JSON-LD context(`vocab/context.jsonld`)로 RDF에 대응시킨다.
같은 입력에서는 같은 그래프가 나온다. 파일을 이름 순으로 읽고, 트리플을 정렬해 싣는다.

여러 지식 저장소가 하나의 그래프로 합쳐진다. 관계의 값은 같은 저장소의 식별자이거나, 다른 저장소의 엔티티를 가리키는
교차 참조(`<저장소 이름>:<식별자>`)이고, 가리키는 엔티티가 있는지는 따지지 않는다. 모든 엔티티에는 온 지식 저장소의 이름을
`onto:repository`로 적는다. 저장소는 `ontology.yaml`의 `classes`로 자기 하위 클래스를 선언할 수 있다.
추론(하위 클래스, 역관계, 추이 관계)은 여기서 하지 않는다. `inference.infer`가 이 그래프에 적용한다.
"""

import json
import re
from dataclasses import dataclass, field

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDFS

from . import vocab
from .errors import OntoError
from .graphs import canonical
from .iri import UNRESOLVED_BASE, class_iri, entity_iri, resolve_reference, unresolved_iri
from .keys import CLASS_DECLARATION_KEYS, CLASSES_KEY, PAGE_KEYS, PROJECT_KEYS, RELATION_KEYS
from .ontology_yaml import OntologyYamlError, read_ontology_yaml
from .pages import FrontmatterError, find_pages, read_page, scalar_values
from .workspace import ONTOLOGY_YAML, Repository, Workspace

PROJECT_IDENTIFIER = "project"
# 지식 저장소가 선언하는 클래스의 이름. 공통 어휘의 클래스 이름처럼 영어로 쓰고 대문자로 시작한다.
CLASS_NAME = re.compile(r"[A-Z][A-Za-z0-9]*")
# 페이지로 서술하지 않는 공통 클래스와 그 이유. 하위 클래스를 선언해 페이지가 이 클래스의 엔티티가 되게 할 수 없다.
UNPAGED_CLASSES = {
    "Project": "별도 페이지 없이 ontology.yaml에서만 만들어지는 클래스",
    "Source": "페이지를 따로 갖지 않는 클래스",
}


@dataclass
class Compiled:
    graph: Graph  # 읽을 수 있었던 파일의 사실만 담는다. 추론은 하지 않은, 적힌 그대로의 사실이다.
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
    nodes: list[dict] = field(default_factory=list)  # 엔티티와, 선언한 하위 클래스
    files: dict[str, str] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def compile_workspace(workspace: Workspace) -> Compiled:
    """루트 저장소의 `projects/` 아래 지식 저장소를 모두 컴파일한다. 읽을 수 없는 파일은 `problems`에 모은다."""
    context = vocab.load_context()
    raw = Graph(bind_namespaces="none")
    vocab.load_vocab(raw)
    common_classes = vocab.common_classes(raw)
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
        read = _read_repository(workspace, repository, context, common_classes)
        problems += read.problems
        if read.name is not None:
            names.append(read.name)
        nodes += read.nodes
        files.update(read.files)

    raw.parse(data=json.dumps({"@context": context, "@graph": nodes}), format="json-ld", base=UNRESOLVED_BASE)
    return Compiled(canonical(raw), files, names, warnings, problems)


def _read_repository(
    workspace: Workspace, repository: Repository, context: dict, common_classes: dict[str, URIRef]
) -> _RepositoryRead:
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

    declarations, declared = _declare_classes(name, data.get(CLASSES_KEY), context, common_classes, yaml_file)
    read.nodes += declarations.nodes
    read.problems += declarations.problems

    def add(identifier: str, meta: dict[str, object], file: str) -> None:
        node = _node(name, identifier, meta, declared)
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


def _node(repository: str, identifier: str, meta: dict[str, object], declared_classes: set[str]) -> dict:
    """엔티티 하나의 JSON-LD 객체. `keys.PAGE_KEYS`에 있는 키만 옮기고, 키의 뜻은 context가 정한다.

    다른 키는 버린다. JSON-LD에 그대로 넘기면 `foo:bar` 같은 키가 술어가 되고, `@`로 시작하는 키는 예약어로 읽힌다.
    엔티티가 어느 지식 저장소에서 왔는지(`onto:repository`)는 페이지가 아니라 컴파일이 적는다. 페이지의 키로는 속일 수 없다.
    """
    node: dict = {"@id": entity_iri(repository, identifier), "onto:repository": repository}
    for key, value in meta.items():
        if key == "class":
            node[key] = _classes(repository, value, declared_classes)
        elif key in PAGE_KEYS:
            node[key] = _references(repository, key, value) if key in RELATION_KEYS else value
    return node


def _classes(repository: str, value: object, declared_classes: set[str]) -> object:
    """`class`의 값 가운데 이 지식 저장소가 선언한 클래스의 이름을 그 클래스의 IRI로 바꾼다. 다른 이름은 context가 푼다.

    클래스는 이름으로만 쓴다. `:`가 든 값(`https://…`, `onto:Component`)은 JSON-LD가 IRI로 읽어 어느 클래스든 가리킬 수 있어,
    다른 저장소가 선언한 클래스를 이름만으로는 못 끌어 쓰는 제한을 우회한다. 그런 값은 어느 클래스도 가리키지 않는
    풀리지 않은 클래스로 남긴다. 알 수 없는 클래스를 오류로 알리는 것은 스크립트 검사의 몫이다.
    """

    def resolve(name: object) -> object:
        if isinstance(name, str) and name in declared_classes:
            return class_iri(repository, name)
        if isinstance(name, str) and ":" in name:
            return unresolved_iri(name)
        return name

    names = value if isinstance(value, list) else [value]
    resolved = [resolve(name) for name in names]
    return resolved if isinstance(value, list) else resolved[0]


def _references(repository: str, key: str, value: object) -> object:
    """관계의 값(식별자 또는 `<저장소 이름>:<식별자>` 교차 참조)을 엔티티의 IRI로 바꾼다."""
    targets = value if isinstance(value, list) else [value]
    if not all(isinstance(target, str) for target in targets):
        raise FrontmatterError(f"`{key}`의 값이 식별자 문자열이 아니다")
    iris = [resolve_reference(repository, target) for target in targets]
    return iris if isinstance(value, list) else iris[0]


@dataclass
class _Declarations:
    nodes: list[dict] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _declare_classes(
    repository: str, declarations: object, context: dict, common_classes: dict[str, URIRef], yaml_file: str
) -> tuple[_Declarations, set[str]]:
    """`ontology.yaml`의 `classes`를 클래스 선언의 JSON-LD 객체로 바꾼다. 선언된 클래스 이름의 집합도 돌려준다.

    선언 하나는 `{이름: {subClassOf: 상위 클래스 이름}}`이다. 상위 클래스는 공통 어휘의 클래스이거나 같은 `classes`에 선언한
    클래스다. 틀린 선언은 `problems`에 모으고 그 클래스를 선언하지 않은 것으로 하며, 나머지 선언은 계속 읽는다.
    """
    result = _Declarations()
    if declarations is None:
        return result, set()
    if not isinstance(declarations, dict):
        result.problems.append(f"{yaml_file}: `{CLASSES_KEY}`가 클래스 이름과 선언의 목록이 아니다")
        return result, set()

    superclasses: dict[str, str] = {}  # 형식이 맞는 선언의 이름 -> 상위 클래스 이름
    for key, declaration in declarations.items():
        name = str(key)
        where = f"{yaml_file}: `{CLASSES_KEY}.{name}`"
        if not isinstance(key, str):
            # YAML 1.1은 따옴표 없는 No, Yes, On, Off, Null, 숫자를 문자열이 아닌 값으로 읽는다. str()로 바꾸면 다른 이름이 된다.
            result.problems.append(
                f"{where}: 클래스 이름은 문자열이어야 한다. YAML은 따옴표 없는 `No`, `Yes`, `On`, `Off`, `Null`, 숫자를 "
                f"문자열로 읽지 않으니 따옴표로 감싼다(읽힌 값: `{key!r}`)"
            )
        elif not CLASS_NAME.fullmatch(name):
            result.problems.append(f"{where}: 클래스 이름은 영어 대문자로 시작하고 영어와 숫자만 쓴다(예: `Invoice`)")
        elif name in context:
            result.problems.append(f"{where}: 공통 어휘의 용어라 하위 클래스 이름으로 쓸 수 없다")
        elif not isinstance(declaration, dict):
            result.problems.append(f"{where}: 선언이 키와 값의 목록이 아니다(예: `subClassOf: Component`)")
        elif unknown := sorted(str(k) for k in declaration if k not in CLASS_DECLARATION_KEYS):
            allowed = ", ".join(CLASS_DECLARATION_KEYS)
            result.problems.append(f"{where}: 정의되지 않은 키 {', '.join(f'`{k}`' for k in unknown)}가 있다(쓸 수 있는 키: {allowed})")
        elif not isinstance(declaration.get("subClassOf"), str) or not declaration["subClassOf"].strip():
            result.problems.append(f"{where}: `subClassOf`에 상위 클래스 이름 하나를 문자열로 적어야 한다")
        else:
            superclasses[name] = declaration["subClassOf"].strip()

    declared = set(superclasses)
    for name, superclass in superclasses.items():
        where = f"{yaml_file}: `{CLASSES_KEY}.{name}`"
        if superclass not in declared and superclass not in common_classes:
            result.problems.append(
                f"{where}의 상위 클래스 `{superclass}`가 공통 어휘에도 이 지식 저장소의 `{CLASSES_KEY}`에도 없다"
            )
            continue
        root, cyclic = _root(name, superclasses, common_classes)
        if cyclic:
            result.problems.append(f"{where}: 상위 클래스를 따라가면 순환해 공통 어휘의 클래스에 닿지 않는다")
            continue
        if root is None:
            continue  # 상위 클래스를 따라가다 없는 이름을 만났다. 그 선언이 이미 문제로 알려진다.
        if root in UNPAGED_CLASSES:
            result.problems.append(
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
