"""원본 문서의 기록: 페이지의 `derivedFrom`, 넘긴 문서의 목록(`skipped.yaml`), 그것이 그래프와 스크립트 검사에 나타나는 모습.

온톨로지 도구의 명령줄 진입점을 견본 페이지 디렉토리에 대고 실행한다(`onto_cli`).

- `derivedFrom`은 `{path, hash}` 항목(또는 그 목록)이다. `path`는 지식 저장소 루트 기준 원본 문서의 경로, `hash`는 그 문서의
  git 해시(`git hash-object`가 내는 40자리 소문자 16진수)다. 해시의 기대값은 도구의 계산이 아니라 git이 낸 값을 쓴다.
- 그래프에서 항목 하나는 `Source` 엔티티(`onto:sourcePath`, `onto:sourceHash`)가 되고 페이지가 `onto:derivedFrom`으로 가리킨다.
  `Source`는 페이지를 갖지 않는다. 질의 결과에서는 원본 문서의 파일 경로로 보인다.
- 낡음(`stale-page`), 없어진 원본 문서(`missing-source`), 없어진 넘긴 문서(`missing-skipped-source`)는 스크립트 검사가 잡는다.
"""

import pytest

from support.onto_cli import ONTOLOGY_DIR, page, repo

ERROR = "오류"
WARNING = "경고"

DESIGN = "docs/design.md"
DESIGN_TEXT = "# 설계\n\n인증은 토큰으로 한다.\n"
OTHER_HASH = "0123456789abcdef0123456789abcdef01234567"
SKIPPED_YAML = f"{ONTOLOGY_DIR}/skipped.yaml"


def file(identifier: str, name: str = "billing") -> str:
    return f"projects/{name}/{ONTOLOGY_DIR}/{identifier}.md"


def yaml_file(name: str = "billing") -> str:
    return f"projects/{name}/{SKIPPED_YAML}"


def git_hash_of(sandbox, content: str) -> str:
    """내용을 `git hash-object`로 해시한 값. 기대값은 도구의 계산이 아니라 git에게서 얻는다. 견본 루트를 만들기 전에 해시가 필요해서 임시 파일로 구한다."""
    directory = sandbox.base / f"hash-{len(list(sandbox.base.glob('hash-*')))}"
    directory.mkdir()
    (directory / "content").write_bytes(content.encode("utf-8"))
    return sandbox.git("hash-object", "--no-filters", "content", cwd=directory).stdout.strip()


def validate(onto_cli, root):
    result = onto_cli.run(root, "validate")
    findings = [tuple(line.split("\t")) for line in result.stdout.splitlines()]
    assert all(len(finding) == 5 for finding in findings), result.stdout
    return result, findings


def found(onto_cli, root) -> list[tuple[str, str, str, str]]:
    return [finding[:4] for finding in validate(onto_cli, root)[1]]


def derived(*entries: tuple[str, str]) -> list[dict[str, str]]:
    return [{"path": path, "hash": hash_} for path, hash_ in entries]


def billing(*pages, files: dict[str, str] | None = None, **project) -> dict[str, dict[str, str]]:
    """`billing` 지식 저장소 하나. `files`는 지식 저장소 안의 경로로 적은 원본 문서 등의 파일이다."""
    return {"billing": {**repo("billing", *pages, **project), **(files or {})}}


def sourced_page(identifier: str = "component/auth", *entries: tuple[str, str], **fields):
    """`partOf: project`로 고아가 아니고 `derivedFrom`을 가진 페이지."""
    title = fields.pop("title", f"인증 {identifier.rpartition('/')[2]}")  # 제목이 같으면 중복 엔티티가 된다
    return page(identifier, "Component", title=title, partOf="project", derivedFrom=derived(*entries), **fields)


# --- 그래프: Source 엔티티와 출처 관계 -------------------------------------------


