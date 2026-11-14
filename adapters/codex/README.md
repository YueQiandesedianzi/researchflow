# Codex 适配器（V0.2 — Skill 原型）

把 `skill/researchflow/` 整个目录复制到以下任一位置即可使用：

| 位置 | 作用域 |
| --- | --- |
| `<你的科研项目>/.agents/skills/researchflow/` | 仓库级（随项目分发给协作者） |
| `~/.agents/skills/researchflow/` | 个人级（所有项目可用） |

前提：`rf` CLI 已安装（`pip install -e <ResearchFlow 仓库>`，或
`pip install researchflow` 发布后）。

## 使用

- 隐式：直接提需求（"把数据按成分组留出，训三个模型对比一下"），
  Codex 按 SKILL.md 的 description 自动路由；
- 显式：`$researchflow 帮我初始化一个表格回归项目`。

Skill 遵循渐进披露：首层只有三条铁律 + 快速上手 + 命令速查入口；
细节（积木契约、plan 格式）在 `references/` 中按需加载。

## 验证

本 Skill 的指令序列经自动化 walkthrough 测试
（`tests/test_adapters.py::test_codex_skill_walkthrough`）：
仅凭 SKILL.md 描述的命令即可完成 初始化 → 校验 → 运行 → 比较 → 报告 全流程。

## 路线

- **V0.2（当前）**：纯 Skill，零代码成本；
- **V0.4**：打包 `.codex-plugin/plugin.json`（skills + `.mcp.json`），
  MCP server（`python -m researchflow.mcp`）暴露与 DSH 适配器等价的工具面，
  经 marketplace 分发。
