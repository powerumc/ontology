"""본문 링크의 대상: 페이지 본문의 링크가 가리키는 대상이 있는지 스크립트 검사(`validate`)가 `broken-reference`로 잡는다.

온톨로지 도구의 명령줄 진입점을 견본 페이지 디렉토리에 대고 실행한다(`onto_cli`).

- 교차 참조(`[글](<저장소 이름>:<식별자>)`)가 가리키는 엔티티가 없으면 깨진 참조다. 관계의 값과 같은 규칙이라, 등록되지 않은 저장소를 가리키면
  `unregistered-repository`, 온톨로지 층이 없는 저장소를 가리키면 깨진 참조다. 읽을 수 없는 저장소를 가리키는 것은 건너뛴다.
- 저장소 안의 상대 링크(`[글](../term/x.md)`)가 가리키는 파일이나 디렉토리가 없으면 깨진 참조다. 저장소 밖을 가리키는 링크(`outside-link`)와 파일이 아닌
  주소(`https`, `mailto`), 문서 안의 조각(`#제목`)은 따지지 않는다. 코드 안의 링크도 링크가 아니다.
- 지식 저장소 안에서 돌리면 다른 저장소를 가리키는 교차 참조는 건너뛰고(그 저장소를 알 수 없다), 상대 링크는 검사한다.
"""

import unicodedata

import pytest

from support.onto_cli import ONTOLOGY_DIR, REPOSITORY, page, repo

ERROR = "오류"
WARNING = "경고"


def file(identifier: str, name: str = "billing") -> str:
    return f"projects/{name}/{ONTOLOGY_DIR}/{identifier}.md"


def validate(onto_cli, root, **options):
    """`validate`를 실행해 `(결과, 문제 목록)`을 돌려준다. 문제는 `(심각도, 지식 저장소, 파일, 검사 항목, 설명)`이다."""
    result = onto_cli.run(root, "validate", **options)
    findings = [tuple(line.split("\t")) for line in result.stdout.splitlines()]
    assert all(len(finding) == 5 for finding in findings), result.stdout
    return result, findings


def of_check(findings, *checks: str) -> list[tuple[str, str, str, str]]:
    return [finding[:4] for finding in findings if finding[3] in checks]


def billing_files(body: str, *, deep: str = "", extra: dict[str, str] | None = None) -> dict[str, str]:
    """`billing`: 본문이 `body`인 페이지 `component/gateway`와, 링크 대상이 될 파일들. 모든 페이지가 관계를 가진다."""
    pages = [
        page("component/gateway", "Component", title="결제 게이트웨이", partOf="project", body=body),
        page("component/api", "Component", title="결제 API", partOf="project"),
        page("term/invoice", "Term", title="청구서", about="project"),
    ]
    if deep:
        pages.append(page("component/deep/er/inner", "Component", title="깊은 컴포넌트", partOf="project", body=deep))
    files = repo("billing", *pages)
    files["docs/design.md"] = "# 설계\n"
    files["docs/my notes.md"] = "# 메모\n"
    files["docs/설계/결정 기록.md"] = "# 결정 기록\n"
    files.update(extra or {})
    return files


def shop_files() -> dict[str, str]:
    return repo("shop", page("component/api", "Component", title="상점 API", partOf="project"))


def samples(body: str, **options) -> dict[str, dict[str, str]]:
    return {"billing": billing_files(body, **options), "shop": shop_files()}


GATEWAY = file("component/gateway")

# 같은 대상을 가리키는 링크의 여러 모양. `shop:component/api`를 대상으로 쓴다.
def forms(target: str) -> dict[str, str]:
    return {
        "인라인_링크": f"[결제]({target})",
        "이미지": f"![그림]({target})",
        "참조_정의": f"[설명][r]\n\n[r]: {target}\n",
        "html_href": f'<a href="{target}">x</a>',
        "따옴표_없는_html_href": f"<a href={target}>x</a>",
        "자동_링크": f"<{target}>",
        "공백이_든_링크": f"[x]( {target} )",
    }


# --- 교차 참조 ----------------------------------------------------------------------


