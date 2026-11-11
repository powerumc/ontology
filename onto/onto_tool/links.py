r"""마크다운 본문의 링크: 어떤 대상을 가리키는지 찾고, 그 대상이 지식 저장소 밖의 파일인지 가린다.

링크는 다섯 모양을 찾는다: 인라인 링크와 이미지(`[글](대상)`, `![글](대상)`), 참조 정의(`[이름]: 대상`), 자동 링크(`<file:///…>`),
HTML 태그의 `href`와 `src`(따옴표가 없어도 된다. 태그 밖의 평문 `src=…`는 링크가 아니다). 링크로 보지 않는 글: 코드 블록(```나 ~~~로 둘러싼 것,
목록 안에서 들여쓴 것 포함), 인라인 코드(`…`), HTML 주석(`<!-- … -->`). 인라인 코드와 HTML 주석은 먼저 시작하는 쪽이 이긴다(렌더러가 왼쪽부터
읽는 것과 같다). 그래서 코드 안의 `<!--`는 주석을 열지 않고, 주석 안의 백틱은 코드를 열지 않는다. 대상은 본문에 적힌 글자 그대로 돌려준다(제목, 꺾쇠는 뗀다).

울타리 코드 블록은 여는 줄(0칸 이상 들여쓴 ```나 ~~~)과 같은 글자로 3개 이상인 닫는 줄 사이다. 닫는 줄은 여는 줄보다 3칸까지만 더 들여쓸 수 있다
(CommonMark와 같다). 그보다 더 들여쓴 줄은 코드 안의 글이다. 닫는 줄이 없으면 본문 끝까지 코드이지만, 4칸 이상 들여써 연 울타리가 닫히지 않으면
울타리가 아니라 들여쓴 코드 블록 안의 글로 본다(그 뒤의 링크를 숨기지 않는다).

한계: 4칸 들여쓴 코드 블록(울타리 없는 것)은 목록의 이어지는 줄과 구별하기 어려워 코드로 보지 않는다. 그 안의 링크는 링크로 본다.
닫히지 않은 HTML 주석은 주석으로 보지 않는다(뒤의 링크를 숨기지 않는다).

지식 저장소 밖의 파일을 가리키는 대상은 다음이다. 지식 저장소가 단독으로 열리면 깨지거나 다른 저장소의 위치를 드러낸다.

- 절대 경로(`/…`, `C:\…`, `C:/…`)와 `file:` 주소. `/docs/design.md`처럼 저장소 루트 기준으로 쓴 링크도 절대 경로로 본다.
  웹 호스트(GitHub)는 저장소 루트로, 편집기는 파일 시스템 루트로 읽어 어느 쪽인지 정할 수 없어 보수적으로 막는다. 링크는 페이지 기준 상대 경로로 쓴다.
- 페이지가 있는 디렉토리에서 상대 경로를 풀면 지식 저장소의 루트 위로 나가는 것(`../`를 너무 많이 올라간다). `\`는 `/`로 읽는다.
  웹 브라우저가 http(s) 주소의 `\`를 `/`로 읽기 때문이다.

`http`, `https`, `mailto`처럼 파일이 아닌 주소, `//host/…`(스킴 없는 주소), 문서 안의 조각(`#제목`)은 파일이 아니라 보지 않는다.
`<저장소 이름>:<식별자>` 모양의 링크 대상은 다른 지식 저장소를 가리키는 교차 참조라 공유 범위 검사(`checks/scopes.py`)가 본다.
경로는 글자 그대로 풀어 따진다. 지식 저장소 안의 심볼릭 링크가 밖을 가리키는지는 보지 않는다. 대상 파일이 있는지도 따지지 않는다.
"""

import posixpath
import re
from urllib.parse import unquote

# 울타리는 들여쓴 것도 연다(목록 안의 코드 블록). 백틱 울타리의 같은 줄에 백틱이 또 있으면 울타리가 아니라 인라인 코드다.
_FENCE_OPEN = re.compile(r"([ \t]*)(`{3,}(?![^\n]*`)|~{3,})")
_FENCE_CLOSE_EXTRA_INDENT = 3  # 닫는 줄이 여는 줄보다 더 들여쓸 수 있는 칸
_FENCE_INDENTED_CODE = 4  # 이만큼 들여써 연 울타리가 닫히지 않으면 울타리가 아니다
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`).+?(?<!`)\1(?!`)", re.DOTALL)
# 인라인 코드와 HTML 주석 가운데 먼저 시작하는 것이 이긴다. 인라인 코드의 짝(`\1`)이 첫 그룹이라 앞에 둔다.
_CODE_OR_COMMENT = re.compile(f"{_INLINE_CODE.pattern}|{_HTML_COMMENT.pattern}", re.DOTALL)
# `<` 바로 뒤에 영문자로 시작하는 태그 이름이 오고 공백, `/`, `>`로 이어지는 태그(`<https://…>` 같은 자동 링크는 아니다). 속성 값의 따옴표 안에는 `>`가 있을 수 있다.
_HTML_TAG = re.compile(r"""<[A-Za-z][A-Za-z0-9-]*(?=[\s/>])(?:[^<>"']|"[^"]*"|'[^']*'|["'])*>""")
_REFERENCE_DEFINITION = re.compile(r"^ {0,3}\[[^\]\n]+\]:[ \t]*(<[^>\n]*>|\S+)", re.MULTILINE)
_AUTOLINK = re.compile(r"<([A-Za-z][A-Za-z0-9+.-]*:[^<>\s]*)>")
_HTML_ATTRIBUTE = re.compile(r"""\b(?:href|src)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'<>=`]+))""", re.IGNORECASE)
_SCHEME = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*):")
_DRIVE = re.compile(r"[A-Za-z]:[\\/]")


