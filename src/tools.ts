/**
 * 模型工具：把「数据探查 / L1~L5 分析 / 工程化 / 查询 / 读报告」变成 agent 可调用的能力。
 *
 * 工具与浏览器面板共用同一份 `src/data` 资产：脚本、报告、数据库都在工作区里，
 * 因此 agent 执行一次分析与用户在面板里看到的文档始终一致。
 *
 * 安全边界：只运行白名单脚本、只接受只读 SELECT、只读取 `src/data` 下的文档。
 */

import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { readDoc } from './docs/docs.ts'
import { runDatasetQuery } from './data/ecommerce/dataset.ts'
import { resolveWorkspace, venvPaths, venvPythonPath } from './env/probe.ts'

/** 单个工具返回给模型的最大字符数，超出只保留尾部。 */
const MAX_OUTPUT_CHARS = 6000

function text(value: string): Array<{ type: 'text'; text: string }> {
  return [{ type: 'text', text: value }]
}

/** 一个可运行的示例脚本。 */
interface AnalysisScript {
  /** 模型使用的稳定键，例如 `L3-shap`。 */
  key: string
  /** 中文名称。 */
  label: string
  /** 所属层次，用于描述。 */
  group: string
  /** 相对工作区的脚本路径。 */
  script: string
  /** 脚本产出的报告（相对 `src/data`）。 */
  reports: string[]
}

/** 白名单：L1~L5 与工程化的全部脚本。 */
export const ANALYSIS_SCRIPTS: AnalysisScript[] = [
  { key: 'L1-eda', label: '描述性主报告', group: 'L1', script: 'src/data/L1/generate_report.py', reports: ['L1/eda_report.md'] },
  { key: 'L1-cross', label: '多维交叉分析', group: 'L1', script: 'src/data/L1/l1_cross_analysis.py', reports: ['L1/cross_report.md'] },
  { key: 'L1-geo', label: '地理空间描述', group: 'L1', script: 'src/data/L1/l1_geo_analysis.py', reports: ['L1/geo_report.md'] },
  { key: 'L1-text', label: '文本数据描述', group: 'L1', script: 'src/data/L1/l1_text_analysis.py', reports: ['L1/text_report.md'] },
  { key: 'L2-diagnostic', label: '诊断性主报告', group: 'L2', script: 'src/data/L2/generate_diagnostic_report.py', reports: ['L2/diagnostic_report.md'] },
  { key: 'L2-causal', label: '因果推断', group: 'L2', script: 'src/data/L2/l2_causal.py', reports: ['L2/causal_report.md'] },
  { key: 'L2-granger', label: 'Granger 因果', group: 'L2', script: 'src/data/L2/l2_granger.py', reports: ['L2/granger_report.md'] },
  { key: 'L2-anomaly', label: '异常检测', group: 'L2', script: 'src/data/L2/l2_anomaly.py', reports: ['L2/anomaly_report.md'] },
  { key: 'L2-clustering', label: '客户聚类', group: 'L2', script: 'src/data/L2/l2_clustering.py', reports: ['L2/clustering_report.md'] },
  { key: 'L2-sequence', label: '序列模式挖掘', group: 'L2', script: 'src/data/L2/l2_sequence.py', reports: ['L2/sequence_report.md'] },
  { key: 'L3-predictive', label: '预测性主报告', group: 'L3', script: 'src/data/L3/generate_predictive_report.py', reports: ['L3/predictive_report.md'] },
  { key: 'L3-ensemble', label: '集成学习', group: 'L3', script: 'src/data/L3/l3_ensemble.py', reports: ['L3/ensemble_report.md'] },
  { key: 'L3-multistep', label: '多步预测', group: 'L3', script: 'src/data/L3/l3_multistep.py', reports: ['L3/multistep_report.md'] },
  { key: 'L3-quantile', label: '分位数区间', group: 'L3', script: 'src/data/L3/l3_quantile.py', reports: ['L3/quantile_report.md'] },
  { key: 'L3-transfer', label: '迁移学习', group: 'L3', script: 'src/data/L3/l3_transfer.py', reports: ['L3/transfer_report.md'] },
  { key: 'L3-shap', label: 'SHAP 可解释性', group: 'L3', script: 'src/data/L3/l3_shap.py', reports: ['L3/shap_report.md'] },
  { key: 'L4-prescriptive', label: '规范性主报告', group: 'L4', script: 'src/data/L4/generate_prescriptive_report.py', reports: ['L4/prescriptive_report.md'] },
  { key: 'L4-dqn', label: 'DQN 库存补货', group: 'L4', script: 'src/data/L4/l4_dqn.py', reports: ['L4/dqn_report.md'] },
  { key: 'L4-bandit', label: '上下文赌博机', group: 'L4', script: 'src/data/L4/l4_bandit.py', reports: ['L4/bandit_report.md'] },
  { key: 'L4-multiobjective', label: '多目标折扣', group: 'L4', script: 'src/data/L4/l4_multiobjective.py', reports: ['L4/multiobjective_report.md'] },
  { key: 'L4-causal-rec', label: '因果推荐去偏', group: 'L4', script: 'src/data/L4/l4_causal_rec.py', reports: ['L4/causal_rec_report.md'] },
  { key: 'L5-continual', label: '持续学习', group: 'L5', script: 'src/data/L5/l5_continual.py', reports: ['L5/continual_report.md'] },
  { key: 'L5-meta', label: '元学习', group: 'L5', script: 'src/data/L5/l5_meta.py', reports: ['L5/meta_report.md'] },
  { key: 'L5-multimodal', label: '多模态融合', group: 'L5', script: 'src/data/L5/l5_multimodal.py', reports: ['L5/multimodal_report.md'] },
  { key: 'ENG-distributed', label: '分布式计算', group: '工程化', script: 'src/data/engineering/eng_distributed.py', reports: ['engineering/distributed_report.md'] },
  { key: 'ENG-ab', label: 'A/B 测试框架', group: '工程化', script: 'src/data/engineering/eng_ab_test.py', reports: ['engineering/ab_test_report.md'] },
  { key: 'ENG-quality', label: '数据质量监控', group: '工程化', script: 'src/data/engineering/eng_data_quality.py', reports: ['engineering/data_quality_report.md'] },
]

