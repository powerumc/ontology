"""`just onto sync [이름]`: 루트 저장소의 기능(`onto/`)을 지식 저장소에 최신화한다.

가장 높은 이음매다. 루트 저장소는 이 저장소의 추적 파일을 임시 디렉토리로 복사한 것이고, 지식 저장소는 로컬 bare 원격을
서브모듈로 붙인 것이다. 루트 저장소의 `onto/`가 복사의 원본이라, 테스트가 `onto/`의 파일을 고치면 루트의 기능이 바뀐 것이다.
"""

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

import pytest

from support.onto_cli import ONTOLOGY_DIR, page, parse_table, repo

YAML = f"{ONTOLOGY_DIR}/ontology.yaml"
INDEX = f"{ONTOLOGY_DIR}/index.md"
RECORD_NAME = ".sync-record.json"  # 마지막 최신화가 `.onto/`에 남기는 기록


def attach(sandbox, root, name: str, *, files: dict[str, str] | None = None, directory: str | None = None) -> Path:
    """지식 저장소를 서브모듈로 붙이고 그 작업 트리의 경로를 돌려준다. 커밋과 푸시까지 한다. `directory`는 서브모듈 디렉토리 이름이다."""
    root.register(sandbox.knowledge_remote(name, files=files), name=directory)
    return root.work / "projects" / (directory or name)


def sync(sandbox, root, *args: str, cwd: Path | None = None):
    return sandbox.just("onto", "sync", *args, cwd=cwd or root.work)


def project_names(sandbox, root) -> list[str]:
    """`just onto query`가 보는, 각 지식 저장소의 `Project` 엔티티가 가진 저장소 이름."""
    result = sandbox.just(
        "onto", "query", "SELECT ?r WHERE { ?e a onto:Project ; onto:repository ?r } ORDER BY ?r", cwd=root.work
    )
    assert result.returncode == 0, result.stderr
    return [row[0] for row in parse_table(result.stdout)[1:]]


# --- 저장소 소유 파일: ontology.yaml ---------------------------------------------------


def test_구성이_없는_지식_저장소에_sync하면_name이_디렉토리_이름이고_공유_범위가_private인_ontology_yaml을_만든다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    assert not (billing / ONTOLOGY_DIR).exists()

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    text = (billing / YAML).read_text(encoding="utf-8")
    assert re.search(r"^scope: private\b", text, re.MULTILINE)  # 가장 좁은 공유 범위
    assert project_names(sandbox, root) == ["billing"]  # 도구가 읽은 name


def test_만든_ontology_yaml은_프로젝트_사이의_의존을_적는_선택_키를_주석으로_안내한다(sandbox):
    """`Project`가 쓰는 관계는 `dependsOn` 하나다. 주석이라 만들자마자 검사를 통과하고, 풀어 쓰면 도구가 받아들인다."""
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    text = (billing / YAML).read_text(encoding="utf-8")
    assert re.search(r"^# dependsOn:.*\bProject\b", text, re.MULTILINE)
    assert not re.search(r"^dependsOn:", text, re.MULTILINE)  # 선택 키라 적어 두지 않는다


def test_ontology_yaml의_name은_원격_저장소가_아니라_서브모듈_디렉토리_이름이다(sandbox):
    root = sandbox.root()
    attach(sandbox, root, "billing", directory="invoice")

    result = sync(sandbox, root, "invoice")

    assert result.returncode == 0, result.stderr
    assert project_names(sandbox, root) == ["invoice"]


def test_sync는_클래스별_디렉토리를_미리_만들지_않는다(sandbox):
    """온톨로지 층에는 저장소 소유 파일(`ontology.yaml`)과 생성물(`index.md`)만 생긴다. 클래스별 디렉토리는 첫 페이지를 쓸 때 생긴다."""
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")

    assert sync(sandbox, root, "billing").returncode == 0

    assert sorted(p.name for p in (billing / ONTOLOGY_DIR).iterdir()) == ["index.md", "ontology.yaml"]


# --- 루트 관리 파일: .onto/ ------------------------------------------------------------


def tracked_onto_files(sandbox, root) -> list[str]:
    """루트 저장소가 추적하는 `onto/` 파일. `onto/`를 뗀 경로."""
    listing = sandbox.git("ls-files", "-z", "onto", cwd=root.work).stdout
    return sorted(path.removeprefix("onto/") for path in listing.split("\0") if path)


def files_under(directory: Path) -> dict[str, bytes]:
    """`directory` 아래 모든 일반 파일의 상대 경로와 내용."""
    return {path.relative_to(directory).as_posix(): path.read_bytes() for path in sorted(directory.rglob("*")) if path.is_file()}


def test_루트가_추적하는_onto_파일이_지식_저장소의_dot_onto로_복사된다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    copied = files_under(billing / ".onto")
    copied.pop(RECORD_NAME, None)  # 최신화가 남기는 기록은 루트에서 온 파일이 아니다
    tracked = tracked_onto_files(sandbox, root)
    assert sorted(copied) == tracked
    assert all(copied[path] == (root.work / "onto" / path).read_bytes() for path in tracked)
    # 온톨로지 도구, 모듈 진입점, 공통 어휘, 구조 제약, 루트 기본 규칙이 들어 있다
    for essential in ("Justfile", "onto_tool/cli.py", "vocab/onto.ttl", "vocab/shapes.ttl", "vocab/context.jsonld", "rules.yaml"):
        assert essential in copied
    # 규약 문서와 클래스별 페이지 템플릿
    for template in ("conventions", "component", "plan", "policy", "term", "decision", "report"):
        assert f"template/{template}.md" in copied


def test_루트의_가상환경_캐시_산출물과_추적하지_않는_파일은_복사하지_않는다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    sandbox.just("onto", "build", cwd=root.work, check=True)  # 루트에 .venv, __pycache__, .build가 생긴다
    (root.work / "onto" / "notes.txt").write_text("추적하지 않는 새 파일\n", encoding="utf-8")
    assert (root.work / "onto" / ".venv").is_dir() and (root.work / "onto" / ".build").is_dir()

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    copied = files_under(billing / ".onto")
    assert "notes.txt" not in copied
    assert not [path for path in copied if path.startswith((".venv/", ".build/")) or "__pycache__" in path]


