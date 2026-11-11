"""원본 문서의 기록: 페이지의 `derivedFrom`, 넘긴 문서의 목록(`skipped.yaml`), 그것이 그래프와 스크립트 검사에 나타나는 모습.

온톨로지 도구의 명령줄 진입점을 견본 페이지 디렉토리에 대고 실행한다(`onto_cli`).

- `derivedFrom`은 `{path, hash}` 항목(또는 그 목록)이다. `path`는 지식 저장소 루트 기준 원본 문서의 경로, `hash`는 그 문서의
  git 해시(git이 기록하는 blob 해시, 40자리 소문자 16진수)다. 해시의 기대값은 도구의 계산이 아니라 git이 낸 값을 쓴다.
- 그래프에서 항목 하나는 `Source` 엔티티(`onto:sourcePath`, `onto:sourceHash`)가 되고 페이지가 `onto:derivedFrom`으로 가리킨다.
  `Source`는 페이지를 갖지 않는다. 질의 결과에서는 원본 문서의 파일 경로로 보인다.
- 낡음(`stale-page`), 없어진 원본 문서(`missing-source`), 없어진 넘긴 문서(`missing-skipped-source`)는 스크립트 검사가 잡는다.
"""

import unicodedata

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
        [{"path": f"{ONTOLOGY_DIR}/component/target.md", "hash": OTHER_HASH}],
        [{"path": f"{ONTOLOGY_DIR}/index.md", "hash": OTHER_HASH}],
        [{"path": ONTOLOGY_DIR, "hash": OTHER_HASH}],
    ],
    ids=[
        "문자열", "숫자", "해시_없음", "경로_없음", "모르는_키", "짧은_해시", "대문자_해시", "숫자_해시", "빈_경로", "절대_경로", "상위_경로", "중간_상위_경로",
        "점_경로", "겹친_슬래시", "디렉토리_모양", "문자열_항목", "목록_항목", "온톨로지_층의_페이지", "온톨로지_층의_인덱스", "온톨로지_층_디렉토리",
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


def test_derivedFrom이_온톨로지_층_안의_파일을_가리키면_원본_문서가_아니라고_알린다(onto_cli):
    """온톨로지 층은 원본 문서와 분리된 층이고 ingest 대상에서 항상 빠진다. 층의 파일을 근거로 삼는 기록은 만들 수 없다."""
    target = page("component/target", "Component", title="대상", partOf="project")
    bad = sourced_page("component/auth", (f"{ONTOLOGY_DIR}/component/target.md", OTHER_HASH))
    root = onto_cli.root(billing(target, bad))

    result, findings = validate(onto_cli, root)

    assert [f[:4] for f in findings] == [(ERROR, "billing", file("component/auth"), "invalid-value")]
    assert "derivedFrom" in findings[0][4] and "온톨로지 층" in findings[0][4] and f"{ONTOLOGY_DIR}/component/target.md" in findings[0][4]
    assert result.returncode == 1


def test_온톨로지_층과_이름만_비슷한_디렉토리의_문서는_원본_문서로_쓸_수_있다(onto_cli):
    """`docs/ontology-notes/`는 `docs/ontology/` 안이 아니다."""
    root = onto_cli.root(
        billing(sourced_page("component/auth", ("docs/ontology-notes/a.md", OTHER_HASH)), files={"docs/ontology-notes/a.md": "메모\n"})
    )

    assert [f[3] for f in validate(onto_cli, root)[1]] == ["stale-page"]  # 해시가 달라 낡음이지만 값은 맞다


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


def test_git_저장소가_아닌_견본은_줄바꿈을_고치지_않고_파일_내용_그대로_해시한다(onto_cli, sandbox):
    """변환 설정이 없는 디렉토리에서는 `git hash-object`가 내는 값과 같다."""
    crlf = "첫 줄\r\n둘째 줄\r\n"
    root = onto_cli.root(billing(sourced_page("component/auth", (DESIGN, git_hash_of(sandbox, crlf))), files={DESIGN: crlf}))

    assert (root / "projects" / "billing" / DESIGN).read_bytes() == crlf.encode("utf-8")
    assert validate(onto_cli, root)[1] == []


# --- 스크립트 검사: 없어진 원본 문서 ---------------------------------------------------


def test_derivedFrom이_가리키는_원본_문서가_없으면_경고로_잡는다(onto_cli):
    """원본 문서는 팀이 소유한다. 팀원이 문서를 옮겼다고 푸시 관문이 막히지 않게 기본은 경고다."""
    root = onto_cli.root(billing(sourced_page("component/auth", ("docs/gone.md", OTHER_HASH))))

    result, findings = validate(onto_cli, root)

    assert [f[:4] for f in findings] == [(WARNING, "billing", file("component/auth"), "missing-source")]
    assert "docs/gone.md" in findings[0][4]
    assert result.returncode == 0


def test_없어진_원본_문서는_규칙으로_오류로_올릴_수_있고_그러면_종료_코드가_1이_된다(onto_cli):
    root = onto_cli.root(billing(sourced_page("component/auth", ("docs/gone.md", OTHER_HASH)), rules={"checks": {"missing-source": {"severity": "error"}}}))

    result, findings = validate(onto_cli, root)

    assert [f[:4] for f in findings] == [(ERROR, "billing", file("component/auth"), "missing-source")]
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
        (f"- path: {ONTOLOGY_DIR}/index.md\n  hash: \"{OTHER_HASH}\"\n", "invalid-value"),
        ("- path: [docs/a.md\n", "unreadable-file"),
    ],
    ids=["목록이_아님", "문자열_항목", "모르는_키", "해시_없음", "온톨로지_층의_파일", "YAML_문법_오류"],
)
def test_넘긴_문서의_목록의_모양이_틀리면_그_파일을_알리며_오류로_보고한다(onto_cli, text, check):
    root = onto_cli.root(billing(files={SKIPPED_YAML: text}))

    result, findings = validate(onto_cli, root)

    assert [f[:4] for f in findings] == [(ERROR, "billing", yaml_file(), check)]
    assert result.returncode == 1
    assert onto_cli.run(root, "build").returncode == 1  # 읽을 수 없는 파일이라 다른 파일과 같이 멈춘다


