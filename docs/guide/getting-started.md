# 시작하기

이 저장소를 받아 내 루트 저장소로 만들고 지식 저장소를 붙이는 과정입니다. 필요한 도구는 `git`, `just`(1.35 이상), `uv`입니다. `just setup`은 세 도구가 있는지만 확인하고 버전은 보지 않습니다. 설치 방법은 [README의 도구 설치](../../README.md#도구-설치)에 있습니다.

## 1. 받아서 내 것으로 만들기

```sh
git clone https://github.com/powerumc/ontology my-ontology && cd my-ontology
git remote set-url origin <내 원격 저장소 주소>
just setup
```

이 공개 원본에는 지식 저장소가 하나도 등록되어 있지 않고, `origin`이 공개 원본인 상태에서는 `just repo add`가 거부됩니다. 그래서 받은 뒤 `origin`부터 내 원격으로 바꿉니다.

## 2. 지식 저장소 붙이기

```sh
just repo add <지식 저장소 주소> [이름] [브랜치]
git commit -m "chore: <이름> 지식 저장소를 등록한다"
just git push
```

등록은 스테이징까지만 하므로 커밋은 따로 합니다. 에이전트에게 "git@github.com:me/billing.git을 지식 저장소로 붙이고 커밋해 줘"처럼 맡겨도 됩니다. 이름을 정하는 규칙과 `repo add`가 하는 일은 [지식 저장소 붙이기와 떼기](knowledge-repos.md)에 있습니다.

여러 프로젝트를 비교·종합한 지식이나 서로 다른 저장소의 용어가 같다는 사실 같은 개인 지식은 **개인 지식 저장소**에 두기를 권합니다. 비공개 저장소를 하나 만들어 같은 방법(`just repo add`)으로 붙이면 팀 저장소에 개인적인 해석이 섞이지 않습니다.

## 3. 다른 기기에서 쓰기

등록한 지식 저장소는 내 루트 저장소에 커밋되어 있으므로, 다른 기기에서는 클론하고 `just setup`만 실행하면 같은 구성이 됩니다.

```sh
git clone <내 원격 저장소 주소> my-ontology && cd my-ontology
just setup
```

`just setup`은 다음 순서로 일하고, 커밋하지 않습니다.

1. 도구(`git`, `just`, `uv`)가 있는지 확인합니다.
2. 서브모듈을 초기화해 detached HEAD가 아니라 추적 브랜치에 체크아웃합니다. 루트가 기록한 커밋에서 시작하며 원격의 최신으로 올리지는 않습니다.
3. 온톨로지 층(`docs/ontology/ontology.yaml`)이 있는 지식 저장소마다 `just onto sync <이름>`으로 최신화합니다. 복사된 기능(`.onto/`, 에이전트 스킬)은 지식 저장소의 커밋에 들어가지 않아 새 클론에는 없기 때문입니다. 이제 지식 저장소 안에서도 `just -f .onto/Justfile …`와 스킬을 쓸 수 있습니다.

## 문제가 생기면

| 상황 | 할 일 |
|---|---|
| 온톨로지 층이 없는 지식 저장소 | `setup`은 최신화하지 않습니다. `just onto sync <이름>`으로 구성하세요. |
| 최신화가 실패함 | 서브모듈 설정은 그대로 남고, `setup`이 실패한 저장소를 알린 뒤 종료 코드 1로 끝납니다. 원인을 고친 다음 `just onto sync <이름>`을 실행하세요. |
