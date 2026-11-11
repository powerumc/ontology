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

from support.onto_cli import ONTOLOGY_DIR, REPOSITORY, page, repo, snapshot

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


def test_공유_범위가_틀린_저장소는_값_오류를_보고하고_비교에서는_private으로_본다(onto_cli):
    repos = pair("public", "internal")
    repos["dst"].update(page("component/c", "Component", title="C", partOf="project", dependsOn="src:component/a"))

    findings = found(onto_cli, onto_cli.root(repos))

    assert findings == [
        (ERROR, "dst", yaml_file("dst"), "invalid-scope"),
        (ERROR, "src", file("component/a", "src"), "scope-violation"),  # `public`이 `private`으로 본 저장소를 가리킨다. 반대 방향은 된다
    ]


# --- 범위를 알 수 없는 저장소와 저장소를 가리키는 두 이름 ----------------------------------
# 범위를 알 수 없는 등록된 저장소(온톨로지 층이 없다, `ontology.yaml`을 읽을 수 없다, `scope` 값이 틀렸다)는 가장 좁은 `private`으로 본다.
# 그 저장소의 문제는 저장소 규칙으로 끌 수 있는 항목이나 경고로만 보고되므로, 그것만 믿으면 저장소 이름이 드러난 채 통과한다.
# 참조는 저장소를 `name`으로도 서브모듈 디렉토리 이름으로도 가리킬 수 있다.


def team_repo(body: str = "본문\n", *, rules: object = None, **fields) -> dict[str, str]:
    """`team`(`team:pay`) 지식 저장소. 페이지 `component/b`가 `fields`(관계)와 본문 `body`를 가진다."""
    project = {"scope": "team:pay", **({"rules": rules} if rules else {})}
    return repo(
        "team",
        page("component/a", "Component", title="A", partOf="project"),
        page("component/b", "Component", title="B", partOf="project", body=body, **fields),
        **project,
    )


def secret_repo(name: str = "secret", title: str = "X", **project) -> dict[str, str]:
    """`private` 지식 저장소. `name`이 서브모듈 디렉토리 이름과 다를 수 있다."""
    return repo(name, page("component/x", "Component", title=title, partOf="project"), **{"scope": "private", **project})


MUTE_BROKEN = {"checks": {"broken-reference": {"enabled": False}, "unregistered-repository": {"enabled": False}}}


def violations(onto_cli, repos) -> list[tuple[str, str, str, str]]:
    return [finding for finding in found(onto_cli, onto_cli.root(repos)) if finding[3] == "scope-violation"]


def test_name과_디렉토리_이름이_다른_저장소를_디렉토리_이름으로_가리켜도_공유_범위를_따진다(onto_cli):
    """디렉토리 이름 `secret`이 팀 저장소에 남는다. `broken-reference`와 `repository-name-mismatch`를 저장소 규칙으로 꺼도 `scope-violation`은 남는다."""
    mismatch_off = {"checks": {"repository-name-mismatch": {"enabled": False}}}
    repos = {
        "team": team_repo(dependsOn="secret:component/x", rules=MUTE_BROKEN),
        "secret": secret_repo("hidden", rules=mismatch_off),
    }

    result, findings = validate(onto_cli, onto_cli.root(repos))

    assert [finding[:4] for finding in findings] == [(ERROR, "team", file("component/b", "team"), "scope-violation")]
    assert result.returncode == 1


def test_name과_디렉토리_이름이_다른_저장소를_name으로_가리켜도_공유_범위를_따진다(onto_cli):
    repos = {"team": team_repo(dependsOn="hidden:component/x"), "secret": secret_repo("hidden")}

    assert violations(onto_cli, repos) == [(ERROR, "team", file("component/b", "team"), "scope-violation")]


def test_온톨로지_층이_없는_저장소는_private으로_보고_그_저장소의_경고와_상관없이_잡는다(onto_cli):
    repos = {"team": team_repo(dependsOn="secret:component/x", rules=MUTE_BROKEN), "secret": {"README.md": "온톨로지 층이 없다\n"}}

    result, findings = validate(onto_cli, onto_cli.root(repos))

    assert [finding[:4] for finding in findings if finding[3] == "scope-violation"] == [(ERROR, "team", file("component/b", "team"), "scope-violation")]
    assert result.returncode == 1


def test_ontology_yaml을_읽을_수_없는_저장소는_private으로_보고_잡는다(onto_cli):
    unreadable = {f"{ONTOLOGY_DIR}/ontology.yaml": "name: [닫히지 않았다\n"}
    repos = {"team": team_repo(dependsOn="secret:component/x", rules=MUTE_BROKEN), "secret": unreadable}

    findings = found(onto_cli, onto_cli.root(repos))

    assert (ERROR, "team", file("component/b", "team"), "scope-violation") in findings


def test_범위를_알_수_없는_저장소를_더_넓은_저장소가_가리키지_않으면_문제가_없다(onto_cli):
    """`private`으로 보므로 `private` 저장소와 같다. 층이 없는 저장소를 가리키는 `private`은 통과한다."""
    repos = {"mine": repo("mine", page("component/a", "Component", title="A", partOf="project", dependsOn="secret:component/x")), "secret": {"README.md": "x\n"}}

    assert violations(onto_cli, repos) == []


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
    "file:///Users/me/projects/secret/docs/x.md",
    "FILE:///Users/me/x",
    "file:relative/x",
    "docs/ontology/component/a",
    "docs/ontology/plan/x",
    "projects/secret/docs/ontology/component/x",
    "secret/component/x",
    "componet/api",
    "api",
    "shop:docs/ontology/component/api",
]
FILE_PATH_IDS = [
    "저장소_안_경로", "상위_디렉토리", "루트_기준_경로", "절대_경로", "홈_경로", "윈도우_드라이브", "윈도우_상대_경로", "점으로_시작", "중간_상위_조각",
    "확장자가_있는_식별자", "저장소_이름이_붙은_경로", "저장소_이름이_붙은_상위_경로", "file_주소", "대문자_file_주소", "상대_file_주소",
    "온톨로지_층_경로", "온톨로지_층의_계획_경로", "projects_경로", "클래스_디렉토리가_아닌_첫_조각", "클래스_디렉토리_오타", "첫_조각만", "저장소_이름이_붙은_층_경로",
]


