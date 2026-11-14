// ResearchFlow DSH 适配器（V0.3）
// 薄适配层：把 rf CLI 的能力注册为 Agent Tools 与 /researchflow 命令。
// 核心逻辑全部在 ResearchFlow Core（Python），本插件只做进程调用与结果转发。
import { execFile } from 'node:child_process'

export const inject = ['tools', 'commands']

// 注：不导出 Config——零依赖 JS bundle 无法可靠引入 schemastery，
// 而激活器要求 Config 带 .validate()。可调项经 cordis.patch.yml 的 config 传入，
// 运行时默认值见 apply() 内的 cfg。

function rf(config, project, args, timeoutMs) {
  const cliArgs = ['-m', 'researchflow', '--json']
  if (project) cliArgs.push('-C', project)
  cliArgs.push(...args)
  return new Promise((resolve) => {
    execFile(config.pythonPath || 'python', cliArgs, {
      timeout: timeoutMs || 2 * 60 * 1000,
      maxBuffer: 32 * 1024 * 1024,
      windowsHide: true,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    }, (error, stdout, stderr) => {
      if (stdout) {
        try {
          resolve(JSON.parse(stdout))
          return
        } catch { /* fallthrough */ }
      }
      resolve({
        ok: false,
        error: error ? String(error.message || error) : 'rf CLI 未返回 JSON',
        stderr: String(stderr || '').slice(-2000) || undefined,
        stdout: String(stdout || '').slice(-2000) || undefined,
      })
    })
  })
}

const asText = (value) => [{ type: 'text', text: typeof value === 'string' ? value : JSON.stringify(value, null, 2) }]

function cliTool(config, def) {
  return {
    name: def.name,
    description: def.description,
    parameters: def.parameters,
    timeoutMs: (def.timeoutMinutes ? def.timeoutMinutes(config) : 2) * 60 * 1000,
    output: { schema: { type: 'object' }, render: (_args, value) => asText(value) },
    ...(def.readOnly ? { isConcurrencySafe: () => true } : {}),
    async execute(args) {
      const project = args.project || config.defaultProject
      if (def.needsProject !== false && !project) {
        return {
          ok: false,
          error: '缺少 project 参数：请给出 ResearchFlow 项目目录的绝对路径（含 researchflow.yaml）',
        }
      }
      return rf(config, project, def.args(args), (def.timeoutMinutes ? def.timeoutMinutes(config) : 2) * 60 * 1000)
    },
  }
}

const PROJECT_PARAM = {
  type: 'string',
  description: 'ResearchFlow 项目目录绝对路径（含 researchflow.yaml）；留空时用插件配置的 defaultProject',
}

