"""온톨로지 도구의 명령줄 진입점을 견본 페이지 디렉토리에 대고 실행하는 테스트 받침.

스펙의 두 번째 이음매다. 검사 항목별 경우처럼 git 저장소를 통째로 꾸리기엔 수가 많은 것에 쓴다.
견본 디렉토리는 루트 저장소의 모양(`projects/<저장소명>/docs/ontology/…`)만 갖춘 임시 디렉토리이고,
git 저장소일 필요가 없다. 도구는 현재 디렉토리를 루트 저장소로 보고 일한다.

도구는 이 저장소가 추적하는 `onto/` 파일의 사본에서 돈다. 새로 만든 파일은 `git add`해야 보인다.
가상환경은 테스트 세션마다 한 번 만든다. 그래서 의존성을 처음 내려받을 때만 네트워크가 필요하다.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from support.sandbox import SOURCE_REPO, Sandbox

# `just onto`가 부르는 것과 같은 명령줄. 모듈 이름으로 실행하므로 현재 디렉토리와 무관하다.
TOOL_COMMAND = ("python", "-X", "utf8", "-m", "onto_tool")


def copy_onto(sandbox: Sandbox, dest: Path) -> Path:
    """루트 저장소가 추적하는 `onto/` 파일을 `dest` 디렉토리로 복사한다. 지식 저장소의 `.onto/`를 만드는 것과 같다."""
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--", "onto"],
        cwd=SOURCE_REPO,
        env=sandbox.env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for rel in filter(None, listing.split("\0")):
        source = SOURCE_REPO / rel
        if not source.is_file():
            continue  # 지웠지만 아직 스테이지하지 않은 파일
        target = dest / Path(rel).relative_to("onto")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    return dest


def install_tool(sandbox: Sandbox) -> Path:
    """`onto/`의 사본을 `sandbox` 안에 만들고 의존성을 설치한다. 사본의 경로를 돌려준다."""
    tool_dir = copy_onto(sandbox, sandbox.new_dir("tool", "onto"))
    # 설치가 실패하면 첫 테스트가 아니라 여기서 이유와 함께 멈춘다.
    synced = sandbox.run(
        ["uv", "sync", "--locked", "--quiet", "--project", tool_dir], cwd=sandbox.base, check=False
    )
    assert synced.returncode == 0, synced.stderr
    return tool_dir


class OntoCli:
    """견본 루트 디렉토리를 만들고 그 안에서 온톨로지 도구를 실행한다."""

    def __init__(self, sandbox: Sandbox, tool_dir: Path) -> None:
        self._sandbox = sandbox
        self._tool_dir = tool_dir
        self._roots = 0

    def root(self, repos: dict[str, dict[str, str]] | None = None) -> Path:
        """견본 루트 디렉토리를 만든다. `repos`는 `{저장소명: {지식 저장소 안의 파일 경로: 내용}}`이다.

        페이지와 `ontology.yaml`은 지식 저장소 안의 경로(`docs/ontology/…`)로 적는다.
        """
        self._roots += 1
        root = self._sandbox.new_dir("samples", f"root-{self._roots}")
        for name, files in (repos or {}).items():
            for rel, text in files.items():
                target = root / "projects" / name / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
        return root

    def run(
        self, root: Path, *args: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        """`root`를 현재 디렉토리로 삼아 도구를 실행한다. 종료 코드를 보는 테스트가 많아 예외를 던지지 않는다."""
        command = ["uv", "run", "--locked", "--quiet", "--project", self._tool_dir, *TOOL_COMMAND, *args]
        return self._sandbox.run(command, cwd=root, check=False, env=env)

    def query(self, root: Path, sparql: str) -> list[list[str]]:
        """SPARQL SELECT 질의를 실행하고 결과를 행 목록(머리 행 제외)으로 돌려준다. 실패하면 예외를 던진다."""
        result = self.run(root, "query", sparql)
        assert result.returncode == 0, result.stderr
        return parse_table(result.stdout)[1:]


def parse_table(output: str) -> list[list[str]]:
    """질의 출력(탭으로 구분한 표)을 행 목록으로 나눈다. 첫 행은 변수 이름이다."""
    return [line.split("\t") for line in output.splitlines()]


# --- 견본 파일 --------------------------------------------------------------

ONTOLOGY_DIR = "docs/ontology"


def ontology_yaml(name: str, **fields: object) -> dict[str, str]:
    """`ontology.yaml` 하나를 가진 지식 저장소 파일 묶음."""
    return {f"{ONTOLOGY_DIR}/ontology.yaml": _yaml({"name": name, **fields})}


def page(identifier: str, cls: str | None, **fields: object) -> dict[str, str]:
    """페이지 하나. `identifier`는 온톨로지 층 기준 상대 경로에서 확장자를 뺀 것이다. `body`는 본문이다."""
    body = str(fields.pop("body", "본문\n"))
    meta = {"class": cls, **fields} if cls is not None else fields
    return {f"{ONTOLOGY_DIR}/{identifier}.md": f"---\n{_yaml(meta)}---\n\n{body}"}


def repo(name: str, *pages: dict[str, str], **project: object) -> dict[str, str]:
    """`ontology.yaml`과 페이지들로 이루어진 지식 저장소 파일 묶음."""
    files = ontology_yaml(name, **project)
    for p in pages:
        files.update(p)
    return files


def _yaml(mapping: dict[str, object]) -> str:
    # JSON의 문자열과 목록은 YAML의 따옴표 문자열과 흐름 목록이기도 하다. 키도 따옴표로 감싸 `@`로 시작하는 키를 쓸 수 있다.
    return "".join(f"{json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}\n" for k, v in mapping.items())
