"""공유 범위(`ontology.yaml`의 `scope`)를 훑는 검사 항목: 값이 맞는지, 교차 참조가 더 좁은 범위나 다른 팀의 저장소를 가리키지 않는지.

공유 범위를 지키는 안전장치라 이 모듈의 항목은 모두 루트 전용이다. 지식 저장소의 규칙이 끄거나 심각도를 바꿀 수 없다.

- 교차 참조는 관계의 값(`dependsOn: billing:component/api`)과 페이지 본문의 링크 대상(`[글](billing:component/api)`)이다. `Project`가
  `ontology.yaml`의 `dependsOn`에 적은 값도 관계의 값이라 같다(문제는 `ontology.yaml`의 것으로 보고한다).
  `class`의 값 `<저장소 이름>:<나머지>`(`class: billing:Invoice`)도 본다. 그런 값은 클래스를 풀지 못하는 값(`disallowed-class`)이지만 그 항목은 저장소 규칙으로
  끌 수 있어, 꺼도 저장소 이름이 담긴 채 통과하지 않게 한다. 같은 이유로 정의되지 않은 키(`undefined-key`)와 그 값, 값의 종류가 틀린 관계의 값(`invalid-value`:
  `dependsOn: {id: billing:component/api}`처럼 중첩된 값)에 든 문자열도 중첩까지 훑어 본다. 키-값의 값뿐 아니라 키도 본다(`notes: {billing:component/api: 메모}`).
  이 항목들도 저장소 규칙으로 끌 수 있기 때문이다.
  제목, 설명, 날짜, 별칭, 본문 평문처럼 참조가 아닌 글에 적힌 저장소 이름은 보지 않는다. 그런 글에 더 좁은 범위의 저장소 이름을 적지 않는 것은 작성자의 몫이다.
- 범위를 알 수 없는 저장소는 가장 좁은 `private`으로 본다. 적지 않은 저장소, 온톨로지 층이 없거나 `ontology.yaml`을 읽을 수 없는 저장소,
  `scope` 값이 틀린 저장소가 그렇다. 그 저장소의 문제는 저장소 규칙으로 끌 수 있는 항목이나 경고로만 보고되므로, 그것에 기대면
  비공개 저장소의 이름이 드러난 채 통과한다. `private`이면 값 오류도 따로 보고된다(`invalid-scope`).
- 참조가 가리키는 엔티티가 있는지는 따지지 않는다. 없는 엔티티를 가리켜도 참조에 적은 저장소 이름이 드러나기 때문이다.
- 참조는 저장소를 `name`으로도 서브모듈 디렉토리 이름으로도 가리킬 수 있다. 둘 다 찾고, 어느 쪽이든 그 저장소의 범위와 비교한다.
  같은 이름을 쓰는 저장소가 여럿이면 모두와 비교한다.
"""

from collections.abc import Iterator

from .. import links, scope
from ..compiler import Compiled, PageRecord
from ..keys import PAGE_KEYS, RELATION_KEYS
from ..rules import RuleSet
from ..scope import Scope, ScopeError
from .catalog import INVALID_SCOPE, SCOPE_VIOLATION
from .model import Issue


def find(compiled: Compiled, rules: RuleSet) -> Iterator[Issue]:
    scopes: dict[str, Scope] = {}  # 지식 저장소의 서브모듈 디렉토리 이름 -> 비교에 쓰는 공유 범위
    for record in compiled.records:
        scopes[record.directory] = scope.DEFAULT
        if record.has_layer and record.name is not None and record.scope_declared:
            try:
                scopes[record.directory] = scope.parse(record.scope)
            except ScopeError as exc:
                yield Issue(
                    INVALID_SCOPE,
                    record.yaml_file,
                    f"`scope`의 값 `{record.scope}`가 공유 범위가 아니다: {exc}. {scope.FORMS} 중 하나로 적는다. "
                    "고칠 때까지 비교에서는 가장 좁은 `private`으로 본다",
                )

    by_reference: dict[str, set[str]] = {}  # 참조에 적는 저장소 이름(`name`, 디렉토리 이름) -> 디렉토리 이름
    for record in compiled.records:
        for name in (record.directory, record.name):
            if name is not None:
                by_reference.setdefault(name, set()).add(record.directory)

    for record in compiled.records:
        source = scopes[record.directory]
        for page in record.referrers():  # 페이지와 `Project` 엔티티(`ontology.yaml`의 `dependsOn`)
            for where, target in _cross_references(page):
                repository = target.partition(":")[0].strip()
                for directory in sorted(by_reference.get(repository, ())):
                    if problem := source.problem_referencing(scopes[directory]):
                        yield Issue(SCOPE_VIOLATION, page.file, f"{where}: 지식 저장소 `{directory}`는 {problem}")


