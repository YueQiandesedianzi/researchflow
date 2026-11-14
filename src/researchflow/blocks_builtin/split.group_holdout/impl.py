import json

import pandas as pd
from sklearn.model_selection import GroupShuffleSplit


def group_holdout(inputs, params, out_dir, log):
    df = pd.read_csv(inputs["dataset"].path)
    group_col = params["group_column"]
    if group_col not in df.columns:
        raise ValueError(f"分组列 {group_col!r} 不存在（可用列: {list(df.columns)}）")
    gss = GroupShuffleSplit(n_splits=1, test_size=params["test_size"],
                            random_state=params["seed"])
    train, test = next(gss.split(df, groups=df[group_col]))
    train, test = sorted(train.tolist()), sorted(test.tolist())
    n_groups = df[group_col].nunique()
    log(f"分组留出: {n_groups} 组 → train {len(train)} 行 / test {len(test)} 行")
    (out_dir / "train_indices.json").write_text(json.dumps(train), encoding="utf-8")
    (out_dir / "test_indices.json").write_text(json.dumps(test), encoding="utf-8")
    return {"train_indices": "train_indices.json", "test_indices": "test_indices.json"}
