---
# Decision 견본: 대안 가운데 하나를 고른 결정과 그 이유.
# 이 파일을 `docs/ontology/<식별자>.md`로 복사해 채운다. 쓰지 않는 키는 지우고, 이 주석도 지운다.
# 식별자는 온톨로지 층 기준 파일 경로에서 확장자를 뺀 것이고 클래스 디렉토리로 시작한다(`decision/use-postgres`). 경로의 각 조각은 영어 소문자, 숫자, 하이픈만 쓴다.
# 값의 형식과 쓰는 법은 conventions.md에 있다.
# 본문과 값은 conventions.md의 "페이지는 원본에 근거한다"를 따른다.
class: Decision
title:        # 필수. 결정의 이름. 원본 문서의 언어로 쓴다
description:  # 한 줄 설명
aliases: []   # 다른 이름. 한국어와 영어 별칭을 둔다
date:         # 결정한 날짜. YYYY-MM-DD
about:        # 이 결정이 다루는 Component나 Project의 식별자. 프로젝트 자신은 `project`다. 목록도 된다
supersedes:   # 이 결정이 대체하는 옛 Decision
derivedFrom:
  - path:     # 근거로 삼은 원본 문서의 저장소 루트 기준 경로(예: `docs/adr/0001-use-postgres.md`). 근거가 여럿이면 항목을 더한다
    hash:     # 그 문서의 git 해시. `status`가 보여 주는 현재 해시를 따옴표로 감싸 옮긴다. conventions.md의 "원본 문서"를 본다
---

# 결정 이름

무엇을 골랐는지 한두 문장으로 쓴다.

## 배경

## 고려한 대안

## 결정과 이유

## 결과