/** 优先用工作区 `.venv` 的解释器，没有时退回 PATH 里的 python。 */
function resolvePython(): string {
  const { venvPath } = venvPaths(resolveWorkspace())
  const python = venvPythonPath(venvPath)
  return existsSync(python) ? python : 'python'
}

/** 执行 Python 脚本并收集输出；超时则终止进程。 */
async function runPython(
  args: string[],
  timeoutMs: number,
): Promise<{ code: number | null; output: string; timedOut: boolean }> {
  const workspace = resolveWorkspace()
  const python = resolvePython()
  return await new Promise(resolvePromise => {
    const child = spawn(python, args, {
      cwd: workspace,
      windowsHide: true,
      env: {
        ...process.env,
        PYTHONIOENCODING: 'utf-8',
        PYTHONUNBUFFERED: '1',
      },
    })

    let output = ''
    const append = (chunk: Buffer | string): void => {
      output += String(chunk)
      if (output.length > MAX_OUTPUT_CHARS * 3) output = output.slice(-MAX_OUTPUT_CHARS * 3)
    }

    const timer = setTimeout(() => {
      try {
        child.kill()
      } catch {
        // 进程可能已退出，忽略。
      }
      resolvePromise({ code: null, output, timedOut: true })
    }, timeoutMs)

    child.stdout?.on('data', append)
    child.stderr?.on('data', append)
    child.on('error', failure => {
      clearTimeout(timer)
      resolvePromise({ code: -1, output: `${output}\n${failure.message}`, timedOut: false })
    })
    child.on('close', code => {
      clearTimeout(timer)
      resolvePromise({ code, output, timedOut: false })
    })
  })
}

/** 只保留尾部，避免把整段训练日志塞进上下文。 */
function tail(output: string): string {
  const trimmed = output.trim()
  return trimmed.length <= MAX_OUTPUT_CHARS ? trimmed : `…（前段输出已省略）\n${trimmed.slice(-MAX_OUTPUT_CHARS)}`
}

/** 读取报告的首段摘要（标题 + 前若干行），用于探测结论。 */
async function reportSummary(relative: string): Promise<string> {
  try {
    const doc = await readDoc(relative)
    const lines = doc.markdown.replace(/\r\n/g, '\n').split('\n')
    const picked = lines.filter(line => line.trim() !== '').slice(0, 26)
    return picked.join('\n')
  } catch {
    return ''
  }
}

/** 把结果集渲染成紧凑表格。 */
function renderRows(columns: string[], rows: (string | number | null)[][]): string {
  const shown = rows
    .slice(0, 200)
    .map(row => row.map(cell => (cell === null ? 'NULL' : String(cell))))
  const widths = columns.map((column, index) =>
    Math.min(60, Math.max(column.length, ...shown.map(row => (row[index] ?? '').length))),
  )
  const pad = (value: string, width: number): string =>
    value.length >= width ? value : value + ' '.repeat(width - value.length)
  const line = (values: string[]): string =>
    values.map((value, index) => pad((value ?? '').slice(0, 60), widths[index] ?? 0)).join(' | ')

  return [
    line(columns),
    widths.map(width => '-'.repeat(width)).join('-+-'),
    ...shown.map(line),
    rows.length > shown.length ? `… 其余 ${rows.length - shown.length} 行已省略` : '',
  ]
    .filter(lineText => lineText !== '')
    .join('\n')
}