@pytest.mark.parametrize("body", forms("shop:component/api").values(), ids=forms("shop:component/api").keys())
def test_본문의_교차_참조가_가리키는_엔티티가_있으면_통과한다(onto_cli, body):
    result, findings = validate(onto_cli, onto_cli.root(samples(body)))

    assert findings == []
    assert result.returncode == 0


@pytest.mark.parametrize("target", ["shop:project", "shop:component/api#section", "shop:component/api?plain=1", "billing:component/api"])
def test_Project와_조각이나_질의가_붙은_링크와_자기_저장소의_이름으로_쓴_교차_참조도_있는_엔티티로_본다(onto_cli, target):
    result, findings = validate(onto_cli, onto_cli.root(samples(f"[x]({target})\n")))

    assert findings == []


@pytest.mark.parametrize("body", forms("shop:component/missing").values(), ids=forms("shop:component/missing").keys())
def test_본문의_교차_참조가_가리키는_엔티티가_없으면_깨진_참조로_잡는다(onto_cli, body):
    result, findings = validate(onto_cli, onto_cli.root(samples(body)))

    assert of_check(findings, "broken-reference") == [(ERROR, "billing", GATEWAY, "broken-reference")]
    assert "shop:component/missing" in findings[0][4]  # 설명이 어느 링크인지 알려 준다
    assert [finding[3] for finding in findings] == ["broken-reference"]
    assert result.returncode == 1


def test_본문의_교차_참조가_등록되지_않은_저장소를_가리키면_등록되지_않은_저장소로_잡는다(onto_cli):
    result, findings = validate(onto_cli, onto_cli.root(samples("[없는 저장소](nowhere:term/x)\n")))

    assert [finding[:4] for finding in findings] == [(ERROR, "billing", GATEWAY, "unregistered-repository")]
    assert "nowhere" in findings[0][4]
    assert result.returncode == 1


def test_본문의_교차_참조가_온톨로지_층이_없는_저장소를_가리키면_깨진_참조로_잡는다(onto_cli):
    repos = {**samples("[문서만 있다](bare:term/x)\n"), "bare": {"README.md": "# 문서만 있다\n"}}

    findings = validate(onto_cli, onto_cli.root(repos))[1]

    assert of_check(findings, "broken-reference") == [(ERROR, "billing", GATEWAY, "broken-reference")]
    assert "bare" in next(f[4] for f in findings if f[3] == "broken-reference")


def test_본문의_교차_참조가_읽을_수_없는_저장소를_가리키면_그_저장소의_문제만_보고한다(onto_cli):
    repos = {**samples("[읽을 수 없다](broken:term/x)\n"), "broken": {f"{ONTOLOGY_DIR}/ontology.yaml": "title: 이름이 없다\n"}}

    findings = validate(onto_cli, onto_cli.root(repos))[1]

    assert of_check(findings, "broken-reference", "unregistered-repository") == []
    assert of_check(findings, "unreadable-file") != []


def test_스킴이_있는_일반_주소는_교차_참조가_아니라서_저장소_이름을_따지지_않는다(onto_cli):
    body = "[메일](mailto:me@example.com) [웹](https://example.com/a) [전화](tel:+821012345678) [내려받기](ftp://example.com/a) [로컬](http://localhost:8080/x)\n"

    result, findings = validate(onto_cli, onto_cli.root(samples(body)))

    assert findings == []


def test_코드_안의_링크는_링크가_아니라서_대상을_따지지_않는다(onto_cli):
    body = "`[x](shop:component/missing)` `[y](../term/none.md)`\n\n```\n[z](nowhere:term/x)\n[w](none.md)\n```\n\n<!-- [v](../term/none.md) -->\n"

    assert validate(onto_cli, onto_cli.root(samples(body)))[1] == []


def test_같은_대상을_여러_번_가리켜도_한_번만_보고하고_다른_대상은_따로_보고한다(onto_cli):
    body = "[a](shop:component/missing) [b](shop:component/missing)\n\n[c](shop:component/also-missing)\n"

    findings = validate(onto_cli, onto_cli.root(samples(body)))[1]

    assert [finding[3] for finding in findings] == ["broken-reference"] * 2


