"""지식 저장소 안에서의 실행(`--scope repository`): 그 저장소의 지식만 다룬다.

온톨로지 도구의 명령줄 진입점을 지식 저장소 하나의 견본 디렉토리에 대고 실행한다(`onto_cli.repository`).
지식 저장소 안에서 `just -f .onto/Justfile …`이 도구에 넘기는 범위가 이것이다. 그 Justfile을 거쳐 루트 저장소에 붙은 실제 지식 저장소에서
도는 것은 `test_onto_repository_just.py`가 본다. 견본은 루트 저장소가 없으므로, 루트나 다른 지식 저장소의 파일을 읽는 일은
그 파일이 있는 `onto_cli.root`와 나란히 둔 견본으로 확인한다.

지식 저장소 안에서는 모든 경로가 그 저장소 기준이다(`docs/ontology/plan/launch.md`). 루트 저장소의 `projects/<저장소>/` 접두어가 없다.
"""

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from support.onto_cli import ONTOLOGY_DIR, REPOSITORY, page, parse_table, repo, snapshot

INDEX = f"{ONTOLOGY_DIR}/index.md"
ERROR = "오류"
WARNING = "경고"

BILLING = repo(
    "billing",
    page("component/gateway", "Component", title="결제 게이트웨이", description="카드 결제를 중계한다", partOf="project"),
    page("plan/launch", "Plan", title="출시 계획", about="component/gateway"),
    title="결제",
    description="결제 시스템의 지식",
)

BILLING_INDEX = """\
# 결제 인덱스

> 이 파일은 `onto build`가 페이지에서 만든 생성물이다. 손으로 고치지 않는다. 페이지를 고친 뒤 다시 만든다.

결제 시스템의 지식

## Component

- [결제 게이트웨이](component/gateway.md) — 카드 결제를 중계한다

## Plan

- [출시 계획](plan/launch.md)
"""


# --- build ------------------------------------------------------------------


def test_build는_이_저장소의_페이지를_컴파일하고_이_저장소의_인덱스를_만든다(onto_cli):
    billing = onto_cli.repository("billing", BILLING, indexed=False)

    result = onto_cli.run(billing, "build", scope=REPOSITORY)

    assert result.returncode == 0, result.stderr
    graph = onto_cli.graph_file.read_text(encoding="utf-8")
    assert "출시 계획" in graph and "결제 게이트웨이" in graph
    assert (billing / INDEX).read_text(encoding="utf-8") == BILLING_INDEX


def test_build는_저장소_하나의_인덱스와_도구_디렉토리의_산출물밖에_만들지_않고_전체_인덱스를_남기지_않는다(onto_cli):
    billing = onto_cli.repository("billing", BILLING, indexed=False)
    before = snapshot(billing)

    result = onto_cli.run(billing, "build", scope=REPOSITORY)

    assert result.returncode == 0, result.stderr
    assert snapshot(billing) - before == {INDEX}
    assert not (onto_cli.build_dir / "index.md").exists()  # 전체 인덱스는 루트 저장소가 여러 저장소를 모을 때만 만든다


def test_build가_알리는_경로는_그_저장소_기준이다(onto_cli):
    billing = onto_cli.repository("billing", BILLING, indexed=False)

    result = onto_cli.run(billing, "build", scope=REPOSITORY)

    assert f"인덱스: {INDEX} (새로 만들었다)" in result.stdout
    assert "projects/" not in result.stdout


# --- query ------------------------------------------------------------------


def test_query의_결과는_그_저장소_기준_파일_경로로_엔티티를_보여_준다(onto_cli):
    billing = onto_cli.repository("billing", BILLING)

    rows = onto_cli.query(billing, "SELECT ?e ?t WHERE { ?e a onto:Plan ; dcterms:title ?t }", scope=REPOSITORY)

    assert rows == [[f"{ONTOLOGY_DIR}/plan/launch.md", "출시 계획"]]
    assert (billing / rows[0][0]).is_file()  # 추가 조회 없이 곧바로 열 수 있다


def test_query는_추론된_관계도_이_저장소_안에서_돌려준다(onto_cli):
    billing = onto_cli.repository("billing", BILLING)

    rows = onto_cli.query(billing, "SELECT ?x ?y WHERE { ?x onto:implementedBy ?y }", scope=REPOSITORY)

    assert rows == []  # 견본에 구현 관계가 없다
    rows = onto_cli.query(billing, "SELECT ?x ?y WHERE { ?x onto:hasPart ?y }", scope=REPOSITORY)
    assert rows == [["docs/ontology/ontology.yaml", f"{ONTOLOGY_DIR}/component/gateway.md"]]  # `partOf`의 역관계


