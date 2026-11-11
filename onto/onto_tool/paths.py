"""도구 자신의 디렉토리와 그 안의 위치. 루트 저장소에서는 `onto/`, 지식 저장소에서는 복사된 `.onto/`다.

산출물도 이 디렉토리 안에 둔다. 지식 저장소의 작업 트리(`.onto/` 밖)에는 아무것도 남기지 않는다.
`.build/`는 루트 저장소의 `.gitignore`가 제외하고, `.onto/` 전체는 지식 저장소의 `.gitignore`가 제외한다.
이름을 `build/`로 하지 않는 것은 하위 디렉토리의 `build/`는 코드일 수 있어서 무시하지 않기 때문이다.

경로 비교(`real_path`, `is_inside`)도 여기 있다. 지식 저장소의 파일이 심볼릭 링크로 저장소 밖을 가리키는지 컴파일과 `rules` 명령이 같은 판정을 쓴다.
"""

import os
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parents[1]
VOCAB_DIR = TOOL_DIR / "vocab"
RULES_FILE = TOOL_DIR / "rules.yaml"  # 루트 기본 규칙. 지식 저장소에서는 복사된 `.onto/rules.yaml`이 그 저장소의 기본값이다
BUILD_DIR = TOOL_DIR / ".build"
GRAPH_FILE = BUILD_DIR / "graph.ttl"
# 모든 지식 저장소를 모은 전체 인덱스. 빌드 산출물이라 커밋하지 않는다. 지식 저장소 하나의 인덱스는 그 저장소의 온톨로지 층에 있다.
ALL_INDEX_FILE = BUILD_DIR / "index.md"


def real_path(path: Path) -> Path:
    """심볼릭 링크를 모두 따라간 경로. 순환하는 링크는 풀리는 데까지만 풀고 예외를 내지 않는다.

    `Path.resolve()`는 순환하는 링크에서 Python 3.11·3.12는 `RuntimeError`를 내고 3.13은 내지 않는다. 같은 입력의 결과가 버전에 따라
    달라지지 않게 `os.path.realpath`로 푼다(순환하는 링크는 저장소 밖을 가리키는 것이 아니라 읽을 수 없는 파일이다).
    """
    return Path(os.path.realpath(path))


def is_inside(path: Path, real_root: Path) -> bool:
    """`path`가 심볼릭 링크를 모두 따라간 곳이 `real_root`(`real_path`로 푼 경로) 안인가. 따라갈 수 없으면 안이 아니다."""
    try:
        return real_path(path).is_relative_to(real_root)
    except (OSError, ValueError):
        return False
