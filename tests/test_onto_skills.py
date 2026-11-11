"""에이전트 스킬 사본: 최신화(`just onto sync`)가 루트의 `.claude/skills/onto-*/`를 지식 저장소의 같은 위치로 복사한다.

가장 높은 이음매다. 루트 저장소(`sandbox.root()`)는 이 저장소의 추적 파일을 복사한 것이라 스킬 세 개(`onto-ingest`, `onto-query`, `onto-lint`)가 들어 있고,
지식 저장소는 로컬 bare 원격을 서브모듈로 붙인 것이다. 스킬 문서의 내용은 LLM이 읽는 글이라 자동 테스트에서 뺀다(스펙의 "테스트 결정").
여기서 보는 것은 스킬이 지식 저장소로 복사되고, 지식 저장소의 커밋에 들어가지 않고, 손으로 고친 사본과 팀의 스킬이 보호되고,
루트에서 없앤 스킬이 지식 저장소에서도 지워지는 동작이다. 스킬 사본은 `.onto/`와 같은 루트 관리 파일이고 마지막 최신화의 기록(`.onto/.sync-record.json`)으로 관리한다.
"""

import hashlib
import json
import re
from pathlib import Path

from support.onto_cli import ONTOLOGY_DIR, page, parse_table, repo

SKILLS = ("onto-ingest", "onto-query", "onto-lint")
SKILL_ROOT = ".claude/skills"
RECORD = ".onto/.sync-record.json"
CHECK = "outdated-managed-files"
TEAM_SKILL = f"{SKILL_ROOT}/review/SKILL.md"
TEAM_TEXT = "---\nname: review\ndescription: 팀의 리뷰 스킬\n---\n\n팀이 쓴 스킬이다.\n"


def attach(sandbox, root, name: str = "billing", *, files: dict[str, str] | None = None) -> Path:
    root.register(sandbox.knowledge_remote(name, files=files))
    return root.work / "projects" / name


def sync(sandbox, root, *args: str):
    return sandbox.just("onto", "sync", *args, cwd=root.work)


def skill_files(directory: Path) -> dict[str, bytes]:
    """`directory`(`.claude/skills`) 아래 모든 일반 파일의 상대 경로와 내용."""
    if not directory.is_dir():
        return {}
    return {path.relative_to(directory).as_posix(): path.read_bytes() for path in sorted(directory.rglob("*")) if path.is_file()}


def tracked_onto_skills(sandbox, root) -> dict[str, bytes]:
    """루트 저장소가 추적하는 `.claude/skills/onto-*/`의 파일. `.claude/skills/`를 뗀 경로와 내용."""
    listing = sandbox.git("ls-files", "-z", SKILL_ROOT, cwd=root.work).stdout
    found = {}
    for path in filter(None, listing.split("\0")):
        relative = path.removeprefix(f"{SKILL_ROOT}/")
        if relative.startswith("onto-"):
            found[relative] = (root.work / path).read_bytes()
    return found


def fingerprint(content: bytes) -> str:
    """`.sync-record.json`이 적는 지문. 일반 파일은 내용의 sha256이고 실행 파일만 `x`가 붙는다."""
    return hashlib.sha256(content).hexdigest()


# --- 복사 -------------------------------------------------------------------------------


def test_최신화가_스킬_세_개를_지식_저장소의_dot_claude_skills로_복사한다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root)
    expected = tracked_onto_skills(sandbox, root)
    assert {name.split("/")[0] for name in expected} == set(SKILLS)  # 루트에 스킬 세 개가 있다

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert skill_files(billing / SKILL_ROOT) == expected  # 내용까지 루트와 같고 그 밖의 파일은 없다
    for name in SKILLS:
        assert (billing / SKILL_ROOT / name / "SKILL.md").is_file()


