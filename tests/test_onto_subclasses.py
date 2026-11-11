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

from support.onto_cli import ONTOLOGY_DIR, page, repo

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
        "rdfs:subClassOf ?super ; onto:declaredIn ?repository }",
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
    classes = onto_cli.query(root, "SELECT (STR(?c) AS ?iri) ?repository WHERE { ?c a owl:Class ; onto:declaredIn ?repository } ORDER BY ?iri")

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
    "자기_자신이_상위_클래스": {"Invoice": {"subClassOf": "Invoice"}},
    "서로가_상위_클래스": {"A": {"subClassOf": "B"}, "B": {"subClassOf": "A"}},
    "순환_아래의_클래스": {"A": {"subClassOf": "B"}, "B": {"subClassOf": "A"}, "C": {"subClassOf": "A"}},
    "Project의_하위_클래스": {"MyProject": {"subClassOf": "Project"}},
    "Source의_하위_클래스": {"Reference": {"subClassOf": "Source"}},
    "Project의_하위_클래스의_하위_클래스": {"MyProject": {"subClassOf": "Project"}, "Deeper": {"subClassOf": "MyProject"}},
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


def test_순환하는_선언은_순환에_든_클래스와_그_아래의_클래스를_모두_알린다(onto_cli):
    classes = {
        "A": {"subClassOf": "B"},
        "B": {"subClassOf": "A"},
        "C": {"subClassOf": "A"},
        "Fine": {"subClassOf": "Component"},
    }
    root = onto_cli.root(billing_with(classes))

    result = onto_cli.run(root, "build")

    assert result.returncode != 0
    for name in ("A", "B", "C"):
        assert f"classes.{name}`" in result.stderr
    assert "classes.Fine`" not in result.stderr
    assert "순환" in result.stderr


@pytest.mark.parametrize("superclass", ["Component", "Plan", "Policy", "Term", "Decision", "Report"])
def test_페이지를_갖는_공통_클래스_여섯_개는_모두_상위_클래스가_될_수_있다(onto_cli, superclass):
    root = onto_cli.root(
        billing_with(
            {"Special": {"subClassOf": superclass}},
            page("component/special", "Special", title="특별한 것"),
        )
    )

    rows = onto_cli.query(root, f"SELECT ?e WHERE {{ ?e a onto:{superclass} ; dcterms:title ?t }}")

    assert rows == [[file("component/special")]]


@pytest.mark.parametrize("superclass", ["Project", "Source"])
def test_페이지가_없는_클래스의_하위_클래스는_선언할_수_없고_이유를_알린다(onto_cli, superclass):
    """`Project`는 `ontology.yaml`에서만 만들어지고, `Source`는 페이지를 갖지 않는다."""
    root = onto_cli.root(
        billing_with(
            {"Mine": {"subClassOf": superclass}},
            page("component/mine", "Mine", title="내 것"),
        )
    )

    result = onto_cli.run(root, "query", f"SELECT ?e WHERE {{ ?e a onto:{superclass} }}")

    assert result.returncode != 0
    assert f"{BILLING}/ontology.yaml" in result.stderr
    assert superclass in result.stderr
    assert result.stdout == ""


# --- 페이지의 class 값 -------------------------------------------------------

OTHER_REPOSITORY_CLASS = "https://onto.invalid/class/shop/Secret"
COMPONENT = "https://onto.invalid/vocab#Component"


@pytest.mark.parametrize(
    ("value", "would_resolve_to"),
    [
        (OTHER_REPOSITORY_CLASS, OTHER_REPOSITORY_CLASS),
        (INVOICE, INVOICE),
        (COMPONENT, COMPONENT),
        ("onto:Component", COMPONENT),
        # `:`가 없는 상대 IRI도 JSON-LD가 base 밖으로 풀 수 있다. 어느 것도 클래스를 가리키지 않아야 한다.
        ("/class/shop/Secret", OTHER_REPOSITORY_CLASS),
        ("//onto.invalid/class/shop/Secret", OTHER_REPOSITORY_CLASS),
        ("../class/shop/Secret", OTHER_REPOSITORY_CLASS),
        ("/vocab#Component", COMPONENT),
        ("../vocab#Component", COMPONENT),
    ],
    ids=[
        "다른_저장소의_클래스_IRI",
        "자기_저장소의_클래스_IRI",
        "공통_어휘의_클래스_IRI",
        "접두사_형식",
        "루트에서_시작하는_상대_경로",
        "스킴_없는_상대_IRI",
        "상위로_나가는_상대_경로",
        "루트에서_시작하는_어휘_경로",
        "상위로_나가는_어휘_경로",
    ],
)
def test_클래스는_이름으로만_쓴다_IRI로_쓴_값은_어느_클래스도_가리키지_않는다(onto_cli, value, would_resolve_to):
    """다른 저장소가 선언한 클래스의 IRI를 `class:`에 써서 이름만으로는 못 끌어 쓰는 제한을 우회할 수 없다.

    IRI로 풀릴 수 있는 값(전체 IRI, 접두사, 상대 경로)은 모두 풀리지 않은 클래스로 남는다.
    """
    root = onto_cli.root(
        {
            "billing": repo(
                "billing",
                page("component/sneaky", None, title="몰래 쓴 클래스", **{"class": value}),
                classes={"Invoice": {"subClassOf": "Component"}},
            ),
            "shop": repo("shop", classes={"Secret": {"subClassOf": "Component"}}),
        }
    )

    result = onto_cli.run(root, "build")
    typed = onto_cli.query(root, 'SELECT (STR(?c) AS ?class) WHERE { ?e dcterms:title "몰래 쓴 클래스" ; a ?c }')

    assert result.returncode == 0, result.stderr
    assert onto_cli.query(root, 'SELECT ?e WHERE { ?e a onto:Component ; dcterms:title "몰래 쓴 클래스" }') == []
    assert onto_cli.query(root, f'SELECT ?e WHERE {{ ?e a <{would_resolve_to}> ; dcterms:title "몰래 쓴 클래스" }}') == []
    assert typed and all(c.startswith("https://onto.invalid/unresolved/") for (c,) in typed)  # 풀리지 않은 클래스로 남아 알아볼 수 있다


