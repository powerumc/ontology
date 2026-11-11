"""`just git status`: 루트 저장소와 지식 저장소별 브랜치, 미커밋 변경, 미푸시 커밋, 뒤처진 커밋을 한 화면에 요약한다."""

import os

ROOT = "루트 저장소"


def _status(sandbox, clone):
    return sandbox.just("git", "status", cwd=clone)


def _line(result, name):
    """저장소 `name`의 요약 줄. `<이름>: 브랜치 …, 미커밋 …, 미푸시 …, 뒤처짐 …` 꼴이다."""
    lines = [line for line in result.stdout.splitlines() if line.startswith(f"{name}: ")]
    assert len(lines) == 1, f"{name}의 줄이 하나여야 한다:\n{result.stdout}"
    return lines[0]


def _sub(clone, name="billing"):
    return clone / "projects" / name


def _local_commit(sandbox, repo, filename="local.md"):
    (repo / filename).write_text(f"# {filename}\n", encoding="utf-8")
    sandbox.git("add", filename, cwd=repo)
    sandbox.git("commit", "-m", f"작업 {filename}", cwd=repo)


def test_깨끗한_저장소는_브랜치와_함께_미커밋_없음_미푸시_0_뒤처짐_0으로_보인다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    clone = root.set_up_clone()

    result = _status(sandbox, clone)

    assert result.returncode == 0, result.stderr
    for name in (ROOT, "projects/billing"):
        line = _line(result, name)
        assert "브랜치 main" in line
        assert "미커밋 없음" in line and "미푸시 0" in line and "뒤처짐 0" in line


def test_저장소마다_따로_세어_보여_준다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    docs = sandbox.knowledge_remote("docs")
    root.register(billing)
    root.register(docs)
    clone = root.set_up_clone()
    sub = _sub(clone)
    (sub / "README.md").write_text("# 고침\n", encoding="utf-8")  # 추적하는 파일의 수정
    (sub / "draft.md").write_text("# 초안\n", encoding="utf-8")  # 추적하지 않는 파일
    _local_commit(sandbox, sub, "a.md")
    _local_commit(sandbox, sub, "b.md")  # 미푸시 2
    billing.commit()
    billing.commit()
    billing.commit()
    sandbox.git("fetch", "origin", cwd=sub)  # 뒤처짐 3(받아 둔 원격 정보 기준)

    result = _status(sandbox, clone)

    line = _line(result, "projects/billing")
    assert "미커밋 2개" in line and "미푸시 2" in line and "뒤처짐 3" in line
    other = _line(result, "projects/docs")  # 다른 저장소는 영향이 없다
    assert "미커밋 없음" in other and "미푸시 0" in other and "뒤처짐 0" in other


def test_루트_저장소의_미커밋_변경과_미푸시_커밋과_뒤처짐도_센다(sandbox):
    root = sandbox.root()
    clone = root.clone()
    (clone / "README.md").write_text("# 고침\n", encoding="utf-8")
    _local_commit(sandbox, clone)
    root.commit({"NOTES.md": "# 메모\n"})
    sandbox.git("fetch", "origin", cwd=clone)

    result = _status(sandbox, clone)

    line = _line(result, ROOT)
    assert "미커밋 1개" in line and "미푸시 1" in line and "뒤처짐 1" in line


def test_작업_브랜치는_같은_이름의_원격_브랜치와_비교하고_원격에_없으면_그_브랜치의_커밋이_모두_미푸시다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    sub = _sub(clone)
    sandbox.git("checkout", "-b", "feature", cwd=sub)
    _local_commit(sandbox, sub, "a.md")
    _local_commit(sandbox, sub, "b.md")

    not_on_remote = _line(_status(sandbox, clone), "projects/billing")
    sandbox.git("push", "origin", "feature", cwd=sub)
    _local_commit(sandbox, sub, "c.md")
    on_remote = _line(_status(sandbox, clone), "projects/billing")

    assert "브랜치 feature" in not_on_remote and "미푸시 2" in not_on_remote and "feature" in not_on_remote.split("미푸시")[1]
    assert "브랜치 feature" in on_remote and "미푸시 1" in on_remote and "뒤처짐 0" in on_remote


