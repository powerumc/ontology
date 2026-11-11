"""`status`: ingest할 대상, 곧 새로 생겼거나 바뀐 원본 문서를 지식 저장소별로 보여 준다.

온톨로지 도구의 명령줄 진입점을 견본 페이지 디렉토리에 대고 실행한다(`onto_cli`). 한 번은 `just onto status`로 서브모듈로 붙은 지식
저장소를 상대로 실행한다. 해시는 git이 기록하는 blob 해시이고 기대값은 도구의 계산이 아니라 `git hash-object`가 낸 값이다.
줄바꿈 변환이 있는 git 저장소(`core.autocrlf`, `.gitattributes`)에서의 해시는 `test_onto_sources.py`가 확인한다.

보고는 문서 하나에 한 줄이고, 탭으로 나눈 다섯 칸이다: 상태(`새 문서`/`바뀐 문서`), 지식 저장소, 원본 문서(지식 저장소 루트 기준 경로),
현재 해시, 설명. 지식 저장소, 상태(새 문서가 먼저), 경로 순이다. 바뀐 것이 없으면 그렇다고 알리는 한 줄만 나온다. 어떤 파일도 고치지 않는다.
"""

import unicodedata

import pytest

from support.onto_cli import ONTOLOGY_DIR, page, repo

NEW = "새 문서"
CHANGED = "바뀐 문서"
NOTHING = "새로 생겼거나 바뀐 원본 문서가 없다"
OTHER_HASH = "0123456789abcdef0123456789abcdef01234567"
SKIPPED_YAML = f"{ONTOLOGY_DIR}/skipped.yaml"


def file(identifier: str, name: str = "billing") -> str:
    return f"projects/{name}/{ONTOLOGY_DIR}/{identifier}.md"


def git_hash(sandbox, root, path: str, name: str = "billing") -> str:
    """git이 낸 작업 트리 파일의 해시."""
    target = root / "projects" / name / path
    return sandbox.git("hash-object", "--no-filters", target.name, cwd=target.parent).stdout.strip()


def build_root(onto_cli, docs: dict[str, dict[str, str]], **project):
    """`docs`는 `{저장소: {지식 저장소 안의 경로: 내용}}`. 지식 저장소마다 `ontology.yaml`과 그 파일을 둔다. 페이지는 따로 더한다."""
    return onto_cli.root({name: {**repo(name, **project.get(name, {})), **files} for name, files in docs.items()})


def write_files(root, files: dict[str, str], name: str = "billing") -> None:
    for relative, text in files.items():
        target = root / "projects" / name / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def derived_page(identifier: str, *entries: tuple[str, str], title: str | None = None) -> dict[str, str]:
    """`derivedFrom`을 가진 페이지. `partOf: project`로 고아가 아니다."""
    return page(
        identifier,
        "Component",
        title=title or f"컴포넌트 {identifier.rpartition('/')[2]}",
        partOf="project",
        derivedFrom=[{"path": path, "hash": hash_} for path, hash_ in entries],
    )


def skipped(*entries: tuple[str, str]) -> dict[str, str]:
    return {SKIPPED_YAML: "".join(f"- path: {path}\n  hash: \"{hash_}\"\n" for path, hash_ in entries)}


def status(onto_cli, root):
    """`status`를 실행해 `(결과, 보고 목록)`을 돌려준다. 보고는 `(상태, 지식 저장소, 원본 문서, 현재 해시, 설명)`이다."""
    result = onto_cli.run(root, "status")
    records = [tuple(line.split("\t")) for line in result.stdout.splitlines() if "\t" in line]
    assert all(len(record) == 5 for record in records), result.stdout
    return result, records


def listed(onto_cli, root) -> list[tuple[str, str, str]]:
    """보고에서 `(상태, 지식 저장소, 원본 문서)`만."""
    return [record[:3] for record in status(onto_cli, root)[1]]


def contents(root) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


# --- 새 원본 문서 ------------------------------------------------------------------


