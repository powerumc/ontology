"""원본 문서: 페이지가 근거로 삼은 문서와 그 해시, 넘긴 문서의 목록, ingest 대상 목록.

원본 문서는 지식 저장소에 이미 있는 문서다(ADR 0004). 온톨로지 층(`docs/ontology/`)과 분리되어 있고 이 도구는 고치지 않는다.
페이지는 `derivedFrom`에 근거로 삼은 문서의 경로와 git 해시를 적고(`{path, hash}` 항목), 읽고도 기록할 것이 없는 문서는
넘긴 문서의 목록(`docs/ontology/skipped.yaml`)에 같은 모양의 항목으로 적는다. 문서의 지금 해시와 적힌 해시가 다르면 낡음이다.

- 해시는 git이 그 문서를 `git add`할 때 기록할 정규 blob 해시다. 저장소의 blob에 CRLF가 들어 있지 않은 문서(LF로 커밋한 문서, 대부분)는
  깨끗한 클론에서 `git rev-parse HEAD:<경로>`와 같고, 같은 커밋이면 `core.autocrlf`나 `.gitattributes`의 `eol`·`text`·`filter`가
  달라 작업 트리의 바이트가 기기마다 달라도 같다. 작업 트리에 있는 파일의 지금 내용으로 계산하므로 커밋하지 않은 수정도 달라진 것으로 본다.
  한계: 저장소의 blob에 이미 CRLF가 들어 있는 문서(변환 설정 없이 CRLF로 커밋한 문서, 줄바꿈이 CRLF인 채 시작한 저장소에 흔하다)는 해시가
  `git rev-parse HEAD:<경로>`와 다를 수 있다. git은 줄바꿈 자동 변환에서 인덱스에 이미 CRLF로 든 파일을 변환하지 않는데(`git add`와
  `git status`는 인덱스를 읽어 그렇게 한다), `git hash-object`는 인덱스를 읽지 않아 `core.autocrlf=true`나 `.gitattributes`의 `text=auto`가
  있으면 CRLF를 LF로 바꿔 해시하기 때문이다. 변환 설정이 없는 기기에서는 같다. 그래서 `core.autocrlf`가 다른 기기에서는 같은 커밋인데도
  해시가 다르고(한쪽에서 ingest한 페이지가 다른 쪽에서 낡음으로 나온다), 커밋한 뒤 `text=auto`를 더한 저장소에서는 모든 기기에서 `git rev-parse`와
  다르다. 해시는 `git rev-parse`가 아니라 `onto status`가 내는 값을 쓴다. 이 한계를 없애려면 저장소의 blob을 LF로 정규화해 다시 커밋한다
  (`.gitattributes`에 `text=auto`를 두고 `git add --renormalize .`).
  지식 저장소가 git 작업 트리(`.git`이 있다)이면 `git hash-object --stdin-paths`(`-w` 없이)로 낸다. git이 그 경로에 `.gitattributes`와
  `core.autocrlf` 같은 변환 설정을 적용해 `git add`가 기록할 blob의 해시를 준다. 그 설정은 사용자가 체크아웃에 쓴 것과 같은
  설정이라 결과를 정하는 입력이므로 고정하지 않는다. 고정하는 것은 저장소를 찾는 방식(`GIT_DIR` 같은 환경 변수를 버리고, 상위 디렉토리의
  저장소를 찾지 않는다)과 `core.safecrlf`뿐이다. `-w`가 없으면 객체도 인덱스도 쓰지 않는다.
  git 저장소가 아닌 디렉토리(견본)에서는 파일 내용 그대로를 git이 blob으로 해시하는 방식(`sha1("blob <바이트 수>\0" + 내용)`)으로 계산한다.
  git을 실행하지 못하면 그 방식으로 계산하고 알린다(`document_hashes`가 알림 문구를 돌려준다).
- 문서는 지식 저장소 안의 일반 파일이다. 심볼릭 링크(경로 중간의 디렉토리 링크 포함)와 디렉토리는 원본 문서가 아니다. git이 링크를
  내용이 아니라 대상 경로의 blob으로 기록하고, 저장소 밖을 가리킬 수 있기 때문이다(ADR 0001).
- 경로는 대소문자를 구분해 저장소가 실제로 가진 이름과 같아야 한다. 대소문자를 구분하지 않는 파일 시스템(macOS)에서도 `docs/Design.md`는
  `docs/design.md`가 아니다. 유니코드는 NFC로 정규화해 비교한다(macOS의 NFD 파일 이름과 NFC로 적은 경로가 같다). 비교만 정규화하고 파일은
  디렉토리에 있는 이름 그대로 연다.
- ingest 대상은 규칙의 `sources`(글롭과 제외 경로)로 정하고, 온톨로지 층은 규칙과 무관하게 항상 뺀다. 숨김 경로(경로의 어느 조각이든 `.`으로
  시작하는 것: `.git`, 루트 관리 파일인 `.onto/`)와 심볼릭 링크도 대상이 아니다.
"""

