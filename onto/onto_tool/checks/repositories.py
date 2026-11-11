"""지식 저장소 자체를 훑는 검사 항목: 이름과 디렉토리 이름의 일치, 온톨로지 층의 유무."""

from collections.abc import Iterator

from ..compiler import Compiled
from .catalog import MISSING_ONTOLOGY_LAYER, REPOSITORY_NAME_MISMATCH
from .model import Issue


def find(compiled: Compiled) -> Iterator[Issue]:
    for record in compiled.records:
        if not record.has_layer:
            yield Issue(
                MISSING_ONTOLOGY_LAYER,
                record.path,
                f"지식 저장소 `{record.directory}`에 온톨로지 층({record.yaml_file})이 없어 검사하지 못했다",
            )
        elif record.name is not None and record.name != record.directory:
            # IRI와 교차 참조는 `name`으로 만들어지므로, 디렉토리 이름과 다르면 교차 참조가 엉뚱한 저장소를 가리킨다.
            yield Issue(
                REPOSITORY_NAME_MISMATCH,
                record.yaml_file,
                f"ontology.yaml의 name(`{record.name}`)이 서브모듈 디렉토리 이름(`{record.directory}`)과 다르다",
            )
