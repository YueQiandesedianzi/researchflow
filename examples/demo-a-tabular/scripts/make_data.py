"""生成 Demo A 合成材料电导率数据集（确定性，seed=42）。

50 个成分组 × 12 样本；目标 sigma 含组效应与非线性项。
注入约 2% NaN 与若干重复行，供 data.clean 演示。
"""

from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.RandomState(42)
rows = []
for g in range(50):
    comp = f"C{g:03d}"
    group_effect = rng.normal(0, 0.8)
    for _ in range(12):
        x1 = rng.uniform(300, 1200)   # 烧结温度
        x2 = rng.uniform(0.1, 5.0)    # 压力
        x3 = rng.uniform(0, 1)        # 掺杂比
        x4 = rng.uniform(0, 100)      # 保温时间
        x5 = rng.uniform(0, 10)       # 原料比
        x6 = rng.uniform(0, 1)        # 添加剂
        sigma = (0.002 * x1 + 1.5 * np.log1p(x2) + 2.0 * x3 - 0.005 * x4
                 + 0.3 * x5 * x6 + group_effect + rng.normal(0, 0.25))
        rows.append([comp, x1, x2, x3, x4, x5, x6, round(sigma, 4)])

df = pd.DataFrame(rows, columns=["composition", "x1", "x2", "x3", "x4", "x5", "x6", "sigma"])
dups = df.sample(10, random_state=1)
df = pd.concat([df, dups], ignore_index=True)
mask = rng.rand(len(df)) < 0.02
df.loc[mask, "x3"] = np.nan
df = df.sample(frac=1, random_state=7).reset_index(drop=True)

out = Path(__file__).parent.parent / "data" / "raw" / "alloys.csv"
out.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(out, index=False)
print(f"生成 {out}：{len(df)} 行（含 {int(mask.sum())} 个 NaN、{len(dups)} 个重复行）")
