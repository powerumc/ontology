# 이슈 트래커: GitHub

이 저장소의 이슈와 스펙은 GitHub 이슈로 관리한다. 모든 작업에 `gh` CLI를 쓴다.

## 규약

- **이슈 만들기**: `gh issue create --title "..." --body "..."`. 본문이 여러 줄이면 heredoc을 쓴다.
- **이슈 읽기**: `gh issue view <number> --json number,title,body,labels,comments`.
- **이슈 목록**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`. 필요에 따라 `--label`과 `--state`로 거른다.
- **부모 이슈의 하위 이슈로 만들기**: `gh issue create --parent <parent> ...`, 또는 나중에 `gh issue edit <parent> --add-sub-issue <child>` (`gh` 2.94 이상). 이전 버전의 `gh`: `gh api --method POST repos/<owner>/<repo>/issues/<parent>/sub_issues -F sub_issue_id=<child-db-id>` (아래 **차단**과 같은 데이터베이스 id). 하위 이슈를 쓸 수 없으면 자식 본문 맨 위에 `Part of #<parent>`를 적는다.
- **댓글 달기**: `gh issue comment <number> --body "..."`
- **라벨 붙이기 / 떼기**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **닫기**: `gh issue close <number> --comment "..."`
- **수용 기준 체크**: 티켓을 닫기 전에 본문 `## Acceptance criteria`의 항목을 하나씩 실제 충족 여부와 맞춰 갱신한다. 구현과 테스트(또는 리뷰의 대조)로 확인한 항목만 `- [x]`로 바꾸고, 충족하지 못했거나 확인하지 못한 항목은 `- [ ]`로 둔다. 체크하지 않은 항목이 있으면 닫는 댓글에 항목과 이유, 후속 이슈 번호를 적는다. 갱신은 본문을 받아(`gh issue view <n> --json body --jq .body`) 그 절의 체크박스만 고친 뒤 `gh issue edit <n> --body-file <파일>`로 올리고, 다른 절은 건드리지 않는다.
- 이슈의 제목과 본문은 한국어로 쓴다. 라벨은 영어 그대로 둔다.

## 제목 규약

스펙과 티켓의 관계가 제목만 봐도 드러나게, 제목 앞에 번호 접두어를 붙인다. 접두어 뒤의 이름은 용어집 어휘로 짓는다.

| 종류 | 제목 형식 | 라벨 | 예 |
|---|---|---|---|
| 스펙 | `[S<n>] 스펙: <이름>` | `spec`, `ready-for-agent` | `[S1] 스펙: 온톨로지 루트 저장소 기반 구축` |
| 티켓 | `[S<n>-<NN>] <이름>` | `ready-for-agent` | `[S1-02] 지식 저장소 등록과 제거` |

- **스펙 번호 `<n>`**: `spec` 라벨이 붙은 이슈 수(닫힌 것 포함)에 1을 더한다. `gh issue list --label spec --state all --json number --jq length`. 스펙을 닫거나 버려도 번호는 다시 쓰지 않는다.
- **티켓 순번 `<NN>`**: 스펙 안에서 두 자리로, 차단하는 티켓부터 `01`로 매긴다. 순서의 힌트일 뿐이고, 실제 순서는 이슈 의존성이 정한다.
- 나중에 티켓을 더하면 그 스펙의 마지막 순번 다음을 쓴다. 기존 순번은 다시 매기지 않는다.
- 접두어는 관계를 보여 줄 뿐이다. 부모 관계는 하위 이슈로, 차단은 이슈 의존성으로 그대로 건다.
- 스펙 이슈를 만들 때 `spec` 라벨을 함께 붙인다: `gh issue create --title "[S<n>] 스펙: …" --label spec --label ready-for-agent …`.

저장소는 `git remote -v`에서 추론한다. 클론 안에서 실행하면 `gh`가 자동으로 그렇게 한다.

## 풀 리퀘스트를 트리아지 대상으로 삼기

**PRs as a request surface: no.** _(외부 PR을 기능 요청으로 다루는 저장소라면 `yes`로 바꾼다. `/triage`가 이 표시를 읽는다.)_

`yes`일 때는 PR도 이슈와 같은 라벨과 상태를 거치며, `gh pr` 명령을 쓴다:

- **PR 읽기**: `gh pr view <number> --comments`, diff는 `gh pr diff <number>`.
- **트리아지할 외부 PR 목록**: `gh api --paginate 'repos/{owner}/{repo}/pulls?state=open' --jq '.[] | select(.author_association | IN("OWNER","MEMBER","COLLABORATOR") | not) | {number, title, author: .user.login, author_association, labels: [.labels[].name]}'`.
- **댓글 / 라벨 / 닫기**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub는 이슈와 PR이 번호 공간을 함께 쓰므로 `#42`만으로는 어느 쪽인지 알 수 없다. `gh pr view 42`로 확인하고, 아니면 `gh issue view 42`로 넘어간다.

## 스킬이 "이슈 트래커에 게시하라"고 할 때

GitHub 이슈를 만든다.

## 스킬이 "관련 티켓을 가져오라"고 할 때

위의 **이슈 읽기**대로 읽는다.

## 웨이파인딩 작업

`/wayfinder`가 쓴다. **맵**은 이슈 하나이고, 티켓은 그 **자식** 이슈다.

- **맵**: `wayfinder:map` 라벨이 붙은 이슈 하나. Notes / Decisions-so-far / Fog 본문을 담는다. `gh issue create --label wayfinder:map`.
- **자식 티켓**: 맵에 GitHub 하위 이슈로 연결된 이슈(**부모 이슈의 하위 이슈로 만들기** 참고). 하위 이슈를 쓸 수 없으면 맵 본문의 작업 목록에 자식을 넣고, 자식 본문 맨 위에 `Part of #<map>`를 적는다. 라벨: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). 맡은 뒤에는 진행하는 개발자에게 할당된다.
- **차단**: GitHub의 **이슈 의존성**을 쓴다. UI에 보이는 표준 표현이다. `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`로 연결한다. `<blocker-db-id>`는 차단하는 이슈의 숫자 **데이터베이스 id**다(`gh api repos/<owner>/<repo>/issues/<n> --jq .id`. `#number`나 `node_id`가 _아니다_). GitHub는 `issue_dependencies_summary.blocked_by`로 열려 있는 차단 이슈만 알려 준다. 의존성을 쓸 수 없으면 자식 본문 맨 위의 `Blocked by: #<n>, #<n>` 줄로 대신한다. 차단하는 이슈가 모두 닫히면 차단이 풀린다.
- **프런티어 조회**: 맵의 열린 자식을 나열하고(`gh issue list --state open`, 맵의 하위 이슈나 작업 목록으로 한정), 열린 차단 이슈가 있거나(`issue_dependencies_summary.blocked_by > 0`, 또는 `Blocked by` 줄에 열린 이슈) 담당자가 있는 것을 뺀다. 맵의 순서에서 첫 번째가 우선이다.
- **맡기**: `gh issue edit <n> --add-assignee @me`. 세션의 첫 쓰기다.
- **해결**: `gh issue comment <n> --body "<answer>"`, 이어서 `gh issue close <n>`, 그리고 맵의 Decisions-so-far에 맥락 포인터(요지 + 링크)를 덧붙인다.
