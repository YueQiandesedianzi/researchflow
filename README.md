# ResearchFlow

> 将科研论文中的方法拆解为可复用的实验模块，利用 AI 自动组合、执行和比较实验，
> 并通过人工审核与程序验证，形成可追溯、可复现的科研工作树。

## 这是什么

ResearchFlow 是一个可复用、跨科研任务、兼容 DSH（DeepSeek Harness）与 Codex 的
科研实验工作流**框架 + 插件**。它不是针对某个数据集的建模工具，而是把科研建模过程
转化为**可组合、可执行、可验证、可追溯的实验工作树**的系统。

三层结构：

| 层 | 形态 | 说明 |
| --- | --- | --- |
| ResearchFlow Core | 平台无关的 Python 包 + CLI | 积木注册、工作树、执行、验证、实验记录、比较、导出 |
| 平台适配器 | DSH Cordis 插件 / Codex Skill + Plugin（MCP） | 把 Core 能力暴露给 Agent；不含核心逻辑 |
| 积木包（Block Packs） | Python 插件包（entry points） | 按领域扩展：表格回归、时间序列、图像、模拟、主动学习…… |

## 文档索引

| 文档 | 内容 |
| --- | --- |
| [docs/00-research.md](docs/00-research.md) | DSH / Codex 插件机制与现有编排项目调研结论 |
| [docs/01-prd.md](docs/01-prd.md) | 产品需求文档（PRD） |
| [docs/02-architecture.md](docs/02-architecture.md) | 核心架构、模块职责与依赖图、关键设计决策 |
| [docs/03-block-schema.md](docs/03-block-schema.md) | 实验积木标准 Schema 与 MVP 积木清单 |
| [docs/04-experiment-tree.md](docs/04-experiment-tree.md) | 工作树 / 实验节点数据结构、Run 记录与持久化方案 |
| [docs/05-platform-adapters.md](docs/05-platform-adapters.md) | DSH 适配器与 Codex 适配器设计 |
| [docs/06-mvp-plan.md](docs/06-mvp-plan.md) | MVP 开发计划、测试、异常恢复与版本兼容要求 |

## 当前状态

**V0.1 已实现并通过验收**（2026-11-13）：Core + CLI、16 个积木、两个 demo、
83 项测试全绿。下一步按 [docs/06-mvp-plan.md](docs/06-mvp-plan.md) 进入 V0.2（Codex Skill）。

### 快速开始

```sh
pip install -e .                            # Core（提供 rf / python -m researchflow）
pip install -e packages/rf-blocks-timeseries  # 时序积木包（entry points 注册）

cd examples/demo-a-tabular
python scripts/make_data.py                 # 生成确定性演示数据
rf run --all --yes                          # 运行整棵实验树
rf status                                   # 节点状态
rf compare eval-ridge-01 eval-rf-01 eval-gbr-01 --baseline eval-ridge-01
rf export --nodes eval-rf-01,plot-rf-parity --out dist/paper-rf --verify
python -m pytest -q                         # 仓库根目录：83 项测试
```

### 仓库结构

```text
ResearchFlow/
├── docs/                        # 设计文档包（00 调研 → 06 MVP 计划）
├── src/researchflow/            # Core：CLI / 积木注册 / 工作树 / Runner /
│   ├── blocks_builtin/          #   验证 / Registry / Compare / Export
│   │                            #   + 12 个内置通用积木
│   └── templates/               # rf init 模板（AGENTS.md、plan、模型配置）
├── packages/rf-blocks-timeseries/  # 时序积木包（4 个，entry points 扩展示例）
├── examples/demo-a-tabular/     # 表格回归验收项目（三模型 + 双决策节点）
├── examples/demo-b-timeseries/  # 时序回归验收项目（滞后特征 + 防泄漏划分）
└── tests/                       # 83 项测试（单元/契约/集成/端到端）
```

## 设计原则

1. Core 与 Agent 平台解耦——核心模块不 import 任何 DSH / Codex 私有接口。
2. 插件式实验积木——每个积木具有明确的输入/输出契约。
3. 所有实验具有独立 Run ID，状态持久化，不依赖对话历史。
4. 配置驱动——换模型、换划分方式只改配置，不复制代码。
5. 自动验证 + 人工审批双重控制实验流程。
6. 实验结果和代码必须可复现。
7. 不绑定特定材料体系、模型或预测目标。

## 与现有工具的关系

- **不重造通用 Agent 编排器**：[dsh_workflow](https://github.com/omdsh-dev/dsh_workflow)
  等项目已解决"多 Agent 并行调度、暂停/恢复、预算治理"。ResearchFlow 解决的是
  其上游的科研语义问题：实验方法积木化、实验树继承关系、验证门禁与证据链。
- **不替代 Snakemake / DVC / MLflow**：它们是批 pipeline 调度、数据版本与实验追踪工具；
  ResearchFlow 是面向 Agent 的实验语义层（详见 [docs/00-research.md](docs/00-research.md) 第 3 节）。

## 差异化价值（产品主线）

1. **Scientific Blocks**：可复用、可验证的科研方法积木。
2. **Experiment Tree**：可持续探索、比较、回退并保留研究决策的实验树。
3. **Research Provenance**：从论文方法、原始数据、运行代码直到投稿图片的完整证据链。
