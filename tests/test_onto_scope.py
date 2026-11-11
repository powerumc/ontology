"""공유 범위 검사: 지식 저장소가 공유 범위(`ontology.yaml`의 `scope`)를 지키는지 스크립트 검사(`validate`)가 잡는다.

온톨로지 도구의 명령줄 진입점을 견본 페이지 디렉토리에 대고 실행한다(`onto_cli`).

검사 항목은 넷이고 모두 루트 전용이다(지식 저장소의 `rules`가 끄거나 심각도를 바꾸려 하면 `invalid-rules` 오류다).

- `invalid-scope`: 공유 범위의 값이 `private`, `team`, `team:<팀 이름>`, `public` 중 하나가 아니다.
- `scope-violation`: 교차 참조가 공유 범위가 더 좁은 지식 저장소나 다른 팀의 지식 저장소를 가리킨다.
- `path-reference`: 관계의 값이 식별자나 교차 참조가 아니라 파일 경로다.
- `outside-link`: 페이지 본문의 링크가 지식 저장소 밖의 파일을 가리킨다.

공유 범위가 정해지지 않은 지식 저장소는 가장 좁은 `private`으로 본다.
"""

import json
import re

import pytest

from support.onto_cli import ONTOLOGY_DIR, page, repo, snapshot

ERROR = "오류"
WARNING = "경고"

SCOPE_CHECKS = ("invalid-scope", "scope-violation", "path-reference", "outside-link")


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


# --- 공유 범위의 값 ------------------------------------------------------------


def lone(scope: object = ...) -> dict[str, dict[str, str]]:
    """`billing` 지식 저장소 하나. `scope`를 주지 않으면 `ontology.yaml`에 공유 범위를 적지 않는다."""
    project = {} if scope is ... else {"scope": scope}
    return {"billing": repo("billing", page("component/api", "Component", title="API", partOf="project"), **project)}


@pytest.mark.parametrize("scope", ["private", "team", "team:payments", "team:결제팀", "public"])
def test_공유_범위가_private_team_team_팀_이름_public_중_하나이면_통과한다(onto_cli, scope):
    result, findings = validate(onto_cli, onto_cli.root(lone(scope)))

    assert (result.returncode, findings) == (0, [])


def test_공유_범위를_적지_않은_지식_저장소는_문제로_보지_않는다(onto_cli):
    result, findings = validate(onto_cli, onto_cli.root(lone()))

    assert (result.returncode, findings) == (0, [])


@pytest.mark.parametrize(
    "scope",
    [
        "internal",
        "Public",
        "PRIVATE",
        "teams",
        "team:",
        "team:a:b",
        "team:two words",
        " public",
        "public ",
        "",
        None,
        5,
        True,
        ["public"],
        {"team": "payments"},
    ],
    ids=[
        "모르는_값", "대문자_public", "대문자_private", "team_아님", "팀_이름_없음", "팀_이름에_콜론", "팀_이름에_공백", "앞_공백", "뒤_공백",
        "빈_문자열", "널", "숫자", "논리값", "목록", "중첩된_값",
    ],
)
def test_공유_범위의_값이_틀리면_오류로_잡고_틀린_값을_알린다(onto_cli, scope):
    root = onto_cli.root(lone(scope))

    result, findings = validate(onto_cli, root)

    assert [finding[:4] for finding in findings] == [(ERROR, "billing", yaml_file(), "invalid-scope")]
    assert "scope" in findings[0][4] and "team:<팀 이름>" in findings[0][4]  # 무엇이 틀렸고 무엇이 맞는지 알려 준다
    assert result.returncode == 1


# --- 교차 참조와 공유 범위 -------------------------------------------------------


def pair(source_scope: object, target_scope: object, to: str = "dst:component/b") -> dict[str, dict[str, str]]:
    """`src`의 페이지가 `dst`의 페이지를 `dependsOn`으로 가리키는 두 지식 저장소. `scope`를 `...`로 주면 적지 않는다."""

    def project(scope: object) -> dict[str, object]:
        return {} if scope is ... else {"scope": scope}

    return {
        "src": repo(
            "src",
            page("component/a", "Component", title="출발", partOf="project", dependsOn=to),
            **project(source_scope),
        ),
        "dst": repo("dst", page("component/b", "Component", title="도착", partOf="project"), **project(target_scope)),
    }


