import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
SCHEMA_FILES = sorted(SCHEMAS_DIR.glob("*.json"))


@pytest.mark.parametrize("schema_path", SCHEMA_FILES, ids=lambda p: p.name)
def test_schema_is_valid_draft_2020_12(schema_path):
    schema = json.loads(schema_path.read_text())
    Draft202012Validator.check_schema(schema)
