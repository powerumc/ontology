"""스크립트 검사(`validate`): 모든 지식 저장소를 합친 그래프와 페이지를 기계적으로 검사해 문제를 오류와 경고로 나눠 보고한다.

온톨로지 도구의 명령줄 진입점을 견본 페이지 디렉토리에 대고 실행한다(`onto_cli`).

보고 형식은 문제 하나에 한 줄이고, 탭으로 나눈 다섯 칸이다: 심각도(`오류`/`경고`), 지식 저장소, 페이지(루트 저장소 기준 파일 경로),
검사 항목(이름), 설명. 문제가 없으면 아무것도 출력하지 않는다. 오류가 하나라도 있으면 종료 코드 1, 경고만 있으면 0이다.
"""

import pytest

from support.onto_cli import ONTOLOGY_DIR, page, repo, snapshot

ERROR = "오류"
WARNING = "경고"


def file(identifier: str, name: str = "billing") -> str:
    return f"projects/{name}/{ONTOLOGY_DIR}/{identifier}.md"


def yaml_file(name: str = "billing") -> str:
    return f"projects/{name}/{ONTOLOGY_DIR}/ontology.yaml"


def validate(onto_cli, root):
    """`validate`를 실행해 `(결과, 문제 목록)`을 돌려준다. 문제는 `(심각도, 지식 저장소, 페이지, 검사 항목, 설명)`이다."""
    result = onto_cli.run(root, "validate")
    findings = [tuple(line.split("\t")) for line in result.stdout.splitlines()]
    assert all(len(finding) == 5 for finding in findings), result.stdout
    return result, findings


def found(onto_cli, root) -> list[tuple[str, str, str, str]]:
    """보고된 문제에서 설명을 뺀 `(심각도, 지식 저장소, 페이지, 검사 항목)` 목록."""
    return [finding[:4] for finding in validate(onto_cli, root)[1]]


def checks_of(onto_cli, root) -> list[str]:
    return [finding[3] for finding in validate(onto_cli, root)[1]]


def clean_repos() -> dict[str, dict[str, str]]:
    """문제가 없는 견본. 두 지식 저장소가 교차 참조로 이어져 있고, 모든 페이지가 관계를 하나 이상 가진다."""
    return {
        "billing": repo(
            "billing",
            page("component/gateway", "Component", title="결제 게이트웨이", partOf="project", dependsOn="shop:component/api"),
            page("plan/launch", "Plan", title="출시 계획", about="component/gateway"),
            title="결제",
        ),
        "shop": repo(
            "shop",
            page("component/api", "Component", title="상점 API", partOf="project"),
            title="상점",
        ),
    }


# --- 출력과 종료 코드 --------------------------------------------------------


def test_지식_저장소가_하나도_없어도_아무것도_보고하지_않고_0으로_끝난다(onto_cli):
    result = onto_cli.run(onto_cli.root({}), "validate")

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_문제가_없는_견본에서는_아무것도_보고하지_않고_0으로_끝난다(onto_cli):
    root = onto_cli.root(clean_repos())

    result = onto_cli.run(root, "validate")

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_문제를_하나씩_지식_저장소_페이지_검사_항목_심각도와_함께_보고한다(onto_cli):
    repos = clean_repos()
    repos["billing"].update(page("component/ledger", "Component", title="원장", partOf="project", owner="kim"))
    root = onto_cli.root(repos)

    result, findings = validate(onto_cli, root)

    assert [finding[:4] for finding in findings] == [(ERROR, "billing", file("component/ledger"), "undefined-key")]
    assert "owner" in findings[0][4]  # 설명이 어느 키가 문제인지 알려 준다


def test_오류가_하나라도_있으면_0이_아닌_종료_코드로_끝난다(onto_cli):
    repos = clean_repos()
    repos["billing"].update(page("component/ledger", "Component", title="원장", partOf="project", owner="kim"))

    result = onto_cli.run(onto_cli.root(repos), "validate")

    assert result.returncode == 1


def of_check(onto_cli, root, check: str) -> list[tuple[str, str, str, str]]:
    """보고된 문제 가운데 검사 항목 `check`의 것만."""
    return [finding for finding in found(onto_cli, root) if finding[3] == check]


def with_pages(*pages, **project):
    """`billing` 지식 저장소 하나. 페이지마다 관계를 가질 필요가 없는 검사에 쓴다(고아 페이지 경고가 섞여도 보는 항목만 고른다)."""
    return {"billing": repo("billing", *pages, **project)}


# --- 정의되지 않은 frontmatter 키 --------------------------------------------


@pytest.mark.parametrize("key", ["owner", "titel", "foo:bar", "@context", "Title"], ids=["모르는_키", "오타", "접두사_형식", "예약어", "대소문자"])
def test_페이지에_정의되지_않은_frontmatter_키가_있으면_오류로_잡는다(onto_cli, key):
    root = onto_cli.root(with_pages(page("component/api", "Component", title="API", **{key: "값"})))

    assert of_check(onto_cli, root, "undefined-key") == [(ERROR, "billing", file("component/api"), "undefined-key")]
    assert onto_cli.run(root, "validate").returncode == 1


def test_정의되지_않은_키는_값이_중첩되어_있어도_키_이름으로_알린다(onto_cli):
    root = onto_cli.root(with_pages(page("component/api", "Component", title="API", sources=[{"path": "docs/a.md"}])))

    result, findings = validate(onto_cli, root)

    assert [f[3] for f in findings if f[2] == file("component/api")].count("undefined-key") == 1
    assert "unreadable-file" not in [f[3] for f in findings]
    assert "sources" in next(f[4] for f in findings if f[3] == "undefined-key")


def test_정의된_키는_모두_통과한다(onto_cli):
    root = onto_cli.root(
        {
            "billing": repo(
                "billing",
                page(
                    "component/gateway",
                    "Component",
                    title="결제 게이트웨이",
                    description="결제를 처리한다",
                    date="2026-03-01",
                    aliases=["payment gateway", "PG"],
                    partOf=["project"],
                    dependsOn=["component/ledger"],
                ),
                page("component/ledger", "Component", title="원장"),
                page("policy/retention", "Policy", title="보존 정책", governs=["component/gateway"]),
                page("plan/v2", "Plan", title="2차 계획", about=["component/gateway"], supersedes=[]),
                page("report/v2", "Report", title="2차 결과", implements=["plan/v2"]),
                page("decision/db", "Decision", title="DB 선택", supersedes=[]),
            )
        }
    )

    assert of_check(onto_cli, root, "undefined-key") == []


# --- 역방향 관계 ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("reverse", "forward"),
    [("hasPart", "partOf"), ("implementedBy", "implements"), ("governedBy", "governs"), ("supersededBy", "supersedes")],
)
def test_역방향_관계를_페이지에_직접_쓰면_오류로_잡는다(onto_cli, reverse, forward):
    root = onto_cli.root(
        with_pages(
            page("component/api", "Component", title="API", **{reverse: "component/other"}),
            page("component/other", "Component", title="다른 것"),
        )
    )

    findings = [f for f in validate(onto_cli, root)[1] if f[2] == file("component/api") and f[0] == ERROR]

    assert [f[3] for f in findings] == ["reverse-relation"]  # 정의되지 않은 키로도 겹쳐 보고하지 않는다
    assert reverse in findings[0][4] and forward in findings[0][4]  # 어느 방향으로 써야 하는지 알려 준다


# --- 식별자 형식 ---------------------------------------------------------------


