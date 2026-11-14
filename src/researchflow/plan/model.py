"""plan.yaml 数据结构与结构校验（不含积木级契约，见 blocks/contract.py）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from researchflow import SCHEMA_VERSION
from researchflow.errors import PlanError
from researchflow.util import load_yaml, sha256_file

NODE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass
class Node:
    id: str
    kind: str                     # execution | decision
    title: str = ""
    block: str | None = None      # execution: "id@range"
    params: dict = field(default_factory=dict)
    inputs: dict = field(default_factory=dict)
    criteria: dict | None = None  # decision
    on_pass: list = field(default_factory=list)
    on_fail: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    notes: str = ""


@dataclass
class Plan:
    schema_version: int
    project: str
    meta: dict
    nodes: list
    path: Path = None

    @property
    def node_map(self) -> dict:
        return {n.id: n for n in self.nodes}

    def get(self, node_id: str) -> Node:
        node = self.node_map.get(node_id)
        if node is None:
            raise PlanError(f"节点 {node_id!r} 不存在。可用: {', '.join(n.id for n in self.nodes)}")
        return node

    def digest(self) -> str:
        return sha256_file(self.path)


def parse_binding(ref: str):
    """解析 "node-id.outputs.port" 形式的绑定，返回 (node_id, port)。"""
    node_id, sep, port = str(ref).partition(".outputs.")
    if not sep or not node_id or not port:
        raise PlanError(f"输入绑定格式错误: {ref!r}（期望 <node>.outputs.<port>）")
    return node_id, port


def _parse_node(raw, errors):
    if not isinstance(raw, dict):
        errors.append(f"节点必须是映射: {raw!r}")
        return None
    nid = raw.get("id")
    if not isinstance(nid, str) or not NODE_ID_RE.match(nid):
        errors.append(f"节点 id {nid!r} 不合法（小写字母/数字/连字符，字母或数字开头）")
        return None
    kind = raw.get("kind")
    if kind not in ("execution", "decision"):
        errors.append(f"节点 {nid}: kind 必须是 execution | decision")
        return None
    params = raw.get("params") or {}
    inputs = raw.get("inputs") or {}
    if not isinstance(params, dict):
        errors.append(f"节点 {nid}: params 必须是映射")
    if not isinstance(inputs, dict):
        errors.append(f"节点 {nid}: inputs 必须是映射")
    node = Node(
        id=nid, kind=kind, title=raw.get("title", ""),
        params=params, inputs=inputs,
        criteria=raw.get("criteria"),
        on_pass=list(raw.get("on_pass") or []),
        on_fail=list(raw.get("on_fail") or []),
        tags=list(raw.get("tags") or []), notes=raw.get("notes", ""),
    )
    if kind == "execution":
        node.block = raw.get("block")
        if not node.block:
            errors.append(f"执行节点 {nid}: 缺少 block 引用")
    return node


def load_plan(path) -> Plan:
    path = Path(path)
    if not path.is_file():
        raise PlanError(f"找不到计划文件: {path}")
    data = load_yaml(path) or {}
    if not isinstance(data, dict):
        raise PlanError(f"plan.yaml 必须是 YAML 映射: {path}")

    errors: list[str] = []
    sv = data.get("schema_version")
    if sv != SCHEMA_VERSION:
        errors.append(f"schema_version: {sv!r}，本 Core 支持 {SCHEMA_VERSION}")
    project = data.get("project")
    if not project:
        errors.append("project: 必填")
    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        errors.append("nodes: 必须是非空数组")

    nodes, seen = [], set()
    for raw in raw_nodes or []:
        node = _parse_node(raw, errors)
        if node is None:
            continue
        if node.id in seen:
            errors.append(f"节点 id 重复: {node.id}")
            continue
        seen.add(node.id)
        nodes.append(node)

    if errors:
        raise PlanError(f"计划结构校验失败: {path}", details=errors)
    return Plan(schema_version=sv, project=project, meta=data.get("meta") or {},
                nodes=nodes, path=path)
