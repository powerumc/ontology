"""참조를 훑는 검사 항목: 깨진 참조, 등록되지 않은 지식 저장소, 식별자도 교차 참조도 아닌 값(파일 경로).

훑는 것은 페이지의 관계의 값과 `Project` 엔티티의 관계의 값(`ontology.yaml`의 `dependsOn`)이다.
`Project`는 페이지가 없어 자기가 쓰는 관계를 `ontology.yaml`에 적는다. 그 값은 페이지의 관계와 같은 규칙으로 검사하고, 문제는 `ontology.yaml`의 것으로 보고한다.

관계의 값은 그래프가 아니라 frontmatter 원문(`ontology.yaml`은 그 값)에서 본다. 등록되지 않은 저장소 이름을 쓴 교차 참조는 컴파일에서 오류 없이
그 문자열 그대로의 IRI가 되어 그래프만으로는 깨진 참조와 구별되지 않기 때문이다. 참조를 엔티티의 IRI로 바꾸는 규칙은
컴파일과 같은 `iri.resolve_reference`를 쓴다.

가리키는 쪽의 사정으로 엔티티를 알 수 없을 때는 그 원인이 따로 보고되므로 참조를 문제 삼지 않는다.
- 읽을 수 없는 페이지: 있는 페이지로 친다(읽을 수 없는 파일로 한 번만 보고된다).
- `ontology.yaml`을 읽을 수 없는 지식 저장소: `name`을 몰라 엔티티의 IRI를 만들 수 없다. 그 저장소로 가는 참조는 건너뛴다.

관계의 값은 식별자(`component/api`, `project`)나 교차 참조(`billing:component/api`)여야 한다. 그 밖의 값은 `path-reference`로 잡는다. 이 항목은
루트 전용이다. 저장소 밖의 파일을 가리키는 경로는 지식 저장소가 단독으로 열리면 깨지고 다른 저장소의 위치를 드러내는데, 같은 값을 깨진 참조나
등록되지 않은 지식 저장소로만 보고하면 그 항목을 저장소 규칙으로 꺼서 통과시킬 수 있기 때문이다. 식별자도 교차 참조도 아닌 값은 다음이다.

- 파일 경로의 모양: 절대 경로(`/…`, `~…`, `C:\…`), `file:` 주소, 역슬래시, `.`이나 `..` 조각, 확장자로 끝나는 마지막 조각
- 주소(`https://…`)
- 첫 조각이 페이지를 두는 클래스 디렉토리(`component/`, `plan/` …)가 아닌 식별자 모양(`docs/ontology/plan/x`, `projects/billing/…`, `componet/api`).
  페이지는 언제나 클래스 디렉토리 아래에 있고(하위 클래스의 페이지도 공통 조상 클래스의 디렉토리다) `Project`의 식별자는 `project`다.
  그래서 첫 조각이 그 밖이면 식별자가 아니다. 클래스 디렉토리 이름의 오타도 이렇게 잡힌다.

가리키는 엔티티가 있으면 모양과 상관없이 식별자로 본다(루트의 언어 규칙 `identifier-pattern`이 점을 허용하는 경우, 클래스 디렉토리 밖에 잘못
둔 페이지). 이런 값은 깨진 참조나 등록되지 않은 지식 저장소로 다시 보고하지 않는다.
"""

import re
from collections.abc import Iterator

from ..compiler import PROJECT_IDENTIFIER, Compiled, PageRecord, RepositoryRecord
from ..iri import entity_iri, resolve_reference
from ..keys import PAGE_CLASS_DIRECTORIES
from ..rules import RuleSet
from .catalog import BROKEN_REFERENCE, PATH_REFERENCE, UNREGISTERED_REPOSITORY
from .model import Issue

_DRIVE = re.compile(r"[A-Za-z]:[\\/]")  # `C:\work`, `C:/work`
_FILE_URL = re.compile(r"file:", re.IGNORECASE)
_EXTENSION = re.compile(r"[^/.]\.[A-Za-z0-9]+$")  # 식별자의 마지막 조각이 `design.md`처럼 확장자로 끝난다
CLASS_DIRECTORIES = tuple(PAGE_CLASS_DIRECTORIES.values())


