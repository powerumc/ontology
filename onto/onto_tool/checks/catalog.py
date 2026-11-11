"""검사 항목의 목록. 항목마다 이름과 무엇을 잡는지를 한 곳에 적는다.

검사를 더할 때 고치는 곳이다. 켬/끔과 심각도는 여기가 아니라 규칙 파일(`rules.yaml`)이 정하므로, 검사를 더하면 `rules.yaml`의
`checks`에도 같은 이름의 항목을 더한다(빠지면 도구가 알린다). 항목을 실제로 돌리는 코드는 같은 패키지의 다른 모듈에 있고,
여기의 항목을 가리켜 문제를 보고한다. 이름은 규칙 파일이 항목을 가리키는 키가 되고 보고에도 나온다.
루트 전용 항목(지식 저장소의 규칙이 끄거나 심각도를 바꿀 수 없는 것)은 `root_only=True`로 적는다. 공유 범위 검사, 규칙을 담은
`ontology.yaml` 자체의 문제를 보고하는 항목, 지식 저장소 사이의 `name` 겹침이 그렇다.
여러 지식 저장소에 걸친 항목(교차 참조, 공유 범위, 저장소 간 중복, 다른 저장소에서 들어오는 참조에 따라 결과가 달라지는 고아 페이지)은
`across_repositories=True`로 적는다. 지식 저장소 안에서 돌릴 때는 그 저장소만 다루므로 이 항목들을 건너뛰고(`checks.validate`) 건너뛰었다고 알린다.
루트 전용인 것과는 별개다. 루트 전용이지만 한 저장소만 보고 판단할 수 있는 항목(`invalid-ontology-yaml`, `invalid-class-declaration`,
`invalid-scope`, `path-reference`, `outside-link`)은 지식 저장소 안에서도 돈다. 새 항목이 어느 쪽인지는 그 항목이 다른 저장소의 사실에 기대는지로 정한다.
"""

from .. import compiler
from .model import Check

# --- 읽을 수 없는 파일: 컴파일이 찾는다 ---------------------------------------------
UNREADABLE_FILE = Check(compiler.UNREADABLE_FILE, "페이지나 ontology.yaml을 읽을 수 없다(YAML 문법 오류, frontmatter 없음)")
INVALID_VALUE = Check(
    compiler.INVALID_VALUE, "페이지 속성의 값의 종류가 맞지 않는다(문자열이어야 하는 자리에 숫자나 중첩된 값, 없는 날짜 등)"
)
INVALID_CLASS_DECLARATION = Check(
    compiler.INVALID_CLASS_DECLARATION, "ontology.yaml의 classes에 선언한 하위 클래스가 틀렸다", root_only=True
)
INVALID_ONTOLOGY_YAML = Check(
    compiler.INVALID_ONTOLOGY_YAML,
    "ontology.yaml 최상위에 정의되지 않은 키가 있거나 Project가 되는 속성(title, description, aliases)의 값의 종류가 맞지 않는다(읽을 수 없는 중첩된 값, 숫자 등)",
    root_only=True,
)
INVALID_IDENTIFIER = Check(
    compiler.INVALID_IDENTIFIER, "식별자 형식에 어긋난 페이지 경로(경로 조각이 언어 규칙의 identifier-pattern에 맞지 않는다. 기본은 영어 소문자, 숫자, 하이픈)"
)

# --- 페이지의 위치 --------------------------------------------------------------------
MISPLACED_PAGE = Check("misplaced-page", "페이지가 자기 클래스의 디렉토리에 있지 않다(하위 클래스는 공통 조상 클래스의 디렉토리)")
MISNAMED_PAGE = Check("misnamed-page", "페이지처럼 보이는 파일의 확장자가 .md가 아니라 페이지로 읽히지 않는다(.MD, .markdown)")

# --- 구조 제약: SHACL이 찾는다(vocab/shapes.ttl) ------------------------------------
MISSING_PROPERTY = Check("missing-property", "필수 속성(class, title)이 없거나 title이 비어 있다")
DISALLOWED_CLASS = Check("disallowed-class", "페이지의 클래스로 쓸 수 없는 클래스다")
RELATION_DOMAIN = Check("relation-domain", "관계를 쓸 수 없는 클래스의 페이지가 그 관계를 썼다")
RELATION_RANGE = Check("relation-range", "관계가 가리킬 수 없는 클래스의 엔티티를 가리켰다")

# --- 페이지의 키와 참조 ------------------------------------------------------------
UNDEFINED_KEY = Check("undefined-key", "페이지에 정의되지 않은 frontmatter 키가 있다")
REVERSE_RELATION = Check("reverse-relation", "역방향 관계(hasPart, implementedBy, governedBy, supersededBy)를 페이지에 직접 썼다")
BROKEN_REFERENCE = Check("broken-reference", "관계가 가리키는 엔티티가 없다(같은 지식 저장소와 교차 참조)")
UNREGISTERED_REPOSITORY = Check(
    "unregistered-repository", "교차 참조가 등록되지 않은 지식 저장소를 가리킨다", across_repositories=True
)
ORPHAN_PAGE = Check(
    "orphan-page",
    "다른 엔티티와의 관계가 들어오는 것도 나가는 것도 없는 페이지다(derivedFrom은 세지 않는다). 들어오는 관계에는 다른 지식 저장소에서 오는 교차 참조도 든다",
    across_repositories=True,
)