def test_본문_링크의_교차_참조는_공유_범위_검사도_그대로_받는다(onto_cli):
    """없는 엔티티를 가리켜도 더 좁은 저장소의 이름이 드러나므로 공유 범위 위반이다. 깨진 참조와 함께 보고한다."""
    repos = {
        "team": repo("team", page("component/a", "Component", title="A", partOf="project", body="[비밀](secret:component/nothing)\n"), scope="team"),
        "secret": repo("secret", page("component/x", "Component", title="X", partOf="project"), scope="private"),
    }

    findings = validate(onto_cli, onto_cli.root(repos))[1]

    assert sorted(finding[3] for finding in findings) == ["broken-reference", "scope-violation"]


# --- 저장소 안의 상대 링크 ------------------------------------------------------------

EXISTING_RELATIVE_LINKS = {
    "같은_디렉토리의_페이지": "[x](api.md)",
    "다른_클래스_디렉토리의_페이지": "[x](../term/invoice.md)",
    "점_조각": "[x](./api.md)",
    "원본_문서": "[x](../../design.md)",
    "공백이_든_파일의_퍼센트_인코딩": "[x](../../my%20notes.md)",
    "한글_경로의_퍼센트_인코딩": "[x](../../%EC%84%A4%EA%B3%84/%EA%B2%B0%EC%A0%95%20%EA%B8%B0%EB%A1%9D.md)",
    "인코딩하지_않은_한글_경로": "[x](<../../설계/결정 기록.md>)",
    "꺾쇠_안의_공백": "[x](<../../my notes.md>)",
    "저장소_루트": "[x](../../../)",
    "디렉토리": "[x](../term/)",
    "층의_디렉토리": "[x](../)",
    "문서_안의_조각": "[x](api.md#heading)",
    "질의": "[x](api.md?plain=1)",
    "역슬래시": "[x](..\\term\\invoice.md)",
    "안으로_갔다_안으로": "[x](../component/../term/invoice.md)",
    "인덱스": "[x](../index.md)",
    "조각만": "[x](#heading)",
    "빈_링크": "[x]()",
    "참조_정의": "[x][r]\n\n[r]: ../term/invoice.md\n",
    "html_href": '<a href="../term/invoice.md">x</a>',
    "html_src": "<img src=../../design.md>",
}


@pytest.mark.parametrize("body", EXISTING_RELATIVE_LINKS.values(), ids=EXISTING_RELATIVE_LINKS.keys())
def test_저장소_안의_상대_링크가_가리키는_파일이나_디렉토리가_있으면_통과한다(onto_cli, body):
    result, findings = validate(onto_cli, onto_cli.root(samples(body)))

    assert findings == []
    assert result.returncode == 0


# 링크의 모양별 본문과, 설명이 보여 줄 링크의 대상
MISSING_RELATIVE_LINKS = {
    "같은_디렉토리": ("[x](none.md)", "none.md"),
    "다른_클래스_디렉토리": ("[없는 것](../term/none.md)", "../term/none.md"),
    "원본_문서": ("[x](../../none.md)", "../../none.md"),
    "이미지": ("![그림](../../assets/none.png)", "../../assets/none.png"),
    "참조_정의": ("[x][r]\n\n[r]: ../term/none.md\n", "../term/none.md"),
    "html_href": ('<a href="../term/none.md">x</a>', "../term/none.md"),
    "html_src": ("<img src=../../assets/none.png>", "../../assets/none.png"),
    "조각이_붙은_링크": ("[x](none.md#heading)", "none.md#heading"),
    "역슬래시": ("[x](..\\term\\none.md)", "..\\term\\none.md"),
    "퍼센트_인코딩": ("[x](../term/no%20ne.md)", "../term/no%20ne.md"),
    "점_조각": ("[x](./none.md)", "./none.md"),
    "안으로_갔다_안으로": ("[x](../component/../term/none.md)", "../component/../term/none.md"),
    "제목이_붙은_링크": ('[x](none.md "제목")', "none.md"),
}


@pytest.mark.parametrize(("body", "destination"), MISSING_RELATIVE_LINKS.values(), ids=MISSING_RELATIVE_LINKS.keys())
def test_저장소_안의_상대_링크가_가리키는_파일이_없으면_깨진_참조로_잡는다(onto_cli, body, destination):
    result, findings = validate(onto_cli, onto_cli.root(samples(body)))

    assert [finding[:4] for finding in findings] == [(ERROR, "billing", GATEWAY, "broken-reference")]
    assert destination in findings[0][4]  # 설명이 어느 링크인지 알려 준다
    assert result.returncode == 1


