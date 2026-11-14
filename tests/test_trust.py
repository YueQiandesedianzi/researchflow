"""批 1 可信度回归：R1 文件依赖指纹 / R2 门禁传播 / R3 决策证据 / R6 产物完整性。

对应外部审查报告（d95acb6）的探针场景，修复后行为即验收标准。
"""

import json

import pytest

from researchflow.project import Project, doctor
from researchflow.registry.store import Store
from researchflow.runner.executor import Executor

from conftest import run_cli, write_project, TINY_CSV, RIDGE_CONFIG

RF_CONFIG = """\
estimator: sklearn.ensemble.RandomForestRegressor
params:
  n_estimators: 10
  random_state: 1
features: all_numeric
target: y
standardize: false
"""

DUAL_PLAN = """\
schema_version: 1
project: dual
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
  - id: train-ridge-01
    kind: execution
    block: model.train_sklearn@^0.1.0
    params: {config: configs/ridge.yaml}
    inputs:
      dataset: {from: load-01.outputs.table}
      train_indices: {from: split-01.outputs.train_indices}
  - id: pred-ridge-01
    kind: execution
    block: model.predict@^0.1.0
    inputs:
      model: {from: train-ridge-01.outputs.model}
      dataset: {from: load-01.outputs.table}
      indices: {from: split-01.outputs.test_indices}
  - id: eval-ridge-01
    kind: execution
    block: eval.regression_metrics@^0.1.0
    inputs:
      predictions: {from: pred-ridge-01.outputs.predictions}
  - id: train-rf-01
    kind: execution
    block: model.train_sklearn@^0.1.0
    params: {config: configs/rf.yaml}
    inputs:
      dataset: {from: load-01.outputs.table}
      train_indices: {from: split-01.outputs.train_indices}
  - id: pred-rf-01
    kind: execution
    block: model.predict@^0.1.0
    inputs:
      model: {from: train-rf-01.outputs.model}
      dataset: {from: load-01.outputs.table}
      indices: {from: split-01.outputs.test_indices}
  - id: eval-rf-01
    kind: execution
    block: eval.regression_metrics@^0.1.0
    inputs:
      predictions: {from: pred-rf-01.outputs.predictions}
"""


def _run_all(project, **kw):
    ex = Executor(Project.open(project), quiet=True)
    try:
        code = ex.run(run_all=True, yes=True, **kw)
        return code, ex.results
    finally:
        ex.close()


@pytest.fixture
def dual_project(tmp_path):
    return write_project(tmp_path / "proj", DUAL_PLAN,
                         configs={"ridge.yaml": RIDGE_CONFIG, "rf.yaml": RF_CONFIG})


# ---------- R1：数据/配置文件内容变化必须使相关节点失效 ----------

def test_r1_data_change_invalidates(dual_project):
    code, results = _run_all(dual_project)
    assert code == 0
    code, results = _run_all(dual_project)
    assert results["eval-ridge-01"][0] == "fresh"
    assert results["eval-rf-01"][0] == "fresh"

    # 同路径改内容：追加一行（组 G9 新样本）
    raw = dual_project / "data" / "raw.csv"
    raw.write_text(raw.read_text(encoding="utf-8") + "G9,9.9,0.9,18.9\n", encoding="utf-8")
    code, results = _run_all(dual_project)
    assert results["load-01"][0] == "ran", "CSV 内容变化后 load 仍 fresh —— R1"
    assert results["train-ridge-01"][0] == "ran"
    assert results["train-rf-01"][0] == "ran"
    assert results["eval-ridge-01"][0] == "ran"


def test_r1_config_change_scoped_invalidation(dual_project):
    _run_all(dual_project)
    cfg = dual_project / "configs" / "ridge.yaml"
    cfg.write_text(cfg.read_text(encoding="utf-8").replace("alpha: 1.0", "alpha: 10000.0"),
                   encoding="utf-8")
    code, results = _run_all(dual_project)
    assert code == 0
    assert results["train-ridge-01"][0] == "ran", "配置内容变化后 train 仍 fresh —— R1"
    assert results["eval-ridge-01"][0] == "ran"
    assert results["train-rf-01"][0] == "fresh", "无关分支应继续复用"
    assert results["eval-rf-01"][0] == "fresh"
    # 再次运行且无变化 → 全部 fresh
    code, results = _run_all(dual_project)
    assert results["eval-ridge-01"][0] == "fresh"


# ---------- R2：门禁上游失败/未完成时，下游不得沿用历史 PASS 产生新运行 ----------

