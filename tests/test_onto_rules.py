"""규칙: 루트 기본값(`rules.yaml`)과 지식 저장소의 덮어쓰기(`ontology.yaml`의 `rules`).

온톨로지 도구의 명령줄 진입점을 견본 페이지 디렉토리에 대고 실행한다(`onto_cli`). 루트 기본 규칙은 도구 디렉토리 안의 파일이라
테스트가 `onto_cli.set_root_check`로 고치고, 테스트가 끝나면 되돌려진다.

규칙으로 바뀌는 것은 스크립트 검사(`validate`)의 보고와 종료 코드다. 규칙의 값은 `rules` 명령이 JSON으로 보여 준다.
"""

import json

import pytest

from support.onto_cli import ONTOLOGY_DIR, page, repo, snapshot

ERROR = "오류"
WARNING = "경고"

# #8이 정한 검사 항목의 기본 심각도. 규칙 파일로 옮겨진 값이 이것과 같아야 한다.
DEFAULT_SEVERITIES = {
    "unreadable-file": "error",
    "invalid-value": "error",
    "invalid-class-declaration": "error",
    "invalid-identifier": "error",
    "misplaced-page": "error",
    "misnamed-page": "error",
    "missing-property": "error",
    "disallowed-class": "error",
    "relation-domain": "error",
    "relation-range": "error",
    "undefined-key": "error",
    "reverse-relation": "error",
    "broken-reference": "error",
    "unregistered-repository": "error",
    "orphan-page": "warning",
    "duplicate-entity": "error",
    "duplicate-entity-across-repositories": "warning",
    "repository-name-mismatch": "error",
    "missing-ontology-layer": "warning",
}


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


def idle_and_stray(**project):
    """고아 페이지(`orphan-page`, 기본은 경고)와 정의되지 않은 키(`undefined-key`, 기본은 오류)가 하나씩 있는 지식 저장소."""
    return repo(
        "billing",
        page("term/idle", "Term", title="한가한 용어"),
        page("component/api", "Component", title="API", partOf="project", owner="kim"),
        **project,
    )


# --- 루트 기본 규칙: 검사 항목 켬/끔과 심각도 -----------------------------------


def test_루트_기본_규칙으로_검사_항목을_끄면_그_항목은_보고되지_않는다(onto_cli):
    root = onto_cli.root({"billing": idle_and_stray()})
    assert found(onto_cli, root) == [
        (ERROR, "billing", file("component/api"), "undefined-key"),
        (WARNING, "billing", file("term/idle"), "orphan-page"),
    ]

    onto_cli.set_root_check("orphan-page", enabled=False)

    assert found(onto_cli, root) == [(ERROR, "billing", file("component/api"), "undefined-key")]


def test_루트_기본_규칙으로_오류_항목을_끄면_오류만_있던_견본이_통과한다(onto_cli):
    root = onto_cli.root({"billing": idle_and_stray()})
    assert onto_cli.run(root, "validate").returncode == 1

    onto_cli.set_root_check("undefined-key", enabled=False)

    result, findings = validate(onto_cli, root)
    assert [f[3] for f in findings] == ["orphan-page"]
    assert result.returncode == 0


def test_루트_기본_규칙으로_경고를_오류로_올리면_종료_코드가_1이_된다(onto_cli):
    root = onto_cli.root({"billing": repo("billing", page("term/idle", "Term", title="한가한 용어"))})
    assert validate(onto_cli, root)[0].returncode == 0

    onto_cli.set_root_check("orphan-page", severity="error")

    result, findings = validate(onto_cli, root)
    assert [f[:4] for f in findings] == [(ERROR, "billing", file("term/idle"), "orphan-page")]
    assert result.returncode == 1


def test_루트_기본_규칙으로_오류를_경고로_내리면_종료_코드가_0이_된다(onto_cli):
    root = onto_cli.root({"billing": repo("billing", page("component/api", "Component", title="API", partOf="project", owner="kim"))})
    assert validate(onto_cli, root)[0].returncode == 1

    onto_cli.set_root_check("undefined-key", severity="warning")

    result, findings = validate(onto_cli, root)
    assert [f[:4] for f in findings] == [(WARNING, "billing", file("component/api"), "undefined-key")]
    assert result.returncode == 0
    assert "오류 0개, 경고 1개" in result.stderr


# --- 규칙의 내용: 키와 기본값 --------------------------------------------------


def rules_of(onto_cli, root, *repository: str) -> dict:
    """`rules` 명령이 보여 주는 규칙. 지식 저장소를 주면 그 저장소에 적용되는 규칙이다."""
    result = onto_cli.run(root, "rules", *repository)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_루트_기본_규칙에_ingest_대상_검사_항목_푸시_관문_중복_처리_언어_규칙의_키와_기본값이_있다(onto_cli):
    rules = rules_of(onto_cli, onto_cli.root({}))

    assert list(rules) == ["sources", "checks", "push-gate", "duplicates", "language"]
    assert rules["push-gate"] == {"enabled": True}
    assert rules["duplicates"] == {"compare": ["title", "aliases"], "ignore-case": True, "ignore-whitespace": True}
    assert rules["language"] == {"identifier-pattern": "[a-z0-9-]+", "body": "source", "aliases": ["ko", "en"]}


def test_ingest_대상의_기본값은_docs_아래_md_파일이고_온톨로지_층은_제외된다(onto_cli):
    rules = rules_of(onto_cli, onto_cli.root({}))

    assert rules["sources"] == {"include": ["docs/**/*.md"], "exclude": ["docs/ontology/**"]}


def test_8의_기본_심각도가_루트_기본_규칙의_값으로_옮겨져_있고_모든_항목이_켜져_있다(onto_cli):
    checks = rules_of(onto_cli, onto_cli.root({}))["checks"]

    assert {name: rule["severity"] for name, rule in checks.items()} == {
        **DEFAULT_SEVERITIES,
        "invalid-ontology-yaml": "error",
        "invalid-rules": "error",
        "duplicate-repository-name": "error",
        "index-mismatch": "error",
        # #10이 더한 원본 문서의 기록 검사
        "stale-page": "warning",
        "missing-source": "warning",
        "missing-skipped-source": "warning",
        # #14가 더한 공유 범위 검사(루트 전용)
        "invalid-scope": "error",
        "scope-violation": "error",
        "path-reference": "error",
        "outside-link": "error",
        # #13이 더한 뒤처진 루트 관리 파일 검사(경고)
        "outdated-managed-files": "warning",
    }
    assert all(rule["enabled"] is True for rule in checks.values())