@pytest.mark.parametrize(
    "identifier",
    ["plan/My Plan", "plan/한글", "plan/Upper", "plan/under_score", "Plan/lower", "plan/dot.name", "plan/a b/c"],
    ids=["공백", "한글", "대문자", "밑줄", "대문자_디렉토리", "점", "공백_디렉토리"],
)
def test_식별자_형식에_어긋나는_페이지_경로를_오류로_잡는다(onto_cli, identifier):
    root = onto_cli.root(with_pages(page(identifier, "Plan", title="계획")))

    assert of_check(onto_cli, root, "invalid-identifier") == [(ERROR, "billing", file(identifier), "invalid-identifier")]
    assert onto_cli.run(root, "validate").returncode == 1


@pytest.mark.parametrize("identifier", ["plan/auth-redesign", "component/api-2", "plan/2026-01-launch", "plan/a/b/c", "term/x"])
def test_영어_소문자_숫자_하이픈으로_된_식별자는_통과한다(onto_cli, identifier):
    root = onto_cli.root(with_pages(page(identifier, "Plan", title="계획")))

    assert of_check(onto_cli, root, "invalid-identifier") == []


def test_식별자_형식에_어긋난_페이지도_그래프에서_빠지지_않고_다른_검사를_받는다(onto_cli):
    """공백이나 한글이 든 경로의 페이지가 조용히 사라지지 않는다."""
    root = onto_cli.root(with_pages(page("plan/내 계획", "Plan", title="계획", partOf="project", color="red")))

    checks = checks_of(onto_cli, root)

    assert "invalid-identifier" in checks
    assert "undefined-key" in checks


# --- name과 서브모듈 디렉토리 이름 ---------------------------------------------


def test_ontology_yaml의_name이_서브모듈_디렉토리_이름과_다르면_오류로_잡는다(onto_cli):
    root = onto_cli.root({"billing": repo("bill", page("component/api", "Component", title="API", partOf="project"))})

    assert of_check(onto_cli, root, "repository-name-mismatch") == [
        (ERROR, "billing", yaml_file("billing"), "repository-name-mismatch")
    ]
    assert onto_cli.run(root, "validate").returncode == 1


def test_name이_디렉토리_이름과_같으면_통과한다(onto_cli):
    root = onto_cli.root(clean_repos())

    assert of_check(onto_cli, root, "repository-name-mismatch") == []


# --- 깨진 참조와 등록되지 않은 지식 저장소 ---------------------------------------


def test_같은_지식_저장소_안의_깨진_참조를_오류로_잡는다(onto_cli):
    root = onto_cli.root(
        with_pages(
            page("component/gateway", "Component", title="게이트웨이", dependsOn="component/missing"),
            page("component/ledger", "Component", title="원장", partOf="project"),
        )
    )

    result, findings = validate(onto_cli, root)

    assert [f[:4] for f in findings] == [(ERROR, "billing", file("component/gateway"), "broken-reference")]
    assert "component/missing" in findings[0][4] and "dependsOn" in findings[0][4]
    assert result.returncode == 1


def test_교차_참조가_가리키는_엔티티가_없으면_오류로_잡는다(onto_cli):
    repos = clean_repos()
    repos["billing"].update(page("component/ledger", "Component", title="원장", dependsOn="shop:component/missing"))

    assert of_check(onto_cli, onto_cli.root(repos), "broken-reference") == [
        (ERROR, "billing", file("component/ledger"), "broken-reference")
    ]


def test_참조가_목록이면_깨진_것마다_보고한다(onto_cli):
    root = onto_cli.root(
        with_pages(
            page(
                "component/gateway",
                "Component",
                title="게이트웨이",
                dependsOn=["component/gone-1", "component/ledger", "component/gone-2"],
            ),
            page("component/ledger", "Component", title="원장"),
        )
    )

    messages = [f[4] for f in validate(onto_cli, root)[1] if f[3] == "broken-reference"]

    assert len(messages) == 2
    assert any("gone-1" in m for m in messages) and any("gone-2" in m for m in messages)


def test_존재하는_엔티티를_가리키는_참조는_같은_저장소와_교차_참조_모두_통과한다(onto_cli):
    """`project`는 `ontology.yaml`이 만드는 Project 엔티티의 식별자다."""
    repos = clean_repos()
    repos["billing"].update(
        page("component/ledger", "Component", title="원장", partOf=["project", "component/gateway", "shop:project"])
    )

    assert of_check(onto_cli, onto_cli.root(repos), "broken-reference") == []
    assert of_check(onto_cli, onto_cli.root(repos), "unregistered-repository") == []


def test_등록되지_않은_지식_저장소를_가리키는_교차_참조를_오류로_잡는다(onto_cli):
    """오류 없이 그 문자열 그대로의 IRI가 되는 참조다. 그래프가 아니라 frontmatter 원문에서 잡는다."""
    repos = clean_repos()
    repos["billing"].update(page("component/ledger", "Component", title="원장", dependsOn="biling:component/api"))

    result, findings = validate(onto_cli, onto_cli.root(repos))

    unregistered = [f for f in findings if f[3] == "unregistered-repository"]
    assert [f[:4] for f in unregistered] == [(ERROR, "billing", file("component/ledger"), "unregistered-repository")]
    assert "biling" in unregistered[0][4]
    assert "broken-reference" not in [f[3] for f in findings]  # 같은 원인을 깨진 참조로 겹쳐 보고하지 않는다
    assert result.returncode == 1


def test_읽을_수_없는_페이지를_가리켜도_깨진_참조로_겹쳐_보고하지_않는다(onto_cli):
    """그 페이지의 문제는 읽을 수 없는 파일로 한 번만 보고한다. 페이지는 있다."""
    repos = clean_repos()
    repos["billing"]["docs/ontology/component/broken.md"] = "frontmatter가 없다\n"
    repos["billing"].update(page("component/ledger", "Component", title="원장", dependsOn="component/broken"))

    findings = found(onto_cli, onto_cli.root(repos))

    assert (ERROR, "billing", file("component/broken"), "unreadable-file") in findings
    assert "broken-reference" not in [f[3] for f in findings]


# --- 읽을 수 없는 파일 ---------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["frontmatter가 없다\n", "---\nclass: [Component\n---\n", "---\nclass: Component\n", "---\n- 목록\n---\n"],
    ids=["frontmatter_없음", "YAML_문법_오류", "닫히지_않음", "키와_값이_아님"],
)
def test_읽을_수_없는_페이지는_오류로_보고하고_나머지_페이지의_검사를_계속한다(onto_cli, text):
    repos = clean_repos()
    repos["billing"][f"{ONTOLOGY_DIR}/component/bad.md"] = text
    repos["billing"].update(page("component/ledger", "Component", title="원장", partOf="project", owner="kim"))

    findings = found(onto_cli, onto_cli.root(repos))

    assert (ERROR, "billing", file("component/bad"), "unreadable-file") in findings
    assert (ERROR, "billing", file("component/ledger"), "undefined-key") in findings


def test_ontology_yaml을_읽을_수_없으면_오류로_보고한다(onto_cli):
    repos = clean_repos()
    repos["billing"][f"{ONTOLOGY_DIR}/ontology.yaml"] = "title: 이름이 없다\n"

    result, findings = validate(onto_cli, onto_cli.root(repos))

    assert (ERROR, "billing", yaml_file("billing"), "unreadable-file") in [f[:4] for f in findings]
    assert result.returncode == 1


