"""产物登记与校验：sha256 指纹 + ArtifactRef。"""

from __future__ import annotations

from pathlib import Path

from researchflow.util import project_rel, sha256_file


def make_ref(file_path, type_, project_root) -> dict:
    """计算哈希并生成 ArtifactRef（path 为项目相对 POSIX 路径）。"""
    file_path = Path(file_path)
    return {
        "type": type_,
        "path": project_rel(file_path, project_root),
        "sha256": sha256_file(file_path),
    }


def register_artifact(store, run_id, port, file_path, type_, project_root) -> dict:
    ref = make_ref(file_path, type_, project_root)
    store.add_artifact(run_id, port, ref["path"], ref["sha256"], type_)
    return ref


def abs_path(project_root, ref: dict) -> Path:
    p = Path(ref["path"])
    return p if p.is_absolute() else Path(project_root) / p


def verify_ref(project_root, ref: dict, check_hash: bool = True):
    """校验产物存在且（可选）哈希一致。返回 (ok, detail)。"""
    path = abs_path(project_root, ref)
    if not path.is_file():
        return False, f"产物不存在: {ref['path']}"
    if check_hash:
        actual = sha256_file(path)
        if actual != ref.get("sha256"):
            return False, f"产物哈希不符: {ref['path']}（记录 {ref.get('sha256', '')[:12]}… 实际 {actual[:12]}…）"
    return True, ""