def test_복사한_스킬은_지식_저장소의_git_상태에_나타나지_않고_저장소의_스킬은_제외하지_않는다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, files={"README.md": "# billing\n", TEAM_SKILL: TEAM_TEXT})

    assert sync(sandbox, root, "billing").returncode == 0

    status = sandbox.git("status", "--porcelain", "--untracked-files=all", cwd=billing).stdout
    assert ".claude" not in status  # 복사한 스킬은 `.gitignore`가 제외하고, 저장소가 추적하는 스킬은 그대로다
    ignored = lambda path: sandbox.git("check-ignore", "--quiet", path, cwd=billing, check=False).returncode == 0  # noqa: E731
    assert all(ignored(f"{SKILL_ROOT}/{name}/SKILL.md") for name in SKILLS)
    assert not ignored(TEAM_SKILL)


def test_루트의_onto로_시작하지_않는_스킬과_에이전트_설정은_복사하지_않는다(sandbox):
    """루트 저장소 자신의 작업용 스킬(`onto-`로 시작하지 않는 것)과 `.claude/agents/`, `.claude/settings.json`은 지식 저장소와 무관하다."""
    root = sandbox.root()
    root.commit({f"{SKILL_ROOT}/root-only/SKILL.md": "루트의 작업용 스킬\n", f"{SKILL_ROOT}/onto-extra/SKILL.md": "추가 스킬\n"})
    billing = attach(sandbox, root)
    assert (root.work / ".claude" / "agents").is_dir() and (root.work / ".claude" / "settings.json").is_file()

    assert sync(sandbox, root, "billing").returncode == 0

    assert sorted(path.name for path in (billing / SKILL_ROOT).iterdir()) == sorted([*SKILLS, "onto-extra"])
    assert not (billing / ".claude" / "agents").exists() and not (billing / ".claude" / "settings.json").exists()


def test_스킬이_들어간_뒤에도_두_번째_최신화는_아무_파일도_바꾸지_않는다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root)
    assert sync(sandbox, root, "billing").returncode == 0
    before = skill_files(billing / SKILL_ROOT)

    second = sync(sandbox, root, "billing")

    assert second.returncode == 0 and "billing: 바뀐 것이 없다" in second.stdout
    assert skill_files(billing / SKILL_ROOT) == before


def test_루트가_스킬을_고치면_다음_최신화가_지식_저장소의_사본을_고친다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root)
    assert sync(sandbox, root, "billing").returncode == 0
    target = root.work / SKILL_ROOT / "onto-query" / "SKILL.md"
    target.write_text(target.read_text(encoding="utf-8") + "\n새로 덧붙인 안내\n", encoding="utf-8")
    sandbox.git("add", str(target.relative_to(root.work)), cwd=root.work)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert (billing / SKILL_ROOT / "onto-query" / "SKILL.md").read_text(encoding="utf-8").endswith("새로 덧붙인 안내\n")
    assert re.search(rf"바꿈\s+{re.escape(SKILL_ROOT)}/onto-query/SKILL\.md", result.stdout)


def test_스킬에_딸린_파일과_하위_디렉토리도_복사한다(sandbox):
    root = sandbox.root()
    root.commit({f"{SKILL_ROOT}/onto-query/examples/queries.md": "예\n", f"{SKILL_ROOT}/onto-query/refs/a/b.txt": "깊은 파일\n"})
    billing = attach(sandbox, root)

    assert sync(sandbox, root, "billing").returncode == 0

    assert (billing / SKILL_ROOT / "onto-query" / "examples" / "queries.md").read_text(encoding="utf-8") == "예\n"
    assert (billing / SKILL_ROOT / "onto-query" / "refs" / "a" / "b.txt").read_text(encoding="utf-8") == "깊은 파일\n"


# --- 지식 저장소의 팀 스킬은 건드리지 않는다 ----------------------------------------------------------


