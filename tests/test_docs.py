"""사용법 문서와 스킬 문서가 실제 명령과 어긋나지 않는지 본다.

스킬 문서의 내용(LLM이 읽는 글)은 자동 테스트에서 뺀다. 문구는 고쳐 써도 뜻이 같으면 되므로 글의 표현은 보지 않고, 기계적으로 가릴 수 있는 것만 본다.

- 문서에 적힌 `just` 명령이 실제로 있는 모듈과 레시피다. 루트 저장소(`just <모듈> <레시피>`)와 지식 저장소 안(`just -f .onto/Justfile <레시피>`) 모두다.
- 스킬이 `<onto> <명령>`으로 부르는 명령을 지식 저장소 안에서도 쓸 수 있다.
- 루트의 모든 레시피가 `README.md`에 적혀 있다.
- 스킬 세 개가 `name`, `description`을 가진 frontmatter로 시작하고 두 명령 접두어를 적는다.
- 루트 `CLAUDE.md`가 스킬과 사용법을 가리키고 기존 `## Agent skills` 블록을 지킨다.
- 지식 저장소로 복사되는 파일에 이 저장소를 개발한 과정의 말(티켓, 스펙)이 남아 있지 않다.
- 테스트 안내의 걸리는 시간이 실제에 맞다.

문서는 이 저장소의 작업 사본에서 읽기만 하고, 명령의 목록은 임시 디렉토리의 루트 저장소(이 저장소의 추적 파일을 복사한 것)에서 `just --summary`로 얻는다.
"""

import re
import subprocess
from pathlib import Path

import pytest

from support.sandbox import SOURCE_REPO, Sandbox

SKILLS = ("onto-ingest", "onto-query", "onto-lint")
README = SOURCE_REPO / "README.md"
CLAUDE = SOURCE_REPO / "CLAUDE.md"
CONVENTIONS = SOURCE_REPO / "onto" / "template" / "conventions.md"
SKILL_FILES = {name: SOURCE_REPO / ".claude" / "skills" / name / "SKILL.md" for name in SKILLS}

# 지식 저장소 안에서 쓰는 레시피. `sync`는 루트 저장소에서만 쓸 수 있다.
REPOSITORY_RECIPES = {"build", "validate", "query", "status", "rules"}
ROOT_ONLY = {"sync"}

# `just setup`, `just <모듈> <레시피>`, `just -f .onto/Justfile <레시피>`. 레시피 자리에 `<명령>` 같은 자리 표시자가 오면 레시피는 비운다.
COMMAND = re.compile(r"just (?:(?P<inside>-f \.onto/Justfile)|(?P<module>setup|git|repo|onto))(?: (?P<recipe>[a-z][a-z-]*))?(?![\w-])")
PLACEHOLDER_COMMAND = re.compile(r"<onto> (?P<recipe>[a-z][a-z-]*)")


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def recipes(tmp_path_factory) -> tuple[set[str], set[str]]:
    """`(루트 저장소의 레시피 `모듈 레시피`, 지식 저장소 안의 레시피)`. 임시 디렉토리의 루트 저장소에서 `just --summary`로 얻는다."""
    sandbox = Sandbox(tmp_path_factory.mktemp("docs"))
    root = sandbox.root(push_gate=False)
    summary = sandbox.just("--summary", cwd=root.work, check=True).stdout.split()
    root_recipes = {name.replace("::", " ") for name in summary}
    inside = sandbox.just("--justfile", root.work / "onto" / "Justfile", "--summary", cwd=root.work, check=True).stdout.split()
    return root_recipes, set(inside)


def documented_commands(path: Path) -> list[tuple[str, str | None, str | None]]:
    """문서에 적힌 `just` 명령을 `(안/루트, 모듈, 레시피)`로. 지식 저장소 안의 명령은 `("inside", None, 레시피)`다."""
    found = []
    for match in COMMAND.finditer(text(path)):
        if match["inside"]:
            found.append(("inside", None, match["recipe"]))
        else:
            found.append(("root", match["module"], match["recipe"]))
    return found


DOCUMENTS = {"README": README, "CLAUDE": CLAUDE, "conventions": CONVENTIONS, **SKILL_FILES}


@pytest.mark.parametrize("name", DOCUMENTS)
def test_문서에_적힌_just_명령은_모두_실제로_있다(recipes, name):
    root_recipes, inside_recipes = recipes
    commands = documented_commands(DOCUMENTS[name])
    assert commands or name != "README", "README에 just 명령이 하나도 없다"

    for where, module, recipe in commands:
        if where == "inside":
            assert recipe is None or recipe in inside_recipes, f"{name}: `just -f .onto/Justfile {recipe}`는 지식 저장소 안에 없는 명령이다"
        elif module == "setup":
            assert "setup" in root_recipes
        elif recipe is not None:
            assert f"{module} {recipe}" in root_recipes, f"{name}: `just {module} {recipe}`는 없는 명령이다"


@pytest.mark.parametrize("name", SKILLS)
def test_스킬이_자리_표시자_접두어로_부르는_명령은_루트와_지식_저장소_안_모두에서_쓸_수_있다(recipes, name):
    inside_recipes = recipes[1]
    called = {match["recipe"] for match in PLACEHOLDER_COMMAND.finditer(text(SKILL_FILES[name]))}

    assert called, f"{name}이 `<onto> <명령>`을 쓰지 않는다"
    assert called <= REPOSITORY_RECIPES and called <= inside_recipes, f"{name}: 지식 저장소 안에서 쓸 수 없는 명령 {sorted(called - REPOSITORY_RECIPES)}"
    assert not called & ROOT_ONLY


