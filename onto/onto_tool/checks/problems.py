"""컴파일이 읽지 못한 파일: 읽을 수 없는 페이지와 ontology.yaml, 값의 종류가 틀린 속성, 틀린 클래스 선언.

컴파일은 읽을 수 없는 파일을 `Compiled.problems`에 이름 있는 검사 항목과 함께 모아 두고 나머지를 계속 읽는다.
`build`와 `query`는 이것이 있으면 멈추지만, 스크립트 검사는 문제 하나로 보고하고 읽은 파일의 검사를 계속한다.
"""

from collections.abc import Iterator

from ..compiler import Compiled
from .catalog import BY_NAME
from .model import Issue


def find(compiled: Compiled) -> Iterator[Issue]:
    for problem in compiled.problems:
        yield Issue(BY_NAME[problem.check], problem.file, problem.message)
