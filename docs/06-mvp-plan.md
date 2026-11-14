# 06 — MVP 开发计划、测试、异常恢复与版本兼容

版本：v0.1-draft｜日期：2026-11-13

## 1. 里程碑路线

| 版本 | 交付 | 关键验收 |
| --- | --- | --- |
| **V0.1** | 平台无关 Python Core + CLI + 16 个 MVP 积木 + 两个 demo 项目 | 满足 [PRD](01-prd.md) 第 8 节全部 8 条 |
| V0.2 | Codex Skill 原型（`.agents/skills/researchflow/`） | 在 Codex 会话中凭 SKILL.md 完成 demo A 全流程 |
| V0.3 | DSH Cordis 插件（Tools + `/researchflow` 命令） | 在 DSH 会话中完成 demo B 全流程；审批/决策走平台机制 |
| V0.4 | Codex Plugin + MCP server；marketplace 分发 | `plugin.json` 安装即用；MCP 工具面与 DSH 适配器等价 |
| V1.0 | 可视化实验工作台（DSH Slots 面板 / 导出 HTML 报告） | 选节点、追踪结果、论文组图组装 |

V0.1 是唯一重投入期；V0.2–V0.4 均为薄适配（估计各 2–4 天）。

## 2. V0.1 工作分解（WBS）

| # | 任务 | 产出 | 估计 |
| --- | --- | --- | --- |
| 1 | 仓库骨架 + 打包 + CLI 框架（`--json`、退出码） | `pyproject.toml`、`rf --help` | 1d |
| 2 | Block Schema 校验器 + 三级发现 + 契约检查 | `blocks/schema.py`、`loader.py`、`contract.py` | 2d |
| 3 | Plan 模型 + 校验 + 拓扑 + Mermaid 渲染 | `plan/`、`rf plan validate/show` | 2d |
| 4 | Registry：SQLite schema + artifacts 哈希落盘 | `registry/`、单写者锁 | 2d |
| 5 | Runner：依赖调度、子进程执行、超时、缓存 | `runner/` | 2d |
| 6 | Validation Engine：10 个内置验证器 + custom 钩子 | `validation/` | 1.5d |
| 7 | 决策节点：auto/manual/auto_then_manual + `rf decide` | `plan/decisions.py` | 1d |
| 8 | Compare：指标表 + 基线相对差 | `compare/` | 1d |
| 9 | Export：复现包 + PROVENANCE + `--verify` | `export/` | 2d |
| 10 | Project Init + AGENTS.md 模板 + `rf doctor` | `project.py` | 1d |
| 11 | 积木实现：共享 12 个（含 io/eval/plot） | `blocks-core` + tabular 包 | 3d |
| 12 | 积木实现：时序特有 4 个 | timeseries 包 | 1d |
| 13 | Demo A（表格回归）+ Demo B（时序回归）端到端 | `examples/`、CI 脚本 | 2d |
| 14 | 测试体系（见第 3 节）+ 文档收尾 | `tests/` | 并行进行 |

合计约 20 人日量级。任务 2–5 是关键路径；11–14 可与 6–9 并行。

### Demo 验收项目（用于证明"不依赖特定数据集"）

- **Demo A — 表格回归**：合成材料性能数据（成分分组列 + 数值特征 + 连续目标），
  树：`load → clean → group_holdout → {ridge, rf, gbr} → eval → parity → 决策 → export`。
- **Demo B — 时间序列回归**：合成传感器序列（趋势+季节+噪声），
  树：`load → lag features → timeseries_holdout / rolling_origin → {ridge, rf} → eval → series_forecast → 决策 → export`。
- 两 demo 共享 12 个积木（75%），决策节点分别用 `auto` 与 `auto_then_manual` 各演示一次。

## 3. 测试策略

