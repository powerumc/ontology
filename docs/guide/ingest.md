# ingest: 원본 문서를 지식으로 정리하기

ingest는 원본 문서를 읽어 온톨로지 층의 페이지를 만들거나 고치는 일입니다. 에이전트가 하고 사람이 검토합니다. 요청할 때만 실행되고 자동으로 돌지 않습니다.

아래 예시는 지식 저장소 `billing`을 정리하는 경우입니다.

## 1. 대상 확인

```sh
just onto status
```

새로 생겼거나 바뀐 원본 문서가 표시됩니다. 에이전트에게 맡기면 다음 단계에서 에이전트가 이 확인부터 하므로 건너뛰어도 됩니다.

## 2. 에이전트에게 요청

스킬 `onto-ingest`로 지식 저장소 하나를 정리하도록 요청합니다. 스킬 이름 없이 하고 싶은 일을 말해도 됩니다.

| 하고 싶은 것 | 이렇게 말합니다 |
|---|---|
| 저장소 하나를 정리 | "billing을 onto-ingest로 정리해 줘" |
| 문서 하나만 반영 | "billing의 docs/design/payment.md를 온톨로지에 반영해 줘" |
| 새 문서를 반영 | "billing에 새로 생긴 설계 문서를 온톨로지에 반영해 줘" |

Claude Code에서는 `/onto-ingest billing`으로 바로 부를 수 있습니다. 대상을 말하지 않았는데 정리할 저장소가 여럿이면 에이전트가 어느 저장소를 정리할지 묻습니다.

에이전트는 다음 순서로 일합니다. 원본 문서는 고치지 않고 커밋도 하지 않습니다.

1. 원본 문서를 읽고, 같은 엔티티의 페이지가 이미 있는지 찾습니다. 있으면 새로 만들지 않고 그 페이지를 고칩니다.
2. 페이지를 쓰고, 페이지의 `derivedFrom`에 원본 문서의 경로와 해시를 기록합니다.
3. 기록할 것이 없는 문서는 `docs/ontology/skipped.yaml`에 적습니다.
4. `build`와 `validate`로 확인하고, 오류가 없을 때까지 페이지를 고칩니다.
5. 새 맥락의 서브에이전트가 쓰거나 고친 페이지를 원본과 대조해(대조 검토) 근거 없는 문장, 인용 누락, 모순을 보고하고, 에이전트가 그 내용을 고친 뒤 4번의 확인을 다시 합니다.

자세한 동작은 [`onto-ingest` 스킬](../../.claude/skills/onto-ingest/SKILL.md)에, 페이지를 쓰는 법은 [온톨로지 층 규약](../../onto/template/conventions.md)에 있습니다.

## 3. 검토

```sh
git -C projects/billing status
git -C projects/billing diff
```

## 4. 컴파일과 검사

```sh
just onto build
just onto validate
```

오류가 0개여야 합니다. 에이전트도 2단계에서 같은 확인을 하지만, 검토하면서 페이지를 고쳤다면 다시 돌립니다. 출력을 읽는 법은 [검사와 규칙](validate.md)에 있습니다.

## 5. 커밋과 푸시

지식 저장소에 먼저 커밋하고, 루트 저장소가 그 커밋을 가리키도록 커밋합니다.

```sh
git -C projects/billing add docs/ontology
git -C projects/billing commit -m "onto(ingest): 결제 설계 문서에서 게이트웨이와 용어 페이지 추가"
git add projects/billing
git commit -m "chore: billing 지식 갱신"
just git push
```

처음 ingest한다면 최신화가 만든 `.gitignore`와 프로젝트 지침 파일(`AGENTS.md`나 `CLAUDE.md`)도 함께 add합니다.

검토를 마친 뒤 커밋을 에이전트에게 따로 요청할 수도 있습니다. 스킬은 스스로 커밋하지 않고, ingest를 마치며 커밋 메시지만 제안합니다.

> 제안한 메시지로 billing에 커밋하고, 루트 저장소에도 커밋해 줘

## 원본 문서가 바뀌었을 때

원본 문서가 바뀌면 그 문서를 근거로 한 페이지는 낡음 상태가 되고, `just onto validate`가 `stale-page`로 경고합니다. `just onto status`가 바뀐 문서와 낡은 페이지를 보여 주니 같은 절차로 다시 ingest하면 됩니다. 에이전트에게는 처음과 똑같이 "billing을 onto-ingest로 정리해 줘"라고 하면 바뀐 문서와 낡은 페이지를 함께 다룹니다.

## 커밋 메시지 규약

온톨로지 층(`docs/ontology/`)을 바꾸는 지식 저장소의 커밋은 `onto(<작업>): <요약>` 형식으로 씁니다. `log.md`를 따로 두지 않고 git 이력과 이 규약이 그 역할을 합니다.

| 형식 | 쓰는 때 | 예 |
|---|---|---|
| `onto(ingest): <무엇을 정리했는지>` | 원본 문서에서 페이지를 만들거나 고쳤을 때 | `onto(ingest): 결제 설계 문서에서 게이트웨이와 용어 페이지 추가` |
| `onto(lint): <무엇을 고쳤는지>` | 점검으로 페이지를 고쳤을 때 | `onto(lint): 결제 게이트웨이의 중복 페이지 병합` |
