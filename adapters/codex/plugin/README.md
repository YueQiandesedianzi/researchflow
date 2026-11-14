# ResearchFlow Codex Plugin（V0.4）

一个安装单元打包两种能力：

| 组件 | 内容 |
| --- | --- |
| **Skill**（`skills/researchflow/`） | 渐进披露教 Agent 使用 `rf` CLI（与 V0.2 同源，测试保证同步） |
| **MCP server**（`.mcp.json`） | `python -m researchflow.mcp`（stdio），暴露 9 个 `researchflow_*` 工具 |

## 前提

```sh
pip install "researchflow[mcp] @ git+https://github.com/YueQiandesedianzi/researchflow.git"
# 或本地开发：pip install -e <本仓库>[mcp]
```

## 安装

- **仓库级 marketplace**（团队共享）：仓库根已带 `.agents/plugins/marketplace.json`，
  clone 本仓库的团队可按提示安装；
- **个人**：在 Codex 的 Plugins 目录中添加本仓库路径 `adapters/codex/plugin`，
  或把本目录复制到个人 marketplace 指向的位置。

## 验证

- MCP 协议级集成测试：`tests/test_mcp.py`（initialize → tools/list → tools/call 全握手）；
- Skill 同步测试：`tests/test_adapters.py::test_plugin_skill_in_sync`。

## 备注

- `marketplace.json` 的 source/policy 字段按 2026 年公开的 Codex 插件规范撰写；
  官方文档部分页面存在访问限制，若字段有更新请以最新官方规范为准（欢迎 issue）。
- DSH 侧亦可把 `python -m researchflow.mcp` 挂为 MCP 连接（备选路径）。
