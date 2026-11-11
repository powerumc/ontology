"""`just setup`: 새로 클론한 루트 저장소를 한 번에 작업할 수 있는 상태로 만든다."""

import re
import shutil

import pytest

from support.sandbox import REQUIRED_TOOLS


@pytest.mark.parametrize("missing", [("git",), ("just",), ("uv",), ("git", "uv")], ids="+".join)
def test_필요한_도구가_없으면_없는_도구를_이름으로_알리고_0이_아닌_종료_코드로_끝난다(sandbox, missing):
    root = sandbox.root().work

    result = sandbox.just("setup", cwd=root, without=missing)

    output = result.stdout + result.stderr
    assert result.returncode != 0
    for tool in REQUIRED_TOOLS:
        assert bool(re.search(rf"\b{tool}\b", output)) == (tool in missing), output


def test_서브모듈이_하나도_없는_루트_저장소에서도_성공한다(sandbox):
    clone = sandbox.root().clone()

    result = sandbox.just("setup", cwd=clone)

    assert result.returncode == 0, result.stderr
    assert not (clone / "projects").exists()


def test_새로_클론한_뒤_setup하면_서브모듈이_초기화되고_추적_브랜치에_체크아웃된다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    recorded = root.register(billing)
    clone = root.clone()

    result = sandbox.just("setup", cwd=clone)

    assert result.returncode == 0, result.stderr
    sub = clone / "projects" / "billing"
    assert (sub / "README.md").is_file()
    assert sandbox.branch(sub) == "main"  # detached HEAD가 아니다
    assert sandbox.head(sub) == recorded


def _snapshot(sandbox, clone):
    """루트 저장소와 각 서브모듈의 상태: 브랜치, HEAD, 작업 트리 변경."""
    state = {"root": sandbox.git("status", "--porcelain", cwd=clone).stdout}
    for sub in sorted((clone / "projects").iterdir()):
        state[sub.name] = (sandbox.branch(sub), sandbox.head(sub))
    return state


def test_추적_브랜치는_루트가_기록한_커밋을_가리키고_원격의_최신으로_올리지_않는다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    recorded = root.register(billing)
    latest = billing.commit()  # 등록한 뒤 원격이 앞으로 나아갔다
    clone = root.clone()

    result = sandbox.just("setup", cwd=clone)

    sub = clone / "projects" / "billing"
    assert result.returncode == 0, result.stderr
    assert latest != recorded
    assert sandbox.branch(sub) == "main"
    assert sandbox.head(sub) == recorded
    assert sandbox.git("rev-parse", "origin/main", cwd=sub).stdout.strip() == latest  # 원격은 앞서 있지만
    assert sandbox.git("status", "--porcelain", cwd=clone).stdout == ""  # 루트에 서브모듈 포인터 차이가 없다