def test_어떤_페이지도_근거로_삼지_않은_원본_문서는_지식_저장소별로_현재_해시와_함께_새_문서로_보여_준다(onto_cli, sandbox):
    docs = {"billing": {"docs/b-spec.md": "청구 명세\n", "docs/a-plan.md": "계획\n"}, "shop": {"docs/cart.md": "장바구니\n"}}
    root = build_root(onto_cli, docs)

    result, records = status(onto_cli, root)

    assert result.returncode == 0
    assert [record[:4] for record in records] == [
        (NEW, "billing", "docs/a-plan.md", git_hash(sandbox, root, "docs/a-plan.md")),
        (NEW, "billing", "docs/b-spec.md", git_hash(sandbox, root, "docs/b-spec.md")),
        (NEW, "shop", "docs/cart.md", git_hash(sandbox, root, "docs/cart.md", "shop")),
    ]


def test_하위_디렉토리의_원본_문서도_보여_주고_md가_아닌_파일과_저장소_최상위_파일은_대상이_아니다(onto_cli):
    docs = {
        "billing": {
            "docs/a.md": "a\n",
            "docs/deeper/than/b.md": "b\n",
            "docs/image.png": "png",
            "docs/notes.txt": "메모",
            "README.md": "읽어 보세요\n",
            "src/main.py": "print()\n",
        }
    }

    assert listed(onto_cli, build_root(onto_cli, docs)) == [(NEW, "billing", "docs/a.md"), (NEW, "billing", "docs/deeper/than/b.md")]


def test_페이지가_근거로_삼고_해시가_같은_원본_문서는_보여_주지_않는다(onto_cli, sandbox):
    root = build_root(onto_cli, {"billing": {"docs/design.md": "설계\n", "docs/new.md": "새 문서\n"}})
    write_files(root, derived_page("component/auth", ("docs/design.md", git_hash(sandbox, root, "docs/design.md"))))

    assert listed(onto_cli, root) == [(NEW, "billing", "docs/new.md")]


def test_근거로_삼은_해시와_다른_원본_문서는_새_문서가_아니라_바뀐_문서다(onto_cli):
    root = build_root(onto_cli, {"billing": {"docs/design.md": "설계\n"}})
    write_files(root, derived_page("component/auth", ("docs/design.md", OTHER_HASH)))

    assert listed(onto_cli, root) == [(CHANGED, "billing", "docs/design.md")]


def test_출력의_현재_해시는_그대로_derivedFrom에_적을_수_있다(onto_cli, sandbox):
    """보고된 해시를 그대로 적은 페이지는 다음 `status`에서 사라지고 검사에서 낡음이 아니다."""
    root = build_root(onto_cli, {"billing": {"docs/design.md": "설계\n"}})
    (_, _, path, hash_, _), = status(onto_cli, root)[1]

    write_files(root, derived_page("component/auth", (path, hash_)))

    assert status(onto_cli, root)[0].stdout.strip() == NOTHING
    reported = onto_cli.run(root, "validate").stdout
    assert "stale-page" not in reported and "missing-source" not in reported  # 낡지도 없어지지도 않았다


# --- 바뀐 원본 문서 ------------------------------------------------------------------


def test_기록한_해시와_달라진_원본_문서는_그것을_근거로_한_낡은_페이지와_함께_보여_준다(onto_cli, sandbox):
    root = build_root(onto_cli, {"billing": {"docs/design.md": "설계\n"}})
    current = git_hash(sandbox, root, "docs/design.md")
    write_files(
        root,
        {
            **derived_page("component/old", ("docs/design.md", OTHER_HASH)),
            **derived_page("component/older", ("docs/design.md", "f" * 40)),
            **derived_page("component/fresh", ("docs/design.md", current)),
        },
    )

    result, records = status(onto_cli, root)

    assert [record[:4] for record in records] == [(CHANGED, "billing", "docs/design.md", current)]
    detail = records[0][4]
    assert "component/old" in detail and OTHER_HASH in detail
    assert "component/older" in detail and "f" * 40 in detail
    assert "component/fresh" not in detail  # 지금 내용을 근거로 한 페이지는 낡지 않았다
    assert result.returncode == 0


