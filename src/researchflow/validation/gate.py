"""Validation Gate：运行后对产物执行积木声明的验证器。"""

from __future__ import annotations

import importlib.util
import traceback

from researchflow.blocks.validators import BUILTIN_VALIDATORS, Finding, ValidatorContext
from researchflow.errors import ContractError


def _load_custom_validate(block):
    validate_py = block.dir / "validate.py"
    if not validate_py.is_file():
        return None
    spec = importlib.util.spec_from_file_location(f"rf_validate_{block.id}", validate_py)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, "validate", None)
    if not callable(fn):
        raise ContractError(f"积木 {block.id} 的 validate.py 未导出 validate()")
    return fn


def run_gate(block, ctx: ValidatorContext) -> list:
    """执行积木声明的全部验证器 + 可选 custom 钩子，返回 Finding 列表。"""
    findings: list[Finding] = []
    for entry in block.validation:
        if isinstance(entry, str):
            name, spec = entry, {}
        elif isinstance(entry, dict) and len(entry) == 1:
            (name, spec), = entry.items()
        else:
            findings.append(Finding(str(entry), False, "validation 条目格式错误"))
            continue
        fn = BUILTIN_VALIDATORS.get(name)
        if fn is None:
            raise ContractError(
                f"积木 {block.id} 声明了未知内置验证器 {name!r}；"
                f"可用: {sorted(BUILTIN_VALIDATORS)}（自定义逻辑请用 validate.py）"
            )
        try:
            findings.append(fn(ctx, spec or {}))
        except Exception as exc:
            findings.append(Finding(name, False, f"验证器异常: {exc}"))

    custom = _load_custom_validate(block)
    if custom is not None:
        try:
            results = custom(inputs=ctx.inputs, outputs=ctx.outputs, params=ctx.params,
                             log=lambda m: None)
            for item in results or []:
                findings.append(Finding(
                    str(item.get("name", "custom")),
                    bool(item.get("passed")),
                    str(item.get("detail", "")),
                ))
        except Exception:
            findings.append(Finding("custom", False,
                                    f"custom validate 异常: {traceback.format_exc(limit=3)}"))
    return findings