def test_루트의_모든_명령이_README에_적혀_있다(recipes):
    readme = text(README)
    for name in sorted(recipes[0]):
        command = "just setup" if name == "setup" else f"just {name}"
        assert command in readme, f"README에 `{command}`가 없다"
    assert "just git push --force" in readme and "just onto rules" in readme
    assert all(f"just -f .onto/Justfile {recipe}" in readme for recipe in ("build", "validate", "query", "status"))


def test_README가_받아서_쓰는_법과_흐름을_담는다():
    readme = text(README)

    assert "git remote set-url origin" in readme  # 받은 뒤 origin을 자기 원격으로 바꾼다
    assert "just repo add" in readme and "git commit" in readme  # 지식 저장소를 붙이고 그 등록을 자기 루트 저장소에 커밋한다
    assert "just setup" in readme  # 초기 설정
    assert "just onto status" in readme and "onto-ingest" in readme  # ingest
    assert "just onto validate" in readme  # 검사
    assert "just git push" in readme  # 푸시
    assert "설계 단계" not in readme  # 계획이 아니라 실제 사용법이다


@pytest.mark.parametrize("name", SKILLS)
def test_스킬은_name과_description이_있는_frontmatter로_시작한다(name):
    document = text(SKILL_FILES[name])
    match = re.match(r"---\n(?P<meta>.*?)\n---\n", document, re.DOTALL)

    assert match, f"{name}: frontmatter가 없다"
    meta = dict(line.split(": ", 1) for line in match["meta"].splitlines())
    assert meta["name"] == name  # 디렉토리 이름과 같다
    assert meta["description"].strip()


@pytest.mark.parametrize("name", SKILLS)
def test_스킬은_루트와_지식_저장소_안에서_쓰는_명령_접두어를_모두_적는다(name):
    document = text(SKILL_FILES[name])

    assert "just onto" in document and "just -f .onto/Justfile" in document


def test_README에_커밋_메시지_규약이_있다():
    readme = text(README)

    assert "onto(ingest):" in readme and "onto(lint):" in readme


def test_루트_CLAUDE는_스킬과_사용법을_가리키고_기존_Agent_skills_블록을_지킨다():
    document = text(CLAUDE)
    intro, marker, block = document.partition("## Agent skills")

    assert marker and all(name in intro for name in SKILLS) and "README.md" in intro and "just" in intro
    assert intro.strip().startswith("## 온톨로지")
    assert len(intro.splitlines()) <= 12  # 짧은 안내다. 지식을 담지 않는다
    # 기존 블록의 소제목들은 그대로다
    for heading in ("### Issue tracker", "### Triage labels", "### Domain docs", "### Subagent routing"):
        assert heading in block


# 지식 저장소로 복사되는 파일(`onto/`와 `.claude/skills/onto-*/`의 추적 파일)은 이 저장소를 개발한 사람이 아니라 지식 저장소에서 쓰는 사람과 에이전트가 읽는다.
# 개발할 때 쓴 말(티켓, 스펙)은 거기서 가리킬 곳이 없다. 어떤 일이 어느 티켓에서 이뤄진다는 말은 그 일이 끝나면 사실과도 어긋난다.
DEVELOPMENT_WORDS = ("티켓", "스펙")


def copied_files(sandbox: Sandbox) -> dict[str, str]:
    """지식 저장소로 복사되는 추적 파일의 `{경로: 내용}`. 작업 트리의 현재 내용이다."""
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--", "onto", ".claude/skills"],
        cwd=SOURCE_REPO,
        env=sandbox.env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    paths = [rel for rel in filter(None, listing.split("\0")) if rel.startswith(("onto/", ".claude/skills/onto-")) and rel != "onto/uv.lock"]
    return {rel: text(SOURCE_REPO / rel) for rel in paths if (SOURCE_REPO / rel).is_file()}


def test_지식_저장소로_복사되는_파일에는_개발_과정의_말이_남아_있지_않다(sandbox):
    files = copied_files(sandbox)
    assert "onto/onto_tool/keys.py" in files and ".claude/skills/onto-query/SKILL.md" in files  # 복사되는 파일을 모두 읽었다

    found = {f"{rel}:{number}": line.strip() for rel, content in files.items() for number, line in enumerate(content.splitlines(), 1) if any(word in line for word in DEVELOPMENT_WORDS)}

    assert found == {}


def test_테스트_안내의_걸리는_시간은_전체_테스트가_병렬로도_몇_분_걸리는_실제에_맞다():
    guide = text(SOURCE_REPO / "tests" / "README.md")

    assert "병렬은 1분 안팎" not in guide  # 테스트가 1500개를 넘어 병렬로도 몇 분이 걸린다
    assert re.search(r"병렬로도 [^.]*\d+분", guide)


def test_onto_ingest_스킬의_쓰는_파일_문장은_프로젝트_의존을_적는_ontology_yaml의_dependsOn을_한_문장에_담는다():
    """앞 문장만 따르는 에이전트가 프로젝트 사이의 의존을 적지 않거나, 예외를 모르고 `ontology.yaml`의 다른 키를 고치지 않게 한다."""
    document = text(SKILL_FILES["onto-ingest"])
    sentence = re.search(r"쓰는 파일은(.*?뿐이다)", document)

    assert sentence is not None
    assert "`skipped.yaml`" in sentence[1] and "`ontology.yaml`" in sentence[1] and "`dependsOn`" in sentence[1]
    assert "다른 키" in document and "고치지 않는다" in document.split("쓰는 파일은")[1].split("**커밋하지")[0]
