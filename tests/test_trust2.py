"""批 2 回归：R4 导出 verify 有效比对 / R5 导出文档诚实 / R7 泄漏防护。"""

import json

import pandas as pd
import pytest

from researchflow.export.exporter import export
from researchflow.project import Project
from researchflow.registry.store import Store
from researchflow.runner.executor import Executor

from conftest import run_cli, write_project, BASE_PLAN, RIDGE_CONFIG

PLOT_PLAN = BASE_PLAN + """
  - id: plot-01
    kind: execution
    block: plot.parity@^0.1.0
    inputs:
      predictions: {from: pred-01.outputs.predictions}
"""

LEAK_CONFIG = """\
estimator: sklearn.linear_model.LinearRegression
params: {}
features: [x1, y]
target: y
standardize: false
"""


def _run_all(project, **kw):
    ex = Executor(Project.open(project), quiet=True)
    try:
        return ex.run(run_all=True, yes=True, **kw), ex.results
    finally:
        ex.close()


# ---------- R4：没有有效比较项时不得判过（unverifiable） ----------

def test_r4_figure_only_export_is_unverifiable(tmp_path):
    proj = write_project(tmp_path / "p", PLOT_PLAN)
    code, _ = _run_all(proj)
    assert code == 0
    out = tmp_path / "dist" / "fig-only"
    result = export(Project.open(proj), ["plot-01"], out, verify=True,
                    emit=lambda m: None)
    assert result["verify"]["status"] == "unverifiable", result["verify"]
    assert result["verified"] is False
    doc = json.loads((out / "VERIFY.json").read_text(encoding="utf-8"))
    assert doc["status"] == "unverifiable"
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "已通过" not in readme and "不可确认" in readme


# ---------- R4/R5：产物不一致必须 failed，README/VERIFY.json 如实反映 ----------

def test_r4r5_artifact_mismatch_fails_honestly(tmp_path):
    proj = write_project(tmp_path / "p", BASE_PLAN)
    code, _ = _run_all(proj)
    assert code == 0

    # 运行后篡改源数据（不 rerun）→ 导出的重跑将基于新数据，产物必然不一致
    raw = proj / "data" / "raw.csv"
    raw.write_text(raw.read_text(encoding="utf-8") + "G9,9.9,0.9,18.9\n", encoding="utf-8")
    out = tmp_path / "dist" / "tampered"
    result = export(Project.open(proj), ["eval-01"], out, verify=True,
                    emit=lambda m: None)
    assert result["verify"]["status"] == "failed", result["verify"]
    assert result["verified"] is False
    assert result["verify"]["diffs"], "应有差异明细"
    doc = json.loads((out / "VERIFY.json").read_text(encoding="utf-8"))
    assert doc["status"] == "failed" and doc["diffs"]
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "已通过" not in readme and "未通过" in readme


# ---------- R7：目标列混入特征列表必须在 fit 前拒绝 ----------

def test_r7_target_in_features_rejected(tmp_path):
    proj = write_project(tmp_path / "p", BASE_PLAN,
                         configs={"ridge.yaml": LEAK_CONFIG})
    code = run_cli("--json", "-C", proj, "run", "--all", "--yes")
    assert code == 3
    store = Store.open(proj / ".researchflow")
    run = store.latest_any("train-01")
    assert run["status"] == "failed"
    store.close()
    stderr_log = (proj / ".researchflow" / "runs" / run["run_id"]
                  / "logs" / "stderr.log").read_text(encoding="utf-8", errors="replace")
    assert "目标列" in stderr_log and "不允许" in stderr_log


# ---------- R7：fill_mean 仅使用训练集统计量 ----------

NAN_CSV = "\n".join(
    ["x,y"] + [f"{i if i != 3 else ''},{2 * i + 1}" for i in range(12)]
) + "\n"

FILL_PLAN = """\
schema_version: 1
project: fill
nodes:
  - id: load-01
    kind: execution
    block: io.load_csv@^0.1.0
    params: {path: data/raw.csv, target: y}
  - id: split-01
    kind: execution
    block: split.random_holdout@^0.1.0
    params: {test_size: 0.34, seed: 1}
    inputs:
      dataset: {from: load-01.outputs.table}
  - id: clean-01
    kind: execution
    block: data.clean@^0.1.0
    params: {na_strategy: fill_mean}
    inputs:
      dataset: {from: load-01.outputs.table}
      train_indices: {from: split-01.outputs.train_indices}
"""


def test_r7_fill_mean_uses_train_stats_only(tmp_path):
    proj = write_project(tmp_path / "p", FILL_PLAN, data=NAN_CSV)
    code, _ = _run_all(proj)
    assert code == 0

    store = Store.open(proj / ".researchflow")
    split_run = store.latest_run("split-01", ("validated",))
    train_idx = json.loads(
        (proj / [a for a in store.artifacts_of(split_run["run_id"])
                 if a["port"] == "train_indices"][0]["path"]).read_text(encoding="utf-8"))
    clean_run = store.latest_run("clean-01", ("validated",))
    table_path = [a for a in store.artifacts_of(clean_run["run_id"])
                  if a["port"] == "table"][0]["path"]
    store.close()

    df = pd.read_csv(proj / table_path)
    src = pd.read_csv(proj / "data" / "raw.csv")
    expected = src.iloc[train_idx]["x"].mean()
    assert df.loc[3, "x"] == pytest.approx(expected), (
        f"填充值 {df.loc[3, 'x']} 应为训练集均值 {expected}（而非全量均值 "
        f"{src['x'].mean()}）")
    assert df.loc[3, "x"] != pytest.approx(src["x"].mean(), rel=1e-3) or \
        abs(expected - src["x"].mean()) < 1e-3
