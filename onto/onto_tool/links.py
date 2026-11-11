r"""마크다운 본문의 링크: 어떤 대상을 가리키는지 찾고, 그 대상이 지식 저장소 밖의 파일인지 가린다.

링크는 다섯 모양을 찾는다: 인라인 링크와 이미지(`[글](대상)`, `![글](대상)`), 참조 정의(`[이름]: 대상`. 대상 뒤가 비었거나 제목뿐일 때만이고,
각주 정의 `[^1]: …`와 `[주의]: 이 값은 …` 같은 문장은 링크가 아니다), 자동 링크(`<file:///…>`),
HTML 태그의 `href`와 `src`(따옴표가 없어도 된다. 태그 밖의 평문 `src=…`는 링크가 아니다. 속성 이름이 `href`·`src`·`xlink:href`인 것만 보므로 `data-src`는 링크가 아니고,
다른 속성의 따옴표 값 안에 든 `href=…`도 링크가 아니다). 링크로 보지 않는 글: 코드 블록(```나 ~~~로 둘러싼 것,
목록 안에서 들여쓴 것 포함), 인라인 코드(`…`), HTML 주석(`<!-- … -->`). 인라인 코드와 HTML 주석은 먼저 시작하는 쪽이 이긴다(렌더러가 왼쪽부터
읽는 것과 같다). 그래서 코드 안의 `<!--`는 주석을 열지 않고, 주석 안의 백틱은 코드를 열지 않는다. 대상은 본문에 적힌 글자 그대로 돌려준다(제목, 꺾쇠는 뗀다).

울타리 코드 블록은 여는 줄(0칸 이상 들여쓴 ```나 ~~~)과 같은 글자로 3개 이상인 닫는 줄 사이다. 닫는 줄은 여는 줄보다 3칸까지만 더 들여쓸 수 있다
(CommonMark와 같다). 그보다 더 들여쓴 줄은 코드 안의 글이다. 닫는 줄이 없으면 본문 끝까지 코드이지만, 4칸 이상 들여써 연 울타리가 닫히지 않으면
울타리가 아니라 들여쓴 코드 블록 안의 글로 본다(그 뒤의 링크를 숨기지 않는다).

줄은 `\n`, `\r\n`, `\r`로만 나눈다. U+2028 같은 유니코드 줄 구분 문자 뒤의 ```는 줄 맨 앞이 아니라 울타리를 열지 않는다.

한계: 4칸 들여쓴 코드 블록(울타리 없는 것)은 목록의 이어지는 줄과 구별하기 어려워 코드로 보지 않는다. 그 안의 링크는 링크로 본다.
닫히지 않은 HTML 주석은 주석으로 보지 않는다(뒤의 링크를 숨기지 않는다).

지식 저장소 밖의 파일을 가리키는 대상은 다음이다. 지식 저장소가 단독으로 열리면 깨지거나 다른 저장소의 위치를 드러낸다.

- 절대 경로(`/…`, `C:\…`, `C:/…`)와 `file:` 주소. `/docs/design.md`처럼 저장소 루트 기준으로 쓴 링크도 절대 경로로 본다.
  웹 호스트(GitHub)는 저장소 루트로, 편집기는 파일 시스템 루트로 읽어 어느 쪽인지 정할 수 없어 보수적으로 막는다. 링크는 페이지 기준 상대 경로로 쓴다.
- 페이지가 있는 디렉토리에서 상대 경로를 풀면 지식 저장소의 루트 위로 나가는 것(`../`를 너무 많이 올라간다). `\`는 `/`로 읽는다.
  웹 브라우저가 http(s) 주소의 `\`를 `/`로 읽기 때문이다.

`http`, `https`, `mailto`처럼 파일이 아닌 주소, `//host/…`(스킴 없는 주소), 문서 안의 조각(`#제목`)은 파일이 아니라 보지 않는다.
`<저장소 이름>:<식별자>` 모양의 링크 대상은 다른 지식 저장소를 가리키는 교차 참조(`cross_reference`)라 공유 범위 검사(`checks/scopes.py`)와
참조 검사(`checks/references.py`)가 본다.
경로는 글자 그대로 풀어 따진다. 지식 저장소 안의 심볼릭 링크가 밖을 가리키는지는 보지 않는다. 지식 저장소 안을 가리키는 상대 링크(`local_target`)의
대상이 있는지는 참조 검사가 본다.
"""

