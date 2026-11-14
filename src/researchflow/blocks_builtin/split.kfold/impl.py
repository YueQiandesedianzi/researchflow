import json

import pandas as pd
from sklearn.model_selection import GroupKFold, KFold


def kfold(inputs, params, out_dir, log):
    df = pd.read_csv(inputs["dataset"].path)
    n_splits = params["n_splits"]
    group_col = params.get("group_column")
    if group_col:
        if group_col not in df.columns:
            raise ValueError(f"分组列 {group_col!r} 不存在")
        splitter = GroupKFold(n_splits=n_splits)
        splits = splitter.split(df, groups=df[group_col])
        kind = f"GroupKFold({group_col})"
    else:
        splitter = KFold(n_splits=n_splits, shuffle=params.get("shuffle", True),
                         random_state=params["seed"])
        splits = splitter.split(df)
        kind = "KFold"
    folds = [{"train": sorted(tr.tolist()), "test": sorted(te.tolist())}
             for tr, te in splits]
    log(f"{kind}: {len(df)} 行 → {len(folds)} 折")
    (out_dir / "folds.json").write_text(json.dumps(folds), encoding="utf-8")
    return {"folds": "folds.json"}
