"""rf CLI —— ResearchFlow Core 唯一对外入口。

约定：
- ``--json``：stdout 输出有界 JSON（大结果给路径，不内联）；
- 退出码：0 成功｜1 未分类错误｜2 契约/校验失败｜3 运行失败｜4 等待人工审批/决策。
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from researchflow import __version__
from researchflow.errors import ProjectNotFoundError, RFError
from researchflow.project import Project, doctor
from researchflow.util import dump_yaml


def build_parser():
    # --json / -C 既可放在子命令前，也可放在子命令后。
    # 子解析器上的副本必须用 SUPPRESS 默认值——argparse 子解析器在全新命名空间
    # 解析后整体回写，默认值会覆盖主解析器已设置的 -C。
    common_main = argparse.ArgumentParser(add_help=False)
    common_main.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    common_main.add_argument("-C", "--project", default=".",
                             help="项目目录（向上查找 researchflow.yaml）")
    common_sub = argparse.ArgumentParser(add_help=False)
    common_sub.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                            help=argparse.SUPPRESS)
    common_sub.add_argument("-C", "--project", default=argparse.SUPPRESS,
                            help=argparse.SUPPRESS)

    p = argparse.ArgumentParser(
        prog="rf",
        description="ResearchFlow — 可组合、可验证、可追溯的科研实验工作树",
        parents=[common_main])
    p.add_argument("--version", action="version", version=f"researchflow {__version__}")
    sub = p.add_subparsers(dest="command", required=True, parser_class=argparse.ArgumentParser)

    def add(name, **kwargs):
        return sub.add_parser(name, parents=[common_sub], **kwargs)

    sp = add("init", help="初始化标准科研项目")
    sp.add_argument("path", nargs="?", default=".")
    sp.add_argument("--template", choices=["tabular", "timeseries"])
    sp.add_argument("--force", action="store_true", help="覆盖已存在文件")

    add("doctor", help="一致性检查")

    sp = add("blocks", help="积木目录")
    sp.add_argument("action", choices=["list", "check"])
    sp.add_argument("path", nargs="?", help="check 时的积木目录")

    sp = add("plan", help="实验工作树")
    sp.add_argument("action", choices=["validate", "show"])
    sp.add_argument("--format", choices=["mermaid", "json"], default="mermaid")

    sp = add("run", help="运行节点（自动补跑未完成的上游）")
    sp.add_argument("node", nargs="?")
    sp.add_argument("--all", action="store_true", help="运行整棵树")
    sp.add_argument("--no-cache", action="store_true", help="禁用新鲜度判断与缓存")
    sp.add_argument("--yes", action="store_true", help="自动批准 requires_approval 积木")

    add("status", help="工作树节点状态一览")

    sp = add("runs", help="运行记录")
    sp.add_argument("action", choices=["list", "show"])
    sp.add_argument("id", nargs="?", help="show 时的 RUN-id")
    sp.add_argument("--node", help="list 时按节点过滤")
    sp.add_argument("--limit", type=int, default=20)

    sp = add("decide", help="确认决策节点")
    sp.add_argument("node")
    group = sp.add_mutually_exclusive_group(required=True)
    group.add_argument("--pass", dest="passed", action="store_true")
    group.add_argument("--fail", dest="passed", action="store_false")
    sp.add_argument("--comment")

    sp = add("compare", help="比较运行（RUN-id 或节点 id）")
    sp.add_argument("selectors", nargs="+")
    sp.add_argument("--baseline", help="基线选择器，输出相对差异")
    sp.add_argument("--format", choices=["md", "csv", "json"], default="md")

    sp = add("export", help="导出研究复现包")
    sp.add_argument("--nodes", required=True, help="逗号分隔的执行节点 id")
    sp.add_argument("--out", required=True, help="导出目录（必须为空或不存在）")
    sp.add_argument("--verify", action="store_true", help="在导出目录内重跑并比对指标")
    sp.add_argument("--no-upstream", action="store_true", help="不包含上游链")

    sp = add("report", help="生成单文件 HTML 实验工作台报告")
    sp.add_argument("--out", help="输出路径（默认 <项目>/report.html）")
    sp.add_argument("--data", action="store_true", help="只输出工作台数据载荷（JSON），不写 HTML")
    return p


# ---------- 命令实现 ----------

def _open_project(args) -> Project:
    return Project.open(args.project)


def cmd_init(args):
    result = Project.init(args.path, template=args.template, force=args.force)
    text = f"✓ 项目已初始化: {result['root']}"
    if result["created"]:
        text += f"\n  生成: {', '.join(result['created'])}"
    if result["skipped"]:
        text += f"\n  跳过（已存在）: {', '.join(result['skipped'])}"
    text += "\n下一步: 编辑 plan.yaml，然后 rf plan validate && rf run --all --yes"
    return 0, result, text


def cmd_doctor(args):
    report = doctor(_open_project(args))
    lines = [f"{'✓' if c['ok'] else '✗'} {c['name']}: {c['detail']}" for c in report["checks"]]
    return (0 if report["ok"] else 3), report, "\n".join(lines)


def cmd_blocks(args):
    from researchflow.blocks.loader import discover
    from researchflow.blocks.schema import load_block

    if args.action == "check":
        if not args.path:
            raise ProjectNotFoundError("blocks check 需要积木目录路径")
        block = load_block(args.path, "local", 3)
        return 0, {"block": block.ref, "source": str(block.dir)}, \
            f"✓ 契约有效: {block.ref}（{block.title}）"

    try:
        project = _open_project(args)
        root = project.root
    except ProjectNotFoundError:
        root = None
    index = discover(root)
    rows = [{
        "id": b.id, "version": b.version_str, "category": b.category,
        "source": b.source, "deterministic": b.deterministic,
        "requires_approval": b.requires_approval, "title": b.title,
    } for b in index.all_best()]
    lines = [f"{b.id:<32} {b.version_str:<8} {b.category:<12} {b.source:<16} {b.title}"
             for b in index.all_best()]
    if index.warnings:
        lines += ["", "警告:"] + [f"  - {w}" for w in index.warnings]
    return 0, {"blocks": rows, "warnings": index.warnings}, "\n".join(lines)


def cmd_plan(args):
    from researchflow.blocks.contract import check_plan_contracts
    from researchflow.blocks.loader import discover
    from researchflow.plan.engine import render_mermaid, topo_order
    from researchflow.plan.model import load_plan

    project = _open_project(args)
    plan = load_plan(project.root / "plan.yaml")
    index = discover(project.root)
    check_plan_contracts(plan, index)
    order = topo_order(plan)
    if args.action == "validate":
        return 0, {"nodes": len(plan.nodes), "order": order}, \
            f"✓ 计划有效: {len(plan.nodes)} 个节点；执行顺序: {' → '.join(order)}"

    status = {}
    try:
        from researchflow.runner.executor import Executor
        ex = Executor(project, quiet=True)
        try:
            status = ex.status()
        finally:
            ex.close()
    except RFError:
        pass
    mermaid = render_mermaid(plan, status)
    if args.format == "json":
        return 0, {"mermaid": mermaid, "status": status}, mermaid
    return 0, {"mermaid": mermaid}, mermaid


def cmd_run(args):
    from researchflow.runner.executor import Executor

    if not args.all and not args.node:
        raise ProjectNotFoundError("请指定节点 id，或使用 --all 运行整棵树")
    project = _open_project(args)
    ex = Executor(project)
    if args.json:
        ex.emit = lambda m: print(m, file=sys.stderr, flush=True)
    try:
        code = ex.run(target=args.node, run_all=args.all,
                      no_cache=args.no_cache, yes=args.yes)
        summary = {"results": ex.results}
        lines = [f"{n}: {r}" for n, r in ex.results.items()]
        return code, summary, "\n".join(lines) if lines else "（无节点需要运行）"
    finally:
        ex.close()


def cmd_status(args):
    from researchflow.plan.engine import topo_order
    from researchflow.runner.executor import Executor

    ex = Executor(_open_project(args), quiet=True)
    try:
        states = ex.status()
        order = topo_order(ex.plan)
        icon = {"validated": "✓", "completed": "✓", "failed": "✗", "failed_validation": "✗",
                "interrupted": "⚠", "passed": "✓", "rejected": "✗", "awaiting": "?",
                "running": "…", "planned": "·"}
        lines = [f"[{icon.get(states.get(nid), '?')}] {nid:<28} {states.get(nid)}"
                 for nid in order]
        return 0, {"status": states}, "\n".join(lines)
    finally:
        ex.close()


def cmd_runs(args):
    from researchflow.registry.store import Store

    project = _open_project(args)
    store = Store.open(project.rf_dir)
    try:
        if args.action == "show":
            if not args.id:
                raise ProjectNotFoundError("runs show 需要 RUN-id")
            run = store.get_run(args.id.upper())
            if run is None:
                raise ProjectNotFoundError(f"运行 {args.id} 不存在")
            data = json.loads(run["run_json"])
            return 0, data, json.dumps(data, ensure_ascii=False, indent=2, default=str)
        rows = store.runs(node_id=args.node, limit=args.limit)
        data = [{"run_id": r["run_id"], "node_id": r["node_id"], "status": r["status"],
                 "started_at": r["started_at"]} for r in rows]
        lines = [f"{r['run_id']}  {r['node_id']:<28} {r['status']:<18} {r['started_at']}"
                 for r in rows]
        return 0, {"runs": data}, "\n".join(lines)
    finally:
        store.close()


def cmd_decide(args):
    from researchflow.runner.executor import Executor

    ex = Executor(_open_project(args), quiet=True)
    try:
        result = ex.decide(args.node, args.passed, comment=args.comment)
        text = f"{'✓ PASS' if result['final'] else '✗ FAIL'} 决策 {result['node_id']}" \
               f"（{result['actor']}）"
        if result["auto_suggestion"] is not None:
            text += f"；自动判据建议 {'PASS' if result['auto_suggestion'] else 'FAIL'}"
        return 0, result, text
    finally:
        ex.close()


def cmd_compare(args):
    from researchflow.compare.compare import compare, format_csv, format_md
    from researchflow.registry.store import Store

    project = _open_project(args)
    store = Store.open(project.rf_dir)
    try:
        data = compare(store, args.selectors, baseline=args.baseline)
    finally:
        store.close()
    if args.format == "json":
        return 0, data, json.dumps(data, ensure_ascii=False, indent=2, default=str)
    text = format_csv(data) if args.format == "csv" else format_md(data)
    return 0, data, text


def cmd_export(args):
    from researchflow.export.exporter import export

    project = _open_project(args)
    nodes = [s.strip() for s in args.nodes.split(",") if s.strip()]
    emit = (lambda m: print(m, file=sys.stderr, flush=True)) if args.json else print
    result = export(project, nodes, args.out, verify=args.verify,
                    include_upstream=not args.no_upstream, emit=emit)
    lines = [f"✓ 已导出: {result['out_dir']}",
             f"  节点: {', '.join(result['nodes'])}",
             f"  积木快照: {', '.join(result['blocks'])}"]
    if result["verify"] is not None:
        v = result["verify"]
        lines.append(f"  verify: {'✓ 通过' if v['ok'] else '✗ 未过'}"
                     f"（比对 {v.get('compared_metrics', 0)} 项指标）")
        if not v["ok"]:
            code = 3
            return code, result, "\n".join(lines)
    return 0, result, "\n".join(lines)


def cmd_report(args):
    from researchflow.report.report import collect, generate

    if getattr(args, "data", False):
        return 0, collect(_open_project(args)), "（工作台数据载荷）"
    out = generate(_open_project(args), args.out)
    return 0, {"report": str(out)}, \
        f"✓ 报告已生成: {out}\n用浏览器打开即可查看（单文件、离线可用）"


_DISPATCH = {
    "init": cmd_init, "doctor": cmd_doctor, "blocks": cmd_blocks,
    "plan": cmd_plan, "run": cmd_run, "status": cmd_status, "runs": cmd_runs,
    "decide": cmd_decide, "compare": cmd_compare, "export": cmd_export,
    "report": cmd_report,
}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code, payload, text = _DISPATCH[args.command](args)
    except RFError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": exc.message, "details": exc.details,
                              "exit_code": exc.exit_code}, ensure_ascii=False, indent=2))
        else:
            print(f"错误: {exc.message}", file=sys.stderr)
            for d in exc.details:
                print(f"  - {d}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        return 130
    except Exception:
        traceback.print_exc()
        return 1
    if args.json:
        print(json.dumps({"ok": code == 0, "exit_code": code, **payload},
                         ensure_ascii=False, indent=2, default=str))
    elif text:
        print(text)
    return code
