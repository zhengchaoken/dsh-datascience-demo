/**
 * 面板主体：banner 导航 + 可折叠侧边菜单 + 首页 / 环境检查两个页面。
 */

import { useCallback, useEffect, useRef, useState, type ReactElement } from 'react'
import type { EnvironmentReport, InstallState } from '../protocol.ts'
import { ApiError, fetchEnvironment, fetchInstallState, startInstall } from './api.ts'

/** 页面标识。 */
type Page = 'home' | 'environment'

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

/** 顶部 banner：一级/二级导航与整体环境状态。 */
function Banner({ page, report }: { page: Page; report: EnvironmentReport | null }): ReactElement {
  const state = report === null ? '检测中' : report.ready ? '环境就绪' : '待配置'
  const tone = report === null ? '' : report.ready ? ' is-ok' : ' is-warning'
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
        <span>首页</span>
        {page === 'environment' ? (
          <>
            <span className="dsd-crumb-sep">/</span>
            <span className="dsd-crumb-current">环境检查</span>
          </>
        ) : null}
      </nav>
      <span className={`dsd-banner-status${tone}`}>
        <span className="dsd-status-dot" />
        {state}
      </span>
    </header>
  )
}

/** 左侧可收缩菜单。 */
function Sidebar({
  page,
  collapsed,
  onToggle,
  onSelect,
}: {
  page: Page
  collapsed: boolean
  onToggle: () => void
  onSelect: (page: Page) => void
}): ReactElement {
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
            className={`dsd-rail-button${page === 'home' ? ' is-active' : ''}`}
            onClick={() => onSelect('home')}
            title="首页"
            aria-label="首页"
          >
            <IconHome />
          </button>
          <button
            className={`dsd-rail-button${page === 'environment' ? ' is-active' : ''}`}
            onClick={() => onSelect('environment')}
            title="环境检查"
            aria-label="环境检查"
          >
            <IconEnv />
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
          className={`dsd-menu-item dsd-menu-parent${page === 'home' ? ' is-active' : ''}`}
          onClick={() => onSelect('home')}
        >
          <IconHome />
          <span className="dsd-menu-label">首页</span>
          <span className="dsd-chevron">
            <IconChevron direction="down" size={11} />
          </span>
        </button>
        <div className="dsd-menu-sub">
          <button
            className={`dsd-menu-item${page === 'environment' ? ' is-active' : ''}`}
            onClick={() => onSelect('environment')}
          >
            <IconEnv />
            <span className="dsd-menu-label">环境检查</span>
          </button>
        </div>
      </div>
    </aside>
  )
}

/** 首页：插件简介。 */
function HomePage({ report }: { report: EnvironmentReport | null }): ReactElement {
  const environmentText =
    report === null ? '正在检测本机环境…' : report.ready ? '本机环境已就绪，可以开始分析。' : '本机环境尚未配置，请前往环境检查。'
  return (
    <section className="dsd-page dsd-home">
      <div className="dsd-hero">
        <div className="dsd-hero-copy">
          <span className="dsd-eyebrow">DATA SCIENCE WORKBENCH</span>
          <h1>数据科学示例</h1>
          <p>
            一个运行在 DSH 中的数据科学工作台示例。先检查本机 Python 3.12 环境与依赖，
            再在统一的浅色工作区里组织分析流程。
          </p>
          <div className="dsd-hero-meta">
            <span className="dsd-pill">Python 3.12</span>
            <span className="dsd-pill">依赖清单驱动</span>
            <span className="dsd-pill">本地执行</span>
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
            探测本机 Python 版本、解释器路径、pip 以及 conda / mamba，结果实时展示。
          </p>
        </div>
        <div className="dsd-feature">
          <div className="dsd-feature-title">
            <span className="dsd-feature-icon">
              <IconHome size={15} />
            </span>
            自动安装
          </div>
          <p className="dsd-feature-body">
            缺少 Python 或依赖时，一键安装 Python 3.12 与依赖清单中的包，过程日志可见。
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
            依赖统一放在 requirements.txt，新增包只需写进该文件，检查与安装都会自动读取。
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
            当前提供环境检查示例，后续的数据分析能力会作为新的子菜单逐步加入。
          </p>
        </div>
      </div>

      <div className="dsd-link-note">{environmentText}</div>
    </section>
  )
}