import html
import posixpath
import re
import string
from urllib.parse import unquote

from .textfile import split_lines

# 울타리는 들여쓴 것도 연다(목록 안의 코드 블록). 백틱 울타리의 같은 줄에 백틱이 또 있으면 울타리가 아니라 인라인 코드다.
_FENCE_OPEN = re.compile(r"([ \t]*)(`{3,}(?![^\n]*`)|~{3,})")
_FENCE_CLOSE_EXTRA_INDENT = 3  # 닫는 줄이 여는 줄보다 더 들여쓸 수 있는 칸
_FENCE_INDENTED_CODE = 4  # 이만큼 들여써 연 울타리가 닫히지 않으면 울타리가 아니다
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`).+?(?<!`)\1(?!`)", re.DOTALL)
# 인라인 코드와 HTML 주석 가운데 먼저 시작하는 것이 이긴다. 인라인 코드의 짝(`\1`)이 첫 그룹이라 앞에 둔다.
_CODE_OR_COMMENT = re.compile(f"{_INLINE_CODE.pattern}|{_HTML_COMMENT.pattern}", re.DOTALL)
# `<` 바로 뒤에 영문자로 시작하는 태그 이름이 오고 공백, `/`, `>`로 이어지는 태그(`<https://…>` 같은 자동 링크는 아니다). 따옴표는 HTML 토크나이저처럼 `=` 바로 뒤
# (공백은 건너뛴다)에서만 속성 값을 열고, 그 값 안에는 `>`가 있을 수 있다. 다른 따옴표(`doesn't`의 아포스트로피, 따옴표 없는 값 `alt=don't` 안의 따옴표)는 그냥 글자다.
# 따옴표가 값을 여는 자리가 `=` 뒤로 정해져 있어 "짝의 시작"과 "외톨이" 두 가지로 읽힐 일이 없다. 그래서 반복을 독점으로(`*+`) 두어 한 번 읽은 것을 되돌리지 않아도
# 되고, `>`가 없을 때 따옴표를 나누는 모든 방법을 시도하는 지수 시간이 생기지 않는다(한 번에 앞으로만 읽는다).
_HTML_TAG = re.compile(r"""<[A-Za-z][A-Za-z0-9-]*+(?=[\s/>])(?:=\s*+(?:"[^"]*+"|'[^']*+')|[^<>])*+>""")
# 참조 정의: 줄머리에 `[이름]: 대상`이고, 대상 뒤가 비었거나 제목(`"…"`, `'…'`, `(…)`)뿐이다(CommonMark). 대상 뒤에 다른 글이 이어지면 정의가 아니라
# 문장이다(`[주의]: 이 값은 …`). 이름이 `^`로 시작하는 `[^1]: …`은 각주 정의라 링크가 아니다.
_REFERENCE_DEFINITION = re.compile(
    r"""^ {0,3}\[(?!\^)[^\]\n]+\]:[ \t]*(<[^>\n]*>|\S+)(?:[ \t]+(?:"[^"\n]*"|'[^'\n]*'|\([^)\n]*\)))?[ \t]*$""", re.MULTILINE
)
_AUTOLINK = re.compile(r"<([A-Za-z][A-Za-z0-9+.-]*:[^<>\s]*)>")
# 태그 안의 속성을 앞에서부터 하나씩 읽는다. 이름은 공백, `/`, `>`, `=` 전까지이고, 값은 `=` 바로 뒤(공백은 건너뛴다)의 따옴표 값이나 공백과 `>` 전까지의 따옴표 없는 값이다.
# 속성 이름과 값을 따로 읽어야 다른 속성의 따옴표 값 안에 든 `href=`나 `data-src` 같은 이름을 링크로 잡지 않는다. 한 번 읽은 글자는 되돌아가 다시 읽지 않아 입력 길이에 비례한다.
_HTML_TAG_NAME = re.compile(r"<[A-Za-z][A-Za-z0-9-]*+")
_HTML_ATTRIBUTE = re.compile(r"""(?P<name>[^\s/>=]++)(?:\s*+=\s*+(?:"(?P<double>[^"]*+)"|'(?P<single>[^']*+)'|(?P<bare>[^\s>]++)))?""")
# 링크를 담는 속성. `xlink:href`는 SVG의 링크 속성이다.
_LINK_ATTRIBUTES = frozenset({"href", "src", "xlink:href"})
_SCHEME = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*):")
_DRIVE = re.compile(r"[A-Za-z]:[\\/]")
# 조각(`#제목`)이나 질의(`?…`)를 여는 글자. 이스케이프한 것(`\#`)과 숫자 엔티티(`&#38;`)의 `#`은 아니다.
_QUERY_OR_FRAGMENT = re.compile(r"(?<![\\&])[#?]")
# 링크 대상 안의 Markdown 백슬래시 이스케이프(문장 부호 앞의 `\`)와 HTML 엔티티. 한 번에 훑어, 이스케이프한 `\&amp;`가 엔티티로 풀리지 않게 한다.
# `.`, `/`, `\` 앞의 `\`는 풀지 않는다. 그 `\`는 경로 구분자(`..\term\a.md`)로 읽는다.
_ESCAPABLE = frozenset(string.punctuation)  # Markdown이 백슬래시로 이스케이프할 수 있는 글자
_ESCAPES = _ESCAPABLE - {".", "/", "\\"}
_ESCAPE_OR_ENTITY = re.compile(r"\\([" + re.escape(string.punctuation) + r"])|&(?:#[0-9]+|#[xX][0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]*);")


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
        for match in _HTML_ATTRIBUTE.finditer(tag[0], _HTML_TAG_NAME.match(tag[0]).end()):
            if match["name"].lower() in _LINK_ATTRIBUTES and (value := _attribute_value(match)) is not None:
                found.append((tag.start() + match.start(), value))
    return list(dict.fromkeys(destination for _, destination in sorted(found) if destination))


