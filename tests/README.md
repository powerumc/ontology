# 테스트 안내

## 실행

```sh
uv run pytest                      # 전체. 기본으로 pytest-xdist가 코어 수만큼 병렬로 돌린다. 의존성을 처음 내려받을 때만 네트워크가 필요하다
uv run pytest -n 0                 # 직렬. 실패를 하나씩 따라가거나 디버거를 붙일 때
uv run pytest -n 0 -k 추적_브랜치   # 적은 수의 테스트는 직렬이 더 빠르다(워커를 띄우는 시간이 든다)
uv run pytest tests/test_setup.py  # 파일 하나
```

테스트마다 임시 디렉토리에 루트 저장소와 원격을 새로 꾸려 한 테스트가 1~2초 걸린다. 직렬은 몇 분, 병렬은 1분 안팎이다. `addopts`의 `-n auto`가 기본이므로 직렬은 `-n 0`으로 돌린다. 병렬이든 직렬이든 같은 결과여야 한다.

### 병렬 실행에서 지켜야 할 것

- 테스트는 `tmp_path` 안에서만 일하고 서로 상태를 나누지 않는다. 이 저장소의 작업 사본은 읽기만 한다.
- 세션 범위 픽스처는 pytest-xdist에서 **워커마다** 한 번씩 만들어진다. `onto_tool_dir`(온톨로지 도구의 사본, 가상환경, 산출물 `.build/`)가 그렇다. 워커 안에서는 테스트가 차례로 돌아 서로 겹치지 않는다. 새 세션 범위 픽스처가 디스크에 쓰면 워커마다 따로 쓰게 하고(`tmp_path_factory`), 고정 경로에 쓰지 않는다.

## 새 파일은 `git add` 한 뒤에 테스트에 보인다

테스트용 루트 저장소는 이 저장소의 **추적 파일**(`git ls-files`)을 임시 디렉토리로 복사해 만든다. 새로 만든 파일(예: `onto/rules.yaml`)을 `git add`하지 않고 테스트를 돌리면 샌드박스 루트에 그 파일이 없어, 이유를 알기 어려운 실패가 난다. 온톨로지 도구(`onto/`)를 실행하는 테스트도 같다(아래). 서브모듈 등록(`.gitmodules`, gitlink)은 복사하지 않는다.

## 테스트 받침 (`tests/support/sandbox.py`)

`sandbox` 픽스처가 테스트마다 새 임시 디렉토리와 격리된 git 환경을 준다.

- `sandbox.root()`: 루트 저장소와 bare 원격. `.register(원격, name=, branch=)`, `.point_at(이름, 커밋)`, `.commit({경로: 내용})`(소유자의 작업 사본에서 커밋하고 푸시), `.clone()`(서브모듈은 초기화하지 않음), `.set_up_clone()`(클론하고 `just setup`까지), `.leave_gitmodules_unmerged(원격)`(인덱스의 `.gitmodules`를 병합 충돌 상태로 만든다)
- `sandbox.knowledge_remote(이름)`: 가짜 지식 저장소와 bare 원격. `.commit(branch=, files={경로: 내용})`(`files`를 생략하면 새 메모 파일을 더한다), `.set_default_branch(브랜치)`
- `sandbox.just(...)`, `sandbox.git(...)`: 명령 실행. `just(without=("uv",))`는 PATH에서 도구를 뺀다
- `sandbox.head(저장소)`, `sandbox.branch(저장소)`
- `sandbox.snapshot(저장소)`: HEAD, 인덱스, 작업 트리 상태, `.gitmodules`, 서브모듈 설정, `.git/modules`를 모은 값. 명령을 부르기 전후로 비교해 "아무것도 바꾸지 않는다"를 확인한다
- `copy_tracked_files(sandbox, 원본, 대상, under=…)`: 원본 저장소의 추적 파일을 복사한다. `under`를 주면 그 아래만 접두어를 떼고 복사한다(`onto/` → `.onto/`)

테스트용 `ssh`가 PATH 맨 앞에 있다. 접속하지 않고 `ssh -G <호스트>`에만 답한다. 개발자의 `~/.ssh/config`를 읽지 않으므로, ssh 호스트 별칭이 필요한 테스트는 `sandbox.ssh_alias("github-personal", "github.com")`로 별칭을 적는다.