def _cross_references(page: PageRecord) -> Iterator[tuple[str, str]]:
    """페이지의 교차 참조 모양의 값(`<이름>:<나머지>`)을 `(설명에 쓸 자리, 값)`으로. 관계의 값, `class`의 값, 본문의 링크 대상이다."""
    for key, target in page.relations():
        if ":" in target:
            yield f"`{key}`의 값 `{target}`", target
    for class_value in dict.fromkeys(_class_values(page)):
        if ":" in class_value:
            yield f"`class`의 값 `{class_value}`", class_value
    for where, text in _unchecked_strings(page):
        if ":" in text:
            yield where, text
    for destination in links.destinations(page.body):
        name, separator, rest = destination.strip().partition(":")
        # `http://…`처럼 `//`가 뒤따르는 것은 주소이고 교차 참조가 아니다. 저장소의 이름이 `http`여도 그렇다.
        if separator and name and not rest.startswith("//"):
            yield f"본문의 링크 `{destination}`", destination


def _class_values(page: PageRecord) -> list[str]:
    """페이지의 `class` 값(문자열 하나나 그 목록)에서 문자열만. 문자열이 아닌 값은 값의 종류가 맞지 않다고 컴파일이 이미 알렸다."""
    value = (page.meta or {}).get("class")
    return [item for item in (value if isinstance(value, list) else [value]) if isinstance(item, str)]


def _unchecked_strings(page: PageRecord) -> Iterator[tuple[str, str]]:
    """다른 검사가 값을 읽지 못해 위에서 보지 못한 문자열을 `(설명에 쓸 자리, 문자열)`로. 정의되지 않은 키(와 그 값)와, 문자열이 아닌(중첩된) 관계의 값이다.

    중첩 안까지 훑고, 키-값의 값뿐 아니라 키도 본다. 참조는 `{secret:component/x: 메모}`처럼 키에 적을 수도 있다.
    정의된 키 가운데 제목, 설명, 날짜, 별칭은 참조가 아닌 글이라 보지 않는다. 원본 문서의 기록(`derivedFrom`)은 경로와 해시라 여기서 보지 않는다.
    그 경로가 저장소 밖을 가리키는지는 컴파일이 `outside-link`로 따로 알린다.
    """
    meta = page.meta or {}
    for key, value in meta.items():
        if key not in PAGE_KEYS:
            yield f"정의되지 않은 키 `{key}`", str(key)
            for kind, text in _strings(value):
                yield f"`{key}`의 {kind} `{text}`", text
    for key in RELATION_KEYS:
        value = meta.get(key)
        for item in value if isinstance(value, list) else [value]:
            if not isinstance(item, str):  # 문자열은 `page.relations()`가 이미 냈다
                for kind, text in _strings(item):
                    yield f"`{key}`의 {kind} `{text}`", text


def _strings(value: object) -> Iterator[tuple[str, str]]:
    """값 안의 문자열을 `(종류, 문자열)`로 중첩된 목록과 키-값의 키와 값까지 모두 낸다. 종류는 `값` 또는 `키`다."""
    if isinstance(value, str):
        yield "값", value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield "키", str(key)
            yield from _strings(item)
