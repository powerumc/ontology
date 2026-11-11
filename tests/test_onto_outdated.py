"""공통 어휘의 버전, 뒤처진 루트 관리 파일(`outdated-managed-files`), 최신화 뒤의 구조 제약 보고.

가장 높은 이음매다. 루트 저장소(`sandbox.root()`)에 지식 저장소를 서브모듈로 붙이고 `just onto sync`와 `just onto validate`를 부른다.
루트의 기능은 `root.work / "onto"`의 추적하는 파일이다. 테스트가 그 파일을 고치면 루트가 기능을 고친 것이다.
"""

import re
import shutil
from pathlib import Path

from support.onto_cli import ONTOLOGY_DIR, page, parse_table, repo

CHECK = "outdated-managed-files"
SEMVER = re.compile(
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-((0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(\.(0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(\+([0-9a-zA-Z-]+(\.[0-9a-zA-Z-]+)*))?"
)
VERSION_INFO = re.compile(r'owl:versionInfo\s+"([^"]*)"')

CONFIGURED = repo(
    "billing",
    page("component/gateway", "Component", title="결제 게이트웨이", partOf="project"),
    page("plan/launch", "Plan", title="출시 계획", about="component/gateway"),
    title="결제",
)


def attach(sandbox, root, name: str, *, files: dict[str, str] | None = None) -> Path:
    root.register(sandbox.knowledge_remote(name, files=files))
    return root.work / "projects" / name


def sync(sandbox, root, *args: str):
    return sandbox.just("onto", "sync", *args, cwd=root.work)


def validate(sandbox, root):
    return sandbox.just("onto", "validate", cwd=root.work)


def findings(result, check: str = CHECK) -> list[list[str]]:
    """`validate`의 보고(탭으로 나눈 다섯 칸) 가운데 `check`의 것."""
    return [row for row in parse_table(result.stdout) if len(row) == 5 and row[3] == check]


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{path}에 `{old}`가 없다"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# --- 공통 어휘의 버전 ----------------------------------------------------------------------


def declared_version(vocabulary: Path) -> str:
    match = VERSION_INFO.search(vocabulary.read_text(encoding="utf-8"))
    assert match, "공통 어휘(onto.ttl)에 `owl:versionInfo`가 없다"
    return match.group(1)


def test_공통_어휘의_버전은_semver로_정해져_있다(sandbox):
    root = sandbox.root()

    version = declared_version(root.work / "onto" / "vocab" / "onto.ttl")

    assert SEMVER.fullmatch(version), version


def test_공통_어휘의_버전이_지식_저장소의_dot_onto에_찍힌다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    assert sync(sandbox, root, "billing").returncode == 0

    stamped = declared_version(billing / ".onto" / "vocab" / "onto.ttl")

    assert stamped == declared_version(root.work / "onto" / "vocab" / "onto.ttl")
    assert SEMVER.fullmatch(stamped)


# --- 뒤처진 루트 관리 파일 ----------------------------------------------------------------


def test_최신화한_직후의_지식_저장소는_경고하지_않는다(sandbox):
    root = sandbox.root()
    attach(sandbox, root, "billing", files=CONFIGURED)
    assert sync(sandbox, root, "billing").returncode == 0

    result = validate(sandbox, root)

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_버전_번호를_올리지_않고_루트의_코드만_고쳐도_뒤처진_지식_저장소를_경고한다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing", files=CONFIGURED)
    shop = attach(sandbox, root, "shop", files=repo("shop"))
    assert sync(sandbox, root).returncode == 0
    version = declared_version(root.work / "onto" / "vocab" / "onto.ttl")
    edit(root.work / "onto" / "onto_tool" / "cli.py", '"모듈형 온톨로지 도구"', '"모듈형 온톨로지 도구(고침)"')  # 코드만 고친다
    assert declared_version(root.work / "onto" / "vocab" / "onto.ttl") == version  # 버전 번호는 그대로다

    result = validate(sandbox, root)

    assert result.returncode == 0, result.stdout  # 경고는 종료 코드를 바꾸지 않는다
    rows = findings(result)
    assert sorted(row[1] for row in rows) == ["billing", "shop"]
    for severity, repository, file, check, message in rows:
        assert severity == "경고"
        assert file == f"projects/{repository}/.onto"
        assert "`.onto/onto_tool/cli.py`" in message  # 어느 파일이 다른지 알린다
        assert f"just onto sync {repository}" in message  # 어떻게 고치는지 알린다
        assert f"버전은 {version}으로 같지만 내용이 다르다" in message  # 버전 번호로는 알 수 없다는 것
    # 최신화하면 사라진다
    assert sync(sandbox, root).returncode == 0
    assert validate(sandbox, root).stdout == ""
    assert (billing / ".onto" / "onto_tool" / "cli.py").read_bytes() == (root.work / "onto" / "onto_tool" / "cli.py").read_bytes()
    assert shop.is_dir()


def test_공통_어휘의_버전을_올렸으면_저장소의_버전과_루트의_버전을_함께_알린다(sandbox):
    root = sandbox.root()
    attach(sandbox, root, "billing", files=CONFIGURED)
    assert sync(sandbox, root, "billing").returncode == 0
    old = declared_version(root.work / "onto" / "vocab" / "onto.ttl")
    edit(root.work / "onto" / "vocab" / "onto.ttl", f'owl:versionInfo "{old}"', 'owl:versionInfo "9.8.7"')

    result = validate(sandbox, root)

    (row,) = findings(result)
    assert f"이 저장소 {old}, 루트 9.8.7" in row[4]
    assert "`.onto/vocab/onto.ttl`" in row[4]


def test_사본의_버전을_읽을_수_없으면_알_수_없다고_알린다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing", files=CONFIGURED)
    assert sync(sandbox, root, "billing").returncode == 0
    (billing / ".onto" / "vocab" / "onto.ttl").write_text("이것은 Turtle이 아니다 {{\n", encoding="utf-8")

    (row,) = findings(validate(sandbox, root))

    assert "`.onto/vocab/onto.ttl`" in row[4] and "알 수 없" in row[4]


def test_루트가_파일을_더했으면_지식_저장소의_없는_파일로_알린다(sandbox):
    root = sandbox.root()
    attach(sandbox, root, "billing", files=CONFIGURED)
    assert sync(sandbox, root, "billing").returncode == 0
    (root.work / "onto" / "template" / "extra.md").write_text("새 견본\n", encoding="utf-8")
    sandbox.git("add", "onto/template/extra.md", cwd=root.work)

    (row,) = findings(validate(sandbox, root))

    assert "없는 파일 1개(`.onto/template/extra.md`)" in row[4]


def test_루트에서_추적하지_않는_파일은_복사되지_않으므로_뒤처진_것으로_보지_않는다(sandbox):
    root = sandbox.root()
    attach(sandbox, root, "billing", files=CONFIGURED)
    assert sync(sandbox, root, "billing").returncode == 0
    (root.work / "onto" / "notes.txt").write_text("아직 git add하지 않았다\n", encoding="utf-8")

    result = validate(sandbox, root)

    assert (result.returncode, result.stdout) == (0, "")


def test_루트에서_없어졌는데_남은_파일과_손으로_고친_사본도_경고한다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing", files=CONFIGURED)
    extra = root.work / "onto" / "extra.txt"
    extra.write_text("원본\n", encoding="utf-8")
    sandbox.git("add", "onto/extra.txt", cwd=root.work)
    assert sync(sandbox, root, "billing").returncode == 0
    assert validate(sandbox, root).stdout == ""
    sandbox.git("rm", "-q", "-f", "onto/extra.txt", cwd=root.work)  # 루트에서 없앴다
    edit(billing / ".onto" / "rules.yaml", "checks:", "checks:  # 내가 손으로 고쳤다")

    (row,) = findings(validate(sandbox, root))

    assert "내용이 다른 파일 1개(`.onto/rules.yaml`)" in row[4]
    assert "루트에서 없어졌는데 남은 파일 1개(`.onto/extra.txt`)" in row[4]


def test_dot_onto가_없는_지식_저장소는_최신화가_필요하다고_경고한다(sandbox):
    root = sandbox.root()
    attach(sandbox, root, "billing", files={**CONFIGURED, f"{ONTOLOGY_DIR}/index.md": "x\n"})

    (row,) = findings(validate(sandbox, root))

    assert row[1] == "billing" and "`.onto/`가 없다" in row[4] and "just onto sync billing" in row[4]


def test_dot_onto가_링크이면_읽지_않고_사본을_읽을_수_없다고_경고한다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing", files=CONFIGURED)
    outside = sandbox.new_dir("elsewhere", "copy")
    (billing / ".onto").symlink_to(outside)

    (row,) = findings(validate(sandbox, root))

    assert "심볼릭 링크" in row[4]


def test_초기화되지_않은_서브모듈은_경고하지_않는다(sandbox):
    """새로 클론한 직후의 루트다. 지식 저장소의 내용이 없으니 사본을 비교할 수 없고, 최신화도 건너뛴다."""
    root = sandbox.root()
    attach(sandbox, root, "billing", files=CONFIGURED)
    clone = root.clone()  # 서브모듈을 초기화하지 않은 상태

    result = sandbox.just("onto", "validate", cwd=clone)

    assert findings(result) == []


def test_지식_저장소는_규칙으로_이_경고를_끌_수_있다(sandbox):
    root = sandbox.root()
    attach(sandbox, root, "billing", files=repo("billing", rules={"checks": {CHECK: {"enabled": False}}}))
    attach(sandbox, root, "shop", files=repo("shop"))

    result = validate(sandbox, root)

    assert [row[1] for row in findings(result)] == ["shop"]  # 끈 저장소만 빠진다


# --- 루트의 검사는 항상 루트의 최신 공통 어휘로 한다 ----------------------------------------------


def test_루트_관리_파일이_뒤처진_지식_저장소도_루트의_최신_공통_어휘로_검사한다(sandbox):
    """지식 저장소의 `.onto/vocab/`(옛 구조 제약)은 루트의 검사가 읽지 않는다."""
    broken = {**CONFIGURED, f"{ONTOLOGY_DIR}/component/untitled.md": "---\nclass: Component\npartOf: project\n---\n\n제목이 없다\n"}
    root = sandbox.root()
    billing = attach(sandbox, root, "billing", files=broken)
    assert sync(sandbox, root, "billing").returncode == 0
    fresh = validate(sandbox, root)
    assert [row[3] for row in parse_table(fresh.stdout) if len(row) == 5] == ["missing-property"]  # 루트의 구조 제약이 제목 없는 페이지를 잡는다

    # 지식 저장소의 사본을 아무것도 제약하지 않는 옛 구조 제약과 빈 공통 어휘로 되돌린다
    (billing / ".onto" / "vocab" / "shapes.ttl").write_text("# 옛 구조 제약: 아무것도 제약하지 않는다\n", encoding="utf-8")
    edit(billing / ".onto" / "vocab" / "onto.ttl", "onto:Plan a owl:Class", "onto:OldPlan a owl:Class")

    stale = validate(sandbox, root)

    checks = sorted(row[3] for row in parse_table(stale.stdout) if len(row) == 5)
    assert checks == sorted(["missing-property", CHECK])  # 같은 구조 제약 위반을 그대로 잡고, 뒤처진 사본은 따로 경고한다
    assert stale.returncode == fresh.returncode == 1


# --- 최신화 뒤의 구조 제약 보고 --------------------------------------------------------------


def test_최신화_뒤에_구조_제약에_어긋난_페이지가_있으면_고칠_곳을_보고한다(sandbox):
    files = {
        **CONFIGURED,
        f"{ONTOLOGY_DIR}/plan/oops.md": "---\nclass: Plan\ntitle: 잘못 쓴 계획\npartOf: component/gateway\n---\n\n본문\n",  # partOf는 Component만 쓴다
    }
    root = sandbox.root()
    attach(sandbox, root, "billing", files=files)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr  # 최신화는 끝났다. 페이지는 저장소 소유라 고치지 않고 보고만 한다
    lines = result.stdout.rstrip().splitlines()
    summary = next(number for number, line in enumerate(lines) if line.startswith("최신화: 지식 저장소"))
    report = lines[summary + 1 :]
    assert "구조 제약" in report[0]
    rows = [line.split("\t") for line in report[1:]]
    assert [(row[1], row[2], row[3]) for row in rows] == [("billing", "projects/billing/docs/ontology/plan/oops.md", "relation-domain")]
    assert "partOf" in rows[0][4]


def test_어휘를_올려_새_구조_제약에_어긋나게_된_페이지를_보고한다(sandbox):
    """`Term`의 `about`은 허용되어 있었다. 루트가 구조 제약을 좁히고 최신화하면 그 페이지가 어긋난다."""
    files = {**CONFIGURED, f"{ONTOLOGY_DIR}/term/refund.md": "---\nclass: Term\ntitle: 환불\nabout: project\n---\n\n본문\n"}
    root = sandbox.root()
    attach(sandbox, root, "billing", files=files)
    before = sync(sandbox, root, "billing")
    assert before.returncode == 0 and "구조 제약" not in before.stdout  # 어긋나지 않으면 보고할 것이 없다
    edit(root.work / "onto" / "vocab" / "shapes.ttl", "[ sh:class onto:Report ] [ sh:class onto:Term ] )", "[ sh:class onto:Report ] )")

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert re.search(r"오류\tbilling\tprojects/billing/docs/ontology/term/refund\.md\trelation-domain\t.*about", result.stdout)


def test_구조_제약_보고는_최신화한_지식_저장소만_다룬다(sandbox):
    bad = {**CONFIGURED, f"{ONTOLOGY_DIR}/plan/oops.md": "---\nclass: Plan\ntitle: 잘못 쓴 계획\npartOf: component/gateway\n---\n\n본문\n"}
    root = sandbox.root()
    attach(sandbox, root, "billing", files=bad)
    attach(sandbox, root, "shop", files={**repo("shop"), f"{ONTOLOGY_DIR}/plan/oops.md": bad[f"{ONTOLOGY_DIR}/plan/oops.md"]})

    result = sync(sandbox, root, "shop")

    assert "projects/shop/" in result.stdout and "projects/billing/" not in result.stdout


def test_구조_제약_보고는_어휘가_정하는_것만_다루고_저장소의_규칙을_따른다(sandbox):
    files = {
        **CONFIGURED,
        f"{ONTOLOGY_DIR}/plan/lonely.md": "---\nclass: Plan\ntitle: 외톨이 계획\n---\n\n본문\n",  # 고아 페이지(경고)는 어휘와 무관하다
        f"{ONTOLOGY_DIR}/plan/oops.md": "---\nclass: Plan\ntitle: 잘못 쓴 계획\npartOf: component/gateway\n---\n\n본문\n",
    }
    root = sandbox.root()
    attach(sandbox, root, "billing", files=files)
    on = sync(sandbox, root, "billing")
    assert "plan/lonely.md" not in on.stdout and "orphan-page" not in on.stdout
    assert "relation-domain" in on.stdout

    muted_yaml = 'name: "other"\nrules: {checks: {relation-domain: {enabled: false}}}\n'  # 이 저장소만 relation-domain을 끈다
    root2 = sandbox.root(name="second")
    attach(sandbox, root2, "other", files={**files, f"{ONTOLOGY_DIR}/ontology.yaml": muted_yaml})

    muted = sync(sandbox, root2, "other")

    assert muted.returncode == 0 and "relation-domain" not in muted.stdout  # 저장소가 끈 항목은 보고하지 않는다
