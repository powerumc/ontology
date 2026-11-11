"""원본 문서: 페이지가 근거로 삼은 문서와 그 해시, 넘긴 문서의 목록, ingest 대상 목록.

원본 문서는 지식 저장소에 이미 있는 문서다(ADR 0004). 온톨로지 층(`docs/ontology/`)과 분리되어 있고 이 도구는 고치지 않는다.
페이지는 `derivedFrom`에 근거로 삼은 문서의 경로와 git 해시를 적고(`{path, hash}` 항목), 읽고도 기록할 것이 없는 문서는
넘긴 문서의 목록(`docs/ontology/skipped.yaml`)에 같은 모양의 항목으로 적는다. 문서의 지금 해시와 적힌 해시가 다르면 낡음이다.

- 해시는 작업 트리에 있는 파일의 지금 내용으로 계산한다. 커밋하지 않은 수정도 달라진 것으로 본다.
  계산은 git이 파일을 blob으로 해시하는 방식(`git hash-object --no-filters`)과 같다: `sha1("blob <바이트 수>\\0" + 내용)`.
  git이 없어도 되고, 줄바꿈 변환 같은 사용자의 git 설정에 따라 달라지지 않는다. 내용 그대로를 해시한다.
- 문서는 지식 저장소 안의 일반 파일이다. 저장소 밖을 가리키는 링크나 디렉토리는 없는 문서로 본다(ADR 0001).
- ingest 대상은 규칙의 `sources`(글롭과 제외 경로)로 정하고, 온톨로지 층은 규칙과 무관하게 항상 뺀다. 숨김 파일과 숨김 디렉토리
  (`.git`, 루트 관리 파일인 `.onto/`)도 대상이 아니다.
"""

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from .keys import SOURCE_ENTRY_KEYS
from .pages import FrontmatterError, ValueKindError
from .rules import Sources
from .workspace import ONTOLOGY_DIR

# git 해시: SHA-1이 내는 40자리 소문자 16진수
GIT_HASH = re.compile(r"[0-9a-f]{40}")
_LAYER = ONTOLOGY_DIR.as_posix()  # 항상 대상에서 빠지는 온톨로지 층의 경로


@dataclass(frozen=True)
class SourceEntry:
    """원본 문서 하나의 기록: `derivedFrom`과 넘긴 문서의 목록의 항목."""

    path: str  # 지식 저장소 루트 기준 경로. `/`로 구분하고 `.`, `..`, 빈 조각이 없다
    hash: str  # 기록한 시점의 git 해시


# --- 기록을 읽기 --------------------------------------------------------------------


def parse_entries(value: object, label: str) -> list[SourceEntry]:
    """`derivedFrom`이나 넘긴 문서의 목록의 값을 항목으로 읽는다. 항목 하나이거나 그 목록이다. 값이 없으면 빈 목록이다.

    모양이 틀리면 `ValueKindError`로 이유를 알린다. `label`은 이유가 가리킬 이름(`` `derivedFrom` ``)이다. 같은 항목은 하나로 줄인다.
    """
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    entries = [
        _entry(item, f"{label}의 {number}번째 항목" if isinstance(value, list) else label)
        for number, item in enumerate(items, start=1)
    ]
    return list(dict.fromkeys(entries))


def _entry(item: object, where: str) -> SourceEntry:
    keys = ", ".join(f"`{key}`" for key in SOURCE_ENTRY_KEYS)
    if not isinstance(item, dict):
        raise ValueKindError(f"{where}이 {keys}를 가진 항목이 아니다(예: `path: docs/design.md`, `hash: <git 해시>`)")
    if unknown := sorted(str(key) for key in item if key not in SOURCE_ENTRY_KEYS):
        raise ValueKindError(f"{where}에 정의되지 않은 키 {', '.join(f'`{key}`' for key in unknown)}가 있다(쓸 수 있는 키: {keys})")
    for key in SOURCE_ENTRY_KEYS:
        if key not in item:
            raise ValueKindError(f"{where}에 `{key}`가 없다")
    path, hash_ = item["path"], item["hash"]
    if not isinstance(path, str) or not _is_normal_path(path):
        raise ValueKindError(
            f"{where}의 `path` `{path}`가 지식 저장소 루트 기준 파일 경로가 아니다"
            "(`/`로 구분하고, `/`로 시작하거나 `.`, `..`, 빈 조각이 있으면 안 된다)"
        )
    if not isinstance(hash_, str) or not GIT_HASH.fullmatch(hash_):
        raise ValueKindError(
            f"{where}의 `hash` `{hash_}`가 git 해시(40자리 소문자 16진수)가 아니다. 숫자로만 이루어진 해시는 따옴표로 감싼다"
        )
    return SourceEntry(path, hash_)


def _is_normal_path(path: str) -> bool:
    return bool(path) and not path.startswith("/") and all(segment not in ("", ".", "..") for segment in path.split("/"))


