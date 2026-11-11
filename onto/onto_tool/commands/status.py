"""`status`: ingest할 대상, 곧 새로 생겼거나 바뀐 원본 문서를 지식 저장소별로 보여 준다. 어떤 파일도 고치지 않는다."""

import argparse
import sys

from ..compiler import compile_workspace
from ..status import CHANGED, NEW, collect
from ._output import warn
from ._rules import ensure_valid
from ._workspace import open_workspace

NAME = "status"
HELP = (
    "ingest할 대상, 곧 새로 생겼거나 바뀐 원본 문서를 지식 저장소별로 보여 준다. 실행할 때마다 현재 파일에서 다시 컴파일하며, "
    "이전 build의 결과를 쓰지 않는다. 문서 하나에 한 줄이고, 탭으로 나눈 다섯 칸(상태, 지식 저장소, 원본 문서, 현재 해시, 설명)이다. "
    "상태는 `새 문서`(어떤 페이지도 근거로 삼지 않았고 넘긴 문서의 목록에도 없다)와 `바뀐 문서`(기록한 해시와 달라졌다. 그것을 근거로 한 "
    "낡은 페이지와, 넘긴 문서였다면 그 사실을 설명에 적는다)다. 원본 문서는 지식 저장소 루트 기준 경로이고, 현재 해시는 git이 기록할 blob "
    "해시(작업 트리의 지금 내용, 커밋하지 않은 수정 포함)라 그대로 페이지의 derivedFrom(path, hash)에 적을 수 있다. 저장소의 blob에 CRLF가 "
    "들어 있지 않은 문서는 깨끗한 클론의 git rev-parse HEAD:<경로>와 같지만, 이미 CRLF로 커밋된 문서는 core.autocrlf나 .gitattributes의 text=auto에 "
    "따라 git rev-parse와 다르고 기기마다 다를 수 있다(해시는 git rev-parse가 아니라 이 명령이 낸 값을 쓴다). 대상은 규칙의 sources(글롭과 제외 경로, "
    "지식 저장소의 ontology.yaml이 덮어쓴 값 포함)를 따르고 온톨로지 층은 항상 빠진다. 바뀐 것이 없으면 그렇다고 알린다. "
    "읽을 수 없는 파일과 틀린 rules는 build와 같은 방식으로 알린다. 어떤 파일도 고치지 않는다(git hash-object는 -w 없이 쓴다)"
)

NOTHING = "새로 생겼거나 바뀐 원본 문서가 없다"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    pass


def run(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    compiled = compile_workspace(workspace)
    warn(compiled.warnings)
    warn(compiled.notices)
    rules = ensure_valid(workspace, compiled)  # 읽을 수 없는 페이지가 있으면 어떤 문서를 근거로 삼았는지 알 수 없다
    entries, notices = collect(workspace, compiled, rules)
    warn(notices)

    for entry in entries:
        print("\t".join(_cell(text) for text in (entry.state, entry.repository, entry.path, entry.hash, entry.detail)))
    sys.stdout.flush()  # 터미널에서 보고가 요약과 오류보다 먼저 보이게 한다

    # 틀린 rules는 기본값으로 대신하지 않고 알린다. 그 저장소의 대상 범위를 알 수 없기 때문이다.
    broken = [record for record in compiled.records if record.directory in rules.problems]
    for record in broken:
        for reason in rules.problems[record.directory]:
            print(f"오류: {record.yaml_file}: {reason}", file=sys.stderr)
    if entries:
        new = sum(entry.state == NEW for entry in entries)
        print(f"원본 문서: {NEW} {new}개, {CHANGED} {len(entries) - new}개", file=sys.stderr)
    elif not broken:
        print(NOTHING)
    return 1 if broken else 0


def _cell(text: str) -> str:
    """한 줄에 문서 하나, 탭으로 나눈 칸이 유지되도록 칸 안의 탭과 줄바꿈을 이스케이프한다."""
    return text.replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")
