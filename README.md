# ontology

저장소 하나를 모듈 하나로 삼는 **모듈형 온톨로지** 도구입니다. 여러 저장소에 흩어진 문서를 저장소마다 온톨로지로 정리하고, 이를 하나로 합쳐 질의하고 검사할 수 있습니다. [Karpathy의 LLM Wiki 패턴](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)을 뼈대로 삼고, 그 위에 RDF 온톨로지와 git 서브모듈 구조를 더했습니다.

## 풀려는 문제

- 프로젝트마다 계획, 정책·정의, 구현 결과 문서가 제각각의 형식으로 흩어져 있습니다. 그래서 LLM 에이전트는 필요한 지식을 찾을 때마다 원본 문서를 처음부터 읽어야 합니다.
- 프로젝트 사이의 관계는 어디에도 기록되어 있지 않습니다.
- 전체를 한곳에서 질의하고 싶지만, 각 프로젝트 저장소 안에서는 그 저장소의 지식만 보여야 합니다.

## 동작 방식

- 이 저장소가 **루트 저장소**입니다. 기능만 제공하고 지식은 담지 않습니다.
- 지식 저장소는 git 서브모듈로 루트 저장소의 `projects/` 아래에 붙습니다. 지식 저장소 하나가 온톨로지 모듈 하나입니다.
- LLM 에이전트가 지식 저장소의 원본 문서를 읽어 온톨로지 층(`docs/ontology/`)의 페이지를 쓰고(ingest), 사람은 `git diff`로 검토합니다. 원본 문서는 고치지 않습니다.
- 페이지는 마크다운과 YAML frontmatter로 씁니다. 이를 RDF 그래프로 컴파일해 SPARQL 질의, SHACL 구조 제약 검사, 가벼운 추론에 활용합니다.
- 루트 저장소에서는 붙인 지식 저장소 전체를, 지식 저장소 안에서는 그 저장소의 지식만 다룹니다.
- 지식 저장소에는 온톨로지 기능이 들어 있지 않습니다. 붙일 때 루트 저장소가 기능을 복사해 줍니다(**최신화**).
  - `onto/`(코드, 공통 어휘, 규칙, 템플릿, 규약 문서)는 지식 저장소의 `.onto/`로, 에이전트 스킬 `.claude/skills/onto-*/`는 같은 위치로 복사됩니다.
  - 복사된 기능은 지식 저장소의 `.gitignore`로 제외되므로, 지식 저장소의 이력에는 `docs/ontology/`의 지식만 남습니다.
  - 지식 저장소의 프로젝트 지침 파일(`CLAUDE.md`, 없으면 `AGENTS.md`)에는 최신화가 표시된 블록 하나를 넣어 온톨로지 층의 인덱스를 안내합니다. 블록 밖은 건드리지 않으며, 복사된 기능이 없는 클론에서도 뜻이 통하도록 썼습니다.
  - 공통 어휘는 semver로 버전을 관리합니다. `just onto validate`는 `.onto/`나 스킬 사본이 루트와 내용이 다른 지식 저장소를 경고합니다(버전 번호를 올리지 않은 수정도 찾아냅니다).

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
        ├── ontology.yaml     # 저장소 이름, 공유 범위, 프로젝트의 의존, 규칙 덮어쓰기
        ├── index.md          # 진입점 (생성물)
        ├── skipped.yaml      # 읽고도 기록할 것이 없던 원본 문서의 목록 (필요할 때 생김)
        └── plan/ policy/ term/ decision/ report/ component/
