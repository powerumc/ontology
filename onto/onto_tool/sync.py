"""최신화: 루트 저장소의 기능을 지식 저장소에 복사한다(ADR 0005).

지식 저장소에는 온톨로지 기능이 없다. 루트 저장소의 `onto/`(도구, 공통 어휘, 구조 제약, 기본 규칙, 템플릿, 규약 문서)를
지식 저장소의 `.onto/`로 복사하고, 온톨로지 층의 뼈대를 만들어 준다. 지식 저장소의 파일은 셋으로 나뉜다.

- **루트 관리 파일**: `.onto/` 아래의 사본. 최신화 때마다 루트의 내용으로 덮어쓰고, 지식 저장소의 `.gitignore`로 제외해
  그 저장소의 커밋에 들어가지 않게 한다. 복사하는 것은 루트 저장소가 추적(`git ls-files`)하는 `onto/` 파일뿐이다.
  루트의 가상환경이나 캐시는 추적하지 않으므로 복사되지 않고, 지식 저장소의 `.onto/`에서 도구를 돌려 생긴 가상환경, 캐시, 빌드 산출물은
  루트 관리 파일이 아니라 건드리지 않는다.
- **표시된 블록**: 지식 저장소가 추적하는 파일 안의 블록(`.gitignore`, 프로젝트 지침 파일). 블록만 루트가 관리하고 블록 밖은 건드리지 않는다(`blocks`).
  프로젝트 지침 파일(`CLAUDE.md`, 없으면 `AGENTS.md`, 둘 다 없으면 `AGENTS.md`를 만든다)의 블록은 온톨로지 층의 인덱스를 가리킨다(`guidance`).
  커밋하지 않은 수정이 있어도 블록만 교체한다. 블록이 지침 파일에 만든 수정이 다음 최신화를 막지 않는다.
- **저장소 소유 파일**: `docs/ontology/ontology.yaml`, 인덱스. 없을 때 한 번만 만들고 이후 건드리지 않는다. 지식 저장소의 `Justfile`도 건드리지 않는다.

손으로 고친 루트 관리 파일은 마지막 최신화 때의 기록과 비교해 가려낸다. 루트 관리 파일은 git이 추적하지 않아 git으로는 알 수 없기 때문이다.
기록(`RECORD_FILE`)은 최신화가 파일마다 쓴 내용의 지문이다. 지금 파일이 기록과 같으면 손대지 않은 것이라 덮어쓰고,
다르면 손으로 고친 것이라 덮어쓰지 않고 보고한다. 기록에 없는 파일이 루트의 내용과 다르면, 누가 만든 것인지 알 수 없으므로 똑같이 보고한다.
보고된 파일은 지우면 다음 최신화가 루트의 내용으로 되살린다.

변경은 지식 저장소의 작업 트리에 남기고 커밋하지 않는다. 같은 입력에서 두 번 실행하면 두 번째는 아무 파일도 다시 쓰지 않는다.
루트 관리 파일이 무엇이고 사본이 루트와 같은지는 `managed`가 읽는다. 최신화 뒤에 구조 제약에 어긋난 페이지와 하위 클래스 선언을 알리는 것은 `conformance`다(`commands.sync`가 부른다).
지식 저장소의 어느 경로든 심볼릭 링크를 따라가거나 일반 파일이 아닌 것을 덮어쓰지 않는다. 쓰거나 지우는 경로가 저장소 밖으로 새지 않게 한다.
"""

import json
import os
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import gitenv, guidance, index
from .blocks import BlockError, MarkedBlock, replace_block
from .commands._rules import ensure_valid
from .compiler import compile_workspace
from .errors import OntoError
from .managed import (
    MANAGED_DIR,
    MANAGED_TREES,
    RECORD_FILE,
    Source,
    blocked,
    fingerprint_of,
    is_repository,
    read_record,
)
from .pages import INDEX_FILE
from .workspace import ONTOLOGY_DIR, ONTOLOGY_YAML, Repository, SubsetWorkspace, Workspace

