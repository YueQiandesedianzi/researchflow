# 04 — 实验工作树、Run 记录与持久化方案

版本：v0.1-draft｜日期：2026-11-13

## 1. 工作树模型（Plan）

工作树是**有向无环图（DAG）**：节点 = 执行节点或决策节点；边 = 数据依赖
（由输入绑定隐式定义，不单独声明）。树状"分支"是 DAG 的视图：从同一划分节点
分出多个模型分支，在比较/决策节点汇合。

### 1.1 `plan.yaml` 顶层结构

```yaml
schema_version: 1
project: teng-conductivity        # 与 researchflow.yaml 一致
meta:
  created_by: agent|human
  updated: 2026-11-13T22:00:00+08:00

nodes:
  # —— 执行节点 ——
  - id: load-01
    kind: execution
    block: io.load_csv@^0.1.0
    params: {path: data/raw/conductivity.csv, target: sigma}
    title: 载入原始数据

  - id: clean-01
    kind: execution
    block: data.clean@^0.1.0
    params: {drop_duplicates: true, na_strategy: drop_rows}
    inputs:
      dataset: {from: load-01.outputs.table}

  - id: split-01
    kind: execution
    block: split.group_holdout@^0.1.0
    params: {group_column: composition, test_size: 0.2, seed: 42}
    inputs:
      dataset: {from: clean-01.outputs.table}

  - id: model-ridge-01
    kind: execution
    block: model.train_sklearn@^0.1.0
    params: {config: configs/ridge.yaml}
    inputs:
      dataset: {from: clean-01.outputs.table}
      train_indices: {from: split-01.outputs.train_indices}

  - id: model-rf-01
    kind: execution
    block: model.train_sklearn@^0.1.0
    params: {config: configs/random_forest.yaml}
    inputs:
      dataset: {from: clean-01.outputs.table}
      train_indices: {from: split-01.outputs.train_indices}

  - id: eval-rf-01
    kind: execution
    block: eval.regression_metrics@^0.1.0
    inputs:
      predictions: {from: model-rf-01.outputs.predictions}
    params: {metrics: [rmse, mae, r2]}

  # —— 决策节点 ——
  - id: gate-beat-baseline
    kind: decision
    title: RF 是否显著优于 Ridge 基线？
    inputs:
      candidate: {from: eval-rf-01.outputs.metrics}
      baseline:  {from: eval-ridge-01.outputs.metrics}
    criteria:
      mode: auto                 # auto | manual | auto_then_manual
      expression: "candidate.rmse <= baseline.rmse * 0.95"
    on_pass: [export-main]       # 通过才允许运行的下游
    on_fail: []
```

### 1.2 节点字段规范

公共：`id`（唯一，`[a-z0-9-]+`）、`kind`、`title`、可选 `tags`、`notes`（研究意图留痕）。

执行节点：`block`（`id@版本范围`）、`params`、`inputs`（端口 → `{from: 节点.outputs.端口}`，
或 `{value: 字面量}` 用于纯参数化来源）、可选 `runs_hint`。

决策节点：`inputs`（至少 candidate，可多个）、`criteria`、
`on_pass` / `on_fail`（下游节点 id 列表）。判据模式：

| mode | 语义 |
| --- | --- |
| `auto` | Runner 求值表达式，结果与依据写入 `decisions` 表 |
| `manual` | 挂起；`rf decide <node> --pass/--fail --comment "..."` 确认 |
| `auto_then_manual` | 自动判据先给建议，人工确认后生效（默认推荐） |

表达式求值：受限上下文（只有输入 metrics 的键与数值比较/算术），
禁用任意函数调用；实现用 AST 白名单解析，不用 `eval`。

### 1.3 节点状态机

状态**不存在 plan.yaml**，由 Registry 按该节点最新 Run + 决策记录推导：

```text
planned → running → completed → validated
                  ↘ failed           ↘ failed_validation（验证未过，阻断下游）
        （决策节点）→ awaiting_decision → passed | rejected
```

`rf status` 渲染：`[✓] split-01  [✗] model-rf-01(validation)  [?] gate-beat-baseline(待决策)`。

## 2. 项目目录布局

```text
<project>/
├── researchflow.yaml          # 项目配置：name、data_version、默认 seed、时区
├── plan.yaml                  # 实验工作树（人/Agent 共同编辑）
├── AGENTS.md                  # rf init 生成的工作规范
├── configs/                   # 模型/积木配置文件（配置驱动）
├── blocks/                    # 项目级自定义积木
├── data/                      # 原始与中间数据（用户管理，rf 只读 raw）
└── .researchflow/
    ├── registry.sqlite        # 实验索引（只增不改）
    ├── lock                   # 单写者锁（fcntl/portalocker）
    ├── cache/<content-hash>/  # 确定性积木的内容寻址缓存
    └── runs/RUN-000021/
        ├── run.json           # Run 记录（见第 3 节）
        ├── resolved.yaml      # 解析冻结后的完整配置快照
        ├── artifacts/         # 产物：predictions.csv、metrics.json、parity.png…
        ├── validation.json    # 验证报告
        └── logs/stdout.log
```