def test_커밋하지_않은_수정도_바뀐_문서로_본다(onto_cli, sandbox):
    """git이 커밋한 파일의 해시(`git rev-parse HEAD:<경로>`)를 적은 페이지는 낡지 않다가, 커밋하지 않은 수정만으로 바뀐 문서가 된다."""
    root = build_root(onto_cli, {"billing": {"docs/design.md": "설계\n"}})
    repository = root / "projects" / "billing"
    sandbox.git("init", "-q", cwd=repository)
    sandbox.git("add", "docs/design.md", cwd=repository)
    sandbox.git("commit", "-q", "-m", "원본 문서", cwd=repository)
    committed = sandbox.git("rev-parse", "HEAD:docs/design.md", cwd=repository).stdout.strip()
    write_files(root, derived_page("component/auth", ("docs/design.md", committed)))
    assert status(onto_cli, root)[0].stdout.strip() == NOTHING

    (repository / "docs" / "design.md").write_text("설계\n커밋하지 않은 수정\n", encoding="utf-8")

    (record,) = status(onto_cli, root)[1]
    assert record[:4] == (CHANGED, "billing", "docs/design.md", git_hash(sandbox, root, "docs/design.md"))


def test_없어진_원본_문서는_status에_나오지_않는다_이는_스크립트_검사의_몫이다(onto_cli):
    root = build_root(onto_cli, {"billing": {}})
    write_files(root, derived_page("component/auth", ("docs/gone.md", OTHER_HASH)))

    result, records = status(onto_cli, root)

    assert records == [] and result.stdout.strip() == NOTHING
    assert "missing-source" in onto_cli.run(root, "validate").stdout


# --- 넘긴 문서 -----------------------------------------------------------------------


def test_넘긴_문서의_목록에_경로와_해시가_적힌_원본_문서는_새_문서로_나오지_않는다(onto_cli, sandbox):
    root = build_root(onto_cli, {"billing": {"docs/meeting.md": "회의록\n", "docs/design.md": "설계\n"}})
    write_files(root, skipped(("docs/meeting.md", git_hash(sandbox, root, "docs/meeting.md"))))

    assert listed(onto_cli, root) == [(NEW, "billing", "docs/design.md")]


def test_넘긴_문서의_내용이_바뀌면_바뀐_문서로_다시_나온다(onto_cli, sandbox):
    root = build_root(onto_cli, {"billing": {"docs/meeting.md": "회의록\n"}})
    recorded = git_hash(sandbox, root, "docs/meeting.md")
    write_files(root, skipped(("docs/meeting.md", recorded)))
    assert status(onto_cli, root)[1] == []

    write_files(root, {"docs/meeting.md": "회의록\n결정이 하나 늘었다\n"})

    (record,) = status(onto_cli, root)[1]
    assert record[:4] == (CHANGED, "billing", "docs/meeting.md", git_hash(sandbox, root, "docs/meeting.md"))
    assert "넘긴" in record[4] and recorded in record[4]


def test_넘긴_문서의_목록에_적힌_해시가_틀려도_그_경로의_문서가_새_문서가_되지_않고_바뀐_문서가_된다(onto_cli):
    root = build_root(onto_cli, {"billing": {"docs/meeting.md": "회의록\n"}})
    write_files(root, skipped(("docs/meeting.md", OTHER_HASH)))

    assert listed(onto_cli, root) == [(CHANGED, "billing", "docs/meeting.md")]


def test_넘긴_문서의_목록에_적힌_문서가_없어지면_status에는_나오지_않고_검사가_잡는다(onto_cli):
    root = build_root(onto_cli, {"billing": {}})
    write_files(root, skipped(("docs/gone.md", OTHER_HASH)))

    assert status(onto_cli, root)[0].stdout.strip() == NOTHING
    assert "missing-skipped-source" in onto_cli.run(root, "validate").stdout


def test_넘긴_문서는_다른_지식_저장소의_같은_경로_문서에_영향을_주지_않는다(onto_cli, sandbox):
    root = build_root(onto_cli, {"billing": {"docs/a.md": "같은 내용\n"}, "shop": {"docs/a.md": "같은 내용\n"}})
    write_files(root, skipped(("docs/a.md", git_hash(sandbox, root, "docs/a.md"))))

    assert listed(onto_cli, root) == [(NEW, "shop", "docs/a.md")]


