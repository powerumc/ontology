"""작업 공간을 여는 명령이 같이 쓰는 것: 현재 디렉토리와 명령줄의 `--scope`로 작업 공간을 만든다."""

import argparse
from pathlib import Path

from ..workspace import Workspace


def open_workspace(args: argparse.Namespace) -> Workspace:
    """현재 디렉토리를 `--scope`가 정한 범위의 작업 공간으로 연다.

    복사된 `Justfile`은 어디서 불러도 그 저장소의 루트에서 도구를 실행한다. 루트 저장소(`just onto …`)에서는 루트 저장소이고,
    지식 저장소 안(`just -f .onto/Justfile …`)에서는 그 지식 저장소다.
    """
    return Workspace(Path.cwd(), args.scope)
