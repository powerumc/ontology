"""뒤처진 루트 관리 파일: 지식 저장소의 `.onto/`가 루트 저장소의 `onto/`와 내용이 다르다.

최신화는 루트의 `onto/`(추적하는 파일)를 지식 저장소의 `.onto/`로 복사한다. 루트가 기능을 고친 뒤 최신화하지 않은 지식 저장소는 옛 사본을 가진다.
이 항목은 그런 저장소를 경고해, 최신화가 필요한 곳을 알린다. 공통 어휘의 버전(`owl:versionInfo`)을 보여 주지만 **버전 번호로 판단하지 않는다.**
버전 번호를 올리지 않고 코드만 고친 경우도 사본이 뒤처진 것이므로, 루트가 정한 파일마다 사본의 내용을 지문(`managed`)으로 비교한다.
다른 곳은 세 가지다: 사본에 없는 파일, 내용이 다른 파일, 루트에서 없어졌는데 마지막 최신화가 둔 채 남은 파일.

루트의 스크립트 검사는 지식 저장소의 `.onto/`를 쓰지 않는다. 항상 루트의 최신 공통 어휘와 구조 제약으로 검사한다. 사본이 뒤처져도 검사 결과는 같다.

비교할 루트의 내용은 도구가 루트 저장소의 `onto/`에서 돌 때만 있다. 초기화되지 않은 서브모듈이나 지식 저장소가 아닌 디렉토리는 비교하지 않는다(최신화가 건너뛰는 것과 같다).
"""

from collections.abc import Iterator
from pathlib import Path

from .. import managed, vocab
from ..compiler import Compiled, RepositoryRecord
from ..rules import RuleSet
from .catalog import OUTDATED_MANAGED_FILES
from .model import Issue

_SHOWN = 3  # 설명에 보여 주는 파일의 수(분류마다)


def find(compiled: Compiled, rules: RuleSet) -> Iterator[Issue]:
    root = compiled.root
    if root is None or not managed.runs_from_root(root):
        return
    sources = managed.collect_sources(root)
    root_version = vocab.version()
    for record in compiled.records:
        repo = root / record.path
        if not managed.is_repository(repo):
            continue
        if drift := managed.drift(repo, sources):
            yield Issue(OUTDATED_MANAGED_FILES, f"{record.path}/{managed.MANAGED_DIR}", _message(record, repo, drift, root_version))


def _message(record: RepositoryRecord, repo: Path, drift: managed.Drift, root_version: str | None) -> str:
    if drift.blocked:
        what = f"사본을 읽을 수 없다: {drift.blocked}"
    elif drift.absent:
        what = f"`{managed.MANAGED_DIR}/`가 없다"
    else:
        what = ", ".join(
            f"{label} {len(paths)}개({_shown(paths)})"
            for label, paths in (
                ("없는 파일", drift.missing),
                ("내용이 다른 파일", drift.different),
                ("루트에서 없어졌는데 남은 파일", drift.leftover),
            )
            if paths
        )
    version = "" if drift.blocked or drift.absent else _version(repo, root_version)
    return (
        f"루트 관리 파일(`{managed.MANAGED_DIR}/`)이 루트 저장소의 `{managed.ROOT_TREE}/`와 다르다: {what}. "
        f"{version}`just onto sync {record.directory}`로 최신화한다"
    )


def _version(repo: Path, root_version: str | None) -> str:
    """공통 어휘의 버전을 비교한 글. 같아도 내용이 다르면 뒤처진 것이다."""
    own = vocab.version(repo / managed.MANAGED_DIR / "vocab")
    if root_version is None:
        return ""
    if own is None:
        return f"공통 어휘의 버전은 이 저장소의 사본에서 알 수 없고 루트는 {root_version}이다. "
    if own == root_version:
        return f"공통 어휘의 버전은 {root_version}으로 같지만 내용이 다르다. "
    return f"공통 어휘의 버전은 이 저장소 {own}, 루트 {root_version}이다. "


def _shown(paths: tuple[str, ...]) -> str:
    shown = ", ".join(f"`{path}`" for path in paths[:_SHOWN])
    return shown + (f" 외 {len(paths) - _SHOWN}개" if len(paths) > _SHOWN else "")