const TOOLS = [
  {
    name: 'researchflow_init',
    description: '初始化标准 ResearchFlow 科研项目（目录、researchflow.yaml、plan.yaml、AGENTS.md）。幂等，不覆盖已有文件。返回生成/跳过的文件清单。',
    needsProject: false,
    parameters: {
      type: 'object',
      required: ['path'],
      properties: {
        path: { type: 'string', description: '项目目录（不存在则创建）' },
        template: { type: 'string', enum: ['tabular', 'timeseries'], description: '可选示例工作树模板' },
      },
    },
    args: (a) => ['init', a.path, ...(a.template ? ['--template', a.template] : [])],
  },
  {
    name: 'researchflow_plan',
    description: '校验或可视化实验工作树。validate 检查结构、无环、积木契约（契约不符退出码 2）；show 返回带运行状态的 Mermaid 图。',
    readOnly: true,
    parameters: {
      type: 'object',
      required: ['action'],
      properties: {
        project: PROJECT_PARAM,
        action: { type: 'string', enum: ['validate', 'show'], description: 'validate 校验；show 输出 Mermaid' },
      },
    },
    args: (a) => ['plan', a.action, '--format', 'json'],
  },
  {
    name: 'researchflow_run',
    description: '运行工作树节点（自动补跑未完成的上游；输入未变的节点自动复用已验证运行）。退出码：0 成功｜2 契约失败（先修 plan）｜3 运行/验证失败（看 runs show 与 logs）｜4 等待人工审批或决策（用 researchflow_decide 处理）。返回各节点结果与 RUN-id。',
    parameters: {
      type: 'object',
      properties: {
        project: PROJECT_PARAM,
        node: { type: 'string', description: '目标节点 id；与 all 二选一' },
        all: { type: 'boolean', description: '运行整棵树' },
        no_cache: { type: 'boolean', description: '禁用新鲜度判断与缓存，强制重跑' },
        yes: { type: 'boolean', description: '自动批准 requires_approval 积木（非交互环境必须）' },
      },
    },
    timeoutMinutes: (c) => c.runTimeoutMinutes || 30,
    args: (a) => ['run', ...(a.node ? [a.node] : []), ...(a.all ? ['--all'] : []),
      ...(a.no_cache ? ['--no-cache'] : []), ...(a.yes ? ['--yes'] : [])],
  },
  {
    name: 'researchflow_status',
    description: '查看工作树每个节点的状态（planned / validated / failed / failed_validation / awaiting / passed / rejected）。',
    readOnly: true,
    parameters: { type: 'object', properties: { project: PROJECT_PARAM } },
    args: () => ['status'],
  },
  {
    name: 'researchflow_runs',
    description: '查询运行记录：list 最近运行，或 show 单次运行的完整记录（输入/产物哈希、指标、验证结果、环境指纹）。',
    readOnly: true,
    parameters: {
      type: 'object',
      properties: {
        project: PROJECT_PARAM,
        run_id: { type: 'string', description: '提供则 show 该运行（如 RUN-000021），否则 list' },
        node: { type: 'string', description: 'list 时按节点过滤' },
        limit: { type: 'integer', description: 'list 条数上限，默认 20' },
      },
    },
    args: (a) => ['runs', a.run_id ? 'show' : 'list', ...(a.run_id ? [a.run_id] : []),
      ...(a.node ? ['--node', a.node] : []), ...(a.limit ? ['--limit', String(a.limit)] : [])],
  },
  {
    name: 'researchflow_compare',
    description: '统一比较多次运行/实验分支的指标，可指定基线输出相对差异。选择器为 RUN-id 或节点 id（取该节点最新已验证运行）。',
    readOnly: true,
    parameters: {
      type: 'object',
      required: ['selectors'],
      properties: {
        project: PROJECT_PARAM,
        selectors: { type: 'array', items: { type: 'string' }, description: 'RUN-id 或节点 id 列表' },
        baseline: { type: 'string', description: '基线选择器，提供则输出 Δ%' },
      },
    },
    args: (a) => ['compare', ...a.selectors, '--format', 'json',
      ...(a.baseline ? ['--baseline', a.baseline] : [])],
  },
  {
    name: 'researchflow_decide',
    description: '确认决策节点（记录决策者、时间与备注；auto_then_manual 模式会附自动判据建议）。决策前其 on_pass 下游被阻断（rf run 退出码 4）。',
    parameters: {
      type: 'object',
      required: ['node', 'pass'],
      properties: {
        project: PROJECT_PARAM,
        node: { type: 'string', description: '决策节点 id' },
        pass: { type: 'boolean', description: 'true 通过，false 驳回' },
        comment: { type: 'string', description: '决策理由（写入决策记录）' },
      },
    },
    args: (a) => ['decide', a.node, a.pass ? '--pass' : '--fail',
      ...(a.comment ? ['--comment', a.comment] : [])],
  },
  {
    name: 'researchflow_export',
    description: '导出研究复现包：选定节点及其上游链的产物、配置、积木源码、环境锁定与 PROVENANCE 证据链。verify 会在导出目录内重跑并比对指标。返回导出目录与验证结果。',
    parameters: {
      type: 'object',
      required: ['nodes', 'out'],
      properties: {
        project: PROJECT_PARAM,
        nodes: { type: 'string', description: '逗号分隔的执行节点 id（如 eval-rf-01,plot-rf-parity）' },
        out: { type: 'string', description: '导出目录（必须为空或不存在）' },
        verify: { type: 'boolean', description: '在导出目录内重跑并比对指标容差' },
      },
    },
    timeoutMinutes: (c) => (c.runTimeoutMinutes || 30) * 2,
    args: (a) => ['export', '--nodes', a.nodes, '--out', a.out, ...(a.verify ? ['--verify'] : [])],
  },
  {
    name: 'researchflow_report',
    description: '生成单文件 HTML 实验工作台（实验树、指标对照、图表、运行与决策记录），离线可开。返回报告文件路径。',
    parameters: {
      type: 'object',
      properties: {
        project: PROJECT_PARAM,
        out: { type: 'string', description: '输出路径（默认 <项目>/report.html）' },
      },
    },
    args: (a) => ['report', ...(a.out ? ['--out', a.out] : [])],
  },
]

function tokenize(input) {
  const out = []
  const re = /"([^"]*)"|(\S+)/g
  let m
  while ((m = re.exec(input)) !== null) out.push(m[1] ?? m[2])
  return out
}

const COMMAND_HELP = [
  '用法: /researchflow <rf 子命令与参数>（项目目录取插件配置 defaultProject）',
  '示例:',
  '  /researchflow status',
  '  /researchflow run --all --yes',
  '  /researchflow compare eval-a eval-b --baseline eval-a',
  '  /researchflow decide gate-01 --pass --comment "数据量充足"',
  '  /researchflow report',
].join('\n')

export function apply(ctx, config) {
  const cfg = { pythonPath: 'python', runTimeoutMinutes: 30, ...(config || {}) }
  const disposers = []

  for (const def of TOOLS) {
    disposers.push(ctx.tools.register(cliTool(cfg, def)))
  }

  disposers.push(ctx.commands.register({
    name: 'researchflow',
    description: 'ResearchFlow 实验工作树（rf CLI 直通；项目目录取插件配置 defaultProject）',
    input: { hint: 'status | run --all --yes | compare ... | decide ... | report' },
    handler: async (invocation) => {
      const args = tokenize(invocation.rawInput || '').filter((a) => a !== '--json')
      if (!args.length) return { kind: 'success', text: COMMAND_HELP }
      if (!cfg.defaultProject) {
        return {
          kind: 'error',
          text: '未配置 defaultProject。请在插件设置中填入 ResearchFlow 项目目录，' +
            '或改用 researchflow_* Agent 工具并显式传 project 参数。',
        }
      }
      const result = await rf(cfg, cfg.defaultProject, args)
      return { kind: result.error ? 'error' : 'success', text: JSON.stringify(result, null, 2) }
    },
  }))

  const cleanup = () => disposers.forEach((dispose) => dispose())
  ctx.effect(() => cleanup)
  return cleanup
}
