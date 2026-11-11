# ontology

저장소 하나를 모듈 하나로 삼는 **모듈형 온톨로지** 도구다. 여러 저장소에 흩어진 문서를 저장소마다 온톨로지로 정리하고, 하나로 합쳐 질의하고 검사한다. [Karpathy의 LLM Wiki 패턴](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)을 뼈대로 하고, 그 위에 RDF 온톨로지와 git 서브모듈 구조를 얹는다.

## 풀려는 문제

- 프로젝트마다 계획, 정책·정의, 구현 결과 문서가 제각각의 형식으로 흩어져 있다. LLM 에이전트는 필요한 지식을 찾을 때마다 원본 문서를 처음부터 읽어야 한다.
- 프로젝트 사이의 관계는 어디에도 기록되어 있지 않다.
- 전체를 한곳에서 질의하고 싶지만, 각 프로젝트 저장소 안에서는 그 저장소의 지식만 보여야 한다.

## 동작 방식

- 이 저장소가 **루트 저장소**다. 기능만 제공하고 지식은 담지 않는다.
- 지식 저장소는 git 서브모듈로 루트 저장소의 `projects/` 아래에 붙는다. 지식 저장소 하나가 온톨로지 모듈 하나다.
- LLM 에이전트가 지식 저장소의 원본 문서를 읽어 온톨로지 층(`docs/ontology/`)의 페이지를 쓰고(ingest), 사람은 `git diff`로 검토한다. 원본 문서는 고치지 않는다.
- 페이지는 마크다운과 YAML frontmatter로 쓴다. 이를 RDF 그래프로 컴파일해 SPARQL 질의, SHACL 구조 제약 검사, 가벼운 추론에 쓴다.
- 루트 저장소에서는 붙인 지식 저장소 전체를, 지식 저장소 안에서는 그 저장소의 지식만 다룬다.
- 지식 저장소에는 온톨로지 기능이 없다. 붙일 때 루트 저장소가 기능을 복사해 준다(**최신화**).
  - `onto/`(코드, 공통 어휘, 규칙, 템플릿, 규약 문서)는 지식 저장소의 `.onto/`로, 에이전트 스킬 `.claude/skills/onto-*/`는 같은 위치로 복사된다.
  - 복사된 기능은 지식 저장소의 `.gitignore`로 제외된다. 지식 저장소의 이력에는 `docs/ontology/`의 지식만 들어간다.
  - 지식 저장소의 프로젝트 지침 파일(`CLAUDE.md`, 없으면 `AGENTS.md`)에는 최신화가 표시된 블록 하나를 넣어 온톨로지 층의 인덱스를 가리킨다. 블록 밖은 건드리지 않고, 복사된 기능이 없는 클론에서도 뜻이 통한다.
  - 공통 어휘는 semver로 버전을 관리한다. `just onto validate`는 `.onto/`나 스킬 사본이 루트와 내용이 다른 지식 저장소를 경고한다(버전 번호를 올리지 않은 수정도 잡는다).

```
(루트 저장소)
├── Justfile                  # setup과 모듈 선언
├── git/  repo/  onto/        # just 모듈. onto/는 지식 저장소에 복사하는 기능이기도 함
├── .claude/skills/           # 에이전트 스킬 onto-ingest, onto-query, onto-lint
├── CLAUDE.md                 # 짧은 안내
└── projects/<저장소명>/       # 지식 저장소 (서브모듈)
    ├── .onto/                # 루트 저장소의 onto/ 사본. 커밋하지 않음
    ├── .claude/skills/onto-*/ # 스킬 사본. 커밋하지 않음
    └── docs/ontology/        # 이 저장소의 지식. 커밋함
        ├── ontology.yaml     # 저장소 이름, 공유 범위, 규칙 덮어쓰기
        ├── index.md          # 진입점 (생성물)
        ├── skipped.yaml      # 읽고도 기록할 것이 없던 원본 문서의 목록 (필요할 때 생김)
        └── plan/ policy/ term/ decision/ report/ component/
```

## 받아서 쓰기

받아서 자기 것으로 쓴다. 필요한 도구는 `git`, `just`, `uv`다.

