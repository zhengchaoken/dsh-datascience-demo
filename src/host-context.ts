/**
 * 宿主端插件上下文的最小结构：只声明本插件实际使用的成员。
 */

import type { WebServerService } from './webserver-types.ts'

/** 系统提示区块参数。 */
export interface SystemPromptSection {
  name: string
  order: number
  text: string
}

/** 宿主插件上下文。 */
export interface HostContext {
  /** 注册随插件生命周期释放的清理函数。 */
  effect(effect: () => () => void, label?: string): () => void
  /** dsh 提供的 web-server 服务。 */
  webServer: WebServerService
  /** 模型工具注册表。 */
  tools: {
    register(definition: unknown): () => void
  }
  /** 系统提示注入点；缺失时只跳过提示，不影响路由与工具。 */
  systemPrompt?: {
    section(section: SystemPromptSection): () => void
  }
}
