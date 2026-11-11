"""규칙: 루트 기본값(`rules.yaml`)과 지식 저장소의 덮어쓰기(`ontology.yaml`의 `rules`).

규칙은 코드를 고치지 않고 바꾸는 값이다. 대상 문서의 범위(`sources`), 검사 항목별 켬/끔과 심각도(`checks`), 푸시 관문(`push-gate`),
중복 처리(`duplicates`), 언어 규칙(`language`). 키의 이름과 값의 종류는 아래 `_schema`가 정하는 한 곳이고, 기본값은 `rules.yaml`에 있다.

- 루트 기본값은 모든 키가 있어야 한다. 모르는 키와 값의 종류가 틀린 값은 오류다(`RulesError`).
- 식별자 형식(`language.identifier-pattern`)은 루트만 정한다. 사용자가 쓴 정규 표현식이라 맞지 않는 긴 식별자에서 지수 시간으로 되돌아가는 모양이면 검사가 끝나지 않는다.
  지식 저장소 하나의 규칙이 루트의 검사와 푸시 관문을 모든 사람에게서 멈추지 못하게 지식 저장소의 `rules`로는 덮어쓸 수 없다(`ROOT_ONLY_RULES`). 루트의 형식은 루트 소유자의 몫이다.
- 지식 저장소는 같은 구조로 바꿀 값만 적는다. 적은 값이 그 저장소의 규칙으로 루트 기본값을 덮어쓰고, 적지 않은 값은 루트를 따른다.
  모르는 키, 값의 종류가 틀린 값, 루트 전용 규칙을 덮어쓰려는 시도는 오류이고, 그럴 때 그 저장소는 덮어쓰기 없이 루트 기본값을 쓴다.
- 이 모듈은 규칙을 읽고 합치기만 한다. 규칙을 쓰는 곳(스크립트 검사, 낡음, 푸시 관문)은 값을 `Rules`에서 꺼내 간다.
"""

import difflib
import re
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

from .textfile import is_missing, load_yaml_text

SEVERITIES = ("error", "warning")
DUPLICATE_NAME_SOURCES = ("title", "aliases")
# 루트만 정할 수 있는 규칙. 지식 저장소가 덮어쓰면 안전장치가 개별 저장소의 규칙으로 꺼진다. 검사 항목 가운데 루트 전용은
# `checks.model.Check.root_only`가 정한다(공유 범위 검사).
# - `push-gate`: 푸시 관문이 저장소의 규칙으로 꺼지지 않게 한다.
# - `language.identifier-pattern`: 식별자 형식은 교차 참조(`<저장소 이름>:<식별자>`)의 문법이기도 해서 저장소마다 다를 이유가 약하고, 사용자가 쓴 정규 표현식이라
#   지식 저장소 하나가 지수 시간으로 되돌아가는 모양을 적으면 루트의 검사와 푸시 관문이 모든 사람에게서 멈춘다.
ROOT_ONLY_RULES = frozenset({("push-gate",), ("language", "identifier-pattern")})


class RulesError(Exception):
    """규칙을 읽을 수 없다. `messages`는 이유이고, 키를 알려 주는 것은 키의 이름(`checks.orphan-page`)으로 시작한다."""

    def __init__(self, *messages: str) -> None:
        super().__init__("\n".join(messages))
        self.messages = list(messages)


# --- 규칙의 모양 -------------------------------------------------------------------


@dataclass(frozen=True)
class CheckRule:
    enabled: bool
    severity: str  # `error` 또는 `warning`

    @property
    def stops_build(self) -> bool:
        """이 검사 항목이 보고하는 읽을 수 없는 파일 때문에 `build`, `query`, `status`가 멈추는가. 켜져 있고 오류일 때만이다.

        `validate`가 오류로 보는 것과 같은 조건이다. 그래서 `validate`가 0으로 끝나면 읽을 수 없는 파일 때문에 `build`가 멈추지 않는다.
        """
        return self.enabled and self.severity == "error"


@dataclass(frozen=True)
class Sources:
    include: tuple[str, ...]
    exclude: tuple[str, ...]


@dataclass(frozen=True)
class PushGate:
    enabled: bool


@dataclass(frozen=True)
class Duplicates:
    compare: tuple[str, ...]  # 이름으로 비교하는 속성: `title`, `aliases`
    ignore_case: bool
    ignore_whitespace: bool


@dataclass(frozen=True)
class Language:
    identifier_pattern: str
    body: str
    aliases: tuple[str, ...]