def test_지식_저장소의_팀_스킬은_복사와_두_번째_최신화에서도_한_글자도_바뀌지_않는다(sandbox):
    other = f"{SKILL_ROOT}/review/checklist.md"
    custom = f"{SKILL_ROOT}/onto-custom/SKILL.md"  # `onto-`로 시작하지만 루트가 모르는 스킬이다
    root = sandbox.root()
    billing = attach(sandbox, root, files={"README.md": "# billing\n", TEAM_SKILL: TEAM_TEXT, other: "점검표\n"})
    (billing / custom).parent.mkdir(parents=True)
    (billing / custom).write_text("누가 손으로 만든 스킬\n", encoding="utf-8")

    first = sync(sandbox, root, "billing")
    second = sync(sandbox, root, "billing")

    assert first.returncode == 0 and second.returncode == 0, first.stderr + second.stderr
    assert (billing / TEAM_SKILL).read_text(encoding="utf-8") == TEAM_TEXT
    assert (billing / other).read_text(encoding="utf-8") == "점검표\n"
    assert (billing / custom).read_text(encoding="utf-8") == "누가 손으로 만든 스킬\n"  # 루트가 두지 않은 스킬은 이름이 같은 묶음이어도 그대로다
    assert "review" not in first.stdout and "onto-custom" not in first.stdout  # 보고에도 나오지 않는다
    assert sandbox.git("status", "--porcelain", "--untracked-files=all", "--", SKILL_ROOT + "/review", cwd=billing).stdout == ""


# --- 루트에서 없앤 스킬 ---------------------------------------------------------------------------


def test_루트에서_없앤_스킬은_다음_최신화가_지식_저장소에서도_지우고_비게_된_디렉토리도_없앤다(sandbox):
    root = sandbox.root()
    root.commit({f"{SKILL_ROOT}/onto-extra/SKILL.md": "추가 스킬\n", f"{SKILL_ROOT}/onto-extra/refs/a.md": "참고\n"})
    billing = attach(sandbox, root, files={"README.md": "# billing\n", TEAM_SKILL: TEAM_TEXT})
    assert sync(sandbox, root, "billing").returncode == 0
    assert (billing / SKILL_ROOT / "onto-extra" / "refs" / "a.md").is_file()
    sandbox.git("rm", "-r", "-q", f"{SKILL_ROOT}/onto-extra", cwd=root.work)  # 루트에서 없앴다

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert not (billing / SKILL_ROOT / "onto-extra").exists()  # 파일과 비게 된 디렉토리가 모두 사라진다
    assert re.search(rf"지움\s+{re.escape(SKILL_ROOT)}/onto-extra/SKILL\.md", result.stdout)
    assert sorted(path.name for path in (billing / SKILL_ROOT).iterdir()) == sorted(["review", *SKILLS])  # 나머지 스킬과 팀 스킬은 그대로다
    assert (billing / TEAM_SKILL).read_text(encoding="utf-8") == TEAM_TEXT


def test_루트에서_모든_스킬을_없애도_팀_스킬이_든_디렉토리는_남는다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, files={"README.md": "# billing\n", TEAM_SKILL: TEAM_TEXT})
    assert sync(sandbox, root, "billing").returncode == 0
    for name in SKILLS:
        sandbox.git("rm", "-r", "-q", f"{SKILL_ROOT}/{name}", cwd=root.work)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert [path.name for path in (billing / SKILL_ROOT).iterdir()] == ["review"]
    assert (billing / TEAM_SKILL).read_text(encoding="utf-8") == TEAM_TEXT


def test_저장소에_스킬이_하나도_없었으면_모두_지운_뒤_비게_된_dot_claude도_없앤다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root)
    assert sync(sandbox, root, "billing").returncode == 0
    for name in SKILLS:
        sandbox.git("rm", "-r", "-q", f"{SKILL_ROOT}/{name}", cwd=root.work)

    assert sync(sandbox, root, "billing").returncode == 0

    assert not (billing / ".claude").exists()


def test_루트에서_없앴지만_손으로_고친_스킬_사본은_지우지_않고_보고한다(sandbox):
    root = sandbox.root()
    root.commit({f"{SKILL_ROOT}/onto-extra/SKILL.md": "추가 스킬\n"})
    billing = attach(sandbox, root)
    assert sync(sandbox, root, "billing").returncode == 0
    copy = billing / SKILL_ROOT / "onto-extra" / "SKILL.md"
    copy.write_text("내가 손으로 고쳤다\n", encoding="utf-8")
    sandbox.git("rm", "-r", "-q", f"{SKILL_ROOT}/onto-extra", cwd=root.work)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1
    assert re.search(rf"건너뜀\s+{re.escape(SKILL_ROOT)}/onto-extra/SKILL\.md\s+—.*손으로 고친", result.stdout)
    assert copy.read_text(encoding="utf-8") == "내가 손으로 고쳤다\n"