@pytest.mark.parametrize("value", [5, True, 1.5], ids=["정수", "논리값", "실수"])
def test_문자열이_아닌_class_값도_어느_클래스도_가리키지_않는다(onto_cli, value):
    """클래스 자리에 리터럴이 들어가 그래프가 어긋나지 않는다. 풀리지 않은 클래스로 남는다."""
    root = onto_cli.root(
        {"billing": repo("billing", page("component/sneaky", None, title="몰래 쓴 클래스", **{"class": value}))}
    )

    result = onto_cli.run(root, "build")
    typed = onto_cli.query(root, 'SELECT (STR(?c) AS ?class) WHERE { ?e dcterms:title "몰래 쓴 클래스" ; a ?c }')
    literal_typed = onto_cli.query(root, "SELECT ?e WHERE { ?e a ?c . FILTER(isLiteral(?c)) }")

    assert result.returncode == 0, result.stderr
    assert typed and all(c.startswith("https://onto.invalid/unresolved/") for (c,) in typed)
    assert literal_typed == []


# --- 클래스 선언의 출처 ------------------------------------------------------


def test_엔티티의_출처를_묻는_질의에_클래스_선언은_섞이지_않는다(onto_cli):
    root = onto_cli.root(
        billing_with(
            {"Invoice": {"subClassOf": "Component"}},
            page("component/invoice-service", "Invoice", title="청구서 서비스"),
        )
    )

    entities = onto_cli.query(root, 'SELECT ?e WHERE { ?e onto:repository "billing" } ORDER BY ?e')
    declared = onto_cli.query(root, 'SELECT (STR(?c) AS ?iri) WHERE { ?c onto:declaredIn "billing" }')

    assert entities == [[file("component/invoice-service")], [f"{BILLING}/ontology.yaml"]]
    assert declared == [[INVOICE]]


# --- YAML이 문자열로 읽지 않는 클래스 이름 -----------------------------------


def raw_classes(*lines: str):
    """따옴표 없이 손으로 쓴 `ontology.yaml`. 테스트 받침의 JSON 키는 늘 문자열이라 YAML이 값으로 읽는 키를 만들지 못한다."""
    text = "name: billing\nclasses:\n" + "".join(f"  {line}\n" for line in lines)
    return {"billing": {f"{ONTOLOGY_DIR}/ontology.yaml": text}}


@pytest.mark.parametrize("name", ["No", "Yes", "On", "Off", "True", "Null", "123"])
def test_YAML이_문자열이_아닌_값으로_읽는_클래스_이름은_따옴표를_요구하며_알린다(onto_cli, name):
    root = onto_cli.root(raw_classes(f"{name}:", "  subClassOf: Component"))

    result = onto_cli.run(root, "build")

    assert result.returncode != 0
    assert f"{BILLING}/ontology.yaml" in result.stderr
    assert "문자열" in result.stderr and "따옴표" in result.stderr
    assert not onto_cli.graph_file.exists()


def test_따옴표로_감싼_클래스_이름은_그_이름_그대로_선언된다(onto_cli):
    root = onto_cli.root(raw_classes('"No":', "  subClassOf: Component"))

    result = onto_cli.run(root, "build")
    rows = onto_cli.query(root, "SELECT (STR(?c) AS ?iri) WHERE { ?c a owl:Class ; onto:declaredIn 'billing' }")

    assert result.returncode == 0, result.stderr
    assert rows == [["https://onto.invalid/class/billing/No"]]
