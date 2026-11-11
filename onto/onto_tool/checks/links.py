"""페이지 본문의 링크를 훑는 검사 항목: 링크가 지식 저장소 밖의 파일을 가리키는지.

지식 저장소가 단독으로 열려도 깨진 경로가 없어야 하고, 다른 저장소의 위치(파일 경로)를 드러내선 안 된다. 다른 저장소의 엔티티는
교차 참조로만 가리킨다(ADR 0001). 링크 모양과 밖을 가리키는 기준은 `links` 모듈이 정한다. 루트 전용 항목이다.
저장소 안을 가리키는 링크의 대상이 있는지는 여기서 보지 않는다. 참조 검사(`references`)가 `broken-reference`로 본다.
페이지가 아닌 파일(생성된 인덱스)은 보지 않는다. 읽을 수 없는 페이지는 본문을 몰라 건너뛰며, 그 문제는 따로 보고된다.
"""

import posixpath
from collections.abc import Iterator

from .. import links
from ..compiler import Compiled
from ..rules import RuleSet
from .catalog import OUTSIDE_LINK
from .model import Issue


def find(compiled: Compiled, rules: RuleSet) -> Iterator[Issue]:
    for record in compiled.records:
        for page in record.pages:
            directory = posixpath.dirname(page.file.removeprefix(f"{record.path}/"))  # 지식 저장소 루트 기준
            for destination in links.destinations(page.body):
                if reason := links.outside_reason(directory, destination):
                    yield Issue(
                        OUTSIDE_LINK,
                        page.file,
                        f"본문의 링크 `{destination}`가 지식 저장소 밖의 파일을 가리킨다({reason}). "
                        "다른 지식 저장소의 엔티티는 관계의 교차 참조(`<저장소 이름>:<식별자>`)로 가리키고, 저장소 밖의 파일은 링크하지 않는다",
                    )