def test_규칙_명령은_어떤_파일도_고치거나_만들지_않는다(onto_cli):
    root = onto_cli.root({"billing": idle_and_stray(rules={"checks": {"orphan-page": {"enabled": False}}})})
    before = snapshot(root)

    assert onto_cli.run(root, "rules").returncode == 0
    assert onto_cli.run(root, "rules", "billing").returncode == 0

    assert snapshot(root) == before
    assert not onto_cli.build_dir.exists()


# --- 지식 저장소의 덮어쓰기 -----------------------------------------------------


def test_지식_저장소의_ontology_yaml이_덮어쓴_규칙은_그_저장소에만_적용된다(onto_cli):
    repos = {
        "billing": repo("billing", page("term/idle", "Term", title="한가한 용어"), rules={"checks": {"orphan-page": {"enabled": False}}}),
        "shop": repo("shop", page("term/idle", "Term", title="놀고 있는 용어")),
    }

    findings = found(onto_cli, onto_cli.root(repos))

    assert findings == [(WARNING, "shop", file("term/idle", "shop"), "orphan-page")]


def test_지식_저장소가_심각도를_덮어쓰면_그_저장소의_종료_코드에_반영된다(onto_cli):
    stray = page("component/api", "Component", title="API", partOf="project", owner="kim")
    lenient = {"billing": repo("billing", stray, rules={"checks": {"undefined-key": {"severity": "warning"}}})}
    default = {"billing": repo("billing", stray)}

    lenient_result, lenient_findings = validate(onto_cli, onto_cli.root(lenient))
    default_result, _ = validate(onto_cli, onto_cli.root(default))

    assert [f[0] for f in lenient_findings] == [WARNING]
    assert (lenient_result.returncode, default_result.returncode) == (0, 1)


def test_덮어쓰지_않은_항목은_루트_기본값을_따르고_루트_기본값이_바뀌면_함께_바뀐다(onto_cli):
    root = onto_cli.root({"billing": idle_and_stray(rules={"checks": {"orphan-page": {"enabled": False}}})})
    assert found(onto_cli, root) == [(ERROR, "billing", file("component/api"), "undefined-key")]

    onto_cli.set_root_check("undefined-key", severity="warning")

    assert found(onto_cli, root) == [(WARNING, "billing", file("component/api"), "undefined-key")]


def test_덮어쓰기는_적은_값만_바꾸고_나머지_값은_루트_기본값으로_남는다(onto_cli):
    """루트가 `orphan-page`를 끈 채 저장소가 심각도만 덮어쓰면 여전히 꺼져 있다. 저장소가 켜면 루트의 심각도(경고)로 보고된다."""
    idle = page("term/idle", "Term", title="한가한 용어")
    onto_cli.set_root_check("orphan-page", enabled=False)
    severity_only = onto_cli.root({"billing": repo("billing", idle, rules={"checks": {"orphan-page": {"severity": "error"}}})})
    enabled_only = onto_cli.root({"billing": repo("billing", idle, rules={"checks": {"orphan-page": {"enabled": True}}})})

    assert found(onto_cli, severity_only) == []
    assert found(onto_cli, enabled_only) == [(WARNING, "billing", file("term/idle"), "orphan-page")]


def test_규칙_명령은_저장소가_덮어쓴_값을_합친_규칙을_보여_주고_덮어쓰지_않은_저장소는_기본값을_보여_준다(onto_cli):
    override = {
        "sources": {"include": ["docs/**/*.md", "design/**/*.md"]},
        "checks": {"orphan-page": {"enabled": False}},
        "language": {"body": "ko"},
    }
    root = onto_cli.root({"billing": repo("billing", rules=override), "shop": repo("shop")})
    default = rules_of(onto_cli, root)

    billing = rules_of(onto_cli, root, "billing")

    assert billing["sources"] == {"include": ["docs/**/*.md", "design/**/*.md"], "exclude": ["docs/ontology/**"]}
    assert billing["checks"]["orphan-page"] == {"enabled": False, "severity": "warning"}
    assert billing["language"] == {"identifier-pattern": "[a-z0-9-]+", "body": "ko", "aliases": ["ko", "en"]}
    assert {**billing, "sources": None, "language": None, "checks": None} == {**default, "sources": None, "language": None, "checks": None}
    assert rules_of(onto_cli, root, "shop") == default


def test_규칙_명령은_없는_지식_저장소를_알린다(onto_cli):
    result = onto_cli.run(onto_cli.root({"billing": repo("billing")}), "rules", "ghost")

    assert result.returncode == 1
    assert "ghost" in result.stderr and "billing" in result.stderr


# --- 루트 전용 규칙 -------------------------------------------------------------


def test_푸시_관문을_지식_저장소에서_덮어쓰려_하면_오류로_알리고_그_저장소는_루트_기본_규칙으로_검사한다(onto_cli):
    """덮어쓰기가 틀리면 통째로 쓰지 않는다. 같이 적은 다른 덮어쓰기(`orphan-page` 끄기)도 적용되지 않는다."""
    override = {"push-gate": {"enabled": False}, "checks": {"orphan-page": {"enabled": False}}}
    root = onto_cli.root({"billing": repo("billing", page("term/idle", "Term", title="한가한 용어"), rules=override)})

    result, findings = validate(onto_cli, root)

    assert [f[:4] for f in findings] == [
        (ERROR, "billing", yaml_file(), "invalid-rules"),
        (WARNING, "billing", file("term/idle"), "orphan-page"),
    ]
    assert "push-gate" in findings[0][4] and "루트 전용" in findings[0][4]  # 어느 규칙이 왜 안 되는지 알려 준다
    assert result.returncode == 1


def test_푸시_관문은_지식_저장소가_덮어쓰지_못하고_루트_기본_규칙의_값이_그대로_적용된다(onto_cli):
    root = onto_cli.root({"billing": repo("billing", rules={"push-gate": {"enabled": False}})})

    assert rules_of(onto_cli, onto_cli.root({}))["push-gate"] == {"enabled": True}
    result = onto_cli.run(root, "rules", "billing")

    assert result.returncode == 1
    assert yaml_file() in result.stderr and "rules.push-gate" in result.stderr and "루트 전용" in result.stderr


def test_루트_기본_규칙으로는_푸시_관문을_끌_수_있다(onto_cli):
    onto_cli.replace_in_root_rules("push-gate:\n  enabled: true", "push-gate:\n  enabled: false")

    assert rules_of(onto_cli, onto_cli.root({}))["push-gate"] == {"enabled": False}


# --- 모르는 키와 틀린 값 --------------------------------------------------------


def test_루트_기본_규칙에_모르는_키가_있으면_파일과_키_이름을_알리며_오류로_끝난다(onto_cli):
    onto_cli.write_root_rules(onto_cli.root_rules() + "\npush-gates:\n  enabled: true\n")
    root = onto_cli.root({"billing": idle_and_stray()})

    result = onto_cli.run(root, "validate")

    assert result.returncode == 1
    assert result.stdout == ""  # 규칙을 믿을 수 없으면 검사하지 않는다
    assert "rules.yaml" in result.stderr and "`push-gates`" in result.stderr and "push-gate" in result.stderr


