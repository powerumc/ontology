"""검사 항목의 목록. 항목마다 이름, 기본 심각도, 무엇을 잡는지를 한 곳에 적는다.

검사를 더하거나 심각도의 기본값을 바꿀 때 고치는 곳이다. 항목을 실제로 돌리는 코드는 같은 패키지의 다른 모듈에 있고,
여기의 항목을 가리켜 문제를 보고한다. 이름은 규칙 파일이 항목을 가리키는 키가 되고 보고에도 나온다.
"""

from .. import compiler
from .model import Check, Severity

ERROR = Severity.ERROR
WARNING = Severity.WARNING

# --- 읽을 수 없는 파일: 컴파일이 찾는다 ---------------------------------------------
UNREADABLE_FILE = Check(compiler.UNREADABLE_FILE, ERROR, "페이지나 ontology.yaml을 읽을 수 없다(YAML 문법 오류, frontmatter 없음)")
INVALID_VALUE = Check(
    compiler.INVALID_VALUE, ERROR, "속성의 값의 종류가 맞지 않는다(문자열이어야 하는 자리에 숫자나 중첩된 값, 없는 날짜 등)"
)
INVALID_CLASS_DECLARATION = Check(
    compiler.INVALID_CLASS_DECLARATION, ERROR, "ontology.yaml의 classes에 선언한 하위 클래스가 틀렸다"
)
INVALID_IDENTIFIER = Check(
    compiler.INVALID_IDENTIFIER, ERROR, "식별자 형식에 어긋난 페이지 경로(경로 조각은 영어 소문자, 숫자, 하이픈만)"
)

# --- 페이지의 위치 --------------------------------------------------------------------
MISPLACED_PAGE = Check("misplaced-page", ERROR, "페이지가 자기 클래스의 디렉토리에 있지 않다(하위 클래스는 공통 조상 클래스의 디렉토리)")
MISNAMED_PAGE = Check("misnamed-page", ERROR, "페이지처럼 보이는 파일의 확장자가 .md가 아니라 페이지로 읽히지 않는다(.MD, .markdown)")

# --- 구조 제약: SHACL이 찾는다(vocab/shapes.ttl) ------------------------------------
MISSING_PROPERTY = Check("missing-property", ERROR, "필수 속성(class, title)이 없거나 title이 비어 있다")
DISALLOWED_CLASS = Check("disallowed-class", ERROR, "페이지의 클래스로 쓸 수 없는 클래스다")
RELATION_DOMAIN = Check("relation-domain", ERROR, "관계를 쓸 수 없는 클래스의 페이지가 그 관계를 썼다")
RELATION_RANGE = Check("relation-range", ERROR, "관계가 가리킬 수 없는 클래스의 엔티티를 가리켰다")

# --- 페이지의 키와 참조 ------------------------------------------------------------
UNDEFINED_KEY = Check("undefined-key", ERROR, "페이지에 정의되지 않은 frontmatter 키가 있다")
REVERSE_RELATION = Check("reverse-relation", ERROR, "역방향 관계(hasPart, implementedBy, governedBy, supersededBy)를 페이지에 직접 썼다")
BROKEN_REFERENCE = Check("broken-reference", ERROR, "관계가 가리키는 엔티티가 없다(같은 지식 저장소와 교차 참조)")
UNREGISTERED_REPOSITORY = Check("unregistered-repository", ERROR, "교차 참조가 등록되지 않은 지식 저장소를 가리킨다")
ORPHAN_PAGE = Check("orphan-page", WARNING, "다른 엔티티와의 관계가 들어오는 것도 나가는 것도 없는 페이지다(derivedFrom은 세지 않는다)")

# --- 중복 ---------------------------------------------------------------------------
DUPLICATE_ENTITY = Check("duplicate-entity", ERROR, "같은 지식 저장소 안에 같은 클래스에서 이름(제목, 별칭)이 같은 엔티티가 있다")
DUPLICATE_ENTITY_ACROSS_REPOSITORIES = Check(
    "duplicate-entity-across-repositories", WARNING, "다른 지식 저장소에 같은 클래스에서 이름(제목, 별칭)이 같은 엔티티가 있다"
)

# --- 지식 저장소 ---------------------------------------------------------------------
REPOSITORY_NAME_MISMATCH = Check("repository-name-mismatch", ERROR, "ontology.yaml의 name이 서브모듈 디렉토리 이름과 다르다")
MISSING_ONTOLOGY_LAYER = Check("missing-ontology-layer", WARNING, "등록된 지식 저장소에 온톨로지 층(ontology.yaml)이 없어 검사하지 못했다")

CHECKS = (
    UNREADABLE_FILE,
    INVALID_VALUE,
    INVALID_CLASS_DECLARATION,
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
    MISSING_ONTOLOGY_LAYER,
)

BY_NAME = {check.name: check for check in CHECKS}