def test_넘긴_문서의_목록의_경로가_절대_경로이면_값의_종류_오류와_저장소_밖_링크_오류를_함께_보고한다(onto_cli):
    """값의 종류(`invalid-value`)는 저장소 규칙으로 끌 수 있고, 저장소 밖을 가리키는 경로(`outside-link`)는 루트 전용이다."""
    root = onto_cli.root(billing(files={SKIPPED_YAML: f"- path: /abs.md\n  hash: \"{OTHER_HASH}\"\n"}))

    result, findings = validate(onto_cli, root)

    assert sorted(f[:4] for f in findings) == [(ERROR, "billing", yaml_file(), "invalid-value"), (ERROR, "billing", yaml_file(), "outside-link")]
    assert result.returncode == 1
    assert onto_cli.run(root, "build").returncode == 1


def test_넘긴_문서의_목록은_질의의_그래프에_나타나지_않는다(onto_cli):
    files = {"docs/meeting.md": "회의록\n", **skipped_yaml(("docs/meeting.md", OTHER_HASH))}
    root = onto_cli.root(billing(files=files))

    assert onto_cli.query(root, "SELECT ?s WHERE { ?s a onto:Source }") == []


# --- 해시: git이 기록하는 정규 blob 해시 ---------------------------------------------------
# 지식 저장소가 git 작업 트리이면 해시는 git이 커밋할 때 기록하는 blob 해시다. 같은 커밋이면 줄바꿈 변환 설정(`core.autocrlf`,
# `.gitattributes`)이 달라 작업 트리의 바이트가 달라도 같다.

OTHER_DOC = "docs/other.md"
LF_TEXT = "첫 줄\n둘째 줄\n"


def git_origin(onto_cli, sandbox, *, attributes: str | None = None):
    """git 저장소로 커밋한 `billing` 지식 저장소. 원본 문서(`docs/design.md`)와 그것을 근거로 한 페이지, 근거로 삼지 않은 문서(`docs/other.md`)가 있다.

    페이지가 적은 해시는 줄바꿈 변환이 없는 곳에서 git이 낸 LF 내용의 blob 해시다. 저장소의 경로를 돌려준다.
    """
    files = {DESIGN: LF_TEXT, OTHER_DOC: LF_TEXT + "다른 문서\n", **({".gitattributes": attributes} if attributes else {})}
    root = onto_cli.root(billing(sourced_page("component/auth", (DESIGN, git_hash_of(sandbox, LF_TEXT))), files=files))
    origin = root / "projects" / "billing"
    sandbox.git("init", "-q", cwd=origin)
    sandbox.git("add", "-A", cwd=origin)
    sandbox.git("commit", "-q", "-m", "초기", cwd=origin)
    return origin


