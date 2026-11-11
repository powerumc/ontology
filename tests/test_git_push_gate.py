"""`just git push`의 푸시 관문: 푸시 전에 스크립트 검사(`just onto validate`)를 돌리고, 오류가 있으면 아무것도 올리지 않는다.

가장 높은 이음매다. 루트 저장소는 이 저장소의 추적 파일을 임시 디렉토리로 복사한 것이고, 지식 저장소는 로컬 bare 원격에 붙인 가짜 저장소다.
관문은 루트 저장소의 도구(`onto/`)로 작업 트리를 검사하므로 지식 저장소는 온톨로지 층(페이지와 인덱스)을 갖춰야 검사를 통과한다.
푸시의 순서와 중단 조건 자체(지식 저장소 먼저, 실패하면 루트는 올리지 않는다)는 관문을 끈 루트로 `test_git_push.py`가 본다. 여기서는 관문이
켜져 있거나 꺼져 있거나 넘겨졌을 때 그 약속이 그대로인지도 본다.

관문이 막으면 요약 없이 종료 코드 1로 끝나고 걸린 문제를 보여 준다. 강제 옵션(`--force`, `-f`)은 관문을 넘기고, 넘겼다는 사실을 출력에 남긴다.
`--force`는 git의 강제 푸시가 아니다. 원격의 이력을 덮어쓰지 않고, 푸시가 거부되는 경우(원격이 앞서 감)는 그대로 거부된다.
"""

import pytest

from support.onto_cli import ONTOLOGY_DIR, page, repo

ROOT = "루트 저장소"
SUMMARY = "== 요약 =="
PASSED = "푸시 관문: 스크립트 검사에 오류가 없습니다"
BLOCKED = "푸시 관문: 스크립트 검사에 오류가 있어 아무것도 푸시하지 않았습니다"
OFF = "푸시 관문: 꺼져 있어 스크립트 검사를 하지 않았습니다"
BYPASSED = "푸시 관문을 강제로 넘깁니다"
BYPASSED_REMINDER = "주의: 푸시 관문을 강제로 넘겼습니다"

GATEWAY = f"projects/billing/{ONTOLOGY_DIR}/component/gateway.md"


def _clean(**project):
    """스크립트 검사에 문제가 없는 `billing`: 관계가 있는 페이지 하나."""
    return repo("billing", page("component/gateway", "Component", title="결제 게이트웨이", partOf="project"), **project)


def _broken(**project):
    """오류가 하나(`broken-reference`) 있는 `billing`: 없는 엔티티를 가리킨다."""
    return repo("billing", page("component/gateway", "Component", title="결제 게이트웨이", partOf="project", dependsOn="component/ghost"), **project)


def _tip(sandbox, bare, branch="main"):
    found = sandbox.git("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", cwd=bare, check=False)
    return found.stdout.strip() or None


def _attach(sandbox, files, *, push_gate=True, indexed=True):
    """`billing`을 붙인 루트 저장소와 그 클론. 인덱스는 생성물이지만 지식 저장소가 커밋하는 파일이라 만들어 커밋하고, 루트가 그 커밋을 가리키게 한다.

    루트와 `billing` 모두 푸시할 커밋이 하나씩 있는 상태다. `(루트, billing 원격, 클론)`을 돌려준다.
    """
    root = sandbox.root(push_gate=push_gate)
    billing = sandbox.knowledge_remote("billing", files=files)
    root.register(billing)
    clone = root.set_up_clone()
    sub = clone / "projects" / "billing"
    if indexed:
        built = sandbox.just("onto", "build", cwd=clone)
        assert built.returncode == 0, built.stderr
    else:
        (sub / "local.md").write_text("# 메모\n", encoding="utf-8")
    sandbox.git("add", "-A", cwd=sub)
    sandbox.git("commit", "-m", "인덱스", cwd=sub)
    sandbox.git("add", "projects/billing", cwd=clone)
    sandbox.git("commit", "-m", "포인터 billing", cwd=clone)
    return root, billing, clone


def _push(sandbox, clone, *args, **kwargs):
    return sandbox.just("git", "push", *args, cwd=clone, **kwargs)


def _tips(sandbox, root, billing):
    return _tip(sandbox, root.origin), _tip(sandbox, billing.url)


def _problems(result):
    """출력에서 스크립트 검사가 보고한 문제 줄(탭으로 나눈 다섯 칸)을 `(심각도, 지식 저장소, 페이지, 검사 항목)`으로."""
    rows = [tuple(line.split("\t")) for line in result.stdout.splitlines() if line.startswith(("오류\t", "경고\t"))]
    assert all(len(row) == 5 for row in rows), result.stdout
    return [row[:4] for row in rows]