```sh
git clone https://github.com/powerumc/ontology my-ontology && cd my-ontology
git remote set-url origin <내 원격 저장소 주소>     # 이제 이 저장소는 내 루트 저장소다
just setup                                         # 도구를 확인하고 서브모듈을 초기화한다
just repo add <지식 저장소 주소> [이름] [브랜치]      # 지식 저장소를 붙이고 기능을 복사한다
git commit -m "chore: <이름> 지식 저장소를 등록한다"   # 등록은 스테이징까지만 한다. 커밋은 내가 한다
just git push                                      # 내 원격으로 올린다
```

- 이 공개 원본에는 어떤 지식 저장소도 등록되어 있지 않다. `origin`이 공개 원본인 채로는 `just repo add`가 거부한다. 받은 뒤 `origin`을 바꾸고 붙인다.
- 등록한 지식 저장소는 내 루트 저장소에 커밋한다. 다른 기기에서는 이 저장소를 클론하고 `just setup`만 하면 같은 구성이 된다.
- 개인 지식(여러 프로젝트를 비교·종합한 지식, 서로 다른 저장소의 용어가 같다는 사실)은 **개인 지식 저장소**에 둔다. 비공개 저장소를 하나 만들어 같은 방법(`just repo add`)으로 붙인다. 팀 저장소에 개인적 해석이 섞이지 않는다.
- 새 기기에서 클론한 직후에는 `just setup`을 한다. 서브모듈이 detached HEAD가 아니라 추적 브랜치에 체크아웃되고, 루트가 기록한 커밋에서 시작한다(원격의 최신으로 올리지 않는다).

## 지식 저장소 붙이기와 떼기

```sh
just repo add git@github.com:me/billing.git                 # projects/billing/에 붙인다. 이름은 주소의 저장소 이름이다
just repo add git@github.com:me/billing.git pay develop     # 이름 pay, 추적 브랜치 develop
just repo remove billing                                    # 흔적까지 완전히 제거한다
just repo remove billing --force                            # 버려질 작업이 있어도 제거한다
```

- `repo add`는 서브모듈 등록, 추적 브랜치 기록, 최신화(`just onto sync <이름>`)를 한다. 최신화는 `.onto/`와 스킬을 복사하고, `.gitignore`와 지침 파일에 표시된 블록을 넣고, 없으면 온톨로지 층의 뼈대(`docs/ontology/ontology.yaml`과 인덱스)를 만든다. `ontology.yaml`의 공유 범위(`scope`)는 가장 좁은 `private`으로 시작한다. 저장소를 공유하는 범위에 맞게 바꾼다.
- 이미 온톨로지 층이 있는 저장소를 붙여도 저장소 소유 파일(`ontology.yaml`, 페이지)은 바뀌지 않는다.
- `repo remove`는 커밋하지 않았거나 푸시하지 않은 작업이 있으면 이유를 알리고 거부한다. 제거도 스테이징까지만 한다.
- 어떤 명령도 자동으로 커밋하지 않는다.

## ingest: 원본 문서를 지식으로 정리하기

ingest는 요청할 때만 한다. 자동으로 돌지 않는다.

1. 대상을 확인한다. 새로 생겼거나 바뀐 원본 문서가 나온다.
   ```sh
   just onto status
   ```
2. 에이전트에게 스킬 `onto-ingest`로 지식 저장소 하나를 정리하게 한다(예: "billing을 onto-ingest로 정리해 줘"). 에이전트는 문서를 읽어 페이지를 쓰고, 페이지의 `derivedFrom`에 원본 문서의 경로와 해시를 기록하고, 기록할 것이 없는 문서는 `docs/ontology/skipped.yaml`에 적는다. 원본 문서는 고치지 않고, 커밋하지 않는다.
3. 에이전트가 쓴 것을 검토한다.
   ```sh
   git -C projects/billing status
   git -C projects/billing diff
   ```
4. 컴파일하고 검사한다. 오류가 0개여야 한다.
   ```sh
   just onto build
   just onto validate
   ```
5. 지식 저장소에 커밋하고, 루트 저장소가 그 커밋을 가리키게 커밋한다.
   ```sh
   git -C projects/billing add docs/ontology      # 처음이면 최신화가 만든 .gitignore와 지침 파일(AGENTS.md나 CLAUDE.md)도 add한다
   git -C projects/billing commit -m "onto(ingest): 결제 설계 문서에서 게이트웨이와 용어 페이지 추가"
   git add projects/billing
   git commit -m "chore: billing 지식 갱신"
   just git push
   ```

