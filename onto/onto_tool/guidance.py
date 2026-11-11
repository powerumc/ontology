"""프로젝트 지침 파일의 표시된 블록: 지식 저장소를 연 에이전트를 온톨로지 층의 인덱스로 안내한다.

지침 파일은 지식 저장소의 것이다(`CLAUDE.md`, 없으면 `AGENTS.md`). 최신화는 그 안의 표시된 블록만 고치고 블록 밖은 건드리지 않는다(`blocks`).
지침 파일이 둘 다 없으면 `AGENTS.md`를 만들고 블록만 담는다. 둘 다 있으면 블록을 넣을 파일은 `CLAUDE.md`다(`choose`).
지침 파일이 이 저장소 안의 일반 파일을 가리키는 링크이면(`ln -s AGENTS.md CLAUDE.md`) 링크는 두고 대상 파일의 블록을 고친다. 저장소 밖을 가리키거나
대상이 없는 링크는 따라가지 않고 건너뛴다. 이미 블록이 든 다른 후보 파일(`holds_block`)은 그 자리에서 내용만 맞춘다. 최신화가 만든 `AGENTS.md`를 팀이 커밋한 뒤 `CLAUDE.md`를 만들어도 옛 블록이
굳지 않고, 블록이 둘로 늘어나지도 않는다. 블록이 없는 후보 파일에는 새로 만들지 않고, 블록을 지우거나 다른 파일로 옮기지도 않는다.

블록은 이 저장소를 따로 클론한 사람과 에이전트도 읽는다. 따로 클론한 저장소에는 복사된 기능(`.onto/`)이 없으므로 블록은 상태와 무관하게 같은 글이고,
없어도 뜻이 통해야 한다.

- 인덱스(`docs/ontology/index.md`)는 이 저장소가 커밋하는 파일이라 어느 클론에나 있다. 블록은 이것을 먼저 가리킨다.
- 복사된 기능에 속한 것(규약 문서, 스킬, `just -f .onto/Justfile …`)은 "있으면" 쓰라고만 안내한다. 없는 파일을 반드시 읽으라고 하지 않는다.
- 블록은 온톨로지에 관한 것만 담는다. 루트 저장소나 다른 지식 저장소는 언급하지 않는다. 이 저장소만 다루는 글이다.
"""

import os
from pathlib import Path

from .blocks import MarkedBlock

# 프로젝트 지침 파일 후보. 앞의 것이 먼저다.
CANDIDATES = ("CLAUDE.md", "AGENTS.md")
# 후보가 하나도 없을 때 만드는 지침 파일.
DEFAULT = "AGENTS.md"

# 마크다운에서 보이지 않는 HTML 주석으로 표시한다. 시작 표시 줄의 설명은 블록을 손으로 고치지 말라는 뜻이다.
BLOCK = MarkedBlock("<!-- onto:begin", "<!-- onto:end -->", " 온톨로지 층 안내. 도구가 이 블록만 고치므로 블록 안을 손으로 고치지 않는다 -->")

# `.onto/`나 `.claude/`를 처음 가리키기 전의 줄은 어느 클론에서나 맞아야 한다. 복사된 기능의 안내는 이 줄 뒤에 온다.
COPIED_FEATURES = "복사된 기능이 있으면"

BODY = (
    "## 온톨로지 층",
    "",
    "이 저장소의 지식은 `docs/ontology/`에 페이지로 정리되어 있다. 계획, 정책, 용어, 결정, 구현 결과, 구성 요소를 찾을 때는 "
    "원본 문서를 처음부터 읽지 말고 인덱스에서 시작한다.",
    "",
    "- 인덱스는 `docs/ontology/index.md`다. 페이지 목록이고, 링크를 따라 페이지를 연다.",
    "- 페이지는 마크다운 파일이다. 맨 위의 frontmatter가 구조화된 속성(`class`, `title`, 관계)이고 그 뒤가 본문이다.",
    "- 페이지는 원본 문서를 정리한 것이다. 근거는 페이지의 `derivedFrom`이 가리키는 원본 문서에서 확인한다.",
    "",
    f"{COPIED_FEATURES}(`.onto/` 디렉토리. 이 저장소의 커밋에 들어가지 않는 사본이라 손으로 고치지 않는다) 다음을 쓴다. "
    "없으면 건너뛰고 위의 인덱스와 페이지를 파일로 읽는다.",
    "",
    "- 페이지를 쓰거나 고칠 때는 규약 문서 `.onto/template/conventions.md`를 따른다. 클래스별 견본은 `.onto/template/`에 있다.",
    "- `.claude/skills/onto-*/`에 스킬이 있으면 ingest, 질의, 검사를 그 스킬로 한다.",
    "- 명령은 이 저장소의 최상위 디렉토리에서 `just -f .onto/Justfile <명령>`으로 부른다.",
    "  - `validate`: 스크립트 검사. 페이지를 고친 뒤 돌려 오류가 없게 한다.",
    "  - `build`: 페이지를 컴파일하고 인덱스를 다시 만든다.",
    "  - `query '<SPARQL>'`: 지식을 SPARQL로 질의한다.",
    "  - `status`: 새로 생겼거나 바뀐 원본 문서를 보여 준다.",
)


def holds_block(data: bytes) -> bool:
    """지침 파일의 글(`data`)에 표시된 블록이 있는가. 시작 표시나 끝 표시 줄이 하나라도 있으면 있는 것이다.

    표시가 짝이 맞지 않는 파일도 블록이 있는 파일로 본다. 그런 파일은 고칠 수 없다고 보고해야 하고, 모르는 척 두면 옛 블록이 조용히 굳는다.
    """
    return any(BLOCK.is_begin(line) or BLOCK.is_end(line) for line in data.split(b"\n"))


def choose(repo: Path) -> str:
    """`repo`(지식 저장소)의 프로젝트 지침 파일 이름. `CLAUDE.md`가 있으면 그것, 없고 `AGENTS.md`가 있으면 그것, 둘 다 없으면 `AGENTS.md`(만들 파일)다.

    이름이 있으면 있는 것으로 본다. 깨진 심볼릭 링크나 디렉토리도 그렇다. 그런 이름을 건너뛰고 다른 파일에 쓰면 팀이 읽는 지침 파일이 아닌 곳에 블록이 생긴다.
    링크가 어디를 가리키고 쓸 수 있는지는 부르는 쪽이 따진다(`sync._guidance_target`).
    """
    return next((name for name in CANDIDATES if os.path.lexists(repo / name)), DEFAULT)