def test_derivedFrom의_경로와_해시가_Source_엔티티와_출처_관계로_그래프에_나타난다(onto_cli):
    root = onto_cli.root(billing(sourced_page("component/auth", (DESIGN, OTHER_HASH))))

    rows = onto_cli.query(
        root,
        "SELECT ?page ?path ?hash WHERE { ?page onto:derivedFrom ?s . ?s a onto:Source ; onto:sourcePath ?path ; onto:sourceHash ?hash }",
    )

    assert rows == [[file("component/auth"), DESIGN, OTHER_HASH]]


def test_Source_엔티티는_질의_결과에서_원본_문서의_파일_경로로_보인다(onto_cli):
    root = onto_cli.root(billing(sourced_page("component/auth", (DESIGN, OTHER_HASH))))

    sources = onto_cli.query(root, "SELECT ?s WHERE { ?s a onto:Source }")

    assert sources == [[f"projects/billing/{DESIGN}"]]


def test_Source_엔티티는_페이지를_따로_갖지_않아_온톨로지_층에_파일이_늘지_않고_검사에도_걸리지_않는다(onto_cli, sandbox):
    root, _ = current_repos(onto_cli, sandbox)

    result, findings = validate(onto_cli, root)

    assert findings == []  # Source는 클래스, 필수 속성, 중복 같은 어느 구조 제약에도 걸리지 않는다
    assert result.returncode == 0
    layer = root / "projects" / "billing" / ONTOLOGY_DIR
    pages = sorted(path.relative_to(layer).as_posix() for path in layer.rglob("*.md") if path.name != "index.md")  # 생성된 인덱스는 페이지가 아니다
    assert pages == ["component/auth.md"]


def test_같은_원본_문서를_같은_해시로_가리킨_페이지는_Source_엔티티를_나누고_해시가_다르면_따로_둔다(onto_cli):
    root = onto_cli.root(
        billing(
            sourced_page("component/auth", (DESIGN, OTHER_HASH)),
            sourced_page("component/session", (DESIGN, OTHER_HASH)),
            sourced_page("component/token", (DESIGN, "f" * 40)),
        )
    )

    rows = onto_cli.query(
        root, "SELECT ?hash (COUNT(?page) AS ?pages) WHERE { ?page onto:derivedFrom ?s . ?s onto:sourceHash ?hash } GROUP BY ?hash ORDER BY ?hash"
    )
    sources = onto_cli.query(root, "SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a onto:Source }")

    assert rows == [[OTHER_HASH, "2"], ["f" * 40, "1"]]
    assert sources == [["2"]]


def test_derivedFrom_하나에_원본_문서를_여럿_적을_수_있고_항목_하나만_적어도_된다(onto_cli):
    many = sourced_page("component/auth", (DESIGN, OTHER_HASH), ("docs/api.md", "f" * 40))
    single = page("component/token", "Component", title="토큰", partOf="project", derivedFrom={"path": "docs/token.md", "hash": OTHER_HASH})
    root = onto_cli.root(billing(many, single))

    rows = onto_cli.query(
        root, "SELECT ?page ?path WHERE { ?page onto:derivedFrom ?s . ?s onto:sourcePath ?path } ORDER BY ?page ?path"
    )

    assert rows == [
        [file("component/auth"), "docs/api.md"],
        [file("component/auth"), DESIGN],
        [file("component/token"), "docs/token.md"],
    ]


def test_저장소가_다르면_같은_경로와_해시도_다른_Source_엔티티다(onto_cli):
    repos = {
        **billing(sourced_page("component/auth", (DESIGN, OTHER_HASH))),
        "shop": repo("shop", sourced_page("component/cart", (DESIGN, OTHER_HASH)), title="상점"),
    }
    root = onto_cli.root(repos)

    sources = onto_cli.query(root, "SELECT ?s WHERE { ?s a onto:Source } ORDER BY ?s")

    assert sources == [[f"projects/billing/{DESIGN}"], [f"projects/shop/{DESIGN}"]]