def test_sync_뒤_지식_저장소의_git_상태에_dot_onto가_나타나지_않고_변경은_커밋되지_않는다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    head = sandbox.head(billing)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    status = sandbox.git("status", "--porcelain", "--untracked-files=all", cwd=billing).stdout.splitlines()
    assert sorted(status) == sorted(["?? .gitignore", "?? AGENTS.md", f"?? {INDEX}", f"?? {YAML}"])  # 지침 파일이 없던 저장소는 AGENTS.md가 생긴다
    assert sandbox.head(billing) == head
    assert sandbox.git("diff", "--cached", "--name-only", cwd=billing).stdout == ""  # 스테이징도 하지 않는다
    assert sandbox.git("check-ignore", "--quiet", ".onto/Justfile", cwd=billing, check=False).returncode == 0


def test_루트_관리_파일에_손으로_고치지_말라는_표시가_있다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")

    assert sync(sandbox, root, "billing").returncode == 0

    notice = (billing / ".onto" / "README.md").read_text(encoding="utf-8")
    assert "손으로 고치지 않는다" in notice


# --- .gitignore의 표시된 블록 ----------------------------------------------------------

BEGIN = "# onto:begin"
END = "# onto:end"


def block_lines(text: str) -> list[str]:
    """`.gitignore`에서 표시된 블록(표시 줄 포함)의 줄. 표시가 하나씩 있어야 한다."""
    lines = text.splitlines()
    begins = [i for i, line in enumerate(lines) if line.startswith(BEGIN)]
    ends = [i for i, line in enumerate(lines) if line == END]
    assert len(begins) == 1 and len(ends) == 1 and begins[0] < ends[0], text
    return lines[begins[0] : ends[0] + 1]


def test_sync가_없던_gitignore를_만들고_루트_관리_파일의_경로를_제외하는_표시된_블록을_넣는다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    assert not (billing / ".gitignore").exists()

    assert sync(sandbox, root, "billing").returncode == 0

    block = block_lines((billing / ".gitignore").read_text(encoding="utf-8"))
    assert "/.onto/" in block
    assert "/.claude/skills/onto-*/" in block  # 스킬 사본도 루트 관리 파일이다
    assert "손으로 고치지 않는다" in block[0]
    ignored = lambda path: sandbox.git("check-ignore", "--quiet", path, cwd=billing, check=False).returncode == 0  # noqa: E731
    assert ignored(".onto/Justfile") and ignored(".claude/skills/onto-ingest/SKILL.md")
    assert not ignored(".claude/skills/team-skill/SKILL.md") and not ignored("docs/ontology/ontology.yaml")  # 저장소의 것은 제외하지 않는다


def test_gitignore에_이미_있는_내용은_한_글자도_바뀌지_않고_블록이_뒤에_덧붙는다(sandbox):
    original = "node_modules/\n*.log\n# 내가 쓴 주석\n"
    root = sandbox.root()
    billing = attach(sandbox, root, "billing", files={"README.md": "# billing\n", ".gitignore": original})

    assert sync(sandbox, root, "billing").returncode == 0

    text = (billing / ".gitignore").read_text(encoding="utf-8")
    assert text.startswith(original)
    assert block_lines(text[len(original) :])


def test_gitignore에_블록이_이미_있으면_그_자리에서_내용만_바뀌고_중복되지_않는다(sandbox):
    stale = f"앞\n*.log\n{BEGIN} 옛 설명\n/옛-경로/\n{END}\n뒤\n!keep.log\n"
    root = sandbox.root()
    billing = attach(sandbox, root, "billing", files={"README.md": "# billing\n", ".gitignore": stale})

    assert sync(sandbox, root, "billing").returncode == 0

    text = (billing / ".gitignore").read_text(encoding="utf-8")
    block = block_lines(text)
    assert "/옛-경로/" not in text and "/.onto/" in block
    assert text.startswith("앞\n*.log\n" + block[0] + "\n")  # 블록은 있던 자리다
    assert text.endswith(f"{END}\n뒤\n!keep.log\n")  # 블록 뒤는 그대로다


def test_gitignore에_커밋되지_않은_수정이_있어도_블록만_교체한다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing", files={"README.md": "# billing\n", ".gitignore": "committed\n"})
    (billing / ".gitignore").write_text(f"mine\n{BEGIN} 옛 설명\n/옛-경로/\n{END}\n미커밋 수정\n", encoding="utf-8")
    assert sandbox.git("status", "--porcelain", ".gitignore", cwd=billing).stdout == " M .gitignore\n"

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    text = (billing / ".gitignore").read_text(encoding="utf-8")
    assert text.startswith("mine\n") and text.endswith(f"{END}\n미커밋 수정\n")
    assert "/옛-경로/" not in text and "/.onto/" in block_lines(text)


def test_블록의_내용이_이미_같으면_gitignore를_다시_쓰지_않는다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing", files={"README.md": "# billing\n", ".gitignore": "a\n"})
    assert sync(sandbox, root, "billing").returncode == 0
    gitignore = billing / ".gitignore"
    before = gitignore.read_bytes()
    os.utime(gitignore, ns=(1_000_000_000, 1_000_000_000))  # 다시 쓰면 바뀔 시각을 먼 과거로 돌려 둔다

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert gitignore.read_bytes() == before
    assert gitignore.stat().st_mtime_ns == 1_000_000_000


@pytest.mark.parametrize(
    "original",
    ["no-trailing-newline", "", "a\n\n\n", "a\r\nb\r\n", "a\nb"],
    ids=["끝에_줄바꿈이_없다", "빈_파일", "빈_줄로_끝난다", "CRLF", "LF_끝에_줄바꿈이_없다"],
)
def test_gitignore의_모양이_달라도_기존_내용은_그대로_앞에_남고_두_번째_sync는_바꾸지_않는다(sandbox, original):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing", files={"README.md": "# billing\n", ".gitignore": original})

    assert sync(sandbox, root, "billing").returncode == 0

    raw = (billing / ".gitignore").read_bytes()
    text = raw.decode("utf-8")
    assert text.startswith(original)
    assert "/.onto/" in block_lines(text)
    if "\r\n" in original:  # CRLF 파일은 블록도 CRLF다
        assert "\n" not in text.replace("\r\n", "")
    assert sync(sandbox, root, "billing").returncode == 0
    assert (billing / ".gitignore").read_bytes() == raw