| 层 | 内容 | 工具/方式 |
| --- | --- | --- |
| 单元 | block.yaml 合法/非法样本；plan 校验（环、坏引用、契约失配）；哈希稳定性；SQLite CRUD；表达式求值白名单 | pytest |
| 契约 | 每个 MVP 积木：fixture 输入 → golden 输出；**确定性测试**（同输入跑两次 sha256 相同） | pytest + 小数据集 |
| 集成 | 两个 demo 全树端到端：init → run --all → compare → export --verify | pytest 子进程调 CLI |
| 故障注入 | 见第 4 节异常矩阵逐项触发 | pytest |
| 兼容 | sqlite migration 升降级；积木版本范围失配的报错路径；`schema_version` 拒绝路径 | pytest |

质量门：Core 语句覆盖率 ≥ 80%；CI 跑 Win/Linux 双平台（路径与锁行为差异）。

## 4. 异常与恢复矩阵

| 异常 | 检测点 | 行为 | 恢复路径 |
| --- | --- | --- | --- |
| 输入契约不符 | Runner 前置检查 | 拒绝执行，退出码 2，指明端口/期望/实际 | 修 plan 或换积木版本 |
| 必需参数缺失/越界 | params JSON Schema | 同上 | 补参数 |
| 积木执行崩溃/超时 | 子进程退出码/看门狗 | Run 标 `failed`，stderr 落 logs | 修复后 `rf run`（已 validated 上游自动复用） |
| 验证失败 | Validation Gate | `failed_validation`，下游阻断，报告落盘 | 修数据/方法后重跑；历史保留 |
| 进程被杀（断电/Ctrl-C） | 启动时发现 `running` 状态的过期 Run | `rf run --resume`：过期 Run 标 `interrupted`，从断点续跑 | 一条命令 |
| 缓存目录损坏 | 命中校验 sha256 不符 | 视为未命中并重算，报警告 | 自动 |
| Registry 与文件不一致 | `rf doctor` | 列出孤儿产物/缺失文件/状态矛盾 | 按报告人工处置；只增不改保证可审计 |
| 并发跑同一节点 | 节点级锁 + 单写者锁 | 后到者等待或明确报错（`--wait` 可选） | 自动串行化 |
| 决策节点挂起 | `rf status` 显示 awaiting | 不阻塞无关分支 | `rf decide` 确认 |

原子性：产物先写 `*.tmp` 再 rename；Run 目录完整后才写 `run.json` 终稿。

## 5. 版本兼容要求

| 对象 | 版本机制 | 兼容策略 |
| --- | --- | --- |
| plan.yaml | `schema_version: 1`（整数） | Core 拒绝更高版本；升级时提供 `rf plan migrate` |
| block.yaml | `schema_version` + 积木 semver | plan 用 `@^x.y` 范围引用；解析结果冻结进 Run 记录 |
| registry.sqlite | `schema_migrations` 表 | 启动时自动迁移；迁移可逆性经测试 |
| Core ↔ 适配器 | 命令面 + `--json` 契约 + 退出码 | 适配器声明所需 Core 最低版本；新增字段只允许增量（旧适配器忽略未知键） |
| Core ↔ 积木包 | entry points group `researchflow.blocks` + `schema_version` | 积木声明 `requires_core = ">=0.1,<0.2"` |
| Run 记录 | `run.json` 内嵌 `core_version` | 导出包可在更新版本 Core 上 `--verify`（容差内） |

兼容矩阵（发布时维护）：适配器版本 × Core 最低版本 × DSH/Codex 基线快照
（DSH 侧参照 dsh_workflow 的 `compatibility.json` 做法，记录验证过的 DSH commit 与时间）。

## 6. 风险与缓解（执行层）

| 风险 | 缓解 |
| --- | --- |
| 子进程执行在 Windows 的锁/路径差异 | 任务 4/5 首日即在 Windows 跑通最小闭环；CI 双平台 |
| sklearn 版本漂移破坏确定性 | `env.packages_digest` 落 Run；导出包含锁定文件；`--verify` 容差告警 |
| Mermaid 图过大致使不可用 | `rf plan show --node <id> --depth n` 局部渲染 |
| Agent 不会用 CLI | AGENTS.md + SKILL.md 双保险，命令面保持 ≤10 个动词 |
