/**
 * 面板主体：banner 导航 + 可折叠侧边菜单 + 首页 / 环境检查 / 示例数据页面。
 */

import { useCallback, useEffect, useRef, useState, type ReactElement } from 'react'
import type {
  DataDocContent,
  DataDocEntry,
  DatasetInfo,
  DatasetQueryResult,
  DatasetTableInfo,
  EnvironmentReport,
  InstallState,
} from '../protocol.ts'
import {
  ApiError,
  fetchDataDoc,
  fetchDataDocs,
  fetchDataset,
  fetchEnvironment,
  fetchInstallState,
  runDatasetQuery,
  startInstall,
} from './api.ts'
import { DocView } from './markdown.tsx'

/** 页面标识：示例数据下挂概览页、九张表页与数据科学文档页。 */
type Page =
  | { kind: 'home' }
  | { kind: 'environment' }
  | { kind: 'dataset' }
  | { kind: 'dataset-table'; table: string }
  | { kind: 'science'; doc: string }

/** 示例数据菜单里的九张表（静态清单，行数等动态信息从 /dataset 接口补充）。 */
const DATASET_MENU: { name: string; label: string }[] = [
  { name: 'categories', label: '类目表' },
  { name: 'customers', label: '客户表' },
  { name: 'products', label: '商品表' },
  { name: 'coupons', label: '优惠券表' },
  { name: 'orders', label: '订单表' },
  { name: 'order_items', label: '订单明细表' },
  { name: 'payments', label: '支付表' },
  { name: 'reviews', label: '评价表' },
  { name: 'user_events', label: '行为事件表' },
]

/** 把异常转成可读文案。 */
function failureMessage(failure: unknown): string {
  return failure instanceof ApiError
    ? failure.message
    : failure instanceof Error
      ? failure.message
      : String(failure)
}

/** 侧边栏与 banner 的 16px 线性图标。 */
function IconHome({ size = 16 }: { size?: number }): ReactElement {
  return (
    <svg className="dsd-menu-icon" viewBox="0 0 16 16" width={size} height={size} fill="none"
      stroke="currentColor" strokeWidth={1.3} strokeLinecap="round" strokeLinejoin="round">
      <path d="M2.2 7.2 8 2.5l5.8 4.7" />
      <path d="M3.6 6.4v6.6h8.8V6.4" />
      <path d="M6.4 13v-3.2h3.2V13" />
    </svg>
  )
}

function IconEnv({ size = 16 }: { size?: number }): ReactElement {
  return (
    <svg className="dsd-menu-icon" viewBox="0 0 16 16" width={size} height={size} fill="none"
      stroke="currentColor" strokeWidth={1.3} strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 13.5V2.5" />
      <path d="M2 13.5h12" />
      <path d="m4.6 10.2 2.6-2.9 2.2 1.6 3.2-3.8" />
      <circle cx="4.6" cy="10.2" r="0.6" fill="currentColor" stroke="none" />
      <circle cx="7.2" cy="7.3" r="0.6" fill="currentColor" stroke="none" />
      <circle cx="9.4" cy="8.9" r="0.6" fill="currentColor" stroke="none" />
    </svg>
  )
}

function IconDatabase({ size = 16 }: { size?: number }): ReactElement {
  return (
    <svg className="dsd-menu-icon" viewBox="0 0 16 16" width={size} height={size} fill="none"
      stroke="currentColor" strokeWidth={1.3} strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="8" cy="3.4" rx="5.4" ry="2" />
      <path d="M2.6 3.4v9.2c0 1.1 2.4 2 5.4 2s5.4-.9 5.4-2V3.4" />
      <path d="M2.6 8c0 1.1 2.4 2 5.4 2s5.4-.9 5.4-2" />
    </svg>
  )
}

function IconTable({ size = 12 }: { size?: number }): ReactElement {
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} fill="none" stroke="currentColor"
      strokeWidth={1.2} strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="2.5" width="12" height="11" rx="1.5" />
      <path d="M2 6h12M2 9.8h12M6.6 6v7.5" />
    </svg>
  )
}

/** 「数据科学」入口：翻开的书页，呼应方法论手册。 */
function IconBook({ size = 16 }: { size?: number }): ReactElement {
  return (
    <svg className="dsd-menu-icon" viewBox="0 0 16 16" width={size} height={size} fill="none"
      stroke="currentColor" strokeWidth={1.3} strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 4.2c-1.1-.9-2.6-1.4-4.6-1.4v9.4c2 0 3.5.5 4.6 1.4" />
      <path d="M8 4.2c1.1-.9 2.6-1.4 4.6-1.4v9.4c-2 0-3.5.5-4.6 1.4" />
      <path d="M8 4.2v9.4" />
    </svg>
  )
}

function IconPlay({ size = 13 }: { size?: number }): ReactElement {
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} fill="currentColor" stroke="none">
      <path d="M4.5 3.2v9.6c0 .6.7 1 1.2.7l7.4-4.8c.5-.3.5-1 0-1.3L5.7 2.5c-.5-.3-1.2 0-1.2.7Z" />
    </svg>
  )
}

function IconChevron({ direction = 'down', size = 12 }: { direction?: 'down' | 'left' | 'right'; size?: number }): ReactElement {
  const rotate = direction === 'down' ? 0 : direction === 'left' ? 90 : -90
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} fill="none" stroke="currentColor"
      strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round"
      style={{ transform: `rotate(${rotate}deg)`, transition: 'transform 0.15s ease' }}>
      <path d="m4 6 4 4 4-4" />
    </svg>
  )
}

function IconRefresh({ size = 14 }: { size?: number }): ReactElement {
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} fill="none" stroke="currentColor"
      strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round">
      <path d="M13.2 8a5.2 5.2 0 1 1-1.6-3.8" />
      <path d="M13.4 2.6v2.6h-2.6" />
    </svg>
  )
}

/** 首页装饰：细线网格上的节点连线，呼应数据分析的「关系网」。 */
function HeroArt(): ReactElement {
  return (
    <svg viewBox="0 0 240 170" width="100%" height="auto" aria-hidden="true">
      <defs>
        <linearGradient id="dsd-art-line" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#2563eb" stopOpacity="0.5" />
          <stop offset="100%" stopColor="#0d9488" stopOpacity="0.35" />
        </linearGradient>
      </defs>
      <g stroke="#c9dcf6" strokeWidth="1">
        <path d="M0 34h240M0 68h240M0 102h240M0 136h240" opacity="0.6" />
        <path d="M40 0v170M80 0v170M120 0v170M160 0v170M200 0v170" opacity="0.6" />
      </g>
      <g fill="none" stroke="url(#dsd-art-line)" strokeWidth="1.4">
        <path d="M14 132 60 96 104 112 146 62 192 78 226 40" />
        <path d="M14 132 60 96 78 138 122 150 166 122 192 78" />
        <path d="M104 112 122 150" opacity="0.7" />
      </g>
      <g fill="#2563eb">
        <circle cx="14" cy="132" r="3.2" />
        <circle cx="60" cy="96" r="2.6" />
        <circle cx="104" cy="112" r="3" />
        <circle cx="146" cy="62" r="2.6" />
        <circle cx="192" cy="78" r="3.2" />
      </g>
      <g fill="#0d9488">
        <circle cx="226" cy="40" r="2.4" />
        <circle cx="78" cy="138" r="2.4" />
        <circle cx="122" cy="150" r="2.8" />
        <circle cx="166" cy="122" r="2.4" />
      </g>
    </svg>
  )
}