@pytest.mark.parametrize(
    "broken",
    [f"a\n{BEGIN}\n/x/\n", f"a\n{END}\n/x/\n", f"{END}\n/x/\n{BEGIN}\n", f"{BEGIN}\n{END}\nb\n{BEGIN}\n{END}\n"],
    ids=["끝_표시가_없다", "시작_표시가_없다", "끝이_시작보다_앞이다", "블록이_둘이다"],
)
def test_표시가_짝이_맞지_않는_gitignore는_고치지_않고_그_저장소를_최신화하지_않는다(sandbox, broken):
    """어느 블록인지 알 수 없다. 제외하지 못한 채 `.onto/`를 복사하면 루트 관리 파일이 지식 저장소의 git 상태에 나타나므로 아무것도 하지 않는다."""
    root = sandbox.root()
    billing = attach(sandbox, root, "billing", files={"README.md": "# billing\n", ".gitignore": broken})
    before = sandbox.snapshot(billing)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1
    assert ".gitignore" in result.stdout
    assert (billing / ".gitignore").read_text(encoding="utf-8") == broken
    assert not (billing / ".onto").exists() and not (billing / ONTOLOGY_DIR).exists()
    assert sandbox.snapshot(billing) == before


def test_gitignore가_심볼릭_링크이면_따라가지_않는다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    outside = sandbox.new_dir("elsewhere", "outside") / "ignore"
    outside.write_text("밖의 파일\n", encoding="utf-8")
    (billing / ".gitignore").symlink_to(outside)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1
    assert outside.read_text(encoding="utf-8") == "밖의 파일\n"
    assert not (billing / ".onto").exists()


# --- 구성이 이미 있는 지식 저장소, 루트 관리 파일만 바뀐다 -----------------------------------

CONFIGURED = repo(
    "billing",
    page("component/gateway", "Component", title="결제 게이트웨이", partOf="project"),
    page("plan/launch", "Plan", title="출시 계획", about="component/gateway"),
    title="결제",
    scope="team:payments",
)


def owned_files(billing: Path) -> dict[str, tuple[bytes, int]]:
    """지식 저장소의 저장소 소유 파일(원본 문서와 온톨로지 층)의 내용과 수정 시각. 루트 관리 파일(`.onto/`, 스킬 사본 `.claude/skills/onto-*/`)과 표시된 블록이 든 파일(`.gitignore`, 지침 파일)은 뺀다."""
    found = {}
    for path in sorted(billing.rglob("*")):
        relative = path.relative_to(billing).as_posix()
        if relative.startswith(".claude/skills/onto-"):
            continue
        if path.is_file() and relative.split("/")[0] not in (".git", ".onto") and relative not in (".gitignore", "CLAUDE.md", "AGENTS.md"):
            found[relative] = (path.read_bytes(), path.stat().st_mtime_ns)
    return found


def test_구성이_이미_있는_지식_저장소는_저장소_소유_파일이_한_글자도_바뀌지_않고_루트_관리_파일만_생긴다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing", files={**CONFIGURED, "README.md": "# billing\n"})
    before = owned_files(billing)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert owned_files(billing) == {**before, INDEX: owned_files(billing)[INDEX]}  # 인덱스가 없었으므로 인덱스만 더해진다
    assert (billing / ".onto" / "Justfile").is_file()


def test_루트의_내용이_바뀌면_루트_관리_파일만_루트의_내용으로_바뀐다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing", files={**CONFIGURED, "README.md": "# billing\n"})
    assert sync(sandbox, root, "billing").returncode == 0
    owned = owned_files(billing)
    rules = root.work / "onto" / "rules.yaml"
    rules.write_text(rules.read_text(encoding="utf-8") + "# 루트에서 고쳤다\n", encoding="utf-8")

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert (billing / ".onto" / "rules.yaml").read_bytes() == rules.read_bytes()
    assert owned_files(billing) == owned  # 저장소 소유 파일은 그대로다. 시각도 바뀌지 않는다


def test_루트에서_없어진_루트_관리_파일은_지식_저장소에서도_지워지고_비게_된_디렉토리도_사라진다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    extra = root.work / "onto" / "extra" / "deep" / "tool.txt"
    extra.parent.mkdir(parents=True)
    extra.write_text("곧 없어질 파일\n", encoding="utf-8")
    sandbox.git("add", "onto/extra", cwd=root.work)
    assert sync(sandbox, root, "billing").returncode == 0
    assert (billing / ".onto" / "extra" / "deep" / "tool.txt").is_file()
    sandbox.git("rm", "-q", "-f", "onto/extra/deep/tool.txt", cwd=root.work)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert not (billing / ".onto" / "extra").exists()
    assert (billing / ".onto" / "Justfile").is_file()  # 나머지는 그대로다


def test_추적하지만_작업_트리에서_지운_루트_파일도_없어진_것으로_본다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    assert sync(sandbox, root, "billing").returncode == 0
    (root.work / "onto" / "README.md").unlink()  # `git rm`하지 않았다. 아직 추적하는 파일이다

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert not (billing / ".onto" / "README.md").exists()


def test_지식_저장소의_dot_onto에서_실행하며_생긴_가상환경_캐시_산출물은_지우지도_보고하지도_않는다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    assert sync(sandbox, root, "billing").returncode == 0
    made = {
        ".venv/bin/python": "가상환경\n",
        ".build/graph.ttl": "산출물\n",
        "onto_tool/__pycache__/cli.cpython-313.pyc": "캐시\n",
        "uv.cache": "캐시\n",
    }
    for relative, text in made.items():
        target = billing / ".onto" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    # 루트 관리 파일이 없어져도 그 디렉토리 안의 다른 파일이 남아 있으면 디렉토리를 지우지 않는다
    stray = root.work / "onto" / "onto_tool" / "extra.py"
    stray.write_text("# 곧 없어질 모듈\n", encoding="utf-8")
    sandbox.git("add", "onto/onto_tool/extra.py", cwd=root.work)
    assert sync(sandbox, root, "billing").returncode == 0
    sandbox.git("rm", "-q", "-f", "onto/onto_tool/extra.py", cwd=root.work)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert not (billing / ".onto" / "onto_tool" / "extra.py").exists()
    for relative, text in made.items():
        assert (billing / ".onto" / relative).read_text(encoding="utf-8") == text, relative
        assert relative not in result.stdout + result.stderr