def _attribute_value(match: re.Match[str]) -> str | None:
    """`_HTML_ATTRIBUTE`가 읽은 속성의 값. 값이 없는 속성(`<a href>`)은 None이다."""
    return next((value for value in match.group("double", "single", "bare") if value is not None), None)


def _blank(match: re.Match[str]) -> str:
    """인라인 코드는 같은 길이의 공백으로, HTML 주석은 공백 하나로 바꾼다."""
    return " " * len(match[0]) if match[1] is not None else " "


def _width(indent: str) -> int:
    return len(indent.expandtabs(4))


def _without_code_blocks(body: str) -> str:
    """울타리 코드 블록(```, ~~~)의 줄을 뺀다. 닫히지 않으면 끝까지 코드다(4칸 이상 들여써 연 것은 울타리로 보지 않는다)."""
    lines = split_lines(body)
    kept: list[str] = []
    unclosed: list[tuple[str, int, int]] = []  # 닫는 줄을 끝내 못 찾은 울타리 `(글자, 길이, 들여쓰기)`. 같거나 더 까다로운 울타리는 찾아볼 것도 없다
    index = 0
    while index < len(lines):
        opening = _FENCE_OPEN.match(lines[index])
        if opening is None:
            kept.append(lines[index])
            index += 1
            continue
        char, length, indent = opening[2][0], len(opening[2]), _width(opening[1])
        if any(c == char and length >= n and indent <= i for c, n, i in unclosed):
            closing = None  # 닫는 줄이 없던 앞의 울타리보다 더 까다로워서, 닫는 줄이 있다면 앞의 것도 닫았을 것이다
        else:
            closing = _fence_closing(lines, index, indent, char, length)
            if closing is None:
                # 새 항목이 이미 포함하는 앞의 항목은 뺀다. 목록이 불어나지 않게 한다.
                unclosed = [e for e in unclosed if not (e[0] == char and e[1] >= length and e[2] <= indent)]
                unclosed.append((char, length, indent))
        if closing is None and indent >= _FENCE_INDENTED_CODE:
            kept.append(lines[index])  # 들여쓴 코드 블록 안의 글이다. 울타리로 보면 본문 끝까지 링크를 숨긴다
            index += 1
            continue
        index = len(lines) if closing is None else closing + 1
    return "\n".join(kept)


