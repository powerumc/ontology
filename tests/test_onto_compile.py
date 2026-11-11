"""온톨로지 도구의 컴파일: 지식 저장소의 페이지가 그래프의 사실로 나타난다.

온톨로지 도구의 명령줄 진입점을 견본 페이지 디렉토리에 대고 실행한다(`onto_cli`).
"""

import re

import pytest

from support.onto_cli import ONTOLOGY_DIR, page, repo, snapshot

PAGES = "projects/billing/docs/ontology"
PLAN_FILE = f"{PAGES}/plan/auth-redesign.md"
PROJECT_FILE = f"{PAGES}/ontology.yaml"
REPOSITORY = "https://onto.invalid/vocab#repository"  # 컴파일이 모든 엔티티에 적는, 엔티티가 온 지식 저장소의 이름


def billing(*pages, **project):
    return {"billing": repo("billing", *pages, **project)}


# --- 식별자와 파일 -----------------------------------------------------------


def test_페이지의_제목이_질의되고_결과의_엔티티는_파일_경로로_나온다(onto_cli):
    root = onto_cli.root(billing(page("plan/auth-redesign", "Plan", title="인증 재설계")))

    rows = onto_cli.query(root, "SELECT ?e ?t WHERE { ?e dcterms:title ?t }")

    assert rows == [[PLAN_FILE, "인증 재설계"]]


def test_식별자는_온톨로지_층_기준_상대_경로에서_확장자를_뺀_것이다(onto_cli):
    root = onto_cli.root(
        billing(
            page("plan/auth-redesign", "Plan", title="인증 재설계"),
            page("component/api/gateway", "Component", title="게이트웨이"),
        )
    )

    rows = onto_cli.query(root, "SELECT (STR(?e) AS ?iri) WHERE { ?e dcterms:title ?t } ORDER BY ?iri")

    assert [iri.rsplit("/billing/", 1)[1] for (iri,) in rows] == ["component/api/gateway", "plan/auth-redesign"]


def test_별도의_id_필드는_없고_JSON_LD_예약어_키는_식별자를_바꾸지_못한다(onto_cli):
    root = onto_cli.root(billing(page("plan/auth-redesign", "Plan", title="제목", id="other", **{"@id": "evil"})))

    rows = onto_cli.query(root, "SELECT (STR(?e) AS ?iri) WHERE { ?e a onto:Plan }")

    assert [iri.rsplit("/billing/", 1)[1] for (iri,) in rows] == ["plan/auth-redesign"]


def test_페이지_아닌_파일은_엔티티가_되지_않는다(onto_cli):
    """`index.md`는 생성물이라 frontmatter가 없다. `skipped.yaml`과 숨김 파일도 페이지가 아니다."""
    files = billing(page("plan/auth-redesign", "Plan", title="인증 재설계"))
    files["billing"].update(
        {
            f"{ONTOLOGY_DIR}/index.md": "# 인덱스\n\n- plan/auth-redesign\n",
            f"{ONTOLOGY_DIR}/skipped.yaml": "- path: docs/old.md\n  hash: 0123456789abcdef0123456789abcdef01234567\n",
            f"{ONTOLOGY_DIR}/.hidden/note.md": "frontmatter 없음\n",
        }
    )
    root = onto_cli.root(files)

    result = onto_cli.run(root, "build")

    assert result.returncode == 0, result.stderr
    assert onto_cli.query(root, "SELECT ?e WHERE { ?e dcterms:title ?t }") == [[PLAN_FILE]]


def test_지식_저장소_여럿이_같은_식별자를_써도_엔티티가_따로_있다(onto_cli):
    root = onto_cli.root(
        {
            "billing": repo("billing", page("plan/roadmap", "Plan", title="결제 로드맵")),
            "shop": repo("shop", page("plan/roadmap", "Plan", title="상점 로드맵")),
        }
    )

    rows = onto_cli.query(root, "SELECT ?e ?t WHERE { ?e a onto:Plan ; dcterms:title ?t } ORDER BY ?t")

    assert rows == [
        ["projects/billing/docs/ontology/plan/roadmap.md", "결제 로드맵"],
        ["projects/shop/docs/ontology/plan/roadmap.md", "상점 로드맵"],
    ]


# --- frontmatter -------------------------------------------------------------


