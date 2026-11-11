"""`build`: 그래프를 컴파일하고 추론해 도구 디렉토리의 `.build/graph.ttl`로 남긴다."""

import argparse
from pathlib import Path

from ..compiler import compile_workspace
from ..inference import infer
from ..paths import GRAPH_FILE
from ..workspace import Workspace
from ._output import warn

NAME = "build"
HELP = "지식 저장소의 페이지를 그래프로 컴파일하고 추론해 도구 디렉토리의 .build/graph.ttl로 남긴다"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    pass


def run(args: argparse.Namespace) -> int:
    workspace = Workspace(Path.cwd())
    compiled = compile_workspace(workspace)
    warn(compiled.warnings)
    compiled.ensure_valid()

    graph = infer(compiled.graph)
    GRAPH_FILE.parent.mkdir(parents=True, exist_ok=True)
    GRAPH_FILE.write_text(graph.serialize(format="turtle"), encoding="utf-8", newline="\n")
    print(
        f"컴파일했다: {workspace.display(GRAPH_FILE)} "
        f"(지식 저장소 {len(compiled.repositories)}개, 엔티티 {len(compiled.files)}개, "
        f"트리플 {len(graph)}개, 그 가운데 추론된 것 {len(graph) - len(compiled.graph)}개)"
    )
    return 0
