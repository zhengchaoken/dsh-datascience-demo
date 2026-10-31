/**
 * 宿主 web-server 路由契约的结构化副本。
 *
 * 插件不在构建期依赖 `@deepseek-ai/dsh-host-webserver`，只在运行时从上下文
 * 拿到 `webServer` 服务并调用 `register()`；把用到的形状在本地声明，源码即可
 * 独立类型检查。
 */

import type { IncomingMessage, ServerResponse } from 'node:http'

/** 路由匹配方式：exact 精确匹配，prefix 匹配 `/p` 与 `/p/...`。 */
export type WebRouteKind = 'exact' | 'prefix'

/** 一条 HTTP 路由。 */
export interface WebRoute {
  kind: WebRouteKind
  /** 绝对路径，不带结尾斜杠。 */
  path: string
  /** 自行负责完整的响应生命周期。 */
  handler: (req: IncomingMessage, res: ServerResponse) => void | Promise<void>
}

/** 插件用到的 web-server 能力切片。 */
export interface WebServerService {
  register(route: WebRoute): () => void
}
