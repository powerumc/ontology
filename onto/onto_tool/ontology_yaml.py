"""지식 저장소의 `docs/ontology/ontology.yaml`: 저장소 이름과 `Project` 엔티티를 서술하는 값."""

from pathlib import Path

from .keys import ONTOLOGY_YAML_KEYS, ONTOLOGY_YAML_REQUIRED_KEYS
from .textfile import load_yaml_text


class OntologyYamlError(Exception):
    """`ontology.yaml`을 읽을 수 없다. 메시지는 이유다. 파일 이름은 부른 쪽이 붙인다."""


def read_ontology_yaml(path: Path) -> dict[str, object]:
    data = load_yaml_text(path, OntologyYamlError)
    if not isinstance(data, dict):
        raise OntologyYamlError("키와 값의 목록이 아니다")
    for key in ONTOLOGY_YAML_REQUIRED_KEYS:
        value = data.get(key)
        if not isinstance(value, str) or not value:
            raise OntologyYamlError(f"필수 키 `{key}`가 없거나 문자열이 아니다")
    return data


def undefined_keys_message(data: dict[str, object]) -> str | None:
    """`ontology.yaml` 최상위에 정의되지 않은 키(`keys.ONTOLOGY_YAML_KEYS`에 없는 키)가 있으면 그것을 알리는 설명, 없으면 None.

    컴파일과 `rules` 명령이 같은 판정을 쓴다. 오타가 조용히 무시되지 않게 하려는 것이다.
    """
    unknown = sorted(str(key) for key in data if key not in ONTOLOGY_YAML_KEYS)
    if not unknown:
        return None
    allowed = ", ".join(f"`{key}`" for key in sorted(ONTOLOGY_YAML_KEYS))
    return f"정의되지 않은 키 {', '.join(f'`{key}`' for key in unknown)}가 있다(쓸 수 있는 키: {allowed})"