# 참조 정의(`[이름]: 대상`)는 대상 뒤가 비었거나 제목(`"…"`, `'…'`, `(…)`)뿐일 때만 정의다. 각주 정의(`[^1]: …`)와 `[주의]: 이 값은 …` 같은 문장은
# 링크가 아니다(CommonMark). 첫 낱말을 링크 대상으로 읽으면 렌더링되는 각주 하나에 오류가 나 푸시 관문이 막힌다.
NOT_DEFINITIONS = {
    "각주_정의": "결제 흐름은 원본 설계를 따른다[^1].\n\n[^1]: 설계 문서 3장\n",
    "이름이_붙은_각주_정의": "원본을 따른다[^note].\n\n[^note]: 원본 문서를 보면 된다\n",
    "각주가_경로로_시작한다": "원본[^2].\n\n[^2]: ../../none.md 의 3장\n",
    "대괄호_뒤_콜론_문장": "[주의]: 이 값은 바뀔 수 있다\n",
    "경로로_시작하는_문장": "[참고]: ../term/none.md 에 있다\n",
    "절대_경로로_시작하는_문장": "[참고]: /etc/hosts 를 본다\n",
    "교차_참조_모양으로_시작하는_문장": "[메모]: nowhere:term/x 는 아직 없다\n",
    "제목_뒤에_글이_더_있다": '[메모]: none.md "제목" 그리고 더\n',
}


@pytest.mark.parametrize("body", NOT_DEFINITIONS.values(), ids=NOT_DEFINITIONS.keys())
def test_각주_정의와_대괄호_뒤_콜론으로_시작하는_문장은_링크가_아니라서_대상을_따지지_않는다(onto_cli, body):
    result, findings = validate(onto_cli, onto_cli.root(samples(body)))

    assert findings == []
    assert result.returncode == 0


DEFINITIONS_WITH_TITLE = {
    "큰따옴표_제목": '[r]: ../term/none.md "제목"\n',
    "작은따옴표_제목": "[r]: ../term/none.md '제목'\n",
    "괄호_제목": "[r]: ../term/none.md (제목)\n",
    "꺾쇠와_제목": '[r]: <../term/none.md> "제목"\n',
    "뒤에_공백": "[r]: ../term/none.md   \n",
    "들여쓴_정의": "   [r]: ../term/none.md\n",
    "교차_참조": '[r]: shop:component/missing "제목"\n',
}


@pytest.mark.parametrize("body", DEFINITIONS_WITH_TITLE.values(), ids=DEFINITIONS_WITH_TITLE.keys())
def test_대상_뒤가_비었거나_제목뿐인_참조_정의는_링크로_보고_대상이_없으면_깨진_참조로_잡는다(onto_cli, body):
    findings = validate(onto_cli, onto_cli.root(samples(f"[x][r]\n\n{body}")))[1]

    assert [finding[:4] for finding in findings] == [(ERROR, "billing", GATEWAY, "broken-reference")]
    assert "none.md" in findings[0][4] or "shop:component/missing" in findings[0][4]


# 링크의 대상은 Markdown이 읽는 대로 읽는다: 문장 부호 앞의 백슬래시는 이스케이프이고(`my\\_file.md`는 `my_file.md`), HTML 엔티티(`&amp;`, `&#38;`)는
# 그 글자다. 그대로 경로로 읽으면 있는 파일을 없다고 알린다. 다만 `\\`를 `/`로 읽는 것(`..\\term\\a.md`)은 그대로다.
ESCAPED_LINKS = {
    "이스케이프된_밑줄": ("[x](../../my\\_file.md)", "docs/my_file.md"),
    "이스케이프된_괄호": ("[x](../../paren\\(1\\).md)", "docs/paren(1).md"),
    "이스케이프된_대괄호와_샵": ("[x](../../a\\[1\\]\\#.md)", "docs/a[1]#.md"),
    "html_href의_앰퍼샌드_엔티티": ('<a href="../../a&amp;b.md">x</a>', "docs/a&b.md"),
    "십진_엔티티": ("[x](../../a&#38;b.md)", "docs/a&b.md"),
    "십육진_엔티티": ("[x](../../a&#x26;b.md)", "docs/a&b.md"),
}


