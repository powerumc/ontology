"""git을 부르는 코드가 같이 쓰는 것: 사용자의 셸이나 git 훅이 물려주는 환경 때문에 읽는 저장소가 달라지지 않게 한다.

`pre-push` 같은 git 훅 안에서는 `GIT_DIR`이나 `GIT_INDEX_FILE`이 설정되어 있다. 그 환경에서 `git -C <저장소> …`나 `git ls-files`를 부르면
인자로 준 저장소가 아니라 환경 변수가 가리키는 저장소(또는 인덱스)를 읽는다. 도구가 git으로 읽는 것은 언제나 지금 일하는 저장소여야 한다.
사용자 설정(`core.autocrlf` 같은 것)은 결과를 정하는 입력일 수 있어 고정하지 않는다. 고정하는 것은 저장소를 찾는 방식이다.
"""

import os
from pathlib import Path

# 어느 저장소를 읽는지를 바꾸는 환경 변수. 사용자의 셸이나 git 훅(`pre-push` 등)이 물려줄 수 있어 버린다.
LOCATION_VARIABLES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
    "GIT_PREFIX",
    "GIT_SUPER_PREFIX",
    "GIT_INTERNAL_SUPER_PREFIX",
)


def environment(ceiling: Path) -> dict[str, str]:
    """git을 부를 환경. 저장소 위치를 바꾸는 변수를 버리고, `ceiling` 위로는 저장소를 찾아 올라가지 않게 한다.

    `ceiling`은 일하는 저장소의 상위 디렉토리다. 그 저장소가 git 저장소가 아닐 때 더 위의 다른 저장소(홈 디렉토리 전체를 추적하는 저장소 등)를
    대신 읽지 않게 한다. 프롬프트도 막아 인증을 기다리며 멈추지 않게 한다.
    """
    variables = {key: value for key, value in os.environ.items() if key not in LOCATION_VARIABLES}
    variables["GIT_CEILING_DIRECTORIES"] = str(ceiling)
    variables["GIT_TERMINAL_PROMPT"] = "0"
    return variables