def _pushed(result):
    """요약에서 저장소별 상태를 `{저장소: 상태}`로. 요약이 없으면 빈 딕셔너리다."""
    _, marker, summary = result.stdout.partition(SUMMARY)
    states = ("푸시됨", "올릴 것 없음", "건너뜀", "실패")
    found = {}
    for line in summary.splitlines() if marker else []:
        state, separator, rest = line.partition(": ")
        if separator and state in states:
            found[rest.split(" — ")[0].split(" (")[0]] = state
    return found


# --- 관문이 막는다 -------------------------------------------------------------------------


def test_스크립트_검사에_오류가_있으면_어떤_저장소도_푸시하지_않고_걸린_문제를_보여_준다(sandbox):
    root, billing, clone = _attach(sandbox, _broken())
    tips = _tips(sandbox, root, billing)
    before = (sandbox.snapshot(clone), sandbox.snapshot(clone / "projects" / "billing"))

    result = _push(sandbox, clone)

    assert result.returncode == 1
    assert _tips(sandbox, root, billing) == tips  # 지식 저장소도 루트 저장소도 올라가지 않았다
    assert _problems(result) == [("오류", "billing", GATEWAY, "broken-reference")]
    assert "component/ghost" in result.stdout  # 걸린 문제의 설명
    assert BLOCKED in result.stderr and "just git push --force" in result.stderr  # 막은 이유와 알고서 넘기는 방법
    assert SUMMARY not in result.stdout and BYPASSED not in result.stdout
    assert (sandbox.snapshot(clone), sandbox.snapshot(clone / "projects" / "billing")) == before  # 아무것도 커밋하거나 스테이징하지 않았다


