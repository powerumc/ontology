"""온톨로지 층의 페이지 파일: 위치에서 식별자를 얻고, frontmatter를 읽는다."""

import datetime
from dataclasses import dataclass
from pathlib import Path

import yaml

FENCE = "---"
INDEX_FILE = "index.md"  # 페이지에서 생성되는 인덱스. 페이지가 아니다.


class FrontmatterError(Exception):
    """frontmatter를 읽을 수 없다. 메시지는 이유다. 파일 이름은 부른 쪽이 붙인다."""


@dataclass(frozen=True)
class Page:
    identifier: str  # 온톨로지 층 기준 상대 경로에서 확장자를 뺀 것. 별도의 id 필드는 없다.
    path: Path
    meta: dict[str, object]  # frontmatter의 키와 값. 날짜는 ISO 문자열이다.


def find_pages(ontology_dir: Path) -> list[tuple[str, Path]]:
    """온톨로지 층의 페이지 파일을 `(식별자, 경로)`로 식별자 순으로 돌려준다.

    페이지는 `.md` 파일이다. 최상위의 `index.md`와 숨김 파일·디렉토리는 페이지가 아니다.
    """
    found = []
    for path in ontology_dir.rglob("*.md"):
        relative = path.relative_to(ontology_dir)
        if relative.as_posix() == INDEX_FILE or any(part.startswith(".") for part in relative.parts):
            continue
        if path.is_file():
            found.append((relative.with_suffix("").as_posix(), path))
    return sorted(found)


def read_page(identifier: str, path: Path) -> Page:
    """페이지 파일을 읽는다. frontmatter를 읽을 수 없으면 `FrontmatterError`를 던진다."""
    return Page(identifier, path, scalar_values(read_frontmatter(path)))


def read_frontmatter(path: Path) -> dict[str, object]:
    """`---`로 둘러싼 맨 앞의 YAML을 읽어 키와 값의 목록으로 돌려준다. 비어 있으면 빈 목록이다."""
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
        meta = yaml.safe_load("\n".join(lines[1:closing]))
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"YAML 문법 오류: {_first_line(exc)}") from exc
    if meta is None:
        return {}
    if not isinstance(meta, dict):
        raise FrontmatterError("frontmatter가 키와 값의 목록이 아니다")
    return meta


def scalar_values(meta: dict[str, object]) -> dict[str, object]:
    """값을 문자열·숫자·논리값 또는 그 목록으로 제한한다. 값이 없는 키는 뺀다. 날짜는 ISO 문자열로 바꾼다.

    중첩된 값은 그래프에 빈 노드(blank node)를 만들어 같은 입력에서 같은 그래프가 나오는 것을 깬다.
    """
    result: dict[str, object] = {}
    for key, value in meta.items():
        if value is None:
            continue
        items = value if isinstance(value, list) else [value]
        if not all(isinstance(item, str | int | float | bool | datetime.date) for item in items):
            raise FrontmatterError(f"`{key}`의 값이 문자열, 숫자, 날짜 또는 그 목록이 아니다")
        converted = [item.isoformat() if isinstance(item, datetime.date) else item for item in items]
        result[str(key)] = converted if isinstance(value, list) else converted[0]
    return result


def _first_line(exc: Exception) -> str:
    return str(exc).strip().splitlines()[0]
