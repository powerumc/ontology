"""어긋난 인덱스: 지식 저장소의 인덱스(`docs/ontology/index.md`)가 없거나 지금 페이지에서 만들어지는 인덱스와 다르다.

인덱스는 생성물이지만 지식 저장소에 커밋한다(ADR 0006). 따로 클론한 사람과 에이전트에게는 인덱스가 온톨로지 층의 유일한 진입점이라,
없는 것도 어긋난 것이다. 기능 없이 페이지를 고치면 인덱스가 실제 내용과 어긋날 수 있다.
지금 페이지로 있어야 할 인덱스를 `build`와 같은 코드로 만들어 파일과 글자 단위로 비교한다. 인덱스를 고치지는 않는다.
고치는 방법은 다시 `build`하는 것이다. 손으로 고친 인덱스도 생성물과 다르므로 같이 잡힌다.
컴파일이 줄바꿈을 `\\n`으로 통일해 읽으므로 CRLF로 클론된 인덱스는 같은 글자로 본다.

인덱스 경로가 심볼릭 링크이거나 디렉토리이면 따라가지 않는다. 컴파일이 읽지 않고 이유만 `RepositoryRecord.index_problem`에 두며,
여기서 그 이유로 보고한다. `build`는 같은 이유로 그 경로에 쓰지 않는다.

다음 지식 저장소는 건너뛴다. 인덱스를 만들 수 없거나 믿을 수 없는 저장소에 "다시 build한다"고 알릴 수는 없고, 그 원인이 따로 보고된다.
- 온톨로지 층이 없거나 `ontology.yaml`을 읽을 수 없는 저장소: 이름을 몰라 인덱스를 만들 수 없다.
- 읽을 수 없는 파일이 있는 저장소: `build`가 멈춰 인덱스를 다시 만들 수 없다.
- 다른 저장소와 `name`이 겹치는 저장소: 그래프에 두 저장소의 엔티티가 섞여 인덱스가 틀린다.
"""

from collections.abc import Iterator

from .. import index
from ..compiler import Compiled
from ..rules import RuleSet
from .catalog import INDEX_MISMATCH
from .model import Issue, repository_of

_SHOWN = 3  # 설명에 보여 주는 어긋난 줄의 수(한쪽당)


def find(compiled: Compiled, rules: RuleSet) -> Iterator[Issue]:
    unreadable = {repository_of(problem.file) for problem in compiled.problems}
    expected = {content.index_file: index.render(content) for content in index.collect(compiled)}
    for record in compiled.records:
        if record.index_file not in expected or record.directory in unreadable:
            continue
        if record.index_problem is not None:
            yield Issue(
                INDEX_MISMATCH,
                record.index_file,
                f"인덱스를 읽거나 쓸 수 없는 경로다: {record.index_problem}. 지우고 `onto build`로 만든다.",
            )
        elif record.index_text is None:
            yield Issue(INDEX_MISMATCH, record.index_file, "인덱스가 없다. `onto build`로 만든다.")
        elif record.index_text != expected[record.index_file]:
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
