"""교차 참조와 합쳐진 그래프: 여러 지식 저장소가 하나의 그래프가 되고, `<저장소 이름>:<식별자>`가 그 저장소의 엔티티로 풀린다.

온톨로지 도구의 명령줄 진입점을 견본 페이지 디렉토리에 대고 실행한다(`onto_cli`).
"""

from support.onto_cli import ONTOLOGY_DIR, page, repo


def pages_of(name: str) -> str:
    return f"projects/{name}/docs/ontology"


def two_repositories(billing_page, shop_page=None):
    """`billing`과 `shop` 지식 저장소. `shop`에는 컴포넌트 `component/api`가 있다."""
    return {
        "billing": repo("billing", billing_page),
        "shop": repo("shop", shop_page or page("component/api", "Component", title="상점 API")),
    }


# --- 교차 참조 ---------------------------------------------------------------


def test_교차_참조가_그_지식_저장소의_엔티티로_풀린다(onto_cli):
    root = onto_cli.root(
        two_repositories(page("component/gateway", "Component", title="결제 게이트웨이", dependsOn=["shop:component/api"]))
    )

    rows = onto_cli.query(root, "SELECT ?s ?o WHERE { ?s onto:dependsOn ?o }")

    assert rows == [[f"{pages_of('billing')}/component/gateway.md", f"{pages_of('shop')}/component/api.md"]]


def test_교차_참조된_엔티티는_자기_저장소에서_쓴_사실을_그대로_가진다(onto_cli):
    """참조하는 쪽이 가리킨 엔티티와 참조되는 쪽이 서술한 엔티티가 그래프에서 하나다."""
    root = onto_cli.root(
        two_repositories(page("component/gateway", "Component", title="결제 게이트웨이", dependsOn=["shop:component/api"]))
    )

    rows = onto_cli.query(root, "SELECT ?t WHERE { ?s onto:dependsOn ?o . ?o a onto:Component ; dcterms:title ?t }")

    assert rows == [["상점 API"]]


def test_교차_참조는_관계마다_쓸_수_있고_값이_목록이어도_된다(onto_cli):
    root = onto_cli.root(
        {
            "billing": repo(
                "billing",
                page(
                    "report/launch",
                    "Report",
                    title="출시",
                    implements=["shop:plan/rollout"],
                    about=["shop:project", "component/gateway"],
                ),
                page("component/gateway", "Component", title="게이트웨이"),
            ),
            "shop": repo("shop", page("plan/rollout", "Plan", title="상점 출시 계획"), title="상점"),
        }
    )

    implements = onto_cli.query(root, "SELECT ?o WHERE { ?s onto:implements ?o }")
    about = onto_cli.query(root, "SELECT ?o WHERE { ?s onto:about ?o } ORDER BY ?o")

    assert implements == [[f"{pages_of('shop')}/plan/rollout.md"]]
    assert about == [[f"{pages_of('billing')}/component/gateway.md"], [f"{pages_of('shop')}/ontology.yaml"]]


def test_다른_저장소의_Project_엔티티는_저장소_이름과_project로_가리킨다(onto_cli):
    root = onto_cli.root(
        two_repositories(page("component/gateway", "Component", title="게이트웨이", partOf=["shop:project"]))
    )

    rows = onto_cli.query(root, "SELECT ?o WHERE { ?s onto:partOf ?o . ?o a onto:Project }")

    assert rows == [[f"{pages_of('shop')}/ontology.yaml"]]


def test_저장소_이름_없는_식별자는_자기_저장소의_엔티티다(onto_cli):
    root = onto_cli.root(
        {
            "billing": repo(
                "billing",
                page("component/gateway", "Component", title="결제 게이트웨이", dependsOn=["component/api"]),
                page("component/api", "Component", title="결제 API"),
            ),
            "shop": repo("shop", page("component/api", "Component", title="상점 API")),
        }
    )

    rows = onto_cli.query(root, "SELECT ?o WHERE { ?s onto:dependsOn ?o }")

    assert rows == [[f"{pages_of('billing')}/component/api.md"]]


