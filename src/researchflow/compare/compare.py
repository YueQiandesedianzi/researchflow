"""统一比较模型与实验分支：只读 Registry，不重跑实验。"""

from __future__ import annotations

import csv
import io

from researchflow.errors import ContractError


def resolve_selector(store, selector: str):
    """选择器：RUN-000021 或节点 id（取该节点最新 validated 运行）。"""
    sel = selector.strip()
    if sel.upper().startswith("RUN-"):
        run = store.get_run(sel.upper())
        if run is None:
            raise ContractError(f"运行 {sel} 不存在")
        return run
    run = store.latest_run(sel, ("validated",))
    if run is None:
        raise ContractError(
            f"节点 {sel!r} 没有已验证的运行（选择器可以是 RUN-id 或节点 id）")
    return run


def compare(store, selectors, baseline: str | None = None) -> dict:
    rows = []
    for sel in selectors:
        run = resolve_selector(store, sel)
        rows.append({
            "selector": sel,
            "run_id": run["run_id"],
            "node_id": run["node_id"],
            "block": f"{run['block_id']}@{run['block_version']}",
            "status": run["status"],
            "metrics": store.metrics_of(run["run_id"]),
        })
    metric_names = sorted({k for r in rows for k in r["metrics"]})
    base = None
    if baseline:
        base_run = resolve_selector(store, baseline)
        base = {"run_id": base_run["run_id"], "metrics": store.metrics_of(base_run["run_id"])}
    return {"rows": rows, "metrics": metric_names, "baseline": base}


def _fmt(v):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def _row_cells(data, r):
    cells = [r["run_id"], r["node_id"], r["block"]]
    cells += [_fmt(r["metrics"].get(m)) for m in data["metrics"]]
    if data["baseline"]:
        for m in data["metrics"]:
            v, bv = r["metrics"].get(m), data["baseline"]["metrics"].get(m)
            if v is None or not bv:
                cells.append("—")
            else:
                cells.append(f"{(v - bv) / abs(bv) * 100:+.2f}%")
    return cells


def format_md(data) -> str:
    header = ["run_id", "node_id", "block"] + data["metrics"]
    if data["baseline"]:
        header += [f"Δ{m}%" for m in data["metrics"]]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for r in data["rows"]:
        lines.append("| " + " | ".join(_row_cells(data, r)) + " |")
    if data["baseline"]:
        lines.append(f"\n基线: {data['baseline']['run_id']}")
    return "\n".join(lines)


def format_csv(data) -> str:
    buf = io.StringIO()
    header = ["run_id", "node_id", "block"] + data["metrics"]
    if data["baseline"]:
        header += [f"delta_{m}_pct" for m in data["metrics"]]
    writer = csv.writer(buf)
    writer.writerow(header)
    for r in data["rows"]:
        writer.writerow(_row_cells(data, r))
    return buf.getvalue().strip()
