---
# Policy 견본: 프로젝트에서 지켜야 하는 규칙이나 제약.
# 이 파일을 `docs/ontology/<식별자>.md`로 복사해 채운다. 쓰지 않는 키는 지우고, 이 주석도 지운다.
# 식별자는 온톨로지 층 기준 파일 경로에서 확장자를 뺀 것이고 클래스 디렉토리로 시작한다(`policy/api-versioning`). 경로의 각 조각은 영어 소문자, 숫자, 하이픈만 쓴다.
# 값의 형식과 쓰는 법은 conventions.md에 있다.
class: Policy
title:        # 필수. 정책의 이름. 원본 문서의 언어로 쓴다
description:  # 한 줄 설명
aliases: []   # 다른 이름. 한국어와 영어 별칭을 둔다
governs:      # 이 정책이 적용되는 Project나 Component의 식별자. 프로젝트 자신은 `project`다. 목록도 된다
supersedes:   # 이 정책이 대체하는 옛 Policy
derivedFrom:
  - path:     # 근거로 삼은 원본 문서의 저장소 루트 기준 경로(예: `docs/policy.md`). 근거가 여럿이면 항목을 더한다
    hash:     # 그 문서의 git 해시. `status`가 보여 주는 현재 해시를 따옴표로 감싸 옮긴다. conventions.md의 "원본 문서"를 본다
---

# 정책 이름

무엇을 지켜야 하는지 한두 문장으로 쓴다.

## 규칙

## 적용 대상

## 이유

## 예외
