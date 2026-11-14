# Demo A — 表格回归（合成合金电导率）

演示：标准初始化 → 数据体检门禁 → 分组防泄漏划分 → 三模型统一评价 → 自动决策 → 导出复现包。
全部使用 Core 内置积木（与 Demo B 共享 12 个通用积木）。

```sh
python scripts/make_data.py          # 生成 data/raw/alloys.csv（确定性）
rf plan validate                     # 校验工作树与积木契约
rf run --all --yes                   # 运行全树（两个决策节点均为 auto）
rf status                            # 查看节点状态
rf compare eval-ridge-01 eval-rf-01 eval-gbr-01 --baseline eval-ridge-01
rf plan show                         # Mermaid 流程图（带状态）
rf export --nodes eval-rf-01,plot-rf-parity --out dist/paper-rf --verify
```

决策节点：
- `gate-data`：数据量 ≥500 才允许清洗建模（auto，演示门禁边 on_pass）。
- `gate-rf-beats-ridge`：RF 的 RMSE 是否比 Ridge 低 10%（auto，记录判定依据）。
