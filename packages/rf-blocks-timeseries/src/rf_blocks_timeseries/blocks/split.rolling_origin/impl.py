import json

import numpy as np
import pandas as pd


def rolling_origin(inputs, params, out_dir, log):
    df = pd.read_csv(inputs["dataset"].path)
    time_col = params["time_column"]
    if time_col not in df.columns:
        raise ValueError(f"时间列 {time_col!r} 不存在")
    order = np.argsort(pd.to_datetime(df[time_col]).to_numpy(), kind="stable")
    n = len(df)
    n_splits = params["n_splits"]
    n_test = max(1, int(round(n * params["test_size"])))
    gap = int(params.get("gap", 0) or 0)
    folds = []
    for i in range(n_splits):
        te_start = n - (n_splits - i) * n_test
        test = sorted(order[te_start: te_start + n_test].tolist())
        train = sorted(order[: te_start - gap].tolist())
        if not train or not test:
            raise ValueError(f"fold {i} 为空: n={n}, n_test={n_test}, gap={gap}")
        folds.append({"train": train, "test": test})
    log(f"滚动原点: {n} 行 → {len(folds)} 折，每折 test {n_test} 行")
    (out_dir / "folds.json").write_text(json.dumps(folds), encoding="utf-8")
    return {"folds": "folds.json"}
