"""`just git push`: 이미 커밋된 것만, 지식 저장소를 먼저 올리고 모두 성공한 뒤 루트 저장소를 올린다. 저장소별 결과를 요약한다."""

import pytest

ROOT = "루트 저장소"
STATES = ("푸시됨", "올릴 것 없음", "건너뜀", "실패")


def _push(sandbox, clone, **kwargs):
    return sandbox.just("git", "push", cwd=clone, **kwargs)


def _outcomes(result):
    """요약의 `<상태>: <저장소> — <이유>` 줄에서 저장소별 `(상태, 줄 전체)`를 뽑는다. 요약 앞의 진행 줄은 보지 않는다."""
    _, marker, summary = result.stdout.partition("== 요약 ==")
    assert marker, f"요약이 없다:\n{result.stdout}"
    found = {}
    for line in summary.splitlines():
        state, sep, rest = line.partition(": ")
        if sep and state in STATES:
            found[rest.split(" — ")[0].split(" (")[0]] = (state, line)
    return found


def _uncommitted(result):
    """푸시 전에 보고한 미커밋 변경 목록. `{저장소: 줄}`이고, 보고가 없으면 빈 딕셔너리다."""
    header = "미커밋 변경이 있는 저장소"
    before_summary = result.stdout.partition("== 요약 ==")[0]
    _, marker, rest = before_summary.partition(header)
    found = {}
    if not marker:
        return found
    for line in rest.splitlines()[1:]:
        if not line.startswith("  "):
            break
        found[line.strip().split(":")[0]] = line.strip()
    return found


def _left_behind(result):
    """요약 뒤에 알리는 "건너뛴 저장소에 푸시하지 않은 커밋이 남아 있다"의 목록. `{저장소: 줄}`이고, 알림이 없으면 빈 딕셔너리다."""
    header = "푸시하지 않은 커밋이 남아 있습니다"
    _, marker, rest = result.stdout.partition("== 요약 ==")[2].partition(header)
    found = {}
    if not marker:
        return found
    for line in rest.splitlines()[1:]:
        if not line.startswith("  "):
            break
        found[line.strip().split(":")[0]] = line.strip()
    return found


def _sub(clone, name="billing"):
    return clone / "projects" / name


def _tip(sandbox, bare, branch="main"):
    """로컬 bare 원격의 브랜치 끝. 브랜치가 없으면 `None`."""
    found = sandbox.git("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", cwd=bare, check=False)
    return found.stdout.strip() or None


def _local_commit(sandbox, repo, filename="local.md"):
    (repo / filename).write_text(f"# {filename}\n", encoding="utf-8")
    sandbox.git("add", filename, cwd=repo)
    sandbox.git("commit", "-m", f"작업 {filename}", cwd=repo)
    return sandbox.head(repo)


def _commit_pointers(sandbox, clone, *names):
    """루트 저장소에서 서브모듈 포인터 변경을 커밋한다."""
    sandbox.git("add", *[f"projects/{name}" for name in names], cwd=clone)
    sandbox.git("commit", "-m", f"포인터 {' '.join(names)}", cwd=clone)
    return sandbox.head(clone)


def _refuse_dangling_pointers(root, **remotes):
    """루트의 원격이 푸시를 받는 순간, 그 커밋이 가리키는 서브모듈 커밋이 지식 저장소의 원격에 이미 있는지 본다. 없으면 푸시를 거부한다.

    루트가 원격에 없는 커밋을 가리키는 순간이 한 번도 없어야 한다는 약속(푸시 순서)을 순서가 아니라 결과로 확인하는 장치다.
    """
    checks = "\n".join(f"check projects/{name} '{remote.url}'" for name, remote in remotes.items())
    hook = root.origin / "hooks" / "pre-receive"
    hook.write_text(
        f"""#!/bin/sh
check() {{
    sha=$(git ls-tree "$new" -- "$1" | awk '{{print $3}}')
    [ -n "$sha" ] || return 0
    # 이 훅은 받는 쪽의 임시 객체 디렉토리에서 돈다. 다른 저장소를 볼 때는 그 환경 변수를 비운다.
    if ! (unset GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_QUARANTINE_PATH
          git --git-dir="$2" cat-file -e "$sha^{{commit}}" 2>/dev/null); then
        echo "원격에 없는 커밋을 가리킨다: $1 $sha" >&2
        exit 1
    fi
}}
while read -r old new ref; do
    case $new in 0*) continue ;; esac
    {checks}
done
""",
        encoding="utf-8",
    )
    hook.chmod(0o755)


