"""生成单文件 HTML 实验工作台报告。

数据来自 plan.yaml + Registry（只读）；输出零外部依赖的 HTML：
内联 CSS/JS + 内嵌 SVG 实验树 + base64 图表，离线可开。
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from researchflow import __version__
from researchflow.plan.engine import dependencies, gate_edges, topo_order
from researchflow.plan.model import load_plan
from researchflow.registry.store import Store
from researchflow.util import now_iso

_FIGURE_MAX_BYTES = 2 * 1024 * 1024
_NODE_W, _NODE_H, _GAP_X, _GAP_Y, _PAD = 176, 52, 36, 78, 40


def _layout(plan, order):
    """分层布局：layer = 最长路径深度；层内按计划顺序，水平居中。"""
    deps = {n.id: dependencies(n) for n in plan.nodes}
    for target, gates in gate_edges(plan).items():
        deps.setdefault(target, set())
        deps[target] |= {g[0] for g in gates}
    layer_of = {}
    for nid in order:
        ups = [u for u in deps.get(nid, ()) if u in layer_of]
        layer_of[nid] = 0 if not ups else max(layer_of[u] for u in ups) + 1
    layers: dict[int, list] = {}
    for nid in order:
        layers.setdefault(layer_of[nid], []).append(nid)
    max_per_layer = max(len(v) for v in layers.values())
    width = _PAD * 2 + max_per_layer * (_NODE_W + _GAP_X) - _GAP_X
    pos = {}
    for layer, ids in layers.items():
        layer_w = len(ids) * (_NODE_W + _GAP_X) - _GAP_X
        x0 = _PAD + (width - 2 * _PAD - layer_w) / 2
        for i, nid in enumerate(ids):
            pos[nid] = {"x": round(x0 + i * (_NODE_W + _GAP_X)),
                        "y": _PAD + layer * (_NODE_H + _GAP_Y)}
    height = _PAD * 2 + (max(layers) + 1) * (_NODE_H + _GAP_Y) - _GAP_Y
    return pos, width, height


def collect(project) -> dict:
    plan = load_plan(project.root / "plan.yaml")
    store = Store.open(project.rf_dir)
    try:
        order = topo_order(plan)
        pos, width, height = _layout(plan, order)
        node_map = plan.node_map
        run_status = store.node_status_map()

        nodes, metric_rows, figures = [], [], []
        for nid in order:
            n = node_map[nid]
            entry = {"id": nid, "kind": n.kind, "title": n.title,
                     "block": (n.block or "").split("@")[0],
                     "x": pos[nid]["x"], "y": pos[nid]["y"], "run": None}
            if n.kind == "decision":
                dec = store.latest_decision(nid)
                entry["status"] = ("passed" if dec["final_result"] else "rejected") \
                    if dec else "awaiting"
            else:
                entry["status"] = run_status.get(nid, "planned")
                run = store.latest_any(nid)
                if run is not None:
                    rj = {}
                    try:
                        rj = json.loads(run["run_json"])
                    except Exception:
                        pass
                    validations = store.validations_of(run["run_id"])
                    metrics = store.metrics_of(run["run_id"])
                    entry["run"] = {
                        "run_id": run["run_id"], "status": run["status"],
                        "started_at": run["started_at"],
                        "duration_s": rj.get("duration_s"),
                        "metrics": metrics,
                        "validations": [{"name": v["name"], "passed": bool(v["passed"]),
                                         "detail": v["detail"]} for v in validations],
                        "artifacts": [{"port": a["port"], "type": a["type"],
                                       "path": a["path"], "sha256": a["sha256"][:12]}
                                      for a in store.artifacts_of(run["run_id"])],
                        "error": rj.get("error"),
                    }
                    if run["status"] == "validated" and metrics:
                        metric_rows.append({"node_id": nid, "run_id": run["run_id"],
                                            "metrics": metrics})
                    for a in store.artifacts_of(run["run_id"]):
                        if a["type"] == "figure" and run["status"] == "validated":
                            fpath = project.root / a["path"]
                            if fpath.is_file() and fpath.stat().st_size <= _FIGURE_MAX_BYTES:
                                figures.append({
                                    "node_id": nid, "run_id": run["run_id"],
                                    "name": fpath.name,
                                    "data": base64.b64encode(fpath.read_bytes()).decode(),
                                })
            nodes.append(entry)

        edges = []
        for n in plan.nodes:
            for binding in (n.inputs or {}).values():
                if isinstance(binding, dict) and "from" in binding:
                    from researchflow.plan.model import parse_binding
                    try:
                        up, _ = parse_binding(binding["from"])
                        edges.append({"from": up, "to": n.id, "gate": None})
                    except Exception:
                        pass
        for target, gates in gate_edges(plan).items():
            for dec_id, expect in gates:
                edges.append({"from": dec_id, "to": target, "gate": expect})

        decisions = [dict(d) for d in store.recent_decisions(50)]
        runs = [{"run_id": r["run_id"], "node_id": r["node_id"], "status": r["status"],
                 "started_at": r["started_at"], "finished_at": r["finished_at"]}
                for r in store.runs(limit=50)]
    finally:
        store.close()

    metric_names = sorted({k for row in metric_rows for k in row["metrics"]})
    return {
        "project": plan.project, "generated_at": now_iso(),
        "core_version": __version__,
        "canvas": {"width": width, "height": height,
                   "node_w": _NODE_W, "node_h": _NODE_H},
        "nodes": nodes, "edges": edges,
        "metric_names": metric_names, "metric_rows": metric_rows,
        "figures": figures, "decisions": decisions, "runs": runs,
    }


def generate(project, out_path=None) -> Path:
    payload = collect(project)
    out = Path(out_path) if out_path else project.root / "report.html"
    data_js = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = (_TEMPLATE
            .replace("__PROJECT__", payload["project"])
            .replace("__GENERATED__", payload["generated_at"])
            .replace("__VERSION__", payload["core_version"])
            .replace("__DATA__", data_js))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__PROJECT__ · ResearchFlow 实验工作台</title>
<style>
:root{--bg:#0f1419;--panel:#171e26;--border:#2a3542;--fg:#d7e0ea;--dim:#8494a7;
--ok:#34a853;--bad:#ea4335;--wait:#fb8c00;--todo:#5f7285;--accent:#4f9cf9}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--fg);font:14px/1.6 "Segoe UI","Microsoft YaHei",sans-serif}
header{padding:16px 24px;border-bottom:1px solid var(--border);display:flex;align-items:baseline;gap:16px;flex-wrap:wrap}
header h1{font-size:18px;font-weight:600}
header .meta{color:var(--dim);font-size:12px}
nav{display:flex;gap:4px;padding:8px 24px;border-bottom:1px solid var(--border);flex-wrap:wrap}
nav button{background:none;border:1px solid transparent;color:var(--dim);padding:6px 14px;border-radius:6px;cursor:pointer;font-size:13px}
nav button.active{color:var(--fg);border-color:var(--accent);background:#1a2330}
section{display:none;padding:20px 24px}
section.active{display:block}
#tree-wrap{display:flex;gap:16px;align-items:flex-start}
#tree-box{flex:1;overflow:auto;background:var(--panel);border:1px solid var(--border);border-radius:8px}
#detail{width:340px;flex:none;background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:16px;font-size:13px;max-height:80vh;overflow:auto}
#detail h2{font-size:15px;margin-bottom:8px}
#detail .kv{display:grid;grid-template-columns:96px 1fr;gap:2px 8px;word-break:break-all}
#detail .k{color:var(--dim)}
#detail h3{font-size:13px;margin:12px 0 4px;color:var(--dim)}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;color:#fff}
.badge.validated,.badge.passed,.badge.completed{background:var(--ok)}
.badge.failed,.badge.failed_validation,.badge.rejected,.badge.interrupted{background:var(--bad)}
.badge.awaiting,.badge.running{background:var(--wait)}
.badge.planned,.badge.skipped{background:var(--todo)}
.node{cursor:pointer}
.node rect{fill:#1c2733;stroke:var(--border);rx:8}
.node.decision polygon{fill:#26313f;stroke:var(--border)}
.node text{fill:var(--fg);font-size:12px;pointer-events:none}
.node .sub{fill:var(--dim);font-size:10px}
.node:hover rect,.node:hover polygon{stroke:var(--accent)}
.edge{stroke:#3b4a5c;fill:none;stroke-width:1.5}
.edge.gate{stroke:var(--wait);stroke-dasharray:5,4}
.edge-label{fill:var(--wait);font-size:10px}
table{border-collapse:collapse;width:100%;font-size:13px;background:var(--panel);border-radius:8px;overflow:hidden}
th,td{border:1px solid var(--border);padding:6px 10px;text-align:left}
th{background:#1a2330;color:var(--dim);font-weight:500}
td.num{font-variant-numeric:tabular-nums}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:16px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:12px}
.card h3{font-size:13px;margin-bottom:8px}
.card img{width:100%;border-radius:4px;background:#fff}
.empty{color:var(--dim);padding:24px;text-align:center}
.hint{color:var(--dim);font-size:12px;margin-bottom:10px}
</style>
</head>
<body>
<header>
  <h1>__PROJECT__</h1>
  <span class="meta">ResearchFlow 实验工作台 · 生成于 __GENERATED__ · Core v__VERSION__</span>
</header>
<nav id="tabs">
  <button data-tab="tree" class="active">实验树</button>
  <button data-tab="metrics">指标对照</button>
  <button data-tab="figures">图表</button>
  <button data-tab="runs">运行记录</button>
  <button data-tab="decisions">决策记录</button>
</nav>

<section id="tab-tree" class="active">
  <div class="hint">点击节点查看详情。虚线橙边 = 决策门禁（on_pass / on_fail）。</div>
  <div id="tree-wrap">
    <div id="tree-box"><svg id="tree"></svg></div>
    <aside id="detail"><div class="empty">点击左侧节点</div></aside>
  </div>
</section>
<section id="tab-metrics"><div id="metrics"></div></section>
<section id="tab-figures"><div class="cards" id="figures"></div></section>
<section id="tab-runs"><div id="runs"></div></section>
<section id="tab-decisions"><div id="decisions"></div></section>

<script>const DATA = __DATA__;</script>
<script>
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = v => v === null || v === undefined ? "—" : (typeof v === "number" ? (Number.isInteger(v) ? v : v.toPrecision(6)) : String(v));

document.querySelectorAll("#tabs button").forEach(b => b.addEventListener("click", () => {
  document.querySelectorAll("#tabs button").forEach(x => x.classList.toggle("active", x === b));
  document.querySelectorAll("section").forEach(s => s.classList.toggle("active", s.id === "tab-" + b.dataset.tab));
}));

// ---- 实验树 ----
const {width: W, height: H, node_w: NW, node_h: NH} = DATA.canvas;
const pos = Object.fromEntries(DATA.nodes.map(n => [n.id, n]));
const STATUS_COLOR = {validated:"#34a853",completed:"#34a853",passed:"#34a853",
  failed:"#ea4335",failed_validation:"#ea4335",rejected:"#ea4335",interrupted:"#ea4335",
  awaiting:"#fb8c00",running:"#fb8c00",planned:"#5f7285"};
let svg = `<defs><marker id="arr" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
  <path d="M0,0 L7,3 L0,6 z" fill="#3b4a5c"/></marker>
  <marker id="arrg" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
  <path d="M0,0 L7,3 L0,6 z" fill="#fb8c00"/></marker></defs>`;
for (const e of DATA.edges) {
  const a = pos[e.from], b = pos[e.to];
  if (!a || !b) continue;
  const x1 = a.x + NW/2, y1 = a.y + NH, x2 = b.x + NW/2, y2 = b.y;
  const my = (y1 + y2) / 2;
  const cls = e.gate ? "edge gate" : "edge";
  const marker = e.gate ? "arrg" : "arr";
  svg += `<path class="${cls}" d="M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2-3}" marker-end="url(#${marker})"/>`;
  if (e.gate) svg += `<text class="edge-label" x="${(x1+x2)/2+6}" y="${my}">on_${e.gate}</text>`;
}
for (const n of DATA.nodes) {
  const color = STATUS_COLOR[n.status] || "#5f7285";
  const cx = n.x + NW/2, cy = n.y + NH/2;
  const shape = n.kind === "decision"
    ? `<polygon points="${cx},${n.y} ${n.x+NW},${cy} ${cx},${n.y+NH} ${n.x},${cy}"/>`
    : `<rect x="${n.x}" y="${n.y}" width="${NW}" height="${NH}" rx="8"/>`;
  svg += `<g class="node ${n.kind === "decision" ? "decision" : ""}" data-id="${esc(n.id)}">
    ${shape}
    <circle cx="${n.x+12}" cy="${n.y+12}" r="4" fill="${color}"/>
    <text x="${cx}" y="${cy-4}" text-anchor="middle">${esc(n.id)}</text>
    <text class="sub" x="${cx}" y="${cy+13}" text-anchor="middle">${esc(n.kind === "decision" ? "decision" : n.block)}</text>
  </g>`;
}
const tree = $("#tree");
tree.setAttribute("width", W); tree.setAttribute("height", H);
tree.innerHTML = svg;
tree.addEventListener("click", ev => {
  const g = ev.target.closest(".node");
  if (g) showDetail(g.dataset.id);
});

function showDetail(id) {
  const n = pos[id];
  if (!n) return;
  let h = `<h2>${esc(n.id)} <span class="badge ${esc(n.status)}">${esc(n.status)}</span></h2><div class="kv">`;
  if (n.title) h += `<span class="k">标题</span><span>${esc(n.title)}</span>`;
  h += `<span class="k">类型</span><span>${esc(n.kind)}</span>`;
  if (n.block) h += `<span class="k">积木</span><span>${esc(n.block)}</span>`;
  if (n.run) {
    const r = n.run;
    h += `<span class="k">最新运行</span><span>${esc(r.run_id)}</span>
      <span class="k">开始</span><span>${esc(r.started_at || "—")}</span>
      <span class="k">耗时</span><span>${r.duration_s ?? "—"} s</span>`;
    if (r.error) h += `<span class="k">错误</span><span>${esc(r.error)}</span>`;
    h += `</div>`;
    if (Object.keys(r.metrics).length) {
      h += `<h3>指标</h3><div class="kv">`;
      for (const [k, v] of Object.entries(r.metrics)) h += `<span class="k">${esc(k)}</span><span class="num">${fmt(v)}</span>`;
      h += `</div>`;
    }
    if (r.validations.length) {
      h += `<h3>验证</h3><div class="kv">`;
      for (const v of r.validations)
        h += `<span class="k">${v.passed ? "✓" : "✗"} ${esc(v.name)}</span><span>${esc(v.detail || "")}</span>`;
      h += `</div>`;
    }
    if (r.artifacts.length) {
      h += `<h3>产物</h3><div class="kv">`;
      for (const a of r.artifacts)
        h += `<span class="k">${esc(a.port)}</span><span>${esc(a.path)}<br><small>${esc(a.type)} · ${esc(a.sha256)}…</small></span>`;
      h += `</div>`;
    }
  } else {
    h += `</div><div class="empty">尚无运行记录</div>`;
  }
  $("#detail").innerHTML = h;
}

// ---- 指标对照 ----
(function () {
  if (!DATA.metric_rows.length) { $("#metrics").innerHTML = `<div class="empty">暂无指标</div>`; return; }
  let h = `<table><tr><th>节点</th><th>run_id</th>` +
    DATA.metric_names.map(m => `<th>${esc(m)}</th>`).join("") + `</tr>`;
  for (const row of DATA.metric_rows) {
    h += `<tr><td>${esc(row.node_id)}</td><td>${esc(row.run_id)}</td>` +
      DATA.metric_names.map(m => `<td class="num">${fmt(row.metrics[m])}</td>`).join("") + `</tr>`;
  }
  $("#metrics").innerHTML = h + `</table>`;
})();

// ---- 图表 ----
(function () {
  if (!DATA.figures.length) { $("#figures").innerHTML = `<div class="empty">暂无图表（运行 visualize 积木后生成）</div>`; return; }
  $("#figures").innerHTML = DATA.figures.map(f =>
    `<div class="card"><h3>${esc(f.node_id)} · ${esc(f.name)}<br><small>${esc(f.run_id)}</small></h3>
     <img src="data:image/png;base64,${f.data}" alt="${esc(f.name)}"></div>`).join("");
})();

// ---- 运行记录 ----
(function () {
  if (!DATA.runs.length) { $("#runs").innerHTML = `<div class="empty">暂无运行</div>`; return; }
  let h = `<table><tr><th>run_id</th><th>节点</th><th>状态</th><th>开始</th><th>结束</th></tr>`;
  for (const r of DATA.runs)
    h += `<tr><td>${esc(r.run_id)}</td><td>${esc(r.node_id)}</td>
      <td><span class="badge ${esc(r.status)}">${esc(r.status)}</span></td>
      <td>${esc(r.started_at || "—")}</td><td>${esc(r.finished_at || "—")}</td></tr>`;
  $("#runs").innerHTML = h + `</table>`;
})();

// ---- 决策记录 ----
(function () {
  if (!DATA.decisions.length) { $("#decisions").innerHTML = `<div class="empty">暂无决策</div>`; return; }
  let h = `<table><tr><th>节点</th><th>结果</th><th>模式</th><th>判据</th><th>建议</th><th>决策者</th><th>备注</th><th>时间</th></tr>`;
  for (const d of DATA.decisions) {
    const res = d.final_result ? "PASS" : "FAIL";
    const sug = d.auto_result === null || d.auto_result === undefined ? "—" : (d.auto_result ? "PASS" : "FAIL");
    h += `<tr><td>${esc(d.node_id)}</td>
      <td><span class="badge ${d.final_result ? "passed" : "rejected"}">${res}</span></td>
      <td>${esc(d.mode)}</td><td>${esc(d.expression || "—")}</td><td>${sug}</td>
      <td>${esc(d.actor)}</td><td>${esc(d.comment || "")}</td><td>${esc(d.decided_at)}</td></tr>`;
  }
  $("#decisions").innerHTML = h + `</table>`;
})();
</script>
</body>
</html>
"""
