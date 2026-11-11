"""도구가 일하는 작업 공간의 모양: 지식 저장소를 찾는 곳.

도구는 현재 디렉토리를 작업 공간의 루트로 본다. `just onto …`와 `just -f .onto/Justfile …`은 어디서 부르든 그 저장소의 루트에서 실행된다.
작업 공간이 다루는 범위(`Within`)는 두 가지다. 지식 저장소의 공유 범위(`ontology.yaml`의 `scope`, `scope.Scope`)와는 다른 것이다.

- 루트 저장소: 루트가 현재 디렉토리이고, `projects/` 아래의 모든 지식 저장소를 다룬다. 보고하는 경로는 루트 기준(`projects/billing/docs/…`)이다.
- 지식 저장소 안: 지식 저장소의 루트가 현재 디렉토리이고, 그 저장소 하나만 다룬다. 보고하는 경로는 그 저장소 기준(`docs/…`)이다.
  루트 저장소나 다른 지식 저장소는 보지 않는다.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

PROJECTS_DIR = "projects"
ONTOLOGY_DIR = Path("docs") / "ontology"
ONTOLOGY_YAML = ONTOLOGY_DIR / "ontology.yaml"
SKIPPED_YAML = ONTOLOGY_DIR / "skipped.yaml"  # 넘긴 문서의 목록. 저장소 소유 파일이고 필요할 때 생긴다


class Within(Enum):
    """도구가 어디 안에서 도는가. 복사된 `Justfile`이 어느 쪽으로 불렸는지로 정해 도구에 넘긴다(`--within`). 공유 범위(`scope.Scope`)와 무관하다."""

    ROOT = "root"  # 루트 저장소: `projects/` 아래의 모든 지식 저장소
    REPOSITORY = "repository"  # 지식 저장소 안: 그 저장소 하나

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Repository:
    """지식 저장소 하나. `directory`는 서브모듈 디렉토리 이름이다."""

    directory: str
    path: Path

    @property
    def ontology_dir(self) -> Path:
        return self.path / ONTOLOGY_DIR


class Workspace:
    def __init__(self, root: Path, within: Within = Within.ROOT) -> None:
        self.root = root.resolve()
        self.within = within

    def relative(self, path: Path) -> str:
        """작업 공간의 루트 기준 경로(지식 저장소 안에서는 그 저장소 기준). 어느 운영체제에서도 같은 모양이 되도록 `/`로 구분한다."""
        return path.relative_to(self.root).as_posix()

    def repositories(self) -> list[Repository]:
        """다루는 지식 저장소(후보)를 이름 순으로 돌려준다.

        루트 저장소에서는 `projects/` 아래의 디렉토리다. 숨김 디렉토리와 파일은 뺀다. 지식 저장소 안에서는 그 저장소 하나이고,
        디렉토리 이름은 그 저장소를 둔 디렉토리의 이름이다(루트 저장소에 붙었을 때는 서브모듈 디렉토리 이름과 같다).
        """
        if self.within is Within.REPOSITORY:
            return [Repository(self.root.name, self.root)]
        projects = self.root / PROJECTS_DIR
        if not projects.is_dir():
            return []
        return [
            Repository(entry.name, entry)
            for entry in sorted(projects.iterdir(), key=lambda e: e.name)
            if entry.is_dir() and not entry.name.startswith(".")
        ]

    def display(self, path: Path) -> str:
        """사용자에게 보여 줄 경로. 작업 공간 안이면 상대 경로, 밖이면 절대 경로다."""
        return self.relative(path) if path.is_relative_to(self.root) else str(path)