# --- 손으로 고친 루트 관리 파일 ------------------------------------------------------------


def test_마지막_최신화_뒤에_손으로_고친_루트_관리_파일은_덮어쓰지_않고_보고한다_나머지는_최신화한다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    assert sync(sandbox, root, "billing").returncode == 0
    edited = billing / ".onto" / "rules.yaml"
    edited.write_text(edited.read_text(encoding="utf-8") + "# 내가 손으로 고친 줄\n", encoding="utf-8")
    mine = edited.read_bytes()
    for name in ("rules.yaml", "Justfile"):  # 루트가 두 파일을 고쳤다
        path = root.work / "onto" / name
        path.write_text(path.read_text(encoding="utf-8") + "# 루트에서 고쳤다\n", encoding="utf-8")

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1  # 최신화를 마치지 못했다
    assert edited.read_bytes() == mine  # 덮어쓰지 않았다
    assert (billing / ".onto" / "Justfile").read_bytes() == (root.work / "onto" / "Justfile").read_bytes()  # 나머지는 최신화했다
    assert re.search(r"건너뜀\s+\.onto/rules\.yaml\b.*손으로 고친", result.stdout)
    assert "billing" in result.stderr


def test_루트가_고치지_않은_파일도_손으로_고쳤으면_매번_보고하고_지우면_루트의_내용으로_되살린다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    assert sync(sandbox, root, "billing").returncode == 0
    edited = billing / ".onto" / "vocab" / "onto.ttl"
    edited.write_text("# 망가뜨렸다\n", encoding="utf-8")

    first = sync(sandbox, root, "billing")
    second = sync(sandbox, root, "billing")

    assert first.returncode == 1 and second.returncode == 1
    assert "vocab/onto.ttl" in second.stdout
    assert edited.read_text(encoding="utf-8") == "# 망가뜨렸다\n"
    edited.unlink()  # 보고를 받은 사람이 되돌리기로 했다
    third = sync(sandbox, root, "billing")
    assert third.returncode == 0, third.stdout + third.stderr
    assert edited.read_bytes() == (root.work / "onto" / "vocab" / "onto.ttl").read_bytes()


def test_루트에서_없어졌지만_손으로_고친_루트_관리_파일은_지우지_않고_보고한다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    extra = root.work / "onto" / "extra.txt"
    extra.write_text("원본\n", encoding="utf-8")
    sandbox.git("add", "onto/extra.txt", cwd=root.work)
    assert sync(sandbox, root, "billing").returncode == 0
    (billing / ".onto" / "extra.txt").write_text("내가 고쳤다\n", encoding="utf-8")
    sandbox.git("rm", "-q", "-f", "onto/extra.txt", cwd=root.work)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1
    assert (billing / ".onto" / "extra.txt").read_text(encoding="utf-8") == "내가 고쳤다\n"
    assert re.search(r"건너뜀\s+\.onto/extra\.txt\b.*루트에서는 없어졌지만", result.stdout)


def test_마지막_최신화의_기록이_없는데_루트의_내용과_다른_파일은_누가_고쳤는지_모르므로_덮어쓰지_않고_보고한다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    (billing / ".onto").mkdir()
    (billing / ".onto" / "rules.yaml").write_text("누가 만든 파일\n", encoding="utf-8")
    identical = billing / ".onto" / "README.md"
    identical.write_bytes((root.work / "onto" / "README.md").read_bytes())  # 루트와 같은 파일은 문제없다

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1
    assert (billing / ".onto" / "rules.yaml").read_text(encoding="utf-8") == "누가 만든 파일\n"
    assert re.search(r"건너뜀\s+\.onto/rules\.yaml\b.*기록이 없", result.stdout)
    assert not re.search(r"건너뜀\s+\.onto/README\.md", result.stdout)


# --- 대상과 결과 ------------------------------------------------------------------------


def test_이름을_생략하면_모든_지식_저장소를_최신화한다(sandbox):
    root = sandbox.root()
    subs = [attach(sandbox, root, name) for name in ("billing", "shop", "wiki")]

    result = sync(sandbox, root)

    assert result.returncode == 0, result.stderr
    for sub in subs:
        assert (sub / ".onto" / "Justfile").is_file() and (sub / YAML).is_file(), sub.name
    assert project_names(sandbox, root) == ["billing", "shop", "wiki"]


def test_이름을_주면_그_지식_저장소만_최신화한다(sandbox):
    root = sandbox.root()
    billing, shop = attach(sandbox, root, "billing"), attach(sandbox, root, "shop")
    shop_before = sandbox.snapshot(shop)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert (billing / ".onto").is_dir()
    assert sandbox.snapshot(shop) == shop_before and not (shop / ".onto").exists()


def test_없는_이름을_주면_있는_저장소를_알리고_아무것도_바꾸지_않는다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    before = sandbox.snapshot(billing)

    result = sync(sandbox, root, "nothing")

    assert result.returncode == 1
    assert "nothing" in result.stderr and "billing" in result.stderr
    assert sandbox.snapshot(billing) == before


def test_지식_저장소가_하나도_없어도_sync는_오류_없이_끝난다(sandbox):
    root = sandbox.root()

    result = sync(sandbox, root)

    assert result.returncode == 0, result.stderr
    assert "지식 저장소가 없다" in result.stdout


def tree(billing: Path) -> dict[str, tuple[bytes, int]]:
    """지식 저장소 작업 트리의 모든 파일(`.git` 제외)의 내용과 수정 시각."""
    return {
        path.relative_to(billing).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(billing.rglob("*"))
        if path.is_file() and path.relative_to(billing).parts[0] != ".git"
    }


