"""텍스트 파일 읽기: 줄 나누기와 YAML 읽기. 읽을 수 없는 이유를 모든 파일에 같은 문구로 알린다.

페이지의 frontmatter, `ontology.yaml`, `skipped.yaml`, 루트 기본 규칙 파일이 같은 함수로 읽는다. 함수는 읽을 수 없으면 부른 쪽이 정한 예외(`error`)에
이유를 담아 던진다. 이유는 `UTF-8 문서가 아니다`, `읽을 수 없다: <이유>`(파일이 없거나 디렉토리이거나 권한이 없다), `YAML 문법 오류: <첫 줄>`,
`값을 읽을 수 없다: <이유>`(`2026-02-30`처럼 날짜 모양이지만 없는 날짜) 가운데 하나다. 파일이 없는 것이 정상인 곳은 부르기 전에 확인한다.
"""

import re
from pathlib import Path

import yaml

_LINE_BREAK = re.compile(r"\r\n|\r|\n")


def split_lines(text: str) -> list[str]:
    """`text`를 줄로 나눈다. 줄바꿈은 `\\n`, `\\r\\n`, `\\r`뿐이다. 끝의 줄바꿈 뒤의 빈 글자는 줄이 아니다.

    `str.splitlines()`는 U+2028, U+2029, U+0085, `\\x0b`, `\\x0c`, `\\x1c`~`\\x1e`에서도 나눈다. 마크다운과 YAML frontmatter의 줄은 그렇게 나뉘지 않아,
    그 문자 뒤의 글이 줄 맨 앞의 글이 되면 frontmatter의 경계(`---`)와 코드 블록의 울타리(```)가 바뀐다.
    """
    lines = _LINE_BREAK.split(text)
    if lines[-1] == "":
        lines.pop()
    return lines


def read_text(path: Path, error: type[Exception]) -> str:
    """`path`를 UTF-8(BOM은 뗀다)로 읽는다. 읽을 수 없으면 `error(이유)`를 던진다."""
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise error("UTF-8 문서가 아니다") from exc
    except OSError as exc:  # 파일이 없거나 사라졌고, 디렉토리이거나, 읽을 권한이 없다
        raise error(f"읽을 수 없다: {exc.strerror or exc}") from exc


def parse_yaml(text: str, error: type[Exception], loader: type[yaml.SafeLoader] = yaml.SafeLoader) -> object:
    """YAML 글을 읽는다. 문법이 틀리거나 값을 읽을 수 없으면 `error(이유)`를 던진다. 빈 글은 `None`이다."""
    try:
        return yaml.load(text, Loader=loader)
    except yaml.YAMLError as exc:
        raise error(f"YAML 문법 오류: {_first_line(exc)}") from exc
    except ValueError as exc:  # `2026-02-30`처럼 날짜 모양이지만 없는 날짜는 YAMLError가 아니라 ValueError로 나온다
        raise error(f"값을 읽을 수 없다: {exc}") from exc


def load_yaml_text(path: Path, error: type[Exception], loader: type[yaml.SafeLoader] = yaml.SafeLoader) -> object:
    """YAML 파일 `path`를 읽는다. 읽을 수 없으면 `error(이유)`를 던진다. 빈 파일은 `None`이다."""
    return parse_yaml(read_text(path, error), error, loader)


def _first_line(exc: Exception) -> str:
    """예외 설명의 첫 줄. 이유를 한 줄로 알릴 때 쓴다."""
    lines = str(exc).strip().splitlines()
    return lines[0] if lines else type(exc).__name__
