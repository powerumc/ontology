"""흐름 테스트: 가짜 지식 저장소를 상대로 등록, 최신화, 페이지 작성, 컴파일, 검사, 질의, 푸시, 제거까지 명령을 처음부터 끝까지 잇는다.

앞 티켓들이 명령마다 따로 본 동작을 사용자가 실제로 밟는 순서대로 한 테스트에 잇는다. 한 명령의 결과가 다음 명령의 입력이 되므로 어느 한 고리가 끊기면 여기서 드러난다.
루트 저장소는 이 저장소의 추적 파일을 임시 디렉토리로 복사한 것(스킬 세 개 포함)이고, 지식 저장소는 로컬 bare 원격이다. 푸시 관문은 켜 둔 채다.
에이전트가 하는 일(페이지 쓰기)은 테스트가 파일을 써서 흉내 낸다. 스킬 문서의 내용은 LLM의 동작이라 여기서 보지 않는다.
"""

import json
from pathlib import Path

from support.onto_cli import ONTOLOGY_DIR, parse_table

DESIGN = "# 결제 설계\n\n결제 게이트웨이는 PG사 API를 감싼다.\n"
MEETING = "# 회의록\n\n잡담이다.\n"
SKILLS = ("onto-ingest", "onto-query", "onto-lint")

GATEWAY = f"{ONTOLOGY_DIR}/component/gateway.md"
API = f"{ONTOLOGY_DIR}/component/api.md"
INVOICE = f"{ONTOLOGY_DIR}/term/invoice.md"
SKIPPED = f"{ONTOLOGY_DIR}/skipped.yaml"
INDEX = f"{ONTOLOGY_DIR}/index.md"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def page(cls: str, title: str, *, hash_: str | None = None, source: str = "docs/design.md", **relations: str) -> str:
    """에이전트가 쓸 페이지. `derivedFrom`은 `status`가 낸 해시를 따옴표로 감싸 적는다."""
    lines = [f"class: {cls}", f"title: {title}", *(f"{key}: {value}" for key, value in relations.items())]
    if hash_ is not None:
        lines += ["derivedFrom:", f"  - path: {source}", f'    hash: "{hash_}"']
    return "---\n" + "\n".join(lines) + "\n---\n\n본문이다.\n"


def stdout_rows(result) -> list[list[str]]:
    return [row for row in parse_table(result.stdout) if row != [""]]