`ssh`·`https` 주소가 필요한 테스트는 `git config --global url.<로컬 원격>.insteadOf <주소>`로 그 주소를 로컬 원격에 잇는다. 전역 설정은 임시 파일이라 테스트마다 따로다.

지키는 약속: 네트워크를 쓰지 않는다(로컬 파일 전송만 허용). 전역 git 설정을 읽지도 바꾸지도 않는다. 임시 디렉토리 밖에서는 명령을 실행하지 않고, 이 저장소의 `Justfile`을 직접 가리켜 실행하지 않는다(등록 명령이 이 작업 사본에 서브모듈을 만든다). 이 저장소의 가상환경이 샌드박스로 새지 않는다.

## 온톨로지 도구의 명령줄 진입점 (`tests/support/onto_cli.py`)

스펙의 두 번째 이음매다. 검사 항목별 경우처럼 git 저장소를 통째로 꾸리기엔 수가 많은 것에 쓴다. `onto_cli` 픽스처가 견본 페이지 디렉토리를 만들고 그 안에서 도구를 실행한다.

```python
def test_예(onto_cli):
    root = onto_cli.root({"billing": repo("billing", page("plan/x", "Plan", title="제목"))})
    rows = onto_cli.query(root, "SELECT ?e ?t WHERE { ?e dcterms:title ?t }")  # 머리 행을 뺀 행 목록
    result = onto_cli.run(root, "build")                                        # 종료 코드, 출력을 직접 볼 때
```

- `onto_cli.root({저장소명: {지식 저장소 안의 경로: 내용}})`: `projects/<저장소명>/…` 모양의 임시 디렉토리. git 저장소가 아니다. 도구는 현재 디렉토리를 루트 저장소로 본다.
- `onto_cli.repository(저장소명, {지식 저장소 안의 경로: 내용})`: 지식 저장소 하나의 견본 디렉토리(파일이 저장소 루트에 놓인다. 루트 저장소는 없다). `onto_cli.run(…, within=REPOSITORY)`(`support.onto_cli.REPOSITORY`)로 실행하면 지식 저장소 안에서 `just -f .onto/Justfile`로 부른 것과 같다. 복사된 `Justfile`이 지식 저장소 안에서 도구에 `--within repository`를 넘기기 때문이다(지식 저장소의 공유 범위 `scope`와 무관하다). `run`, `build`, `query`가 `within`을 받는다. 루트나 다른 지식 저장소를 읽지 않는 것은 `onto_cli.root`의 `projects/<저장소>/` 아래 저장소를 `chmod 000`으로 읽을 수 없게 한 채 그 안에서 돌려 본다.
- `repo(이름, 페이지…)`, `page(식별자, 클래스, 제목=…, partOf=[…])`, `ontology_yaml(이름, …)`: 견본 파일을 만든다. 값은 JSON으로 적어 YAML이 된다. `repo`의 키워드 인자는 `ontology.yaml`의 키가 된다(예: `repo("billing", title="결제", classes={"Invoice": {"subClassOf": "Component"}})`). 다른 지식 저장소의 엔티티는 `partOf=["shop:component/api"]`처럼 `<저장소 이름>:<식별자>`로 가리킨다.
- 도구는 이 저장소의 추적 `onto/` 파일의 사본에서 돈다. 가상환경은 테스트 세션마다 한 번 만든다. 의존성을 처음 내려받을 때만 네트워크가 필요하다.
- `onto_cli.query`와 `build`가 보는 그래프는 추론(하위 클래스, 역관계, 추이 관계)이 끝난 것이다. 정렬하지 않은 질의의 행 순서는 rdflib이 정하고 실행마다 다를 수 있으니, 행의 순서를 비교하는 테스트는 `ORDER BY`를 쓴다.
- 도구는 산출물(컴파일한 그래프)을 자기 디렉토리의 `.build/`에 둔다. 도구 사본은 테스트 세션이 공유하므로 `onto_cli`가 테스트마다 비운다. `onto_cli.build(root)`가 그래프 파일의 내용을, `onto_cli.graph_file`이 그 위치를 준다. 견본 루트에는 아무것도 생기지 않아야 하고, `snapshot(root)`로 앞뒤를 비교한다.
- 같은 도구를 `just onto …`로 부르는 테스트(`test_onto_just.py`)는 서브모듈로 붙인 지식 저장소를 상대로 하고, 테스트마다 가상환경을 새로 만들어 더 느리다. 명령줄 인자 전달, 산출물이 git에 잡히지 않는 것, 모듈 연결처럼 just를 거쳐야 보이는 것만 거기서 확인한다.

