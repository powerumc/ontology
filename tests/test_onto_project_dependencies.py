"""프로젝트 사이의 의존: `Project`는 `ontology.yaml`의 `dependsOn`으로 다른 `Project`와 `Component`에 의존한다고 적는다.

온톨로지 도구의 명령줄 진입점을 견본 페이지 디렉토리에 대고 실행한다(`onto_cli`).

`Project`는 페이지가 없는 엔티티라 관계를 `ontology.yaml`에 적는다. `Project`가 쓰는 관계는 `dependsOn` 하나다(스펙의 관계 표).
값의 형식과 검사(깨진 참조, 등록되지 않은 저장소, 경로 참조, 공유 범위, 구조 제약)는 페이지의 관계와 같고, 문제는 `ontology.yaml`의 것으로 보고된다.
"""

import pytest

from support.onto_cli import ONTOLOGY_DIR, REPOSITORY, page, repo

ERROR = "오류"
WARNING = "경고"


def yaml_file(name: str) -> str:
    return f"projects/{name}/{ONTOLOGY_DIR}/ontology.yaml"


def validate(onto_cli, root, **options):
    """`validate`를 실행해 `(결과, 문제 목록)`을 돌려준다. 문제는 `(심각도, 지식 저장소, 파일, 검사 항목, 설명)`이다."""
    result = onto_cli.run(root, "validate", **options)
    findings = [tuple(line.split("\t")) for line in result.stdout.splitlines()]
    assert all(len(finding) == 5 for finding in findings), result.stdout
    return result, findings


def of_check(findings, check: str) -> list[tuple[str, str, str, str]]:
    return [finding[:4] for finding in findings if finding[3] == check]


def two_repositories(**billing_project) -> dict[str, dict[str, str]]:
    """`billing`(이 테스트가 `ontology.yaml`의 값을 정한다)과 `shop`. 두 저장소 모두 페이지가 관계로 이어져 있어 고아 경고가 없다."""
    return {
        "billing": repo("billing", page("component/gateway", "Component", title="결제 게이트웨이", partOf="project"), **billing_project),
        "shop": repo("shop", page("component/api", "Component", title="상점 API", partOf="project"), title="상점"),
    }


# --- 컴파일 ---------------------------------------------------------------------


def test_ontology_yaml의_dependsOn은_Project가_다른_저장소의_Project에_의존한다는_사실이_된다(onto_cli):
    root = onto_cli.root(two_repositories(dependsOn="shop:project"))

    rows = onto_cli.query(root, "SELECT ?s ?o WHERE { ?s onto:dependsOn ?o }")

    assert rows == [[yaml_file("billing"), yaml_file("shop")]]


def test_ontology_yaml의_dependsOn은_Component도_가리키고_목록으로_여럿을_쓸_수_있다(onto_cli):
    root = onto_cli.root(two_repositories(dependsOn=["shop:component/api", "shop:project", "component/gateway"]))

    rows = onto_cli.query(root, "SELECT ?o WHERE { ?s a onto:Project ; onto:dependsOn ?o } ORDER BY ?o")

    assert rows == [
        [f"projects/billing/{ONTOLOGY_DIR}/component/gateway.md"],
        [f"projects/shop/{ONTOLOGY_DIR}/component/api.md"],
        [yaml_file("shop")],
    ]


def test_Project의_dependsOn은_추이_관계도_역관계도_아니다(onto_cli):
    """직접 의존만 적는다. 간접 의존은 질의에서 경로로 구한다."""
    repos = {
        "billing": repo("billing", dependsOn="shop:project"),
        "shop": repo("shop", dependsOn="mall:project"),
        "mall": repo("mall"),
    }
    root = onto_cli.root(repos)

    direct = onto_cli.query(root, "SELECT ?s ?o WHERE { ?s onto:dependsOn ?o } ORDER BY ?s")
    billing_to_mall = onto_cli.run(root, "query", 'ASK { ?s onto:repository "billing" ; onto:dependsOn ?o . ?o onto:repository "mall" }')

    assert direct == [[yaml_file("billing"), yaml_file("shop")], [yaml_file("shop"), yaml_file("mall")]]
    assert billing_to_mall.stdout.strip() == "false"


