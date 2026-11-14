"""Project Manager：项目上下文、rf init、rf doctor。"""

from __future__ import annotations

from pathlib import Path

from researchflow.errors import ProjectNotFoundError
from researchflow.util import atomic_write_text, dump_yaml, load_yaml

CONFIG_NAME = "researchflow.yaml"
TEMPLATE_DIR = Path(__file__).parent / "templates"


class Project:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.config = load_yaml(self.root / CONFIG_NAME) or {}
        self.rf_dir = self.root / ".researchflow"

    @property
    def name(self) -> str:
        return self.config.get("name", self.root.name)

    @classmethod
    def find_root(cls, start) -> Path:
        start = Path(start).resolve()
        for cand in [start, *start.parents]:
            if (cand / CONFIG_NAME).is_file():
                return cand
        raise ProjectNotFoundError(
            f"未在 {start} 及其上级找到 {CONFIG_NAME}。先运行 rf init，或用 -C 指定项目目录。")

    @classmethod
    def open(cls, start) -> "Project":
        return cls(cls.find_root(start))

    @classmethod
    def init(cls, path, template: str | None = None, force: bool = False) -> dict:
        """生成标准项目结构。幂等：已存在文件默认跳过。"""
        root = Path(path).resolve()
        root.mkdir(parents=True, exist_ok=True)
        created, skipped = [], []

        def put(rel: str, content: str):
            dest = root / rel
            if dest.exists() and not force:
                skipped.append(rel)
                return
            atomic_write_text(dest, content)
            created.append(rel)

        name = root.name
        put(CONFIG_NAME, dump_yaml({
            "schema_version": 1, "name": name, "seed": 42, "data_version": "v1",
        }))
        if template:
            tpl = (TEMPLATE_DIR / f"plan.{template}.yaml").read_text(encoding="utf-8")
            put("plan.yaml", tpl.replace("__PROJECT__", name))
            put("configs/ridge.yaml", (TEMPLATE_DIR / "config.ridge.yaml").read_text(encoding="utf-8"))
        else:
            put("plan.yaml", (TEMPLATE_DIR / "plan.empty.yaml").read_text(encoding="utf-8")
                .replace("__PROJECT__", name))
        agents = (TEMPLATE_DIR / "AGENTS.md.tmpl").read_text(encoding="utf-8")
        put("AGENTS.md", agents.replace("__PROJECT__", name))
        put(".gitignore", ".researchflow/cache/\n__pycache__/\n*.tmp\n")
        for d in ("blocks", "configs", "data", ".researchflow"):
            (root / d).mkdir(parents=True, exist_ok=True)
        return {"root": str(root), "created": created, "skipped": skipped}


def doctor(project: Project) -> dict:
    """一致性检查（只读）：计划契约、Registry 与文件对照、孤儿产物。"""
    from researchflow.blocks.contract import check_plan_contracts
    from researchflow.blocks.loader import discover
    from researchflow.plan.model import load_plan
    from researchflow.registry.artifacts import verify_ref
    from researchflow.registry.store import Store

    report = {"ok": True, "checks": []}

    def check(name, ok, detail=""):
        report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok:
            report["ok"] = False

    try:
        plan = load_plan(project.root / "plan.yaml")
        index = discover(project.root)
        check_plan_contracts(plan, index)
        check("plan", True, f"{len(plan.nodes)} 个节点，{len(index.blocks)} 种积木可用")
        if index.warnings:
            check("blocks.warnings", True, "；".join(index.warnings))
    except Exception as exc:
        check("plan", False, str(exc))

    store = Store.open(project.rf_dir)
    try:
        runs = store.runs(limit=100000)
        by_status: dict = {}
        for r in runs:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        check("runs", True, f"{len(runs)} 次运行 {by_status}")
        running = by_status.get("running", 0)
        if running:
            check("runs.stale", False,
                  f"{running} 个运行停留在 running 状态（下次 rf run 会自动标记 interrupted）")

        bad, checked = [], 0
        for r in runs[:200]:
            for a in store.artifacts_of(r["run_id"]):
                checked += 1
                ok, detail = verify_ref(project.root,
                                        {"path": a["path"], "sha256": a["sha256"]},
                                        check_hash=False)
                if not ok:
                    bad.append(detail)
        check("artifacts", not bad, f"抽查 {checked} 个产物" + (f"，{len(bad)} 个缺失" if bad else "，无缺失"))
        if bad:
            report["checks"].append({"name": "artifacts.missing", "ok": False,
                                     "detail": bad[:10]})

        run_dirs = {p.name for p in (project.rf_dir / "runs").glob("RUN-*") if p.is_dir()}
        known = {r["run_id"] for r in runs}
        orphans = sorted(run_dirs - known)
        check("orphans", not orphans,
              f"{len(orphans)} 个孤儿 Run 目录" + (f": {orphans[:5]}" if orphans else ""))
    finally:
        store.close()
    return report
