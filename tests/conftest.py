"""共享 fixture：微型项目工厂 + CLI 便捷入口。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "src"))

from researchflow.cli import main as cli_main  # noqa: E402


def run_cli(*argv) -> int:
    return cli_main([str(a) for a in argv])


TINY_CSV = "\n".join(
    ["composition,x1,x2,y"]
    + [f"G{g},{g * 0.5 + i},{i * 0.3},{2 * (g * 0.5 + i) - i * 0.3 + g * 0.1}"
       for g in range(5) for i in range(6)]
) + "\n"

RIDGE_CONFIG = """\
estimator: sklearn.linear_model.Ridge
params:
  alpha: 1.0
features: all_numeric
target: y
standardize: false
"""

BASE_PLAN = """\
schema_version: 1
project: tiny
nodes:
  - id: load-01
    kind: execution
    block: io.load_csv@^0.1.0
    params: {path: data/raw.csv, target: y}
  - id: split-01
    kind: execution
    block: split.group_holdout@^0.1.0
    params: {group_column: composition, test_size: 0.34, seed: 1}
    inputs:
      dataset: {from: load-01.outputs.table}
  - id: train-01
    kind: execution
    block: model.train_sklearn@^0.1.0
    params: {config: configs/ridge.yaml}
    inputs:
      dataset: {from: load-01.outputs.table}
      train_indices: {from: split-01.outputs.train_indices}
  - id: pred-01
    kind: execution
    block: model.predict@^0.1.0
    inputs:
      model: {from: train-01.outputs.model}
      dataset: {from: load-01.outputs.table}
      indices: {from: split-01.outputs.test_indices}
  - id: eval-01
    kind: execution
    block: eval.regression_metrics@^0.1.0
    inputs:
      predictions: {from: pred-01.outputs.predictions}
"""


def write_project(root: Path, plan_yaml: str, *, data: str | None = TINY_CSV,
                  configs: dict | None = None, blocks: dict | None = None) -> Path:
    root = Path(root)
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "configs").mkdir(exist_ok=True)
    (root / "researchflow.yaml").write_text(
        yaml.safe_dump({"schema_version": 1, "name": root.name, "seed": 42}), encoding="utf-8")
    (root / "plan.yaml").write_text(plan_yaml, encoding="utf-8")
    if data is not None:
        (root / "data" / "raw.csv").write_text(data, encoding="utf-8")
    for name, content in (configs or {"ridge.yaml": RIDGE_CONFIG}).items():
        (root / "configs" / name).write_text(content, encoding="utf-8")
    for block_id, files in (blocks or {}).items():
        bdir = root / "blocks" / block_id
        bdir.mkdir(parents=True, exist_ok=True)
        for fname, content in files.items():
            (bdir / fname).write_text(content, encoding="utf-8")
    return root


@pytest.fixture
def tiny_project(tmp_path) -> Path:
    return write_project(tmp_path / "proj", BASE_PLAN)
