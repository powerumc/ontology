"""표시된 블록: 지식 저장소가 추적하는 파일 안에서 루트 저장소가 관리하는 부분.

지식 저장소의 `.gitignore`와 프로젝트 지침 파일은 지식 저장소의 것이고, 그 안의 표시된 블록만 루트가 고친다.
블록은 시작 표시 줄과 끝 표시 줄 사이다(표시 줄 포함). 이 모듈은 파일의 바이트 안에서 블록만 바꾼다.

- 블록이 없으면 파일 끝에 덧붙인다. 파일의 기존 내용은 그대로 앞에 남는다.
- 블록이 이미 있으면 그 자리에서 블록의 내용만 바꾼다. 블록 앞뒤는 바이트 하나도 바뀌지 않는다.
- 블록의 내용이 이미 같으면 같은 바이트를 돌려준다. 부르는 쪽이 파일을 다시 쓰지 않을 수 있다.
- 파일이 CRLF를 쓰면 블록도 CRLF로 쓴다. 파일의 인코딩은 따지지 않는다(표시 줄과 블록 내용만 UTF-8로 더한다).
- 표시가 짝이 맞지 않거나 블록이 둘 이상이면 어느 쪽이 블록인지 알 수 없다. 아무것도 바꾸지 않고 `BlockError`로 알린다.
"""

from collections.abc import Sequence
from dataclasses import dataclass


class BlockError(Exception):
    """표시된 블록을 찾을 수 없다. 메시지는 이유다. 파일 이름은 부른 쪽이 붙인다."""


@dataclass(frozen=True)
class MarkedBlock:
    """표시 줄의 모양. 한 파일 형식(주석 문법)마다 하나다."""

    begin: str  # 시작 표시 줄의 앞부분. 이 글자로 시작하고 바로 뒤가 줄 끝이나 공백인 줄이 시작 표시다
    end: str  # 끝 표시 줄 전체
    note: str = ""  # 시작 표시 줄에서 `begin` 뒤에 붙는 글자. 블록을 설명하는 말이다. 앞의 공백은 직접 적는다

    @property
    def begin_line(self) -> str:
        return self.begin + self.note

    def is_begin(self, line: bytes) -> bool:
        marker = self.begin.encode()
        text = line.rstrip(b"\r")
        return text.startswith(marker) and text[len(marker) :][:1] in (b"", b" ", b"\t")

    def is_end(self, line: bytes) -> bool:
        return line.rstrip(b"\r") == self.end.encode()


def replace_block(data: bytes, block: MarkedBlock, body: Sequence[str]) -> bytes:
    """`data`의 표시된 블록 내용을 `body`(줄의 목록)로 바꾼 바이트를 돌려준다. 블록이 없으면 끝에 덧붙인다."""
    eol = b"\r\n" if b"\r\n" in data else b"\n"
    cr = b"\r" if eol == b"\r\n" else b""
    lines = data.split(b"\n")  # CRLF 파일의 줄은 `\r`로 끝난다
    begins = [number for number, line in enumerate(lines) if block.is_begin(line)]
    ends = [number for number, line in enumerate(lines) if block.is_end(line)]

    if not begins and not ends:
        return _append(data, [block.begin_line, *body, block.end], eol)
    if len(begins) != 1 or len(ends) != 1:
        raise BlockError(
            f"시작 표시(`{block.begin}`)가 {len(begins)}개, 끝 표시(`{block.end}`)가 {len(ends)}개라 어느 블록을 고칠지 알 수 없다. "
            "표시가 하나씩 짝을 이루도록 직접 고친 뒤 다시 실행한다"
        )
    first, last = begins[0], ends[0]
    if last < first:
        raise BlockError(f"끝 표시(`{block.end}`)가 시작 표시(`{block.begin}`)보다 앞에 있다. 직접 고친 뒤 다시 실행한다")

    inner = [line.encode() + cr for line in (block.begin_line, *body)]
    closing = block.end.encode() + (b"\r" if lines[last].endswith(b"\r") else b"")  # 파일 끝에 줄바꿈이 없으면 그것도 그대로 둔다
    return b"\n".join([*lines[:first], *inner, closing, *lines[last + 1 :]])


def _append(data: bytes, block_lines: Sequence[str], eol: bytes) -> bytes:
    """`data` 끝에 블록을 덧붙인다. 기존 내용과 블록 사이에 빈 줄 하나를 둔다."""
    head = data
    if head and not head.endswith(b"\n"):
        head += eol
    if head.strip(b"\r\n") and not head.endswith((b"\n\n", b"\n\r\n")):
        head += eol
    return head + b"".join(line.encode() + eol for line in block_lines)