原则：`runs/` 与 `cache/` 由 rf 独占写入；其余目录用户可自由管理。

## 3. Run 记录（`run.json`）

```json
{
  "run_id": "RUN-000021",
  "node_id": "model-rf-01",
  "plan_digest": "sha256:…",
  "block": {"id": "model.train_sklearn", "version": "0.1.0",
            "source_sha256": "…"},
  "params_sha256": "…",
  "inputs": {"dataset": {"type": "table", "path": "…", "sha256": "…"},
             "train_indices": {"type": "indices", "path": "…", "sha256": "…"}},
  "code": {"git_commit": "a1b2c3d", "git_dirty": false},
  "env": {"python": "3.12.4", "platform": "win32",
          "packages_digest": "sha256:…(pip freeze 规范化)"},
  "status": "validated",
  "started_at": "…", "finished_at": "…", "duration_s": 12.4,
  "artifacts": {"model": {"path": "artifacts/model.pkl", "sha256": "…"},
                "predictions": {"path": "artifacts/predictions.csv", "sha256": "…"}},
  "metrics": {},
  "validations": [{"name": "file_exists", "passed": true, "detail": ""}],
  "cache": {"hit": false, "source_run": null},
  "error": null
}
```

- `run_id`：`RUN-` + SQLite 自增序号（%06d），项目内唯一、人类可读。
- **追溯链**：`inputs[*].sha256` 指向上游 Run 的产物哈希 → 沿链可回到
  `io.load_csv` 登记的原始数据哈希；配合 `code.git_commit` 与 `block.source_sha256`
  构成完整 PROVENANCE。
- `plan_digest`：执行时 plan.yaml 的哈希，用于检测"运行后计划被改"。

## 4. SQLite 索引（`registry.sqlite`）

```sql
CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);

CREATE TABLE runs (
  run_id        TEXT PRIMARY KEY,          -- RUN-000021
  seq           INTEGER UNIQUE,            -- 自增序号
  node_id       TEXT NOT NULL,
  block_id      TEXT NOT NULL,
  block_version TEXT NOT NULL,
  status        TEXT NOT NULL,             -- running/completed/failed/failed_validation
  cache_key     TEXT,                      -- 确定性积木的内容寻址键
  started_at    TEXT, finished_at TEXT,
  run_json      TEXT NOT NULL              -- run.json 全文（查询免读盘）
);
CREATE INDEX idx_runs_node ON runs(node_id);
CREATE INDEX idx_runs_cache ON runs(cache_key);

CREATE TABLE artifacts (
  id INTEGER PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES runs(run_id),
  port TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, type TEXT NOT NULL
);
CREATE INDEX idx_artifacts_hash ON artifacts(sha256);

CREATE TABLE metrics (
  run_id TEXT NOT NULL REFERENCES runs(run_id),
  name TEXT NOT NULL, value REAL NOT NULL,
  PRIMARY KEY (run_id, name)
);

CREATE TABLE validations (
  id INTEGER PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES runs(run_id),
  name TEXT NOT NULL, passed INTEGER NOT NULL, detail TEXT
);

CREATE TABLE decisions (
  id INTEGER PRIMARY KEY,
  node_id TEXT NOT NULL,
  mode TEXT NOT NULL,               -- auto / manual / auto_then_manual
  expression TEXT, auto_result INTEGER,
  final_result INTEGER NOT NULL,    -- 1 pass / 0 fail
  actor TEXT NOT NULL,              -- human:<name> | auto
  comment TEXT, decided_at TEXT NOT NULL
);

CREATE TABLE exports (
  id INTEGER PRIMARY KEY,
  out_dir TEXT NOT NULL, nodes TEXT NOT NULL,   -- JSON 数组
  verified INTEGER NOT NULL, created_at TEXT NOT NULL
);
```

写入经 `lock` 文件单写者序列化；读取走 WAL 模式支持并发查询。
所有表**只 INSERT**（除 `runs.status` 在运行期的一次状态推进），历史不可改写。

## 5. 缓存与重跑

- `cache_key = sha256(block源码 + 规范化params + 各输入ArtifactRef.sha256)`，
  仅 `deterministic: true` 的积木计算。
- 命中：不执行，直接登记一条 `cache.hit=true, source_run=…` 的新 Run 记录
  （产物硬链接自 cache，保持 D2 不可变语义）。
- `rf run --no-cache` 强制重跑；`rf run --resume` 从中断节点继续
  （已完成且 validated 的节点复用，其余重跑）。

## 6. 复现与导出验证

`rf export --verify` 在导出目录内：重建积木源码快照 + `resolved.yaml` →
重跑关键节点 → 比对 `metrics` 容差（默认相对 1e-6）与原 Run 记录 →
通过才生成 `PROVENANCE.json` 终稿并封包。失败则导出标记
`verified=0` 并输出差异清单。
