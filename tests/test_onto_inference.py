"""추론: 하위 클래스, 역관계, 추이 관계 세 규칙이 질의 결과에 반영된다.

공통 어휘가 선언한 추이 관계(`partOf` 하나)와 역관계(`hasPart`, `implementedBy`, `governedBy`, `supersededBy`)를 쓴다.
온톨로지 도구의 명령줄 진입점을 견본 페이지 디렉토리에 대고 실행한다(`onto_cli`).
"""

import re

import pytest

from support.onto_cli import page, repo

PAGES = "projects/billing/docs/ontology"


def billing(*pages, **project):
    return {"billing": repo("billing", *pages, **project)}


def file(identifier: str) -> str:
    return f"{PAGES}/{identifier}.md"


# --- 공통 어휘의 선언 --------------------------------------------------------


def test_공통_어휘의_추이_관계는_partOf_하나다(onto_cli):
    root = onto_cli.root()

    rows = onto_cli.query(
        root, "SELECT (STRAFTER(STR(?p), STR(onto:)) AS ?name) WHERE { ?p a owl:TransitiveProperty } ORDER BY ?name"
    )

    assert rows == [["partOf"]]


def test_공통_어휘가_스펙의_관계_표대로_역관계를_선언한다(onto_cli):
    root = onto_cli.root()

    rows = onto_cli.query(
        root,
        "SELECT (STRAFTER(STR(?a), STR(onto:)) AS ?name) (STRAFTER(STR(?b), STR(onto:)) AS ?inverse) "
        "WHERE { ?a owl:inverseOf ?b }",
    )

    declared = {frozenset(row) for row in rows}  # owl:inverseOf는 대칭이라 어느 쪽에 적었는지는 묻지 않는다
    assert declared == {
        frozenset(("partOf", "hasPart")),
        frozenset(("implements", "implementedBy")),
        frozenset(("governs", "governedBy")),
        frozenset(("supersedes", "supersededBy")),
    }


def test_dependsOn은_추이_관계도_역관계도_아니다(onto_cli):
    root = onto_cli.root()

    rows = onto_cli.query(
        root,
        "SELECT ?x WHERE { "
        "{ onto:dependsOn a ?x . FILTER(?x IN (owl:TransitiveProperty, owl:SymmetricProperty)) } "
        "UNION { onto:dependsOn owl:inverseOf ?x } UNION { ?x owl:inverseOf onto:dependsOn } }",
    )

    assert rows == []


# --- 추이 관계 ---------------------------------------------------------------


def test_A가_B의_일부이고_B가_C의_일부이면_A는_C의_일부다(onto_cli):
    root = onto_cli.root(
        billing(
            page("component/a", "Component", title="A", partOf=["component/b"]),
            page("component/b", "Component", title="B", partOf=["component/c"]),
            page("component/c", "Component", title="C"),
        )
    )

    rows = onto_cli.query(root, "SELECT ?s ?o WHERE { ?s onto:partOf ?o } ORDER BY ?s ?o")

    assert rows == [
        [file("component/a"), file("component/b")],
        [file("component/a"), file("component/c")],
        [file("component/b"), file("component/c")],
    ]


def test_추이_관계는_사슬이_길어도_끝까지_이어진다(onto_cli):
    chain = ["component/a", "component/b", "component/c", "component/d", "component/e"]
    pages = [page(identifier, "Component", title=identifier, partOf=[parent]) for identifier, parent in zip(chain, chain[1:])]
    root = onto_cli.root(billing(*pages, page(chain[-1], "Component", title=chain[-1])))

    from_a = onto_cli.query(root, 'SELECT ?o WHERE { ?s dcterms:title "component/a" ; onto:partOf ?o } ORDER BY ?o')

    assert from_a == [[file(identifier)] for identifier in chain[1:]]


def test_엔티티가_Project의_일부로_끝나는_사슬도_이어진다(onto_cli):
    root = onto_cli.root(
        billing(
            page("component/api", "Component", title="API", partOf=["component/platform"]),
            page("component/platform", "Component", title="플랫폼", partOf=["project"]),
            title="결제",
        )
    )

    rows = onto_cli.query(root, 'SELECT ?o WHERE { ?s dcterms:title "API" ; onto:partOf ?o . ?o a onto:Project }')

    assert rows == [[f"{PAGES}/ontology.yaml"]]


def test_지식_저장소를_넘나드는_사슬도_추이로_이어진다(onto_cli):
    root = onto_cli.root(
        {
            "billing": repo("billing", page("component/gateway", "Component", title="게이트웨이", partOf=["shop:component/api"])),
            "shop": repo(
                "shop",
                page("component/api", "Component", title="상점 API", partOf=["mall:project"]),
            ),
            "mall": repo("mall", title="몰"),
        }
    )

    rows = onto_cli.query(root, 'SELECT ?o WHERE { ?s dcterms:title "게이트웨이" ; onto:partOf ?o } ORDER BY ?o')

    assert rows == [["projects/mall/docs/ontology/ontology.yaml"], ["projects/shop/docs/ontology/component/api.md"]]


