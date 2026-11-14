"""版本范围匹配与三级发现优先级。"""

from pathlib import Path

import pytest

from researchflow.blocks.loader import discover, match_version, parse_version
from researchflow.errors import ContractError


@pytest.mark.parametrize("spec,ver,expected", [
    (None, (0, 1, 0), True),
    ("", (1, 0, 0), True),
    ("^0.1.0", (0, 1, 0), True),
    ("^0.1.0", (0, 1, 9), True),
    ("^0.1.0", (0, 2, 0), False),
    ("^0.1.0", (1, 0, 0), False),
    ("^1.2.3", (1, 9, 0), True),
    ("^1.2.3", (2, 0, 0), False),
    ("^1.2.3", (1, 2, 2), False),
    ("0.1.0", (0, 1, 0), True),
    ("0.1.0", (0, 1, 1), False),
    (">=0.1,<0.2", (0, 1, 5), True),
    (">=0.1,<0.2", (0, 2, 0), False),
    (">=0.1,<0.2", (0, 0, 9), False),
])
def test_match_version(spec, ver, expected):
    assert match_version(spec, ver) is expected


def test_parse_version():
    assert parse_version("1.2.3") == (1, 2, 3)
    assert parse_version("0.10.2-rc.1") == (0, 10, 2)


def test_project_overrides_builtin(tmp_path):
    # 项目级覆盖内置 io.load_csv
    bdir = tmp_path / "blocks" / "io.load_csv"
    bdir.mkdir(parents=True)
    bdir.joinpath("block.yaml").write_text("""\
id: io.load_csv
version: 9.9.9
schema_version: 1
category: io
title: 项目定制载入
description: 覆盖内置
kind: python
entry: impl:load
inputs: {}
outputs:
  table: {type: table}
params: {type: object, properties: {}}
execution: {deterministic: true, requires_approval: false}
""", encoding="utf-8")
    bdir.joinpath("impl.py").write_text("def load(inputs, params, out_dir, log):\n    return {}\n")
    index = discover(tmp_path, load_entry_points=False)
    block = index.resolve("io.load_csv@^9.0.0")
    assert block.version == (9, 9, 9)
    assert block.source == "project"
    # 无范围时同样优先项目级
    assert index.resolve("io.load_csv").version == (9, 9, 9)


def test_unknown_block_and_version_gap(tmp_path):
    index = discover(tmp_path, load_entry_points=False)
    with pytest.raises(ContractError):
        index.resolve("no.such_block")
    with pytest.raises(ContractError) as exc:
        index.resolve("io.load_csv@^99.0.0")
    assert "版本" in exc.value.message
