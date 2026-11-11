"""템플릿과 규약 문서(`onto/template/`): 클래스별 페이지 견본과 페이지 쓰는 법.

견본과 규약 문서의 예는 문서일 뿐이라 따로 믿지 않는다. 도구가 받아들이는지를 도구에 돌려 확인한다(`onto_cli`).
"""

import hashlib
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


SOURCE_PATH = "docs/design.md"
SOURCE_CONTENT = "# 설계\n\n원본 문서의 내용\n"


def blob_hash(content: str) -> str:
    """git이 파일 내용을 blob으로 해시한 값. `git hash-object`의 정의(`sha1("blob <바이트 수>\\0" + 내용)`)다. git 저장소가 아닌 견본 디렉토리의 해시와 같다."""
    data = content.encode()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def filled(cls: str, directory: str) -> str:
    """견본의 필수 제목, 관계, 근거를 채운 페이지. 채운 값이 그 클래스에서 쓸 수 있는 것인지는 스크립트 검사가 따진다."""
    text = re.sub(r"^title:.*$", "title: 견본 제목", template(directory), flags=re.MULTILINE)
    for key, value in RELATION_VALUES.items():
        text = re.sub(rf"^{key}:.*$", f"{key}: {value}", text, flags=re.MULTILINE)
    text = re.sub(r"^supersedes:.*$", f"supersedes: {directory}/old", text, flags=re.MULTILINE)
    text = re.sub(r"^  - path:.*$", f"  - path: {SOURCE_PATH}", text, flags=re.MULTILINE)
    return re.sub(r"^    hash:.*$", f'    hash: "{blob_hash(SOURCE_CONTENT)}"', text, flags=re.MULTILINE)


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
    pages[SOURCE_PATH] = SOURCE_CONTENT  # derivedFrom이 가리키는 원본 문서. 해시가 맞아 낡음이 아니다
    root = onto_cli.root({"billing": pages})

    result = onto_cli.run(root, "validate")

    assert result.returncode == 0, result.stdout
    assert result.stdout == ""


def test_견본의_derivedFrom은_채우지_않으면_값의_종류가_틀렸다고_잡히고_견본마다_있다(onto_cli):
    for directory in CLASSES.values():
        assert re.search(r"^derivedFrom:\n  - path:.*\n    hash:", template(directory), re.MULTILINE), directory
    root = onto_cli.root({"billing": repo("billing", {f"{ONTOLOGY_DIR}/plan/unfilled.md": template("plan")})})

    result = onto_cli.run(root, "validate")

    assert "invalid-value" in result.stdout and "derivedFrom" in result.stdout


def test_견본의_복사_경로_안내는_식별자_정의와_맞다_클래스_디렉토리를_두_번_쓰지_않는다():
    for directory in CLASSES.values():
        text = template(directory)
        assert f"`docs/ontology/<식별자>.md`로 복사" in text, directory
        assert f"docs/ontology/{directory}/<식별자>" not in text, directory


def test_견본의_채우지_않은_제목은_필수_속성이_없다고_잡힌다(onto_cli):
    """견본을 채우지 않고 두면 걸린다. 에이전트가 견본의 자리를 남기지 않게 하는 안전장치다."""
    unfilled = re.sub(r"^derivedFrom:\n  - path:.*\n    hash:.*\n", "", template("plan"), flags=re.MULTILINE)  # 근거는 따로 본다(위)
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


def test_규약_문서의_해시_안내는_status가_낸_값을_쓰게_하고_변환을_건너뛴_해시를_권하지_않는다():
    text = conventions()

    assert "--no-filters" not in text
    assert "`status`가 보여 주는 현재 해시를 그대로 옮겨 적는다" in text
    assert "CRLF" in text and "`git rev-parse HEAD:<경로>`" in text  # 저장소 blob에 CRLF가 든 문서는 git에서 직접 얻은 해시와 다를 수 있다


def test_규약_문서의_예에서_해시는_모두_따옴표로_감싼다():
    hashes = re.findall(r"^\s*hash: (.*)$", conventions(), re.MULTILINE)

    assert hashes and all(re.fullmatch(r'"[0-9a-f]{40}"', value) for value in hashes), hashes


def test_규약_문서가_보여_주는_페이지_예는_도구가_받아들인다(onto_cli):
    """예의 근거 문서와 해시, 가리키는 `component/ledger`를 갖춰 놓으면 스크립트 검사에 걸리지 않는다. 낡음도 아니다."""
    section = conventions().split("## 페이지")[1].split("### 키")[0]
    example = re.search(r"```markdown\n(.*?)```", section, re.DOTALL)
    assert example is not None
    source = "# 결정 기록\n\nPostgreSQL을 쓴다.\n"
    path = re.search(r"path: (\S+)", example.group(1)).group(1)
    page_text = re.sub(r'hash: "[0-9a-f]{40}"', f'hash: "{blob_hash(source)}"', example.group(1))  # 예의 자리표시 해시를 실제 문서의 해시로 바꾼다
    ledger = page("component/ledger", "Component", title="원장", partOf="project")
    files = {f"{ONTOLOGY_DIR}/decision/use-postgres.md": page_text, path: source, **ledger, **ontology_yaml("billing")}
    root = onto_cli.root({"billing": files})

    result = onto_cli.run(root, "validate")

    assert result.returncode == 0, result.stdout
    assert result.stdout == ""



