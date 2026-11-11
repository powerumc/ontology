"""규칙을 읽는 명령이 같이 쓰는 것: 루트 기본 규칙을 읽고, 틀렸으면 파일과 키를 알리는 오류로 바꾼다."""

from ..checks import applied_rules, load_root_rules, split_problems
from ..checks.model import repository_of
from ..compiler import Compiled
from ..errors import OntoError
from ..paths import RULES_FILE
from ..rules import RuleSet, Rules, RulesError
from ..workspace import Workspace
from ._output import warn


def root_rules(workspace: Workspace) -> Rules:
    try:
        return load_root_rules(RULES_FILE)
    except RulesError as exc:
        where = workspace.display(RULES_FILE)
        raise OntoError(*(f"{where}: {message}" for message in exc.messages)) from exc


def ensure_valid(workspace: Workspace, compiled: Compiled) -> RuleSet:
    """컴파일 결과를 그래프로 쓸 수 있는지 확인하고, 지식 저장소마다 적용되는 규칙을 돌려준다.

    읽을 수 없는 파일이 있으면 일부만 컴파일한 그래프를 내놓지 않으려고 멈춘다(`OntoError`). 다만 그 파일이 있는 지식 저장소의 규칙에서
    그 문제를 보고하는 검사 항목이 오류일 때만 멈춘다(루트 전용 항목은 루트의 값). 꺼졌거나 경고이면 멈추지 않고 그 파일을 건너뛰며,
    건너뛴 파일은 표준 오류로 알린다. 그래서 `validate`가 0으로 끝나면 읽을 수 없는 파일 때문에 `build`나 `query`가 멈추는 일은 없다.
    """
    applied = applied_rules(compiled, root_rules(workspace))
    blocking, skipped = split_problems(compiled, applied)
    if blocking:
        raise OntoError(*(str(problem) for problem in blocking))
    notes = []
    for problem in skipped:
        enabled = applied.of(repository_of(problem.file)).checks[problem.check].enabled
        why = "규칙에서 꺼 둔" if not enabled else "규칙에서 경고로 정한"
        notes.append(f"{problem} ({why} 검사 항목 `{problem.check}`의 문제라 건너뛰었다)")
    warn(notes)
    return applied