def test_dependsOn을_적은_Project의_다른_사실은_그대로이고_제목이_없어도_이름으로_채우지_않는다(onto_cli):
    root = onto_cli.root(two_repositories(description="결제", dependsOn="shop:project"))

    rows = onto_cli.query(
        root, 'SELECT ?d ?t WHERE { ?e a onto:Project ; onto:repository "billing" ; dcterms:description ?d . OPTIONAL { ?e dcterms:title ?t } }'
    )

    assert rows == [["결제", ""]]


def test_ontology_yaml의_dependsOn이_없으면_Project는_관계를_갖지_않는다(onto_cli):
    root = onto_cli.root(two_repositories())

    assert onto_cli.query(root, "SELECT ?s ?o WHERE { ?s a onto:Project ; onto:dependsOn ?o }") == []


# --- 스크립트 검사: 정상 --------------------------------------------------------------


def test_ontology_yaml의_dependsOn은_정의되지_않은_키로_보고하지_않고_문제가_없으면_통과한다(onto_cli):
    root = onto_cli.root(two_repositories(dependsOn=["shop:project", "shop:component/api"]))

    result, findings = validate(onto_cli, root)

    assert findings == []
    assert result.returncode == 0


def test_Project가_의존하는_Component는_다른_엔티티와의_관계가_있어_고아_페이지가_아니다(onto_cli):
    repos = {
        "billing": repo("billing", dependsOn="shop:component/api"),
        "shop": repo("shop", page("component/api", "Component", title="상점 API")),
    }

    findings = validate(onto_cli, onto_cli.root(repos))[1]

    assert of_check(findings, "orphan-page") == []


def test_Project는_dependsOn_말고_다른_관계를_ontology_yaml에_쓸_수_없다(onto_cli):
    """스펙의 관계 표에서 `Project`가 쓰는 관계는 `dependsOn` 하나다. 다른 관계의 키는 정의되지 않은 키다."""
    for key in ("partOf", "about", "hasPart"):
        root = onto_cli.root(two_repositories(**{key: "shop:project"}))

        findings = validate(onto_cli, root)[1]

        assert of_check(findings, "invalid-ontology-yaml") == [(ERROR, "billing", yaml_file("billing"), "invalid-ontology-yaml")], key
        assert key in next(f[4] for f in findings if f[3] == "invalid-ontology-yaml"), key


# --- 스크립트 검사: 참조 --------------------------------------------------------------


def test_dependsOn이_가리키는_엔티티가_없으면_ontology_yaml의_깨진_참조로_보고한다(onto_cli):
    root = onto_cli.root(two_repositories(dependsOn=["shop:component/missing", "component/gone", "shop:project"]))

    findings = validate(onto_cli, root)[1]

    broken = [f for f in findings if f[3] == "broken-reference"]
    assert [f[:4] for f in broken] == [(ERROR, "billing", yaml_file("billing"), "broken-reference")] * 2
    assert any("shop:component/missing" in f[4] and "dependsOn" in f[4] for f in broken)
    assert any("component/gone" in f[4] for f in broken)


def test_dependsOn이_등록되지_않은_저장소를_가리키면_등록되지_않은_저장소로_보고한다(onto_cli):
    root = onto_cli.root(two_repositories(dependsOn="nowhere:project"))

    findings = validate(onto_cli, root)[1]

    assert of_check(findings, "unregistered-repository") == [(ERROR, "billing", yaml_file("billing"), "unregistered-repository")]
    assert "nowhere" in next(f[4] for f in findings if f[3] == "unregistered-repository")


@pytest.mark.parametrize(
    "value", ["docs/ontology/component/api", "projects/shop/docs/ontology/component/api.md", "https://example.com/shop", "../shop/docs/ontology/ontology.yaml"]
)
def test_dependsOn의_값이_파일_경로나_주소이면_경로_참조로_보고한다(onto_cli, value):
    root = onto_cli.root(two_repositories(dependsOn=value))

    findings = validate(onto_cli, root)[1]

    assert of_check(findings, "path-reference") == [(ERROR, "billing", yaml_file("billing"), "path-reference")]
    assert of_check(findings, "broken-reference") == []