def test_frontmatter의_클래스_제목_설명_별칭_날짜가_그래프의_사실이_된다(onto_cli):
    root = onto_cli.root(
        billing(
            page(
                "plan/auth-redesign",
                "Plan",
                title="인증 재설계",
                description="인증을 토큰 기반으로 바꾼다",
                aliases=["인증 개편", "auth redesign"],
                date="2026-11-01",
            )
        )
    )

    rows = onto_cli.query(
        root,
        "SELECT ?e ?title ?description ?alias ?date WHERE { ?e a onto:Plan ; dcterms:title ?title ; "
        "dcterms:description ?description ; skos:altLabel ?alias ; dcterms:date ?date } ORDER BY ?alias",
    )

    assert rows == [
        [PLAN_FILE, "인증 재설계", "인증을 토큰 기반으로 바꾼다", "auth redesign", "2026-11-01"],
        [PLAN_FILE, "인증 재설계", "인증을 토큰 기반으로 바꾼다", "인증 개편", "2026-11-01"],
    ]


def test_따옴표_없는_YAML_날짜도_날짜_값이_된다(onto_cli):
    files = billing()
    files["billing"][f"{ONTOLOGY_DIR}/report/launch.md"] = "---\nclass: Report\ndate: 2026-11-01\n---\n"
    root = onto_cli.root(files)

    rows = onto_cli.query(root, "SELECT ?when (DATATYPE(?when) AS ?type) WHERE { ?e dcterms:date ?when }")

    assert rows == [["2026-11-01", "http://www.w3.org/2001/XMLSchema#date"]]


@pytest.mark.parametrize("env", [None, {"LC_ALL": "C"}], ids=["기본_로케일", "C_로케일"])
def test_한국어_제목과_별칭이_깨지지_않고_질의된다(onto_cli, sandbox, env):
    root = onto_cli.root(billing(page("plan/auth-redesign", "Plan", title="인증 재설계", aliases=["인증 개편", "auth"])))
    run_env = None if env is None else {**sandbox.env, **env}

    by_title = onto_cli.run(root, "query", 'SELECT ?e WHERE { ?e dcterms:title "인증 재설계" }', env=run_env)
    aliases = onto_cli.run(root, "query", "SELECT ?e ?alias WHERE { ?e skos:altLabel ?alias }", env=run_env)

    assert by_title.returncode == 0, by_title.stderr
    assert by_title.stdout.splitlines() == ["e", PLAN_FILE]
    assert aliases.returncode == 0, aliases.stderr
    assert sorted(aliases.stdout.splitlines()[1:]) == sorted([f"{PLAN_FILE}\t인증 개편", f"{PLAN_FILE}\tauth"])


def test_한국어_별칭으로도_영어_별칭으로도_같은_엔티티에_닿는다(onto_cli):
    root = onto_cli.root(billing(page("plan/auth-redesign", "Plan", title="인증 재설계", aliases=["인증 개편", "auth redesign"])))

    korean = onto_cli.query(root, 'SELECT ?e WHERE { ?e skos:altLabel "인증 개편" }')
    english = onto_cli.query(root, 'SELECT ?e WHERE { ?e skos:altLabel "auth redesign" }')

    assert korean == english == [[PLAN_FILE]]


# (관계, 쓰는 쪽 클래스, 쓰는 쪽 식별자, 가리키는 쪽 클래스, 가리키는 쪽 식별자)
RELATIONS = [
    ("partOf", "Component", "component/api", "Component", "component/platform"),
    ("dependsOn", "Component", "component/api", "Component", "component/database"),
    ("implements", "Report", "report/launch", "Plan", "plan/auth-redesign"),
    ("governs", "Policy", "policy/no-secrets", "Component", "component/api"),
    ("supersedes", "Plan", "plan/auth-redesign-v2", "Plan", "plan/auth-redesign"),
    ("about", "Decision", "decision/use-jwt", "Component", "component/api"),
]


@pytest.mark.parametrize("relation, from_class, from_id, to_class, to_id", RELATIONS, ids=[r[0] for r in RELATIONS])
def test_같은_저장소_안의_관계는_쓴_방향_그대로_그래프의_사실이_된다(onto_cli, relation, from_class, from_id, to_class, to_id):
    root = onto_cli.root(
        billing(
            page(from_id, from_class, title="쓰는 쪽", **{relation: [to_id]}),
            page(to_id, to_class, title="가리키는 쪽"),
        )
    )

    rows = onto_cli.query(root, f"SELECT ?s ?o WHERE {{ ?s onto:{relation} ?o }}")

    assert rows == [[f"{PAGES}/{from_id}.md", f"{PAGES}/{to_id}.md"]]


