"""Experiment Runner：按工作树拓扑执行节点。

职责：新鲜度判断（输入未变则复用）、内容寻址缓存、requires_approval 审批、
子进程隔离执行、验证门禁、决策节点求值、中断恢复（过期 running → interrupted）。
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

from researchflow import __version__
from researchflow.blocks.contract import check_params, check_plan_contracts
from researchflow.blocks.loader import block_source_hash, discover
from researchflow.blocks.validators import ValidatorContext
from researchflow.errors import ApprovalNeeded, ContractError, RunFailedError
from researchflow.plan.decisions import evaluate_expression
from researchflow.plan.engine import ancestors, dependencies, gate_edges, topo_order
from researchflow.plan.model import load_plan, parse_binding
from researchflow.registry.artifacts import abs_path, make_ref, register_artifact, verify_ref
from researchflow.registry.store import Store
from researchflow.runner import cache as cache_mod
from researchflow.util import (dump_yaml, now_iso, read_json, sha256_json,
                               atomic_write_text, write_json_atomic)
from researchflow.validation.gate import run_gate


class DecisionSkipped(Exception):
    """决策结果使该分支被有意跳过（非错误，不影响退出码）。"""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class Executor:
    def __init__(self, project, quiet: bool = False):
        self.project = project
        self.store = Store.open(project.rf_dir)
        self.index = discover(project.root)
        self.plan = load_plan(project.root / "plan.yaml")
        check_plan_contracts(self.plan, self.index)
        self.quiet = quiet
        self.results: dict = {}
        self._git_info = None
        self._env_info = None

    def emit(self, msg):
        if not self.quiet:
            print(msg, flush=True)

    def _finalize(self, run_id, run_dir, status, run_json):
        """run.json 落盘 + Registry 更新（两个持久面同步）。"""
        write_json_atomic(Path(run_dir) / "run.json", run_json)
        self.store.finish_run(run_id, status, run_json)

    def close(self):
        self.store.close()

    # ---------- 环境指纹 ----------

    def _git(self):
        if self._git_info is None:
            info = {"git_commit": None, "git_dirty": None}
            try:
                commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.project.root,
                                        capture_output=True, text=True, encoding="utf-8",
                                        errors="replace", timeout=10)
                if commit.returncode == 0:
                    info["git_commit"] = commit.stdout.strip()
                    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=self.project.root,
                                           capture_output=True, text=True, encoding="utf-8",
                                           errors="replace", timeout=10)
                    info["git_dirty"] = bool(dirty.stdout.strip())
            except Exception:
                pass
            self._git_info = info
        return self._git_info

    def _env(self):
        if self._env_info is None:
            digest = None
            try:
                freeze = subprocess.run([sys.executable, "-m", "pip", "freeze", "--quiet"],
                                        capture_output=True, text=True, encoding="utf-8",
                                        errors="replace", timeout=60)
                if freeze.returncode == 0:
                    lines = sorted(freeze.stdout.lower().split())
                    digest = hashlib.sha256("\n".join(lines).encode()).hexdigest()
            except Exception:
                pass
            self._env_info = {
                "python": platform.python_version(), "platform": sys.platform,
                "packages_digest": digest, "core_version": __version__,
            }
        return self._env_info

    # ---------- 主入口 ----------

    def run(self, target: str | None = None, run_all: bool = False,
            no_cache: bool = False, yes: bool = False) -> int:
        interrupted = self.store.mark_interrupted()
        if interrupted:
            self.emit(f"⚠ 发现 {interrupted} 个中断的运行，已标记 interrupted")
        order = topo_order(self.plan)
        if target:
            self.plan.get(target)  # 存在性检查
            wanted = ancestors(self.plan, target)
            order = [nid for nid in order if nid in wanted]
        skipped: set = set()
        exit_code = 0
        for nid in order:
            node = self.plan.get(nid)
            if dependencies(node) & skipped:
                skipped.add(nid)
                self.results[nid] = "skipped"
                continue
            try:
                self.results[nid] = self._run_node(node, no_cache=no_cache, yes=yes)
            except DecisionSkipped as exc:
                skipped.add(nid)
                self.results[nid] = "skipped(decision)"
                self.emit(f"↷ {nid}: {exc.message}")
            except ApprovalNeeded as exc:
                skipped.add(nid)
                self.results[nid] = "awaiting"
                self.emit(f"⏸ {nid}: {exc.message}")
                exit_code = max(exit_code, 4)
            except RunFailedError as exc:
                skipped.add(nid)
                self.results[nid] = "failed"
                self.emit(f"✗ {nid}: {exc.message}")
                for d in exc.details:
                    for line in str(d).splitlines()[-8:]:
                        self.emit(f"    {line}")
                exit_code = 3
                if not run_all:
                    raise
        return exit_code

    def _run_node(self, node, no_cache=False, yes=False):
        if node.kind == "decision":
            return self._run_decision(node, yes=yes)
        return self._run_execution(node, no_cache=no_cache, yes=yes)

    # ---------- 执行节点 ----------

    def _check_gates(self, node):
        for dec_id, expect in gate_edges(self.plan).get(node.id, []):
            dec = self.store.latest_decision(dec_id)
            if dec is None:
                raise ApprovalNeeded(
                    f"决策节点 {dec_id} 未决，先执行: rf decide {dec_id} --pass/--fail")
            if expect == "pass" and not dec["final_result"]:
                raise DecisionSkipped(f"决策 {dec_id} 未通过，on_pass 分支不执行")
            if expect == "fail" and dec["final_result"]:
                raise DecisionSkipped(f"决策 {dec_id} 已通过，on_fail 分支不执行")

    def _resolve_upstream_ref(self, up_id, up_port, consumer: str) -> dict:
        up_run = self.store.latest_run(up_id, ("validated",))
        if up_run is None:
            raise RunFailedError(
                f"上游节点 {up_id} 没有已验证（validated）的运行，无法为 {consumer} 提供输入")
        rows = self.store.artifacts_of(up_run["run_id"])
        row = next((r for r in rows if r["port"] == up_port), None)
        if row is None:
            raise RunFailedError(f"上游运行 {up_run['run_id']} 缺少端口 {up_port} 的产物")
        ref = {"type": row["type"], "path": row["path"], "sha256": row["sha256"]}
        ok, detail = verify_ref(self.project.root, ref)
        if not ok:
            raise RunFailedError(f"输入产物校验失败: {detail}")
        return ref

    def _resolve_inputs(self, node, block) -> dict:
        refs = {}
        for port in block.inputs:
            binding = node.inputs.get(port)
            if binding is None:
                continue
            if "value" in binding:
                refs[port] = {"type": block.inputs[port]["type"], "path": None,
                              "sha256": sha256_json(binding["value"]), "_value": binding["value"]}
            else:
                up_id, up_port = parse_binding(binding["from"])
                refs[port] = self._resolve_upstream_ref(up_id, up_port, node.id)
        return refs

    def _is_fresh(self, node, block, params, source_hash, input_refs):
        latest = self.store.latest_run(node.id, ("validated",))
        if latest is None:
            return None
        rj = json.loads(latest["run_json"])
        if rj.get("block", {}).get("version") != block.version_str:
            return None
        if rj.get("block", {}).get("source_sha256") != source_hash:
            return None
        if rj.get("params_sha256") != sha256_json(params):
            return None
        old_inputs = rj.get("inputs", {})
        if set(old_inputs) != set(input_refs):
            return None
        for port, ref in input_refs.items():
            if old_inputs.get(port, {}).get("sha256") != ref["sha256"]:
                return None
        return latest

    def _run_execution(self, node, no_cache=False, yes=False):
        block = self.index.resolve(node.block)
        params = check_params(block.params_schema, node.params, where=f"节点 {node.id} 参数")
        source_hash = block_source_hash(block)
        self._check_gates(node)

        if block.requires_approval and not yes:
            if sys.stdin.isatty():
                ans = input(f"⚠ 积木 {block.ref} 声明 requires_approval，节点 {node.id} 待执行。"
                            f"继续？[y/N] ")
                if ans.strip().lower() not in ("y", "yes"):
                    raise ApprovalNeeded(f"用户未批准节点 {node.id}")
            else:
                raise ApprovalNeeded(f"积木 {block.ref} 需要人工审批（非交互环境请加 --yes）")

        expected_inputs = self._resolve_inputs(node, block)

        if not no_cache:
            latest = self._is_fresh(node, block, params, source_hash, expected_inputs)
            if latest is not None:
                self.emit(f"= {node.id}: 输入未变，复用 {latest['run_id']}")
                return ("fresh", latest["run_id"])

        cache_key = None
        if block.deterministic:
            cache_key = cache_mod.make_cache_key(source_hash, params, expected_inputs)
            if not no_cache:
                hit = self.store.find_cache(cache_key)
                if hit is not None:
                    run_id = self._replay_cache(node, block, params, source_hash,
                                                expected_inputs, cache_key, hit)
                    if run_id is not None:
                        self.emit(f"≡ {node.id}: 缓存命中（源 {hit['run_id']}）→ {run_id}")
                        return ("cache", run_id)
        return self._execute(node, block, params, source_hash, expected_inputs, cache_key)

    def _replay_cache(self, node, block, params, source_hash, input_refs, cache_key, hit):
        run_id = self.store.create_run(node.id, block.id, block.version_str, cache_key)
        run_dir = self.project.rf_dir / "runs" / run_id
        artifacts_dir = run_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        copied = cache_mod.replay_from_cache(self.project.rf_dir, cache_key, artifacts_dir,
                                             self.project.root)
        if copied is None:
            # 缓存损坏：放弃这次 run 记录，回退真实执行
            self.store.finish_run(run_id, "interrupted", {"error": "cache corrupted, rerun"})
            return None
        started = now_iso()
        t0 = time.monotonic()
        artifacts = {}
        for port, spec in block.outputs.items():
            artifacts[port] = register_artifact(self.store, run_id, port, copied[port],
                                                spec["type"], self.project.root)
        metrics = self._load_metrics(block, artifacts)
        self.store.add_metrics(run_id, metrics)
        validations = [{"name": "cache_replay", "passed": True,
                        "detail": f"复用 {hit['run_id']} 的已验证产物"}]
        self.store.add_validation(run_id, "cache_replay", True, f"源运行 {hit['run_id']}")
        write_json_atomic(run_dir / "validation.json", validations)
        run_json = self._build_run_json(run_id, node, block, params, source_hash, input_refs,
                                        artifacts, metrics, validations, "validated", started,
                                        t0, cache_key, None,
                                        cache_info={"hit": True, "source_run": hit["run_id"]})
        self._finalize(run_id, run_dir, "validated", run_json)
        return run_id

    def _execute(self, node, block, params, source_hash, input_refs, cache_key):
        run_id = self.store.create_run(node.id, block.id, block.version_str, cache_key)
        run_dir = self.project.rf_dir / "runs" / run_id
        artifacts_dir, logs_dir = run_dir / "artifacts", run_dir / "logs"
        inputs_dir = run_dir / "inputs"
        for d in (artifacts_dir, logs_dir, inputs_dir):
            d.mkdir(parents=True, exist_ok=True)
        started = now_iso()
        t0 = time.monotonic()
        status, error, details = "failed", None, []
        artifacts, metrics, validations = {}, {}, []
        try:
            input_refs = self._materialize_values(input_refs, inputs_dir)
            self._write_resolved(run_dir, node, block, params, source_hash, input_refs)
            result = self._spawn(block, input_refs, params, run_dir, artifacts_dir, logs_dir)
            outputs = result.get("outputs", {})
            missing = [p for p in block.outputs if p not in outputs]
            if missing:
                raise RunFailedError(f"积木未返回输出端口: {missing}（已返回: {sorted(outputs)}）")
            for port, spec in block.outputs.items():
                f = artifacts_dir / outputs[port]
                if not f.is_file():
                    raise RunFailedError(f"积木未产出文件 {outputs[port]!r}（端口 {port}）")
                artifacts[port] = register_artifact(self.store, run_id, port, f,
                                                    spec["type"], self.project.root)
            metrics = self._load_metrics(block, artifacts)
            self.store.add_metrics(run_id, metrics)

            ctx = ValidatorContext(
                inputs=self._abs_refs(input_refs), outputs=self._abs_refs(artifacts),
                params=params, run_dir=run_dir, project_root=self.project.root, block=block)
            findings = run_gate(block, ctx)
            validations = [{"name": f.name, "passed": f.passed, "detail": f.detail}
                           for f in findings]
            write_json_atomic(run_dir / "validation.json", validations)
            for f in findings:
                self.store.add_validation(run_id, f.name, f.passed, f.detail)
            if all(f.passed for f in findings):
                status = "validated"
                if cache_key:
                    try:
                        cache_mod.store_to_cache(self.project.rf_dir, cache_key, artifacts,
                                                 self.project.root)
                    except Exception as exc:
                        self.emit(f"  （缓存写入失败，忽略: {exc}）")
            else:
                status = "failed_validation"
                error = "验证门禁未通过"
                details = [f"{f.name}: {f.detail}" for f in findings if not f.passed]
        except RunFailedError as exc:
            error, details = exc.message, list(exc.details)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

        run_json = self._build_run_json(run_id, node, block, params, source_hash, input_refs,
                                        artifacts, metrics, validations, status, started, t0,
                                        cache_key, error)
        self._finalize(run_id, run_dir, status, run_json)
        if status == "validated":
            self.emit(f"✓ {node.id}: {run_id} validated（{time.monotonic() - t0:.1f}s）")
            return ("ran", run_id)
        raise RunFailedError(f"节点 {node.id} 运行失败（{run_id}，{status}）: {error}",
                             details=details)

    # ---------- 子进程 ----------

    def _materialize_values(self, input_refs, inputs_dir):
        final = {}
        for port, ref in input_refs.items():
            if "_value" in ref:
                f = Path(inputs_dir) / f"{port}.json"
                write_json_atomic(f, ref["_value"])
                final[port] = make_ref(f, ref["type"], self.project.root)
            else:
                final[port] = ref
        return final

    def _spawn(self, block, input_refs, params, run_dir, artifacts_dir, logs_dir):
        job = {
            "block_dir": str(block.dir),
            "entry": f"{block.entry_module}:{block.entry_func}",
            "inputs": {p: {"type": r["type"], "path": str(abs_path(self.project.root, r)),
                           "sha256": r["sha256"]}
                       for p, r in input_refs.items()},
            "params": params,
            "out_dir": str(artifacts_dir),
            "project_root": str(self.project.root),
            "result_file": str(Path(logs_dir) / "result.json"),
        }
        job_path = Path(logs_dir) / "job.json"
        write_json_atomic(job_path, job)
        env = dict(os.environ, MPLBACKEND="Agg", PYTHONIOENCODING="utf-8")
        stdout_path, stderr_path = Path(logs_dir) / "stdout.log", Path(logs_dir) / "stderr.log"
        with open(stdout_path, "w", encoding="utf-8") as so, \
                open(stderr_path, "w", encoding="utf-8") as se:
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "researchflow.runner.child", str(job_path)],
                    cwd=str(self.project.root), env=env, stdout=so, stderr=se,
                    timeout=block.timeout_seconds)
            except subprocess.TimeoutExpired:
                raise RunFailedError(f"执行超时（>{block.timeout_seconds}s），已终止子进程")
        result_path = Path(job["result_file"])
        if not result_path.is_file():
            raise RunFailedError("积木子进程未写回结果文件")
        result = read_json(result_path)
        if proc.returncode != 0 or not result.get("ok"):
            tail = ""
            if stderr_path.is_file():
                tail = stderr_path.read_text(encoding="utf-8", errors="replace")[-1500:]
            raise RunFailedError("积木执行失败（详见 logs/stderr.log）",
                                 details=[result.get("error", tail)])
        return result

    # ---------- 决策节点 ----------

    def _decision_context(self, node) -> dict:
        context = {}
        for port, binding in (node.inputs or {}).items():
            if not (isinstance(binding, dict) and "from" in binding):
                continue
            up_id, _ = parse_binding(binding["from"])
            up_run = self.store.latest_run(up_id, ("validated",))
            if up_run is None:
                raise RunFailedError(f"决策输入 {port} 的上游 {up_id} 没有已验证的运行")
            context[port] = self.store.metrics_of(up_run["run_id"])
        return context

    def _run_decision(self, node, yes=False):
        criteria = node.criteria or {}
        mode = criteria.get("mode")
        expression = criteria.get("expression")
        context = self._decision_context(node)
        auto_result = evaluate_expression(expression, context) if expression else None
        if mode == "auto":
            self.store.add_decision(node.id, mode, expression, auto_result,
                                    bool(auto_result), actor="auto")
            self.emit(f"{'✓' if auto_result else '✗'} 决策 {node.id}: "
                      f"{'PASS' if auto_result else 'FAIL'}（{expression}）")
            return ("decided", bool(auto_result))
        # manual / auto_then_manual：已有生效决策则沿用，不重复询问
        existing = self.store.latest_decision(node.id)
        if existing is not None:
            return ("decided", bool(existing["final_result"]))
        suggestion = ""
        if mode == "auto_then_manual" and auto_result is not None:
            suggestion = f"；自动判据建议 {'PASS' if auto_result else 'FAIL'}（{expression}）"
        raise ApprovalNeeded(
            f"决策节点 {node.id}（{node.title or '未命名'}）需要人工确认: "
            f"rf decide {node.id} --pass/--fail{suggestion}")

    def decide(self, node_id, passed: bool, comment=None) -> dict:
        node = self.plan.get(node_id)
        if node.kind != "decision":
            raise ContractError(f"节点 {node_id} 不是决策节点")
        criteria = node.criteria or {}
        expression = criteria.get("expression")
        auto_result = None
        if expression:
            try:
                auto_result = evaluate_expression(expression, self._decision_context(node))
            except Exception:
                auto_result = None
        actor = f"human:{getpass.getuser()}"
        self.store.add_decision(node_id, criteria.get("mode", "manual"), expression,
                                auto_result, passed, actor=actor, comment=comment)
        return {"node_id": node_id, "final": bool(passed),
                "auto_suggestion": auto_result, "actor": actor}

    # ---------- 状态 ----------

    def status(self) -> dict:
        runs_map = self.store.node_status_map()
        states = {}
        for n in self.plan.nodes:
            if n.kind == "decision":
                dec = self.store.latest_decision(n.id)
                if dec is None:
                    states[n.id] = "awaiting"
                else:
                    states[n.id] = "passed" if dec["final_result"] else "rejected"
            else:
                states[n.id] = runs_map.get(n.id, "planned")
        return states

    # ---------- 记录组装 ----------

    def _abs_refs(self, refs):
        from researchflow.blocks.api import Ref
        return {p: Ref(path=abs_path(self.project.root, r), type=r["type"],
                       sha256=r["sha256"]) for p, r in refs.items()}

    def _load_metrics(self, block, artifacts) -> dict:
        flat = {}
        for port, spec in block.outputs.items():
            if spec["type"] == "metrics" and port in artifacts:
                try:
                    data = read_json(abs_path(self.project.root, artifacts[port]))
                    if isinstance(data, dict):
                        flat.update(data)
                except Exception:
                    pass
        return flat

    def _write_resolved(self, run_dir, node, block, params, source_hash, input_refs):
        resolved = {
            "run_node": node.id,
            "block": {"id": block.id, "version": block.version_str,
                      "source_sha256": source_hash, "source": block.source},
            "params": params,
            "inputs": {p: {k: v for k, v in r.items() if not k.startswith("_")}
                       for p, r in input_refs.items()},
            "plan_digest": self.plan.digest(),
            "resolved_at": now_iso(),
        }
        atomic_write_text(Path(run_dir) / "resolved.yaml", dump_yaml(resolved))

    def _build_run_json(self, run_id, node, block, params, source_hash, input_refs,
                        artifacts, metrics, validations, status, started, t0,
                        cache_key, error, cache_info=None):
        return {
            "run_id": run_id,
            "node_id": node.id,
            "plan_digest": self.plan.digest(),
            "block": {"id": block.id, "version": block.version_str,
                      "source_sha256": source_hash},
            "params": params,
            "params_sha256": sha256_json(params),
            "inputs": {p: {k: v for k, v in r.items() if not k.startswith("_")}
                       for p, r in input_refs.items()},
            "code": self._git(),
            "env": self._env(),
            "status": status,
            "started_at": started,
            "finished_at": now_iso(),
            "duration_s": round(time.monotonic() - t0, 3),
            "artifacts": {p: r for p, r in artifacts.items()},
            "metrics": metrics,
            "validations": validations,
            "cache": cache_info or {"hit": False, "source_run": None},
            "cache_key": cache_key,
            "error": error,
        }
