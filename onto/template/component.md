---
# Component 견본: 프로젝트를 이루는 시스템, 모듈, 서비스.
# 이 파일을 `docs/ontology/component/<식별자>.md`로 복사해 채운다. 쓰지 않는 키는 지우고, 이 주석도 지운다.
# 식별자는 파일 경로에서 나온다(`component/payment-api`). 파일 이름은 영어 소문자, 숫자, 하이픈만 쓴다.
# 값의 형식과 쓰는 법은 conventions.md에 있다.
class: Component
title:        # 필수. 컴포넌트의 이름. 원본 문서의 언어로 쓴다
description:  # 한 줄 설명
aliases: []   # 다른 이름. 한국어와 영어 별칭을 둔다
partOf:       # 이 컴포넌트가 일부인 Component나 Project의 식별자. 프로젝트 자신은 `project`다. 목록도 된다
dependsOn:    # 이 컴포넌트가 동작하려면 필요한 Component나 Project. 직접 의존만 적는다
supersedes:   # 이 컴포넌트가 대체하는 옛 Component
# derivedFrom: # 근거로 삼은 원본 문서. 경로와 git 해시를 적는다. conventions.md의 "원본 문서"를 본다
#   - path: docs/design.md
#     hash: 0123456789abcdef0123456789abcdef01234567
---

# 컴포넌트 이름

이 컴포넌트가 무엇이고 왜 있는지 두세 문장으로 쓴다.

## 책임

## 구성과 인터페이스

## 의존
