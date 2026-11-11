"""최신화가 프로젝트 지침 파일(`CLAUDE.md`, 없으면 `AGENTS.md`)에 넣는 표시된 블록.

가장 높은 이음매다(`just onto sync`). 블록은 지식 저장소를 연 에이전트를 온톨로지 층의 인덱스로 안내한다. 지침 파일은 팀의 것이라
블록 밖은 한 글자도 바뀌지 않아야 하고, 복사된 기능(`.onto/`)이 없는 클론에서도 블록의 뜻이 통해야 한다.
"""

import os
import re
import shutil
from pathlib import Path

from support.onto_cli import ONTOLOGY_DIR, page, repo

BEGIN = "<!-- onto:begin"
END = "<!-- onto:end -->"
INDEX = f"{ONTOLOGY_DIR}/index.md"
# 블록 안에서 복사된 기능의 안내가 시작되는 줄. 이 줄 앞은 복사된 기능이 없는 클론에서도 맞아야 한다.
CONDITIONAL = "복사된 기능이 있으면"

TEAM = "# 팀 지침\n\n- 커밋 메시지는 한국어로 쓴다.\n- 테스트 없이 병합하지 않는다.\n"


def attach(sandbox, root, name: str, *, files: dict[str, str] | None = None):
    """지식 저장소를 서브모듈로 붙인다. 지식 저장소의 작업 트리 경로와 그 원격을 돌려준다."""
    remote = sandbox.knowledge_remote(name, files=files)
    root.register(remote)
    return root.work / "projects" / name, remote


def sync(sandbox, root, *args: str):
    return sandbox.just("onto", "sync", *args, cwd=root.work)


def block_of(text: str) -> str:
    """지침 파일에서 표시된 블록(표시 줄 포함). 표시가 하나씩 있어야 한다."""
    lines = text.splitlines(keepends=True)
    begins = [i for i, line in enumerate(lines) if line.startswith(BEGIN)]
    ends = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == END]
    assert len(begins) == 1 and len(ends) == 1 and begins[0] < ends[0], text
    return "".join(lines[begins[0] : ends[0] + 1])


def standard_block(sandbox) -> str:
    """루트가 넣는 블록 그대로. 지침 파일이 없는 지식 저장소에 최신화해 만들어진 `AGENTS.md`다."""
    root = sandbox.root(name="standard")  # 한 테스트에서 루트를 둘 만들 수 있게 이름을 달리 준다
    fresh, _ = attach(sandbox, root, "fresh")
    assert sync(sandbox, root, "fresh").returncode == 0
    text = (fresh / "AGENTS.md").read_text(encoding="utf-8")
    assert text == block_of(text)  # 새로 만든 지침 파일에는 블록만 있다
    return text


# --- 어느 파일에 넣는가 ------------------------------------------------------------------


