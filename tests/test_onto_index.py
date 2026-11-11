"""인덱스 생성(`build`)과 어긋난 인덱스 검사(`validate`).

온톨로지 도구의 명령줄 진입점을 견본 페이지 디렉토리에 대고 실행한다(`onto_cli`). git에 잡히는지는 `test_onto_just.py`가 본다.

인덱스는 지식 저장소의 `docs/ontology/index.md`다. 페이지를 클래스별로 묶어 제목, 링크, 한 줄 설명을 보여 주는 생성물이고,
지식 저장소를 따로 클론한 사람과 에이전트의 진입점이라 커밋한다(ADR 0006). 기대하는 글자는 손으로 적은 값이다.
"""

import os
import re
import time
from pathlib import Path
from urllib.parse import unquote

from support.onto_cli import ONTOLOGY_DIR, page, repo, snapshot

INDEX = f"{ONTOLOGY_DIR}/index.md"

BILLING = {
    "billing": repo(
        "billing",
        page("component/gateway", "Component", title="결제 게이트웨이", description="카드 결제를 중계한다", partOf="project"),
        page("plan/launch", "Plan", title="출시 계획", about="component/gateway"),
        title="결제",
        description="결제 시스템의 지식",
    )
}

# 인덱스 머리의 표시. 생성물이며 손으로 고치지 말라는 말이다.
GENERATED_NOTICE = "이 파일은 `onto build`가 페이지에서 만든 생성물이다. 손으로 고치지 않는다. 페이지를 고친 뒤 다시 만든다."

# `shop`이라는 이름으로 쓴 같은 견본. 이름이 겹치는 견본의 한쪽으로 쓴다.
BILLING_AS_SHOP = repo("shop", page("component/api", "Component", title="상점 API", partOf="project"), title="상점")

BILLING_INDEX = f"""\
# 결제 인덱스

> {GENERATED_NOTICE}

결제 시스템의 지식

## Component

- [결제 게이트웨이](component/gateway.md) — 카드 결제를 중계한다

## Plan

- [출시 계획](plan/launch.md)
"""


def sample(onto_cli, repos):
    """인덱스가 아직 없는 견본. `OntoCli.root()`는 기본으로 `build`해 인덱스를 갖추므로, `build`가 인덱스를 새로 만드는지 보려면 이렇게 만든다."""
    return onto_cli.root(repos, indexed=False)


def index_of(root, name: str = "billing") -> str:
    return (root / "projects" / name / INDEX).read_text(encoding="utf-8")


def build(onto_cli, root):
    result = onto_cli.run(root, "build")
    assert result.returncode == 0, result.stderr
    return result


# --- 내용 ---------------------------------------------------------------------


def test_build는_각_지식_저장소의_온톨로지_층에_페이지를_클래스별로_묶은_인덱스를_만든다(onto_cli):
    root = sample(onto_cli, BILLING)

    build(onto_cli, root)

    assert index_of(root) == BILLING_INDEX


def test_하위_클래스의_페이지는_공통_클래스의_묶음에_들고_하위_클래스_이름이_붙는다(onto_cli):
    root = sample(onto_cli,
        {
            "billing": repo(
                "billing",
                page("component/gateway", "Component", title="게이트웨이", partOf="project"),
                page("component/invoice", "Invoice", title="청구서", partOf="project"),
                classes={"Invoice": {"subClassOf": "Component"}},
            )
        }
    )

    build(onto_cli, root)

    assert index_of(root) == (
        "# billing 인덱스\n"
        "\n"
        f"> {GENERATED_NOTICE}\n"
        "\n"
        "## Component\n"
        "\n"
        "- [게이트웨이](component/gateway.md)\n"
        "- [청구서](component/invoice.md) (Invoice)\n"
    )


