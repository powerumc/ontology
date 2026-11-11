"""도구가 일하는 루트 저장소의 모양: 지식 저장소를 찾는 곳.

도구는 현재 디렉토리를 루트 저장소로 본다. `just onto …`는 어디서 부르든 루트 저장소에서 실행된다.
"""

from dataclasses import dataclass
from pathlib import Path

PROJECTS_DIR = "projects"
ONTOLOGY_DIR = Path("docs") / "ontology"
ONTOLOGY_YAML = ONTOLOGY_DIR / "ontology.yaml"
SKIPPED_YAML = ONTOLOGY_DIR / "skipped.yaml"  # 넘긴 문서의 목록. 저장소 소유 파일이고 필요할 때 생긴다


@dataclass(frozen=True)
class Repository:
    """루트 저장소에 붙은 지식 저장소 하나. `directory`는 서브모듈 디렉토리 이름이다."""

    directory: str
    path: Path

    @property
    def ontology_dir(self) -> Path:
        return self.path / ONTOLOGY_DIR


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def relative(self, path: Path) -> str:
        """루트 저장소 기준 경로. 어느 운영체제에서도 같은 모양이 되도록 `/`로 구분한다."""
        return path.relative_to(self.root).as_posix()

    def repositories(self) -> list[Repository]:
        """`projects/` 아래의 지식 저장소 후보를 이름 순으로 돌려준다. 숨김 디렉토리와 파일은 뺀다."""
        projects = self.root / PROJECTS_DIR
        if not projects.is_dir():
            return []
        return [
            Repository(entry.name, entry)
            for entry in sorted(projects.iterdir(), key=lambda e: e.name)
            if entry.is_dir() and not entry.name.startswith(".")
        ]

    def display(self, path: Path) -> str:
        """사용자에게 보여 줄 경로. 루트 저장소 안이면 상대 경로, 밖이면 절대 경로다."""
        return self.relative(path) if path.is_relative_to(self.root) else str(path)