# (가리키는 쪽의 공유 범위, 가리켜지는 쪽의 공유 범위) -> 통과하면 True
REFERENCES = {
    ("public", "public"): True,
    ("public", "team"): False,
    ("public", "team:payments"): False,
    ("public", "private"): False,
    ("team", "public"): True,
    ("team", "team"): True,
    ("team", "team:payments"): False,
    ("team", "private"): False,
    ("team:payments", "public"): True,
    ("team:payments", "team"): False,
    ("team:payments", "team:payments"): True,
    ("team:payments", "team:shop"): False,
    ("team:payments", "private"): False,
    ("private", "public"): True,
    ("private", "team"): True,
    ("private", "team:payments"): True,
    ("private", "private"): True,
}


@pytest.mark.parametrize(("source", "target"), list(REFERENCES), ids=[f"{s}->{t}" for s, t in REFERENCES])
def test_교차_참조는_더_넓은_범위와_같은_범위의_같은_팀으로만_갈_수_있다(onto_cli, source, target):
    root = onto_cli.root(pair(source, target))

    result, findings = validate(onto_cli, root)

    if REFERENCES[source, target]:
        assert (result.returncode, findings) == (0, [])
    else:
        assert [finding[:4] for finding in findings] == [(ERROR, "src", file("component/a", "src"), "scope-violation")]
        assert "dependsOn" in findings[0][4] and "dst:component/b" in findings[0][4]  # 어느 관계의 어느 값인지 알려 준다
        assert f"`{source}`" in findings[0][4] and f"`{target}`" in findings[0][4]
        assert result.returncode == 1


def test_공유_범위를_적지_않은_지식_저장소는_private으로_본다(onto_cli):
    assert found(onto_cli, onto_cli.root(pair("public", ...))) == [(ERROR, "src", file("component/a", "src"), "scope-violation")]
    assert found(onto_cli, onto_cli.root(pair(..., "public"))) == []
    assert found(onto_cli, onto_cli.root(pair(..., ...))) == []


def test_교차_참조가_가리키는_엔티티가_없어도_더_좁은_저장소의_이름을_드러내므로_잡는다(onto_cli):
    root = onto_cli.root(pair("public", "private", to="dst:component/missing"))

    assert found(onto_cli, root) == [
        (ERROR, "src", file("component/a", "src"), "broken-reference"),
        (ERROR, "src", file("component/a", "src"), "scope-violation"),
    ]


def test_관계가_여럿이면_가리키는_값마다_하나씩_보고하고_좁은_저장소와_넓은_저장소를_섞어도_좁은_쪽만_잡는다(onto_cli):
    repos = {
        "src": repo(
            "src",
            page("component/a", "Component", title="출발", partOf="dst:project", dependsOn=["wide:component/w", "dst:component/b"]),
            page("plan/p", "Plan", title="계획", about=["dst:component/b", "wide:project"]),
            scope="team:payments",
        ),
        "dst": repo("dst", page("component/b", "Component", title="도착", partOf="project"), scope="private"),
        "wide": repo("wide", page("component/w", "Component", title="넓은", partOf="project"), scope="public"),
    }

    root = onto_cli.root(repos)
    findings = validate(onto_cli, root)[1]

    assert [finding[:4] for finding in findings] == [
        (ERROR, "src", file("component/a", "src"), "scope-violation"),
        (ERROR, "src", file("component/a", "src"), "scope-violation"),
        (ERROR, "src", file("plan/p", "src"), "scope-violation"),
    ]
    shown = [re.search(r"`(\w+:[\w/-]+)`", finding[4])[1] for finding in findings]  # 설명이 보여 주는 `이름:식별자` 값
    assert sorted(shown) == ["dst:component/b", "dst:component/b", "dst:project"]