def test_query는_원본_문서의_Source_엔티티도_그_저장소_기준_파일_경로로_보여_준다(onto_cli):
    doc_hash = "0123456789abcdef0123456789abcdef01234567"
    billing = onto_cli.repository(
        "billing",
        repo(
            "billing",
            page(
                "component/gateway",
                "Component",
                title="결제 게이트웨이",
                partOf="project",
                derivedFrom=[{"path": "docs/design.md", "hash": doc_hash}],
            ),
        ),
    )

    rows = onto_cli.query(billing, "SELECT ?s WHERE { ?s a onto:Source }", scope=REPOSITORY)

    assert rows == [["docs/design.md"]]


# --- validate ---------------------------------------------------------------


def validate(onto_cli, repository):
    result = onto_cli.run(repository, "validate", scope=REPOSITORY)
    findings = [tuple(line.split("\t")) for line in result.stdout.splitlines()]
    assert all(len(finding) == 5 for finding in findings), result.stdout
    return result, findings


def test_문제가_없는_저장소는_아무것도_보고하지_않고_0으로_끝난다(onto_cli):
    billing = onto_cli.repository("billing", BILLING)

    result, findings = validate(onto_cli, billing)

    assert result.returncode == 0 and findings == []


def test_validate는_건너뛴_검사를_알린다(onto_cli):
    billing = onto_cli.repository("billing", BILLING)

    result = onto_cli.run(billing, "validate", scope=REPOSITORY)

    assert result.returncode == 0
    assert "이 저장소만 검사했다" in result.stderr
    for skipped in ("교차 참조", "공유 범위", "저장소 간 중복", "unregistered-repository", "duplicate-entity-across-repositories"):
        assert skipped in result.stderr, skipped
    assert "just onto validate" in result.stderr  # 어디서 전체를 검사하는지


def test_validate는_문제를_그_저장소_기준_파일_경로로_보고한다(onto_cli):
    billing = onto_cli.repository(
        "billing", {**BILLING, **page("component/ledger", "Component", title="원장", partOf="project", owner="kim")}
    )

    result, findings = validate(onto_cli, billing)

    assert result.returncode == 1
    assert [finding[:4] for finding in findings] == [(ERROR, "billing", f"{ONTOLOGY_DIR}/component/ledger.md", "undefined-key")]


def test_validate는_어긋난_인덱스를_그_저장소_기준_경로로_보고한다(onto_cli):
    billing = onto_cli.repository("billing", BILLING)
    (billing / ONTOLOGY_DIR / "plan" / "launch.md").write_text(
        (billing / ONTOLOGY_DIR / "plan" / "launch.md").read_text(encoding="utf-8").replace("출시 계획", "출시 계획 2차"), encoding="utf-8"
    )

    _, findings = validate(onto_cli, billing)

    assert [finding[:4] for finding in findings] == [(ERROR, "billing", INDEX, "index-mismatch")]


def test_다른_저장소를_가리키는_교차_참조는_검사하지_않는다(onto_cli):
    billing = onto_cli.repository(
        "billing",
        repo(
            "billing",
            page("component/gateway", "Component", title="결제 게이트웨이", partOf="project", dependsOn="shop:component/api"),
            page("plan/launch", "Plan", title="출시 계획", about=["component/gateway", "ghost:component/none"]),
        ),
    )

    result, findings = validate(onto_cli, billing)

    # 등록된 저장소를 가리키든(`shop`), 등록되지 않은 저장소를 가리키든(`ghost`) 이 저장소만으로는 알 수 없다
    assert result.returncode == 0 and findings == []


def test_같은_저장소_안의_참조는_검사한다(onto_cli):
    billing = onto_cli.repository(
        "billing",
        repo(
            "billing",
            page("component/gateway", "Component", title="결제 게이트웨이", partOf="project"),
            page("plan/launch", "Plan", title="출시 계획", about="component/ghost"),
            # 자기 저장소 이름을 붙인 참조는 교차 참조가 아니라 같은 저장소의 엔티티를 가리킨다
            page("plan/refund", "Plan", title="환불 계획", about="billing:component/missing"),
        ),
    )

    result, findings = validate(onto_cli, billing)

    assert result.returncode == 1
    assert [finding[:4] for finding in findings] == [
        (ERROR, "billing", f"{ONTOLOGY_DIR}/plan/launch.md", "broken-reference"),
        (ERROR, "billing", f"{ONTOLOGY_DIR}/plan/refund.md", "broken-reference"),
    ]


