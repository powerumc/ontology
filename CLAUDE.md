## 온톨로지

이 저장소는 루트 저장소다. 기능(`onto/`, `git/`, `repo/`)만 담고 지식은 담지 않는다. 지식은 `projects/` 아래의 지식 저장소에 있다(이유는 `docs/adr/0001`).

- 지식을 ingest, 질의, 점검할 때는 스킬 `onto-ingest`, `onto-query`, `onto-lint`를 쓴다(`.claude/skills/`).
- 명령은 `just`다. `just`, `just onto`, `just git`, `just repo`가 명령 목록을 보여 주고, 사용법은 `README.md`에 있다.

## Agent skills

### Issue tracker

이슈와 스펙은 GitHub 이슈로 관리한다. `gh` CLI를 쓴다. `docs/agents/issue-tracker.md` 참고.

### Triage labels

다섯 가지 표준 트리아지 역할의 기본 라벨 문자열을 그대로 쓴다. `docs/agents/triage-labels.md` 참고.

### Domain docs

단일 컨텍스트 구성이다. 루트의 `GLOSSARY.md`와 `docs/adr/`를 쓰며, 문서는 한국어로 쓴다. `docs/agents/domain.md` 참고.

### Subagent routing

메인 세션(Opus, high)은 컨트롤러다. 직접 구현하지 않고, 단계마다 아래 서브에이전트에 맡긴다. 정의는 `.claude/agents/`에 있고, 이름은 `역할-모델-노력` 형식이다.

| 단계 | 서브에이전트 |
|---|---|
| 최초 스펙·계획 작성 | `spec-author-fable-xhigh` |
| 세부 계획(태스크 분해) | `planner-opus-xhigh` |
| 구현 | `implementer-sonnet-xhigh` |
| 태스크 리뷰·재리뷰 | `reviewer-opus-xhigh` |
| 리뷰 지적 수정 | `implementer-sonnet-xhigh` |
| 스펙 최종 리뷰 | `spec-reviewer-fable-xhigh` |

- 서브에이전트는 다른 서브에이전트를 부르지 못한다. 단계 사이 연결은 컨트롤러가 한다.
- 디스패치 프롬프트에는 읽을 파일, 할 일, 결과를 쓸 위치를 모두 담는다. 서브에이전트는 대화 맥락을 모른다.
- 리뷰 결과의 수정은 리뷰어가 아니라 `implementer-sonnet-xhigh`에 맡기고, 수정 뒤 `reviewer-opus-xhigh`로 재리뷰한다.
- 사용자 레벨(`~/.claude/agents`)의 `sonnet-xhigh`, `opus-xhigh`, `opus-max`는 이 프로젝트에서 쓰지 않는다.
