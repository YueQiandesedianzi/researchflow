import json
import pickle

import pandas as pd


def predict(inputs, params, out_dir, log):
    with open(inputs["model"].path, "rb") as f:
        bundle = pickle.load(f)
    model, features, target = bundle["model"], bundle["features"], bundle["target"]
    df = pd.read_csv(inputs["dataset"].path)
    indices = json.loads(inputs["indices"].path.read_text(encoding="utf-8"))
    subset = df.iloc[indices]
    missing = [c for c in features if c not in subset.columns]
    if missing:
        raise ValueError(f"数据表缺少模型所需特征列: {missing}")

    y_pred = model.predict(subset[features])
    result = pd.DataFrame()
    for col in params.get("index_columns") or []:
        if col not in subset.columns:
            raise ValueError(f"index_columns 列不存在: {col!r}")
        result[col] = subset[col].to_numpy()
    if target in subset.columns:
        result["y_true"] = subset[target].to_numpy()
    else:
        result["y_true"] = float("nan")
    result["y_pred"] = y_pred
    log(f"预测 {len(result)} 行（estimator={bundle.get('estimator')}）")
    result.to_csv(out_dir / "predictions.csv", index=False)
    return {"predictions": "predictions.csv"}
