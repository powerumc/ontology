---
name: onto-query
description: 지식 저장소의 온톨로지를 SPARQL로 질의해 프로젝트의 구성 요소, 계획, 정책, 용어, 결정, 구현 결과와 그 관계를 찾는다. 어떤 컴포넌트가 무엇에 의존하는지, 어떤 정책이 무엇에 적용되는지처럼 지식 저장소에 대한 질문에 답할 때 쓴다.
---

# onto-query

원본 문서를 처음부터 읽지 않고 온톨로지에서 답을 찾는다. 질의는 읽기 전용이고 어떤 파일도 고치지 않는다.

## 작업 위치

- 최상위에 `.onto/Justfile`이 있으면 **지식 저장소 안**이다. 이 저장소의 지식만 질의한다. 명령은 `just -f .onto/Justfile <명령>`이다.
- 최상위에 `onto/Justfile`이 있으면 **루트 저장소**다. `projects/` 아래에 붙은 지식 저장소 전체를 합쳐 질의한다(여러 프로젝트를 가로지르는 질문은 여기서 한다). 명령은 `just onto <명령>`이다. `projects/`가 없거나 비어 있으면 붙인 지식 저장소가 없는 것이다. `just repo add <주소>`로 붙인 뒤에 한다고 알린다.
- 아래에서 `<onto>`는 그 명령 접두어(`just onto` 또는 `just -f .onto/Justfile`)다.
- 둘 다 없으면 복사된 기능이 없는 클론이다. 이 스킬을 쓸 수 없다. `docs/ontology/index.md`에서 페이지로 찾아 읽는다.

## 질의하는 법

```sh
<onto> query 'SELECT ?e ?t WHERE { ?e a onto:Component ; dcterms:title ?t } ORDER BY ?t'
```

- 질의문은 **작은따옴표 하나**로 감싸 한 인자로 넘긴다. 꺾쇠, 중괄호, 큰따옴표는 그대로 전달된다.
- 실행할 때마다 현재 파일에서 다시 컴파일한다. `build`를 먼저 할 필요가 없고, 방금 쓴 페이지도 바로 보인다.
- 질의하는 그래프는 추론이 끝난 것이다. 하위 클래스, 역관계(`hasPart` 등), 추이 관계(`partOf`)가 이미 들어 있다.
- 접두어 `onto:`, `dcterms:`, `skos:`, `prov:`, `owl:`, `rdfs:`, `rdf:`, `xsd:`는 선언 없이 쓴다.
- 엔티티를 질의문에서 가리킬 때는 IRI를 쓴다: `<https://onto.invalid/entity/<저장소 이름>/<식별자>>`(예: `<https://onto.invalid/entity/billing/component/gateway>`).
- 행의 순서가 필요하면 `ORDER BY`를 쓴다. 쓰지 않으면 순서가 정해지지 않는다.
- `SELECT`는 표, `ASK`는 `true`/`false`, `CONSTRUCT`와 `DESCRIBE`는 Turtle로 나온다.

## 클래스와 관계

클래스는 엔티티의 종류다. 저장소가 `ontology.yaml`의 `classes`에 선언한 하위 클래스도 상위 클래스를 질의하면 함께 나온다.

| 클래스 | 서술하는 것 |
|---|---|
| `onto:Project` | 지식 저장소 하나가 다루는 프로젝트 그 자체(식별자 `project`) |
| `onto:Component` | 프로젝트를 이루는 시스템, 모듈, 서비스 |
| `onto:Plan` | 앞으로 할 일을 정한 것 |
| `onto:Policy` | 프로젝트에서 지켜야 하는 규칙이나 제약 |
| `onto:Term` | 프로젝트에서 뜻을 정해 둔 용어 |
| `onto:Decision` | 대안 가운데 하나를 고른 결정과 그 이유 |
| `onto:Report` | 구현한 결과를 기록한 것 |
| `onto:Source` | 페이지가 근거로 삼은 원본 문서(페이지는 없다) |

| 관계 | 뜻 | 쓰는 쪽 → 가리키는 쪽 | 추론으로 생기는 역 |
|---|---|---|---|
| `onto:partOf` | A는 B의 일부다. 추이 관계다 | `Component` → `Component`, `Project` | `onto:hasPart` |
| `onto:dependsOn` | A가 동작하려면 B가 필요하다. 직접 의존만 적고, 간접 의존은 `onto:dependsOn+` 경로로 구한다 | `Component`, `Project` → `Component`, `Project` | 없음 |
| `onto:implements` | 이 구현 결과가 그 계획이나 결정을 실행했다 | `Report` → `Plan`, `Decision` | `onto:implementedBy` |
| `onto:governs` | 이 정책이 그 대상에 적용된다 | `Policy` → `Project`, `Component` | `onto:governedBy` |
| `onto:supersedes` | 새 것이 같은 클래스의 옛 것을 대체한다 | 같은 클래스끼리 | `onto:supersededBy` |
| `onto:about` | 이 페이지가 다루는 대상 | `Plan`, `Decision`, `Report`, `Term` → `Project`, `Component` | 없음 |
| `onto:derivedFrom` | 이 페이지의 근거가 된 원본 문서 | 모든 페이지 → `Source` | 없음 |

