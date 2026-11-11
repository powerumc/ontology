"""`just repo add <url> [이름] [브랜치]`: 지식 저장소를 `projects/<이름>/`에 서브모듈로 붙이고 추적 브랜치를 기록한다."""

import os
import shutil

import pytest


def _add(sandbox, root, *args):
    return sandbox.just("repo", "add", *args, cwd=root.work)


def _recorded_branch(sandbox, root, name):
    """`.gitmodules`에 기록된 추적 브랜치. 기록이 없으면 `None`."""
    result = sandbox.git(
        "config", "-f", ".gitmodules", "--get", f"submodule.projects/{name}.branch", cwd=root.work, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _staged(sandbox, root):
    return set(sandbox.git("diff", "--cached", "--name-only", cwd=root.work).stdout.split())


def test_URL만_주면_저장소_이름을_이름으로_원격의_기본_브랜치를_추적_브랜치로_삼아_등록한다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    tip = billing.commit(branch="trunk")
    billing.set_default_branch("trunk")  # 기본 브랜치가 main이 아니다

    result = _add(sandbox, root, billing.url)

    sub = root.work / "projects" / "billing"
    assert result.returncode == 0, result.stderr
    assert (sub / "README.md").is_file()
    assert _recorded_branch(sandbox, root, "billing") == "trunk"
    assert sandbox.head(sub) == tip


def test_이름과_브랜치를_지정하면_그대로_등록한다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    dev_tip = billing.commit(branch="dev")  # 기본 브랜치는 main이다

    result = _add(sandbox, root, billing.url, "invoice", "dev")

    sub = root.work / "projects" / "invoice"
    assert result.returncode == 0, result.stderr
    assert not (root.work / "projects" / "billing").exists()  # 저장소 이름이 아니라 지정한 이름이다
    assert _recorded_branch(sandbox, root, "invoice") == "dev"
    assert sandbox.branch(sub) == "dev"
    assert sandbox.head(sub) == dev_tip


@pytest.mark.parametrize("branch", [None, "dev"], ids=["기본_브랜치", "지정한_브랜치"])
def test_등록_직후_서브모듈은_추적_브랜치에_체크아웃되어_있다(sandbox, branch):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    billing.commit(branch="dev")

    result = _add(sandbox, root, billing.url, "billing", *([branch] if branch else []))

    sub = root.work / "projects" / "billing"
    tracked = branch or "main"
    assert result.returncode == 0, result.stderr
    assert sandbox.branch(sub) == tracked  # detached HEAD가 아니다
    assert sandbox.git("rev-parse", "--abbrev-ref", f"{tracked}@{{upstream}}", cwd=sub).stdout.strip() == f"origin/{tracked}"


def test_등록은_루트_저장소에_스테이징까지만_하고_커밋하지_않는다(sandbox):
    root = sandbox.root()
    root_head = sandbox.head(root.work)

    result = _add(sandbox, root, sandbox.knowledge_remote("billing").url)

    assert result.returncode == 0, result.stderr
    assert sandbox.head(root.work) == root_head
    assert _staged(sandbox, root) == {".gitmodules", "projects/billing"}


@pytest.mark.parametrize(
    "url",
    [
        "https://example.invalid/team/billing.git",
        "https://example.invalid/team/billing",
        "https://example.invalid/team/billing/",
        "git@example.invalid:team/billing.git",
        "ssh://git@example.invalid/team/billing.git",
    ],
)
def test_저장소_이름은_ssh와_https_주소의_표기와_무관하게_뽑는다(sandbox, url):
    """주소는 `url.<기준>.insteadOf`(테스트용 전역 설정)로 임시 디렉토리의 로컬 원격에 이어 둔다.

    등록 정보에는 쓴 주소가 그대로 남는다. 서브모듈을 받는 `git clone`은 루트의 로컬 설정을 읽지 않으므로 전역 설정에 둔다.
    """
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    sandbox.git("config", "--global", f"url.{billing.url}.insteadOf", url, cwd=root.work)

    result = _add(sandbox, root, url)

    assert result.returncode == 0, result.stderr
    assert (root.work / "projects" / "billing" / "README.md").is_file()
    assert sandbox.git("config", "-f", ".gitmodules", "--get", "submodule.projects/billing.url", cwd=root.work).stdout.strip() == url


# --- 같은 이름이 이미 있으면 거부한다 ----------------------------------------------


def _rejected_leaving_everything_unchanged(sandbox, root, *args):
    before = sandbox.snapshot(root.work)

    result = _add(sandbox, root, *args)

    assert result.returncode != 0
    assert sandbox.snapshot(root.work) == before
    return result


def test_이미_등록된_이름이면_거부하고_아무것도_바꾸지_않는다(sandbox):
    root = sandbox.root()
    first = sandbox.knowledge_remote("billing")
    root.register(first)
    other = sandbox.knowledge_remote("other")

    result = _rejected_leaving_everything_unchanged(sandbox, root, other.url, "billing")

    assert "projects/billing" in result.stderr and "이미" in result.stderr  # 이유를 알린다
    assert (root.work / "projects" / "billing" / "README.md").read_text(encoding="utf-8") == "# billing\n"


def test_방금_등록하고_아직_커밋하지_않은_이름도_거부한다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    assert _add(sandbox, root, billing.url).returncode == 0

    _rejected_leaving_everything_unchanged(sandbox, root, billing.url)


def test_등록은_안_됐지만_같은_이름의_디렉토리가_이미_있으면_거부하고_그_디렉토리를_건드리지_않는다(sandbox):
    root = sandbox.root()
    taken = root.work / "projects" / "billing"
    taken.mkdir(parents=True)
    (taken / "notes.md").write_text("# 내 메모\n", encoding="utf-8")

    result = _rejected_leaving_everything_unchanged(sandbox, root, sandbox.knowledge_remote("billing").url)

    assert "projects/billing" in result.stderr and "이미" in result.stderr
    assert (taken / "notes.md").read_text(encoding="utf-8") == "# 내 메모\n"


def test_이전_등록의_서브모듈_저장소가_git_내부에_남아_있으면_거부한다(sandbox):
    """손으로 `git rm`만 한 경우처럼 `.git/modules`에 남은 저장소는 다음 등록에서 재사용되지 않게 막는다."""
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    root.register(billing)
    sandbox.git("rm", "-f", "projects/billing", cwd=root.work)
    assert sandbox.snapshot(root.work)["modules"] == ["modules/projects/billing"]

    result = _rejected_leaving_everything_unchanged(sandbox, root, billing.url)

    assert "modules/projects/billing" in result.stderr  # 지울 곳을 알린다


def test_다른_이름의_저장소가_이미_등록되어_있어도_등록된다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    root.register(sandbox.knowledge_remote("docs"))
    api = sandbox.knowledge_remote("api")

    result = _add(sandbox, root, api.url)

    assert result.returncode == 0, result.stderr
    assert sandbox.branch(root.work / "projects" / "api") == "main"
    assert (root.work / "projects" / "billing" / "README.md").is_file()


# --- 공개 원본에는 등록하지 않는다 (docs/adr/0007) -----------------------------------

# 공개 원본을 가리키는 여러 표기. ssh와 https, `.git` 유무, 포트·계정 정보·대소문자·끝 슬래시가 달라도 같은 저장소다.
PUBLIC_ORIGIN_NOTATIONS = [
    "git@github.com:powerumc/ontology.git",
    "git@github.com:powerumc/ontology",
    "https://github.com/powerumc/ontology.git",
    "https://github.com/powerumc/ontology",
    "https://github.com/powerumc/ontology/",
    "https://github.com/powerumc/ontology.git/",
    "ssh://git@github.com/powerumc/ontology.git",
    "ssh://git@github.com:22/powerumc/ontology",
    "git://github.com/powerumc/ontology.git",
    "https://user:token@github.com/powerumc/ontology.git",
    "https://GitHub.com/PowerUmc/Ontology.git",
    "git@github.com:/powerumc/ontology.git",  # scp 꼴의 경로 앞 슬래시
    "https://github.com//powerumc/ontology.git",  # 겹친 슬래시
    "https://www.github.com/powerumc/ontology",  # www 호스트
    "ssh://git@ssh.github.com:443/powerumc/ontology.git",  # GitHub이 안내하는 443 포트 접속
    "git+ssh://git@github.com/powerumc/ontology.git",
    "ssh+git://git@github.com/powerumc/ontology",
]


@pytest.mark.parametrize("origin", PUBLIC_ORIGIN_NOTATIONS)
def test_origin이_공개_원본이면_표기와_무관하게_거부하고_아무것도_바꾸지_않는다(sandbox, origin):
    root = sandbox.root()
    sandbox.git("remote", "set-url", "origin", origin, cwd=root.work)

    result = _rejected_leaving_everything_unchanged(sandbox, root, sandbox.knowledge_remote("billing").url)

    assert "공개 원본" in result.stderr  # 이유를 알린다


@pytest.mark.parametrize(
    "origin",
    ["git@github-personal:powerumc/ontology.git", "ssh://git@github-personal/powerumc/ontology.git"],
)
def test_ssh_설정의_호스트_별칭으로_적은_공개_원본도_거부한다(sandbox, origin):
    """여러 GitHub 계정을 쓰는 사람은 `~/.ssh/config`의 `Host` 별칭으로 주소를 적는다. 별칭을 풀어 호스트를 본다."""
    sandbox.ssh_alias("github-personal", "github.com")
    root = sandbox.root()
    sandbox.git("remote", "set-url", "origin", origin, cwd=root.work)

    result = _rejected_leaving_everything_unchanged(sandbox, root, sandbox.knowledge_remote("billing").url)

    assert "공개 원본" in result.stderr


def test_ssh_호스트_별칭이_다른_호스트를_가리키면_등록된다(sandbox):
    sandbox.ssh_alias("work-github", "git.example.invalid")
    root = sandbox.root()
    sandbox.git("remote", "set-url", "origin", "git@work-github:powerumc/ontology.git", cwd=root.work)

    result = _add(sandbox, root, sandbox.knowledge_remote("billing").url)

    assert result.returncode == 0, result.stderr


def test_insteadOf로_줄여_쓴_공개_원본_주소도_거부한다(sandbox):
    """`git remote get-url`은 `url.<기준>.insteadOf` 축약을 푼 주소를 준다."""
    sandbox.git("config", "--global", "url.git@github.com:powerumc/.insteadOf", "gh:", cwd=sandbox.base)
    root = sandbox.root()
    sandbox.git("remote", "set-url", "origin", "gh:ontology.git", cwd=root.work)

    result = _rejected_leaving_everything_unchanged(sandbox, root, sandbox.knowledge_remote("billing").url)

    assert "공개 원본" in result.stderr


def test_푸시할_주소가_공개_원본이어도_거부한다(sandbox):
    """받아 온 주소는 다르더라도 푸시하면 등록 커밋이 공개 원본에 올라간다."""
    root = sandbox.root()
    sandbox.git("remote", "set-url", "--push", "origin", "git@github.com:powerumc/ontology.git", cwd=root.work)

    result = _rejected_leaving_everything_unchanged(sandbox, root, sandbox.knowledge_remote("billing").url)

    assert "공개 원본" in result.stderr


def test_origin이_없으면_등록된다(sandbox):
    root = sandbox.root()
    sandbox.git("remote", "remove", "origin", cwd=root.work)

    result = _add(sandbox, root, sandbox.knowledge_remote("billing").url)

    assert result.returncode == 0, result.stderr
    assert (root.work / "projects" / "billing" / "README.md").is_file()


@pytest.mark.parametrize(
    "origin",
    [
        "git@github.com:powerumc/ontology-private.git",
        "https://github.com/other/ontology.git",
        "https://github.com/powerumc/ontology-notes",
        "https://gitlab.com/powerumc/ontology.git",
        "git@github.com:powerumc/ontology/extra.git",
    ],
)
def test_origin이_공개_원본과_다른_주소면_등록된다(sandbox, origin):
    root = sandbox.root()
    sandbox.git("remote", "set-url", "origin", origin, cwd=root.work)

    result = _add(sandbox, root, sandbox.knowledge_remote("billing").url)

    assert result.returncode == 0, result.stderr
    assert (root.work / "projects" / "billing" / "README.md").is_file()


# --- 등록할 수 없는 입력은 아무것도 바꾸지 않고 거부한다 --------------------------------


@pytest.mark.parametrize("name", ["../evil", "a/b", ".", "..", "-x", ".notes", ".hidden"])
def test_projects_밖이나_아래로_벗어나는_이름은_거부한다(sandbox, name):
    root = sandbox.root()
    outside = root.work / "evil"

    result = _rejected_leaving_everything_unchanged(sandbox, root, sandbox.knowledge_remote("billing").url, name)

    assert "이름" in result.stderr
    assert not outside.exists()


def test_이름에_공백이_들어_있어도_등록된다(sandbox):
    root = sandbox.root()

    result = _add(sandbox, root, sandbox.knowledge_remote("billing").url, "my repo")

    assert result.returncode == 0, result.stderr
    assert (root.work / "projects" / "my repo" / "README.md").is_file()


def test_원격에_없는_브랜치를_지정하면_거부하고_아무것도_바꾸지_않는다(sandbox):
    """없는 브랜치로 `git submodule add -b`를 하면 `projects/<이름>/`와 `.git/modules`가 반쯤 남는다."""
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")

    result = _rejected_leaving_everything_unchanged(sandbox, root, billing.url, "billing", "nope")

    assert "nope" in result.stderr


def test_원격에_접속할_수_없으면_거부하고_아무것도_바꾸지_않는다(sandbox):
    root = sandbox.root()
    missing = sandbox.base / "remotes" / "missing.git"

    _rejected_leaving_everything_unchanged(sandbox, root, missing)


def test_기본_브랜치를_알_수_없는_원격은_거부하고_브랜치를_지정하라고_알린다(sandbox):
    """커밋이 하나도 없는 원격에는 기본 브랜치가 없다."""
    root = sandbox.root()
    empty = sandbox.new_dir("remotes", "empty.git")
    sandbox.git("init", "--bare", "--initial-branch=main", empty, cwd=empty)

    result = _rejected_leaving_everything_unchanged(sandbox, root, empty)

    assert "브랜치" in result.stderr


def test_받아_오다_실패해도_반쯤_등록된_채_남지_않는다(sandbox):
    """브랜치 목록에는 보이지만 객체가 없는 원격. 접속 확인은 지나가고 복제가 실패한다."""
    root = sandbox.root()
    broken = sandbox.knowledge_remote("broken")
    (broken.url / "refs" / "heads" / "main").write_text("a" * 40 + "\n", encoding="utf-8")

    _rejected_leaving_everything_unchanged(sandbox, root, broken.url)


def test_옵션처럼_보이는_URL은_거부한다(sandbox):
    root = sandbox.root()

    _rejected_leaving_everything_unchanged(sandbox, root, "--upload-pack=touch evil")


def test_gitmodules를_읽지_못하면_거부하고_아무것도_바꾸지_않는다(sandbox):
    """동시에 저장소를 붙이다 `.gitmodules`에 충돌 표시가 남은 경우."""
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    (root.work / ".gitmodules").write_text(
        '<<<<<<< HEAD\n[submodule "projects/billing"]\n=======\n>>>>>>> other\n', encoding="utf-8"
    )

    result = _rejected_leaving_everything_unchanged(sandbox, root, sandbox.knowledge_remote("docs").url)

    assert ".gitmodules" in result.stderr


@pytest.mark.parametrize("url", ["../billing.git", "./billing.git", ".."])
def test_상대_URL은_받지_않고_거부한다(sandbox, url):
    """`git submodule add`는 상대 URL을 루트의 origin 기준으로, 사전 확인은 현재 디렉토리 기준으로 푼다. 받지 않는다."""
    root = sandbox.root()

    result = _rejected_leaving_everything_unchanged(sandbox, root, url)

    assert "상대" in result.stderr


def test_gitmodules가_병합_충돌_상태이면_이유를_알리고_거부하며_아무것도_바꾸지_않는다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    root.leave_gitmodules_unmerged(sandbox.knowledge_remote("docs"))
    assert sandbox.git("ls-files", "-u", "--", ".gitmodules", cwd=root.work).stdout  # 충돌 상태다
    before = sandbox.snapshot(root.work)

    result = _add(sandbox, root, sandbox.knowledge_remote("invoice").url)

    assert result.returncode != 0
    assert "충돌" in result.stderr
    assert sandbox.snapshot(root.work) == before
    assert not (root.work / "projects" / "invoice").exists()


# --- 등록 직후의 최신화 ---------------------------------------------------------------------


def test_등록한_직후_새_지식_저장소에_루트의_기능이_복사되고_커밋되지_않는다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    tip = billing.commit()

    result = _add(sandbox, root, billing.url)

    sub = root.work / "projects" / "billing"
    assert result.returncode == 0, result.stderr
    assert (sub / ".onto" / "Justfile").is_file() and (sub / ".onto" / "onto_tool" / "cli.py").is_file()
    assert (sub / "docs" / "ontology" / "ontology.yaml").is_file()
    assert "최신화: 지식 저장소 1개" in result.stdout  # 최신화의 요약이 이어서 나온다
    assert sandbox.head(sub) == tip  # 지식 저장소에 커밋하지 않는다
    status = sandbox.git("status", "--porcelain", "--untracked-files=all", cwd=sub).stdout
    assert ".onto" not in status and ".gitignore" in status
    assert _staged(sandbox, root) == {".gitmodules", "projects/billing"}  # 루트 저장소에도 등록만 스테이징한다


def test_이미_구성이_있는_지식_저장소를_등록해도_저장소_소유_파일은_바뀌지_않는다(sandbox):
    root = sandbox.root()
    ontology_yaml = 'name: "billing"\nscope: "team:payments"\ntitle: "결제"\n'
    plan = "---\nclass: Plan\ntitle: 출시 계획\nabout: project\n---\n\n본문\n"
    billing = sandbox.knowledge_remote(
        "billing", files={"README.md": "# billing\n", "docs/ontology/ontology.yaml": ontology_yaml, "docs/ontology/plan/launch.md": plan}
    )

    result = _add(sandbox, root, billing.url)

    sub = root.work / "projects" / "billing"
    assert result.returncode == 0, result.stderr
    assert (sub / "docs" / "ontology" / "ontology.yaml").read_text(encoding="utf-8") == ontology_yaml
    assert (sub / "docs" / "ontology" / "plan" / "launch.md").read_text(encoding="utf-8") == plan
    assert (sub / ".onto" / "Justfile").is_file()


def test_루트의_기능을_복사하지_못해도_등록은_남고_다시_실행하는_방법을_알린다(sandbox):
    root = sandbox.root()
    billing = sandbox.knowledge_remote("billing")
    broken = sandbox.new_dir("elsewhere", "broken-uv")  # 실행하면 실패하는 uv가 PATH 맨 앞에 있다
    (broken / "uv").write_text("#!/bin/sh\necho 'uv를 실행할 수 없다' >&2\nexit 1\n", encoding="utf-8")
    (broken / "uv").chmod(0o755)
    env = {**sandbox.env, "PATH": f"{broken}{os.pathsep}{sandbox.env['PATH']}"}

    result = sandbox.run([shutil.which("just"), "repo", "add", billing.url], cwd=root.work, check=False, env=env)

    assert result.returncode != 0
    assert "uv를 실행할 수 없다" in result.stderr  # 복사하지 못한 이유가 보인다
    assert "just onto sync billing" in result.stderr
    assert (root.work / "projects" / "billing" / "README.md").is_file()  # 등록은 되돌리지 않는다
    assert _staged(sandbox, root) == {".gitmodules", "projects/billing"}
    assert not (root.work / "projects" / "billing" / ".onto").exists()


def test_URL에서_뽑은_이름이_숨김_이름이면_거부한다(sandbox):
    """`.`으로 시작하는 디렉토리는 온톨로지 도구가 지식 저장소로 보지 않는다. 등록해 놓고 어떤 `onto` 명령에도 잡히지 않는 일을 막는다."""
    root = sandbox.root()

    result = _rejected_leaving_everything_unchanged(sandbox, root, sandbox.knowledge_remote(".github").url)

    assert "이름" in result.stderr and "'.'" in result.stderr


def test_최신화가_일부만_건너뛰어도_복사하지_못했다고_알리지_않고_마치지_못했다고_알린다(sandbox):
    """읽을 수 없는 페이지가 있어 인덱스만 건너뛰고, `.onto/`와 `.gitignore`는 다 만든 경우다."""
    root = sandbox.root()
    billing = sandbox.knowledge_remote(
        "billing",
        files={
            "README.md": "# billing\n",
            "docs/ontology/ontology.yaml": 'name: "billing"\n',
            "docs/ontology/plan/broken.md": "frontmatter가 없다\n",
        },
    )

    result = _add(sandbox, root, billing.url)

    sub = root.work / "projects" / "billing"
    assert result.returncode != 0
    assert (sub / ".onto" / "Justfile").is_file() and ".onto/" in (sub / ".gitignore").read_text(encoding="utf-8")  # 복사는 끝났다
    assert "최신화를 마치지 못했습니다" in result.stderr and "복사하지 못했" not in result.stderr
    assert "just onto sync billing" in result.stderr
