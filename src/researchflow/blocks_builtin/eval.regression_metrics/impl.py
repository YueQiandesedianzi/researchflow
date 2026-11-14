import json

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

_AVAILABLE = ("rmse", "mae", "r2", "mape")


def evaluate(inputs, params, out_dir, log):
    df = pd.read_csv(inputs["predictions"].path)
    for col in ("y_true", "y_pred"):
        if col not in df.columns:
            raise ValueError(f"预测表缺少 {col!r} 列（可用: {list(df.columns)}）")
    y_true = df["y_true"].to_numpy(dtype=float)
    y_pred = df["y_pred"].to_numpy(dtype=float)
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true, y_pred = y_true[mask], y_pred[mask]
    if len(y_true) == 0:
        raise ValueError("y_true/y_pred 全部为 NaN，无法评价")

    selected = params.get("metrics") or ["rmse", "mae", "r2"]
    unknown = [m for m in selected if m not in _AVAILABLE]
    if unknown:
        raise ValueError(f"未知指标: {unknown}（可选: {_AVAILABLE}）")
    results = {}
    if "rmse" in selected:
        results["rmse"] = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    if "mae" in selected:
        results["mae"] = float(mean_absolute_error(y_true, y_pred))
    if "r2" in selected:
        results["r2"] = float(r2_score(y_true, y_pred))
    if "mape" in selected:
        nz = y_true != 0
        results["mape"] = float(np.mean(np.abs((y_true[nz] - y_pred[nz]) / y_true[nz]))) if nz.any() else None
    results["n_eval"] = int(len(y_true))
    log("指标: " + ", ".join(f"{k}={v:.6g}" for k, v in results.items()
                             if isinstance(v, float)))
    (out_dir / "metrics.json").write_text(json.dumps(results, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    return {"metrics": "metrics.json"}
