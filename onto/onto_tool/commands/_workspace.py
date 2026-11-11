"""작업 공간을 여는 명령이 같이 쓰는 것: 도구가 있는 곳과 명령줄의 `--within`으로 작업 공간을 만든다."""

import argparse
from pathlib import Path

from ..errors import OntoError
from ..paths import TOOL_DIR
from ..managed import MANAGED_DIR, ROOT_TREE
from ..workspace import Within, Workspace


def open_workspace(args: argparse.Namespace) -> Workspace:
    """`--within`이 정한 범위의 작업 공간을 연다. 도구가 있는 곳과 범위가 맞지 않으면 `OntoError`다.

    복사된 `Justfile`은 보통 그 저장소의 루트에서 도구를 실행한다. 루트 저장소(`just onto …`)에서는 루트 저장소이고,
    지식 저장소 안(`just -f .onto/Justfile …`)에서는 그 지식 저장소다. 다만 실행 위치는 `Justfile`을 부른 방식에 따라 달라질 수 있다.
    `import '.onto/Justfile'`한 파일의 `working-directory`는 불러 들인 쪽 기준이라 저장소의 상위 디렉토리가 되고, `-d`는 실행 위치를 마음대로 바꾼다.

    그래서 지식 저장소 안에서는 실행 위치를 보지 않는다. 지식 저장소에 복사된 도구는 언제나 `.onto/`에 있고, 작업 공간은 그 바로 위 디렉토리다.
    실행 위치가 저장소의 상위 디렉토리여도 그 저장소를 다루고, 저장소를 하나도 찾지 못한 채 0으로 끝나지 않는다.
    루트 저장소에서는 실행 위치가 루트 저장소다(`Justfile`이 `working-directory`로 맞춘다).

    범위는 `Justfile`이 있는 디렉토리의 이름으로 가려 넘기지만 도구는 자기가 어디 있는지 안다. 둘이 맞지 않으면 엉뚱한 범위로
    조용히 일하지 않고 바른 명령을 알리며 멈춘다. 도구가 어느 쪽에도 있지 않으면(루트 저장소의 `onto/`가 아닌 다른 곳에 둔 사본) 받은 범위를 믿는다.
    """
    if TOOL_DIR.name == MANAGED_DIR:  # 지식 저장소에 복사된 도구
        if args.within is not Within.REPOSITORY:
            raise OntoError(_mismatch(args.command, args.within, Path.cwd().resolve()))
        return Workspace(TOOL_DIR.parent, Within.REPOSITORY)
    root = Path.cwd().resolve()
    if args.within is Within.REPOSITORY and TOOL_DIR == (root / ROOT_TREE).resolve():  # 루트 저장소의 도구
        raise OntoError(_mismatch(args.command, args.within, root))
    return Workspace(root, args.within)


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