def test_스크립트_검사에_오류가_없으면_푸시한다(sandbox):
    root, billing, clone = _attach(sandbox, _clean())

    result = _push(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert _tip(sandbox, billing.url) == sandbox.head(clone / "projects" / "billing")
    assert _tip(sandbox, root.origin) == sandbox.head(clone)
    assert _problems(result) == []
    assert PASSED in result.stdout
    assert result.stdout.index(PASSED) < result.stdout.index(SUMMARY)  # 검사는 푸시보다 앞이다
    assert _pushed(result) == {"projects/billing": "푸시됨", ROOT: "푸시됨"}


def test_경고만_있으면_경고를_보여_주고_푸시한다(sandbox):
    files = {**_clean(), **page("term/idle", "Term", title="아무와도 이어지지 않은 용어")}  # 고아 페이지는 경고다
    root, billing, clone = _attach(sandbox, files)

    result = _push(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert _problems(result) == [("경고", "billing", f"projects/billing/{ONTOLOGY_DIR}/term/idle.md", "orphan-page")]
    assert _tip(sandbox, billing.url) == sandbox.head(clone / "projects" / "billing")
    assert _tip(sandbox, root.origin) == sandbox.head(clone)
    assert _pushed(result) == {"projects/billing": "푸시됨", ROOT: "푸시됨"}


def test_검사는_커밋된_내용이_아니라_작업_트리를_보고_미커밋_변경_목록이_검사_결과와_함께_보인다(sandbox):
    root, billing, clone = _attach(sandbox, _clean())
    gateway = clone / "projects" / "billing" / ONTOLOGY_DIR / "component" / "gateway.md"
    gateway.write_text(gateway.read_text(encoding="utf-8").replace('"partOf"', '"dependsOn": "component/ghost"\n"partOf"'), encoding="utf-8")  # 커밋하지 않은 수정이 문제를 만든다
    tips = _tips(sandbox, root, billing)

    result = _push(sandbox, clone)

    assert result.returncode == 1
    assert _tips(sandbox, root, billing) == tips
    assert _problems(result) == [("오류", "billing", GATEWAY, "broken-reference")]
    assert "미커밋 변경이 있는 저장소" in result.stdout and "projects/billing" in result.stdout
    assert result.stdout.index("미커밋 변경이 있는 저장소") < result.stdout.index("broken-reference")  # 보고가 검사 결과 앞에 보인다


def test_지식_저장소가_하나도_없어도_관문을_거쳐_루트_저장소를_푸시한다(sandbox):
    root = sandbox.root()
    clone = root.clone()
    (clone / "NOTES.md").write_text("# 메모\n", encoding="utf-8")
    sandbox.git("add", "NOTES.md", cwd=clone)
    sandbox.git("commit", "-m", "메모", cwd=clone)

    result = _push(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert PASSED in result.stdout
    assert _tip(sandbox, root.origin) == sandbox.head(clone)
    assert _pushed(result) == {ROOT: "푸시됨"}


def test_초기화하지_않은_지식_저장소는_관문을_막지_않고_푸시는_그_저장소를_건너뛴다(sandbox):
    root = sandbox.root()
    root.register(sandbox.knowledge_remote("billing"))
    clone = root.clone()  # `just setup`을 하지 않아 `projects/billing`이 빈 디렉토리다
    (clone / "NOTES.md").write_text("# 메모\n", encoding="utf-8")
    sandbox.git("add", "NOTES.md", cwd=clone)
    sandbox.git("commit", "-m", "메모", cwd=clone)

    result = _push(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert [finding[3] for finding in _problems(result)] == ["missing-ontology-layer"]  # 경고뿐이라 막지 않는다
    assert _tip(sandbox, root.origin) == sandbox.head(clone)
    assert _pushed(result) == {"projects/billing": "건너뜀", ROOT: "푸시됨"}


# --- 강제 옵션 -----------------------------------------------------------------------------


@pytest.mark.parametrize("option", ["--force", "-f"])
def test_강제_옵션을_주면_오류가_있어도_푸시하고_관문을_넘겼다는_사실을_출력에_남긴다(sandbox, option):
    root, billing, clone = _attach(sandbox, _broken())

    result = _push(sandbox, clone, option)

    assert result.returncode == 0, result.stderr
    assert _tip(sandbox, billing.url) == sandbox.head(clone / "projects" / "billing")
    assert _tip(sandbox, root.origin) == sandbox.head(clone)
    assert _problems(result) == [("오류", "billing", GATEWAY, "broken-reference")]  # 넘기는 문제는 그대로 보여 준다
    assert BYPASSED in result.stdout
    assert result.stdout.index(BYPASSED) < result.stdout.index(SUMMARY)
    assert BYPASSED_REMINDER in result.stdout.partition(SUMMARY)[2]  # 푸시 결과 뒤에서도 다시 알린다
    assert _pushed(result) == {"projects/billing": "푸시됨", ROOT: "푸시됨"}


def test_강제_옵션을_줘도_넘길_오류가_없으면_넘겼다고_알리지_않는다(sandbox):
    root, billing, clone = _attach(sandbox, _clean())

    result = _push(sandbox, clone, "--force")

    assert result.returncode == 0, result.stderr
    assert PASSED in result.stdout
    assert BYPASSED not in result.stdout and BYPASSED_REMINDER not in result.stdout
    assert _pushed(result) == {"projects/billing": "푸시됨", ROOT: "푸시됨"}


def test_강제_옵션은_git의_강제_푸시가_아니라서_원격이_앞서_가면_그대로_거부된다(sandbox):
    root, billing, clone = _attach(sandbox, _broken())
    other = billing.commit()  # billing의 원격에 로컬에 없는 커밋이 생겨 푸시가 거부된다
    root_tip = _tip(sandbox, root.origin)

    result = _push(sandbox, clone, "--force")

    assert result.returncode == 1
    assert _tip(sandbox, billing.url) == other  # 원격의 이력을 덮어쓰지 않았다
    assert _tip(sandbox, root.origin) == root_tip
    assert _pushed(result) == {"projects/billing": "실패", ROOT: "건너뜀"}
    assert "rejected" in result.stdout


@pytest.mark.parametrize("arguments", [("--frce",), ("--force", "billing"), ("billing",), ("-x",)], ids=["오타", "이름이_더_있다", "이름만", "모르는_짧은_옵션"])
def test_알_수_없는_인자는_아무것도_하지_않고_거부한다(sandbox, arguments):
    root, billing, clone = _attach(sandbox, _clean())
    tips = _tips(sandbox, root, billing)
    before = sandbox.snapshot(clone)

    result = _push(sandbox, clone, *arguments)

    assert result.returncode == 1
    assert "알 수 없는 인자" in result.stderr and "--force" in result.stderr  # 쓸 수 있는 옵션을 알린다
    assert _tips(sandbox, root, billing) == tips
    assert sandbox.snapshot(clone) == before
    assert PASSED not in result.stdout and SUMMARY not in result.stdout  # 검사도 푸시도 하지 않았다


# --- 관문을 끈다: 루트 기본 규칙만 ----------------------------------------------------------


def test_루트_기본_규칙으로_관문을_끄면_검사하지_않고_푸시하고_껐다고_알린다(sandbox):
    root, billing, clone = _attach(sandbox, _broken(), push_gate=False, indexed=False)

    result = _push(sandbox, clone)

    assert result.returncode == 0, result.stderr
    assert _tip(sandbox, billing.url) == sandbox.head(clone / "projects" / "billing")
    assert _tip(sandbox, root.origin) == sandbox.head(clone)
    assert _problems(result) == []  # 오류가 있는 저장소여도 검사하지 않았다
    assert OFF in result.stdout and PASSED not in result.stdout and BYPASSED not in result.stdout
    assert _pushed(result) == {"projects/billing": "푸시됨", ROOT: "푸시됨"}


def test_지식_저장소의_규칙으로는_관문을_끌_수_없다(sandbox):
    """저장소의 `rules`에 `push-gate`를 적으면 `invalid-rules` 오류이고, 관문은 그대로 켜진 채 그 오류로 막는다."""
    root, billing, clone = _attach(sandbox, _clean(rules={"push-gate": {"enabled": False}}))
    tips = _tips(sandbox, root, billing)

    result = _push(sandbox, clone)

    assert result.returncode == 1
    assert _tips(sandbox, root, billing) == tips
    assert [finding[3] for finding in _problems(result)] == ["invalid-rules"]
    assert OFF not in result.stdout and BLOCKED in result.stderr


def test_지식_저장소의_규칙이_관문을_끄려_해도_오류가_있는_저장소는_막힌다(sandbox):
    root, billing, clone = _attach(sandbox, _broken(rules={"push-gate": {"enabled": False}}))
    tips = _tips(sandbox, root, billing)

    result = _push(sandbox, clone)

    assert result.returncode == 1
    assert _tips(sandbox, root, billing) == tips
    assert sorted(finding[3] for finding in _problems(result)) == ["broken-reference", "invalid-rules"]


# --- 읽을 수 없는 루트 기본 규칙 -------------------------------------------------------------


def test_루트_기본_규칙을_읽을_수_없으면_관문을_열지_않고_막고_강제_옵션만_넘긴다(sandbox):
    root, billing, clone = _attach(sandbox, _clean())
    rules = clone / "onto" / "rules.yaml"
    rules.write_text(rules.read_text(encoding="utf-8") + "\nmodel-unknown-key: 1\n", encoding="utf-8")  # 모르는 키는 오류다
    tips = _tips(sandbox, root, billing)

    blocked = _push(sandbox, clone)

    assert blocked.returncode == 1
    assert _tips(sandbox, root, billing) == tips  # 관문이 켜져 있는지 알 수 없으면 켜진 것으로 본다
    assert "model-unknown-key" in blocked.stderr and BLOCKED in blocked.stderr

    forced = _push(sandbox, clone, "--force")

    assert forced.returncode == 0, forced.stderr
    assert _tip(sandbox, billing.url) == sandbox.head(clone / "projects" / "billing")
    assert BYPASSED in forced.stdout


# --- 관문이 꺼져 있거나 넘겨져도 푸시의 순서와 중단 조건은 그대로다 -----------------------------------


@pytest.mark.parametrize(
    ("push_gate", "arguments", "files"),
    [(False, (), _broken()), (True, ("--force",), _broken())],
    ids=["관문이_꺼져_있다", "관문을_강제로_넘겼다"],
)
def test_지식_저장소의_푸시가_실패하면_루트_저장소는_올리지_않고_실패와_이유를_보고한다(sandbox, push_gate, arguments, files):
    root, billing, clone = _attach(sandbox, files, push_gate=push_gate, indexed=push_gate)
    billing.url.rename(billing.url.with_name("moved-away.git"))  # billing의 원격에 접속할 수 없다
    root_tip = _tip(sandbox, root.origin)

    result = _push(sandbox, clone, *arguments)

    assert result.returncode == 1
    assert _tip(sandbox, root.origin) == root_tip  # 루트는 올리지 않았다
    assert _pushed(result) == {"projects/billing": "실패", ROOT: "건너뜀"}


# --- 어디서 불러도 루트 저장소를 검사한다 ------------------------------------------------------------


def test_d로_실행_위치를_바꿔도_관문은_루트_저장소를_검사한다(sandbox):
    """`-d`는 `Justfile`을 `-f`로 가리킬 때 실행 위치를 바꾼다. 관문이 그 위치를 루트로 믿으면 저장소를 하나도 찾지 못한 채 통과한다."""
    root, billing, clone = _attach(sandbox, _broken())
    tips = _tips(sandbox, root, billing)

    for directory in (clone / "projects", clone / "projects" / "billing", clone / "onto"):
        result = sandbox.just("-f", clone / "Justfile", "-d", directory, "git", "push", cwd=clone)

        assert result.returncode == 1, (directory, result.stdout, result.stderr)
        assert _tips(sandbox, root, billing) == tips, directory
        assert _problems(result) == [("오류", "billing", GATEWAY, "broken-reference")], directory


def test_하위_디렉토리에서_불러도_관문은_루트_저장소를_검사한다(sandbox):
    root, billing, clone = _attach(sandbox, _broken())
    tips = _tips(sandbox, root, billing)

    result = _push(sandbox, clone / "projects" / "billing" / ONTOLOGY_DIR)

    assert result.returncode == 1
    assert _tips(sandbox, root, billing) == tips
    assert _problems(result) == [("오류", "billing", GATEWAY, "broken-reference")]