def _fence_closing(lines: list[str], opened: int, indent: int, char: str, length: int) -> int | None:
    """`opened`째 줄에서 연 울타리(`char`가 `length`개 이상, 들여쓰기 `indent`칸)를 닫는 줄의 번호. 닫는 줄이 없으면 None이다."""
    closer = re.compile(rf"([ \t]*){re.escape(char)}{{{length},}}[ \t]*")
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
    depth = 0  # 대상 안의 괄호는 짝이 맞으면 대상의 일부다. 이스케이프한 괄호(`\\(`)는 세지 않는다
    end = index
    while end < len(text) and not text[end].isspace():
        if text[end] == "\\" and text[end + 1 : end + 2] in _ESCAPABLE:
            end += 2
            continue
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
    path = _path_of(target)
    if not path:
        return None  # 문서 안의 조각(`#제목`)
    if path.startswith("/"):
        return "절대 경로다"
    resolved = posixpath.normpath(posixpath.join(page_directory, path))
    if resolved == ".." or resolved.startswith("../"):
        return "페이지에서 상대 경로를 풀면 지식 저장소의 루트 위로 나간다"
    return None


def local_target(page_directory: str, destination: str) -> str | None:
    """페이지의 링크 대상 `destination`이 가리키는 지식 저장소 안의 파일이나 디렉토리를 지식 저장소 루트 기준 경로(`/`로 구분)로 돌려준다.

    파일을 가리키는 링크가 아니거나(`http`, `mailto` 같은 주소, 교차 참조, 문서 안의 조각) 저장소 밖을 가리키면(`outside_reason`) None이다.
    조각(`#제목`)과 질의(`?…`)는 뗀다. 대상이 있는지는 여기서 따지지 않는다.
    """
    target = destination.strip()
    if outside_reason(page_directory, destination) is not None or target.startswith("//") or _SCHEME.match(target):
        return None
    path = _path_of(target)
    return posixpath.normpath(posixpath.join(page_directory, path)) if path else None


def cross_reference(destination: str) -> tuple[str, str] | None:
    """링크 대상 `destination`이 다른 지식 저장소의 엔티티를 가리키는 `<저장소 이름>:<식별자>` 모양이면 `(저장소 이름, 식별자)`를, 아니면 None을 돌려준다.

    `//`가 뒤따르는 주소(`http://…`)와 파일 경로(윈도우 드라이브, `file:` 주소)는 교차 참조가 아니다. 식별자에서 조각(`#제목`)과 질의(`?…`)는 뗀다.
    `mailto:me@example.com`이나 `tel:+8210…` 같은 스킴이 이 모양이므로, 저장소 이름과 식별자의 모양으로 진짜 교차 참조인지 가리는 것은 부른 쪽의 몫이다.
    """
    target = destination.strip()
    name, separator, rest = target.partition(":")
    if not separator or not name or rest.startswith("//") or _DRIVE.match(target) or name.lower() == "file":
        return None
    return name.strip(), _QUERY_OR_FRAGMENT.split(rest, maxsplit=1)[0].strip()


def _path_of(target: str) -> str:
    """스킴이 없는 링크 대상의 경로 부분. 조각과 질의를 떼고, Markdown 백슬래시 이스케이프와 HTML 엔티티와 퍼센트 인코딩을 풀고, `\\`를 `/`로 읽는다.

    문서 안의 조각(`#제목`)이면 빈 글자다. `.`, `/`, `\\` 앞의 `\\`는 이스케이프가 아니라 경로 구분자다(웹 브라우저가 `\\`를 `/`로 읽는다).
    """
    path = _QUERY_OR_FRAGMENT.split(target, maxsplit=1)[0]
    return unquote(_ESCAPE_OR_ENTITY.sub(_unescape, path)).replace("\\", "/")


def _unescape(match: re.Match[str]) -> str:
    if match[1] is not None:
        return match[1] if match[1] in _ESCAPES else match[0]
    return html.unescape(match[0])