@pytest.mark.parametrize("command", [["validate"], ["rules"]])
def test_루트_기본_규칙의_오류는_규칙을_읽는_모든_명령이_같이_알린다(onto_cli, command):
    onto_cli.replace_in_root_rules("  orphan-page: {enabled: true, severity: warning}", "  orphan-pagee: {enabled: true, severity: warning}")

    result = onto_cli.run(onto_cli.root({}), *command)

    assert result.returncode == 1
    assert "rules.yaml" in result.stderr
    assert "`checks.orphan-pagee`" in result.stderr  # 모르는 검사 항목의 이름
    assert "혹시 `orphan-page`" in result.stderr  # 오타 같으면 맞는 이름을 알려 준다
    assert "`checks.orphan-page`" in result.stderr and "없다" in result.stderr  # 빠진 항목도 함께 알린다


def test_루트_기본_규칙에서_빠진_검사_항목이_있으면_알린다(onto_cli):
    onto_cli.replace_in_root_rules("  misnamed-page: {enabled: true, severity: error}\n", "")

    result = onto_cli.run(onto_cli.root({}), "validate")

    assert result.returncode == 1
    assert "`checks.misnamed-page`" in result.stderr and "없다" in result.stderr


@pytest.mark.parametrize(
    ("old", "new", "key"),
    [
        ("  orphan-page: {enabled: true, severity: warning}", "  orphan-page: {enabled: true, severity: fatal}", "checks.orphan-page.severity"),
        ("  orphan-page: {enabled: true, severity: warning}", "  orphan-page: {enabled: yes please, severity: warning}", "checks.orphan-page.enabled"),
        ("  orphan-page: {enabled: true, severity: warning}", "  orphan-page: {enabled: true, severity: warning, level: 3}", "checks.orphan-page.level"),
        ("  enabled: true\n\n# 중복", "  enabled: 1\n\n# 중복", "push-gate.enabled"),
        ("    - \"docs/**/*.md\"", "    - \"/etc/*.md\"", "sources.include"),
        ("    - \"docs/**/*.md\"", "    - \"../other/**/*.md\"", "sources.include"),
        ("  compare: [title, aliases]", "  compare: [title, description]", "duplicates.compare"),
        ("  identifier-pattern: \"[a-z0-9-]+\"", "  identifier-pattern: \"[a-z\"", "language.identifier-pattern"),
        ("  aliases: [ko, en]", "  aliases: ko", "language.aliases"),
    ],
    ids=["심각도_값", "켬끔_값", "항목의_모르는_키", "푸시_관문_값", "절대_경로_글롭", "저장소_밖_글롭", "비교할_속성", "정규_표현식", "별칭_언어"],
)
def test_루트_기본_규칙의_값이_틀리면_키_이름을_알리며_오류로_끝난다(onto_cli, old, new, key):
    onto_cli.replace_in_root_rules(old, new)

    result = onto_cli.run(onto_cli.root({}), "rules")

    assert result.returncode == 1
    assert f"`{key}`" in result.stderr and "rules.yaml" in result.stderr


def test_ontology_yaml에_모르는_키가_있으면_파일과_키_이름을_알리며_오류로_보고한다(onto_cli):
    root = onto_cli.root({"billing": repo("billing", page("component/api", "Component", title="API", partOf="project"), titel="결제")})

    result, findings = validate(onto_cli, root)

    assert [f[:4] for f in findings] == [(ERROR, "billing", yaml_file(), "invalid-ontology-yaml")]
    assert "`titel`" in findings[0][4]
    assert result.returncode == 1


def test_ontology_yaml에_모르는_키가_있으면_컴파일도_멈춘다(onto_cli):
    """오타 때문에 값이 조용히 무시되지 않는다. build도 질의도 같은 문제로 끝난다."""
    root = onto_cli.root({"billing": repo("billing", titel="결제")})

    for command in (["build"], ["query", "ASK { ?s ?p ?o }"]):
        result = onto_cli.run(root, *command)
        assert result.returncode == 1, command
        assert yaml_file() in result.stderr and "`titel`" in result.stderr


def test_ontology_yaml의_허용_키는_공유_범위와_규칙_덮어쓰기를_포함한다(onto_cli):
    root = onto_cli.root(
        {
            "billing": repo(
                "billing",
                title="결제",
                description="결제 프로젝트",
                aliases=["pay"],
                classes={"Invoice": {"subClassOf": "Component"}},
                scope="team:payments",
                rules={"checks": {"orphan-page": {"enabled": False}}},
            )
        }
    )

    assert validate(onto_cli, root)[1] == []


@pytest.mark.parametrize(
    ("rules", "key"),
    [
        ({"checks": {"orphan-pagee": {"enabled": False}}}, "rules.checks.orphan-pagee"),
        ({"checks": {"orphan-page": {"severity": "fatal"}}}, "rules.checks.orphan-page.severity"),
        ({"checks": {"orphan-page": {"level": "error"}}}, "rules.checks.orphan-page.level"),
        ({"source": {"include": ["docs/**/*.md"]}}, "rules.source"),
        ({"sources": {"include": ["../x/*.md"]}}, "rules.sources.include"),
        ({"duplicates": {"ignore-case": "no"}}, "rules.duplicates.ignore-case"),
        ({"language": {"identifier-pattern": "["}}, "rules.language.identifier-pattern"),
        ({"checks": ["orphan-page"]}, "rules.checks"),
        ([{"checks": {}}], "rules"),
        ("orphan-page", "rules"),
    ],
    ids=["모르는_검사_항목", "심각도_값", "항목의_모르는_키", "모르는_규칙", "저장소_밖_글롭", "논리값", "정규_표현식", "목록", "최상위가_목록", "최상위가_문자열"],
)
def test_ontology_yaml의_rules가_틀리면_키_이름을_알리며_오류로_보고하고_루트_기본_규칙으로_검사한다(onto_cli, rules, key):
    root = onto_cli.root({"billing": repo("billing", page("term/idle", "Term", title="한가한 용어"), rules=rules)})

    result, findings = validate(onto_cli, root)

    assert [f[:4] for f in findings] == [
        (ERROR, "billing", yaml_file(), "invalid-rules"),
        (WARNING, "billing", file("term/idle"), "orphan-page"),
    ]
    assert f"`{key}`" in findings[0][4]
    assert result.returncode == 1


def test_rules가_비어_있어도_오류가_아니다(onto_cli):
    root = onto_cli.root({"billing": repo("billing", rules=None), "shop": repo("shop", rules={})})

    assert validate(onto_cli, root)[1] == []


