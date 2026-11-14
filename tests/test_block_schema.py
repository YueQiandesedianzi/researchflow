"""全部真实积木契约有效 + 非法清单被拒绝。"""

from pathlib import Path

import pytest

from researchflow.blocks.loader import builtin_blocks_dir
from researchflow.blocks.schema import load_block
from researchflow.errors import ContractError

TS_BLOCKS = (Path(__file__).parent.parent / "packages" / "rf-blocks-timeseries"
             / "src" / "rf_blocks_timeseries" / "blocks")


def _block_dirs(container: Path):
    return sorted(p for p in container.iterdir() if (p / "block.yaml").is_file())


@pytest.mark.parametrize("block_dir", _block_dirs(builtin_blocks_dir()),
                         ids=lambda p: p.name)
def test_builtin_block_contract_valid(block_dir):
    block = load_block(block_dir, "builtin", 1)
    assert block.id == block_dir.name
    assert block.outputs


@pytest.mark.parametrize("block_dir", _block_dirs(TS_BLOCKS), ids=lambda p: p.name)
def test_timeseries_pack_block_contract_valid(block_dir):
    block = load_block(block_dir, "pack:test", 2)
    assert block.id == block_dir.name


def _write_manifest(tmp_path, **overrides):
    import yaml

    data = {
        "id": "test.ok", "version": "0.1.0", "schema_version": 1,
        "category": "transform", "title": "t", "description": "d",
        "kind": "python", "entry": "impl:fn",
        "inputs": {}, "outputs": {"out": {"type": "table"}},
        "execution": {"deterministic": True, "requires_approval": False},
    }
    data.update(overrides)
    bdir = tmp_path / "test.ok"
    bdir.mkdir()
    (bdir / "block.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    (bdir / "impl.py").write_text("def fn(inputs, params, out_dir, log):\n    return {}\n")
    return bdir


def test_minimal_valid_block(tmp_path):
    block = load_block(_write_manifest(tmp_path), "project", 3)
    assert block.id == "test.ok"
    assert block.timeout_seconds == 3600  # 默认


@pytest.mark.parametrize("override,bad", [
    ({"id": "Bad ID"}, "id"),
    ({"version": "1.0"}, "version"),
    ({"schema_version": 99}, "schema_version"),
    ({"category": "nope"}, "category"),
    ({"kind": "command"}, "kind"),
    ({"entry": "no-colon"}, "entry"),
    ({"outputs": {"o": {"type": "weird"}}}, "type"),
    ({"execution": {"deterministic": True}}, "requires_approval"),
    ({"validation": [{"a": 1, "b": 2}]}, "validation"),
])
def test_invalid_manifest_rejected(tmp_path, override, bad):
    with pytest.raises(ContractError) as exc:
        load_block(_write_manifest(tmp_path, **override), "project", 3)
    assert exc.value.details, f"应报告 {bad} 的问题明细"


def test_missing_entry_file_rejected(tmp_path):
    bdir = _write_manifest(tmp_path)
    (bdir / "impl.py").unlink()
    with pytest.raises(ContractError):
        load_block(bdir, "project", 3)
