"""导出选定节点及其上游链为**可独立复现的研究包**。

导出目录本身就是一个合法 ResearchFlow 项目（plan.yaml + blocks/ + configs/ + data/），
``--verify`` 在其中重跑全链并与原 Run 指标按容差比对，通过才标记 verified。
决策节点不进导出包（计算链可复现，判断属于研究决策，记录在 PROVENANCE）。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from researchflow.blocks.contract import check_plan_contracts
from researchflow.blocks.loader import discover
from researchflow.errors import ContractError
from researchflow.plan.engine import ancestors
from researchflow.plan.model import load_plan
from researchflow.registry.store import Store
from researchflow.util import atomic_write_text, dump_yaml, now_iso, read_json, write_json_atomic


def _referenced_param_files(project, nodes):
    """收集节点 params 中指向项目内现有文件的字符串值（configs、data 等）。"""
    files = set()
    for n in nodes:
        for value in (n.params or {}).values():
            if isinstance(value, str):
                p = project.root / value
                try:
                    if p.is_file() and p.is_relative_to(project.root):
                        files.add(Path(value))
                except ValueError:
                    pass
    return sorted(files)


def export(project, node_ids, out_dir, verify=False, include_upstream=True,
           tolerance=1e-6, emit=print) -> dict:
    store = Store.open(project.rf_dir)
    plan = load_plan(project.root / "plan.yaml")
    index = discover(project.root)
    check_plan_contracts(plan, index)

    selected = []
    for nid in node_ids:
        node = plan.get(nid)
        if node.kind == "decision":
            raise ContractError(
                f"导出目标应为执行节点，{nid} 是决策节点（其判断已随 PROVENANCE 记录）")
        selected.append(nid)
    included = set(selected)
    if include_upstream:
        for nid in selected:
            included |= ancestors(plan, nid)
    exec_nodes = [n for n in plan.nodes if n.id in included and n.kind == "execution"]

    runs = {}
    for n in exec_nodes:
        run = store.latest_run(n.id, ("validated",))
        if run is None:
            raise ContractError(f"节点 {n.id} 没有已验证的运行，无法导出（先 rf run）")
        runs[n.id] = run

    out_dir = Path(out_dir).resolve()
    if out_dir.exists() and any(out_dir.iterdir()):
        raise ContractError(f"导出目录非空: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) plan 子集（仅执行节点；绑定均在包含集内，因为已并入祖先）
    subset = []
    for n in exec_nodes:
        entry = {"id": n.id, "kind": "execution", "block": n.block, "title": n.title}
        if n.params:
            entry["params"] = n.params
        if n.inputs:
            entry["inputs"] = n.inputs
        subset.append(entry)
    atomic_write_text(out_dir / "plan.yaml", dump_yaml({
        "schema_version": plan.schema_version,
        "project": f"{plan.project}-export",
        "meta": {"exported_from": plan.project, "exported_at": now_iso()},
        "nodes": subset,
    }))

    # 2) 项目配置
    config = dict(project.config)
    config["name"] = f"{config.get('name', plan.project)}-export"
    atomic_write_text(out_dir / "researchflow.yaml", dump_yaml(config))

    # 3) 积木源码快照（项目级 blocks/ 覆盖内置，保证 source hash 一致 → 缓存键一致）
    snapshotted = set()
    for n in exec_nodes:
        block = index.resolve(n.block)
        if block.id in snapshotted:
            continue
        snapshotted.add(block.id)
        shutil.copytree(block.dir, out_dir / "blocks" / block.id)

    # 4) 参数引用的项目文件（configs/*.yaml、data/*.csv 等）
    for rel in _referenced_param_files(project, exec_nodes):
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(project.root / rel, dest)

    # 5) 证据：原 Run 记录 + 产物副本
    provenance = {"exported_at": now_iso(), "source_project": str(project.root),
                  "selected_nodes": selected, "nodes": {}}
    for n in exec_nodes:
        run = runs[n.id]
        rj = json.loads(run["run_json"])
        src_run = project.root / ".researchflow" / "runs" / run["run_id"]
        dest_run = out_dir / "evidence" / "runs" / run["run_id"]
        (dest_run / "artifacts").mkdir(parents=True, exist_ok=True)
        for name in ("run.json", "resolved.yaml", "validation.json"):
            if (src_run / name).is_file():
                shutil.copy2(src_run / name, dest_run / name)
        for ref in rj.get("artifacts", {}).values():
            src = project.root / ref["path"]
            if src.is_file():
                shutil.copy2(src, dest_run / "artifacts" / src.name)
        provenance["nodes"][n.id] = {
            "run_id": run["run_id"], "block": rj.get("block"),
            "params_sha256": rj.get("params_sha256"), "inputs": rj.get("inputs"),
            "code": rj.get("code"), "env": rj.get("env"),
            "metrics": rj.get("metrics"), "status": rj.get("status"),
        }
    write_json_atomic(out_dir / "PROVENANCE.json", provenance)

    # 6) 环境锁定（失败记入 warnings，不再静默）+ 复现说明
    warnings: list = []
    try:
        freeze = subprocess.run([sys.executable, "-m", "pip", "freeze", "--quiet"],
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=60)
        if freeze.returncode == 0 and freeze.stdout.strip():
            atomic_write_text(out_dir / "requirements-lock.txt",
                              "\n".join(sorted(freeze.stdout.splitlines())) + "\n")
        else:
            warnings.append(f"requirements-lock.txt 生成失败（pip freeze 退出码 {freeze.returncode}）")
    except Exception as exc:
        warnings.append(f"requirements-lock.txt 生成失败（{type(exc).__name__}）")
    atomic_write_text(out_dir / "reproduce.sh",
                      "#!/bin/sh\n# 在本目录重跑全部实验链\npython -m researchflow run --all --yes\n")
    atomic_write_text(out_dir / "reproduce.ps1",
                      "# 在本目录重跑全部实验链\npython -m researchflow run --all --yes\n")

    # 7) verify（在导出目录内重跑并做产物级比对）→ VERIFY.json → README（真实状态）
    verify_result = None
    if verify:
        verify_result = _verify(out_dir, store, runs, selected, tolerance, emit, warnings)
    verify_doc = {
        "status": verify_result["status"] if verify_result else "skipped",
        "compared_metrics": (verify_result or {}).get("compared_metrics", 0),
        "compared_artifacts": (verify_result or {}).get("compared_artifacts", 0),
        "diffs": (verify_result or {}).get("diffs", []),
        "tolerance": tolerance,
        "warnings": warnings,
        "verified_at": now_iso(),
    }
    write_json_atomic(out_dir / "VERIFY.json", verify_doc)
    atomic_write_text(out_dir / "README.md", _export_readme(plan, selected, verify_doc))

    verified = bool(verify_result and verify_result["ok"]) if verify else False
    store.add_export(out_dir, selected, verified)
    return {
        "out_dir": str(out_dir),
        "nodes": [n.id for n in exec_nodes],
        "blocks": sorted(snapshotted),
        "runs": {nid: runs[nid]["run_id"] for nid in runs},
        "verified": verified,
        "verify": verify_result or {"status": "skipped"},
    }


def _export_readme(plan, selected, verify_doc: dict) -> str:
    lines = [
        f"# {plan.project} — ResearchFlow 研究复现包",
        "",
        f"- 导出节点: {', '.join(selected)}（含全部上游链）",
        "- `plan.yaml` / `blocks/` / `configs/` / `data/`：完整计算链，可直接重跑",
        "- `PROVENANCE.json`：每个节点的运行记录、输入/产物哈希、代码与环境指纹",
        "- `evidence/runs/`：原始 Run 记录与产物副本",
        "- `VERIFY.json`：复现校验的机器可读结果",
        "- `requirements-lock.txt`：导出时的 Python 环境锁定",
        "",
        "## 复现",
        "",
        "```sh",
        "pip install researchflow  # 或指向你的 Core 源码",
        "python -m researchflow run --all --yes",
        "```",
        "",
    ]
    status = verify_doc.get("status")
    if status == "verified":
        lines.append(
            f"> ✅ 本包已通过 `--verify` 重跑校验（指标 {verify_doc['compared_metrics']} 项 + "
            f"确定性产物 {verify_doc['compared_artifacts']} 项，全部一致）。")
    elif status == "failed":
        lines.append(
            f"> ❌ 本包**未通过** verify 重跑校验（{len(verify_doc.get('diffs', []))} 处差异），"
            f"详见 VERIFY.json 的 diffs。")
    elif status == "unverifiable":
        lines.append(
            "> ⚠️ verify 无法执行有效比较（没有可比较的指标或确定性产物），"
            "复现结果**不可确认**，详见 VERIFY.json。")
    else:
        lines.append("> 未执行 verify 校验（导出时未加 --verify）。")
    for w in verify_doc.get("warnings") or []:
        lines.append(f"> ⚠️ {w}")
    return "\n".join(lines)


def _verify(out_dir, store, runs, selected, tolerance, emit, warnings=None) -> dict:
    """在导出目录内重跑实验链并做**产物级**复现比对（R4）。

    比对策略：metrics 按容差；table/indices/json 确定性产物按 sha256；
    figure/model 仅存在性检查。没有任何有效比较项 → unverifiable（不得判过）。
    """
    emit("  [verify] 在导出目录内重跑实验链…")
    proc = subprocess.run(
        [sys.executable, "-m", "researchflow", "--json", "-C", str(out_dir),
         "run", "--all", "--yes"],
        cwd=str(out_dir), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=3600)
    if proc.returncode != 0:
        return {"ok": False, "status": "failed", "stage": "rerun",
                "detail": (proc.stdout + proc.stderr)[-2000:],
                "warnings": warnings or []}

    from researchflow.registry.artifacts import abs_path as _abs

    new_store = Store.open(out_dir / ".researchflow")
    diffs, compared_metrics, compared_artifacts, existence = [], 0, 0, 0
    try:
        for nid in selected:
            old_run = runs[nid]
            old_rj = json.loads(old_run["run_json"])
            new_run = new_store.latest_run(nid, ("validated",))
            if new_run is None:
                diffs.append({"node": nid, "issue": "重跑后无已验证运行"})
                continue
            new_arts = {a["port"]: a for a in new_store.artifacts_of(new_run["run_id"])}

            old_metrics = store.metrics_of(old_run["run_id"])
            new_metrics = new_store.metrics_of(new_run["run_id"])
            for name, old_v in old_metrics.items():
                new_v = new_metrics.get(name)
                compared_metrics += 1
                if new_v is None:
                    diffs.append({"node": nid, "metric": name, "issue": "重跑缺少该指标"})
                elif abs(new_v - old_v) > tolerance * max(abs(old_v), 1e-12):
                    diffs.append({"node": nid, "metric": name,
                                  "original": old_v, "reproduced": new_v})

            for port, ref in (old_rj.get("artifacts") or {}).items():
                atype = ref.get("type")
                new_a = new_arts.get(port)
                if new_a is None:
                    diffs.append({"node": nid, "port": port, "issue": "重跑缺少该产物"})
                    continue
                if atype in ("table", "indices", "json"):
                    compared_artifacts += 1
                    if new_a["sha256"] != ref["sha256"]:
                        diffs.append({"node": nid, "port": port,
                                      "issue": "产物内容不一致",
                                      "original_sha256": ref["sha256"][:16],
                                      "reproduced_sha256": new_a["sha256"][:16]})
                else:  # figure / model / file：存在性 + 非空
                    existence += 1
                    p = _abs(out_dir, {"path": new_a["path"]})
                    if not p.is_file() or p.stat().st_size == 0:
                        diffs.append({"node": nid, "port": port, "issue": "产物缺失或为空"})
    finally:
        new_store.close()

    compared = compared_metrics + compared_artifacts
    if not diffs and compared == 0:
        return {"ok": False, "status": "unverifiable",
                "reason": f"没有可比较的指标或确定性产物（仅 {existence} 项存在性检查）",
                "compared_metrics": 0, "compared_artifacts": 0,
                "warnings": warnings or []}
    return {"ok": not diffs,
            "status": "verified" if not diffs else "failed",
            "compared_metrics": compared_metrics,
            "compared_artifacts": compared_artifacts,
            "diffs": diffs, "warnings": warnings or []}
