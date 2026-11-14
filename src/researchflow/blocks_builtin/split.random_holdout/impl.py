import json

import numpy as np
import pandas as pd


def random_holdout(inputs, params, out_dir, log):
    df = pd.read_csv(inputs["dataset"].path)
    n = len(df)
    n_test = max(1, int(round(n * params["test_size"])))
    rng = np.random.RandomState(params["seed"])
    order = rng.permutation(n) if params.get("shuffle", True) else np.arange(n)
    test = sorted(order[:n_test].tolist())
    train = sorted(order[n_test:].tolist())
    log(f"随机留出: {n} 行 → train {len(train)} / test {len(test)}")
    (out_dir / "train_indices.json").write_text(json.dumps(train), encoding="utf-8")
    (out_dir / "test_indices.json").write_text(json.dumps(test), encoding="utf-8")
    return {"train_indices": "train_indices.json", "test_indices": "test_indices.json"}