def test_온톨로지_층이_없는_저장소는_경고로_알린다(onto_cli):
    empty = onto_cli.repository("billing", {"README.md": "# 결제\n"}, indexed=False)

    result, findings = validate(onto_cli, empty)

    assert result.returncode == 0
    assert [finding[:4] for finding in findings] == [(WARNING, "billing", ".", "missing-ontology-layer")]


def test_규칙이_저장소_이름의_규칙_덮어쓰기와_함께_적용된다(onto_cli):
    billing = onto_cli.repository(
        "billing",
        repo(
            "billing",
            page("component/gateway", "Component", title="결제 게이트웨이"),  # 고아 페이지(기본은 경고)
            rules={"checks": {"orphan-page": {"enabled": False}}},
        ),
    )

    result, findings = validate(onto_cli, billing)

    assert result.returncode == 0 and findings == []


# --- 읽을 수 없는 파일 ---------------------------------------------------------


def test_읽을_수_없는_페이지가_오류_항목이면_build와_query가_그_저장소_기준_경로로_알리며_멈춘다(onto_cli):
    billing = onto_cli.repository("billing", {**BILLING, f"{ONTOLOGY_DIR}/plan/bad.md": "frontmatter가 없다\n"}, indexed=False)

    for command in (("build",), ("query", "ASK { ?s ?p ?o }"), ("status",)):
        result = onto_cli.run(billing, *command, scope=REPOSITORY)

        assert result.returncode == 1, command
        assert f"오류: {ONTOLOGY_DIR}/plan/bad.md:" in result.stderr, command


def test_읽을_수_없는_페이지의_항목이_꺼져_있으면_그_파일을_건너뛰고_알린다(onto_cli):
    billing = onto_cli.repository(
        "billing",
        {
            **repo(
                "billing",
                page("component/gateway", "Component", title="결제 게이트웨이", partOf="project"),
                rules={"checks": {"unreadable-file": {"enabled": False}}},
            ),
            f"{ONTOLOGY_DIR}/plan/bad.md": "frontmatter가 없다\n",
        },
        indexed=False,
    )

    result = onto_cli.run(billing, "build", scope=REPOSITORY)

    assert result.returncode == 0, result.stderr
    assert f"{ONTOLOGY_DIR}/plan/bad.md" in result.stderr and "unreadable-file" in result.stderr
    assert "결제 게이트웨이" in (billing / INDEX).read_text(encoding="utf-8")


def test_읽을_수_없는_페이지가_오류_항목이면_validate는_인덱스를_다시_만들라고_하지_않고_그_파일만_보고한다(onto_cli):
    billing = onto_cli.repository("billing", {**BILLING, f"{ONTOLOGY_DIR}/plan/bad.md": "frontmatter가 없다\n"}, indexed=False)

    _, findings = validate(onto_cli, billing)

    assert [finding[:4] for finding in findings] == [(ERROR, "billing", f"{ONTOLOGY_DIR}/plan/bad.md", "unreadable-file")]


# --- status -----------------------------------------------------------------


def test_status는_이_저장소의_원본_문서만_저장소_기준_경로로_보여_준다(onto_cli):
    billing = onto_cli.repository("billing", {**BILLING, "docs/design.md": "# 설계\n", "docs/sub/api.md": "# API\n"})

    result = onto_cli.run(billing, "status", scope=REPOSITORY)

    assert result.returncode == 0, result.stderr
    rows = [line.split("\t") for line in result.stdout.splitlines()]
    assert [(row[0], row[1], row[2]) for row in rows] == [
        ("새 문서", "billing", "docs/design.md"),
        ("새 문서", "billing", "docs/sub/api.md"),
    ]


# --- rules ------------------------------------------------------------------


def test_rules는_이_저장소의_이름으로_덮어쓴_규칙을_보여_준다(onto_cli):
    billing = onto_cli.repository("billing", repo("billing", rules={"checks": {"orphan-page": {"enabled": False}}}))

    result = onto_cli.run(billing, "rules", "billing", scope=REPOSITORY)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["checks"]["orphan-page"]["enabled"] is False
    assert json.loads(onto_cli.run(billing, "rules", scope=REPOSITORY).stdout)["checks"]["orphan-page"]["enabled"] is True