```

## 받아서 쓰기

이 저장소를 받아 자신의 것으로 쓰시면 됩니다. 필요한 도구는 `git`, `just`, `uv`입니다.

```sh
git clone https://github.com/powerumc/ontology my-ontology && cd my-ontology
git remote set-url origin <내 원격 저장소 주소>     # 이제 이 저장소가 내 루트 저장소가 됩니다
just setup                                         # 도구를 확인하고 서브모듈을 초기화합니다(온톨로지 층이 있는 지식 저장소는 기능도 복사합니다)
just repo add <지식 저장소 주소> [이름] [브랜치]      # 지식 저장소를 붙이고 기능을 복사합니다
git commit -m "chore: <이름> 지식 저장소를 등록한다"   # 등록은 스테이징까지만 하므로 커밋은 직접 합니다
just git push                                      # 내 원격으로 올립니다
```

- 이 공개 원본에는 지식 저장소가 하나도 등록되어 있지 않습니다. `origin`이 공개 원본인 상태에서는 `just repo add`가 거부되니, 받은 뒤 `origin`을 바꾸고 나서 붙여 주세요.
- 등록한 지식 저장소는 내 루트 저장소에 커밋합니다. 다른 기기에서는 이 저장소를 클론하고 `just setup`만 하면 같은 구성이 됩니다. 복사된 기능(`.onto/`, 스킬 사본)은 지식 저장소의 커밋에 들어가지 않기 때문에, `setup`이 서브모듈을 체크아웃한 뒤 온톨로지 층(`docs/ontology/ontology.yaml`)이 있는 지식 저장소마다 `just onto sync <이름>`을 실행해 다시 만들어 줍니다.
- 개인 지식(여러 프로젝트를 비교·종합한 지식, 서로 다른 저장소의 용어가 같다는 사실)은 **개인 지식 저장소**에 두는 것을 권합니다. 비공개 저장소를 하나 만들어 같은 방법(`just repo add`)으로 붙이시면 됩니다. 이렇게 하면 팀 저장소에 개인적인 해석이 섞이지 않습니다.
- 새 기기에서 클론한 직후에는 `just setup`을 실행해 주세요. 서브모듈이 detached HEAD가 아니라 추적 브랜치에 체크아웃되고, 루트가 기록한 커밋에서 시작합니다(원격의 최신으로 올리지는 않습니다). 이어서 최신화가 `.onto/`와 스킬 사본을 만들어 주므로, 지식 저장소 안에서도 `just -f .onto/Justfile …`와 스킬을 쓸 수 있습니다.
  - 최신화는 커밋하지 않습니다. 온톨로지 층이 없는 지식 저장소는 최신화하지 않으니, `just onto sync <이름>`으로 구성해 주세요.
  - 최신화가 실패하더라도 서브모듈 설정은 그대로 유지되고, 실패한 저장소를 알린 뒤 종료 코드 1로 끝납니다. 원인을 고친 다음 `just onto sync <이름>`을 실행하시면 됩니다.

## 지식 저장소 붙이기와 떼기

```sh
just repo add git@github.com:me/billing.git                 # projects/billing/에 붙입니다. 이름은 주소의 저장소 이름을 씁니다
just repo add git@github.com:me/billing.git pay develop     # 이름 pay, 추적 브랜치 develop
just repo remove billing                                    # 흔적까지 깨끗하게 제거합니다
just repo remove billing --force                            # 버려질 작업이 있어도 제거합니다
```

- `repo add`는 서브모듈 등록, 추적 브랜치 기록, 최신화(`just onto sync <이름>`)를 합니다. 최신화는 `.onto/`와 스킬을 복사하고, `.gitignore`와 지침 파일에 표시된 블록을 넣으며, 온톨로지 층이 없으면 뼈대(`docs/ontology/ontology.yaml`과 인덱스)를 만들어 줍니다. `ontology.yaml`의 공유 범위(`scope`)는 가장 좁은 `private`으로 시작하니, 저장소를 공유하는 범위에 맞게 바꿔 주세요.
- 이미 온톨로지 층이 있는 저장소를 붙여도 저장소 소유 파일(`ontology.yaml`, 페이지)은 바뀌지 않습니다. 그 저장소가 `ontology.yaml`에 `name`을 선언했다면 등록 이름이 그 `name`과 같아야 합니다(`name`은 서브모듈 디렉토리 이름과 같아야 하고, 교차 참조가 그 이름으로 저장소를 가리키기 때문입니다). 이름이 다르면 `repo add`가 등록하기 전에 거부하고 선언된 이름을 알려 줍니다. 선언한 `name`을 확인하지 못한 경우(원격에서 받지 못했거나 파일을 읽을 수 없는 경우)에는 그 사실을 알리고 등록은 계속합니다. 확인을 위해 추적 브랜치의 끝을 한 번 더 얕게 받아 옵니다.
- `repo remove`는 커밋하지 않았거나 푸시하지 않은 작업이 있으면 이유를 알리고 거부합니다. 제거도 스테이징까지만 합니다.
- 어떤 명령도 자동으로 커밋하지 않습니다.

## ingest: 원본 문서를 지식으로 정리하기

ingest는 요청할 때만 실행되고, 자동으로 돌지 않습니다.

1. 대상을 확인합니다. 새로 생겼거나 바뀐 원본 문서가 표시됩니다.
   ```sh
   just onto status
   ```
2. 에이전트에게 스킬 `onto-ingest`로 지식 저장소 하나를 정리하도록 요청합니다(예: "billing을 onto-ingest로 정리해 줘"). 에이전트는 문서를 읽어 페이지를 쓰고, 페이지의 `derivedFrom`에 원본 문서의 경로와 해시를 기록하며, 기록할 것이 없는 문서는 `docs/ontology/skipped.yaml`에 적습니다. 다 쓰고 나면 새 맥락의 서브에이전트가 쓰거나 고친 페이지를 원본과 대조해(대조 검토) 근거 없는 문장, 인용 누락, 모순을 보고하고, 에이전트가 그 내용을 고칩니다. 원본 문서는 고치지 않으며, 커밋도 하지 않습니다.
3. 에이전트가 쓴 내용을 검토합니다.
   ```sh
   git -C projects/billing status
   git -C projects/billing diff
   ```
4. 컴파일하고 검사합니다. 오류가 0개여야 합니다.
   ```sh
   just onto build
   just onto validate
   ```
5. 지식 저장소에 커밋하고, 루트 저장소가 그 커밋을 가리키도록 커밋합니다.
   ```sh
   git -C projects/billing add docs/ontology      # 처음이라면 최신화가 만든 .gitignore와 지침 파일(AGENTS.md나 CLAUDE.md)도 함께 add합니다
   git -C projects/billing commit -m "onto(ingest): 결제 설계 문서에서 게이트웨이와 용어 페이지 추가"
   git add projects/billing
   git commit -m "chore: billing 지식 갱신"
   just git push
   ```

원본 문서가 바뀌면 그 문서를 근거로 한 페이지는 낡음 상태가 됩니다(`stale-page` 경고). `just onto status`가 바뀐 문서와 낡은 페이지를 보여 주니, 같은 방법으로 다시 ingest하시면 됩니다.

## 질의

```sh
just onto query 'SELECT ?e ?t WHERE { ?e a onto:Component ; dcterms:title ?t } ORDER BY ?t'
```

- 질의문은 작은따옴표로 감싸 하나의 인자로 넘깁니다. 실행할 때마다 현재 파일에서 다시 컴파일하고, 하위 클래스, 역관계, 추이 관계가 추론된 그래프를 질의합니다.
- 결과의 엔티티는 파일 경로로 나오며, 그 경로가 곧 페이지입니다.
- 에이전트에게는 스킬 `onto-query`로 질문하시면 됩니다. 질의하는 법, 클래스와 관계 목록, 자주 쓰는 질의가 스킬에 정리되어 있습니다.
- `just onto build`는 컴파일한 그래프(`onto/.build/graph.ttl`)와 지식 저장소별 인덱스, 모든 지식 저장소를 모은 전체 인덱스(`onto/.build/index.md`)를 만듭니다. 인덱스(`docs/ontology/index.md`)는 생성물이지만 지식 저장소에 커밋하는 파일입니다.

## 검사

```sh
just onto validate
```

- 스크립트 검사입니다. 구조 제약, 깨진 참조(관계의 값과 본문 링크의 대상), 고아 페이지, 낡음, 인덱스, 공유 범위, 중복, 식별자 형식 같은 것을 기계적으로 찾아냅니다. 어떤 파일도 고치지 않습니다.
- 문제는 한 줄에 하나씩, 탭으로 나눈 다섯 칸(심각도, 지식 저장소, 파일, 검사 항목, 설명)으로 출력됩니다. 오류가 하나라도 있으면 종료 코드 1, 경고만 있으면 0입니다. 문제가 없으면 아무것도 출력하지 않습니다.
- 모순, 근거 없는 문장, 인용 누락, 빠진 개념처럼 판단이 필요한 검사(LLM 검사)는 에이전트에게 스킬 `onto-lint`로 요청해 주세요. 스크립트 검사를 먼저 돌리고, 이어서 판단 검사를 한 뒤, 고치기 전에 결과를 보고합니다.
- 검사 항목마다 켬/끔과 심각도(오류, 경고)가 규칙으로 정해져 있습니다. 루트 기본값은 `onto/rules.yaml`에 있고, 지식 저장소는 `docs/ontology/ontology.yaml`의 `rules`로 자기 저장소에 한해 덮어쓸 수 있습니다. 적용되는 규칙은 다음 명령으로 JSON 형태로 확인할 수 있습니다. 푸시 관문, 식별자 형식(`language.identifier-pattern`), 공유 범위 검사는 루트 전용이라 덮어쓸 수 없습니다.
  ```sh
  just onto rules            # 루트 기본 규칙
  just onto rules billing    # billing의 ontology.yaml이 덮어쓴 값까지 합친 규칙
  ```

## 받기와 푸시

```sh
just git status          # 저장소별 미커밋, 미푸시, 뒤처짐 요약
just git pull            # 루트 저장소와 모든 지식 저장소를 fast-forward로 받습니다
just git push            # 스크립트 검사 후 모든 저장소를 푸시합니다
just git push --force    # 검사에 오류가 있어도 올립니다
```

- `pull`은 fast-forward만 합니다. 추적 브랜치에 있지 않은 지식 저장소나 fast-forward가 되지 않는 저장소는 건드리지 않고 건너뛰며, 그 이유를 알려 줍니다. 루트의 서브모듈 포인터 변경은 커밋하지 않습니다.
- `push`는 이미 커밋한 것만 올립니다. 지식 저장소를 먼저 하나씩 올리고, 모두 성공해야 루트 저장소를 올립니다. 현재 브랜치를 같은 이름의 원격 브랜치로 올리며, 미커밋 변경이 있는 저장소는 올리기 전에 목록으로 알려 줍니다.
- `push`는 올리기 전에 루트 저장소에서 스크립트 검사(`just onto validate`)를 실행합니다(**푸시 관문**). 검사는 커밋된 내용이 아니라 작업 트리를 기준으로 합니다. 오류가 있으면 어떤 저장소도 올리지 않고 걸린 문제를 보여 준 뒤 1로 끝납니다. 경고만 있으면 경고를 보여 주고 올립니다.
- `--force`(`-f`)는 관문만 건너뜁니다. 오류가 있어도 올리고, 관문을 건너뛰었다는 사실을 출력에 남깁니다. git의 강제 푸시와는 달라서 원격의 이력을 덮어쓰지 않습니다.
- 루트 기본 규칙(`onto/rules.yaml`)의 `push-gate`의 `enabled`를 `false`로 하면 관문이 꺼집니다. 지식 저장소의 규칙으로는 끌 수 없습니다. 관문이 꺼져 있는지도 도구(`just onto rules`)가 읽기 때문에, 도구를 실행할 수 없는 환경(`uv`가 없는 경우 등)에서는 켜진 것으로 보고 "검사 도구를 실행하지 못했다"며 푸시를 막습니다(`--force`로 건너뛸 수 있습니다).
- 스크립트 검사는 `projects/` 바로 아래에 있는 숨김이 아닌 디렉토리만 지식 저장소로 봅니다. 그 밖에 직접 등록한 서브모듈은 검사 없이 올라가며, 푸시 전에 이름으로 알려 드립니다.
- 검사 관문은 이 명령 하나뿐입니다. git 훅과 CI는 두지 않았습니다.

## 최신화

```sh
just onto sync [이름]    # 루트의 기능을 지식 저장소에 반영합니다. 이름을 생략하면 모든 지식 저장소에 반영합니다
```

루트의 `onto/`나 스킬(`.claude/skills/onto-*/`)을 고친 뒤, 또는 `just onto validate`가 `outdated-managed-files`로 최신화가 필요하다고 경고할 때 실행해 주세요. `just repo add`와 `just setup`이 최신화를 함께 실행하므로, 새로 붙이거나 새 기기에서 클론했을 때는 따로 실행하지 않으셔도 됩니다. 루트 저장소에서만 쓸 수 있습니다.

- 루트 관리 파일(`.onto/`, `.claude/skills/onto-*/`)을 루트의 내용으로 덮어씁니다. 루트에서 없앤 `onto-` 스킬은 지식 저장소에서도 지웁니다. 지식 저장소 팀의 스킬(`onto-`로 시작하지 않는 것)은 건드리지 않습니다.
- 마지막 최신화 뒤에 손으로 고친 루트 관리 파일은 덮어쓰지 않고, 파일마다 이유와 함께 알려 드립니다(종료 코드 1). 루트의 내용으로 되돌리려면 그 파일을 지우고 다시 실행해 주세요.
- 지식 저장소의 `Justfile`과 페이지, `ontology.yaml`은 바꾸지 않습니다. 새 구조 제약에 어긋나게 된 페이지는 마지막에 알려 드리기만 합니다.
- 변경은 지식 저장소의 작업 트리에 남고 커밋하지 않습니다. 두 번 실행해도 두 번째에는 아무것도 바뀌지 않습니다.

## 지식 저장소 안에서 쓰기

지식 저장소 안에서는 복사된 `Justfile`을 직접 지정해 `build`, `validate`, `query`, `status`를 쓸 수 있습니다. 이때는 그 저장소의 지식만 다룹니다.

```sh
cd projects/billing
just -f .onto/Justfile build
just -f .onto/Justfile validate
just -f .onto/Justfile query 'SELECT ?e WHERE { ?e a onto:Term }'
just -f .onto/Justfile status
```

- 에이전트도 같은 스킬(`onto-ingest`, `onto-query`, `onto-lint`)로 그 저장소 안에서 일합니다. 스킬이 루트에서는 `just onto …`를, 지식 저장소 안에서는 `just -f .onto/Justfile …`를 쓰도록 안내합니다.
- 저장소의 어느 디렉토리에서 실행해도 그 저장소를 기준으로 동작하고, 보고하는 경로도 그 저장소 기준입니다.
- 교차 참조, 공유 범위 위반, 저장소 간 중복, 고아 페이지처럼 여러 저장소에 걸친 검사는 건너뛰고, 건너뛰었다는 사실을 알려 드립니다. 이런 검사는 루트 저장소에서 해 주세요.
- `sync`는 쓸 수 없습니다. 지식 저장소의 `.onto/`는 루트 저장소가 복사해 준 사본이기 때문입니다.
- 지식 저장소 팀의 `Justfile`이 `mod onto '.onto/Justfile'`로 불러와도 똑같이 동작합니다.
- 복사된 기능이 없는 클론(팀원이 프로젝트 저장소만 클론한 경우)에서는 인덱스(`docs/ontology/index.md`)에서 페이지를 찾아 파일로 읽으시면 됩니다.

## 명령 표

| 명령 | 동작 |
|---|---|
| `just setup` | 도구(git, just, uv)를 확인하고 서브모듈을 초기화해 추적 브랜치에 체크아웃한 뒤, 온톨로지 층이 있는 지식 저장소를 최신화합니다(커밋하지 않습니다) |
| `just repo add <url> [이름] [브랜치]` | 지식 저장소를 `projects/<이름>/`에 붙이고 기능을 복사합니다. 스테이징까지만 합니다 |
| `just repo remove <이름> [--force]` | 지식 저장소를 흔적까지 깨끗하게 제거합니다. 버려질 작업이 있으면 거부합니다 |
| `just git status` | 저장소별 미커밋, 미푸시, 뒤처짐 요약 |
| `just git pull` | 모든 저장소의 최신 내용을 fast-forward로 받기 |
| `just git push [--force]` | 스크립트 검사 후 모든 저장소를 푸시합니다. 오류가 있으면 아무것도 올리지 않습니다(`--force`로 건너뛸 수 있습니다) |
| `just onto sync [이름]` | 루트의 기능과 스킬을 지식 저장소에 최신화 |
| `just onto build` | 그래프 컴파일과 인덱스 생성 |
| `just onto validate` | 스크립트 검사 |
| `just onto query '<SPARQL>'` | SPARQL 질의 |
| `just onto status` | 새로 생겼거나 바뀐 원본 문서 목록 |
| `just onto rules [이름]` | 적용되는 규칙을 JSON으로 출력 |
| `just -f .onto/Justfile <build\|validate\|query\|status\|rules>` | 지식 저장소 안에서 그 저장소만 다룹니다 |

`just`, `just git`, `just repo`, `just onto`만 실행하면 명령 목록을 보여 드립니다.

## 에이전트 스킬

| 스킬 | 언제 | 하는 일 |
|---|---|---|
| `onto-ingest` | 새로 생겼거나 바뀐 문서를 정리할 때 | `status`로 대상 확인, 기존 엔티티 찾기, 페이지 쓰기, `derivedFrom` 기록, 넘긴 문서 기록, `build`와 `validate`로 확인, 새 맥락의 서브에이전트가 원본과 대조하는 대조 검토 |
| `onto-query` | 지식 저장소에 대해 질문할 때 | SPARQL 질의, 결과에서 페이지와 근거 원본으로 가기 |
| `onto-lint` | 점검을 요청할 때 | 스크립트 검사 뒤 모순, 근거 없는 문장, 인용 누락, 빠진 개념을 찾아 보고하고, 승인받은 것만 고칩니다 |

세 스킬은 루트 저장소의 `.claude/skills/`에 있고, 최신화가 지식 저장소의 같은 위치로 복사합니다. 루트에서는 붙인 지식 저장소 전체를, 지식 저장소 안에서는 그 저장소만 다룹니다. 스킬은 원본 문서를 고치지 않고, 커밋하지 않으며, 지식 저장소 단위로 일합니다.

## 커밋 메시지 규약

온톨로지 층(`docs/ontology/`)을 바꾸는 지식 저장소의 커밋은 `onto(<작업>): <요약>` 형식으로 써 주세요. `log.md`를 따로 두지 않고, git 이력과 이 규약이 그 역할을 합니다.

| 형식 | 쓰는 때 |
|---|---|
| `onto(ingest): <무엇을 정리했는지>` | 원본 문서에서 페이지를 만들거나 고쳤을 때 |
| `onto(lint): <무엇을 고쳤는지>` | 점검으로 페이지를 고쳤을 때 |

예: `onto(ingest): 결제 설계 문서에서 게이트웨이와 용어 페이지 추가`, `onto(lint): 결제 게이트웨이의 중복 페이지 병합`.

## 문서

- [`GLOSSARY.md`](GLOSSARY.md): 이 프로젝트의 용어
- [`docs/adr/`](docs/adr/): 되돌리기 어려운 결정과 그 이유
- [`onto/template/conventions.md`](onto/template/conventions.md): 페이지를 쓰는 법(키, 클래스, 식별자, 관계, `derivedFrom`). 지식 저장소에는 `.onto/template/conventions.md`로 복사됩니다
- [`tests/README.md`](tests/README.md): 테스트 실행과 테스트 받침
- [스펙 이슈 #1](https://github.com/powerumc/ontology/issues/1): 사용자 스토리, 구현 결정, 테스트 결정
- [이슈 목록](https://github.com/powerumc/ontology/issues): 구현 티켓
- [`docs/agents/`](docs/agents/): 에이전트 스킬이 읽는 이슈 트래커와 문서 규약

## 참고한 사례

- [Karpathy LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): 원본 소스, 위키, 스키마 파일의 3개 층과 ingest, query, lint의 3개 운영
- [LA3D/llm-wiki-colab](https://la3d.github.io/llm-wiki-colab/): 연합형 확장. OWL/SKOS 관계, JSON-LD context, SHACL
- [wazootech/wiki](https://github.com/wazootech/wiki): frontmatter를 RDF로 변환하고 소스별 named graph로 적재