class Rules:
    """검증을 마친 규칙 하나. 값은 `rules.yaml`과 같은 구조의 `dict`이고, 아래 속성이 종류별로 꺼내 준다."""

    def __init__(self, values: Mapping[str, Any]) -> None:
        self.values = values

    @cached_property
    def sources(self) -> Sources:
        section = self.values["sources"]
        return Sources(tuple(section["include"]), tuple(section["exclude"]))

    @cached_property
    def checks(self) -> dict[str, CheckRule]:
        return {name: CheckRule(rule["enabled"], rule["severity"]) for name, rule in self.values["checks"].items()}

    @cached_property
    def push_gate(self) -> PushGate:
        return PushGate(self.values["push-gate"]["enabled"])

    @cached_property
    def duplicates(self) -> Duplicates:
        section = self.values["duplicates"]
        return Duplicates(tuple(section["compare"]), section["ignore-case"], section["ignore-whitespace"])

    @cached_property
    def language(self) -> Language:
        section = self.values["language"]
        return Language(section["identifier-pattern"], section["body"], tuple(section["aliases"]))

    def overridden_by(self, override: Mapping[str, Any]) -> "Rules":
        """`override`(검증을 마친 부분 규칙)로 값을 덮어쓴 새 규칙. 덮어쓰지 않은 값은 그대로다."""
        return Rules(_merge(self.values, override))


def _merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _merge(value, override[key]) if isinstance(value, Mapping) and key in override else override.get(key, value)
        for key, value in base.items()
    }


# --- 값의 종류 ---------------------------------------------------------------------
# 값 하나를 검증해 정규화한 값을 돌려준다. 맞지 않으면 `ValueError`로 이유를 던진다.


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("`true`나 `false`여야 한다")
    return value


def _severity(value: object) -> str:
    if value not in SEVERITIES:
        raise ValueError(f"{' 또는 '.join(f'`{s}`' for s in SEVERITIES)}여야 한다")
    return str(value)