원본 문서가 바뀌면 그것을 근거로 한 페이지는 낡음이 된다(`stale-page` 경고). `just onto status`가 바뀐 문서와 낡은 페이지를 보여 주고, 같은 방법으로 다시 ingest한다.

## 질의

```sh
just onto query 'SELECT ?e ?t WHERE { ?e a onto:Component ; dcterms:title ?t } ORDER BY ?t'
```

- 질의문은 작은따옴표 하나로 감싸 한 인자로 넘긴다. 실행할 때마다 현재 파일에서 다시 컴파일하고, 하위 클래스, 역관계, 추이 관계가 추론된 그래프를 질의한다.
- 결과의 엔티티는 파일 경로로 나온다. 그 경로가 페이지다.
- 에이전트에게는 스킬 `onto-query`로 질문한다. 질의하는 법, 클래스와 관계 목록, 자주 쓰는 질의가 스킬에 있다.
- `just onto build`는 컴파일한 그래프(`onto/.build/graph.ttl`)와 지식 저장소마다의 인덱스, 모든 지식 저장소를 모은 전체 인덱스(`onto/.build/index.md`)를 만든다. 인덱스(`docs/ontology/index.md`)는 생성물이지만 지식 저장소가 커밋하는 파일이다.

## 검사

```sh
just onto validate
```

- 스크립트 검사다. 구조 제약, 깨진 참조, 고아 페이지, 낡음, 인덱스, 공유 범위, 중복, 식별자 형식 같은 것을 기계적으로 잡는다. 어떤 파일도 고치지 않는다.
- 문제는 한 줄에 하나이고 탭으로 나눈 다섯 칸(심각도, 지식 저장소, 파일, 검사 항목, 설명)이다. 오류가 하나라도 있으면 종료 코드 1이고, 경고만 있으면 0이다. 문제가 없으면 아무것도 출력하지 않는다.
- 모순이나 빠진 개념처럼 판단이 필요한 검사는 에이전트에게 스킬 `onto-lint`로 요청한다. 스크립트 검사를 먼저 돌리고, 이어서 판단 검사를 하고, 고치기 전에 보고한다.
- 검사 항목마다 켬/끔과 심각도(오류, 경고)가 규칙으로 정해져 있다. 루트 기본값은 `onto/rules.yaml`에 있고, 지식 저장소는 `docs/ontology/ontology.yaml`의 `rules`로 자기 저장소에 한해 덮어쓴다. 적용되는 규칙은 다음 명령이 JSON으로 보여 준다. 푸시 관문과 공유 범위 검사는 루트 전용이라 덮어쓸 수 없다.
  ```sh
  just onto rules            # 루트 기본 규칙
  just onto rules billing    # billing의 ontology.yaml이 덮어쓴 값까지 합친 규칙
  ```

## 받기와 푸시

```sh
just git status          # 저장소별 미커밋, 미푸시, 뒤처짐 요약
just git pull            # 루트 저장소와 모든 지식 저장소를 fast-forward로 받는다
just git push            # 스크립트 검사 후 모든 저장소를 푸시한다
just git push --force    # 검사에 오류가 있어도 올린다
```

- `pull`은 fast-forward만 한다. 추적 브랜치에 있지 않은 지식 저장소와 fast-forward가 안 되는 저장소는 건드리지 않고 건너뛰어 이유를 보고한다. 루트의 서브모듈 포인터 변경은 커밋하지 않는다.
- `push`는 이미 커밋한 것만 올린다. 지식 저장소를 먼저 하나씩 올리고, 모두 성공해야 루트 저장소를 올린다. 현재 브랜치를 같은 이름의 원격 브랜치로 올린다. 미커밋 변경이 있는 저장소는 올리기 전에 목록으로 알린다.
- `push`는 올리기 전에 루트 저장소에서 스크립트 검사(`just onto validate`)를 돌린다(**푸시 관문**). 검사는 커밋된 내용이 아니라 작업 트리를 본다. 오류가 있으면 어떤 저장소도 올리지 않고 걸린 문제를 보여 주며 1로 끝난다. 경고만 있으면 경고를 보여 주고 올린다.
- `--force`(`-f`)는 관문만 넘긴다. 오류가 있어도 올리고, 관문을 넘겼다는 사실을 출력에 남긴다. git의 강제 푸시가 아니라서 원격의 이력을 덮어쓰지 않는다.
- 루트 기본 규칙(`onto/rules.yaml`)의 `push-gate`의 `enabled`를 `false`로 하면 관문이 꺼진다. 지식 저장소의 규칙으로는 끌 수 없다. 관문이 꺼져 있는지도 도구(`just onto rules`)가 읽으므로, 도구를 실행하지 못하는 환경(`uv`가 없다 등)에서는 켜진 것으로 보고 "검사 도구를 실행하지 못했다"며 막는다(`--force`로 넘긴다).
- 스크립트 검사는 `projects/` 바로 아래 숨김이 아닌 디렉토리만 지식 저장소로 본다. 그 밖에 손으로 등록한 서브모듈은 검사 없이 올라가며 푸시 전에 이름으로 알린다.
- 검사 관문은 이 명령 하나뿐이다. git 훅과 CI는 두지 않는다.

