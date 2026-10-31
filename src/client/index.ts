/**
 * dsh-datascience-demo — 浏览器端入口。
 *
 * 两个槽位注册，全部走 dsh 官方的 slots 扩展点：
 *
 * - `sidebar.panellist`（list）：左侧边栏的「数据科学示例」入口，和插件
 *   自带的「插件」入口位于同一列。点击后 shell 会调用
 *   `layout.selectPanel('datascience-demo')`。
 * - `main`（keyed）：右侧（中央列）的空白面板。当 `activePanelId` 等于
 *   `datascience-demo` 时 shell 渲染它；点击任意会话行则自动回到会话。
 *
 * 失败策略：挂载异常只记录日志，绝不抛出。client 插件抛出会拖垮整个 web
 * 启动，外部插件不能有这种能力。
 */

import * as React from 'react'

/** 面板 id，同时是 `main` 槽位的 key 与侧边栏条目的 id。 */
const PANEL_ID = 'datascience-demo'

/** 侧边栏条目 id（`sidebar.panellist` 的注册 id）。 */
const ENTRY_ID = 'datascience-demo'

/** 侧边栏菜单文案。 */
const ENTRY_LABEL = '数据科学示例'

/** 条目在侧边栏列表中的顺序。 */
const ENTRY_ORDER = 20

/** 浏览器端依赖的服务：`slots` 由 ui-renderer 提供。 */
export const inject = ['slots']

/** 浏览器端插件上下文的最小结构。 */
interface ClientContext {
  effect(effect: () => unknown, label?: string): () => void
  slots: {
    inject(key: string, callback: () => () => void): () => void
    register(options: Record<string, unknown>, component: unknown): () => void
  }
}

/** 16px 边长的图表图标，保持与 shell 自带侧边栏图标同一视觉重量。 */
const ICON = (size: number): string =>
  '<svg viewBox="0 0 16 16" width="' + size + '" height="' + size + '" fill="none" stroke="currentColor" ' +
  'stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M2 13.5V2.5"/>' +
  '<path d="M2 13.5h12"/>' +
  '<path d="M4.8 11.5V8.2"/>' +
  '<path d="M8 11.5V5.4"/>' +
  '<path d="M11.2 11.5V7"/>' +
  '</svg>'

/** 挂载侧边栏入口与空白面板。 */
export function apply(ctx: ClientContext): void {
  // ---- 侧边栏入口 --------------------------------------------------------
  ctx.effect(() => {
    try {
      return ctx.slots.inject('sidebar.panellist', () =>
        ctx.slots.register(
          {
            name: 'sidebar.panellist',
            id: ENTRY_ID,
            order: ENTRY_ORDER,
            label: () => ENTRY_LABEL,
          },
          (props: { size?: number }) =>
            React.createElement('span', {
              'data-dsh-dsd-entry': ENTRY_ID,
              dangerouslySetInnerHTML: { __html: ICON(props.size ?? 16) },
            }),
        ),
      )
    } catch (failure) {
      console.warn('[dsh-datascience-demo] sidebar entry mount failed:', failure)
      return () => {}
    }
  }, 'dsh-datascience-demo: sidebar entry')

  // ---- 右侧空白面板 ------------------------------------------------------
  ctx.effect(() => {
    try {
      return ctx.slots.inject('main', () =>
        ctx.slots.register(
          { name: 'main', key: PANEL_ID },
          () =>
            React.createElement('div', {
              className: 'dsd-root',
              style: { flex: '1 1 auto', width: '100%', height: '100%', minHeight: 0 },
            }),
        ),
      )
    } catch (failure) {
      console.warn('[dsh-datascience-demo] panel mount failed:', failure)
      return () => {}
    }
  }, 'dsh-datascience-demo: panel')
}
