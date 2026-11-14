# DSH 适配器（V0.3 — Cordis 插件）

薄适配层：把 `rf` CLI 能力注册为 9 个 Agent Tools + `/researchflow` 斜杠命令。
**不含核心逻辑**——全部计算在 ResearchFlow Core（Python）。

## 安装

在 DSH 会话中（需插件管理权限）：

```
plugin_manager install_bundle → target: <本仓库>/adapters/dsh/researchflow-dsh
```

或命令行：`dsh plugin --profile <profile> add <本仓库>/adapters/dsh/researchflow-dsh`

## 能力

| Agent Tool | 对应 CLI |
| --- | --- |
| `researchflow_init` | `rf init` |
| `researchflow_plan` | `rf plan validate/show` |
| `researchflow_run` | `rf run` |
| `researchflow_status` | `rf status` |
| `researchflow_runs` | `rf runs list/show` |
| `researchflow_compare` | `rf compare` |
| `researchflow_decide` | `rf decide` |
| `researchflow_export` | `rf export` |
| `researchflow_report` | `rf report` |

斜杠命令：`/researchflow <rf 子命令与参数>`（项目目录取插件配置 `defaultProject`）。

## 配置（cordis.patch.yml 的 config 项）

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `pythonPath` | `python` | Python 解释器（须已安装 researchflow 包） |
| `defaultProject` | — | `/researchflow` 命令与工具的默认项目目录 |
| `runTimeoutMinutes` | 30 | run / export 的单次超时 |

## 已知限制（V0.3）

- 未导出 Config schema（零依赖 JS bundle 无法引入 schemastery），
  配置靠 patch 默认值与运行时兜底，无设置表单；
- `/researchflow` 斜杠命令的交互验证需在真实会话输入框进行；
- V1.0 将补充 Client Slots 实验树面板（实时刷新、节点操作）。
