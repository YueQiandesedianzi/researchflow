"""MCP server 测试：工具分发单元测试 + stdio 协议级集成测试。"""

import json
import queue
import subprocess
import sys
import threading

import pytest

from researchflow.mcp.server import _invoke

mcp = pytest.importorskip("mcp", reason="可选依赖 mcp 未安装")

from conftest import run_cli  # noqa: F401  （确保 tiny_project 有运行记录用例复用）


def test_invoke_status(tiny_project):
    result = _invoke("status", project=str(tiny_project))
    assert result["ok"] is True
    assert result["status"]["load-01"] == "planned"


def test_invoke_error_payload(tiny_project):
    result = _invoke("compare", project=str(tiny_project),
                     selectors=["no-such-node"], baseline=None, format="json")
    assert result["ok"] is False
    assert result["exit_code"] == 2
    assert result["error"]


class _Stdio:
    def __init__(self, proc):
        self.proc = proc
        self.q: queue.Queue = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        threading.Thread(target=lambda: proc.stderr.read(), daemon=True).start()

    def _pump(self):
        for line in self.proc.stdout:
            self.q.put(line)

    def send(self, msg):
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def read_until_id(self, rid, timeout=60):
        while True:
            line = self.q.get(timeout=timeout)
            msg = json.loads(line)
            if msg.get("id") == rid:
                return msg


@pytest.mark.slow
def test_stdio_handshake_and_tool_call(tiny_project):
    """完整 MCP 握手 + tools/list + tools/call（与 Codex .mcp.json 同一入口）。"""
    proc = subprocess.Popen(
        [sys.executable, "-m", "researchflow.mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8")
    try:
        io = _Stdio(proc)
        io.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "0"}}})
        init_resp = io.read_until_id(1)
        assert init_resp["result"]["serverInfo"]["name"] == "researchflow"
        io.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        io.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = io.read_until_id(2)["result"]["tools"]
        names = sorted(t["name"] for t in tools)
        assert names == sorted([
            "researchflow_init", "researchflow_plan", "researchflow_run",
            "researchflow_status", "researchflow_runs", "researchflow_compare",
            "researchflow_decide", "researchflow_export", "researchflow_report",
        ])

        io.send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "researchflow_status", "arguments": {"project": str(tiny_project)}}})
        result = io.read_until_id(3)["result"]
        payload = result.get("structuredContent")
        if payload is None:
            payload = json.loads(result["content"][0]["text"])
        assert payload["ok"] is True
        assert payload["status"]["eval-01"] == "planned"
    finally:
        proc.terminate()