/** 顶部 banner：一级/二级导航。 */
function Banner({ page, docTitle }: { page: Page; docTitle: string | null }): ReactElement {
  const trail: string[] = ['首页']
  if (page.kind === 'environment') trail.push('环境检查')
  if (page.kind === 'dataset') trail.push('示例数据')
  if (page.kind === 'dataset-table') {
    trail.push('示例数据', DATASET_MENU.find(item => item.name === page.table)?.label ?? page.table)
  }
  if (page.kind === 'science') {
    trail.push('示例数据', '数据科学', docTitle ?? '文档')
  }
  return (
    <header className="dsd-banner">
      <div className="dsd-brand">
        <span className="dsd-logo">
          <IconEnv size={18} />
        </span>
        <span>
          <span className="dsd-brand-name">数据科学示例</span>
          <span className="dsd-brand-en">datascience-demo</span>
        </span>
      </div>
      <nav className="dsd-crumbs" aria-label="当前位置">
        <span>数据科学示例</span>
        <span className="dsd-crumb-sep">/</span>
        {trail.map((node, index) => (
          <span key={node}>
            {index > 0 ? <span className="dsd-crumb-sep">/ </span> : null}
            {index === trail.length - 1 ? (
              <span className="dsd-crumb-current">{node}</span>
            ) : (
              <span>{node} </span>
            )}
          </span>
        ))}
      </nav>
    </header>
  )
}

