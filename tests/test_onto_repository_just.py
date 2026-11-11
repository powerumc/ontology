"""`just -f .onto/Justfile build|validate|query|status`: 루트 저장소에 붙은 지식 저장소 안에서 그 저장소의 지식만 다룬다.

가장 높은 이음매다. 루트 저장소는 이 저장소의 추적 파일을 임시 디렉토리로 복사한 것이고, 지식 저장소는 로컬 bare 원격을
`just repo add`로 붙인 것이다(등록하면 `onto sync`가 자동으로 `.onto/`를 복사한다). 지식 저장소 안에서 복사된 `.onto/Justfile`을 직접
가리켜 실행한다. 이 저장소의 `Justfile`을 직접 가리키지 않는다.

지식 저장소 안의 명령이 보고하는 경로는 그 저장소 기준(`docs/ontology/…`)이고, 루트 저장소의 `just onto …`는 루트 기준
(`projects/<저장소>/docs/ontology/…`)이다. 도구가 지식 저장소 안의 범위를 어떻게 다루는지의 세부(검사 항목, 규칙, 읽을 수 없는 파일)는
`test_onto_repository_scope.py`가 본다. 여기서는 Justfile을 거쳐 범위가 바르게 정해지는지를 본다.
"""

import re

from support.onto_cli import ONTOLOGY_DIR, page, parse_table, repo

JUSTFILE = ".onto/Justfile"
BILLING_PLAN = "plan/auth-redesign"
BILLING_PLAN_TITLE = "인증 재설계"
SHOP_PLAN = "plan/checkout"
SHOP_PLAN_TITLE = "결제창 개편"
INDEX = f"{ONTOLOGY_DIR}/index.md"


def attach(sandbox, root, name: str, files: dict[str, str]):
    """지식 저장소를 `just repo add`로 붙인다. 등록하면 최신화가 `.onto/`를 복사하고 인덱스를 만든다. 지식 저장소의 작업 트리를 돌려준다."""
    remote = sandbox.knowledge_remote(name, files=files)
    result = sandbox.just("repo", "add", remote.url, name, cwd=root.work)
    assert result.returncode == 0, result.stderr
    return root.work / "projects" / name


def knowledge_repos(sandbox, **billing_extra):
    """`billing`과 `shop`을 붙인 루트 저장소. `(루트 저장소, billing, shop)`의 작업 트리를 돌려준다."""
    root = sandbox.root()
    billing_files = {
        **repo("billing", page(BILLING_PLAN, "Plan", title=BILLING_PLAN_TITLE), title="결제"),
        "docs/design.md": "# 설계\n",
        **billing_extra,
    }
    shop_files = {**repo("shop", page(SHOP_PLAN, "Plan", title=SHOP_PLAN_TITLE), title="상점"), "docs/shop-notes.md": "# 상점 메모\n"}
    billing = attach(sandbox, root, "billing", billing_files)
    shop = attach(sandbox, root, "shop", shop_files)
    return root.work, billing, shop


def onto(sandbox, repository, *args: str, cwd=None, justfile: str = JUSTFILE):
    """지식 저장소 안에서 복사된 Justfile을 직접 가리켜 도구 명령을 실행한다."""
    return sandbox.just("-f", justfile, *args, cwd=cwd or repository)


def tree(path) -> dict[str, bytes]:
    """`path` 아래의 파일 내용. 도구를 돌리느라 `.onto/`에 생긴 가상환경과 캐시, 산출물은 뺀다."""
    skipped = {".venv", "__pycache__", ".build"}
    return {
        p.relative_to(path).as_posix(): p.read_bytes()
        for p in sorted(path.rglob("*"))
        if p.is_file() and not skipped & set(p.relative_to(path).parts) and ".git" not in p.relative_to(path).parts[:1]
    }


# --- build ------------------------------------------------------------------


def test_build는_이_저장소의_페이지만_컴파일하고_이_저장소의_인덱스만_만든다(sandbox):
    root, billing, shop = knowledge_repos(sandbox)
    (billing / INDEX).unlink()  # build가 인덱스를 새로 만드는지 본다
    shop_before = tree(shop)

    result = onto(sandbox, billing, "build")

    assert result.returncode == 0, result.stderr
    graph = (billing / ".onto" / ".build" / "graph.ttl").read_text(encoding="utf-8")
    assert BILLING_PLAN_TITLE in graph and SHOP_PLAN_TITLE not in graph
    assert "지식 저장소 1개" in result.stdout
    assert (billing / INDEX).is_file()
    assert f"인덱스: {INDEX} (새로 만들었다)" in result.stdout
    assert tree(shop) == shop_before  # 다른 지식 저장소의 인덱스는 건드리지 않는다
    assert not (root / "onto" / ".build").exists()  # 루트 저장소의 산출물도 만들지 않는다
    assert not (billing / ".onto" / ".build" / "index.md").exists()  # 전체 인덱스는 루트 저장소가 모을 때만 만든다