@pytest.mark.parametrize(("body", "name"), ESCAPED_LINKS.values(), ids=ESCAPED_LINKS.keys())
def test_백슬래시_이스케이프와_html_엔티티를_푼_경로의_파일이_있으면_통과한다(onto_cli, body, name):
    result, findings = validate(onto_cli, onto_cli.root(samples(body, extra={name: "# 대상\n"})))

    assert findings == []
    assert result.returncode == 0


def test_이스케이프와_엔티티를_푼_경로의_파일이_없으면_푼_경로를_알리며_깨진_참조로_잡는다(onto_cli):
    findings = validate(onto_cli, onto_cli.root(samples("[x](../../none\\_file.md) [y](../../none&amp;file.md)\n")))[1]

    assert [finding[:4] for finding in findings] == [(ERROR, "billing", GATEWAY, "broken-reference")] * 2
    assert sorted("`docs/none_file.md`" in finding[4] or "`docs/none&file.md`" in finding[4] for finding in findings) == [True, True]


def test_문장_부호가_아닌_글자_앞의_백슬래시는_경로_구분자로_읽는다(onto_cli):
    result, findings = validate(onto_cli, onto_cli.root(samples("[있다](..\\term\\invoice.md) [없다](..\\term\\none.md)\n")))

    assert [finding[:4] for finding in findings] == [(ERROR, "billing", GATEWAY, "broken-reference")]
    assert "none.md" in findings[0][4]


# 경로의 대소문자는 실제 파일과 같아야 한다. 대소문자를 구분하지 않는 파일 시스템(macOS)에서도 같다. 같은 커밋이 기기에 따라 통과하거나 막히지 않게
# 원본 문서의 경로(`derivedFrom`)와 같은 방식으로 디렉토리의 실제 이름과 맞춘다. 유니코드는 NFC로 정규화해 비교한다.
CASE_MISMATCH = {
    "디렉토리_이름": "[x](../Term/invoice.md)",
    "파일_이름": "[x](../term/Invoice.md)",
    "원본_문서": "[x](../../Design.md)",
    "디렉토리를_가리키는_링크": "[x](../Term/)",
    "퍼센트_인코딩한_경로": "[x](../../My%20Notes.md)",
}


@pytest.mark.parametrize("body", CASE_MISMATCH.values(), ids=CASE_MISMATCH.keys())
def test_경로의_대소문자가_실제_파일과_다르면_모든_플랫폼에서_깨진_참조로_잡는다(onto_cli, body):
    findings = validate(onto_cli, onto_cli.root(samples(body)))[1]

    assert [finding[:4] for finding in findings] == [(ERROR, "billing", GATEWAY, "broken-reference")]


def test_파일_시스템에_NFD로_저장된_이름도_NFC로_쓴_링크가_가리키는_것으로_본다(onto_cli):
    """macOS는 파일 이름을 NFD로 저장한다. 같은 문서를 가리키는 링크가 어느 기기에서 만든 것이든 같은 결과여야 한다."""
    nfd = unicodedata.normalize("NFD", "docs/자료/기록.md")
    assert nfd != "docs/자료/기록.md"
    body = "[x](<../../자료/기록.md>) [y](../../%EC%9E%90%EB%A3%8C/%EA%B8%B0%EB%A1%9D.md)\n"

    result, findings = validate(onto_cli, onto_cli.root(samples(body, extra={nfd: "# 기록\n"})))

    assert findings == []


def test_저장소_밖을_가리키는_링크는_깨진_참조가_아니라_저장소_밖_링크로만_보고한다(onto_cli):
    body = "[a](../../../../shop/docs/design.md) [b](/Users/me/none.md) [c](file:///Users/me/none.md) [d](C:/Users/me/none.md)\n"

    findings = validate(onto_cli, onto_cli.root(samples(body)))[1]

    assert sorted(finding[3] for finding in findings) == ["outside-link"] * 4