def test_클래스가_없거나_풀리지_않는_페이지도_인덱스에서_빠지지_않고_분류되지_않음에_든다(onto_cli):
    root = sample(onto_cli,
        {
            "billing": repo(
                "billing",
                page("component/gateway", "Component", title="게이트웨이", partOf="project"),
                page("misc/unknown", "Gadget", title="알 수 없는 것"),
                page("misc/nothing", None, title="클래스 없음"),
            )
        }
    )

    build(onto_cli, root)

    assert index_of(root).endswith(
        "## Component\n"
        "\n"
        "- [게이트웨이](component/gateway.md)\n"
        "\n"
        "## 분류되지 않음\n"
        "\n"
        "- [클래스 없음](misc/nothing.md)\n"
        "- [알 수 없는 것](misc/unknown.md) (Gadget)\n"
    )


def test_클래스_묶음은_공통_클래스_순서로_나오고_항목은_식별자_순이다(onto_cli):
    root = sample(onto_cli,
        {
            "billing": repo(
                "billing",
                page("report/b", "Report", title="가"),
                page("term/a", "Term", title="나"),
                page("report/a", "Report", title="다"),
                page("plan/a", "Plan", title="라"),
                page("component/z", "Component", title="마"),
                page("decision/a", "Decision", title="바"),
                page("policy/a", "Policy", title="사"),
            )
        }
    )

    build(onto_cli, root)

    lines = index_of(root).splitlines()
    assert [line for line in lines if line.startswith("## ")] == [
        "## Component",
        "## Plan",
        "## Policy",
        "## Term",
        "## Decision",
        "## Report",
    ]
    assert [line for line in lines if line.startswith("- ")] == [
        "- [마](component/z.md)",
        "- [라](plan/a.md)",
        "- [사](policy/a.md)",
        "- [나](term/a.md)",
        "- [바](decision/a.md)",
        "- [다](report/a.md)",
        "- [가](report/b.md)",
    ]


def test_설명이_여러_줄이면_한_줄로_줄이고_제목의_대괄호는_링크를_깨지_않게_막는다(onto_cli):
    root = sample(onto_cli,
        {
            "billing": repo(
                "billing",
                page(
                    "component/gateway",
                    "Component",
                    title="결제 [게이트웨이] 2\\3",
                    description="첫 줄\n  둘째   줄\n",
                    partOf="project",
                ),
            )
        }
    )

    build(onto_cli, root)

    assert "- [결제 \\[게이트웨이\\] 2\\\\3](component/gateway.md) — 첫 줄 둘째 줄\n" in index_of(root)


def test_제목이_없는_페이지는_식별자로_보여_준다(onto_cli):
    root = sample(onto_cli, {"billing": repo("billing", page("component/gateway", "Component", partOf="project"))})

    build(onto_cli, root)

    assert "- [component/gateway](component/gateway.md)\n" in index_of(root)


# --- 지식 저장소 단독으로 열리는 인덱스 ---------------------------------------------


def test_인덱스의_링크는_인덱스_기준_상대_경로이고_모두_지식_저장소_안의_페이지를_가리킨다(onto_cli):
    root = sample(onto_cli, BILLING)
    build(onto_cli, root)

    # 단독으로 클론한 지식 저장소를 흉내 낸다: 그 저장소의 파일만 다른 디렉토리로 옮긴다.
    standalone = sample(onto_cli, {})
    for source in (root / "projects" / "billing").rglob("*"):
        if source.is_file():
            target = standalone / source.relative_to(root / "projects" / "billing")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())

    links = re.findall(r"\]\(([^)]*)\)", index_of(root))
    assert links == ["component/gateway.md", "plan/launch.md"]
    for link in links:
        assert (standalone / "docs" / "ontology" / link).is_file()


