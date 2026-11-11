# 테스트 안내

## 실행

```sh
uv run pytest                      # 전체. 의존성을 처음 내려받을 때만 네트워크가 필요하다
uv run pytest tests/test_setup.py  # 파일 하나
uv run pytest -k 추적_브랜치        # 이름으로 고르기
```

## 새 파일은 `git add` 한 뒤에 테스트에 보인다

테스트용 루트 저장소는 이 저장소의 **추적 파일**(`git ls-files`)을 임시 디렉토리로 복사해 만든다. 새로 만든 파일(예: `onto/rules.yaml`)을 `git add`하지 않고 테스트를 돌리면 샌드박스 루트에 그 파일이 없어, 이유를 알기 어려운 실패가 난다. 온톨로지 도구(`onto/`)를 실행하는 테스트도 같다(아래). 서브모듈 등록(`.gitmodules`, gitlink)은 복사하지 않는다.

## 테스트 받침 (`tests/support/sandbox.py`)

`sandbox` 픽스처가 테스트마다 새 임시 디렉토리와 격리된 git 환경을 준다.

- `sandbox.root()`: 루트 저장소와 bare 원격. `.register(원격, name=, branch=)`, `.point_at(이름, 커밋)`, `.clone()`
- `sandbox.knowledge_remote(이름)`: 가짜 지식 저장소와 bare 원격. `.commit(branch=)`
- `sandbox.just(...)`, `sandbox.git(...)`: 명령 실행. `just(without=("uv",))`는 PATH에서 도구를 뺀다
- `sandbox.head(저장소)`, `sandbox.branch(저장소)`

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
- `repo(이름, 페이지…)`, `page(식별자, 클래스, 제목=…, partOf=[…])`, `ontology_yaml(이름, …)`: 견본 파일을 만든다. 값은 JSON으로 적어 YAML이 된다.
- 도구는 이 저장소의 추적 `onto/` 파일의 사본에서 돈다. 가상환경은 테스트 세션마다 한 번 만든다. 의존성을 처음 내려받을 때만 네트워크가 필요하다.
- 같은 도구를 `just onto …`로 부르는 테스트(`test_onto_just.py`)는 서브모듈로 붙인 지식 저장소를 상대로 하고, 테스트마다 가상환경을 새로 만들어 더 느리다. 명령줄 인자 전달, 산출물이 git에 잡히지 않는 것, 모듈 연결처럼 just를 거쳐야 보이는 것만 거기서 확인한다.
