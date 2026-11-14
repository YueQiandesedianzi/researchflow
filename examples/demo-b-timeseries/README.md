# Demo B — 时间序列回归（合成传感器时序）

演示：时序特征构造（滞后 + 滚动统计，shift(1) 防前视泄漏）→ 时序留出划分
（no_time_leakage 验证器 + gap）→ 双模型对照 → 滚动原点划分支线 → 自动决策。
与 Demo A 共享同一套 io / model / eval 积木，仅划分、特征与绘图积木来自
`rf-blocks-timeseries` 包（entry points 注册）。

```sh
python scripts/make_data.py          # 生成 data/series.csv（确定性）
rf plan validate
rf run --all --yes
rf status
rf compare eval-ridge-01 eval-rf-01 --baseline eval-ridge-01
rf export --nodes eval-rf-01,plot-rf-forecast --out dist/paper-ts --verify
```