def test_서로의_일부라고_적힌_순환이_있어도_추론은_끝난다(onto_cli):
    root = onto_cli.root(
        billing(
            page("component/a", "Component", title="A", partOf=["component/b"]),
            page("component/b", "Component", title="B", partOf=["component/a"]),
        )
    )

    result = onto_cli.run(root, "query", "SELECT ?s ?o WHERE { ?s onto:partOf ?o } ORDER BY ?s ?o")

    assert result.returncode == 0, result.stderr
    assert len(result.stdout.splitlines()) - 1 == 4  # a→b, b→a, 그리고 순환에서 따라오는 a→a, b→b


def test_dependsOn은_추이_관계가_아니어서_간접_의존은_추론되지_않는다(onto_cli):
    root = onto_cli.root(
        billing(
            page("component/a", "Component", title="A", dependsOn=["component/b"]),
            page("component/b", "Component", title="B", dependsOn=["component/c"]),
            page("component/c", "Component", title="C"),
        )
    )

    rows = onto_cli.query(root, "SELECT ?s ?o WHERE { ?s onto:dependsOn ?o } ORDER BY ?s")
    a_to_c = onto_cli.run(root, "query", 'ASK { ?s dcterms:title "A" ; onto:dependsOn ?o . ?o dcterms:title "C" }')

    assert rows == [[file("component/a"), file("component/b")], [file("component/b"), file("component/c")]]
    assert a_to_c.stdout.strip() == "false"


def test_dependsOn은_역방향도_추론되지_않는다(onto_cli):
    root = onto_cli.root(
        billing(
            page("component/a", "Component", title="A", dependsOn=["component/b"]),
            page("component/b", "Component", title="B"),
        )
    )

    triples = onto_cli.query(root, "SELECT ?s ?o WHERE { ?s ?p ?o . FILTER(?p != rdf:type && STRSTARTS(STR(?p), STR(onto:)) && ?p != onto:repository) }")

    assert triples == [[file("component/a"), file("component/b")]]


# --- 역관계 ------------------------------------------------------------------


def test_partOf의_역인_hasPart가_질의_결과에_나온다(onto_cli):
    root = onto_cli.root(
        billing(
            page("component/api", "Component", title="API", partOf=["component/platform"]),
            page("component/platform", "Component", title="플랫폼"),
        )
    )

    rows = onto_cli.query(root, "SELECT ?s ?o WHERE { ?s onto:hasPart ?o }")

    assert rows == [[file("component/platform"), file("component/api")]]


def test_추이로_이어진_일부도_hasPart로_나온다(onto_cli):
    root = onto_cli.root(
        billing(
            page("component/a", "Component", title="A", partOf=["component/b"]),
            page("component/b", "Component", title="B", partOf=["component/c"]),
            page("component/c", "Component", title="C"),
        )
    )

    rows = onto_cli.query(root, 'SELECT ?o WHERE { ?s dcterms:title "C" ; onto:hasPart ?o } ORDER BY ?o')

    assert rows == [[file("component/a")], [file("component/b")]]


@pytest.mark.parametrize(
    "relation, inverse, from_class, from_id, to_class, to_id",
    [
        ("implements", "implementedBy", "Report", "report/launch", "Plan", "plan/auth-redesign"),
        ("governs", "governedBy", "Policy", "policy/no-secrets", "Component", "component/api"),
        ("supersedes", "supersededBy", "Plan", "plan/auth-redesign-v2", "Plan", "plan/auth-redesign"),
    ],
    ids=["implementedBy", "governedBy", "supersededBy"],
)
def test_쓴_방향의_역관계가_질의_결과에_나온다(onto_cli, relation, inverse, from_class, from_id, to_class, to_id):
    root = onto_cli.root(
        billing(
            page(from_id, from_class, title="쓰는 쪽", **{relation: [to_id]}),
            page(to_id, to_class, title="가리키는 쪽"),
        )
    )

    inverse_rows = onto_cli.query(root, f"SELECT ?s ?o WHERE {{ ?s onto:{inverse} ?o }}")
    written_rows = onto_cli.query(root, f"SELECT ?s ?o WHERE {{ ?s onto:{relation} ?o }}")

    assert inverse_rows == [[file(to_id), file(from_id)]]
    assert written_rows == [[file(from_id), file(to_id)]]  # 쓴 방향은 그대로다