def test_페이지가_깊은_디렉토리에_있으면_그_위치에서_상대_경로를_푼다(onto_cli):
    deep = "[있다](../../../../design.md) [없다](../../../design.md) [형제](inner.md) [없는_형제](other.md)\n"

    findings = validate(onto_cli, onto_cli.root(samples("본문\n", deep=deep)))[1]

    inner = file("component/deep/er/inner")
    assert [finding[:4] for finding in findings] == [(ERROR, "billing", inner, "broken-reference")] * 2
    assert sorted("../../../design.md" in finding[4] for finding in findings) == [False, True]


def test_링크_대상이_저장소_안을_가리키는_깨진_심볼릭_링크이면_없는_것으로_본다(onto_cli):
    root = onto_cli.root(samples("[x](../term/dangling.md)\n"))
    (root / "projects/billing" / ONTOLOGY_DIR / "term/dangling.md").symlink_to("none.md")

    findings = validate(onto_cli, root)[1]

    assert [finding[:4] for finding in findings if finding[3] == "broken-reference"] == [(ERROR, "billing", GATEWAY, "broken-reference")]


def test_다른_지식_저장소의_같은_이름의_파일은_이_저장소의_대상으로_세지_않는다(onto_cli):
    """상대 링크는 페이지가 있는 저장소 안에서만 푼다. 다른 저장소에 같은 경로가 있어도 깨진 참조다."""
    repos = samples("[x](../../only-in-shop.md)\n")
    repos["shop"]["docs/only-in-shop.md"] = "# 상점 문서\n"

    findings = validate(onto_cli, onto_cli.root(repos))[1]

    assert [finding[:4] for finding in findings] == [(ERROR, "billing", GATEWAY, "broken-reference")]


def test_생성된_인덱스는_페이지가_아니라서_링크_대상을_따지지_않는다(onto_cli):
    root = onto_cli.root(samples("본문\n"))
    index = root / "projects/billing" / ONTOLOGY_DIR / "index.md"
    original = index.read_text(encoding="utf-8")
    assert original

    index.write_text(original + "\n[x](component/none.md) [y](shop:component/none)\n", encoding="utf-8")

    assert [finding[3] for finding in validate(onto_cli, root)[1]] == ["index-mismatch"]


# --- 규칙 ------------------------------------------------------------------------------


def test_저장소가_broken_reference를_끄면_본문_링크의_깨진_참조도_보고하지_않는다(onto_cli):
    muted = repo(
        "billing",
        page("component/gateway", "Component", title="결제 게이트웨이", partOf="project", body="[a](shop:component/missing) [b](none.md)\n"),
        rules={"checks": {"broken-reference": {"enabled": False}}},
    )
    repos = {"billing": muted, "shop": shop_files()}

    result, findings = validate(onto_cli, onto_cli.root(repos))

    assert findings == []
    assert result.returncode == 0


def test_루트_규칙이_broken_reference를_경고로_낮추면_본문_링크의_깨진_참조도_경고이고_종료_코드는_0이다(onto_cli):
    onto_cli.set_root_check("broken-reference", severity="warning")

    result, findings = validate(onto_cli, onto_cli.root(samples("[a](shop:component/missing) [b](none.md)\n")))

    assert [finding[:4] for finding in findings] == [(WARNING, "billing", GATEWAY, "broken-reference")] * 2
    assert result.returncode == 0


# --- 지식 저장소 안에서 -----------------------------------------------------------------


def test_지식_저장소_안에서는_다른_저장소를_가리키는_교차_참조_링크를_건너뛰고_상대_링크와_자기_저장소의_링크는_검사한다(onto_cli):
    body = (
        "[다른 저장소](shop:component/api) [등록 안 됨](nowhere:term/x) [없는 상대 링크](../term/none.md)\n\n"
        "[자기 저장소의 없는 것](billing:component/missing) [자기 저장소의 있는 것](billing:component/api) [상대 링크](../term/invoice.md)\n"
    )
    inside = onto_cli.repository("billing", billing_files(body))

    result = onto_cli.run(inside, "validate", within=REPOSITORY)

    findings = [tuple(line.split("\t")) for line in result.stdout.splitlines()]
    path = f"{ONTOLOGY_DIR}/component/gateway.md"
    assert [(f[0], f[2], f[3]) for f in findings] == [(ERROR, path, "broken-reference")] * 2
    assert sorted("none.md" in f[4] for f in findings) == [False, True]
    assert any("billing:component/missing" in f[4] for f in findings)
    assert result.returncode == 1
