"""`just git pull`: 루트 저장소와 모든 지식 저장소를 fast-forward로만 최신으로 올리고, 저장소별 결과를 요약한다."""

import pytest

ROOT = "루트 저장소"


def _pull(sandbox, clone, **kwargs):
    return sandbox.just("git", "pull", cwd=clone, **kwargs)


def _outcomes(result):
    """요약의 `<상태>: <저장소> — <이유>` 줄에서 저장소별 `(상태, 줄 전체)`를 뽑는다. 요약 앞의 진행 줄은 보지 않는다."""
    _, marker, summary = result.stdout.partition("== 요약 ==")
    assert marker, f"요약이 없다:\n{result.stdout}"
    found = {}
    for line in summary.splitlines():
        state, sep, rest = line.partition(": ")
        if sep and state in ("갱신됨", "변화 없음", "건너뜀", "실패"):
            found[rest.split(" — ")[0].split(" (")[0]] = (state, line)
    return found


def _sub(clone, name="billing"):
    return clone / "projects" / name


def _remote_tip(sandbox, sub, branch="main"):
    """서브모듈이 마지막으로 받아 둔 원격 브랜치의 끝."""
    return sandbox.git("rev-parse", f"origin/{branch}", cwd=sub).stdout.strip()


def _local_commit(sandbox, sub, filename="local.md"):
    (sub / filename).write_text(f"# {filename}\n", encoding="utf-8")
    sandbox.git("add", filename, cwd=sub)
    sandbox.git("commit", "-m", f"작업 {filename}", cwd=sub)


# --- 인자 없이 부르면 명령 목록 --------------------------------------------------------


def test_인자_없이_just_git만_부르면_받지_않고_모듈의_명령_목록을_보여_준다(sandbox):
    """모듈의 첫 명령이 기본으로 실행되면 `just git`만 쳐도 저장소가 바뀐다."""
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    billing.commit()
    before = sandbox.snapshot(clone)
    sub_head = sandbox.head(_sub(clone))

    result = sandbox.just("git", cwd=clone)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "pull" in result.stdout and "status" in result.stdout
    assert sandbox.snapshot(clone) == before
    assert sandbox.head(_sub(clone)) == sub_head  # 원격이 앞서 있어도 받지 않았다


# --- 추적 브랜치에서 fast-forward ---------------------------------------------------------


def test_추적_브랜치에_있고_fast_forward가_가능한_지식_저장소는_원격의_최신으로_올라간다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    docs = sandbox.knowledge_remote("docs")
    root.register(billing)
    root.register(docs)
    clone = root.set_up_clone()
    billing.commit()
    latest = billing.commit()

    result = _pull(sandbox, clone)

    sub = _sub(clone)
    assert result.returncode == 0, result.stderr
    assert sandbox.head(sub) == latest
    assert sandbox.branch(sub) == "main"
    assert (sub / "docs" / "note-1.md").is_file() and (sub / "docs" / "note-2.md").is_file()
    outcomes = _outcomes(result)
    assert outcomes["projects/billing"][0] == "갱신됨"
    assert outcomes["projects/docs"][0] == "변화 없음"


def test_기록된_추적_브랜치가_main이_아니면_그_브랜치를_받는다(sandbox):
    root = sandbox.root()
    docs = sandbox.knowledge_remote("docs")
    docs.commit(branch="dev")
    root.register(docs, branch="dev")
    clone = root.set_up_clone()
    main_tip = sandbox.head(_sub(clone, "docs"))
    dev_tip = docs.commit(branch="dev")
    docs.commit(branch="main")  # 추적하지 않는 브랜치의 변화

    result = _pull(sandbox, clone)

    sub = _sub(clone, "docs")
    assert result.returncode == 0, result.stderr
    assert sandbox.branch(sub) == "dev"
    assert sandbox.head(sub) == dev_tip != main_tip
    assert _outcomes(result)["projects/docs"][0] == "갱신됨"


# --- 추적 브랜치가 아닌 브랜치 ------------------------------------------------------------


