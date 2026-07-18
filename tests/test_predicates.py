import pytest

from engine.predicates import PredicateError, evaluate

VALUES = {"plan": {"classification": "beyond-crud"}, "score": 7}


def test_eq_true():
    assert evaluate({"field": "score", "op": "eq", "value": 7}, VALUES) is True


def test_eq_false():
    assert evaluate({"field": "score", "op": "eq", "value": 8}, VALUES) is False


def test_ne():
    assert evaluate({"field": "score", "op": "ne", "value": 8}, VALUES) is True
    assert evaluate({"field": "score", "op": "ne", "value": 7}, VALUES) is False


def test_in():
    pred = {"field": "plan.classification", "op": "in", "value": ["crud", "beyond-crud"]}
    assert evaluate(pred, VALUES) is True
    pred = {"field": "plan.classification", "op": "in", "value": ["crud"]}
    assert evaluate(pred, VALUES) is False


def test_dotted_path_eq():
    pred = {"field": "plan.classification", "op": "eq", "value": "beyond-crud"}
    assert evaluate(pred, VALUES) is True


def test_unknown_op_raises():
    with pytest.raises(PredicateError):
        evaluate({"field": "score", "op": "gt", "value": 1}, VALUES)


def test_missing_field_raises():
    with pytest.raises(PredicateError):
        evaluate({"field": "nope", "op": "eq", "value": 1}, VALUES)


def test_missing_dotted_field_raises():
    with pytest.raises(PredicateError):
        evaluate({"field": "plan.nope", "op": "eq", "value": 1}, VALUES)