GATE_PLAN = """\
schema_version: 1
project: gated
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
  - id: score-01
    kind: execution
    block: eval.regression_metrics@^0.1.0
    params: {metrics: [rmse]}
    inputs:
      predictions: {from: pred-01.outputs.predictions}
  - id: gate-01
    kind: decision
    title: 分数达标？
    inputs:
      candidate: {from: score-01.outputs.metrics}
    criteria:
      mode: auto
      expression: "candidate.rmse < 1000"
    on_pass: [consumer-01]
  - id: consumer-01
    kind: execution
    block: data.inspect@^0.1.0
    inputs:
      dataset: {from: load-01.outputs.table}
"""


def test_r2_stale_pass_cannot_release(tmp_path):
    proj = write_project(tmp_path / "p", GATE_PLAN)
    code, results = _run_all(proj)
    assert code == 0
    store = Store.open(proj / ".researchflow")
    consumer_run_1 = store.latest_run("consumer-01")["run_id"]
    assert store.latest_decision("gate-01")["final_result"] == 1
    store.close()

    # 令评分积木必然失败（未知指标），强制全链重跑
    plan_path = proj / "plan.yaml"
    plan_path.write_text(plan_path.read_text(encoding="utf-8")
                         .replace("metrics: [rmse]", "metrics: [nope]"), encoding="utf-8")
    code, results = _run_all(proj, no_cache=True)
    assert code == 3
    assert results["score-01"] == "failed"
    assert results["gate-01"] == "skipped"
    assert results["consumer-01"] == "skipped", "历史 PASS 不得放行本轮 —— R2"
    store = Store.open(proj / ".researchflow")
    assert store.latest_run("consumer-01")["run_id"] == consumer_run_1, "consumer 产生了新运行"
    store.close()


# ---------- R3：人工审批绑定证据，依据变化必须重新确认 ----------

MANUAL_PLAN = GATE_PLAN.replace("mode: auto", "mode: manual")


def test_r3_manual_decision_evidence_binding(tmp_path):
    proj = write_project(tmp_path / "p", MANUAL_PLAN)
    code, results = _run_all(proj)
    assert code == 4 and results["gate-01"] == "awaiting"

    assert run_cli("--json", "-C", proj, "decide", "gate-01", "--pass",
                   "--comment", "初批数据可靠") == 0
    code, results = _run_all(proj)
    assert code == 0 and results["consumer-01"][0] == "ran"

    # 内容无变化的重跑（含缓存路径）→ 不重复审批
    code, results = _run_all(proj)
    assert code == 0, f"无内容变化却要求重审: {results}"

    # 改变上游结果：追加数据行 → 评估指标变化 → 证据失效 → 重新挂起
    raw = proj / "data" / "raw.csv"
    raw.write_text(raw.read_text(encoding="utf-8") + "G9,9.9,0.9,18.9\n", encoding="utf-8")
    code, results = _run_all(proj)
    assert code == 4, f"证据变化后未重新挂起: {results}"
    assert results["gate-01"] == "awaiting"
    assert results["consumer-01"] in ("skipped", "awaiting"), "旧审批放行了新实验 —— R3"

    # 重新确认后放行
    assert run_cli("--json", "-C", proj, "decide", "gate-01", "--pass") == 0
    code, results = _run_all(proj)
    assert code == 0


# ---------- R6：fresh 前必须校验被复用节点自身产物完整性 ----------

def test_r6_tampered_terminal_artifact_detected(tmp_path):
    proj = write_project(tmp_path / "p", GATE_PLAN)
    _run_all(proj)
    metrics_files = sorted(proj.glob(".researchflow/runs/*/artifacts/metrics.json"))
    assert metrics_files
    target = metrics_files[-1]
    data = json.loads(target.read_text(encoding="utf-8"))
    data["rmse"] = data.get("rmse", 0) + 999
    target.write_text(json.dumps(data), encoding="utf-8")

    report = doctor(Project.open(proj), deep=True)
    assert report["ok"] is False, "doctor --deep 未发现被改写的产物 —— R6"

    code, results = _run_all(proj)
    assert results["score-01"][0] != "fresh", "被改写的终端产物仍报告 fresh —— R6"

    # 重算/缓存回放后，最新 Run 的产物必须完整可验（append-only 下旧篡改仍被
    # doctor 如实持续报告——历史记录不可改写正是设计意图）
    from researchflow.registry.artifacts import verify_ref

    store = Store.open(proj / ".researchflow")
    latest = store.latest_run("score-01", ("validated",))
    assert latest is not None
    for row in store.artifacts_of(latest["run_id"]):
        ok, detail = verify_ref(proj, {"path": row["path"], "sha256": row["sha256"]})
        assert ok, f"新 Run 产物仍损坏: {detail}"
    report = doctor(Project.open(proj), deep=True)
    assert report["ok"] is False, "历史篡改不应被新运行掩盖"
    store.close()
