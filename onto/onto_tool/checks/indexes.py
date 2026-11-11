"""어긋난 인덱스: 지식 저장소의 인덱스(`docs/ontology/index.md`)가 지금 페이지에서 만들어지는 인덱스와 다르다.

인덱스는 생성물이지만 지식 저장소에 커밋한다(ADR 0006). 기능 없이 페이지를 고치면 인덱스가 실제 내용과 어긋날 수 있다.
지금 페이지로 있어야 할 인덱스를 `build`와 같은 코드로 만들어 파일과 글자 단위로 비교한다. 인덱스를 고치지는 않는다.
고치는 방법은 다시 `build`하는 것이다. 손으로 고친 인덱스도 생성물과 다르므로 같이 잡힌다.

인덱스 파일이 아직 없는 지식 저장소는 어긋난 것으로 보지 않는다. 없는 것은 어긋난 내용이 아니라 만든 적이 없는 것이고,
`build`와 최신화가 만든다. 컴파일이 줄바꿈을 `\\n`으로 통일해 읽으므로 CRLF로 클론된 인덱스는 같은 글자로 본다.
"""

from collections.abc import Iterator

from ..compiler import Compiled
from .catalog import INDEX_MISMATCH
from .model import Issue

_SHOWN = 3  # 설명에 보여 주는 어긋난 줄의 수(한쪽당)


def find(compiled: Compiled) -> Iterator[Issue]:
    # `index`가 `checks.classes`를 쓰므로 위에서 불러오면 두 패키지가 서로를 먼저 불러 순환한다.
    from .. import index

    expected = {content.index_file: index.render(content) for content in index.collect(compiled)}
    for record in compiled.records:
        if record.index_file not in expected or record.index_text is None or record.index_text == expected[record.index_file]:
            continue
        yield Issue(
            INDEX_MISMATCH,
            record.index_file,
            f"인덱스가 현재 페이지와 어긋나 있다. `onto build`로 다시 만든다. {_difference(expected[record.index_file], record.index_text)}",
        )


def _difference(expected: str, actual: str) -> str:
    """어긋난 곳을 줄 단위로 알린다: 있어야 하는데 없는 줄, 있으면 안 되는데 있는 줄."""
    expected_lines, actual_lines = expected.splitlines(), actual.splitlines()
    missing = [line for line in expected_lines if line.strip() and line not in actual_lines]
    extra = [line for line in actual_lines if line.strip() and line not in expected_lines]
    parts = [
        f"{label}: {_shown(lines)}" for label, lines in (("인덱스에 없는 줄", missing), ("인덱스에 남은 줄", extra)) if lines
    ]
    return " / ".join(parts) or "줄의 순서나 빈 줄이 다르다"


def _shown(lines: list[str]) -> str:
    shown = ", ".join(f"`{line.strip()}`" for line in lines[:_SHOWN])
    return shown + (f" 외 {len(lines) - _SHOWN}줄" if len(lines) > _SHOWN else "")
