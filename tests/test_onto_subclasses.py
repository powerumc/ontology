"""하위 클래스: 지식 저장소가 `ontology.yaml`의 `classes`에 자기 클래스를 선언하고, 그 엔티티가 상위 클래스로도 질의된다.

선언 형식:

```yaml
name: billing
classes:
  Invoice:                 # 이 지식 저장소의 네임스페이스에 생기는 클래스. 영어 대문자로 시작하고 영어와 숫자만 쓴다
    subClassOf: Component  # 공통 어휘의 클래스, 또는 같은 `classes`에 선언한 다른 클래스
```

페이지는 `class: Invoice`로 쓴다. 온톨로지 도구의 명령줄 진입점을 견본 페이지 디렉토리에 대고 실행한다(`onto_cli`).
"""

import pytest

from support.onto_cli import page, repo

BILLING = "projects/billing/docs/ontology"
INVOICE = "https://onto.invalid/class/billing/Invoice"


def file(identifier: str, name: str = "billing") -> str:
    return f"projects/{name}/docs/ontology/{identifier}.md"


def billing_with(classes, *pages):
    return {"billing": repo("billing", *pages, classes=classes)}


# --- 공통 어휘의 하위 클래스 -------------------------------------------------


def test_공통_어휘의_하위_클래스는_엔티티가_상위_클래스로도_질의된다(onto_cli):
    """`Term`은 SKOS의 `Concept`의 하위 클래스다."""
    root = onto_cli.root({"billing": repo("billing", page("term/invoice", "Term", title="청구서"))})

    rows = onto_cli.query(root, "SELECT ?e WHERE { ?e a skos:Concept }")

    assert rows == [[file("term/invoice")]]


# --- 지식 저장소가 선언한 하위 클래스 ----------------------------------------


def test_하위_클래스의_엔티티가_공통_어휘의_상위_클래스로_질의된다(onto_cli):
    root = onto_cli.root(
        billing_with(
            {"Invoice": {"subClassOf": "Component"}},
            page("component/invoice-service", "Invoice", title="청구서 서비스"),
            page("component/api", "Component", title="API"),
        )
    )

    components = onto_cli.query(root, "SELECT ?t WHERE { ?e a onto:Component ; dcterms:title ?t } ORDER BY ?t")
    invoices = onto_cli.query(root, f"SELECT ?t WHERE {{ ?e a <{INVOICE}> ; dcterms:title ?t }}")

    assert components == [["API"], ["청구서 서비스"]]
    assert invoices == [["청구서 서비스"]]


def test_선언한_클래스는_자기_네임스페이스에_생기고_어느_저장소의_것인지_가려낼_수_있다(onto_cli):
    root = onto_cli.root(billing_with({"Invoice": {"subClassOf": "Component"}}))

    rows = onto_cli.query(
        root,
        "SELECT (STR(?c) AS ?iri) ?label ?super ?repository WHERE { ?c a owl:Class ; rdfs:label ?label ; "
        "rdfs:subClassOf ?super ; onto:repository ?repository }",
    )

    assert rows == [[INVOICE, "Invoice", "https://onto.invalid/vocab#Component", "billing"]]


def test_클래스_선언은_공통_어휘의_네임스페이스에_들어가지_않는다(onto_cli):
    root = onto_cli.root(billing_with({"Invoice": {"subClassOf": "Component"}}))

    inside = onto_cli.query(
        root, "SELECT ?c WHERE { ?c a owl:Class . FILTER(STRSTARTS(STR(?c), STR(onto:)) && CONTAINS(STR(?c), 'Invoice')) }"
    )
    entity_space = onto_cli.query(root, "SELECT ?c WHERE { ?c a owl:Class . FILTER(STRSTARTS(STR(?c), 'https://onto.invalid/entity/')) }")

    assert inside == []
    assert entity_space == []