# --- 중복 ---------------------------------------------------------------------------
DUPLICATE_ENTITY = Check("duplicate-entity", "같은 지식 저장소 안에 같은 클래스에서 이름(제목, 별칭)이 같은 엔티티가 있다")
DUPLICATE_ENTITY_ACROSS_REPOSITORIES = Check(
    "duplicate-entity-across-repositories",
    "다른 지식 저장소에 같은 클래스에서 이름(제목, 별칭)이 같은 엔티티가 있다",
    across_repositories=True,
)

# --- 지식 저장소 ---------------------------------------------------------------------
REPOSITORY_NAME_MISMATCH = Check("repository-name-mismatch", "ontology.yaml의 name이 서브모듈 디렉토리 이름과 다르다")
DUPLICATE_REPOSITORY_NAME = Check(
    compiler.DUPLICATE_REPOSITORY_NAME,
    "여러 지식 저장소가 같은 name을 쓴다(엔티티가 하나로 합쳐지므로 build와 query도 멈춘다)",
    root_only=True,
    across_repositories=True,
)
MISSING_ONTOLOGY_LAYER = Check("missing-ontology-layer", "등록된 지식 저장소에 온톨로지 층(ontology.yaml)이 없어 검사하지 못했다")
INVALID_RULES = Check(
    "invalid-rules", "ontology.yaml의 rules가 틀렸다(정의되지 않은 키, 값의 종류, 루트 전용 규칙을 덮어쓰려는 시도). 그 저장소는 루트 기본 규칙으로 검사한다"
)

# --- 원본 문서의 기록 ----------------------------------------------------------------
STALE_PAGE = Check(
    "stale-page", "페이지가 근거로 삼은 원본 문서가 기록한 해시와 달라졌다(낡음). git이 기록할 blob 해시를 작업 트리의 현재 내용으로 따진다"
)
MISSING_SOURCE = Check("missing-source", "페이지의 derivedFrom이 가리키는 원본 문서가 없다")
MISSING_SKIPPED_SOURCE = Check("missing-skipped-source", "넘긴 문서의 목록(skipped.yaml)에 적힌 원본 문서가 없다")

# --- 공유 범위(루트 전용) ------------------------------------------------------------
INVALID_SCOPE = Check(
    "invalid-scope", "ontology.yaml의 scope(공유 범위)가 private, team, team:<팀 이름>, public 중 하나가 아니다", root_only=True
)

SCOPE_VIOLATION = Check(
    "scope-violation",
    "교차 참조가 공유 범위가 더 좁은 지식 저장소(public에서 team이나 private으로, team에서 private으로)나 다른 팀(team:<팀 이름>이 다른 team)의 저장소를 가리킨다",
    root_only=True,
    across_repositories=True,
)

PATH_REFERENCE = Check(
    "path-reference",
    "관계의 값이 식별자도 교차 참조도 아니다(파일 경로, file: 주소, 첫 조각이 클래스 디렉토리가 아닌 값. 저장소 밖을 가리키는 경로는 저장소가 단독으로 열리면 깨진다)",
    root_only=True,
)
OUTSIDE_LINK = Check(
    compiler.OUTSIDE_LINK,
    "페이지 본문의 링크(절대 경로, file: 주소, 저장소의 루트 위로 나가는 상대 경로)나 페이지 파일(심볼릭 링크)이 지식 저장소 밖의 파일을 가리킨다",
    root_only=True,
)

# --- 인덱스 -------------------------------------------------------------------------
INDEX_MISMATCH = Check(
    "index-mismatch",
    "지식 저장소의 인덱스(index.md)가 없거나 현재 페이지에서 만들어지는 인덱스와 다르다(심볼릭 링크나 디렉토리라 쓸 수 없는 경우 포함. 다시 build한다)",
)

CHECKS = (
    UNREADABLE_FILE,
    INVALID_VALUE,
    INVALID_CLASS_DECLARATION,
    INVALID_ONTOLOGY_YAML,
    INVALID_IDENTIFIER,
    MISPLACED_PAGE,
    MISNAMED_PAGE,
    MISSING_PROPERTY,
    DISALLOWED_CLASS,
    RELATION_DOMAIN,
    RELATION_RANGE,
    UNDEFINED_KEY,
    REVERSE_RELATION,
    BROKEN_REFERENCE,
    UNREGISTERED_REPOSITORY,
    ORPHAN_PAGE,
    DUPLICATE_ENTITY,
    DUPLICATE_ENTITY_ACROSS_REPOSITORIES,
    REPOSITORY_NAME_MISMATCH,
    DUPLICATE_REPOSITORY_NAME,
    MISSING_ONTOLOGY_LAYER,
    INVALID_RULES,
    STALE_PAGE,
    MISSING_SOURCE,
    MISSING_SKIPPED_SOURCE,
    INVALID_SCOPE,
    SCOPE_VIOLATION,
    PATH_REFERENCE,
    OUTSIDE_LINK,
    INDEX_MISMATCH,
)

BY_NAME = {check.name: check for check in CHECKS}