def test_두_번_연속_실행하면_두_번째는_아무_파일도_바꾸지_않는다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    assert sync(sandbox, root, "billing").returncode == 0
    for path in billing.rglob("*"):  # 다시 쓰면 바뀔 수정 시각을 먼 과거로 돌려 둔다
        if path.is_file() and path.relative_to(billing).parts[0] != ".git":
            os.utime(path, ns=(1_000_000_000, 1_000_000_000))
    before = tree(billing)
    snapshot = sandbox.snapshot(billing)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert tree(billing) == before
    assert sandbox.snapshot(billing) == snapshot
    assert "바뀐 것이 없다" in result.stdout


def test_끝에_저장소별로_만든_파일_바꾼_파일_건너뛴_파일을_요약한다(sandbox):
    root = sandbox.root()
    attach(sandbox, root, "billing"), attach(sandbox, root, "shop")
    first = sync(sandbox, root)
    tracked = tracked_onto_files(sandbox, root)
    skills = sandbox.git("ls-files", "-z", ".claude/skills", cwd=root.work).stdout.split("\0")
    skills = [path for path in skills if path.startswith(".claude/skills/onto-")]
    assert len(skills) >= 3  # 스킬 세 개
    created = len(tracked) + len(skills) + 4  # .onto/ 아래 복사본(기록은 세지 않는다)과 스킬 사본, .gitignore, AGENTS.md(지침 파일), ontology.yaml, 인덱스

    assert f"billing: 만든 파일 {created}개, 바꾼 파일 0개, 지운 파일 0개, 건너뛴 파일 0개" in first.stdout
    assert f"shop: 만든 파일 {created}개" in first.stdout
    for line in (".gitignore", "AGENTS.md", YAML, INDEX):
        assert f"만듦  {line}" in first.stdout
    assert first.stdout.rstrip().splitlines()[-1].startswith("최신화: 지식 저장소 2개")  # 끝에 전체 요약

    # 한 저장소는 루트 관리 파일을 루트가 고쳐 바뀌고, 다른 저장소는 손으로 고친 파일이 있어 건너뛴다
    rules = root.work / "onto" / "rules.yaml"
    rules.write_text(rules.read_text(encoding="utf-8") + "# 루트에서 고쳤다\n", encoding="utf-8")
    (root.work / "projects" / "shop" / ".onto" / "rules.yaml").write_text("손으로 고쳤다\n", encoding="utf-8")
    second = sync(sandbox, root)

    assert "billing: 만든 파일 0개, 바꾼 파일 1개, 지운 파일 0개, 건너뛴 파일 0개" in second.stdout
    assert "바꿈  .onto/rules.yaml" in second.stdout
    assert "shop: 만든 파일 0개, 바꾼 파일 0개, 지운 파일 0개, 건너뛴 파일 1개" in second.stdout
    assert second.returncode == 1  # shop을 마치지 못했다
    assert second.stdout.rstrip().splitlines()[-1] == "최신화: 지식 저장소 2개, 만든 파일 0개, 바꾼 파일 1개, 지운 파일 0개, 건너뛴 파일 1개"


# --- 인덱스 ------------------------------------------------------------------------------


def validate(sandbox, root):
    return sandbox.just("onto", "validate", cwd=root.work)


def test_새로_구성한_지식_저장소의_최신화_직후에_스크립트_검사가_오류_없이_통과한다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")

    assert sync(sandbox, root, "billing").returncode == 0

    assert (billing / INDEX).is_file()
    result = validate(sandbox, root)
    assert result.returncode == 0, result.stdout
    assert result.stdout == ""


def test_구성은_있지만_인덱스가_없는_지식_저장소에도_인덱스를_만들어_검사를_통과시킨다(sandbox):
    """인덱스가 없는 것은 `index-mismatch`다. 최신화 직후의 저장소가 검사를 통과하려면 새 저장소만이 아니라 인덱스가 없는 모든 저장소에 만든다."""
    root = sandbox.root()
    billing = attach(sandbox, root, "billing", files=CONFIGURED)
    assert validate(sandbox, root).returncode == 1  # 최신화 전에는 인덱스가 없어 오류다

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    index = (billing / INDEX).read_text(encoding="utf-8")
    assert "결제 게이트웨이" in index and "출시 계획" in index
    check = validate(sandbox, root)
    assert check.returncode == 0, check.stdout


def test_이미_있는_인덱스는_어긋나도_고치지_않는다(sandbox):
    """인덱스는 생성물이지만 커밋하는 저장소 소유 파일이다. 어긋남은 스크립트 검사가 알리고 `build`가 고친다."""
    root = sandbox.root()
    stale = "# 손으로 쓴 옛 인덱스\n"
    billing = attach(sandbox, root, "billing", files={**CONFIGURED, INDEX: stale})

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert (billing / INDEX).read_text(encoding="utf-8") == stale
    assert "index-mismatch" in validate(sandbox, root).stdout


def test_읽을_수_없는_페이지가_있는_저장소는_인덱스를_만들지_못했다고_보고하고_나머지는_최신화한다(sandbox):
    root = sandbox.root()
    broken = {**CONFIGURED, f"{ONTOLOGY_DIR}/plan/broken.md": "frontmatter가 없다\n"}
    billing = attach(sandbox, root, "billing", files=broken)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1
    assert not (billing / INDEX).exists()
    assert re.search(r"건너뜀\s+docs/ontology/index\.md\b.*plan/broken\.md", result.stdout)
    assert (billing / ".onto" / "Justfile").is_file()


def test_다른_지식_저장소의_문제는_이_저장소의_인덱스를_막지_않는다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing", files=CONFIGURED)
    attach(sandbox, root, "shop", files={**repo("shop"), f"{ONTOLOGY_DIR}/plan/broken.md": "frontmatter가 없다\n"})

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert (billing / INDEX).is_file()


# --- 저장소의 상태와 안전 ---------------------------------------------------------------------


def test_초기화되지_않은_서브모듈은_건너뛰고_보고한다_빈_디렉토리를_채우지_않는다(sandbox):
    root = sandbox.root()
    attach(sandbox, root, "billing")
    clone = root.clone()  # 서브모듈을 초기화하지 않은 새 클론이다
    before = sorted(p.name for p in (clone / "projects" / "billing").iterdir())

    result = sync(sandbox, root, "billing", cwd=clone)

    assert result.returncode == 1
    assert re.search(r"건너뜀\s+projects/billing\b.*초기화", result.stdout)
    assert sorted(p.name for p in (clone / "projects" / "billing").iterdir()) == before == []  # git submodule update가 막히지 않는다