/** 左侧可收缩菜单：首页、环境检查、示例数据（父菜单，下挂九张表与数据科学）。 */
function Sidebar({
  page,
  collapsed,
  datasetOpen,
  scienceOpen,
  docs,
  onToggle,
  onDatasetToggle,
  onScienceToggle,
  onSelect,
}: {
  page: Page
  collapsed: boolean
  datasetOpen: boolean
  scienceOpen: boolean
  docs: DataDocEntry[]
  onToggle: () => void
  onDatasetToggle: () => void
  onScienceToggle: () => void
  onSelect: (page: Page) => void
}): ReactElement {
  const inDataset = page.kind === 'dataset' || page.kind === 'dataset-table' || page.kind === 'science'

  if (collapsed) {
    return (
      <aside className="dsd-sidebar is-collapsed">
        <div className="dsd-sidebar-head">
          <button className="dsd-collapse" onClick={onToggle} title="展开菜单" aria-label="展开菜单">
            <IconChevron direction="right" size={13} />
          </button>
        </div>
        <div className="dsd-rail">
          <button
            className={`dsd-rail-button${page.kind === 'home' ? ' is-active' : ''}`}
            onClick={() => onSelect({ kind: 'home' })}
            title="首页"
            aria-label="首页"
          >
            <IconHome />
          </button>
          <button
            className={`dsd-rail-button${page.kind === 'environment' ? ' is-active' : ''}`}
            onClick={() => onSelect({ kind: 'environment' })}
            title="环境检查"
            aria-label="环境检查"
          >
            <IconEnv />
          </button>
          <button
            className={`dsd-rail-button${inDataset ? ' is-active' : ''}`}
            onClick={() => {
              onToggle()
              onSelect({ kind: 'dataset' })
            }}
            title="示例数据"
            aria-label="示例数据"
          >
            <IconDatabase />
          </button>
          <button
            className={`dsd-rail-button${page.kind === 'science' ? ' is-active' : ''}`}
            onClick={() => {
              onToggle()
              onSelect({ kind: 'science', doc: page.kind === 'science' ? page.doc : 'README.md' })
            }}
            title="数据科学"
            aria-label="数据科学"
          >
            <IconBook />
          </button>
        </div>
      </aside>
    )
  }

  return (
    <aside className="dsd-sidebar">
      <div className="dsd-sidebar-head">
        <span className="dsd-sidebar-title">菜单</span>
        <button className="dsd-collapse" onClick={onToggle} title="收起菜单" aria-label="收起菜单">
          <IconChevron direction="left" size={13} />
        </button>
      </div>
      <div className="dsd-menu">
        <button
          className={`dsd-menu-item${page.kind === 'home' ? ' is-active' : ''}`}
          onClick={() => onSelect({ kind: 'home' })}
        >
          <IconHome />
          <span className="dsd-menu-label">首页</span>
        </button>
        <button
          className={`dsd-menu-item${page.kind === 'environment' ? ' is-active' : ''}`}
          onClick={() => onSelect({ kind: 'environment' })}
        >
          <IconEnv />
          <span className="dsd-menu-label">环境检查</span>
        </button>
        <button
          className={`dsd-menu-item dsd-menu-parent${inDataset ? ' is-open' : ''}`}
          onClick={onDatasetToggle}
        >
          <IconDatabase />
          <span className="dsd-menu-label">示例数据</span>
          <span className="dsd-chevron">
            <IconChevron direction={datasetOpen ? 'down' : 'right'} size={11} />
          </span>
        </button>
        {datasetOpen ? (
          <div className="dsd-menu-sub">
            <button
              className={`dsd-menu-item${page.kind === 'dataset' ? ' is-active' : ''}`}
              onClick={() => onSelect({ kind: 'dataset' })}
            >
              <IconTable />
              <span className="dsd-menu-label">数据集概览</span>
            </button>
            {DATASET_MENU.map(item => (
              <button
                key={item.name}
                className={`dsd-menu-item${
                  page.kind === 'dataset-table' && page.table === item.name ? ' is-active' : ''
                }`}
                onClick={() => onSelect({ kind: 'dataset-table', table: item.name })}
              >
                <IconTable />
                <span className="dsd-menu-label">{item.label}</span>
                <span className="dsd-menu-sub-name">{item.name}</span>
              </button>
            ))}
            <button
              className={`dsd-menu-item dsd-menu-parent dsd-menu-nested${
                page.kind === 'science' ? ' is-open' : ''
              }`}
              onClick={onScienceToggle}
            >
              <IconBook />
              <span className="dsd-menu-label">数据科学</span>
              <span className="dsd-chevron">
                <IconChevron direction={scienceOpen ? 'down' : 'right'} size={11} />
              </span>
            </button>
            {scienceOpen ? (
              <div className="dsd-menu-sub dsd-menu-sub-deep">
                {docs.map(item => (
                  <button
                    key={item.id}
                    className={`dsd-menu-item${
                      page.kind === 'science' && page.doc === item.path ? ' is-active' : ''
                    }`}
                    onClick={() => onSelect({ kind: 'science', doc: item.path })}
                    title={item.summary}
                  >
                    <IconBook size={12} />
                    <span className="dsd-menu-label">{item.label}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </aside>
  )
}

/** 首页：纯静态介绍，不展示任何环境检查结果。 */
function HomePage(): ReactElement {
  return (
    <section className="dsd-page dsd-home">
      <div className="dsd-hero">
        <div className="dsd-hero-copy">
          <span className="dsd-eyebrow">DATA SCIENCE WORKBENCH</span>
          <h1>数据科学示例</h1>
          <p>
            面向电商数据分析的工作台：检查本机 Python 环境、在工作目录中创建独立虚拟环境、
            按清单安装常用分析库，并附带一套可直接查询的多表电商数据。
          </p>
          <div className="dsd-hero-meta">
            <span className="dsd-pill">Python 3.12</span>
            <span className="dsd-pill">.venv 隔离环境</span>
            <span className="dsd-pill">电商示例数据</span>
          </div>
        </div>
        <div className="dsd-hero-art">
          <HeroArt />
        </div>
      </div>

      <div className="dsd-features">
        <div className="dsd-feature">
          <div className="dsd-feature-title">
            <span className="dsd-feature-icon">
              <IconEnv size={15} />
            </span>
            环境检查
          </div>
          <p className="dsd-feature-body">
            展示系统平台、Python 解释器与虚拟环境状态，按四个部分逐项检查。
          </p>
        </div>
        <div className="dsd-feature">
          <div className="dsd-feature-title">
            <span className="dsd-feature-icon">
              <IconHome size={15} />
            </span>
            独立虚拟环境
          </div>
          <p className="dsd-feature-body">
            在当前工作目录创建 .venv，依赖与系统 Python 隔离，避免污染全局环境。
          </p>
        </div>
        <div className="dsd-feature">
          <div className="dsd-feature-title">
            <span className="dsd-feature-icon">
              <IconRefresh size={15} />
            </span>
            依赖清单
          </div>
          <p className="dsd-feature-body">
            依赖统一维护在 requirements.txt，安装时使用清华源加速，过程日志实时可见。
          </p>
        </div>
        <div className="dsd-feature">
          <div className="dsd-feature-title">
            <span className="dsd-feature-icon">
              <IconDatabase size={15} />
            </span>
            示例数据
          </div>
          <p className="dsd-feature-body">
            内置九张表的电商数据集，支持逐表预览并在线执行 SELECT 查询。
          </p>
        </div>
      </div>
    </section>
  )
}

/** 一个小节的标题行。 */
function SectionHead({
  index,
  title,
  subtitle,
  status,
}: {
  index: string
  title: string
  subtitle: string
  status: ReactElement | null
}): ReactElement {
  return (
    <div className="dsd-section-head">
      <span className="dsd-section-index">{index}</span>
      <div className="dsd-section-heading">
        <div className="dsd-section-title">{title}</div>
        <div className="dsd-section-sub">{subtitle}</div>
      </div>
      {status}
    </div>
  )
}

/** 状态徽标：绿色可用 / 橙色待处理。 */
function Flag({ ok, children }: { ok: boolean; children: string }): ReactElement {
  return (
    <span className={`dsd-card-flag ${ok ? 'is-ok' : 'is-bad'}`}>
      <span className="dsd-status-dot" />
      {children}
    </span>
  )
}

/** 环境检查页：系统 / Python / 环境管理器 / 依赖清单 四部分。 */
function EnvironmentPage({
  report,
  loading,
  error,
  install,
  onInstall,
  onRefresh,
}: {
  report: EnvironmentReport | null
  loading: boolean
  error: string | null
  install: InstallState | null
  onInstall: () => void
  onRefresh: () => void
}): ReactElement {
  const logs = install?.logs ?? []
  const installing = install?.status === 'running'
  const logRef = useRef<HTMLPreElement | null>(null)
  const [showPackages, setShowPackages] = useState(false)

  useEffect(() => {
    const element = logRef.current
    if (element !== null) element.scrollTop = element.scrollHeight
  }, [logs.length])

  const pythonReady = report !== null && report.python.found && report.python.versionOk
  const venvReady = report !== null && report.workspace.venvExists
  const missingDependencies =
    report === null ? [] : report.dependencies.filter(dependency => !dependency.installed)

  const statusText =
    install === null || install.status === 'idle'
      ? '尚未开始'
      : install.status === 'running'
        ? '正在安装'
        : install.status === 'succeeded'
          ? '安装成功'
          : '安装失败'

  return (
    <section className="dsd-page">
      <div className="dsd-page-head">
        <div>
          <h2>环境检查</h2>
          <p className="dsd-page-sub">系统、Python、虚拟环境与依赖清单。</p>
        </div>
        <div className="dsd-toolbar">
          <button className="dsd-button" onClick={onRefresh} disabled={loading || installing}>
            <IconRefresh />
            刷新
          </button>
        </div>
      </div>

      {error !== null ? <div className="dsd-alert">{error}</div> : null}

      {loading && report === null ? (
        <div className="dsd-loading">
          <span className="dsd-spinner" />
          正在探测本机环境…
        </div>
      ) : report === null ? (
        <div className="dsd-empty">暂无环境信息，请点击刷新重试。</div>
      ) : (
        <>
          <div className="dsd-env-stack">
            <section className="dsd-card dsd-env-section">
              <SectionHead
                index="01"
                title="系统"
                subtitle="当前运行环境（静态信息）"
                status={<Flag ok>{report.system.arch}</Flag>}
              />
              <div className="dsd-kv-grid">
                <div className="dsd-kv-row">
                  <span className="dsd-kv-key">系统</span>
                  <span className="dsd-kv-value">{report.system.type} {report.system.release}</span>
                </div>
                <div className="dsd-kv-row">
                  <span className="dsd-kv-key">平台</span>
                  <span className="dsd-kv-value">{report.system.platform} · {report.system.arch}</span>
                </div>
                <div className="dsd-kv-row">
                  <span className="dsd-kv-key">Node</span>
                  <span className="dsd-kv-value dsd-mono">{report.system.node}</span>
                </div>
                <div className="dsd-kv-row">
                  <span className="dsd-kv-key">检查时间</span>
                  <span className="dsd-kv-value dsd-mono">{report.checkedAt}</span>
                </div>
              </div>
            </section>

            <section className="dsd-card dsd-env-section">
              <SectionHead
                index="02"
                title="Python"
                subtitle="系统解释器"
                status={
                  report.python.found
                    ? <Flag ok={report.python.versionOk}>{report.python.versionOk ? '可用' : '版本不符'}</Flag>
                    : <Flag ok={false}>未找到</Flag>
                }
              />
              <div className="dsd-kv-grid">
                <div className="dsd-kv-row">
                  <span className="dsd-kv-key">版本</span>
                  <span className="dsd-kv-value dsd-mono">{report.python.version ?? '—'}</span>
                </div>
                <div className="dsd-kv-row">
                  <span className="dsd-kv-key">pip</span>
                  <span className="dsd-kv-value dsd-mono">{report.python.pipVersion ?? '未检测到'}</span>
                </div>
                <div className="dsd-kv-row dsd-kv-wide">
                  <span className="dsd-kv-key">路径</span>
                  <span className="dsd-kv-value dsd-mono">{report.python.executable ?? '—'}</span>
                </div>
              </div>
              {pythonReady ? null : (
                <div className="dsd-action-row">
                  <button className="dsd-button is-primary" onClick={onInstall} disabled={installing || loading}>
                    {installing ? '正在安装…' : '安装 Python 3.12'}
                  </button>
                  <span className="dsd-action-hint">
                    安装后会继续创建 .venv 并安装依赖清单。
                  </span>
                </div>
              )}
            </section>

            <section className="dsd-card dsd-env-section">
              <SectionHead
                index="03"
                title="环境管理器"
                subtitle="当前工作目录中的独立虚拟环境"
                status={
                  venvReady
                    ? <Flag ok>{report.workspace.pythonVersion ?? '已创建'}</Flag>
                    : <Flag ok={false}>无 .venv</Flag>
                }
              />
              <div className="dsd-kv-grid">
                <div className="dsd-kv-row dsd-kv-wide">
                  <span className="dsd-kv-key">工作目录</span>
                  <span className="dsd-kv-value dsd-mono">{report.workspace.path}</span>
                </div>
                <div className="dsd-kv-row dsd-kv-wide">
                  <span className="dsd-kv-key">.venv</span>
                  <span className="dsd-kv-value dsd-mono">{report.workspace.venvPath}</span>
                </div>
                {venvReady ? (
                  <>
                    <div className="dsd-kv-row">
                      <span className="dsd-kv-key">Python</span>
                      <span className="dsd-kv-value dsd-mono">{report.workspace.pythonVersion ?? '—'}</span>
                    </div>
                    <div className="dsd-kv-row">
                      <span className="dsd-kv-key">pip</span>
                      <span className="dsd-kv-value dsd-mono">{report.workspace.pipVersion ?? '—'}</span>
                    </div>
                  </>
                ) : null}
                <div className="dsd-kv-row dsd-kv-wide">
                  <span className="dsd-kv-key">conda/mamba</span>
                  <span className="dsd-kv-value">
                    {report.managers.length === 0
                      ? '未检测到（安装 Python 时回退到官方安装包）'
                      : report.managers.map(manager => `${manager.name} ${manager.version}`).join(' · ')}
                  </span>
                </div>
              </div>
              {pythonReady && !venvReady ? (
                <div className="dsd-action-row">
                  <button className="dsd-button is-primary" onClick={onInstall} disabled={installing || loading}>
                    {installing ? '正在安装…' : '创建 .venv 并安装依赖'}
                  </button>
                  <span className="dsd-action-hint">
                    使用 python -m venv .venv，随后升级 pip 并按清华源安装依赖。
                  </span>
                </div>
              ) : null}
            </section>

            <section className="dsd-card dsd-env-section">
              <SectionHead
                index="04"
                title="依赖清单"
                subtitle="requirements.txt 中的直接依赖"
                status={
                  <Flag ok={missingDependencies.length === 0 && report.dependencies.length > 0}>
                    {report.dependencies.length === 0
                      ? '清单为空'
                      : missingDependencies.length === 0
                        ? '全部已安装'
                        : `缺少 ${missingDependencies.length} 项`}
                  </Flag>
                }
              />
              {report.dependencies.length === 0 ? (
                <div className="dsd-empty">requirements.txt 中没有依赖条目。</div>
              ) : (
                <div className="dsd-deps">
                  {report.dependencies.map(dependency => (
                    <span
                      className={`dsd-chip${dependency.installed ? '' : ' is-missing'}`}
                      key={dependency.name}
                    >
                      <span className="dsd-chip-dot" />
                      {dependency.name}
                      {dependency.installed ? (
                        <span className="dsd-mono">{dependency.version}</span>
                      ) : (
                        <span>未安装</span>
                      )}
                    </span>
                  ))}
                </div>
              )}

              {venvReady && missingDependencies.length > 0 ? (
                <div className="dsd-action-row">
                  <button className="dsd-button is-primary" onClick={onInstall} disabled={installing || loading}>
                    {installing ? '正在安装…' : '安装缺失依赖'}
                  </button>
                  <span className="dsd-action-hint">
                    使用清华源安装，已安装的包会跳过。
                  </span>
                </div>
              ) : null}

              {venvReady ? (
                <div className="dsd-packages">
                  <button
                    className="dsd-packages-toggle"
                    onClick={() => setShowPackages(value => !value)}
                  >
                    <IconChevron direction={showPackages ? 'down' : 'right'} size={11} />
                    查看 pip list（{report.installedPackages.length} 个已安装包）
                  </button>
                  {showPackages ? (
                    <div className="dsd-package-list">
                      {report.installedPackages.map(entry => (
                        <div className="dsd-package-row" key={entry.name}>
                          <span className="dsd-package-name">{entry.name}</span>
                          <span className="dsd-mono">{entry.version}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}

              {report.dependenciesError !== null ? (
                <div className="dsd-link-note">依赖状态：{report.dependenciesError}</div>
              ) : null}
              <div className="dsd-link-note">清单文件：{report.requirementsFile}</div>
            </section>
          </div>

          {install !== null && install.status === 'failed' && install.error !== null ? (
            <div className="dsd-alert">安装失败：{install.error}</div>
          ) : null}

          <div className="dsd-install-panel">
            <div className="dsd-install-head">
              <span className="dsd-install-title">安装日志</span>
              <span className={`dsd-install-state${install === null ? '' : ` is-${install.status}`}`}>
                {installing ? <span className="dsd-spinner" /> : <span className="dsd-status-dot" />}
                {statusText}
              </span>
            </div>
            <pre className={`dsd-log${logs.length === 0 ? ' is-empty' : ''}`} ref={logRef}>
              {logs.length === 0 ? '尚未开始安装。点击上方按钮后，这里会实时显示安装过程。' : logs.join('\n')}
            </pre>
            <div className="dsd-log-hint">
              {installing
                ? '安装进行中，日志会自动刷新；完成后环境信息会自动重新检测。'
                : '安装流程：确认 Python 3.12 → python -m venv .venv → 升级 pip/setuptools/wheel → 按清华源安装依赖。'}
            </div>
          </div>
        </>
      )}
    </section>
  )
}

/** ER 图节点：手绘固定坐标，viewBox 920×620。 */
interface GraphNode {
  name: string
  label: string
  domain: 'user' | 'product' | 'trade' | 'marketing' | 'content'
  x: number
  y: number
  w: number
  h: number
}

/** 九张表在三列布局中的位置：左列用户域，中列交易域，右列商品 + 营销域。 */
const GRAPH_NODES: GraphNode[] = [
  { name: 'customers', label: '客户表', domain: 'user', x: 24, y: 60, w: 164, h: 84 },
  { name: 'user_events', label: '行为事件表', domain: 'content', x: 24, y: 260, w: 164, h: 70 },
  { name: 'orders', label: '订单表', domain: 'trade', x: 280, y: 40, w: 200, h: 96 },
  { name: 'order_items', label: '订单明细表', domain: 'trade', x: 280, y: 200, w: 200, h: 74 },
  { name: 'reviews', label: '评价表', domain: 'content', x: 280, y: 360, w: 200, h: 70 },
  { name: 'categories', label: '类目表', domain: 'product', x: 600, y: 40, w: 200, h: 70 },
  { name: 'products', label: '商品表', domain: 'product', x: 600, y: 190, w: 200, h: 84 },
  { name: 'payments', label: '支付表', domain: 'trade', x: 600, y: 350, w: 200, h: 70 },
  { name: 'coupons', label: '优惠券表', domain: 'marketing', x: 600, y: 500, w: 200, h: 70 },
]

/** 域配色：与侧边栏、卡片保持同一套色系。 */
const DOMAIN_COLORS: Record<GraphNode['domain'], string> = {
  user: '#2563eb',
  product: '#0d9488',
  trade: '#b45309',
  marketing: '#7c3aed',
  content: '#be123c',
}

/** 域名称。 */
const DOMAIN_LABELS: Record<GraphNode['domain'], string> = {
  user: '用户域',
  product: '商品域',
  trade: '交易域',
  marketing: '营销域',
  content: '内容域',
}

/** ER 图的一条边：path 为手绘走线，label 为基数标注。 */
interface GraphEdge {
  d: string
  label: string
  labelX: number
  labelY: number
}

/** 全部边按主干关系绘制；评价 → 商品 / 客户的次要边放到下方关系表。 */
const GRAPH_EDGES: GraphEdge[] = [
  { d: 'M188,100 L280,88', label: '1 : N', labelX: 234, labelY: 82 },
  { d: 'M100,144 L100,260', label: '1 : N', labelX: 108, labelY: 206 },
  { d: 'M340,136 L340,200', label: '1 : 1..N', labelX: 348, labelY: 172 },
  { d: 'M480,237 L600,232', label: 'N : 1', labelX: 540, labelY: 226 },
  { d: 'M680,190 L680,110', label: 'N : 1', labelX: 688, labelY: 154 },
  { d: 'M800,60 L842,60 L842,92 L800,92', label: '父 : 子', labelX: 848, labelY: 80 },
  { d: 'M480,120 L540,120 L540,385 L600,385', label: '1 : 0..1', labelX: 548, labelY: 260 },
  { d: 'M480,95 L560,95 L560,535 L600,535', label: 'N : 0..1', labelX: 568, labelY: 320 },
  { d: 'M280,115 L245,115 L245,395 L280,395', label: '1 : 0..1', labelX: 200, labelY: 300 },
  { d: 'M700,274 L700,320 L520,320 L520,395 L480,395', label: 'N : 1', labelX: 528, labelY: 314 },
  { d: 'M188,120 L215,120 L215,410 L280,410', label: 'N : 1', labelX: 188, labelY: 425 },
]

/** 表关系图（ER）：九张表的键关系、基数与实时行数。 */
function RelationGraph({ dataset }: { dataset: DatasetInfo | null }): ReactElement {
  const rowCount = (name: string): string => {
    const table = dataset?.tables.find(item => item.name === name)
    return table === undefined ? '—' : `${table.rowCount.toLocaleString()} 行`
  }
  const columnCount = (name: string): string => {
    const table = dataset?.tables.find(item => item.name === name)
    return table === undefined ? '' : `${table.columns.length} 列`
  }

  return (
    <div className="dsd-graph-scroll">
      <svg className="dsd-graph" viewBox="0 0 920 620" role="img" aria-label="电商数据集表关系图">
        <defs>
          <marker id="dsd-arrow" viewBox="0 0 8 8" refX="7" refY="4"
            markerWidth="6" markerHeight="6" orient="auto">
            <path d="M1,1 L7,4 L1,7" fill="none" stroke="#8ba3c0" strokeWidth="1.2" />
          </marker>
        </defs>

        {GRAPH_EDGES.map(edge => (
          <g key={edge.d}>
            <path
              d={edge.d}
              className="dsd-graph-edge"
              markerEnd="url(#dsd-arrow)"
            />
            <text className="dsd-graph-label" x={edge.labelX} y={edge.labelY}>
              {edge.label}
            </text>
          </g>
        ))}

        {GRAPH_NODES.map(node => (
          <g key={node.name}>
            <rect
              x={node.x}
              y={node.y}
              width={node.w}
              height={node.h}
              rx="8"
              className="dsd-graph-node"
              style={{ stroke: DOMAIN_COLORS[node.domain] }}
            />
            <text className="dsd-graph-name" x={node.x + 12} y={node.y + 24}>
              {node.name}
            </text>
            <text className="dsd-graph-sub" x={node.x + 12} y={node.y + 42}>
              {node.label}
            </text>
            <text
              className="dsd-graph-count"
              x={node.x + node.w - 12}
              y={node.y + 24}
              textAnchor="end"
            >
              {rowCount(node.name)}
            </text>
            <text
              className="dsd-graph-sub"
              x={node.x + node.w - 12}
              y={node.y + 42}
              textAnchor="end"
            >
              {columnCount(node.name)}
            </text>
            <text
              className="dsd-graph-domain"
              x={node.x + 12}
              y={node.y + node.h - 12}
              style={{ fill: DOMAIN_COLORS[node.domain] }}
            >
              {DOMAIN_LABELS[node.domain]}
            </text>
          </g>
        ))}
      </svg>
    </div>
  )
}

/** 知识图谱的域卡片（对应 README 第 5 节的五个业务域）。 */
const KNOWLEDGE_DOMAINS: { domain: GraphNode['domain']; entities: string[]; note: string }[] = [
  { domain: 'user', entities: ['客户 Customer', '省市 · 会员等级'], note: '3,000 名会员，10 省 23 市，四档等级' },
  { domain: 'product', entities: ['类目 Category', '商品 Product'], note: '6 个一级 × 4 个二级类目，600 个商品' },
  { domain: 'trade', entities: ['订单 Order', '明细 OrderItem', '支付 Payment'], note: '19,669 订单 / 36,907 明细 / 19,181 支付' },
  { domain: 'marketing', entities: ['优惠券 Coupon'], note: '8 张券，4,189 单使用（21.3%）' },
  { domain: 'content', entities: ['评价 Review', '行为事件 Event'], note: '5,976 条评价 / 76,905 条埋点' },
]

/** 知识图谱的三元组关系：源实体 - 关系 → 目标实体，附数据表现。 */
const KNOWLEDGE_TRIPLES: { source: string; relation: string; target: string; cardinality: string; check: string }[] = [
  { source: '客户', relation: '下单', target: '订单', cardinality: '1 : N', check: '3,000 客户产生 19,669 笔订单' },
  { source: '订单', relation: '包含', target: '订单明细', cardinality: '1 : 1..4', check: '每单 1~4 行明细，无空单' },
  { source: '订单明细', relation: '对应', target: '商品', cardinality: 'N : 1', check: '36,907 行明细指向 600 个商品' },
  { source: '商品', relation: '归属', target: '二级类目', cardinality: 'N : 1', check: '600 个商品全部挂在二级类目' },
  { source: '二级类目', relation: '归属', target: '一级类目', cardinality: 'N : 1', check: '24 个二级类目分属 6 个一级类目' },
  { source: '订单', relation: '使用', target: '优惠券', cardinality: 'N : 0..1', check: '4,189 单使用优惠券（占 21.3%）' },
  { source: '订单', relation: '支付', target: '支付单', cardinality: '1 : 0..1', check: '仅 488 单待付款无支付，其余恰好 1 条' },
  { source: '订单', relation: '产生', target: '评价', cardinality: '1 : 0..1', check: '每单最多 1 条；17,292 单已完成中 5,976 单有评价' },
  { source: '评价', relation: '指向', target: '商品 · 客户', cardinality: 'N : 1', check: '每条评价都对应有效商品与客户' },
  { source: '客户', relation: '产生', target: '行为事件', cardinality: '1 : N', check: '76,905 条浏览 / 加购埋点' },
  { source: '行为事件', relation: '指向', target: '商品', cardinality: 'N : 1', check: '全部指向有效商品' },
  { source: '客户', relation: '持有', target: '会员等级', cardinality: '1 : 1', check: '普通 / 白银 / 黄金 / 钻石' },
]

/** 知识图谱：五个业务域 + 实体三元组关系。 */
function KnowledgeGraph(): ReactElement {
  return (
    <>
      <div className="dsd-domain-grid">
        {KNOWLEDGE_DOMAINS.map(item => (
          <div
            className="dsd-domain-card"
            key={item.domain}
            style={{ borderTopColor: DOMAIN_COLORS[item.domain] }}
          >
            <div className="dsd-domain-title" style={{ color: DOMAIN_COLORS[item.domain] }}>
              {DOMAIN_LABELS[item.domain]}
            </div>
            {item.entities.map(entity => (
              <div className="dsd-domain-entity" key={entity}>{entity}</div>
            ))}
            <div className="dsd-domain-note">{item.note}</div>
          </div>
        ))}
      </div>

      <div className="dsd-grid-scroll dsd-triple-scroll">
        <table className="dsd-grid">
          <thead>
            <tr>
              <th>源实体</th>
              <th>关系</th>
              <th>目标实体</th>
              <th>基数</th>
              <th>数据表现</th>
            </tr>
          </thead>
          <tbody>
            {KNOWLEDGE_TRIPLES.map(triple => (
              <tr key={`${triple.source}-${triple.relation}-${triple.target}`}>
                <td>{triple.source}</td>
                <td className="dsd-triple-relation">{triple.relation}</td>
                <td>{triple.target}</td>
                <td className="dsd-mono">{triple.cardinality}</td>
                <td className="is-text" title={triple.check}>{triple.check}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

/** 概览页的关键业务术语（口径来自 src/data/ecommerce/README.md）。 */
const DATASET_TERMS: { term: string; definition: string; sql: string }[] = [
  { term: 'GMV', definition: '已完成+已发货订单的实付合计', sql: "SUM(total_amount) WHERE order_status IN ('已完成','已发货')" },
  { term: '客单价', definition: 'GMV / 订单数', sql: 'SUM(total_amount) / COUNT(*)' },
  { term: '件单价', definition: 'GMV / 销售件数', sql: 'SUM(subtotal) / SUM(quantity)' },
  { term: '连带率', definition: '平均每单商品件数', sql: 'SUM(quantity) / COUNT(DISTINCT order_id)' },
  { term: '复购率', definition: '购买 ≥2 次的客户占比', sql: '按 customer_id 分组计数' },
  { term: '退款率', definition: '已退款支付单占比', sql: "payments.payment_status = '已退款'" },
  { term: '转化率', definition: '浏览→加购→购买漏斗比例', sql: 'user_events 按 event_type 统计' },
  { term: '动销率', definition: '有销量的商品占比', sql: 'order_items 去重 product_id / products' },
  { term: '毛利率', definition: '(成交额-成本) / 成交额', sql: 'subtotal - cost×quantity' },
  { term: 'RFM', definition: '最近消费 / 频率 / 金额三维分群', sql: '基于 orders 按客户聚合' },
]

/** 示例数据概览页：整体介绍电商数据集（内容基于 src/data/ecommerce/README.md）。 */
function DatasetOverviewPage({
  dataset,
  error,
  onRetry,
  onOpenTable,
}: {
  dataset: DatasetInfo | null
  error: string | null
  onRetry: () => void
  onOpenTable: (table: string) => void
}): ReactElement {
  return (
    <section className="dsd-page">
      <div className="dsd-page-head">
        <div>
          <h2>电商分析数据集</h2>
          <p className="dsd-page-sub">
            覆盖类目、商品、客户、订单、支付、评价与行为埋点的多表关联电商数据，可直接用于取数分析。
          </p>
        </div>
        <div className="dsd-toolbar">
          <button className="dsd-button" onClick={onRetry}>
            <IconRefresh />
            刷新
          </button>
        </div>
      </div>

      {error !== null ? <div className="dsd-alert">{error}</div> : null}

      <div className="dsd-env-stack">
        <section className="dsd-card dsd-env-section">
          <SectionHead
            index="01"
            title="数据范围与口径"
            subtitle="时间跨度、覆盖维度与金额、状态的统一定义"
            status={<Flag ok>2024-01-01 起</Flag>}
          />
          <div className="dsd-kv-grid">
            <div className="dsd-kv-row dsd-kv-wide">
              <span className="dsd-kv-key">时间范围</span>
              <span className="dsd-kv-value">2024-01-01 ~ 2025-06-15，含完整大促与季节性波动</span>
            </div>
            <div className="dsd-kv-row dsd-kv-wide">
              <span className="dsd-kv-key">覆盖维度</span>
              <span className="dsd-kv-value">10 省 23 市、四档会员等级、四个下单渠道（APP / 小程序 / 网页 / 线下）</span>
            </div>
            <div className="dsd-kv-row dsd-kv-wide">
              <span className="dsd-kv-key">金额口径</span>
              <span className="dsd-kv-value">实付金额 = 明细小计合计 + 运费；全部金额保留两位小数</span>
            </div>
            <div className="dsd-kv-row dsd-kv-wide">
              <span className="dsd-kv-key">状态口径</span>
              <span className="dsd-kv-value">待付款 / 已发货 / 已完成 / 已取消，取消可发生在任意阶段</span>
            </div>
          </div>
        </section>

        <section className="dsd-card dsd-env-section">
          <SectionHead
            index="02"
            title="数据规模"
            subtitle="九张表，点击任意一行进入该表的数据预览 / 查询"
            status={
              dataset !== null ? (
                <Flag ok>{`共 ${dataset.tables.reduce((sum, table) => sum + table.rowCount, 0).toLocaleString()} 行`}</Flag>
              ) : null
            }
          />
          <div className="dsd-table-scale">
            <div className="dsd-grid-scroll">
              <table className="dsd-grid">
                <thead>
                  <tr>
                    <th>表</th>
                    <th>中文名</th>
                    <th className="is-num">行数</th>
                    <th>说明</th>
                  </tr>
                </thead>
                <tbody>
                  {(dataset?.tables ?? DATASET_MENU.map(item => ({
                    name: item.name,
                    label: item.label,
                    description: '',
                    rowCount: -1,
                    columns: [],
                  }))).map(table => (
                    <tr key={table.name} className="is-link" onClick={() => onOpenTable(table.name)}>
                      <td className="dsd-mono">{table.name}</td>
                      <td>{table.label}</td>
                      <td className="is-num">
                        {table.rowCount >= 0 ? table.rowCount.toLocaleString() : '—'}
                      </td>
                      <td>{table.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="dsd-link-note">
            数据包含双 11、618 大促峰值，春节低谷与周末效应，整体呈缓慢增长；另有约 1.2% 批发型大额订单
            （单件商品数量 30~200）与 0.5% 高单价异常订单（单价约为常规的 10 倍），适合作为异常检测的练习样本。
          </div>
        </section>

        <section className="dsd-card dsd-env-section">
          <SectionHead
            index="03"
            title="表关系图"
            subtitle="九张表的主干键关系与基数，节点标注当前行数与列数"
            status={<Flag ok>11 条表间关联</Flag>}
          />
          <RelationGraph dataset={dataset} />
          <div className="dsd-link-note">
            节点按业务域配色，面板较窄时可横向滚动查看完整图谱。评价同时关联商品与客户，图中以订单主链路呈现。
          </div>
        </section>

        <section className="dsd-card dsd-env-section">
          <SectionHead
            index="04"
            title="知识图谱"
            subtitle="按用户 / 商品 / 交易 / 营销 / 内容五个业务域组织的实体关系"
            status={null}
          />
          <KnowledgeGraph />
        </section>

        <section className="dsd-card dsd-env-section">
          <SectionHead
            index="05"
            title="关键业务术语"
            subtitle="常用分析口径与 SQL 示意"
            status={null}
          />
          <div className="dsd-grid-scroll">
            <table className="dsd-grid">
              <thead>
                <tr>
                  <th>术语</th>
                  <th>口径</th>
                  <th>SQL 示意</th>
                </tr>
              </thead>
              <tbody>
                {DATASET_TERMS.map(item => (
                  <tr key={item.term}>
                    <td>{item.term}</td>
                    <td>{item.definition}</td>
                    <td className="dsd-mono">{item.sql}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <div className="dsd-alert dsd-alert-warn">
          口径提示：约 21% 订单的发货时刻早于同日支付时刻，日期信息本身无误。涉及「支付到发货时长」的分析，
          建议按日粒度统计。
        </div>

        {dataset !== null ? (
          <div className="dsd-link-note">
            数据库文件：<span className="dsd-mono">{dataset.dbFile}</span>（{dataset.engine}，只读）
          </div>
        ) : null}
      </div>
    </section>
  )
}

/** 客户端 SQL 预校验：与服务端同一套规则，尽早给出提示。 */
function validateSelectSql(sql: string): string | null {
  const body = sql.trim().replace(/;+\s*$/, '')
  if (body === '') return '请输入 SQL 语句'
  if (!/^(select|with)\b/i.test(body)) return '只允许 SELECT 查询，不支持写入或 DDL 语句'
  if (body.includes(';')) return '只允许单条 SELECT 语句'
  return null
}

/** 结果单元格：NULL 灰色斜体、数字右对齐等宽、长文本截断。 */
function Cell({ value }: { value: string | number | null }): ReactElement {
  if (value === null) {
    return <td className="is-null">NULL</td>
  }
  if (typeof value === 'number') {
    return <td className="is-num">{value}</td>
  }
  return <td className="is-text" title={value}>{value}</td>
}

/** 单表页面：SQL 输入区 + 可滚动结果表格 + 底部统计条。 */
function DatasetTablePage({
  table,
  meta,
}: {
  table: string
  meta: DatasetTableInfo | null
}): ReactElement {
  const [sql, setSql] = useState(`select * from ${table} limit 100`)
  const [result, setResult] = useState<DatasetQueryResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [showColumns, setShowColumns] = useState(false)

  const inputError = validateSelectSql(sql)

  const execute = useCallback(
    async (statement: string): Promise<void> => {
      const invalid = validateSelectSql(statement)
      if (invalid !== null) {
        setError(invalid)
        return
      }
      setRunning(true)
      setError(null)
      try {
        setResult(await runDatasetQuery(statement))
      } catch (failure) {
        setError(failureMessage(failure))
      } finally {
        setRunning(false)
      }
    },
    [],
  )

  // 进入页面即执行默认预览查询。
  const defaultSql = `select * from ${table} limit 100`
  useEffect(() => {
    void execute(defaultSql)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <section className="dsd-page dsd-page-wide">
      <div className="dsd-page-head">
        <div>
          <h2>
            {meta?.label ?? table}
            <span className="dsd-page-table-name dsd-mono">{table}</span>
          </h2>
          <p className="dsd-page-sub">{meta?.description ?? ''}</p>
        </div>
        <div className="dsd-toolbar">
          <span className="dsd-pill">
            共 {meta !== null ? meta.rowCount.toLocaleString() : '—'} 行
          </span>
        </div>
      </div>

      {meta !== null && meta.columns.length > 0 ? (
        <div className="dsd-packages dsd-columns">
          <button className="dsd-packages-toggle" onClick={() => setShowColumns(value => !value)}>
            <IconChevron direction={showColumns ? 'down' : 'right'} size={11} />
            字段说明（{meta.columns.length} 列）
          </button>
          {showColumns ? (
            <div className="dsd-column-list">
              {meta.columns.map(column => (
                <div className="dsd-column-row" key={column.name}>
                  <span className="dsd-column-name dsd-mono">{column.name}</span>
                  <span className="dsd-column-type dsd-mono">{column.type}</span>
                  <span className="dsd-column-comment">{column.comment}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="dsd-sql-panel">
        <div className="dsd-sql-head">
          <span className="dsd-install-title">数据预览 / 查询</span>
          <span className="dsd-sql-hint">仅支持单条 SELECT 语句，Ctrl+Enter 执行</span>
        </div>
        <textarea
          className={`dsd-sql-input${inputError !== null ? ' is-invalid' : ''}`}
          value={sql}
          onChange={event => setSql(event.target.value)}
          onKeyDown={event => {
            if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && inputError === null && !running) {
              void execute(sql)
            }
          }}
          rows={3}
          spellCheck={false}
        />
        <div className="dsd-sql-actions">
          <button
            className="dsd-button is-primary"
            onClick={() => void execute(sql)}
            disabled={running || inputError !== null}
          >
            {running ? <span className="dsd-spinner" /> : <IconPlay />}
            {running ? '执行中…' : '执行'}
          </button>
          <button
            className="dsd-button"
            onClick={() => {
              setSql(defaultSql)
              void execute(defaultSql)
            }}
            disabled={running}
          >
            重置为默认查询
          </button>
          {inputError !== null ? <span className="dsd-sql-error">{inputError}</span> : null}
        </div>
      </div>

      {error !== null ? <div className="dsd-alert">{error}</div> : null}

      <div className="dsd-result-panel">
        {result === null ? (
          <div className="dsd-loading">
            {running ? (
              <>
                <span className="dsd-spinner" />
                正在查询…
              </>
            ) : (
              '暂无结果'
            )}
          </div>
        ) : result.columns.length === 0 ? (
          <div className="dsd-empty">查询返回 0 行。</div>
        ) : (
          <div className="dsd-grid-scroll dsd-result-scroll">
            <table className="dsd-grid">
              <thead>
                <tr>
                  <th className="dsd-grid-index">#</th>
                  {result.columns.map(column => (
                    <th key={column}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    <td className="dsd-grid-index">{rowIndex + 1}</td>
                    {row.map((value, columnIndex) => (
                      <Cell key={columnIndex} value={value} />
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="dsd-result-stats">
          <span>表总行数 {meta !== null ? meta.rowCount.toLocaleString() : '—'}</span>
          <span className="dsd-stat-sep" />
          <span>
            返回 {result !== null ? result.rowCount.toLocaleString() : 0} 行
            {result?.truncated ? `（超出 ${result.maxRows.toLocaleString()} 行上限已截断）` : ''}
          </span>
          <span className="dsd-stat-sep" />
          <span>{result !== null ? result.columns.length : 0} 列</span>
          <span className="dsd-stat-sep" />
          <span>耗时 {result !== null ? result.elapsedMs.toFixed(1) : '—'} ms</span>
        </div>
      </div>
    </section>
  )
}

/** 面板根组件。 */
export function App(): ReactElement {
  const [page, setPage] = useState<Page>({ kind: 'home' })
  const [collapsed, setCollapsed] = useState(false)
  const [datasetOpen, setDatasetOpen] = useState(false)
  const [scienceOpen, setScienceOpen] = useState(false)
  const [docs, setDocs] = useState<DataDocEntry[]>([])
  const [doc, setDoc] = useState<DataDocContent | null>(null)
  const [docLoading, setDocLoading] = useState(false)
  const [docError, setDocError] = useState<string | null>(null)
  const [docReload, setDocReload] = useState(0)
  const [dataset, setDataset] = useState<DatasetInfo | null>(null)
  const [datasetError, setDatasetError] = useState<string | null>(null)
  const [report, setReport] = useState<EnvironmentReport | null>(null)
  const [install, setInstall] = useState<InstallState | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      const next = await fetchEnvironment()
      setReport(next)
      setInstall(next.install)
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : failure instanceof Error ? failure.message : String(failure))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // 安装任务运行期间轮询日志；结束后重新探测一次环境。
  useEffect(() => {
    if (install?.status !== 'running') return undefined
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined

    const tick = async (): Promise<void> => {
      try {
        const next = await fetchInstallState()
        if (cancelled) return
        setInstall(next)
        if (next.status === 'running') {
          timer = setTimeout(() => void tick(), 800)
        } else {
          void refresh()
        }
      } catch (failure) {
        if (cancelled) return
        setError(failure instanceof Error ? failure.message : String(failure))
        timer = setTimeout(() => void tick(), 1500)
      }
    }

    timer = setTimeout(() => void tick(), 400)
    return () => {
      cancelled = true
      if (timer !== undefined) clearTimeout(timer)
    }
  }, [install?.status, refresh])

  const handleInstall = useCallback(async (): Promise<void> => {
    setError(null)
    try {
      const started = await startInstall()
      setInstall(started)
    } catch (failure) {
      setError(failureMessage(failure))
    }
  }, [])

  /** 加载示例数据集元信息（九张表的行数与字段说明）。 */
  const loadDataset = useCallback(async (): Promise<void> => {
    setDatasetError(null)
    try {
      setDataset(await fetchDataset())
    } catch (failure) {
      setDatasetError(failureMessage(failure))
    }
  }, [])

  // 首次进入示例数据相关页面时才请求数据集接口。
  useEffect(() => {
    if ((page.kind === 'dataset' || page.kind === 'dataset-table') && dataset === null) {
      void loadDataset()
    }
  }, [page.kind, dataset, loadDataset])

  // 「数据科学」菜单条目随面板首次加载一起取回。
  useEffect(() => {
    let cancelled = false
    void fetchDataDocs()
      .then(list => {
        if (!cancelled) setDocs(list)
      })
      .catch(() => {
        if (!cancelled) setDocs([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  const docPath = page.kind === 'science' ? page.doc : null

  // 切换文档时重新读取 Markdown。
  useEffect(() => {
    if (docPath === null) return undefined
    let cancelled = false
    setDocLoading(true)
    setDocError(null)
    void fetchDataDoc(docPath)
      .then(content => {
        if (!cancelled) setDoc(content)
      })
      .catch(failure => {
        if (!cancelled) {
          setDoc(null)
          setDocError(failureMessage(failure))
        }
      })
      .finally(() => {
        if (!cancelled) setDocLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [docPath, docReload])

  /** 「数据科学」父菜单：展开/收起，首次展开时进入分析框架。 */
  const handleScienceToggle = useCallback((): void => {
    setScienceOpen(open => {
      const next = !open
      if (next) {
        setPage(current => (current.kind === 'science' ? current : { kind: 'science', doc: 'README.md' }))
      }
      return next
    })
  }, [])

  /** 「示例数据」父菜单：展开/收起，未进入过该栏目时跳到概览页。 */
  const handleDatasetToggle = useCallback((): void => {
    setDatasetOpen(open => {
      const next = !open
      if (next) {
        setPage(current =>
          current.kind === 'dataset' || current.kind === 'dataset-table' || current.kind === 'science'
            ? current
            : { kind: 'dataset' },
        )
      }
      return next
    })
  }, [])

  /** 在示例数据栏目内跳转时保持菜单展开。 */
  const handleSelect = useCallback((next: Page): void => {
    if (next.kind === 'dataset' || next.kind === 'dataset-table') setDatasetOpen(true)
    if (next.kind === 'science') {
      setDatasetOpen(true)
      setScienceOpen(true)
    }
    setPage(next)
  }, [])

  return (
    <div className="dsd-app">
      <Banner page={page} docTitle={doc?.title ?? null} />
      <div className="dsd-body">
        <Sidebar
          page={page}
          collapsed={collapsed}
          datasetOpen={datasetOpen}
          scienceOpen={scienceOpen}
          docs={docs}
          onToggle={() => setCollapsed(value => !value)}
          onDatasetToggle={handleDatasetToggle}
          onScienceToggle={handleScienceToggle}
          onSelect={handleSelect}
        />
        <main className="dsd-main">
          {page.kind === 'home' ? (
            <HomePage />
          ) : page.kind === 'environment' ? (
            <EnvironmentPage
              report={report}
              loading={loading}
              error={error}
              install={install}
              onInstall={() => void handleInstall()}
              onRefresh={() => void refresh()}
            />
          ) : page.kind === 'dataset' ? (
            <DatasetOverviewPage
              dataset={dataset}
              error={datasetError}
              onRetry={() => void loadDataset()}
              onOpenTable={table => handleSelect({ kind: 'dataset-table', table })}
            />
          ) : page.kind === 'dataset-table' ? (
            <DatasetTablePage
              key={page.table}
              table={page.table}
              meta={dataset?.tables.find(table => table.name === page.table) ?? null}
            />
          ) : (
            <DocView
              doc={doc}
              loading={docLoading}
              error={docError}
              onRetry={() => setDocReload(value => value + 1)}
              onNavigate={path => handleSelect({ kind: 'science', doc: path })}
            />
          )}
        </main>
      </div>
    </div>
  )
}
