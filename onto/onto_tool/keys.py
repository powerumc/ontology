"""페이지 frontmatter와 `ontology.yaml`이 쓸 수 있는 키. 코드에서 키의 집합을 정하는 곳은 여기 한 곳이다.

컴파일은 여기 있는 키만 그래프로 옮긴다. 같은 상수를 여러 곳이 쓴다: 정의되지 않은 키를 오류로 알리는 검사,
규칙(`ontology.yaml`의 공유 범위와 규칙 덮어쓰기), `ontology.yaml`을 만드는 최신화.
frontmatter 키와 RDF의 대응은 `vocab/context.jsonld`가 정한다. 여기 있는 키가 context와 어긋나지 않고 모두 그래프에 나타나는지는
`tests/test_onto_compile.py`의 `test_문서화된_…`가 확인한다. 문서화된 키의 목록을 값으로 적고, 그 키를 모두 쓴 견본을
컴파일해 키마다 그래프에서 찾는다(키를 더하면 그 목록에도 더한다). 반대로 여기 없는 키는 컴파일이 버리고,
그런 키를 쓴 페이지는 정의되지 않은 키를 오류로 알리는 검사가 잡는다.

정해 둔 것:

- `Project`의 제목·설명·별칭(`ontology.yaml`의 `title`, `description`, `aliases`)은 선택이다. 없으면 없는 채로 두고
  `name`으로 채우지 않는다. 그러므로 `Project`에는 제목을 필수로 요구하는 구조 제약을 두지 않는다.
  `name`과 공유 범위만 든 `ontology.yaml`이 최신화 직후 검사를 통과해야 하기 때문이다.
- `Project`는 페이지가 없어 자기가 쓰는 관계를 `ontology.yaml`에 적는다. `Project`가 쓰는 관계는 `dependsOn` 하나다(`PROJECT_RELATION_KEYS`).
  값의 형식(식별자 또는 `<저장소 이름>:<식별자>` 교차 참조, 여럿이면 목록)과 깨진 참조, 등록되지 않은 저장소, 경로 참조, 공유 범위, 구조 제약
  검사는 페이지의 관계와 같다. 다른 관계의 키는 정의되지 않은 키다.
- `ontology.yaml`의 `scope`(공유 범위)와 `rules`(규칙 덮어쓰기)는 허용되는 키다. `rules` 안의 키(`sources`, `checks`, …)는
  `rules.py`의 스키마가 정한다. `scope`의 값은 `scope.py`가 읽고, 공유 범위 검사(`checks/scopes.py`)가 값과 교차 참조를 검사한다.
  `scope`는 컴파일된 그래프에 나타나지 않는다. 적지 않은 지식 저장소는 `private`으로 본다.
"""

# 페이지 frontmatter
PAGE_PROPERTY_KEYS = ("class", "title", "description", "date", "aliases")
# 엔티티를 식별자(같은 지식 저장소)나 `<저장소 이름>:<식별자>`(교차 참조)로 가리키는 키. `derivedFrom`은 값의 형태가 달라 여기 없다.
RELATION_KEYS = ("partOf", "dependsOn", "implements", "governs", "supersedes", "about")
# 페이지가 근거로 삼은 원본 문서. 값은 `{path, hash}` 항목(또는 그 목록)이고, 컴파일이 항목마다 `Source` 엔티티를 만들어 가리킨다.
# 다른 엔티티와의 관계가 아니라서 `RELATION_KEYS`에 두지 않는다. 그래서 고아 페이지와 깨진 참조를 따지는 검사가 세지 않는다.
# 항목의 `path`는 지식 저장소 루트 기준 원본 문서의 경로, `hash`는 그 문서의 git 해시(40자리 소문자 16진수)다.
# 넘긴 문서의 목록(`docs/ontology/skipped.yaml`)의 항목도 같은 모양이다.
SOURCE_KEY = "derivedFrom"
SOURCE_ENTRY_KEYS = ("path", "hash")
PAGE_KEYS = frozenset((*PAGE_PROPERTY_KEYS, *RELATION_KEYS, SOURCE_KEY))
# 페이지의 클래스(공통 어휘의 클래스) -> 그 클래스의 페이지를 두는 디렉토리. 하위 클래스의 페이지는 공통 조상 클래스의 디렉토리에 둔다.
PAGE_CLASS_DIRECTORIES = {
    "Component": "component",
    "Plan": "plan",
    "Policy": "policy",
    "Term": "term",
    "Decision": "decision",
    "Report": "report",
}
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
# `Project`가 쓰는 관계의 키. `RELATION_KEYS`에 든 키 가운데 `Project`가 쓸 수 있는 것이다. 값은 페이지의 관계와 같은 형식이다.
PROJECT_RELATION_KEYS = ("dependsOn",)
# 지식 저장소가 자기 네임스페이스에 선언하는 하위 클래스. `{클래스 이름: {subClassOf: 상위 클래스 이름}}`이고 선택이다.
# 엔티티를 서술하는 사실이 아니라 어휘의 선언이라 `Project`의 사실이 되지 않고, JSON-LD context에도 없다.
CLASSES_KEY = "classes"
CLASS_DECLARATION_KEYS = ("subClassOf",)
# 공유 범위(`private`, `team`, `team:<팀 이름>`, `public`). 값을 읽는 것은 `scope.py`이고 검사는 공유 범위 검사(`checks/scopes.py`)가 한다.
SCOPE_KEY = "scope"
# 규칙 덮어쓰기. 루트 기본 규칙(`rules.yaml`)과 같은 구조로 바꿀 값만 적는다. 읽기와 검증은 `rules.py`가 한다.
RULES_KEY = "rules"
ONTOLOGY_YAML_KEYS = frozenset((*ONTOLOGY_YAML_REQUIRED_KEYS, *PROJECT_KEYS, *PROJECT_RELATION_KEYS, CLASSES_KEY, SCOPE_KEY, RULES_KEY))
