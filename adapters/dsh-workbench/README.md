# ResearchFlow Workbench（V1.0 — DSH 可视化实验工作台）

独立 bundle（与 `@researchflow/dsh-adapter` 的工具包解耦），两个入口：

| 入口 | 形态 |
| --- | --- |
| **独立页面（完整功能）** | 浏览器直开 `http://127.0.0.1:<port>/researchflow` —— 五标签工作台：实验树（缩放/运行/决策）、指标对照（基线 Δ%）、图表、运行记录（run.json 详情模态）、决策日志，附复现包导出 |
| **应用内启动器** | 页面右下角悬浮球（🌲）→ 轻量抽屉（状态摘要 + 待办决策快捷按钮 + 一键打开完整工作台），避免双份 UI 维护 |

数据源：Host 半注册的同源路由 → `rf` CLI（与工具包同一语义）。

## 页面能力清单

- **实验树**：SVG 缩放（−/＋/复位）、状态图例；点击节点 → 详情抽屉（指标、验证器、产物哈希与产物下载链接）；执行节点可「运行此节点」（带 loading 态）；决策节点 awaiting 时显示备注输入 + 通过/驳回
- **指标对照**：全部 validated 节点指标成表，基线下拉 → 全表 Δ% 列；点击行跳回实验树
- **图表**：base64 产物图卡片，点击看大图（artifact 路由）
- **运行记录**：runs 表格 → 点击行弹出 run.json 分区详情（输入/产物/验证/指标/环境 + 原始 JSON）
- **决策记录**：决策表（结果/模式/判据/建议/决策者/备注/时间），点击行跳回树
- **通用**：项目切换（localStorage）、8s 轮询（页面隐藏暂停）、错误 toast（含退出码 2/3/4 人类可读解释）、空态引导

## 路由（Host 半，webServer 契约）

| 路由 | 说明 |
| --- | --- |
| `GET /researchflow` | 独立工作台页面 |
| `GET /researchflow/api/config` | 插件配置（defaultProject） |
| `GET /researchflow/api/tree?project=…` | `rf report --data --json` 的工作台载荷（节点坐标/状态/指标/决策） |
| `GET /researchflow/api/run_show?project&run_id` | `rf runs show --json`（Run 完整记录） |
| `GET /researchflow/api/artifact?project&run_id&port` | Registry 产物字节流（仅按记录解析，防路径穿越） |
| `POST /researchflow/api/decide` | `{project, node, pass, comment}` → `rf decide` |
| `POST /researchflow/api/run` | `{project, node\|all, no_cache}` → `rf run --yes` |
| `POST /researchflow/api/export` | `{project, nodes, out, verify}` → `rf export --json` |

## 面板能力

- 实验树 SVG（分层布局来自 Core，颜色即状态，橙虚线门禁边）；
- 点击节点 → 详情侧栏（最新 Run、指标、验证器、产物哈希）；
- 决策节点 awaiting 时 → **通过 / 驳回** 按钮（写决策记录，agent 工具同源）；
- 执行节点 → **运行此节点**；顶栏 → 全部运行 / 刷新 / 8s 自动轮询；
- 项目目录可切换（localStorage 记忆，默认取插件配置 `defaultProject`）。

## 安装与注意

```
plugin_manager install_bundle → target: <本仓库>/adapters/dsh-workbench
```

- 安装后**刷新一次 DSH 页面**（Ctrl+R / F5），Client 模块才会加载（非 dev:web 环境无 HMR 推送）；
- 路由监听 127.0.0.1；V1.0 接受同源页面直接调用，未加校验头（公网部署需补鉴权）；
- 面板文本当前为中文硬编码，locale 化留待后续；
- 与 dsh-adapter 工具包独立：卸载互不影响。