def test_공유_범위가_틀린_저장소는_값_오류_하나만_보고하고_그_저장소와의_참조는_비교하지_않는다(onto_cli):
    repos = pair("public", "internal")
    repos["src"].update(page("component/b", "Component", title="B", partOf="project", dependsOn="dst:component/b"))
    repos["dst"].update(page("component/c", "Component", title="C", partOf="project", dependsOn="src:component/a"))

    findings = found(onto_cli, onto_cli.root(repos))

    assert findings == [(ERROR, "dst", yaml_file("dst"), "invalid-scope")]


def test_자기_저장소의_이름으로_가리켜도_같은_범위라_통과한다(onto_cli):
    repos = pair("private", "private", to="src:project")

    assert found(onto_cli, onto_cli.root(repos)) == []


def test_교차_참조는_가리키는_쪽의_저장소에서_보고한다(onto_cli):
    root = onto_cli.root(pair("public", "private"))

    result, findings = validate(onto_cli, root)

    assert [(finding[1], finding[2]) for finding in findings] == [("src", file("component/a", "src"))]


def test_등록되지_않은_저장소를_가리키는_참조는_공유_범위를_따지지_않고_그_오류만_보고한다(onto_cli):
    root = onto_cli.root(pair("public", "private", to="ghost:component/x"))

    assert found(onto_cli, root) == [(ERROR, "src", file("component/a", "src"), "unregistered-repository")]


# --- 관계의 값이 파일 경로 ---------------------------------------------------------


def related(**fields) -> dict[str, dict[str, str]]:
    """`billing`의 페이지 하나가 `fields`의 관계를 쓰는 견본. `shop`의 `component/api`와 `billing`의 `component/core`가 있다."""
    return {
        "billing": repo(
            "billing",
            page("component/gateway", "Component", title="게이트웨이", **fields),
            page("component/core", "Component", title="코어", partOf="project"),
            scope="private",
        ),
        "shop": repo("shop", page("component/api", "Component", title="API", partOf="project"), scope="private"),
    }


FILE_PATHS = [
    "docs/design.md",
    "../shop/docs/ontology/component/api.md",
    "projects/shop/docs/ontology/component/api.md",
    "/Users/me/projects/shop/docs/ontology/component/api.md",
    "~/notes/api.md",
    "C:\\work\\shop\\api.md",
    "..\\shop\\api.md",
    "./component/core",
    "component/../component/core",
    "component/core.md",
    "shop:docs/ontology/component/api.md",
    "shop:../billing/component/core",
]
FILE_PATH_IDS = [
    "저장소_안_경로", "상위_디렉토리", "루트_기준_경로", "절대_경로", "홈_경로", "윈도우_드라이브", "윈도우_상대_경로", "점으로_시작", "중간_상위_조각",
    "확장자가_있는_식별자", "저장소_이름이_붙은_경로", "저장소_이름이_붙은_상위_경로",
]


@pytest.mark.parametrize("path", FILE_PATHS, ids=FILE_PATH_IDS)
def test_관계의_값이_식별자나_교차_참조가_아니라_파일_경로이면_오류로_잡고_깨진_참조로_또_보고하지_않는다(onto_cli, path):
    root = onto_cli.root(related(partOf="project", dependsOn=path))

    result, findings = validate(onto_cli, root)

    assert [finding[:4] for finding in findings] == [(ERROR, "billing", file("component/gateway"), "path-reference")]
    assert "dependsOn" in findings[0][4] and path in findings[0][4]  # 어느 관계의 어느 값인지 알려 준다
    assert result.returncode == 1


@pytest.mark.parametrize(
    "value",
    ["component/core", "shop:component/api", "project", "shop:project", "billing:component/core"],
    ids=["같은_저장소의_식별자", "교차_참조", "프로젝트", "다른_저장소의_프로젝트", "자기_저장소_이름의_교차_참조"],
)
def test_식별자와_교차_참조는_파일_경로로_보지_않는다(onto_cli, value):
    root = onto_cli.root(related(partOf="project", dependsOn=value))

    assert found(onto_cli, root) == []


