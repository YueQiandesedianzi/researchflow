# rf 命令面与约定

所有命令支持 `--json`（有界 JSON 到 stdout，大结果给路径）与
`-C <目录>`（指定项目，默认当前目录向上查找 researchflow.yaml）。
`--json` / `-C` 放在子命令前后均可。

退出码：**0** 成功｜**1** 未分类错误｜**2** 契约/校验失败（执行前被拒绝）｜
**3** 运行失败（含验证门禁未过）｜**4** 等待人工审批/决策。

| 命令 | 作用 | 关键参数 |
| --- | --- | --- |
| `rf init [path]` | 初始化标准项目（幂等，不覆盖已有文件） | `--template tabular\|timeseries`、`--force` |
| `rf doctor` | 一致性检查：计划契约、产物完整性、孤儿目录、滞留 running | — |
| `rf blocks list` | 列出全部可用积木（内置/积木包/项目级） | — |
| `rf blocks check <dir>` | 校验单个积木目录的契约 | — |
| `rf plan validate` | 校验工作树：结构、无环、积木引用、参数、端口类型 | — |
| `rf plan show` | 输出 Mermaid 流程图（带运行状态着色） | `--format mermaid\|json` |
| `rf run <node>` | 运行节点，自动补跑未完成的上游 | `--no-cache`、`--yes` |
| `rf run --all` | 运行整棵树 | `--yes` |
| `rf status` | 工作树节点状态（planned/validated/failed/awaiting…） | — |
| `rf runs list` | 最近运行记录 | `--node <id>`、`--limit N` |
| `rf runs show <RUN-id>` | 单次运行完整记录（输入/产物哈希、指标、验证、环境） | — |
| `rf decide <node>` | 确认决策节点 | `--pass` 或 `--fail`、`--comment` |
| `rf compare <sel>...` | 指标对照表（sel = RUN-id 或节点 id） | `--baseline <sel>`、`--format md\|csv\|json` |
| `rf export` | 导出复现包（产物+配置+积木源码+环境+PROVENANCE） | `--nodes a,b`、`--out <dir>`、`--verify`、`--no-upstream` |
| `rf report` | 生成单文件 HTML 实验工作台（实验树/指标/图表/决策） | `--out <path>` |

## 典型流程

```sh
rf init --template tabular && rf plan validate
rf run --all --yes            # 退出码 4 → 有决策待确认
rf decide gate-01 --pass --comment "数据量充足"
rf run --all --yes            # 继续
rf compare eval-ridge-01 eval-rf-01 --baseline eval-ridge-01
rf export --nodes eval-rf-01 --out dist/main --verify
```

## 运行语义（重要）

- **新鲜度**：输入哈希未变的节点自动复用上次的 validated Run，不重跑。
- **缓存**：确定性积木按 sha256(源码+参数+输入) 命中内容寻址缓存。
- **验证门禁**：积木声明的验证器（如 no_group_overlap）失败 →
  节点 `failed_validation`，下游自动阻断；修复后重跑即可。
- **中断恢复**：进程被杀后再次 `rf run`，过期 running 自动标记 interrupted 并续跑。
