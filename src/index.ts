/**
 * dsh-datascience-demo — 宿主端入口。
 *
 * 界面在浏览器端（src/client）。宿主端注册两组能力：
 *  - `/api/dsh-datascience/environment`：探测本机 Python / 包管理器 / 依赖；
 *  - `/api/dsh-datascience/install`：启动环境安装并轮询过程日志。
 */

import type { HostContext } from './host-context.ts'
import { makeRoutes } from './routes.ts'
import { InstallController } from './env/install.ts'

/** 稳定的 cordis 插件名（与 cordis.patch.yml 中的 id 对应）。 */
export const name = 'datascience-demo'

/** 宿主侧只需要 web-server 的路由注册能力。 */
export const inject = ['webServer']

/** 注册路由；随插件卸载一起释放。 */
export function apply(ctx: HostContext): void {
  const install = new InstallController()
  const { routes } = makeRoutes({ install })

  ctx.effect(() => {
    const disposers = routes.map(route => ctx.webServer.register(route))
    return () => {
      for (const dispose of disposers) dispose()
    }
  }, 'dsh-datascience-demo: api routes')
}
