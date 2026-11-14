# 积木目录速查（Block Catalog v0.1）

积木 = 有明确契约的方法模块：`inputs`（数据端口）+ `params`（配置）→
`outputs`（产物端口）+ `validation`（成功判据）。
端口类型：`table / series / indices / model / metrics / figure / json / file`。
接线规则：上游输出端口类型必须与下游输入端口类型**精确相等**。

## 内置通用积木（12）

| id | category | 说明 | 关键 params | 输入 → 输出 |
| --- | --- | --- | --- | --- |
| `io.load_csv` | io | 载入 CSV 并登记源指纹 | `path`(必)、`target`、`time_column` | — → table |
| `data.inspect` | transform | 体检报告（行/列/缺失/类型） | — | table → metrics |
| `data.clean` | transform | 去重 + 缺失处理 | `drop_duplicates`、`na_strategy`(drop_rows/fill_mean/fill_zero) | table → table |
| `split.random_holdout` | data_split | 随机留出 | `test_size`、`seed` | table → train_indices, test_indices |
| `split.group_holdout` | data_split | 分组留出（防同组泄漏） | `group_column`(必)、`test_size`、`seed` | table → train/test_indices |
| `split.kfold` | data_split | K 折 / 分组 K 折 | `n_splits`、`group_column` | table → folds |
| `features.select` | feature | 选列/丢列 | `include`/`exclude`/`keep` | table → table |
| `model.train_sklearn` | model | 通用 sklearn 回归训练（配置驱动） | `config`(必，见下) | table, train_indices → model, train_info |
| `model.predict` | model | 预测指定索引行 | `index_columns`（携带索引列） | model, table, indices → predictions |
| `eval.regression_metrics` | evaluate | RMSE/MAE/R²/MAPE | `metrics` | predictions → metrics |
| `plot.parity` | visualize | parity 图 | `title` | predictions → figure |
| `plot.residuals` | visualize | 残差图 | `title` | predictions → figure |

## 时序积木包（4，`rf-blocks-timeseries`）

| id | category | 说明 | 关键 params | 输入 → 输出 |
| --- | --- | --- | --- | --- |
| `split.timeseries_holdout` | data_split | 时序留出（不打乱） | `time_column`(必)、`test_size`、`gap` | table → train/test_indices |
| `split.rolling_origin` | data_split | 滚动原点 CV | `time_column`、`n_splits`、`gap` | table → folds |
| `features.lag` | feature | 滞后/滚动特征（shift(1) 防前视） | `time_column`、`target`(必)、`lags`、`rolling` | table → table |
| `plot.series_forecast` | visualize | 真实 vs 预测序列图 | `time_column`(必) | predictions → figure |

## 模型配置（model.train_sklearn 的 config YAML）

```yaml
estimator: sklearn.ensemble.RandomForestRegressor   # 全限定类名
params: {n_estimators: 200, random_state: 42}       # 固定 random_state 保确定性
features: all_numeric        # 或显式列名 [x1, x2]
target: sigma                # 目标列
standardize: false
```

**换模型 = 换 config 文件**，不要新建训练脚本。

## 新增项目级积木

**优先用脚手架**（契约立即可过、实现可运行、可真实冒烟）：

```sh
rf blocks new my.transform --smoke   # 生成 blocks/my.transform/ 并在临时计划里真跑一次
```

然后编辑 `impl.py` 的 TODO 处即可。手写时目录为 `blocks/<category>.<name>/`，两个文件：

```yaml
# block.yaml —— 契约（全部字段必填，除标注可选）
id: my.transform
version: 0.1.0
schema_version: 1
category: transform
title: 我的变换
description: 一句话说明（Agent 检索依据）
kind: python
entry: impl:run
inputs:
  dataset: {type: table}
outputs:
  table: {type: table}
params: {type: object, properties: {factor: {type: number, default: 1.0}}}
validation: [file_exists]        # 内置验证器：file_exists/non_empty_splits/
                                 # no_group_overlap/no_time_leakage/no_nan/
                                 # schema_matches/metrics_keys_present/metric_threshold
execution:
  deterministic: true            # true 才进缓存
  requires_approval: false
```

```python
# impl.py
def run(inputs, params, out_dir, log):
    import pandas as pd
    df = pd.read_csv(inputs["dataset"].path)   # Ref.path 为绝对路径
    df["y"] = df["y"] * params["factor"]
    df.to_csv(out_dir / "table.csv", index=False)
    return {"table": "table.csv"}               # {输出端口: 文件名}
```

然后 `rf blocks check blocks/my.transform` 校验，再接入 plan.yaml。
可选 `validate.py` 自定义验证钩子：`validate(inputs, outputs, params, log)`
返回 `[{"name":..., "passed":..., "detail":...}]`。
