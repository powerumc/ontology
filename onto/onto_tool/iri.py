"""엔티티의 절대 IRI.

기준은 기기와 무관한 `https` 고정값이다. 실제로 접속되는 주소일 필요는 없다(`.invalid`는 예약된 최상위 도메인이다).
다른 기기에서 컴파일해도 같은 IRI가 나와야 하므로 작업 사본의 경로나 원격 저장소 주소를 섞지 않는다.
임의의 스킴(예: `onto://`)은 rdflib이 상대 식별자를 풀지 못해 트리플이 하나도 만들어지지 않으므로 쓰지 않는다.

공통 어휘의 네임스페이스는 여기에 두지 않는다. `vocab/onto.ttl`과 `vocab/context.jsonld`가 같은 값을 정의한다.
"""

from urllib.parse import quote

ENTITY_BASE = "https://onto.invalid/entity/"


def entity_iri(repository: str, identifier: str) -> str:
    """지식 저장소 `repository` 안의 식별자 `identifier`가 가리키는 엔티티의 IRI.

    식별자 형식(영어 소문자, 숫자, 하이픈)을 어긴 경로도 IRI로 만든다. 그런 페이지가 그래프에서 조용히
    빠지지 않고 스크립트 검사가 오류로 알리게 하려는 것이다. rdflib은 공백이 든 IRI를 객체째 버린다.
    """
    return ENTITY_BASE + quote(f"{repository}/{identifier}", safe="/")
