"""`just onto build`와 `just onto query`: 루트 저장소에 서브모듈로 붙은 지식 저장소를 상대로 한 가장 높은 이음매.

도구가 `onto/` 안에서 자족적으로 uv로 도는 것도 여기서 확인된다. 루트 저장소는 이 저장소의 추적 파일을
임시 디렉토리로 복사한 것이고, 테스트마다 도구의 가상환경을 새로 만든다.
"""

import json
from pathlib import Path

from support.onto_cli import ONTOLOGY_DIR, copy_onto, page, parse_table, repo, snapshot

PAGES = "projects/billing/docs/ontology"
PLAN_FILE = f"{PAGES}/plan/auth-redesign.md"
PLAN_TITLE = "인증 재설계"
GRAPH = Path("onto") / ".build" / "graph.ttl"  # 도구 디렉토리 안의 무시되는 디렉토리
ALL_INDEX = Path("onto") / ".build" / "index.md"  # 모든 지식 저장소를 모은 전체 인덱스. 도구 디렉토리 안의 무시되는 디렉토리다
INDEX = "docs/ontology/index.md"  # 지식 저장소 하나의 인덱스. 그 저장소 안의 경로


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
    assert PLAN_TITLE in (root / GRAPH).read_text(encoding="utf-8")


def test_컴파일된_그래프와_전체_인덱스는_빌드_산출물이라_루트_저장소의_git에_잡히지_않는다(sandbox):
    root = root_with_billing(sandbox, page("plan/auth-redesign", "Plan", title=PLAN_TITLE))
    assert sandbox.git("status", "--porcelain", cwd=root).stdout == ""

    build = sandbox.just("onto", "build", cwd=root)

    assert build.returncode == 0, build.stderr
    assert (root / GRAPH).is_file() and (root / ALL_INDEX).is_file()
    assert not (root / "build").exists()  # 루트 저장소 최상위에는 아무것도 만들지 않는다
    # 그래프와 전체 인덱스뿐 아니라 도구의 가상환경과 잠금 파일도 루트 저장소의 작업 트리를 더럽히지 않는다.
    # (지식 저장소가 서브모듈이라 인덱스가 생긴 것은 포인터 변경으로 보이므로 서브모듈은 뺀다.)
    assert sandbox.git("status", "--porcelain", "--ignore-submodules=all", cwd=root).stdout == ""
    for artifact in (GRAPH, ALL_INDEX):
        assert sandbox.git("check-ignore", "--quiet", artifact.as_posix(), cwd=root, check=False).returncode == 0, artifact


def test_지식_저장소의_인덱스는_그_저장소의_git에_잡히는_파일이다(sandbox):
    root = root_with_billing(sandbox, page("plan/auth-redesign", "Plan", title=PLAN_TITLE))
    billing = root / "projects" / "billing"

    build = sandbox.just("onto", "build", cwd=root)

    assert build.returncode == 0, build.stderr
    assert (billing / INDEX).is_file()
    assert sandbox.git("check-ignore", "--quiet", INDEX, cwd=billing, check=False).returncode == 1  # 무시되지 않는다
    assert sandbox.git("status", "--porcelain", "--untracked-files=all", cwd=billing).stdout == f"?? {INDEX}\n"


def test_인덱스를_커밋한_뒤_같은_페이지로_다시_build해도_지식_저장소에_바뀐_것이_없다(sandbox):
    """인덱스가 커밋되는 파일이라, 다시 만들어도 같은 글자여야 이력에 의미 없는 변경이 쌓이지 않는다."""
    root = root_with_billing(sandbox, page("plan/auth-redesign", "Plan", title=PLAN_TITLE))
    billing = root / "projects" / "billing"
    assert sandbox.just("onto", "build", cwd=root).returncode == 0
    sandbox.git("add", INDEX, cwd=billing)
    sandbox.git("commit", "-m", "인덱스", cwd=billing)

    rebuild = sandbox.just("onto", "build", cwd=root)

    assert rebuild.returncode == 0, rebuild.stderr
    assert sandbox.git("status", "--porcelain", "--untracked-files=all", cwd=billing).stdout == ""


