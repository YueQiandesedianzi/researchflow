# 00 — 平台机制与现有工具调研

> 对应第一轮任务 1–3：阅读 DSH / Codex 官方插件机制，检索现有开源工作流编排项目，
> 确定功能重叠与可复用部分。调研时间：2026-11-13。

## 1. DSH（DeepSeek Harness）插件机制

来源：DSH 内置 `cordis-plugin-development` 技能文档（随安装分发）、
[dsh_workflow README](https://github.com/omdsh-dev/dsh_workflow)、
[dshbase 插件目录](https://dshbase.com/plugins/dsh-workflow-2/)。

### 1.1 安装单元：Bundle

- Bundle 是一个 npm 包，`package.json` 声明 `dsh.bundle.patch` 指向 `cordis.patch.yml`；
  patch 向 Cordis 合成树 `insert` 插件行（`id` / `name` / `config`）。
- 通过 `plugin_manager` 的 `install_bundle` 安装进 profile，影响该 profile 的所有会话，
  重启后保留；新 bundle 可经 HMR 即时激活。
- 插件可携带展示元数据（`locale/*.json` 的 `meta.title` / `meta.description`）与图标，
  供 Plugin Manager 与设置页在未激活状态下读取。

### 1.2 Host 插件形态

```js
// index.js —— 三种导出形式之一，不可混用
export function apply(ctx, config) {}
export const inject = ['tools'];      // 声明依赖的服务
export const Config = /* Schema */;   // 激活时校验 config
```

- 所有资源在 `apply` 内用 `ctx.effect` / `ctx.on` 注册并返回清理函数。
- 可注册的扩展点（由 Cordis 服务与检查工具确认）：
  **Agent Tools**、**斜杠命令**、Session 事件、后台 jobs、审批（`ctx.approval`）、
  一次性人类确认（`ctx.userQuestions`）、子 Agent（`ctx.subagents`）、
  Client UI Slots（面板/装饰）等。
- 插件配置变更通过 `configEditor` 服务持久化；密钥走 `ctx.credentials`。

### 1.3 对 ResearchFlow 的含义

DSH 适配器应做成**标准 bundle**：一个 Host 插件注册一组 `researchflow_*` Agent Tools
和 `/researchflow` 斜杠命令族，工具实现只调用 Core CLI 并返回有界 JSON；
长耗时运行挂到 `ctx.jobs`；需要人工审批的节点走 `ctx.approval` / `ctx.userQuestions`。
V1.0 再用 Client Slots 做实验树面板。**适配器中不放任何核心逻辑。**

## 2. Codex 插件机制

来源：[OpenAI Plugins 官方文档](https://learn.chatgpt.com/docs/plugins)、
[Build skills](https://learn.chatgpt.com/docs/build-skills.md)、
[插件创作规范](https://developers.openai.com/plugins/build/plugins)、
[Codex CLI 插件系统解析](https://codex.danielvaughan.com/2026/03/30/codex-cli-plugin-system/)、
[第三方调研汇总](https://github.com/superset-sh/superset/blob/d234858cdbfd67ee8f18dc24ca92b1f53314ade6/docs/codex-plugins-research.md)。

### 2.1 安装单元：Plugin

一个 plugin 是可安装单元，可打包 **Skills + Apps（连接器）+ MCP servers**：

```text
plugin-name/
├── .codex-plugin/plugin.json   # 必需清单：name/version/description/skills/mcpServers/interface
├── skills/<skill-name>/SKILL.md
├── .mcp.json                   # 可选：stdio 或 HTTP MCP 服务
└── assets/
```

- 分发经三级 marketplace：OpenAI 官方 / 仓库级 `.agents/plugins/marketplace.json` /
  个人 `~/.agents/plugins/marketplace.json`；条目带安装策略
  （`INSTALLED_BY_DEFAULT` / `AVAILABLE` / `NOT_AVAILABLE`）。
- 安装在 `~/.codex/config.toml` 写入启用条目；**无热重载**，新会话生效。

### 2.2 Skills

- 一个 skill = 含 `SKILL.md` 的目录（frontmatter：`name`、`description`，
  description 兼作路由触发器），可带 `scripts/`、`references/`、`assets/`。
- 发现作用域就近优先：仓库 `.agents/skills/` → 用户 `~/.agents/skills/` → ADMIN → 系统内置。
- **渐进披露**：初始上下文只放 name/description/path（上限约上下文 2% 或 8000 字符），
  被选中后才加载完整 SKILL.md。
- 调用方式：模型按 description 隐式匹配，或显式 `$skill`。

### 2.3 MCP

- `.mcp.json` 声明 stdio（`command` + `args`）或 HTTP（`url` + 头）服务；
  工具命名空间 `mcp__<server>__<tool>` 防止冲突。
- `config.toml` 支持 per-tool 的启用与审批策略。

### 2.4 对 ResearchFlow 的含义

- **V0.2（Skill 原型）**：`researchflow` skill 只用渐进披露教 Agent 使用 `rf` CLI——
  SKILL.md 给入口，`references/` 放积木目录与 plan 格式细节。零代码成本、最快验证习惯。
- **V0.4（正式 Plugin）**：`.codex-plugin/plugin.json` 打包 skills + `.mcp.json`，
  MCP 服务（`researchflow-mcp`，随 Core 同仓库发布的 Python stdio server）暴露与
  DSH 适配器等价的能力面。Codex 兼容 Claude 插件约定，同一 marketplace 文件可被双端消费。

## 3. 现有工作流编排项目与功能重叠

### 3.1 dsh_workflow（重点研究对象）

[dsh_workflow](https://github.com/omdsh-dev/dsh_workflow) 是官方 bundle 形态的 DSH 插件，
已实现：版本化 workflow capsule、run graph + `events.jsonl` + artifacts 持久落盘、
按 run 快照重跑 / effect cache 续跑、并发与 token 预算硬限制、审批分级、
QuickJS 沙箱执行生成式流程、六个标准 pattern（fan-out、对抗验证等）、
`/workflow` 命令族与三个 Agent 工具。

**结论：通用 Agent 编排已被解决。** ResearchFlow 不重造这一层：

| dsh_workflow 已覆盖 | ResearchFlow 的差异化 |
| --- | --- |
| 多 Agent 并行调度、暂停/恢复、预算、治理 | 实验方法的**积木契约**（输入/输出/验证） |
| 通用 run 记录（面向 Agent 任务） | 科研 **Run 记录**（数据版本、配置哈希、指标、验证结果、证据链） |
| 一次性流程的保存与复用 | 跨会话持续演化的**实验工作树**（分支、回退、决策留痕） |
| 生成式脚本沙箱 | 确定性缓存、分组泄漏检查等**科学验证器** |

衔接方式（可选集成，非依赖）：大规模超参试错时，由 dsh_workflow capsule 并行调用
多个 `rf run`，实验记录仍全部落在 ResearchFlow Registry。

### 3.2 科研 pipeline / 实验追踪工具

| 工具 | 定位 | 与 ResearchFlow 的关系 |
| --- | --- | --- |
| Snakemake / Nextflow | 批处理 pipeline 调度（文件驱动 DAG） | ResearchFlow 的工作树面向"Agent 可编辑的科研决策"，非千任务批调度；V1.0+ 可把定稿实验树导出为 Snakemake |
| DVC | 数据 / 模型版本管理 | ResearchFlow 用文件哈希 + Run 记录覆盖轻量场景；大数据版本可外挂 DVC |
| MLflow | 实验追踪、模型登记 | 指标/产物记录思路一致，但 MLflow 无"积木契约 + 决策节点 + 验证门禁"；可留 `rf export --to mlflow` 桥接口 |
| 通用 Agent 编排（KodaX 等） | 任务分解与并行 | 见 3.1，互补 |

**差异化落点重申**：Scientific Blocks（可验证的科研方法积木）、
Experiment Tree（带决策留痕的实验树）、Research Provenance（投稿级证据链）。

## 4. 平台适配结论

| 维度 | DSH 适配器 | Codex 适配器 |
| --- | --- | --- |
| 安装单元 | Cordis bundle（`dsh.bundle.patch`） | `.codex-plugin/plugin.json`（skills + MCP） |
| 首要形态 | Host 插件：Agent Tools + 斜杠命令 | Skill（渐进披露教 Agent 用 CLI） |
| 升级形态 | Client Slots 实验树面板（V1.0） | MCP server（V0.4，Python stdio） |
| 人工审批 | `ctx.approval` / `ctx.userQuestions` | Codex 工具审批 + 会话内确认 |
| 长任务 | `ctx.jobs` 后台任务 | CLI 后台运行 + 轮询 `rf status` |
| 核心逻辑 | **零**（全部经 Core CLI） | **零**（全部经 Core CLI / MCP） |

两平台共享同一份 Core、同一份 AGENTS.md 模板、同一份积木包生态。