def test_build는_이_저장소의_작업_트리에_인덱스와_dot_onto_안의_산출물밖에_만들지_않는다(sandbox):
    _, billing, _ = knowledge_repos(sandbox)
    status = sandbox.git("status", "--porcelain", "--untracked-files=all", cwd=billing).stdout
    assert f"?? {INDEX}" in status  # 등록하면 최신화가 만든 인덱스다
    (billing / INDEX).unlink()

    result = onto(sandbox, billing, "build")

    assert result.returncode == 0, result.stderr
    # 인덱스만 다시 생기고, `.onto/` 안의 가상환경과 산출물은 지식 저장소의 `.gitignore`가 제외해 git에 보이지 않는다
    assert sandbox.git("status", "--porcelain", "--untracked-files=all", cwd=billing).stdout == status


# --- validate ---------------------------------------------------------------


def test_validate는_이_저장소만_검사하고_여러_저장소에_걸친_검사를_건너뛰었다고_알린다(sandbox):
    _, billing, shop = knowledge_repos(sandbox)
    # 다른 지식 저장소의 오류는 이 저장소의 검사에 나타나지 않는다
    (shop / ONTOLOGY_DIR / "plan" / "ghost.md").write_text("---\nclass: Plan\ntitle: 유령\nowner: kim\n---\n", encoding="utf-8")
    page_file = billing / ONTOLOGY_DIR / BILLING_PLAN
    page_file.with_suffix(".md").write_text(
        f"---\nclass: Plan\ntitle: {BILLING_PLAN_TITLE}\nabout: shop:{SHOP_PLAN}\n---\n본문\n", encoding="utf-8"
    )
    assert onto(sandbox, billing, "build").returncode == 0  # 인덱스를 갖춘다

    result = onto(sandbox, billing, "validate")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == ""  # 다른 저장소를 가리키는 교차 참조는 문제가 아니다
    assert "이 저장소만 검사했다" in result.stderr and "공유 범위" in result.stderr
    assert "unregistered-repository" in result.stderr


def test_validate는_이_저장소의_문제를_이_저장소_기준_경로로_보고하고_오류가_있으면_1로_끝난다(sandbox):
    _, billing, _ = knowledge_repos(sandbox)
    (billing / ONTOLOGY_DIR / "plan" / "ghost.md").write_text("---\nclass: Plan\ntitle: 유령\nowner: kim\n---\n", encoding="utf-8")

    result = onto(sandbox, billing, "validate")

    assert result.returncode == 1
    rows = [line.split("\t")[:4] for line in result.stdout.splitlines()]
    assert ["오류", "billing", f"{ONTOLOGY_DIR}/plan/ghost.md", "undefined-key"] in rows
    assert all("projects/" not in row[2] for row in rows)


# --- query ------------------------------------------------------------------


def test_query의_결과에_다른_지식_저장소의_엔티티가_나오지_않고_경로는_이_저장소_기준이다(sandbox):
    root, billing, _ = knowledge_repos(sandbox)

    result = onto(sandbox, billing, "query", "SELECT ?e ?t WHERE { ?e a onto:Plan ; dcterms:title ?t }")

    assert result.returncode == 0, result.stderr
    assert parse_table(result.stdout) == [["e", "t"], [f"{ONTOLOGY_DIR}/{BILLING_PLAN}.md", BILLING_PLAN_TITLE]]
    assert (billing / f"{ONTOLOGY_DIR}/{BILLING_PLAN}.md").is_file()


# --- status -----------------------------------------------------------------


def test_status는_이_저장소의_원본_문서만_보여_주고_해시는_git이_낸_값이다(sandbox):
    root, billing, _ = knowledge_repos(sandbox)
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "root-notes.md").write_text("# 루트의 문서\n", encoding="utf-8")  # 루트 저장소의 문서

    result = onto(sandbox, billing, "status")

    assert result.returncode == 0, result.stderr
    (row,) = [line.split("\t") for line in result.stdout.splitlines()]
    assert row[:3] == ["새 문서", "billing", "docs/design.md"]  # `shop/docs/shop-notes.md`와 `docs/root-notes.md`가 아니다
    committed = sandbox.git("rev-parse", "HEAD:docs/design.md", cwd=billing).stdout.strip()
    assert row[3] == committed


