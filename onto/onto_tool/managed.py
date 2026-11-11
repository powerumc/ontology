"""루트 관리 파일: 루트 저장소가 정한 내용(`onto/`)과 지식 저장소가 지금 가진 사본(`.onto/`)(ADR 0005).

최신화(`sync`)는 사본을 루트의 내용으로 맞추고, 스크립트 검사(`checks.outdated`)는 사본이 루트와 같은지 읽는다. 둘이 같은 것을 같은 방식으로
읽도록 루트가 정한 파일, 파일의 지문, 마지막 최신화의 기록, 쓰면 안 되는 경로의 판정을 여기에 둔다. 이 모듈은 아무 파일도 쓰지 않는다.

루트 관리 파일은 루트 저장소가 추적(`git ls-files`)하는 `onto/` 파일뿐이다. 작업 트리의 지금 내용이다.
사본이 루트와 같은지는 버전 번호가 아니라 내용(지문)으로 판단한다. 버전 번호를 올리지 않고 코드만 고쳐도 사본은 뒤처진다.
"""

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from . import gitenv
from .errors import OntoError
from .paths import TOOL_DIR

# 루트 저장소의 디렉토리 -> 지식 저장소 안의 위치. 지식 저장소에 복사하는 루트 관리 파일의 묶음이다.
ROOT_TREE = "onto"
MANAGED_DIR = ".onto"
MANAGED_TREES = ((ROOT_TREE, MANAGED_DIR),)
# 마지막 최신화가 쓴 루트 관리 파일의 지문. `.onto/` 안의 기록이라 지식 저장소의 `.gitignore`가 함께 제외한다.
RECORD_FILE = f"{MANAGED_DIR}/.sync-record.json"


@dataclass(frozen=True)
class Source:
    """루트 저장소가 정한 루트 관리 파일 하나의 내용."""

    content: bytes
    executable: bool

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.content, self.executable)


@dataclass(frozen=True)
class Drift:
    """지식 저장소의 사본이 루트의 내용과 다른 곳. 경로는 지식 저장소 기준(`.onto/…`)이다. 모두 비어 있으면 사본이 루트와 같다."""

    missing: tuple[str, ...] = ()  # 루트에 있는데 사본에 없다
    different: tuple[str, ...] = ()  # 사본에 있지만 내용이 다르다(링크처럼 사본이라 할 수 없는 것 포함)
    leftover: tuple[str, ...] = ()  # 루트에서 없어졌는데, 마지막 최신화가 둔 파일이 사본에 남아 있다
    blocked: str | None = None  # `.onto/` 자체가 링크이거나 디렉토리가 아니라 사본을 읽을 수 없는 이유
    absent: bool = False  # `.onto/`가 아예 없다(최신화한 적이 없다)

    def __bool__(self) -> bool:
        return bool(self.missing or self.different or self.leftover or self.blocked or self.absent)


# --- 루트 저장소가 정한 것 ---------------------------------------------------------------


def runs_from_root(root: Path) -> bool:
    """도구가 루트 저장소의 `onto/`에서 도는가. 그때만 `root`의 `onto/`가 이 도구와 같은 루트의 기능이다."""
    return TOOL_DIR == (root / ROOT_TREE).resolve()


def collect_sources(root: Path) -> dict[str, Source]:
    """루트 저장소가 추적하는 `onto/` 파일을 지식 저장소 안의 경로(`.onto/…`)로 모은다. 작업 트리의 지금 내용이다.

    추적하지만 작업 트리에서 지운 파일은 없는 것으로 본다. 추적하지 않는 파일(새 파일, 가상환경, 캐시, 산출물)은 복사하지 않는다.
    """
    sources: dict[str, Source] = {}
    for tree, target in MANAGED_TREES:
        listing = _git(root, "ls-files", "--stage", "-z", "--", f"{tree}/")
        entries = [entry for entry in listing.split(b"\0") if entry]
        if not entries:
            raise OntoError(f"루트 저장소가 추적하는 `{tree}/` 파일이 없다. 복사할 기능이 없다")
        for entry in entries:
            meta, _, raw_path = entry.partition(b"\t")
            mode = meta.split()[0]
            relative = os.fsdecode(raw_path)
            if mode in (b"120000", b"160000"):
                raise OntoError(f"`{relative}`는 심볼릭 링크나 서브모듈이라 복사할 수 없다. 루트의 `{tree}/`에는 일반 파일만 둔다")
            try:
                content = (root / relative).read_bytes()
            except FileNotFoundError:
                continue
            sources[f"{target}/{PurePosixPath(relative).relative_to(tree).as_posix()}"] = Source(content, mode == b"100755")
    return sources


