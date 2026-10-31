/**
 * 宿主端插件上下文的最小结构：只声明本插件实际使用的两个成员。
 */

import type { WebServerService } from './webserver-types.ts'

/** 宿主插件上下文。 */
export interface HostContext {
  /** 注册随插件生命周期释放的清理函数。 */
  effect(effect: () => () => void, label?: string): () => void
  /** dsh 提供的 web-server 服务。 */
  webServer: WebServerService
}