### 스크립트 검사(`test_onto_validate.py`)

`validate`의 보고는 문제 하나에 한 줄이고, 탭으로 나눈 다섯 칸이다: 심각도(`오류`/`경고`), 지식 저장소, 페이지(루트 저장소 기준 파일 경로), 검사 항목(이름), 설명. 파일 안의 `validate(onto_cli, root)`가 종료 코드와 이 다섯 칸의 목록을 주고, `found`는 설명을 뺀 앞 네 칸만 준다. 문제가 없는 견본(`clean_repos()`)에서는 출력이 비어야 한다.

검사 항목마다 통과하는 견본과 걸리는 견본이 한 쌍씩 있다. 검사 항목의 이름은 `onto/onto_tool/checks/catalog.py`에, 기본 심각도와 켬/끔은 루트 기본 규칙 `onto/rules.yaml`에 있고, 구조 제약(필수 속성, 값의 종류, 허용되는 클래스, 관계의 도메인과 범위)은 `onto/vocab/shapes.ttl`에 있다. 새 검사 항목을 더하면 카탈로그, `onto/rules.yaml`의 `checks`, 이 파일에 쌍을 더한다(규칙 파일에 빠지면 도구가 멈춘다).

### 규칙(`test_onto_rules.py`)

루트 기본 규칙(`onto/rules.yaml`)은 도구 사본 안의 파일이고 테스트 세션이 공유한다. `onto_cli.set_root_check(이름, enabled=…, severity=…)`와 `onto_cli.replace_in_root_rules(옛, 새)`가 그 파일을 고치고, 테스트가 끝나면 `onto_cli`가 원래대로 되돌린다. 지식 저장소의 덮어쓰기는 `repo("billing", …, rules={"checks": {"orphan-page": {"enabled": False}}})`처럼 `ontology.yaml`의 `rules`로 적는다. `rules` 명령(`onto_cli.run(root, "rules", "billing")`)이 적용되는 규칙을 JSON으로 보여 주므로, 검사에 쓰이지 않는 값(`sources`, `push-gate`, `language`의 일부)의 병합도 여기서 확인한다.

### 인덱스(`test_onto_index.py`)

`build`가 지식 저장소의 `docs/ontology/index.md`를 만들고 `validate`가 없거나 어긋난 인덱스(`index-mismatch`)를 잡는 것을 `onto_cli`로 본다. 기대하는 인덱스는 손으로 적은 글자다. 인덱스를 만드는 코드로 기대값을 만들지 않는다. 인덱스가 git에 잡히는지(커밋되는 파일인지)와 전체 인덱스(`onto/.build/index.md`)가 잡히지 않는지는 `just`를 거쳐야 보이므로 `test_onto_just.py`가 본다.

지식 저장소는 인덱스가 있어야 스크립트 검사를 통과한다(없는 것도 `index-mismatch`다). 그래서 `onto_cli.root()`는 기본으로 견본을 쓴 뒤 `build`를 한 번 실행해 인덱스를 갖춘다(읽을 수 없는 파일이 든 견본은 `build`가 멈춰 인덱스 없이 남는다). 다른 검사 항목의 테스트에 인덱스 문제가 끼지 않게 하는 약속이다. 인덱스가 없는 견본이 필요하면 `onto_cli.root(repos, indexed=False)`로 만든다. `build`가 인덱스를 새로 만드는지 보는 테스트(`test_onto_index.py`의 대부분, 작업 트리에 생기는 것을 비교하는 테스트)는 반드시 `indexed=False`여야 한다. 미리 만들어 둔 인덱스는 `build`가 쓰지 않아도 같은 글자라 아무것도 확인하지 못한다.

`just`를 거치는 테스트(`test_onto_just.py`)의 견본은 `sandbox.knowledge_remote`가 만든 저장소라 이 받침이 닿지 않는다. 인덱스가 있어야 하면 `just onto build`를 먼저 실행한다.

### 원본 문서와 낡음(`test_onto_sources.py`, `test_onto_status.py`)

