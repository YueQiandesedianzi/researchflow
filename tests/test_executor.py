"""Runner 集成：运行、新鲜度、缓存、契约拒绝、验证门禁阻断、决策流。"""

import json
import shutil

import pytest
import yaml

from researchflow.project import Project
from researchflow.registry.store import Store
from researchflow.runner.executor import Executor

from conftest import BASE_PLAN, run_cli, write_project


def _run_all(project):
    ex = Executor(Project.open(project), quiet=True)
    try:
        code = ex.run(run_all=True, yes=True)
        return code, ex.results
    finally:
        ex.close()


def test_run_all_then_fresh(tiny_project):
    code, results = _run_all(tiny_project)
    assert code == 0
    assert results["eval-01"][0] == "ran"
    # 产物与记录齐全
    run_id = results["eval-01"][1]
    run_dir = tiny_project / ".researchflow" / "runs" / run_id
    assert (run_dir / "run.json").is_file()
    assert (run_dir / "resolved.yaml").is_file()
    assert (run_dir / "artifacts" / "metrics.json").is_file()
    rj = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert rj["status"] == "validated"
    assert rj["block"]["id"] == "eval.regression_metrics"
    assert rj["inputs"]["predictions"]["sha256"]
    # 第二次运行：全部复用
    code, results = _run_all(tiny_project)
    assert code == 0
    assert results["eval-01"][0] == "fresh"


def test_determinism_two_projects(tiny_project, tmp_path):
    from researchflow.util import sha256_file

    other = tmp_path / "proj2"
    shutil.copytree(tiny_project, other, ignore=shutil.ignore_patterns(".researchflow"))
    _run_all(tiny_project)
    _run_all(other)

    def metrics_hash(root):
        files = sorted(root.glob(".researchflow/runs/*/artifacts/metrics.json"))
        return [sha256_file(f) for f in files]

    assert metrics_hash(tiny_project) == metrics_hash(other)


def test_cache_hit_across_twin_nodes(tmp_path):
    plan = """\
schema_version: 1
project: twin
nodes:
  - id: load-01
    kind: execution
    block: io.load_csv@^0.1.0
    params: {path: data/raw.csv, target: y}
  - id: split-a
    kind: execution
    block: split.group_holdout@^0.1.0
    params: {group_column: composition, test_size: 0.34, seed: 1}
    inputs:
      dataset: {from: load-01.outputs.table}
  - id: split-b
    kind: execution
    block: split.group_holdout@^0.1.0
    params: {group_column: composition, test_size: 0.34, seed: 1}
    inputs:
      dataset: {from: load-01.outputs.table}
"""
    proj = write_project(tmp_path / "p", plan)
    code, results = _run_all(proj)
    assert code == 0
    assert results["split-a"][0] == "ran"
    assert results["split-b"][0] == "cache"
    # 缓存运行的记录同样可追溯
    run_id = results["split-b"][1]
    rj = json.loads((proj / ".researchflow" / "runs" / run_id / "run.json")
                    .read_text(encoding="utf-8"))
    assert rj["cache"]["hit"] is True
    assert rj["status"] == "validated"


def test_contract_violation_exit_2(tmp_path):
    # 把 table 接到 model 端口：类型不符 → 退出码 2
    bad_plan = BASE_PLAN.replace(
        "model: {from: train-01.outputs.model}",
        "model: {from: load-01.outputs.table}")
    proj = write_project(tmp_path / "p", bad_plan)
    assert run_cli("--json", "-C", proj, "plan", "validate") == 2


def test_validation_failure_blocks_downstream(tmp_path):
    nan_block = {
        "block.yaml": """\
id: test.nan_maker
version: 0.1.0
schema_version: 1
category: transform
title: 制造 NaN
description: 测试用：输出含 NaN 的表
kind: python
entry: impl:make
inputs:
  dataset: {type: table}
outputs:
  table: {type: table}
params: {type: object, properties: {}}
validation:
  - no_nan
execution:
  deterministic: false
  requires_approval: false
  timeout_seconds: 60
""",
        "impl.py": """\
import pandas as pd


def make(inputs, params, out_dir, log):
    df = pd.read_csv(inputs["dataset"].path)
    df.loc[0, "y"] = float("nan")
    df.to_csv(out_dir / "table.csv", index=False)
    return {"table": "table.csv"}
""",
    }
    plan = """\
schema_version: 1
project: nan
nodes:
  - id: load-01
    kind: execution
    block: io.load_csv@^0.1.0
    params: {path: data/raw.csv, target: y}
  - id: nan-01
    kind: execution
    block: test.nan_maker@^0.1.0
    inputs:
      dataset: {from: load-01.outputs.table}
  - id: split-01
    kind: execution
    block: split.random_holdout@^0.1.0
    inputs:
      dataset: {from: nan-01.outputs.table}
"""
    proj = write_project(tmp_path / "p", plan, blocks={"test.nan_maker": nan_block})
    code, results = _run_all(proj)
    assert code == 3
    assert results["nan-01"] == "failed"
    assert results["split-01"] == "skipped"
    store = Store.open(proj / ".researchflow")
    try:
        assert store.latest_any("nan-01")["status"] == "failed_validation"
        findings = store.validations_of(store.latest_any("nan-01")["run_id"])
        assert any(f["name"] == "no_nan" and not f["passed"] for f in findings)
    finally:
        store.close()


MANUAL_PLAN = BASE_PLAN + """
  - id: gate-01
    kind: decision
    title: 人工确认预测质量
    inputs:
      candidate: {from: pred-01.outputs.predictions}
    criteria:
      mode: manual
    on_pass: [report-01]
  - id: report-01
    kind: execution
    block: data.inspect@^0.1.0
    inputs:
      dataset: {from: pred-01.outputs.predictions}
"""


def test_manual_decision_flow(tmp_path):
    proj = write_project(tmp_path / "p", MANUAL_PLAN)
    # 第一次：决策未决 → 退出码 4，report-01 未运行
    code, results = _run_all(proj)
    assert code == 4
    assert results["gate-01"] == "awaiting"
    # report-01 被未决门禁挡住
    assert results["report-01"] == "awaiting"
    # 人工驳回：report-01 被有意跳过（退出码回到 0）
    assert run_cli("--json", "-C", proj, "decide", "gate-01", "--fail",
                   "--comment", "先不进报告") == 0
    code, results = _run_all(proj)
    assert code == 0
    assert results["report-01"] == "skipped(decision)"
    # 人工通过：report-01 运行
    assert run_cli("--json", "-C", proj, "decide", "gate-01", "--pass") == 0
    code, results = _run_all(proj)
    assert code == 0
    assert results["report-01"][0] in ("ran", "cache")


def test_auto_decision_recorded(tiny_project):
    plan = BASE_PLAN + """
  - id: gate-auto
    kind: decision
    inputs:
      candidate: {from: eval-01.outputs.metrics}
    criteria:
      mode: auto
      expression: "candidate.rmse < 1.0"
    on_pass: []
"""
    (tiny_project / "plan.yaml").write_text(
        yaml.safe_dump(yaml.safe_load(plan), sort_keys=False, allow_unicode=True),
        encoding="utf-8")
    code, _ = _run_all(tiny_project)
    assert code == 0
    store = Store.open(tiny_project / ".researchflow")
    try:
        dec = store.latest_decision("gate-auto")
        assert dec is not None and dec["final_result"] == 1
        assert dec["actor"] == "auto"
    finally:
        store.close()