def test_인덱스에는_루트_저장소나_다른_지식_저장소에_관한_내용이_없다(onto_cli):
    root = sample(onto_cli,
        {
            "billing": repo(
                "billing",
                page("component/gateway", "Component", title="게이트웨이", partOf="project", dependsOn="shop:component/api"),
                title="결제",
            ),
            "shop": repo("shop", page("component/api", "Component", title="상점 API", partOf="project"), title="상점"),
        }
    )

    build(onto_cli, root)

    for name, other in (("billing", "shop"), ("shop", "billing")):
        text = index_of(root, name)
        assert other not in text
        assert "projects" not in text and "../" not in text and str(root) not in text
    assert "상점 API" not in index_of(root, "billing")
    assert "게이트웨이" not in index_of(root, "shop")


def test_인덱스에_생성물이며_손으로_고치지_말라는_표시가_있다(onto_cli):
    root = sample(onto_cli, BILLING)

    build(onto_cli, root)

    marker = next(line for line in index_of(root).splitlines() if line.startswith("> "))
    assert "생성물" in marker and "손으로 고치지 않는다" in marker


# --- 같은 입력에서 같은 글자 ---------------------------------------------------------


def test_같은_페이지에서는_글자_하나_다르지_않은_인덱스가_나온다(onto_cli):
    first = sample(onto_cli, BILLING)
    second = sample(onto_cli, BILLING)  # 다른 디렉토리, 다른 시각
    build(onto_cli, first)
    expected = (first / "projects" / "billing" / INDEX).read_bytes()

    time.sleep(1.1)
    build(onto_cli, first)
    build(onto_cli, second)

    assert (first / "projects" / "billing" / INDEX).read_bytes() == expected
    assert (second / "projects" / "billing" / INDEX).read_bytes() == expected


def test_다시_build해도_바뀐_것이_없으면_인덱스_파일을_다시_쓰지_않는다(onto_cli):
    root = sample(onto_cli, BILLING)
    build(onto_cli, root)
    path = root / "projects" / "billing" / INDEX
    os.utime(path, (1_000_000_000, 1_000_000_000))

    result = build(onto_cli, root)

    assert path.stat().st_mtime == 1_000_000_000
    assert "그대로" in result.stdout


def test_페이지가_하나도_없는_지식_저장소에서도_인덱스가_만들어진다(onto_cli):
    root = sample(onto_cli, {"billing": repo("billing", title="결제")})

    build(onto_cli, root)

    assert index_of(root) == (
        "# 결제 인덱스\n"
        "\n"
        f"> {GENERATED_NOTICE}\n"
        "\n"
        "페이지가 아직 없다.\n"
    )


def test_온톨로지_층이_없는_디렉토리에는_인덱스를_만들지_않는다(onto_cli):
    root = sample(onto_cli, {"billing": repo("billing"), "plain": {"README.md": "# 온톨로지 층이 없다\n"}})

    build(onto_cli, root)

    assert not (root / "projects" / "plain" / "docs").exists()


def test_읽을_수_없는_페이지가_있어_build가_멈추면_인덱스도_만들지_않는다(onto_cli):
    files = repo("billing", page("plan/launch", "Plan", title="출시 계획"))
    files[f"{ONTOLOGY_DIR}/plan/broken.md"] = "# frontmatter 없음\n"
    root = sample(onto_cli, {"billing": files})

    result = onto_cli.run(root, "build")

    assert result.returncode != 0
    assert not (root / "projects" / "billing" / INDEX).exists()


# --- 어긋난 인덱스를 잡는 스크립트 검사 --------------------------------------------------


def validate(onto_cli, root):
    """`validate`를 실행해 `(결과, 문제 목록)`을 돌려준다. 문제는 `(심각도, 지식 저장소, 페이지, 검사 항목, 설명)`이다."""
    result = onto_cli.run(root, "validate")
    return result, [tuple(line.split("\t")) for line in result.stdout.splitlines()]


def mismatches(onto_cli, root) -> list[tuple[str, str, str, str]]:
    """어긋난 인덱스로 보고된 것에서 설명을 뺀 `(심각도, 지식 저장소, 페이지, 검사 항목)` 목록."""
    return [finding[:4] for finding in validate(onto_cli, root)[1] if finding[3] == "index-mismatch"]