def clone_root(onto_cli, sandbox, origin, *config: str):
    """`origin`을 `projects/billing`으로 클론한 견본 루트. `config`는 `git clone -c`로 주는 설정이다."""
    root = onto_cli.root({})
    (root / "projects").mkdir()
    arguments = [argument for setting in config for argument in ("-c", setting)]
    sandbox.git("clone", "-q", *arguments, origin, root / "projects" / "billing", cwd=root)
    return root


def status_hashes(onto_cli, root, env=None) -> dict[str, str]:
    """`status`가 보여 주는 문서 경로 -> 현재 해시."""
    result = onto_cli.run(root, "status", env=env)
    assert result.returncode == 0, result.stderr
    return {fields[2]: fields[3] for fields in (line.split("\t") for line in result.stdout.splitlines() if "\t" in line)}


LINE_ENDING_SETUPS = [
    (None, ("core.autocrlf=true",)),
    ("*.md text eol=crlf\n", ()),
    ("*.md text eol=crlf\n", ("core.autocrlf=true",)),
]


@pytest.mark.parametrize(
    ("attributes", "config"), LINE_ENDING_SETUPS, ids=["autocrlf", "gitattributes_eol", "둘_다"]
)
def test_해시는_깨끗한_클론의_git_rev_parse와_같고_줄바꿈_변환_설정과_무관하다(onto_cli, sandbox, attributes, config):
    origin = git_origin(onto_cli, sandbox, attributes=attributes)
    committed = {path: sandbox.git("rev-parse", f"HEAD:{path}", cwd=origin).stdout.strip() for path in (DESIGN, OTHER_DOC)}
    default = clone_root(onto_cli, sandbox, origin)
    converted = clone_root(onto_cli, sandbox, origin, *config)
    assert b"\r\n" in (converted / "projects" / "billing" / OTHER_DOC).read_bytes()  # 작업 트리의 바이트가 정말 다르다

    for root in (default, converted):
        assert status_hashes(onto_cli, root) == {OTHER_DOC: committed[OTHER_DOC]}  # 근거로 삼은 문서는 낡지 않아 나오지 않는다
        assert "stale-page" not in validate(onto_cli, root)[0].stdout  # 한 기기에서 ingest한 페이지가 다른 기기에서 낡지 않는다
    assert committed[DESIGN] == git_hash_of(sandbox, LF_TEXT)


def test_줄바꿈_변환이_있는_작업_트리에서도_커밋하지_않은_수정은_낡음으로_본다(onto_cli, sandbox):
    origin = git_origin(onto_cli, sandbox)
    root = clone_root(onto_cli, sandbox, origin, "core.autocrlf=true")
    assert "stale-page" not in validate(onto_cli, root)[0].stdout

    (root / "projects" / "billing" / DESIGN).write_bytes("첫 줄\r\n바뀐 둘째 줄\r\n".encode("utf-8"))

    assert [f[3] for f in validate(onto_cli, root)[1]] == ["stale-page"]


def test_git_저장소의_위치를_바꾸는_환경_변수가_있어도_그_지식_저장소의_해시를_낸다(onto_cli, sandbox):
    """git 훅(`pre-push` 등)이 `GIT_DIR`을 물려줘도 다른 저장소를 해시하지 않는다."""
    origin = git_origin(onto_cli, sandbox, attributes="*.md text eol=crlf\n")
    root = clone_root(onto_cli, sandbox, origin)
    elsewhere = sandbox.new_dir("elsewhere", "repo")
    sandbox.git("init", "-q", cwd=elsewhere)

    plain = status_hashes(onto_cli, root)
    disturbed = status_hashes(onto_cli, root, env={**onto_cli.env, "GIT_DIR": str(elsewhere / ".git"), "GIT_WORK_TREE": str(elsewhere)})

    assert disturbed == plain == {OTHER_DOC: sandbox.git("rev-parse", f"HEAD:{OTHER_DOC}", cwd=origin).stdout.strip()}


