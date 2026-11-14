# 07 — 外部审查响应（R1–R8 修复记录）

对应审查：[researchflow-review-evidence/审查报告.md](https://github.com/YueQiandesedianzi/researchflow)（2026-11-14，固定 d95acb6）。
三批修复均带回归测试（`tests/test_trust*.py`，12 项）与独立提交。

## 逐条对照

| # | 问题 | 修复 | 提交 | 回归测试 |
| --- | --- | --- | --- | --- |
| R1 | 数据/配置内容变化不进指纹 | block.yaml 新增 `file_params` 显式文件依赖；内容哈希进入新鲜度、缓存键、resolved.yaml、run.json，并快照进 Run 目录。改内容 → 相关节点重算；无关分支保持 fresh | `7b9fdcb` | `test_trust.py::test_r1_*` |
| R2 | 历史 PASS 放行本轮 | 门禁控制边与数据边统一参与失败/挂起传播，标签继承阻塞因子语义（awaiting/skipped(decision)/skipped） | `7b9fdcb` | `test_trust.py::test_r2_*` |
| R3 | 人工审批未绑定证据 | decisions 增加 `evidence` 列（schema v2 迁移）；内容寻址摘要绑定上游指标+判据+配置；变化→重新挂起，无变化（含缓存回放）不重审 | `7b9fdcb` | `test_trust.py::test_r3_*` |
| R4 | 零比较也 verified | verify 产物级比对：metrics 容差、table/indices/json 按 sha256、figure/model 仅存在性；无可比项一律 **unverifiable**；环境锁定失败入 warnings | `91b2a0a` | `test_trust2.py::test_r4_*` |
| R5 | README 先写"已通过" | README 后置到 verify 之后，如实反映状态；新增机器可读 **VERIFY.json** | `91b2a0a` | `test_trust2.py::test_r4r5_*` |
| R6 | fresh 不校验自身产物 | `_is_fresh` 复用前校验该 Run 全部产物存在且哈希一致；`doctor --deep` 全量校验（历史篡改持续如实报告） | `7b9fdcb` | `test_trust.py::test_r6_*` |
| R7 | 目标列可混入特征 | fit 前强制拒绝 target∈features、特征重复、非数值目标；data.clean 新增可选 `train_indices`，fill_mean 仅用训练集统计量，缺失时警告泄漏 | `91b2a0a` | `test_trust2.py::test_r7_*` |
| R8 | mark_interrupted 误标活运行 | 项目级执行器互斥锁（pid + 活性检测，`PROCESS_QUERY_LIMITED_INFORMATION` + STILL_ACTIVE）；活持有者→明确拒绝，陈锁→自动回收；互斥保护下 running 必为真中断 | 本批 | `test_trust3.py` |

## 附带修复

- **CI**：Windows 中文编码（cli 重配 UTF-8 + `PYTHONIOENCODING`），矩阵扩到 win/ubuntu × py3.10/3.12/3.13（`e9d58a8`、本批）。
- **工作台路由边界**：Origin 同源校验（写操作 403 外源）、`allowedRoots` 项目根约束（默认空=本地信任，本机配置为 E:\开发）、请求体 1MB 上限、`--yes` 改为按请求显式传入（页面复选框，默认不批）。
- **`rf blocks new` 脚手架**（V1.1，审查前已完成，`eabd3f2`）。

## 采纳为后续路线的架构建议（未在本轮实施）

- 统一不可变 RunSpec（一次解决多处指纹分叉）——R1/R3 已先行落地其文件依赖与证据部分；
- EvaluationProtocol（数据版本+划分摘要+指标定义的可比性协议）；
- ProjectService/RunService 公开服务层（替代 MCP 对 CLI 私有 `_DISPATCH` 的复用）；
- 工作台增量读取与图表懒加载（当前 8s 全量轮询，节点多时再起 Python 有开销）；
- 内容寻址存储 + 引用计数 GC（替代逐 Run 复制产物）。

这些将进入 V1.2+ 计划，见 [06-mvp-plan.md](06-mvp-plan.md) 后续修订。

## 验证基线

- 全套 **112 项测试**通过（Win/Py3.13 本地；CI 覆盖 win/ubuntu × py3.10/3.12/3.13）；
- 工作台路由实测：外源 Origin 403、越根项目 403、无 Origin 本地调用 200；
- 审查探针场景逐项复现为自动化回归（篡改、泄漏、旁路、零比较、双进程语义）。
