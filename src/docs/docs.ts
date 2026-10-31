/**
 * 数据科学文档（src/data 下的 Markdown 与图表）的只读访问层。
 *
 * 文档全部来自工作区的 `src/data` 目录：README 系列讲方法论，各层目录放
 * 专题报告，`images*` 放图表，`profiling` 下还有独立的 HTML 报告。这里只做两件事——
 * 把文档清单交给界面，把指定路径的 Markdown / 图片 / HTML 内容读出来。
 *
 * 安全约束：路径一律相对 `src/data`，拒绝 `..`、绝对路径与非白名单扩展名，
 * 因此界面无法借此读取工作区其它文件。
 */

import { existsSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import type { DataDocContent, DataDocEntry } from '../protocol.ts'

/** 构建产物在 lib/ 下（向上一级即包根），tsx 直跑源码时在 src/docs/ 下（向上两级）。 */
const DATA_ROOT = ['../src/data', '../../src/data']
  .map(candidate => fileURLToPath(new URL(candidate, import.meta.url)))
  .find(candidate => existsSync(candidate))!

/** 「数据科学」菜单的固定条目，按层次顺序排列。 */
export const DATA_DOCS: DataDocEntry[] = [
  {
    id: 'framework',
    label: '分析框架',
    path: 'README.md',
    summary: '数据科学的五个层次：从看见现象到自主进化',
  },
  { id: 'L1', label: 'L1 描述性分析', path: 'L1/README.md', summary: '用统计与可视化把数据讲清楚' },
  { id: 'L2', label: 'L2 诊断性分析', path: 'L2/README.md', summary: '用相关、因果、异常、聚类、序列找原因' },
  { id: 'L3', label: 'L3 预测性分析', path: 'L3/README.md', summary: '用时序、集成、解释、迁移做预测' },
  { id: 'L4', label: 'L4 规范性分析', path: 'L4/README.md', summary: '用推荐、赌博机、强化学习、多目标做决策' },
  { id: 'L5', label: 'L5 认知性分析', path: 'L5/README.md', summary: '用持续学习、元学习、多模态让系统进化' },
  { id: 'profiling', label: '数据探查报告', path: 'profiling/README.md', summary: '建模前的一次完整体检' },
  { id: 'engineering', label: '数据工程化', path: 'engineering/README.md', summary: '从能跑通到能上线' },
]

const MARKDOWN_EXTENSIONS = new Set(['.md'])
const ASSET_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.html'])

const MIME_BY_EXTENSION: Record<string, string> = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.svg': 'image/svg+xml',
  '.html': 'text/html; charset=utf-8',
}

/** 把相对路径解析到 `src/data` 内的绝对路径；越界或扩展名不允许时返回 null。 */
function resolveInsideData(relative: string): string | null {
  const cleaned = relative.replace(/\\/g, '/').replace(/^\/+/, '')
  if (cleaned === '' || cleaned.includes('\0')) return null
  const segments = cleaned.split('/')
  if (segments.some(segment => segment === '..' || segment === '.')) return null
  const absolute = path.resolve(DATA_ROOT, cleaned)
  const relativeToRoot = path.relative(DATA_ROOT, absolute)
  if (relativeToRoot === '' || relativeToRoot.startsWith('..') || path.isAbsolute(relativeToRoot)) {
    return null
  }
  return absolute
}

/** 读取一篇 Markdown 文档；标题取首个一级标题，取不到时回退到文件名。 */
export async function readDoc(relative: string): Promise<DataDocContent> {
  if (!MARKDOWN_EXTENSIONS.has(path.extname(relative).toLowerCase())) {
    throw new Error('只支持 Markdown 文档')
  }
  const absolute = resolveInsideData(relative)
  if (absolute === null) throw new Error('文档路径不合法')
  if (!existsSync(absolute)) throw new Error('文档不存在')

  const markdown = await readFile(absolute, 'utf8')
  const heading = markdown.split('\n').find(line => /^#\s+/.test(line))
  const title = heading ? heading.replace(/^#\s+/, '').trim() : path.basename(relative, '.md')
  return { path: relative.replace(/\\/g, '/'), title, markdown }
}

/** 读取一张图表或一份 HTML 报告；返回内容与 MIME 类型。 */
export async function readDocAsset(
  relative: string,
): Promise<{ content: Buffer; mime: string }> {
  if (!ASSET_EXTENSIONS.has(path.extname(relative).toLowerCase())) {
    throw new Error('只支持图片或 HTML 资源')
  }
  const absolute = resolveInsideData(relative)
  if (absolute === null) throw new Error('资源路径不合法')
  if (!existsSync(absolute)) throw new Error('资源不存在')

  const mime = MIME_BY_EXTENSION[path.extname(relative).toLowerCase()] ?? 'application/octet-stream'
  return { content: await readFile(absolute), mime }
}