def test_틀린_rules는_저장소_하나의_문제이고_다른_저장소의_덮어쓰기는_적용된다(onto_cli):
    repos = {
        "billing": repo("billing", rules={"checks": {"orphan-pagee": {}}}),
        "shop": repo("shop", page("term/idle", "Term", title="한가한 용어"), rules={"checks": {"orphan-page": {"enabled": False}}}),
    }

    assert found(onto_cli, onto_cli.root(repos)) == [(ERROR, "billing", yaml_file(), "invalid-rules")]


def test_invalid_rules도_루트_기본_규칙으로_끄거나_심각도를_바꿀_수_있다(onto_cli):
    root = onto_cli.root({"billing": repo("billing", rules={"push-gate": {"enabled": False}})})
    onto_cli.set_root_check("invalid-rules", severity="warning")

    result, findings = validate(onto_cli, root)

    assert [f[:4] for f in findings] == [(WARNING, "billing", yaml_file(), "invalid-rules")]
    assert result.returncode == 0


# --- 규칙이 검사에 쓰이는 곳: 언어 규칙의 식별자 형식, 중복 처리 ----------------------


def underscore_page():
    return page("plan/auth_redesign", "Plan", title="인증 재설계", about="project")


def test_언어_규칙의_식별자_형식을_루트_기본_규칙으로_바꾸면_검사가_따른다(onto_cli):
    root = onto_cli.root({"billing": repo("billing", underscore_page())})
    assert [f[3] for f in validate(onto_cli, root)[1]] == ["invalid-identifier"]

    onto_cli.replace_in_root_rules('identifier-pattern: "[a-z0-9-]+"', 'identifier-pattern: "[a-z0-9_-]+"')

    assert validate(onto_cli, root)[1] == []


def test_식별자_형식은_루트_전용이라_지식_저장소가_덮어쓰려_하면_오류로_거부하고_루트_기본_형식으로_검사한다(onto_cli):
    """식별자 형식은 교차 참조의 문법이기도 하고 사용자가 쓴 정규 표현식이라, 지식 저장소 하나가 루트의 검사를 멈추지 못하게 루트만 정한다."""
    lenient = {"language": {"identifier-pattern": "[a-z0-9_-]+"}}
    repos = {
        "billing": repo("billing", underscore_page(), rules=lenient),
        "shop": repo("shop", page("plan/launch_plan", "Plan", title="출시 계획", about="project")),
    }

    result, findings = validate(onto_cli, onto_cli.root(repos))

    assert sorted(f[:4] for f in findings) == [
        (ERROR, "billing", yaml_file(), "invalid-rules"),
        (ERROR, "billing", file("plan/auth_redesign"), "invalid-identifier"),  # 덮어쓰기는 버려지고 루트 기본 형식으로 검사한다
        (ERROR, "shop", file("plan/launch_plan", "shop"), "invalid-identifier"),
    ]
    invalid = next(f for f in findings if f[3] == "invalid-rules")
    assert "`rules.language.identifier-pattern`" in invalid[4] and "루트 전용" in invalid[4]
    assert result.returncode == 1


def test_규칙_명령은_식별자_형식을_덮어쓰려는_저장소를_오류로_끝낸다(onto_cli):
    root = onto_cli.root({"billing": repo("billing", rules={"language": {"identifier-pattern": "[a-z0-9_-]+"}})})

    result = onto_cli.run(root, "rules", "billing")

    assert result.returncode == 1
    assert yaml_file() in result.stderr and "rules.language.identifier-pattern" in result.stderr and "루트 전용" in result.stderr


def test_식별자_오류의_설명은_적용된_식별자_형식을_알린다(onto_cli):
    onto_cli.replace_in_root_rules('identifier-pattern: "[a-z0-9-]+"', 'identifier-pattern: "[a-z0-9]+"')
    root = onto_cli.root({"billing": repo("billing", underscore_page())})

    message = next(f[4] for f in validate(onto_cli, root)[1] if f[3] == "invalid-identifier")

    assert "[a-z0-9]+" in message and "auth_redesign" in message


def test_식별자_형식이_대문자를_허용하는_저장소에서도_다른_디렉토리의_페이지는_디렉토리_오류가_남는다(onto_cli):
    """`Plan/`이 식별자 형식에 어긋나지 않으면 식별자 항목이 대신 보고하지 않으므로, 클래스별 디렉토리 항목이 보고한다."""
    onto_cli.replace_in_root_rules('identifier-pattern: "[a-z0-9-]+"', 'identifier-pattern: "[A-Za-z0-9-]+"')
    root = onto_cli.root({"billing": repo("billing", page("Plan/lower", "Plan", title="계획", about="project"))})

    assert [f[3] for f in validate(onto_cli, root)[1]] == ["misplaced-page"]


def ledger_pair():
    return [
        page("component/a", "Component", title="API Gateway", aliases=["PG"], partOf="project"),
        page("component/b", "Component", title="api gateway", partOf="project"),
    ]


def test_중복_처리의_대소문자_구분을_루트_기본_규칙으로_바꾸면_검사가_따른다(onto_cli):
    root = onto_cli.root({"billing": repo("billing", *ledger_pair())})
    assert [f[3] for f in validate(onto_cli, root)[1]] == ["duplicate-entity", "duplicate-entity"]

    onto_cli.replace_in_root_rules("ignore-case: true", "ignore-case: false")

    assert validate(onto_cli, root)[1] == []


def test_중복_처리의_공백_구분을_루트_기본_규칙으로_바꾸면_검사가_따른다(onto_cli):
    spaced = [
        page("component/a", "Component", title="결제 게이트웨이", partOf="project"),
        page("component/b", "Component", title="결제게이트웨이", partOf="project"),
    ]
    root = onto_cli.root({"billing": repo("billing", *spaced)})
    assert [f[3] for f in validate(onto_cli, root)[1]] == ["duplicate-entity", "duplicate-entity"]

    onto_cli.replace_in_root_rules("ignore-whitespace: true", "ignore-whitespace: false")

    assert validate(onto_cli, root)[1] == []


def test_중복_처리가_비교하는_속성을_제목으로_좁히면_별칭이_같아도_중복이_아니다(onto_cli):
    by_alias = [
        page("component/a", "Component", title="하나", aliases=["PG"], partOf="project"),
        page("component/b", "Component", title="둘", aliases=["pg"], partOf="project"),
    ]
    root = onto_cli.root({"billing": repo("billing", *by_alias)})
    assert [f[3] for f in validate(onto_cli, root)[1]] == ["duplicate-entity", "duplicate-entity"]

    onto_cli.replace_in_root_rules("compare: [title, aliases]", "compare: [title]")

    assert validate(onto_cli, root)[1] == []