@pytest.mark.parametrize(
    "fields",
    [{"title": {"ko": "원장"}}, {"partOf": 5}, {"partOf": [True]}, {"dependsOn": [{"a": 1}]}],
    ids=["중첩된_제목", "숫자_참조", "논리값_참조", "중첩된_참조"],
)
def test_값의_종류가_맞지_않아_읽을_수_없는_속성은_값의_종류_항목으로_보고한다(onto_cli, fields):
    repos = clean_repos()
    repos["billing"].update(page("component/ledger", "Component", **{"title": "원장", **fields}))

    findings = found(onto_cli, onto_cli.root(repos))

    assert (ERROR, "billing", file("component/ledger"), "invalid-value") in findings
    assert "unreadable-file" not in [f[3] for f in findings]


def test_ontology_yaml의_클래스_선언이_틀리면_오류로_보고한다(onto_cli):
    repos = clean_repos()
    repos["billing"] = repo(
        "billing",
        page("component/a", "Component", title="A", partOf="project"),
        classes={"Loop": {"subClassOf": "Loop"}},
    )

    findings = found(onto_cli, onto_cli.root(repos))

    assert (ERROR, "billing", yaml_file("billing"), "invalid-class-declaration") in findings


def test_project_식별자의_페이지는_오류로_보고한다(onto_cli):
    """`project`는 ontology.yaml이 만드는 Project 엔티티의 식별자다."""
    repos = clean_repos()
    repos["billing"].update(page("project", "Component", title="프로젝트 페이지"))

    findings = found(onto_cli, onto_cli.root(repos))

    assert (ERROR, "billing", file("project"), "invalid-identifier") in findings


# --- 온톨로지 층이 없는 지식 저장소 --------------------------------------------


def test_온톨로지_층이_없는_지식_저장소는_경고로_보고하고_종료_코드는_0이다(onto_cli):
    repos = {**clean_repos(), "empty": {"README.md": "온톨로지 층이 없다\n"}}

    result, findings = validate(onto_cli, onto_cli.root(repos))

    assert [f[:4] for f in findings] == [(WARNING, "empty", "projects/empty", "missing-ontology-layer")]
    assert result.returncode == 0


# --- 고아 페이지 ---------------------------------------------------------------


def test_관계가_들어오는_것도_나가는_것도_없는_페이지는_경고로_잡고_종료_코드는_0이다(onto_cli):
    repos = clean_repos()
    repos["billing"].update(page("term/idle", "Term", title="아무와도 이어지지 않은 용어"))

    result, findings = validate(onto_cli, onto_cli.root(repos))

    assert [f[:4] for f in findings] == [(WARNING, "billing", file("term/idle"), "orphan-page")]
    assert result.returncode == 0


def test_나가는_관계가_있으면_고아가_아니다(onto_cli):
    root = onto_cli.root(with_pages(page("term/invoice", "Term", title="청구서", about="project")))

    assert of_check(onto_cli, root, "orphan-page") == []


def test_들어오는_관계만_있어도_고아가_아니다(onto_cli):
    root = onto_cli.root(
        with_pages(
            page("component/a", "Component", title="A", dependsOn="component/b"),
            page("component/b", "Component", title="B"),
        )
    )

    assert of_check(onto_cli, root, "orphan-page") == []


def test_다른_지식_저장소에서_들어오는_교차_참조도_관계로_센다(onto_cli):
    repos = clean_repos()  # `billing`의 gateway가 `shop:component/api`에 의존한다. shop의 api는 partOf도 가진다
    repos["shop"].update(page("component/cache", "Component", title="캐시"))
    repos["billing"].update(page("component/ledger", "Component", title="원장", dependsOn="shop:component/cache"))

    findings = found(onto_cli, onto_cli.root(repos))

    assert (WARNING, "shop", file("component/cache", "shop"), "orphan-page") not in findings


def test_관계로_이어진_두_페이지는_고아가_아니고_이어지지_않은_페이지만_고아다(onto_cli):
    """`a`가 `b`의 일부라고 쓰면 둘 다 이어진 것이다. 어느 쪽에서도 이어지지 않은 `c`만 고아다."""
    root = onto_cli.root(
        with_pages(
            page("component/a", "Component", title="A", partOf="component/b"),
            page("component/b", "Component", title="B"),
            page("component/c", "Component", title="C"),
        )
    )

    assert of_check(onto_cli, root, "orphan-page") == [(WARNING, "billing", file("component/c"), "orphan-page")]


def test_페이지가_없는_지식_저장소의_project는_고아로_보고하지_않는다(onto_cli):
    """`Project` 엔티티는 페이지가 아니다."""
    root = onto_cli.root(with_pages(title="결제"))

    assert validate(onto_cli, root)[1] == []


# --- 이름이 같은 엔티티의 중복 -------------------------------------------------


def linked(*pages):
    """`(식별자, 클래스, 속성)`마다 `project`에 이어진 페이지. 고아 경고가 섞이지 않는다. 구성요소는 `partOf`로, 나머지는 `about`으로 잇는다."""
    return [
        page(identifier, cls, **{"partOf" if cls in ("Component", "Invoice", "Gateway") else "about": "project"}, **fields)
        for identifier, cls, fields in pages
    ]


def test_같은_지식_저장소_안에서_같은_클래스의_이름이_같은_엔티티는_오류로_잡는다(onto_cli):
    root = onto_cli.root(
        with_pages(*linked(("component/ledger-a", "Component", {"title": "원장"}), ("component/ledger-b", "Component", {"title": "원장"})))
    )

    result, findings = validate(onto_cli, root)

    # 두 페이지 모두에서 보인다. 어느 쪽을 열어도 중복을 알 수 있고, 설명이 상대 페이지를 가리킨다.
    assert [f[:4] for f in findings] == [
        (ERROR, "billing", file("component/ledger-a"), "duplicate-entity"),
        (ERROR, "billing", file("component/ledger-b"), "duplicate-entity"),
    ]
    assert file("component/ledger-b") in findings[0][4] and file("component/ledger-a") in findings[1][4]
    assert result.returncode == 1


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ({"title": "API Gateway"}, {"title": "api gateway"}),
        ({"title": "Ledger"}, {"title": "LEDGER"}),
        ({"title": "결제 게이트웨이"}, {"title": "결제게이트웨이"}),
        ({"title": "결제  게이트웨이 "}, {"title": "결제 게이트웨이"}),
        ({"title": "Payment Gateway"}, {"title": "다른 이름", "aliases": ["payment gateway"]}),
        ({"title": "하나", "aliases": ["PG", "pay"]}, {"title": "둘", "aliases": ["P G"]}),
    ],
    ids=["대소문자", "대문자", "공백_없음", "공백_수", "제목과_별칭", "별칭끼리"],
)
def test_제목과_별칭을_대소문자와_공백을_무시하고_비교한다(onto_cli, first, second):
    root = onto_cli.root(with_pages(*linked(("component/a", "Component", first), ("component/b", "Component", second))))

    assert [f[3] for f in found(onto_cli, root)] == ["duplicate-entity", "duplicate-entity"]


def test_이름이_다르면_중복이_아니다(onto_cli):
    root = onto_cli.root(
        with_pages(*linked(("component/a", "Component", {"title": "원장", "aliases": ["ledger"]}), ("component/b", "Component", {"title": "원장 조회"})))
    )

    assert validate(onto_cli, root)[1] == []


def test_이름이_같아도_클래스가_다르면_중복이_아니다(onto_cli):
    """같은 대상이 여러 페이지로 갈라지는 것을 잡는 검사다. 구성요소 `원장`과 용어 `원장`은 다른 엔티티다."""
    root = onto_cli.root(with_pages(*linked(("component/ledger", "Component", {"title": "원장"}), ("term/ledger", "Term", {"title": "원장"}))))

    assert validate(onto_cli, root)[1] == []


