"""`build`: 그래프를 컴파일해 `build/graph.ttl`로 남긴다."""

import argparse
from pathlib import Path

from ..compiler import compile_workspace
from ..workspace import Workspace
from ._output import warn

NAME = "build"
HELP = "지식 저장소의 페이지를 그래프로 컴파일하고 build/graph.ttl로 남긴다"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    pass


def run(args: argparse.Namespace) -> int:
    workspace = Workspace(Path.cwd())
    compiled = compile_workspace(workspace)
    warn(compiled.warnings)

    target = workspace.graph_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(compiled.graph.serialize(format="turtle"), encoding="utf-8", newline="\n")
    print(
        f"컴파일했다: {workspace.relative(target)} "
        f"(지식 저장소 {len(compiled.repositories)}개, 엔티티 {len(compiled.files)}개, 트리플 {len(compiled.graph)}개)"
    )
    return 0