페이지의 `derivedFrom`은 `{path, hash}` 항목(또는 그 목록)이다. `path`는 지식 저장소 루트 기준 원본 문서의 경로, `hash`는 그 문서의 git 해시(git이 기록하는 blob 해시, 40자리 소문자 16진수)다. 넘긴 문서의 목록(`docs/ontology/skipped.yaml`)은 같은 모양의 항목의 목록이다. 지식 저장소가 git 작업 트리이면 도구가 `git hash-object --stdin-paths`로 해시를 내므로(`.gitattributes`와 `core.autocrlf` 적용), 저장소의 blob에 CRLF가 들어 있지 않은 문서는 깨끗한 클론의 `git rev-parse HEAD:<경로>`와 같고 줄바꿈 변환 설정과 무관하다. 한계: 저장소의 blob에 이미 CRLF가 든 문서는 `core.autocrlf=true`나 `text=auto`가 있으면 CRLF를 LF로 바꿔 해시하므로 `git rev-parse`와 다르고(변환 설정이 없는 기기에서는 같아 기기마다 다를 수 있다), 이를 `test_저장소의_blob에_CRLF가_든_문서의_…`와 `test_CRLF로_커밋한_문서에_text_auto를_…`가 못 박는다. git 저장소가 아닌 견본 디렉토리에서는 파일 내용 그대로 blob 해시를 낸다. 테스트가 기대하는 해시는 도구의 계산이 아니라 git이 낸 값이다: `git hash-object`(견본 루트를 만들기 전에 임시 파일로 구한다)와 `git rev-parse HEAD:<경로>`. 줄바꿈 변환을 다루는 테스트는 `git init`과 커밋으로 만든 원본 저장소를 `git clone -c core.autocrlf=true`로 클론한다.

- `test_onto_sources.py`: `derivedFrom`이 그래프의 `Source` 엔티티(`onto:sourcePath`, `onto:sourceHash`)와 `onto:derivedFrom` 관계로 나타나는 것, 값의 모양(온톨로지 층 안을 가리키는 `path`는 값의 종류 오류), 낡음(`stale-page`, 경고)·없어진 원본 문서(`missing-source`, 경고)·없어진 넘긴 문서(`missing-skipped-source`, 경고) 검사, git 저장소에서의 해시(줄바꿈 변환과 CRLF가 든 blob의 한계, 환경 변수, 아무것도 고치지 않는 것, git 실패 시 대체), 경로 대조(대소문자, 유니코드 정규화, 심볼릭 링크).
- `test_onto_status.py`: `status`가 새 문서와 바뀐 문서를 지식 저장소별로 보여 주는 것(보고는 문서 하나에 탭 다섯 칸), 넘긴 문서(페이지가 지금 내용을 근거로 삼았으면 넘긴 목록의 옛 항목은 무시), 대상 범위(규칙의 글롭과 제외 경로, 온톨로지 층·숨김 경로·심볼릭 링크는 항상 제외), 아무 파일도 고치지 않는 것, 깨진 `rules`를 기본값으로 대신하지 않는 것. `just onto status`는 마지막 테스트 하나만 거친다.
- 읽을 수 없는 파일의 문제로 `build`·`query`·`status`가 멈추는 조건(그 항목이 오류일 때만)과 `validate`와의 동치는 `test_onto_rules.py`의 `test_validate가_0으로_끝나면…`이 확인한다.

### 최신화(`test_onto_sync.py`)

`just onto sync [이름]`은 루트 저장소의 `onto/`를 지식 저장소의 `.onto/`로 복사한다. 루트 저장소(`sandbox.root()`)에 지식 저장소를 서브모듈로 붙이고(`root.register(sandbox.knowledge_remote(…))`) `sandbox.just("onto", "sync", …, cwd=root.work)`를 부르는 가장 높은 이음매에서 본다. 이 저장소의 `Justfile`을 직접 가리키지 않는다.