def test_기록이_스킬이_아닌_파일이나_스킬_디렉토리_밖을_가리켜도_지우지_않는다(sandbox):
    """기록은 지식 저장소 안의 파일이라 믿지 않는다. 팀의 스킬 파일이 기록에 적혀 있고 지문이 맞아도 `onto-`로 시작하는 스킬 밖이면 지우지 않는다."""
    root = sandbox.root()
    billing = attach(sandbox, root, files={"README.md": "# billing\n", TEAM_SKILL: TEAM_TEXT, "docs/notes.md": "메모\n"})
    assert sync(sandbox, root, "billing").returncode == 0
    record = json.loads((billing / RECORD).read_text(encoding="utf-8"))
    record[TEAM_SKILL] = fingerprint(TEAM_TEXT.encode())
    record[f"{SKILL_ROOT}/onto-x/../review/SKILL.md"] = fingerprint(TEAM_TEXT.encode())
    record["docs/notes.md"] = fingerprint("메모\n".encode())
    (billing / RECORD).write_text(json.dumps(record), encoding="utf-8")

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert (billing / TEAM_SKILL).read_text(encoding="utf-8") == TEAM_TEXT
    assert (billing / "docs" / "notes.md").read_text(encoding="utf-8") == "메모\n"


# --- 손으로 고친 사본 ------------------------------------------------------------------------------


def test_손으로_고친_스킬_사본은_덮어쓰지_않고_보고하며_지우면_되살린다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root)
    assert sync(sandbox, root, "billing").returncode == 0
    copy = billing / SKILL_ROOT / "onto-ingest" / "SKILL.md"
    original = copy.read_bytes()
    copy.write_text("내가 손으로 고친 스킬\n", encoding="utf-8")

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1
    assert re.search(rf"건너뜀\s+{re.escape(SKILL_ROOT)}/onto-ingest/SKILL\.md\s+—.*손으로 고친", result.stdout)
    assert copy.read_text(encoding="utf-8") == "내가 손으로 고친 스킬\n"  # 덮어쓰지 않았다
    copy.unlink()

    assert sync(sandbox, root, "billing").returncode == 0
    assert copy.read_bytes() == original  # 지우면 루트의 내용으로 되살아난다


# --- 뒤처진 사본의 경고 ---------------------------------------------------------------------------


def test_스킬_사본이_없는_지식_저장소는_뒤처졌다고_경고하고_최신화가_고친다(sandbox):
    """스킬을 복사하기 전에 최신화한 저장소다. `.onto/`는 있지만 스킬 사본이 없다."""
    root = sandbox.root()
    billing = attach(sandbox, root, files=repo("billing", page("component/gateway", "Component", title="게이트웨이", partOf="project")))
    assert sync(sandbox, root, "billing").returncode == 0
    assert drift_rows(sandbox, root) == []
    for name in SKILLS:
        for path in sorted((billing / SKILL_ROOT / name).rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        (billing / SKILL_ROOT / name).rmdir()

    (row,) = drift_rows(sandbox, root)

    assert row[1] == "billing" and "없는 파일" in row[4] and f"`{SKILL_ROOT}/onto-" in row[4] and "just onto sync billing" in row[4]
    assert sync(sandbox, root, "billing").returncode == 0
    assert drift_rows(sandbox, root) == []


def test_손으로_고친_스킬_사본도_뒤처진_것으로_경고한다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root, files=repo("billing", page("component/gateway", "Component", title="게이트웨이", partOf="project")))
    assert sync(sandbox, root, "billing").returncode == 0
    (billing / SKILL_ROOT / "onto-lint" / "SKILL.md").write_text("고쳤다\n", encoding="utf-8")

    (row,) = drift_rows(sandbox, root)

    assert f"내용이 다른 파일 1개(`{SKILL_ROOT}/onto-lint/SKILL.md`)" in row[4]