def test_관계의_값은_하나여도_목록이어도_된다(onto_cli):
    root = onto_cli.root(
        billing(
            page("component/api", "Component", title="API", partOf="component/platform", dependsOn=["component/db", "component/cache"]),
            page("component/platform", "Component", title="플랫폼"),
            page("component/db", "Component", title="DB"),
            page("component/cache", "Component", title="캐시"),
        )
    )

    part_of = onto_cli.query(root, "SELECT ?o WHERE { ?s onto:partOf ?o }")
    depends_on = onto_cli.query(root, "SELECT ?o WHERE { ?s onto:dependsOn ?o } ORDER BY ?o")

    assert part_of == [[f"{PAGES}/component/platform.md"]]
    assert depends_on == [[f"{PAGES}/component/cache.md"], [f"{PAGES}/component/db.md"]]


def test_없는_엔티티를_가리키는_관계는_파일_경로가_아니라_IRI로_나온다(onto_cli):
    root = onto_cli.root(billing(page("component/api", "Component", title="API", partOf=["component/missing"])))

    rows = onto_cli.query(root, "SELECT ?o WHERE { ?s onto:partOf ?o }")

    assert len(rows) == 1
    assert rows[0][0].startswith("https://") and rows[0][0].endswith("/billing/component/missing")


# --- Project 엔티티 ----------------------------------------------------------


def test_Project_엔티티가_페이지_없이_ontology_yaml에서_만들어진다(onto_cli):
    root = onto_cli.root(billing(title="결제", description="결제 서비스", aliases=["billing service"]))

    rows = onto_cli.query(
        root,
        "SELECT ?e (STR(?e) AS ?iri) ?t ?d ?a WHERE "
        "{ ?e a onto:Project ; dcterms:title ?t ; dcterms:description ?d ; skos:altLabel ?a }",
    )

    assert len(rows) == 1
    file, iri, title, description, alias = rows[0]
    assert file == PROJECT_FILE
    assert iri.endswith("/billing/project")
    assert (title, description, alias) == ("결제", "결제 서비스", "billing service")


def test_ontology_yaml에_제목이_없어도_Project_엔티티는_있다(onto_cli):
    root = onto_cli.root(billing())

    assert onto_cli.query(root, "SELECT ?e WHERE { ?e a onto:Project }") == [[PROJECT_FILE]]


def test_지식_저장소마다_Project_엔티티가_하나씩_있다(onto_cli):
    root = onto_cli.root({"billing": repo("billing"), "shop": repo("shop")})

    rows = onto_cli.query(root, "SELECT ?e WHERE { ?e a onto:Project } ORDER BY ?e")

    assert rows == [["projects/billing/docs/ontology/ontology.yaml"], ["projects/shop/docs/ontology/ontology.yaml"]]


def test_컴포넌트가_식별자_project로_Project의_일부가_된다(onto_cli):
    root = onto_cli.root(billing(page("component/api", "Component", title="API", partOf=["project"])))

    rows = onto_cli.query(root, "SELECT ?s ?o WHERE { ?s onto:partOf ?o }")

    assert rows == [[f"{PAGES}/component/api.md", PROJECT_FILE]]


# --- 지식 저장소를 찾는 곳 ---------------------------------------------------


def test_지식_저장소가_없으면_공통_어휘만_있는_그래프가_나온다(onto_cli):
    root = onto_cli.root()

    result = onto_cli.run(root, "build")

    assert result.returncode == 0, result.stderr
    assert onto_cli.query(root, "SELECT ?e WHERE { ?e a onto:Plan }") == []
    assert onto_cli.query(root, "SELECT ?c WHERE { ?c a owl:Class }") != []


def test_온톨로지_층이_없는_서브모듈은_알리고_건너뛴다(onto_cli):
    files = billing(page("plan/auth-redesign", "Plan", title="인증 재설계"))
    files["notes"] = {"README.md": "# 온톨로지 층이 없는 저장소\n"}
    root = onto_cli.root(files)

    result = onto_cli.run(root, "query", "SELECT ?e WHERE { ?e dcterms:title ?t }")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["e", PLAN_FILE]
    assert "projects/notes" in result.stderr


# --- 읽을 수 없는 파일 -------------------------------------------------------

