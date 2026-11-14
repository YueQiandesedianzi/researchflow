# 05 — 平台适配器设计（DSH / Codex）

版本：v0.1-draft｜日期：2026-11-13
前提：机制调研结论见 [00-research.md](00-research.md)。**两条铁律：适配器不含核心逻辑；
一切能力经 Core CLI（`rf --json`）或同仓库的 MCP server 暴露。**

## 1. DSH 适配器（V0.3，Cordis bundle）

### 1.1 Bundle 结构

```text
researchflow-dsh/
├── package.json          # "dsh": {"bundle": {"patch": "./cordis.patch.yml"}}
├── cordis.patch.yml
├── index.js              # Host 插件：apply(ctx, config)
├── client.js             # V1.0 才需要：Slots 面板
├── locale/en.json, locale/zh.json
└── icon.svg
```

```yaml
# cordis.patch.yml
- insert:
    - id: researchflow
      name: '@researchflow/dsh-adapter'
      config:
        pythonPath: python
        maxRunMinutes: 120
```

```js
// index.js 骨架
export const Config = /* Schema: pythonPath、maxRunMinutes、autoApproveSafe */ ;

export function apply(ctx, config) {
  // 1) 注册 Agent Tools：researchflow_init / plan / run / status / compare / export / decide
  // 2) 注册斜杠命令族：/researchflow <子命令>
  // 3) 长任务：包装为 ctx.jobs 后台任务，轮询 rf status --json
  // 4) requires_approval 积木与 manual 决策：ctx.approval / ctx.userQuestions
  // 5) 所有资源经 ctx.effect/ctx.on 注册并返回清理
}
```

### 1.2 工具面（与 CLI 一一对应）

| Agent Tool | 包装命令 | 返回（有界 JSON） |
| --- | --- | --- |
| `researchflow_init` | `rf init --json` | 生成的文件清单 |
| `researchflow_plan` | `rf plan validate/show --json` | 校验结果或 Mermaid 文本路径 |
| `researchflow_run` | `rf run <node> --json` | run_id、状态、指标摘要、验证结果 |
| `researchflow_status` | `rf status --json` | 工作树节点状态表 |
| `researchflow_compare` | `rf compare ... --json` | 指标对照表 |
| `researchflow_decide` | `rf decide <node> --pass/--fail` | 决策记录 |
| `researchflow_export` | `rf export ... --json` | 导出目录与 verify 结果 |

设计约束（遵循 agent-experience 原则）：工具描述只写行为与返回；参数规则写在参数上；
输出有界——大产物给路径不内联；关键约束（审批、阻断）出现在调用前的描述中。

### 1.3 与 dsh_workflow 的集成（可选，非依赖）

大规模超参试错时，由 dsh_workflow capsule 并行调 `rf run`（其预算/并发/恢复机制），
实验记录仍全部落在 ResearchFlow Registry。提供示例 capsule，README 说明分工。

### 1.4 UI（V1.0）

Client 插件经 Slots 注册"实验树"面板：读 `rf status/plan show --json`，
节点点击 → Run 详情与产物预览；决策节点提供通过/驳回按钮（走
[practices/user-actions 约定](00-research.md)，与 Agent 工具共享同一操作层）。

## 2. Codex 适配器

### 2.1 V0.2 — Skill 原型（最小成本验证）

放置于仓库 `.agents/skills/researchflow/`（项目级）或 `~/.agents/skills/`（个人级）：

```text
researchflow/
├── SKILL.md              # frontmatter: name + description（路由触发器）
└── references/
    ├── commands.md       # rf 命令面与退出码
    ├── block-catalog.md  # MVP 积木契约速查
    └── plan-format.md    # plan.yaml 规范与示例
```

SKILL.md 遵循渐进披露：首层只讲"何时用 + 六条核心命令 + 三条铁律
（实验必过 rf / 复用积木 / 决策未过不引用结果）"，细节按需从 references 加载。
Agent 经 shell 调 `rf` CLI，无新代码。

### 2.2 V0.4 — 正式 Plugin + MCP（✅ 已实现）

> 实现状态：MCP server 位于 `src/researchflow/mcp/`（mcp v2 SDK，stdio），
> 打包位于 `adapters/codex/plugin/`，marketplace 分发文件在仓库根 `.agents/plugins/`。
> 协议级集成测试见 `tests/test_mcp.py`。以下为原始设计。

```text
researchflow-codex/
├── .codex-plugin/plugin.json
├── skills/researchflow/…        # 同 2.1
├── .mcp.json
└── assets/
```

```jsonc
// .codex-plugin/plugin.json
{
  "name": "researchflow",
  "version": "0.4.0",
  "description": "Composable, verifiable, traceable research experiment trees",
  "skills": "./skills/",
  "mcpServers": "./.mcp.json",
  "interface": {"displayName": "ResearchFlow", "category": "research",
                "capabilities": ["Read", "Write"]}
}
```

```jsonc
// .mcp.json —— MCP server 随 Core 同仓库发布：pip install researchflow[mcp]
{"researchflow": {"command": "python", "args": ["-m", "researchflow.mcp"]}}
```

MCP 工具面与 1.2 完全等价（`init/plan/run/status/compare/decide/export`），
实现上复用 Core 的 Python API 而非包 CLI，同一语义两种传输。
分发：仓库级 `.agents/plugins/marketplace.json` + npm/git source；
Codex 兼容 Claude 插件约定，同一 marketplace 文件可被双端消费。

## 3. 两平台共享资产

| 资产 | 归属 | 说明 |
| --- | --- | --- |
| Core CLI 与命令面 | Core 仓库 | 适配器唯一接口约定（JSON、退出码 0/2/3/4） |
| AGENTS.md 模板 | Core 仓库 | `rf init` 生成，DSH 与 Codex 会话读同一份 |
| 积木包 | 各自仓库（entry points） | 两平台自动可用，零适配 |
| MCP server | Core 仓库 extra | Codex 用；DSH 侧亦可挂为 MCP 连接（备选路径） |
| 版本兼容矩阵 | Core 文档 | 适配器版本 ↔ 所需 Core 最低版本（见 [06](06-mvp-plan.md) 第 5 节） |