def test_서로_다른_지식_저장소_사이의_같은_이름은_경고로_잡고_종료_코드는_0이다(onto_cli):
    repos = {
        "billing": repo("billing", *linked(("component/ledger", "Component", {"title": "원장"}))),
        "shop": repo("shop", *linked(("component/ledger", "Component", {"title": "원장"}))),
    }

    result, findings = validate(onto_cli, onto_cli.root(repos))

    assert [f[:4] for f in findings] == [
        (WARNING, "billing", file("component/ledger"), "duplicate-entity-across-repositories"),
        (WARNING, "shop", file("component/ledger", "shop"), "duplicate-entity-across-repositories"),
    ]
    assert file("component/ledger", "shop") in findings[0][4]
    assert result.returncode == 0


def test_같은_저장소_안의_중복과_다른_저장소와의_중복은_항목을_나눠_보고한다(onto_cli):
    repos = {
        "billing": repo(
            "billing", *linked(("component/ledger-a", "Component", {"title": "원장"}), ("component/ledger-b", "Component", {"title": "원장"}))
        ),
        "shop": repo("shop", *linked(("component/ledger", "Component", {"title": "원장"}))),
    }

    findings = found(onto_cli, onto_cli.root(repos))

    assert findings == [
        (ERROR, "billing", file("component/ledger-a"), "duplicate-entity"),
        (WARNING, "billing", file("component/ledger-a"), "duplicate-entity-across-repositories"),
        (ERROR, "billing", file("component/ledger-b"), "duplicate-entity"),
        (WARNING, "billing", file("component/ledger-b"), "duplicate-entity-across-repositories"),
        (WARNING, "shop", file("component/ledger", "shop"), "duplicate-entity-across-repositories"),
    ]


def test_하위_클래스의_엔티티와_상위_클래스의_엔티티도_이름이_같으면_중복이다(onto_cli):
    """질의는 하위 클래스의 엔티티를 상위 클래스로 집계한다. 같은 대상이 갈라지는 것은 마찬가지다."""
    root = onto_cli.root(
        with_pages(
            *linked(("component/a-ledger", "Component", {"title": "원장"}), ("component/b-ledger", "Invoice", {"title": "원장"})),
            classes={"Invoice": {"subClassOf": "Component"}},
        )
    )

    assert found(onto_cli, root) == [
        (ERROR, "billing", file("component/a-ledger"), "duplicate-entity"),
        (ERROR, "billing", file("component/b-ledger"), "duplicate-entity"),
    ]


def test_저장소마다_따로_선언한_하위_클래스의_엔티티끼리도_같은_클래스에서_비교한다(onto_cli):
    """하위 클래스의 IRI는 저장소마다 따로다. 하위 클래스를 쓰는 저장소가 늘어도 저장소 간 중복 경고가 꺼지지 않는다."""
    gateway = {"Gateway": {"subClassOf": "Component"}}
    repos = {
        "billing": repo("billing", *linked(("component/gateway", "Gateway", {"title": "결제 게이트웨이"})), classes=gateway),
        "shop": repo("shop", *linked(("component/gateway", "Gateway", {"title": "결제 게이트웨이"})), classes=gateway),
        "pay": repo("pay", *linked(("component/gateway", "Component", {"title": "결제 게이트웨이"}))),
    }

    result, findings = validate(onto_cli, onto_cli.root(repos))

    assert [f[:4] for f in findings] == [
        (WARNING, "billing", file("component/gateway"), "duplicate-entity-across-repositories"),
        (WARNING, "pay", file("component/gateway", "pay"), "duplicate-entity-across-repositories"),
        (WARNING, "shop", file("component/gateway", "shop"), "duplicate-entity-across-repositories"),
    ]
    assert result.returncode == 0


def test_공통_조상이_다른_하위_클래스의_엔티티는_이름이_같아도_중복이_아니다(onto_cli):
    root = onto_cli.root(
        with_pages(
            *linked(("component/ledger", "Invoice", {"title": "원장"}), ("term/ledger", "Glossary", {"title": "원장"})),
            classes={"Invoice": {"subClassOf": "Component"}, "Glossary": {"subClassOf": "Term"}},
        )
    )

    assert validate(onto_cli, root)[1] == []


# --- 구조 제약: 필수 속성 -------------------------------------------------------

PAGE_CLASSES = {
    "Component": "component",
    "Plan": "plan",
    "Policy": "policy",
    "Term": "term",
    "Decision": "decision",
    "Report": "report",
}


def checks_on(onto_cli, root, identifier: str, name: str = "billing") -> list[str]:
    """한 페이지에 대해 보고된 오류와 경고의 검사 항목."""
    return [f[3] for f in validate(onto_cli, root)[1] if f[2] == file(identifier, name)]


def test_class가_없는_페이지는_필수_속성_누락으로_오류를_보고한다(onto_cli):
    root = onto_cli.root(with_pages(page("component/api", None, title="API", partOf="project")))

    result, findings = validate(onto_cli, root)

    assert [f[:4] for f in findings] == [(ERROR, "billing", file("component/api"), "missing-property")]
    assert "class" in findings[0][4]
    assert result.returncode == 1


@pytest.mark.parametrize("cls", PAGE_CLASSES)
def test_title이_없는_페이지는_필수_속성_누락으로_오류를_보고한다(onto_cli, cls):
    directory = PAGE_CLASSES[cls]
    root = onto_cli.root(with_pages(page(f"{directory}/x", cls, about="project") if cls != "Component" else page("component/x", cls, partOf="project")))

    findings = [f for f in validate(onto_cli, root)[1] if f[3] == "missing-property"]

    assert [f[:4] for f in findings] == [(ERROR, "billing", file(f"{directory}/x"), "missing-property")]
    assert "title" in findings[0][4]


def test_하위_클래스_페이지도_title이_필요하다(onto_cli):
    root = onto_cli.root(
        with_pages(page("component/inv", "Invoice", partOf="project"), classes={"Invoice": {"subClassOf": "Component"}})
    )

    assert of_check(onto_cli, root, "missing-property") == [(ERROR, "billing", file("component/inv"), "missing-property")]


def test_Project에는_title이_필요하지_않다(onto_cli):
    """`ontology.yaml`에 `name`만 있어도 최신화 직후 검사를 통과해야 한다."""
    root = onto_cli.root(with_pages(page("component/api", "Component", title="API", partOf="project")))

    assert validate(onto_cli, root)[1] == []


# --- 구조 제약: 값의 종류 -------------------------------------------------------


@pytest.mark.parametrize(
    "fields",
    [
        {"title": 123},
        {"title": True},
        {"title": ["하나", "둘"]},
        {"description": 5},
        {"description": ["하나", "둘"]},
        {"aliases": [5]},
        {"aliases": ["ok", 7]},
        {"date": "tomorrow"},
        {"date": "2026-02-30"},
        {"date": 2026},
    ],
    ids=["숫자_제목", "논리값_제목", "제목_둘", "숫자_설명", "설명_둘", "숫자_별칭", "숫자_별칭_섞임", "날짜_아님", "없는_날짜", "숫자_날짜"],
)
def test_값의_종류가_맞지_않는_속성은_오류로_잡는다(onto_cli, fields):
    root = onto_cli.root(with_pages(page("component/api", "Component", **{"title": "API", "partOf": "project", **fields})))

    result, findings = validate(onto_cli, root)

    invalid = [f for f in findings if f[3] == "invalid-value"]
    assert invalid and all(f[:3] == (ERROR, "billing", file("component/api")) for f in invalid)
    assert next(iter(fields)) in invalid[0][4]  # 어느 속성인지 알려 준다
    assert result.returncode == 1
    assert "Traceback" not in result.stderr  # 날짜가 아닌 값이 도구가 고장 난 것처럼 보이는 출력을 내지 않는다