BAD_PAGES = {
    "frontmatter_없음": "# 제목\n\n본문만 있다\n",
    "닫히지_않음": "---\nclass: Plan\ntitle: 제목\n",
    "YAML_문법_오류": "---\nclass: [Plan\ntitle: 제목\n---\n",
    "키와_값의_목록이_아님": "---\n- Plan\n- 제목\n---\n",
    "중첩된_값": "---\nclass: Plan\ntitle:\n  ko: 제목\n---\n",
    "관계_값이_문자열이_아님": "---\nclass: Component\npartOf: [1, 2]\n---\n",
    "없는_날짜": "---\nclass: Report\ntitle: x\ndate: 2026-02-30\n---\n",
}


@pytest.mark.parametrize("command", ["build", "query"])
@pytest.mark.parametrize("content", BAD_PAGES.values(), ids=BAD_PAGES.keys())
def test_frontmatter를_읽을_수_없는_페이지는_파일_이름과_함께_오류로_알린다(onto_cli, command, content):
    files = billing(page("plan/good", "Plan", title="좋은 페이지"))
    files["billing"][f"{ONTOLOGY_DIR}/plan/broken.md"] = content
    root = onto_cli.root(files)

    result = onto_cli.run(root, command, *(["SELECT ?e WHERE { ?e a onto:Plan }"] if command == "query" else []))

    assert result.returncode != 0
    assert f"{PAGES}/plan/broken.md" in result.stderr
    assert f"{PAGES}/plan/good.md" not in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""  # 일부만 컴파일한 결과를 내놓지 않는다
    assert not onto_cli.graph_file.exists()


def test_UTF_8이_아닌_페이지도_파일_이름과_함께_오류로_알린다(onto_cli):
    root = onto_cli.root(billing())
    broken = root / PAGES / "plan" / "broken.md"
    broken.parent.mkdir(parents=True)
    broken.write_bytes("---\ntitle: 제목\n---\n".encode("euc-kr"))

    result = onto_cli.run(root, "build")

    assert result.returncode != 0
    assert f"{PAGES}/plan/broken.md" in result.stderr


def test_읽을_수_없는_페이지가_여럿이면_모두_알린다(onto_cli):
    files = billing()
    files["billing"][f"{ONTOLOGY_DIR}/plan/one.md"] = BAD_PAGES["frontmatter_없음"]
    files["billing"][f"{ONTOLOGY_DIR}/plan/two.md"] = BAD_PAGES["닫히지_않음"]
    root = onto_cli.root(files)

    result = onto_cli.run(root, "build")

    assert result.returncode != 0
    assert f"{PAGES}/plan/one.md" in result.stderr
    assert f"{PAGES}/plan/two.md" in result.stderr


@pytest.mark.parametrize(
    "content",
    ["name: [billing\n", "title: 이름이 없다\n", "- billing\n", "name: ''\n", "name: billing\nstarted: 2026-02-30\n"],
)
def test_읽을_수_없는_ontology_yaml도_파일_이름과_함께_오류로_알린다(onto_cli, content):
    root = onto_cli.root({"billing": {f"{ONTOLOGY_DIR}/ontology.yaml": content}})

    result = onto_cli.run(root, "build")

    assert result.returncode != 0
    assert PROJECT_FILE in result.stderr
    assert "Traceback" not in result.stderr


# --- 공통 어휘 ---------------------------------------------------------------


def test_공통_어휘가_클래스_여덟_개를_정의한다(onto_cli):
    root = onto_cli.root()

    rows = onto_cli.query(
        root,
        "SELECT (STRAFTER(STR(?c), STR(onto:)) AS ?name) WHERE "
        "{ ?c a owl:Class . FILTER(STRSTARTS(STR(?c), STR(onto:))) } ORDER BY ?name",
    )

    assert [name for (name,) in rows] == sorted(
        ["Project", "Component", "Plan", "Policy", "Term", "Decision", "Report", "Source"]
    )


def test_공통_어휘가_관계_일곱_개와_추론으로만_생기는_역관계_네_개를_정의한다(onto_cli):
    root = onto_cli.root()

    rows = onto_cli.query(
        root,
        "SELECT (STRAFTER(STR(?p), STR(onto:)) AS ?name) WHERE "
        "{ ?p a owl:ObjectProperty . FILTER(STRSTARTS(STR(?p), STR(onto:))) } ORDER BY ?name",
    )

    assert [name for (name,) in rows] == sorted(
        ["partOf", "dependsOn", "implements", "governs", "supersedes", "derivedFrom", "about"]
        + ["hasPart", "implementedBy", "governedBy", "supersededBy"]
    )


