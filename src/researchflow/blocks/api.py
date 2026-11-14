"""积木实现侧的稳定 API。

积木（包括独立分发的积木包）只应依赖本模块与标准科学计算栈，
不感知 Plan / Registry / Agent 的存在。

实现函数约定签名::

    def fn(inputs, params, out_dir, log) -> dict[str, str]:
        # inputs: {端口名: Ref}（Ref.path 为绝对路径）
        # params: 已按 schema 校验并应用默认值的 dict；
        #         另注入 ``_project_root``（项目根绝对路径），
        #         项目相对路径用 resolve_in_project(params["path"], params["_project_root"]) 解析
        # out_dir: 本次运行的产物目录（Path），积木只应写入此目录
        # log:  Callable[[str], None]
        # 返回: {输出端口名: 产物文件名（相对 out_dir）}
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Ref:
    path: Path
    type: str = "file"
    sha256: str = ""


def resolve_in_project(p, project_root) -> Path:
    """把项目相对路径解析为绝对路径（已是绝对路径则原样返回）。"""
    p = Path(p)
    return p if p.is_absolute() else Path(project_root) / p
