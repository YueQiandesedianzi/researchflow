"""生成 Demo B 合成传感器时序（确定性，seed=42）。

2000 个小时级采样点：趋势 + 日周期 + 周周期 + 噪声。
"""

from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.RandomState(42)
n = 2000
h = np.arange(n)
y = (0.002 * h
     + 5 * np.sin(2 * np.pi * h / 24)
     + 3 * np.sin(2 * np.pi * h / 168)
     + rng.normal(0, 0.5, n))
time = pd.date_range("2025-01-01", periods=n, freq="h")
df = pd.DataFrame({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "y": np.round(y, 4)})

out = Path(__file__).parent.parent / "data" / "series.csv"
out.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(out, index=False)
print(f"生成 {out}：{len(df)} 行")