def test_공통_어휘의_클래스와_관계는_고정_네임스페이스_하나를_쓴다(onto_cli):
    """네임스페이스는 https이고 엔티티의 IRI와 겹치지 않으며, 어휘가 정의한 것은 모두 그 안에 있다."""
    root = onto_cli.root(billing(page("plan/auth-redesign", "Plan", title="제목")))

    outside = onto_cli.query(
        root,
        "SELECT ?t WHERE { ?t a ?kind . FILTER(?kind IN (owl:Class, owl:ObjectProperty) && !STRSTARTS(STR(?t), STR(onto:))) }",
    )
    namespace = onto_cli.query(root, "SELECT (STR(onto:) AS ?ns) WHERE {}")
    entity = onto_cli.query(root, "SELECT (STR(?e) AS ?iri) WHERE { ?e a onto:Plan }")

    assert outside == []
    assert namespace[0][0].startswith("https://")
    assert not entity[0][0].startswith(namespace[0][0])


def test_공통_어휘가_표준_어휘를_재사용한다(onto_cli):
    """용어는 SKOS, 출처는 PROV-O. 제목과 날짜는 DCTERMS(위의 페이지 테스트)."""
    root = onto_cli.root()

    rows = onto_cli.query(
        root,
        "SELECT ?term ?source ?derived WHERE { "
        "BIND(EXISTS { onto:Term rdfs:subClassOf skos:Concept } AS ?term) "
        "BIND(EXISTS { onto:Source rdfs:subClassOf prov:Entity } AS ?source) "
        "BIND(EXISTS { onto:derivedFrom rdfs:subPropertyOf prov:wasDerivedFrom } AS ?derived) }",
    )

    assert rows == [["true", "true", "true"]]


# --- 같은 입력에서는 같은 그래프 ---------------------------------------------


def test_같은_입력에서는_작업_사본의_위치와_파일을_만든_순서와_무관하게_같은_그래프가_나온다(onto_cli):
    pages = [
        page("plan/auth-redesign", "Plan", title="인증 재설계", aliases=["인증 개편", "auth redesign"], partOf=["project"]),
        page("component/api", "Component", title="API", partOf=["project"], dependsOn=["component/db"]),
        page("component/db", "Component", title="DB", partOf=["project"]),
    ]
    forward = onto_cli.root({"billing": repo("billing", *pages), "shop": repo("shop", page("plan/x", "Plan", title="x"))})
    backward = onto_cli.root({"shop": repo("shop", page("plan/x", "Plan", title="x")), "billing": repo("billing", *reversed(pages))})

    first = onto_cli.build(forward)
    second = onto_cli.build(backward)

    assert first == second
    assert onto_cli.build(forward) == first


def test_절대_IRI의_기준은_기기와_무관한_https_고정값이다(onto_cli):
    root = onto_cli.root(
        billing(page("plan/auth-redesign", "Plan", title="제목", partOf=["project"]), title="결제")
    )

    rows = onto_cli.query(
        root, "SELECT (STR(?e) AS ?iri) WHERE { { ?e dcterms:title ?t } UNION { ?x onto:partOf ?e } } ORDER BY ?iri"
    )
    graph = onto_cli.build(root).decode("utf-8")

    assert rows
    for (iri,) in rows:
        assert iri.startswith("https://")
        assert str(root) not in iri
    assert str(root) not in graph
    assert "file:" not in graph


# --- 질의의 출력 -------------------------------------------------------------


def test_ASK_질의는_true나_false를_출력한다(onto_cli):
    root = onto_cli.root(billing(page("plan/auth-redesign", "Plan", title="인증 재설계")))

    found = onto_cli.run(root, "query", 'ASK { ?e dcterms:title "인증 재설계" }')
    missing = onto_cli.run(root, "query", 'ASK { ?e dcterms:title "없는 제목" }')

    assert (found.returncode, found.stdout.strip()) == (0, "true")
    assert (missing.returncode, missing.stdout.strip()) == (0, "false")