def test_Source는_공통_어휘의_PROV_Entity의_하위_클래스라_추론된_질의에서도_보인다(onto_cli):
    root = onto_cli.root(billing(sourced_page("component/auth", (DESIGN, OTHER_HASH))))

    rows = onto_cli.query(root, "SELECT ?s WHERE { ?s a prov:Entity }")

    assert rows == [[f"projects/billing/{DESIGN}"]]


# --- derivedFrom은 정의된 키이고 관계가 아니다 --------------------------------------


def test_derivedFrom은_정의되지_않은_키로_보고되지_않는다(onto_cli, sandbox):
    root, _ = current_repos(onto_cli, sandbox)

    assert "undefined-key" not in [finding[3] for finding in validate(onto_cli, root)[1]]


def test_derivedFrom만_가진_페이지는_다른_엔티티와의_관계가_없어_여전히_고아_페이지다(onto_cli):
    lonely = page("component/lonely", "Component", title="외톨이", derivedFrom=derived((DESIGN, OTHER_HASH)))
    root = onto_cli.root(billing(lonely))

    assert [f for f in found(onto_cli, root) if f[3] == "orphan-page"] == [(WARNING, "billing", file("component/lonely"), "orphan-page")]


def test_derivedFrom이_가리키는_Source는_다른_페이지의_관계_대상으로_세지_않는다(onto_cli):
    """두 페이지가 같은 원본 문서를 근거로 삼아도 서로 이어진 것이 아니다."""
    one = page("component/a", "Component", title="A", derivedFrom=derived((DESIGN, OTHER_HASH)))
    two = page("component/b", "Component", title="B", derivedFrom=derived((DESIGN, OTHER_HASH)))
    root = onto_cli.root(billing(one, two))

    orphans = [f for f in found(onto_cli, root) if f[3] == "orphan-page"]

    assert [f[2] for f in orphans] == [file("component/a"), file("component/b")]


def test_정의되지_않은_키_보고가_쓸_수_있는_키에_derivedFrom을_보여_준다(onto_cli):
    root = onto_cli.root(billing(page("component/api", "Component", title="API", partOf="project", owner="kim")))

    message = next(f[4] for f in validate(onto_cli, root)[1] if f[3] == "undefined-key")

    assert "derivedFrom" in message


@pytest.mark.parametrize(
    "value",
    [
        "docs/design.md",
        5,
        [{"path": DESIGN}],
        [{"hash": OTHER_HASH}],
        [{"path": DESIGN, "hash": OTHER_HASH, "note": "메모"}],
        [{"path": DESIGN, "hash": "abc123"}],
        [{"path": DESIGN, "hash": OTHER_HASH.upper()}],
        [{"path": DESIGN, "hash": 123}],
        [{"path": "", "hash": OTHER_HASH}],
        [{"path": "/etc/passwd", "hash": OTHER_HASH}],
        [{"path": "../outside.md", "hash": OTHER_HASH}],
        [{"path": "docs/../design.md", "hash": OTHER_HASH}],
        [{"path": "./docs/design.md", "hash": OTHER_HASH}],
        [{"path": "docs//design.md", "hash": OTHER_HASH}],
        [{"path": "docs/", "hash": OTHER_HASH}],
        [f"{DESIGN}@{OTHER_HASH}"],
        [[DESIGN, OTHER_HASH]],
    ],
    ids=[
        "문자열", "숫자", "해시_없음", "경로_없음", "모르는_키", "짧은_해시", "대문자_해시", "숫자_해시", "빈_경로", "절대_경로", "상위_경로", "중간_상위_경로",
        "점_경로", "겹친_슬래시", "디렉토리_모양", "문자열_항목", "목록_항목",
    ],
)
def test_derivedFrom의_모양이_틀리면_값의_종류_오류로_보고하고_build도_멈춘다(onto_cli, value):
    bad = page("component/auth", "Component", title="인증", partOf="project", derivedFrom=value)
    root = onto_cli.root(billing(bad))

    result, findings = validate(onto_cli, root)

    assert [f[:4] for f in findings if f[3] == "invalid-value"] == [(ERROR, "billing", file("component/auth"), "invalid-value")]
    assert "derivedFrom" in next(f[4] for f in findings if f[3] == "invalid-value")
    assert result.returncode == 1
    assert onto_cli.run(root, "build").returncode == 1


