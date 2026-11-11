"""`just onto build`와 `just onto query`: 루트 저장소에 서브모듈로 붙은 지식 저장소를 상대로 한 가장 높은 이음매.

도구가 `onto/` 안에서 자족적으로 uv로 도는 것도 여기서 확인된다. 루트 저장소는 이 저장소의 추적 파일을
임시 디렉토리로 복사한 것이고, 테스트마다 도구의 가상환경을 새로 만든다.
"""

from pathlib import Path

from support.onto_cli import ONTOLOGY_DIR, copy_onto, page, parse_table, repo

PAGES = "projects/billing/docs/ontology"
PLAN_FILE = f"{PAGES}/plan/auth-redesign.md"
PLAN_TITLE = "인증 재설계"


def root_with_billing(sandbox, *pages, **project) -> Path:
    """`billing` 지식 저장소를 서브모듈로 붙인 루트 저장소의 작업 사본."""
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing", files=repo("billing", *pages, **project)))
    return root.work


def query(sandbox, root: Path, sparql: str, *, cwd: Path | None = None):
    return sandbox.just("onto", "query", sparql, cwd=cwd or root)


def test_just_onto_build가_projects_아래_지식_저장소의_페이지로_그래프를_만든다(sandbox):
    root = root_with_billing(sandbox, page("plan/auth-redesign", "Plan", title=PLAN_TITLE))

    result = sandbox.just("onto", "build", cwd=root)

    assert result.returncode == 0, result.stderr
    graph = root / "build" / "graph.ttl"
    assert PLAN_TITLE in graph.read_text(encoding="utf-8")


def test_컴파일된_그래프는_빌드_산출물이라_git에_잡히지_않는다(sandbox):
    root = root_with_billing(sandbox, page("plan/auth-redesign", "Plan", title=PLAN_TITLE))
    assert sandbox.git("status", "--porcelain", cwd=root).stdout == ""

    build = sandbox.just("onto", "build", cwd=root)

    assert build.returncode == 0, build.stderr
    assert (root / "build" / "graph.ttl").is_file()
    # 그래프뿐 아니라 도구의 가상환경과 잠금 파일도 작업 트리를 더럽히지 않는다.
    assert sandbox.git("status", "--porcelain", cwd=root).stdout == ""


def test_just_onto_query는_결과의_엔티티를_루트_저장소_기준_파일_경로로_보여_준다(sandbox):
    root = root_with_billing(sandbox, page("plan/auth-redesign", "Plan", title=PLAN_TITLE))

    result = query(sandbox, root, "SELECT ?e ?t WHERE { ?e dcterms:title ?t }")

    assert result.returncode == 0, result.stderr
    assert parse_table(result.stdout) == [["e", "t"], [PLAN_FILE, PLAN_TITLE]]
    assert (root / PLAN_FILE).is_file()  # 추가 조회 없이 곧바로 열 수 있다


def test_just_onto_query는_하위_디렉토리에서_불러도_루트_저장소_기준_경로를_보여_준다(sandbox):
    root = root_with_billing(sandbox, page("plan/auth-redesign", "Plan", title=PLAN_TITLE))
    (root / "docs" / "deeper").mkdir(parents=True)

    result = query(sandbox, root, "SELECT ?e WHERE { ?e a onto:Plan }", cwd=root / "docs" / "deeper")

    assert result.returncode == 0, result.stderr
    assert parse_table(result.stdout) == [["e"], [PLAN_FILE]]


def test_꺾쇠_중괄호_따옴표_세미콜론이_든_질의가_그대로_전달된다(sandbox):
    root = root_with_billing(sandbox, page("plan/auth-redesign", "Plan", title=PLAN_TITLE))
    sparql = (
        "PREFIX dc: <http://purl.org/dc/terms/>\n"
        "SELECT ?e ?label WHERE {{\n"
        "  ?e dc:title ?t ; a <https://onto.invalid/vocab#Plan> .\n"
        "  BIND(CONCAT(\"<\", ?t, \"> {'\\\"'} ; $x\") AS ?label)\n"
        "}}"
    )

    result = query(sandbox, root, sparql)

    assert result.returncode == 0, result.stderr
    assert parse_table(result.stdout) == [["e", "label"], [PLAN_FILE, f"<{PLAN_TITLE}> {{'\"'}} ; $x"]]


def test_just_onto_query는_이전_build의_결과를_쓰지_않고_현재_파일에서_다시_컴파일한다(sandbox):
    root = root_with_billing(sandbox, page("plan/auth-redesign", "Plan", title=PLAN_TITLE))
    assert sandbox.just("onto", "build", cwd=root).returncode == 0
    page_file = root / PLAN_FILE
    page_file.write_text(page_file.read_text(encoding="utf-8").replace(PLAN_TITLE, "인증 재설계 2차"), encoding="utf-8")

    after_edit = query(sandbox, root, "SELECT ?t WHERE { ?e dcterms:title ?t }")
    (root / "build" / "graph.ttl").write_text("깨진 그래프", encoding="utf-8")
    after_corruption = query(sandbox, root, "SELECT ?t WHERE { ?e dcterms:title ?t }")

    assert parse_table(after_edit.stdout) == [["t"], ["인증 재설계 2차"]]
    assert after_corruption.returncode == 0, after_corruption.stderr
    assert parse_table(after_corruption.stdout) == [["t"], ["인증 재설계 2차"]]


def test_just_onto_query는_build를_하지_않아도_돈다(sandbox):
    root = root_with_billing(sandbox, page("plan/auth-redesign", "Plan", title=PLAN_TITLE))

    result = query(sandbox, root, "SELECT ?e WHERE { ?e a onto:Plan }")

    assert result.returncode == 0, result.stderr
    assert not (root / "build").exists()  # query는 파일을 남기지 않는다


def test_읽을_수_없는_페이지는_just를_거쳐도_파일_이름과_함께_오류로_알린다(sandbox):
    broken = {f"{ONTOLOGY_DIR}/plan/broken.md": "# frontmatter 없음\n"}
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing", files={**repo("billing"), **broken}))

    result = sandbox.just("onto", "build", cwd=root.work)

    assert result.returncode != 0
    assert f"{PAGES}/plan/broken.md" in result.stderr


def test_루트_저장소의_다른_파일_없이_onto만_복사한_디렉토리에서도_도구가_돈다(sandbox):
    """도구는 루트의 pyproject.toml과 가상환경에 기대지 않는다. 지식 저장소는 `onto/`를 `.onto/`로 복사해 받는다."""
    knowledge_repo = sandbox.new_dir("knowledge", "billing")
    copy_onto(sandbox, knowledge_repo / ".onto")

    result = sandbox.just(
        "query", "ASK { onto:Plan a owl:Class }", cwd=knowledge_repo, justfile=knowledge_repo / ".onto" / "Justfile"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "true"
    assert not (knowledge_repo / "pyproject.toml").exists()