def test_넘겼던_문서를_나중에_페이지로_ingest했으면_넘긴_목록의_옛_항목은_무시하고_status에_나오지_않는다(onto_cli, sandbox):
    """회의록을 넘겼다 -> 내용이 바뀌어 바뀐 문서로 다시 나왔다 -> 에이전트가 읽고 페이지를 만들었다. 지금 내용은 이미 처리되었다."""
    root = build_root(onto_cli, {"billing": {"docs/meeting.md": "회의록\n결정이 하나 늘었다\n"}})
    write_files(
        root,
        {
            **skipped(("docs/meeting.md", OTHER_HASH)),
            **derived_page("component/auth", ("docs/meeting.md", git_hash(sandbox, root, "docs/meeting.md"))),
        },
    )

    result, records = status(onto_cli, root)

    assert records == [] and result.stdout.strip() == NOTHING


def test_지금_내용을_근거로_한_페이지가_있어도_옛_내용을_근거로_한_다른_페이지는_낡았다고_알리고_넘긴_문서_얘기는_하지_않는다(onto_cli, sandbox):
    root = build_root(onto_cli, {"billing": {"docs/meeting.md": "회의록\n"}})
    current = git_hash(sandbox, root, "docs/meeting.md")
    write_files(
        root,
        {
            **skipped(("docs/meeting.md", OTHER_HASH)),
            **derived_page("component/auth", ("docs/meeting.md", current)),
            **derived_page("component/old", ("docs/meeting.md", "f" * 40)),
        },
    )

    (record,) = status(onto_cli, root)[1]

    assert record[:4] == (CHANGED, "billing", "docs/meeting.md", current)
    assert "component/old" in record[4] and "component/auth" not in record[4] and "넘긴" not in record[4]


# --- 바뀐 것이 없을 때 -----------------------------------------------------------------


def test_바뀐_것이_없으면_그렇다고_알려_주고_0으로_끝난다(onto_cli, sandbox):
    root = build_root(onto_cli, {"billing": {"docs/design.md": "설계\n", "docs/meeting.md": "회의록\n"}})
    write_files(
        root,
        {
            **derived_page("component/auth", ("docs/design.md", git_hash(sandbox, root, "docs/design.md"))),
            **skipped(("docs/meeting.md", git_hash(sandbox, root, "docs/meeting.md"))),
        },
    )

    result = onto_cli.run(root, "status")

    assert result.returncode == 0
    assert result.stdout.strip() == NOTHING


@pytest.mark.parametrize("repos", [{}, {"billing": {}}], ids=["지식_저장소_없음", "원본_문서_없음"])
def test_원본_문서가_하나도_없어도_바뀐_것이_없다고_알린다(onto_cli, repos):
    result = onto_cli.run(build_root(onto_cli, repos), "status")

    assert (result.returncode, result.stdout.strip()) == (0, NOTHING)


def test_새_문서나_바뀐_문서가_있으면_바뀐_것이_없다는_말은_나오지_않는다(onto_cli):
    result = onto_cli.run(build_root(onto_cli, {"billing": {"docs/a.md": "a\n"}}), "status")

    assert NOTHING not in result.stdout


# --- 순서 ------------------------------------------------------------------------------


def test_지식_저장소_상태_경로_순으로_보여_주고_새_문서가_바뀐_문서보다_먼저다(onto_cli):
    docs = {
        "shop": {"docs/z.md": "z\n"},
        "billing": {"docs/b-changed.md": "b\n", "docs/c-new.md": "c\n", "docs/a-new.md": "a\n"},
    }
    root = build_root(onto_cli, docs)
    write_files(root, derived_page("component/auth", ("docs/b-changed.md", OTHER_HASH)))

    assert listed(onto_cli, root) == [
        (NEW, "billing", "docs/a-new.md"),
        (NEW, "billing", "docs/c-new.md"),
        (CHANGED, "billing", "docs/b-changed.md"),
        (NEW, "shop", "docs/z.md"),
    ]


# --- 대상 범위: 규칙의 글롭과 제외 경로 ---------------------------------------------------


def test_대상_범위의_기본값은_docs_아래_md_파일이고_온톨로지_층은_빠진다(onto_cli):
    root = build_root(onto_cli, {"billing": {"docs/a.md": "a\n", "docs/ontology/index.md": "# 인덱스\n", "design/b.md": "b\n"}})
    write_files(root, page("plan/launch", "Plan", title="출시", about="project"))

    # 온톨로지 층의 페이지(`docs/ontology/plan/launch.md`)와 인덱스는 원본 문서가 아니다
    assert listed(onto_cli, root) == [(NEW, "billing", "docs/a.md")]