def test_CONSTRUCT_질의는_Turtle로_출력하고_엔티티의_IRI가_가리키는_파일을_주석으로_덧붙인다(onto_cli):
    root = onto_cli.root(billing(page("plan/auth-redesign", "Plan", title="제목", about=["project"])))

    result = onto_cli.run(root, "query", "CONSTRUCT { ?s onto:about ?o } WHERE { ?s onto:about ?o }")

    assert result.returncode == 0, result.stderr
    assert "onto:about" in result.stdout
    mapped = re.findall(r"^# <(https://[^>]+)> (\S+)$", result.stdout, flags=re.MULTILINE)
    assert sorted(path for _, path in mapped) == sorted([PLAN_FILE, PROJECT_FILE])
    for iri, _ in mapped:
        assert f"<{iri}>" in result.stdout.split("\n\n", 1)[1]  # 주석이 가리키는 IRI는 Turtle 본문에 나온다


def test_질의문에_문법_오류가_있으면_0이_아닌_종료_코드로_알린다(onto_cli):
    root = onto_cli.root(billing())

    result = onto_cli.run(root, "query", "SELEC ?e WHERE { ?e a onto:Plan }")

    assert result.returncode != 0
    assert "SPARQL" in result.stderr
    assert result.stdout == ""


def test_값이_없는_칸은_비우고_줄바꿈과_탭이_든_값은_한_줄을_유지한다(onto_cli):
    root = onto_cli.root(billing(page("plan/auth-redesign", "Plan", title="첫 줄\n둘째\t줄")))

    result = onto_cli.run(root, "query", "SELECT ?t ?missing WHERE { ?e dcterms:title ?t . OPTIONAL { ?e dcterms:description ?missing } }")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["t\tmissing", "첫 줄\\n둘째\\t줄\t"]


# --- 리뷰 지적의 회귀 --------------------------------------------------------


@pytest.mark.parametrize("cls", ["plan", "@id", "Plan Draft"])
def test_공통_어휘에_없는_클래스_이름도_작업_사본의_경로가_그래프에_새지_않는다(onto_cli, cls):
    """디렉토리 이름을 따라 `class: plan`처럼 쓰는 일이 흔하다. 같은 입력은 어디서 컴파일해도 같은 그래프여야 한다."""
    files = billing(page("plan/auth-redesign", cls, title="제목"))
    first_root, second_root = onto_cli.root(files), onto_cli.root(files)

    first = onto_cli.build(first_root)
    second = onto_cli.build(second_root)

    assert first == second
    for root in (first_root, second_root):
        assert str(root) not in first.decode("utf-8")
    assert "file:" not in first.decode("utf-8")


def test_지식_저장소_최상위에_표준_라이브러리나_의존성과_같은_이름의_파일이_있어도_도구가_돈다(onto_cli):
    root = onto_cli.root(billing(page("plan/auth-redesign", "Plan", title="인증 재설계")))
    for name in ("yaml", "json", "rdflib", "types"):
        (root / f"{name}.py").write_text("raise RuntimeError('도구가 실행 위치의 모듈에 가려졌다')\n", encoding="utf-8")

    result = onto_cli.run(root, "query", "SELECT ?e WHERE { ?e a onto:Plan }")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["e", PLAN_FILE]


def test_build는_지식_저장소의_인덱스_말고는_작업_트리에_아무것도_만들지_않고_산출물은_도구_디렉토리에_둔다(onto_cli):
    root = onto_cli.root(billing(page("plan/auth-redesign", "Plan", title="인증 재설계")), indexed=False)
    before = snapshot(root)

    result = onto_cli.run(root, "build")

    assert result.returncode == 0, result.stderr
    assert onto_cli.graph_file.is_file()
    assert snapshot(root) - before == {f"{PAGES}/index.md"}  # 인덱스는 생성물이지만 커밋하는 파일이라 온톨로지 층에 둔다
    assert before <= snapshot(root)


def test_식별자가_project인_페이지는_Project_엔티티와_합쳐지지_않고_파일_이름과_함께_오류로_알린다(onto_cli):
    root = onto_cli.root(billing(page("project", "Component", title="가짜 프로젝트"), title="결제"))

    result = onto_cli.run(root, "build")

    assert result.returncode != 0
    assert f"{PAGES}/project.md" in result.stderr
    assert not onto_cli.graph_file.exists()


def test_하위_디렉토리의_project_페이지는_Project_엔티티와_겹치지_않는다(onto_cli):
    root = onto_cli.root(billing(page("component/project", "Component", title="프로젝트 컴포넌트"), title="결제"))

    rows = onto_cli.query(root, "SELECT ?e ?t WHERE { ?e dcterms:title ?t } ORDER BY ?e")

    assert rows == [[f"{PAGES}/component/project.md", "프로젝트 컴포넌트"], [PROJECT_FILE, "결제"]]


