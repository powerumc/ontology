"""낡음 추적: ingest할 대상, 곧 새로 생겼거나 바뀐 원본 문서를 지식 저장소별로 가려낸다.

대상은 규칙의 `sources`(글롭과 제외 경로)가 가리키는 원본 문서다. 온톨로지 층은 규칙과 무관하게 항상 빠지고(`sources.list_documents`),
지식 저장소가 `ontology.yaml`의 `rules`로 범위를 바꾸면 그 저장소의 목록만 달라진다. 문서마다 현재 해시(작업 트리의 지금 내용)를
페이지의 `derivedFrom`과 넘긴 문서의 목록(`skipped.yaml`)에 적힌 해시와 비교한다.

- 새 문서: 어떤 페이지도 근거로 삼지 않았고 넘긴 문서의 목록에도 없다.
- 바뀐 문서: 기록한 해시와 지금 해시가 다르다. 기록은 문서를 근거로 한 페이지의 `derivedFrom`이거나 넘긴 문서의 목록이다.
  지금 내용을 근거로 한 페이지는 낡지 않았으므로 낡은 페이지만 알린다. 넘겼던 문서를 나중에 페이지로 ingest해 지금 해시를 근거로 한
  페이지가 있으면, 넘긴 문서의 목록에 남은 옛 항목은 무시한다(페이지가 이긴다). 그 문서는 낡은 페이지가 따로 없으면 나오지 않는다.

기록한 경로와 문서의 경로는 유니코드를 NFC로 정규화해 맞춘다. 대소문자는 구분한다. 그러면 파일 시스템에 따라 결과가 달라지지 않는다
(`sources` 모듈 설명).

`derivedFrom`은 페이지가 읽히는 한 컴파일이 읽어 둔 값(`PageRecord.sources`)을 쓴다. 없어진 문서는 여기서 다루지 않는다. 새로 생기거나 바뀐 것이
아니고 읽을 수도 없으므로, 스크립트 검사(`missing-source`, `missing-skipped-source`)가 잡는다. 어떤 파일도 고치지 않는다.
"""

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .compiler import Compiled, RepositoryRecord
from .rules import RuleSet, Sources
from .sources import document_hashes, list_documents, nfc
from .workspace import Workspace

NEW = "새 문서"
CHANGED = "바뀐 문서"
_ORDER = (NEW, CHANGED)  # 보고는 새 문서가 먼저다


@dataclass(frozen=True)
class Entry:
    """ingest 대상 원본 문서 하나."""

    state: str  # `NEW` 또는 `CHANGED`
    repository: str  # 지식 저장소(서브모듈 디렉토리 이름)
    path: str  # 지식 저장소 루트 기준 경로. 그대로 `derivedFrom`의 `path`로 적는다
    hash: str  # 지금 내용의 git 해시. 그대로 `derivedFrom`의 `hash`로 적는다
    detail: str  # 왜 대상인지


def collect(workspace: Workspace, compiled: Compiled, rules: RuleSet) -> tuple[list[Entry], list[str]]:
    """모든 지식 저장소의 ingest 대상을 지식 저장소, 상태(새 문서가 먼저), 경로 순으로 돌려준다. 두 번째 값은 알릴 것이다.

    온톨로지 층이 없거나 `ontology.yaml`을 읽을 수 없는 저장소와, `rules`가 틀린 저장소는 건너뛴다. 틀린 `rules`는 기본 범위로
    대신하지 않는다. 부르는 쪽이 `rules.problems`로 알린다.
    """
    entries: list[Entry] = []
    notices: list[str] = []
    for record in compiled.records:
        if record.has_layer and record.name is not None and record.directory not in rules.problems:
            found, notice = _repository_entries(workspace.root / record.path, record, rules.of(record.directory).sources)
            entries.extend(found)
            if notice and (message := f"{record.label}: {notice}") not in compiled.notices:  # 컴파일이 이미 알린 것은 빼고
                notices.append(message)
    return sorted(entries, key=lambda entry: (entry.repository, _ORDER.index(entry.state), entry.path)), notices


def _repository_entries(repository: Path, record: RepositoryRecord, sources: Sources) -> tuple[list[Entry], str | None]:
    pages: dict[str, list[tuple[str, str]]] = defaultdict(list)  # 경로(NFC) -> 근거로 삼은 페이지(식별자)와 기록한 해시
    for page in record.pages:
        for source in page.sources:
            pages[nfc(source.path)].append((page.identifier, source.hash))
    skipped: dict[str, set[str]] = defaultdict(set)  # 경로(NFC) -> 넘긴 문서의 목록에 적힌 해시
    for source in record.skipped:
        skipped[nfc(source.path)].add(source.hash)

    documents = list_documents(repository, sources)
    hashes, notice = document_hashes(repository, documents)
    entries: list[Entry] = []
    for path in documents:
        current = hashes[path]
        if current is None:  # 목록을 만든 뒤 사라졌거나 읽을 수 없다
            continue
        key = nfc(path)
        if key not in pages and key not in skipped:
            entries.append(Entry(NEW, record.directory, path, current, "어떤 페이지도 근거로 삼지 않았다"))
            continue
        stale = sorted((identifier, recorded) for identifier, recorded in pages.get(key, []) if recorded != current)
        processed = any(recorded == current for _, recorded in pages.get(key, []))  # 지금 내용을 근거로 한 페이지가 있다
        skipped_changed = key in skipped and current not in skipped[key] and not processed
        reasons = []
        if stale:
            shown = ", ".join(f"`{identifier}`(기록한 해시 `{recorded}`)" for identifier, recorded in stale)
            reasons.append(f"낡은 페이지: {shown}")
        if skipped_changed:
            shown = ", ".join(f"`{recorded}`" for recorded in sorted(skipped[key]))
            reasons.append(f"넘긴 문서였지만 내용이 바뀌었다(넘길 때 기록한 해시 {shown})")
        if reasons:
            entries.append(Entry(CHANGED, record.directory, path, current, "; ".join(reasons)))
    return entries, notice