GITIGNORE = ".gitignore"
GITIGNORE_BLOCK = MarkedBlock(
    "# onto:begin", "# onto:end", " 루트 저장소가 관리하는 블록이다. `onto sync`가 이 블록만 고친다. 손으로 고치지 않는다."
)
# 지식 저장소의 커밋에 들어가지 않을 루트 관리 파일의 경로. 지식 저장소의 루트에 고정한다(`/`로 시작).
IGNORED_PATHS = (f"/{MANAGED_DIR}/", "/.claude/skills/onto-*/")

ONTOLOGY_YAML_PATH = ONTOLOGY_YAML.as_posix()
INDEX_PATH = (ONTOLOGY_DIR / INDEX_FILE).as_posix()


@dataclass(frozen=True)
class Skip:
    """건너뛴 루트 관리 파일이나 저장소 소유 파일 하나. 경로는 지식 저장소 기준이다."""

    path: str
    reason: str
    # 같은 위치가 막은 파일이다(심볼릭 링크나 디렉토리가 아닌 조각). 이유가 막은 위치를 가리키므로 같은 이유의 파일을 묶어 한 줄로 보여 줘도 된다.
    # 아닌 파일(손으로 고친 파일, 쓸 수 없는 파일)은 하나하나가 사람이 챙길 파일이라 묶지 않는다.
    shared: bool = False


@dataclass
class Result:
    """지식 저장소 하나를 최신화한 결과. 경로는 모두 그 지식 저장소 기준이다."""

    repository: str
    created: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    skipped: list[Skip] = field(default_factory=list)
    # 확인이 필요한 것(경로, 이유). 최신화는 이것 때문에 건너뛴 것이 없지만 지식 저장소의 git 상태가 어긋난 채 남는다.
    attention: list[tuple[str, str]] = field(default_factory=list)

    def skip(self, path: str, reason: str, *, shared: bool = False) -> None:
        self.skipped.append(Skip(path, reason, shared))

    @property
    def complete(self) -> bool:
        """건너뛴 것이 없다. 건너뛴 파일이 있으면 지식 저장소는 루트와 어긋난 채로 남는다."""
        return not self.skipped

    @property
    def unchanged(self) -> bool:
        return not (self.created or self.changed or self.removed or self.skipped or self.attention)


# --- 지식 저장소 하나 ------------------------------------------------------------------


def sync_repository(workspace: Workspace, repository: Repository, sources: dict[str, Source]) -> Result:
    result = Result(repository.directory)
    path = repository.path
    if not is_repository(path):
        result.skip(workspace.relative(path), "초기화되지 않은 서브모듈이거나 지식 저장소가 아니라 건너뛰었다. `just setup`으로 초기화한다")
        return result

    # `.gitignore`가 먼저다. 제외하지 못한 채 `.onto/`를 복사하면 루트 관리 파일이 지식 저장소의 git 상태에 나타나 커밋될 수 있다.
    if not _update_gitignore(path, result):
        return result
    _report_tracked(path, result)
    if _create_ontology_yaml(path, repository.directory, result):
        _create_index(workspace, repository, result)
        _update_guidance(path, result)
    _copy_managed_files(path, sources, result)
    return result


def _report_tracked(repo: Path, result: Result) -> None:
    """지식 저장소의 git이 루트 관리 파일의 위치를 이미 추적하고 있으면 알린다. 복사는 계속한다.

    `.gitignore`는 추적하는 파일을 제외하지 못한다. 누가 블록이 없는 사이에 `git add -A`로 `.onto/`를 커밋했다면, 블록을 되살려도 그 위치의 변경이
    git 상태에 계속 나타난다. 추적에서 빼는 것은 지식 저장소의 이력을 바꾸는 일이라 최신화가 하지 않고, 방법을 알린다.
    """
    for _, target_dir in MANAGED_TREES:
        if _is_tracked(repo, target_dir):
            result.attention.append(
                (
                    f"{target_dir}/",
                    f"이 저장소의 git이 이미 추적하고 있어 `.gitignore`가 제외하지 못하고 변경이 git 상태에 나타난다. "
                    f"추적에서 뺀다(파일은 남는다): `git rm -r --cached {target_dir}`",
                )
            )


