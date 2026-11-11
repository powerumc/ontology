"""규칙을 읽는 명령이 같이 쓰는 것: 루트 기본 규칙을 읽고, 틀렸으면 파일과 키를 알리는 오류로 바꾼다."""

from ..checks import load_root_rules
from ..errors import OntoError
from ..paths import RULES_FILE
from ..rules import Rules, RulesError
from ..workspace import Workspace


def root_rules(workspace: Workspace) -> Rules:
    try:
        return load_root_rules(RULES_FILE)
    except RulesError as exc:
        where = workspace.display(RULES_FILE)
        raise OntoError(*(f"{where}: {message}" for message in exc.messages)) from exc