def test_올바른_종류의_값은_통과한다(onto_cli):
    root = onto_cli.root(
        with_pages(
            page(
                "component/api",
                "Component",
                title="API",
                description="설명",
                date="2026-03-01",
                aliases=["에이피아이", "api"],
                partOf="project",
            )
        )
    )

    assert validate(onto_cli, root)[1] == []


# --- 구조 제약: 허용되는 클래스 --------------------------------------------------


@pytest.mark.parametrize("cls", ["Componnet", "component", "Widget", "Source", "Project", "owl:Class"])
def test_허용되지_않는_클래스는_오류로_잡는다(onto_cli, cls):
    root = onto_cli.root(with_pages(page("component/api", cls, title="API", partOf="project")))

    result, findings = validate(onto_cli, root)

    disallowed = [f for f in findings if f[3] == "disallowed-class"]
    assert [f[:3] for f in disallowed] == [(ERROR, "billing", file("component/api"))]
    assert cls in disallowed[0][4]  # 쓴 클래스를 알려 준다
    assert result.returncode == 1


@pytest.mark.parametrize("cls", PAGE_CLASSES)
def test_공통_어휘의_페이지_클래스는_통과한다(onto_cli, cls):
    directory = PAGE_CLASSES[cls]
    root = onto_cli.root(with_pages(page(f"{directory}/x", cls, title="X")))

    assert of_check(onto_cli, root, "disallowed-class") == []


def test_선언한_하위_클래스는_통과하고_하위_클래스의_하위_클래스도_통과한다(onto_cli):
    root = onto_cli.root(
        with_pages(
            page("component/a", "Invoice", title="A"),
            page("component/b", "RecurringInvoice", title="B"),
            classes={"Invoice": {"subClassOf": "Component"}, "RecurringInvoice": {"subClassOf": "Invoice"}},
        )
    )

    assert of_check(onto_cli, root, "disallowed-class") == []


def test_다른_저장소가_선언한_하위_클래스는_페이지의_클래스로_허용되지_않는다(onto_cli):
    repos = {
        "billing": repo("billing", page("component/a", "Secret", title="A", partOf="project")),
        "shop": repo("shop", classes={"Secret": {"subClassOf": "Component"}}),
    }

    assert of_check(onto_cli, onto_cli.root(repos), "disallowed-class") == [
        (ERROR, "billing", file("component/a"), "disallowed-class")
    ]


def test_ontology_yaml이_만드는_Project_엔티티는_허용되지_않는_클래스로_보고하지_않는다(onto_cli):
    root = onto_cli.root(with_pages(title="결제"))

    assert validate(onto_cli, root)[1] == []


def test_식별자가_project로_끝나는_페이지가_Project_클래스를_써도_허용되지_않는다(onto_cli):
    root = onto_cli.root(with_pages(page("component/project", "Project", title="프로젝트")))

    assert of_check(onto_cli, root, "disallowed-class") == [(ERROR, "billing", file("component/project"), "disallowed-class")]


def test_class가_없는_페이지가_관계를_써도_관계_도메인으로_겹쳐_보고하지_않는다(onto_cli):
    root = onto_cli.root(with_pages(page("component/api", None, title="API", partOf="project")))

    assert checks_of(onto_cli, root) == ["missing-property"]


# --- 구조 제약: 관계를 쓸 수 있는 클래스와 가리킬 수 있는 클래스 ----------------------

# 스펙의 관계 표: 관계 -> (쓸 수 있는 페이지의 클래스, 가리킬 수 있는 클래스). `Project`는 페이지가 아니라 가리킬 때만 나온다.
RELATIONS = {
    "partOf": ({"Component"}, {"Component", "Project"}),
    "dependsOn": ({"Component"}, {"Component", "Project"}),
    "implements": ({"Report"}, {"Plan", "Decision"}),
    "governs": ({"Policy"}, {"Project", "Component"}),
    "about": ({"Plan", "Decision", "Report", "Term"}, {"Project", "Component"}),
}
TARGETS = {"Project": "project", **{cls: f"{directory}/target" for cls, directory in PAGE_CLASSES.items()}}


def every_class_page(**fields):
    """페이지 클래스마다 페이지 하나(`<디렉토리>/target`)."""
    return [page(f"{directory}/target", cls, title=f"{cls} 대상", **fields) for cls, directory in PAGE_CLASSES.items()]


@pytest.mark.parametrize("relation", RELATIONS)
def test_관계를_쓸_수_없는_클래스의_페이지가_그_관계를_쓰면_오류로_잡는다(onto_cli, relation):
    domain, range_ = RELATIONS[relation]
    valid_target = TARGETS[sorted(range_)[0]]
    subjects = [
        page(f"{directory}/subject", cls, title=f"{cls} 주체", **{relation: valid_target}) for cls, directory in PAGE_CLASSES.items()
    ]
    root = onto_cli.root(with_pages(*every_class_page(), *subjects))

    flagged = {f[2] for f in validate(onto_cli, root)[1] if f[3] == "relation-domain"}

    assert flagged == {file(f"{directory}/subject") for cls, directory in PAGE_CLASSES.items() if cls not in domain}
    assert all(f[0] == ERROR for f in validate(onto_cli, root)[1] if f[3] == "relation-domain")
    assert [f for f in found(onto_cli, root) if f[3] == "relation-range"] == []


@pytest.mark.parametrize("relation", RELATIONS)
def test_관계가_가리킬_수_없는_클래스의_엔티티를_가리키면_오류로_잡는다(onto_cli, relation):
    domain, range_ = RELATIONS[relation]
    directory = PAGE_CLASSES[sorted(domain)[0]]
    subject = page(f"{directory}/subject", sorted(domain)[0], title="주체", **{relation: list(TARGETS.values())})
    root = onto_cli.root(with_pages(*every_class_page(), subject))

    result, findings = validate(onto_cli, root)

    invalid = [f for f in findings if f[3] == "relation-range"]
    expected_invalid = {name for cls, name in TARGETS.items() if cls not in range_}
    assert {f[2] for f in invalid} == {file(f"{directory}/subject")}
    assert all(f[0] == ERROR for f in invalid)
    assert len(invalid) == len(expected_invalid)
    for name in TARGETS.values():
        mentioned = any(f"billing:{name}`" in f[4] for f in invalid)
        assert mentioned == (name in expected_invalid), (name, [f[4] for f in invalid])
    assert result.returncode == 1


def test_관계를_쓰고_가리키는_클래스가_표와_같으면_통과한다(onto_cli):
    root = onto_cli.root(
        with_pages(
            page("component/a", "Component", title="A", partOf=["component/b", "project"], dependsOn=["component/b", "project"]),
            page("component/b", "Component", title="B"),
            page("plan/p", "Plan", title="P", about="component/a"),
            page("decision/d", "Decision", title="D", about="project"),
            page("term/t", "Term", title="T", about="component/a"),
            page("report/r", "Report", title="R", implements=["plan/p", "decision/d"], about="component/a"),
            page("policy/x", "Policy", title="X", governs=["project", "component/a"]),
        )
    )

    assert validate(onto_cli, root)[1] == []


