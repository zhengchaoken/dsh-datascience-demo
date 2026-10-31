/**
 * 宿主运行时提供的包只在本机 DSH 安装里存在，插件独立检出时不带类型。
 * 这里只声明实际用到的形状，构建时这些包保持 external。
 */

declare module '@deepseek-ai/dsh-tools' {
  /** 注册表可直接接收的工具定义。 */
  export interface ToolDefinition {
    readonly name: string
    readonly description: string
    readonly parameters: Record<string, unknown>
    readonly output: {
      readonly schema: unknown
      render(args: any, value: any): Array<{ type: 'text'; text: string }>
    }
    execute(args: any, exec?: any): Promise<unknown>
  }

  /** 定义一个带类型的工具；返回值可直接交给 tools.register。 */
  export function defineTool(options: any): ToolDefinition
}