def mismatch(name: str = "billing") -> tuple[str, str, str, str]:
    return ("오류", name, f"projects/{name}/{INDEX}", "index-mismatch")


def built(onto_cli, repos):
    root = sample(onto_cli, repos)
    build(onto_cli, root)
    return root


def edit(root, relative: str, old: str, new: str) -> None:
    path = root / "projects" / "billing" / ONTOLOGY_DIR / relative
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_build한_직후의_인덱스는_스크립트_검사를_통과한다(onto_cli):
    root = built(onto_cli, BILLING)

    result = onto_cli.run(root, "validate")

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_페이지를_더하고_다시_만들지_않으면_어긋난_인덱스로_잡는다(onto_cli):
    root = built(onto_cli, BILLING)
    added = root / "projects" / "billing" / ONTOLOGY_DIR / "term" / "refund.md"
    added.parent.mkdir()
    added.write_text("---\nclass: Term\ntitle: 환불\nabout: project\n---\n\n본문\n", encoding="utf-8")

    result, findings = validate(onto_cli, root)

    assert result.returncode == 1
    assert [finding[:4] for finding in findings] == [mismatch()]
    assert "term/refund.md" in findings[0][4]  # 인덱스에 없는 페이지가 설명에 나온다


def test_페이지를_지우고_다시_만들지_않으면_어긋난_인덱스로_잡는다(onto_cli):
    root = built(onto_cli, BILLING)
    (root / "projects" / "billing" / ONTOLOGY_DIR / "plan" / "launch.md").unlink()

    result, findings = validate(onto_cli, root)

    assert result.returncode == 1
    assert [finding[:4] for finding in findings if finding[3] == "index-mismatch"] == [mismatch()]
    assert "plan/launch.md" in next(finding[4] for finding in findings if finding[3] == "index-mismatch")


def test_제목을_바꾸고_다시_만들지_않으면_어긋난_인덱스로_잡는다(onto_cli):
    root = built(onto_cli, BILLING)
    edit(root, "plan/launch.md", '"title": "출시 계획"', '"title": "출시 계획 2차"')

    assert mismatches(onto_cli, root) == [mismatch()]


def test_설명이나_클래스나_Project의_제목을_바꾸고_다시_만들지_않아도_어긋난_인덱스로_잡는다(onto_cli):
    for relative, old, new in (
        ("component/gateway.md", "카드 결제를 중계한다", "카드 결제를 중계하고 취소한다"),
        ("plan/launch.md", '"class": "Plan"', '"class": "Policy"'),
        ("ontology.yaml", "결제 시스템의 지식", "결제 시스템"),
    ):
        root = built(onto_cli, BILLING)
        edit(root, relative, old, new)

        assert mismatches(onto_cli, root) == [mismatch()], relative


def test_손으로_고친_인덱스는_어긋난_인덱스로_잡는다(onto_cli):
    root = built(onto_cli, BILLING)
    edit(root, "index.md", "## Plan", "## 계획")

    assert mismatches(onto_cli, root) == [mismatch()]


def test_다시_만들면_어긋난_인덱스가_사라진다(onto_cli):
    root = built(onto_cli, BILLING)
    edit(root, "plan/launch.md", '"title": "출시 계획"', '"title": "출시 계획 2차"')
    assert mismatches(onto_cli, root) == [mismatch()]

    build(onto_cli, root)

    assert validate(onto_cli, root)[1] == []


def test_어긋난_인덱스는_그_지식_저장소의_것만_잡는다(onto_cli):
    repos = {
        **BILLING,
        "shop": repo("shop", page("component/api", "Component", title="상점 API", partOf="project"), title="상점"),
    }
    root = built(onto_cli, repos)
    edit(root, "plan/launch.md", '"title": "출시 계획"', '"title": "출시 계획 2차"')

    assert mismatches(onto_cli, root) == [mismatch("billing")]