@pytest.mark.parametrize("value", ["component/missing", "shop:component/missing", "ghost:component/x"], ids=["없는_식별자", "없는_엔티티의_교차_참조", "등록되지_않은_저장소"])
def test_파일_경로가_아닌_틀린_참조는_이전처럼_깨진_참조로_보고한다(onto_cli, value):
    root = onto_cli.root(related(partOf="project", dependsOn=value))

    checks = [finding[3] for finding in validate(onto_cli, root)[1]]

    assert checks and "path-reference" not in checks


def test_식별자_형식이_점을_허용하는_저장소에서는_가리키는_엔티티가_있으면_확장자_모양도_식별자다(onto_cli):
    dotted = {"language": {"identifier-pattern": "[a-z0-9.-]+"}}
    repos = {
        "billing": repo(
            "billing",
            page("component/core.v2", "Component", title="코어 2", partOf="project"),
            page("component/gateway", "Component", title="게이트웨이", partOf="project", dependsOn=["component/core.v2", "component/missing.v2"]),
            rules=dotted,
        )
    }

    findings = validate(onto_cli, onto_cli.root(repos))[1]

    assert [finding[:4] for finding in findings] == [(ERROR, "billing", file("component/gateway"), "path-reference")]  # 없는 엔티티는 경로 모양이라 경로다
    assert "component/missing.v2" in findings[0][4]


def test_관계가_여럿이면_파일_경로인_값만_골라_하나씩_보고한다(onto_cli):
    root = onto_cli.root(related(partOf="project", dependsOn=["component/core", "docs/design.md", "../shop/api.md"]))

    findings = validate(onto_cli, root)[1]

    assert [finding[:4] for finding in findings] == [(ERROR, "billing", file("component/gateway"), "path-reference")] * 2
    assert sorted("docs/design.md" in finding[4] for finding in findings) == [False, True]


def test_모든_관계_키에서_파일_경로를_잡는다(onto_cli):
    fields = {"partOf": "project", "dependsOn": "docs/a.md"}
    root = onto_cli.root(
        {
            "billing": repo(
                "billing",
                page("component/gateway", "Component", title="게이트웨이", **fields),
                page("plan/p", "Plan", title="계획", about="docs/b.md"),
                page("policy/q", "Policy", title="정책", governs="docs/c.md"),
                page("report/r", "Report", title="보고", implements="docs/d.md"),
                page("decision/d", "Decision", title="결정", supersedes="docs/e.md"),
            )
        }
    )

    keys = sorted(finding[4].split("`")[1] for finding in validate(onto_cli, root)[1] if finding[3] == "path-reference")

    assert keys == ["about", "dependsOn", "governs", "implements", "supersedes"]


def test_파일_경로_참조는_가리키는_저장소의_공유_범위를_따지지_않는다(onto_cli):
    """`shop:docs/design.md`는 저장소 이름이 적힌 파일 경로이기도 하다. 공유 범위는 저장소 이름을 드러내는 것으로 따로 잡는다."""
    repos = related(partOf="project", dependsOn="shop:docs/design.md")
    repos["billing"] = repo(
        "billing", page("component/gateway", "Component", title="게이트웨이", partOf="project", dependsOn="shop:docs/design.md"), scope="public"
    )
    repos["shop"] = repo("shop", page("component/api", "Component", title="API", partOf="project"), scope="private")

    assert sorted(finding[3] for finding in validate(onto_cli, onto_cli.root(repos))[1]) == ["path-reference", "scope-violation"]


# --- 페이지 본문의 링크가 지식 저장소 밖을 가리킨다 -----------------------------------------
# 견본 페이지는 `docs/ontology/component/gateway.md`다. 거기서 `../`를 세 번 오르면 지식 저장소의 루트이고 네 번 오르면 저장소 밖이다.

INSIDE = "../../../"  # 지식 저장소의 루트
OUTSIDE = "../../../../"  # 지식 저장소의 바깥(루트 저장소의 `projects/`)


def with_body(body: str) -> dict[str, dict[str, str]]:
    """`billing`의 페이지 하나(`component/gateway`)의 본문이 `body`인 견본."""
    return {"billing": repo("billing", page("component/gateway", "Component", title="게이트웨이", partOf="project", body=body))}