def test_derivedFrom_값이_틀린_페이지의_다른_문제도_가려지지_않는다(onto_cli):
    bad = page("component/auth", "Component", title="인증", derivedFrom="docs/design.md", owner="kim")
    root = onto_cli.root(billing(bad))

    checks = sorted(f[3] for f in validate(onto_cli, root)[1])

    assert checks == ["invalid-value", "undefined-key"]  # 읽을 수 없는 페이지는 그래프에 없어 고아 여부는 따지지 않는다


def test_derivedFrom을_비워_두면_원본_문서가_없는_페이지로_읽는다(onto_cli):
    empty = page("component/auth", "Component", title="인증", partOf="project", derivedFrom=None)
    root = onto_cli.root(billing(empty))

    assert validate(onto_cli, root)[1] == []
    assert onto_cli.query(root, "SELECT ?s WHERE { ?s a onto:Source }") == []


# --- 스크립트 검사: 낡음 -----------------------------------------------------------


def current_repos(onto_cli, sandbox, *, text: str = DESIGN_TEXT, **extra):
    """원본 문서의 해시를 git에게서 받아 적은 지식 저장소. `(루트, 해시)`를 돌려준다."""
    hash_ = git_hash_of(sandbox, text)
    root = onto_cli.root(billing(sourced_page("component/auth", (DESIGN, hash_)), files={DESIGN: text}, **extra))
    return root, hash_


def test_기록한_해시와_원본_문서의_현재_내용이_같으면_낡지_않았다(onto_cli, sandbox):
    root, _ = current_repos(onto_cli, sandbox)

    result, findings = validate(onto_cli, root)

    assert (result.returncode, findings) == (0, [])


def test_원본_문서가_바뀌면_그것을_근거로_한_페이지를_낡음으로_잡고_해시를_알린다(onto_cli, sandbox):
    root, recorded = current_repos(onto_cli, sandbox)
    changed = DESIGN_TEXT + "토큰은 한 시간 뒤 만료된다.\n"
    (root / "projects" / "billing" / DESIGN).write_text(changed, encoding="utf-8")
    current = git_hash_of(sandbox, changed)

    result, findings = validate(onto_cli, root)

    assert [f[:4] for f in findings] == [(WARNING, "billing", file("component/auth"), "stale-page")]
    message = findings[0][4]
    assert DESIGN in message and recorded in message and current in message
    assert result.returncode == 0  # 낡음은 기본으로 경고다


def test_낡음은_루트_기본_규칙으로_오류로_올릴_수_있고_그러면_종료_코드가_1이_된다(onto_cli, sandbox):
    root, _ = current_repos(onto_cli, sandbox)
    (root / "projects" / "billing" / DESIGN).write_text("바뀐 내용\n", encoding="utf-8")
    onto_cli.set_root_check("stale-page", severity="error")

    result, findings = validate(onto_cli, root)

    assert [f[:4] for f in findings] == [(ERROR, "billing", file("component/auth"), "stale-page")]
    assert result.returncode == 1


def test_낡음_검사는_지식_저장소가_규칙으로_끌_수_있다(onto_cli, sandbox):
    root, _ = current_repos(onto_cli, sandbox, rules={"checks": {"stale-page": {"enabled": False}}})
    (root / "projects" / "billing" / DESIGN).write_text("바뀐 내용\n", encoding="utf-8")

    assert validate(onto_cli, root)[1] == []


