import pandas as pd


def select(inputs, params, out_dir, log):
    df = pd.read_csv(inputs["dataset"].path)
    include = params.get("include")
    exclude = params.get("exclude") or []
    keep = params.get("keep") or []
    if include and exclude:
        raise ValueError("include 与 exclude 互斥，请只用一个")
    if include:
        missing = [c for c in include if c not in df.columns]
        if missing:
            raise ValueError(f"include 列不存在: {missing}")
        cols = list(dict.fromkeys(list(include) + list(keep)))
    else:
        cols = [c for c in df.columns if c not in exclude]
    missing_keep = [c for c in keep if c not in df.columns]
    if missing_keep:
        raise ValueError(f"keep 列不存在: {missing_keep}")
    out_df = df[cols]
    log(f"特征选择: {df.shape[1]} 列 → {out_df.shape[1]} 列")
    out_df.to_csv(out_dir / "table.csv", index=False)
    return {"table": "table.csv"}