def test_중복_처리를_지식_저장소가_덮어쓰면_그_저장소의_엔티티만_달라진다(onto_cli):
    strict = {"duplicates": {"ignore-case": False}}
    repos = {
        "billing": repo("billing", *ledger_pair(), rules=strict),
        "shop": repo("shop", page("component/a", "Component", title="Order Book", partOf="project"), page("component/b", "Component", title="order book", partOf="project")),
    }

    findings = found(onto_cli, onto_cli.root(repos))

    assert findings == [
        (ERROR, "shop", file("component/a", "shop"), "duplicate-entity"),
        (ERROR, "shop", file("component/b", "shop"), "duplicate-entity"),
    ]


# --- S1-08 리뷰 지적 -----------------------------------------------------------


def stray_page():
    return page("component/api", "Component", title="API", partOf="project", owner="kim")


MUTE_UNDEFINED_KEY = {"checks": {"undefined-key": {"enabled": False}}}


@pytest.mark.parametrize(
    "mute",
    [{"checks": {"undefined-key": {"enabled": False}}}, {"checks": {"undefined-key": {"severity": "warning"}}}],
    ids=["끄기", "경고로_낮추기"],
)
def test_저장소가_undefined_key를_꺼도_ontology_yaml의_모르는_키는_오류로_보고하고_build도_같은_이유로_멈춘다(onto_cli, mute):
    """`ontology.yaml`은 규칙을 담은 파일이다. 그 파일의 오타를 저장소가 자기 규칙으로 묻지 못한다. 페이지의 팀 고유 키는 묻을 수 있다."""
    root = onto_cli.root({"billing": repo("billing", stray_page(), scpoe="team", rules=mute)})

    result, findings = validate(onto_cli, root)
    build = onto_cli.run(root, "build")

    ontology_yaml_findings = [f for f in findings if f[2] == yaml_file()]
    assert [f[:4] for f in ontology_yaml_findings] == [(ERROR, "billing", yaml_file(), "invalid-ontology-yaml")]
    assert "`scpoe`" in ontology_yaml_findings[0][4]
    assert result.returncode == 1
    assert build.returncode == 1 and "`scpoe`" in build.stderr  # validate가 오류로 보는 문제로 build도 멈춘다


def test_저장소가_undefined_key를_끄면_페이지의_모르는_키만_보고되지_않는다(onto_cli):
    root = onto_cli.root({"billing": repo("billing", stray_page(), rules=MUTE_UNDEFINED_KEY)})

    assert validate(onto_cli, root)[1] == []


def test_루트_전용_검사_항목은_저장소가_덮어쓰지_못한다(onto_cli):
    """루트 전용 검사 항목을 지식 저장소가 덮어쓰려 하면 오류다. 덮어쓰기는 통째로 버려지고 루트 기본 규칙으로 검사한다."""
    for name in (
        "invalid-ontology-yaml",
        "invalid-class-declaration",
        "duplicate-repository-name",
        "invalid-scope",
        "scope-violation",
        "path-reference",
        "outside-link",
    ):
        override = {"checks": {name: {"enabled": False}, "orphan-page": {"enabled": False}}}
        root = onto_cli.root({"billing": repo("billing", page("term/idle", "Term", title="한가한 용어"), rules=override)})

        result, findings = validate(onto_cli, root)

        assert [f[:4] for f in findings] == [
            (ERROR, "billing", yaml_file(), "invalid-rules"),
            (WARNING, "billing", file("term/idle"), "orphan-page"),  # 같이 적은 덮어쓰기도 적용되지 않는다
        ], name
        assert f"`rules.checks.{name}`" in findings[0][4] and "루트 전용" in findings[0][4]
        assert result.returncode == 1


def test_저장소가_invalid_value를_꺼도_읽을_수_없는_Project_속성은_ontology_yaml의_문제로_보고된다(onto_cli):
    """중첩된 값은 읽을 수 없어 build가 멈춘다. 같은 문제를 validate도 오류로 본다."""
    rules = {"checks": {"invalid-value": {"enabled": False}}}
    root = onto_cli.root({"billing": repo("billing", title={"ko": "결제"}, rules=rules)})

    result, findings = validate(onto_cli, root)

    assert [f[:4] for f in findings] == [(ERROR, "billing", yaml_file(), "invalid-ontology-yaml")]
    assert result.returncode == 1 and onto_cli.run(root, "build").returncode == 1


def test_저장소가_invalid_value를_끄면_페이지의_값의_종류_오류는_보고되지_않는다(onto_cli):
    rules = {"checks": {"invalid-value": {"enabled": False}}}
    root = onto_cli.root({"billing": repo("billing", page("component/api", "Component", title=["a", {"b": 1}], partOf="project"), rules=rules)})

    assert "invalid-value" not in [f[3] for f in validate(onto_cli, root)[1]]


def test_루트_기본_규칙은_ontology_yaml의_문제_항목을_바꿀_수_있다(onto_cli):
    """루트가 정한 값은 모든 저장소에 적용된다. 경고로 낮추면 validate가 통과하고 build도 그 문제로 멈추지 않는다."""
    onto_cli.set_root_check("invalid-ontology-yaml", severity="warning")
    root = onto_cli.root({"billing": repo("billing", scpoe="team")})

    result, findings = validate(onto_cli, root)

    assert [f[:4] for f in findings] == [(WARNING, "billing", yaml_file(), "invalid-ontology-yaml")]
    assert result.returncode == 0
    assert onto_cli.run(root, "build").returncode == 0


@pytest.mark.parametrize("typo", [{"rule": {"sources": {"include": ["design/**/*.md"]}}}, {"scpoe": "team"}], ids=["rules_오타", "scope_오타"])
def test_규칙_명령은_ontology_yaml_최상위의_오타를_조용히_넘기지_않고_오류로_끝난다(onto_cli, typo):
    root = onto_cli.root({"billing": repo("billing", **typo)})

    result = onto_cli.run(root, "rules", "billing")

    (key,) = typo
    assert result.returncode == 1 and result.stdout == ""
    assert yaml_file() in result.stderr and f"`{key}`" in result.stderr


def test_식별자_형식을_끈_저장소의_대문자_디렉토리_페이지도_디렉토리_오류는_보고된다(onto_cli):
    """`Plan/`을 식별자 형식 항목이 대신 보고하는 것은 그 항목이 켜져 있을 때뿐이다."""
    rules = {"checks": {"invalid-identifier": {"enabled": False}}}
    muted = onto_cli.root({"billing": repo("billing", page("Plan/lower", "Plan", title="계획", about="project"), rules=rules)})
    default = onto_cli.root({"billing": repo("billing", page("Plan/lower", "Plan", title="계획", about="project"))})

    assert [f[3] for f in validate(onto_cli, muted)[1]] == ["misplaced-page"]
    assert [f[3] for f in validate(onto_cli, default)[1]] == ["invalid-identifier"]