def test_등록부터_제거까지_명령을_처음부터_끝까지_잇는다(sandbox):
    root = sandbox.root()
    git = lambda *args, cwd=root.work: sandbox.git(*args, cwd=cwd)  # noqa: E731
    just = lambda *args, cwd=root.work: sandbox.just(*args, cwd=cwd)  # noqa: E731
    remote = sandbox.knowledge_remote("billing", files={"README.md": "# billing\n", "docs/design.md": DESIGN, "docs/meeting.md": MEETING})
    sub = root.work / "projects" / "billing"

    # --- 등록: 서브모듈로 붙이고 루트의 기능을 복사한다. 루트에는 스테이징까지만 한다 ---
    added = just("repo", "add", remote.url, "billing")
    assert added.returncode == 0, added.stderr
    assert sandbox.head(root.work) == sandbox.git("rev-parse", "origin/main", cwd=root.work).stdout.strip()  # 커밋하지 않았다
    assert set(git("diff", "--cached", "--name-only").stdout.split()) == {".gitmodules", "projects/billing"}
    assert (sub / ".onto" / "Justfile").is_file()  # 기능
    assert all((sub / ".claude" / "skills" / name / "SKILL.md").is_file() for name in SKILLS)  # 스킬
    assert (sub / ONTOLOGY_DIR / "ontology.yaml").is_file() and (sub / INDEX).is_file()  # 온톨로지 층의 뼈대
    registered = git("commit", "-m", "chore: billing 지식 저장소를 등록한다")
    assert registered.returncode == 0

    # --- 대상 확인: 새 문서 목록과 그 해시. 기대 해시는 도구가 아니라 git이 낸 값이다 ---
    design_hash = git("hash-object", "docs/design.md", cwd=sub).stdout.strip()
    meeting_hash = git("hash-object", "docs/meeting.md", cwd=sub).stdout.strip()
    status = just("onto", "status")
    assert status.returncode == 0, status.stderr
    assert [row[:4] for row in stdout_rows(status)] == [
        ["새 문서", "billing", "docs/design.md", design_hash],
        ["새 문서", "billing", "docs/meeting.md", meeting_hash],
    ]

    # --- 페이지 작성(에이전트가 하는 일): 페이지는 status의 해시를 근거로 적고, 기록할 것이 없는 문서는 넘긴 문서로 적는다 ---
    write(sub / GATEWAY, page("Component", "결제 게이트웨이", hash_=design_hash, partOf="project", aliases='[결제 GW, "Payment Gateway"]'))
    write(sub / API, page("Component", "결제 API", hash_=design_hash, partOf="project", dependsOn="component/gateway"))
    write(sub / INVOICE, page("Term", "인보이스", hash_=design_hash, about="component/gateway", aliases="[청구서, Invoice]"))
    write(sub / SKIPPED, f'- path: docs/meeting.md\n  hash: "{meeting_hash}"\n')

    # --- 컴파일과 검사: 인덱스가 만들어지고 오류도 경고도 없다. 방금 쓴 것은 더 이상 대상이 아니다 ---
    built = just("onto", "build")
    assert built.returncode == 0, built.stderr
    index = (sub / INDEX).read_text(encoding="utf-8")
    assert all(name in index for name in ("component/gateway.md", "component/api.md", "term/invoice.md"))
    validated = just("onto", "validate")
    assert (validated.returncode, validated.stdout) == (0, ""), validated.stdout + validated.stderr
    drained = just("onto", "status")
    assert (drained.returncode, drained.stdout.strip()) == (0, "새로 생겼거나 바뀐 원본 문서가 없다")

    # --- 질의: 결과의 엔티티가 곧 페이지의 경로다. 추론한 관계(역관계)도 나온다 ---
    page_of = lambda identifier: f"projects/billing/{ONTOLOGY_DIR}/{identifier}.md"  # noqa: E731
    components = just("onto", "query", "SELECT ?e ?t WHERE { ?e a onto:Component ; dcterms:title ?t } ORDER BY ?e")
    assert components.returncode == 0, components.stderr
    assert stdout_rows(components)[1:] == [[page_of("component/api"), "결제 API"], [page_of("component/gateway"), "결제 게이트웨이"]]
    inverse = just("onto", "query", "SELECT DISTINCT ?x WHERE { ?x onto:hasPart ?y }")  # 아무도 hasPart를 쓰지 않았다. partOf의 역으로 추론된 것이다
    assert inverse.returncode == 0 and stdout_rows(inverse)[1:] == [[f"projects/billing/{ONTOLOGY_DIR}/ontology.yaml"]]
    sources = just("onto", "query", "SELECT ?p WHERE { ?e onto:derivedFrom ?s . ?s onto:sourcePath ?p } ORDER BY ?p")
    assert sources.returncode == 0 and set(row[0] for row in stdout_rows(sources)[1:]) == {"docs/design.md"}

    # --- 지식 저장소 안: 복사된 기능으로 그 저장소만 다룬다 ---
    for command, expected in (("build", None), ("validate", ""), ("status", None)):
        inside = just("-f", ".onto/Justfile", command, cwd=sub)
        assert inside.returncode == 0, f"{command}: {inside.stderr}"
        if expected is not None:
            assert inside.stdout == expected
    inside_query = just("-f", ".onto/Justfile", "query", "SELECT ?e WHERE { ?e a onto:Term }", cwd=sub)
    assert inside_query.returncode == 0 and stdout_rows(inside_query)[1:] == [[f"{ONTOLOGY_DIR}/term/invoice.md"]]  # 그 저장소 기준 경로다

    # --- 낡음: 원본 문서가 바뀌면 그것을 근거로 한 페이지가 대상으로 나오고, 해시를 올리면 사라진다 ---
    write(sub / "docs" / "design.md", DESIGN + "\n재시도는 세 번이다.\n")
    changed_hash = git("hash-object", "docs/design.md", cwd=sub).stdout.strip()
    changed = just("onto", "status")
    (row,) = stdout_rows(changed)
    assert row[:4] == ["바뀐 문서", "billing", "docs/design.md", changed_hash]
    assert all(identifier in row[4] for identifier in ("component/gateway", "component/api", "term/invoice"))  # 낡은 페이지
    stale = just("onto", "validate")
    assert stale.returncode == 0 and {line.split("\t")[3] for line in stale.stdout.splitlines()} == {"stale-page"}  # 경고만 있다
    for identifier in ("component/gateway", "component/api", "term/invoice"):
        path = sub / ONTOLOGY_DIR / f"{identifier}.md"
        write(path, path.read_text(encoding="utf-8").replace(design_hash, changed_hash))
    assert just("onto", "validate").stdout == "" and "원본 문서가 없다" in just("onto", "status").stdout

    # --- 커밋: 복사된 기능은 지식 저장소의 git 상태에 나타나지 않는다. 커밋은 사람이 한다 ---
    assert just("onto", "build").returncode == 0
    git("add", "docs/design.md", cwd=sub)  # 원본 문서의 수정은 팀의 커밋이다
    assert git("commit", "-m", "docs: 재시도 정책을 설계에 더한다", cwd=sub).returncode == 0
    untracked = git("status", "--porcelain", "--untracked-files=all", cwd=sub).stdout
    assert ".onto" not in untracked and ".claude" not in untracked  # 복사된 기능은 보이지 않는다
    git("add", "-A", cwd=sub)
    assert git("commit", "-m", "onto(ingest): 결제 설계 문서에서 게이트웨이와 용어 페이지 추가", cwd=sub).returncode == 0
    committed = set(git("ls-files", cwd=sub).stdout.split())
    assert {GATEWAY, API, INVOICE, SKIPPED, INDEX, ".gitignore"} <= committed
    assert not any(path.startswith((".onto/", ".claude/")) for path in committed)
    git("add", "projects/billing")
    assert git("commit", "-m", "chore: billing 지식 갱신").returncode == 0

    # --- 푸시: 관문이 스크립트 검사를 돌려 통과시키고, 지식 저장소가 먼저 올라간 뒤 루트가 올라간다 ---
    overview = just("git", "status")
    assert overview.returncode == 0 and "billing" in overview.stdout
    pushed = just("git", "push")
    assert pushed.returncode == 0, pushed.stdout + pushed.stderr
    assert "푸시 관문: 스크립트 검사에 오류가 없습니다" in pushed.stdout + pushed.stderr
    assert sandbox.git("rev-parse", "refs/heads/main", cwd=remote.url).stdout.strip() == sandbox.head(sub)
    assert sandbox.git("rev-parse", "refs/heads/main", cwd=root.origin).stdout.strip() == sandbox.head(root.work)
    pointer = sandbox.git("rev-parse", "HEAD:projects/billing", cwd=root.work).stdout.strip()
    assert sandbox.git("cat-file", "-t", pointer, cwd=remote.url).stdout.strip() == "commit"  # 루트가 가리키는 커밋이 원격에 있다

    # --- 제거: 푸시까지 마친 저장소는 강제 옵션 없이 흔적까지 완전히 떠난다 ---
    removed = just("repo", "remove", "billing")
    assert removed.returncode == 0, removed.stderr
    assert ".claude" not in removed.stdout + removed.stderr and "무시되는 파일" not in removed.stdout + removed.stderr  # 복사된 스킬은 되살릴 수 없는 파일로 알리지 않는다
    assert not sub.exists()
    assert not (root.work / ".git" / "modules" / "projects" / "billing").exists()
    assert git("ls-files", "--stage", "--", "projects/billing").stdout == ""  # 서브모듈 등록이 사라졌다
    assert "projects/billing" in git("diff", "--cached", "--name-only").stdout  # 제거는 스테이징까지만 한다. 커밋은 사람이 한다
    assert json.loads(just("onto", "rules").stdout)["push-gate"] == {"enabled": True}  # 루트의 기능은 그대로 돈다
