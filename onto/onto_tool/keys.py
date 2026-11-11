"""페이지 frontmatter와 `ontology.yaml`이 쓸 수 있는 키. 코드에서 키의 집합을 정하는 곳은 여기 한 곳이다.

컴파일은 여기 있는 키만 그래프로 옮긴다. 뒤 티켓이 같은 상수를 쓴다: 정의되지 않은 키를 오류로 알리는 검사,
규칙(`ontology.yaml`의 공유 범위와 규칙 덮어쓰기), `ontology.yaml`을 만드는 최신화.
frontmatter 키와 RDF의 대응은 `vocab/context.jsonld`가 정한다. 여기 있는 키가 context와 어긋나지 않고 모두 그래프에 나타나는지는
`tests/test_onto_compile.py`의 `test_문서화된_…`가 확인한다. 문서화된 키의 목록을 값으로 적고, 그 키를 모두 쓴 견본을
컴파일해 키마다 그래프에서 찾는다(키를 더하면 그 목록에도 더한다). 반대로 여기 없는 키는 컴파일이 버리고,
그런 키를 쓴 페이지는 정의되지 않은 키를 오류로 알리는 검사가 잡는다.

정해 둔 것:

- `Project`의 제목·설명·별칭(`ontology.yaml`의 `title`, `description`, `aliases`)은 선택이다. 없으면 없는 채로 두고
  `name`으로 채우지 않는다. 그러므로 `Project`에는 제목을 필수로 요구하는 구조 제약을 두지 않는다.
  `name`과 공유 범위만 든 `ontology.yaml`이 최신화 직후 검사를 통과해야 하기 때문이다.
- 공유 범위와 규칙 덮어쓰기를 적는 키는 규칙을 다루는 티켓이 여기에 더한다. 지금은 읽지 않는다.
"""

# 페이지 frontmatter
PAGE_PROPERTY_KEYS = ("class", "title", "description", "date", "aliases")
# 엔티티를 식별자(같은 지식 저장소)나 `<저장소 이름>:<식별자>`(교차 참조)로 가리키는 키. `derivedFrom`은 값의 형태가 달라
# 출처를 다루는 티켓이 더한다.
RELATION_KEYS = ("partOf", "dependsOn", "implements", "governs", "supersedes", "about")
PAGE_KEYS = frozenset((*PAGE_PROPERTY_KEYS, *RELATION_KEYS))
# 공통 어휘에는 있지만 페이지에는 쓰지 않는 역방향 관계와 그 원래 방향. 추론이 만든다.
# 페이지에 쓰면 정의되지 않은 키가 아니라 역방향 관계로 알린다.
REVERSE_RELATION_KEYS = {
    "hasPart": "partOf",
    "implementedBy": "implements",
    "governedBy": "governs",
    "supersededBy": "supersedes",
}

# ontology.yaml
ONTOLOGY_YAML_REQUIRED_KEYS = ("name",)
# `Project` 엔티티의 사실이 되는 선택 키. 페이지 frontmatter와 같은 이름과 뜻이다.
PROJECT_KEYS = ("title", "description", "aliases")
# 지식 저장소가 자기 네임스페이스에 선언하는 하위 클래스. `{클래스 이름: {subClassOf: 상위 클래스 이름}}`이고 선택이다.
# 엔티티를 서술하는 사실이 아니라 어휘의 선언이라 `Project`의 사실이 되지 않고, JSON-LD context에도 없다.
CLASSES_KEY = "classes"
CLASS_DECLARATION_KEYS = ("subClassOf",)
ONTOLOGY_YAML_KEYS = frozenset((*ONTOLOGY_YAML_REQUIRED_KEYS, *PROJECT_KEYS, CLASSES_KEY))