def outside_links(onto_cli, body: str) -> list[tuple[str, str, str, str]]:
    return [finding for finding in found(onto_cli, onto_cli.root(with_body(body))) if finding[3] == "outside-link"]


OUTSIDE_LINKS = {
    "다른_저장소의_문서": f"[설계]({OUTSIDE}shop/docs/design.md)",
    "저장소_밖의_상위_디렉토리": f"[x]({OUTSIDE}../etc/passwd)",
    "안으로_갔다_밖으로": "[x](../component/../../../../../x.md)",
    "절대_경로": "[x](/Users/me/notes/design.md)",
    "저장소_루트_기준_절대_경로": "[x](/docs/design.md)",
    "file_주소": "[x](file:///Users/me/notes/design.md)",
    "윈도우_드라이브": "[x](C:\\Users\\me\\design.md)",
    "윈도우_드라이브_슬래시": "[x](C:/Users/me/design.md)",
    "이미지": f"![그림]({OUTSIDE}assets/diagram.png)",
    "제목이_붙은_링크": f'[x]({OUTSIDE}x.md "제목")',
    "꺾쇠_안의_경로": f"[x](<{OUTSIDE}my file.md>)",
    "퍼센트_인코딩": f"[x]({OUTSIDE}my%20file.md)",
    "조각이_붙은_링크": f"[x]({OUTSIDE}x.md#section)",
    "참조_정의": f"[설계][ref]\n\n[ref]: {OUTSIDE}x.md\n",
    "html_href": f'<a href="{OUTSIDE}x.md">설계</a>',
    "html_src": f"<img src='{OUTSIDE}a.png'>",
    "자동_링크": "<file:///Users/me/notes/design.md>",
    "목록과_문장_속": f"- 항목\n- 앞 문장 [x]({OUTSIDE}x.md) 뒤 문장\n",
}


@pytest.mark.parametrize("body", OUTSIDE_LINKS.values(), ids=OUTSIDE_LINKS.keys())
def test_본문의_링크가_지식_저장소_밖의_파일을_가리키면_오류로_잡는다(onto_cli, body):
    root = onto_cli.root(with_body(body))

    result, findings = validate(onto_cli, root)

    assert [finding[:4] for finding in findings] == [(ERROR, "billing", file("component/gateway"), "outside-link")]
    assert result.returncode == 1


def test_저장소_밖을_가리키는_링크는_설명에_링크의_대상을_보여_준다(onto_cli):
    findings = validate(onto_cli, onto_cli.root(with_body(f"[설계]({OUTSIDE}shop/docs/design.md)")))[1]

    assert f"{OUTSIDE}shop/docs/design.md" in findings[0][4]


INSIDE_LINKS = {
    "같은_디렉토리": "[x](other.md)",
    "다른_클래스_디렉토리": "[x](../term/glossary.md)",
    "원본_문서": "[x](../../design.md)",
    "저장소_루트의_문서": f"[x]({INSIDE}README.md)",
    "저장소_루트": f"[x]({INSIDE})",
    "점_조각": "[x](./other.md)",
    "안으로_갔다_안으로": "[x](../component/../term/a.md)",
    "조각만": "[x](#heading)",
    "문서_안의_조각": "[x](other.md#heading)",
    "질의": "[x](other.md?raw=1)",
    "http": "[x](http://example.com/a/b.md)",
    "https": "[x](https://example.com/a)",
    "상위를_닮은_주소": f"[x](https://example.com/{OUTSIDE}a)",
    "mailto": "[x](mailto:me@example.com)",
    "프로토콜_생략_주소": "[x](//example.com/a)",
    "자동_링크_주소": "<https://example.com/a>",
    "빈_링크": "[x]()",
    "링크가_아닌_대괄호": "배열은 a[1]이고 (../../../../a.md) 괄호는 그냥 글이다.",
    "html_주소": '<a href="https://example.com/x">x</a>',
    "코드_블록": f"```\n[x]({OUTSIDE}x.md)\n```\n",
    "물결_코드_블록": f"~~~md\n[x]({OUTSIDE}x.md)\n~~~\n",
    "인라인_코드": f"예를 들어 `[x]({OUTSIDE}x.md)`처럼 쓰지 않는다.",
    "여러_백틱_코드": f"``[x]({OUTSIDE}x.md)``",
}


