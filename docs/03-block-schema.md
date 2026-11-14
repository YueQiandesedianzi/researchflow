# 03 — 实验积木标准 Schema（Block Contract v1）

版本：v0.1-draft｜日期：2026-11-13｜`schema_version: 1`

## 1. 设计意图

积木是 ResearchFlow 的最小复用单元：一个**有明确契约的独立方法模块**。
AI 组装实验时先检索积木目录，能复用就不生成新代码；契约让"能不能接、
接完算不算成功"在执行前可判定。

设计要点：

- **inputs / outputs 是数据端口**（产物在节点间流动），**params 是配置值**
  （JSON Schema 描述）。分组列名、测试比例是 params，不是 inputs。
- 契约三问：接受什么 → 产生什么 → 什么情况算成功（validation）。
- 执行语义显式化：是否确定性、是否需要人工审批、超时上限。

## 2. 积木目录与清单

```text
split.group_holdout/
├── block.yaml        # 契约清单（本文件规范）
├── impl.py           # 实现：entry 指定的 callable
└── validate.py       # 可选：自定义验证钩子
```

### 2.1 `block.yaml` 字段规范

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string，点分命名（`category.name`） | ✓ | 全局唯一；同名时项目级覆盖包级 |
| `version` | semver | ✓ | 积木自身版本；plan 中用范围引用（`@^0.1`） |
| `schema_version` | int | ✓ | 契约规范版本，当前 `1` |
| `category` | enum | ✓ | `io / transform / data_split / feature / model / evaluate / visualize / decide / export` |
| `title` / `description` | string | ✓ / ✓ | 给人和 Agent 读的一行说明；description 兼作检索依据 |
| `kind` | enum | ✓ | `python`（V0.1 唯一支持）；`command` 预留 |
| `entry` | string | kind=python 时 ✓ | `module:callable`，相对积木目录解析 |
| `inputs` | map<端口名, PortSpec> | ✓（可空 map） | 数据输入端口 |
| `outputs` | map<端口名, PortSpec> | ✓ | 数据输出端口 |
| `params` | JSON Schema object | — | 参数 schema；Runner 校验后传入 |
| `validation` | list<string \| map> | — | 验证器：内置名或 `{custom: ...}`，见第 4 节 |
| `execution.deterministic` | bool | ✓ | true 才允许进内容寻址缓存 |
| `execution.requires_approval` | bool | ✓ | true 时运行前需人工/平台审批 |
| `execution.timeout_seconds` | int | — | 默认 3600 |
| `execution.env` | list<string> | — | 额外 Python 依赖声明（导出时并入锁定文件） |

### 2.2 PortSpec

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `type` | 端口类型（见 2.3） | 契约检查依据 |
| `required` | bool | 默认 true |
| `description` | string | 端口含义 |
| `schema` | map | 可选，对 `table` 声明必需列、对 `metrics` 声明必需键 |

### 2.3 端口类型系统（小而正交）

| 类型 | 物理形态 | 典型用途 |
| --- | --- | --- |
| `table` | CSV 产物 | 数据表（特征+目标） |
| `series` | 含时间列的 CSV | 时间序列数据 |
| `indices` | JSON 数组 | 划分索引 |
| `model` | pickle/onnx 文件 | 训练好的模型 |
| `metrics` | JSON 对象 | 指标集合 |
| `figure` | PNG/SVG | 图 |
| `json` / `file` | 任意 | 兜底（尽量少用，利于契约强度） |

产物在节点间以 **ArtifactRef** 引用：`{type, path, sha256, meta?}`。
契约检查 = 上游输出端口类型 ∈ 下游输入端口类型（MVP 要求精确相等）。

## 3. 完整示例：分组留出划分

```yaml
# blocks-core/split.group_holdout/block.yaml
id: split.group_holdout
version: 0.1.0
schema_version: 1
category: data_split
title: 按组留出划分
description: 按分组列划分训练/测试集，保证同一组的样本不会同时出现在两侧（防分组泄漏）。
kind: python
entry: impl:split_group_holdout

inputs:
  dataset:
    type: table
    description: 输入数据表（含分组列）

outputs:
  train_indices: {type: indices, description: 训练集行索引}
  test_indices:  {type: indices, description: 测试集行索引}

params:
  type: object
  required: [group_column]
  properties:
    group_column: {type: string, description: 分组列名，须存在于表头}
    test_size:    {type: number, default: 0.2, minimum: 0.05, maximum: 0.5}
    seed:         {type: integer, default: 42}

validation:
  - non_empty_splits          # 内置：两侧索引均非空
  - no_group_overlap          # 内置：以 params.group_column 检查无组泄漏

execution:
  deterministic: true
  requires_approval: false
  timeout_seconds: 300
```