def test_기본_브랜치가_아닌_추적_브랜치도_기록된_커밋에_체크아웃된다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    docs = sandbox.knowledge_remote("docs")
    docs.commit(branch="dev")
    root.register(billing)
    recorded = root.register(docs, branch="dev")
    docs.commit(branch="dev")
    clone = root.clone()

    result = sandbox.just("setup", cwd=clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.branch(clone / "projects" / "billing") == "main"
    docs_clone = clone / "projects" / "docs"
    assert sandbox.branch(docs_clone) == "dev"
    assert sandbox.head(docs_clone) == recorded
    assert sandbox.git("rev-parse", "--abbrev-ref", "dev@{upstream}", cwd=docs_clone).stdout.strip() == "origin/dev"
    assert sandbox.git("status", "--porcelain", cwd=clone).stdout == ""


def test_기록된_커밋이_추적_브랜치의_이력에_없으면_detached_HEAD로_두고_보고한다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    side_commit = billing.commit(branch="feature")  # main의 이력에 없는 커밋
    root.register(billing)
    root.point_at("billing", side_commit)
    clone = root.clone()

    result = sandbox.just("setup", cwd=clone)

    sub = clone / "projects" / "billing"
    assert result.returncode == 0, result.stderr
    assert sandbox.branch(sub) is None
    assert sandbox.head(sub) == side_commit
    assert "projects/billing" in result.stdout + result.stderr  # 보고한다


def test_이미_추적_브랜치에_있고_로컬_커밋이_있는_서브모듈은_건드리지_않는다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    clone = root.clone()
    assert sandbox.just("setup", cwd=clone).returncode == 0
    sub = clone / "projects" / "billing"
    (sub / "local.md").write_text("# 로컬 작업\n", encoding="utf-8")
    sandbox.git("add", "local.md", cwd=sub)
    sandbox.git("commit", "-m", "local work", cwd=sub)
    local_head = sandbox.head(sub)

    result = sandbox.just("setup", cwd=clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.branch(sub) == "main"
    assert sandbox.head(sub) == local_head


def test_setup을_다시_실행해도_결과가_같다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    docs = sandbox.knowledge_remote("docs")
    root.register(billing)
    billing.commit()
    root.register(docs)
    root.point_at("docs", docs.commit(branch="feature"))  # detached로 남는 경우도 포함한다
    clone = root.clone()

    first = sandbox.just("setup", cwd=clone)
    after_first = _snapshot(sandbox, clone)
    second = sandbox.just("setup", cwd=clone)

    assert first.returncode == 0 and second.returncode == 0, first.stderr + second.stderr
    assert _snapshot(sandbox, clone) == after_first


def test_setup은_아무것도_커밋하지_않는다(sandbox):
    root = sandbox.root()
    recorded = root.register(sandbox.knowledge_remote("billing"))
    clone = root.clone()
    root_head = sandbox.head(clone)

    result = sandbox.just("setup", cwd=clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.head(clone) == root_head
    assert sandbox.head(clone / "projects" / "billing") == recorded


def test_초기화하지_못한_서브모듈이_있어도_나머지를_설정하고_0이_아닌_종료_코드로_끝난다(sandbox):
    root = sandbox.root()
    broken = sandbox.knowledge_remote("broken")
    root.register(broken)
    root.register(sandbox.knowledge_remote("billing"))
    clone = root.clone()
    shutil.rmtree(broken.url)  # 원격에 닿을 수 없는 서브모듈

    result = sandbox.just("setup", cwd=clone)

    assert result.returncode != 0
    assert "projects/broken" in result.stderr
    assert sandbox.branch(clone / "projects" / "billing") == "main"


def test_기록된_커밋에서_detached된_서브모듈의_로컬_브랜치에_푸시하지_않은_커밋이_있으면_브랜치를_되돌리지_않는다(sandbox):
    """서브모듈에서 커밋한 뒤 `git submodule update`를 하면 HEAD가 기록된 커밋으로 detached된다."""
    root = sandbox.root()
    recorded = root.register(sandbox.knowledge_remote("billing"))
    clone = root.clone()
    assert sandbox.just("setup", cwd=clone).returncode == 0
    sub = clone / "projects" / "billing"
    (sub / "local.md").write_text("# 로컬 작업\n", encoding="utf-8")
    sandbox.git("add", "local.md", cwd=sub)
    sandbox.git("commit", "-m", "local work", cwd=sub)
    local_tip = sandbox.head(sub)
    sandbox.git("submodule", "update", "--", "projects/billing", cwd=clone)
    assert sandbox.head(sub) == recorded and sandbox.branch(sub) is None

    result = sandbox.just("setup", cwd=clone)

    assert result.returncode == 0, result.stderr
    assert sandbox.git("rev-parse", "main", cwd=sub).stdout.strip() == local_tip  # 로컬 커밋을 잃지 않았다
    assert sandbox.branch(sub) is None
    assert "projects/billing" in result.stdout + result.stderr  # 보고한다


def test_인자_없이_just만_부르면_명령_목록을_보여_주고_setup을_실행하지_않는다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    clone = root.clone()

    result = sandbox.just(cwd=clone)

    assert result.returncode == 0, result.stderr
    assert "setup" in result.stdout
    assert not (clone / "projects" / "billing" / "README.md").exists()  # 서브모듈을 초기화하지 않았다


def test_명령_목록은_setup이_무엇을_하는_명령인지_한_줄로_보여_준다(sandbox):
    """just는 레시피 바로 위의 주석 한 줄만 설명으로 쓴다. 처음 쓰는 사람이 이 목록으로 setup을 알아본다."""
    clone = sandbox.root().clone()

    result = sandbox.just(cwd=clone)

    setup_line = next(line for line in result.stdout.splitlines() if line.split()[:1] == ["setup"])
    assert "새로 클론한 루트 저장소를 작업할 수 있는 상태로 만든다" in setup_line


def test_gitmodules를_읽지_못하면_성공으로_넘기지_않고_0이_아닌_종료_코드로_끝난다(sandbox):
    """동시에 저장소를 붙이다 `.gitmodules`에 충돌 표시가 남은 경우."""
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    clone = root.clone()
    (clone / ".gitmodules").write_text("<<<<<<< HEAD\n[submodule \"projects/billing\"]\n=======\n>>>>>>> other\n", encoding="utf-8")

    result = sandbox.just("setup", cwd=clone)

    assert result.returncode != 0
    assert ".gitmodules" in result.stderr


def test_gitmodules에는_있지만_루트에_기록된_커밋이_없는_항목은_건너뛰고_보고한다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    root.register(sandbox.knowledge_remote("docs"))
    clone = root.clone()
    sandbox.git("rm", "--cached", "projects/billing", cwd=clone)  # gitlink만 사라지고 .gitmodules 항목이 남는다

    result = sandbox.just("setup", cwd=clone)

    assert result.returncode == 0, result.stderr
    assert "projects/billing" in result.stderr  # 보고한다
    assert sandbox.branch(clone / "projects" / "docs") == "main"  # 나머지는 설정한다


def test_이름에_공백이_든_서브모듈도_설정한다(sandbox):
    root = sandbox.root()
    recorded = root.register(sandbox.knowledge_remote("billing"), name="my repo")
    root.register(sandbox.knowledge_remote("docs"))
    clone = root.clone()

    result = sandbox.just("setup", cwd=clone)

    assert result.returncode == 0, result.stderr
    spaced = clone / "projects" / "my repo"
    assert sandbox.branch(spaced) == "main"
    assert sandbox.head(spaced) == recorded
    assert sandbox.branch(clone / "projects" / "docs") == "main"
