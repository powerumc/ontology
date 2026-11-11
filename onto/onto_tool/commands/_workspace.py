"""작업 공간을 여는 명령이 같이 쓰는 것: 현재 디렉토리와 명령줄의 `--within`으로 작업 공간을 만든다."""

import argparse
from pathlib import Path

from ..errors import OntoError
from ..paths import TOOL_DIR
from ..sync import MANAGED_DIR, ROOT_TREE
from ..workspace import Within, Workspace


def open_workspace(args: argparse.Namespace) -> Workspace:
    """현재 디렉토리를 `--within`이 정한 범위의 작업 공간으로 연다. 도구가 있는 곳과 범위가 맞지 않으면 `OntoError`다.

    복사된 `Justfile`은 어디서 불러도 그 저장소의 루트에서 도구를 실행한다. 루트 저장소(`just onto …`)에서는 루트 저장소이고,
    지식 저장소 안(`just -f .onto/Justfile …`)에서는 그 지식 저장소다.

    범위는 `Justfile`이 부른 방식으로 가려 넘기지만, 도구는 자기가 어디 있는지 안다. 루트 저장소의 도구는 `onto/`에, 지식 저장소에 복사된 도구는
    `.onto/`에 있다. 둘이 맞지 않으면 엉뚱한 범위로 조용히 일하지 않고(저장소를 하나도 찾지 못하고 0으로 끝나는 것을 포함) 바른 명령을 알리며 멈춘다.
    도구가 그 둘 어느 쪽에도 있지 않으면(다른 곳에 둔 사본) 받은 범위를 믿는다.
    """
    root = Path.cwd().resolve()
    at = _where(root)
    if at is not None and at is not args.within:
        raise OntoError(_mismatch(args.command, args.within, root))
    return Workspace(root, args.within)


def _where(root: Path) -> Within | None:
    """도구가 `root` 기준으로 루트 저장소의 `onto/`에 있는지, 지식 저장소의 `.onto/`에 있는지. 어느 쪽도 아니면 None이다."""
    if TOOL_DIR == (root / ROOT_TREE).resolve():
        return Within.ROOT
    if TOOL_DIR == (root / MANAGED_DIR).resolve():
        return Within.REPOSITORY
    return None


def _mismatch(command: str, asked: Within, root: Path) -> str:
    if asked is Within.REPOSITORY:
        return (
            f"`--within repository`는 지식 저장소 안에서 복사된 `{MANAGED_DIR}/`의 도구로 돌아야 하는데, 이 도구는 루트 저장소의 `{ROOT_TREE}/`에 있다"
            f"(실행 위치 {root}). 루트 저장소에서는 `just onto {command}`를 실행한다"
        )
    return (
        f"이 도구는 지식 저장소에 복사된 `{MANAGED_DIR}/`에 있어 이 지식 저장소만 다룬다(실행 위치 {root}). `--within root`로는 돌 수 없다. "
        f"이 저장소 안에서는 `just -f {MANAGED_DIR}/Justfile {command}`를 실행한다"
    )