@pytest.mark.parametrize("pattern", [".+", "[a-z0-9:-]+", "[a-z0-9 -]+", "\\S+"], ids=["아무_글자", "콜론", "공백", "공백이_아닌_글자"])
def test_참조_문법을_깨는_식별자_형식은_규칙_오류로_거부한다(onto_cli, pattern):
    """`:`는 교차 참조의 경계이고 참조는 앞뒤 공백을 뗀다. 이를 허용하는 형식에서는 식별자가 참조로 가리킬 수 없는 페이지가 생긴다."""
    onto_cli.replace_in_root_rules('identifier-pattern: "[a-z0-9-]+"', f"identifier-pattern: {json.dumps(pattern)}")

    result = onto_cli.run(onto_cli.root({}), "rules")

    assert result.returncode == 1 and "`language.identifier-pattern`" in result.stderr and ":" in result.stderr


def test_루트_기본_규칙의_식별자_형식도_참조_문법을_깨면_오류로_끝난다(onto_cli):
    onto_cli.replace_in_root_rules('identifier-pattern: "[a-z0-9-]+"', 'identifier-pattern: "[a-z0-9:-]+"')

    result = onto_cli.run(onto_cli.root({}), "rules")

    assert result.returncode == 1 and "`language.identifier-pattern`" in result.stderr


@pytest.mark.parametrize(
    "pattern",
    ["[a-z0-9_-]+", "[A-Za-z0-9-]+", "[a-z]+", "[a-z0-9]+(-[a-z0-9]+)*", "[a-z0-9-]{1,64}", "(?:[a-z0-9]+-)*[a-z0-9]+", "[a-z0-9]+(?:\\.[a-z0-9]+)?"],
    ids=["밑줄", "대문자", "소문자", "하이픈으로_이은_낱말", "길이_제한", "낱말과_하이픈의_반복", "선택적인_점_조각"],
)
def test_참조_문법을_깨지_않는_식별자_형식은_받아들인다(onto_cli, pattern):
    onto_cli.replace_in_root_rules('identifier-pattern: "[a-z0-9-]+"', f"identifier-pattern: {json.dumps(pattern)}")
    root = onto_cli.root({"billing": repo("billing")})

    assert validate(onto_cli, root)[1] == []


# 식별자 형식은 사용자가 쓴 정규 표현식이다. 맞지 않는 긴 식별자에서 지수 시간으로 되돌아가는 모양이면 `validate`가 끝나지 않아, 지식 저장소 하나의 규칙이
# 루트의 검사와 푸시 관문을 모든 사람에게서 멈춘다. 그래서 식별자 형식은 루트 전용이고, 지식 저장소가 적으면 그 저장소만 오류로 보고하고 루트 기본 형식으로 검사한다.
BACKTRACKING_PATTERNS = {
    "중첩된_반복": "([a-z]+-?)+",
    "접두어가_붙은_중첩된_반복": "(adr|rfc)-([a-z0-9]+-?)+",
    "반복의_반복": "([a-z0-9]+)*",
    "글자_모임의_반복": "ab(c+)+",
}
SLOW_IDENTIFIER = "adr-" + "a" * 48 + "_x"  # 밑줄이 들어 있어 어느 형식에도 맞지 않는다


@pytest.mark.parametrize("pattern", BACKTRACKING_PATTERNS.values(), ids=BACKTRACKING_PATTERNS.keys())
def test_지수_시간으로_되돌아갈_수_있는_식별자_형식을_지식_저장소가_적어도_검사는_끝나고_그_저장소만_오류가_된다(onto_cli, pattern):
    """모양이 어떻든 지식 저장소의 식별자 형식은 쓰이지 않는다. 맞지 않는 긴 식별자가 있어도 루트 기본 형식으로 곧 끝난다."""
    slow = page(f"component/{SLOW_IDENTIFIER}", "Component", title="긴 식별자", partOf="project")
    repos = {
        "billing": repo("billing", slow, rules={"language": {"identifier-pattern": pattern}}),
        "shop": repo("shop", page("component/api", "Component", title="API", partOf="project")),
    }

    result = onto_cli.run(onto_cli.root(repos), "validate", timeout=60)
    findings = [tuple(line.split("\t")) for line in result.stdout.splitlines()]

    assert sorted((f[1], f[3]) for f in findings) == [("billing", "invalid-identifier"), ("billing", "invalid-rules")]
    assert result.returncode == 1


@pytest.mark.parametrize(
    ("language", "key"),
    [
        ({"body": "sorce"}, "rules.language.body"),
        ({"body": "Korean"}, "rules.language.body"),
        ({"aliases": ["korean", "englsh"]}, "rules.language.aliases"),
        ({"aliases": ["source"]}, "rules.language.aliases"),
        ({"aliases": ["ko", ""]}, "rules.language.aliases"),
    ],
    ids=["body_오타", "body_언어_이름", "별칭_언어_이름", "별칭에_source", "별칭에_빈_값"],
)
def test_언어_규칙의_값이_source나_언어_코드가_아니면_규칙_오류로_보고한다(onto_cli, language, key):
    root = onto_cli.root({"billing": repo("billing", rules={"language": language})})

    findings = validate(onto_cli, root)[1]

    assert [f[:4] for f in findings] == [(ERROR, "billing", yaml_file(), "invalid-rules")]
    assert f"`{key}`" in findings[0][4]


@pytest.mark.parametrize("body", ["source", "ko", "en", "pt-BR", "zh-Hans", "fil"])
def test_언어_규칙은_source와_언어_코드를_받아들인다(onto_cli, body):
    root = onto_cli.root({"billing": repo("billing", rules={"language": {"body": body, "aliases": ["ko", "en", "ja"]}})})

    assert validate(onto_cli, root)[1] == []


def test_루트_기본_규칙의_언어_값_오타도_오류로_끝난다(onto_cli):
    onto_cli.replace_in_root_rules("body: source", "body: sorce")

    result = onto_cli.run(onto_cli.root({}), "validate")

    assert result.returncode == 1 and "`language.body`" in result.stderr


def test_루트_기본_규칙에_없는_날짜가_있으면_파일_이름과_함께_오류로_끝나고_트레이스백이_없다(onto_cli):
    onto_cli.write_root_rules(onto_cli.root_rules() + "\nmemo: 2026-02-30\n")

    result = onto_cli.run(onto_cli.root({}), "rules")

    assert result.returncode == 1
    assert "rules.yaml" in result.stderr and "Traceback" not in result.stderr