def test_자기_저장소의_이름을_붙여_쓴_참조도_같은_엔티티다(onto_cli):
    root = onto_cli.root(
        {
            "billing": repo(
                "billing",
                page("component/gateway", "Component", title="게이트웨이", dependsOn=["billing:component/api"]),
                page("component/api", "Component", title="API"),
            )
        }
    )

    rows = onto_cli.query(root, "SELECT ?o WHERE { ?s onto:dependsOn ?o }")

    assert rows == [[f"{pages_of('billing')}/component/api.md"]]


def test_같은_식별자가_다른_지식_저장소에_있어도_교차_참조는_가리킨_저장소의_엔티티로_간다(onto_cli):
    root = onto_cli.root(
        {
            "billing": repo(
                "billing",
                page("component/api", "Component", title="결제 API"),
                page("component/gateway", "Component", title="게이트웨이", dependsOn=["shop:component/api"]),
            ),
            "shop": repo("shop", page("component/api", "Component", title="상점 API")),
        }
    )

    titles = onto_cli.query(root, "SELECT ?t WHERE { ?s onto:dependsOn ?o . ?o dcterms:title ?t }")
    all_titles = onto_cli.query(root, "SELECT ?t WHERE { ?e a onto:Component ; dcterms:title ?t } ORDER BY ?t")

    assert titles == [["상점 API"]]
    assert all_titles == [["게이트웨이"], ["결제 API"], ["상점 API"]]


def test_풀리지_않는_교차_참조가_있어도_컴파일은_멈추지_않고_IRI로_나온다(onto_cli):
    """깨진 참조를 문제로 알리는 것은 스크립트 검사의 몫이다. 컴파일은 그래프를 만든다."""
    root = onto_cli.root(
        {
            "billing": repo(
                "billing",
                page("component/gateway", "Component", title="게이트웨이", dependsOn=["nowhere:component/api", "shop:component/missing"]),
            ),
            "shop": repo("shop"),
        }
    )

    build = onto_cli.run(root, "build")
    rows = onto_cli.query(root, "SELECT (STR(?o) AS ?iri) WHERE { ?s onto:dependsOn ?o } ORDER BY ?iri")

    assert build.returncode == 0, build.stderr
    assert [iri.rsplit("/entity/", 1)[1] for (iri,) in rows] == ["nowhere/component/api", "shop/component/missing"]


def test_따옴표_없이_손으로_쓴_YAML의_교차_참조도_풀린다(onto_cli):
    """콜론 뒤에 공백이 없으면 YAML은 `shop:component/api`를 하나의 문자열로 읽는다. 값 하나, 흐름 목록, 블록 목록 모두."""
    files = two_repositories(page("component/unused", "Component", title="안 씀"))
    files["billing"][f"{ONTOLOGY_DIR}/component/single.md"] = (
        "---\nclass: Component\ntitle: 하나\ndependsOn: shop:component/api\n---\n"
    )
    files["billing"][f"{ONTOLOGY_DIR}/component/flow.md"] = (
        "---\nclass: Component\ntitle: 흐름\ndependsOn: [shop:component/api, component/unused]\n---\n"
    )
    files["billing"][f"{ONTOLOGY_DIR}/component/block.md"] = (
        "---\nclass: Component\ntitle: 블록\ndependsOn:\n  - shop:component/api\n  - component/unused\n---\n"
    )
    root = onto_cli.root(files)

    rows = onto_cli.query(
        root, "SELECT ?t (COUNT(?o) AS ?count) WHERE { ?s dcterms:title ?t ; onto:dependsOn ?o } GROUP BY ?t ORDER BY ?t"
    )
    to_shop = onto_cli.query(root, 'SELECT ?t WHERE { ?s dcterms:title ?t ; onto:dependsOn ?o . ?o onto:repository "shop" } ORDER BY ?t')

    assert rows == [["블록", "2"], ["하나", "1"], ["흐름", "2"]]
    assert to_shop == [["블록"], ["하나"], ["흐름"]]


