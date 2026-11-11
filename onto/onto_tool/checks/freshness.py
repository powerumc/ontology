"""낡음과 원본 문서의 기록: 페이지가 근거로 삼은 원본 문서가 바뀌었거나 없어졌는지, 넘긴 문서가 없어졌는지.

페이지의 `derivedFrom`과 넘긴 문서의 목록(`skipped.yaml`)이 적은 해시를, 컴파일이 읽어 둔 원본 문서의 지금 해시
(`RepositoryRecord.document_hashes`: git이 기록하는 blob 해시이고 작업 트리의 현재 내용으로 낸다)와 비교한다.
커밋하지 않은 수정도 달라진 것으로 본다. `sources` 모듈 설명이 해시와 경로 대조의 규칙을 적는다.
대상 범위(규칙의 `sources`)와 상관없이 페이지가 가리키는 문서는 모두 본다. 범위는 새 원본 문서를 가려내는 `status`의 몫이다.

- `stale-page`: 기록한 해시와 지금 해시가 다르다(낡음). 원본 문서가 바뀌었으니 페이지를 다시 ingest할 때다.
- `missing-source`: 문서가 없다. 근거가 사라진 페이지다.
- `missing-skipped-source`: 넘긴 문서의 목록에 적힌 문서가 없다. 내용이 바뀐 넘긴 문서는 여기서 잡지 않는다. `status`가 바뀐 문서로 다시 보여 준다.
"""

from collections.abc import Iterator

from ..compiler import Compiled
from ..rules import RuleSet
from .catalog import MISSING_SKIPPED_SOURCE, MISSING_SOURCE, STALE_PAGE
from .model import Issue


def find(compiled: Compiled, rules: RuleSet) -> Iterator[Issue]:
    for record in compiled.records:
        for page in record.pages:
            for entry in page.sources:
                current = record.document_hashes.get(entry.path)
                if current is None:
                    yield Issue(
                        MISSING_SOURCE,
                        page.file,
                        f"`derivedFrom`이 가리키는 원본 문서 `{entry.path}`가 없다(이름이 대소문자까지 같은 일반 파일이 지식 저장소에 없다. 디렉토리와 심볼릭 링크는 원본 문서가 아니다)",
                    )
                elif current != entry.hash:
                    yield Issue(
                        STALE_PAGE,
                        page.file,
                        f"근거로 삼은 원본 문서 `{entry.path}`가 바뀌었다(기록한 해시 `{entry.hash}`, 현재 해시 `{current}`)",
                    )
        for entry in record.skipped:
            if record.document_hashes.get(entry.path) is None:
                yield Issue(
                    MISSING_SKIPPED_SOURCE,
                    record.skipped_file,
                    f"넘긴 문서의 목록에 적힌 원본 문서 `{entry.path}`가 없다(이름이 대소문자까지 같은 일반 파일이 지식 저장소에 없다. 디렉토리와 심볼릭 링크는 원본 문서가 아니다)",
                )
