"""`validate`: 스크립트 검사. 모든 지식 저장소를 합친 그래프와 페이지를 기계적으로 검사해 문제를 보고한다."""

import argparse
import sys

from ..checks import ACROSS_REPOSITORIES_CHECKS, Severity, validate
from ..compiler import compile_workspace
from ..workspace import Scope
from ._output import warn
from ._rules import root_rules
from ._workspace import open_workspace

NAME = "validate"
HELP = (
    "스크립트 검사. 모든 지식 저장소를 합친 그래프와 페이지를 기계적으로 검사한다. 지식 저장소 안에서는 그 저장소만 검사하고, "
    "여러 지식 저장소에 걸친 검사(교차 참조, 공유 범위, 저장소 간 중복)는 건너뛰었다고 알린다. 실행할 때마다 현재 파일에서 다시 컴파일하며, "
    "이전 build의 결과를 쓰지 않는다. 문제는 한 줄에 하나, 탭으로 나눈 다섯 칸(심각도, 지식 저장소, 페이지, 검사 항목, 설명)으로 "
    "보고한다. 지식 저장소 칸은 서브모듈 디렉토리 이름이고, 페이지 칸은 작업 공간 기준 경로다(루트 저장소에서는 루트 기준, 지식 저장소 안에서는 그 저장소 기준). "
    "검사 항목의 켬/끔과 심각도는 규칙(루트의 rules.yaml, 지식 저장소의 ontology.yaml이 덮어쓴 값)을 따른다. "
    "오류가 하나라도 있으면 0이 아닌 종료 코드로 끝나고, 경고만 있으면 0이다. 문제가 없으면 아무것도 출력하지 않는다. "
    "어떤 파일도 고치지 않는다"
)

_SKIPPED_NOTICE = (
    "지식 저장소 안에서 실행해 이 저장소만 검사했다. 여러 지식 저장소에 걸친 검사(교차 참조, 공유 범위, 저장소 간 중복)는 건너뛰었다: {checks}. "
    "다른 저장소를 가리키는 교차 참조는 검사하지 않았다. 루트 저장소에서 `just onto validate`로 전체를 검사한다"
)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    pass


def run(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    rules = root_rules(workspace)  # 기본 규칙이 틀렸으면 검사하지 않고 알린다
    # 컴파일의 `warnings`는 검사 항목이 같은 내용을 문제로 보고하므로 따로 출력하지 않는다.
    compiled = compile_workspace(workspace)
    warn(compiled.notices)
    if workspace.scope is Scope.REPOSITORY:
        warn([_SKIPPED_NOTICE.format(checks=", ".join(f"`{name}`" for name in ACROSS_REPOSITORIES_CHECKS))])
    findings = validate(compiled, rules)
    for finding in findings:
        print("\t".join((finding.severity.value, finding.repository, finding.file, finding.check, _one_line(finding.message))))
    errors = sum(finding.severity is Severity.ERROR for finding in findings)
    if findings:
        sys.stdout.flush()  # 터미널에서 보고가 요약보다 먼저 보이게 한다
        print(f"스크립트 검사: 오류 {errors}개, 경고 {len(findings) - errors}개", file=sys.stderr)
    return 1 if errors else 0


def _one_line(message: str) -> str:
    """한 줄에 문제 하나, 탭으로 나눈 칸이 유지되도록 설명의 줄바꿈과 탭을 공백으로 바꾼다."""
    return " ".join(message.split())
