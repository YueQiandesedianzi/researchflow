"""积木脚手架：生成、契约校验、冒烟、CLI。"""

import pytest

from researchflow.blocks.scaffold import scaffold, smoke_test
from researchflow.blocks.schema import load_block
from researchflow.errors import ContractError

from conftest import run_cli


def test_scaffold_creates_valid_block(tiny_project):
    result = scaffold(tiny_project, "transform.my_scale", title="我的缩放")
    block = load_block(result["dir"], "project", 3)
    assert block.id == "transform.my_scale"
    assert result["shape"] == "table2table"
    # CLI check 同样通过
    assert run_cli("--json", "blocks", "check", result["dir"]) == 0


def test_scaffold_rejects_bad_id_and_duplicate(tiny_project):
    with pytest.raises(ContractError):
        scaffold(tiny_project, "Bad ID")
    scaffold(tiny_project, "transform.dup")
    with pytest.raises(ContractError):
        scaffold(tiny_project, "transform.dup")
    # --force 覆盖则放行
    scaffold(tiny_project, "transform.dup", force=True)


def test_scaffold_unknown_category_rejected(tiny_project):
    with pytest.raises(ContractError) as exc:
        scaffold(tiny_project, "zzz.custom")
    assert "category" in exc.value.message


def test_smoke_transform_runs_for_real(tiny_project):
    scaffold(tiny_project, "transform.passthru")
    result = smoke_test(tiny_project, "transform.passthru")
    assert result.get("ok") is True, result
    assert result["results"]["new-01"][0] == "ran"


def test_smoke_skips_non_table_input(tiny_project):
    scaffold(tiny_project, "data_split.holdout")
    result = smoke_test(tiny_project, "data_split.holdout")
    # split 形状有 table dataset 输入 → 应真实运行而非跳过
    assert result.get("ok") is True, result


def test_cli_blocks_new_with_smoke(tiny_project, capsys):
    code = run_cli("--json", "-C", tiny_project, "blocks", "new",
                   "transform.cli_demo", "--smoke")
    assert code == 0
    out = capsys.readouterr().out
    import json
    payload = json.loads(out[out.index("{"):])
    assert payload["ok"] is True
    assert payload["smoke"]["ok"] is True
    # 接入发现：项目级积木出现在 blocks list
    code = run_cli("--json", "-C", tiny_project, "blocks", "list")
    out = capsys.readouterr().out
    payload = json.loads(out[out.index("{"):])
    ids = [b["id"] for b in payload["blocks"]]
    assert "transform.cli_demo" in ids