def test_지식_저장소의_규칙으로_대상_범위를_바꾸면_그_저장소의_목록만_달라진다(onto_cli):
    docs = {"billing": {"docs/a.md": "a\n", "design/b.md": "b\n"}, "shop": {"docs/a.md": "a\n", "design/b.md": "b\n"}}
    root = onto_cli.root(
        {
            "billing": {**repo("billing", rules={"sources": {"include": ["design/**/*.md"]}}), **docs["billing"]},
            "shop": {**repo("shop"), **docs["shop"]},
        }
    )

    assert listed(onto_cli, root) == [(NEW, "billing", "design/b.md"), (NEW, "shop", "docs/a.md")]


def test_루트_기본_규칙의_대상_범위를_바꾸면_모든_지식_저장소의_목록이_달라진다(onto_cli):
    root = build_root(onto_cli, {"billing": {"docs/a.md": "a\n", "design/b.md": "b\n"}, "shop": {"docs/a.md": "a\n", "design/b.md": "b\n"}})
    onto_cli.replace_in_root_rules('    - "docs/**/*.md"\n', '    - "design/**/*.md"\n')

    assert listed(onto_cli, root) == [(NEW, "billing", "design/b.md"), (NEW, "shop", "design/b.md")]


def test_제외_경로의_문서는_대상이_아니다(onto_cli):
    root = onto_cli.root(
        {
            "billing": {
                **repo("billing", rules={"sources": {"exclude": ["docs/ontology/**", "docs/drafts/**", "docs/*.tmp.md"]}}),
                "docs/a.md": "a\n",
                "docs/drafts/wip.md": "초안\n",
                "docs/drafts/deep/wip2.md": "초안\n",
                "docs/x.tmp.md": "임시\n",
            }
        }
    )

    assert listed(onto_cli, root) == [(NEW, "billing", "docs/a.md")]


def test_온톨로지_층은_규칙이_제외_경로를_비우고_모든_md를_포함해도_항상_대상에서_빠진다(onto_cli):
    rules = {"sources": {"include": ["**/*.md", "docs/**"], "exclude": []}}
    root = onto_cli.root(
        {
            "billing": {
                **repo("billing", rules=rules),
                "docs/a.md": "a\n",
                "docs/ontology/index.md": "# 인덱스\n",
                **page("plan/launch", "Plan", title="출시", about="project"),
                **page("term/token", "Term", title="토큰", about="project"),
            }
        }
    )

    assert listed(onto_cli, root) == [(NEW, "billing", "docs/a.md")]


def test_숨김_파일과_숨김_디렉토리는_글롭에_맞아도_대상이_아니다(onto_cli):
    rules = {"sources": {"include": ["**/*.md"]}}
    root = onto_cli.root(
        {
            "billing": {
                **repo("billing", rules=rules),
                "docs/a.md": "a\n",
                "docs/.hidden.md": "숨김\n",
                ".onto/template/page.md": "루트 관리 파일\n",
                ".git/notes.md": "git\n",
                ".claude/skills/x/SKILL.md": "스킬\n",
            }
        }
    )

    assert listed(onto_cli, root) == [(NEW, "billing", "docs/a.md")]


@pytest.mark.parametrize(
    ("include", "expected"),
    [
        ([".onto/**/*.md"], []),
        (["docs/.drafts/*.md"], []),
        ([".onto/**/*.md", "docs/.drafts/*.md", "docs/**/*.md"], ["docs/a.md"]),
        (["**/*.md"], ["docs/a.md"]),
    ],
    ids=["숨김_디렉토리에서_시작", "중간에_숨김_디렉토리", "다른_글롭과_함께", "모든_md"],
)
def test_숨김_경로는_글롭이_어떻게_쓰여도_항상_제외한다(onto_cli, include, expected):
    files = {"docs/a.md": "a\n", ".onto/template/page.md": "루트 관리 파일\n", "docs/.drafts/wip.md": "초안\n"}
    root = onto_cli.root({"billing": {**repo("billing", rules={"sources": {"include": include}}), **files}})

    assert [path for _, _, path in listed(onto_cli, root)] == expected