def test_dot_onto가_심볼릭_링크이면_따라가지_않고_밖에_아무것도_쓰지_않는다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    outside = sandbox.new_dir("elsewhere", "outside")
    (billing / ".onto").symlink_to(outside)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1
    assert list(outside.iterdir()) == []
    assert len(re.findall(r"^  건너뜀", result.stdout, re.MULTILINE)) == 1  # 파일마다 알리지 않고 한 번만 알린다
    assert re.search(r"건너뜀\s+\.onto/\s+—\s+`\.onto`가 심볼릭 링크", result.stdout)


def test_docs가_심볼릭_링크이면_따라가지_않고_밖에_ontology_yaml을_만들지_않는다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing", files={"README.md": "# billing\n"})  # docs/가 없다
    outside = sandbox.new_dir("elsewhere", "docs")
    (billing / "docs").symlink_to(outside)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1
    assert list(outside.iterdir()) == []
    assert "심볼릭 링크" in result.stdout


def test_지식_저장소의_Justfile은_만들지도_고치지도_않는다(sandbox):
    root = sandbox.root()
    team = "default:\n\t@echo 팀의 Justfile\n"
    without = attach(sandbox, root, "billing")
    with_justfile = attach(sandbox, root, "shop", files={"README.md": "# shop\n", "Justfile": team, "justfile": team})

    result = sync(sandbox, root)

    assert result.returncode == 0, result.stderr
    assert not any((without / name).exists() for name in ("Justfile", "justfile", ".justfile"))
    assert (with_justfile / "Justfile").read_text(encoding="utf-8") == team
    assert (with_justfile / "justfile").read_text(encoding="utf-8") == team


def test_sync는_루트_저장소를_바꾸지_않는다_커밋도_스테이징도_하지_않는다(sandbox):
    root = sandbox.root()
    attach(sandbox, root, "billing")
    head = sandbox.head(root.work)
    status = sandbox.git("status", "--porcelain", "--ignore-submodules=all", cwd=root.work).stdout

    assert sync(sandbox, root, "billing").returncode == 0

    assert sandbox.head(root.work) == head
    assert sandbox.git("diff", "--cached", "--name-only", cwd=root.work).stdout == ""
    assert sandbox.git("status", "--porcelain", "--ignore-submodules=all", cwd=root.work).stdout == status


def test_지식_저장소_안의_dot_onto에서는_sync를_거부한다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    assert sync(sandbox, root, "billing").returncode == 0
    before = tree(billing)

    result = sandbox.just("-f", ".onto/Justfile", "sync", cwd=billing)

    assert result.returncode == 1
    assert "루트 저장소에서만" in result.stderr
    # 도구를 돌리느라 `.onto/`에 생긴 가상환경과 캐시는 빼고 비교한다
    after = {path: value for path, value in tree(billing).items() if ".venv" not in path.split("/") and "__pycache__" not in path.split("/")}
    assert after == before


def test_복사된_dot_onto는_그_자리에서_돈다(sandbox):
    """도구와 잠금 파일, 규칙이 함께 복사되어 지식 저장소 안에서 `.onto/Justfile`을 직접 가리켜 실행할 수 있다."""
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    assert sync(sandbox, root, "billing").returncode == 0

    result = sandbox.just("-f", ".onto/Justfile", "rules", cwd=billing)

    assert result.returncode == 0, result.stderr
    assert '"push-gate"' in result.stdout  # 복사된 `.onto/rules.yaml`이 그 저장소의 기본 규칙이다


def test_루트에서_실행_권한이_있는_파일은_지식_저장소에서도_실행할_수_있다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    script = root.work / "onto" / "run.sh"
    script.write_text("#!/bin/sh\necho 실행\n", encoding="utf-8")
    sandbox.git("add", "onto/run.sh", cwd=root.work)
    sandbox.git("update-index", "--chmod=+x", "onto/run.sh", cwd=root.work)

    assert sync(sandbox, root, "billing").returncode == 0

    copied = billing / ".onto" / "run.sh"
    assert os.access(copied, os.X_OK)
    assert not os.access(billing / ".onto" / "README.md", os.X_OK)


def test_루트의_onto에_심볼릭_링크가_추적되어_있으면_복사하지_않고_멈춘다(sandbox):
    """링크의 대상이 `onto/` 밖일 수 있다. 어느 지식 저장소에도 아무것도 쓰기 전에 알린다."""
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    (root.work / "onto" / "link").symlink_to("Justfile")
    sandbox.git("add", "onto/link", cwd=root.work)
    before = sandbox.snapshot(billing)

    result = sync(sandbox, root)

    assert result.returncode == 1
    assert "onto/link" in result.stderr and "심볼릭 링크" in result.stderr
    assert sandbox.snapshot(billing) == before


@pytest.mark.parametrize("directory", ["no", "123", "my repo", "a: b"], ids=["YAML_불리언", "숫자", "공백", "콜론과_공백"])
def test_디렉토리_이름이_YAML에서_다른_값으로_읽히는_모양이어도_name은_디렉토리_이름_그대로다(sandbox, directory):
    root = sandbox.root()
    attach(sandbox, root, "billing", directory=directory)

    result = sync(sandbox, root, directory)

    assert result.returncode == 0, result.stderr
    assert project_names(sandbox, root) == [directory]