def test_detached_HEAD는_그렇다고_알리고_원격에_없는_커밋을_미푸시로_센다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    clone = root.set_up_clone()
    sub = _sub(clone)
    sandbox.git("checkout", "--detach", cwd=sub)
    _local_commit(sandbox, sub)

    line = _line(_status(sandbox, clone), "projects/billing")

    assert "detached HEAD" in line and "미푸시 1" in line


def test_초기화되지_않은_지식_저장소는_그렇다고_알린다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    clone = root.clone()  # 서브모듈을 초기화하지 않았다

    result = _status(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert "초기화" in _line(result, "projects/billing")
    assert "브랜치 main" in _line(result, ROOT)


def test_지식_저장소가_하나도_없어도_루트_저장소를_보여_준다(sandbox):
    clone = sandbox.root().clone()

    result = _status(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert "브랜치 main" in _line(result, ROOT)


def test_루트의_서브모듈_포인터_변경은_루트의_미커밋_변경으로_세고_어느_저장소인지_알린다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    root.register(sandbox.knowledge_remote("docs"))
    clone = root.set_up_clone()
    billing.commit()
    assert sandbox.just("git", "pull", cwd=clone).returncode == 0  # billing이 올라가 포인터가 달라졌다

    result = _status(sandbox, clone)

    assert "미커밋 1개" in _line(result, ROOT)
    assert "미커밋 없음" in _line(result, "projects/billing")  # 서브모듈 안의 변경이 아니다
    notice = next(line for line in result.stdout.splitlines() if "서브모듈 포인터" in line)
    assert "projects/billing" in notice and "projects/docs" not in notice


def test_서브모듈_안의_변경은_루트의_미커밋_변경으로_세지_않는다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    clone = root.set_up_clone()
    (_sub(clone) / "README.md").write_text("# 고침\n", encoding="utf-8")

    result = _status(sandbox, clone)

    assert "미커밋 없음" in _line(result, ROOT)
    assert "미커밋 1개" in _line(result, "projects/billing")


# --- 원격에 접속하지 않고, 아무것도 바꾸지 않는다 ------------------------------------------------


def test_원격에_접속하지_않으므로_뒤처짐은_마지막으로_받은_원격_정보_기준이다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    sub = _sub(clone)
    known_tip = sandbox.git("rev-parse", "origin/main", cwd=sub).stdout.strip()
    billing.commit()
    billing.commit()  # 원격은 앞서 갔지만 받아 오지 않았다

    result = _status(sandbox, clone)

    assert "뒤처짐 0" in _line(result, "projects/billing")  # 모르는 것은 세지 않는다
    assert sandbox.git("rev-parse", "origin/main", cwd=sub).stdout.strip() == known_tip  # fetch하지 않았다
    assert "원격" in result.stdout.splitlines()[-1] and "pull" in result.stdout.splitlines()[-1]  # 기준을 알린다


def test_원격에_접속할_수_없어도_로컬_정보로_요약하고_조용히_끝난다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    billing.url.rename(billing.url.with_name("moved-away.git"))
    root.origin.rename(root.origin.with_name("root-moved-away.git"))

    result = _status(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "브랜치 main" in _line(result, "projects/billing")


def test_아무것도_바꾸거나_커밋하지_않는다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    clone = root.set_up_clone()
    sub = _sub(clone)
    (sub / "README.md").write_text("# 고침\n", encoding="utf-8")
    (clone / "NOTES.md").write_text("# 메모\n", encoding="utf-8")
    billing.commit()
    before_root = sandbox.snapshot(clone)
    before_sub = sandbox.snapshot(sub)
    os.utime(clone / "README.md")  # 내용은 그대로, 인덱스에 적힌 시각만 낡게 한다. 상태를 읽다가 인덱스를 새로 쓰기 쉬운 경우다
    index_before = (clone / ".git" / "index").stat()

    result = _status(sandbox, clone)

    index_after = (clone / ".git" / "index").stat()
    assert result.returncode == 0, result.stderr
    assert (index_after.st_mtime_ns, index_after.st_ino) == (index_before.st_mtime_ns, index_before.st_ino)  # 읽기만 한다
    assert sandbox.snapshot(clone) == before_root
    assert sandbox.snapshot(sub) == before_sub


def test_하위_디렉토리에서_불러도_루트_저장소를_기준으로_보여_준다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    clone = root.set_up_clone()

    result = sandbox.just("git", "status", cwd=clone / "docs")

    assert result.returncode == 0, result.stderr
    assert "브랜치 main" in _line(result, "projects/billing")
