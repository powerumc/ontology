"""관계의 값(참조)을 훑는 검사 항목: 깨진 참조, 등록되지 않은 지식 저장소, 파일 경로.

그래프가 아니라 페이지의 frontmatter 원문에서 본다. 등록되지 않은 저장소 이름을 쓴 교차 참조는 컴파일에서 오류 없이
그 문자열 그대로의 IRI가 되어 그래프만으로는 깨진 참조와 구별되지 않기 때문이다. 참조를 엔티티의 IRI로 바꾸는 규칙은
컴파일과 같은 `iri.resolve_reference`를 쓴다.

가리키는 쪽의 사정으로 엔티티를 알 수 없을 때는 그 원인이 따로 보고되므로 참조를 문제 삼지 않는다.
- 읽을 수 없는 페이지: 있는 페이지로 친다(읽을 수 없는 파일로 한 번만 보고된다).
- `ontology.yaml`을 읽을 수 없는 지식 저장소: `name`을 몰라 엔티티의 IRI를 만들 수 없다. 그 저장소로 가는 참조는 건너뛴다.

관계의 값은 식별자(`component/api`)나 교차 참조(`billing:component/api`)여야 한다. 파일 경로(`docs/design.md`,
`../shop/docs/ontology/component/api.md`)는 저장소 밖의 파일을 가리키거나(지식 저장소가 단독으로 열리면 깨진다) 다른 저장소의 위치를
드러내므로 `path-reference`로 잡는다. 가리키는 엔티티가 있으면 파일 경로 모양이어도 식별자로 본다(언어 규칙의 `identifier-pattern`이
점을 허용하는 저장소). 파일 경로는 깨진 참조나 등록되지 않은 지식 저장소로 다시 보고하지 않는다.
"""

import re
from collections.abc import Iterator

from ..compiler import PROJECT_IDENTIFIER, Compiled
from ..iri import entity_iri, resolve_reference
from ..rules import RuleSet
from .catalog import BROKEN_REFERENCE, PATH_REFERENCE, UNREGISTERED_REPOSITORY
from .model import Issue

_DRIVE = re.compile(r"[A-Za-z]:[\\/]")  # `C:\work`, `C:/work`
_EXTENSION = re.compile(r"[^/.]\.[A-Za-z0-9]+$")  # 식별자의 마지막 조각이 `design.md`처럼 확장자로 끝난다


def is_file_path(reference: str) -> bool:
    """관계의 값이 식별자나 교차 참조가 아니라 파일 경로의 모양인가.

    절대 경로(`/…`, `~…`, `C:\\…`), 역슬래시, `.`이나 `..` 조각, 확장자로 끝나는 마지막 조각이 파일 경로의 모양이다.
    `://`가 든 주소는 파일 경로가 아니다. 가리키는 엔티티가 있는지는 따지지 않는다. 부른 쪽이 본다.
    """
    if "://" in reference:
        return False
    if reference.startswith(("/", "~", "\\")) or _DRIVE.match(reference) or "\\" in reference:
        return True
    identifier = reference.partition(":")[2] if ":" in reference else reference  # 교차 참조의 저장소 이름은 뗀다
    return any(segment in (".", "..") for segment in identifier.split("/")) or bool(_EXTENSION.search(identifier.rsplit("/", 1)[-1]))


def find(compiled: Compiled, rules: RuleSet) -> Iterator[Issue]:
    records = compiled.records
    # 지식 저장소는 `name`으로도 서브모듈 디렉토리 이름으로도 가리킬 수 있다. 둘이 다르면 그 문제는 따로 보고한다.
    registered = {name for record in records for name in (record.directory, record.name) if name}
    unreadable = {record.directory for record in records if record.has_layer and record.name is None}
    without_layer = {record.directory for record in records if not record.has_layer}
    entities = {
        entity_iri(record.name, identifier)
        for record in records
        if record.name is not None
        for identifier in (PROJECT_IDENTIFIER, *(page.identifier for page in record.pages))
    }
    for record in records:
        if record.name is None:
            continue
        for page in record.pages:
            for key, target in page.relations():
                where = f"`{key}`의 값 `{target}`"
                repository, separator, _ = target.partition(":")
                repository = repository.strip()
                if is_file_path(target) and resolve_reference(record.name, target) not in entities:
                    yield Issue(
                        PATH_REFERENCE,
                        page.file,
                        f"{where}: 식별자나 교차 참조가 아니라 파일 경로다. 같은 지식 저장소의 엔티티는 식별자(`component/api`)로, "
                        "다른 지식 저장소의 엔티티는 교차 참조(`<저장소 이름>:<식별자>`)로 가리킨다",
                    )
                elif separator and repository not in registered:
                    yield Issue(
                        UNREGISTERED_REPOSITORY,
                        page.file,
                        f"{where}: 등록되지 않은 지식 저장소를 가리킨다(저장소 이름: `{repository}`)",
                    )
                elif separator and repository in unreadable:
                    continue
                elif separator and repository in without_layer:
                    yield Issue(BROKEN_REFERENCE, page.file, f"{where}: 지식 저장소 `{repository}`에 온톨로지 층이 없다")
                elif resolve_reference(record.name, target) not in entities:
                    yield Issue(BROKEN_REFERENCE, page.file, f"{where}: 가리키는 엔티티가 없다")
