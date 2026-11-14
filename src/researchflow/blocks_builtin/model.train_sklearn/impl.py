import importlib
import json
import pickle

import pandas as pd
import yaml
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from researchflow.blocks.api import resolve_in_project


def _load_class(dotted: str):
    module_name, _, class_name = dotted.rpartition(".")
    if not module_name:
        raise ValueError(f"estimator 必须是全限定类名（如 sklearn.ensemble.RandomForestRegressor）: {dotted!r}")
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name, None)
    if cls is None:
        raise ValueError(f"estimator 类不存在: {dotted!r}")
    return cls


def train(inputs, params, out_dir, log):
    config_path = resolve_in_project(params["config"], params.get("_project_root", "."))
    if not config_path.is_file():
        raise FileNotFoundError(f"模型配置不存在: {config_path}")
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    target = cfg.get("target")
    if not target:
        raise ValueError(f"模型配置缺少 target: {config_path}")

    df = pd.read_csv(inputs["dataset"].path)
    train_idx = json.loads((inputs["train_indices"].path).read_text(encoding="utf-8"))
    train_df = df.iloc[train_idx]

    features_spec = cfg.get("features", "all_numeric")
    if features_spec == "all_numeric":
        features = [c for c in train_df.select_dtypes("number").columns if c != target]
    else:
        features = list(features_spec)
        missing = [c for c in features if c not in train_df.columns]
        if missing:
            raise ValueError(f"特征列不存在: {missing}")
    if target not in train_df.columns:
        raise ValueError(f"目标列 {target!r} 不存在")
    # R7：科学有效性检查——答案不得进入特征、特征不得重复、目标必须数值
    if target in features:
        raise ValueError(
            f"目标列 {target!r} 不允许出现在特征列表中（会把答案直接用于预测，"
            f"产生虚假的满分指标）")
    duplicated = sorted({c for c in features if features.count(c) > 1})
    if duplicated:
        raise ValueError(f"特征列重复: {duplicated}")
    if not features:
        raise ValueError("特征列表为空（检查 features 配置）")
    if not pd.api.types.is_numeric_dtype(train_df[target]):
        raise ValueError(
            f"目标列 {target!r} 必须是数值类型（回归任务），实际 dtype: "
            f"{train_df[target].dtype}")

    cls = _load_class(cfg["estimator"])
    estimator = cls(**(cfg.get("params") or {}))
    steps = []
    if cfg.get("standardize"):
        steps.append(("scaler", StandardScaler()))
    steps.append(("estimator", estimator))
    pipeline = Pipeline(steps)
    pipeline.fit(train_df[features], train_df[target])
    log(f"训练 {cfg['estimator']}: {len(train_df)} 样本 × {len(features)} 特征"
        f"（standardize={bool(cfg.get('standardize'))}）")

    bundle = {"model": pipeline, "features": features, "target": target,
              "estimator": cfg["estimator"]}
    with open(out_dir / "model.pkl", "wb") as f:
        pickle.dump(bundle, f)
    info = {"estimator": cfg["estimator"], "params": cfg.get("params") or {},
            "features": features, "target": target, "n_train": int(len(train_df)),
            "standardize": bool(cfg.get("standardize"))}
    (out_dir / "train_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    return {"model": "model.pkl", "train_info": "train_info.json"}