/** 环境检查页。 */
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

  useEffect(() => {
    const element = logRef.current
    if (element !== null) element.scrollTop = element.scrollHeight
  }, [logs.length])

  const pythonMissing = report !== null && (!report.python.found || !report.python.versionOk)
  const missingDependencies =
    report === null ? [] : report.dependencies.filter(dependency => !dependency.installed)
  const needsInstall = pythonMissing || missingDependencies.length > 0
  const installLabel = pythonMissing ? '安装 Python 3.12 与依赖' : '安装缺失依赖'

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
          <p className="dsd-page-sub">检查本机 Python 3.12、环境管理器与依赖清单。</p>
        </div>
        <div className="dsd-toolbar">
          <button className="dsd-button" onClick={onRefresh} disabled={loading || installing}>
            <IconRefresh />
            刷新
          </button>
          {needsInstall ? (
            <button className="dsd-button is-primary" onClick={onInstall} disabled={installing || loading}>
              {installing ? '正在安装…' : installLabel}
            </button>
          ) : null}
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
          <div className="dsd-env-grid">
            <div className="dsd-card">
              <div className="dsd-card-head">
                <span className="dsd-card-label">系统</span>
                <span className="dsd-card-flag is-ok">
                  <span className="dsd-status-dot" />
                  {report.system.arch}
                </span>
              </div>
              <div className="dsd-kv">
                <div className="dsd-kv-row">
                  <span className="dsd-kv-key">系统</span>
                  <span className="dsd-kv-value">{report.system.type} {report.system.release}</span>
                </div>
                <div className="dsd-kv-row">
                  <span className="dsd-kv-key">架构</span>
                  <span className="dsd-kv-value">{report.system.arch} · {report.system.platform}</span>
                </div>
                <div className="dsd-kv-row">
                  <span className="dsd-kv-key">Node</span>
                  <span className="dsd-kv-value dsd-mono">{report.system.node}</span>
                </div>
              </div>
            </div>

            <div className="dsd-card">
              <div className="dsd-card-head">
                <span className="dsd-card-label">Python</span>
                <span className={`dsd-card-flag ${report.python.found && report.python.versionOk ? 'is-ok' : 'is-bad'}`}>
                  <span className="dsd-status-dot" />
                  {!report.python.found ? '未找到' : report.python.versionOk ? '可用' : '版本不符'}
                </span>
              </div>
              <div className="dsd-kv">
                <div className="dsd-kv-row">
                  <span className="dsd-kv-key">版本</span>
                  <span className="dsd-kv-value dsd-mono">{report.python.version ?? '—'}</span>
                </div>
                <div className="dsd-kv-row">
                  <span className="dsd-kv-key">pip</span>
                  <span className="dsd-kv-value dsd-mono">{report.python.pipVersion ?? '未检测到'}</span>
                </div>
                <div className="dsd-kv-row">
                  <span className="dsd-kv-key">路径</span>
                  <span className="dsd-kv-value dsd-mono">{report.python.executable ?? '—'}</span>
                </div>
              </div>
            </div>

            <div className="dsd-card">
              <div className="dsd-card-head">
                <span className="dsd-card-label">环境管理器</span>
                <span className={`dsd-card-flag ${report.managers.length > 0 ? 'is-ok' : 'is-bad'}`}>
                  <span className="dsd-status-dot" />
                  {report.managers.length > 0 ? `${report.managers.length} 个` : '未检测到'}
                </span>
              </div>
              {report.managers.length > 0 ? (
                <div className="dsd-kv">
                  {report.managers.map(manager => (
                    <div className="dsd-kv-row" key={manager.name}>
                      <span className="dsd-kv-key">{manager.name}</span>
                      <span className="dsd-kv-value dsd-mono">{manager.version}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="dsd-empty">没有 conda / mamba，自动安装时会使用 python.org 官方安装包。</div>
              )}
            </div>

            <div className="dsd-card dsd-card-wide">
              <div className="dsd-card-head">
                <span className="dsd-card-label">依赖清单</span>
                <span className={`dsd-card-flag ${missingDependencies.length > 0 ? 'is-bad' : 'is-ok'}`}>
                  <span className="dsd-status-dot" />
                  {report.dependencies.length === 0
                    ? '清单为空'
                    : missingDependencies.length === 0
                      ? '全部已安装'
                      : `缺少 ${missingDependencies.length} 项`}
                </span>
              </div>
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
                        <span>{dependency.requirement || '未安装'}</span>
                      )}
                    </span>
                  ))}
                </div>
              )}
              {report.dependenciesError !== null ? (
                <div className="dsd-link-note">读取依赖状态时出错：{report.dependenciesError}</div>
              ) : null}
              <div className="dsd-link-note">清单文件：{report.requirementsFile}</div>
            </div>
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
                : '安装使用本机已有的 Python 3.12；没有时优先使用 mamba / conda，最后回退到 python.org 官方安装包。'}
            </div>
          </div>
        </>
      )}
    </section>
  )
}

/** 面板根组件。 */
export function App(): ReactElement {
  const [page, setPage] = useState<Page>('home')
  const [collapsed, setCollapsed] = useState(false)
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
      setError(failure instanceof ApiError ? failure.message : failure instanceof Error ? failure.message : String(failure))
    }
  }, [])

  return (
    <div className="dsd-app">
      <Banner page={page} report={report} />
      <div className="dsd-body">
        <Sidebar
          page={page}
          collapsed={collapsed}
          onToggle={() => setCollapsed(value => !value)}
          onSelect={setPage}
        />
        <main className="dsd-main">
          {page === 'home' ? (
            <HomePage report={report} />
          ) : (
            <EnvironmentPage
              report={report}
              loading={loading}
              error={error}
              install={install}
              onInstall={() => void handleInstall()}
              onRefresh={() => void refresh()}
            />
          )}
        </main>
      </div>
    </div>
  )
}
