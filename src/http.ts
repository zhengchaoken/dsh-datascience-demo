/**
 * 极小的 JSON 响应辅助函数。本插件只拥有一组路由，因此不引入额外依赖。
 */

import type { IncomingMessage, OutgoingHttpHeaders, ServerResponse } from 'node:http'

const JSON_HEADERS = {
  'content-type': 'application/json; charset=utf-8',
  'referrer-policy': 'no-referrer',
  'cache-control': 'no-store',
} satisfies OutgoingHttpHeaders

/** 写一个 JSON 响应。 */
export function writeJson(
  res: ServerResponse,
  status: number,
  body: unknown,
  headers: OutgoingHttpHeaders = {},
): void {
  res.writeHead(status, { ...JSON_HEADERS, ...headers })
  res.end(JSON.stringify(body))
}

/** 写一个 JSON 错误响应。 */
export function writeError(res: ServerResponse, status: number, message: string): void {
  writeJson(res, status, { error: message })
}

/** 读取并解析 JSON 请求体；超过 64KB 或不是 JSON 时抛出可读错误。 */
export async function readJsonBody(req: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = []
  let size = 0
  for await (const chunk of req) {
    size += (chunk as Buffer).length
    if (size > 64 * 1024) throw new Error('请求体过大')
    chunks.push(chunk as Buffer)
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'))
  } catch {
    throw new Error('请求体不是合法 JSON')
  }
}

/** 把未知异常转成可读文案。 */
export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}