def not_a_reference(reference: str) -> str | None:
    """관계의 값 `reference`가 식별자도 교차 참조도 아니면 그 이유를, 식별자나 교차 참조의 모양이면 None을 돌려준다.

    가리키는 엔티티가 있는지는 따지지 않는다. 부른 쪽이 본다.
    """
    if _FILE_URL.match(reference):
        return "`file:` 주소다"
    if "://" in reference:
        return "주소다"
    if reference.startswith(("/", "~", "\\")) or _DRIVE.match(reference) or "\\" in reference:
        return "파일 경로다"
    identifier = (reference.partition(":")[2] if ":" in reference else reference).strip()  # 교차 참조의 저장소 이름은 뗀다. 해석(`resolve_reference`)처럼 앞뒤 공백도 뗀다
    segments = identifier.split("/")
    if any(segment in (".", "..") for segment in segments) or _EXTENSION.search(segments[-1]):
        return "파일 경로다"
    if identifier != PROJECT_IDENTIFIER and segments[0] not in CLASS_DIRECTORIES:
        shown = ", ".join(f"`{directory}/`" for directory in CLASS_DIRECTORIES)
        return f"파일 경로이거나 식별자가 아니다(식별자의 첫 조각은 페이지를 두는 클래스 디렉토리({shown}) 가운데 하나여야 한다)"
    return None


class _Known:
    """참조가 가리킬 수 있는 것: 등록된 지식 저장소와 그 안의 엔티티."""

    def __init__(self, records: list[RepositoryRecord]) -> None:
        # 지식 저장소는 `name`으로도 서브모듈 디렉토리 이름으로도 가리킬 수 있다. 둘이 다르면 그 문제는 따로 보고한다.
        self.registered = {name for record in records for name in (record.directory, record.name) if name}
        self.unreadable = {record.directory for record in records if record.has_layer and record.name is None}
        self.without_layer = {record.directory for record in records if not record.has_layer}
        self.entities = {
            entity_iri(record.name, identifier)
            for record in records
            if record.name is not None
            for identifier in (PROJECT_IDENTIFIER, *(page.identifier for page in record.pages))
        }

    def exists(self, record: RepositoryRecord, target: str) -> bool:
        """`record`의 저장소에서 쓴 식별자나 교차 참조 `target`이 가리키는 엔티티가 있는가."""
        return resolve_reference(record.name, target) in self.entities

    def dangling(self, record: RepositoryRecord, page: PageRecord, where: str, target: str) -> Iterator[Issue]:
        """식별자나 교차 참조 `target`이 등록되지 않은 지식 저장소나 없는 엔티티를 가리키면 그 문제를 낸다. `where`는 설명이 가리킬 자리다."""
        repository, separator, _ = target.partition(":")
        repository = repository.strip()
        if separator and repository not in self.registered:
            yield Issue(UNREGISTERED_REPOSITORY, page.file, f"{where}: 등록되지 않은 지식 저장소를 가리킨다(저장소 이름: `{repository}`)")
        elif separator and repository in self.unreadable:
            return
        elif separator and repository in self.without_layer:
            yield Issue(BROKEN_REFERENCE, page.file, f"{where}: 지식 저장소 `{repository}`에 온톨로지 층이 없다")
        elif not self.exists(record, target):
            yield Issue(BROKEN_REFERENCE, page.file, f"{where}: 가리키는 엔티티가 없다")


def find(compiled: Compiled, rules: RuleSet) -> Iterator[Issue]:
    known = _Known(compiled.records)
    for record in compiled.records:
        if record.name is None:
            continue
        for page in record.referrers():
            for key, target in page.relations():
                where = f"`{key}`의 값 `{target}`"
                reason = not_a_reference(target)
                if reason and not known.exists(record, target):
                    yield Issue(
                        PATH_REFERENCE,
                        page.file,
                        f"{where}: 식별자나 교차 참조가 아니다({reason}). 같은 지식 저장소의 엔티티는 식별자(`component/api`)로, "
                        "다른 지식 저장소의 엔티티는 교차 참조(`<저장소 이름>:<식별자>`)로 가리킨다",
                    )
                else:
                    yield from known.dangling(record, page, where, target)