def test_하위_클래스의_엔티티는_상위_클래스에_허용된_관계를_쓰고_상위_클래스를_가리키는_자리에_올_수_있다(onto_cli):
    root = onto_cli.root(
        with_pages(
            page("component/inv", "Invoice", title="청구", partOf="project", dependsOn="component/api"),
            page("component/api", "Component", title="API", partOf="component/inv"),
            page("policy/p", "Policy", title="P", governs="component/inv"),
            classes={"Invoice": {"subClassOf": "Component"}},
        )
    )

    assert validate(onto_cli, root)[1] == []


def test_가리키는_엔티티가_없으면_깨진_참조만_보고하고_클래스는_따지지_않는다(onto_cli):
    root = onto_cli.root(with_pages(page("component/a", "Component", title="A", partOf="component/gone")))

    assert checks_of(onto_cli, root) == ["broken-reference"]


def test_다른_지식_저장소의_엔티티도_클래스를_따진다(onto_cli):
    repos = clean_repos()
    repos["shop"].update(page("plan/rollout", "Plan", title="출시", about="project"))
    repos["billing"].update(page("component/ledger", "Component", title="원장", partOf="shop:plan/rollout"))

    assert of_check(onto_cli, onto_cli.root(repos), "relation-range") == [
        (ERROR, "billing", file("component/ledger"), "relation-range")
    ]


# supersedes는 어느 클래스의 페이지든 쓸 수 있고, 같은 클래스끼리만 이어진다.


@pytest.mark.parametrize("cls", PAGE_CLASSES)
def test_supersedes는_같은_클래스의_엔티티를_가리키면_통과한다(onto_cli, cls):
    directory = PAGE_CLASSES[cls]
    root = onto_cli.root(
        with_pages(
            page(f"{directory}/new", cls, title="새 것", supersedes=f"{directory}/old"),
            page(f"{directory}/old", cls, title="옛 것"),
        )
    )

    findings = found(onto_cli, root)

    assert [f for f in findings if f[3] in ("relation-domain", "relation-range")] == []


def test_supersedes가_다른_클래스의_엔티티를_가리키면_오류로_잡는다(onto_cli):
    root = onto_cli.root(
        with_pages(
            page("plan/new", "Plan", title="새 계획", supersedes=["plan/old", "decision/old"]),
            page("plan/old", "Plan", title="옛 계획"),
            page("decision/old", "Decision", title="옛 결정"),
        )
    )

    result, findings = validate(onto_cli, root)

    invalid = [f for f in findings if f[3] == "relation-range"]
    assert [f[:3] for f in invalid] == [(ERROR, "billing", file("plan/new"))]
    assert "decision/old" in invalid[0][4] and "plan/old" not in invalid[0][4]
    assert result.returncode == 1


def test_supersedes는_공통_클래스가_같으면_하위_클래스와_상위_클래스도_같은_클래스로_본다(onto_cli):
    """하위 클래스의 엔티티는 질의에서 상위 클래스로 집계된다. 새 것이 옛 것을 대체하는 데 걸림이 없다."""
    root = onto_cli.root(
        with_pages(
            page("component/new", "Invoice", title="새 것", supersedes=["component/old", "component/sibling"]),
            page("component/old", "Component", title="옛 것"),
            page("component/sibling", "Receipt", title="형제"),
            page("component/newest", "Component", title="가장 새 것", supersedes="component/new"),
            classes={"Invoice": {"subClassOf": "Component"}, "Receipt": {"subClassOf": "Component"}},
        )
    )

    assert of_check(onto_cli, root, "relation-range") == []


def test_supersedes는_공통_클래스가_다르면_하위_클래스끼리도_오류로_잡는다(onto_cli):
    root = onto_cli.root(
        with_pages(
            page("component/new", "Invoice", title="새 것", supersedes="term/old"),
            page("term/old", "Glossary", title="옛 것"),
            classes={"Invoice": {"subClassOf": "Component"}, "Glossary": {"subClassOf": "Term"}},
        )
    )

    assert of_check(onto_cli, root, "relation-range") == [(ERROR, "billing", file("component/new"), "relation-range")]



def test_Project의_속성도_값의_종류를_따진다(onto_cli):
    """Project 엔티티는 `ontology.yaml`에서 만들어진다. 보고하는 파일은 그 `ontology.yaml`이고, 규칙을 담은 파일의 문제라 `invalid-ontology-yaml`이다."""
    repos = clean_repos()
    repos["billing"] = repo("billing", *[page("component/a", "Component", title="A", partOf="project")], title=5)

    assert of_check(onto_cli, onto_cli.root(repos), "invalid-ontology-yaml") == [(ERROR, "billing", yaml_file("billing"), "invalid-ontology-yaml")]


# --- 보고의 순서와 요약 ---------------------------------------------------------


def test_문제는_지식_저장소_페이지_순으로_정렬해_보고하고_요약은_표준_오류로_알린다(onto_cli):
    repos = clean_repos()
    repos["shop"].update(page("component/z", "Component", title="Z", partOf="project", owner="kim"))
    repos["billing"].update(page("component/b", "Component", title="B", partOf="project", owner="kim"))
    repos["billing"].update(page("term/idle", "Term", title="한가한 용어"))
    repos["billing"].update(page("component/a", "Component", title="A", partOf="project", owner="kim"))

    result, findings = validate(onto_cli, onto_cli.root(repos))

    assert [(f[1], f[2], f[3]) for f in findings] == [
        ("billing", file("component/a"), "undefined-key"),
        ("billing", file("component/b"), "undefined-key"),
        ("billing", file("term/idle"), "orphan-page"),
        ("shop", file("component/z", "shop"), "undefined-key"),
    ]
    assert "오류 3개, 경고 1개" in result.stderr


# --- 이 명령이 하지 않는 일 ----------------------------------------------------


def contents(root):
    return {p.relative_to(root).as_posix(): (p.read_bytes() if p.is_file() else None) for p in root.rglob("*")}


def test_스크립트_검사는_어떤_파일도_고치거나_만들지_않는다(onto_cli):
    repos = clean_repos()
    repos["billing"].update(page("component/ledger", "Component", title="원장", partOf="project", owner="kim"))
    root = onto_cli.root(repos)
    before = contents(root)
    before_paths = snapshot(root)

    result = onto_cli.run(root, "validate")

    assert result.returncode == 1  # 문제가 있어도 고치지 않는다
    assert snapshot(root) == before_paths
    assert contents(root) == before
    assert not onto_cli.build_dir.exists()  # build의 산출물도 만들지 않는다


def test_실행할_때마다_현재_파일에서_다시_컴파일한다(onto_cli):
    """이전 `build`의 결과를 재사용하지 않는다."""
    root = onto_cli.root(clean_repos())
    onto_cli.build(root)
    onto_cli.graph_file.write_text("이전 build가 남긴 낡은 그래프가 아니다\n", encoding="utf-8")
    assert onto_cli.run(root, "validate").returncode == 0

    broken = root / "projects/billing" / ONTOLOGY_DIR / "component/gateway.md"
    broken.write_text(broken.read_text(encoding="utf-8").replace('"title"', '"titel"'), encoding="utf-8")
    after_break = checks_of(onto_cli, root)
    broken.write_text(broken.read_text(encoding="utf-8").replace('"titel"', '"title"'), encoding="utf-8")
    after_fix = checks_of(onto_cli, root)

    assert after_break == ["missing-property", "undefined-key"]
    assert after_fix == []