def test_교차_참조의_저장소_이름과_식별자_앞뒤_공백은_무시한다(onto_cli):
    root = onto_cli.root(
        two_repositories(page("component/gateway", "Component", title="게이트웨이", dependsOn=[" shop : component/api "]))
    )

    rows = onto_cli.query(root, "SELECT ?o WHERE { ?s onto:dependsOn ?o }")

    assert rows == [[f"{pages_of('shop')}/component/api.md"]]


# --- 합쳐진 그래프와 출처 ----------------------------------------------------


def test_여러_지식_저장소가_하나의_그래프로_합쳐진다(onto_cli):
    root = onto_cli.root(
        {
            "billing": repo("billing", page("plan/roadmap", "Plan", title="결제 로드맵"), title="결제"),
            "shop": repo("shop", page("plan/roadmap", "Plan", title="상점 로드맵"), title="상점"),
            "mall": repo("mall", page("component/api", "Component", title="몰 API")),
        }
    )

    plans = onto_cli.query(root, "SELECT ?t WHERE { ?e a onto:Plan ; dcterms:title ?t } ORDER BY ?t")
    projects = onto_cli.query(root, "SELECT ?e WHERE { ?e a onto:Project } ORDER BY ?e")

    assert plans == [["결제 로드맵"], ["상점 로드맵"]]
    assert len(projects) == 3


def test_엔티티가_어느_지식_저장소에서_왔는지_질의로_가려낸다(onto_cli):
    root = onto_cli.root(
        {
            "billing": repo("billing", page("plan/roadmap", "Plan", title="결제 로드맵"), page("component/api", "Component", title="결제 API")),
            "shop": repo("shop", page("plan/roadmap", "Plan", title="상점 로드맵")),
        }
    )

    from_billing = onto_cli.query(root, 'SELECT ?t WHERE { ?e onto:repository "billing" ; dcterms:title ?t } ORDER BY ?t')
    plans_from_shop = onto_cli.query(root, 'SELECT ?t WHERE { ?e a onto:Plan ; onto:repository "shop" ; dcterms:title ?t }')
    sources = onto_cli.query(root, "SELECT ?t ?repository WHERE { ?e a onto:Plan ; dcterms:title ?t ; onto:repository ?repository } ORDER BY ?t")

    assert from_billing == [["결제 API"], ["결제 로드맵"]]
    assert plans_from_shop == [["상점 로드맵"]]
    assert sources == [["결제 로드맵", "billing"], ["상점 로드맵", "shop"]]


def test_Project_엔티티도_어느_지식_저장소에서_왔는지_가려낼_수_있다(onto_cli):
    root = onto_cli.root({"billing": repo("billing", title="결제"), "shop": repo("shop", title="상점")})

    rows = onto_cli.query(root, "SELECT ?repository ?t WHERE { ?e a onto:Project ; onto:repository ?repository ; dcterms:title ?t } ORDER BY ?repository")

    assert rows == [["billing", "결제"], ["shop", "상점"]]


def test_교차_참조가_가리키는_엔티티의_출처도_질의로_가려낸다(onto_cli):
    root = onto_cli.root(
        two_repositories(page("component/gateway", "Component", title="게이트웨이", dependsOn=["shop:component/api"]))
    )

    rows = onto_cli.query(
        root,
        "SELECT ?from ?to WHERE { ?s onto:dependsOn ?o ; onto:repository ?from . ?o onto:repository ?to }",
    )

    assert rows == [["billing", "shop"]]


def test_frontmatter로_출처_저장소를_속일_수_없다(onto_cli):
    root = onto_cli.root(
        {"billing": repo("billing", page("plan/roadmap", "Plan", title="결제 로드맵", **{"onto:repository": "shop", "repository": "shop"}))}
    )

    rows = onto_cli.query(root, "SELECT ?repository WHERE { ?e a onto:Plan ; onto:repository ?repository }")

    assert rows == [["billing"]]