속성: `dcterms:title`(제목), `dcterms:description`, `dcterms:date`, `skos:altLabel`(별칭), `onto:repository`(엔티티가 온 지식 저장소의 이름), `onto:sourcePath`와 `onto:sourceHash`(`Source`의 경로와 해시).

어휘가 바뀌었을 수 있으니 확실하지 않으면 질의로 읽는다. 클래스는 `SELECT ?c ?l WHERE { ?c a owl:Class ; rdfs:label ?l } ORDER BY ?l`, 관계는 `SELECT ?p ?c WHERE { ?p a owl:ObjectProperty ; rdfs:comment ?c } ORDER BY ?p`다.

## 결과에서 페이지로 가는 법

`SELECT` 결과의 엔티티는 **파일 경로**로 나온다. 그 경로를 그대로 열면 페이지다. 추가 조회가 필요 없다.

```
e	t
projects/billing/docs/ontology/component/gateway.md	결제 게이트웨이
```

- 첫 줄은 변수 이름이고 그 뒤로 한 줄에 행 하나, 칸은 탭으로 나뉜다.
- 루트 저장소에서는 루트 기준 경로(`projects/billing/docs/ontology/…`)이고, 지식 저장소 안에서는 그 저장소 기준 경로(`docs/ontology/…`)다.
- `Project` 엔티티는 `ontology.yaml`의 경로로, `Source` 엔티티는 원본 문서의 경로로 나온다. 엔티티가 아닌 값(문자열, 날짜, 그 밖의 IRI)은 그대로 나온다.
- 페이지에서 근거 원본으로 가려면 `derivedFrom`이 가리키는 `Source` 엔티티를 고른다: `SELECT ?e ?s WHERE { ?e onto:derivedFrom ?s }`. 두 칸 모두 그대로 열 수 있는 경로다(`?s`는 루트에서 `projects/billing/docs/design.md`, 지식 저장소 안에서 `docs/design.md`). `onto:sourcePath`는 지식 저장소 루트 기준 경로라 루트에서는 그대로 열 수 없다.
- 답에는 근거가 된 페이지 경로를 함께 적는다. 중요한 주장은 페이지의 `derivedFrom`이 가리키는 원본 문서에서 확인한다.

## 자주 쓰는 질의

```sparql
# 이름(제목이나 별칭)으로 찾기. 한글과 영어를 모두 시도한다
SELECT DISTINCT ?e WHERE { { ?e dcterms:title ?n } UNION { ?e skos:altLabel ?n } FILTER(CONTAINS(LCASE(STR(?n)), "invoice")) }

# 클래스별 엔티티(하위 클래스 포함)
SELECT ?e ?t WHERE { ?e a onto:Policy ; dcterms:title ?t } ORDER BY ?t

# 직접 의존과 간접 의존
SELECT ?a ?b WHERE { ?a onto:dependsOn ?b }
SELECT ?a ?b WHERE { ?a onto:dependsOn+ ?b }

# 어떤 컴포넌트의 일부(간접 포함)
SELECT ?x WHERE { ?x onto:partOf <https://onto.invalid/entity/billing/component/gateway> }

# 정책이 적용되는 대상, 결정을 실행한 구현 결과
SELECT ?p ?x WHERE { ?p onto:governs ?x }
SELECT ?d ?r WHERE { ?d a onto:Decision ; onto:implementedBy ?r }

# 지식 저장소별로 거르기(루트에서)
SELECT ?e WHERE { ?e a onto:Term ; onto:repository "billing" }
```

## 막히면

- 결과가 비면 이름 철자를 의심한다. 별칭까지 찾는 질의(위)와 `docs/ontology/index.md`로 확인한다.
- 읽을 수 없는 파일이 있어 질의가 멈추면 `<onto> validate`로 원인을 본다.
- 페이지가 낡았는지(`stale-page`)와 깨진 참조는 질의로 알 수 없다. `<onto> validate`와 `<onto> status`로 본다.
- 지식 저장소 안에서는 그 저장소의 엔티티만 나온다. 다른 프로젝트와 비교하는 질문은 루트 저장소에서 한다.
- 여러 프로젝트를 비교·종합한 결론이나 서로 다른 저장소의 용어가 같다는 사실은 프로젝트 저장소에 쓰지 않는다. 남기고 싶으면 개인 지식 저장소에 두자고 사용자에게 제안한다(`onto-ingest`).