def test_루트에서_없앤_스킬이_사본에_남아_있으면_뒤처진_것으로_경고한다(sandbox):
    root = sandbox.root()
    root.commit({f"{SKILL_ROOT}/onto-extra/SKILL.md": "추가 스킬\n"})
    attach(sandbox, root, files=repo("billing", page("component/gateway", "Component", title="게이트웨이", partOf="project")))
    assert sync(sandbox, root, "billing").returncode == 0
    assert drift_rows(sandbox, root) == []
    sandbox.git("rm", "-r", "-q", f"{SKILL_ROOT}/onto-extra", cwd=root.work)

    (row,) = drift_rows(sandbox, root)

    assert f"루트에서 없어졌는데 남은 파일 1개(`{SKILL_ROOT}/onto-extra/SKILL.md`)" in row[4]


def drift_rows(sandbox, root) -> list[list[str]]:
    """`just onto validate`가 보고한 `outdated-managed-files` 행."""
    result = sandbox.just("onto", "validate", cwd=root.work)
    return [row for row in parse_table(result.stdout) if len(row) == 5 and row[3] == CHECK]


# --- 지식 저장소의 git이 스킬 사본을 이미 추적하는 경우 -------------------------------------------------


def test_지식_저장소가_스킬_사본을_이미_추적하고_있으면_추적에서_빼라고_알린다(sandbox):
    """`.gitignore`는 추적하는 파일을 제외하지 못한다. 루트 스킬과 같은 이름의 사본을 누가 커밋했으면 사람이 추적에서 빼야 한다."""
    root = sandbox.root()
    committed = (root.work / SKILL_ROOT / "onto-ingest" / "SKILL.md").read_text(encoding="utf-8")
    billing = attach(sandbox, root, files={"README.md": "# billing\n", f"{SKILL_ROOT}/onto-ingest/SKILL.md": committed, TEAM_SKILL: TEAM_TEXT})

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1  # 사람이 확인할 것이다
    assert re.search(rf"확인 필요\s+{re.escape(SKILL_ROOT)}/onto-ingest/\s+—.*이미 추적.*git rm -r --cached {re.escape(SKILL_ROOT)}/onto-ingest", result.stdout)
    assert "onto-query/\n" not in result.stdout.split("확인 필요")[-1]  # 추적하지 않는 스킬은 알리지 않는다
    assert "review" not in result.stdout  # 팀의 스킬은 알리지 않는다
    assert (billing / SKILL_ROOT / "onto-query" / "SKILL.md").is_file()  # 최신화는 계속한다


# --- 루트의 스킬에 문제가 있는 경우 -----------------------------------------------------------------


def test_루트의_스킬에_추적하지_않는_파일이_있으면_복사하지_않고_경고한다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root)
    (root.work / SKILL_ROOT / "onto-ingest" / "draft.md").write_text("아직 git add하지 않았다\n", encoding="utf-8")
    (root.work / SKILL_ROOT / "team-draft").mkdir()
    (root.work / SKILL_ROOT / "team-draft" / "SKILL.md").write_text("onto 스킬이 아닌 초안\n", encoding="utf-8")

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0
    assert "추적하지 않는 파일" in result.stderr and f"{SKILL_ROOT}/onto-ingest/draft.md" in result.stderr and "git add" in result.stderr
    assert "team-draft" not in result.stderr  # 복사 대상이 아닌 스킬의 초안은 알리지 않는다
    assert not (billing / SKILL_ROOT / "onto-ingest" / "draft.md").exists()


