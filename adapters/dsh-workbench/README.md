# ResearchFlow Workbench（V1.0 — DSH 可视化实验工作台）

独立 bundle（与 `@researchflow/dsh-adapter` 的工具包解耦），两个入口：

| 入口 | 形态 |
| --- | --- |
| **应用内面板** | 页面右下角悬浮球（🌲）→ 抽屉式实验工作台（`shell.overlay` slot，React，宿主主题 token） |
| **独立页面** | 浏览器直开 `http://127.0.0.1:<port>/researchflow`（无 React 依赖，纯 JS） |

数据源：Host 半注册的同源路由 → `rf` CLI（与工具包同一语义）。

## 路由（Host 半，webServer 契约）

| 路由 | 说明 |
| --- | --- |
| `GET /researchflow` | 独立工作台页面 |
| `GET /researchflow/api/config` | 插件配置（defaultProject） |
| `GET /researchflow/api/tree?project=…` | `rf report --data --json` 的工作台载荷（节点坐标/状态/指标/决策） |
| `POST /researchflow/api/decide` | `{project, node, pass, comment}` → `rf decide` |
| `POST /researchflow/api/run` | `{project, node\|all, no_cache}` → `rf run --yes` |

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
