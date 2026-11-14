"""平台适配器测试：Codex Skill 结构 + 模拟 walkthrough。"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).parent.parent
SKILL_DIR = REPO / "adapters" / "codex" / "skill" / "researchflow"


def test_skill_structure():
    skill_md = SKILL_DIR / "SKILL.md"
    assert skill_md.is_file()
    text = skill_md.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "SKILL.md 缺少 frontmatter"
    fm = yaml.safe_load(m.group(1))
    assert fm["name"] == "researchflow"
    assert fm.get("description"), "description 兼作路由触发器，必填"
    assert len(fm["description"]) <= 1024
    # 渐进披露：SKILL.md 引用的 references 必须存在
    for ref in re.findall(r"references/([\w.-]+\.md)", text):
        assert (SKILL_DIR / "references" / ref).is_file(), f"缺少 references/{ref}"


def test_skill_commands_exist():
    """SKILL.md 中出现的 rf 子命令必须都在 CLI 里。"""
    from researchflow.cli import build_parser

    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    text += (SKILL_DIR / "references" / "commands.md").read_text(encoding="utf-8")
    used = set(re.findall(r"rf ([a-z][a-z0-9-]*)", text))
    parser = build_parser()
    sub_action = next(a for a in parser._actions if a.dest == "command")
    available = set(sub_action.choices)
    missing = used - available
    assert not missing, f"SKILL 提到但 CLI 没有的命令: {missing}"


def test_catalog_blocks_resolvable():
    """block-catalog.md 列出的 16 个积木均可解析。"""
    from researchflow.blocks.loader import discover

    text = (SKILL_DIR / "references" / "block-catalog.md").read_text(encoding="utf-8")
    ids = sorted(set(re.findall(r"`((?:io|data|split|features|model|eval|plot)\.[\w]+)`", text)))
    assert len(ids) == 16, ids
    index = discover(load_entry_points=True)
    for bid in ids:
        assert index.resolve(bid).id == bid


def test_dsh_adapter_bundle_static():
    """DSH bundle 静态契约：清单、patch、无 Config 导出、图标与语言资源。"""
    import json

    bundle = REPO / "adapters" / "dsh" / "researchflow-dsh"
    pkg = json.loads((bundle / "package.json").read_text(encoding="utf-8"))
    assert pkg["dsh"]["bundle"]["patch"] == "./cordis.patch.yml"
    assert "./locale/*.json" in pkg["exports"] and "./icon" in pkg["exports"]
    patch = yaml.safe_load((bundle / "cordis.patch.yml").read_text(encoding="utf-8"))
    rows = patch[0]["insert"]
    assert rows[0]["id"] == "researchflow"
    assert rows[0]["name"] == pkg["name"]
    index_js = (bundle / "index.js").read_text(encoding="utf-8")
    assert "export function apply" in index_js
    assert "export const Config" not in index_js  # 激活器要求 schemastery，见源码注释
    assert "export const inject" in index_js
    for locale in ("en.json", "zh.json"):
        meta = json.loads((bundle / "locale" / locale).read_text(encoding="utf-8"))
        assert meta["meta"]["title"] and meta["meta"]["description"]
    icon = (bundle / "icon.svg").read_text(encoding="utf-8")
    assert icon.strip().startswith("<svg") and len(icon.encode()) < 256 * 1024


def test_codex_plugin_bundle_static():
    """V0.4 Codex Plugin 打包契约。"""
    import json

    plugin = REPO / "adapters" / "codex" / "plugin"
    manifest = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "researchflow"
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./.mcp.json"
    mcp_conf = json.loads((plugin / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp_conf["researchflow"]["args"] == ["-m", "researchflow.mcp"]
    assert (plugin / "skills" / "researchflow" / "SKILL.md").is_file()

    marketplace = json.loads(
        (REPO / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
    entry = marketplace["plugins"][0]
    assert entry["source"]["type"] == "git-subdir"
    assert entry["source"]["path"] == "adapters/codex/plugin"
    assert entry["policy"]["installation"] in ("AVAILABLE", "INSTALLED_BY_DEFAULT")


def test_plugin_skill_in_sync():
    """plugin/skills 是 adapters/codex/skill 的同步副本（防止漂移）。"""
    import filecmp

    src = REPO / "adapters" / "codex" / "skill" / "researchflow"
    dst = REPO / "adapters" / "codex" / "plugin" / "skills" / "researchflow"
    cmp = filecmp.dircmp(src, dst)
    assert not cmp.left_only and not cmp.right_only and not cmp.diff_files, \
        f"skill 副本与源不一致: {cmp.left_only} {cmp.right_only} {cmp.diff_files}"
    for sub in cmp.subdirs.values():
        assert not sub.left_only and not sub.right_only and not sub.diff_files


def test_codex_skill_walkthrough(tmp_path):
    """模拟 Codex Agent 仅凭 SKILL.md 快速上手段落完成全流程。

    对应验收：在 Codex 会话中凭 SKILL.md 完成 demo 全流程（V0.2 的代理验证）。
    """
    proj = tmp_path / "walkthrough"
    proj.mkdir()
    # 用户数据就位（SKILL.md: 把数据放入 data/）
    (proj / "data").mkdir()
    shutil.copy(REPO / "examples" / "demo-b-timeseries" / "data" / "series.csv",
                proj / "data" / "series.csv")

    def rf(*args, expect=0):
        proc = subprocess.run(
            [sys.executable, "-m", "researchflow", "--json", *args],
            cwd=proj, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=1800)
        assert proc.returncode == expect, \
            f"rf {' '.join(args)} → {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
        return json.loads(proc.stdout)

    # SKILL.md 快速上手序列
    rf("init", "--template", "timeseries")
    assert rf("plan", "validate")["ok"] is True
    assert rf("run", "--all", "--yes")["ok"] is True
    status = rf("status")["status"]
    assert status["eval-01"] == "validated", status
    cmp_data = rf("compare", "eval-01", "--format", "json")
    assert cmp_data["rows"][0]["metrics"]["rmse"] > 0
    assert rf("report")["ok"] is True
    assert (proj / "report.html").is_file()
