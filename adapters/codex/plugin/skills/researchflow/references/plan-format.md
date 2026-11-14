# plan.yaml —— 实验工作树格式

工作树是 DAG：节点 = **执行节点** 或 **决策节点**；边 = 数据依赖（输入绑定）+
决策门禁（on_pass/on_fail）。计划是可编辑意图；运行状态只存在 Registry，不写回计划。

```yaml
schema_version: 1
project: my-project
meta: {intent: 一句话说明本树的研究意图}
nodes:
  # —— 执行节点 ——
  - id: split-01
    kind: execution
    block: split.group_holdout@^0.1.0     # 积木id@版本范围（^0.1 / >=0.1,<0.2 / 精确）
    title: 按组留出（可选，给人读）
    params: {group_column: composition, test_size: 0.2, seed: 42}
    inputs:                                # 端口绑定：{from: 节点.outputs.端口}
      dataset: {from: clean-01.outputs.table}

  # —— 决策节点 ——
  - id: gate-beat-baseline
    kind: decision
    title: 新模型是否显著优于基线？
    inputs:                                # 端口名即表达式变量名
      candidate: {from: eval-rf-01.outputs.metrics}
      baseline:  {from: eval-ridge-01.outputs.metrics}
    criteria:
      mode: auto                           # auto | manual | auto_then_manual
      expression: "candidate.rmse <= baseline.rmse * 0.95"
    on_pass: [export-01]                   # 通过才允许运行的下游
    on_fail: []
```

## 规则

- `id`：小写字母/数字/连字符；全树唯一。
- 输入绑定：`{from: "<node>.outputs.<port>"}` 或 `{value: <字面量>}`（物化为 json 产物）。
- 决策表达式：只允许数值、比较、四则、`and/or/not`，变量为输入端口名的指标键
  （如 `candidate.rmse`）；禁止函数调用与下标访问。
- 决策模式：
  - `auto`：运行时自动求值并记录；
  - `manual`：挂起（退出码 4），`rf decide <node> --pass/--fail` 确认；
  - `auto_then_manual`：自动判据先给建议，人工确认后生效。
- 门禁边：`on_pass` 的下游在决策通过前被拒绝执行（退出码 4）；
  决策驳回后被有意跳过（不影响退出码）。
- 无环；`rf plan validate` 会检查：积木存在且版本匹配、必需端口已绑定、
  端口类型相等、参数符合 schema、门禁引用存在。

## 常用片段

三模型对照（同一划分下挂多个分支，在 compare 处汇合）：

```yaml
  - id: model-rf-01
    kind: execution
    block: model.train_sklearn@^0.1.0
    params: {config: configs/random_forest.yaml}
    inputs:
      dataset: {from: clean-01.outputs.table}
      train_indices: {from: split-01.outputs.train_indices}
  # model-gbr-01 同理换 config；各自接 model.predict → eval.regression_metrics
```

完整可运行示例见仓库 `examples/demo-a-tabular/plan.yaml`（表格）与
`examples/demo-b-timeseries/plan.yaml`（时序）。
