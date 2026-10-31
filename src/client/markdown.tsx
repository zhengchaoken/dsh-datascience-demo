/**
 * 轻量 Markdown 渲染：数据科学文档只用到标题、表格、代码块、列表、引用、图表
 * 与少量内联样式，因此不引入第三方解析器，保持插件零依赖。
 *
 * 文档里的相对链接（`.md` / `.html`）会转换为面板内跳转，相对图片路径会改写为
 * `/api/dsh-datascience/doc-asset` 地址。
 */

import { useMemo, type ReactElement, type ReactNode } from 'react'
import type { DataDocContent } from '../protocol.ts'
import { docAssetUrl } from './api.ts'

/** 把相对路径解析到 `src/data` 下的路径（例如 `images/1.png` + `L4`）。 */
function resolvePath(baseDir: string, target: string): string {
  const parts = baseDir === '' ? [] : baseDir.split('/')
  for (const segment of target.replace(/\\/g, '/').split('/')) {
    if (segment === '' || segment === '.') continue
    if (segment === '..') parts.pop()
    else parts.push(segment)
  }
  return parts.join('/')
}

function dirOf(path: string): string {
  const index = path.lastIndexOf('/')
  return index < 0 ? '' : path.slice(0, index)
}

/** 内联片段：[文本](链接)、![说明](图片)、**加粗**、`代码`。 */
const INLINE_PATTERN = /(!\[[^\]]*\]\([^)]*\)|\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*|`[^`]+`)/g

function inlineNodes(text: string, baseDir: string, onNavigate: (path: string) => void): ReactNode[] {
  const nodes: ReactNode[] = []
  let cursor = 0
  let key = 0

  for (const match of text.matchAll(INLINE_PATTERN)) {
    const index = match.index ?? 0
    if (index > cursor) nodes.push(text.slice(cursor, index))
    const token = match[0]

    const image = /^!\[([^\]]*)\]\(([^)]+)\)$/.exec(token)
    if (image) {
      nodes.push(
        <img
          key={key++}
          className="dsd-md-image-inline"
          src={image[2].startsWith('http') ? image[2] : docAssetUrl(resolvePath(baseDir, image[2]))}
          alt={image[1]}
        />,
      )
      cursor = index + token.length
      continue
    }

    const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token)
    if (link) {
      const label = link[1]
      const href = link[2]
      const fragmentless = href.split('#')[0]
      const internalTarget =
        href.startsWith('#') || fragmentless === ''
          ? null
          : /\.(md|html)$/i.test(fragmentless)
            ? fragmentless
            : null
      nodes.push(
        internalTarget !== null ? (
          <a
            key={key++}
            className="dsd-md-link"
            role="button"
            tabIndex={0}
            onClick={() => onNavigate(resolvePath(baseDir, internalTarget))}
            onKeyDown={event => {
              if (event.key === 'Enter') onNavigate(resolvePath(baseDir, internalTarget))
            }}
          >
            {label}
          </a>
        ) : href.startsWith('#') ? (
          <span key={key++} className="dsd-md-anchor">{label}</span>
        ) : (
          <a key={key++} className="dsd-md-link" href={href} target="_blank" rel="noreferrer">{label}</a>
        ),
      )
      cursor = index + token.length
      continue
    }

    if (token.startsWith('**') && token.endsWith('**')) {
      nodes.push(<strong key={key++}>{token.slice(2, -2)}</strong>)
      cursor = index + token.length
      continue
    }

    if (token.startsWith('`') && token.endsWith('`')) {
      nodes.push(<code key={key++} className="dsd-md-code-inline">{token.slice(1, -1)}</code>)
      cursor = index + token.length
    }
  }

  if (cursor < text.length) nodes.push(text.slice(cursor))
  return nodes
}

function splitCells(line: string): string[] {
  return line
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map(cell => cell.trim())
}

function isAlignRow(line: string): boolean {
  const cells = splitCells(line)
  return cells.length > 0 && cells.every(cell => /^:?-{1,}:?$/.test(cell.replace(/\s/g, '')))
}

function blockKind(line: string): string {
  if (line.startsWith('```')) return 'fence'
  if (/^#{1,6}\s/.test(line)) return 'heading'
  if (/^\|/.test(line)) return 'table'
  if (/^!\[[^\]]*\]\([^)]+\)$/.test(line.trim())) return 'image'
  if (/^[-*]\s+/.test(line)) return 'list'
  if (/^\d+\.\s+/.test(line)) return 'list'
  if (/^>\s?/.test(line)) return 'quote'
  if (/^-{3,}$/.test(line.trim()) || /^\*{3,}$/.test(line.trim())) return 'rule'
  return 'text'
}

