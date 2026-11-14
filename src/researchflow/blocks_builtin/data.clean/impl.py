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
    if strategy == "drop_rows":
        before = len(df)
        df = df.dropna(subset=subset)
        log(f"drop_rows: {before} → {len(df)} 行")
    elif strategy == "fill_mean":
        numeric = df[subset].select_dtypes("number").columns
        df[numeric] = df[numeric].fillna(df[numeric].mean())
        log(f"fill_mean: 填充数值列 {list(numeric)}")
    elif strategy == "fill_zero":
        df[subset] = df[subset].fillna(0)
        log("fill_zero: 填充 0")
    out = out_dir / "table.csv"
    df.to_csv(out, index=False)
    return {"table": "table.csv"}
