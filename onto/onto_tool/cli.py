"""명령줄 진입점. `python -m onto_tool <명령> …`"""

import argparse
import logging
import sys

from .commands import build, query, validate
from .errors import OntoError

# 새 명령은 모듈을 만들어 여기에 더한다(규약은 commands/__init__.py).
COMMANDS = (build, query, validate)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="onto", description="모듈형 온톨로지 도구")
    subcommands = parser.add_subparsers(dest="command", required=True, metavar="명령")
    for command in COMMANDS:
        subparser = subcommands.add_parser(command.NAME, help=command.HELP, description=command.HELP)
        command.add_arguments(subparser)
        subparser.set_defaults(run=command.run)
    return parser


def main(argv: list[str] | None = None) -> int:
    # 날짜 값의 종류(xsd:date)를 어긴 값마다 rdflib이 변환 실패를 traceback과 함께 로그로 남긴다.
    # 값의 종류 검사는 스크립트 검사의 몫이라, 컴파일과 질의가 도구가 고장 난 것처럼 보이는 출력을 내지 않게 한다.
    logging.getLogger("rdflib.term").setLevel(logging.ERROR)
    # 한국어가 깨지지 않도록 출력 인코딩을 로케일에 맡기지 않는다.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    args = make_parser().parse_args(argv)
    try:
        return args.run(args)
    except OntoError as exc:
        for message in exc.messages:
            print(f"오류: {message}", file=sys.stderr)
        return 1