def test_검사는_루트의_구조_제약으로_돌고_지식_저장소의_사본이_덮어쓰지_못한다(onto_cli):
    """지식 저장소에 `.onto/vocab/`의 사본이 있어도 도구 자신의 공통 어휘와 구조 제약을 쓴다."""
    repos = clean_repos()
    repos["billing"].update(page("component/ledger", "Component", partOf="project"))  # title이 없다
    repos["billing"][".onto/vocab/shapes.ttl"] = ""
    repos["billing"][".onto/vocab/onto.ttl"] = ""
    repos["billing"][f"{ONTOLOGY_DIR}/shapes.ttl"] = ""

    findings = found(onto_cli, onto_cli.root(repos))

    assert findings == [(ERROR, "billing", file("component/ledger"), "missing-property")]


# --- S1-07 리뷰 지적 -----------------------------------------------------------


@pytest.mark.parametrize("title", ["", "   ", "\t"], ids=["빈_문자열", "공백", "탭"])
def test_비어_있는_title은_title이_없는_것과_같이_필수_속성_누락으로_잡는다(onto_cli, title):
    root = onto_cli.root(with_pages(page("component/api", "Component", title=title, partOf="project")))

    findings = [f for f in validate(onto_cli, root)[1] if f[3] == "missing-property"]

    assert [f[:3] for f in findings] == [(ERROR, "billing", file("component/api"))]
    assert "title" in findings[0][4]


def test_class_가_빈_값이면_허용되지_않는_클래스로_보고하고_설명이_빈_값이라고_알린다(onto_cli):
    root = onto_cli.root(with_pages(page("component/api", "", title="API", partOf="project")))

    findings = [f for f in validate(onto_cli, root)[1] if f[3] == "disallowed-class"]

    assert len(findings) == 1 and "빈 값" in findings[0][4]


def test_자기_자신만_가리키는_페이지는_고아다(onto_cli):
    """자기 자신은 다른 엔티티가 아니다."""
    root = onto_cli.root(
        with_pages(
            page("component/self", "Component", title="자기", partOf="component/self"),
            page("component/a", "Component", title="A", dependsOn="component/b"),
            page("component/b", "Component", title="B"),
        )
    )

    assert of_check(onto_cli, root, "orphan-page") == [(WARNING, "billing", file("component/self"), "orphan-page")]


def test_값의_종류가_틀린_속성이_있어도_같은_페이지의_다른_문제를_함께_보고한다(onto_cli):
    root = onto_cli.root(
        with_pages(
            page(
                "component/kind",
                "Component",
                title={"ko": "중첩"},
                owner="kim",
                hasPart="component/other",
                partOf="component/nope",
            ),
            page("component/other", "Component", title="다른 것", partOf="project"),
        )
    )

    findings = [f[3] for f in validate(onto_cli, root)[1] if f[2] == file("component/kind") and f[0] == ERROR]

    assert sorted(findings) == ["broken-reference", "invalid-value", "reverse-relation", "undefined-key"]


def test_따옴표_없는_없는_날짜는_따옴표를_친_없는_날짜와_같은_값의_종류_오류로_보고한다(onto_cli):
    """YAML이 날짜로 읽지 못해도 페이지 전체를 읽을 수 없게 만들지 않는다. 같은 페이지의 다른 문제도 함께 나온다."""
    unquoted = {"docs/ontology/report/r.md": "---\nclass: Report\ntitle: R\ndate: 2026-02-30\nowner: kim\n---\n"}
    quoted = {"docs/ontology/report/r.md": '---\nclass: Report\ntitle: R\ndate: "2026-02-30"\nowner: kim\n---\n'}

    results = []
    for text in (unquoted, quoted):
        repos = clean_repos()
        repos["billing"].update(text)
        findings = validate(onto_cli, onto_cli.root(repos))[1]
        results.append(sorted(f[3] for f in findings if f[2] == file("report/r") and f[3] != "orphan-page"))
        assert "unreadable-file" not in [f[3] for f in findings]

    # 값의 종류가 틀린 페이지는 그래프에 오르지 않아 고아 여부는 따지지 않는다. 나머지 문제는 두 쓰기 방식에서 같다.
    assert results[0] == results[1] == ["invalid-value", "undefined-key"]


# --- 클래스별 디렉토리 ---------------------------------------------------------


@pytest.mark.parametrize(
    ("identifier", "cls", "expected"),
    [
        ("plan/is-component", "Component", "component"),
        ("loose", "Component", "component"),
        ("report/auth", "Decision", "decision"),
        ("component/is-a-term", "Term", "term"),
    ],
    ids=["다른_클래스의_디렉토리", "최상위", "구현_결과_디렉토리의_결정", "구성요소_디렉토리의_용어"],
)
def test_페이지가_자기_클래스의_디렉토리에_있지_않으면_오류로_잡는다(onto_cli, identifier, cls, expected):
    root = onto_cli.root(with_pages(page(identifier, cls, title="페이지", about="project")))

    findings = [f for f in validate(onto_cli, root)[1] if f[3] == "misplaced-page"]

    assert [f[:3] for f in findings] == [(ERROR, "billing", file(identifier))]
    assert f"`{expected}/`" in findings[0][4]  # 어느 디렉토리에 둬야 하는지 알려 준다


def test_클래스가_둘_이상이어서_디렉토리_하나에_둘_수_없는_페이지는_오류로_잡는다(onto_cli):
    root = onto_cli.root(with_pages(page("component/both", ["Component", "Plan"], title="둘 다", partOf="project", about="project")))

    assert of_check(onto_cli, root, "misplaced-page") == [(ERROR, "billing", file("component/both"), "misplaced-page")]


@pytest.mark.parametrize("cls", PAGE_CLASSES)
def test_페이지가_자기_클래스의_디렉토리에_있으면_통과한다(onto_cli, cls):
    root = onto_cli.root(with_pages(page(f"{PAGE_CLASSES[cls]}/x", cls, title="X"), page(f"{PAGE_CLASSES[cls]}/deeper/y", cls, title="Y")))

    assert of_check(onto_cli, root, "misplaced-page") == []


def test_하위_클래스의_페이지는_공통_조상_클래스의_디렉토리에_둔다(onto_cli):
    root = onto_cli.root(
        with_pages(
            page("component/invoice", "Invoice", title="청구", partOf="project"),
            page("component/recurring", "RecurringInvoice", title="정기 청구", partOf="project"),
            page("plan/wrong-invoice", "Invoice", title="엉뚱한 곳", partOf="project"),
            classes={"Invoice": {"subClassOf": "Component"}, "RecurringInvoice": {"subClassOf": "Invoice"}},
        )
    )

    assert of_check(onto_cli, root, "misplaced-page") == [(ERROR, "billing", file("plan/wrong-invoice"), "misplaced-page")]


def test_클래스를_알_수_없는_페이지는_디렉토리_오류로_겹쳐_보고하지_않는다(onto_cli):
    root = onto_cli.root(with_pages(page("plan/widget", "Widget", title="위젯", about="project"), page("plan/none", None, title="없음", about="project")))

    assert of_check(onto_cli, root, "misplaced-page") == []


def test_reports가_implements로_쓴_참조가_디렉토리_규약을_따르면_깨지지_않는다(onto_cli):
    """디렉토리 규약이 지켜지면 식별자의 첫 조각이 클래스를 드러내 `decision/auth`가 `Decision`을 가리킨다."""
    root = onto_cli.root(
        with_pages(page("decision/auth", "Decision", title="인증", about="project"), page("report/auth", "Report", title="인증 결과", implements="decision/auth"))
    )

    assert validate(onto_cli, root)[1] == []


