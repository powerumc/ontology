"""도구 자신의 디렉토리와 그 안의 위치. 루트 저장소에서는 `onto/`, 지식 저장소에서는 복사된 `.onto/`다.

산출물도 이 디렉토리 안에 둔다. 지식 저장소의 작업 트리(`.onto/` 밖)에는 아무것도 남기지 않는다.
`.build/`는 루트 저장소의 `.gitignore`가 제외하고, `.onto/` 전체는 지식 저장소의 `.gitignore`가 제외한다.
이름을 `build/`로 하지 않는 것은 하위 디렉토리의 `build/`는 코드일 수 있어서 무시하지 않기 때문이다.
"""

from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parents[1]
VOCAB_DIR = TOOL_DIR / "vocab"
BUILD_DIR = TOOL_DIR / ".build"
GRAPH_FILE = BUILD_DIR / "graph.ttl"
# 모든 지식 저장소를 모은 전체 인덱스. 빌드 산출물이라 커밋하지 않는다. 지식 저장소 하나의 인덱스는 그 저장소의 온톨로지 층에 있다.
ALL_INDEX_FILE = BUILD_DIR / "index.md"