## 최신화

```sh
just onto sync [이름]    # 루트의 기능을 지식 저장소에 반영한다. 이름을 생략하면 모든 지식 저장소
```

루트의 `onto/`나 스킬(`.claude/skills/onto-*/`)을 고친 뒤, 또는 `just onto validate`가 `outdated-managed-files`로 최신화가 필요하다고 경고할 때 한다. 루트 저장소에서만 쓸 수 있다.

- 루트 관리 파일(`.onto/`, `.claude/skills/onto-*/`)을 루트의 내용으로 덮어쓴다. 루트에서 없앤 `onto-` 스킬은 지식 저장소에서도 지운다. 지식 저장소 팀의 스킬(`onto-`로 시작하지 않는 것)은 건드리지 않는다.
- 마지막 최신화 뒤에 손으로 고친 루트 관리 파일은 덮어쓰지 않고 파일마다 이유와 함께 보고한다(종료 코드 1). 루트의 내용으로 되돌리려면 그 파일을 지우고 다시 실행한다.
- 지식 저장소의 `Justfile`과 페이지, `ontology.yaml`은 바꾸지 않는다. 새 구조 제약에 어긋나게 된 페이지는 끝에 보고만 한다.
- 변경은 지식 저장소의 작업 트리에 남고 커밋하지 않는다. 두 번 실행하면 두 번째는 아무것도 바꾸지 않는다.

## 지식 저장소 안에서 쓰기

지식 저장소 안에서는 복사된 `Justfile`을 직접 가리켜 `build`, `validate`, `query`, `status`를 쓴다. 그때는 그 저장소의 지식만 다룬다.

```sh
cd projects/billing
just -f .onto/Justfile build
just -f .onto/Justfile validate
just -f .onto/Justfile query 'SELECT ?e WHERE { ?e a onto:Term }'
just -f .onto/Justfile status
```

- 에이전트도 같은 스킬(`onto-ingest`, `onto-query`, `onto-lint`)로 그 저장소 안에서 일한다. 스킬이 루트에서는 `just onto …`를, 지식 저장소 안에서는 `just -f .onto/Justfile …`를 쓰라고 안내한다.
- 저장소의 어느 디렉토리에서 불러도 그 저장소가 기준이다. 보고하는 경로도 그 저장소 기준이다.
- 교차 참조, 공유 범위 위반, 저장소 간 중복, 고아 페이지처럼 여러 저장소에 걸친 검사는 건너뛰고 건너뛰었다고 알린다. 그런 검사는 루트 저장소에서 한다.
- `sync`는 쓸 수 없다. 지식 저장소의 `.onto/`는 루트 저장소가 복사해 준 사본이다.
- 지식 저장소의 팀 `Justfile`이 `mod onto '.onto/Justfile'`로 불러도 같다.
- 복사된 기능이 없는 클론(팀원이 프로젝트 저장소만 클론한 경우)에서는 인덱스(`docs/ontology/index.md`)에서 페이지로 찾아가 파일로 읽는다.

## 명령 표