def test_추적_브랜치가_아닌_브랜치에_있으면_fetch만_하고_건너뛴_것으로_보고한다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    sub = _sub(clone)
    sandbox.git("checkout", "-b", "feature", cwd=sub)
    _local_commit(sandbox, sub)
    feature_head = sandbox.head(sub)
    latest = billing.commit()

    result = _pull(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.branch(sub) == "feature" and sandbox.head(sub) == feature_head  # 건드리지 않았다
    assert not (sub / "docs" / "note-1.md").exists()
    assert _remote_tip(sandbox, sub) == latest  # fetch는 했다
    state, line = _outcomes(result)["projects/billing"]
    assert state == "건너뜀"
    assert "feature" in line and "main" in line and "fetch만" in line  # 이유: 어느 브랜치에 있고 무엇이 추적 브랜치인지


def test_detached_HEAD에_있는_지식_저장소는_fetch만_하고_건너뛴_것으로_보고한다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    sub = _sub(clone)
    sandbox.git("checkout", "--detach", cwd=sub)
    detached = sandbox.head(sub)
    latest = billing.commit()

    result = _pull(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.head(sub) == detached and sandbox.branch(sub) is None
    assert _remote_tip(sandbox, sub) == latest
    state, line = _outcomes(result)["projects/billing"]
    assert state == "건너뜀" and "detached HEAD" in line


# --- 로컬 커밋 --------------------------------------------------------------------------


def test_로컬_커밋_때문에_fast_forward가_안_되면_건드리지_않고_건너뛴_것으로_보고한다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    sub = _sub(clone)
    _local_commit(sandbox, sub)
    local_head = sandbox.head(sub)
    latest = billing.commit()  # 로컬과 원격이 갈라졌다

    result = _pull(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.head(sub) == local_head  # 병합도 리베이스도 하지 않았다
    assert sandbox.branch(sub) == "main"
    assert sandbox.git("status", "--porcelain", cwd=sub).stdout == ""
    assert sandbox.git("rev-parse", "origin/main", cwd=sub).stdout.strip() == latest
    state, line = _outcomes(result)["projects/billing"]
    assert state == "건너뜀" and "갈라져" in line


def test_로컬이_앞서_있기만_하면_받을_것이_없으므로_변화_없음이고_로컬_커밋은_그대로다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    clone = root.set_up_clone()
    sub = _sub(clone)
    _local_commit(sandbox, sub)
    local_head = sandbox.head(sub)

    result = _pull(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.head(sub) == local_head
    assert _outcomes(result)["projects/billing"][0] == "변화 없음"


# --- 미커밋 변경 -------------------------------------------------------------------------


def test_받아_올_변경과_같은_파일에_미커밋_변경이_있으면_건드리지_않고_건너뛴_것으로_보고한다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    sub = _sub(clone)
    (sub / "README.md").write_text("# 내가 고치는 중\n", encoding="utf-8")
    head = sandbox.head(sub)
    before = sandbox.git("status", "--porcelain", cwd=sub).stdout
    billing.commit(files={"README.md": "# 원격이 고친 README\n"})  # 같은 파일을 원격도 바꿨다

    result = _pull(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.head(sub) == head
    assert (sub / "README.md").read_text(encoding="utf-8") == "# 내가 고치는 중\n"
    assert sandbox.git("status", "--porcelain", cwd=sub).stdout == before
    state, line = _outcomes(result)["projects/billing"]
    assert state == "건너뜀" and "README.md" in line and "미커밋" in line


def test_받아_올_파일과_겹치는_추적하지_않는_파일이_있으면_건드리지_않고_건너뛴_것으로_보고한다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    sub = _sub(clone)
    (sub / "docs" / "plan.md").write_text("# 내 초안\n", encoding="utf-8")
    head = sandbox.head(sub)
    billing.commit(files={"docs/plan.md": "# 원격의 계획\n"})

    result = _pull(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.head(sub) == head
    assert (sub / "docs" / "plan.md").read_text(encoding="utf-8") == "# 내 초안\n"
    state, line = _outcomes(result)["projects/billing"]
    assert state == "건너뜀" and "docs/plan.md" in line


def test_미커밋_변경이_있어도_받아_올_변경과_겹치지_않으면_fast_forward로_받고_변경은_그대로다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    sub = _sub(clone)
    (sub / "README.md").write_text("# 내가 고치는 중\n", encoding="utf-8")
    (sub / "draft.md").write_text("# 새 초안\n", encoding="utf-8")
    sandbox.git("add", "draft.md", cwd=sub)
    latest = billing.commit()  # 다른 파일만 바뀐다

    result = _pull(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.head(sub) == latest
    assert (sub / "docs" / "note-1.md").is_file()
    assert (sub / "README.md").read_text(encoding="utf-8") == "# 내가 고치는 중\n"
    assert sorted(sandbox.git("status", "--porcelain", cwd=sub).stdout.splitlines()) == [" M README.md", "A  draft.md"]
    assert _outcomes(result)["projects/billing"][0] == "갱신됨"


# --- 저장소 하나의 문제로 멈추지 않는다 -----------------------------------------------------


def test_한_저장소가_건너뛰어져도_나머지는_계속_처리한다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    docs = sandbox.knowledge_remote("docs")
    root.register(billing)  # 먼저 처리되는 쪽이 건너뛰어진다
    root.register(docs)
    clone = root.set_up_clone()
    _local_commit(sandbox, _sub(clone))
    billing.commit()
    docs_tip = docs.commit()

    result = _pull(sandbox, clone)

    assert result.returncode == 0, result.stderr
    outcomes = _outcomes(result)
    assert outcomes["projects/billing"][0] == "건너뜀"
    assert outcomes["projects/docs"][0] == "갱신됨"
    assert sandbox.head(_sub(clone, "docs")) == docs_tip


def test_한_저장소의_fetch가_실패해도_나머지는_계속_처리하고_실패를_보고하며_0이_아닌_종료_코드로_끝난다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    docs = sandbox.knowledge_remote("docs")
    root.register(billing)
    root.register(docs)
    clone = root.set_up_clone()
    billing.commit()
    docs_tip = docs.commit()
    billing.url.rename(billing.url.with_name("moved-away.git"))  # billing의 원격에 접속할 수 없다
    billing_head = sandbox.head(_sub(clone))

    result = _pull(sandbox, clone)

    assert result.returncode != 0
    outcomes = _outcomes(result)
    assert outcomes["projects/billing"][0] == "실패" and "fetch" in outcomes["projects/billing"][1]
    assert outcomes["projects/docs"][0] == "갱신됨"
    assert sandbox.head(_sub(clone, "docs")) == docs_tip
    assert sandbox.head(_sub(clone)) == billing_head


def test_지식_저장소가_하나도_없어도_루트_저장소를_받고_성공한다(sandbox):
    root = sandbox.root()
    clone = root.clone()
    latest = root.commit({"NOTES.md": "# 메모\n"})

    result = _pull(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.head(clone) == latest
    assert _outcomes(result)[ROOT][0] == "갱신됨"


# --- 루트 저장소 ------------------------------------------------------------------------


def _root_local_commit(sandbox, clone, filename="LOCAL.md"):
    (clone / filename).write_text(f"# {filename}\n", encoding="utf-8")
    sandbox.git("add", filename, cwd=clone)
    sandbox.git("commit", "-m", f"루트 작업 {filename}", cwd=clone)


def test_루트_저장소도_fast_forward로_받는다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    clone = root.set_up_clone()
    latest = root.commit({"NOTES.md": "# 메모\n"})

    result = _pull(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.head(clone) == latest  # 병합 커밋 없이 원격의 끝이다
    assert (clone / "NOTES.md").is_file()
    assert _outcomes(result)[ROOT][0] == "갱신됨"


def test_루트_저장소를_받을_수_없으면_건너뛰고_보고한_뒤_지식_저장소를_계속_처리한다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    _root_local_commit(sandbox, clone)
    local_head = sandbox.head(clone)
    root.commit({"NOTES.md": "# 메모\n"})  # 루트의 로컬과 원격이 갈라졌다
    billing_tip = billing.commit()

    result = _pull(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.head(clone) == local_head
    assert not (clone / "NOTES.md").exists()
    outcomes = _outcomes(result)
    assert outcomes[ROOT][0] == "건너뜀" and "갈라져" in outcomes[ROOT][1]
    assert outcomes["projects/billing"][0] == "갱신됨"
    assert sandbox.head(_sub(clone)) == billing_tip


def test_받아_올_변경과_같은_파일에_미커밋_변경이_있으면_루트_저장소도_건드리지_않고_건너뛴다(sandbox):
    root = sandbox.root()
    clone = root.clone()
    (clone / "README.md").write_text("# 내가 고치는 중\n", encoding="utf-8")
    head = sandbox.head(clone)
    root.commit({"README.md": "# 원격이 고친 README\n"})

    result = _pull(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.head(clone) == head
    assert (clone / "README.md").read_text(encoding="utf-8") == "# 내가 고치는 중\n"
    state, line = _outcomes(result)[ROOT]
    assert state == "건너뜀" and "README.md" in line


def test_루트_저장소가_detached_HEAD이거나_원격에_없는_브랜치에_있으면_건너뛴다(sandbox):
    root = sandbox.root()
    clone = root.clone()
    root.commit({"NOTES.md": "# 메모\n"})

    sandbox.git("checkout", "--detach", cwd=clone)
    detached = _pull(sandbox, clone)
    sandbox.git("checkout", "-b", "topic", cwd=clone)
    topic = _pull(sandbox, clone)

    assert detached.returncode == 0 and topic.returncode == 0
    state, line = _outcomes(detached)[ROOT]
    assert state == "건너뜀" and "detached HEAD" in line
    state, line = _outcomes(topic)[ROOT]
    assert state == "건너뜀" and "topic" in line
    assert not (clone / "NOTES.md").exists()


def test_루트_저장소를_받아_새로_등록된_서브모듈이_생기면_초기화가_필요하다고_알린다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    docs = sandbox.knowledge_remote("docs")
    root.register(billing)
    clone = root.set_up_clone()
    billing_tip = billing.commit()
    root.register(docs)  # 다른 기기에서 저장소를 하나 더 붙여 푸시했다

    result = _pull(sandbox, clone)

    assert result.returncode == 0, result.stderr
    outcomes = _outcomes(result)
    assert outcomes[ROOT][0] == "갱신됨"
    assert outcomes["projects/billing"][0] == "갱신됨"  # 초기화가 안 된 저장소가 있어도 나머지는 계속 처리한다
    assert sandbox.head(_sub(clone)) == billing_tip
    state, line = outcomes["projects/docs"]
    assert state == "건너뜀" and "초기화" in line and "just setup" in line
    assert "just setup" in result.stdout.split("== 요약 ==")[1].splitlines()[-1]  # 끝에서도 한 번 더 알린다
    assert not (_sub(clone, "docs") / ".git").exists()  # pull은 초기화하지 않는다

    follow_up = sandbox.just("setup", cwd=clone)
    assert follow_up.returncode == 0, follow_up.stderr
    assert sandbox.branch(_sub(clone, "docs")) == "main"


def test_gitmodules를_읽지_못하면_이유를_알리고_0이_아닌_종료_코드로_끝나며_루트_저장소는_처리한다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    clone = root.set_up_clone()
    (clone / ".gitmodules").write_text("[submodule\n", encoding="utf-8")

    result = _pull(sandbox, clone)

    assert result.returncode != 0
    assert ".gitmodules" in result.stderr
    assert ROOT in _outcomes(result)


def test_하위_디렉토리에서_불러도_루트_저장소를_기준으로_받는다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    latest = billing.commit()

    result = sandbox.just("git", "pull", cwd=clone / "docs")

    assert result.returncode == 0, result.stderr
    assert sandbox.head(_sub(clone)) == latest


# --- 커밋하지 않는다 --------------------------------------------------------------------


def test_지식_저장소가_올라가면_루트의_서브모듈_포인터_변경은_커밋되지_않은_채_남고_어디가_바뀌었는지_알린다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    docs = sandbox.knowledge_remote("docs")
    root.register(billing)
    root.register(docs)
    clone = root.set_up_clone()
    root_head = sandbox.head(clone)
    billing.commit()

    result = _pull(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.head(clone) == root_head  # 루트에 커밋하지 않았다
    assert sandbox.git("diff", "--cached", "--name-only", cwd=clone).stdout == ""  # 스테이징도 하지 않았다
    assert sandbox.git("status", "--porcelain", cwd=clone).stdout.splitlines() == [" M projects/billing"]
    notice = result.stdout.split("서브모듈 포인터")[1]  # 안내 아래에 바뀐 저장소만 적힌다
    assert "projects/billing" in notice and "projects/docs" not in notice


def test_루트가_기록한_커밋으로_올라간_지식_저장소는_포인터_변경으로_알리지_않는다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    latest = billing.commit()
    root.point_at("billing", latest)  # 다른 기기가 새 커밋을 루트에 기록해 푸시했다

    result = _pull(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.head(_sub(clone)) == latest
    assert sandbox.git("status", "--porcelain", cwd=clone).stdout == ""
    assert "서브모듈 포인터" not in result.stdout


def test_받는_동안_어떤_저장소에도_커밋을_만들지_않는다(sandbox):
    """fast-forward는 원격의 커밋을 그대로 가져올 뿐이라 병합 커밋도, 새 커밋도 생기지 않는다."""
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    sub = _sub(clone)
    latest = billing.commit()
    root_commits = sandbox.git("rev-list", "--count", "--all", cwd=clone).stdout.strip()

    assert _pull(sandbox, clone).returncode == 0

    assert sandbox.head(sub) == latest
    assert sandbox.git("rev-list", "--count", "--merges", "HEAD", cwd=sub).stdout.strip() == "0"
    assert sandbox.git("rev-list", "--count", "--all", cwd=clone).stdout.strip() == root_commits
    assert sandbox.git("rev-list", "--count", "HEAD", cwd=sub).stdout == sandbox.git("rev-list", "--count", latest, cwd=billing.seed).stdout


# --- 사용자의 git 설정이 약속을 깨지 않는다 -----------------------------------------------------


def _enable_autostash(sandbox, how, repo):
    """미커밋 변경을 스태시했다가 다시 적용하게 하는 git 설정을 켠다. 받기가 이 설정을 따르면 겹치는 변경이 섞인다."""
    if how == "전역_autoStash":
        sandbox.git("config", "--global", "merge.autoStash", "true", cwd=repo)
    else:
        sandbox.git("config", "branch.main.mergeOptions", "--autostash", cwd=repo)


@pytest.mark.parametrize("how", ["전역_autoStash", "브랜치_mergeOptions"])
@pytest.mark.parametrize("target", ["지식_저장소", "루트_저장소"])
def test_merge_autoStash가_켜져_있어도_겹치는_미커밋_변경은_섞지_않고_건너뛴다(sandbox, target, how):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    repo, name = (_sub(clone), "projects/billing") if target == "지식_저장소" else (clone, ROOT)
    _enable_autostash(sandbox, how, repo)
    (repo / "README.md").write_text("# 내가 고치는 중\n", encoding="utf-8")
    head = sandbox.head(repo)
    before = sandbox.git("status", "--porcelain", cwd=repo).stdout
    new_readme = {"README.md": "# 원격이 고친 README\n"}
    if target == "지식_저장소":
        billing.commit(files=new_readme)
    else:
        root.commit(new_readme)

    result = _pull(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.head(repo) == head
    assert (repo / "README.md").read_text(encoding="utf-8") == "# 내가 고치는 중\n"  # 충돌 표시도, 섞인 내용도 없다
    assert sandbox.git("status", "--porcelain", cwd=repo).stdout == before
    assert sandbox.git("stash", "list", cwd=repo).stdout == ""
    state, line = _outcomes(result)[name]
    assert state == "건너뜀" and "README.md" in line and "미커밋" in line


def test_받아_올_파일과_같은_경로의_무시되는_로컬_파일은_덮어쓰지_않고_건너뛴_것으로_보고한다(sandbox):
    """`.gitignore`가 제외한 파일도 git에 없는 로컬 작업이다. 되돌릴 수 없으므로 추적하지 않는 파일처럼 지키고 거부한다."""
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing", files={"README.md": "# billing\n", ".gitignore": "scratch/\n"})
    root.register(billing)
    clone = root.set_up_clone()
    sub = _sub(clone)
    (sub / "scratch").mkdir()
    (sub / "scratch" / "todo.md").write_text("개인 메모\n", encoding="utf-8")
    head = sandbox.head(sub)
    billing.commit(files={".gitignore": "", "scratch/todo.md": "# 원격의 파일\n"})  # 원격이 무시 규칙을 풀고 같은 경로를 커밋했다

    result = _pull(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.head(sub) == head
    assert (sub / "scratch" / "todo.md").read_text(encoding="utf-8") == "개인 메모\n"
    state, line = _outcomes(result)["projects/billing"]
    assert state == "건너뜀" and "scratch/todo.md" in line and "무시" in line


# --- 추적 브랜치를 알 수 없는 경우 -------------------------------------------------------------


def _forget_remote_head(sandbox, sub):
    """서브모듈에서 `origin/HEAD`를 지운다. `.gitmodules`에 추적 브랜치가 없으면 추적 브랜치를 알 길이 그것뿐이다."""
    sandbox.git("remote", "set-head", "origin", "-d", cwd=sub)


def test_기록된_추적_브랜치가_없고_origin_HEAD가_지워졌어도_작업_브랜치를_올리지_않는다(sandbox):
    """기록된 추적 브랜치가 없으면 원격의 기본 브랜치(`origin/HEAD`)가 추적 브랜치다. 그것이 없을 때 루트처럼 현재 브랜치를 올리면 안 된다.

    fetch가 `origin/HEAD`를 다시 만들어 주는지는 git 버전과 설정(`remote.<이름>.followRemoteHEAD`)에 달려 있다.
    다시 만들면 "추적 브랜치가 아니라 feature에 있다", 만들지 않으면 "추적 브랜치를 알 수 없다"로 건너뛴다.
    어느 쪽이든 올리지 않고 fetch만 하는 것이 약속이므로, 이유의 문구가 아니라 그 결과를 확인한다.
    """
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)  # -b 없이 등록해 .gitmodules에 추적 브랜치가 없다
    clone = root.set_up_clone()
    sub = _sub(clone)
    sandbox.git("checkout", "-b", "feature", cwd=sub)
    feature_head = sandbox.head(sub)
    latest = billing.commit(branch="feature")  # 원격의 feature가 앞서 있다
    _forget_remote_head(sandbox, sub)

    result = _pull(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.branch(sub) == "feature" and sandbox.head(sub) == feature_head  # 올리지 않았다
    assert _remote_tip(sandbox, sub, "feature") == latest  # fetch는 했다
    state, line = _outcomes(result)["projects/billing"]
    assert state == "건너뜀" and "fetch만" in line


def test_추적_브랜치를_끝내_알_수_없으면_현재_브랜치를_올리지_않고_fetch만_하고_건너뛴다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    sub = _sub(clone)
    sandbox.git("checkout", "-b", "feature", cwd=sub)
    feature_head = sandbox.head(sub)
    latest = billing.commit(branch="feature")
    billing.set_default_branch("gone")  # 원격의 기본 브랜치가 가리키는 브랜치가 없어 fetch도 origin/HEAD를 만들지 못한다
    _forget_remote_head(sandbox, sub)

    result = _pull(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.branch(sub) == "feature" and sandbox.head(sub) == feature_head  # 루트처럼 현재 브랜치를 올리지 않았다
    assert _remote_tip(sandbox, sub, "feature") == latest  # fetch는 했다
    state, line = _outcomes(result)["projects/billing"]
    assert state == "건너뜀" and "추적 브랜치를 알 수 없" in line
