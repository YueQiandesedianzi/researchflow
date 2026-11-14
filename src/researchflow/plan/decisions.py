"""决策节点：受限表达式求值（AST 白名单，禁止任意函数调用）。

上下文形如 {"candidate": {...metrics}, "baseline": {...}}，
表达式示例: ``candidate.rmse <= baseline.rmse * 0.95``。
"""

from __future__ import annotations

import ast
import operator

from researchflow.errors import ContractError

_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Mod: operator.mod,
}
_CMPOPS = {
    ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
    ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne,
}


def _eval(node, context):
    if isinstance(node, ast.Expression):
        return _eval(node.body, context)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, bool)):
            return node.value
        raise ContractError(f"表达式常量类型不允许: {node.value!r}")
    if isinstance(node, ast.Name):
        if node.id not in context:
            raise ContractError(f"表达式引用了未提供的变量 {node.id!r}（可用: {sorted(context)}）")
        return context[node.id]
    if isinstance(node, ast.Attribute):
        base = _eval(node.value, context)
        if not isinstance(base, dict):
            raise ContractError(f"只能对指标集合取属性: .{node.attr}")
        if node.attr not in base:
            raise ContractError(f"指标 {node.attr!r} 不存在（可用: {sorted(base)}）")
        return base[node.attr]
    if isinstance(node, ast.BoolOp):
        values = [bool(_eval(v, context)) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            return not bool(_eval(node.operand, context))
        if isinstance(node.op, ast.USub):
            return -_eval(node.operand, context)
        if isinstance(node.op, ast.UAdd):
            return +_eval(node.operand, context)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_eval(node.left, context), _eval(node.right, context))
    if isinstance(node, ast.Compare):
        left = _eval(node.left, context)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval(comparator, context)
            fn = _CMPOPS.get(type(op))
            if fn is None:
                raise ContractError(f"不允许的比较符: {type(op).__name__}")
            if not fn(left, right):
                return False
            left = right
        return True
    raise ContractError(f"表达式含有不允许的语法: {type(node).__name__}（仅支持数值比较/算术/and/or/not）")


def evaluate_expression(expr: str, context: dict) -> bool:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ContractError(f"决策表达式语法错误: {expr!r}: {exc}") from exc
    return bool(_eval(tree, context))
