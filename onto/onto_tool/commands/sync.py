"""`sync`: 루트 저장소의 기능을 지식 저장소에 복사하거나 최신화한다. 루트 저장소에서만 실행한다."""

import argparse
import sys

from .. import vocab
from ..checks import Finding
from ..conformance import nonconforming
from ..errors import OntoError
from ..managed import MANAGED_DIR, MANAGED_TREES, ROOT_TREE, collect_sources, untracked_sources
from ..paths import TOOL_DIR
from ..sync import Result, sync_repository
from ..workspace import Within, Workspace
from ._output import warn
from ._rules import root_rules
from ._workspace import open_workspace

NAME = "sync"
HELP = (
    "루트 저장소의 기능을 지식 저장소에 복사하거나 최신화한다. 루트 저장소의 onto/(추적하는 파일만)를 지식 저장소의 .onto/로 복사하고, "
    "지식 저장소의 .gitignore에 표시된 블록으로 .onto/를 제외하고, 프로젝트 지침 파일(CLAUDE.md, 없으면 AGENTS.md, 둘 다 없으면 AGENTS.md를 만든다)에는 "
    "온톨로지 층의 인덱스를 가리키는 표시된 블록을 넣으며(블록 밖은 바꾸지 않는다), 없으면 온톨로지 층의 뼈대(docs/ontology/ontology.yaml과 인덱스)를 만든다. "
    "이름(서브모듈 디렉토리 이름)을 생략하면 모든 지식 저장소에 적용한다. 마지막 최신화 뒤에 손으로 고친 루트 관리 파일은 덮어쓰지 않고 보고한다. "
    "저장소 소유 파일(ontology.yaml, 페이지)은 바꾸지 않는다. 변경은 지식 저장소의 작업 트리에 남고 커밋하지 않는다. "
    "끝에 최신화한 저장소의 페이지와 ontology.yaml(하위 클래스 선언) 가운데 새 구조 제약에 어긋난 것을 보고한다(validate와 같은 다섯 칸. 종료 코드는 바꾸지 않는다). "
    "저장소마다 만든 파일, 바꾼 파일, 지운 파일, 건너뛴 파일을 요약한다. 건너뛴 파일은 하나씩 이유와 함께 보여 주고(같은 위치가 막은 파일만 묶는다), "
    "건너뛴 것이 있거나 사람이 확인할 것(지식 저장소가 이미 추적하는 .onto/)이 있으면 0이 아닌 종료 코드로 끝난다. "
    "루트 저장소에서만 쓸 수 있고 지식 저장소 안에서는 거부한다"
)

# 한 가지 동작이 이 수보다 많은 루트 관리 파일에 걸치면 파일마다 적지 않고 묶어서 적는다(처음 복사할 때 수십 줄이 쏟아지지 않게 한다).
LISTED_LIMIT = 10
UNTRACKED_SHOWN = 5  # 추적하지 않는 파일을 경고에 보여 주는 수


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("repository", nargs="?", help="지식 저장소의 이름(서브모듈 디렉토리 이름). 생략하면 모든 지식 저장소")


def run(args: argparse.Namespace) -> int:
    workspace = open_workspace(args)
    _require_root(workspace)

    repositories = workspace.repositories()
    if args.repository is not None:
        known = {repository.directory: repository for repository in repositories}
        if args.repository not in known:
            raise OntoError(f"지식 저장소 `{args.repository}`가 없다(있는 것: {', '.join(known) or '없음'})")
        repositories = [known[args.repository]]
    if not repositories:
        print("지식 저장소가 없다")
        return 0

    sources = collect_sources(workspace.root)
    if untracked := untracked_sources(workspace.root):  # 동작은 바꾸지 않는다. 고친 코드가 빠진 파일을 가져다 쓰면 지식 저장소의 도구가 깨진다
        shown = ", ".join(untracked[:UNTRACKED_SHOWN]) + (f" 외 {len(untracked) - UNTRACKED_SHOWN}개" if len(untracked) > UNTRACKED_SHOWN else "")
        warn([f"루트의 `{ROOT_TREE}/`에 추적하지 않는 파일이 있어 복사하지 않았다: {shown}. 복사하려면 `git add`한다"])
    results = [sync_repository(workspace, repository, sources) for repository in repositories]
    for result in results:
        _print(result)
    print(_total(results))
    # 지식 저장소의 도구와 공통 어휘가 루트의 것으로 바뀌었다. 새 구조 제약에 어긋나게 된 페이지는 저장소 소유 파일이라 고치지 않고 알린다.
    _print_nonconforming(nonconforming(workspace, [result.repository for result in results], root_rules(workspace)))
    sys.stdout.flush()  # 출력이 파이프로 갈 때 아래 오류(표준 오류)가 요약보다 먼저 나오지 않게 한다

    incomplete = [result.repository for result in results if not result.complete]
    pending = [result.repository for result in results if result.complete and result.attention]
    if incomplete:
        print(
            f"오류: 건너뛴 파일이 있어 최신화를 마치지 못한 지식 저장소: {', '.join(incomplete)}. 이유는 위의 `건너뜀` 줄에 있다",
            file=sys.stderr,
        )
    if pending:
        print(
            f"오류: 최신화는 마쳤지만 확인이 필요한 지식 저장소: {', '.join(pending)}. 이유는 위의 `확인 필요` 줄에 있다",
            file=sys.stderr,
        )
    return 1 if incomplete or pending else 0