def test_다른_저장소의_엔티티를_가리키는_관계도_역관계가_나온다(onto_cli):
    root = onto_cli.root(
        {
            "billing": repo("billing", page("report/launch", "Report", title="출시", implements=["shop:plan/rollout"])),
            "shop": repo("shop", page("plan/rollout", "Plan", title="출시 계획")),
        }
    )

    rows = onto_cli.query(root, "SELECT ?s ?o WHERE { ?s onto:implementedBy ?o }")

    assert rows == [["projects/shop/docs/ontology/plan/rollout.md", f"{PAGES}/report/launch.md"]]


def test_supersedes는_추이가_아니어서_대체의_대체가_직접_대체로_추론되지_않는다(onto_cli):
    root = onto_cli.root(
        billing(
            page("plan/v3", "Plan", title="v3", supersedes=["plan/v2"]),
            page("plan/v2", "Plan", title="v2", supersedes=["plan/v1"]),
            page("plan/v1", "Plan", title="v1"),
        )
    )

    supersedes = onto_cli.query(root, "SELECT ?s ?o WHERE { ?s onto:supersedes ?o } ORDER BY ?s")
    superseded_by = onto_cli.query(root, "SELECT ?s ?o WHERE { ?s onto:supersededBy ?o } ORDER BY ?s")

    assert supersedes == [[file("plan/v2"), file("plan/v1")], [file("plan/v3"), file("plan/v2")]]
    assert superseded_by == [[file("plan/v1"), file("plan/v2")], [file("plan/v2"), file("plan/v3")]]


# --- 컴파일 결과의 파일과 결정성 ---------------------------------------------


def test_build가_남기는_그래프_파일에도_추론된_사실이_들어_있다(onto_cli):
    root = onto_cli.root(
        billing(
            page("component/a", "Component", title="A", partOf=["component/b"]),
            page("component/b", "Component", title="B", partOf=["component/c"]),
            page("component/c", "Component", title="C"),
        )
    )

    result = onto_cli.run(root, "build")
    graph = onto_cli.graph_file.read_text(encoding="utf-8")

    assert result.returncode == 0, result.stderr
    assert re.search(r"onto:hasPart\s+<[^>]*/billing/component/a>", graph)  # 추이로 이어진 C의 일부 A
    assert re.search(r"onto:partOf\s+<[^>]*/billing/component/b>,\s*<[^>]*/billing/component/c>", graph)


def test_추론이_들어가도_같은_입력에서는_해시_시드와_파일을_만든_순서와_무관하게_같은_그래프가_나온다(onto_cli, sandbox):
    pages = [
        page("component/a", "Component", title="A", partOf=["component/b"], dependsOn=["shop:component/api"]),
        page("component/b", "Component", title="B", partOf=["component/c"]),
        page("component/c", "Component", title="C", partOf=["project"]),
        page("report/launch", "Report", title="출시", implements=["plan/rollout"]),
        page("plan/rollout", "Plan", title="출시 계획"),
        page("term/invoice", "Term", title="청구서"),
    ]
    shop = repo("shop", page("component/api", "Component", title="상점 API", partOf=["project"]))
    forward = onto_cli.root({"billing": repo("billing", *pages), "shop": shop})
    backward = onto_cli.root({"shop": shop, "billing": repo("billing", *reversed(pages))})
    unordered = "SELECT ?s ?p ?o WHERE { ?s ?p ?o . FILTER(STRSTARTS(STR(?s), 'https://onto.invalid/entity/')) }"

    graphs, rows = set(), set()
    for root, seed in ((forward, "1"), (forward, "2"), (backward, "3"), (backward, "4")):
        env = {**sandbox.env, "PYTHONHASHSEED": seed}
        build = onto_cli.run(root, "build", env=env)
        assert build.returncode == 0, build.stderr
        graphs.add(onto_cli.graph_file.read_bytes())
        query = onto_cli.run(root, "query", unordered, env=env)
        assert query.returncode == 0, query.stderr
        rows.add(tuple(sorted(query.stdout.splitlines())))  # 정렬하지 않은 질의의 행 순서는 rdflib이 정한다

    assert len(graphs) == 1
    assert len(rows) == 1


# --- 입력은 건드리지 않는다 --------------------------------------------------


def test_추론된_사실은_질의_결과에만_나오고_페이지는_바뀌지_않는다(onto_cli):
    root = onto_cli.root(
        billing(
            page("component/a", "Component", title="A", partOf=["component/b"]),
            page("component/b", "Component", title="B"),
        )
    )
    before = {path: path.read_bytes() for path in (root / "projects").rglob("*") if path.is_file()}

    rows = onto_cli.query(root, "SELECT ?o WHERE { ?s onto:hasPart ?o }")

    assert rows == [[file("component/a")]]
    assert {path: path.read_bytes() for path in (root / "projects").rglob("*") if path.is_file()} == before
