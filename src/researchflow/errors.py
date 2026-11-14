"""统一异常与退出码约定。

退出码（CLI 与适配器共用约定）：
- 0 成功
- 1 未分类错误
- 2 契约 / 计划 / 配置校验失败（执行前拒绝）
- 3 运行失败（含验证门禁未过）
- 4 需要人工审批 / 决策挂起
"""


class RFError(Exception):
    exit_code = 1

    def __init__(self, message, details=None):
        super().__init__(message)
        self.message = message
        self.details = details or []


class ContractError(RFError):
    """积木清单、参数、接线等契约问题。"""

    exit_code = 2


class PlanError(ContractError):
    """plan.yaml 结构或引用问题。"""


class ProjectNotFoundError(RFError):
    exit_code = 2


class RunFailedError(RFError):
    """积木执行失败或验证门禁未过。"""

    exit_code = 3


class ApprovalNeeded(RFError):
    """需要人工审批或决策确认，当前挂起。"""

    exit_code = 4
