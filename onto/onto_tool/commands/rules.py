"""`rules`: 적용되는 규칙을 JSON으로 보여 준다. 지식 저장소를 주면 그 저장소의 `ontology.yaml`이 덮어쓴 값까지 합친 규칙이다."""

import argparse
import json

from ..checks import rule_set
from ..errors import OntoError
from ..keys import RULES_KEY
from ..ontology_yaml import OntologyYamlError, read_ontology_yaml, undefined_keys_message
from ..workspace import ONTOLOGY_YAML
from ._rules import root_rules
from ._workspace import open_workspace

NAME = "rules"
HELP = (
    "적용되는 규칙을 JSON으로 보여 준다. 지식 저장소의 이름(서브모듈 디렉토리 이름)을 주면 그 저장소의 ontology.yaml의 rules가 "
    "루트 기본 규칙(rules.yaml)을 덮어쓴 결과이고, 주지 않으면 루트 기본 규칙이다. 어떤 파일도 고치지 않는다"
)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("repository", nargs="?", help="지식 저장소의 이름(서브모듈 디렉토리 이름). 생략하면 루트 기본 규칙")


def run(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    rules = root_rules(workspace)
    if args.repository is not None:
        known = {repository.directory: repository for repository in workspace.repositories()}
        if args.repository not in known:
            raise OntoError(f"지식 저장소 `{args.repository}`가 없다(있는 것: {', '.join(known) or '없음'})")
        yaml_file = known[args.repository].path / ONTOLOGY_YAML
        where = workspace.display(yaml_file)
        try:
            data = read_ontology_yaml(yaml_file)
        except FileNotFoundError as exc:
            raise OntoError(f"{where}: 온톨로지 층이 없다") from exc
        except OntologyYamlError as exc:
            raise OntoError(f"{where}: {exc}") from exc
        if undefined := undefined_keys_message(data):  # `rule:` 같은 오타가 조용히 기본값으로 읽히지 않게 한다
            raise OntoError(f"{where}: {undefined}")
        applied = rule_set(rules, {args.repository: data[RULES_KEY]} if data.get(RULES_KEY) is not None else {})
        if applied.problems:
            raise OntoError(*(f"{where}: {reason}" for reason in applied.problems[args.repository]))
        rules = applied.of(args.repository)
    print(json.dumps(rules.values, ensure_ascii=False, indent=2))
    return 0
