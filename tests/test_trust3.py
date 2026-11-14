"""批 3 回归：R8 执行器互斥（同项目并发执行的明确拒绝与陈锁回收）。"""

import json
import subprocess
import sys

import pytest

from researchflow.errors import RunFailedError
from researchflow.project import Project
from researchflow.runner.executor import Executor

from conftest import BASE_PLAN  # noqa: F401  （tiny_project fixture 来自 conftest）


def _lock_path(project):
    return project / ".researchflow" / "locks" / "executor.lock"


def _sleeper():
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


def test_mutex_rejects_second_live_executor(tiny_project, monkeypatch):
    """存活持有者存在时，第二个执行器被明确拒绝且不得抢锁。

    （用 monkeypatch 模拟存活持有者：本测试环境的沙箱会强杀遗留子进程，
    真实双进程语义由 test_stale_lock_reclaimed 的陈锁回收路径互补覆盖。）
    """
    monkeypatch.setattr(Executor, "_pid_alive", staticmethod(lambda pid: True))
    lock = _lock_path(tiny_project)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": 424242, "started_at": "x"}), encoding="utf-8")
    ex = Executor(Project.open(tiny_project), quiet=True)
    try:
        with pytest.raises(RunFailedError) as exc:
            ex.run(run_all=True, yes=True)
        assert "另一个执行器" in exc.value.message
    finally:
        ex.close()
    # 锁属于他人，未被本次释放
    assert lock.is_file()
    lock.unlink()


def test_stale_lock_reclaimed(tiny_project):
    """持有者已死（进程退出）→ 陈锁被回收，运行正常进行。"""
    dead = _sleeper()
    dead_pid = dead.pid
    dead.terminate()
    dead.wait(timeout=10)

    lock = _lock_path(tiny_project)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": dead_pid, "started_at": "x"}), encoding="utf-8")
    ex = Executor(Project.open(tiny_project), quiet=True)
    try:
        code = ex.run(run_all=True, yes=True)
        assert code == 0
    finally:
        ex.close()
    assert not lock.exists()


def test_interrupted_marking_safe_under_mutex(tiny_project):
    """互斥保护下，停留在 running 的记录才被标记 interrupted（模拟真中断）。"""
    from researchflow.registry.store import Store

    store = Store.open(tiny_project / ".researchflow")
    store.create_run("ghost-node", "io.load_csv", "0.1.0")  # 停留在 running
    store.close()

    ex = Executor(Project.open(tiny_project), quiet=True)
    try:
        ex.run(run_all=True, yes=True)
    finally:
        ex.close()
    store = Store.open(tiny_project / ".researchflow")
    assert store.latest_any("ghost-node")["status"] == "interrupted"
    store.close()
