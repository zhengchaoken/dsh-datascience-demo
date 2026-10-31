/**
 * 面板主体：banner 导航 + 可折叠侧边菜单 + 首页 / 环境检查 / 示例数据页面。
 */

import { useCallback, useEffect, useRef, useState, type ReactElement } from 'react'
import type {
  DatasetInfo,
  DatasetQueryResult,
  DatasetTableInfo,
  EnvironmentReport,
  InstallState,
} from '../protocol.ts'
import {
  ApiError,
  fetchDataset,
  fetchEnvironment,
  fetchInstallState,
  runDatasetQuery,
  startInstall,
} from './api.ts'

/** 页面标识：示例数据下挂概览页与九张表页。 */
type Page =
  | { kind: 'home' }
  | { kind: 'environment' }
  | { kind: 'dataset' }
  | { kind: 'dataset-table'; table: string }

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
function Banner({ page }: { page: Page }): ReactElement {
  const trail: string[] = ['首页']
  if (page.kind === 'environment') trail.push('环境检查')
  if (page.kind === 'dataset') trail.push('示例数据')
  if (page.kind === 'dataset-table') {
    trail.push('示例数据', DATASET_MENU.find(item => item.name === page.table)?.label ?? page.table)
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

/** 左侧可收缩菜单：首页、环境检查、示例数据（父菜单，下挂九张表）。 */
function Sidebar({
  page,
  collapsed,
  datasetOpen,
  onToggle,
  onDatasetToggle,
  onSelect,
}: {
  page: Page
  collapsed: boolean
  datasetOpen: boolean
  onToggle: () => void
  onDatasetToggle: () => void
  onSelect: (page: Page) => void
}): ReactElement {
  const inDataset = page.kind === 'dataset' || page.kind === 'dataset-table'

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
            一个运行在 DSH 中的数据科学工作台示例。它负责准备本机分析环境：
            检查 Python、在工作目录中创建独立虚拟环境，并按清单安装常用分析库。
          </p>
          <div className="dsd-hero-meta">
            <span className="dsd-pill">Python 3.12</span>
            <span className="dsd-pill">.venv 隔离环境</span>
            <span className="dsd-pill">依赖清单驱动</span>
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
              <IconChevron direction="down" size={15} />
            </span>
            可扩展
          </div>
          <p className="dsd-feature-body">
            当前提供环境准备能力，后续的数据分析功能会作为新的菜单逐步加入。
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

/** 概览页的关键业务术语（口径来自 src/data/README.md）。 */
const DATASET_TERMS: { term: string; definition: string; sql: string }[] = [
  { term: 'GMV', definition: '已完成+已发货订单的实付合计', sql: "SUM(total_amount) WHERE order_status IN ('已完成','已发货')" },
  { term: '客单价', definition: 'GMV / 订单数', sql: 'SUM(total_amount) / COUNT(*)' },
  { term: '件单价', definition: 'GMV / 销售件数', sql: 'SUM(total) / SUM(quantity)' },
  { term: '连带率', definition: '平均每单商品件数', sql: 'SUM(quantity) / COUNT(DISTINCT order_id)' },
  { term: '复购率', definition: '购买 ≥2 次的客户占比', sql: '按 customer_id 分组计数' },
  { term: '退款率', definition: '已退款支付单占比', sql: "payments.payment_status = '已退款'" },
  { term: '转化率', definition: '浏览→加购→购买漏斗比例', sql: 'user_events 按 event_type 统计' },
  { term: '动销率', definition: '有销量的商品占比', sql: 'order_items 去重 product_id / products' },
  { term: '毛利率', definition: '(成交额-成本) / 成交额', sql: 'subtotal - cost×quantity' },
  { term: 'RFM', definition: '最近消费 / 频率 / 金额三维分群', sql: '基于 orders 按客户聚合' },
]

/** 概览页的表间关系要点（来自 src/data/README.md 第 3 节）。 */
const DATASET_RELATIONS: string[] = [
  'orders ↔ products 是多对多，靠 order_items 连接，分析销量必须 JOIN 明细表',
  '金额链路：orders.total_amount = Σ(order_items.subtotal) + freight_amount；Σ(item_discount) = orders.discount_amount',
  '状态机：待付款 →（支付）→ 已发货 →（签收）→ 已完成，任何阶段可转为已取消',
  '行为-交易闭环：user_events（浏览/加购）发生在 orders.created_at 之前，可构造「浏览→加购→购买」漏斗',
  '评价只挂在已完成订单上，rating 分布由商品 quality_score 驱动',
]

/** 示例数据概览页：整体介绍电商数据集（内容基于 src/data/README.md）。 */
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
            DataClerk 式确定性生成的多表关联电商数据，L1~L5 各层分析示例的统一数据源。
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
            title="生成机制"
            subtitle="同一份生成脚本在任何时间、任何机器上产出字节级一致的数据库"
            status={<Flag ok>种子 42</Flag>}
          />
          <div className="dsd-kv-grid">
            <div className="dsd-kv-row dsd-kv-wide">
              <span className="dsd-kv-key">显式随机源</span>
              <span className="dsd-kv-value">全程只用 random.Random(42)，不触碰全局 random</span>
            </div>
            <div className="dsd-kv-row dsd-kv-wide">
              <span className="dsd-kv-key">锚定日期</span>
              <span className="dsd-kv-value">所有日期相对固定的 2025-06-15 生成，不读系统时钟</span>
            </div>
            <div className="dsd-kv-row dsd-kv-wide">
              <span className="dsd-kv-key">生成顺序</span>
              <span className="dsd-kv-value">类目 → 客户 → 商品 → 订单 → 支付 → 评价 → 行为事件</span>
            </div>
            <div className="dsd-kv-row dsd-kv-wide">
              <span className="dsd-kv-key">金额精度</span>
              <span className="dsd-kv-value">金额一律保留两位小数；两次生成 SHA256 相同（c957ca93…）</span>
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
            埋入的模式：双 11、618 大促峰值，春节低谷，周末效应，缓慢增长趋势；约 1.2% 批发型异常订单
            （单件商品数量 30~200）与 0.5% 价格异常订单（单价 ×10）——后两者是 L2 异常检测的靶子。
          </div>
        </section>

        <section className="dsd-card dsd-env-section">
          <SectionHead
            index="03"
            title="表间业务关系"
            subtitle="客户下单 → 订单包含明细 → 明细对应商品；订单关联支付、评价与优惠券"
            status={null}
          />
          <ul className="dsd-fact-list">
            {DATASET_RELATIONS.map(relation => (
              <li key={relation}>{relation}</li>
            ))}
          </ul>
        </section>

        <section className="dsd-card dsd-env-section">
          <SectionHead
            index="04"
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
          已知问题（当前 build）：约 20% 订单存在 shipped_at 时刻早于同日 paid_at 的时刻错位（日期粒度正确），
          系生成器中发货时钟独立随机所致。当前数据库保持原样，各层分析报告均基于此 build 生成。
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

  /** 「示例数据」父菜单：展开/收起，未进入过该栏目时跳到概览页。 */
  const handleDatasetToggle = useCallback((): void => {
    setDatasetOpen(open => {
      const next = !open
      if (next) {
        setPage(current =>
          current.kind === 'dataset' || current.kind === 'dataset-table'
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
    setPage(next)
  }, [])

  return (
    <div className="dsd-app">
      <Banner page={page} />
      <div className="dsd-body">
        <Sidebar
          page={page}
          collapsed={collapsed}
          datasetOpen={datasetOpen}
          onToggle={() => setCollapsed(value => !value)}
          onDatasetToggle={handleDatasetToggle}
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
          ) : (
            <DatasetTablePage
              key={page.table}
              table={page.table}
              meta={dataset?.tables.find(table => table.name === page.table) ?? null}
            />
          )}
        </main>
      </div>
    </div>
  )
}