def test_just_onto_validate는_커밋된_인덱스가_페이지와_어긋나면_오류로_보고한다(sandbox):
    root = root_with_billing(sandbox, page("plan/auth-redesign", "Plan", title=PLAN_TITLE))
    assert sandbox.just("onto", "build", cwd=root).returncode == 0
    page_file = root / PLAN_FILE
    page_file.write_text(page_file.read_text(encoding="utf-8").replace(PLAN_TITLE, "인증 재설계 2차"), encoding="utf-8")

    result = sandbox.just("onto", "validate", cwd=root)

    assert result.returncode == 1
    assert result.stdout.split("\t")[:4] == ["오류", "billing", f"{PAGES}/index.md", "index-mismatch"]


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
    (root / GRAPH).write_text("깨진 그래프", encoding="utf-8")
    after_corruption = query(sandbox, root, "SELECT ?t WHERE { ?e dcterms:title ?t }")

    assert parse_table(after_edit.stdout) == [["t"], ["인증 재설계 2차"]]
    assert after_corruption.returncode == 0, after_corruption.stderr
    assert parse_table(after_corruption.stdout) == [["t"], ["인증 재설계 2차"]]


def test_just_onto_query는_build를_하지_않아도_돈다(sandbox):
    root = root_with_billing(sandbox, page("plan/auth-redesign", "Plan", title=PLAN_TITLE))

    result = query(sandbox, root, "SELECT ?e WHERE { ?e a onto:Plan }")

    assert result.returncode == 0, result.stderr
    assert not (root / GRAPH).parent.exists()  # query는 파일을 남기지 않는다


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


def test_지식_저장소_안에서_돌려도_산출물은_onto_디렉토리_안에만_생긴다(sandbox):
    """지식 저장소는 팀과 공유한다. `.onto/` 밖의 작업 트리에 파일이 생기면 그 저장소가 원래 쓰는 `build/`와 섞인다."""
    knowledge_repo = sandbox.new_dir("knowledge", "billing")
    copy_onto(sandbox, knowledge_repo / ".onto")
    justfile = knowledge_repo / ".onto" / "Justfile"
    (knowledge_repo / "build").mkdir()
    (knowledge_repo / "build" / "app.jar").write_text("그 저장소의 빌드 산출물\n", encoding="utf-8")
    outside = {path for path in snapshot(knowledge_repo) if not path.startswith(".onto")}

    build = sandbox.just("build", cwd=knowledge_repo, justfile=justfile)
    query = sandbox.just("query", "ASK { ?s ?p ?o }", cwd=knowledge_repo, justfile=justfile)

    assert build.returncode == 0, build.stderr
    assert query.returncode == 0, query.stderr
    assert (knowledge_repo / ".onto" / ".build" / "graph.ttl").is_file()
    assert {path for path in snapshot(knowledge_repo) if not path.startswith(".onto")} == outside
    assert (knowledge_repo / "build" / "app.jar").read_text(encoding="utf-8") == "그 저장소의 빌드 산출물\n"


def test_레시피_없이_부르면_명령_목록만_보여_주고_파일을_만들지_않는다(sandbox):
    """첫 레시피인 build가 기본으로 돌아 파일을 쓰지 않는다. 루트 `Justfile`의 기본 레시피와 같다."""
    root = root_with_billing(sandbox, page("plan/auth-redesign", "Plan", title=PLAN_TITLE))
    knowledge_repo = sandbox.new_dir("knowledge", "billing")
    copy_onto(sandbox, knowledge_repo / ".onto")
    before = snapshot(knowledge_repo)

    as_module = sandbox.just("onto", cwd=root)
    as_file = sandbox.just(cwd=knowledge_repo, justfile=knowledge_repo / ".onto" / "Justfile")

    for result in (as_module, as_file):
        assert result.returncode == 0, result.stderr
        assert "build" in result.stdout and "query" in result.stdout
    assert not (root / GRAPH).parent.exists()
    assert sandbox.git("status", "--porcelain", cwd=root).stdout == ""
    assert snapshot(knowledge_repo) == before


def test_실행_위치에_표준_라이브러리나_의존성과_같은_이름의_파일이_있어도_도구가_돈다(sandbox):
    """`.onto/`는 구현 코드가 있는 프로젝트 저장소의 최상위에서 돈다. 거기의 `yaml.py`나 `types.py`가 도구를 가리면 안 된다."""
    root = root_with_billing(sandbox, page("plan/auth-redesign", "Plan", title=PLAN_TITLE))
    for name in ("yaml", "types", "rdflib"):
        (root / f"{name}.py").write_text("raise RuntimeError('도구가 실행 위치의 모듈에 가려졌다')\n", encoding="utf-8")

    result = query(sandbox, root, "SELECT ?e WHERE { ?e a onto:Plan }")

    assert result.returncode == 0, result.stderr
    assert parse_table(result.stdout) == [["e"], [PLAN_FILE]]


