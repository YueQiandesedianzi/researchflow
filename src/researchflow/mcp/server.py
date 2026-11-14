"""MCP server 实现：复用 CLI 的命令分发（薄胶合，零重复逻辑）。

工具面与 DSH 适配器一一对应（researchflow_*），描述与参数规则保持一致。
"""

from __future__ import annotations

from types import SimpleNamespace

from researchflow.errors import RFError

_INSTRUCTIONS = (
    "ResearchFlow 科研实验工作树。所有实验经 researchflow_* 工具执行；"
    "状态在项目 .researchflow/ 持久化。关键约定：plan 先 validate 再 run；"
    "退出码 0 成功｜2 契约失败（先修计划）｜3 运行失败｜4 等待 researchflow_decide。"
)


def _invoke(command: str, **kwargs) -> dict:
    """调用 CLI 命令分发，返回统一 JSON 载荷。"""
    from researchflow.cli import _DISPATCH

    args = SimpleNamespace(command=command, json=True, **kwargs)
    try:
        code, payload, _text = _DISPATCH[command](args)
    except RFError as exc:
        return {"ok": False, "exit_code": exc.exit_code,
                "error": exc.message, "details": exc.details}
    return {"ok": code == 0, "exit_code": code, **payload}


def build_server():
    try:
        from mcp.server.mcpserver import MCPServer
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            'MCP 支持需要可选依赖：pip install "researchflow[mcp]"（mcp>=2）'
        ) from exc

    server = MCPServer("researchflow", instructions=_INSTRUCTIONS)

    @server.tool(
        name="researchflow_init",
        description="初始化标准 ResearchFlow 科研项目（目录、researchflow.yaml、plan.yaml、AGENTS.md）。幂等，不覆盖已有文件。",
    )
    def tool_init(path: str, template: str | None = None) -> dict:
        """path: 项目目录（不存在则创建）；template: 可选 tabular | timeseries。"""
        return _invoke("init", path=path, template=template, force=False)

    @server.tool(
        name="researchflow_plan",
        description="校验或可视化实验工作树。validate 检查结构、无环、积木契约（契约不符退出码 2）；show 返回带运行状态的 Mermaid 图。",
    )
    def tool_plan(action: str, project: str | None = None) -> dict:
        """action: validate | show；project: 项目目录（含 researchflow.yaml）。"""
        return _invoke("plan", project=project or ".", action=action, format="json")

    @server.tool(
        name="researchflow_run",
        description="运行工作树节点（自动补跑未完成的上游；输入未变的节点自动复用已验证运行）。退出码：0 成功｜2 契约失败｜3 运行/验证失败｜4 等待人工审批或决策（用 researchflow_decide 处理）。返回各节点结果与 RUN-id。",
    )
    def tool_run(project: str, node: str | None = None, all: bool = False,
                 no_cache: bool = False, yes: bool = False) -> dict:
        """project: 项目目录；node 与 all 二选一；yes 自动批准 requires_approval 积木。"""
        return _invoke("run", project=project, node=node, all=all,
                       no_cache=no_cache, yes=yes)

    @server.tool(
        name="researchflow_status",
        description="查看工作树每个节点的状态（planned / validated / failed / failed_validation / awaiting / passed / rejected）。",
    )
    def tool_status(project: str) -> dict:
        """project: 项目目录。"""
        return _invoke("status", project=project)

    @server.tool(
        name="researchflow_runs",
        description="查询运行记录：list 最近运行，或提供 run_id 查看单次运行的完整记录（输入/产物哈希、指标、验证结果、环境指纹）。",
    )
    def tool_runs(project: str, run_id: str | None = None,
                  node: str | None = None, limit: int = 20) -> dict:
        """run_id 如 RUN-000021；node 过滤 list；limit 为 list 条数上限。"""
        return _invoke("runs", project=project, action="show" if run_id else "list",
                       id=run_id, node=node, limit=limit)

    @server.tool(
        name="researchflow_compare",
        description="统一比较多次运行/实验分支的指标，可指定基线输出相对差异。选择器为 RUN-id 或节点 id（取该节点最新已验证运行）。",
    )
    def tool_compare(project: str, selectors: list[str],
                     baseline: str | None = None) -> dict:
        """selectors: RUN-id 或节点 id 列表；baseline: 基线选择器。"""
        return _invoke("compare", project=project, selectors=selectors,
                       baseline=baseline, format="json")

    @server.tool(
        name="researchflow_decide",
        description="确认决策节点（记录决策者、时间与备注；auto_then_manual 模式会附自动判据建议）。决策前其 on_pass 下游被阻断（researchflow_run 退出码 4）。",
    )
    def tool_decide(project: str, node: str, passed: bool,
                    comment: str | None = None) -> dict:
        """node: 决策节点 id；passed: true 通过 / false 驳回。"""
        return _invoke("decide", project=project, node=node,
                       passed=passed, comment=comment)

    @server.tool(
        name="researchflow_export",
        description="导出研究复现包：选定节点及其上游链的产物、配置、积木源码、环境锁定与 PROVENANCE 证据链。verify 会在导出目录内重跑并比对指标。返回导出目录与验证结果。",
    )
    def tool_export(project: str, nodes: str, out: str, verify: bool = False) -> dict:
        """nodes: 逗号分隔的执行节点 id；out: 导出目录（必须为空或不存在）。"""
        return _invoke("export", project=project, nodes=nodes, out=out,
                       verify=verify, no_upstream=False)

    @server.tool(
        name="researchflow_report",
        description="生成单文件 HTML 实验工作台（实验树、指标对照、图表、运行与决策记录），离线可开。返回报告文件路径。",
    )
    def tool_report(project: str, out: str | None = None) -> dict:
        """out: 输出路径（默认 <项目>/report.html）。"""
        return _invoke("report", project=project, out=out)

    return server


def main() -> None:
    build_server().run("stdio")


if __name__ == "__main__":
    main()