import hashlib
import os
import re
import subprocess
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from . import gitenv
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
    if path == _LAYER or path.startswith(f"{_LAYER}/"):
        raise ValueKindError(
            f"{where}의 `path` `{path}`가 온톨로지 층(`{_LAYER}/`) 안을 가리킨다. 온톨로지 층은 원본 문서가 아니다"
            "(원본 문서는 층과 분리된 문서이고 ingest 대상에서 항상 빠진다)"
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

class _GitFailure(Exception):
    """git으로 해시를 내지 못했다. 메시지는 이유다."""


def blob_hash(content: bytes) -> str:
    """내용을 git이 blob으로 해시하는 방식으로 해시한 값. 줄바꿈 변환 같은 git의 입력 변환은 적용하지 않는다."""
    return hashlib.sha1(b"blob %d\0" % len(content) + content, usedforsecurity=False).hexdigest()


def document_hashes(repository: Path, paths: Iterable[str]) -> tuple[dict[str, str | None], str | None]:
    """지식 저장소 `repository` 안의 원본 문서 `paths`의 지금 내용의 해시를 `{경로: 해시}`로 돌려준다. 경로는 받은 글자 그대로다.

    문서가 없으면 None이다. 없는 문서는 이름이 저장소의 것과 대소문자까지 같은 일반 파일이 아닌 경우다(`_locate`).
    git 작업 트리이면 git이 기록하는 정규 blob 해시이고, 아니면 파일 내용 그대로의 blob 해시다(모듈 설명).
    두 번째 값은 알릴 것이다. git을 실행하지 못해 파일 내용 그대로 계산했을 때만 있고, 아니면 None이다.
    """
    listings: dict[Path, list[str]] = {}
    located = {path: _locate(repository, path, listings) for path in sorted(set(paths))}
    present = sorted({actual for actual in located.values() if actual is not None})
    computed: dict[str, str | None] = {}
    notice = None
    if present and (repository / ".git").exists():
        try:
            computed = dict(_git_hashes(repository, present))
        except _GitFailure as exc:
            notice = (
                f"원본 문서의 해시를 git으로 내지 못해 파일 내용 그대로 계산했다({exc}). "
                "줄바꿈 변환이 있는 저장소에서는 git이 기록하는 해시와 다를 수 있다"
            )
    if present and not computed:
        computed = {actual: _plain_hash(repository / actual) for actual in present}
    return {path: computed.get(actual) if actual is not None else None for path, actual in located.items()}, notice


def _plain_hash(path: Path) -> str | None:
    try:
        return blob_hash(path.read_bytes())
    except OSError:
        return None


def _git_hashes(repository: Path, paths: list[str]) -> dict[str, str]:
    """`git hash-object`로 낸 `{경로: 정규 blob 해시}`. `-w`가 없어 아무것도 쓰지 않는다. 실패하면 `_GitFailure`다.

    `git add`가 기록할 blob의 해시를 낸다. 파일마다 `.gitattributes`와 `core.autocrlf` 같은 설정으로 입력 변환(`text`, `eol`, `filter`)을 거친다.
    그 설정은 결과를 정하는 입력이라 고정하지 않는다. 사용자 환경에서 고정하는 것: 저장소 위치를 바꾸는 환경 변수를 버리고,
    상위 디렉토리로 올라가 다른 저장소(루트 저장소)를 찾지 않게 하며(`GIT_CEILING_DIRECTORIES`), `core.safecrlf`를 끈다.
    """
    real = repository.resolve()
    environment = gitenv.environment(real.parent)
    command = ["git", "-c", "core.safecrlf=false", "-C", str(real), "hash-object"]

    def run(arguments: list[str], text: bytes = b"") -> list[str]:
        try:
            done = subprocess.run([*command, *arguments], input=text, capture_output=True, env=environment, check=False)
        except OSError as exc:
            raise _GitFailure(f"git을 실행하지 못했다: {exc.strerror or exc}") from exc
        if done.returncode != 0:
            reason = done.stderr.decode("utf-8", errors="replace").strip().splitlines()
            raise _GitFailure(reason[0] if reason else f"git이 종료 코드 {done.returncode}로 끝났다")
        return done.stdout.decode("ascii", errors="replace").split()

    # `--stdin-paths`는 한 줄에 경로 하나를 읽고 `"`로 시작하는 줄을 C 방식 따옴표로 읽는다. 그런 경로와 줄바꿈이 든 경로는 하나씩 부른다.
    batch = [path for path in paths if "\n" not in path and not path.startswith('"')]
    hashes: dict[str, str] = {}
    if batch:
        lines = run(["--stdin-paths"], b"\n".join(os.fsencode(path) for path in batch) + b"\n")
        if len(lines) != len(batch):
            raise _GitFailure("git이 낸 해시의 수가 경로의 수와 다르다")
        hashes.update(zip(batch, lines, strict=True))
    for path in paths:
        if path not in hashes:
            (hashes[path],) = run(["--", path])
    if not all(GIT_HASH.fullmatch(value) for value in hashes.values()):
        raise _GitFailure("git이 40자리 16진수가 아닌 해시를 냈다")
    return hashes


def _locate(repository: Path, path: str, listings: dict[Path, list[str]]) -> str | None:
    """지식 저장소 안의 원본 문서 `path`가 실제로 있는 경로(저장소 루트 기준, 디렉토리에 있는 이름 그대로)를 돌려준다. 없으면 None이다.

    조각마다 디렉토리의 항목과 맞춘다. 대소문자는 구분하고 유니코드는 NFC로 정규화해 비교한다. 그래서 대소문자를 구분하지 않는
    파일 시스템에서도 같은 결과가 나온다. 경로 중간이든 끝이든 심볼릭 링크이면 없는 문서이고, 끝은 일반 파일이어야 한다.
    `listings`는 디렉토리 목록을 모아 두는 곳이다.
    """
    current = repository
    actual: list[str] = []
    for component in path.split("/"):
        if current not in listings:
            try:
                listings[current] = sorted(os.listdir(current))
            except OSError:  # 디렉토리가 아니거나 읽을 수 없다
                return None
        name = _entry_named(component, listings[current])
        if name is None:
            return None
        current = current / name
        actual.append(name)
        if current.is_symlink():
            return None
    return "/".join(actual) if current.is_file() else None


def _entry_named(component: str, names: list[str]) -> str | None:
    """`names`에서 이름이 `component`와 같은 항목. 글자 그대로 같은 것이 먼저이고, 없으면 NFC로 같은 것이 하나뿐일 때 그것이다."""
    if component in names:
        return component
    wanted = nfc(component)
    candidates = [name for name in names if nfc(name) == wanted]
    return candidates[0] if len(candidates) == 1 else None


def nfc(text: str) -> str:
    """경로를 비교하는 키. 파일 이름을 바꾸는 것이 아니라 같은지 가리는 데만 쓴다."""
    return unicodedata.normalize("NFC", text)


# --- ingest 대상 --------------------------------------------------------------------


def list_documents(repository: Path, sources: Sources) -> list[str]:
    """지식 저장소 `repository` 안에서 규칙의 `sources`가 가리키는 원본 문서를 경로 순으로 돌려준다.

    경로는 지식 저장소 루트 기준이고 `/`로 구분한다. `include`의 글롭과 맞고 `exclude`의 글롭과 맞지 않는 일반 파일이다.
    온톨로지 층(`docs/ontology/`)은 규칙과 무관하게 항상 빠진다. 숨김 경로(경로의 어느 조각이든 `.`으로 시작한다)도 글롭이 가리켜도 항상
    빠지고, 심볼릭 링크도 원본 문서가 아니라 뺀다. 글롭은 `*`가 한 조각 안의 글자들, `?`가 글자 하나, `[…]`가 글자 집합이고,
    `**`는 조각으로 쓰면 디렉토리를 0개 이상 건너뛴다.
    """
    include = [_glob_regex(glob) for glob in sources.include]
    exclude = [_glob_regex(glob) for glob in sources.exclude]
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
                    not _is_hidden(path)
                    and any(form.fullmatch(path) for form in include)
                    and not any(form.fullmatch(path) for form in exclude)
                    and not path.startswith(f"{_LAYER}/")
                    and (repository / path).is_file()
                    and not (repository / path).is_symlink()
                ):
                    found.add(path)
    return sorted(found)


def _is_hidden(path: str) -> bool:
    """경로의 어느 조각이든 `.`으로 시작하는 숨김 경로. 글롭이 앞쪽을 숨김 디렉토리로 정해도(`.onto/**`) 대상이 아니다."""
    return any(segment.startswith(".") for segment in path.split("/"))


def _walk_roots(include: tuple[str, ...]) -> list[str]:
    """글롭을 맞춰 볼 디렉토리. 글롭의 앞쪽 글자 그대로인 디렉토리(`docs/**/*.md`는 `docs`)만 훑어, 저장소 전체를 걷지 않는다.

    다른 디렉토리 아래에 든 디렉토리는 뺀다. 저장소 루트는 빈 문자열이다. 숨김 디렉토리(`.onto/**`)에서 시작하는 글롭은 찾을 파일이
    모두 숨김 경로라 훑지 않는다.
    """
    roots: set[str] = set()
    for glob in include:
        prefix: list[str] = []
        for segment in glob.split("/")[:-1]:  # 마지막 조각은 파일의 이름이다
            if re.search(r"[*?\[]", segment):
                break
            prefix.append(segment)
        if not any(segment.startswith(".") for segment in prefix):
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