/** 构建全部工具；由 index.ts 交给 `tools.register`。 */
export function makeTools(defineTool: (definition: unknown) => unknown): unknown[] {
  return [
    defineTool({
      name: 'ds_run_analysis',
      description:
        '运行本项目的数据科学示例脚本并返回执行结果与报告摘要。覆盖 L1 描述性、L2 诊断性、L3 预测性、L4 规范性、L5 认知性与工程化主题。' +
        '当用户说「跑一下某个分析 / 重新生成某个报告 / 做 L3 的 SHAP / 做持续学习」时使用。' +
        `可用 analysis：${ANALYSIS_SCRIPTS.map(item => `${item.key}（${item.label}）`).join('、')}。`,
      parameters: {
        analysis: { type: 'string', required: true, description: '脚本键，例如 L2-causal、L3-shap、L4-dqn、L5-meta、ENG-ab。' },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: false,
          properties: {
            status: { type: 'string', required: true },
            analysis: { type: 'string', required: true },
            durationMs: { type: 'integer', required: true },
            output: { type: 'string', required: true },
            reports: { type: 'array', items: { type: 'string' }, required: true },
            summary: { type: 'string', required: true },
          },
        },
        render: (_args: unknown, value: { status?: string; summary?: string; output?: string; reports?: string[] }) =>
          text(
            `[${value.status ?? 'unknown'}] 报告：${(value.reports ?? []).join('、')}\n\n${value.summary ?? ''}\n\n--- 执行输出（尾部） ---\n${value.output ?? ''}`,
          ),
      },
      async execute(args: { analysis?: unknown }) {
        const key = typeof args.analysis === 'string' ? args.analysis.trim() : ''
        const spec = ANALYSIS_SCRIPTS.find(item => item.key.toLowerCase() === key.toLowerCase())
        if (spec === undefined) {
          throw new Error(
            `未知的分析脚本「${key}」，可用：${ANALYSIS_SCRIPTS.map(item => item.key).join('、')}`,
          )
        }
        const started = Date.now()
        const result = await runPython([spec.script], 30 * 60 * 1000)
        const status = result.timedOut ? 'timeout' : result.code === 0 ? 'ok' : 'failed'
        const summary = await reportSummary(spec.reports[0] ?? '')
        return {
          status,
          analysis: spec.key,
          durationMs: Date.now() - started,
          output: tail(result.output),
          reports: spec.reports,
          summary,
        }
      },
    }),

    defineTool({
      name: 'ds_profiling',
      description:
        '对指定 SQLite 数据库执行数据探查（结构、缺失、一致性、分布、就绪度），生成 Markdown 报告与图表，并返回结论摘要。' +
        '当用户说「对某个数据做探查 / 数据体检 / 数据质量初筛」时使用。默认探查项目的电商数据库。',
      parameters: {
        database: {
          type: 'string',
          description: 'SQLite 数据库路径（相对工作区），默认 src/data/ecommerce/ecommerce.db。',
        },
        tables: {
          type: 'string',
          description: '逗号分隔的表名，默认探查全部业务表。',
        },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: false,
          properties: {
            status: { type: 'string', required: true },
            database: { type: 'string', required: true },
            reportPath: { type: 'string', required: true },
            summary: { type: 'string', required: true },
            output: { type: 'string', required: true },
            durationMs: { type: 'integer', required: true },
          },
        },
        render: (_args: unknown, value: { status?: string; reportPath?: string; summary?: string; output?: string }) =>
          text(
            `[${value.status ?? 'unknown'}] 探查报告：${value.reportPath ?? ''}\n\n${value.summary ?? ''}\n\n--- 执行输出（尾部） ---\n${value.output ?? ''}`,
          ),
      },
      async execute(args: { database?: unknown; tables?: unknown }) {
        const database =
          typeof args.database === 'string' && args.database.trim() !== ''
            ? args.database.trim()
            : 'src/data/ecommerce/ecommerce.db'
        const scriptArgs = ['src/data/profiling/data_profiling_report.py', '--db', database]
        if (typeof args.tables === 'string' && args.tables.trim() !== '') {
          scriptArgs.push('--tables', args.tables.trim())
        }
        const started = Date.now()
        const result = await runPython(scriptArgs, 25 * 60 * 1000)
        const summary = await reportSummary('profiling/data_profiling_report.md')
        return {
          status: result.timedOut ? 'timeout' : result.code === 0 ? 'ok' : 'failed',
          database,
          reportPath: 'src/data/profiling/data_profiling_report.md',
          summary,
          output: tail(result.output),
          durationMs: Date.now() - started,
        }
      },
    }),

    defineTool({
      name: 'ds_query',
      description:
        '对电商示例库执行一条只读 SQL（select / with），返回结果表。用于核对口径、验证假设、取样本数据。',
      parameters: {
        sql: { type: 'string', required: true, description: '单条只读 SQL，例如 select * from orders limit 100。' },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: false,
          properties: {
            rendered: { type: 'string', required: true },
            rowCount: { type: 'integer', required: true },
            truncated: { type: 'boolean', required: true },
          },
        },
        render: (_args: unknown, value: { rendered?: string }) => text(value.rendered ?? ''),
      },
      async execute(args: { sql?: unknown }) {
        const sql = typeof args.sql === 'string' ? args.sql : ''
        if (sql.trim() === '') throw new Error('缺少 SQL 语句')
        const result = await runDatasetQuery(sql)
        return {
          rendered: renderRows(result.columns, result.rows),
          rowCount: result.rowCount,
          truncated: result.truncated,
        }
      },
    }),

    defineTool({
      name: 'ds_read_report',
      description:
        '读取 `src/data` 下的分析报告或方法论文档（Markdown），返回正文。' +
        '当用户想查看已生成的报告、想要某层的方法说明、或需要引用报告里的数字时使用。',
      parameters: {
        path: {
          type: 'string',
          required: true,
          description:
            '相对 src/data 的路径，例如 profiling/data_profiling_report.md、L3/predictive_report.md、README.md。',
        },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: false,
          properties: {
            path: { type: 'string', required: true },
            title: { type: 'string', required: true },
            content: { type: 'string', required: true },
            truncated: { type: 'boolean', required: true },
          },
        },
        render: (_args: unknown, value: { path?: string; title?: string; content?: string }) =>
          text(`# ${value.title ?? ''}\n路径：src/data/${value.path ?? ''}\n\n${value.content ?? ''}`),
      },
      async execute(args: { path?: unknown }) {
        const target = typeof args.path === 'string' ? args.path.trim() : ''
        if (target === '') throw new Error('缺少文档路径')
        const doc = await readDoc(target)
        const limit = 12000
        const truncated = doc.markdown.length > limit
        return {
          path: doc.path,
          title: doc.title,
          content: truncated ? `${doc.markdown.slice(0, limit)}\n\n…（正文超过 ${limit} 字符，已截断）` : doc.markdown,
          truncated,
        }
      },
    }),

    defineTool({
      name: 'ds_list_analyses',
      description:
        '列出本项目可运行的全部分析脚本（L1~L5 与工程化）及其产出的报告文件。用于在不确定脚本键时先查看清单。',
      parameters: {},
      output: {
        schema: {
          type: 'object',
          additionalProperties: false,
          properties: { rendered: { type: 'string', required: true } },
        },
        render: (_args: unknown, value: { rendered?: string }) => text(value.rendered ?? ''),
      },
      async execute() {
        const rendered = ANALYSIS_SCRIPTS.map(
          item => `${item.key} | ${item.group} | ${item.label} | 脚本 ${item.script} | 报告 ${item.reports.join('、')}`,
        ).join('\n')
        return { rendered: `${ANALYSIS_SCRIPTS.length} 个分析脚本：\n${rendered}` }
      },
    }),
  ]
}

/** 给模型的系统提示公告：什么时候用这些工具。 */
export function toolGuidance(): string {
  return (
    '本机已安装 dsh-datascience-demo 插件（数据科学示例）：侧边栏「示例数据 → 数据科学」可阅读分析框架与 L1~L5 报告。' +
    '能力：ds_query 只读查询电商库、ds_profiling 生成数据探查报告、ds_run_analysis 运行 L1~L5/工程化脚本、ds_read_report 读取报告正文、ds_list_analyses 查看脚本清单。' +
    '当用户说「对某数据做探查」「做 L1~L5 分析」「跑某个分析/生成某份报告」「看看报告」时，优先调用这些工具，而不是自己去猜脚本路径。' +
    '工作区和脚本路径以工具返回为准；重新生成报告后，面板中对应文档会同步更新。'
  )
}

/** 供 index.ts 判断工作区是否就绪（仅供调试与提示）。 */
export function workspaceScriptExists(script: string): boolean {
  return existsSync(join(resolveWorkspace(), script))
}