def test_원본_문서를_근거로_한_페이지마다_낡음으로_잡고_같은_원본_문서를_다른_해시로_적은_페이지만_낡았다(onto_cli, sandbox):
    """한 페이지는 지금 내용으로 다시 ingest되었고 다른 페이지는 옛 내용을 근거로 한다."""
    now = git_hash_of(sandbox, DESIGN_TEXT)
    pages = (sourced_page("component/auth", (DESIGN, now)), sourced_page("component/session", (DESIGN, OTHER_HASH)))
    root = onto_cli.root(billing(*pages, files={DESIGN: DESIGN_TEXT}))

    assert found(onto_cli, root) == [(WARNING, "billing", file("component/session"), "stale-page")]


def test_커밋하지_않은_수정도_작업_트리의_현재_내용으로_낡음을_가린다(onto_cli, sandbox):
    """git이 커밋한 파일의 해시(`git rev-parse HEAD:<경로>`)를 적은 페이지는 낡지 않다가, 커밋하지 않은 수정만으로 낡음이 된다."""
    recorded = git_hash_of(sandbox, DESIGN_TEXT)
    root = onto_cli.root(billing(sourced_page("component/auth", (DESIGN, recorded)), files={DESIGN: DESIGN_TEXT}))
    repository = root / "projects" / "billing"
    sandbox.git("init", "-q", cwd=repository)
    sandbox.git("add", DESIGN, cwd=repository)
    sandbox.git("commit", "-q", "-m", "원본 문서", cwd=repository)
    assert sandbox.git("rev-parse", f"HEAD:{DESIGN}", cwd=repository).stdout.strip() == recorded  # git이 커밋한 blob의 해시와 같다
    assert validate(onto_cli, root)[1] == []

    (repository / DESIGN).write_text(DESIGN_TEXT + "커밋하지 않은 수정\n", encoding="utf-8")

    assert found(onto_cli, root) == [(WARNING, "billing", file("component/auth"), "stale-page")]


def test_줄바꿈이_다른_파일도_git이_계산한_해시와_같게_해시한다(onto_cli, sandbox):
    """도구는 줄바꿈을 고치지 않고 파일 내용 그대로 해시한다(`git hash-object --no-filters`와 같다)."""
    crlf = "첫 줄\r\n둘째 줄\r\n"
    root = onto_cli.root(billing(sourced_page("component/auth", (DESIGN, git_hash_of(sandbox, crlf))), files={DESIGN: crlf}))

    assert (root / "projects" / "billing" / DESIGN).read_bytes() == crlf.encode("utf-8")
    assert validate(onto_cli, root)[1] == []


# --- 스크립트 검사: 없어진 원본 문서 ---------------------------------------------------


def test_derivedFrom이_가리키는_원본_문서가_없으면_오류로_잡는다(onto_cli):
    root = onto_cli.root(billing(sourced_page("component/auth", ("docs/gone.md", OTHER_HASH))))

    result, findings = validate(onto_cli, root)

    assert [f[:4] for f in findings] == [(ERROR, "billing", file("component/auth"), "missing-source")]
    assert "docs/gone.md" in findings[0][4]
    assert result.returncode == 1


def test_없어진_원본_문서는_낡음으로_따로_보고하지_않는다(onto_cli):
    root = onto_cli.root(billing(sourced_page("component/auth", ("docs/gone.md", OTHER_HASH))))

    assert "stale-page" not in [f[3] for f in validate(onto_cli, root)[1]]


