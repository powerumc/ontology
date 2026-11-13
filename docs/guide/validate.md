# 검사와 규칙

검사는 두 가지입니다.

| | 스크립트 검사 | LLM 검사 |
|---|---|---|
| 실행 | `just onto validate` | 에이전트에게 `onto-lint`로 요청 |
| 찾는 것 | 구조 제약, 깨진 참조, 고아 페이지, 낡음, 인덱스, 공유 범위, 중복, 식별자 형식 | 모순, 근거 없는 문장, 인용 누락, 빠진 개념 |
| 방식 | 기계적이라 결과가 항상 같음 | 판단이 필요함 |
| 파일 수정 | 하지 않음 | 결과를 보고하고, 승인받은 것만 고침 |

## 스크립트 검사

```sh
just onto validate
```

깨진 참조는 관계의 값과 본문 링크의 대상을 모두 봅니다. 어떤 파일도 고치지 않습니다.

문제는 한 줄에 하나씩, 탭으로 나눈 다섯 칸으로 출력됩니다.

```
심각도	지식 저장소	파일	검사 항목	설명
```

오류가 하나라도 있으면 종료 코드 1, 경고만 있으면 0입니다. 문제가 없으면 아무것도 출력하지 않습니다.

## LLM 검사

에이전트에게 스킬 `onto-lint`로 요청합니다. 에이전트는 스크립트 검사를 먼저 돌리고 이어서 LLM 검사를 한 뒤, 고치기 전에 결과를 보고하고 어느 것을 고칠지 묻습니다.

| 하고 싶은 것 | 이렇게 말합니다 |
|---|---|
| 저장소 점검 | "billing을 onto-lint로 점검해 줘" |
| 범위를 좁혀 점검 | "billing의 결정 페이지만 onto-lint로 점검해 줘" |
| 보고 뒤 고치기 | "중복 페이지 병합만 고쳐 줘" |

Claude Code에서는 `/onto-lint billing`으로 바로 부를 수 있습니다. 고친 내용은 `onto(lint): <무엇을 고쳤는지>`로 커밋합니다([커밋 메시지 규약](ingest.md#커밋-메시지-규약)). 자세한 동작은 [`onto-lint` 스킬](../../.claude/skills/onto-lint/SKILL.md)에 있습니다.

## 규칙

검사 항목마다 켬/끔과 심각도(오류, 경고)가 규칙으로 정해져 있습니다. 루트 기본값은 [`onto/rules.yaml`](../../onto/rules.yaml)에 있고, 지식 저장소는 `docs/ontology/ontology.yaml`의 `rules`로 자기 저장소에 한해 덮어쓸 수 있습니다.

```sh
just onto rules            # 루트 기본 규칙
just onto rules billing    # billing의 ontology.yaml이 덮어쓴 값까지 합친 규칙
```

적용되는 규칙은 JSON으로 출력됩니다. 다음 항목은 루트 전용이라 지식 저장소가 덮어쓸 수 없고, 덮어쓰려 하면 `invalid-rules` 오류가 납니다.

- 푸시 관문(`push-gate`)
- 식별자 형식(`language.identifier-pattern`)
- 공유 범위 검사 항목(`invalid-scope`, `scope-violation`, `path-reference`, `outside-link`)
- `ontology.yaml` 자체의 문제를 보고하는 항목(`invalid-ontology-yaml`, `invalid-class-declaration`)
- 지식 저장소 사이의 `name` 겹침(`duplicate-repository-name`)

근거는 [`onto/rules.yaml`](../../onto/rules.yaml)의 주석에 있습니다.
