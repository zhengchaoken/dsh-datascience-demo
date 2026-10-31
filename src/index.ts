/**
 * dsh-datascience-demo — 宿主端入口。
 *
 * 注册三组能力：
 *  - `/api/dsh-datascience/environment`：探测本机 Python / 包管理器 / 依赖；
 *  - `/api/dsh-datascience/install`：启动环境安装并轮询过程日志；
 *  - `/api/dsh-datascience/docs`：`src/data` 下的文档与图片资产（面板阅读用）。
 *
 * 同时向模型注册数据科学工具（查询 / 探查 / 运行分析 / 读报告），
 * 并注入一段系统提示，告诉 agent 什么时候用它们。
 */

import { defineTool } from '@deepseek-ai/dsh-tools'
import type { HostContext } from './host-context.ts'
import { makeRoutes } from './routes.ts'
import { InstallController } from './env/install.ts'
import { makeTools, toolGuidance } from './tools.ts'

/** 稳定的 cordis 插件名（与 cordis.patch.yml 中的 id 对应）。 */
export const name = 'datascience-demo'

/** 路由 + 工具注册 + 系统提示注入。 */
export const inject = ['webServer', 'tools', 'systemPrompt']

/** 系统提示区块的顺序（与其它插件的工具说明相邻）。 */
const SECTION_ORDER = 160

/** 注册路由与模型工具；随插件卸载一起释放。 */
export function apply(ctx: HostContext): void {
  const install = new InstallController()
  const { routes } = makeRoutes({ install })

  ctx.effect(() => {
    const disposers = routes.map(route => ctx.webServer.register(route))
    return () => {
      for (const dispose of disposers) dispose()
    }
  }, 'dsh-datascience-demo: api routes')

  const tools = makeTools(defineTool)
  ctx.effect(() => {
    const disposers = tools.map(tool => ctx.tools.register(tool))
    return () => {
      for (const dispose of disposers) dispose()
    }
  }, 'dsh-datascience-demo: agent tools')

  try {
    ctx.systemPrompt?.section({
      name: 'plugin:dsh-datascience-demo',
      order: SECTION_ORDER,
      text: toolGuidance(),
    })
  } catch {
    // 缺少系统提示席位不应影响其余能力：路由与工具才是主体。
  }
}