/** 渲染一篇文档的 Markdown 正文。 */
export function MarkdownView({
  markdown,
  baseDir,
  onNavigate,
}: {
  markdown: string
  baseDir: string
  onNavigate: (path: string) => void
}): ReactElement {
  const blocks = useMemo(() => {
    const lines = markdown.replace(/\r\n/g, '\n').split('\n')
    const output: ReactElement[] = []
    let index = 0
    let key = 0

    const inline = (text: string): ReactNode => inlineNodes(text, baseDir, onNavigate)

    while (index < lines.length) {
      const line = lines[index]
      if (line.trim() === '') {
        index += 1
        continue
      }

      // 代码块
      if (line.startsWith('```')) {
        const language = line.slice(3).trim()
        const body: string[] = []
        index += 1
        while (index < lines.length && !lines[index].startsWith('```')) {
          body.push(lines[index])
          index += 1
        }
        index += 1
        output.push(
          <pre key={key++} className="dsd-md-pre" data-language={language}>
            <code>{body.join('\n')}</code>
          </pre>,
        )
        continue
      }

      // 标题
      const heading = /^(#{1,6})\s+(.*)$/.exec(line)
      if (heading) {
        const level = heading[1].length
        const content = inline(heading[2])
        if (level === 1) output.push(<h1 key={key++} className="dsd-md-h1">{content}</h1>)
        else if (level === 2) output.push(<h2 key={key++} className="dsd-md-h2">{content}</h2>)
        else if (level === 3) output.push(<h3 key={key++} className="dsd-md-h3">{content}</h3>)
        else output.push(<h4 key={key++} className="dsd-md-h4">{content}</h4>)
        index += 1
        continue
      }

      // 表格
      if (line.startsWith('|') && index + 1 < lines.length && isAlignRow(lines[index + 1])) {
        const header = splitCells(line)
        const rows: string[][] = []
        index += 2
        while (index < lines.length && lines[index].startsWith('|')) {
          rows.push(splitCells(lines[index]))
          index += 1
        }
        output.push(
          <div key={key++} className="dsd-md-table-wrap">
            <table className="dsd-md-table">
              <thead>
                <tr>
                  {header.map((cell, cellIndex) => (
                    <th key={cellIndex}>{inline(cell)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {header.map((_, cellIndex) => (
                      <td key={cellIndex}>{inline(row[cellIndex] ?? '')}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>,
        )
        continue
      }

      // 独占一行的图片：渲染为带说明的图表卡片
      const image = /^!\[([^\]]*)\]\(([^)]+)\)$/.exec(line.trim())
      if (image) {
        const src = image[2].startsWith('http') ? image[2] : docAssetUrl(resolvePath(baseDir, image[2]))
        output.push(
          <figure key={key++} className="dsd-md-figure">
            <img src={src} alt={image[1]} loading="lazy" />
            {image[1] ? <figcaption>{image[1]}</figcaption> : null}
          </figure>,
        )
        index += 1
        continue
      }

      // 列表
      if (/^[-*]\s+/.test(line) || /^\d+\.\s+/.test(line)) {
        const ordered = /^\d+\.\s+/.test(line)
        const items: string[] = []
        while (
          index < lines.length &&
          (/^[-*]\s+/.test(lines[index]) || /^\d+\.\s+/.test(lines[index]))
        ) {
          items.push(lines[index].replace(/^([-*]|\d+\.)\s+/, ''))
          index += 1
        }
        output.push(
          ordered ? (
            <ol key={key++} className="dsd-md-list">
              {items.map((item, itemIndex) => <li key={itemIndex}>{inline(item)}</li>)}
            </ol>
          ) : (
            <ul key={key++} className="dsd-md-list">
              {items.map((item, itemIndex) => <li key={itemIndex}>{inline(item)}</li>)}
            </ul>
          ),
        )
        continue
      }

      // 引用
      if (/^>\s?/.test(line)) {
        const body: string[] = []
        while (index < lines.length && /^>\s?/.test(lines[index])) {
          body.push(lines[index].replace(/^>\s?/, ''))
          index += 1
        }
        output.push(<blockquote key={key++} className="dsd-md-quote">{inline(body.join(' '))}</blockquote>)
        continue
      }

      // 分隔线
      if (/^-{3,}$/.test(line.trim()) || /^\*{3,}$/.test(line.trim())) {
        output.push(<hr key={key++} className="dsd-md-rule" />)
        index += 1
        continue
      }

      // 段落：连续非空、非块级前缀的行合并。
      // 用 do/while 保证每轮至少消费一行——像 `|Z| > 3 的观测……` 这种以 `|` 开头
      // 却并非表格的文本行，否则会让循环原地打转并失控耗尽渲染进程内存。
      const body: string[] = []
      do {
        body.push(lines[index].trim())
        index += 1
      } while (
        index < lines.length &&
        lines[index].trim() !== '' &&
        blockKind(lines[index]) === 'text'
      )
      output.push(<p key={key++} className="dsd-md-text">{inline(body.join(' '))}</p>)
    }

    return output
  }, [markdown, baseDir, onNavigate])

  return <div className="dsd-md">{blocks}</div>
}

/** 文档页：标题栏 + Markdown 正文。 */
export function DocView({
  doc,
  loading,
  error,
  onRetry,
  onNavigate,
  eyebrow = 'DATA SCIENCE DOCUMENT',
}: {
  doc: DataDocContent | null
  loading: boolean
  error: string | null
  onRetry: () => void
  onNavigate: (path: string) => void
  eyebrow?: string
}): ReactElement {
  if (loading && doc === null) {
    return (
      <section className="dsd-page">
        <div className="dsd-card dsd-doc-loading">正在加载文档…</div>
      </section>
    )
  }

  if (error !== null) {
    return (
      <section className="dsd-page">
        <div className="dsd-card dsd-doc-error">
          <p>文档读取失败：{error}</p>
          <button className="dsd-button" onClick={onRetry}>重试</button>
        </div>
      </section>
    )
  }

  if (doc === null) {
    return (
      <section className="dsd-page">
        <div className="dsd-card dsd-doc-loading">请选择左侧菜单中的文档。</div>
      </section>
    )
  }

  return (
    <section className="dsd-page">
      <div className="dsd-doc-head">
        <span className="dsd-eyebrow">{eyebrow}</span>
        <h1>{doc.title}</h1>
        <p className="dsd-doc-path">src/data/{doc.path}</p>
      </div>
      <div className="dsd-card dsd-doc-card">
        <MarkdownView markdown={doc.markdown} baseDir={dirOf(doc.path)} onNavigate={onNavigate} />
      </div>
    </section>
  )
}
