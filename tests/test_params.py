"""参数契约（JSON Schema 子集）。"""

import pytest

from researchflow.blocks.contract import check_params
from researchflow.errors import ContractError

SCHEMA = {
    "type": "object",
    "required": ["name"],
    "properties": {
        "name": {"type": "string"},
        "size": {"type": "number", "default": 0.2, "minimum": 0.05, "maximum": 0.5},
        "seed": {"type": "integer", "default": 42},
        "mode": {"type": "string", "enum": ["a", "b"]},
        "tags": {"type": "array"},
    },
}


def test_defaults_applied():
    resolved = check_params(SCHEMA, {"name": "x"})
    assert resolved == {"name": "x", "size": 0.2, "seed": 42}


def test_required_missing():
    with pytest.raises(ContractError) as exc:
        check_params(SCHEMA, {})
    assert any("name" in d for d in exc.value.details)


def test_unknown_param_rejected():
    with pytest.raises(ContractError) as exc:
        check_params(SCHEMA, {"name": "x", "sze": 0.3})
    assert any("sze" in d for d in exc.value.details)


def test_type_mismatch():
    with pytest.raises(ContractError):
        check_params(SCHEMA, {"name": "x", "size": "big"})


def test_integer_rejects_bool():
    with pytest.raises(ContractError):
        check_params(SCHEMA, {"name": "x", "seed": True})


def test_enum_and_range():
    with pytest.raises(ContractError):
        check_params(SCHEMA, {"name": "x", "mode": "c"})
    with pytest.raises(ContractError):
        check_params(SCHEMA, {"name": "x", "size": 0.9})
    assert check_params(SCHEMA, {"name": "x", "mode": "a", "size": 0.5})["mode"] == "a"