# --- 리뷰 지적 -------------------------------------------------------------------------------


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def test_기록에_dot_onto_밖이나_상위로_나가는_절대_경로가_있어도_그_경로의_파일을_지우지_않는다(sandbox):
    """기록은 지식 저장소 안의 파일이라 믿지 않는다. 바른 지문을 함께 적어 놓아도 `.onto/` 밖의 경로는 버린다."""
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    outside = sandbox.new_dir("elsewhere", "victim") / "keep.txt"
    outside.write_text("밖의 파일\n", encoding="utf-8")
    readme = billing / "README.md"
    victims = {
        "../README.md": sha256(readme.read_text(encoding="utf-8")),
        ".onto/../README.md": sha256(readme.read_text(encoding="utf-8")),
        "README.md": sha256(readme.read_text(encoding="utf-8")),
        str(outside): sha256("밖의 파일\n"),
        ".onto/../../victim/keep.txt": sha256("밖의 파일\n"),
    }
    (billing / ".onto").mkdir()
    (billing / ".onto" / RECORD_NAME).write_text(json.dumps(victims), encoding="utf-8")
    before = readme.read_bytes()

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert readme.read_bytes() == before
    assert outside.read_text(encoding="utf-8") == "밖의 파일\n"
    assert (billing / ".onto" / "Justfile").is_file()  # 나머지는 정상으로 최신화한다


def test_인덱스_경로가_심볼릭_링크이면_따라가지_않고_건너뛴다(sandbox):
    root = sandbox.root()
    outside = sandbox.new_dir("elsewhere", "index-target") / "index.md"
    outside.write_text("밖의 파일\n", encoding="utf-8")
    billing = attach(sandbox, root, "billing", files=CONFIGURED)
    (billing / INDEX).symlink_to(outside)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1
    assert outside.read_text(encoding="utf-8") == "밖의 파일\n"
    assert re.search(r"건너뜀\s+docs/ontology/index\.md\b.*심볼릭 링크", result.stdout)
    assert (billing / ".onto" / "Justfile").is_file()


@pytest.mark.parametrize("direction", ["파일이_디렉토리로", "디렉토리가_파일로"])
def test_루트에서_파일이_디렉토리로_또는_반대로_바뀌어도_한_번의_실행으로_끝난다(sandbox, direction):
    """옛 경로가 새 경로를 막고 있으므로 지우기가 복사보다 먼저여야 한다."""
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    extra = root.work / "onto" / "extra"
    if direction == "파일이_디렉토리로":
        extra.write_text("파일이었다\n", encoding="utf-8")
    else:
        extra.mkdir()
        (extra / "x.txt").write_text("디렉토리였다\n", encoding="utf-8")
    sandbox.git("add", "onto/extra", cwd=root.work)
    assert sync(sandbox, root, "billing").returncode == 0
    sandbox.git("rm", "-r", "-q", "-f", "onto/extra", cwd=root.work)
    if direction == "파일이_디렉토리로":
        extra.mkdir()
        (extra / "x.txt").write_text("이제 디렉토리다\n", encoding="utf-8")
    else:
        extra.write_text("이제 파일이다\n", encoding="utf-8")
    sandbox.git("add", "onto/extra", cwd=root.work)

    first = sync(sandbox, root, "billing")
    second = sync(sandbox, root, "billing")

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0 and "바뀐 것이 없다" in second.stdout
    if direction == "파일이_디렉토리로":
        assert (billing / ".onto" / "extra" / "x.txt").read_text(encoding="utf-8") == "이제 디렉토리다\n"
    else:
        assert (billing / ".onto" / "extra").read_text(encoding="utf-8") == "이제 파일이다\n"


def test_루트의_onto에_추적하지_않는_파일이_있으면_복사하지_않고_경고한다_동작은_바꾸지_않는다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    clean = sync(sandbox, root, "billing")
    assert clean.returncode == 0 and clean.stderr == ""  # 가상환경과 캐시는 무시되는 파일이라 경고하지 않는다
    for name in ("new_module.py", "notes.txt"):
        (root.work / "onto" / name).write_text("아직 git add하지 않았다\n", encoding="utf-8")

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0
    assert "추적하지 않는 파일" in result.stderr and "onto/new_module.py" in result.stderr and "onto/notes.txt" in result.stderr
    assert "git add" in result.stderr
    assert not (billing / ".onto" / "new_module.py").exists()  # 복사하지 않는다(스펙대로 추적하는 파일만)


def test_지식_저장소가_dot_onto를_이미_추적하고_있으면_추적에서_빼라고_알린다(sandbox):
    """`.gitignore`는 추적하는 파일을 제외하지 못해, 블록을 되살려도 `.onto/`의 변경이 git 상태에 남는다."""
    root = sandbox.root()
    billing = attach(sandbox, root, "billing", files={"README.md": "# billing\n", ".onto/stray.txt": "누가 커밋했다\n"})
    assert sandbox.git("ls-files", ".onto", cwd=billing).stdout.strip() == ".onto/stray.txt"

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1  # git 상태가 계속 오염되므로 사람이 확인해야 한다
    assert re.search(r"확인 필요\s+\.onto/\s+—.*이미 추적.*git rm -r --cached \.onto", result.stdout)
    assert "건너뜀" not in result.stdout  # 아무것도 건너뛰지 않았다: 복사는 끝까지 했다
    assert "건너뛴 파일 0개, 확인할 것 1개" in result.stdout
    assert (billing / ".onto" / "Justfile").is_file()  # 최신화는 계속한다
    assert (billing / ".onto" / "stray.txt").read_text(encoding="utf-8") == "누가 커밋했다\n"  # 추적하는 파일은 건드리지 않는다
    assert "billing" in result.stderr and "확인" in result.stderr


def test_같은_이유로_건너뛴_루트_관리_파일이_많으면_위치별로_묶어_한_줄로_알린다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    assert sync(sandbox, root, "billing").returncode == 0
    outside = sandbox.new_dir("elsewhere", "tool")
    shutil.rmtree(billing / ".onto" / "onto_tool")
    (billing / ".onto" / "onto_tool").symlink_to(outside)  # 도구 디렉토리 통째로 링크다. 그 아래 수십 개 파일이 막힌다

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1
    assert len(re.findall(r"^  건너뜀", result.stdout, re.MULTILINE)) == 1
    assert re.search(r"건너뜀\s+\.onto/ 아래 파일 \d+개\s+—.*심볼릭 링크", result.stdout)
    assert list(outside.iterdir()) == []


