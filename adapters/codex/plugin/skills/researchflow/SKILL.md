---
name: researchflow
description: 科研实验工作树（ResearchFlow）。当用户要求做实验、训练/对比模型、划分数据集、评价指标、记录或复现实验、导出论文结果与复现包时使用。通过 rf CLI 执行可组合、可验证、可追溯的实验流程。
---

# ResearchFlow

把科研实验组织成**可组合、可验证、可追溯**的工作树。所有实验经 `rf` CLI
（或 `python -m researchflow`）执行；状态持久化在项目 `.researchflow/`，
不依赖对话历史，多会话可接力。

## 三条铁律

1. **实验必过 rf**：禁止手写脚本直接读写 `.researchflow/`。
2. **复用积木**：新增实验 = 编辑 plan.yaml + 复用/新增积木（配置驱动）；
   禁止复制既有脚本改参数。模型差异写在 `configs/*.yaml`。
3. **决策未过不引用**：决策节点（decision）未通过前，其下游结果不得用于论文或报告。

## 快速上手

```sh
rf init --template tabular        # 或 timeseries；在项目根执行一次
# 把数据放入 data/，编辑 plan.yaml 中 io.load_csv 的 path/target
rf plan validate                  # 必须先校验（结构 + 积木契约）
rf run --all --yes                # 运行整棵树（--yes 自动批准审批型积木）
rf status                         # 节点状态一览
rf compare eval-a eval-b --baseline eval-a   # 统一指标对照
rf report                         # 生成单文件 HTML 实验工作台
rf export --nodes a,b --out dist/pkg --verify  # 导出并验证复现包
```

## 何时查阅 references

- 命令细节、退出码、`--json` 输出约定 → [references/commands.md](references/commands.md)
- 可用积木清单与契约（划分/特征/模型/评价/绘图/时序）、如何新增积木
  → [references/block-catalog.md](references/block-catalog.md)
- plan.yaml 写法：执行节点、决策节点、门禁边 → [references/plan-format.md](references/plan-format.md)

## 工作方式

1. 先 `rf blocks list` 检索积木，**优先复用**；确需新增再按契约编写项目级积木。
2. 每次修改 plan.yaml 后必须 `rf plan validate` 再运行。
3. 运行失败：看 `rf runs show <RUN-id>` 与 `.researchflow/runs/<RUN-id>/logs/`。
4. 对比结论必须基于 `rf compare` 的输出，不要凭记忆陈述指标。
5. 退出码含义：0 成功｜2 契约/校验失败（先修 plan）｜3 运行失败（看日志）｜
   4 等待人工审批/决策（用 `rf decide <node> --pass/--fail` 处理后再继续）。
