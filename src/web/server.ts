/**
 * 独立 Web 服务：自己监听端口，托管面板静态产物与插件已有的 `/api/dsh-datascience` 路由。
 *
 * 与 DSH 插件共用同一份后端实现（routes / probe / install / dataset / docs），
 * 区别只是把「向宿主 webServer 注册路由」换成「自己 createServer」。
 *
 * 用法：node dist-web/server.mjs [--port 5180] [--host 127.0.0.1] [--workspace <目录>]
 */

import { createServer } from 'node:http'
import { existsSync, readFileSync } from 'node:fs'
import { networkInterfaces } from 'node:os'
import { dirname, extname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { InstallController } from '../env/install.ts'
import { makeRoutes } from '../routes.ts'

/** 插件 API 的统一前缀，与 DSH 侧完全一致。 */
const API_PREFIX = '/api/dsh-datascience'

const DEFAULT_PORT = 5180
const DEFAULT_HOST = '127.0.0.1'

/** 产物目录：server.mjs 与 index.html、assets/ 同层。 */
const WEB_ROOT = dirname(fileURLToPath(import.meta.url))

/** 静态文件的 MIME 类型。 */
const MIME_BY_EXTENSION: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
}

/** 取命令行参数值，例如 `--port 5180`。 */
function argValue(flag: string): string | null {
  const index = process.argv.indexOf(flag)
  if (index === -1) return null
  const value = process.argv[index + 1]
  return value === undefined || value.startsWith('--') ? null : value
}

/** 端口解析失败时回退默认值。 */
function parsePort(raw: string | null): number {
  const value = raw === null ? DEFAULT_PORT : Number(raw)
  return Number.isInteger(value) && value > 0 && value < 65536 ? value : DEFAULT_PORT
}

/** 只放行首页与 assets 下的单层文件，避免路径穿越。 */
function resolveStatic(pathname: string): string | null {
  if (pathname === '/' || pathname === '/index.html') return join(WEB_ROOT, 'index.html')
  const match = /^\/assets\/([A-Za-z0-9._-]+)$/.exec(pathname)
  return match === null ? null : join(WEB_ROOT, 'assets', match[1]!)
}

/** 工作目录：命令行优先，其次 DSD_WORKSPACE，默认保持当前目录。 */
const workspaceArg = argValue('--workspace') ?? process.env['DSD_WORKSPACE'] ?? null
if (workspaceArg !== null && workspaceArg.trim() !== '') {
  const workspace = resolve(workspaceArg.trim())
  process.env['DSD_WORKSPACE'] = workspace
  process.chdir(workspace)
}

const install = new InstallController()
const { routes } = makeRoutes({ install })
const apiHandler = routes[0]!.handler

const port = parsePort(argValue('--port') ?? process.env['DSD_WEB_PORT'] ?? null)
const host = argValue('--host') ?? process.env['DSD_WEB_HOST'] ?? DEFAULT_HOST

const server = createServer((req, res) => {
  void (async () => {
    let pathname: string
    try {
      pathname = new URL(req.url ?? '/', 'http://localhost').pathname
    } catch {
      res.writeHead(400, { 'content-type': 'text/plain; charset=utf-8' })
      res.end('请求地址不合法')
      return
    }

    if (pathname === API_PREFIX || pathname.startsWith(`${API_PREFIX}/`)) {
      await apiHandler(req, res)
      return
    }

    const file = resolveStatic(pathname)
    if (file === null || !existsSync(file)) {
      res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' })
      res.end('页面不存在')
      return
    }

    res.writeHead(200, {
      'content-type': MIME_BY_EXTENSION[extname(file)] ?? 'application/octet-stream',
      'cache-control': 'no-cache',
    })
    res.end(readFileSync(file))
  })().catch((failure: unknown) => {
    if (!res.headersSent) res.writeHead(500, { 'content-type': 'text/plain; charset=utf-8' })
    res.end(`服务异常：${failure instanceof Error ? failure.message : String(failure)}`)
  })
})

/** 列出本机的非回环 IPv4 地址，用于提示外部可用的访问地址。 */
function lanAddresses(): string[] {
  const addresses: string[] = []
  for (const list of Object.values(networkInterfaces())) {
    for (const item of list ?? []) {
      if (item.family === 'IPv4' && !item.internal) addresses.push(item.address)
    }
  }
  return addresses
}

/** 监听通配地址时，对外提示本机回环与各网卡地址。 */
function printStartup(): void {
  const wildcard = host === '0.0.0.0' || host === '::'
  console.log(`数据科学 Web 面板：http://${wildcard ? '127.0.0.1' : host}:${port}`)
  if (wildcard) {
    const addresses = lanAddresses()
    console.log(
      addresses.length === 0
        ? '外部访问：未检测到可用网卡，请确认网络连接'
        : `外部访问：${addresses.map(address => `http://${address}:${port}`).join('、')}`,
    )
  }
  console.log(`工作目录：${process.cwd()}`)
  console.log(`静态资源：${WEB_ROOT}`)
}

server.listen(port, host, printStartup)

for (const signal of ['SIGINT', 'SIGTERM'] as const) {
  process.on(signal, () => {
    server.close(() => process.exit(0))
  })
}