def test_just_onto_query는_서브모듈로_붙은_여러_저장소를_합쳐_교차_참조와_추론을_질의한다(sandbox):
    """가장 높은 이음매에서 보는 이 티켓의 줄기: 저장소 둘이 하나의 그래프가 되고, 교차 참조가 풀리고, 추이·역관계가 나온다."""
    root = sandbox.root()
    root.register(
        sandbox.knowledge_remote(
            "billing",
            files=repo("billing", page("component/gateway", "Component", title="게이트웨이", partOf=["shop:component/api"])),
        )
    )
    root.register(
        sandbox.knowledge_remote(
            "shop",
            files=repo("shop", page("component/api", "Component", title="상점 API", partOf=["project"]), title="상점"),
        )
    )

    part_of = query(sandbox, root.work, "SELECT ?s ?o WHERE { ?s onto:partOf ?o } ORDER BY ?s ?o")
    has_part = query(
        sandbox, root.work, 'SELECT ?o WHERE { ?s a onto:Project ; onto:repository "shop" ; onto:hasPart ?o } ORDER BY ?o'
    )

    gateway, api, shop = (
        "projects/billing/docs/ontology/component/gateway.md",
        "projects/shop/docs/ontology/component/api.md",
        "projects/shop/docs/ontology/ontology.yaml",
    )
    assert part_of.returncode == 0, part_of.stderr
    assert parse_table(part_of.stdout) == [["s", "o"], [gateway, api], [gateway, shop], [api, shop]]
    assert parse_table(has_part.stdout) == [["o"], [gateway], [api]]  # 정렬은 IRI 순이라 billing이 shop보다 앞선다


def test_just_onto_validate는_문제를_보고하고_오류가_있으면_0이_아닌_종료_코드로_끝난다(sandbox):
    root = root_with_billing(
        sandbox, page("component/gateway", "Component", title="게이트웨이", partOf="project", owner="kim"), title="결제"
    )

    result = sandbox.just("onto", "validate", cwd=root)

    assert result.returncode == 1
    assert result.stdout.splitlines() and all(len(line.split("\t")) == 5 for line in result.stdout.splitlines())
    assert result.stdout.split("\t")[:4] == ["오류", "billing", f"{PAGES}/component/gateway.md", "undefined-key"]
    assert "error: Recipe" not in result.stderr  # just가 레시피 실패를 따로 덧붙이지 않는다


def test_just_onto_validate는_문제가_없으면_아무것도_보고하지_않고_파일을_만들지_않는다(sandbox):
    root = root_with_billing(
        sandbox, page("component/gateway", "Component", title="게이트웨이", partOf="project"), title="결제"
    )

    result = sandbox.just("onto", "validate", cwd=root)

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert not (root / GRAPH).parent.exists()
    assert sandbox.git("status", "--porcelain", cwd=root).stdout == ""


def test_just_onto_rules는_루트_기본_규칙과_저장소가_덮어쓴_규칙을_보여_주고_파일을_만들지_않는다(sandbox):
    override = {"checks": {"orphan-page": {"enabled": False}}}
    root = root_with_billing(sandbox, page("component/gateway", "Component", title="게이트웨이", partOf="project"), title="결제", rules=override)

    default = sandbox.just("onto", "rules", cwd=root)
    billing = sandbox.just("onto", "rules", "billing", cwd=root)

    assert default.returncode == 0, default.stderr
    assert billing.returncode == 0, billing.stderr
    assert json.loads(default.stdout)["checks"]["orphan-page"] == {"enabled": True, "severity": "warning"}
    assert json.loads(billing.stdout)["checks"]["orphan-page"] == {"enabled": False, "severity": "warning"}
    assert sandbox.git("status", "--porcelain", cwd=root).stdout == ""


def test_복사된_onto는_함께_복사된_루트_기본_규칙을_기본값으로_쓴다(sandbox):
    """지식 저장소에서는 루트의 `onto/rules.yaml`이 `.onto/rules.yaml`로 복사되어 그 저장소의 기본값이 된다."""
    knowledge_repo = sandbox.new_dir("knowledge", "billing")
    copy_onto(sandbox, knowledge_repo / ".onto")
    rules_file = knowledge_repo / ".onto" / "rules.yaml"
    rules_file.write_text(rules_file.read_text(encoding="utf-8").replace("ignore-case: true", "ignore-case: false"), encoding="utf-8")

    result = sandbox.just("rules", cwd=knowledge_repo, justfile=knowledge_repo / ".onto" / "Justfile")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["duplicates"]["ignore-case"] is False