def test_줄바꿈이_CRLF로_바뀐_인덱스는_어긋난_것으로_보지_않는다(onto_cli):
    """git의 줄바꿈 변환(autocrlf)이 있는 기기에서 클론한 인덱스다."""
    root = built(onto_cli, BILLING)
    path = root / "projects" / "billing" / INDEX
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))

    assert validate(onto_cli, root)[1] == []


def test_스크립트_검사는_어긋난_인덱스를_고치지_않는다(onto_cli):
    root = built(onto_cli, BILLING)
    edit(root, "plan/launch.md", '"title": "출시 계획"', '"title": "출시 계획 2차"')
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    names = snapshot(root)

    validate(onto_cli, root)

    assert snapshot(root) == names
    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


# --- 전체 인덱스: 빌드 산출물 ------------------------------------------------------------


def test_build는_모든_지식_저장소를_모은_전체_인덱스를_도구_디렉토리의_산출물로_만든다(onto_cli):
    root = sample(onto_cli,
        {
            **BILLING,
            "shop": repo("shop", page("component/api", "Component", title="상점 API", partOf="project"), title="상점"),
        }
    )

    build(onto_cli, root)

    all_index = onto_cli.build_dir / "index.md"
    text = all_index.read_text(encoding="utf-8")
    assert text.startswith("# 전체 인덱스\n")
    assert "빌드 산출물" in text and "커밋하지 않는다" in text
    assert text.index("## 결제 (billing)") < text.index("### Component") < text.index("## 상점 (shop)")
    # 링크는 이 파일(.build/) 기준 상대 경로라, 따라가면 페이지 파일에 닿는다. 마크다운 렌더러처럼 퍼센트 인코딩을 푼다.
    links = re.findall(r"\]\(([^)]*)\)", text)
    assert len(links) == 3
    assert {(all_index.parent / unquote(link)).resolve() for link in links} == {
        (root / "projects" / "billing" / ONTOLOGY_DIR / "component" / "gateway.md").resolve(),
        (root / "projects" / "billing" / ONTOLOGY_DIR / "plan" / "launch.md").resolve(),
        (root / "projects" / "shop" / ONTOLOGY_DIR / "component" / "api.md").resolve(),
    }


def test_전체_인덱스는_루트_저장소에_파일을_만들지_않는다(onto_cli):
    root = sample(onto_cli, BILLING)
    before = snapshot(root)

    build(onto_cli, root)

    # 지식 저장소의 인덱스만 생기고, 루트 저장소에는 전체 인덱스도 그래프도 생기지 않는다.
    assert snapshot(root) - before == {f"projects/billing/{INDEX}"}


def test_지식_저장소가_하나도_없어도_전체_인덱스가_만들어진다(onto_cli):
    build(onto_cli, sample(onto_cli, {}))

    text = (onto_cli.build_dir / "index.md").read_text(encoding="utf-8")
    assert text.startswith("# 전체 인덱스\n") and "지식 저장소가 없다." in text


def test_링크의_공백과_한글은_퍼센트_인코딩해_링크가_깨지지_않게_한다(onto_cli):
    """식별자 형식을 어긴 페이지다(검사가 오류로 잡는다). 그래도 인덱스에서 빠지지 않고 링크는 열려야 한다."""
    root = sample(onto_cli, {"billing": repo("billing", page("plan/출시 계획", "Plan", title="출시 계획"))})

    build(onto_cli, root)

    assert "- [출시 계획](plan/%EC%B6%9C%EC%8B%9C%20%EA%B3%84%ED%9A%8D.md)\n" in index_of(root)


# --- 인덱스가 없는 지식 저장소 -------------------------------------------------------------
# 따로 클론한 사람과 에이전트에게 인덱스는 온톨로지 층의 유일한 진입점이다(ADR 0006). 없는 것도 어긋난 것이다.