def test_CLAUDE_md가_있으면_거기에_블록을_넣고_AGENTS_md는_건드리지_않는다(sandbox):
    root = sandbox.root()
    agents = "# 에이전트 지침\n\n다른 도구가 읽는다.\n"
    billing, _ = attach(sandbox, root, "billing", files={"README.md": "# billing\n", "CLAUDE.md": TEAM, "AGENTS.md": agents})

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    text = (billing / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.startswith(TEAM) and block_of(text[len(TEAM) :])
    assert (billing / "AGENTS.md").read_text(encoding="utf-8") == agents
    assert "바꿈  CLAUDE.md" in result.stdout


def test_CLAUDE_md가_없고_AGENTS_md가_있으면_AGENTS_md에_블록을_넣는다(sandbox):
    root = sandbox.root()
    billing, _ = attach(sandbox, root, "billing", files={"README.md": "# billing\n", "AGENTS.md": TEAM})

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    text = (billing / "AGENTS.md").read_text(encoding="utf-8")
    assert text.startswith(TEAM) and block_of(text[len(TEAM) :])
    assert not (billing / "CLAUDE.md").exists()


def test_지침_파일이_둘_다_없으면_AGENTS_md를_만들고_블록만_담는다(sandbox):
    root = sandbox.root()
    billing, _ = attach(sandbox, root, "billing")
    assert not (billing / "CLAUDE.md").exists() and not (billing / "AGENTS.md").exists()

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    text = (billing / "AGENTS.md").read_text(encoding="utf-8")
    assert text == block_of(text)
    assert not (billing / "CLAUDE.md").exists()
    assert "만듦  AGENTS.md" in result.stdout


def test_최신화가_만든_AGENTS_md는_커밋되지_않은_채_남고_복사된_기능은_git_상태에_나타나지_않는다(sandbox):
    root = sandbox.root()
    billing, _ = attach(sandbox, root, "billing")
    head = sandbox.head(billing)

    assert sync(sandbox, root, "billing").returncode == 0

    status = sandbox.git("status", "--porcelain", "--untracked-files=all", cwd=billing).stdout.splitlines()
    assert sorted(status) == sorted(["?? .gitignore", "?? AGENTS.md", f"?? {INDEX}", f"?? {ONTOLOGY_DIR}/ontology.yaml"])
    assert sandbox.head(billing) == head and sandbox.git("diff", "--cached", "--name-only", cwd=billing).stdout == ""


def test_온톨로지_층을_구성하지_못한_지식_저장소에는_블록을_넣지_않는다(sandbox):
    """인덱스가 없는 저장소의 지침 파일에 인덱스를 가리키는 블록을 넣지 않는다. 구성을 막은 이유는 따로 보고된다."""
    root = sandbox.root()
    billing, _ = attach(sandbox, root, "billing", files={"README.md": "# billing\n", "CLAUDE.md": TEAM})
    outside = sandbox.new_dir("elsewhere", "docs")
    (billing / "docs").symlink_to(outside)  # docs/ontology/ontology.yaml을 만들 수 없다

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1
    assert (billing / "CLAUDE.md").read_text(encoding="utf-8") == TEAM
    assert not (billing / "AGENTS.md").exists()


# --- 블록 밖은 바뀌지 않는다 -------------------------------------------------------------


def test_지침_파일의_기존_내용은_한_글자도_바뀌지_않고_블록이_뒤에_덧붙는다(sandbox):
    original = "# 지침\r\n\r\n- 줄바꿈이 CRLF다.\r\n- 마지막 줄에 줄바꿈이 없다"
    root = sandbox.root()
    billing, _ = attach(sandbox, root, "billing", files={"README.md": "# billing\n", "CLAUDE.md": original})
    raw = (billing / "CLAUDE.md").read_bytes()

    assert sync(sandbox, root, "billing").returncode == 0

    after = (billing / "CLAUDE.md").read_bytes()
    assert after.startswith(raw)  # 기존 바이트가 그대로 앞에 남는다
    block = after[len(raw) :].decode("utf-8")
    assert BEGIN in block and END in block
    assert "\r\n" in block and not re.search(r"(?<!\r)\n", block)  # 파일이 CRLF이면 블록도 CRLF다


def test_블록이_이미_있으면_그_자리에서_내용만_바뀌고_앞뒤는_한_글자도_바뀌지_않는다(sandbox):
    block = standard_block(sandbox)
    before, after = "# 앞\n\n팀이 쓴 지침.\n\n", "\n## 뒤\n\n팀이 쓴 지침이 더 있다.\n"
    stale = "<!-- onto:begin 옛 설명 -->\n옛 안내\n<!-- onto:end -->\n"
    root = sandbox.root()
    billing, _ = attach(sandbox, root, "billing", files={"README.md": "# billing\n", "CLAUDE.md": before + stale + after})

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert (billing / "CLAUDE.md").read_text(encoding="utf-8") == before + block + after
    assert "옛 안내" not in (billing / "CLAUDE.md").read_text(encoding="utf-8")


def test_블록이_중복되지_않는다_여러_번_실행해도_하나다(sandbox):
    root = sandbox.root()
    billing, _ = attach(sandbox, root, "billing", files={"README.md": "# billing\n", "CLAUDE.md": TEAM})

    for _ in range(3):
        assert sync(sandbox, root, "billing").returncode == 0

    text = (billing / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.count(BEGIN) == 1 and text.count(END) == 1
    assert text.startswith(TEAM)


def test_두_번_연속_실행하면_두_번째는_지침_파일을_다시_쓰지_않는다(sandbox):
    root = sandbox.root()
    billing, _ = attach(sandbox, root, "billing", files={"README.md": "# billing\n", "CLAUDE.md": TEAM})
    assert sync(sandbox, root, "billing").returncode == 0
    guidance = billing / "CLAUDE.md"
    os.utime(guidance, ns=(1_000_000_000, 1_000_000_000))  # 다시 쓰면 바뀔 수정 시각을 먼 과거로 돌려 둔다
    before = guidance.read_bytes()

    result = sync(sandbox, root, "billing")

    assert result.returncode == 0, result.stderr
    assert guidance.read_bytes() == before and guidance.stat().st_mtime_ns == 1_000_000_000
    assert "바뀐 것이 없다" in result.stdout


# --- 커밋되지 않은 수정 --------------------------------------------------------------------


def test_지침_파일에_커밋되지_않은_수정이_있어도_블록만_교체하고_다음_최신화가_막히지_않는다(sandbox):
    root = sandbox.root()
    billing, _ = attach(sandbox, root, "billing", files={"README.md": "# billing\n", "CLAUDE.md": TEAM})
    mine = TEAM + "\n- 이 줄은 커밋하지 않았다.\n"
    (billing / "CLAUDE.md").write_text(mine, encoding="utf-8")
    assert sandbox.git("status", "--porcelain", "CLAUDE.md", cwd=billing).stdout.strip() == "M CLAUDE.md"  # 커밋되지 않은 수정이 있다

    first = sync(sandbox, root, "billing")  # 블록을 넣는다. 이제 지침 파일에는 블록 때문에 생긴 수정도 있다
    guidance = billing / "CLAUDE.md"
    assert first.returncode == 0, first.stderr
    assert guidance.read_text(encoding="utf-8").startswith(mine)
    # 루트가 블록의 글을 고쳤다. 그 사이 팀원이 블록 뒤에 줄을 더했다
    source = root.work / "onto" / "onto_tool" / "guidance.py"
    source.write_text(source.read_text(encoding="utf-8").replace("## 온톨로지 층", "## 온톨로지 층(고침)", 1), encoding="utf-8")
    guidance.write_text(guidance.read_text(encoding="utf-8") + "\n- 블록 뒤에 더한 줄.\n", encoding="utf-8")
    tail = "\n- 블록 뒤에 더한 줄.\n"

    second = sync(sandbox, root, "billing")

    assert second.returncode == 0, second.stdout + second.stderr  # 직전에 넣은 블록과 커밋되지 않은 수정이 최신화를 막지 않는다
    text = guidance.read_text(encoding="utf-8")
    assert text.startswith(mine) and text.endswith(tail)
    assert "## 온톨로지 층(고침)" in block_of(text)
    assert "바꿈  CLAUDE.md" in second.stdout


# --- 표시가 틀렸거나 쓸 수 없는 지침 파일 ---------------------------------------------------


def test_표시가_짝이_맞지_않으면_지침_파일을_고치지_않고_이유와_함께_보고한다_나머지는_최신화한다(sandbox):
    broken = f"{TEAM}\n{BEGIN} 옛 설명 -->\n끝 표시가 없다\n"
    root = sandbox.root()
    billing, _ = attach(sandbox, root, "billing", files={"README.md": "# billing\n", "CLAUDE.md": broken})

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1
    assert (billing / "CLAUDE.md").read_text(encoding="utf-8") == broken
    assert re.search(r"건너뜀\s+CLAUDE\.md\s+—.*표시", result.stdout)
    assert (billing / ".onto" / "Justfile").is_file() and (billing / "docs/ontology/index.md").is_file()  # 나머지는 최신화했다


def test_지침_파일이_심볼릭_링크이면_따라가지_않고_밖의_파일을_고치지_않는다(sandbox):
    root = sandbox.root()
    billing, _ = attach(sandbox, root, "billing", files={"README.md": "# billing\n"})
    outside = sandbox.new_dir("elsewhere", "shared") / "CLAUDE.md"
    outside.write_text("저장소 밖의 파일\n", encoding="utf-8")
    (billing / "CLAUDE.md").symlink_to(outside)

    result = sync(sandbox, root, "billing")

    assert result.returncode == 1
    assert outside.read_text(encoding="utf-8") == "저장소 밖의 파일\n"
    assert not (billing / "AGENTS.md").exists()  # 링크가 CLAUDE.md의 자리에 있으므로 다른 파일에 쓰지 않는다
    assert re.search(r"건너뜀\s+CLAUDE\.md\s+—.*심볼릭 링크", result.stdout)


# --- 블록의 내용 ---------------------------------------------------------------------------


def paths_in(text: str) -> list[str]:
    """글 안의 백틱으로 감싼 것 가운데 경로(`/`가 든 것)."""
    return [token for token in re.findall(r"`([^`]+)`", text) if "/" in token]


def test_블록은_인덱스를_가리키고_복사된_기능이_있으면_규약_문서와_스킬과_명령을_쓰라고_안내한다(sandbox):
    block = standard_block(sandbox)

    unconditional, _, conditional = block.partition(CONDITIONAL)
    assert "`docs/ontology/index.md`" in unconditional  # 인덱스가 먼저다
    assert "`.onto/template/conventions.md`" in conditional  # 규약 문서
    assert "`.claude/skills/onto-*/`" in conditional  # 스킬
    assert "just -f .onto/Justfile" in conditional  # 명령
    for command in ("validate", "build", "query", "status"):
        assert f"`{command}" in conditional


def test_블록은_복사된_기능이_없는_클론에서도_뜻이_통하고_없는_파일을_읽으라고_하지_않는다(sandbox):
    """지식 저장소의 커밋에는 지침 파일과 온톨로지 층만 들어간다. 따로 클론하면 `.onto/`도 스킬도 없다."""
    root = sandbox.root()
    billing, remote = attach(sandbox, root, "billing", files={"README.md": "# billing\n", "CLAUDE.md": TEAM})
    assert sync(sandbox, root, "billing").returncode == 0
    sandbox.git("add", "CLAUDE.md", ".gitignore", "docs/ontology", cwd=billing)
    sandbox.git("commit", "-m", "onto: 온톨로지 층", cwd=billing)
    sandbox.git("push", "origin", "HEAD:main", cwd=billing)
    clone = sandbox.new_dir("clones", "standalone")
    sandbox.git("clone", remote.url, clone / "billing", cwd=clone)
    standalone = clone / "billing"
    assert not (standalone / ".onto").exists() and not (standalone / ".claude").exists()  # 복사된 기능이 없다

    block = block_of((standalone / "CLAUDE.md").read_text(encoding="utf-8"))

    unconditional, separator, conditional = block.partition(CONDITIONAL)
    assert separator, "복사된 기능의 안내는 있으면이라는 조건 뒤에 있어야 한다"
    assert paths_in(unconditional)  # 가리키는 곳이 있다
    for path in paths_in(unconditional):
        assert (standalone / path).exists(), path  # 조건 앞에서 가리키는 것은 클론에 모두 있다
    assert "없으면" in conditional  # 복사된 기능이 없을 때 할 일이 적혀 있다
    # 조건 앞에는 복사된 기능에 속한 것이 없다
    assert ".onto" not in unconditional and ".claude" not in unconditional and "just" not in unconditional


def test_블록은_루트_저장소나_다른_지식_저장소를_언급하지_않는다(sandbox):
    root = sandbox.root()
    billing, _ = attach(sandbox, root, "billing")
    shop, _ = attach(sandbox, root, "shop")

    assert sync(sandbox, root).returncode == 0

    block = block_of((billing / "AGENTS.md").read_text(encoding="utf-8"))
    assert block == block_of((shop / "AGENTS.md").read_text(encoding="utf-8"))  # 저장소에 따라 달라지지 않는다
    for forbidden in ("루트", "projects", "서브모듈", "shop", "billing", "just onto", "sync", "최신화"):
        assert forbidden not in block, forbidden


def test_블록은_온톨로지에_관한_것만_담는다(sandbox):
    block = standard_block(sandbox)

    for path in paths_in(block):
        assert path.startswith(("docs/ontology/", ".onto/", ".claude/skills/onto-", "just -f .onto/Justfile")), path
    assert "## 온톨로지 층" in block
