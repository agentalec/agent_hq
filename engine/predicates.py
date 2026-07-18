"""Structured predicate evaluation (§5.2).

Predicates gate declarative enqueue targets in task definitions:
`{field, op, value}` where `field` is a dotted path into a `values` dict
(e.g. task outputs), evaluated against one of a small op set.
"""

from __future__ import annotations

OPS = ("eq", "ne", "in")


class PredicateError(Exception):
    """Raised for an unknown op or a field missing from `values`."""


def _lookup(field: str, values: dict):
    cur = values
    for part in field.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise PredicateError(f"predicate field '{field}' not found in values")
        cur = cur[part]
    return cur


def evaluate(pred: dict, values: dict) -> bool:
    op = pred["op"]
    if op not in OPS:
        raise PredicateError(f"unknown predicate op '{op}'")
    field_value = _lookup(pred["field"], values)
    if op == "eq":
        return field_value == pred["value"]
    if op == "ne":
        return field_value != pred["value"]
    # op == "in" -- value must be a real collection: a string would do
    # substring matching and silently mis-route a scalar task.yml typo.
    if not isinstance(pred["value"], (list, tuple, set)):
        raise PredicateError(
            f"'in' predicate value must be a list, got {type(pred['value']).__name__}"
        )
    return field_value in pred["value"]
