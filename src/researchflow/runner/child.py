"""积木子进程执行器：``python -m researchflow.runner.child <job.json>``。

job.json: {
  "block_dir": str, "entry": "module:callable",
  "inputs": {port: {"type": str, "path": str(abs), "sha256": str}},
  "params": {...}, "out_dir": str(abs), "project_root": str, "result_file": str(abs)
}
子进程只把结果写入 result_file；stdout/stderr 由父进程重定向到日志。
"""

from __future__ import annotations

import importlib.util
import json
import sys
import traceback
from pathlib import Path

from researchflow.blocks.api import Ref


def _log(msg):
    print(f"[block] {msg}", flush=True)


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    job_path = Path(argv[0])
    job = json.loads(job_path.read_text(encoding="utf-8"))
    result_file = Path(job["result_file"])
    out_dir = Path(job["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        block_dir = Path(job["block_dir"])
        module_name, func_name = job["entry"].split(":", 1)
        module_file = block_dir / (module_name.replace(".", "/") + ".py")
        spec = importlib.util.spec_from_file_location(f"rf_block_{module_name}", module_file)
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(block_dir))
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path.remove(str(block_dir))
        fn = getattr(module, func_name)

        inputs = {
            port: Ref(path=Path(ref["path"]), type=ref.get("type", "file"),
                      sha256=ref.get("sha256", ""))
            for port, ref in job["inputs"].items()
        }
        params = dict(job["params"])
        params.setdefault("_project_root", job["project_root"])
        _log(f"执行 {job['entry']}，输出目录 {out_dir}")
        outputs = fn(inputs, params, out_dir, _log)
        if not isinstance(outputs, dict):
            raise TypeError(f"积木返回值必须是 {{端口: 文件名}} 映射，得到 {type(outputs).__name__}")
        for port, filename in outputs.items():
            if not isinstance(filename, str) or Path(filename).is_absolute() or ".." in Path(filename).parts:
                raise ValueError(f"输出端口 {port!r} 的文件名不合法: {filename!r}")
        result_file.write_text(json.dumps({"ok": True, "outputs": outputs}, ensure_ascii=False),
                               encoding="utf-8")
        return 0
    except Exception:
        traceback.print_exc()
        result_file.write_text(
            json.dumps({"ok": False, "error": traceback.format_exc(limit=10)}, ensure_ascii=False),
            encoding="utf-8",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