def test_손으로_고친_루트_관리_파일이_많아도_파일마다_이유와_함께_하나씩_알린다(sandbox):
    """같은 위치가 막은 파일(링크)과 달리, 손으로 고친 파일은 하나하나가 사람이 챙길 파일이다. 지우면 손수정이 흔적 없이 사라진다."""
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    assert sync(sandbox, root, "billing").returncode == 0
    edited = sorted((billing / ".onto" / "onto_tool").glob("*.py"))[:12]
    assert len(edited) == 12
    for path in edited:
        path.write_text(path.read_text(encoding="utf-8") + "# 내가 손으로 고친 줄\n", encoding="utf-8")

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1
    reported = re.findall(r"^  건너뜀\s+(\S+)\s+—\s+(.*)$", result.stdout, re.MULTILINE)
    assert sorted(path for path, _ in reported) == sorted(f".onto/onto_tool/{p.name}" for p in edited)  # 파일 이름이 하나도 빠지지 않는다
    assert all("손으로 고친" in reason for _, reason in reported)  # 이유가 파일마다 붙는다
    assert "건너뛴 파일 12개" in result.stdout


def test_손으로_고친_파일과_링크가_막은_파일이_함께_있으면_링크가_막은_파일만_묶는다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    assert sync(sandbox, root, "billing").returncode == 0
    (billing / ".onto" / "rules.yaml").write_text("손으로 고쳤다\n", encoding="utf-8")
    outside = sandbox.new_dir("elsewhere", "tool")
    shutil.rmtree(billing / ".onto" / "onto_tool")
    (billing / ".onto" / "onto_tool").symlink_to(outside)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1
    assert len(re.findall(r"^  건너뜀", result.stdout, re.MULTILINE)) == 2
    assert re.search(r"건너뜀\s+\.onto/rules\.yaml\s+—.*손으로 고친", result.stdout)
    assert re.search(r"건너뜀\s+\.onto/ 아래 파일 \d+개\s+—.*심볼릭 링크", result.stdout)


def run_with_git_variables(sandbox, root, **variables: str):
    """사용자의 셸이나 git 훅이 물려주는 `GIT_*` 환경 변수를 둔 채 `just onto sync billing`을 실행한다."""
    just = shutil.which("just")
    return sandbox.run([just, "onto", "sync", "billing"], cwd=root.work, check=False, env={**sandbox.env, **variables})


def test_git_인덱스_파일을_가리키는_환경_변수가_있어도_루트가_추적하는_파일을_복사한다(sandbox):
    """git 훅 안처럼 `GIT_INDEX_FILE`이 설정된 환경에서 `git ls-files`는 그 인덱스를 읽는다. 최신화는 루트 저장소의 인덱스를 읽어야 한다."""
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    elsewhere = sandbox.new_dir("elsewhere", "hook") / "index"  # 없는 인덱스 파일: git은 빈 인덱스로 읽는다

    result = run_with_git_variables(sandbox, root, GIT_INDEX_FILE=str(elsewhere))

    assert result.returncode == 0, result.stdout + result.stderr
    assert sorted(files_under(billing / ".onto")) == sorted([*tracked_onto_files(sandbox, root), RECORD_NAME])
    assert not elsewhere.exists()  # 그 인덱스를 쓰지도 않았다


def test_git_저장소를_가리키는_환경_변수가_있어도_지식_저장소가_dot_onto를_추적하는지는_그_저장소에서_본다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing", files={"README.md": "# billing\n", ".onto/stray.txt": "누가 커밋했다\n"})
    other = sandbox.new_dir("elsewhere", "other")
    sandbox.git("init", "--initial-branch=main", cwd=other)  # `.onto/`를 추적하지 않는 다른 저장소

    result = run_with_git_variables(sandbox, root, GIT_DIR=str(other / ".git"))

    assert result.returncode == 1
    assert re.search(r"확인 필요\s+\.onto/\s+—.*이미 추적", result.stdout)
    assert (billing / ".onto" / "Justfile").is_file()


def test_루트_저장소가_아니면_상위_디렉토리의_다른_저장소를_찾아_복사하지_않는다(sandbox):
    """루트 저장소의 `.git`이 없어도 `git`은 위로 올라가 다른 저장소를 찾는다. 위 저장소가 `onto/`를 추적해도 그것을 루트의 기능으로 삼지 않는다."""
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    parent = root.work.parent
    shutil.rmtree(root.work / ".git")
    sandbox.git("init", "--initial-branch=main", cwd=parent)
    sandbox.git("add", "-A", cwd=parent)
    assert sandbox.git("ls-files", "root/onto/Justfile", cwd=parent).stdout.strip()  # 위 저장소가 `onto/`를 추적한다

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1
    assert "추적하는 파일을 알 수 없다" in result.stderr
    assert not (billing / ".onto").exists()


def test_출력을_한_파이프로_모아도_전체_요약이_오류_줄보다_먼저_나온다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, "billing")
    assert sync(sandbox, root, "billing").returncode == 0
    (billing / ".onto" / "rules.yaml").write_text("손으로 고쳤다\n", encoding="utf-8")

    result = sandbox.run(["sh", "-c", f"{shutil.which('just')} onto sync billing 2>&1"], cwd=root.work, check=False)

    lines = result.stdout.splitlines()
    summary = next(number for number, line in enumerate(lines) if line.startswith("최신화: 지식 저장소"))
    error = next(number for number, line in enumerate(lines) if line.startswith("오류:"))
    assert summary < error


def test_인덱스는_build와_같은_기준으로_만든다_규칙에서_꺼진_읽기_문제의_파일은_건너뛰고_만든다(sandbox):
    """`build`는 실효 심각도가 오류인 읽기 문제에서만 멈춘다. 최신화가 `build`가 만드는 인덱스를 못 만든다고 하지 않는다."""
    root = sandbox.root()
    files = repo(
        "billing",
        page("plan/launch", "Plan", title="출시 계획", about="project"),
        {f"{ONTOLOGY_DIR}/plan/broken.md": "frontmatter가 없다\n"},
        rules={"checks": {"unreadable-file": {"enabled": False}}},
    )
    billing = attach(sandbox, root, "billing", files=files)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stdout + result.stderr
    index = (billing / INDEX).read_text(encoding="utf-8")
    assert "출시 계획" in index and "broken" not in index  # 읽을 수 없는 페이지는 싣지 않는다
    check = validate(sandbox, root)
    assert check.returncode == 0, check.stdout  # `build`와 `validate`가 보는 인덱스와 같다