def test_하위_클래스의_하위_클래스도_모든_상위_클래스로_질의된다(onto_cli):
    root = onto_cli.root(
        billing_with(
            {"Invoice": {"subClassOf": "Component"}, "RecurringInvoice": {"subClassOf": "Invoice"}},
            page("component/subscription", "RecurringInvoice", title="구독 청구서"),
        )
    )

    as_component = onto_cli.query(root, "SELECT ?t WHERE { ?e a onto:Component ; dcterms:title ?t }")
    as_invoice = onto_cli.query(root, f"SELECT ?t WHERE {{ ?e a <{INVOICE}> ; dcterms:title ?t }}")

    assert as_component == as_invoice == [["구독 청구서"]]


def test_하위_클래스는_선언의_순서와_무관하게_상위_클래스를_찾는다(onto_cli):
    root = onto_cli.root(
        billing_with(
            {"RecurringInvoice": {"subClassOf": "Invoice"}, "Invoice": {"subClassOf": "Component"}},
            page("component/subscription", "RecurringInvoice", title="구독 청구서"),
        )
    )

    rows = onto_cli.query(root, "SELECT ?t WHERE { ?e a onto:Component ; dcterms:title ?t }")

    assert rows == [["구독 청구서"]]


def test_다른_클래스의_하위_클래스라고_선언한_엔티티는_그_클래스로_질의되지_않는다(onto_cli):
    root = onto_cli.root(
        billing_with(
            {"Invoice": {"subClassOf": "Component"}},
            page("component/invoice-service", "Invoice", title="청구서 서비스"),
        )
    )

    rows = onto_cli.query(root, "SELECT ?e WHERE { ?e a onto:Plan }")

    assert rows == []


def test_하위_클래스의_엔티티도_관계와_추론을_똑같이_쓴다(onto_cli):
    root = onto_cli.root(
        billing_with(
            {"Invoice": {"subClassOf": "Component"}},
            page("component/invoice-service", "Invoice", title="청구서 서비스", partOf=["component/platform"]),
            page("component/platform", "Component", title="플랫폼"),
        )
    )

    rows = onto_cli.query(root, "SELECT ?s ?o WHERE { ?s onto:hasPart ?o }")

    assert rows == [[file("component/platform"), file("component/invoice-service")]]


# --- 이름의 충돌 -------------------------------------------------------------


def test_두_지식_저장소가_같은_이름의_클래스를_선언해도_서로_다른_클래스다(onto_cli):
    root = onto_cli.root(
        {
            "billing": repo(
                "billing",
                page("component/invoice-service", "Invoice", title="결제 쪽 청구서"),
                classes={"Invoice": {"subClassOf": "Component"}},
            ),
            "shop": repo(
                "shop",
                page("plan/invoice-redesign", "Invoice", title="상점 쪽 청구서"),
                classes={"Invoice": {"subClassOf": "Plan"}},
            ),
        }
    )

    components = onto_cli.query(root, "SELECT ?t WHERE { ?e a onto:Component ; dcterms:title ?t }")
    plans = onto_cli.query(root, "SELECT ?t WHERE { ?e a onto:Plan ; dcterms:title ?t }")
    classes = onto_cli.query(root, "SELECT (STR(?c) AS ?iri) ?repository WHERE { ?c a owl:Class ; onto:repository ?repository } ORDER BY ?iri")

    assert components == [["결제 쪽 청구서"]]
    assert plans == [["상점 쪽 청구서"]]
    assert classes == [[INVOICE, "billing"], ["https://onto.invalid/class/shop/Invoice", "shop"]]


def test_클래스를_선언하지_않은_저장소가_다른_저장소의_클래스_이름을_쓸_수는_없다(onto_cli):
    """`class: Invoice`는 그 페이지가 있는 지식 저장소의 선언만 가리킨다. 다른 저장소의 선언은 이름만으로 끌어 쓰지 않는다."""
    root = onto_cli.root(
        {
            "billing": repo("billing", classes={"Invoice": {"subClassOf": "Component"}}),
            "shop": repo("shop", page("component/invoice-widget", "Invoice", title="상점의 청구서 위젯")),
        }
    )

    rows = onto_cli.query(root, "SELECT ?e WHERE { ?e a onto:Component }")

    assert rows == []


