# ontology

저장소 하나를 모듈 하나로 삼는 **모듈형 온톨로지** 도구다. 여러 저장소에 흩어진 문서를 저장소마다 온톨로지로 정리하고, 하나로 합쳐 질의하고 검사한다. [Karpathy의 LLM Wiki 패턴](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)을 뼈대로 하고, 그 위에 RDF 온톨로지와 git 서브모듈 구조를 얹는다.

> **상태: 설계 단계.** 아직 구현되지 않았다. 아래의 구조와 명령은 계획이며, 진행 상황은 [스펙 이슈 #1](https://github.com/powerumc/ontology/issues/1)과 그 하위 이슈에서 볼 수 있다.

## 풀려는 문제

- 프로젝트마다 계획, 정책·정의, 구현 결과 문서가 제각각의 형식으로 흩어져 있다. LLM 에이전트는 필요한 지식을 찾을 때마다 원본 문서를 처음부터 읽어야 한다.
- 프로젝트 사이의 관계는 어디에도 기록되어 있지 않다.
- 전체를 한곳에서 질의하고 싶지만, 각 프로젝트 저장소 안에서는 그 저장소의 지식만 보여야 한다.

## 받아서 쓰기

이 저장소가 **루트 저장소**다. 받아서 자기 것으로 쓴다.

1. 이 저장소를 받는다.
2. `origin`을 자기 원격 저장소로 바꾼다.
3. 자기 프로젝트를 **지식 저장소**로 붙이고, 그 서브모듈 등록을 자기 루트 저장소에 커밋한다.

이 공개 원본에는 어떤 지식 저장소도 등록되어 있지 않다.

## 동작 방식

- 루트 저장소는 기능만 제공한다. 지식은 담지 않는다.
- 지식 저장소는 git 서브모듈로 루트 저장소의 `projects/` 아래에 붙는다. 지식 저장소 하나가 온톨로지 모듈 하나다.
- 지식 저장소에는 온톨로지 기능이 없다. 붙일 때 루트 저장소가 자기 `onto/`(코드, 공통 어휘, 규칙, 템플릿, 지침)를 지식 저장소의 `.onto/`로 복사한다.
- 복사된 기능은 지식 저장소의 `.gitignore`로 제외된다. 지식 저장소의 이력에는 `docs/ontology/`의 지식만 들어간다.
- 지식 저장소의 프로젝트 지침 파일(`CLAUDE.md`, 없으면 `AGENTS.md`)에는 최신화가 표시된 블록 하나를 넣어 온톨로지 층의 인덱스를 가리킨다. 블록 밖은 건드리지 않고, 복사된 기능이 없는 클론에서도 뜻이 통한다.
- 공통 어휘는 semver로 버전을 관리하고, 버전은 지식 저장소의 `.onto/vocab/onto.ttl`에 찍힌다. `just onto validate`는 `.onto/`가 루트의 `onto/`와 내용이 다른 지식 저장소를 경고한다(버전 번호를 올리지 않은 수정도 잡는다). `just onto sync`는 끝에 새 구조 제약에 어긋난 페이지를 보고한다.
- LLM 에이전트가 지식 저장소의 원본 문서를 읽어 온톨로지 층의 페이지를 쓰고, 사람은 git diff로 검토한다. 원본 문서는 고치지 않는다.
- 페이지는 마크다운과 YAML frontmatter로 쓴다. 이를 RDF 그래프로 컴파일해 SPARQL 질의, SHACL 구조 제약 검사, 가벼운 추론에 쓴다.
- 루트 저장소에서는 붙인 지식 저장소 전체를, 지식 저장소 안에서는 그 저장소의 지식만 다룬다.

```
(루트 저장소)
├── Justfile
├── git/  repo/  onto/        # just 모듈. onto/는 지식 저장소에 복사하는 기능이기도 함
├── .claude/skills/           # 에이전트 스킬
└── projects/<저장소명>/       # 지식 저장소 (서브모듈)
    ├── .onto/                # 루트 저장소의 onto/ 사본. 커밋하지 않음
    └── docs/ontology/        # 이 저장소의 지식. 커밋함
        ├── ontology.yaml     # 저장소 이름, 공유 범위, 규칙 덮어쓰기
        ├── index.md          # 진입점 (생성물)
        └── plan/ policy/ term/ decision/ report/ component/
```

## 계획된 명령

| 명령 | 동작 |
|---|---|
| `just setup` | 도구 확인, 서브모듈 초기화 |
| `just repo add <url> [이름] [브랜치]` | 지식 저장소를 붙이고 기능을 복사 |
| `just repo remove <이름>` | 지식 저장소를 완전히 제거 |
| `just git pull` | 모든 저장소의 최신 내용을 fast-forward로 받기 |
| `just git push` | 스크립트 검사 후 모든 저장소 푸시 |
| `just git status` | 저장소별 상태 요약 |
| `just onto sync [이름]` | 루트 저장소의 기능을 지식 저장소에 최신화 |
| `just onto build` | 그래프 컴파일과 인덱스 생성 |
| `just onto validate` | 스크립트 검사 |
| `just onto query` | SPARQL 질의 |
| `just onto status` | 새로 생겼거나 바뀐 원본 문서 목록 |

지식 저장소 안에서는 `just -f .onto/Justfile build`처럼 복사된 `Justfile`을 직접 가리켜 `build`, `validate`, `query`, `status`를 쓰고, 그때는 그 저장소만 다룬다. 루트의 `onto` 모듈과 같은 파일이고(`Justfile`이 있는 디렉토리의 이름으로 어디 안에서 도는지 가린다. 지식 저장소의 팀 `Justfile`이 `mod onto '.onto/Justfile'`이나 `import '.onto/Justfile'`로 불러도 같다), 저장소의 어느 디렉토리에서 불러도, `-d`로 실행 위치를 바꿔도 도구가 자기가 있는 `.onto/`의 위를 그 저장소로 본다. 보고하는 경로는 그 저장소 기준이며, `validate`는 교차 참조·공유 범위 위반·저장소 간 중복·고아 페이지처럼 여러 저장소에 걸친 검사를 건너뛰고 건너뛰었다고 알린다. `sync`는 루트 저장소에서만 쓸 수 있다. 어떤 명령도 자동으로 커밋하지 않는다.

## 문서

- [`GLOSSARY.md`](GLOSSARY.md): 이 프로젝트의 용어
- [`docs/adr/`](docs/adr/): 되돌리기 어려운 결정과 그 이유
- [스펙 이슈 #1](https://github.com/powerumc/ontology/issues/1): 사용자 스토리, 구현 결정, 테스트 결정
- [이슈 목록](https://github.com/powerumc/ontology/issues): 구현 티켓. 선행 관계는 이슈 의존성으로 걸려 있다
- [`docs/agents/`](docs/agents/): 에이전트 스킬이 읽는 이슈 트래커와 문서 규약

## 참고한 사례

- [Karpathy LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): 원본 소스, 위키, 스키마 파일의 3개 층과 ingest, query, lint의 3개 운영
- [LA3D/llm-wiki-colab](https://la3d.github.io/llm-wiki-colab/): 연합형 확장. OWL/SKOS 관계, JSON-LD context, SHACL
- [wazootech/wiki](https://github.com/wazootech/wiki): frontmatter를 RDF로 변환하고 소스별 named graph로 적재
