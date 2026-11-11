"""사용법 문서와 스킬 문서가 실제 명령과 어긋나지 않는지 본다.

스킬 문서의 내용(LLM이 읽는 글)은 자동 테스트에서 뺀다. 여기서는 기계적으로 가릴 수 있는 것만 본다.

- 문서에 적힌 `just` 명령이 실제로 있는 모듈과 레시피다. 루트 저장소(`just <모듈> <레시피>`)와 지식 저장소 안(`just -f .onto/Justfile <레시피>`) 모두다.
- 루트의 모든 레시피가 `README.md`에 적혀 있다.
- 스킬 세 개가 `name`, `description`을 가진 frontmatter로 시작하고, 루트와 지식 저장소 안의 명령 접두어, 개인 지식 저장소 안내, 커밋 메시지 규약을 담는다.
- 루트 `CLAUDE.md`가 스킬과 사용법을 가리키고 기존 `## Agent skills` 블록을 지킨다.

문서는 이 저장소의 작업 사본에서 읽기만 하고, 명령의 목록은 임시 디렉토리의 루트 저장소(이 저장소의 추적 파일을 복사한 것)에서 `just --summary`로 얻는다.
"""

import re
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
def test_스킬은_루트와_지식_저장소_안에서_쓰는_명령_접두어를_모두_안내한다(name):
    document = text(SKILL_FILES[name])

    assert "just onto" in document and "just -f .onto/Justfile" in document
    assert "루트 저장소" in document and "지식 저장소 안" in document


@pytest.mark.parametrize("name", SKILLS)
def test_스킬은_여러_프로젝트를_비교하는_지식은_개인_지식_저장소에_둔다고_안내한다(name):
    document = text(SKILL_FILES[name])

    assert "개인 지식 저장소" in document and "비교·종합" in document


def test_ingest_스킬은_절차와_지킬_것을_담는다():
    document = text(SKILL_FILES["onto-ingest"])

    for step in ("status", "build", "validate", "derivedFrom", "skipped.yaml"):
        assert step in document
    assert "원본 문서는 읽기 전용" in document and "커밋하지 않고" in document and "지식 저장소 단위" in document
    assert "onto(ingest):" in document


def test_lint_스킬은_스크립트_검사를_먼저_하고_고치기_전에_보고한다():
    document = text(SKILL_FILES["onto-lint"])

    steps = ("1. **스크립트 검사.**", "2. **판단이 필요한 검사.**", "3. **보고하고 멈춘다.**", "4. **승인받은 것만 고친다.**")
    assert [document.index(step) for step in steps] == sorted(document.index(step) for step in steps)  # 스크립트 검사 다음에 판단 검사, 그다음 보고, 마지막이 수정
    assert "고치기 전에 사용자에게 보고한다" in document
    assert "onto(lint):" in document


def test_query_스킬은_질의하는_법과_클래스와_관계_목록과_결과에서_페이지로_가는_법을_담는다():
    document = text(SKILL_FILES["onto-query"])

    assert "query '" in document and "SELECT" in document
    for term in ("onto:Component", "onto:Policy", "onto:partOf", "onto:dependsOn", "onto:governs", "onto:implements", "onto:supersedes", "onto:about", "onto:derivedFrom"):
        assert term in document
    assert "## 결과에서 페이지로 가는 법" in document and "파일 경로" in document


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