@pytest.mark.parametrize("body", INSIDE_LINKS.values(), ids=INSIDE_LINKS.keys())
def test_본문의_링크가_지식_저장소_안이거나_파일이_아니거나_코드_안이면_잡지_않는다(onto_cli, body):
    assert outside_links(onto_cli, body) == []


def test_코드_블록이_끝나면_그_뒤의_링크는_다시_본다(onto_cli):
    body = f"```\n[x]({OUTSIDE}code.md)\n```\n\n[y]({OUTSIDE}after.md)\n"

    findings = validate(onto_cli, onto_cli.root(with_body(body)))[1]

    assert [finding[3] for finding in findings] == ["outside-link"]
    assert "after.md" in findings[0][4] and "code.md" not in findings[0][4]


def test_같은_대상을_여러_번_가리켜도_한_번만_보고하고_다른_대상은_따로_보고한다(onto_cli):
    body = f"[a]({OUTSIDE}x.md) [b]({OUTSIDE}x.md)\n\n[c]({OUTSIDE}y.md)\n"

    findings = validate(onto_cli, onto_cli.root(with_body(body)))[1]

    assert [finding[3] for finding in findings] == ["outside-link"] * 2


def test_본문이_아닌_frontmatter의_글은_링크로_보지_않는다(onto_cli):
    repos = {"billing": repo("billing", page("component/gateway", "Component", title=f"[x]({OUTSIDE}x.md)", partOf="project"))}

    assert [finding[3] for finding in validate(onto_cli, onto_cli.root(repos))[1]] == []


def test_페이지가_깊은_디렉토리에_있으면_그_위치에서_상대_경로를_푼다(onto_cli):
    repos = {
        "billing": repo(
            "billing",
            page("component/deep/er/gateway", "Component", title="깊은 게이트웨이", partOf="project", body="[x](../../../../design.md) [y](../../../../../../../x.md)\n"),
        )
    }

    findings = validate(onto_cli, onto_cli.root(repos))[1]

    assert [(finding[3], "x.md" in finding[4]) for finding in findings if finding[3] == "outside-link"] == [("outside-link", True)]


def test_본문의_링크는_모든_지식_저장소에서_저장소_밖을_기준으로_잡는다(onto_cli):
    repos = {
        "billing": repo("billing", page("component/gateway", "Component", title="게이트웨이", partOf="project", body=f"[x]({OUTSIDE}shop/docs/design.md)\n")),
        "shop": repo("shop", page("component/api", "Component", title="API", partOf="project", body=f"[y]({INSIDE}README.md)\n")),
    }

    assert found(onto_cli, onto_cli.root(repos)) == [(ERROR, "billing", file("component/gateway"), "outside-link")]


def test_생성된_인덱스는_페이지가_아니라서_링크_검사를_받지_않는다(onto_cli):
    root = onto_cli.root(with_body("본문\n"))
    index = root / "projects" / "billing" / ONTOLOGY_DIR / "index.md"
    original = index.read_text(encoding="utf-8")
    assert original  # build가 만든 인덱스가 있다

    # 인덱스를 고치면 인덱스 검사가 알리지만 링크 검사는 인덱스를 읽지 않는다
    index.write_text(original + f"\n[x]({OUTSIDE}x.md)\n", encoding="utf-8")

    assert [finding[3] for finding in validate(onto_cli, root)[1]] == ["index-mismatch"]


# --- 루트 전용: 지식 저장소의 규칙으로 끄거나 낮출 수 없다 -------------------------------------


