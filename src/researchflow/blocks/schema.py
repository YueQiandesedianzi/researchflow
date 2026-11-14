"""block.yaml 契约校验（Block Contract v1）。

见 docs/03-block-schema.md。校验失败抛 ContractError，附全部问题清单。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from researchflow import SCHEMA_VERSION
from researchflow.errors import ContractError
from researchflow.util import load_yaml

PORT_TYPES = {"table", "series", "indices", "model", "metrics", "figure", "json", "file"}
CATEGORIES = {
    "io", "transform", "data_split", "feature",
    "model", "evaluate", "visualize", "decide", "export",
}
ID_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.\-]+)?$")
ENTRY_RE = re.compile(r"^[A-Za-z_][\w.]*:[A-Za-z_][\w.]*$")


@dataclass
class Block:
    id: str
    version: tuple          # (major, minor, patch)
    version_str: str
    category: str
    title: str
    description: str
    kind: str               # v0.1 仅 "python"
    entry_module: str
    entry_func: str
    inputs: dict
    outputs: dict
    params_schema: dict
    validation: list
    deterministic: bool
    requires_approval: bool
    timeout_seconds: int
    env: list
    schema_version: int
    source: str             # builtin | pack:<entry-point> | project
    precedence: int         # project 3 > pack 2 > builtin 1
    dir: Path = field(default=None)

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version_str}"


def _check_ports(name, ports, errors):
    if ports is None:
        return {}
    if not isinstance(ports, dict):
        errors.append(f"{name}: 必须是端口名到 PortSpec 的映射")
        return {}
    for port, spec in ports.items():
        if not isinstance(spec, dict):
            errors.append(f"{name}.{port}: PortSpec 必须是映射")
            continue
        t = spec.get("type")
        if t not in PORT_TYPES:
            errors.append(f"{name}.{port}.type: {t!r} 不在 {sorted(PORT_TYPES)}")
        if "required" in spec and not isinstance(spec["required"], bool):
            errors.append(f"{name}.{port}.required: 必须是布尔值")
        if "schema" in spec and not isinstance(spec["schema"], dict):
            errors.append(f"{name}.{port}.schema: 必须是映射")
    return ports


def _check_params(schema, errors):
    if schema is None:
        return {"type": "object", "properties": {}}
    if not isinstance(schema, dict) or schema.get("type") != "object":
        errors.append("params: 必须是 type: object 的 JSON Schema")
        return {}
    props = schema.get("properties", {})
    if not isinstance(props, dict):
        errors.append("params.properties: 必须是映射")
    allowed = {"string", "number", "integer", "boolean", "array", "object"}
    for key, sub in props.items():
        if not isinstance(sub, dict):
            errors.append(f"params.{key}: 必须是映射")
            continue
        if sub.get("type") not in allowed:
            errors.append(f"params.{key}.type: {sub.get('type')!r} 不支持（{sorted(allowed)}）")
    req = schema.get("required", [])
    if not isinstance(req, list):
        errors.append("params.required: 必须是数组")
    return schema


def _check_validation(entries, errors):
    if entries is None:
        return []
    if not isinstance(entries, list):
        errors.append("validation: 必须是数组")
        return []
    for i, item in enumerate(entries):
        if isinstance(item, str):
            continue
        if isinstance(item, dict) and len(item) == 1:
            continue
        errors.append(f"validation[{i}]: 必须是验证器名或单键映射，得到 {item!r}")
    return entries


def _check_execution(spec, errors):
    spec = spec or {}
    out = {
        "deterministic": spec.get("deterministic"),
        "requires_approval": spec.get("requires_approval"),
        "timeout_seconds": spec.get("timeout_seconds", 3600),
        "env": spec.get("env", []),
    }
    if not isinstance(out["deterministic"], bool):
        errors.append("execution.deterministic: 必填且必须是布尔值")
    if not isinstance(out["requires_approval"], bool):
        errors.append("execution.requires_approval: 必填且必须是布尔值")
    if not isinstance(out["timeout_seconds"], int) or out["timeout_seconds"] <= 0:
        errors.append("execution.timeout_seconds: 必须是正整数")
    if not isinstance(out["env"], list):
        errors.append("execution.env: 必须是数组")
    return out


def load_block(block_dir, source: str, precedence: int) -> Block:
    """解析并校验一个积木目录，返回 Block；契约问题抛 ContractError。"""
    block_dir = Path(block_dir)
    manifest_path = block_dir / "block.yaml"
    if not manifest_path.is_file():
        raise ContractError(f"积木目录缺少 block.yaml: {block_dir}")
    data = load_yaml(manifest_path) or {}
    if not isinstance(data, dict):
        raise ContractError(f"block.yaml 必须是 YAML 映射: {manifest_path}")

    errors: list[str] = []
    bid = data.get("id")
    if not isinstance(bid, str) or not ID_RE.match(bid):
        errors.append(f"id: {bid!r} 不合法（需形如 category.name，小写字母/数字/下划线/点）")

    version_str = str(data.get("version", ""))
    m = SEMVER_RE.match(version_str)
    if not m:
        errors.append(f"version: {version_str!r} 不是合法 semver")
        version = (0, 0, 0)
    else:
        version = (int(m.group(1)), int(m.group(2)), int(m.group(3)))

    sv = data.get("schema_version")
    if sv != SCHEMA_VERSION:
        errors.append(f"schema_version: {sv!r}，本 Core 支持 {SCHEMA_VERSION}")

    category = data.get("category")
    if category not in CATEGORIES:
        errors.append(f"category: {category!r} 不在 {sorted(CATEGORIES)}")

    title = data.get("title")
    description = data.get("description")
    if not title:
        errors.append("title: 必填")
    if not description:
        errors.append("description: 必填")

    kind = data.get("kind")
    if kind != "python":
        errors.append(f"kind: {kind!r}，v0.1 仅支持 'python'")

    entry = data.get("entry", "")
    if not isinstance(entry, str) or not ENTRY_RE.match(entry):
        errors.append(f"entry: {entry!r} 需形如 module:callable")
        entry_module, entry_func = "", ""
    else:
        entry_module, entry_func = entry.split(":", 1)
        if kind == "python" and not (block_dir / (entry_module.replace(".", "/") + ".py")).is_file():
            errors.append(f"entry: 找不到实现文件 {entry_module}.py（{block_dir}）")

    inputs = _check_ports("inputs", data.get("inputs"), errors)
    outputs = _check_ports("outputs", data.get("outputs"), errors)
    if not outputs:
        errors.append("outputs: 至少声明一个输出端口")
    params_schema = _check_params(data.get("params"), errors)
    validation = _check_validation(data.get("validation"), errors)
    exec_spec = _check_execution(data.get("execution"), errors)

    if errors:
        raise ContractError(f"积木契约校验失败: {manifest_path}", details=errors)

    return Block(
        id=bid, version=version, version_str=version_str, category=category,
        title=title, description=description, kind=kind,
        entry_module=entry_module, entry_func=entry_func,
        inputs=inputs or {}, outputs=outputs or {}, params_schema=params_schema,
        validation=validation,
        deterministic=exec_spec["deterministic"],
        requires_approval=exec_spec["requires_approval"],
        timeout_seconds=exec_spec["timeout_seconds"], env=exec_spec["env"],
        schema_version=sv, source=source, precedence=precedence, dir=block_dir,
    )
