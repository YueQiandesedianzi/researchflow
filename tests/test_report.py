"""HTML 报告生成。"""

import json
import re

from researchflow.project import Project
from researchflow.report.report import generate
from researchflow.runner.executor import Executor


def _payload_of(html: str) -> dict:
    m = re.search(r"const DATA = (\{.*?\});</script>", html, re.S)
    assert m, "报告中未找到内嵌数据"
    return json.loads(m.group(1).replace("<\\/", "</"))


def test_report_generation(tiny_project):
    ex = Executor(Project.open(tiny_project), quiet=True)
    try:
        assert ex.run(run_all=True, yes=True) == 0
    finally:
        ex.close()

    out = generate(Project.open(tiny_project))
    assert out.is_file()
    html = out.read_text(encoding="utf-8")
    assert "<svg id=\"tree\">" in html

    data = _payload_of(html)
    assert data["project"] == "tiny"
    node_ids = {n["id"] for n in data["nodes"]}
    assert {"load-01", "split-01", "train-01", "pred-01", "eval-01"} <= node_ids
    eval_node = next(n for n in data["nodes"] if n["id"] == "eval-01")
    assert eval_node["status"] == "validated"
    assert eval_node["run"]["metrics"]["rmse"] >= 0
    assert data["metric_rows"], "指标对照表应有内容"
    assert data["runs"], "运行记录应有内容"
    # 布局坐标应在画布内
    assert all(0 <= n["x"] <= data["canvas"]["width"] for n in data["nodes"])