# --- sync -------------------------------------------------------------------


def test_sync는_루트_저장소에서만_쓸_수_있다고_알리며_거부한다(sandbox):
    _, billing, _ = knowledge_repos(sandbox)
    before = tree(billing)

    result = onto(sandbox, billing, "sync")

    assert result.returncode == 1
    assert "루트 저장소에서만 쓸 수 있다" in result.stderr
    assert tree(billing) == before


# --- 어느 디렉토리에서 불러도 --------------------------------------------------------


def test_지식_저장소의_하위_디렉토리에서_불러도_그_저장소를_기준으로_동작한다(sandbox):
    _, billing, _ = knowledge_repos(sandbox)
    deeper = billing / "docs" / "deeper"
    deeper.mkdir(parents=True)

    query = onto(sandbox, billing, "query", "SELECT ?e WHERE { ?e a onto:Plan }", cwd=deeper, justfile="../../.onto/Justfile")
    status = onto(sandbox, billing, "status", cwd=deeper, justfile="../../.onto/Justfile")

    assert query.returncode == 0, query.stderr
    assert parse_table(query.stdout) == [["e"], [f"{ONTOLOGY_DIR}/{BILLING_PLAN}.md"]]
    assert status.returncode == 0, status.stderr
    assert [line.split("\t")[:3] for line in status.stdout.splitlines()] == [["새 문서", "billing", "docs/design.md"]]
    assert not (deeper / ".build").exists() and not (deeper / INDEX).exists()  # 부른 디렉토리에는 아무것도 만들지 않는다


# --- 루트와 같은 파일 ------------------------------------------------------------


def test_지식_저장소의_Justfile은_루트의_onto_모듈과_같은_파일이다(sandbox):
    root, billing, shop = knowledge_repos(sandbox)

    assert (billing / JUSTFILE).read_bytes() == (root / "onto" / "Justfile").read_bytes()
    assert (shop / JUSTFILE).read_bytes() == (root / "onto" / "Justfile").read_bytes()


def test_루트_저장소에서는_모든_지식_저장소를_합쳐_다룬다(sandbox):
    root, billing, _ = knowledge_repos(sandbox)
    assert onto(sandbox, billing, "build").returncode == 0  # 지식 저장소 안의 실행이 루트의 결과를 바꾸지 않는다

    query = sandbox.just("onto", "query", "SELECT ?e ?t WHERE { ?e a onto:Plan ; dcterms:title ?t } ORDER BY ?t", cwd=root)
    validate = sandbox.just("onto", "validate", cwd=root)

    assert query.returncode == 0, query.stderr
    assert parse_table(query.stdout) == [
        ["e", "t"],
        [f"projects/shop/{ONTOLOGY_DIR}/{SHOP_PLAN}.md", SHOP_PLAN_TITLE],
        [f"projects/billing/{ONTOLOGY_DIR}/{BILLING_PLAN}.md", BILLING_PLAN_TITLE],
    ]
    assert validate.returncode == 0, validate.stdout + validate.stderr
    assert "이 저장소만 검사했다" not in validate.stderr  # 루트에서는 여러 저장소에 걸친 검사를 건너뛰지 않는다
    build = sandbox.just("onto", "build", cwd=root)
    assert build.returncode == 0, build.stderr
    assert "지식 저장소 2개" in build.stdout
    assert re.search(r"전체 인덱스: onto/\.build/index\.md", build.stdout)


# --- Justfile을 건드리지 않는다 --------------------------------------------------------


def test_복사된_Justfile로_실행해도_지식_저장소의_Justfile은_만들어지지도_고쳐지지도_않는다(sandbox):
    root = sandbox.root()
    team = "default:\n\t@echo 팀의 Justfile\n"
    shop = attach(sandbox, root, "shop", {"README.md": "# shop\n", "Justfile": team, **repo("shop", title="상점")})
    billing = attach(sandbox, root, "billing", repo("billing", title="결제"))

    for repository in (shop, billing):
        for command in ("build", "validate", "status"):
            assert onto(sandbox, repository, command).returncode == 0, (repository.name, command)

    assert (shop / "Justfile").read_text(encoding="utf-8") == team
    assert not any((billing / name).exists() for name in ("Justfile", "justfile", ".justfile"))
    bare = sandbox.just(cwd=shop)  # `-f` 없이 부르면 팀의 Justfile이 쓰인다
    assert bare.returncode == 0 and bare.stdout == "팀의 Justfile\n"
    assert sandbox.git("ls-files", "Justfile", cwd=shop).stdout.strip() == "Justfile"