def test_원본_문서가_디렉토리이거나_저장소_밖을_가리키는_링크이면_없는_것으로_본다(onto_cli, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("저장소 밖의 파일\n", encoding="utf-8")
    root = onto_cli.root(billing(sourced_page("component/auth", ("docs/folder", OTHER_HASH), ("docs/escape.md", OTHER_HASH)), files={"docs/folder/x.md": "x\n"}))
    (root / "projects" / "billing" / "docs" / "escape.md").symlink_to(outside)

    assert [f[3] for f in validate(onto_cli, root)[1]] == ["missing-source", "missing-source"]


def test_없어진_원본_문서를_가리키는_derivedFrom_검사는_지식_저장소가_규칙으로_끌_수_있다(onto_cli):
    rules = {"checks": {"missing-source": {"enabled": False}}}
    root = onto_cli.root(billing(sourced_page("component/auth", ("docs/gone.md", OTHER_HASH)), rules=rules))

    assert validate(onto_cli, root)[1] == []


# --- 스크립트 검사: 넘긴 문서의 목록 -----------------------------------------------------


def skipped_yaml(*entries: tuple[str, str]) -> dict[str, str]:
    lines = "".join(f"- path: {path}\n  hash: \"{hash_}\"\n" for path, hash_ in entries)
    return {SKIPPED_YAML: lines}


def test_넘긴_문서의_목록에_적힌_원본_문서가_없어졌으면_경고로_잡는다(onto_cli):
    root = onto_cli.root(billing(files=skipped_yaml(("docs/meeting.md", OTHER_HASH))))

    result, findings = validate(onto_cli, root)

    assert [f[:4] for f in findings] == [(WARNING, "billing", yaml_file(), "missing-skipped-source")]
    assert "docs/meeting.md" in findings[0][4]
    assert result.returncode == 0


def test_넘긴_문서의_목록에_적힌_원본_문서가_있으면_해시가_달라도_이_검사는_잡지_않는다(onto_cli):
    """내용이 바뀐 넘긴 문서는 `status`가 바뀐 문서로 다시 보여 준다. 검사가 잡는 것은 없어진 문서뿐이다."""
    files = {"docs/meeting.md": "회의록\n", **skipped_yaml(("docs/meeting.md", OTHER_HASH))}
    root = onto_cli.root(billing(files=files))

    assert validate(onto_cli, root)[1] == []


def test_넘긴_문서의_목록이_없으면_문제가_없다(onto_cli):
    assert validate(onto_cli, onto_cli.root(billing()))[1] == []


@pytest.mark.parametrize("text", ["", "# 주석뿐\n", "[]\n"], ids=["빈_파일", "주석뿐", "빈_목록"])
def test_넘긴_문서의_목록이_비어_있어도_문제가_없다(onto_cli, text):
    assert validate(onto_cli, onto_cli.root(billing(files={SKIPPED_YAML: text})))[1] == []


@pytest.mark.parametrize(
    ("text", "check"),
    [
        ("path: docs/a.md\nhash: x\n", "invalid-value"),
        ("- docs/a.md\n", "invalid-value"),
        (f"- path: docs/a.md\n  hash: \"{OTHER_HASH}\"\n  why: 메모\n", "invalid-value"),
        ("- path: docs/a.md\n", "invalid-value"),
        (f"- path: /abs.md\n  hash: \"{OTHER_HASH}\"\n", "invalid-value"),
        ("- path: [docs/a.md\n", "unreadable-file"),
    ],
    ids=["목록이_아님", "문자열_항목", "모르는_키", "해시_없음", "절대_경로", "YAML_문법_오류"],
)
def test_넘긴_문서의_목록의_모양이_틀리면_그_파일을_알리며_오류로_보고한다(onto_cli, text, check):
    root = onto_cli.root(billing(files={SKIPPED_YAML: text}))

    result, findings = validate(onto_cli, root)

    assert [f[:4] for f in findings] == [(ERROR, "billing", yaml_file(), check)]
    assert result.returncode == 1
    assert onto_cli.run(root, "build").returncode == 1  # 읽을 수 없는 파일이라 다른 파일과 같이 멈춘다


def test_넘긴_문서의_목록은_질의의_그래프에_나타나지_않는다(onto_cli):
    files = {"docs/meeting.md": "회의록\n", **skipped_yaml(("docs/meeting.md", OTHER_HASH))}
    root = onto_cli.root(billing(files=files))

    assert onto_cli.query(root, "SELECT ?s WHERE { ?s a onto:Source }") == []