def violating_repos(check: str, **project) -> dict[str, dict[str, str]]:
    """`check`가 보고하는 문제가 `billing`에 하나 든 견본. `project`는 `billing`의 `ontology.yaml`에 더할 키다."""
    gateway = {"partOf": "project"}
    body = "본문\n"
    scope: object = "private"
    if check == "invalid-scope":
        scope = "internal"
    elif check == "scope-violation":
        scope, gateway["dependsOn"] = "public", "shop:component/api"
    elif check == "path-reference":
        gateway["dependsOn"] = "docs/design.md"
    elif check == "outside-link":
        body = f"[설계]({OUTSIDE}shop/docs/design.md)\n"
    return {
        "billing": repo("billing", page("component/gateway", "Component", title="게이트웨이", body=body, **gateway), **{"scope": scope, **project}),
        "shop": repo("shop", page("component/api", "Component", title="API", partOf="project"), scope="private"),
    }


@pytest.mark.parametrize("check", SCOPE_CHECKS)
def test_견본마다_공유_범위_검사_항목_하나가_걸린다(onto_cli, check):
    assert [finding[3] for finding in validate(onto_cli, onto_cli.root(violating_repos(check)))[1]] == [check]


@pytest.mark.parametrize("check", SCOPE_CHECKS)
@pytest.mark.parametrize(
    "setting", [{"enabled": False}, {"severity": "warning"}, {"enabled": False, "severity": "warning"}], ids=["끄기", "경고로_낮추기", "끄고_낮추기"]
)
def test_지식_저장소의_규칙은_공유_범위_검사를_끄거나_심각도를_낮추지_못하고_덮어쓰려_하면_오류다(onto_cli, check, setting):
    """덮어쓰기는 통째로 버려지고 그 저장소는 루트 기본 규칙으로 검사한다. 그래서 문제는 여전히 오류로 보고된다."""
    root = onto_cli.root(violating_repos(check, rules={"checks": {check: setting}}))

    result, findings = validate(onto_cli, root)

    assert {finding[3]: finding[0] for finding in findings} == {"invalid-rules": ERROR, check: ERROR}  # 보고된 항목과 심각도
    assert len(findings) == 2
    invalid = next(finding for finding in findings if finding[3] == "invalid-rules")
    assert f"`rules.checks.{check}`" in invalid[4] and "루트 전용" in invalid[4]  # 어느 규칙이 왜 안 되는지 알려 준다
    assert result.returncode == 1


@pytest.mark.parametrize("check", SCOPE_CHECKS)
def test_규칙_명령은_공유_범위_검사를_덮어쓰려는_저장소를_오류로_끝낸다(onto_cli, check):
    root = onto_cli.root(violating_repos(check, rules={"checks": {check: {"enabled": False}}}))

    result = onto_cli.run(root, "rules", "billing")

    assert result.returncode == 1
    assert yaml_file() in result.stderr and f"rules.checks.{check}" in result.stderr and "루트 전용" in result.stderr


@pytest.mark.parametrize("check", SCOPE_CHECKS)
def test_루트_기본_규칙은_공유_범위_검사의_심각도를_바꾸거나_끌_수_있다(onto_cli, check):
    root = onto_cli.root(violating_repos(check))
    assert [finding[0] for finding in validate(onto_cli, root)[1]] == [ERROR]

    onto_cli.set_root_check(check, severity="warning")
    lowered, lowered_findings = validate(onto_cli, root)
    onto_cli.set_root_check(check, enabled=False)
    disabled, disabled_findings = validate(onto_cli, root)

    assert ([finding[:4] for finding in lowered_findings], lowered.returncode) == ([(WARNING, "billing", lowered_findings[0][2], check)], 0)
    assert (disabled_findings, disabled.returncode) == ([], 0)


def test_공유_범위_검사_항목은_기본이_모두_오류이고_켜져_있다(onto_cli):
    checks = json.loads(onto_cli.run(onto_cli.root({}), "rules").stdout)["checks"]

    assert {name: checks[name] for name in SCOPE_CHECKS} == {name: {"enabled": True, "severity": "error"} for name in SCOPE_CHECKS}


def test_공유_범위_검사는_어떤_파일도_고치거나_만들지_않는다(onto_cli):
    root = onto_cli.root(violating_repos("scope-violation"))
    before = snapshot(root)

    assert onto_cli.run(root, "validate").returncode == 1

    assert snapshot(root) == before
