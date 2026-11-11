"""`build`: 그래프를 컴파일하고 추론해 도구 디렉토리의 `.build/graph.ttl`로 남기고, 지식 저장소마다 인덱스를 만든다."""

import argparse
import os
from pathlib import Path

from .. import index
from ..compiler import compile_workspace
from ..errors import OntoError
from ..inference import infer
from ..paths import ALL_INDEX_FILE, BUILD_DIR, GRAPH_FILE
from ..workspace import Workspace
from ._output import warn

NAME = "build"
HELP = (
    "지식 저장소의 페이지를 그래프로 컴파일하고 추론해 도구 디렉토리의 .build/graph.ttl로 남긴다. "
    "지식 저장소마다 온톨로지 층에 인덱스(docs/ontology/index.md)를 만든다. 인덱스는 생성물이지만 커밋하는 파일이다. "
    "모든 지식 저장소를 모은 전체 인덱스는 도구 디렉토리의 .build/index.md로 남긴다"
)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    pass


def run(args: argparse.Namespace) -> int:
    workspace = Workspace(Path.cwd())
    compiled = compile_workspace(workspace)
    warn(compiled.warnings)
    compiled.ensure_valid()

    # 아무것도 쓰기 전에, 인덱스를 쓸 수 없는 경로(심볼릭 링크 등)를 모두 모아 알린다. 그래프만 쓰고 멈추지 않는다.
    contents = index.collect(compiled)
    paths = {record.index_file: record for record in compiled.records}
    blocked = [
        f"{content.index_file}: 인덱스를 쓰지 않았다. {paths[content.index_file].index_problem}"
        for content in contents
        if paths[content.index_file].index_problem is not None
    ]
    if blocked:
        raise OntoError(*blocked)

    graph = infer(compiled.graph)
    GRAPH_FILE.parent.mkdir(parents=True, exist_ok=True)
    GRAPH_FILE.write_text(graph.serialize(format="turtle"), encoding="utf-8", newline="\n")
    print(
        f"컴파일했다: {workspace.display(GRAPH_FILE)} "
        f"(지식 저장소 {len(compiled.repositories)}개, 엔티티 {len(compiled.files)}개, "
        f"트리플 {len(graph)}개, 그 가운데 추론된 것 {len(graph) - len(compiled.graph)}개)"
    )

    for content in contents:
        path = workspace.root / content.index_file
        print(f"인덱스: {content.index_file} ({_write(path, index.render(content))})")
    # 전체 인덱스 파일(.build/ 안)에서 페이지 파일로 가는 상대 경로
    all_text = index.render_all(contents, lambda file: Path(os.path.relpath(workspace.root / file, BUILD_DIR)).as_posix())
    print(f"전체 인덱스: {workspace.display(ALL_INDEX_FILE)} ({_write(ALL_INDEX_FILE, all_text)})")
    return 0


def _write(path: Path, text: str) -> str:
    """`text`를 `path`에 쓴다. 이미 같은 글자면 파일을 다시 쓰지 않는다. 무엇을 했는지 짧게 돌려준다."""
    # 줄바꿈은 운영체제와 무관하게 `\n`이다. 읽을 때도 `\n`으로 통일하므로(`compiler`) 같은 글자로 비교된다.
    existing = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None
    if existing == text:
        return "그대로"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return "새로 만들었다" if existing is None else "고쳤다"
