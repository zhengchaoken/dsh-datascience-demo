/**
 * 独立 Web 入口：把与 DSH 面板完全相同的 {@link App} 挂到普通浏览器上。
 *
 * 与 DSH 侧的区别只在外壳——那边由 slots 注册到右侧工作区，这里直接
 * createRoot，并把同一份 APP_CSS 注入 document.head；App 与 API 客户端零改动。
 */

import * as React from 'react'
import { createRoot } from 'react-dom/client'
import { App } from '../client/App.tsx'
import { APP_CSS } from '../client/styles.ts'

/** 与插件侧一致的样式标记，便于去重。 */
const PLUGIN_ID = 'dsh-datascience-demo'

/** 注入面板样式；已存在时跳过。 */
function installStyles(): void {
  if (document.querySelector(`style[data-plugin-css="${PLUGIN_ID}"]`) !== null) return
  const tag = document.createElement('style')
  tag.dataset['plugin'] = PLUGIN_ID
  tag.dataset['pluginCss'] = PLUGIN_ID
  tag.textContent = APP_CSS
  document.head.appendChild(tag)
}

const container = document.getElementById('root')
if (container === null) {
  console.error('[dsh-datascience-demo] 缺少 #root 容器，无法挂载面板')
} else {
  installStyles()
  createRoot(container).render(
    React.createElement(
      'div',
      { style: { display: 'flex', height: '100vh', minHeight: 0 } },
      React.createElement(App),
    ),
  )
}
