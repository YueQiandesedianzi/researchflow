"""端到端 demo 验收：两个独立任务跑同一套基础积木（PRD 验收标准 1/2/3/4/6/7）。"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent

pytestmark = pytest.mark.slow


def _copy_demo(tmp_path, name):
    src = REPO / "examples" / name
    dest = tmp_path / name
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".researchflow", "dist"))
    subprocess.run([sys.executable, str(dest / "scripts" / "make_data.py")],
                   check=True, capture_output=True, text=True, encoding="utf-8",
                   errors="replace")
    return dest


def _rf(project, *args, expect=0):
    proc = subprocess.run(
        [sys.executable, "-m", "researchflow", "--json", "-C", str(project), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    assert proc.returncode == expect, \
        f"rf {' '.join(args)} → {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    return json.loads(proc.stdout)


def _check_demo(project, eval_nodes, baseline, export_nodes):
    assert _rf(project, "plan", "validate")["ok"] is True
    assert _rf(project, "run", "--all", "--yes")["ok"] is True

    status = _rf(project, "status")["status"]
    for nid in eval_nodes:
        assert status[nid] == "validated", f"{nid}: {status[nid]}"

    cmp_data = _rf(project, "compare", *eval_nodes, "--baseline", baseline,
                   "--format", "json")
    for row in cmp_data["rows"]:
        assert row["metrics"]["rmse"] > 0

    out_dir = project / "dist" / "export-test"
    result = _rf(project, "export", "--nodes", ",".join(export_nodes),
                 "--out", out_dir, "--verify")
    assert result["verified"] is True, result.get("verify")
    assert (out_dir / "PROVENANCE.json").is_file()
    assert (out_dir / "plan.yaml").is_file()
    prov = json.loads((out_dir / "PROVENANCE.json").read_text(encoding="utf-8"))
    for nid in prov["nodes"]:
        assert prov["nodes"][nid]["run_id"].startswith("RUN-")
        assert prov["nodes"][nid]["block"]["source_sha256"]

    assert _rf(project, "doctor")["ok"] is True


def test_demo_a_tabular(tmp_path):
    project = _copy_demo(tmp_path, "demo-a-tabular")
    _check_demo(project,
                eval_nodes=["eval-ridge-01", "eval-rf-01", "eval-gbr-01"],
                baseline="eval-ridge-01",
                export_nodes=["eval-rf-01", "plot-rf-parity"])


def test_demo_b_timeseries(tmp_path):
    project = _copy_demo(tmp_path, "demo-b-timeseries")
    _check_demo(project,
                eval_nodes=["eval-ridge-01", "eval-rf-01"],
                baseline="eval-ridge-01",
                export_nodes=["eval-rf-01", "plot-rf-forecast"])


def test_init_templates(tmp_path):
    """FR-1：rf init 生成标准结构，模板计划立即可校验。"""
    proj = tmp_path / "new-proj"
    _rf(tmp_path, "init", str(proj), "--template", "tabular")
    assert (proj / "AGENTS.md").is_file()
    assert (proj / "researchflow.yaml").is_file()
    assert _rf(proj, "plan", "validate")["ok"] is True
    # 幂等：再 init 不覆盖
    before = (proj / "plan.yaml").read_text(encoding="utf-8")
    _rf(tmp_path, "init", str(proj), "--template", "timeseries")
    assert (proj / "plan.yaml").read_text(encoding="utf-8") == before