| 명령 | 동작 |
|---|---|
| `just setup` | 도구(git, just, uv)를 확인하고 서브모듈을 초기화해 추적 브랜치에 체크아웃 |
| `just repo add <url> [이름] [브랜치]` | 지식 저장소를 `projects/<이름>/`에 붙이고 기능을 복사. 스테이징까지만 한다 |
| `just repo remove <이름> [--force]` | 지식 저장소를 흔적까지 완전히 제거. 버려질 작업이 있으면 거부 |
| `just git status` | 저장소별 미커밋, 미푸시, 뒤처짐 요약 |
| `just git pull` | 모든 저장소의 최신 내용을 fast-forward로 받기 |
| `just git push [--force]` | 스크립트 검사 후 모든 저장소 푸시. 오류가 있으면 아무것도 올리지 않는다(`--force`로 넘긴다) |
| `just onto sync [이름]` | 루트의 기능과 스킬을 지식 저장소에 최신화 |
| `just onto build` | 그래프 컴파일과 인덱스 생성 |
| `just onto validate` | 스크립트 검사 |
| `just onto query '<SPARQL>'` | SPARQL 질의 |
| `just onto status` | 새로 생겼거나 바뀐 원본 문서 목록 |
| `just onto rules [이름]` | 적용되는 규칙을 JSON으로 출력 |
| `just -f .onto/Justfile <build\|validate\|query\|status\|rules>` | 지식 저장소 안에서 그 저장소만 다룬다 |

`just`, `just git`, `just repo`, `just onto`만 부르면 명령 목록을 보여 준다.

## 에이전트 스킬

| 스킬 | 언제 | 하는 일 |
|---|---|---|
| `onto-ingest` | 새로 생겼거나 바뀐 문서를 정리할 때 | `status`로 대상 확인, 기존 엔티티 찾기, 페이지 쓰기, `derivedFrom` 기록, 넘긴 문서 기록, `build`와 `validate`로 확인 |
| `onto-query` | 지식 저장소에 대해 질문할 때 | SPARQL 질의, 결과에서 페이지와 근거 원본으로 가기 |
| `onto-lint` | 점검을 요청할 때 | 스크립트 검사 뒤 모순과 빠진 개념을 찾아 보고하고, 승인받은 것만 고친다 |

세 스킬은 루트 저장소의 `.claude/skills/`에 있고, 최신화가 지식 저장소의 같은 위치로 복사한다. 루트에서는 붙인 지식 저장소 전체를, 지식 저장소 안에서는 그 저장소만 다룬다. 스킬은 원본 문서를 고치지 않고, 커밋하지 않고, 지식 저장소 단위로 일한다.

## 커밋 메시지 규약

온톨로지 층(`docs/ontology/`)을 바꾸는 지식 저장소의 커밋은 `onto(<작업>): <요약>`으로 쓴다. `log.md`를 두지 않고 git 이력과 이 규약이 그 일을 한다.

| 형식 | 쓰는 때 |
|---|---|
| `onto(ingest): <무엇을 정리했는지>` | 원본 문서에서 페이지를 만들거나 고쳤을 때 |
| `onto(lint): <무엇을 고쳤는지>` | 점검으로 페이지를 고쳤을 때 |

예: `onto(ingest): 결제 설계 문서에서 게이트웨이와 용어 페이지 추가`, `onto(lint): 결제 게이트웨이의 중복 페이지 병합`.

## 문서

- [`GLOSSARY.md`](GLOSSARY.md): 이 프로젝트의 용어
- [`docs/adr/`](docs/adr/): 되돌리기 어려운 결정과 그 이유
- [`onto/template/conventions.md`](onto/template/conventions.md): 페이지를 쓰는 법(키, 클래스, 식별자, 관계, `derivedFrom`). 지식 저장소에는 `.onto/template/conventions.md`로 복사된다
- [`tests/README.md`](tests/README.md): 테스트 실행과 테스트 받침
- [스펙 이슈 #1](https://github.com/powerumc/ontology/issues/1): 사용자 스토리, 구현 결정, 테스트 결정
- [이슈 목록](https://github.com/powerumc/ontology/issues): 구현 티켓
- [`docs/agents/`](docs/agents/): 에이전트 스킬이 읽는 이슈 트래커와 문서 규약

## 참고한 사례

- [Karpathy LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): 원본 소스, 위키, 스키마 파일의 3개 층과 ingest, query, lint의 3개 운영
- [LA3D/llm-wiki-colab](https://la3d.github.io/llm-wiki-colab/): 연합형 확장. OWL/SKOS 관계, JSON-LD context, SHACL
- [wazootech/wiki](https://github.com/wazootech/wiki): frontmatter를 RDF로 변환하고 소스별 named graph로 적재