def test_dependsOn이_Project나_Component가_아닌_엔티티를_가리키면_구조_제약_위반으로_ontology_yaml에_보고한다(onto_cli):
    repos = two_repositories(dependsOn="shop:plan/launch")
    repos["shop"].update(page("plan/launch", "Plan", title="출시", about="project"))

    findings = validate(onto_cli, onto_cli.root(repos))[1]

    assert of_check(findings, "relation-range") == [(ERROR, "billing", yaml_file("billing"), "relation-range")]


@pytest.mark.parametrize("value", [{"id": "shop:project"}, [{"a": 1}], 5, [True]], ids=["키_값", "중첩된_목록", "숫자", "논리값"])
def test_dependsOn의_값이_식별자_문자열이_아니면_ontology_yaml의_값_오류로_보고한다(onto_cli, value):
    root = onto_cli.root(two_repositories(dependsOn=value))

    findings = validate(onto_cli, root)[1]

    assert of_check(findings, "invalid-ontology-yaml") == [(ERROR, "billing", yaml_file("billing"), "invalid-ontology-yaml")]
    assert "dependsOn" in next(f[4] for f in findings if f[3] == "invalid-ontology-yaml")


def test_dependsOn의_값이_비어_있으면_적지_않은_것과_같다(onto_cli):
    root = onto_cli.root(two_repositories(dependsOn=None))

    result, findings = validate(onto_cli, root)

    assert findings == []
    assert result.returncode == 0


# --- 스크립트 검사: 공유 범위 ---------------------------------------------------------


def test_공유_범위가_더_좁은_저장소의_Project에_의존하면_공유_범위_위반으로_보고한다(onto_cli):
    repos = {
        "team": repo("team", scope="team", dependsOn="secret:project"),
        "secret": repo("secret", scope="private"),
    }

    findings = validate(onto_cli, onto_cli.root(repos))[1]

    assert of_check(findings, "scope-violation") == [(ERROR, "team", yaml_file("team"), "scope-violation")]
    assert "secret" in next(f[4] for f in findings if f[3] == "scope-violation")


def test_가리키는_엔티티가_없어도_더_좁은_저장소의_이름이_드러나면_공유_범위_위반이다(onto_cli):
    repos = {
        "team": repo("team", scope="team", dependsOn="secret:component/nothing"),
        "secret": repo("secret", scope="private"),
    }

    findings = validate(onto_cli, onto_cli.root(repos))[1]

    assert of_check(findings, "scope-violation") == [(ERROR, "team", yaml_file("team"), "scope-violation")]


def test_더_넓은_저장소와_같은_범위의_저장소에_의존하는_것은_통과한다(onto_cli):
    repos = {
        "notes": repo("notes", scope="private", dependsOn=["open:project", "mate:project"]),
        "open": repo("open", scope="public"),
        "mate": repo("mate", scope="private"),
    }

    findings = validate(onto_cli, onto_cli.root(repos))[1]

    assert findings == []


def test_중첩된_dependsOn_값에_적힌_더_좁은_저장소의_이름도_공유_범위_위반으로_보고한다(onto_cli):
    repos = {
        "team": repo("team", scope="team", dependsOn={"id": "secret:project"}),
        "secret": repo("secret", scope="private"),
    }

    findings = validate(onto_cli, onto_cli.root(repos))[1]

    assert of_check(findings, "scope-violation") == [(ERROR, "team", yaml_file("team"), "scope-violation")]


# --- 지식 저장소 안에서 -----------------------------------------------------------------


def test_지식_저장소_안에서는_같은_저장소의_깨진_참조를_보고하고_다른_저장소를_가리키는_값은_건너뛴다(onto_cli):
    billing = repo(
        "billing", page("component/gateway", "Component", title="게이트웨이", partOf="project"), dependsOn=["component/gone", "shop:project"]
    )
    inside = onto_cli.repository("billing", billing)

    result = onto_cli.run(inside, "validate", within=REPOSITORY)

    findings = [tuple(line.split("\t")) for line in result.stdout.splitlines()]
    assert [(f[0], f[2], f[3]) for f in findings] == [(ERROR, f"{ONTOLOGY_DIR}/ontology.yaml", "broken-reference")]
    assert "component/gone" in findings[0][4]