def test_git_저장소의_status와_validate는_git_객체와_인덱스를_포함해_아무것도_고치지_않는다(onto_cli, sandbox):
    origin = git_origin(onto_cli, sandbox)
    root = clone_root(onto_cli, sandbox, origin, "core.autocrlf=true")
    (root / "projects" / "billing" / DESIGN).write_text("커밋하지 않은 수정\n", encoding="utf-8")
    before = {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}

    assert onto_cli.run(root, "status").returncode == 0
    assert onto_cli.run(root, "validate").returncode == 0

    assert {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()} == before


def test_git이_해시를_내지_못하면_파일_내용_그대로_계산하고_표준_오류로_알린다(onto_cli, sandbox):
    root = onto_cli.root(billing(sourced_page("component/auth", (DESIGN, git_hash_of(sandbox, LF_TEXT))), files={DESIGN: LF_TEXT, OTHER_DOC: "다른 문서\n"}))
    (root / "projects" / "billing" / ".git").write_text("gitdir: /nonexistent\n", encoding="utf-8")  # git 저장소처럼 보이지만 쓸 수 없다

    validated = onto_cli.run(root, "validate")
    status = onto_cli.run(root, "status")

    assert (validated.returncode, validated.stdout) == (0, "")
    assert "git으로 내지 못해" in validated.stderr
    assert status.returncode == 0 and f"\tbilling\t{OTHER_DOC}\t{git_hash_of(sandbox, '다른 문서' + chr(10))}" in status.stdout
    assert status.stderr.count("git으로 내지 못해") == 1


# 한계: 저장소의 blob에 이미 CRLF가 든 문서. git은 줄바꿈 자동 변환에서 인덱스에 이미 CRLF로 든 파일을 변환하지 않는다(`git add`와
# `git status`가 인덱스를 읽어 그렇게 한다). `git hash-object`는 인덱스를 읽지 않아 CRLF를 LF로 바꿔 해시한다. 그래서 이런 문서의 해시는
# `git rev-parse HEAD:<경로>`와 다를 수 있다. 문서(`onto/onto_tool/sources.py`, `status` 도움말, `tests/README.md`)가 이 한계를 적는다.

CRLF_TEXT = "첫 줄\r\n둘째 줄\r\n"
CRLF_AS_LF = "첫 줄\n둘째 줄\n"


def crlf_origin(onto_cli, sandbox, *, later_attributes: str | None = None):
    """CRLF 줄바꿈 그대로 커밋한 원본 문서(`docs/other.md`)가 있는 git 저장소. 변환 설정이 없는 곳에서 커밋해 저장소의 blob에 CRLF가 든다.

    `later_attributes`를 주면 그 `.gitattributes`를 두 번째 커밋으로 더한다(문서는 그대로다).
    """
    root = onto_cli.root(billing(files={OTHER_DOC: CRLF_TEXT}))
    origin = root / "projects" / "billing"
    sandbox.git("init", "-q", cwd=origin)
    sandbox.git("add", "-A", cwd=origin)
    sandbox.git("commit", "-q", "-m", "초기", cwd=origin)
    assert int(sandbox.git("cat-file", "-s", f"HEAD:{OTHER_DOC}", cwd=origin).stdout) == len(CRLF_TEXT.encode("utf-8"))  # 저장소의 blob에 정말 CRLF가 든다
    if later_attributes is not None:
        (origin / ".gitattributes").write_text(later_attributes, encoding="utf-8")
        sandbox.git("add", ".gitattributes", cwd=origin)
        sandbox.git("commit", "-q", "-m", "속성", cwd=origin)
    return origin


