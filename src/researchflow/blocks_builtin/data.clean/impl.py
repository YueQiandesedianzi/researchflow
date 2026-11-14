import json

import pandas as pd


def clean(inputs, params, out_dir, log):
    df = pd.read_csv(inputs["dataset"].path)
    n0 = len(df)
    if params.get("drop_duplicates"):
        df = df.drop_duplicates()
        log(f"去重: {n0} → {len(df)} 行")
    strategy = params.get("na_strategy", "none")
    subset = params.get("subset") or list(df.columns)
    missing = [c for c in subset if c not in df.columns]
    if missing:
        raise ValueError(f"subset 列不存在: {missing}")

    train_idx = None
    if "train_indices" in inputs:
        train_idx = json.loads(inputs["train_indices"].path.read_text(encoding="utf-8"))

    if strategy == "drop_rows":
        before = len(df)
        df = df.dropna(subset=subset)
        log(f"drop_rows: {before} → {len(df)} 行")
    elif strategy == "fill_mean":
        numeric = df[subset].select_dtypes("number").columns
        if train_idx is not None:
            means = df.iloc[train_idx][numeric].mean()
            log(f"fill_mean: 均值仅来自训练集（{len(train_idx)} 行），列 {list(numeric)}")
        else:
            means = df[numeric].mean()
            log("fill_mean: ⚠ 未提供 train_indices，均值来自含测试集的全量数据"
                "（统计泄漏风险，请接入 train_indices）")
        df[numeric] = df[numeric].fillna(means)
    elif strategy == "fill_zero":
        df[subset] = df[subset].fillna(0)
        log("fill_zero: 填充 0")
    out = out_dir / "table.csv"
    df.to_csv(out, index=False)
    return {"table": "table.csv"}