def test_하위_클래스를_가진_저장소를_교차_참조해도_클래스는_섞이지_않는다(onto_cli):
    root = onto_cli.root(
        {
            "billing": repo(
                "billing",
                page("component/invoice-service", "Invoice", title="청구서 서비스", dependsOn=["shop:component/api"]),
                classes={"Invoice": {"subClassOf": "Component"}},
            ),
            "shop": repo("shop", page("component/api", "Component", title="상점 API")),
        }
    )

    rows = onto_cli.query(root, f"SELECT ?t WHERE {{ ?s a <{INVOICE}> ; onto:dependsOn ?o . ?o dcterms:title ?t }}")
    shop_invoices = onto_cli.query(root, f'SELECT ?e WHERE {{ ?e a <{INVOICE}> ; onto:repository "shop" }}')

    assert rows == [["상점 API"]]
    assert shop_invoices == []


# --- 선언이 틀린 경우 --------------------------------------------------------

BAD_DECLARATIONS = {
    "목록이_아님": ["Invoice"],
    "선언이_목록이_아님": {"Invoice": "Component"},
    "subClassOf_없음": {"Invoice": {}},
    "subClassOf가_문자열이_아님": {"Invoice": {"subClassOf": ["Component"]}},
    "정의되지_않은_키": {"Invoice": {"subClassOf": "Component", "extends": "Plan"}},
    "없는_상위_클래스": {"Invoice": {"subClassOf": "Widget"}},
    "소문자로_시작한_이름": {"invoice": {"subClassOf": "Component"}},
    "공백이_든_이름": {"Bad Name": {"subClassOf": "Component"}},
    "한글_이름": {"청구서": {"subClassOf": "Component"}},
    "공통_어휘의_클래스_이름": {"Component": {"subClassOf": "Plan"}},
}


@pytest.mark.parametrize("command", ["build", "query"])
@pytest.mark.parametrize("classes", BAD_DECLARATIONS.values(), ids=BAD_DECLARATIONS.keys())
def test_클래스_선언이_틀리면_ontology_yaml_파일_이름과_함께_오류로_알린다(onto_cli, command, classes):
    root = onto_cli.root(billing_with(classes, page("component/api", "Component", title="API")))

    result = onto_cli.run(root, command, *(["SELECT ?e WHERE { ?e a onto:Component }"] if command == "query" else []))

    assert result.returncode != 0
    assert f"{BILLING}/ontology.yaml" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""
    assert not onto_cli.graph_file.exists()


def test_클래스_선언이_틀린_저장소가_여럿이면_모두_알린다(onto_cli):
    root = onto_cli.root(
        {
            "billing": repo("billing", classes={"Invoice": {"subClassOf": "Widget"}}),
            "shop": repo("shop", classes={"Cart": {"subClassOf": "Gadget"}}),
        }
    )

    result = onto_cli.run(root, "build")

    assert result.returncode != 0
    assert "projects/billing/docs/ontology/ontology.yaml" in result.stderr
    assert "projects/shop/docs/ontology/ontology.yaml" in result.stderr


def test_클래스를_선언하지_않으면_classes_키가_없어도_된다(onto_cli):
    root = onto_cli.root({"billing": repo("billing", page("component/api", "Component", title="API")), "shop": repo("shop", classes={})})

    result = onto_cli.run(root, "build")

    assert result.returncode == 0, result.stderr


def test_ontology_yaml의_classes는_Project_엔티티의_사실이_되지_않는다(onto_cli):
    root = onto_cli.root(billing_with({"Invoice": {"subClassOf": "Component"}}))

    predicates = onto_cli.query(
        root, "SELECT DISTINCT (STR(?p) AS ?predicate) WHERE { ?e a onto:Project ; ?p ?o } ORDER BY ?predicate"
    )

    assert [p for (p,) in predicates] == [
        "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
        "https://onto.invalid/vocab#repository",
    ]
