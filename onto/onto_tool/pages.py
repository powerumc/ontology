"""온톨로지 층의 페이지 파일: 위치에서 식별자를 얻고, frontmatter를 읽는다."""

import datetime
from collections.abc import Iterator
from pathlib import Path

import yaml

from .keys import PAGE_KEYS, SOURCE_KEY

FENCE = "---"
INDEX_FILE = "index.md"  # 페이지에서 생성되는 인덱스. 페이지가 아니다.
# 마크다운 문서에 흔히 쓰는 확장자. `.md`가 아닌 것은 페이지로 읽히지 않으므로, 페이지를 잘못 이름 붙인 것으로 본다.
MARKDOWN_SUFFIXES = (".md", ".markdown", ".mdown", ".mkd")


class FrontmatterError(Exception):
    """frontmatter를 읽을 수 없다. 메시지는 이유다. 파일 이름은 부른 쪽이 붙인다."""


class ValueKindError(FrontmatterError):
    """frontmatter를 읽었지만 값의 종류가 맞지 않다(문자열이어야 하는데 중첩된 값이다 등). 스크립트 검사가 따로 보고한다."""


class NonexistentDate(str):
    """`2026-02-30`처럼 날짜 모양이지만 없는 날짜. YAML이 날짜로 읽지 못해 쓴 글자 그대로 남긴다."""


class _FrontmatterLoader(yaml.SafeLoader):
    """없는 날짜 하나가 문서 전체를 읽을 수 없게 만들지 않는 YAML 로더.

    기본 로더는 `2026-02-30`에서 `ValueError`를 던져 페이지 전체를 읽을 수 없게 만든다. 그러면 같은 페이지의 다른 문제가
    가려진다. 이 로더는 그 값을 `NonexistentDate`로 남겨, 값의 종류가 틀린 속성 하나로만 알린다.
    """


def _construct_timestamp(loader: _FrontmatterLoader, node: yaml.Node) -> object:
    try:
        return yaml.SafeLoader.construct_yaml_timestamp(loader, node)
    except ValueError:
        return NonexistentDate(loader.construct_scalar(node))


_FrontmatterLoader.add_constructor("tag:yaml.org,2002:timestamp", _construct_timestamp)


def _visible_files(ontology_dir: Path) -> Iterator[tuple[str, Path]]:
    """온톨로지 층 안의 파일을 `(층 기준 상대 경로, 경로)`로. 숨김 파일과 숨김 디렉토리 안은 뺀다."""
    for path in ontology_dir.rglob("*"):
        relative = path.relative_to(ontology_dir)
        if not any(part.startswith(".") for part in relative.parts) and path.is_file():
            yield relative.as_posix(), path


def find_pages(ontology_dir: Path) -> list[tuple[str, Path]]:
    """온톨로지 층의 페이지 파일을 `(식별자, 경로)`로 식별자 순으로 돌려준다.

    페이지는 `.md` 파일이다. 최상위의 `index.md`와 숨김 파일·디렉토리는 페이지가 아니다.
    """
    found = [
        (Path(relative).with_suffix("").as_posix(), path)
        for relative, path in _visible_files(ontology_dir)
        if relative.endswith(".md") and relative != INDEX_FILE
    ]
    return sorted(found)


def find_misnamed_pages(ontology_dir: Path) -> list[Path]:
    """페이지처럼 보이지만 확장자가 `.md`가 아니어서 페이지로 읽히지 않는 파일(`.MD`, `.markdown` 등)을 경로 순으로 돌려준다."""
    return sorted(
        path
        for relative, path in _visible_files(ontology_dir)
        if path.suffix.lower() in MARKDOWN_SUFFIXES and path.suffix != ".md"
    )


def read_page(path: Path) -> tuple[dict[str, object], str]:
    """페이지 파일을 `(frontmatter, 본문)`으로 읽는다.

    frontmatter는 `---`로 둘러싼 맨 앞의 YAML을 읽은 키와 값의 목록이고, 비어 있으면 빈 목록이다. 값은 읽은 그대로다(날짜는
    `datetime.date`, 없는 날짜는 `NonexistentDate`). 값의 종류는 `page_values`가 따진다. 본문은 닫는 `---` 다음 줄부터의 글이다(줄바꿈은 `\n`).
    """
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise FrontmatterError("UTF-8 문서가 아니다") from exc
    if not lines or lines[0].strip() != FENCE:
        raise FrontmatterError(f"첫 줄이 {FENCE}가 아니라 frontmatter가 없다")
    closing = next((i for i in range(1, len(lines)) if lines[i].strip() == FENCE), None)
    if closing is None:
        raise FrontmatterError(f"{FENCE}로 닫히지 않았다")
    try:
        meta = yaml.load("\n".join(lines[1:closing]), Loader=_FrontmatterLoader)
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"YAML 문법 오류: {_first_line(exc)}") from exc
    except ValueError as exc:
        raise FrontmatterError(f"값을 읽을 수 없다: {exc}") from exc
    body = "\n".join(lines[closing + 1 :])
    if meta is None:
        return {}, body
    if not isinstance(meta, dict):
        raise FrontmatterError("frontmatter가 키와 값의 목록이 아니다")
    return meta, body


def page_values(meta: dict[str, object]) -> dict[str, object]:
    """읽은 frontmatter에서 컴파일이 쓸 값을 만든다. 값의 종류가 맞지 않으면 `ValueKindError`를 던진다.

    값의 종류는 정의된 키(`keys.PAGE_KEYS`)에서만 따진다. 정의되지 않은 키는 컴파일이 버리고 스크립트 검사가 키 이름으로
    알리므로, 그 값이 중첩되어 있어도 페이지를 읽을 수 없는 것으로 만들지 않고 그대로 둔다.
    `derivedFrom`은 중첩된 값(`{path, hash}` 항목)이 정상이라 여기서 다루지 않는다. `sources.parse_entries`가 따로 읽는다.
    """
    defined = scalar_values({key: value for key, value in meta.items() if key in PAGE_KEYS and key != SOURCE_KEY})
    undefined = {key: value for key, value in meta.items() if key not in PAGE_KEYS}
    return {**defined, **undefined}


def scalar_values(meta: dict[str, object]) -> dict[str, object]:
    """값을 문자열·숫자·논리값 또는 그 목록으로 제한한다. 값이 없는 키는 뺀다. 날짜는 ISO 문자열로 바꾼다.

    중첩된 값은 그래프에 빈 노드(blank node)를 만들어 같은 입력에서 같은 그래프가 나오는 것을 깬다.
    """
    result: dict[str, object] = {}
    for key, value in meta.items():
        if value is None:
            continue
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, NonexistentDate):
                raise ValueKindError(f"`{key}`의 값 `{item}`: 없는 날짜다")
        if not all(isinstance(item, str | int | float | bool | datetime.date) for item in items):
            raise ValueKindError(f"`{key}`의 값이 문자열, 숫자, 날짜 또는 그 목록이 아니다")
        converted = [item.isoformat() if isinstance(item, datetime.date) else item for item in items]
        result[str(key)] = converted if isinstance(value, list) else converted[0]
    return result


def _first_line(exc: Exception) -> str:
    return str(exc).strip().splitlines()[0]
