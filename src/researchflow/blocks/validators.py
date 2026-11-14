"""内置验证器库（Validation Engine 的判定逻辑）。

每个验证器签名: fn(ctx, spec) -> Finding。
- ctx: ValidatorContext（输入/输出产物、参数、Run 目录、所属积木）
- spec: validation 条目的参数（字符串条目时为 {}）
验证器自身抛异常视为"未通过"（detail 记录异常），由 gate 兜底。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass
class ValidatorContext:
    inputs: dict            # 端口 -> Ref（绝对路径）
    outputs: dict           # 端口 -> Ref（绝对路径）
    params: dict
    run_dir: Path
    project_root: Path
    block: object = None    # 所属 Block（可读端口 schema）


@dataclass
class Finding:
    name: str
    passed: bool
    detail: str = ""


def _read_table(ref) -> pd.DataFrame:
    return pd.read_csv(ref.path)


def _read_json(ref):
    return json.loads(Path(ref.path).read_text(encoding="utf-8"))


def _indices_outputs(ctx):
    return {p: r for p, r in ctx.outputs.items() if r.type == "indices"}


def _split_pair(ctx):
    """在 indices 输出中找 train/test 对（folds 结构返回 None）。"""
    outs = _indices_outputs(ctx)
    train = next((outs[p] for p in outs if "train" in p), None)
    test = next((outs[p] for p in outs if "test" in p), None)
    if train is None or test is None:
        return None
    return _read_json(train), _read_json(test)


def v_file_exists(ctx, spec) -> Finding:
    missing = [p for p, r in ctx.outputs.items()
               if not Path(r.path).is_file() or Path(r.path).stat().st_size == 0]
    if missing:
        return Finding("file_exists", False, f"产物缺失或为空: {missing}")
    return Finding("file_exists", True, f"{len(ctx.outputs)} 个产物齐备")


def v_non_empty_splits(ctx, spec) -> Finding:
    problems = []
    for port, ref in _indices_outputs(ctx).items():
        data = _read_json(ref)
        if isinstance(data, list) and data and isinstance(data[0], dict):
            for i, fold in enumerate(data):
                if not fold.get("train") or not fold.get("test"):
                    problems.append(f"{port}[fold {i}] 存在空集")
        elif not data:
            problems.append(f"{port} 为空")
    if problems:
        return Finding("non_empty_splits", False, "; ".join(problems))
    return Finding("non_empty_splits", True, "")


def v_no_group_overlap(ctx, spec) -> Finding:
    pair = _split_pair(ctx)
    if pair is None:
        return Finding("no_group_overlap", False, "未找到 train/test 索引对（folds 结构请用 custom 验证）")
    group_col = ctx.params.get("group_column")
    if not group_col:
        return Finding("no_group_overlap", False, "params 缺少 group_column")
    df = _read_table(ctx.inputs["dataset"])
    train_idx, test_idx = pair
    g_train = set(df.iloc[train_idx][group_col].unique())
    g_test = set(df.iloc[test_idx][group_col].unique())
    overlap = g_train & g_test
    if overlap:
        sample = sorted(map(str, overlap))[:5]
        return Finding("no_group_overlap", False, f"{len(overlap)} 个组同时出现在两侧: {sample}")
    return Finding("no_group_overlap", True, f"train {len(g_train)} 组 / test {len(g_test)} 组无交集")


def v_no_time_leakage(ctx, spec) -> Finding:
    time_col = ctx.params.get("time_column")
    if not time_col:
        return Finding("no_time_leakage", False, "params 缺少 time_column")
    df = _read_table(ctx.inputs["dataset"])
    times = pd.to_datetime(df[time_col])
    gap = int(ctx.params.get("gap", 0) or 0)
    pairs = []
    pair = _split_pair(ctx)
    if pair is not None:
        pairs.append(("split", pair[0], pair[1]))
    else:
        for port, ref in _indices_outputs(ctx).items():
            data = _read_json(ref)
            if isinstance(data, list) and data and isinstance(data[0], dict):
                for i, fold in enumerate(data):
                    pairs.append((f"{port}[fold {i}]", fold["train"], fold["test"]))
    if not pairs:
        return Finding("no_time_leakage", False, "未找到可检查的划分")
    problems = []
    for label, train_idx, test_idx in pairs:
        t_max, t_min = times.iloc[train_idx].max(), times.iloc[test_idx].min()
        if t_max > t_min:
            problems.append(f"{label}: train 截止 {t_max} 晚于 test 起始 {t_min}")
        if gap and (min(test_idx) - max(train_idx)) <= gap:
            problems.append(f"{label}: 间隔不足 gap={gap} 行")
    if problems:
        return Finding("no_time_leakage", False, "; ".join(problems))
    return Finding("no_time_leakage", True, f"{len(pairs)} 组划分时序有序")


def v_row_count_preserved(ctx, spec) -> Finding:
    table_in = next((r for r in ctx.inputs.values() if r.type in ("table", "series")), None)
    if table_in is None:
        return Finding("row_count_preserved", False, "无 table 输入可对照")
    n_in = len(_read_table(table_in))
    bad = []
    for port, ref in ctx.outputs.items():
        if ref.type in ("table", "series"):
            n_out = len(_read_table(ref))
            if n_out != n_in:
                bad.append(f"{port}: {n_out} != {n_in}")
    if bad:
        return Finding("row_count_preserved", False, "; ".join(bad))
    return Finding("row_count_preserved", True, f"{n_in} 行")


def v_no_nan(ctx, spec) -> Finding:
    bad = []
    for port, ref in ctx.outputs.items():
        if ref.type in ("table", "series"):
            df = _read_table(ref)
            n = int(df.isna().sum().sum())
            if n:
                cols = df.columns[df.isna().any()].tolist()[:5]
                bad.append(f"{port}: {n} 个 NaN（列: {cols}）")
    if bad:
        return Finding("no_nan", False, "; ".join(bad))
    return Finding("no_nan", True, "")


def v_schema_matches(ctx, spec) -> Finding:
    problems = []
    for port, ref in ctx.outputs.items():
        if ref.type not in ("table", "series"):
            continue
        declared = ((ctx.block.outputs.get(port) or {}).get("schema") or {}) if ctx.block else {}
        required = declared.get("required_columns") or []
        if not required:
            continue
        cols = set(_read_table(ref).columns)
        missing = [c for c in required if c not in cols]
        if missing:
            problems.append(f"{port}: 缺少列 {missing}")
    if problems:
        return Finding("schema_matches", False, "; ".join(problems))
    return Finding("schema_matches", True, "")


def v_metrics_keys_present(ctx, spec) -> Finding:
    problems = []
    for port, ref in ctx.outputs.items():
        if ref.type != "metrics":
            continue
        declared = ((ctx.block.outputs.get(port) or {}).get("schema") or {}) if ctx.block else {}
        required = declared.get("required_keys") or []
        keys = set(_read_json(ref).keys())
        missing = [k for k in required if k not in keys]
        if missing:
            problems.append(f"{port}: 缺少指标键 {missing}")
    if problems:
        return Finding("metrics_keys_present", False, "; ".join(problems))
    return Finding("metrics_keys_present", True, "")

_OPS = {
    "<": lambda a, b: a < b, "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
}


def v_metric_threshold(ctx, spec) -> Finding:
    metric, op, value = spec.get("metric"), spec.get("op"), spec.get("value")
    if not metric or op not in _OPS or value is None:
        return Finding("metric_threshold", False, f"规格不完整: {spec!r}（需要 metric/op/value）")
    metrics_ref = next((r for r in ctx.outputs.values() if r.type == "metrics"), None)
    if metrics_ref is None:
        return Finding("metric_threshold", False, "无 metrics 输出")
    data = _read_json(metrics_ref)
    if metric not in data:
        return Finding("metric_threshold", False, f"指标 {metric!r} 不存在（可用: {sorted(data)}）")
    actual = data[metric]
    ok = _OPS[op](actual, value)
    return Finding("metric_threshold", ok, f"{metric}={actual} {op} {value} → {'通过' if ok else '未过'}")


BUILTIN_VALIDATORS = {
    "file_exists": v_file_exists,
    "non_empty_splits": v_non_empty_splits,
    "no_group_overlap": v_no_group_overlap,
    "no_time_leakage": v_no_time_leakage,
    "row_count_preserved": v_row_count_preserved,
    "no_nan": v_no_nan,
    "schema_matches": v_schema_matches,
    "metrics_keys_present": v_metrics_keys_present,
    "metric_threshold": v_metric_threshold,
}
