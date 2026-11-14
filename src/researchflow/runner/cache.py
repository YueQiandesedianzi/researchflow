"""确定性积木的内容寻址缓存。

cache_key = sha256(积木源码指纹 + 解析后参数 + 各输入产物 sha256)
缓存目录: .researchflow/cache/<key>/{manifest.json, artifacts/}
"""

from __future__ import annotations

import shutil
from pathlib import Path

from researchflow.util import read_json, sha256_json, write_json_atomic


def make_cache_key(source_hash: str, params: dict, input_refs: dict) -> str:
    return sha256_json({
        "block": source_hash,
        "params": params,
        "inputs": {port: ref["sha256"] for port, ref in sorted(input_refs.items())},
    })


def cache_dir(rf_dir, key: str) -> Path:
    return Path(rf_dir) / "cache" / key


def store_to_cache(rf_dir, key: str, artifacts: dict, project_root) -> None:
    """artifacts: {port: ref}，把产物文件复制进缓存。"""
    from researchflow.registry.artifacts import abs_path

    dest = cache_dir(rf_dir, key)
    dest_artifacts = dest / "artifacts"
    dest_artifacts.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for port, ref in artifacts.items():
        src = abs_path(project_root, ref)
        target = dest_artifacts / src.name
        shutil.copy2(src, target)
        manifest[port] = {"type": ref["type"], "sha256": ref["sha256"], "filename": src.name}
    write_json_atomic(dest / "manifest.json", manifest)


def replay_from_cache(rf_dir, key: str, run_artifacts_dir, project_root):
    """从缓存复制产物到 Run 目录，返回 {port: 目标文件路径}；缓存损坏返回 None。"""
    from researchflow.util import sha256_file

    dest = cache_dir(rf_dir, key)
    manifest_path = dest / "manifest.json"
    if not manifest_path.is_file():
        return None
    manifest = read_json(manifest_path)
    copied = {}
    for port, item in manifest.items():
        src = dest / "artifacts" / item["filename"]
        if not src.is_file() or sha256_file(src) != item["sha256"]:
            return None  # 缓存损坏 → 视为未命中
        target = Path(run_artifacts_dir) / item["filename"]
        shutil.copy2(src, target)
        copied[port] = target
    return copied
