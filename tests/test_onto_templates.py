"""템플릿과 규약 문서(`onto/template/`): 클래스별 페이지 견본과 페이지 쓰는 법.

견본과 규약 문서의 예는 문서일 뿐이라 따로 믿지 않는다. 도구가 받아들이는지를 도구에 돌려 확인한다(`onto_cli`).
"""

import re

from support.onto_cli import ONTOLOGY_DIR, ontology_yaml, page, repo
from support.sandbox import SOURCE_REPO

TEMPLATE_DIR = SOURCE_REPO / "onto" / "template"
# 클래스 -> 페이지를 두는 디렉토리. 견본의 파일 이름이기도 하다.
CLASSES = {
    "Component": "component",
    "Plan": "plan",
    "Policy": "policy",
    "Term": "term",
    "Decision": "decision",
    "Report": "report",
}
# 관계의 값으로 쓸 수 있는 대상. 견본을 쓴 클래스가 쓸 수 있는 관계마다, 가리킬 수 있는 엔티티 하나다.
RELATION_VALUES = {
    "partOf": "project",
    "dependsOn": "project",
    "implements": "plan/old",
    "governs": "project",
    "about": "project",
}


def template(directory: str) -> str:
    return (TEMPLATE_DIR / f"{directory}.md").read_text(encoding="utf-8")


def filled(cls: str, directory: str) -> str:
    """견본의 필수 제목과 관계를 채운 페이지. 채운 관계가 그 클래스에서 쓸 수 있는 것인지는 스크립트 검사가 따진다."""
    text = re.sub(r"^title:.*$", "title: 견본 제목", template(directory), flags=re.MULTILINE)
    for key, value in RELATION_VALUES.items():
        text = re.sub(rf"^{key}:.*$", f"{key}: {value}", text, flags=re.MULTILINE)
    return re.sub(r"^supersedes:.*$", f"supersedes: {directory}/old", text, flags=re.MULTILINE)


def test_클래스마다_페이지_견본이_있고_견본의_class가_그_클래스다():
    for cls, directory in CLASSES.items():
        assert re.search(rf"^class: {cls}\b", template(directory), re.MULTILINE), directory


def test_견본의_키는_모두_그_클래스의_페이지가_쓸_수_있는_것이다(onto_cli):
    """견본을 채워 페이지로 두면 스크립트 검사에 걸리지 않는다. 정의되지 않은 키, 클래스가 쓸 수 없는 관계가 견본에 있으면 걸린다."""
    pages: dict[str, str] = {}
    for cls, directory in CLASSES.items():
        pages[f"{ONTOLOGY_DIR}/{directory}/sample.md"] = filled(cls, directory)
        pages.update(page(f"{directory}/old", cls, title=f"옛 {directory}"))  # supersedes가 가리키는 대상
    pages.update(ontology_yaml("billing"))
    root = onto_cli.root({"billing": pages})

    result = onto_cli.run(root, "validate")

    assert result.returncode == 0, result.stdout
    assert result.stdout == ""


def test_견본의_채우지_않은_제목은_필수_속성이_없다고_잡힌다(onto_cli):
    """견본을 채우지 않고 두면 걸린다. 에이전트가 견본의 자리를 남기지 않게 하는 안전장치다."""
    unfilled = template("plan")
    root = onto_cli.root({"billing": repo("billing", {f"{ONTOLOGY_DIR}/plan/unfilled.md": unfilled})})

    result = onto_cli.run(root, "validate")

    assert result.returncode == 1
    assert "missing-property" in result.stdout


# --- 규약 문서 -----------------------------------------------------------------------


def conventions() -> str:
    return (TEMPLATE_DIR / "conventions.md").read_text(encoding="utf-8")


def test_규약_문서가_식별자_교차_참조_derivedFrom_언어_하위_클래스_선언을_설명한다():
    headings = re.findall(r"^#{2,3} (.+)$", conventions(), re.MULTILINE)

    for topic in ("식별자", "참조하는 법", "원본 문서와 `derivedFrom`", "언어", "하위 클래스"):
        assert topic in headings, topic


def test_규약_문서가_보여_주는_하위_클래스_선언은_도구가_받아들인다(onto_cli):
    section = conventions().split("## 하위 클래스")[1]
    declaration = re.search(r"```yaml\n(.*?)```", section, re.DOTALL)
    assert declaration is not None
    yaml_text = declaration.group(1)  # 예의 `name`이 이 견본의 디렉토리 이름과 같다
    invoice = page("component/invoice-2024", "Invoice", title="2024년 인보이스", partOf="project")
    recurring = page("component/subscription", "RecurringInvoice", title="구독 인보이스", partOf="project")
    files = {f"{ONTOLOGY_DIR}/ontology.yaml": yaml_text, **invoice, **recurring}
    root = onto_cli.root({"billing": files})

    result = onto_cli.run(root, "validate")

    assert result.returncode == 0, result.stdout
    assert result.stdout == ""  # 공통 조상 클래스의 디렉토리(component/)에 두고 하위 클래스를 class로 쓴다