def test_저장소의_blob에_CRLF가_든_문서의_해시는_core_autocrlf가_다른_기기에서_서로_다를_수_있다(onto_cli, sandbox):
    origin = crlf_origin(onto_cli, sandbox)
    committed = sandbox.git("rev-parse", f"HEAD:{OTHER_DOC}", cwd=origin).stdout.strip()
    as_lf = git_hash_of(sandbox, CRLF_AS_LF)
    default = clone_root(onto_cli, sandbox, origin)
    converting = clone_root(onto_cli, sandbox, origin, "core.autocrlf=true")

    assert committed != as_lf
    assert status_hashes(onto_cli, default) == {OTHER_DOC: committed}  # 변환 설정이 없으면 git rev-parse와 같다
    assert status_hashes(onto_cli, converting) == {OTHER_DOC: as_lf}  # core.autocrlf=true는 CRLF를 LF로 바꿔 해시한다
    for root in (default, converting):
        assert sandbox.git("status", "--porcelain", cwd=root / "projects" / "billing").stdout == ""  # 두 기기 모두 git status는 깨끗하다


def test_CRLF로_커밋한_문서에_text_auto를_나중에_더하면_모든_기기에서_git_rev_parse와_다른_해시가_나온다(onto_cli, sandbox):
    origin = crlf_origin(onto_cli, sandbox, later_attributes="* text=auto\n")
    committed = sandbox.git("rev-parse", f"HEAD:{OTHER_DOC}", cwd=origin).stdout.strip()
    as_lf = git_hash_of(sandbox, CRLF_AS_LF)
    default = clone_root(onto_cli, sandbox, origin)
    converting = clone_root(onto_cli, sandbox, origin, "core.autocrlf=true")

    assert committed != as_lf
    assert status_hashes(onto_cli, default) == status_hashes(onto_cli, converting) == {OTHER_DOC: as_lf}


# --- 경로: 대소문자와 유니코드 정규화, 심볼릭 링크 -----------------------------------------------


def test_원본_문서_경로의_대소문자가_파일_이름과_다르면_어느_파일_시스템에서도_없는_문서로_본다(onto_cli, sandbox):
    """macOS처럼 대소문자를 구분하지 않는 파일 시스템에서도 Linux와 같은 결과(`missing-source`)가 나온다."""
    root = onto_cli.root(billing(sourced_page("component/auth", ("docs/Design.md", git_hash_of(sandbox, DESIGN_TEXT))), files={DESIGN: DESIGN_TEXT}))

    assert found(onto_cli, root) == [(WARNING, "billing", file("component/auth"), "missing-source")]


def test_경로의_중간_디렉토리_이름도_대소문자를_구분한다(onto_cli, sandbox):
    root = onto_cli.root(billing(sourced_page("component/auth", ("Docs/design.md", git_hash_of(sandbox, DESIGN_TEXT))), files={DESIGN: DESIGN_TEXT}))

    assert [f[3] for f in validate(onto_cli, root)[1]] == ["missing-source"]


@pytest.mark.parametrize(("on_disk", "written"), [("NFD", "NFC"), ("NFC", "NFD")], ids=["파일이_NFD", "파일이_NFC"])
def test_유니코드_정규화_형식이_달라도_같은_이름의_원본_문서로_본다(onto_cli, sandbox, on_disk, written):
    """macOS 앱이 만든 NFD 파일 이름과 LLM이 적은 NFC 경로를 같은 문서로 본다. 파일은 디렉토리에 있는 이름 그대로 연다."""
    name = "docs/설계 문서.md"
    root = onto_cli.root(
        billing(
            sourced_page("component/auth", (unicodedata.normalize(written, name), git_hash_of(sandbox, DESIGN_TEXT))),
            files={unicodedata.normalize(on_disk, name): DESIGN_TEXT},
        )
    )

    assert validate(onto_cli, root)[1] == []


def test_심볼릭_링크인_원본_문서는_없는_문서로_본다(onto_cli, sandbox):
    """git은 링크를 내용이 아니라 대상 경로의 blob으로 기록한다. 경로 중간의 디렉토리 링크도 같다."""
    hash_ = git_hash_of(sandbox, DESIGN_TEXT)
    root = onto_cli.root(billing(sourced_page("component/auth", ("docs/latest.md", hash_), ("docs/linked/design.md", hash_)), files={DESIGN: DESIGN_TEXT}))
    (root / "projects" / "billing" / "docs" / "latest.md").symlink_to("design.md")
    (root / "projects" / "billing" / "docs" / "linked").symlink_to(".", target_is_directory=True)

    assert [f[3] for f in validate(onto_cli, root)[1]] == ["missing-source", "missing-source"]