def test_인덱스가_없는_지식_저장소는_어긋난_인덱스로_잡고_종료_코드는_1이다(onto_cli):
    root = sample(onto_cli, BILLING)  # build하지 않았다

    result, findings = validate(onto_cli, root)

    assert result.returncode == 1
    assert [finding[:4] for finding in findings] == [mismatch()]
    assert "인덱스가 없다" in findings[0][4]
    assert not (root / "projects" / "billing" / INDEX).exists()  # 스크립트 검사는 인덱스를 만들지 않는다


def test_페이지가_하나도_없는_지식_저장소도_인덱스가_없으면_잡는다(onto_cli):
    root = sample(onto_cli, {"billing": repo("billing", title="결제")})

    assert mismatches(onto_cli, root) == [mismatch()]


def test_build한_뒤_인덱스를_지우면_어긋난_인덱스로_잡고_다시_만들면_사라진다(onto_cli):
    root = built(onto_cli, BILLING)
    (root / "projects" / "billing" / INDEX).unlink()
    assert mismatches(onto_cli, root) == [mismatch()]

    build(onto_cli, root)

    assert validate(onto_cli, root)[1] == []


def test_온톨로지_층이_없거나_ontology_yaml을_읽을_수_없는_저장소는_인덱스가_없어도_어긋난_인덱스로_잡지_않는다(onto_cli):
    """인덱스를 만들 수 없는 저장소다. 그 원인(층이 없다, 읽을 수 없다)이 따로 보고된다."""
    root = sample(
        onto_cli,
        {
            "plain": {"README.md": "# 온톨로지 층이 없다\n"},
            "broken": {f"{ONTOLOGY_DIR}/ontology.yaml": "name: [깨진\n"},
        },
    )

    findings = validate(onto_cli, root)[1]

    assert {finding[3] for finding in findings} == {"missing-ontology-layer", "unreadable-file"}


def test_OntoCli_root는_기본으로_인덱스를_갖춘_견본을_만든다(onto_cli):
    """다른 검사 항목의 테스트에 인덱스 문제가 끼지 않게 하는 테스트 받침의 약속이다. 인덱스가 없어야 하면 indexed=False다."""
    indexed = onto_cli.root(BILLING)
    unindexed = onto_cli.root(BILLING, indexed=False)

    assert index_of(indexed) == BILLING_INDEX
    assert not (unindexed / "projects" / "billing" / INDEX).exists()
    assert not onto_cli.build_dir.exists()  # 견본을 갖추느라 한 build의 산출물은 남기지 않는다


# --- 읽을 수 없는 파일이 있는 지식 저장소 ----------------------------------------------------


def test_읽을_수_없는_파일이_있는_저장소는_고칠_수_없는_안내를_덧붙이지_않고_원인만_보고한다(onto_cli):
    """`build`는 읽을 수 없는 파일이 있으면 멈춘다. 그런 저장소에 "다시 build한다"고 알릴 수는 없다."""
    root = built(onto_cli, BILLING)
    (root / "projects" / "billing" / ONTOLOGY_DIR / "plan" / "launch.md").write_text("# frontmatter 없음\n", encoding="utf-8")

    result, findings = validate(onto_cli, root)

    assert result.returncode == 1
    assert [finding[3] for finding in findings] == ["unreadable-file"]


# --- 인덱스 경로가 심볼릭 링크나 디렉토리인 지식 저장소 ---------------------------------------
# 지식 저장소는 팀이 공유한다. 거기에 커밋된 심볼릭 링크를 따라가면 `build`가 저장소 밖의 파일을 덮어쓴다.


def link_index(root, target) -> None:
    link = root / "projects" / "billing" / INDEX
    link.symlink_to(target)