- 테스트는 루트의 기능을 `root.work / "onto"`에서 고쳐 시험한다. 복사하는 것은 루트가 **추적하는** `onto/` 파일이라, 새 파일은 `git add`해야 복사된다(없어진 파일은 `git rm`하거나 작업 트리에서 지운다).
- `.onto/.sync-record.json`은 마지막 최신화가 파일마다 쓴 내용의 기록이고, 손으로 고친 파일을 가려내는 데 쓴다. 루트에서 온 파일이 아니라 `copied`에서 뺀다.
- 다시 쓰지 않았는지는 수정 시각으로 본다. 파일의 시각을 `os.utime`으로 먼 과거로 돌려 두고 다시 실행해 시각이 그대로인지 비교한다.
- 지식 저장소 안에서 `just -f .onto/Justfile …`을 부르면 도구가 `.onto/` 안에 가상환경과 `__pycache__`를 만든다. 작업 트리를 앞뒤로 비교하는 테스트는 이를 빼고 비교한다.
- `.onto/.sync-record.json`을 손으로 꾸며(`.onto/` 밖이나 `..`, 절대 경로가 든 기록) 기록이 저장소 밖의 파일을 지우지 못하는 것을 본다. 최신화의 인덱스 생성 기준은 `build`와 같다(규칙에서 오류인 읽기 문제가 있을 때만 못 만든다).
- 출력의 순서는 `sh -c 'just … 2>&1'`로 두 출력을 한 파이프에 모아 본다. 두 파이프로 따로 받으면 순서를 알 수 없다.
- `just repo add`가 등록 직후 최신화를 자동으로 실행하는 것은 `test_repo_add.py`가 본다. 그래서 등록하면 지식 저장소에 미커밋 파일(`.gitignore`, `docs/ontology/`)이 생기고, 방금 등록한 저장소를 바로 떼려면 `repo remove --force`가 필요하다(`test_repo_remove.py`).

### 지식 저장소 안에서의 실행(`test_onto_within_repository.py`, `test_onto_repository_just.py`)

루트 저장소에 붙은 지식 저장소 안에서 `just -f .onto/Justfile build|validate|query|status`를 실행하면 그 저장소의 지식만 다룬다. 두 이음매로 나눠 본다.

- `test_onto_repository_just.py`(가장 높은 이음매): 루트 저장소(`sandbox.root()`)에 지식 저장소를 `just repo add`로 붙이고(등록하면 최신화가 `.onto/`를 복사한다) 그 안에서 복사된 `Justfile`을 직접 가리켜 실행한다. Justfile이 있는 디렉토리의 이름(`.onto`인지 `onto`인지)으로 어디 안에서 도는지를 가려 도구에 넘기는 연결(`-f .onto/Justfile`, 지식 저장소의 팀 `Justfile`이 `mod onto '.onto/Justfile'`이나 `import '.onto/Justfile'`로 부르는 경우, 루트에서 `just -f onto/Justfile`로 직접 가리키는 경우), `-d`로 실행 위치를 바꾸거나 `import`로 실행 위치가 저장소의 상위 디렉토리가 되어도 도구가 `.onto/`의 위를 그 저장소로 보는 것(루트 저장소에서 `-f onto/Justfile -d …`로 바꿔도 `Justfile`이 먼저 루트 저장소로 옮겨 가 모든 지식 저장소를 합쳐 다룬다), 도구가 있는 곳(`onto/`인지 `.onto/`인지)과 받은 범위가 맞지 않으면 바른 명령을 알리며 거부하는 것, 저장소의 하위 디렉토리에서 불러도 그 저장소가 기준인 것, 루트와 같은 파일을 쓰는 것, 루트 저장소의 실행 결과가 그대로인 것, 지식 저장소의 `Justfile`을 만들거나 고치지 않는 것을 본다. 지식 저장소 안에서 `just -f .onto/Justfile …`을 부르면 `.onto/` 안에 가상환경과 산출물이 생기므로 작업 트리를 비교하는 테스트는 이를 빼고 비교한다.
- `test_onto_within_repository.py`(도구의 명령줄 진입점): 지식 저장소 하나의 견본(`onto_cli.repository`)을 `--within repository`로 실행한다. 경로가 저장소 기준인 것, 교차 참조(다른 저장소를 가리키는 `<저장소>:<식별자>`)와 여러 저장소에 걸친 검사를 건너뛰고 건너뛰었다고 알리는 것, 같은 저장소 안의 참조는 검사하는 것, 읽을 수 없는 파일의 규칙, `status`·`rules`·`sync`, 루트 저장소와 다른 지식 저장소를 읽지 않는 것을 본다.