def test_rules는_이_저장소가_아닌_저장소의_이름에는_이_저장소만_있다고_알린다(onto_cli):
    billing = onto_cli.repository("billing", BILLING)

    result = onto_cli.run(billing, "rules", "shop", scope=REPOSITORY)

    assert result.returncode == 1
    assert "`shop`가 없다" in result.stderr and "있는 것: billing" in result.stderr


# --- sync -------------------------------------------------------------------


def test_sync는_지식_저장소_안에서_거부하고_아무것도_바꾸지_않는다(onto_cli):
    billing = onto_cli.repository("billing", BILLING)
    before = snapshot(billing)

    result = onto_cli.run(billing, "sync", scope=REPOSITORY)

    assert result.returncode == 1
    assert "루트 저장소에서만 쓸 수 있다" in result.stderr
    assert snapshot(billing) == before


# --- 루트 저장소와 다른 지식 저장소는 읽지 않는다 ---------------------------------------


@contextmanager
def unreadable(*paths: Path) -> Iterator[None]:
    """`paths`를 읽을 수도 훑을 수도 없게 한다. 도구가 그 경로를 읽으려 하면 실패한다. 끝나면 되돌린다."""
    originals = {path: path.stat().st_mode & 0o777 for path in paths}
    try:
        for path in paths:
            path.chmod(0o000)
        yield
    finally:
        for path, mode in originals.items():
            path.chmod(mode)


def inside_root(onto_cli, repos: dict[str, dict[str, str]]) -> Path:
    """`billing`이 루트 저장소의 `projects/` 아래에 있는 견본. 루트 저장소와 다른 지식 저장소가 나란히 있다. `billing`의 경로를 돌려준다."""
    root = onto_cli.root(repos, indexed=False)
    (root / "docs").mkdir()
    (root / "docs" / "root-notes.md").write_text("# 루트의 문서\n", encoding="utf-8")
    onto_cli.run(root / "projects" / "billing", "build", scope=REPOSITORY)
    return root / "projects" / "billing"


SHOP = repo("shop", page("plan/launch", "Plan", title="상점 출시 계획"), page("plan/other", "Plan", title="상점 다른 계획"), title="상점")


def test_다른_저장소와_루트_저장소가_읽을_수_없어도_모든_명령이_이_저장소만으로_돈다(onto_cli):
    """다른 지식 저장소, 루트의 문서, `projects/` 목록을 읽거나 훑으려 하면 실패한다."""
    billing = inside_root(onto_cli, {"billing": BILLING, "shop": SHOP})
    root = billing.parent.parent

    with unreadable(root / "projects" / "shop", root / "docs"):
        os.chmod(root / "projects", 0o100)  # 지나갈 수만 있다. 목록을 훑을 수 없다
        try:
            results = {
                command: onto_cli.run(billing, *command, scope=REPOSITORY)
                for command in (("build",), ("validate",), ("status",), ("rules", "billing"), ("query", "SELECT ?e WHERE { ?e a onto:Plan }"))
            }
        finally:
            os.chmod(root / "projects", 0o755)

    for command, result in results.items():
        assert result.returncode == 0, (command, result.stderr)
    assert parse_table(results[("query", "SELECT ?e WHERE { ?e a onto:Plan }")].stdout) == [["e"], [f"{ONTOLOGY_DIR}/plan/launch.md"]]


def test_다른_저장소의_엔티티와_문제와_원본_문서가_결과에_섞이지_않는다(onto_cli):
    broken_shop = {**SHOP, f"{ONTOLOGY_DIR}/plan/bad.md": "frontmatter가 없다\n", "docs/shop-notes.md": "# 상점 문서\n"}
    billing = inside_root(onto_cli, {"billing": BILLING, "shop": broken_shop})

    query = onto_cli.run(billing, "query", "SELECT ?e ?t WHERE { ?e dcterms:title ?t } ORDER BY ?t", scope=REPOSITORY)
    validate_result, findings = validate(onto_cli, billing)
    status = onto_cli.run(billing, "status", scope=REPOSITORY)

    assert query.returncode == 0, query.stderr  # 다른 저장소의 읽을 수 없는 파일에 멈추지 않는다
    titles = {row[1] for row in parse_table(query.stdout)[1:]}
    assert titles == {"결제", "결제 게이트웨이", "출시 계획"}
    assert validate_result.returncode == 0 and findings == []
    assert status.stdout == "새로 생겼거나 바뀐 원본 문서가 없다\n"  # 루트의 `docs/root-notes.md`와 `shop`의 문서가 아니다