def _require_root(workspace: Workspace) -> None:
    """루트 저장소의 `onto/`에서 도는지 본다. 지식 저장소 안(`just -f .onto/Justfile`)에서는 거부한다. 루트 저장소가 복사의 원본이다."""
    if workspace.within is Within.REPOSITORY:
        raise OntoError(
            "`sync`는 루트 저장소에서만 쓸 수 있다. 지식 저장소의 `.onto/`는 루트 저장소가 복사해 준 사본이다. "
            "루트 저장소에서 `just onto sync [이름]`을 실행한다"
        )
    if TOOL_DIR != (workspace.root / ROOT_TREE).resolve():
        raise OntoError(f"`sync`는 루트 저장소의 `{ROOT_TREE}/`에서 실행해야 한다(도구는 {TOOL_DIR}에 있고 실행 위치는 {workspace.root}이다)")


def _print(result: Result) -> None:
    if result.unchanged:
        print(f"{result.repository}: 바뀐 것이 없다")
        return
    counts = (len(result.created), len(result.changed), len(result.removed), len(result.skipped), len(result.attention))
    print(f"{result.repository}: {_summary(*counts)}")
    for verb, paths in (("만듦", result.created), ("바꿈", result.changed), ("지움", result.removed)):
        for line in _lines(paths):
            print(f"  {verb}  {line}")
    # 같은 위치(링크, 디렉토리가 아닌 조각)가 막은 파일은 같은 이유끼리 묶는다(링크 하나가 수십 파일을 막아도 한 줄이다).
    # 그 밖의 건너뛴 파일은 하나하나가 사람이 챙길 파일(손으로 고친 파일 등)이라 이유와 함께 하나씩 적는다.
    shared: dict[str, list[str]] = {}
    for skip in result.skipped:
        if skip.shared:
            shared.setdefault(skip.reason, []).append(skip.path)
    for skip in result.skipped:
        if not skip.shared:
            print(f"  건너뜀  {skip.path} — {skip.reason}")
        elif paths := shared.pop(skip.reason, None):
            for line in _lines(paths):
                print(f"  건너뜀  {line} — {skip.reason}")
    for path, reason in result.attention:
        print(f"  확인 필요  {path} — {reason}")


def _print_nonconforming(findings: list[Finding]) -> None:
    """최신화한 지식 저장소에서 구조 제약에 어긋난 페이지와 하위 클래스 선언. 문제 하나에 한 줄이고 `validate`의 보고와 같은 모양(탭으로 나눈 다섯 칸)이다."""
    if not findings:
        return
    files = len({finding.file for finding in findings})
    print(
        f"구조 제약에 어긋난 파일 {files}개(공통 어휘 {vocab.version() or '버전을 알 수 없음'}). 페이지와 `ontology.yaml`은 저장소 소유 파일이라 "
        "최신화가 고치지 않는다. 고친 뒤 `just onto validate`로 확인한다"
    )
    for finding in findings:
        print("\t".join((finding.severity.value, finding.repository, finding.file, finding.check, " ".join(finding.message.split()))))


def _summary(created: int, changed: int, removed: int, skipped: int, attention: int = 0) -> str:
    text = f"만든 파일 {created}개, 바꾼 파일 {changed}개, 지운 파일 {removed}개, 건너뛴 파일 {skipped}개"
    return f"{text}, 확인할 것 {attention}개" if attention else text


def _lines(paths: list[str]) -> list[str]:
    """보여 줄 줄. 루트 관리 파일이 많으면 위치별로 묶고, 그 밖의 파일(`.gitignore`, `ontology.yaml`, 인덱스)은 하나씩 적는다."""
    prefixes = tuple(f"{target}/" for _, target in MANAGED_TREES)
    managed = [path for path in paths if path.startswith(prefixes)]
    if len(managed) <= LISTED_LIMIT:
        return paths
    grouped = [f"{prefix} 아래 파일 {count}개" for prefix in prefixes if (count := sum(path.startswith(prefix) for path in managed))]
    return [path for path in paths if path not in managed] + grouped


def _total(results: list[Result]) -> str:
    counts = (sum(len(getattr(result, kind)) for result in results) for kind in ("created", "changed", "removed", "skipped", "attention"))
    return f"최신화: 지식 저장소 {len(results)}개, {_summary(*counts)}"
