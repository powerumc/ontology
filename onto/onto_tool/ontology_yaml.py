"""지식 저장소의 `docs/ontology/ontology.yaml`: 저장소 이름과 `Project` 엔티티를 서술하는 값."""

from pathlib import Path

import yaml


class OntologyYamlError(Exception):
    """`ontology.yaml`을 읽을 수 없다. 메시지는 이유다. 파일 이름은 부른 쪽이 붙인다."""


def read_ontology_yaml(path: Path) -> dict[str, object]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise OntologyYamlError("UTF-8 문서가 아니다") from exc
    except yaml.YAMLError as exc:
        raise OntologyYamlError(f"YAML 문법 오류: {str(exc).strip().splitlines()[0]}") from exc
    if not isinstance(data, dict):
        raise OntologyYamlError("키와 값의 목록이 아니다")
    name = data.get("name")
    if not isinstance(name, str) or not name:
        raise OntologyYamlError("저장소 이름 `name`이 없다")
    return data
