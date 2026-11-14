"""计划结构校验、拓扑、门禁边、Mermaid 渲染。"""

import pytest

from researchflow.errors import PlanError
from researchflow.plan.engine import ancestors, gate_edges, render_mermaid, topo_order
from researchflow.plan.model import load_plan, parse_binding

from conftest import write_project, BASE_PLAN


def test_parse_binding():
    assert parse_binding("load-01.outputs.table") == ("load-01", "table")
    with pytest.raises(PlanError):
        parse_binding("load-01.table")


def test_duplicate_node_rejected(tmp_path):
    plan = BASE_PLAN + """
  - id: load-01
    kind: execution
    block: io.load_csv@^0.1.0
    params: {path: data/raw.csv}
"""
    proj = write_project(tmp_path / "p", plan)
    with pytest.raises(PlanError) as exc:
        load_plan(proj / "plan.yaml")
    assert any("重复" in d for d in exc.value.details)


def test_cycle_detected(tmp_path):
    plan = """\
schema_version: 1
project: cyc
nodes:
  - id: a-01
    kind: execution
    block: io.load_csv@^0.1.0
    params: {path: data/raw.csv}
    inputs:
      dataset: {from: b-01.outputs.table}
  - id: b-01
    kind: execution
    block: io.load_csv@^0.1.0
    params: {path: data/raw.csv}
    inputs:
      dataset: {from: a-01.outputs.table}
"""
    proj = write_project(tmp_path / "p", plan)
    with pytest.raises(PlanError) as exc:
        topo_order(load_plan(proj / "plan.yaml"))
    assert "循环" in exc.value.message


def test_gate_edges_and_ancestors(tiny_project):
    plan = load_plan(tiny_project / "plan.yaml")
    assert gate_edges(plan) == {}
    assert ancestors(plan, "eval-01") == {"load-01", "split-01", "train-01", "pred-01", "eval-01"}
    order = topo_order(plan)
    assert order.index("load-01") < order.index("eval-01")


def test_mermaid_render(tiny_project):
    plan = load_plan(tiny_project / "plan.yaml")
    text = render_mermaid(plan, {"load-01": "validated", "eval-01": "planned"})
    assert text.startswith("flowchart TB")
    assert "-->" in text
    assert "classDef ok" in text


def test_empty_nodes_rejected(tmp_path):
    proj = write_project(tmp_path / "p", "schema_version: 1\nproject: x\nnodes: []\n")
    with pytest.raises(PlanError):
        load_plan(proj / "plan.yaml")
