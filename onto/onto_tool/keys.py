"""페이지 frontmatter와 `ontology.yaml`이 쓸 수 있는 키. 코드에서 키의 집합을 정하는 곳은 여기 한 곳이다.

컴파일은 여기 있는 키만 그래프로 옮긴다. 뒤 티켓이 같은 상수를 쓴다: 정의되지 않은 키를 오류로 알리는 검사,
규칙(`ontology.yaml`의 공유 범위와 규칙 덮어쓰기), `ontology.yaml`을 만드는 최신화.
frontmatter 키와 RDF의 대응은 `vocab/context.jsonld`가 정하고, 두 곳이 어긋나지 않는지는 `tests/test_onto_keys.py`가 확인한다.

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

# ontology.yaml
ONTOLOGY_YAML_REQUIRED_KEYS = ("name",)
# `Project` 엔티티의 사실이 되는 선택 키. 페이지 frontmatter와 같은 이름과 뜻이다.
PROJECT_KEYS = ("title", "description", "aliases")
# 지식 저장소가 자기 네임스페이스에 선언하는 하위 클래스. `{클래스 이름: {subClassOf: 상위 클래스 이름}}`이고 선택이다.
# 엔티티를 서술하는 사실이 아니라 어휘의 선언이라 `Project`의 사실이 되지 않고, JSON-LD context에도 없다.
CLASSES_KEY = "classes"
CLASS_DECLARATION_KEYS = ("subClassOf",)
ONTOLOGY_YAML_KEYS = frozenset((*ONTOLOGY_YAML_REQUIRED_KEYS, *PROJECT_KEYS, CLASSES_KEY))
