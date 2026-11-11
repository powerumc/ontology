"""`just repo remove <이름> [--force]`: 지식 저장소를 서브모듈의 흔적까지 완전히 제거한다."""

import shutil
from pathlib import Path

import pytest


def _add(sandbox, root, *args):
    return sandbox.just("repo", "add", *args, cwd=root.work)


def _remove(sandbox, root, *args, cwd=None):
    return sandbox.just("repo", "remove", *args, cwd=cwd or root.work)


def _sub(root, name="billing"):
    return root.work / "projects" / name


def _local_commit(sandbox, sub, filename="local.md"):
    """서브모듈의 현재 HEAD에 커밋 하나를 쌓는다. 푸시하지 않는다."""
    (sub / filename).write_text(f"# {filename}\n", encoding="utf-8")
    sandbox.git("add", filename, cwd=sub)
    sandbox.git("commit", "-m", f"작업 {filename}", cwd=sub)


def _sub_state(sandbox, sub):
    """서브모듈 안의 상태. 거부된 제거가 지식 저장소의 작업을 건드리지 않았는지 본다."""
    return {
        "head": sandbox.head(sub),
        "branch": sandbox.branch(sub),
        "status": sandbox.git("status", "--porcelain", "--untracked-files=all", cwd=sub).stdout,
        "refs": sandbox.git("for-each-ref", cwd=sub).stdout,
        "stash": sandbox.git("stash", "list", cwd=sub).stdout,
    }


def _refused_leaving_everything_unchanged(sandbox, root, *args, name="billing", sub_readable=True):
    """제거를 거부했는지, 루트 저장소와 지식 저장소 어느 쪽도 바뀌지 않았는지 확인하고 결과를 돌려준다.

    `sub_readable=False`는 서브모듈 저장소가 망가져 git으로 상태를 읽을 수 없는 경우다.
    """
    sub = _sub(root, name)
    root_before = sandbox.snapshot(root.work)
    sub_before = _sub_state(sandbox, sub) if sub_readable and (sub / ".git").exists() else None

    result = _remove(sandbox, root, name, *args)

    assert result.returncode != 0
    assert sandbox.snapshot(root.work) == root_before
    if sub_before is not None:
        assert _sub_state(sandbox, sub) == sub_before
    return result


# --- 완전히 제거한다 -----------------------------------------------------------------


def test_제거하면_작업_트리와_등록_정보와_git_내부의_서브모듈_저장소가_모두_사라진다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    root_head = sandbox.head(root.work)

    result = _remove(sandbox, root, "billing")

    state = sandbox.snapshot(root.work)
    assert result.returncode == 0, result.stderr
    assert not _sub(root).exists()  # 작업 트리
    assert state["gitmodules"] is None  # 등록 정보
    assert state["config"] == ""  # 로컬 설정의 등록 정보
    assert state["modules"] == []  # git 내부에 남는 서브모듈 저장소
    assert "160000" not in {line.split()[0] for line in state["index"].splitlines()}
    assert state["projects"] is None
    assert sandbox.head(root.work) == root_head  # 커밋하지 않는다
    assert state["status"].splitlines() == ["D  .gitmodules", "D  projects/billing"]  # 스테이징까지만 한다


def test_다른_지식_저장소는_그대로_둔다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    root.register(sandbox.knowledge_remote("docs"))

    result = _remove(sandbox, root, "billing")

    state = sandbox.snapshot(root.work)
    assert result.returncode == 0, result.stderr
    assert not _sub(root).exists()
    assert (_sub(root, "docs") / "README.md").is_file()
    assert sandbox.branch(_sub(root, "docs")) == "main"
    assert state["modules"] == ["modules/projects/docs"]
    assert "submodule.projects/docs.url" in state["config"]
    assert "projects/billing" not in (root.work / ".gitmodules").read_text(encoding="utf-8")
    assert "projects/docs" in (root.work / ".gitmodules").read_text(encoding="utf-8")
    assert state["projects"] == ["docs"]