def test_심볼릭_링크는_원본_문서가_아니라_같은_문서가_두_번_나오지_않고_온톨로지_층의_페이지도_나오지_않는다(onto_cli):
    root = build_root(onto_cli, {"billing": {"docs/v2.md": "두 번째 판\n"}})
    write_files(root, derived_page("component/auth"))
    docs = root / "projects" / "billing" / "docs"
    (docs / "latest.md").symlink_to("v2.md")
    (docs / "page-link.md").symlink_to("ontology/component/auth.md")  # 온톨로지 층의 페이지를 가리키는 링크로 층의 제외를 우회하지 못한다

    assert listed(onto_cli, root) == [(NEW, "billing", "docs/v2.md")]


@pytest.mark.parametrize(
    ("glob", "expected"),
    [
        ("docs/**/*.md", ["docs/a.md", "docs/x/b.md", "docs/x/y/c.md"]),
        ("docs/*.md", ["docs/a.md"]),
        ("docs/x/**", ["docs/x/b.md", "docs/x/y/c.md", "docs/x/y/d.txt"]),
        ("**/c.md", ["docs/x/y/c.md"]),
        ("docs/[ab].md", ["docs/a.md"]),
        ("docs/?.md", ["docs/a.md"]),
        ("docs/x/*/*.md", ["docs/x/y/c.md"]),
    ],
    ids=["이중별_0개_이상", "한_디렉토리", "이중별_끝", "이중별_앞", "글자_집합", "물음표", "중간_별"],
)
def test_글롭은_이중별이_디렉토리를_0개_이상_건너뛰고_별은_한_디렉토리_안에서만_맞는다(onto_cli, glob, expected):
    files = {path: "내용\n" for path in ("docs/a.md", "docs/x/b.md", "docs/x/y/c.md", "docs/x/y/d.txt")}
    root = onto_cli.root({"billing": {**repo("billing", rules={"sources": {"include": [glob]}}), **files}})

    assert [path for _, _, path in listed(onto_cli, root)] == expected


def test_원본_문서_경로의_대소문자가_다르면_validate처럼_그_문서를_근거로_삼지_않은_것으로_본다(onto_cli, sandbox):
    """macOS(대소문자를 구분하지 않는 파일 시스템)에서도 Linux와 같은 결과다. validate는 `missing-source`를 낸다."""
    root = build_root(onto_cli, {"billing": {"docs/design.md": "설계\n"}})
    write_files(root, derived_page("component/auth", ("docs/Design.md", git_hash(sandbox, root, "docs/design.md"))))

    assert listed(onto_cli, root) == [(NEW, "billing", "docs/design.md")]
    assert "missing-source" in onto_cli.run(root, "validate").stdout


@pytest.mark.parametrize(("on_disk", "written"), [("NFD", "NFC"), ("NFC", "NFD")], ids=["파일이_NFD", "파일이_NFC"])
def test_유니코드_정규화_형식이_달라도_같은_이름의_문서로_보아_근거로_삼은_문서와_넘긴_문서가_다시_나오지_않는다(onto_cli, sandbox, on_disk, written):
    name = "docs/설계 문서.md"
    meeting = "docs/회의록.md"
    root = build_root(
        onto_cli, {"billing": {unicodedata.normalize(on_disk, name): "설계\n", unicodedata.normalize(on_disk, meeting): "회의록\n"}}
    )
    hashes = {path: git_hash(sandbox, root, path) for path in (unicodedata.normalize(on_disk, name), unicodedata.normalize(on_disk, meeting))}
    write_files(
        root,
        {
            **derived_page("component/auth", (unicodedata.normalize(written, name), hashes[unicodedata.normalize(on_disk, name)])),
            **skipped((unicodedata.normalize(written, meeting), hashes[unicodedata.normalize(on_disk, meeting)])),
        },
    )

    result = onto_cli.run(root, "status")

    assert (result.returncode, result.stdout.strip()) == (0, NOTHING)


# --- 어떤 파일도 고치지 않는다 -------------------------------------------------------------


