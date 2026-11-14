"""决策表达式白名单。"""

import pytest

from researchflow.errors import ContractError
from researchflow.plan.decisions import evaluate_expression

CTX = {"candidate": {"rmse": 0.5, "r2": 0.9}, "baseline": {"rmse": 1.0}}


@pytest.mark.parametrize("expr,expected", [
    ("candidate.rmse <= baseline.rmse * 0.95", True),
    ("candidate.rmse < 0.4", False),
    ("candidate.r2 > 0.8 and baseline.rmse > 0.5", True),
    ("candidate.r2 > 0.95 or candidate.rmse < 1", True),
    ("not (candidate.rmse > 1)", True),
    ("candidate.rmse * 2 == baseline.rmse", True),
    ("(candidate.rmse - baseline.rmse) < 0", True),
])
def test_valid_expressions(expr, expected):
    assert evaluate_expression(expr, CTX) is expected


@pytest.mark.parametrize("expr", [
    "__import__('os').system('dir')",
    "open('secret.txt').read()",
    "candidate.rmse.__class__",
    "unknown.rmse < 1",
    "candidate.nope < 1",
    "[x for x in candidate]",
    "candidate['rmse'] < 1",     # 下标访问不在白名单
    "abs(candidate.rmse) < 1",   # 函数调用不在白名单
])
def test_forbidden_or_unknown_rejected(expr):
    with pytest.raises(ContractError):
        evaluate_expression(expr, CTX)