def test_방금_등록하고_커밋하지_않은_저장소를_제거하면_등록_전_상태로_돌아간다(sandbox):
    root = sandbox.root()
    before = sandbox.snapshot(root.work)
    assert _add(sandbox, root, sandbox.knowledge_remote("billing").url).returncode == 0

    result = _remove(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert sandbox.snapshot(root.work) == before


def test_이름에_공백이_든_저장소도_제거한다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"), name="my repo")

    result = _remove(sandbox, root, "my repo")

    state = sandbox.snapshot(root.work)
    assert result.returncode == 0, result.stderr
    assert state["modules"] == [] and state["projects"] is None and state["gitmodules"] is None


def test_하위_디렉토리에서_불러도_루트_저장소를_기준으로_제거한다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    deeper = root.work / "docs" / "deeper"
    deeper.mkdir(parents=True)

    result = _remove(sandbox, root, "billing", cwd=deeper)

    assert result.returncode == 0, result.stderr
    assert not _sub(root).exists()


# --- 제거한 뒤 같은 이름으로 다시 등록한다 -----------------------------------------


def test_제거한_뒤_같은_이름으로_다시_등록할_수_있다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    assert _remove(sandbox, root, "billing").returncode == 0

    result = _add(sandbox, root, billing.url)

    assert result.returncode == 0, result.stderr
    assert sandbox.branch(_sub(root)) == "main"
    assert (_sub(root) / "README.md").is_file()


def test_방금_등록하고_제거한_이름도_다시_등록할_수_있다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    assert _add(sandbox, root, billing.url).returncode == 0
    assert _remove(sandbox, root, "billing").returncode == 0

    result = _add(sandbox, root, billing.url)

    assert result.returncode == 0, result.stderr
    assert sandbox.branch(_sub(root)) == "main"


# --- 없는 이름 -----------------------------------------------------------------------


def test_없는_이름을_제거하려_하면_오류로_알리고_아무것도_바꾸지_않는다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    before = sandbox.snapshot(root.work)

    result = _remove(sandbox, root, "nope")

    assert result.returncode != 0
    assert "nope" in result.stderr
    assert sandbox.snapshot(root.work) == before


def test_등록된_저장소가_아닌_디렉토리는_이름이_같아도_지우지_않는다(sandbox):
    root = sandbox.root()
    plain = _sub(root, "notes")
    plain.mkdir(parents=True)
    (plain / "mine.md").write_text("# 내 메모\n", encoding="utf-8")
    before = sandbox.snapshot(root.work)

    result = _remove(sandbox, root, "notes", "--force")

    assert result.returncode != 0
    assert (plain / "mine.md").read_text(encoding="utf-8") == "# 내 메모\n"
    assert sandbox.snapshot(root.work) == before


@pytest.mark.parametrize("name", ["bill*", "bill?ng", "../projects/billing", "projects/billing", "billing/"])
def test_이름은_글롭이나_경로가_아니라_글자_그대로_찾아서_다른_저장소를_지우지_않는다(sandbox, name):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    before = sandbox.snapshot(root.work)

    result = _remove(sandbox, root, name, "--force")

    assert result.returncode != 0
    assert (_sub(root) / "README.md").is_file()
    assert sandbox.snapshot(root.work) == before


@pytest.mark.parametrize("args", [[], ["billing", "--bogus"], ["billing", "docs"]], ids=["이름_없음", "모르는_옵션", "이름_둘"])
def test_잘못된_인자는_오류로_알리고_아무것도_바꾸지_않는다(sandbox, args):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    root.register(sandbox.knowledge_remote("docs"))
    before = sandbox.snapshot(root.work)

    result = _remove(sandbox, root, *args)

    assert result.returncode != 0
    assert result.stderr
    assert sandbox.snapshot(root.work) == before
    assert (_sub(root) / "README.md").is_file()


# --- 지식 저장소의 작업이 있으면 거부한다 -------------------------------------------


def _modify_tracked_file(sandbox, sub):
    (sub / "README.md").write_text("# 고친 README\n", encoding="utf-8")


def _add_untracked_file(sandbox, sub):
    (sub / "draft.md").write_text("# 초안\n", encoding="utf-8")


def _stage_new_file(sandbox, sub):
    (sub / "staged.md").write_text("# 스테이지\n", encoding="utf-8")
    sandbox.git("add", "staged.md", cwd=sub)


@pytest.mark.parametrize(
    ("make_dirty", "filename"),
    [
        (_modify_tracked_file, "README.md"),
        (_add_untracked_file, "draft.md"),
        (_stage_new_file, "staged.md"),
    ],
    ids=["고친_파일", "추적하지_않는_새_파일", "스테이지한_새_파일"],
)
def test_미커밋_변경이_있는_지식_저장소는_제거를_거부한다(sandbox, make_dirty, filename):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    make_dirty(sandbox, _sub(root))

    result = _refused_leaving_everything_unchanged(sandbox, root)

    assert "미커밋" in result.stderr
    assert filename in result.stderr  # 무엇이 버려지는지 알린다


def test_추적_브랜치에_푸시하지_않은_커밋이_있으면_제거를_거부한다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    _local_commit(sandbox, _sub(root))

    result = _refused_leaving_everything_unchanged(sandbox, root)

    assert "원격에 없는 커밋" in result.stderr
    assert "작업 local.md" in result.stderr  # 어느 커밋이 버려지는지 알린다


def test_현재_브랜치가_아니어도_어느_로컬_브랜치든_원격에_없는_커밋이_있으면_거부한다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    sub = _sub(root)
    sandbox.git("checkout", "-b", "feature", cwd=sub)
    _local_commit(sandbox, sub)
    sandbox.git("checkout", "main", cwd=sub)  # 푸시하지 않은 커밋은 다른 브랜치에 있다
    assert sandbox.branch(sub) == "main"

    result = _refused_leaving_everything_unchanged(sandbox, root)

    assert "원격에 없는 커밋" in result.stderr
    assert "feature" in result.stderr


def test_detached_HEAD에서_쌓은_커밋도_원격에_없으면_거부한다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    sub = _sub(root)
    sandbox.git("checkout", "--detach", cwd=sub)
    _local_commit(sandbox, sub)  # 어느 브랜치에도 속하지 않는 커밋

    result = _refused_leaving_everything_unchanged(sandbox, root)

    assert "원격에 없는 커밋" in result.stderr


def test_원격에_같은_이름이_없는_새_로컬_브랜치의_커밋도_거부한다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    sub = _sub(root)
    sandbox.git("checkout", "-b", "idea", cwd=sub)
    _local_commit(sandbox, sub)
    sandbox.git("checkout", "main", cwd=sub)

    _refused_leaving_everything_unchanged(sandbox, root)


def test_스태시에_남긴_작업이_있으면_제거를_거부한다(sandbox):
    """스태시는 서브모듈의 git 저장소 안에만 있어서, 제거하면 흔적 없이 사라진다."""
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    sub = _sub(root)
    (sub / "README.md").write_text("# 잠시 치워 둔 변경\n", encoding="utf-8")
    sandbox.git("stash", cwd=sub)
    assert sandbox.git("status", "--porcelain", cwd=sub).stdout == ""

    result = _refused_leaving_everything_unchanged(sandbox, root)

    assert "스태시" in result.stderr


def test_푸시까지_마친_작업은_제거를_막지_않는다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    sub = _sub(root)
    sandbox.git("checkout", "-b", "feature", cwd=sub)
    _local_commit(sandbox, sub)
    sandbox.git("push", "-u", "origin", "feature", cwd=sub)  # 다른 브랜치에 있는 커밋도 푸시했다
    sandbox.git("checkout", "main", cwd=sub)
    _local_commit(sandbox, sub, "main-work.md")
    sandbox.git("push", "origin", "main", cwd=sub)

    result = _remove(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert not _sub(root).exists()


def test_무시되는_파일만_있으면_제거를_막지_않는다(sandbox):
    """최신화(#12)가 복사하는 `.onto/` 같은 루트 관리 파일은 지식 저장소의 `.gitignore`로 제외된다."""
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    sub = _sub(root)
    exclude = Path(sandbox.git("rev-parse", "--path-format=absolute", "--git-path", "info/exclude", cwd=sub).stdout.strip())
    exclude.write_text(".onto/\n", encoding="utf-8")
    (sub / ".onto").mkdir()
    (sub / ".onto" / "Justfile").write_text("# 복사된 기능\n", encoding="utf-8")
    assert sandbox.git("status", "--porcelain", cwd=sub).stdout == ""

    result = _remove(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert not _sub(root).exists()


def test_거부할_때는_이유와_강제_옵션이_있다는_것을_알린다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    _add_untracked_file(sandbox, _sub(root))

    result = _refused_leaving_everything_unchanged(sandbox, root)

    assert "--force" in result.stderr
    assert "just repo remove billing --force" in result.stderr  # 그대로 붙여 쓸 수 있다


def test_이름에_공백이_들어_있으면_강제_옵션_안내가_따옴표로_감싼다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"), name="my repo")
    _add_untracked_file(sandbox, _sub(root, "my repo"))

    result = _refused_leaving_everything_unchanged(sandbox, root, name="my repo")

    assert "just repo remove 'my repo' --force" in result.stderr


# --- 강제 옵션 ----------------------------------------------------------------------


@pytest.mark.parametrize("flag", ["--force", "-f"])
def test_강제_옵션을_주면_미커밋과_미푸시_작업이_있어도_제거하고_버려지는_것을_출력에_남긴다(sandbox, flag):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    sub = _sub(root)
    _local_commit(sandbox, sub)  # 푸시하지 않은 커밋
    sandbox.git("checkout", "-b", "feature", cwd=sub)
    _local_commit(sandbox, sub, "feature-work.md")  # 다른 브랜치의 푸시하지 않은 커밋
    _add_untracked_file(sandbox, sub)  # 미커밋 변경

    result = _remove(sandbox, root, "billing", flag)

    output = result.stdout + result.stderr
    state = sandbox.snapshot(root.work)
    assert result.returncode == 0, result.stderr
    assert not _sub(root).exists()
    assert state["modules"] == [] and state["config"] == "" and state["gitmodules"] is None
    assert "draft.md" in output  # 버려지는 미커밋 변경
    assert "작업 local.md" in output and "작업 feature-work.md" in output  # 버려지는 커밋


def test_강제_옵션은_이름_앞에_와도_된다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    _add_untracked_file(sandbox, _sub(root))

    result = _remove(sandbox, root, "--force", "billing")

    assert result.returncode == 0, result.stderr
    assert not _sub(root).exists()


def test_방금_등록한_저장소에_최신화가_만든_파일이_있어도_강제로_바로_뗄_수_있다(sandbox):
    """등록 직후에는 최신화(#12)가 만든 파일 때문에 미커밋 변경이 있다. 잘못 붙인 저장소를 바로 떼려면 강제 옵션이 필요하다."""
    root = sandbox.root()
    before = sandbox.snapshot(root.work)
    assert _add(sandbox, root, sandbox.knowledge_remote("billing").url).returncode == 0
    sub = _sub(root)
    (sub / "CLAUDE.md").write_text("# 최신화가 쓴 블록\n", encoding="utf-8")
    (sub / "docs" / "ontology").mkdir(parents=True)
    (sub / "docs" / "ontology" / "ontology.yaml").write_text("name: billing\n", encoding="utf-8")

    refused = _remove(sandbox, root, "billing")
    assert refused.returncode != 0 and _sub(root).exists()

    forced = _remove(sandbox, root, "billing", "--force")

    assert forced.returncode == 0, forced.stderr
    assert sandbox.snapshot(root.work) == before


# --- 아직 초기화하지 않은 지식 저장소 -------------------------------------------------


def test_초기화하지_않은_서브모듈도_제거하고_루트_저장소의_작업_트리를_건드리지_않는다(sandbox):
    """새로 클론한 직후(`just setup` 전)의 `projects/<이름>/`은 빈 디렉토리다. 그 안에서 git을 부르면 루트 저장소가 나온다."""
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    clone = root.clone()
    assert not (clone / "projects" / "billing" / ".git").exists()

    result = sandbox.just("repo", "remove", "billing", cwd=clone)

    assert result.returncode == 0, result.stderr
    assert not (clone / "projects" / "billing").exists()
    assert (clone / "README.md").is_file() and (clone / "Justfile").is_file()  # 루트 저장소의 파일이 그대로다
    assert sandbox.git("status", "--porcelain", cwd=clone).stdout.splitlines() == ["D  .gitmodules", "D  projects/billing"]


def test_초기화하지_않은_자리에_사용자의_파일이_있으면_거부한다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    clone = root.clone()
    (clone / "projects" / "billing").mkdir(parents=True, exist_ok=True)
    (clone / "projects" / "billing" / "mine.md").write_text("# 내 파일\n", encoding="utf-8")
    before = sandbox.snapshot(clone)

    result = sandbox.just("repo", "remove", "billing", cwd=clone)

    assert result.returncode != 0
    assert "--force" in result.stderr
    assert (clone / "projects" / "billing" / "mine.md").is_file()
    assert sandbox.snapshot(clone) == before


# --- 등록 정보가 어긋난 저장소 -------------------------------------------------------


def test_루트에_기록된_커밋이_없고_gitmodules_항목만_남은_저장소도_제거한다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    root.register(sandbox.knowledge_remote("docs"))
    clone = root.clone()
    sandbox.git("rm", "--cached", "projects/billing", cwd=clone)  # gitlink만 사라지고 .gitmodules 항목이 남는다

    result = sandbox.just("repo", "remove", "billing", cwd=clone)

    gitmodules = (clone / ".gitmodules").read_text(encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert not (clone / "projects" / "billing").exists()
    assert "projects/billing" not in gitmodules and "projects/docs" in gitmodules


def test_gitmodules에_항목이_없고_루트에_기록된_커밋만_남은_저장소도_제거한다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    root.register(sandbox.knowledge_remote("docs"))
    sandbox.git("config", "-f", ".gitmodules", "--remove-section", "submodule.projects/billing", cwd=root.work)

    result = _remove(sandbox, root, "billing")

    index = sandbox.git("ls-files", "--stage", cwd=root.work).stdout
    assert result.returncode == 0, result.stderr
    assert not _sub(root).exists()
    assert "projects/billing" not in index and "projects/docs" in index
    assert sandbox.snapshot(root.work)["modules"] == ["modules/projects/docs"]


def test_서브모듈_이름이_경로와_다르게_등록된_저장소도_흔적까지_제거한다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    sandbox.git("submodule", "add", "--name", "legacy-name", billing.url, "projects/billing", cwd=root.work)
    sandbox.git("add", "-A", cwd=root.work)
    sandbox.git("commit", "-m", "add billing as legacy-name", cwd=root.work)
    assert sandbox.snapshot(root.work)["modules"] == ["modules/legacy-name"]

    result = _remove(sandbox, root, "billing")

    state = sandbox.snapshot(root.work)
    assert result.returncode == 0, result.stderr
    assert state["modules"] == [] and state["config"] == "" and state["gitmodules"] is None


def test_서브모듈_저장소가_망가져_상태를_읽지_못하면_거부하고_강제하면_제거한다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    broken = root.work / ".git" / "modules" / "projects" / "billing"
    shutil.rmtree(broken)  # 작업 트리의 .git 파일이 가리키는 곳이 사라졌다

    result = _refused_leaving_everything_unchanged(sandbox, root, sub_readable=False)
    assert "읽지 못했습니다" in result.stderr and "--force" in result.stderr

    forced = _remove(sandbox, root, "billing", "--force")

    state = sandbox.snapshot(root.work)
    assert forced.returncode == 0, forced.stderr
    assert not _sub(root).exists()
    assert state["modules"] == [] and state["config"] == "" and state["gitmodules"] is None


def test_gitmodules를_읽지_못하면_제거를_거부한다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    (root.work / ".gitmodules").write_text('<<<<<<< HEAD\n[submodule "projects/billing"]\n=======\n>>>>>>> other\n', encoding="utf-8")
    before = sandbox.snapshot(root.work)

    result = _remove(sandbox, root, "billing", "--force")

    assert result.returncode != 0
    assert ".gitmodules" in result.stderr
    assert sandbox.snapshot(root.work) == before


# --- 출력 -----------------------------------------------------------------------------


def test_한글_파일_이름도_읽을_수_있게_알린다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    (_sub(root) / "초안.md").write_text("# 초안\n", encoding="utf-8")

    result = _refused_leaving_everything_unchanged(sandbox, root)

    assert "초안.md" in result.stderr


def test_버려지는_작업이_많으면_일부만_보이고_전체_개수를_알린다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    sub = _sub(root)
    for i in range(25):
        (sub / f"draft-{i:02d}.md").write_text("# 초안\n", encoding="utf-8")
    for i in range(12):
        _local_commit(sandbox, sub, f"work-{i:02d}.md")

    result = _refused_leaving_everything_unchanged(sandbox, root)

    assert "25개" in result.stderr and "12개" in result.stderr  # 전체 개수
    assert result.stderr.count("draft-") < 25 and result.stderr.count("작업 work-") < 12  # 목록은 줄여서 보인다
    assert "외 5개" in result.stderr and "외 2개" in result.stderr  # 보이지 않는 개수