`checks.catalog`의 검사 항목은 `across_repositories=True`로 여러 저장소에 걸친 항목을 표시한다(교차 참조 `unregistered-repository`, 저장소 간 중복, `name` 겹침, 공유 범위 `scope-violation`, 다른 저장소에서 들어오는 참조에 따라 결과가 달라지는 `orphan-page`). 지식 저장소 안의 `validate`는 이 항목들을 돌리지 않는다. 한 저장소만 보고 판단할 수 있는 루트 전용 항목(`invalid-scope`, `path-reference`, `outside-link`)은 지식 저장소 안에서도 돈다.

### 템플릿과 규약 문서(`test_onto_templates.py`)

`onto/template/`의 견본과 규약 문서가 보여 주는 예는 도구에 돌려 확인한다(`onto_cli`). 견본의 키(`derivedFrom` 포함)가 모두 그 클래스의 페이지가 쓸 수 있는 것인지, 규약 문서의 페이지 예와 하위 클래스 선언이 받아들여지는지를 스크립트 검사가 판단한다. 견본을 더하거나 고치면 이 테스트가 걸러 낸다. 예의 근거 문서는 테스트가 만들고 해시는 git의 정의(`sha1("blob <바이트 수>\0" + 내용)`)로 계산해 자리표시 해시를 바꿔 넣는다. 규약 문서가 해시를 구하는 법(`status`의 값을 옮겨 적는다, 해시는 따옴표로 감싼다)은 글자로 확인한다.

### 공유 범위(`test_onto_scope.py`)

공유 범위 검사 항목 넷(`invalid-scope`, `scope-violation`, `path-reference`, `outside-link`)을 `onto_cli`로 본다. 모두 루트 전용이라 지식 저장소의 `rules`가 끄거나 심각도를 바꾸려 하면 `invalid-rules` 오류이고, 그래도 문제는 루트 기본 규칙의 심각도로 보고된다(이 파일이 항목마다 확인한다). 공유 범위는 `repo("billing", …, scope="team:payments")`처럼 `ontology.yaml`의 `scope`로 적는다. 적지 않은 지식 저장소는 `private`으로 본다.

- 값: `private`, `team`, `team:<팀 이름>`, `public`만 통과하고 나머지(대소문자, 공백, 빈 팀 이름, 문자열이 아닌 값)는 오류다.
- 교차 참조: 공유 범위 쌍마다 통과 여부를 표(`REFERENCES`)로 적었다. 더 넓은 범위로는 되고, 같은 범위끼리는 `private`과 `public`이면 되고 `team`이면 같은 팀(`team`과 `team`, 같은 `team:<팀 이름>`)만 된다. 가리키는 엔티티가 없어도 저장소 이름이 드러나므로 잡는다. 저장소는 `name`으로도 서브모듈 디렉토리 이름으로도 가리킬 수 있고 둘 다 본다. 범위를 알 수 없는 저장소(층이 없다, `ontology.yaml`을 읽을 수 없다, `scope` 값이 틀렸다)는 `private`으로 보고 비교한다. 이 경우마다 덮어쓸 수 있는 항목(`broken-reference`, `repository-name-mismatch` 등)을 저장소 규칙으로 꺼도 `scope-violation`이 남는지 본다.
- 파일 경로: 관계의 값이 식별자도 교차 참조도 아니면 `path-reference`만 보고하고 `broken-reference`나 `unregistered-repository`로 다시 보고하지 않는다. 절대 경로, `file:` 주소, `..` 조각, 확장자로 끝나는 경로, 첫 조각이 클래스 디렉토리가 아닌 값(`docs/ontology/plan/x`, `projects/<저장소>/…`, 오타)이 그렇다. 이 값들도 끌 수 있는 항목을 꺼 두고 확인한다.
- 본문의 링크: 인라인 링크, 이미지, 참조 정의, 자동 링크, HTML `href`·`src`(따옴표 없는 것 포함)가 저장소 밖의 파일(절대 경로, `file:` 주소, 저장소 루트 위로 나가는 상대 경로, 역슬래시 경로)을 가리키면 `outside-link`다. 코드 블록(목록 안에서 들여쓴 것 포함)과 인라인 코드와 HTML 주석 안, HTML 태그 밖의 평문 `src=…`, `http` 같은 주소, 저장소 안의 경로는 잡지 않는다. 인라인 코드와 주석은 먼저 시작하는 쪽이 이기고(코드 안의 `<!--`는 주석을 열지 않는다), 울타리의 닫는 줄은 여는 줄보다 3칸까지만 더 들여쓸 수 있으며 4칸 이상 들여써 연 울타리가 닫히지 않으면 울타리로 보지 않는다. 견본 페이지가 `docs/ontology/component/` 아래에 있어 `../`를 세 번 오르면 저장소의 루트, 네 번 오르면 저장소 밖이다. `<저장소 이름>:<식별자>` 모양의 링크 대상은 관계의 값과 같이 공유 범위를 따진다(`scope-violation`). `class`의 값에 적은 `<저장소 이름>:<나머지>`도 같다(`disallowed-class`를 꺼도 남는다). 정의되지 않은 키(`undefined-key`)의 값과 값의 종류가 틀린 관계의 값(`invalid-value`)에 든 교차 참조 모양도 중첩까지 훑어 같다(그 항목들을 꺼도 남는다). 제목·설명·별칭·본문 평문에 적힌 저장소 이름은 검사하지 않는다.
- 심볼릭 링크 페이지: 페이지 파일이 다른 저장소의 파일을 가리키는 심볼릭 링크이면 읽지 않고 `outside-link` 오류로 알린다(`build`도 멈춘다). 링크의 내용(비공개 제목)은 출력과 인덱스에 나오지 않는다. 가리키는 파일이 없는 깨진 링크도 저장소 밖을 가리키면 같은 오류이고(링크 파일 자체가 대상을 담는다), 저장소 안을 가리키면 알리지 않는다. 링크는 `onto_cli.root()`가 만든 뒤 테스트가 만든다.