def read_skipped(path: Path) -> list[SourceEntry]:
    """넘긴 문서의 목록(`skipped.yaml`)을 읽는다. 파일이 없거나 비어 있으면 빈 목록이다.

    읽을 수 없으면 `FrontmatterError`, 모양이 틀리면 `ValueKindError`로 이유를 알린다(파일 이름은 부른 쪽이 붙인다).
    목록은 `{path, hash}` 항목의 목록이고, 항목의 모양은 `derivedFrom`과 같다.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return []
    except UnicodeDecodeError as exc:
        raise FrontmatterError("UTF-8 문서가 아니다") from exc
    except OSError as exc:  # 디렉토리이거나 권한이 없다
        raise FrontmatterError(f"읽을 수 없다: {exc.strerror or exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"YAML 문법 오류: {str(exc).strip().splitlines()[0]}") from exc
    except ValueError as exc:  # `2026-02-30`처럼 날짜 모양이지만 없는 날짜
        raise FrontmatterError(f"값을 읽을 수 없다: {exc}") from exc
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueKindError("`path`와 `hash`를 가진 항목의 목록이 아니다")
    return parse_entries(data, "목록")


# --- 해시 ---------------------------------------------------------------------------


def blob_hash(content: bytes) -> str:
    """내용을 git이 blob으로 해시하는 방식으로 해시한 값. `git hash-object --no-filters`와 같다."""
    return hashlib.sha1(b"blob %d\0" % len(content) + content, usedforsecurity=False).hexdigest()


def document_hash(repository: Path, path: str) -> str | None:
    """지식 저장소 `repository` 안의 원본 문서 `path`의 지금 내용의 해시. 문서가 없거나 읽을 수 없으면 None이다.

    일반 파일이 아니거나(디렉토리), 저장소 밖을 가리키는 링크이면 없는 문서다.
    """
    target = _regular_file(repository.resolve(), repository / path)
    if target is None:
        return None
    try:
        return blob_hash(target.read_bytes())
    except OSError:
        return None


def _regular_file(repository: Path, candidate: Path) -> Path | None:
    """`candidate`가 `repository`(이미 풀어 쓴 경로) 안의 일반 파일이면 풀어 쓴 경로, 아니면 None."""
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):  # 없다, 링크가 끊겼거나 순환한다
        return None
    return resolved if resolved.is_relative_to(repository) and resolved.is_file() else None


# --- ingest 대상 --------------------------------------------------------------------


def list_documents(repository: Path, sources: Sources) -> list[str]:
    """지식 저장소 `repository` 안에서 규칙의 `sources`가 가리키는 원본 문서를 경로 순으로 돌려준다.

    경로는 지식 저장소 루트 기준이고 `/`로 구분한다. `include`의 글롭과 맞고 `exclude`의 글롭과 맞지 않는 일반 파일이다.
    온톨로지 층(`docs/ontology/`)은 규칙과 무관하게 항상 빠지고, 숨김 파일과 숨김 디렉토리 안도 뺀다. 글롭은 `*`가 한 조각 안의
    글자들, `?`가 글자 하나, `[…]`가 글자 집합이고, `**`는 조각으로 쓰면 디렉토리를 0개 이상 건너뛴다.
    """
    include = [_glob_regex(glob) for glob in sources.include]
    exclude = [_glob_regex(glob) for glob in sources.exclude]
    real = repository.resolve()
    found: set[str] = set()
    for root in _walk_roots(sources.include):
        top = repository / root
        if not top.is_dir():
            continue
        for directory, dirnames, filenames in os.walk(top):  # 링크된 디렉토리는 따라가지 않는다
            relative = PurePosixPath(Path(directory).relative_to(repository).as_posix())
            dirnames[:] = sorted(
                name for name in dirnames if not name.startswith(".") and (relative / name).as_posix() != _LAYER
            )
            for name in filenames:
                path = (relative / name).as_posix()
                if (
                    not name.startswith(".")
                    and any(form.fullmatch(path) for form in include)
                    and not any(form.fullmatch(path) for form in exclude)
                    and not path.startswith(f"{_LAYER}/")
                    and _regular_file(real, repository / path) is not None
                ):
                    found.add(path)
    return sorted(found)


def _walk_roots(include: tuple[str, ...]) -> list[str]:
    """글롭을 맞춰 볼 디렉토리. 글롭의 앞쪽 글자 그대로인 디렉토리(`docs/**/*.md`는 `docs`)만 훑어, 저장소 전체를 걷지 않는다.

    다른 디렉토리 아래에 든 디렉토리는 뺀다. 저장소 루트는 빈 문자열이다.
    """
    roots: set[str] = set()
    for glob in include:
        prefix: list[str] = []
        for segment in glob.split("/")[:-1]:  # 마지막 조각은 파일의 이름이다
            if re.search(r"[*?\[]", segment):
                break
            prefix.append(segment)
        roots.add("/".join(prefix))
    return sorted(root for root in roots if not any(other != root and (not other or root.startswith(f"{other}/")) for other in roots))


def _glob_regex(glob: str) -> re.Pattern[str]:
    """지식 저장소 루트 기준 글롭을 경로 전체에 맞는 정규 표현식으로 바꾼다."""
    segments = glob.split("/")
    parts: list[str] = []
    for index, segment in enumerate(segments):
        last = index == len(segments) - 1
        if segment == "**":
            parts.append(".*" if last else "(?:[^/]+/)*")
        else:
            parts.append(_segment_regex(segment) + ("" if last else "/"))
    return re.compile("".join(parts))


def _segment_regex(segment: str) -> str:
    """글롭의 한 조각(`/`가 없다)을 정규 표현식으로. `fnmatch`의 변환과 같되 `/`에는 맞지 않는다."""
    parts: list[str] = []
    position = 0
    while position < len(segment):
        char = segment[position]
        position += 1
        if char == "*":
            parts.append("[^/]*")
        elif char == "?":
            parts.append("[^/]")
        elif char == "[":
            end = position
            if end < len(segment) and segment[end] == "!":
                end += 1
            if end < len(segment) and segment[end] == "]":
                end += 1
            while end < len(segment) and segment[end] != "]":
                end += 1
            if end >= len(segment):  # 닫히지 않은 `[`는 글자 그대로다
                parts.append(re.escape("["))
                continue
            body = segment[position:end].replace("\\", "\\\\")
            position = end + 1
            if body.startswith("!"):
                parts.append("[^" + body[1:] + "/]")
            else:
                parts.append("[" + ("\\" + body if body.startswith("^") else body) + "]")
        else:
            parts.append(re.escape(char))
    return "".join(parts)