def destinations(body: str) -> list[str]:
    """`body`가 링크하는 대상. 코드 안은 뺀다. 같은 대상은 한 번만, 처음 나온 순서로 돌려준다."""
    text = _CODE_OR_COMMENT.sub(_blank, _without_code_blocks(body))
    found: list[tuple[int, str]] = []
    for match in re.finditer(r"\]\(", text):
        found.append((match.start(), _inline_destination(text, match.end())))
    for match in _REFERENCE_DEFINITION.finditer(text):
        found.append((match.start(1), match[1].removeprefix("<").removesuffix(">")))
    for match in _AUTOLINK.finditer(text):
        found.append((match.start(1), match[1]))
    for tag in _HTML_TAG.finditer(text):
        for match in _HTML_ATTRIBUTE.finditer(tag[0]):
            found.append((tag.start() + match.start(), next(group for group in match.groups() if group is not None)))
    return list(dict.fromkeys(destination for _, destination in sorted(found) if destination))


def _blank(match: re.Match[str]) -> str:
    """인라인 코드는 같은 길이의 공백으로, HTML 주석은 공백 하나로 바꾼다."""
    return " " * len(match[0]) if match[1] is not None else " "


def _width(indent: str) -> int:
    return len(indent.expandtabs(4))


def _without_code_blocks(body: str) -> str:
    """울타리 코드 블록(```, ~~~)의 줄을 뺀다. 닫히지 않으면 끝까지 코드다(4칸 이상 들여써 연 것은 울타리로 보지 않는다)."""
    lines = body.splitlines()
    kept: list[str] = []
    index = 0
    while index < len(lines):
        opening = _FENCE_OPEN.match(lines[index])
        if opening is None:
            kept.append(lines[index])
            index += 1
            continue
        closing = _fence_closing(lines, index, _width(opening[1]), opening[2])
        if closing is None and _width(opening[1]) >= _FENCE_INDENTED_CODE:
            kept.append(lines[index])  # 들여쓴 코드 블록 안의 글이다. 울타리로 보면 본문 끝까지 링크를 숨긴다
            index += 1
            continue
        index = len(lines) if closing is None else closing + 1
    return "\n".join(kept)


def _fence_closing(lines: list[str], opened: int, indent: int, fence: str) -> int | None:
    """`opened`째 줄에서 연 울타리(`fence`, 들여쓰기 `indent`칸)를 닫는 줄의 번호. 닫는 줄이 없으면 None이다."""
    closer = re.compile(rf"([ \t]*){re.escape(fence[0])}{{{len(fence)},}}[ \t]*")
    for number in range(opened + 1, len(lines)):
        closing = closer.fullmatch(lines[number])
        if closing and _width(closing[1]) <= indent + _FENCE_CLOSE_EXTRA_INDENT:
            return number
    return None


def _inline_destination(text: str, start: int) -> str:
    """`](` 바로 뒤(`start`)에서 인라인 링크의 대상을 읽는다. 뒤에 붙은 제목은 뗀다. 대상이 없으면 빈 글자다."""
    index = start
    while index < len(text) and text[index] in " \t\n":
        index += 1
    if text[index : index + 1] == "<":
        end = text.find(">", index)
        newline = text.find("\n", index)
        return text[index + 1 : end] if end != -1 and (newline == -1 or end < newline) else ""
    depth = 0  # 대상 안의 괄호는 짝이 맞으면 대상의 일부다
    end = index
    while end < len(text) and not text[end].isspace():
        if text[end] == "(":
            depth += 1
        elif text[end] == ")":
            if depth == 0:
                break
            depth -= 1
        end += 1
    return text[index:end]


def outside_reason(page_directory: str, destination: str) -> str | None:
    """페이지의 링크 대상 `destination`이 지식 저장소 밖의 파일이면 그 이유를, 아니면 None을 돌려준다.

    `page_directory`는 지식 저장소 루트 기준 페이지가 있는 디렉토리의 경로(`docs/ontology/component`)다.
    """
    target = destination.strip()
    if target.startswith("//"):
        return None  # 스킴 없는 주소(`//example.com/a`)
    if scheme := _SCHEME.match(target):
        if _DRIVE.match(target):
            return "윈도우의 절대 경로다"
        return "`file:` 주소다" if scheme[1].lower() == "file" else None  # http, https, mailto 같은 주소는 파일이 아니다
    path = unquote(re.split(r"[#?]", target, maxsplit=1)[0]).replace("\\", "/")
    if not path:
        return None  # 문서 안의 조각(`#제목`)
    if path.startswith("/"):
        return "절대 경로다"
    resolved = posixpath.normpath(posixpath.join(page_directory, path))
    if resolved == ".." or resolved.startswith("../"):
        return "페이지에서 상대 경로를 풀면 지식 저장소의 루트 위로 나간다"
    return None
