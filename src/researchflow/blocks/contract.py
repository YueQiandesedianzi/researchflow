"""参数校验（JSON Schema 子集）与计划接线契约检查。"""

from __future__ import annotations

from researchflow.errors import ContractError, PlanError

_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


def check_params(schema: dict | None, params: dict | None, where: str = "params") -> dict:
    """按积木 params schema 校验并应用默认值，返回解析后的参数。失败抛 ContractError。"""
    schema = schema or {"type": "object", "properties": {}}
    props = schema.get("properties", {})
    params = dict(params or {})
    errors: list[str] = []
    resolved: dict = {}

    for key, sub in props.items():
        if key in params:
            value = params[key]
        elif "default" in sub:
            value = sub["default"]
        else:
            continue
        t = sub.get("type")
        if t and not _TYPE_CHECKS[t](value):
            errors.append(f"{where}.{key}: 期望 {t}，得到 {type(value).__name__}（{value!r}）")
            continue
        if "enum" in sub and value not in sub["enum"]:
            errors.append(f"{where}.{key}: {value!r} 不在枚举 {sub['enum']} 内")
        if t in ("number", "integer"):
            if "minimum" in sub and value < sub["minimum"]:
                errors.append(f"{where}.{key}: {value} 小于 minimum {sub['minimum']}")
            if "maximum" in sub and value > sub["maximum"]:
                errors.append(f"{where}.{key}: {value} 大于 maximum {sub['maximum']}")
        resolved[key] = value

    for key in schema.get("required", []):
        if key not in params and "default" not in props.get(key, {}):
            errors.append(f"{where}.{key}: 缺少必需参数")
    for key in params:
        if key not in props:
            errors.append(f"{where}.{key}: 未声明的参数（拼写错误？）。已声明: {sorted(props)}")

    if errors:
        raise ContractError(f"参数契约校验失败（{where}）", details=errors)
    return resolved


def _check_binding(plan, node, port, port_spec, binding, resolve_block, errors):
    from researchflow.plan.model import parse_binding

    if not isinstance(binding, dict):
        errors.append(f"节点 {node.id} 输入 {port!r}: 绑定必须是 {{from: ...}} 或 {{value: ...}}")
        return
    if "value" in binding:
        return  # 字面量绑定在运行时物化为 json 产物
    if "from" not in binding:
        errors.append(f"节点 {node.id} 输入 {port!r}: 绑定需要 from 或 value 键")
        return
    try:
        up_id, up_port = parse_binding(binding["from"])
    except PlanError as exc:
        errors.append(f"节点 {node.id} 输入 {port!r}: {exc.message}")
        return
    up = plan.node_map.get(up_id)
    if up is None:
        errors.append(f"节点 {node.id} 输入 {port!r}: 上游节点 {up_id!r} 不存在")
        return
    if up.id == node.id:
        errors.append(f"节点 {node.id} 输入 {port!r}: 不能引用自身")
        return
    if up.kind != "execution":
        errors.append(f"节点 {node.id} 输入 {port!r}: {up_id!r} 是决策节点，没有数据输出")
        return
    up_block = resolve_block(up)
    if up_block is None:
        return
    out_spec = up_block.outputs.get(up_port)
    if out_spec is None:
        errors.append(
            f"节点 {node.id} 输入 {port!r}: 上游 {up_id} 的积木 {up_block.id} "
            f"没有输出端口 {up_port!r}（可选: {sorted(up_block.outputs)}）"
        )
        return
    expected = port_spec.get("type")
    if expected and out_spec["type"] != expected:
        errors.append(
            f"节点 {node.id} 输入 {port!r}: 类型不符——需要 {expected}，"
            f"上游 {up_id}.outputs.{up_port} 提供 {out_spec['type']}"
        )


def check_plan_contracts(plan, index) -> None:
    """校验整个计划的积木引用、参数与端口接线。失败抛 PlanError（退出码 2）。"""
    errors: list[str] = []
    resolved_cache: dict = {}

    def resolve_block(node):
        if node.id not in resolved_cache:
            try:
                resolved_cache[node.id] = index.resolve(node.block)
            except ContractError as exc:
                errors.append(f"节点 {node.id}: {exc.message}")
                resolved_cache[node.id] = None
        return resolved_cache[node.id]

    for node in plan.nodes:
        if node.kind == "execution":
            block = resolve_block(node)
            if block is None:
                continue
            try:
                check_params(block.params_schema, node.params, where=f"节点 {node.id} 参数")
            except ContractError as exc:
                errors.extend(exc.details or [exc.message])
            for port, spec in block.inputs.items():
                binding = node.inputs.get(port)
                if binding is None:
                    if spec.get("required", True):
                        errors.append(f"节点 {node.id}: 缺少必需输入端口 {port!r}")
                    continue
                _check_binding(plan, node, port, spec, binding, resolve_block, errors)
            for port in node.inputs:
                if port not in block.inputs:
                    errors.append(f"节点 {node.id}: 绑定了积木未声明的输入端口 {port!r}")
        else:  # decision
            mode = (node.criteria or {}).get("mode")
            if mode not in ("auto", "manual", "auto_then_manual"):
                errors.append(f"决策节点 {node.id}: criteria.mode 必须是 auto | manual | auto_then_manual")
            if mode in ("auto", "auto_then_manual") and not (node.criteria or {}).get("expression"):
                errors.append(f"决策节点 {node.id}: mode={mode} 需要 criteria.expression")
            for port, binding in node.inputs.items():
                _check_binding(plan, node, port, {}, binding, resolve_block, errors)
            for target in (node.on_pass or []) + (node.on_fail or []):
                if target not in plan.node_map:
                    errors.append(f"决策节点 {node.id}: on_pass/on_fail 引用了不存在的节点 {target!r}")

    if errors:
        raise PlanError("计划契约校验失败", details=errors)
