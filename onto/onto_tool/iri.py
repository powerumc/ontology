"""엔티티의 절대 IRI.

기준은 기기와 무관한 `https` 고정값이다. 실제로 접속되는 주소일 필요는 없다(`.invalid`는 예약된 최상위 도메인이다).
다른 기기에서 컴파일해도 같은 IRI가 나와야 하므로 작업 사본의 경로나 원격 저장소 주소를 섞지 않는다.
임의의 스킴(예: `onto://`)은 rdflib이 상대 식별자를 풀지 못해 트리플이 하나도 만들어지지 않으므로 쓰지 않는다.

공통 어휘의 네임스페이스는 여기에 두지 않는다. `vocab/onto.ttl`과 `vocab/context.jsonld`가 같은 값을 정의한다.
"""

from urllib.parse import quote

ENTITY_BASE = "https://onto.invalid/entity/"
# 지식 저장소가 선언한 하위 클래스의 IRI는 `<CLASS_BASE><저장소 이름>/<클래스 이름>`이다. 저장소마다 네임스페이스가 따로라
# 다른 저장소가 같은 이름의 클래스를 선언해도 겹치지 않고, 엔티티의 IRI와 공통 어휘의 네임스페이스와도 겹치지 않는다.
CLASS_BASE = "https://onto.invalid/class/"
# `Source` 엔티티(원본 문서의 한 시점의 내용)의 IRI는 `<SOURCE_BASE><저장소 이름>/<경로>@<해시>`다. 페이지의 엔티티와 같은 네임스페이스에
# 두지 않는다. 페이지의 식별자와 겹칠 수 없고, 질의에서 엔티티와 원본 문서를 구분한다.
SOURCE_BASE = "https://onto.invalid/source/"
# 풀리지 않는 용어(예: 공통 어휘에도 선언에도 없는 `class` 값)는 `unresolved_iri`가 이 base 아래의 IRI로 바꾼다.
# JSON-LD를 파싱할 때도 이 base를 준다. 주지 않으면 rdflib이 실행 위치의 `file://` 주소를 쓰므로, 상대 IRI로 풀리는 값이
# 기기마다 다른 IRI로 그래프에 들어간다. 엔티티의 IRI와 겹치지 않는 고정값이라, 풀리지 않은 용어가 그래프에서 알아볼 수 있게 남는다.
UNRESOLVED_BASE = "https://onto.invalid/unresolved/"


def entity_iri(repository: str, identifier: str) -> str:
    """지식 저장소 `repository` 안의 식별자 `identifier`가 가리키는 엔티티의 IRI.

    식별자 형식(영어 소문자, 숫자, 하이픈)을 어긴 경로도 IRI로 만든다. 그런 페이지가 그래프에서 조용히
    빠지지 않고 스크립트 검사가 오류로 알리게 하려는 것이다. rdflib은 공백이 든 IRI를 객체째 버린다.
    """
    return ENTITY_BASE + quote(f"{repository}/{identifier}", safe="/")


def resolve_reference(repository: str, reference: str) -> str:
    """`repository` 안의 페이지가 쓴 참조가 가리키는 엔티티의 IRI.

    같은 지식 저장소의 엔티티는 식별자 그대로(`component/api`), 다른 지식 저장소의 엔티티는
    `<저장소 이름>:<식별자>`(`billing:component/api`)로 쓴다. 식별자의 경로 조각은 언어 규칙의 `identifier-pattern`을 따르고,
    `:`나 앞뒤 공백이 든 조각은 그 형식이 허용하더라도 참조로 가리킬 수 없다. 식별자 형식 검사(`checks/frontmatter.py`)가
    그런 조각을 형식과 상관없이 `invalid-identifier`로 알리고, `rules.py`는 그것을 허용하는 형식을 미리 거부한다.
    그래서 `:`는 저장소 이름과 식별자의 경계로만 나온다. 가리키는 엔티티가 있는지는 여기서 따지지 않는다.
    """
    name, separator, identifier = reference.partition(":")
    if separator:
        return entity_iri(name.strip(), identifier.strip())
    return entity_iri(repository, reference.strip())


def class_iri(repository: str, name: str) -> str:
    """지식 저장소 `repository`가 선언한 하위 클래스 `name`의 IRI."""
    return CLASS_BASE + quote(f"{repository}/{name}", safe="/")


def unresolved_iri(term: str) -> str:
    """어느 엔티티나 클래스도 가리키지 않는 용어 `term`의 IRI. 풀리지 않은 채로 그래프에서 알아볼 수 있게 `UNRESOLVED_BASE` 아래에 둔다."""
    return UNRESOLVED_BASE + quote(term, safe="")


def source_iri(repository: str, path: str, hash: str) -> str:
    """지식 저장소 `repository` 안의 원본 문서 `path`가 `hash`였을 때의 `Source` 엔티티의 IRI.

    경로가 같아도 해시가 다르면 다른 엔티티다. 페이지가 근거로 삼은 시점의 내용을 가리키므로, 문서가 바뀐 뒤에도 옛 내용을
    근거로 한 페이지와 지금 내용을 근거로 한 페이지가 서로 다른 `Source`를 가리킨다. 해시는 16진수라 따로 인코딩하지 않는다.
    """
    return f"{SOURCE_BASE}{quote(f'{repository}/{path}', safe='/')}@{hash}"