@pytest.mark.parametrize("text", ["", "# 주석뿐\n"], ids=["빈_파일", "주석뿐"])
def test_빈_루트_기본_규칙은_빈_키_이름_없이_파일을_알리며_오류로_끝난다(onto_cli, text):
    onto_cli.write_root_rules(text)

    result = onto_cli.run(onto_cli.root({}), "rules")

    assert result.returncode == 1
    assert "rules.yaml" in result.stderr and "``" not in result.stderr and "Traceback" not in result.stderr


def test_루트_기본_규칙을_읽을_수_없으면_파일을_알리며_오류로_끝나고_트레이스백이_없다(onto_cli):
    onto_cli.replace_root_rules_with_directory()

    result = onto_cli.run(onto_cli.root({}), "validate")

    assert result.returncode == 1
    assert "rules.yaml" in result.stderr and "Traceback" not in result.stderr


# --- S1-08 재리뷰 지적 -----------------------------------------------------------

RAW_PAGE = {f"{ONTOLOGY_DIR}/component/raw.md": "frontmatter가 없는 본문\n"}


def unreadable_pages_repo(**project):
    """읽을 수 없는 페이지(값이 중첩된 제목, frontmatter 없음)와 읽을 수 있는 페이지가 든 지식 저장소."""
    return repo(
        "billing",
        page("component/api", "Component", title="API", partOf="project"),
        page("component/nested", "Component", title={"ko": "중첩된 제목"}, partOf="project"),
        RAW_PAGE,
        **project,
    )


MUTE_UNREADABLE = {"checks": {"unreadable-file": {"enabled": False}, "invalid-value": {"enabled": False}}}


@pytest.mark.parametrize("command", ["build", "query"])
def test_저장소가_읽기_문제_항목을_끄면_validate가_통과하고_build와_query도_그_파일을_건너뛰며_멈추지_않는다(onto_cli, command):
    root = onto_cli.root({"billing": unreadable_pages_repo(rules=MUTE_UNREADABLE)})
    args = ("SELECT ?t WHERE { ?e dcterms:title ?t } ORDER BY ?t",) if command == "query" else ()

    validated = onto_cli.run(root, "validate")
    result = onto_cli.run(root, command, *args)

    assert (validated.returncode, validated.stdout) == (0, "")
    assert result.returncode == 0, result.stderr
    if command == "query":
        assert result.stdout.splitlines() == ["t", "API"]  # 읽을 수 없는 페이지는 그래프에 없다
    # 건너뛴 파일은 조용히 사라지지 않고 표준 오류로 알린다. 설명은 끈 검사 항목의 이름을 댄다.
    skipped = [line for line in result.stderr.splitlines() if "건너뛰" in line]
    assert any(file("component/nested") in line and "invalid-value" in line for line in skipped)
    assert any(file("component/raw") in line and "unreadable-file" in line for line in skipped)


def test_저장소가_끈_읽기_문제만_건너뛰고_켜져_있는_항목의_문제가_있는_파일은_멈춘다(onto_cli):
    """`invalid-value`만 끄면 frontmatter가 없는 페이지(`unreadable-file`)는 그대로 멈춘다."""
    rules = {"checks": {"invalid-value": {"enabled": False}}}
    root = onto_cli.root({"billing": unreadable_pages_repo(rules=rules)})

    result = onto_cli.run(root, "build")

    assert result.returncode == 1
    assert file("component/raw") in result.stderr
    assert file("component/nested") not in result.stderr  # 끈 항목의 문제는 멈추는 이유로 보고하지 않는다


def test_한_저장소가_끈_항목은_다른_저장소의_읽기_문제를_건너뛰게_하지_않는다(onto_cli):
    root = onto_cli.root(
        {
            "billing": unreadable_pages_repo(rules=MUTE_UNREADABLE),
            "shop": repo("shop", page("component/nested", "Component", title={"ko": "중첩된 제목"}, partOf="project")),
        }
    )

    result = onto_cli.run(root, "build")

    assert result.returncode == 1
    assert file("component/nested", "shop") in result.stderr
    assert file("component/nested") not in result.stderr


def test_루트_기본_규칙이_끈_읽기_문제는_모든_저장소에서_건너뛴다(onto_cli):
    onto_cli.set_root_check("invalid-value", enabled=False)
    root = onto_cli.root({"billing": repo("billing", page("component/nested", "Component", title={"ko": "중첩된 제목"}, partOf="project"))})

    assert onto_cli.run(root, "validate").returncode == 0
    assert onto_cli.run(root, "build").returncode == 0


def test_저장소가_invalid_identifier를_끄면_Project와_겹치는_project_페이지도_건너뛰고_build는_멈추지_않는다(onto_cli):
    rules = {"checks": {"invalid-identifier": {"enabled": False}}}
    root = onto_cli.root({"billing": repo("billing", page("project", "Component", title="가짜 프로젝트"), rules=rules)})

    validated = onto_cli.run(root, "validate")
    built = onto_cli.run(root, "build")

    assert (validated.returncode, validated.stdout) == (0, "")
    assert built.returncode == 0, built.stderr
    assert "invalid-identifier" in built.stderr and file("project") in built.stderr


GOOD_PAGE = page("component/api", "Component", title="API", partOf="project")
# 읽을 수 없는 파일의 문제를 보고하는 검사 항목 -> 그 문제를 내는 (페이지들, ontology.yaml의 키들). 마지막 둘은 루트 전용 항목이다.
READ_PROBLEMS = {
    "unreadable-file": ((RAW_PAGE,), {}),
    "invalid-value": ((page("component/nested", "Component", title={"ko": "중첩된 제목"}, partOf="project"),), {}),
    "invalid-identifier": ((page("project", "Component", title="가짜 프로젝트"),), {}),
    "invalid-ontology-yaml": ((), {"scpoe": "team"}),
    "invalid-class-declaration": ((), {"classes": {"Invoice": {"subClassOf": "Nothing"}}}),
}
ROOT_ONLY_READ_PROBLEMS = {"invalid-ontology-yaml", "invalid-class-declaration"}


def read_problem_repos(check: str, **project):
    """`check`가 보고하는 읽을 수 없는 파일 하나가 든 `billing` 지식 저장소. `project`는 `ontology.yaml`에 더할 키다."""
    pages, extra = READ_PROBLEMS[check]
    return {"billing": repo("billing", GOOD_PAGE, *pages, **{**extra, **project})}