### 푸시 관문(`test_git_push_gate.py`)

`just git push`가 푸시 전에 스크립트 검사(`just onto validate`)를 돌리고 오류가 있으면 아무것도 올리지 않는 것을 가장 높은 이음매에서 본다. 루트 저장소(`sandbox.root()`)에 지식 저장소를 서브모듈로 붙이고 클론에서 `sandbox.just("git", "push", …)`를 부른다. 관문은 루트 저장소의 도구로 작업 트리를 검사하므로 지식 저장소는 온톨로지 층(페이지와 인덱스)을 갖춰야 통과한다. 파일의 `_attach`가 `just onto build`로 인덱스를 만들어 지식 저장소에 커밋하고 루트가 그 커밋을 가리키게 한다.

- 켜진 관문은 푸시마다 스크립트 검사(컴파일과 구조 제약 검사)를 돌려 시간이 들고, 온톨로지 층이 없는 견본은 검사에 막힌다. 관문과 상관없는 푸시 테스트(`test_git_push.py`)는 `sandbox.root(push_gate=False)`로 루트 기본 규칙의 관문을 끈 채 시작한다. 꺼 둬도 푸시는 꺼졌는지를 `onto rules`로 읽으므로 도구의 가상환경은 만들어지고, 아끼는 것은 검사 한 번이다. 순서와 중단 조건이 같다는 약속은 거기서 확인되고, 관문을 강제로 넘겼을 때도 같다는 것은 이 파일이 확인한다.
- 오류가 있는 견본은 없는 엔티티를 가리키는 관계(`broken-reference`), 경고만 있는 견본은 고아 페이지(`orphan-page`)다.
- 막히면 요약(`== 요약 ==`) 없이 종료 코드 1이고, 걸린 문제는 표준 출력에 `validate`와 같은 탭 다섯 칸으로 나온다. 어떤 저장소도 올라가지 않고 커밋이나 스테이징도 없다(`snapshot`으로 앞뒤를 비교한다).
- 강제 옵션(`--force`, `-f`)은 오류를 넘기고, 넘겼다는 사실을 푸시 전과 요약 뒤에 알린다. git의 강제 푸시가 아니라서 원격이 앞서 있으면 그대로 거부된다. 모르는 인자(오타 포함)는 아무것도 하기 전에 거부한다.
- 루트 기본 규칙의 `push-gate`로 끄고, 지식 저장소의 `rules`로는 끌 수 없다(`invalid-rules` 오류로 막힌다). 루트 기본 규칙을 읽을 수 없으면 켜진 것으로 보고 막는다.
- `-d`로 실행 위치를 바꾸거나 하위 디렉토리에서 불러도 루트 저장소를 검사한다.