@pytest.mark.parametrize("path", FILE_PATHS, ids=FILE_PATH_IDS)
def test_관계의_값이_식별자나_교차_참조가_아니라_파일_경로이면_오류로_잡고_깨진_참조로_또_보고하지_않는다(onto_cli, path):
    root = onto_cli.root(related(partOf="project", dependsOn=path))

    result, findings = validate(onto_cli, root)

    assert [finding[:4] for finding in findings] == [(ERROR, "billing", file("component/gateway"), "path-reference")]
    assert "dependsOn" in findings[0][4] and path in findings[0][4]  # 어느 관계의 어느 값인지 알려 준다
    assert result.returncode == 1


@pytest.mark.parametrize("path", FILE_PATHS, ids=FILE_PATH_IDS)
def test_파일_경로는_저장소_규칙으로_끌_수_있는_항목을_꺼도_path_reference로_남는다(onto_cli, path):
    """`path-reference`가 보지 않는 모양은 `broken-reference`나 `unregistered-repository`에만 걸려, 그 항목을 끄면 통과했다."""
    repos = related(partOf="project", dependsOn=path)
    repos["billing"] = repo(
        "billing",
        page("component/gateway", "Component", title="게이트웨이", partOf="project", dependsOn=path),
        page("component/core", "Component", title="코어", partOf="project"),
        scope="private",
        rules=MUTE_BROKEN,
    )

    result, findings = validate(onto_cli, onto_cli.root(repos))

    assert [finding[:4] for finding in findings] == [(ERROR, "billing", file("component/gateway"), "path-reference")]
    assert result.returncode == 1


def test_파일_경로가_아닌_값은_식별자_모양이어도_첫_조각이_클래스_디렉토리가_아니면_오류의_설명이_그_이유를_알린다(onto_cli):
    findings = validate(onto_cli, onto_cli.root(related(partOf="project", dependsOn="componet/api")))[1]

    assert findings[0][3] == "path-reference" and "클래스 디렉토리" in findings[0][4]


@pytest.mark.parametrize(
    "value",
    ["component/core", "shop:component/api", "project", "shop:project", "billing:component/core"],
    ids=["같은_저장소의_식별자", "교차_참조", "프로젝트", "다른_저장소의_프로젝트", "자기_저장소_이름의_교차_참조"],
)
def test_식별자와_교차_참조는_파일_경로로_보지_않는다(onto_cli, value):
    root = onto_cli.root(related(partOf="project", dependsOn=value))

    assert found(onto_cli, root) == []


def test_저장소_이름_뒤에_공백이_있는_교차_참조도_엔티티가_없으면_경로가_아니라_깨진_참조로_보고한다(onto_cli):
    """`open: component/missing`의 식별자는 공백을 뗀 `component/missing`이다. 엔티티가 있으면 통과하는 값이 없을 때만 경로라고 설명되면 안 된다."""
    repos = {
        "team": team_repo(dependsOn=["open: component/missing"]),
        "open": repo("open", page("component/x", "Component", title="공개 X", partOf="project"), scope="public"),
    }

    findings = validate(onto_cli, onto_cli.root(repos))[1]

    assert [finding[:4] for finding in findings] == [(ERROR, "team", file("component/b", "team"), "broken-reference")]
    assert "가리키는 엔티티가 없다" in findings[0][4]


@pytest.mark.parametrize("value", ["component/missing", "shop:component/missing", "ghost:component/x"], ids=["없는_식별자", "없는_엔티티의_교차_참조", "등록되지_않은_저장소"])
def test_파일_경로가_아닌_틀린_참조는_이전처럼_깨진_참조로_보고한다(onto_cli, value):
    root = onto_cli.root(related(partOf="project", dependsOn=value))

    checks = [finding[3] for finding in validate(onto_cli, root)[1]]

    assert checks and "path-reference" not in checks