def test_페이지의_정의되지_않은_키는_그래프에_들어가지_않는다(onto_cli):
    """콜론이 든 키(`foo:bar`)도 술어로 풀리지 않는다. 정의되지 않은 키를 오류로 알리는 것은 스크립트 검사의 몫이다."""
    root = onto_cli.root(billing(page("plan/auth-redesign", "Plan", title="제목", memo="메모", **{"foo:bar": "값"})))

    rows = onto_cli.query(
        root, "SELECT DISTINCT (STR(?p) AS ?predicate) WHERE { ?e a onto:Plan ; ?p ?o } ORDER BY ?predicate"
    )

    assert rows == [
        ["http://purl.org/dc/terms/title"],
        ["http://www.w3.org/1999/02/22-rdf-syntax-ns#type"],
        [REPOSITORY],
    ]


def test_ontology_yaml의_다른_키는_Project의_사실이_되지_않고_제목이_없어도_이름으로_채우지_않는다(onto_cli):
    """`ontology.yaml`의 `title`·`description`·`aliases`는 선택이다. 공유 범위나 규칙 같은 키는 엔티티를 서술하지 않는다."""
    with_other_keys = onto_cli.root(billing(title="결제", scope="private", rules={"sources": {"include": ["docs/**/*.md"]}}))
    without_title = onto_cli.root(billing())

    predicates = onto_cli.query(
        with_other_keys, "SELECT DISTINCT (STR(?p) AS ?predicate) WHERE { ?e a onto:Project ; ?p ?o } ORDER BY ?predicate"
    )
    title = onto_cli.query(without_title, "SELECT ?e ?t WHERE { ?e a onto:Project . OPTIONAL { ?e dcterms:title ?t } }")

    assert predicates == [
        ["http://purl.org/dc/terms/title"],
        ["http://www.w3.org/1999/02/22-rdf-syntax-ns#type"],
        [REPOSITORY],
    ]
    assert title == [[PROJECT_FILE, ""]]


def test_형식이_틀린_날짜_값이어도_도구_내부의_오류_출력_없이_값은_그대로_질의된다(onto_cli):
    """날짜 값의 종류 검사는 스크립트 검사의 몫이다. 컴파일은 rdflib의 변환 실패 로그를 사용자에게 흘리지 않는다."""
    root = onto_cli.root(billing(page("report/launch", "Report", title="출시", date="2026-11")))

    result = onto_cli.run(root, "query", "SELECT ?d WHERE { ?e dcterms:date ?d }")

    assert result.returncode == 0
    assert result.stdout.splitlines() == ["d", "2026-11"]
    assert result.stderr == ""


def test_여러_지식_저장소의_읽을_수_없는_파일을_한꺼번에_모두_알린다(onto_cli):
    broken_billing = billing(page("plan/good", "Plan", title="좋은 페이지"))
    broken_billing["billing"][f"{ONTOLOGY_DIR}/plan/broken.md"] = BAD_PAGES["frontmatter_없음"]
    broken_shop = {"shop": {f"{ONTOLOGY_DIR}/ontology.yaml": "title: 이름이 없다\n"}}
    broken_mall = {"mall": repo("mall")}
    broken_mall["mall"][f"{ONTOLOGY_DIR}/report/bad-date.md"] = BAD_PAGES["없는_날짜"]
    root = onto_cli.root({**broken_billing, **broken_shop, **broken_mall})

    result = onto_cli.run(root, "build")

    assert result.returncode != 0
    for file in (f"{PAGES}/plan/broken.md", "projects/shop/docs/ontology/ontology.yaml", "projects/mall/docs/ontology/report/bad-date.md"):
        assert file in result.stderr
    assert not onto_cli.graph_file.exists()


# --- 문서화된 키 -------------------------------------------------------------

DCTERMS = "http://purl.org/dc/terms/"
VOCAB = "https://onto.invalid/vocab#"
# 문서화된 frontmatter 키와, 그 키가 그래프에서 되는 술어. `onto/onto_tool/keys.py`가 아는 키의 집합과 같아야 한다.
# 키를 더하면 여기에도 더한다. 도구 내부의 상수를 읽지 않고, 여기 적힌 목록으로 도구를 실행해 결과를 본다.
PAGE_KEYS_AS_PREDICATES = {
    "class": "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
    "title": f"{DCTERMS}title",
    "description": f"{DCTERMS}description",
    "date": f"{DCTERMS}date",
    "aliases": "http://www.w3.org/2004/02/skos/core#altLabel",
    "partOf": f"{VOCAB}partOf",
    "dependsOn": f"{VOCAB}dependsOn",
    "implements": f"{VOCAB}implements",
    "governs": f"{VOCAB}governs",
    "supersedes": f"{VOCAB}supersedes",
    "derivedFrom": f"{VOCAB}derivedFrom",
    "about": f"{VOCAB}about",
}
DOCUMENTED_RELATION_KEYS = ("partOf", "dependsOn", "implements", "governs", "supersedes", "about")


