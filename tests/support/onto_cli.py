"""온톨로지 도구의 명령줄 진입점을 견본 페이지 디렉토리에 대고 실행하는 테스트 받침.

스펙의 두 번째 이음매다. 검사 항목별 경우처럼 git 저장소를 통째로 꾸리기엔 수가 많은 것에 쓴다.
견본 디렉토리는 루트 저장소의 모양(`projects/<저장소명>/docs/ontology/…`)만 갖춘 임시 디렉토리이고,
git 저장소일 필요가 없다. 도구는 현재 디렉토리를 루트 저장소로 보고 일한다.

도구는 이 저장소가 추적하는 `onto/` 파일의 사본에서 돈다. 새로 만든 파일은 `git add`해야 보인다.
가상환경은 테스트 세션마다 한 번 만든다. 그래서 의존성을 처음 내려받을 때만 네트워크가 필요하다.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from support.sandbox import SOURCE_REPO, Sandbox, copy_tracked_files

# `just onto`가 부르는 것과 같은 명령줄. 모듈 이름으로 실행하므로 현재 디렉토리와 무관하다.
# `-P`는 현재 디렉토리를 `sys.path` 맨 앞에 넣지 않는다. 지식 저장소 최상위의 `yaml.py` 같은 파일이 의존성을 가리지 않게 한다.
TOOL_COMMAND = ("python", "-P", "-X", "utf8", "-m", "onto_tool")
# 루트 기본 규칙. 도구 디렉토리 안에 있다(지식 저장소에서는 `.onto/rules.yaml`).
RULES_FILE = "rules.yaml"


def copy_onto(sandbox: Sandbox, dest: Path) -> Path:
    """루트 저장소가 추적하는 `onto/` 파일을 `dest` 디렉토리로 복사한다. 지식 저장소의 `.onto/`를 만드는 것과 같다."""
    copy_tracked_files(sandbox, SOURCE_REPO, dest, under="onto")
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
        # 도구 사본은 테스트 세션이 공유한다. 앞 테스트가 남긴 산출물이 보이지 않게 비운다.
        shutil.rmtree(self.build_dir, ignore_errors=True)
        # 루트 기본 규칙도 공유한다. 테스트가 고친 것은 `restore_root_rules`가 되돌린다.
        self._rules_file = tool_dir / RULES_FILE
        self._original_rules = self._rules_file.read_text(encoding="utf-8") if self._rules_file.is_file() else None

    @property
    def env(self) -> dict[str, str]:
        """도구를 실행하는 격리된 환경. `run(env=…)`에 넘길 값을 이 위에 덧붙여 만든다(`env`는 환경 전체를 대신한다)."""
        return dict(self._sandbox.env)

    @property
    def build_dir(self) -> Path:
        """도구가 산출물(컴파일한 그래프)을 두는 곳. 도구 디렉토리 안의 무시되는 디렉토리다."""
        return self._tool_dir / ".build"

    @property
    def graph_file(self) -> Path:
        return self.build_dir / "graph.ttl"

    # --- 루트 기본 규칙 -------------------------------------------------------------

    def root_rules(self) -> str:
        """루트 기본 규칙 파일(`rules.yaml`)의 내용."""
        return self._rules_file.read_text(encoding="utf-8")

    def write_root_rules(self, text: str) -> None:
        """루트 기본 규칙 파일을 통째로 바꾼다. 테스트가 끝나면 되돌려진다."""
        self._rules_file.write_text(text, encoding="utf-8")

    def set_root_check(self, name: str, *, enabled: bool | None = None, severity: str | None = None) -> None:
        """루트 기본 규칙에서 검사 항목 `name`의 켬/끔이나 심각도(`error`, `warning`)를 바꾼다. 항목은 파일에 한 줄로 적혀 있다."""
        text = self.root_rules()
        line = re.compile(rf"^(  {re.escape(name)}: \{{enabled: )(true|false)(, severity: )(error|warning)(\}})$", re.MULTILINE)
        assert line.search(text), f"루트 기본 규칙에 `{name}` 항목의 줄이 없다"
        flag = None if enabled is None else str(enabled).lower()
        self.write_root_rules(line.sub(lambda m: f"{m[1]}{flag or m[2]}{m[3]}{severity or m[4]}{m[5]}", text, count=1))

    def replace_in_root_rules(self, old: str, new: str) -> None:
        """루트 기본 규칙의 글자 `old`를 `new`로 바꾼다. 파일에 `old`가 없으면 테스트가 실패한다."""
        text = self.root_rules()
        assert old in text, f"루트 기본 규칙에 `{old}`가 없다"
        self.write_root_rules(text.replace(old, new, 1))

    def restore_root_rules(self) -> None:
        if self._original_rules is not None:
            self.write_root_rules(self._original_rules)

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

    def build(self, root: Path) -> bytes:
        """`build`를 실행하고 컴파일된 그래프 파일의 내용을 돌려준다. 실패하면 예외를 던진다."""
        result = self.run(root, "build")
        assert result.returncode == 0, result.stderr
        return self.graph_file.read_bytes()

    def query(self, root: Path, sparql: str) -> list[list[str]]:
        """SPARQL SELECT 질의를 실행하고 결과를 행 목록(머리 행 제외)으로 돌려준다. 실패하면 예외를 던진다."""
        result = self.run(root, "query", sparql)
        assert result.returncode == 0, result.stderr
        return parse_table(result.stdout)[1:]


def snapshot(root: Path) -> set[str]:
    """`root` 아래 모든 파일과 디렉토리의 상대 경로. 명령이 작업 트리에 무언가를 남겼는지 앞뒤를 비교하는 데 쓴다."""
    return {p.relative_to(root).as_posix() for p in root.rglob("*")}


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
