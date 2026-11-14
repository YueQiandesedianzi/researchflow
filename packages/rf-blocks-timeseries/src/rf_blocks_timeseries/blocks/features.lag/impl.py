import pandas as pd

_ALLOWED_AGGS = {"mean", "std", "min", "max"}


def lag(inputs, params, out_dir, log):
    df = pd.read_csv(inputs["dataset"].path)
    time_col, target = params["time_column"], params["target"]
    for col in (time_col, target):
        if col not in df.columns:
            raise ValueError(f"列 {col!r} 不存在（可用: {list(df.columns)}）")
    df = df.assign(**{time_col: pd.to_datetime(df[time_col])})
    df = df.sort_values(time_col, kind="stable").reset_index(drop=True)

    new_cols = []
    for k in params.get("lags") or []:
        k = int(k)
        if k < 1:
            raise ValueError(f"滞后阶数必须 ≥ 1: {k}")
        col = f"{target}_lag{k}"
        df[col] = df[target].shift(k)
        new_cols.append(col)
    for spec in params.get("rolling") or []:
        window, agg = int(spec.get("window", 3)), spec.get("agg", "mean")
        if agg not in _ALLOWED_AGGS:
            raise ValueError(f"不支持的滚动统计: {agg!r}（可选: {sorted(_ALLOWED_AGGS)}）")
        col = f"{target}_roll{agg}{window}"
        # shift(1) 后滚动：当前行的统计不含当前值，防前视泄漏
        df[col] = getattr(df[target].shift(1).rolling(window), agg)()
        new_cols.append(col)

    n0 = len(df)
    if params.get("drop_na", True):
        df = df.dropna(subset=new_cols).reset_index(drop=True)
    df[time_col] = df[time_col].dt.strftime("%Y-%m-%dT%H:%M:%S")
    log(f"滞后特征: 新增 {new_cols}；{n0} → {len(df)} 行")
    df.to_csv(out_dir / "table.csv", index=False)
    return {"table": "table.csv"}