def test_status는_어떤_파일도_고치거나_만들지_않는다(onto_cli, sandbox):
    root = build_root(onto_cli, {"billing": {"docs/a.md": "a\n", "docs/b.md": "b\n", "docs/c.md": "c\n"}})
    write_files(
        root,
        {**derived_page("component/auth", ("docs/a.md", OTHER_HASH)), **skipped(("docs/c.md", git_hash(sandbox, root, "docs/c.md")))},
    )
    before = contents(root)

    assert onto_cli.run(root, "status").returncode == 0

    assert contents(root) == before
    assert not onto_cli.build_dir.exists()


# --- 규칙과 읽을 수 없는 파일 ---------------------------------------------------------------


def test_깨진_rules는_기본값으로_대신하지_않고_그_저장소를_알리며_다른_저장소는_계속_보여_준다(onto_cli):
    broken = {"sources": {"include": 5}}
    root = onto_cli.root(
        {
            "billing": {**repo("billing", rules=broken), "docs/a.md": "a\n"},
            "shop": {**repo("shop"), "docs/cart.md": "장바구니\n"},
        }
    )

    result, records = status(onto_cli, root)

    assert result.returncode == 1
    assert "projects/billing/docs/ontology/ontology.yaml" in result.stderr and "rules.sources.include" in result.stderr
    assert [record[:3] for record in records] == [(NEW, "shop", "docs/cart.md")]  # billing의 문서를 기본 범위로 보여 주지 않는다
    assert NOTHING not in result.stdout


def test_깨진_rules만_있으면_바뀐_것이_없다고_알리지_않는다(onto_cli):
    root = onto_cli.root({"billing": {**repo("billing", rules={"sources": {"include": 5}}), "docs/a.md": "a\n"}})

    result = onto_cli.run(root, "status")

    assert result.returncode == 1 and NOTHING not in result.stdout


def test_읽을_수_없는_페이지가_있으면_build처럼_멈추고_그_파일을_알린다(onto_cli):
    root = build_root(onto_cli, {"billing": {"docs/a.md": "a\n"}})
    write_files(root, {f"{ONTOLOGY_DIR}/component/raw.md": "frontmatter가 없다\n"})

    result = onto_cli.run(root, "status")

    assert result.returncode == 1
    assert file("component/raw") in result.stderr and result.stdout == ""


def test_읽을_수_없는_파일의_검사_항목을_꺼_둔_저장소는_그_파일을_건너뛰고_status를_계속한다(onto_cli):
    rules = {"checks": {"unreadable-file": {"enabled": False}}}
    root = onto_cli.root({"billing": {**repo("billing", rules=rules), "docs/a.md": "a\n", **{f"{ONTOLOGY_DIR}/component/raw.md": "frontmatter가 없다\n"}}})

    result, records = status(onto_cli, root)

    assert result.returncode == 0
    assert [record[:3] for record in records] == [(NEW, "billing", "docs/a.md")]


def test_온톨로지_층이_없는_지식_저장소는_건너뛰고_알린다(onto_cli):
    root = onto_cli.root({"legacy": {"docs/a.md": "a\n"}, "billing": {**repo("billing"), "docs/b.md": "b\n"}})

    result, records = status(onto_cli, root)

    assert [record[:3] for record in records] == [(NEW, "billing", "docs/b.md")]
    assert "legacy" in result.stderr


# --- just onto status --------------------------------------------------------------------


def test_just_onto_status가_서브모듈로_붙은_지식_저장소의_새_문서와_바뀐_문서를_보여_준다(sandbox):
    design = "# 설계\n"
    files = {
        **repo("billing", derived_page("component/auth", ("docs/design.md", OTHER_HASH))),
        "docs/design.md": design,
        "docs/new.md": "새 문서\n",
    }
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing", files=files))
    expected = {
        path: sandbox.git("hash-object", "--no-filters", path, cwd=root.work / "projects" / "billing" / "docs").stdout.strip()
        for path in ("design.md", "new.md")
    }

    result = sandbox.just("onto", "status", cwd=root.work)

    assert result.returncode == 0, result.stderr
    records = [tuple(line.split("\t")) for line in result.stdout.splitlines()]
    assert [record[:4] for record in records] == [
        (NEW, "billing", "docs/new.md", expected["new.md"]),
        (CHANGED, "billing", "docs/design.md", expected["design.md"]),
    ]
    assert sandbox.git("status", "--porcelain", cwd=root.work).stdout == ""  # 아무것도 만들지 않는다