def untracked_sources(root: Path) -> list[str]:
    """루트의 `onto/`에 있지만 추적하지 않아 복사하지 않는 파일(`.gitignore`가 제외한 가상환경, 캐시, 산출물은 뺀다). 루트 기준 경로다."""
    found: list[str] = []
    for tree, _ in MANAGED_TREES:
        listing = _git(root, "ls-files", "-z", "--others", "--exclude-standard", "--", f"{tree}/")
        found += sorted(os.fsdecode(entry) for entry in listing.split(b"\0") if entry)
    return found


def _git(root: Path, *args: str) -> bytes:
    """루트 저장소(`root`)에서 git을 부른다. 환경 변수가 가리키는 다른 저장소나 인덱스, `root` 위의 저장소를 읽지 않는다(`gitenv`)."""
    try:
        result = subprocess.run(
            ["git", "--literal-pathspecs", *args], cwd=root, env=gitenv.environment(root.resolve().parent), capture_output=True, check=False
        )
    except FileNotFoundError as exc:
        raise OntoError("git이 없어 루트 저장소가 추적하는 파일을 알 수 없다") from exc
    if result.returncode != 0:
        raise OntoError(f"루트 저장소가 추적하는 파일을 알 수 없다(git이 실패했다): {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


# --- 지식 저장소의 사본 ------------------------------------------------------------------


def is_repository(path: Path) -> bool:
    """초기화된 지식 저장소(git 작업 트리)인가. 초기화되지 않은 서브모듈의 빈 디렉토리와 링크는 아니다."""
    return not path.is_symlink() and (path / ".git").exists()


def drift(repo: Path, sources: dict[str, Source]) -> Drift:
    """지식 저장소 `repo`의 `.onto/`가 `sources`(루트가 정한 내용)와 다른 곳. 아무것도 쓰지 않는다."""
    for _, target_dir in MANAGED_TREES:
        if reason := blocked(repo, target_dir, directory=True):
            return Drift(blocked=reason)
        if not (repo / target_dir).exists():
            return Drift(absent=True)
    recorded = read_record(repo)
    missing: list[str] = []
    different: list[str] = []
    for target, source in sorted(sources.items()):
        if blocked(repo, target):
            different.append(target)
            continue
        try:
            current = fingerprint_of(repo / target)
        except OSError:
            different.append(target)
            continue
        if current is None:
            missing.append(target)
        elif current != source.fingerprint:
            different.append(target)
    leftover = [target for target in sorted(set(recorded) - set(sources)) if os.path.lexists(repo / target)]
    return Drift(tuple(missing), tuple(different), tuple(leftover))


def read_record(repo: Path) -> dict[str, str]:
    """마지막 최신화가 쓴 루트 관리 파일의 지문. 없거나 읽을 수 없거나 모양이 틀리면 빈 기록이다(손으로 고쳤는지 알 수 없는 것으로 본다).

    기록은 지식 저장소 안의 파일이라 믿지 않는다. 루트 관리 파일의 위치(`.onto/` 아래)를 벗어나는 경로는 버려, 기록으로 저장소 밖을 지우게 할 수 없다.
    """
    if blocked(repo, RECORD_FILE):
        return {}
    try:
        data = json.loads((repo / RECORD_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    prefixes = tuple(f"{target}/" for _, target in MANAGED_TREES)
    return {
        path: fingerprint
        for path, fingerprint in data.items()
        if isinstance(path, str)
        and isinstance(fingerprint, str)
        and path.startswith(prefixes)
        and ".." not in PurePosixPath(path).parts
        and not PurePosixPath(path).is_absolute()
    }


def fingerprint(content: bytes, executable: bool) -> str:
    return hashlib.sha256(content).hexdigest() + ("x" if executable else "")


def fingerprint_of(path: Path) -> str | None:
    """지금 파일의 지문. 파일이 없으면 `None`."""
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        return None
    return fingerprint(content, bool(path.stat().st_mode & 0o100))


def blocked(repo: Path, relative: str, *, directory: bool = False) -> str | None:
    """`repo` 안의 `relative`에 쓰거나 지워도 되는지. 안 되면 이유를 돌려준다. `directory`는 마지막 조각이 디렉토리여야 한다는 뜻이다.

    경로의 어느 조각이든 심볼릭 링크면 따라가지 않는다(저장소 밖의 파일을 덮어쓰거나 지울 수 있다). 마지막 조각이 이미 있는데 일반 파일이
    아니거나(`directory`이면 디렉토리가 아니거나), 중간 조각이 디렉토리가 아니어도 안 된다.
    """
    parts = PurePosixPath(relative).parts
    current = repo
    for number, part in enumerate(parts, start=1):
        current = current / part
        where = "/".join(parts[:number])
        if current.is_symlink():
            return f"`{where}`가 심볼릭 링크라 따라가지 않는다"
        if not current.exists():
            return None
        if number == len(parts) and not directory and not current.is_file():
            return f"`{where}`가 일반 파일이 아니다"
        if (number < len(parts) or directory) and not current.is_dir():
            return f"`{where}`가 디렉토리가 아니다"
    return None
