# 지식 저장소 붙이기와 떼기

두 명령 모두 스테이징까지만 하므로 커밋은 직접 합니다.

## 붙이기

```sh
just repo add git@github.com:me/billing.git                 # projects/billing/에 붙입니다. 이름은 주소의 저장소 이름입니다
just repo add git@github.com:me/billing.git pay develop     # 이름 pay, 추적 브랜치 develop
```

`repo add`는 서브모듈을 등록하고 추적 브랜치를 기록한 뒤 최신화(`just onto sync <이름>`)를 합니다. 최신화는 `.onto/`와 스킬을 복사하고, `.gitignore`와 프로젝트 지침 파일에 표시된 블록을 넣습니다. 온톨로지 층이 없으면 뼈대(`docs/ontology/ontology.yaml`과 인덱스)도 만듭니다.

새로 만든 `ontology.yaml`의 공유 범위(`scope`)는 가장 좁은 `private`으로 시작합니다. 저장소를 공유하는 범위에 맞게 바꿔 주세요. 쓸 수 있는 값은 [온톨로지 층 규약](../../onto/template/conventions.md#ontologyyaml)에 있습니다.

### 이미 온톨로지 층이 있는 저장소

저장소 소유 파일(`ontology.yaml`, 페이지)은 바뀌지 않습니다. 다만 그 저장소가 `ontology.yaml`에 `name`을 선언했다면 등록 이름이 그 `name`과 같아야 합니다. `name`은 서브모듈 디렉토리 이름과 같아야 하고, 교차 참조가 그 이름으로 저장소를 가리키기 때문입니다.

| 선언한 `name`과 등록 이름 | `repo add`의 동작 |
|---|---|
| 같음 | 등록합니다. |
| 다름 | 등록하기 전에 거부하고 선언된 이름을 알려 줍니다. |
| 확인하지 못함(원격에서 받지 못했거나 파일을 읽을 수 없음) | 그 사실을 알리고 등록은 계속합니다. |

확인을 위해 추적 브랜치의 끝을 한 번 더 얕게 받아 옵니다.

## 떼기

```sh
just repo remove billing            # 흔적까지 깨끗하게 제거합니다
just repo remove billing --force    # 버려질 작업이 있어도 제거합니다
```

커밋하지 않았거나 푸시하지 않은 작업이 있으면 이유를 알리고 거부합니다.

## 에이전트에게 맡기기

이 작업에는 스킬이 없습니다. 루트 `CLAUDE.md`가 명령은 `just`라고 안내하므로, 루트 저장소에서 에이전트에게 말하면 에이전트가 위 명령을 찾아 실행합니다. `repo remove`의 거부를 `--force`로 넘길지는 사람이 정합니다.

| 하고 싶은 것 | 이렇게 말합니다 |
|---|---|
| 붙이기 | "git@github.com:me/billing.git을 지식 저장소로 붙여 줘" |
| 이름과 브랜치를 정해 붙이기 | "git@github.com:me/billing.git을 pay라는 이름으로, develop 브랜치를 따라가게 붙여 줘" |
| 떼기 | "billing 지식 저장소를 떼어 줘" |

`repo add`가 이름 때문에 거부하거나 `repo remove`가 버려질 작업 때문에 거부하면 그 이유가 출력에 나옵니다.