def test_인덱스가_심볼릭_링크이면_build는_따라가지_않고_링크_대상을_바꾸지_않는다(onto_cli):
    root = sample(onto_cli, BILLING)
    outside = root / "outside.txt"
    outside.write_text("지식 저장소 밖의 파일\n", encoding="utf-8")
    link_index(root, outside)

    result = onto_cli.run(root, "build")

    assert result.returncode != 0
    assert outside.read_text(encoding="utf-8") == "지식 저장소 밖의 파일\n"
    assert (root / "projects" / "billing" / INDEX).is_symlink()  # 링크를 지우거나 바꾸지도 않는다
    assert f"projects/billing/{INDEX}" in result.stderr and "심볼릭 링크" in result.stderr
    assert "Traceback" not in result.stderr
    assert not onto_cli.graph_file.exists()  # 아무것도 쓰기 전에 멈춘다


def test_인덱스가_없는_파일을_가리키는_심볼릭_링크이면_build가_그_자리에_파일을_새로_만들지_않는다(onto_cli):
    root = sample(onto_cli, BILLING)
    outside = root / "outside.txt"
    link_index(root, outside)  # outside.txt는 없다

    result = onto_cli.run(root, "build")

    assert result.returncode != 0
    assert not outside.exists()
    assert "Traceback" not in result.stderr


def test_인덱스가_심볼릭_링크이면_스크립트_검사는_링크_대상을_읽지_않고_어긋난_인덱스로_보고한다(onto_cli):
    root = built(onto_cli, BILLING)
    secret = root / "secret.txt"
    secret.write_text("비밀 줄 하나\n비밀 줄 둘\n", encoding="utf-8")
    index_file = root / "projects" / "billing" / INDEX
    index_file.unlink()
    link_index(root, secret)

    result, findings = validate(onto_cli, root)

    assert result.returncode == 1
    assert [finding[:4] for finding in findings] == [mismatch()]
    assert "심볼릭 링크" in findings[0][4]
    assert "비밀" not in result.stdout + result.stderr
    assert secret.read_text(encoding="utf-8") == "비밀 줄 하나\n비밀 줄 둘\n"


def test_인덱스_자리가_디렉토리이면_build는_traceback_없이_오류로_알리고_validate는_어긋난_인덱스로_보고한다(onto_cli):
    root = sample(onto_cli, BILLING)
    (root / "projects" / "billing" / INDEX).mkdir()

    build_result = onto_cli.run(root, "build")
    _, findings = validate(onto_cli, root)

    assert build_result.returncode != 0
    assert f"projects/billing/{INDEX}" in build_result.stderr and "일반 파일이 아니다" in build_result.stderr
    assert "Traceback" not in build_result.stderr
    assert not onto_cli.graph_file.exists()
    assert [finding[:4] for finding in findings] == [mismatch()]


def test_온톨로지_층_디렉토리가_지식_저장소_밖을_가리키는_링크이면_build는_밖에_인덱스를_만들지_않는다(onto_cli):
    outside = onto_cli.root({}) / "elsewhere"
    root = onto_cli.root({}, indexed=False)
    for relative, text in BILLING["billing"].items():
        target = outside / Path(relative).relative_to(ONTOLOGY_DIR)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    docs = root / "projects" / "billing" / "docs"
    docs.mkdir(parents=True)
    (docs / "ontology").symlink_to(outside)

    result = onto_cli.run(root, "build")

    assert result.returncode != 0
    assert not (outside / "index.md").exists()
    assert "지식 저장소 밖" in result.stderr and "Traceback" not in result.stderr


# --- 이름이 겹치는 지식 저장소 ----------------------------------------------------------------
# 엔티티의 IRI가 `name`으로 만들어져 두 저장소의 엔티티가 하나로 합쳐진다. 한 저장소의 제목이 다른 저장소의 인덱스에 들 수 있다.

SECRET = "개인 비밀 메모"