# --- 페이지로 읽히지 않는 파일 -------------------------------------------------


@pytest.mark.parametrize("name", ["upper.MD", "mixed.Md", "long.markdown"])
def test_확장자가_md가_아닌_페이지_파일을_조용히_건너뛰지_않고_오류로_알린다(onto_cli, name):
    repos = clean_repos()
    repos["billing"][f"{ONTOLOGY_DIR}/component/{name}"] = "---\nclass: Component\ntitle: 확장자가 틀렸다\n---\n"

    result, findings = validate(onto_cli, onto_cli.root(repos))

    assert [f[:4] for f in findings] == [(ERROR, "billing", f"projects/billing/{ONTOLOGY_DIR}/component/{name}", "misnamed-page")]
    assert result.returncode == 1


def test_페이지가_아닌_파일과_숨김_파일은_보고하지_않는다(onto_cli):
    repos = clean_repos()
    for name in ("notes.txt", "diagram.png", ".draft.MD", "component/.hidden.markdown", "other.yaml"):
        repos["billing"][f"{ONTOLOGY_DIR}/{name}"] = "내용\n"

    assert validate(onto_cli, onto_cli.root(repos))[1] == []


# --- 연쇄 오류 억제의 일관성 ---------------------------------------------------


def test_클래스가_없는_페이지의_관계는_도메인도_범위도_따지지_않는다(onto_cli):
    root = onto_cli.root(
        with_pages(
            page("component/none", None, title="클래스 없음", partOf="project", supersedes="component/old"),
            page("component/old", "Component", title="옛 것", partOf="project"),
        )
    )

    assert [f[3] for f in validate(onto_cli, root)[1]] == ["missing-property"]


def test_클래스가_허용되지_않는_페이지의_관계도_도메인과_범위를_따지지_않는다(onto_cli):
    root = onto_cli.root(
        with_pages(
            page("component/widget", "Widget", title="위젯", partOf="project", supersedes="component/old"),
            page("component/old", "Component", title="옛 것", partOf="project"),
            page("plan/p", "Plan", title="계획", about="component/widget"),
        )
    )

    assert [f[3] for f in validate(onto_cli, root)[1]] == ["disallowed-class"]


def test_클래스가_없는_엔티티를_가리키는_관계는_범위를_따지지_않는다(onto_cli):
    root = onto_cli.root(
        with_pages(page("component/a", "Component", title="A", partOf="component/none"), page("component/none", None, title="클래스 없음"))
    )

    assert [f[3] for f in validate(onto_cli, root)[1]] == ["missing-property"]


@pytest.mark.parametrize("cls", [None, "Widget"], ids=["클래스_없음", "허용되지_않는_클래스"])
def test_클래스를_알_수_없는_페이지도_제목이_필요하다(onto_cli, cls):
    """클래스를 고친 뒤에야 제목 누락이 새로 드러나지 않는다."""
    root = onto_cli.root(with_pages(page("component/x", cls, about="project")))

    assert sorted(f[3] for f in validate(onto_cli, root)[1] if f[0] == ERROR) == sorted(
        ["missing-property", "missing-property"] if cls is None else ["disallowed-class", "missing-property"]
    )


def test_ontology_yaml을_읽을_수_없는_저장소를_가리키는_교차_참조는_깨진_참조로_보고하지_않는다(onto_cli):
    """그 저장소의 엔티티를 알 수 없다. 읽을 수 없는 ontology.yaml이 한 번만 보고된다."""
    repos = clean_repos()
    repos["shop"][f"{ONTOLOGY_DIR}/ontology.yaml"] = "title: 이름이 없다\n"
    repos["billing"].update(page("component/ledger", "Component", title="원장", partOf="project", dependsOn="shop:component/api"))

    findings = found(onto_cli, onto_cli.root(repos))

    assert (ERROR, "shop", yaml_file("shop"), "unreadable-file") in findings
    assert [f for f in findings if f[3] in ("broken-reference", "unregistered-repository")] == []


def test_온톨로지_층이_없는_서브모듈을_가리키는_교차_참조는_등록되지_않았다고_하지_않고_층이_없다고_알린다(onto_cli):
    repos = {**clean_repos(), "empty": {"README.md": "온톨로지 층이 없다\n"}}
    repos["billing"].update(page("component/ledger", "Component", title="원장", partOf="project", dependsOn="empty:component/api"))

    findings = [f for f in validate(onto_cli, onto_cli.root(repos))[1] if f[2] == file("component/ledger")]

    assert [f[3] for f in findings] == ["broken-reference"]
    assert "온톨로지 층이 없다" in findings[0][4]


# --- S1-07 재리뷰 지적 -----------------------------------------------------------


def test_클래스가_둘인_페이지의_디렉토리_오류_설명은_실행마다_같고_디렉토리_순서로_적는다(onto_cli):
    """문자열 해시는 프로세스마다 달라지므로, 집합을 도는 순서로 적으면 같은 견본의 출력이 실행마다 달라진다."""
    root = onto_cli.root(with_pages(page("component/both", ["Plan", "Component"], title="둘 다", partOf="project", about="project")))

    outputs = {
        seed: onto_cli.run(root, "validate", env={**onto_cli.env, "PYTHONHASHSEED": str(seed)}).stdout for seed in range(1, 7)
    }

    assert len(set(outputs.values())) == 1, outputs
    message = next(f[4] for f in validate(onto_cli, root)[1] if f[3] == "misplaced-page")
    assert message.index("`Component`(`component/`)") < message.index("`Plan`(`plan/`)")


def test_관계의_범위는_주어의_클래스를_알_수_없어도_가리키는_쪽의_클래스만으로_따진다(onto_cli):
    """주어의 클래스 문제를 고친 뒤에야 범위 오류가 새로 드러나지 않는다. 범위는 주어의 클래스와 무관하다."""
    root = onto_cli.root(
        with_pages(page("component/widget", "Widget", title="위젯", partOf="plan/target"), page("plan/target", "Plan", title="대상", about="project"))
    )

    assert sorted(f[3] for f in validate(onto_cli, root)[1]) == ["disallowed-class", "relation-range"]


def test_supersedes의_범위는_주어의_클래스를_알_수_없으면_따지지_않는다(onto_cli):
    """supersedes만 주어의 클래스를 보고 범위를 정한다. 주어의 클래스를 알 수 없으면 그 문제가 먼저 보고된다."""
    root = onto_cli.root(
        with_pages(page("component/widget", "Widget", title="위젯", supersedes="component/old"), page("component/old", "Component", title="옛 것", partOf="project"))
    )

    assert [f[3] for f in validate(onto_cli, root)[1]] == ["disallowed-class"]


@pytest.mark.parametrize("directory", ["Plan", "PLAN"])
def test_대문자_디렉토리의_페이지는_같은_원인을_식별자_형식_하나로만_보고한다(onto_cli, directory):
    root = onto_cli.root(with_pages(page(f"{directory}/lower", "Plan", title="계획", about="project")))

    assert [f[3] for f in validate(onto_cli, root)[1]] == ["invalid-identifier"]


def test_대문자가_아닌_이유로_디렉토리가_다르면_식별자_형식과_별개로_디렉토리_오류도_보고한다(onto_cli):
    root = onto_cli.root(with_pages(page("Report/lower", "Plan", title="계획", about="project")))

    assert sorted(f[3] for f in validate(onto_cli, root)[1]) == ["invalid-identifier", "misplaced-page"]
