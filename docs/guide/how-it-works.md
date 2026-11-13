# 동작 방식

이 도구가 지식을 어디에 두고 어떻게 다루는지 설명합니다. 용어의 정확한 뜻은 [용어집](../../GLOSSARY.md)에, 결정의 이유는 [ADR](../adr/)에 있습니다.

## 루트 저장소와 지식 저장소

이 저장소가 **루트 저장소**입니다. 도구, 공통 어휘, 규칙, 템플릿 같은 기능만 갖고 지식은 담지 않습니다([ADR 0001](../adr/0001-root-provides-function-only.md)).

지식은 **지식 저장소**에 있습니다. 지식 저장소는 git 서브모듈로 루트 저장소의 `projects/<이름>/`에 붙고, 지식 저장소 하나가 온톨로지 모듈 하나입니다. 루트 저장소에서는 붙인 지식 저장소 전체를, 지식 저장소 안에서는 그 저장소의 지식만 다룹니다.

누구나 이 저장소를 받아 `origin`을 자기 원격으로 바꿔 씁니다. 공개 원본에는 어떤 지식 저장소도 등록하지 않습니다([ADR 0007](../adr/0007-take-the-root-and-change-its-remote.md)).

## 원본 문서와 온톨로지 층

지식 저장소에 이미 있는 계획, 정책·정의, 구현 결과 문서가 **원본 문서**입니다. LLM 에이전트가 원본 문서를 읽어 `docs/ontology/`에 페이지를 쓰고(ingest), 사람은 `git diff`로 검토합니다. 원본 문서는 고치지 않습니다([ADR 0004](../adr/0004-ontology-layer-separate-from-source-documents.md)).

페이지는 마크다운과 YAML frontmatter로 씁니다. 도구는 이를 RDF 그래프로 컴파일해 SPARQL 질의, 구조 제약 검사(SHACL), 가벼운 추론(하위 클래스, 역관계, 추이 관계)에 씁니다([ADR 0002](../adr/0002-formal-ontology-authored-in-frontmatter.md)). 엔티티의 식별자는 지식 저장소 안의 페이지 경로입니다([ADR 0003](../adr/0003-path-based-identifiers.md)). 페이지를 쓰는 법은 [온톨로지 층 규약](../../onto/template/conventions.md)에 있습니다.

## 최신화: 기능을 지식 저장소에 복사하기

지식 저장소에는 온톨로지 기능이 들어 있지 않습니다. 붙일 때 루트 저장소가 기능을 복사해 주며, 이렇게 복사된 `.onto/`와 에이전트 스킬을 **루트 관리 파일**, 복사하는 일을 **최신화**라고 합니다([ADR 0005](../adr/0005-root-managed-files-copied-into-knowledge-repos.md)). 최신화는 지식 저장소의 작업 트리만 바꾸고 커밋하지 않습니다. 무엇을 커밋할지는 사람이 정합니다.

| 최신화가 하는 일 | 지식 저장소의 위치 | 커밋 |
|---|---|---|
| 루트 저장소의 `onto/`(코드, 공통 어휘, 규칙, 템플릿, 규약 문서)를 복사 | `.onto/` | 하지 않음 |
| 에이전트 스킬 `.claude/skills/onto-*/`를 복사 | 같은 위치 | 하지 않음 |
| 루트 관리 파일을 제외하는 표시된 블록을 써 넣음 | `.gitignore` | 사람이 커밋함 |
| 온톨로지 층의 인덱스를 안내하는 표시된 블록을 써 넣음 | 프로젝트 지침 파일(`CLAUDE.md`, 없으면 `AGENTS.md`) | 사람이 커밋함 |

루트 관리 파일은 `.gitignore`로 제외되므로 지식 저장소의 이력에 도구가 쌓이지 않습니다. 지침 파일의 블록 밖은 건드리지 않으며, 블록은 복사된 기능이 없는 클론에서도 뜻이 통하도록 씁니다. 그래서 생성물인 인덱스는 지식 저장소에 커밋합니다. 지식 저장소만 따로 클론한 사람에게는 인덱스가 유일한 진입점이기 때문입니다([ADR 0006](../adr/0006-generated-index-is-committed.md)).

공통 어휘는 semver로 버전을 관리합니다. 지식 저장소의 루트 관리 파일이 뒤처졌는지는 버전이 아니라 내용으로 판단하므로, 버전 번호를 올리지 않은 수정도 `just onto validate`가 경고합니다. 언제 어떻게 최신화하는지는 [최신화](sync.md)에 있습니다.

## 디렉토리 구조

```
(루트 저장소)
├── Justfile                  # setup과 모듈 선언
├── git/  repo/  onto/        # just 모듈. onto/는 지식 저장소에 복사하는 기능이기도 함
├── .claude/skills/           # 에이전트 스킬 onto-ingest, onto-query, onto-lint
├── CLAUDE.md                 # 짧은 안내
└── projects/<저장소명>/       # 지식 저장소 (서브모듈)
    ├── .onto/                # 루트 저장소의 onto/를 복사한 것. 커밋하지 않음
    ├── .claude/skills/onto-*/ # 복사된 스킬. 커밋하지 않음
    └── docs/ontology/        # 이 저장소의 지식. 커밋함
        ├── ontology.yaml     # 저장소 이름, 공유 범위, 프로젝트의 의존, 규칙 덮어쓰기
        ├── index.md          # 진입점 (생성물)
        ├── skipped.yaml      # 읽고도 기록할 것이 없던 원본 문서의 목록 (필요할 때 생김)
        └── plan/ policy/ term/ decision/ report/ component/
```