def clashing(onto_cli, *, indexed: bool = False):
    """`aaa`가 `name: shop`을 베껴 쓴 견본. 디렉토리 이름이 `shop`인 저장소와 이름이 겹친다."""
    return onto_cli.root(
        {
            "aaa": repo("shop", page("component/api", "Component", title=SECRET, partOf="project")),
            "shop": repo("shop", page("component/api", "Component", title="상점 API", partOf="project"), title="상점"),
        },
        indexed=indexed,
    )


def test_저장소의_name이_겹치면_build는_멈추고_어느_저장소에도_인덱스를_쓰지_않는다(onto_cli):
    root = clashing(onto_cli)

    result = onto_cli.run(root, "build")

    assert result.returncode != 0
    assert f"projects/aaa/{ONTOLOGY_DIR}/ontology.yaml" in result.stderr and "`shop`" in result.stderr
    for name in ("aaa", "shop"):
        assert not (root / "projects" / name / INDEX).exists()
    assert not onto_cli.graph_file.exists()


def test_저장소의_name이_겹쳐도_이미_있던_인덱스를_다른_저장소의_제목으로_고치지_않는다(onto_cli):
    root = onto_cli.root({"shop": BILLING_AS_SHOP})
    before = index_of(root, "shop")
    stray = root / "projects" / "aaa" / ONTOLOGY_DIR
    stray.mkdir(parents=True)
    for relative, text in repo("shop", page("component/gateway", "Component", title=SECRET, partOf="project")).items():
        target = root / "projects" / "aaa" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    result = onto_cli.run(root, "build")

    assert result.returncode != 0
    assert index_of(root, "shop") == before
    assert SECRET not in before


def test_저장소의_name이_겹치면_query도_멈춘다(onto_cli):
    result = onto_cli.run(clashing(onto_cli), "query", "ASK { ?s ?p ?o }")

    assert result.returncode != 0
    assert "`shop`" in result.stderr


def test_저장소의_name이_겹치면_스크립트_검사가_name을_베낀_저장소에_오류를_보고하고_인덱스는_따지지_않는다(onto_cli):
    root = clashing(onto_cli)

    result, findings = validate(onto_cli, root)

    assert result.returncode == 1
    yaml_of = lambda name: f"projects/{name}/{ONTOLOGY_DIR}/ontology.yaml"  # noqa: E731
    assert ("오류", "aaa", yaml_of("aaa"), "duplicate-repository-name") in [finding[:4] for finding in findings]
    assert "index-mismatch" not in [finding[3] for finding in findings]  # 섞인 그래프로 만든 인덱스를 기준으로 삼지 않는다
    assert all(finding[1] != "shop" or finding[3] != "duplicate-repository-name" for finding in findings)  # 고칠 곳은 베낀 쪽이다


def test_저장소의_name이_겹쳐도_이름을_베끼지_않은_저장소의_페이지에는_엮인_문제를_보고하지_않는다(onto_cli):
    """두 저장소의 엔티티가 한 그래프에서 합쳐져 제목이 둘이 되어도, 고칠 필요 없는 쪽(`shop`)에는 아무것도 보고하지 않는다."""
    root = clashing(onto_cli)

    _, findings = validate(onto_cli, root)

    assert [finding for finding in findings if finding[1] == "shop"] == []


def test_이름이_겹치는_저장소를_고치면_각자_자기_페이지만_인덱스에_싣는다(onto_cli):
    root = clashing(onto_cli)
    yaml_file = root / "projects" / "aaa" / ONTOLOGY_DIR / "ontology.yaml"
    yaml_file.write_text(yaml_file.read_text(encoding="utf-8").replace('"shop"', '"aaa"'), encoding="utf-8")

    build(onto_cli, root)

    assert SECRET in index_of(root, "aaa") and "상점 API" not in index_of(root, "aaa")
    assert "상점 API" in index_of(root, "shop") and SECRET not in index_of(root, "shop")