def _is_tracked(repo: Path, relative: str) -> bool:
    """지식 저장소 `repo`의 git이 `relative` 아래를 추적하는가. 읽는 저장소는 `repo`이고, 환경 변수나 위의 저장소가 대신하지 않는다(`gitenv`)."""
    try:
        listing = subprocess.run(
            ["git", "--literal-pathspecs", "-C", str(repo), "ls-files", "-z", "--", relative],
            env=gitenv.environment(repo.resolve().parent),
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    return listing.returncode == 0 and bool(listing.stdout.strip(b"\0"))


def _update_gitignore(repo: Path, result: Result) -> bool:
    """`.gitignore`의 표시된 블록을 루트 관리 파일의 경로로 바꾼다. 블록 밖과 커밋 여부는 따지지 않는다. 고치지 못하면 `False`."""
    return _update_block(
        repo,
        GITIGNORE,
        GITIGNORE_BLOCK,
        IGNORED_PATHS,
        result,
        broken="`.onto/`를 복사하면 지식 저장소의 git 상태에 나타나므로 이 저장소는 최신화하지 않았다",
    )


def _update_guidance(repo: Path, result: Result) -> bool:
    """프로젝트 지침 파일(`CLAUDE.md`, 없으면 `AGENTS.md`, 둘 다 없으면 `AGENTS.md`를 만든다)의 표시된 블록을 인덱스 안내로 바꾼다.

    블록 밖과 커밋 여부는 따지지 않는다. 지침 파일에 커밋하지 않은 수정이 있어도, 직전 최신화가 넣은 블록이 있어도 블록만 고친다.
    블록의 내용이 이미 같으면 파일을 다시 쓰지 않는다. 고른 파일을 고치지 못하면 `False`다.

    지침 파일이 이 저장소 안의 일반 파일을 가리키는 심볼릭 링크이면(`ln -s AGENTS.md CLAUDE.md`) 링크를 두고 대상 파일의 블록을 고친다(`_guidance_target`).
    보고도 대상 이름으로 한다. 저장소 밖을 가리키거나 대상이 없거나 일반 파일이 아닌 링크는 따라가지 않고 건너뛴다.

    블록이 이미 든 다른 후보 파일은 그 자리에서 내용만 맞춘다. 두 후보가 같은 파일(한쪽이 다른 쪽의 링크)이면 한 번만 고친다.
    블록이 없는 다른 후보 파일, 따라갈 수 없는 링크, 일반 파일이 아닌 것은 건드리지 않는다. 블록을 새로 만들지도 지우지도 않는다.
    """
    chosen = guidance.choose(repo)
    target, reason = _guidance_target(repo, chosen)
    if target is None:
        result.skip(chosen, reason)
    done = target is not None and _update_block(repo, target, guidance.BLOCK, guidance.BODY, result)
    handled = {target}
    for name in guidance.CANDIDATES:
        if name == chosen:
            continue
        other, _ = _guidance_target(repo, name)
        if other is not None and other not in handled and _holds_block(repo, other):
            handled.add(other)
            _update_block(repo, other, guidance.BLOCK, guidance.BODY, result)
    return done


def _guidance_target(repo: Path, name: str) -> tuple[str | None, str]:
    """지침 파일 `name`의 블록을 실제로 고칠 파일의 이름(저장소 기준 경로)과, 고칠 수 없으면 그 이유를 돌려준다.

    링크가 아니면 `name` 자신이다(없으면 만들 파일이다). 링크이면 끝까지 풀어서 이 저장소 안의 일반 파일일 때만 그 파일이다. 저장소 밖을 가리키거나
    대상이 없거나(깨진 링크, 도는 링크) 일반 파일이 아니면 따라가지 않는다. `.git/`와 루트 관리 파일(`.onto/`)은 링크로 가리켜도 고치지 않는다.
    루트가 관리하는 파일에 블록을 쓰게 하지 않고, 쓰기가 저장소 밖으로 새지 않게 한다.
    """
    if not (repo / name).is_symlink():
        return name, ""
    root = repo.resolve()
    try:
        real = (repo / name).resolve(strict=True)
    except OSError:
        return None, f"`{name}`가 대상이 없는 심볼릭 링크라 따라가지 않는다"
    if not real.is_relative_to(root):
        return None, f"`{name}`가 이 저장소 밖을 가리키는 심볼릭 링크라 따라가지 않는다"
    relative = real.relative_to(root).as_posix()
    if relative.split("/")[0] in (".git", MANAGED_DIR):
        return None, f"`{name}`가 `{relative}`를 가리키는 심볼릭 링크라 따라가지 않는다. 루트 관리 파일과 git의 파일에는 블록을 쓰지 않는다"
    if not real.is_file():
        return None, f"`{name}`가 일반 파일이 아닌 것을 가리키는 심볼릭 링크라 따라가지 않는다"
    if reason := blocked(repo, relative):
        return None, f"`{name}`가 가리키는 `{relative}`를 고칠 수 없다(심볼릭 링크를 따라가지 않는다): {reason}"
    return relative, ""


def _holds_block(repo: Path, relative: str) -> bool:
    """`repo`의 일반 파일 `relative`에 표시된 블록이 있는가. 없거나 읽을 수 없거나 링크이면 아니다."""
    path = repo / relative
    if blocked(repo, relative) or not path.is_file():
        return False
    try:
        return guidance.holds_block(path.read_bytes())
    except OSError:
        return False


def _update_block(repo: Path, relative: str, block: MarkedBlock, body: Sequence[str], result: Result, *, broken: str = "") -> bool:
    """`repo`의 파일 `relative`에서 표시된 블록의 내용을 `body`로 바꾼다. 파일이 없으면 블록만 담아 만든다. 고치지 못하면 `False`.

    블록 밖은 한 글자도 바뀌지 않고, 내용이 같으면 파일을 쓰지 않는다. `broken`은 표시가 틀려 블록을 찾지 못했을 때 이유 뒤에 붙일 말이다.
    """
    if reason := blocked(repo, relative):
        result.skip(relative, reason)
        return False
    path = repo / relative
    try:
        existing = path.read_bytes() if path.exists() else None
        try:
            updated = replace_block(existing or b"", block, body)
        except BlockError as exc:
            result.skip(relative, f"{exc}. {broken}" if broken else str(exc))
            return False
        if updated != existing:
            _write(path, updated, like=path if existing is not None else None)
            (result.created if existing is None else result.changed).append(relative)
    except OSError as exc:
        result.skip(relative, f"읽거나 쓸 수 없다({exc.strerror})")
        return False
    return True


def _create_ontology_yaml(repo: Path, name: str, result: Result) -> bool:
    """`docs/ontology/ontology.yaml`이 없으면 만든다. 있으면 한 글자도 건드리지 않는다. 구성이 있으면(있었거나 만들었으면) `True`."""
    if reason := blocked(repo, ONTOLOGY_YAML_PATH):
        result.skip(ONTOLOGY_YAML_PATH, reason)
        return False
    path = repo / ONTOLOGY_YAML
    if path.exists():
        return True
    try:
        _write(path, _ontology_yaml(name).encode())
    except OSError as exc:
        result.skip(ONTOLOGY_YAML_PATH, f"쓸 수 없다({exc.strerror})")
        return False
    result.created.append(ONTOLOGY_YAML_PATH)
    return True


def _ontology_yaml(name: str) -> str:
    """새 지식 저장소의 `ontology.yaml`. `name`은 서브모듈 디렉토리 이름이고, 공유 범위는 가장 좁은 `private`이다."""
    required = yaml.safe_dump({"name": name, "scope": "private"}, allow_unicode=True, sort_keys=False, width=10**6)
    name_line, scope_line = required.splitlines()
    return f"""\
# 이 지식 저장소의 온톨로지 설정이다. 저장소 소유 파일이라 최신화가 다시 쓰지 않는다. 이 저장소에 커밋한다.
{name_line}  # 이 저장소의 이름. 서브모듈 디렉토리 이름과 같아야 하고, 다른 저장소가 `<이름>:<식별자>`로 이 저장소를 가리킨다
{scope_line}  # 공유 범위: private, team, team:<팀 이름>, public. 가장 좁은 private으로 시작한다. 저장소를 공유하는 범위에 맞게 바꾼다
# 아래는 필요할 때 쓰는 선택 키다.
# title: 프로젝트 이름          # 이 프로젝트(Project 엔티티)의 제목
# description: 한 줄 설명
# aliases: [별칭, alias]
# classes:                      # 이 저장소만의 하위 클래스
#   Invoice:
#     subClassOf: Component
# rules:                        # 루트의 기본 규칙 가운데 이 저장소에서만 바꿀 값
#   checks:
#     orphan-page: {{enabled: false}}
"""


def _create_index(workspace: Workspace, repository: Repository, result: Result) -> None:
    """인덱스(`docs/ontology/index.md`)가 없으면 만든다. 있으면 어긋났어도 건드리지 않는다(어긋남은 스크립트 검사가 알린다).

    인덱스가 없는 것은 스크립트 검사가 오류로 잡는다(`index-mismatch`). 최신화 직후의 저장소가 검사를 통과하도록 인덱스 없는 모든 저장소에 만든다.
    이 저장소의 페이지만 컴파일한다. 다른 지식 저장소의 문제가 이 저장소의 최신화를 막지 않는다.
    인덱스를 만드는 조건은 `build`와 같다(`commands._rules.ensure_valid`). `build`가 만드는 인덱스를 최신화가 못 만든다고 하지 않는다.
    """
    if reason := blocked(repository.path, INDEX_PATH):
        result.skip(INDEX_PATH, reason)
        return
    if (repository.path / INDEX_PATH).exists():
        return  # 컴파일은 느리다. 인덱스가 이미 있으면 읽지 않는다
    only = SubsetWorkspace(workspace, {repository.directory})
    compiled = compile_workspace(only)
    record = compiled.records[0]
    try:
        ensure_valid(only, compiled)  # `build`와 같은 판정이다. 규칙에서 오류인 읽기 문제가 있을 때만 멈추고, 경고이거나 꺼진 문제의 파일은 건너뛰고 만든다
    except OntoError as exc:
        more = f" 외 {len(exc.messages) - 1}개" if len(exc.messages) > 1 else ""
        result.skip(INDEX_PATH, f"읽을 수 없는 파일이 있어 인덱스를 만들지 못했다: {exc.messages[0]}{more}. 고친 뒤 `onto build`로 만든다")
        return
    content = next((content for content in index.collect(compiled) if content.index_file == record.index_file), None)
    if content is None:
        result.skip(INDEX_PATH, "저장소 이름을 알 수 없어 인덱스를 만들지 못했다")
        return
    try:
        _write(workspace.root / record.index_file, index.render(content).encode())
    except OSError as exc:
        result.skip(INDEX_PATH, f"쓸 수 없다({exc.strerror})")
        return
    result.created.append(INDEX_PATH)


# --- 루트 관리 파일 ---------------------------------------------------------------------


def _copy_managed_files(repo: Path, sources: dict[str, Source], result: Result) -> None:
    """루트 관리 파일을 루트의 내용으로 맞춘다. 마지막 최신화 뒤에 손으로 고친 파일은 덮어쓰거나 지우지 않고 보고한다."""
    for _, target_dir in MANAGED_TREES:
        if reason := blocked(repo, target_dir, directory=True):
            result.skip(f"{target_dir}/", f"{reason}. 루트 관리 파일을 복사하지 않았다")
            return
    recorded = read_record(repo)
    record = dict(recorded)

    # 루트에서 없어진 루트 관리 파일. 기록이 있는 것만 우리가 만든 파일이다. 그 밖의 파일(가상환경, 캐시, 산출물)은 건드리지 않는다.
    # 복사보다 먼저 지운다. 루트에서 파일이 디렉토리로(또는 반대로) 바뀌면 옛 경로가 새 경로를 막고 있어서, 나중에 지우면 한 번 더 실행해야 한다.
    for target in sorted(set(recorded) - set(sources)):
        if reason := blocked(repo, target):
            result.skip(target, reason, shared=True)
            continue
        path = repo / target
        try:
            current = fingerprint_of(path)
            if current is None:
                del record[target]
            elif current != recorded[target]:
                result.skip(target, _hand_edited(True, removed_from_root=True))
            else:
                path.unlink()
                _remove_empty_parents(repo, path)
                del record[target]
                result.removed.append(target)
        except OSError as exc:
            result.skip(target, f"읽거나 지울 수 없다({exc.strerror})")

    for target, source in sorted(sources.items()):
        if reason := blocked(repo, target):
            result.skip(target, reason, shared=True)
            continue
        path = repo / target
        try:
            current = fingerprint_of(path)
            if current == source.fingerprint:
                record[target] = current
                continue
            if current is not None and current != recorded.get(target):
                result.skip(target, _hand_edited(target in recorded))
                continue
            _write(path, source.content, executable=source.executable)
        except OSError as exc:
            result.skip(target, f"읽거나 쓸 수 없다({exc.strerror})")
            continue
        record[target] = source.fingerprint
        (result.created if current is None else result.changed).append(target)

    if record != recorded:
        try:
            _write(repo / RECORD_FILE, (json.dumps(record, indent=2, sort_keys=True) + "\n").encode())
        except OSError as exc:
            result.skip(RECORD_FILE, f"쓸 수 없다({exc.strerror})")


def _hand_edited(has_record: bool, *, removed_from_root: bool = False) -> str:
    """손으로 고친 루트 관리 파일을 건드리지 않은 이유와, 그 파일을 어떻게 하면 되는지."""
    if removed_from_root:
        return "루트에서는 없어졌지만 마지막 최신화 뒤에 손으로 고친 파일이라 지우지 않았다. 지워도 되면 이 파일을 직접 지운다"
    if has_record:
        return "마지막 최신화 뒤에 손으로 고친 파일이라 덮어쓰지 않았다. 루트의 내용으로 되돌리려면 이 파일을 지우고 다시 실행한다"
    return "마지막 최신화의 기록이 없고 루트의 내용과 달라 손으로 고쳤는지 알 수 없어 덮어쓰지 않았다. 덮어써도 되면 이 파일을 지우고 다시 실행한다"


def _remove_empty_parents(repo: Path, path: Path) -> None:
    """파일을 지운 뒤 비게 된 디렉토리를 지식 저장소 루트 아래에서 위로 올라가며 지운다. 비어 있지 않은 디렉토리에서 멈춘다."""
    parent = path.parent
    while parent != repo:
        try:
            parent.rmdir()
        except OSError:
            return
        parent = parent.parent


# --- 파일 다루기 ------------------------------------------------------------------------


def _write(path: Path, data: bytes, *, executable: bool = False, like: Path | None = None) -> None:
    """`data`를 `path`에 쓴다. 임시 파일에 쓰고 바꿔 끼워, 쓰다 멈춰도 기존 파일이 깨지지 않는다. `like`가 있으면 그 파일의 권한을 잇는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = (like.stat().st_mode & 0o7777) if like is not None else (0o755 if executable else 0o644)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