def test_규약_문서가_참조와_링크의_공유_범위_규칙과_검사의_한계를_적는다():
    text = conventions()

    for phrase in (
        "`path-reference`",  # 관계의 값에는 식별자나 교차 참조만 쓴다. 경로와 주소는 오류다
        "`docs/ontology/plan/x`",
        "`componet/api`",
        "`scope-violation`",  # 더 좁은 범위나 다른 팀의 저장소는 가리킬 수 없다
        "`outside-link`",  # 본문 링크는 저장소 밖을 가리키지 않는다
        "페이지 기준 상대 경로",
        "`/docs/design.md`",  # 저장소 루트 기준 링크도 오류다
        "[결제 API](billing:component/api)",  # 본문에서 다른 저장소의 엔티티를 가리키는 법
        "`team:<팀 이름>`",
        "제목, 별칭, 본문 글(평문)에 더 좁은 범위의 저장소 이름을 적는 것은 검사가 잡지 못하니",  # 검사의 한계
    ):
        assert phrase in text, phrase


def test_규약_문서가_본문_링크의_대상이_없으면_깨진_참조라고_적는다():
    section = conventions().split("### 본문의 링크")[1].split("## 원본 문서와")[0]

    assert "`broken-reference`" in section  # 교차 참조가 가리키는 엔티티와 저장소 안의 상대 링크가 가리키는 파일이 있어야 한다
    assert "교차 참조" in section and "상대 링크" in section
    assert "대소문자" in section  # 경로의 대소문자는 실제 파일과 같게 쓴다


def test_규약_문서가_Project의_dependsOn을_관계_표와_ontology_yaml_절에_적는다():
    text = conventions()
    relations = text.split("## 관계와 교차 참조")[1].split("### 참조하는 법")[0]
    ontology_yaml = text.split("## `ontology.yaml`")[1].split("## 확인")[0]

    assert re.search(r"^\| `dependsOn` \|[^|]*\| `Component`, `Project` → `Component`, `Project` \|$", relations, re.MULTILINE)
    assert re.search(r"^\| `dependsOn` \|", ontology_yaml, re.MULTILINE)  # `ontology.yaml`의 키 표
    assert "`Project`가 쓰는 관계는 `dependsOn` 하나" in text


def test_규약_문서가_보여_주는_Project의_dependsOn_예는_도구가_받아들인다(onto_cli):
    section = conventions().split("## `ontology.yaml`")[1].split("## 확인")[0]
    examples = [block for block in re.findall(r"```yaml\n(.*?)```", section, re.DOTALL) if "dependsOn:" in block]
    assert len(examples) == 1
    yaml_text = examples[0]  # 예의 `name`이 이 견본의 디렉토리 이름과 같다
    repos = {
        "billing": {f"{ONTOLOGY_DIR}/ontology.yaml": yaml_text, **page("component/gateway", "Component", title="게이트웨이", partOf="project")},
        "shop": repo("shop", page("component/api", "Component", title="상점 API", partOf="project")),
    }
    root = onto_cli.root(repos)

    result = onto_cli.run(root, "validate")

    assert result.returncode == 0, result.stdout
    assert result.stdout == ""
    dependencies = onto_cli.query(root, "SELECT ?o WHERE { ?e a onto:Project ; onto:repository 'billing' ; onto:dependsOn ?o }")
    assert dependencies  # 예가 의존을 적었고 도구가 그것을 읽었다


def test_규약_문서가_보여_주는_본문_링크와_교차_참조는_도구가_받아들이고_경로_참조는_거부한다(onto_cli):
    """문서가 권하는 쓰기(페이지 기준 상대 경로, `<저장소>:<식별자>` 링크)는 통과하고, 금지하는 값(`docs/ontology/plan/x`)은 걸린다."""
    link = "[설계](../../design.md) [결제 API](billing:component/api)\n"
    ok = page("component/gateway", "Component", title="게이트웨이", partOf="project", dependsOn="billing:component/api", body=link)
    repos = {
        "shop": {**repo("shop", ok, scope="private"), "docs/design.md": SOURCE_CONTENT},  # 링크의 대상(`../../design.md`)은 저장소 안에 있다
        "billing": repo("billing", page("component/api", "Component", title="결제 API", partOf="project"), scope="private"),
    }
    assert onto_cli.run(onto_cli.root(repos), "validate").stdout == ""

    bad = {"shop": repo("shop", page("component/gateway", "Component", title="게이트웨이", partOf="project", dependsOn="docs/ontology/plan/x"))}

    assert "path-reference" in onto_cli.run(onto_cli.root(bad), "validate").stdout
