"""`rules`: 적용되는 규칙을 JSON으로 보여 준다. 지식 저장소를 주면 그 저장소의 `ontology.yaml`이 덮어쓴 값까지 합친 규칙이다."""

import argparse
import json
import os

from ..checks import rule_set
from ..compiler import LINK_OUTSIDE
from ..errors import OntoError
from ..keys import RULES_KEY
from ..ontology_yaml import OntologyYamlError, read_ontology_yaml, undefined_keys_message
from ..paths import is_inside, real_path
from ..textfile import is_missing
from ..workspace import ONTOLOGY_YAML, Within
from ._rules import root_rules
from ._workspace import open_workspace

NAME = "rules"
HELP = (
    "적용되는 규칙을 JSON으로 보여 준다. 지식 저장소의 이름(서브모듈 디렉토리 이름)을 주면 그 저장소의 ontology.yaml의 rules가 "
    "루트 기본 규칙(rules.yaml)을 덮어쓴 결과이고, 주지 않으면 루트 기본 규칙이다. 지식 저장소 안에서는 이름을 주지 않아도 그 저장소의 "
    "덮어쓰기까지 합친 규칙이다(온톨로지 층이 없으면 기본 규칙). 어떤 파일도 고치지 않는다"
)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("repository", nargs="?", help="지식 저장소의 이름(서브모듈 디렉토리 이름). 생략하면 루트 기본 규칙. 지식 저장소 안에서는 생략하면 그 저장소")


def run(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    rules = root_rules(workspace)
    known = {repository.directory: repository for repository in workspace.repositories()}
    name = args.repository
    if name is None and workspace.within is Within.REPOSITORY:
        # 지식 저장소 안에서는 다룰 저장소가 하나뿐이라 이름을 생략하면 그 저장소다. 덮어쓸 온톨로지 층이 아직 없으면 기본 규칙이다.
        (only,) = known.values()
        name = only.directory if (only.path / ONTOLOGY_YAML).is_file() else None
    if name is not None:
        if name not in known:
            raise OntoError(f"지식 저장소 `{name}`가 없다(있는 것: {', '.join(known) or '없음'})")
        yaml_file = known[name].path / ONTOLOGY_YAML
        where = workspace.display(yaml_file)
        # 컴파일이 읽지 않는 ontology.yaml(저장소 밖을 가리키는 심볼릭 링크)은 여기서도 읽지 않는다. 읽으면 다른 저장소의 덮어쓰기가 이 저장소의 규칙으로 보여
        # `validate`가 실제로 쓰는 규칙과 어긋난다. 가리키는 파일이 없는 링크도 같다.
        if os.path.lexists(yaml_file) and not is_inside(yaml_file, real_path(known[name].path)):
            raise OntoError(f"{where}: {LINK_OUTSIDE.format('ontology.yaml')}")
        if is_missing(yaml_file):
            raise OntoError(f"{where}: 온톨로지 층이 없다")
        try:
            data = read_ontology_yaml(yaml_file)
        except OntologyYamlError as exc:
            raise OntoError(f"{where}: {exc}") from exc
        if undefined := undefined_keys_message(data):  # `rule:` 같은 오타가 조용히 기본값으로 읽히지 않게 한다
            raise OntoError(f"{where}: {undefined}")
        applied = rule_set(rules, {name: data[RULES_KEY]} if data.get(RULES_KEY) is not None else {})
        if applied.problems:
            raise OntoError(*(f"{where}: {reason}" for reason in applied.problems[name]))
        rules = applied.of(name)
    print(json.dumps(rules.values, ensure_ascii=False, indent=2))
    return 0
