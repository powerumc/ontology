# 지식 저장소 안에서 쓰기

지식 저장소 안에서는 복사된 `Justfile`을 직접 지정해 그 저장소의 지식만 다룹니다.

```sh
cd projects/billing
just -f .onto/Justfile build
just -f .onto/Justfile validate
just -f .onto/Justfile query 'SELECT ?e WHERE { ?e a onto:Term }'
just -f .onto/Justfile status
just -f .onto/Justfile rules
```

저장소의 어느 디렉토리에서 실행해도 그 저장소를 기준으로 동작하고, 보고하는 경로도 그 저장소 기준입니다. 지식 저장소 팀의 `Justfile`이 `mod onto '.onto/Justfile'`로 불러와도 똑같이 동작합니다.

에이전트도 같은 스킬(`onto-ingest`, `onto-query`, `onto-lint`)로 일합니다. 스킬이 루트에서는 `just onto …`를, 지식 저장소 안에서는 `just -f .onto/Justfile …`를 쓰도록 안내합니다. 지식 저장소 안에서는 저장소 이름을 말하지 않아도 됩니다.

| 하고 싶은 것 | 이렇게 말합니다 |
|---|---|
| 정리 | "이 저장소를 onto-ingest로 정리해 줘" |
| 질문 | "이 저장소의 컴포넌트와 그 의존 관계를 보여 줘" |
| 점검 | "onto-lint로 점검해 줘" |

다른 프로젝트와 비교하는 질문은 루트 저장소에서 하세요.

## 루트 저장소와 다른 점

| | 루트 저장소 | 지식 저장소 안 |
|---|---|---|
| 다루는 지식 | 붙인 지식 저장소 전체 | 그 저장소만 |
| 여러 저장소에 걸친 검사(교차 참조, 공유 범위 위반, 저장소 간 중복, 고아 페이지) | 합니다 | 건너뛰고, 건너뛰었다고 알립니다 |
| `sync` | 씁니다 | 쓸 수 없습니다. `.onto/`는 루트 저장소가 복사해 준 루트 관리 파일입니다 |

여러 저장소에 걸친 검사는 루트 저장소에서 해 주세요.

## 복사된 기능이 없는 클론

팀원이 프로젝트 저장소만 클론했다면 `.onto/`가 없습니다. 인덱스(`docs/ontology/index.md`)에서 페이지를 찾아 파일로 읽으면 됩니다.
