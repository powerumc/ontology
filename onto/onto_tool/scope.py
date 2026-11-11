"""공유 범위: 지식 저장소를 볼 수 있는 대상의 범위와, 한 지식 저장소의 엔티티를 다른 지식 저장소가 참조해도 되는지의 판정.

`ontology.yaml`의 `scope`는 `private`, `team`, `team:<팀 이름>`, `public` 중 하나다. 값은 글자 그대로 읽는다(대소문자를 구분하고 공백을
다듬지 않는다). 팀 이름은 비어 있지 않고 공백과 `:`가 없는 글자다. `team`(이름 없음)과 `team:<팀 이름>`은 서로 다른 팀이다.
공유 범위를 적지 않은 지식 저장소는 가장 좁은 `private`으로 본다(`DEFAULT`).

참조의 방향이 정하는 것:

- 더 넓은 범위의 저장소를 가리키는 것은 된다(`private` -> `team` -> `public`).
- 더 좁은 범위의 저장소를 가리키는 것은 안 된다. 팀 저장소가 비공개 저장소의 이름을 드러내게 된다.
- 같은 범위끼리는 된다. 다만 팀 저장소는 같은 팀(같은 이름, 또는 둘 다 이름 없음)이어야 한다. 다른 팀의 저장소 이름도 드러내선 안 된다.
"""

import re
from dataclasses import dataclass

PRIVATE = "private"
TEAM = "team"
PUBLIC = "public"
# 좁은 것에서 넓은 것으로
_ORDER = (PRIVATE, TEAM, PUBLIC)
# `team:` 뒤에 오는 팀 이름
_TEAM_NAME = re.compile(r"[^\s:]+")

# 값으로 쓸 수 있는 모양. 오류 설명이 보여 준다.
FORMS = "`private`, `team`, `team:<팀 이름>`, `public`"


class ScopeError(ValueError):
    """공유 범위의 값이 틀렸다. 메시지는 이유다."""


@dataclass(frozen=True)
class Scope:
    level: str  # `private`, `team`, `public`
    team: str | None = None  # `team:<팀 이름>`의 팀 이름. `team`만 적었거나 팀이 아니면 None

    def __str__(self) -> str:
        return self.level if self.team is None else f"{self.level}:{self.team}"

    def problem_referencing(self, target: "Scope") -> str | None:
        """이 범위의 지식 저장소가 `target` 범위의 지식 저장소를 가리켜도 되는지. 안 되면 이유를, 되면 None을 돌려준다."""
        mine, theirs = _ORDER.index(self.level), _ORDER.index(target.level)
        if theirs < mine:
            return f"공유 범위가 더 좁다(이 저장소 `{self}`, 가리키는 저장소 `{target}`)"
        if theirs == mine == _ORDER.index(TEAM) and self.team != target.team:
            return f"다른 팀의 저장소다(이 저장소 `{self}`, 가리키는 저장소 `{target}`)"
        return None


DEFAULT = Scope(PRIVATE)


def parse(value: object) -> Scope:
    """`ontology.yaml`의 `scope` 값을 읽는다. 틀리면 `ScopeError`로 이유를 알린다."""
    if not isinstance(value, str):
        raise ScopeError(f"문자열이 아니다(읽힌 값: `{value!r}`)")
    if value in (PRIVATE, TEAM, PUBLIC):
        return Scope(value)
    name = value.removeprefix(f"{TEAM}:")
    if name != value:
        if _TEAM_NAME.fullmatch(name):
            return Scope(TEAM, name)
        raise ScopeError("`team:` 뒤의 팀 이름이 비어 있거나 공백이나 `:`가 들어 있다")
    raise ScopeError("정해진 값이 아니다(대소문자를 구분하고 앞뒤에 공백이 없어야 한다)")
