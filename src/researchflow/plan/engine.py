"""工作树拓扑、门禁边与 Mermaid 渲染。"""

from __future__ import annotations

from researchflow.errors import PlanError
from researchflow.plan.model import parse_binding

_STATUS_ICON = {
    "validated": "✓", "completed": "✓", "failed": "✗", "failed_validation": "✗",
    "running": "…", "interrupted": "⚠", "passed": "✓", "rejected": "✗",
    "awaiting": "?", "planned": "·",
}


def dependencies(node) -> set:
    """节点的数据依赖（来自输入绑定的上游节点 id）。"""
    deps = set()
    for binding in (node.inputs or {}).values():
        if isinstance(binding, dict) and "from" in binding:
            try:
                up_id, _ = parse_binding(binding["from"])
                deps.add(up_id)
            except PlanError:
                pass  # 契约校验阶段已报告
    return deps


def gate_edges(plan) -> dict:
    """决策门禁边: {目标节点 id: [(决策节点 id, "pass"|"fail")]}。"""
    edges: dict[str, list] = {}
    for node in plan.nodes:
        if node.kind != "decision":
            continue
        for target in node.on_pass:
            edges.setdefault(target, []).append((node.id, "pass"))
        for target in node.on_fail:
            edges.setdefault(target, []).append((node.id, "fail"))
    return edges


def topo_order(plan) -> list:
    """Kahn 拓扑排序（同层按计划声明顺序）。有环抛 PlanError。"""
    node_ids = [n.id for n in plan.nodes]
    deps = {n.id: dependencies(n) & set(node_ids) for n in plan.nodes}
    # 决策门禁也构成序关系
    for target, gates in gate_edges(plan).items():
        if target in deps:
            deps[target] |= {g[0] for g in gates}
    indegree = {nid: len(d) for nid, d in deps.items()}
    order_map = {nid: i for i, nid in enumerate(node_ids)}
    ready = sorted([nid for nid, d in indegree.items() if d == 0], key=order_map.get)
    order = []
    while ready:
        nid = ready.pop(0)
        order.append(nid)
        for other, d in deps.items():
            if nid in d:
                d.discard(nid)
                indegree[other] -= 1
                if indegree[other] == 0:
                    ready.append(other)
                    ready.sort(key=order_map.get)
    if len(order) != len(node_ids):
        cyclic = sorted(set(node_ids) - set(order))
        raise PlanError(f"工作树存在循环依赖，涉及节点: {cyclic}")
    return order


def ancestors(plan, node_id: str) -> set:
    """node_id 的全部上游（含门禁依赖），含自身。"""
    deps = {n.id: dependencies(n) for n in plan.nodes}
    for target, gates in gate_edges(plan).items():
        deps.setdefault(target, set())
        deps[target] |= {g[0] for g in gates}
    seen, stack = set(), [node_id]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(deps.get(cur, ()))
    return seen


def render_mermaid(plan, status: dict | None = None) -> str:
    status = status or {}
    lines = ["flowchart TB"]
    alias = {n.id: f"n{i}" for i, n in enumerate(plan.nodes)}
    classed = {"ok": [], "bad": [], "wait": [], "todo": []}
    for n in plan.nodes:
        st = status.get(n.id, "planned")
        icon = _STATUS_ICON.get(st, "·")
        label = f"{icon} {n.id}"
        if n.kind == "decision":
            lines.append(f'    {alias[n.id]}{{{{"{label}"}}}}')
        else:
            block_id = (n.block or "").split("@")[0]
            lines.append(f'    {alias[n.id]}["{label}<br/>{block_id}"]')
        bucket = ("ok" if st in ("validated", "completed", "passed")
                  else "bad" if st in ("failed", "failed_validation", "rejected", "interrupted")
                  else "wait" if st in ("awaiting", "running")
                  else "todo")
        classed[bucket].append(alias[n.id])
    for n in plan.nodes:
        for binding in (n.inputs or {}).values():
            if isinstance(binding, dict) and "from" in binding:
                try:
                    up_id, _ = parse_binding(binding["from"])
                    if up_id in alias:
                        lines.append(f"    {alias[up_id]} --> {alias[n.id]}")
                except PlanError:
                    pass
    for target, gates in gate_edges(plan).items():
        for dec_id, expect in gates:
            if target in alias and dec_id in alias:
                lines.append(f"    {alias[dec_id]} -. {('on_pass' if expect == 'pass' else 'on_fail')} .-> {alias[target]}")
    lines += [
        "    classDef ok fill:#1b5e20,stroke:#2e7d32,color:#fff",
        "    classDef bad fill:#b71c1c,stroke:#c62828,color:#fff",
        "    classDef wait fill:#e65100,stroke:#ef6c00,color:#fff",
        "    classDef todo fill:#37474f,stroke:#546e7a,color:#fff",
    ]
    for bucket, ids in classed.items():
        if ids:
            lines.append(f"    class {','.join(ids)} {bucket}")
    return "\n".join(lines)