# --- 인자 없이 부르면 명령 목록 --------------------------------------------------------


def test_인자_없이_just_git만_부르면_푸시하지_않고_모듈의_명령_목록을_보여_준다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    _local_commit(sandbox, _sub(clone))
    billing_tip = _tip(sandbox, billing.url)

    result = sandbox.just("git", cwd=clone)

    assert result.returncode == 0, result.stderr
    assert "push" in result.stdout
    assert _tip(sandbox, billing.url) == billing_tip


# --- 지식 저장소를 먼저, 모두 성공하면 루트 저장소를 -------------------------------------------


def test_미푸시_커밋이_있는_지식_저장소를_모두_올린_뒤_루트_저장소를_올리고_저장소별_결과를_요약한다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    docs = sandbox.knowledge_remote("docs")
    quiet = sandbox.knowledge_remote("quiet")
    root.register(billing)
    root.register(docs)
    root.register(quiet)
    clone = root.set_up_clone()
    _refuse_dangling_pointers(root, billing=billing, docs=docs, quiet=quiet)
    _local_commit(sandbox, _sub(clone, "billing"))
    billing_head = _local_commit(sandbox, _sub(clone, "billing"), "more.md")
    docs_head = _local_commit(sandbox, _sub(clone, "docs"))
    root_head = _commit_pointers(sandbox, clone, "billing", "docs")  # 루트가 새 커밋을 가리킨다

    result = _push(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert _tip(sandbox, billing.url) == billing_head
    assert _tip(sandbox, docs.url) == docs_head
    assert _tip(sandbox, root.origin) == root_head  # 지식 저장소가 먼저 올라가 있어야 원격이 받는다(훅이 확인한다)
    outcomes = _outcomes(result)
    assert outcomes["projects/billing"][0] == "푸시됨" and "2" in outcomes["projects/billing"][1]  # 커밋 2개
    assert outcomes["projects/docs"][0] == "푸시됨"
    assert outcomes["projects/quiet"][0] == "올릴 것 없음"
    assert outcomes[ROOT][0] == "푸시됨"
    assert _uncommitted(result) == {}


def test_지식_저장소_하나가_푸시에_실패하면_루트_저장소는_올리지_않고_실패한_저장소와_이유를_보고한다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    docs = sandbox.knowledge_remote("docs")
    root.register(billing)
    root.register(docs)
    clone = root.set_up_clone()
    _local_commit(sandbox, _sub(clone, "billing"))
    docs_head = _local_commit(sandbox, _sub(clone, "docs"))
    _commit_pointers(sandbox, clone, "billing", "docs")
    other = billing.commit()  # billing의 원격에 로컬에 없는 커밋이 생겨 푸시가 거부된다
    root_tip = _tip(sandbox, root.origin)

    result = _push(sandbox, clone)

    assert result.returncode != 0
    assert _tip(sandbox, billing.url) == other  # 건드리지 않았다
    assert _tip(sandbox, docs.url) == docs_head  # 실패한 저장소 때문에 나머지가 멈추지 않는다
    assert _tip(sandbox, root.origin) == root_tip  # 루트는 올리지 않았다
    outcomes = _outcomes(result)
    state, line = outcomes["projects/billing"]
    assert state == "실패" and "rejected" in line  # 이유: git이 거부한 것
    assert outcomes["projects/docs"][0] == "푸시됨"
    state, line = outcomes[ROOT]
    assert state == "건너뜀" and "projects/billing" in line  # 루트를 올리지 않은 까닭과 그 저장소


def test_지식_저장소의_원격에_접속할_수_없어도_실패로_보고하고_루트_저장소는_올리지_않는다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    _local_commit(sandbox, _sub(clone))
    _commit_pointers(sandbox, clone, "billing")
    root_tip = _tip(sandbox, root.origin)
    billing.url.rename(billing.url.with_name("moved-away.git"))

    result = _push(sandbox, clone)

    assert result.returncode != 0
    assert _tip(sandbox, root.origin) == root_tip
    state, line = _outcomes(result)["projects/billing"]
    assert state == "실패" and "fatal" in line
    assert _outcomes(result)[ROOT][0] == "건너뜀"


def test_루트_저장소의_푸시가_거부되면_실패로_보고하고_0이_아닌_종료_코드로_끝나며_지식_저장소는_이미_올라가_있다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    billing_head = _local_commit(sandbox, _sub(clone))
    _commit_pointers(sandbox, clone, "billing")
    other = root.commit({"NOTES.md": "# 메모\n"})  # 루트의 원격이 앞서 갔다

    result = _push(sandbox, clone)

    assert result.returncode != 0
    assert _tip(sandbox, billing.url) == billing_head
    assert _tip(sandbox, root.origin) == other
    outcomes = _outcomes(result)
    assert outcomes["projects/billing"][0] == "푸시됨"
    state, line = outcomes[ROOT]
    assert state == "실패" and "rejected" in line


# --- 루트 저장소가 원격에 없는 서브모듈 커밋을 가리키는 경우 -------------------------------------


def test_루트가_다른_브랜치의_푸시하지_않은_서브모듈_커밋을_가리키면_루트_저장소를_올리지_않고_실패로_보고한다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    sub = _sub(clone)
    sandbox.git("checkout", "-b", "feature", cwd=sub)
    feature_head = _local_commit(sandbox, sub)
    _commit_pointers(sandbox, clone, "billing")  # 루트가 feature의 커밋을 가리킨다
    sandbox.git("checkout", "main", cwd=sub)  # 그 브랜치를 떠났으니 이번 푸시가 올리지 않는다
    root_tip = _tip(sandbox, root.origin)

    result = _push(sandbox, clone)

    assert result.returncode != 0
    assert _tip(sandbox, root.origin) == root_tip
    assert _tip(sandbox, billing.url, "feature") is None
    outcomes = _outcomes(result)
    assert outcomes["projects/billing"][0] == "올릴 것 없음"
    state, line = outcomes[ROOT]
    assert state == "실패" and "projects/billing" in line and feature_head[:7] in line


def test_detached_HEAD의_서브모듈_커밋을_루트가_가리키면_그_저장소는_건너뛰고_루트_저장소는_올리지_않는다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    sub = _sub(clone)
    sandbox.git("checkout", "--detach", cwd=sub)
    detached_head = _local_commit(sandbox, sub)
    _commit_pointers(sandbox, clone, "billing")
    root_tip = _tip(sandbox, root.origin)

    result = _push(sandbox, clone)

    assert result.returncode != 0
    assert _tip(sandbox, root.origin) == root_tip
    outcomes = _outcomes(result)
    state, line = outcomes["projects/billing"]
    assert state == "건너뜀" and "detached HEAD" in line
    state, line = outcomes[ROOT]
    assert state == "실패" and detached_head[:7] in line


def test_루트가_가리키는_서브모듈_커밋이_이미_원격에_있으면_올릴_것이_없는_지식_저장소가_있어도_루트를_올린다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    published = billing.commit()
    sandbox.git("fetch", "origin", cwd=_sub(clone))
    sandbox.git("merge", "--ff-only", published, cwd=_sub(clone))  # 원격에 있는 커밋으로 올라갔다(올릴 것은 없다)
    root_head = _commit_pointers(sandbox, clone, "billing")

    result = _push(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert _tip(sandbox, root.origin) == root_head
    assert _outcomes(result)["projects/billing"][0] == "올릴 것 없음"
    assert _outcomes(result)[ROOT][0] == "푸시됨"


def test_루트의_원격이_이미_기록한_서브모듈_커밋은_로컬에_받아_오지_않았어도_다시_확인하지_않고_루트를_올린다(sandbox):
    """루트만 그냥 pull해서 포인터가 앞서 갔고, 지식 저장소는 아직 받지 않았다. 푸시가 새로 알리는 포인터가 아니다."""
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    root.point_at("billing", billing.commit())  # 다른 기기가 새 커밋을 루트에 기록해 푸시했다
    sandbox.git("-c", "fetch.recurseSubmodules=no", "pull", "--ff-only", cwd=clone)  # 루트만 받았다. 지식 저장소에는 그 커밋이 없다
    root_head = _local_commit(sandbox, clone, "NOTES.md")

    result = _push(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert _tip(sandbox, root.origin) == root_head
    assert _outcomes(result)["projects/billing"][0] == "올릴 것 없음"
    assert _outcomes(result)[ROOT][0] == "푸시됨"


def test_초기화하지_않은_지식_저장소는_건너뛰고_루트가_기록한_커밋이_원격의_것과_같으면_루트는_올린다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    clone = root.clone()  # 서브모듈을 초기화하지 않았다
    root_head = _local_commit(sandbox, clone, "NOTES.md")

    result = _push(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert _tip(sandbox, root.origin) == root_head
    state, line = _outcomes(result)["projects/billing"]
    assert state == "건너뜀" and "초기화" in line and "just setup" in line
    assert not (_sub(clone) / ".git").exists()  # push는 초기화하지 않는다


def test_초기화하지_않은_지식_저장소의_포인터가_원격의_것과_다르면_확인할_수_없어_루트를_올리지_않는다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.clone()
    newer = billing.commit()
    sandbox.git("update-index", "--cacheinfo", f"160000,{newer},projects/billing", cwd=clone)
    sandbox.git("commit", "-m", "포인터만 옮김", cwd=clone)  # 가리키는 저장소가 없어 확인할 수 없다
    root_tip = _tip(sandbox, root.origin)

    result = _push(sandbox, clone)

    assert result.returncode != 0
    assert _tip(sandbox, root.origin) == root_tip
    state, line = _outcomes(result)[ROOT]
    assert state == "실패" and "projects/billing" in line and "초기화" in line


# --- 커밋한 것만 올린다 -----------------------------------------------------------------------


def test_미커밋_변경은_올라가지_않고_그런_저장소를_목록으로_보고하며_커밋도_스테이징도_하지_않는다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    docs = sandbox.knowledge_remote("docs")
    root.register(billing)
    root.register(docs)
    clone = root.set_up_clone()
    sub = _sub(clone)
    committed = _local_commit(sandbox, sub)
    (sub / "README.md").write_text("# 아직 커밋하지 않은 수정\n", encoding="utf-8")  # 추적하는 파일의 수정
    (sub / "draft.md").write_text("# 초안\n", encoding="utf-8")  # 추적하지 않는 파일
    (clone / "NOTES.md").write_text("# 루트의 메모\n", encoding="utf-8")
    sub_status = sandbox.git("status", "--porcelain", cwd=sub).stdout
    root_status = sandbox.git("status", "--porcelain", cwd=clone).stdout
    root_head = sandbox.head(clone)

    result = _push(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert _tip(sandbox, billing.url) == committed  # 커밋한 것은 올라갔다
    remote_files = sandbox.git("ls-tree", "-r", "--name-only", "main", cwd=billing.url).stdout.split()
    assert "local.md" in remote_files and "draft.md" not in remote_files
    assert sandbox.git("show", "main:README.md", cwd=billing.url).stdout == "# billing\n"  # 수정은 올라가지 않았다
    uncommitted = _uncommitted(result)
    assert set(uncommitted) == {"projects/billing", ROOT}  # 변경이 없는 docs는 보고하지 않는다
    assert "2" in uncommitted["projects/billing"]  # 미커밋 변경 2개
    # 아무것도 커밋하거나 스테이징하지 않았고 작업 트리는 그대로다
    assert sandbox.git("status", "--porcelain", cwd=sub).stdout == sub_status
    assert sandbox.git("status", "--porcelain", cwd=clone).stdout == root_status
    assert sandbox.head(sub) == committed and sandbox.head(clone) == root_head
    assert (sub / "README.md").read_text(encoding="utf-8") == "# 아직 커밋하지 않은 수정\n"


# --- 작업 브랜치 ------------------------------------------------------------------------------


def test_작업_브랜치는_같은_이름의_원격_브랜치로_올리고_원격에_없으면_만든다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    sub = _sub(clone)
    main_tip = _tip(sandbox, billing.url)
    sandbox.git("checkout", "-b", "feature", "origin/main", cwd=sub)  # 추적 대상이 origin/main이어서 그냥 push하면 이름이 달라 거부된다
    feature_head = _local_commit(sandbox, sub)

    result = _push(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert _tip(sandbox, billing.url, "feature") == feature_head
    assert _tip(sandbox, billing.url) == main_tip  # 기본 브랜치는 그대로다
    state, line = _outcomes(result)["projects/billing"]
    assert state == "푸시됨" and "feature" in line


def test_원격에_이미_있는_작업_브랜치는_이어서_올린다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    sub = _sub(clone)
    sandbox.git("checkout", "-b", "feature", cwd=sub)
    _local_commit(sandbox, sub, "first.md")
    assert _push(sandbox, clone).returncode == 0
    second = _local_commit(sandbox, sub, "second.md")

    result = _push(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert _tip(sandbox, billing.url, "feature") == second
    assert _outcomes(result)["projects/billing"][0] == "푸시됨"


# --- 올릴 것이 없는 저장소 -------------------------------------------------------------------


def test_올릴_것이_없는_저장소는_원격에_접속하지_않아_원격을_쓸_수_없어도_실패하지_않는다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    docs = sandbox.knowledge_remote("docs")
    root.register(billing)
    root.register(docs)
    clone = root.set_up_clone()
    docs_head = _local_commit(sandbox, _sub(clone, "docs"))
    _commit_pointers(sandbox, clone, "docs")
    billing.url.rename(billing.url.with_name("moved-away.git"))  # billing에는 올릴 것이 없다. 건드린다면 접속에 실패한다

    result = _push(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert _tip(sandbox, docs.url) == docs_head
    outcomes = _outcomes(result)
    assert outcomes["projects/billing"][0] == "올릴 것 없음"
    assert outcomes["projects/docs"][0] == "푸시됨"
    assert outcomes[ROOT][0] == "푸시됨"


def test_모든_저장소에_올릴_것이_없으면_아무것도_바꾸지_않고_성공한다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    before_root = sandbox.snapshot(clone)
    before_sub = sandbox.snapshot(_sub(clone))
    tips = (_tip(sandbox, root.origin), _tip(sandbox, billing.url))

    result = _push(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert {state for state, _ in _outcomes(result).values()} == {"올릴 것 없음"}
    assert (_tip(sandbox, root.origin), _tip(sandbox, billing.url)) == tips
    assert sandbox.snapshot(clone) == before_root
    assert sandbox.snapshot(_sub(clone)) == before_sub


def test_지식_저장소가_하나도_없어도_루트_저장소를_올리고_성공한다(sandbox):
    root = sandbox.root()
    clone = root.clone()
    head = _local_commit(sandbox, clone, "NOTES.md")

    result = _push(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert _tip(sandbox, root.origin) == head
    assert _outcomes(result)[ROOT][0] == "푸시됨"


# --- 루트 저장소와 목록 ------------------------------------------------------------------------


def test_루트_저장소가_detached_HEAD이면_올리지_않고_건너뛴다(sandbox):
    root = sandbox.root()
    clone = root.clone()
    sandbox.git("checkout", "--detach", cwd=clone)
    _local_commit(sandbox, clone, "NOTES.md")
    root_tip = _tip(sandbox, root.origin)

    result = _push(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert _tip(sandbox, root.origin) == root_tip
    state, line = _outcomes(result)[ROOT]
    assert state == "건너뜀" and "detached HEAD" in line


def test_gitmodules를_읽지_못하면_이유를_알리고_루트_저장소는_올리지_않으며_0이_아닌_종료_코드로_끝난다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    clone = root.set_up_clone()
    _local_commit(sandbox, clone, "NOTES.md")
    (clone / ".gitmodules").write_text("[submodule\n", encoding="utf-8")
    root_tip = _tip(sandbox, root.origin)

    result = _push(sandbox, clone)

    assert result.returncode != 0
    assert ".gitmodules" in result.stderr
    assert _tip(sandbox, root.origin) == root_tip  # 어느 저장소를 먼저 올려야 하는지 몰라 올리지 않는다
    assert _outcomes(result)[ROOT][0] == "건너뜀"


def test_하위_디렉토리에서_불러도_루트_저장소를_기준으로_올린다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    head = _local_commit(sandbox, _sub(clone))

    result = sandbox.just("git", "push", cwd=clone / "docs")

    assert result.returncode == 0, result.stderr
    assert _tip(sandbox, billing.url) == head


# --- 올라가는 루트 커밋 전체가 가리키는 서브모듈 커밋을 본다 ------------------------------------------


def test_루트가_가리킨_뒤_등록을_해제해_저장소가_없어진_커밋은_확인할_수_없어_루트를_올리지_않는다(sandbox):
    """`just repo remove --force`는 스테이징까지만 한다. 커밋한 포인터는 HEAD에 남아 있는데 지식 저장소의 등록은 인덱스에서 빠진다."""
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    unpushed = _local_commit(sandbox, _sub(clone))
    _commit_pointers(sandbox, clone, "billing")
    assert sandbox.just("repo", "remove", "billing", "--force", cwd=clone).returncode == 0
    root_tip = _tip(sandbox, root.origin)

    result = _push(sandbox, clone)

    assert result.returncode != 0
    assert _tip(sandbox, root.origin) == root_tip
    state, line = _outcomes(result)[ROOT]
    assert state == "실패" and "projects/billing" in line and unpushed[:7] in line


def test_작업_트리의_gitmodules에서_등록이_빠져_있어도_올라가는_루트_커밋이_가리키는_커밋을_확인한다(sandbox):
    """무엇을 검사할지는 미커밋 상태(작업 트리의 `.gitmodules`, 인덱스)가 아니라 올라가는 커밋이 정한다."""
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    unpushed = _local_commit(sandbox, _sub(clone))
    _commit_pointers(sandbox, clone, "billing")
    (clone / ".gitmodules").write_text("", encoding="utf-8")  # 미커밋 변경. 그 저장소는 목록에서 빠져 푸시되지 않는다
    root_tip = _tip(sandbox, root.origin)

    result = _push(sandbox, clone)

    assert result.returncode != 0
    assert _tip(sandbox, root.origin) == root_tip
    assert _tip(sandbox, billing.url) != unpushed
    state, line = _outcomes(result)[ROOT]
    assert state == "실패" and "projects/billing" in line and unpushed[:7] in line


def test_함께_올라가는_중간_루트_커밋이_원격에_없는_서브모듈_커밋을_가리키면_루트_저장소를_올리지_않는다(sandbox):
    """서브모듈에서 커밋을 고쳐 쓰면(amend) 앞 루트 커밋은 사라진 커밋을 가리킨 채 이력에 남는다. 받는 사람이 그 커밋을 체크아웃하면 서브모듈을 받지 못한다."""
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    sub = _sub(clone)
    replaced = _local_commit(sandbox, sub)
    _commit_pointers(sandbox, clone, "billing")  # 루트가 곧 사라질 커밋을 가리킨다
    (sub / "local.md").write_text("# 고쳐 씀\n", encoding="utf-8")
    sandbox.git("commit", "-a", "--amend", "-m", "고쳐 씀", cwd=sub)
    amended = sandbox.head(sub)
    _commit_pointers(sandbox, clone, "billing")  # HEAD는 고친 커밋을 가리킨다
    root_tip = _tip(sandbox, root.origin)

    result = _push(sandbox, clone)

    assert result.returncode != 0
    assert _tip(sandbox, billing.url) == amended  # 지식 저장소는 올라갔다
    assert _tip(sandbox, root.origin) == root_tip
    state, line = _outcomes(result)[ROOT]
    assert state == "실패" and replaced[:7] in line and amended[:7] not in line


def test_병합_커밋이_충돌을_풀며_기록한_서브모듈_커밋도_원격에_없으면_루트_저장소를_올리지_않는다(sandbox):
    """병합 커밋은 부모와 비교하지 않으면 diff에 나오지 않는다. 충돌을 풀며 새 포인터를 적은 병합 커밋을 놓치지 않는다."""
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    sub = _sub(clone)
    sandbox.git("checkout", "-b", "feature", cwd=sub)
    unpushed = _local_commit(sandbox, sub)
    sandbox.git("checkout", "main", cwd=sub)  # 그 커밋은 이번 푸시가 올리지 않는다
    sandbox.git("checkout", "-b", "side", cwd=clone)
    _local_commit(sandbox, clone, "SIDE.md")
    sandbox.git("checkout", "main", cwd=clone)
    _local_commit(sandbox, clone, "MAIN.md")
    sandbox.git("merge", "--no-commit", "--no-ff", "side", cwd=clone)
    sandbox.git("update-index", "--cacheinfo", f"160000,{unpushed},projects/billing", cwd=clone)
    sandbox.git("commit", "-m", "병합하며 포인터를 옮김", cwd=clone)
    root_tip = _tip(sandbox, root.origin)

    result = _push(sandbox, clone)

    assert result.returncode != 0
    assert _tip(sandbox, root.origin) == root_tip
    state, line = _outcomes(result)[ROOT]
    assert state == "실패" and unpushed[:7] in line


def test_새_루트_작업_브랜치는_초기화하지_않은_지식_저장소의_포인터가_그대로면_거부하지_않고_올린다(sandbox):
    """같은 이름의 원격 브랜치가 없어도, 이 브랜치의 커밋이 포인터를 바꾸지 않았으면 확인할 것이 없다."""
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    clone = root.clone()  # 서브모듈을 초기화하지 않았다
    sandbox.git("checkout", "-b", "feature", cwd=clone)
    head = _local_commit(sandbox, clone, "NOTES.md")

    result = _push(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert _tip(sandbox, root.origin, "feature") == head
    assert _outcomes(result)[ROOT][0] == "푸시됨"


# --- 푸시하지 못한 저장소 -----------------------------------------------------------------------


def test_푸시하지_않은_커밋_수를_세지_못한_지식_저장소가_있으면_실패로_보고하고_루트_저장소는_올리지_않는다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    sub = _sub(clone)
    _local_commit(sandbox, sub)
    git_dir = sandbox.git("rev-parse", "--absolute-git-dir", cwd=sub).stdout.strip()
    with open(f"{git_dir}/refs/remotes/origin/main", "w", encoding="utf-8") as f:  # 없는 객체를 가리키는 원격 추적 참조: rev-list가 실패한다
        f.write("1" * 40 + "\n")
    root_head = _local_commit(sandbox, clone, "NOTES.md")  # 루트 커밋은 포인터를 바꾸지 않으므로 포인터 검사가 막아 주지 않는다
    root_tip = _tip(sandbox, root.origin)

    result = _push(sandbox, clone)

    assert result.returncode != 0
    assert _tip(sandbox, root.origin) == root_tip != root_head
    outcomes = _outcomes(result)
    assert outcomes["projects/billing"][0] == "실패"
    state, line = outcomes[ROOT]
    assert state == "건너뜀" and "projects/billing" in line


def test_건너뛴_저장소에_푸시하지_않은_커밋이_남으면_종료_코드는_0이어도_요약_끝에서_눈에_띄게_알린다(sandbox):
    """건너뜀은 정상 결과다. 그 커밋을 루트가 가리키면 루트 푸시가 실패하므로 안전하다. 그래도 커밋한 작업이 공유되지 않았다는 사실은 보여야 한다."""
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    docs = sandbox.knowledge_remote("docs")
    root.register(billing)
    root.register(docs)
    clone = root.set_up_clone()
    sandbox.git("checkout", "--detach", cwd=_sub(clone, "billing"))
    _local_commit(sandbox, _sub(clone, "billing"))
    _local_commit(sandbox, _sub(clone, "billing"), "more.md")  # billing: detached HEAD에 커밋 2개
    sandbox.git("checkout", "--detach", cwd=clone)
    _local_commit(sandbox, clone, "NOTES.md")  # 루트도 detached HEAD에 커밋 1개

    result = _push(sandbox, clone)

    assert result.returncode == 0, result.stderr
    outcomes = _outcomes(result)
    assert outcomes["projects/billing"][0] == "건너뜀" and outcomes[ROOT][0] == "건너뜀"
    assert outcomes["projects/docs"][0] == "올릴 것 없음"
    left = _left_behind(result)
    assert set(left) == {"projects/billing", ROOT}  # 올릴 것이 없는 docs는 알리지 않는다
    assert "2" in left["projects/billing"] and "1" in left[ROOT]


def test_올리지_않은_커밋이_남은_건너뜀이_없으면_그런_알림을_하지_않는다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    clone = root.set_up_clone()

    result = _push(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert "푸시하지 않은 커밋이 남아 있습니다" not in result.stdout


# --- 사용자의 git 설정이 약속을 깨지 않는다 -----------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("push.followTags", "true"),  # 올리는 커밋에 닿는 주석 태그를 함께 올린다
        ("push.recurseSubmodules", "on-demand"),
        ("push.default", "nothing"),
        ("push.autoSetupRemote", "true"),  # 인자 없는 push가 추적 설정을 만든다
        ("submodule.recurse", "true"),
        ("diff.ignoreSubmodules", "all"),  # 서브모듈 포인터 변경을 diff에서 숨긴다
    ],
)
def test_사용자의_push_설정이_켜져_있어도_브랜치만_같은_이름으로_올리고_태그와_추적_설정은_건드리지_않는다(sandbox, key, value):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    sandbox.git("config", "--global", key, value, cwd=clone)
    sub = _sub(clone)
    sandbox.git("checkout", "-b", "feature", "origin/main", cwd=sub)  # 추적 대상이 origin/main이다
    feature_head = _local_commit(sandbox, sub)
    sandbox.git("tag", "-a", "v-billing", "-m", "지식 저장소의 태그", cwd=sub)
    root_head = _commit_pointers(sandbox, clone, "billing")
    sandbox.git("tag", "-a", "v-root", "-m", "루트의 태그", cwd=clone)

    result = _push(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert _tip(sandbox, billing.url, "feature") == feature_head
    assert _tip(sandbox, root.origin) == root_head
    assert sandbox.git("tag", "--list", cwd=billing.url).stdout == ""  # 태그는 올리지 않았다
    assert sandbox.git("tag", "--list", cwd=root.origin).stdout == ""
    assert sandbox.git("config", "--get", "branch.feature.merge", cwd=sub).stdout.strip() == "refs/heads/main"  # 추적 설정은 그대로다
    assert sandbox.git("config", "--get", "branch.main.merge", cwd=clone).stdout.strip() == "refs/heads/main"
    assert {state for state, _ in _outcomes(result).values()} == {"푸시됨"}


def test_diff_설정이_서브모듈_변경을_숨겨도_루트가_원격에_없는_서브모듈_커밋을_가리키면_올리지_않는다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    sandbox.git("config", "--global", "diff.ignoreSubmodules", "all", cwd=clone)
    sub = _sub(clone)
    sandbox.git("checkout", "-b", "feature", cwd=sub)
    feature_head = _local_commit(sandbox, sub)
    _commit_pointers(sandbox, clone, "billing")
    sandbox.git("checkout", "main", cwd=sub)
    root_tip = _tip(sandbox, root.origin)

    result = _push(sandbox, clone)

    assert result.returncode != 0
    assert _tip(sandbox, root.origin) == root_tip
    state, line = _outcomes(result)[ROOT]
    assert state == "실패" and feature_head[:7] in line