def _strings(value: object, what: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{what}의 목록이어야 한다")
    return [item.strip() for item in value]


def _globs(value: object) -> list[str]:
    globs = _strings(value, "비어 있지 않은 글롭 문자열")
    for glob in globs:
        # 지식 저장소의 어떤 파일도 저장소 밖의 파일을 가리키지 않는다(ADR 0001). 글롭도 저장소 안을 벗어나지 못한다.
        if glob.startswith("/") or ".." in glob.split("/"):
            raise ValueError(f"글롭 `{glob}`는 지식 저장소 루트 기준의 상대 경로여야 하고 `/`로 시작하거나 `..`를 쓸 수 없다")
    return globs


def _compare(value: object) -> list[str]:
    names = _strings(value, "속성 이름")
    unknown = [name for name in names if name not in DUPLICATE_NAME_SOURCES]
    if not names or unknown:
        allowed = ", ".join(f"`{name}`" for name in DUPLICATE_NAME_SOURCES)
        raise ValueError(f"비교할 속성을 하나 이상 {allowed} 가운데서 적어야 한다")
    return names


# 식별자의 경로 조각이 이 중 하나와 맞는 형식은 받지 않는다. 참조(`<저장소 이름>:<식별자>`)가 그 식별자를 가리키지 못한다.
# `:`는 저장소 이름과의 경계로 읽히고, 참조는 앞뒤 공백을 뗀다.
_UNREFERENCEABLE_SEGMENTS = ("a:b", ":", "a:", ":a", " a", "a ")
# 언어 코드: `ko`, `en`, `pt-BR`, `zh-Hans`
_LANGUAGE_CODE = re.compile(r"[a-z]{2,3}(-[A-Za-z0-9]+)*")


def _pattern(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("정규 표현식 문자열이어야 한다")
    try:
        form = re.compile(value)
    except re.error as exc:
        raise ValueError(f"정규 표현식이 아니다: {exc}") from exc
    if any(form.fullmatch(segment) for segment in _UNREFERENCEABLE_SEGMENTS):
        raise ValueError(
            f"형식 `{value}`는 `:`나 앞뒤 공백이 든 경로 조각을 허용한다. `:`는 교차 참조(`<저장소 이름>:<식별자>`)의 경계이고 "
            "참조는 앞뒤 공백을 떼므로, 그런 식별자의 페이지는 참조로 가리킬 수 없다"
        )
    return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("비어 있지 않은 문자열이어야 한다")
    return value.strip()


def _body_language(value: object) -> str:
    """`source`(원본 문서의 언어를 따른다)이거나 언어 코드."""
    if not isinstance(value, str) or not (value.strip() == "source" or _LANGUAGE_CODE.fullmatch(value.strip())):
        raise ValueError("`source`나 언어 코드(예: `ko`, `en`, `pt-BR`)여야 한다")
    return value.strip()


def _languages(value: object) -> list[str]:
    codes = _strings(value, "언어 코드 문자열")
    if bad := [code for code in codes if not _LANGUAGE_CODE.fullmatch(code)]:
        raise ValueError(f"언어 코드(예: `ko`, `en`, `pt-BR`)의 목록이어야 한다. 아닌 값: {', '.join(f'`{code}`' for code in bad)}")
    return codes


_Schema = dict[str, "_Schema | Callable[[object], object]"]


def _schema(known_checks: Collection[str]) -> _Schema:
    """규칙의 키와 값의 종류. 규칙의 키 이름을 정하는 곳이다. 이름은 `rules.yaml`과 지식 저장소의 `ontology.yaml`이 같이 쓴다."""
    return {
        "sources": {"include": _globs, "exclude": _globs},
        "checks": {name: {"enabled": _boolean, "severity": _severity} for name in known_checks},
        "push-gate": {"enabled": _boolean},
        "duplicates": {"compare": _compare, "ignore-case": _boolean, "ignore-whitespace": _boolean},
        "language": {"identifier-pattern": _pattern, "body": _body_language, "aliases": _languages},
    }


# --- 읽기와 검증 -------------------------------------------------------------------


class _Reader:
    """규칙 하나(루트의 파일 전체, 또는 지식 저장소의 `rules`)를 스키마에 대고 읽는다. 이유는 모두 모은다."""

    def __init__(self, prefix: tuple[str, ...], forbidden: Collection[tuple[str, ...]], *, complete: bool) -> None:
        self.prefix = prefix
        self.forbidden = forbidden
        self.complete = complete  # 스키마의 모든 키가 있어야 한다(루트 기본값)
        self.problems: list[str] = []

    def problem(self, path: tuple[str, ...], reason: str) -> None:
        label = ".".join((*self.prefix, *path))
        self.problems.append(f"`{label}`: {reason}" if label else reason)  # 파일 전체의 문제는 키 이름이 없다

    def read(self, data: object, schema: _Schema, path: tuple[str, ...] = ()) -> dict[str, Any]:
        if not isinstance(data, dict):
            self.problem(path, "키와 값의 목록이 아니다")
            return {}
        result: dict[str, Any] = {}
        for key in data:
            if key not in schema:
                self._unknown(path, str(key), schema)
        for key, node in schema.items():
            here = (*path, key)
            if key not in data:
                if self.complete:
                    self.problem(here, "없다. 기본 규칙에는 모든 키가 있어야 한다")
                continue
            if here in self.forbidden:
                self.problem(here, "루트 전용이라 지식 저장소의 `rules`에서 덮어쓸 수 없다")
                continue
            if isinstance(node, dict):
                result[key] = self.read(data[key], node, here)
                continue
            try:
                result[key] = node(data[key])
            except ValueError as exc:
                self.problem(here, str(exc))
        return result

    def _unknown(self, path: tuple[str, ...], key: str, schema: _Schema) -> None:
        near = difflib.get_close_matches(key, list(schema), n=1)
        hint = f" 혹시 `{near[0]}`?" if near else ""
        if len(schema) <= 8:
            allowed = ", ".join(f"`{name}`" for name in schema)
            self.problem((*path, key), f"정의되지 않은 키다(쓸 수 있는 키: {allowed}).{hint}")
        else:  # 검사 항목처럼 많은 키는 나열하지 않는다
            self.problem((*path, key), f"정의되지 않은 키다.{hint} 검사 항목의 이름은 `just onto validate` 보고의 검사 항목 칸에 나온다")


def load_root_rules(path: Path, *, known_checks: Collection[str]) -> Rules:
    """루트 기본 규칙 파일을 읽는다. 읽을 수 없거나, 모르는 키나 틀린 값이 있거나, 키가 빠졌으면 `RulesError`다."""
    if is_missing(path):
        raise RulesError("루트 기본 규칙 파일이 없다")
    data = load_yaml_text(path, RulesError)
    reader = _Reader((), (), complete=True)
    values = reader.read(data, _schema(known_checks))
    if reader.problems:
        raise RulesError(*reader.problems)
    return Rules(values)


@dataclass(frozen=True)
class RuleSet:
    """루트 기본 규칙과, 지식 저장소(서브모듈 디렉토리 이름)마다 덮어쓴 규칙. 스크립트 검사가 저장소마다 규칙을 꺼내 쓴다."""

    root: Rules
    repositories: Mapping[str, Rules]  # 덮어쓰기가 있고 맞는 저장소의 것만 든다
    problems: Mapping[str, tuple[str, ...]]  # 덮어쓰기가 틀린 저장소 -> 이유. 그 저장소는 루트 기본값을 쓴다

    def of(self, repository: str) -> Rules:
        return self.repositories.get(repository, self.root)


def build_rule_set(
    root: Rules, overrides: Mapping[str, object], *, known_checks: Collection[str], root_only_checks: Collection[str] = ()
) -> RuleSet:
    """`overrides`(저장소 -> `ontology.yaml`의 `rules` 값)를 읽어 저장소별 규칙을 만든다."""
    repositories: dict[str, Rules] = {}
    problems: dict[str, tuple[str, ...]] = {}
    for repository, override in overrides.items():
        values, reasons = read_override(override, known_checks=known_checks, root_only_checks=root_only_checks)
        if reasons:
            problems[repository] = tuple(reasons)
        else:
            repositories[repository] = root.overridden_by(values)
    return RuleSet(root, repositories, problems)


def read_override(
    override: object, *, known_checks: Collection[str], root_only_checks: Collection[str] = ()
) -> tuple[dict[str, Any], list[str]]:
    """지식 저장소의 `rules` 값을 읽어 `(검증을 마친 부분 규칙, 이유 목록)`을 돌려준다. 이유가 있으면 부분 규칙은 쓰지 않는다."""
    forbidden = {*ROOT_ONLY_RULES, *(("checks", name) for name in root_only_checks)}
    reader = _Reader(("rules",), forbidden, complete=False)
    values = reader.read(override, _schema(known_checks))
    return values, reader.problems