@pytest.mark.parametrize("check", READ_PROBLEMS)
@pytest.mark.parametrize(
    "setting",
    [{"enabled": False}, {"severity": "warning"}, {"severity": "error"}],
    ids=["끄기", "경고로_낮추기", "오류"],
)
def test_validate가_0으로_끝나면_build_query_status도_멈추지_않고_오류이면_모두_멈춘다(onto_cli, check, setting):
    """읽을 수 없는 파일의 문제는 그 항목이 오류일 때만 `build`·`query`·`status`를 멈춘다. 꺼졌거나 경고이면 그 파일을 건너뛰고 알린다."""
    onto_cli.set_root_check(check, **setting)  # 견본을 만들기 전에 정한다. 견본을 만들 때 도는 build가 인덱스를 갖추게 한다
    root = onto_cli.root(read_problem_repos(check))
    stops = setting == {"severity": "error"}

    results = {
        "validate": onto_cli.run(root, "validate"),
        "build": onto_cli.run(root, "build"),
        "query": onto_cli.run(root, "query", "SELECT ?e WHERE { ?e a onto:Component }"),
        "status": onto_cli.run(root, "status"),
    }

    assert {name: result.returncode != 0 for name, result in results.items()} == {name: stops for name in results}, {
        name: result.stderr for name, result in results.items()
    }
    if not stops:  # 건너뛴 파일은 조용히 사라지지 않고 표준 오류로 알린다
        assert all(check in results[name].stderr for name in ("build", "query", "status")), results["build"].stderr


@pytest.mark.parametrize("check", sorted(set(READ_PROBLEMS) - ROOT_ONLY_READ_PROBLEMS))
@pytest.mark.parametrize("setting", [{"enabled": False}, {"severity": "warning"}], ids=["끄기", "경고로_낮추기"])
def test_지식_저장소가_읽기_문제_항목을_끄거나_경고로_낮추면_그_저장소의_validate와_build가_같이_통과한다(onto_cli, check, setting):
    root = onto_cli.root(read_problem_repos(check, rules={"checks": {check: setting}}))

    validated = onto_cli.run(root, "validate")
    built = onto_cli.run(root, "build")

    assert (validated.returncode, built.returncode) == (0, 0), (validated.stdout, built.stderr)


def test_경고로_낮춘_읽기_문제의_파일을_건너뛴_저장소도_인덱스가_어긋나면_validate가_알린다(onto_cli):
    """읽기 문제로 build가 멈추지 않으면 인덱스를 다시 만들 수 있다. 그 저장소에서도 인덱스 검사를 건너뛰지 않는다."""
    rules = {"checks": {"invalid-value": {"severity": "warning"}}}
    root = onto_cli.root(
        {"billing": repo("billing", page("component/nested", "Component", title={"ko": "중첩된 제목"}, partOf="project"), page("component/api", "Component", title="API", partOf="project"), rules=rules)}
    )
    assert validate(onto_cli, root)[0].returncode == 0  # root()의 build가 읽을 수 없는 페이지를 건너뛰고 인덱스를 만들었다
    (root / "projects" / "billing" / ONTOLOGY_DIR / "component" / "extra.md").write_text(
        '---\nclass: Component\ntitle: 새 페이지\npartOf: project\n---\n본문\n', encoding="utf-8"
    )

    result, findings = validate(onto_cli, root)

    assert [(f[0], f[3]) for f in findings if f[3] == "index-mismatch"] == [(ERROR, "index-mismatch")]
    assert result.returncode == 1


def test_identifier_pattern을_파일_이름에_맞게_바꾼_저장소에서도_Plan_디렉토리의_오류는_가려지지_않는다(onto_cli):
    """식별자 형식 항목이 디렉토리 오류를 대신 보고하는 것은 그 항목이 디렉토리 항목보다 약하지 않을 때뿐이다."""
    page_in_plan_directory = page("Plan/lower", "Plan", title="계획", about="project")

    def findings(**checks):
        root = onto_cli.root({"billing": repo("billing", page_in_plan_directory, rules={"checks": checks})})
        result, reported = validate(onto_cli, root)
        return result.returncode, [(f[0], f[3]) for f in reported]

    # 식별자 형식 항목만 경고로 낮추면 디렉토리 오류(오류)가 가려지지 않는다
    assert findings(**{"invalid-identifier": {"severity": "warning"}}) == (1, [(WARNING, "invalid-identifier"), (ERROR, "misplaced-page")])
    # 둘이 같거나 식별자 형식 항목이 더 강하면 하나로 줄여 알린다
    assert findings() == (1, [(ERROR, "invalid-identifier")])
    assert findings(**{"misplaced-page": {"severity": "warning"}}) == (1, [(ERROR, "invalid-identifier")])
    both = {"invalid-identifier": {"severity": "warning"}, "misplaced-page": {"severity": "warning"}}
    assert findings(**both) == (0, [(WARNING, "invalid-identifier")])


@pytest.mark.parametrize(
    ("pattern", "identifier"),
    [
        ("[b-z0-9-]+(:[b-z0-9-]+)?", "component/b:c"),
        (" ?[b-z0-9-]+", "component/ b"),
        ("[b-z0-9-]+ ?", "component/b "),
    ],
    ids=["콜론", "앞_공백", "뒤_공백"],
)
def test_식별자_형식이_견본_조각을_빠져나가도_콜론이나_앞뒤_공백이_든_경로_조각은_식별자_오류로_보고한다(onto_cli, pattern, identifier):
    """참조는 `:`를 저장소 이름과의 경계로 읽고 앞뒤 공백을 뗀다. 그런 조각은 형식이 허용해도 참조로 가리킬 수 없다."""
    onto_cli.replace_in_root_rules('identifier-pattern: "[a-z0-9-]+"', f"identifier-pattern: {json.dumps(pattern)}")
    root = onto_cli.root({"billing": repo("billing", page(identifier, "Component", title="C", partOf="project"))})

    result, findings = validate(onto_cli, root)

    assert [f[:4] for f in findings] == [(ERROR, "billing", file(identifier), "invalid-identifier")]
    assert result.returncode == 1
    assert "참조" in findings[0][4]


def test_Project_속성의_값의_종류가_틀리면_저장소가_invalid_value를_꺼도_ontology_yaml의_문제로_보고한다(onto_cli):
    """`ontology.yaml`은 규칙을 담은 파일이다. 숫자 같은 값의 종류 문제도 중첩된 값처럼 저장소가 규칙으로 묻지 못한다."""
    rules = {"checks": {"invalid-value": {"enabled": False}}}
    root = onto_cli.root({"billing": repo("billing", title=5, aliases=[1, "pay"], rules=rules)})

    result, findings = validate(onto_cli, root)

    assert {f[:4] for f in findings} == {(ERROR, "billing", yaml_file(), "invalid-ontology-yaml")}
    assert result.returncode == 1


def test_루트_기본_규칙은_Project_속성의_값의_종류_보고를_바꿀_수_있다(onto_cli):
    onto_cli.set_root_check("invalid-ontology-yaml", severity="warning")
    root = onto_cli.root({"billing": repo("billing", title=5)})

    result, findings = validate(onto_cli, root)

    assert [f[:4] for f in findings] == [(WARNING, "billing", yaml_file(), "invalid-ontology-yaml")]
    assert result.returncode == 0
