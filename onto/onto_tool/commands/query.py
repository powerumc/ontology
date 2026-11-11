"""`query`: SPARQL로 그래프를 질의한다. 실행할 때마다 현재 파일에서 다시 컴파일한다."""

import argparse
import sys
from pathlib import Path

from rdflib import Literal, URIRef
from rdflib.term import Node

from ..compiler import compile_workspace
from ..errors import OntoError
from ..inference import infer
from ..workspace import Workspace
from ._output import warn
from ._rules import ensure_valid

NAME = "query"
HELP = (
    "SPARQL 질의를 실행한다. 하위 클래스, 역관계, 추이 관계가 추론된 그래프를 질의한다. "
    "SELECT 결과의 엔티티는 루트 저장소 기준 파일 경로로 나온다. "
    "CONSTRUCT와 DESCRIBE는 Turtle로 나오고, 엔티티의 IRI가 가리키는 파일이 주석으로 붙는다. "
    "읽을 수 없는 파일이 있으면 멈춘다. 다만 그 문제를 보고하는 검사 항목이 그 지식 저장소의 규칙에서 오류일 때만 멈추고, 꺼졌거나 경고이면 그 파일을 건너뛰고 표준 오류로 알린다"
)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("sparql", help="SPARQL 질의문 하나")


def run(args: argparse.Namespace) -> int:
    workspace = Workspace(Path.cwd())
    compiled = compile_workspace(workspace)
    warn(compiled.warnings)
    warn(compiled.notices)
    ensure_valid(workspace, compiled)
    graph = infer(compiled.graph)
    # 질의 결과에서 `Source` 엔티티는 원본 문서의 파일 경로로 보인다
    files = {**compiled.files, **compiled.source_files}
    try:
        result = graph.query(args.sparql)
    except Exception as exc:  # rdflib은 문법 오류와 평가 오류를 여러 예외 형식으로 던진다
        raise OntoError(f"SPARQL 질의를 처리하지 못했다: {exc}") from exc

    if result.type == "SELECT":
        print("\t".join(str(variable) for variable in result.vars))
        for row in result:
            print("\t".join(_cell(row[variable], files) for variable in result.vars))
    elif result.type == "ASK":
        print("true" if result.askAnswer else "false")
    else:  # CONSTRUCT, DESCRIBE
        for prefix, namespace in graph.namespaces():
            result.graph.bind(prefix, namespace)
        # Turtle 본문에는 파일 경로를 넣을 수 없다. 엔티티의 IRI가 가리키는 파일을 주석으로 앞에 붙인다.
        mentioned = {str(term) for triple in result.graph for term in triple if isinstance(term, URIRef)}
        for iri in sorted(mentioned & files.keys()):
            print(f"# <{iri}> {files[iri]}")
        print()
        sys.stdout.write(result.graph.serialize(format="turtle"))
    return 0


def _cell(value: Node | None, files: dict[str, str]) -> str:
    """결과 한 칸의 글자. 엔티티는 파일 경로로, 그 밖의 IRI는 그대로 보여 준다."""
    if value is None:
        return ""
    if isinstance(value, URIRef):
        return files.get(str(value), str(value))
    if isinstance(value, Literal):
        return _escape(str(value))
    return f"_:{value}"


def _escape(text: str) -> str:
    """한 줄에 한 행, 한 행에 탭으로 나눈 칸이 유지되도록 줄바꿈·탭·역슬래시를 이스케이프한다."""
    return text.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")