def test_루트의_스킬이_심볼릭_링크이면_복사하지_않고_멈춘다_스킬이_아닌_링크는_상관없다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root)
    (root.work / SKILL_ROOT / "root-only").mkdir()
    (root.work / SKILL_ROOT / "root-only" / "SKILL.md").symlink_to("../../../README.md")
    sandbox.git("add", f"{SKILL_ROOT}/root-only", cwd=root.work)
    assert sync(sandbox, root, "billing").returncode == 0  # 복사 대상이 아닌 스킬의 링크는 멈추지 않는다
    (root.work / SKILL_ROOT / "onto-link").mkdir()
    (root.work / SKILL_ROOT / "onto-link" / "SKILL.md").symlink_to("../../../README.md")
    sandbox.git("add", f"{SKILL_ROOT}/onto-link", cwd=root.work)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1 and "심볼릭 링크" in result.stderr and f"{SKILL_ROOT}/onto-link/SKILL.md" in result.stderr
    assert not (billing / SKILL_ROOT / "onto-link").exists()


# --- 지식 저장소의 위치가 링크이거나 파일인 경우 ---------------------------------------------------------


def test_dot_claude가_심볼릭_링크이면_스킬은_따라가지_않고_건너뛰며_dot_onto는_복사한다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root)
    outside = sandbox.new_dir("elsewhere", "claude")
    (billing / ".claude").symlink_to(outside)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1
    reported = re.findall(r"^  건너뜀\s+(\S+)\s+—\s+(.*)$", result.stdout, re.MULTILINE)
    assert sorted(path for path, _ in reported) == sorted(f"{SKILL_ROOT}/{name}/SKILL.md" for name in SKILLS)  # 스킬 파일마다 알린다
    assert all("`.claude`가 심볼릭 링크" in reason for _, reason in reported)
    assert list(outside.iterdir()) == []  # 링크 밖에 아무것도 쓰지 않는다
    assert (billing / ".onto" / "Justfile").is_file()  # 나머지 루트 관리 파일은 최신화한다


def test_dot_claude_skills가_일반_파일이면_건너뛰고_보고한다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root)
    (billing / ".claude").mkdir()
    (billing / ".claude" / "skills").write_text("파일이다\n", encoding="utf-8")

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1
    assert re.search(r"건너뜀\s+.*디렉토리가 아니다", result.stdout)
    assert (billing / ".claude" / "skills").read_text(encoding="utf-8") == "파일이다\n"


def test_스킬_파일_자리가_디렉토리이면_건너뛰고_그_밖은_복사한다(sandbox):
    root = sandbox.root()
    billing = attach(sandbox, root)
    (billing / SKILL_ROOT / "onto-ingest" / "SKILL.md").mkdir(parents=True)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1
    assert re.search(rf"건너뜀\s+{re.escape(SKILL_ROOT)}/onto-ingest/SKILL\.md\s+—.*일반 파일이 아니다", result.stdout)
    assert (billing / SKILL_ROOT / "onto-query" / "SKILL.md").is_file()


# --- 지식 저장소 안에서는 복사한 스킬을 쓴다 ------------------------------------------------------------


def test_복사한_스킬이_안내하는_지식_저장소_안의_명령이_실제로_돈다(sandbox):
    """스킬은 지식 저장소 안에서 `just -f .onto/Justfile <명령>`을 쓰라고 안내한다. 같은 접두어로 명령 네 개가 그 저장소만 다룬다."""
    root = sandbox.root()
    files = repo("billing", page("component/gateway", "Component", title="게이트웨이", partOf="project"))
    billing = attach(sandbox, root, files=files)
    assert sync(sandbox, root, "billing").returncode == 0
    assert (billing / SKILL_ROOT / "onto-ingest" / "SKILL.md").is_file()

    for command in (["build"], ["validate"], ["status"], ["query", "SELECT ?e WHERE { ?e a onto:Component }"]):
        result = sandbox.just("-f", ".onto/Justfile", *command, cwd=billing)
        assert result.returncode == 0, f"{command}: {result.stdout}{result.stderr}"


def test_온톨로지_층의_위치는_스킬이_알려_주는_경로와_같다(sandbox):
    """스킬이 페이지를 두라고 안내하는 `docs/ontology/`는 최신화가 만든 뼈대의 위치다."""
    root = sandbox.root()
    billing = attach(sandbox, root)
    assert sync(sandbox, root, "billing").returncode == 0

    assert (billing / ONTOLOGY_DIR / "ontology.yaml").is_file() and (billing / ONTOLOGY_DIR / "index.md").is_file()