def test_문서화된_frontmatter_키를_모두_쓴_페이지는_키마다_그래프에_나타나고_관계는_대상_엔티티와_이어진다(onto_cli):
    targets = {key: f"component/{key.lower()}-target" for key in DOCUMENTED_RELATION_KEYS}
    subject = page(
        "component/subject",
        "Component",
        title="주체",
        description="설명",
        date="2026-11-01",
        aliases=["별칭", "alias"],
        derivedFrom=[{"path": "docs/design.md", "hash": "0123456789abcdef0123456789abcdef01234567"}],
        **{key: [target] for key, target in targets.items()},
    )
    root = onto_cli.root(billing(subject, *(page(target, "Component", title=f"{key} 대상") for key, target in targets.items())))

    rows = onto_cli.query(root, 'SELECT (STR(?p) AS ?predicate) ?o WHERE { ?e dcterms:title "주체" ; ?p ?o }')

    facts = {(predicate, obj) for predicate, obj in rows}
    expected = {
        "class": {(PAGE_KEYS_AS_PREDICATES["class"], f"{VOCAB}Component")},
        "title": {(PAGE_KEYS_AS_PREDICATES["title"], "주체")},
        "description": {(PAGE_KEYS_AS_PREDICATES["description"], "설명")},
        "date": {(PAGE_KEYS_AS_PREDICATES["date"], "2026-11-01")},
        "aliases": {(PAGE_KEYS_AS_PREDICATES["aliases"], "별칭"), (PAGE_KEYS_AS_PREDICATES["aliases"], "alias")},
        # 관계는 값이 대상 엔티티의 IRI로 풀려, 질의 결과에서 대상 페이지의 파일 경로로 나온다.
        **{key: {(PAGE_KEYS_AS_PREDICATES[key], f"{PAGES}/{target}.md")} for key, target in targets.items()},
        # 원본 문서는 `Source` 엔티티가 되어, 질의 결과에서 원본 문서의 파일 경로로 나온다.
        "derivedFrom": {(PAGE_KEYS_AS_PREDICATES["derivedFrom"], "projects/billing/docs/design.md")},
    }
    assert set(expected) == set(PAGE_KEYS_AS_PREDICATES)  # 목록의 모든 키를 썼다
    missing = {key: sorted(wanted - facts) for key, wanted in expected.items() if not wanted <= facts}
    assert missing == {}


def test_문서화된_ontology_yaml_키를_모두_쓰면_키마다_그래프에_나타난다(onto_cli):
    """`name`은 엔티티의 출처와 식별자에, `title`·`description`·`aliases`는 Project의 사실에, `classes`는 선언한 클래스에 나타난다."""
    root = onto_cli.root(
        billing(
            page("component/invoice-service", "Invoice", title="청구서 서비스"),
            title="결제",
            description="결제 서비스",
            aliases=["billing service", "청구"],
            classes={"Invoice": {"subClassOf": "Component"}},
        )
    )

    project = onto_cli.query(
        root, 'SELECT (STR(?e) AS ?iri) (STR(?p) AS ?predicate) ?o WHERE { ?e a onto:Project ; ?p ?o }'
    )
    invoice_as_component = onto_cli.query(root, 'SELECT ?e WHERE { ?e a onto:Component ; dcterms:title "청구서 서비스" }')

    facts = {(predicate, obj) for _, predicate, obj in project}
    assert {iri for iri, _, _ in project} == {"https://onto.invalid/entity/billing/project"}  # name
    assert (f"{VOCAB}repository", "billing") in facts  # name
    assert (f"{DCTERMS}title", "결제") in facts
    assert (f"{DCTERMS}description", "결제 서비스") in facts
    assert {obj for predicate, obj in facts if predicate.endswith("altLabel")} == {"billing service", "청구"}
    assert invoice_as_component == [[f"{PAGES}/component/invoice-service.md"]]  # classes
