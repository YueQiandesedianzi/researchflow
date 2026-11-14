import json

import numpy as np
import pandas as pd


def timeseries_holdout(inputs, params, out_dir, log):
    df = pd.read_csv(inputs["dataset"].path)
    time_col = params["time_column"]
    if time_col not in df.columns:
        raise ValueError(f"时间列 {time_col!r} 不存在（可用列: {list(df.columns)}）")
    times = pd.to_datetime(df[time_col])
    order = np.argsort(times.to_numpy(), kind="stable")
    n = len(df)
    n_test = max(1, int(round(n * params["test_size"])))
    gap = int(params.get("gap", 0) or 0)
    test = sorted(order[n - n_test:].tolist())
    train = sorted(order[: n - n_test - gap].tolist())
    if not train:
        raise ValueError(f"训练集为空: n={n}, n_test={n_test}, gap={gap}")
    log(f"时序留出: {n} 行 → train {len(train)} / gap {gap} / test {len(test)}；"
        f"边界 {times.iloc[train].max()} → {times.iloc[test].min()}")
    (out_dir / "train_indices.json").write_text(json.dumps(train), encoding="utf-8")
    (out_dir / "test_indices.json").write_text(json.dumps(test), encoding="utf-8")
    return {"train_indices": "train_indices.json", "test_indices": "test_indices.json"}
