"""구조 제약: 필수 속성, 값의 종류, 허용되는 클래스, 관계를 쓰고 가리킬 수 있는 클래스.

제약은 코드가 아니라 `vocab/shapes.ttl`(SHACL)에 있다. 이 모듈은 컴파일한 그래프에 그것을 돌리고, 결과를 검사 항목의
문제로 옮긴다. 어느 제약이 어느 검사 항목에 속하는지는 도형의 `onto:check`가 정한다.

그래프는 적힌 사실 그대로(`Compiled.graph`)다. 추론은 하지 않는다(`inference="none"`). 하위 클래스는 SHACL이 그래프의
`rdfs:subClassOf`로 따른다. 누락은 열린 세계를 가정하는 OWL이 아니라 SHACL이 잡는다.
"""

from collections.abc import Iterator

from rdflib import Graph, URIRef
from rdflib.namespace import RDF, SH, XSD

from .. import vocab
from ..compiler import Compiled
from ..rules import RuleSet
from .catalog import BY_NAME, MISSING_PROPERTY, RELATION_DOMAIN, RELATION_RANGE
from ..classes import ClassIndex
from ..labels import class_label, entity_label
from .model import Issue

# 범위가 주어의 클래스에도 달린 관계(`supersedes`: 같은 클래스끼리)의 도형. `vocab/shapes.ttl`의 `shape:supersedes-range`다.
SUPERSEDES_RANGE = URIRef("https://onto.invalid/shape#supersedes-range")

# `sh:datatype`로 요구하는 값을 사람이 읽는 말로
_EXPECTED_VALUE = {str(XSD.string): "문자열", str(XSD.date): "날짜(예: 2026-03-01)"}


def find(compiled: Compiled, rules: RuleSet) -> Iterator[Issue]:
    # pyshacl은 불러오는 데 시간이 든다. build와 query는 쓰지 않으므로 검사할 때 불러온다.
    from pyshacl import validate

    shapes = vocab.load_shapes()
    _, report, _ = validate(compiled.graph, shacl_graph=shapes, inference="none")
    keys = vocab.property_keys(vocab.load_context())
    check_predicate = URIRef(vocab.onto_namespace(shapes) + "check")
    classes = ClassIndex(compiled.graph)

    for result in report.subjects(RDF.type, SH.ValidationResult):
        focus = report.value(result, SH.focusNode)
        value = report.value(result, SH.value)
        file = compiled.files.get(str(focus))
        check = _check_of(shapes, report.value(result, SH.sourceShape), check_predicate)
        # 엔티티가 아닌 노드(하위 도형이 클래스에 대해 내는 결과)는 바깥 도형의 결과로 이미 보고된다.
        if file is None or check is None:
            continue
        if check in (RELATION_DOMAIN.name, RELATION_RANGE.name):
            # 가리키는 엔티티가 없는 관계는 깨진 참조 항목이 보고한다. 클래스를 따질 대상이 없다.
            if check == RELATION_RANGE.name and isinstance(value, URIRef) and str(value) not in compiled.files:
                continue
            # 클래스를 알 수 없는 엔티티(클래스가 없거나 허용되지 않는다)가 든 관계는 클래스를 따지지 않는다. 그 엔티티의
            # 클래스 문제가 먼저 보고되고, 고친 뒤에야 관계의 오류가 새로 드러나는 일이 없게 한다.
            # 따지는 엔티티는 판정에 클래스가 쓰이는 쪽뿐이다: 도메인은 주어(페이지), 범위는 가리키는 쪽이다. 주어의 클래스가 범위에
            # 쓰이는 것은 `supersedes`(같은 클래스끼리) 하나다.
            if check == RELATION_DOMAIN.name:
                involved = [focus]
            elif isinstance(value, URIRef):
                involved = [focus, value] if report.value(result, SH.sourceShape) == SUPERSEDES_RANGE else [value]
            else:
                involved = []
            if not all(classes.has_allowed_class(node) for node in involved):
                continue
        yield Issue(BY_NAME[check], file, _message(compiled.graph, shapes, report, result, check, keys))


def _check_of(shapes: Graph, shape: object, check_predicate: URIRef) -> str | None:
    """도형의 `onto:check`. 속성 제약이 자기 것을 갖지 않으면 그것을 품은 도형의 것을 쓴다."""
    pending, seen = [shape], set()
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        name = shapes.value(node, check_predicate)
        if name is not None:
            return str(name)
        pending.extend(shapes.subjects(SH.property, node))
    return None


def _message(graph: Graph, shapes: Graph, report: Graph, result: object, check: str, keys: dict[str, str]) -> str:
    """결과 하나를 설명으로 옮긴다. 제약을 적은 문장(`sh:message`)이 있으면 그것에, 어긋난 값을 덧붙인다."""
    component = report.value(result, SH.sourceConstraintComponent)
    path = report.value(result, SH.resultPath)
    key = keys.get(str(path), str(path))
    value = report.value(result, SH.value)
    rule = report.value(result, SH.resultMessage)

    if component == SH.MinCountConstraintComponent:
        return f"필수 속성이 없다: `{key}`"
    if component == SH.MaxCountConstraintComponent:
        return f"`{key}`의 값은 하나만 쓸 수 있다"
    if component == SH.DatatypeConstraintComponent:
        expected = shapes.value(report.value(result, SH.sourceShape), SH.datatype)
        return f"`{key}`의 값 종류가 맞지 않는다: `{value}`(쓸 수 있는 값: {_EXPECTED_VALUE.get(str(expected), expected)})"
    if component == SH.NodeConstraintComponent:  # 허용되지 않는 클래스. 값이 그 클래스다
        return f"허용되지 않는 클래스 `{class_label(value)}`: {rule}"
    if check == MISSING_PROPERTY.name or component == SH.PatternConstraintComponent:
        return str(rule)  # 제목이 없거나 비어 있다, 페이지가 쓴 Project 클래스. 도형의 문장이 그대로 설명이다
    focus = report.value(result, SH.focusNode)
    if check == RELATION_DOMAIN.name:  # 관계를 쓸 수 없는 클래스의 페이지
        return f"{rule}. 이 페이지의 클래스: {_classes(graph, focus)}"
    return f"{rule}. `{entity_label(value)}`의 클래스: {_classes(graph, value)}"  # 가리킬 수 없는 클래스의 엔티티


def _classes(graph: Graph, entity: object) -> str:
    return ", ".join(f"`{class_label(cls)}`" for cls in sorted(graph.objects(entity, RDF.type), key=str)) or "없음"