def test_식별자_형식이_점을_허용하는_저장소에서는_가리키는_엔티티가_있으면_확장자_모양도_식별자다(onto_cli):
    onto_cli.replace_in_root_rules('identifier-pattern: "[a-z0-9-]+"', 'identifier-pattern: "[a-z0-9.-]+"')
    repos = {
        "billing": repo(
            "billing",
            page("component/core.v2", "Component", title="코어 2", partOf="project"),
            page("component/gateway", "Component", title="게이트웨이", partOf="project", dependsOn=["component/core.v2", "component/missing.v2"]),
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
    "역슬래시_상대_경로": "[x](..\\..\\..\\..\\shop\\docs\\x.md)",
    "역슬래시_절대_경로": "[x](\\Users\\me\\x.md)",
    "따옴표_없는_html_href_경로": f"<a href={OUTSIDE}x.md>설계</a>",
    "따옴표_없는_html_src_경로": f"<img src={OUTSIDE}a.png>",
    "주석_뒤의_링크": f"<!-- 메모 -->\n[x]({OUTSIDE}x.md)\n",
    "목록_안의_들여쓴_울타리_뒤의_링크": f"- 항목\n\n      ```\n      코드\n      ```\n\n[x]({OUTSIDE}x.md)\n",
    "퍼센트_인코딩": f"[x]({OUTSIDE}my%20file.md)",
    "조각이_붙은_링크": f"[x]({OUTSIDE}x.md#section)",
    "참조_정의": f"[설계][ref]\n\n[ref]: {OUTSIDE}x.md\n",
    "html_href": f'<a href="{OUTSIDE}x.md">설계</a>',
    "html_src": f"<img src='{OUTSIDE}a.png'>",
    "자동_링크": "<file:///Users/me/notes/design.md>",
    "목록과_문장_속": f"- 항목\n- 앞 문장 [x]({OUTSIDE}x.md) 뒤 문장\n",
    "다른_속성_뒤의_html_src": f'<img alt="그림" width=10 src={OUTSIDE}a.png>',
    "여러_줄에_걸친_html_태그": f'<a\n  class="x"\n  href="{OUTSIDE}x.md">x</a>',
    "따옴표_안에_꺾쇠가_든_html_태그": f'<a title="a>b" href="{OUTSIDE}x.md">x</a>',
    # 따옴표는 `=` 바로 뒤에서만 값을 연다. 따옴표 없는 속성 값 안의 따옴표는 그냥 글자라, 본문의 다음 따옴표까지 태그를 늘리지 않는다.
    "따옴표_없는_속성_값_안의_아포스트로피": f"<img alt=don't src={OUTSIDE}x.png> 그리고 it's done",
    "따옴표_없는_속성_값_안의_큰따옴표": f'<a title=5" href={OUTSIDE}x.md>x</a> 그리고 "인용"',
    "작은따옴표_값_안의_큰따옴표": f"""<a title='"인용" >' href={OUTSIDE}x.md>x</a>""",
    "들여쓴_닫히지_않은_울타리_뒤의_링크": f"예시:\n\n    ```python\n    print(1)\n\n본문 [x]({OUTSIDE}x.md)\n",
    "울타리는_3칸까지_더_들여써도_닫는다": f"```\n코드\n   ```\n\n[x]({OUTSIDE}x.md)\n",
    "코드_안의_주석_표시_사이의_링크": f"주석은 `<!--`로 열고 [x]({OUTSIDE}x.md)를 지나 `-->`로 닫는다.\n",
    "주석_안의_백틱은_코드를_열지_않는다": f"<!-- 메모의 ` 하나 -->\n[x]({OUTSIDE}x.md) 그리고 `코드`\n",
    "다른_속성_값에_href_글자가_든_태그의_진짜_href": f'<a title="href=./ok" href="{OUTSIDE}x.md">x</a>',
    "다른_속성_값에_src_글자가_든_태그의_진짜_src": f"<img alt='a src=./ok b' src={OUTSIDE}a.png>",
    "대문자_속성_이름": f'<a HREF="{OUTSIDE}x.md">x</a>',
    "xlink_href": f'<svg><image xlink:href="{OUTSIDE}x.png"/></svg>',
    "공백_없이_이어진_속성": f'<a title="x"href="{OUTSIDE}x.md">x</a>',
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
    "역슬래시_안쪽": "[x](..\\term\\a.md)",
    "따옴표_없는_html_주소": "<a href=https://example.com/a>x</a>",
    "html_주석": f"<!-- [x]({OUTSIDE}x.md) -->",
    "여러_줄_html_주석": f"<!--\n[x]({OUTSIDE}x.md)\n<a href='{OUTSIDE}y.md'>y</a>\n-->\n",
    "목록_안의_들여쓴_울타리": f"- 항목\n\n      ```\n      [x]({OUTSIDE}x.md)\n      ```\n",
    "빈_링크": "[x]()",
    "링크가_아닌_대괄호": "배열은 a[1]이고 (../../../../a.md) 괄호는 그냥 글이다.",
    "html_주소": '<a href="https://example.com/x">x</a>',
    "코드_블록": f"```\n[x]({OUTSIDE}x.md)\n```\n",
    "물결_코드_블록": f"~~~md\n[x]({OUTSIDE}x.md)\n~~~\n",
    "인라인_코드": f"예를 들어 `[x]({OUTSIDE}x.md)`처럼 쓰지 않는다.",
    "여러_백틱_코드": f"``[x]({OUTSIDE}x.md)``",
    "본문_평문의_src와_href": "설정의 src=/etc/app.conf 값을 바꾸고 href=/login 으로 보낸다.\n",
    "html_태그_밖의_href": "href=/login 은 <b>굵게</b> 쓴다.\n",
    "울타리_안에_4칸_들여쓴_울타리가_든_코드_블록": f"```md\n- 목록\n\n    ```\n    [x]({OUTSIDE}x.md)\n    ```\n```\n",
    # 링크가 아닌 속성 값 안의 `href=`, `src=` 글자와, `href`·`src`로 끝나는 다른 속성의 이름
    "다른_속성_값_안의_href_글자": '<abbr title="see href=/etc/passwd">API</abbr>',
    "작은따옴표_속성_값_안의_src_글자": "<abbr title='a src=../../../../x.png b'>x</abbr>",
    "data_src_속성": f'<img data-src="{OUTSIDE}x.png">',
    "data_href_속성": f"<a data-href={OUTSIDE}x.md>x</a>",
    "따옴표_없는_data_src_속성": f"<img data-src={OUTSIDE}x.png alt=그림>",
}


@pytest.mark.parametrize("body", INSIDE_LINKS.values(), ids=INSIDE_LINKS.keys())
def test_본문의_링크가_지식_저장소_안이거나_파일이_아니거나_코드_안이면_잡지_않는다(onto_cli, body):
    assert outside_links(onto_cli, body) == []


def test_링크가_아닌_속성_값_안의_href_글자는_대상으로_보고하지_않고_진짜_링크만_보고한다(onto_cli):
    body = f'<abbr title="see href=/etc/passwd">API</abbr> <a href="{OUTSIDE}x.md">설계</a>\n'

    findings = validate(onto_cli, onto_cli.root(with_body(body)))[1]

    assert [finding[3] for finding in findings] == ["outside-link"]
    assert "x.md" in findings[0][4] and "/etc/passwd" not in findings[0][4]


# 마크다운의 줄바꿈은 `\n`, `\r\n`, `\r`뿐이다. 유니코드의 줄 구분 문자(U+2028 등)는 줄을 나누지 않는다. 나누면 한 줄 중간의 ```가 줄 맨 앞의
# 울타리로 읽혀 그 뒤의 링크가 코드 블록 안에 숨는다.
LINE_SEPARATORS = {
    "U+2028": "\u2028",
    "U+2029": "\u2029",
    "U+0085": "\x85",
    "수직_탭": "\x0b",
    "폼_피드": "\x0c",
    "파일_구분자": "\x1c",
    "그룹_구분자": "\x1d",
    "레코드_구분자": "\x1e",
}


@pytest.mark.parametrize("separator", LINE_SEPARATORS.values(), ids=LINE_SEPARATORS.keys())
def test_줄바꿈이_아닌_구분_문자_뒤의_울타리는_코드_블록을_열지_않아_그_뒤의_링크를_숨기지_않는다(onto_cli, separator):
    body = f"앞 글{separator}```\n[x]({OUTSIDE}x.md)\n```\n"

    assert outside_links(onto_cli, body) == [(ERROR, "billing", file("component/gateway"), "outside-link")]


@pytest.mark.parametrize("line_break", ["\r\n", "\r"], ids=["CRLF", "CR"])
def test_CRLF와_CR_줄바꿈의_코드_블록도_코드_블록으로_읽는다(onto_cli, line_break):
    body = line_break.join(["```", f"[x]({OUTSIDE}code.md)", "```", "", f"[y]({OUTSIDE}after.md)", ""])

    findings = validate(onto_cli, onto_cli.root(with_body(body)))[1]

    assert [finding[3] for finding in findings] == ["outside-link"]
    assert "after.md" in findings[0][4] and "code.md" not in findings[0][4]


# 링크를 찾는 정규식이 입력에 따라 지수 시간으로 되돌아가면 `validate`가 끝나지 않고, 푸시 관문(`--force`까지)이 멈춘다. 끝나지 않는 입력은 시간 상한으로 가린다.
# 입력은 느린 구현이 사실상 끝내지 못하는 크기다(따옴표 하나마다 약 1.6배, 울타리 줄 수의 제곱). 느리지 않은 구현은 1초 안에 끝낸다. 상한은 느려진 기기에서도 흔들리지 않게 넉넉히 둔다.
SLOW_BODIES = {
    "닫히지_않은_태그_뒤의_아포스트로피": "수가 <limit the worker doesn't block. It's the scheduler's job; " + "it's, doesn't. " * 200,
    "닫히지_않은_태그_뒤의_따옴표": "x <y 조건 " + '"용어" ' * 200 + "\n",
    "닫히지_않은_태그_뒤의_작은따옴표와_큰따옴표": "a <p99 " + "'a' \"b\" it's " * 100 + "\n",
    "닫히지_않은_들여쓴_울타리_여러_개": "    ```x\n" * 60000,
}
SLOW_BODY_LIMIT = 120  # 초


@pytest.mark.parametrize("body", SLOW_BODIES.values(), ids=SLOW_BODIES.keys())
def test_본문의_링크_검사는_따옴표와_울타리가_많아도_정해진_시간_안에_끝난다(onto_cli, body):
    root = onto_cli.root(with_body(body))

    result = onto_cli.run(root, "validate", timeout=SLOW_BODY_LIMIT)

    assert result.returncode in (0, 1), result.stderr  # 끝났다(검사 결과는 여기서 따지지 않는다)


def test_닫히지_않은_태그_뒤에_따옴표가_많아도_그_뒤의_링크는_본다(onto_cli):
    body = "수가 <limit the worker doesn't block. " + "it's, doesn't. " * 200 + f"\n\n<a href={OUTSIDE}x.md>설계</a>\n"

    assert outside_links(onto_cli, body) == [(ERROR, "billing", file("component/gateway"), "outside-link")]


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
        "shop": {**repo("shop", page("component/api", "Component", title="API", partOf="project", body=f"[y]({INSIDE}README.md)\n")), "README.md": "# 상점\n"},
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


# --- 다른 저장소를 가리키는 심볼릭 링크 페이지 --------------------------------------------------
# 페이지 파일이 지식 저장소 밖(다른 지식 저장소)의 파일을 가리키는 심볼릭 링크이면 그 파일을 페이지로 읽지 않는다. 읽으면 비공개
# 저장소의 제목이 팀 저장소의 그래프와 커밋되는 인덱스에 실리고, 링크 자체가 다른 저장소의 경로를 담는다. 오류는 `outside-link`다.

SECRET_TITLE = "비밀 프로젝트의 X"


def linked_root(onto_cli):
    """`team`에 `component/y.md`가 `secret`의 페이지를 가리키는 심볼릭 링크로 든 견본 루트."""
    root = onto_cli.root({"team": team_repo(), "secret": secret_repo(title=SECRET_TITLE)})
    (root / "projects/team" / ONTOLOGY_DIR / "component/y.md").symlink_to(root / "projects/secret" / ONTOLOGY_DIR / "component/x.md")
    return root


def test_다른_저장소의_페이지를_가리키는_심볼릭_링크_페이지는_읽지_않고_오류로_알린다(onto_cli):
    root = linked_root(onto_cli)

    result, findings = validate(onto_cli, root)

    assert [finding[:4] for finding in findings] == [(ERROR, "team", file("component/y", "team"), "outside-link")]
    assert SECRET_TITLE not in result.stdout + result.stderr  # 링크의 내용은 읽지 않는다
    assert result.returncode == 1


def test_심볼릭_링크_페이지가_있으면_build도_멈추고_인덱스에_비공개_제목이_실리지_않는다(onto_cli):
    root = linked_root(onto_cli)
    index = root / "projects/team" / ONTOLOGY_DIR / "index.md"
    before = index.read_text(encoding="utf-8")

    result = onto_cli.run(root, "build")

    assert result.returncode == 1 and file("component/y", "team") in result.stderr and "심볼릭 링크" in result.stderr
    assert index.read_text(encoding="utf-8") == before and SECRET_TITLE not in before


def test_루트_규칙이_심볼릭_링크_페이지를_경고로_낮추면_build가_그_페이지를_건너뛰고_알린다(onto_cli):
    onto_cli.set_root_check("outside-link", severity="warning")
    root = linked_root(onto_cli)

    built = onto_cli.run(root, "build")
    team_entities = [row[0] for row in onto_cli.query(root, 'SELECT ?e WHERE { ?e onto:repository "team" }')]

    assert built.returncode == 0 and "outside-link" in built.stderr
    assert file("component/y", "team") not in team_entities and file("component/b", "team") in team_entities


def test_가리키는_파일이_없는_심볼릭_링크_페이지도_저장소_밖을_가리키면_오류로_알린다(onto_cli):
    """링크 파일 자체가 다른 저장소의 이름이나 절대 경로를 담는다. 가리키던 페이지가 지워졌거나 지식 저장소를 단독으로 열어도 그대로 남는다."""
    root = onto_cli.root({"team": team_repo(), "secret": secret_repo(title=SECRET_TITLE)})
    layer = root / "projects/team" / ONTOLOGY_DIR
    (layer / "component/y.md").symlink_to(root / "projects/secret" / ONTOLOGY_DIR / "component/gone.md")  # 절대 경로, 저장소 밖
    (layer / "component/w.md").symlink_to("/Users/me/private-notes/x.md")  # 절대 경로, 어디에도 없는 곳
    (layer / "component/r.md").symlink_to("../../../../secret/docs/ontology/component/gone.md")  # 상대 경로로 저장소 밖
    (layer / "component/z.md").symlink_to("../term/gone.md")  # 저장소 안이면 알릴 것이 없다

    result, findings = validate(onto_cli, root)

    assert sorted(finding[:4] for finding in findings) == [(ERROR, "team", file(f"component/{name}", "team"), "outside-link") for name in ("r", "w", "y")]
    assert all("심볼릭 링크" in finding[4] for finding in findings)
    assert result.returncode == 1


def test_저장소_안을_가리키는_깨진_심볼릭_링크_페이지는_알리지_않는다(onto_cli):
    root = onto_cli.root({"team": team_repo()})
    (root / "projects/team" / ONTOLOGY_DIR / "component/z.md").symlink_to("../term/gone.md")

    assert found(onto_cli, root) == []


# `ontology.yaml`과 `skipped.yaml`도 지식 저장소가 커밋하는 파일이다. 페이지처럼 저장소 밖(다른 지식 저장소)의 파일을 가리키는 심볼릭 링크이면 읽지 않고
# `outside-link`로 알린다. 읽으면 다른 저장소의 이름과 설정, 원본 문서의 경로가 이 저장소의 사실이 된다.


def test_ontology_yaml이_다른_저장소의_파일을_가리키는_심볼릭_링크이면_읽지_않고_오류로_알린다(onto_cli):
    root = onto_cli.root({"team": team_repo(), "secret": secret_repo(title=SECRET_TITLE, description="비밀 설명")})
    link = root / "projects/team" / ONTOLOGY_DIR / "ontology.yaml"
    link.unlink()
    link.symlink_to(root / "projects/secret" / ONTOLOGY_DIR / "ontology.yaml")

    result, findings = validate(onto_cli, root)

    assert (ERROR, "team", yaml_file("team"), "outside-link") in [finding[:4] for finding in findings]
    assert "duplicate-repository-name" not in [finding[3] for finding in findings]  # secret의 name을 이 저장소의 것으로 읽지 않았다
    assert "심볼릭 링크" in next(finding[4] for finding in findings if finding[3] == "outside-link")
    assert result.returncode == 1
    built = onto_cli.run(root, "build")
    assert built.returncode == 1 and yaml_file("team") in built.stderr
    assert "비밀 설명" not in built.stdout + built.stderr


def test_ontology_yaml이_같은_저장소_안을_가리키는_심볼릭_링크이면_그대로_읽는다(onto_cli):
    root = onto_cli.root({"team": team_repo()})
    layer = root / "projects/team" / ONTOLOGY_DIR
    (layer / "ontology.real.yaml").write_text((layer / "ontology.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (layer / "ontology.yaml").unlink()
    (layer / "ontology.yaml").symlink_to("ontology.real.yaml")

    assert found(onto_cli, root) == []


def test_skipped_yaml이_다른_저장소의_파일을_가리키는_심볼릭_링크이면_읽지_않고_오류로_알린다(onto_cli):
    """읽으면 그 파일에 적힌 원본 문서의 경로가 이 저장소의 `missing-skipped-source` 경고로 드러난다."""
    root = onto_cli.root({"team": team_repo()})
    other = root / "other-notes.yaml"  # 지식 저장소 밖
    other.write_text(f'- path: docs/secret-meeting.md\n  hash: "{"a" * 40}"\n', encoding="utf-8")
    (root / "projects/team" / ONTOLOGY_DIR / "skipped.yaml").symlink_to(other)

    result, findings = validate(onto_cli, root)

    skipped = f"projects/team/{ONTOLOGY_DIR}/skipped.yaml"
    assert [finding[:4] for finding in findings] == [(ERROR, "team", skipped, "outside-link")]
    assert "secret-meeting" not in result.stdout + result.stderr
    assert result.returncode == 1
    assert onto_cli.run(root, "build").returncode == 1


def test_가리키는_파일이_없는_skipped_yaml_심볼릭_링크도_저장소_밖을_가리키면_오류로_알린다(onto_cli):
    root = onto_cli.root({"team": team_repo()})
    (root / "projects/team" / ONTOLOGY_DIR / "skipped.yaml").symlink_to("/Users/me/private-notes/skipped.yaml")

    findings = found(onto_cli, root)

    assert findings == [(ERROR, "team", f"projects/team/{ONTOLOGY_DIR}/skipped.yaml", "outside-link")]


def test_가리키는_파일이_없는_ontology_yaml_심볼릭_링크도_저장소_밖을_가리키면_오류로_알린다(onto_cli):
    """링크 파일 자체가 다른 저장소나 기기의 경로를 담는다. 온톨로지 층이 없다는 경고만으로는 푸시 관문을 통과해 그 경로가 팀 저장소에 올라간다."""
    root = onto_cli.root({"team": team_repo()})
    link = root / "projects/team" / ONTOLOGY_DIR / "ontology.yaml"
    link.unlink()
    link.symlink_to("/Users/me/private-notes/ontology.yaml")

    result, findings = validate(onto_cli, root)

    assert (ERROR, "team", yaml_file("team"), "outside-link") in [finding[:4] for finding in findings]
    assert "심볼릭 링크" in next(finding[4] for finding in findings if finding[3] == "outside-link")
    assert result.returncode == 1
    assert onto_cli.run(root, "build").returncode == 1


def test_저장소_안을_가리키는_깨진_ontology_yaml_링크는_저장소_밖_링크로_알리지_않는다(onto_cli):
    root = onto_cli.root({"team": team_repo()})
    link = root / "projects/team" / ONTOLOGY_DIR / "ontology.yaml"
    link.unlink()
    link.symlink_to("ontology.missing.yaml")

    result, findings = validate(onto_cli, root)

    assert "outside-link" not in [finding[3] for finding in findings]
    assert "missing-ontology-layer" in [finding[3] for finding in findings]
    assert result.returncode == 0


def test_순환하는_skipped_yaml_링크는_없는_파일이_아니라_읽을_수_없는_파일로_알린다(onto_cli):
    root = onto_cli.root({"team": team_repo()})
    (root / "projects/team" / ONTOLOGY_DIR / "skipped.yaml").symlink_to("skipped.yaml")

    result, findings = validate(onto_cli, root)

    skipped = f"projects/team/{ONTOLOGY_DIR}/skipped.yaml"
    assert [finding[:4] for finding in findings] == [(ERROR, "team", skipped, "unreadable-file")]
    assert result.returncode == 1
    assert onto_cli.run(root, "build").returncode == 1


def test_순환하는_페이지_링크는_없는_파일이_아니라_읽을_수_없는_파일로_알린다(onto_cli):
    root = onto_cli.root({"team": team_repo()})
    (root / "projects/team" / ONTOLOGY_DIR / "component/loop.md").symlink_to("loop.md")

    result, findings = validate(onto_cli, root)

    assert [finding[:4] for finding in findings] == [(ERROR, "team", file("component/loop", "team"), "unreadable-file")]
    assert "Too many levels of symbolic links" in findings[0][4]
    assert result.returncode == 1
    assert onto_cli.run(root, "build").returncode == 1


def test_서로를_가리키는_두_페이지_링크도_읽을_수_없는_파일로_알린다(onto_cli):
    root = onto_cli.root({"team": team_repo()})
    layer = root / "projects/team" / ONTOLOGY_DIR
    (layer / "component/ping.md").symlink_to("pong.md")
    (layer / "component/pong.md").symlink_to("ping.md")

    findings = found(onto_cli, root)

    assert sorted(findings) == [(ERROR, "team", file(f"component/{name}", "team"), "unreadable-file") for name in ("ping", "pong")]


def test_순환하는_ontology_yaml_링크는_온톨로지_층이_없는_것이_아니라_읽을_수_없는_파일로_알린다(onto_cli):
    root = onto_cli.root({"team": team_repo()})
    link = root / "projects/team" / ONTOLOGY_DIR / "ontology.yaml"
    link.unlink()
    link.symlink_to("ontology.yaml")

    result, findings = validate(onto_cli, root)

    assert (ERROR, "team", yaml_file("team"), "unreadable-file") in [finding[:4] for finding in findings]
    assert "missing-ontology-layer" not in [finding[3] for finding in findings]  # 층이 없는 것이 아니라 읽을 수 없는 것이다
    assert "Too many levels of symbolic links" in next(finding[4] for finding in findings if finding[3] == "unreadable-file")
    assert result.returncode == 1
    assert onto_cli.run(root, "build").returncode == 1


def test_docs_ontology가_일반_파일인_저장소는_읽을_수_없는_ontology_yaml이_아니라_온톨로지_층이_없는_것으로_본다(onto_cli):
    """`ontology.yaml`이 있을 수조차 없는 경우(`ENOTDIR`)다. 순환하는 링크와 달리 없는 파일이라 경고로 알리고 그 저장소만 건너뛴다."""
    root = onto_cli.root({"team": team_repo(), "plain": {"docs/ontology": "층이 아니라 파일이다\n"}})

    result, findings = validate(onto_cli, root)
    built = onto_cli.run(root, "build")

    assert [finding[:4] for finding in findings] == [(WARNING, "plain", "projects/plain", "missing-ontology-layer")]
    assert result.returncode == 0
    assert built.returncode == 0  # 다른 저장소의 build가 멈추지 않는다


def test_순환하는_링크도_규칙에서_unreadable_file을_경고로_낮추면_build가_건너뛰고_알린다(onto_cli):
    onto_cli.set_root_check("unreadable-file", severity="warning")
    root = onto_cli.root({"team": team_repo()})
    (root / "projects/team" / ONTOLOGY_DIR / "component/loop.md").symlink_to("loop.md")

    result = onto_cli.run(root, "build")

    assert result.returncode == 0 and "unreadable-file" in result.stderr


def test_가리키는_파일이_없는_skipped_yaml_링크가_저장소_안을_가리키면_넘긴_문서가_없는_것으로_본다(onto_cli):
    root = onto_cli.root({"team": team_repo()})
    (root / "projects/team" / ONTOLOGY_DIR / "skipped.yaml").symlink_to("skipped.missing.yaml")

    assert found(onto_cli, root) == []


def test_rules는_저장소_밖을_가리키는_ontology_yaml을_읽지_않고_컴파일처럼_오류로_알린다(onto_cli):
    """읽으면 다른 저장소의 `rules` 덮어쓰기가 이 저장소의 규칙으로 보인다. `validate`가 실제로 쓰는 규칙과 어긋난다."""
    mute = {"checks": {"orphan-page": {"enabled": False}}}
    root = onto_cli.root({"team": team_repo(), "secret": secret_repo(rules=mute)})
    link = root / "projects/team" / ONTOLOGY_DIR / "ontology.yaml"
    link.unlink()
    link.symlink_to(root / "projects/secret" / ONTOLOGY_DIR / "ontology.yaml")

    result = onto_cli.run(root, "rules", "team")

    assert result.returncode == 1
    assert yaml_file("team") in result.stderr and "심볼릭 링크" in result.stderr
    assert "orphan-page" not in result.stdout + result.stderr  # 다른 저장소의 설정은 읽지 않는다
    assert "Traceback" not in result.stderr


def test_rules는_가리키는_파일이_없어도_저장소_밖을_가리키는_ontology_yaml_링크를_읽지_않고_오류로_알린다(onto_cli):
    root = onto_cli.root({"team": team_repo()})
    link = root / "projects/team" / ONTOLOGY_DIR / "ontology.yaml"
    link.unlink()
    link.symlink_to("/Users/me/private-notes/ontology.yaml")

    result = onto_cli.run(root, "rules", "team")

    assert result.returncode == 1
    assert yaml_file("team") in result.stderr and "심볼릭 링크" in result.stderr


# --- 본문에 교차 참조 모양으로 쓴 링크 ---------------------------------------------------------
# `[글](<저장소 이름>:<식별자>)`는 관계의 값과 같은 교차 참조라 같은 규칙으로 공유 범위를 따진다.

BODY_CROSS_REFERENCES = {
    "인라인_링크": "[비밀](secret:component/x)",
    "이미지": "![그림](secret:component/x)",
    "참조_정의": "[설명][r]\n\n[r]: secret:component/x\n",
    "html_href": '<a href="secret:component/x">x</a>',
    "따옴표_없는_html_href": "<a href=secret:component/x>x</a>",
    "자동_링크": "<secret:component/x>",
    "조각이_붙은_링크": "[x](secret:component/x#section)",
    "공백이_든_저장소_이름": "[x]( secret:component/x )",
}


@pytest.mark.parametrize("body", BODY_CROSS_REFERENCES.values(), ids=BODY_CROSS_REFERENCES.keys())
def test_본문의_링크가_더_좁은_저장소를_교차_참조로_가리키면_scope_violation으로_잡는다(onto_cli, body):
    repos = {"team": team_repo(body), "secret": secret_repo()}

    result, findings = validate(onto_cli, onto_cli.root(repos))

    assert [finding[:4] for finding in findings] == [(ERROR, "team", file("component/b", "team"), "scope-violation")]
    assert "본문의 링크" in findings[0][4] and "secret:component/x" in findings[0][4]
    assert result.returncode == 1


def test_본문의_교차_참조_링크는_더_넓은_저장소와_같은_팀과_진짜_스킴이면_통과한다(onto_cli):
    body = (
        "[공개](open:component/x) [같은 팀](mate:component/x) [웹](https://example.com/secret:a) [메일](mailto:me@example.com) "
        "[http](http://example.com) [없는 저장소](ghost:component/x)\n"
    )
    repos = {
        "team": team_repo(body),
        "open": repo("open", page("component/x", "Component", title="공개 X", partOf="project"), scope="public"),
        "mate": repo("mate", page("component/x", "Component", title="팀 X", partOf="project"), scope="team:pay"),
    }

    assert violations(onto_cli, repos) == []


def test_본문의_교차_참조_링크도_다른_팀이면_잡고_name과_디렉토리_이름_어느_쪽이든_본다(onto_cli):
    repos = {
        "team": team_repo("[다른 팀](other:component/x) [이름](hidden:component/x)\n"),
        "other": repo("other", page("component/x", "Component", title="다른 X", partOf="project"), scope="team:legal"),
        "secret": secret_repo("hidden"),
    }

    assert violations(onto_cli, repos) == [(ERROR, "team", file("component/b", "team"), "scope-violation")] * 2


def test_인라인_코드_안의_주석_표시는_주석을_열지_않아_그_사이의_교차_참조_링크도_본다(onto_cli):
    body = "주석은 `<!--`로 열고 [y](secret:component/x)를 지나 `-->`로 닫는다.\n"
    repos = {"team": team_repo(body), "secret": secret_repo()}

    assert violations(onto_cli, repos) == [(ERROR, "team", file("component/b", "team"), "scope-violation")]


# --- class 값에 적은 교차 참조 모양 --------------------------------------------------------------
# `class: secret:Invoice`는 클래스를 풀지 못하는 값(`disallowed-class`)이다. 그 항목은 저장소 규칙으로 끌 수 있으므로, 끄더라도 비공개 저장소의
# 이름이 담긴 채 통과하지 않게 `class` 값의 `<저장소 이름>:<나머지>`도 관계의 값과 같은 규칙으로 공유 범위를 따진다.

MUTE_CLASS = {"checks": {"disallowed-class": {"enabled": False}, "misplaced-page": {"enabled": False}}}


def test_class_값이_더_좁은_저장소의_이름을_교차_참조_모양으로_담으면_scope_violation으로_잡는다(onto_cli):
    repos = {
        "team": repo("team", page("component/b", "secret:Invoice", title="B", partOf="project"), scope="team:pay", rules=MUTE_CLASS),
        "secret": secret_repo(),
    }

    findings = validate(onto_cli, onto_cli.root(repos))[1]

    assert [finding[:4] for finding in findings] == [(ERROR, "team", file("component/b", "team"), "scope-violation")]
    assert "`class`의 값 `secret:Invoice`" in findings[0][4]


def test_class_값의_저장소_이름이_더_넓은_저장소이거나_등록되지_않았으면_공유_범위를_따지지_않는다(onto_cli):
    repos = {
        "team": repo(
            "team",
            page("component/b", "open:Invoice", title="B", partOf="project"),
            page("component/c", "ghost:Invoice", title="C", partOf="project"),
            scope="team:pay",
            rules=MUTE_CLASS,
        ),
        "open": repo("open", page("component/x", "Component", title="공개 X", partOf="project"), scope="public"),
    }

    assert violations(onto_cli, repos) == []


# --- 원본 문서의 기록이 지식 저장소 밖을 가리킨다 ---------------------------------------------------------
# `derivedFrom`과 넘긴 문서의 목록(`skipped.yaml`)의 `path`는 지식 저장소 루트 기준이라 저장소 밖을 가리킬 수 없다. 모양이 틀렸다는 `invalid-value`와 `missing-source`는
# 저장소 규칙으로 끌 수 있으므로, 저장소 밖을 가리키는 경로는 루트 전용 `outside-link`로도 알린다. 끄고도 다른 저장소의 위치가 담긴 채 통과하지 않게 한다.

SOURCE_HASH = "0123456789abcdef0123456789abcdef01234567"
MUTE_SOURCES = {"checks": {"invalid-value": {"enabled": False}, "missing-source": {"enabled": False}, "missing-skipped-source": {"enabled": False}}}
OUTSIDE_SOURCE_PATHS = {
    "저장소_밖의_상위_디렉토리": "../shop/docs/design.md",
    "안으로_갔다_밖으로": "docs/../../shop/docs/design.md",
    "절대_경로": "/Users/me/notes/design.md",
    "윈도우_드라이브": "C:\\Users\\me\\design.md",
    "file_주소": "file:///Users/me/notes/design.md",
}
INSIDE_SOURCE_PATHS = {
    "원본_문서": "docs/design.md",
    "안으로_갔다_안으로": "docs/api/../design.md",  # 모양은 틀리지만(invalid-value) 저장소 안이다
    "웹_주소": "https://example.com/design.md",  # 파일이 아니다
}


def sourced(path: str, **project) -> dict[str, dict[str, str]]:
    """`billing`의 페이지 하나가 `path`를 근거로 삼는다. 이 견본은 `invalid-value`와 `missing-source`를 끈다."""
    gateway = page("component/gateway", "Component", title="게이트웨이", partOf="project", derivedFrom=[{"path": path, "hash": SOURCE_HASH}])
    return {"billing": repo("billing", gateway, rules=MUTE_SOURCES, **project)}


@pytest.mark.parametrize("path", OUTSIDE_SOURCE_PATHS.values(), ids=OUTSIDE_SOURCE_PATHS.keys())
def test_derivedFrom의_경로가_지식_저장소_밖을_가리키면_값_검사를_꺼도_outside_link로_잡는다(onto_cli, path):
    root = onto_cli.root(sourced(path))

    result, findings = validate(onto_cli, root)

    assert [finding[:4] for finding in findings] == [(ERROR, "billing", file("component/gateway"), "outside-link")]
    assert "derivedFrom" in findings[0][4] and path in findings[0][4]
    assert result.returncode == 1


@pytest.mark.parametrize("path", INSIDE_SOURCE_PATHS.values(), ids=INSIDE_SOURCE_PATHS.keys())
def test_derivedFrom의_경로가_지식_저장소_안이거나_파일이_아니면_outside_link가_아니다(onto_cli, path):
    assert [finding[3] for finding in validate(onto_cli, onto_cli.root(sourced(path)))[1]] == []


def test_derivedFrom의_경로가_밖을_가리키면_값의_종류_오류와_함께_둘_다_보고한다(onto_cli):
    """값 검사를 끄지 않으면 모양 오류(`invalid-value`)와 저장소 밖(`outside-link`)이 서로 다른 항목으로 나란히 보고된다."""
    bad = page("component/gateway", "Component", title="게이트웨이", partOf="project", derivedFrom=[{"path": "../shop/docs/design.md", "hash": SOURCE_HASH}])

    result, findings = validate(onto_cli, onto_cli.root({"billing": repo("billing", bad)}))

    assert sorted(finding[3] for finding in findings) == ["invalid-value", "outside-link"]
    assert result.returncode == 1


def test_저장소_밖을_가리키는_derivedFrom_항목이_여럿이어도_경로마다_한_번씩_보고한다(onto_cli):
    entries = [{"path": "../a.md", "hash": SOURCE_HASH}, {"path": "../a.md", "hash": SOURCE_HASH}, {"path": "/b.md", "hash": SOURCE_HASH}, {"path": "docs/design.md", "hash": SOURCE_HASH}]
    gateway = page("component/gateway", "Component", title="게이트웨이", partOf="project", derivedFrom=entries)

    findings = validate(onto_cli, onto_cli.root({"billing": repo("billing", gateway, rules=MUTE_SOURCES)}))[1]

    assert [finding[3] for finding in findings] == ["outside-link", "outside-link"]
    assert "../a.md" in findings[0][4] and "/b.md" in findings[1][4]


def skipped(path: str) -> dict[str, dict[str, str]]:
    """`billing`의 넘긴 문서의 목록이 `path`를 적는다. 이 견본은 `invalid-value`와 `missing-skipped-source`를 끈다."""
    files = repo("billing", rules=MUTE_SOURCES)
    files[f"{ONTOLOGY_DIR}/skipped.yaml"] = json.dumps([{"path": path, "hash": SOURCE_HASH}], ensure_ascii=False) + "\n"
    return {"billing": files}


@pytest.mark.parametrize("path", OUTSIDE_SOURCE_PATHS.values(), ids=OUTSIDE_SOURCE_PATHS.keys())
def test_넘긴_문서의_목록의_경로가_지식_저장소_밖을_가리키면_값_검사를_꺼도_outside_link로_잡는다(onto_cli, path):
    root = onto_cli.root(skipped(path))

    result, findings = validate(onto_cli, root)

    assert [finding[:4] for finding in findings] == [(ERROR, "billing", f"projects/billing/{ONTOLOGY_DIR}/skipped.yaml", "outside-link")]
    assert path in findings[0][4]
    assert result.returncode == 1


@pytest.mark.parametrize("path", INSIDE_SOURCE_PATHS.values(), ids=INSIDE_SOURCE_PATHS.keys())
def test_넘긴_문서의_목록의_경로가_지식_저장소_안이거나_파일이_아니면_outside_link가_아니다(onto_cli, path):
    assert [finding[3] for finding in validate(onto_cli, onto_cli.root(skipped(path)))[1]] == []


def test_저장소_밖을_가리키는_원본_문서의_기록은_지식_저장소_안에서도_보고한다(onto_cli):
    """`outside-link`는 한 저장소만으로 판단할 수 있어 지식 저장소 안(`--within repository`)에서도 돈다."""
    files = sourced("../shop/docs/design.md")["billing"]
    repository = onto_cli.repository("billing", files)

    result = onto_cli.run(repository, "validate", within=REPOSITORY)

    assert [line.split("\t")[3] for line in result.stdout.splitlines()] == ["outside-link"]
    assert result.returncode == 1


# --- 정의되지 않은 키와 값의 종류가 틀린 관계의 값 ---------------------------------------------------
# `undefined-key`, `invalid-value`, `reverse-relation`도 저장소 규칙으로 끌 수 있어, 그 값에 든 교차 참조 모양도 중첩까지 훑어 공유 범위를 따진다. 제목, 설명, 날짜, 별칭은 보지 않는다.

MUTE_UNDEFINED = {"checks": {"undefined-key": {"enabled": False}, "invalid-value": {"enabled": False}, "reverse-relation": {"enabled": False}}}


def with_fields(**fields) -> dict[str, dict[str, str]]:
    """`team`의 페이지 `component/b`가 `fields`를 가진다. 이 견본의 규칙은 `undefined-key`, `invalid-value`, `reverse-relation`을 끈다."""
    page_fields = {"partOf": "project", **fields}
    return {"team": repo("team", page("component/b", "Component", title="B", **page_fields), scope="team:pay", rules=MUTE_UNDEFINED), "secret": secret_repo()}


UNCHECKED_FIELDS = {
    "정의되지_않은_키의_문자열": {"notes": "secret:component/x"},
    "정의되지_않은_키의_목록": {"notes": ["메모", "secret:component/x"]},
    "정의되지_않은_키의_중첩된_값": {"notes": {"links": [{"to": "secret:component/x"}]}},
    "문자열이_아닌_관계의_값": {"dependsOn": {"id": "secret:component/x"}},
    "관계의_목록_안의_중첩된_값": {"dependsOn": ["component/b", {"id": "secret:component/x"}]},
    "역방향_관계_키": {"hasPart": "secret:component/x"},
    # 참조가 키-값의 값이 아니라 키에 적힐 수도 있다.
    "정의되지_않은_최상위_키": {"secret:component/x": "메모"},
    "정의되지_않은_키의_중첩된_키": {"notes": {"secret:component/x": "메모"}},
    "정의되지_않은_키의_목록_안의_중첩된_키": {"notes": [{"links": {"secret:component/x": 1}}]},
    "문자열이_아닌_관계의_값의_키": {"dependsOn": {"secret:component/x": "메모"}},
}


@pytest.mark.parametrize("fields", UNCHECKED_FIELDS.values(), ids=UNCHECKED_FIELDS.keys())
def test_끌_수_있는_항목이_보고하는_값에_든_더_좁은_저장소의_교차_참조도_scope_violation으로_잡는다(onto_cli, fields):
    result, findings = validate(onto_cli, onto_cli.root(with_fields(**fields)))

    assert [finding[:4] for finding in findings] == [(ERROR, "team", file("component/b", "team"), "scope-violation")]
    assert "secret:component/x" in findings[0][4]
    assert result.returncode == 1


def test_정의되지_않은_키의_값이_더_넓은_저장소나_등록되지_않은_이름이거나_주소이면_공유_범위를_따지지_않는다(onto_cli):
    repos = {
        "team": repo(
            "team",
            page("component/b", "Component", title="B", partOf="project", notes=["open:component/x", "ghost:component/x", "https://example.com/a", "비율: 3:1"]),
            scope="team:pay",
            rules=MUTE_UNDEFINED,
        ),
        "open": repo("open", page("component/x", "Component", title="공개 X", partOf="project"), scope="public"),
    }

    assert violations(onto_cli, repos) == []


def test_제목_설명_별칭에_적은_저장소_이름은_보지_않는다(onto_cli):
    """참조가 아닌 글이다. 한계로 문서화되어 있다(규약 문서의 공유 범위 검사의 한계)."""
    fields = {"title": "secret:component/x", "description": "secret:component/x를 가리키는 글", "aliases": ["secret:component/x"]}
    repos = {"team": repo("team", page("component/b", "Component", partOf="project", **fields), scope="team:pay"), "secret": secret_repo()}

    assert violations(onto_cli, repos) == []


def test_본문의_교차_참조_링크는_코드_안이면_보지_않는다(onto_cli):
    repos = {"team": team_repo("`[x](secret:component/x)`\n\n```\n[y](secret:component/x)\n```\n"), "secret": secret_repo()}

    assert violations(onto_cli, repos) == []


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
