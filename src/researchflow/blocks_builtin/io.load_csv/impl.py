import hashlib
import json

import pandas as pd

from researchflow.blocks.api import resolve_in_project


def load_csv(inputs, params, out_dir, log):
    src = resolve_in_project(params["path"], params.get("_project_root", "."))
    if not src.is_file():
        raise FileNotFoundError(f"数据文件不存在: {src}")
    df = pd.read_csv(src)
    log(f"载入 {src.name}: {len(df)} 行 × {df.shape[1]} 列")
    out = out_dir / "table.csv"
    df.to_csv(out, index=False)
    meta = {
        "source_path": str(src),
        "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
        "rows": int(len(df)),
        "columns": [str(c) for c in df.columns],
    }
    if params.get("target"):
        meta["target"] = params["target"]
    if params.get("time_column"):
        meta["time_column"] = params["time_column"]
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    return {"table": "table.csv"}
