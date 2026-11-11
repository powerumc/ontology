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

- `sandbox.root()`: 루트 저장소와 bare 원격. `.register(원격, name=, branch=)`, `.point_at(이름, 커밋)`, `.clone()`
- `sandbox.knowledge_remote(이름)`: 가짜 지식 저장소와 bare 원격. `.commit(branch=)`, `.set_default_branch(브랜치)`
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
- `repo(이름, 페이지…)`, `page(식별자, 클래스, 제목=…, partOf=[…])`, `ontology_yaml(이름, …)`: 견본 파일을 만든다. 값은 JSON으로 적어 YAML이 된다. `repo`의 키워드 인자는 `ontology.yaml`의 키가 된다(예: `repo("billing", title="결제", classes={"Invoice": {"subClassOf": "Component"}})`). 다른 지식 저장소의 엔티티는 `partOf=["shop:component/api"]`처럼 `<저장소 이름>:<식별자>`로 가리킨다.
- 도구는 이 저장소의 추적 `onto/` 파일의 사본에서 돈다. 가상환경은 테스트 세션마다 한 번 만든다. 의존성을 처음 내려받을 때만 네트워크가 필요하다.
- `onto_cli.query`와 `build`가 보는 그래프는 추론(하위 클래스, 역관계, 추이 관계)이 끝난 것이다. 정렬하지 않은 질의의 행 순서는 rdflib이 정하고 실행마다 다를 수 있으니, 행의 순서를 비교하는 테스트는 `ORDER BY`를 쓴다.
- 도구는 산출물(컴파일한 그래프)을 자기 디렉토리의 `.build/`에 둔다. 도구 사본은 테스트 세션이 공유하므로 `onto_cli`가 테스트마다 비운다. `onto_cli.build(root)`가 그래프 파일의 내용을, `onto_cli.graph_file`이 그 위치를 준다. 견본 루트에는 아무것도 생기지 않아야 하고, `snapshot(root)`로 앞뒤를 비교한다.
- 같은 도구를 `just onto …`로 부르는 테스트(`test_onto_just.py`)는 서브모듈로 붙인 지식 저장소를 상대로 하고, 테스트마다 가상환경을 새로 만들어 더 느리다. 명령줄 인자 전달, 산출물이 git에 잡히지 않는 것, 모듈 연결처럼 just를 거쳐야 보이는 것만 거기서 확인한다.