```python
# impl.py —— 约定签名：输入为解析后的 ArtifactRef/值，输出写 out_dir 并返回端口映射
def split_group_holdout(inputs, params, out_dir, log):
    import json, pandas as pd
    from sklearn.model_selection import GroupShuffleSplit
    df = pd.read_csv(inputs["dataset"].path)
    gss = GroupShuffleSplit(n_splits=1, test_size=params["test_size"],
                            random_state=params["seed"])
    train, test = next(gss.split(df, groups=df[params["group_column"]]))
    (out_dir / "train_indices.json").write_text(json.dumps(train.tolist()))
    (out_dir / "test_indices.json").write_text(json.dumps(test.tolist()))
    return {"train_indices": "train_indices.json", "test_indices": "test_indices.json"}
```

要点：实现**只读输入产物、只写 out_dir**；Runner 负责把返回值登记为带 sha256 的
ArtifactRef。积木不感知计划、Registry 与 Agent。

## 4. 验证器（Validation）

### 4.1 内置验证器（Validation Engine 提供）

| 名称 | 语义 |
| --- | --- |
| `file_exists` | 声明的输出产物均存在且非空 |
| `non_empty_splits` | indices 类输出无空集 |
| `no_group_overlap` | 按 `params.group_column` 验证 train/test 组集合不相交 |
| `no_time_leakage` | 时序划分中 train 最大时间戳 < test 最小时间戳（可配 `gap`） |
| `row_count_preserved` | 输出行数与输入一致（清洗类声明豁免） |
| `no_nan` | 指定列/全表无 NaN |
| `schema_matches` | 输出表含端口 `schema` 声明的必需列 |
| `metrics_keys_present` | metrics 输出含声明键 |
| `metric_threshold` | `{metric: rmse, op: "<=", value: x}` 或相对基线表达式 |
| `deterministic_replay` | （可选、昂贵）原地重跑一次比对输出哈希 |

### 4.2 自定义钩子

`validate.py` 导出 `validate(inputs, outputs, params, log) -> list[Finding]`；
Finding = `{name, passed, detail}`。与内置结果合并进 `validation.json`，
任一失败即 `failed_validation`。

## 5. 版本与发现规则

- plan 引用：`block: split.group_holdout@^0.1.0`；解析到已发现的最高兼容版本，
  解析结果（精确版本 + 源码哈希）冻结进 Run 记录。
- 发现顺序：项目 `blocks/` → 已安装积木包（entry points group `researchflow.blocks`）
  → Core 内置。同名前者覆盖后者并打印提醒。
- `schema_version` 大于 Core 支持版本 → 拒绝加载并提示升级。

## 6. MVP 积木清单（v0.1）

共享积木（两包复用，验证通用性）：

| id | category | 说明 | 关键验证器 |
| --- | --- | --- | --- |
| `io.load_csv` | io | 载入 CSV 并登记数据版本哈希 | `file_exists`, `schema_matches` |
| `data.inspect` | transform | 行/列/缺失/类型体检报告 | `metrics_keys_present` |
| `data.clean` | transform | 去重、缺失处理（配置化策略） | `no_nan`（按列） |
| `split.random_holdout` | data_split | 随机留出 | `non_empty_splits` |
| `split.group_holdout` | data_split | 分组留出 | `no_group_overlap` |
| `split.kfold` | data_split | K 折（输出折索引集合） | `non_empty_splits` |
| `features.select` | feature | 配置化选列/丢列 | `schema_matches` |
| `model.train_sklearn` | model | 通用 sklearn 回归训练（estimator+超参全配置化） | `file_exists` |
| `model.predict` | model | 用 model + indices 产预测表 | `row_count_preserved` |
| `eval.regression_metrics` | evaluate | RMSE/MAE/R²/MAPE | `metrics_keys_present`, `metric_threshold` |
| `plot.parity` | visualize | parity 图 | `file_exists` |
| `plot.residuals` | visualize | 残差图 | `file_exists` |

时间序列包特有：

| id | category | 说明 | 关键验证器 |
| --- | --- | --- | --- |
| `split.timeseries_holdout` | data_split | 按时间留出（支持 gap/embargo） | `no_time_leakage` |
| `split.rolling_origin` | data_split | 滚动原点评估划分 | `no_time_leakage` |
| `features.lag` | feature | 滞后/滚动窗口特征 | `no_time_leakage`（特征构造侧） |
| `plot.series_forecast` | visualize | 真实 vs 预测序列图 | `file_exists` |

合计 16 个积木；其中 12 个跨两个 demo 项目共享（75% > 60% 的 PRD 要求）。
模型侧只有**一个**训练积木：`model.train_sklearn` 吃配置（`configs/*.yaml`），
体现"配置驱动，不复制代码"（D8）。

## 7. 明确不支持（v1 契约）

- `kind: command`（外部可执行）：安全边界复杂，V0.2+ 再议；
- 端口类型的子类型/泛型（如 `table<series>`）：保持精确相等，够用即可；
- 积木间直接函数调用：一切经产物端口，保证可追溯。
