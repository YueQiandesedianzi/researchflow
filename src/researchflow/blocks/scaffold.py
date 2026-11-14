"""积木脚手架：rf blocks new —— 30 秒创建合规积木。

生成的积木：契约立即通过 ``rf blocks check``；实现是可运行的 passthrough
（不是空壳），``--smoke`` 可在临时计划中真实跑一次。Agent 生成积木时
先 scaffold 再改实现，比凭空写两个文件可靠得多。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from researchflow.blocks.schema import CATEGORIES, ID_RE, load_block
from researchflow.errors import ContractError
from researchflow.util import dump_yaml

# ---------- 形状模板（category → 端口形状 + 可运行实现） ----------

_IMPL_TABLE2TABLE = '''import pandas as pd


def run(inputs, params, out_dir, log):
    """TODO: 在此实现你的方法。inputs["dataset"].path 为输入产物绝对路径；
    产物写入 out_dir 并返回 {输出端口: 文件名}。"""
    df = pd.read_csv(inputs["dataset"].path)
    # TODO: 对 df 施加你的变换（当前为 passthrough）
    log(f"输入 {len(df)} 行（脚手架 passthrough，请实现你的逻辑）")
    df.to_csv(out_dir / "table.csv", index=False)
    return {"table": "table.csv"}
'''

_IMPL_SPLIT = '''import json

import numpy as np
import pandas as pd


def run(inputs, params, out_dir, log):
    df = pd.read_csv(inputs["dataset"].path)
    n = len(df)
    n_test = max(1, int(round(n * params["test_size"])))
    rng = np.random.RandomState(params["seed"])
    order = rng.permutation(n)
    # TODO: 替换为你的划分逻辑（当前为随机留出）
    test = sorted(order[:n_test].tolist())
    train = sorted(order[n_test:].tolist())
    log(f"train {len(train)} / test {len(test)}")
    (out_dir / "train_indices.json").write_text(json.dumps(train), encoding="utf-8")
    (out_dir / "test_indices.json").write_text(json.dumps(test), encoding="utf-8")
    return {"train_indices": "train_indices.json", "test_indices": "test_indices.json"}
'''

_IMPL_EVALUATE = '''import json

import pandas as pd


def run(inputs, params, out_dir, log):
    df = pd.read_csv(inputs["predictions"].path)
    # TODO: 计算你的指标（约定 predictions 含 y_true / y_pred 列）
    metrics = {"n_rows": int(len(df))}
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    log(f"metrics: {metrics}")
    return {"metrics": "metrics.json"}
'''

_IMPL_VISUALIZE = '''import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def run(inputs, params, out_dir, log):
    df = pd.read_csv(inputs["predictions"].path)
    fig, ax = plt.subplots(figsize=(5, 4), dpi=150)
    # TODO: 替换为你的绘图逻辑
    ax.plot(df.index, df.iloc[:, -1], ".", ms=3)
    ax.set_title(params.get("title", "plot"))
    fig.tight_layout()
    fig.savefig(out_dir / "figure.png")
    plt.close(fig)
    log("figure.png")
    return {"figure": "figure.png"}
'''

_IMPL_IO = '''import pandas as pd

from researchflow.blocks.api import resolve_in_project


def run(inputs, params, out_dir, log):
    src = resolve_in_project(params["path"], params.get("_project_root", "."))
    df = pd.read_csv(src)
    log(f"载入 {src.name}: {len(df)} 行")
    df.to_csv(out_dir / "table.csv", index=False)
    return {"table": "table.csv"}
'''

_IMPL_GENERIC = '''import json

import pandas as pd


def run(inputs, params, out_dir, log):
    df = pd.read_csv(inputs["dataset"].path)
    result = {"rows": int(len(df)), "columns": [str(c) for c in df.columns]}
    # TODO: 实现你的逻辑
    (out_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    log(f"result: {result}")
    return {"result": "result.json"}
'''

_SHAPES = {
    "io": {
        "inputs": {},
        "outputs": {"table": {"type": "table", "description": "输出数据表"}},
        "params": {"type": "object", "required": ["path"],
                   "properties": {"path": {"type": "string", "description": "项目相对路径的 CSV"}}},
        "validation": ["file_exists"],
        "impl": _IMPL_IO,
    },
    "table2table": {
        "inputs": {"dataset": {"type": "table", "description": "输入数据表"}},
        "outputs": {"table": {"type": "table", "description": "输出数据表"}},
        "params": {"type": "object", "properties": {}},
        "validation": ["file_exists"],
        "impl": _IMPL_TABLE2TABLE,
    },
    "split": {
        "inputs": {"dataset": {"type": "table", "description": "输入数据表"}},
        "outputs": {"train_indices": {"type": "indices"}, "test_indices": {"type": "indices"}},
        "params": {"type": "object",
                   "properties": {"test_size": {"type": "number", "default": 0.2, "minimum": 0.05, "maximum": 0.5},
                                  "seed": {"type": "integer", "default": 42}}},
        "validation": ["non_empty_splits"],
        "impl": _IMPL_SPLIT,
    },
    "evaluate": {
        "inputs": {"predictions": {"type": "table", "description": "预测表"}},
        "outputs": {"metrics": {"type": "metrics", "description": "指标集合"}},
        "params": {"type": "object", "properties": {}},
        "validation": ["file_exists"],
        "impl": _IMPL_EVALUATE,
    },
    "visualize": {
        "inputs": {"predictions": {"type": "table", "description": "预测表"}},
        "outputs": {"figure": {"type": "figure", "description": "输出图"}},
        "params": {"type": "object", "properties": {"title": {"type": "string", "default": "plot"}}},
        "validation": ["file_exists"],
        "impl": _IMPL_VISUALIZE,
    },
    "generic": {
        "inputs": {"dataset": {"type": "table", "description": "输入数据表"}},
        "outputs": {"result": {"type": "json", "description": "结果"}},
        "params": {"type": "object", "properties": {}},
        "validation": ["file_exists"],
        "impl": _IMPL_GENERIC,
    },
}

_CATEGORY_SHAPE = {
    "io": "io", "transform": "table2table", "feature": "table2table",
    "data_split": "split", "model": "table2table", "evaluate": "evaluate",
    "visualize": "visualize",
}


def scaffold(project_root, block_id: str, title: str | None = None,
             force: bool = False) -> dict:
    """在项目 blocks/ 下生成积木骨架并立即契约校验。"""
    if not ID_RE.match(block_id):
        raise ContractError(f"积木 id {block_id!r} 不合法（需形如 category.name，小写/数字/下划线/点）")
    category = block_id.split(".")[0]
    if category not in CATEGORIES:
        raise ContractError(
            f"category {category!r} 无效，可选: {', '.join(sorted(CATEGORIES))}")
    shape_name = _CATEGORY_SHAPE.get(category, "generic")
    shape = _SHAPES[shape_name]

    block_dir = Path(project_root) / "blocks" / block_id
    if block_dir.exists() and not force:
        raise ContractError(f"积木目录已存在: {block_dir}（加 --force 覆盖）")
    block_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "id": block_id,
        "version": "0.1.0",
        "schema_version": 1,
        "category": category,
        "title": title or block_id,
        "description": "TODO: 一句话说明这个积木做什么（Agent 检索依据）",
        "kind": "python",
        "entry": "impl:run",
        "inputs": shape["inputs"],
        "outputs": shape["outputs"],
        "params": shape["params"],
        "validation": shape["validation"],
        "execution": {"deterministic": True, "requires_approval": False,
                      "timeout_seconds": 300},
    }
    (block_dir / "block.yaml").write_text(dump_yaml(manifest), encoding="utf-8")
    (block_dir / "impl.py").write_text(shape["impl"], encoding="utf-8")

    block = load_block(block_dir, "project", 3)
    return {"dir": str(block_dir), "shape": shape_name, "block": block.ref,
            "category": category}


def _smoke_params(block) -> dict | None:
    """为冒烟计划推断必需参数；无法推断返回 None。"""
    schema = block.params_schema or {}
    params = {}
    for key in schema.get("required", []):
        prop = (schema.get("properties") or {}).get(key, {})
        if "default" in prop:
            continue
        if key == "path":
            params[key] = "data/fixture.csv"
        else:
            return None
    return params


def smoke_test(project_root, block_id: str) -> dict:
    """对 table 输入型积木做最小端到端：临时计划 load → 新积木 → run。"""
    from researchflow.blocks.loader import discover
    from researchflow.project import Project
    from researchflow.runner.executor import Executor

    index = discover(project_root)
    block = index.resolve(block_id)
    dataset_spec = block.inputs.get("dataset")
    if dataset_spec is None or dataset_spec.get("type") != "table":
        return {"skipped": "积木没有 table 型 dataset 输入，跳过冒烟（请自行接入 plan 测试）"}
    params = _smoke_params(block)
    if params is None:
        return {"skipped": "存在无法推断的必需参数，跳过冒烟"}

    with tempfile.TemporaryDirectory(prefix="rf-smoke-") as tmp:
        root = Path(tmp)
        (root / "data").mkdir(parents=True)
        rows = ["x,y"] + [f"{i},{2 * i + 1}" for i in range(12)]
        (root / "data" / "fixture.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
        (root / "researchflow.yaml").write_text(
            "schema_version: 1\nname: smoke\nseed: 42\n", encoding="utf-8")
        plan = {
            "schema_version": 1,
            "project": "smoke",
            "nodes": [
                {"id": "load-01", "kind": "execution", "block": "io.load_csv@^0.1.0",
                 "params": {"path": "data/fixture.csv", "target": "y"}},
                {"id": "new-01", "kind": "execution", "block": f"{block.id}@{block.version_str}",
                 "params": params,
                 "inputs": {"dataset": {"from": "load-01.outputs.table"}}},
            ],
        }
        (root / "plan.yaml").write_text(dump_yaml(plan), encoding="utf-8")
        # 让被测积木以项目级身份可见：链接进临时项目
        import shutil
        shutil.copytree(Path(project_root) / "blocks" / block.id,
                        root / "blocks" / block.id)

        ex = Executor(Project.open(root), quiet=True)
        try:
            code = ex.run(run_all=True, yes=True)
            return {"ok": code == 0, "results": ex.results}
        finally:
            ex.close()
