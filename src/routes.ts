/**
 * `/api/dsh-datascience` 路由族：环境检查与安装任务。
 *
 * 路由是用户界面触发的操作，与在终端里执行命令同属用户授权范围；模型工具
 * 不经过这里。
 */

import type { IncomingMessage, ServerResponse } from 'node:http'
import type { WebRoute } from './webserver-types.ts'
import { errorMessage, readJsonBody, writeError, writeJson } from './http.ts'
import { probeEnvironment } from './env/probe.ts'
import type { InstallController } from './env/install.ts'
import { describeDataset, runDatasetQuery } from './data/ecommerce/dataset.ts'
import { DATA_DOCS, readDoc, readDocAsset } from './docs/docs.ts'

/** 注册这组路由所需的依赖。 */
export interface RoutesDeps {
  install: InstallController
}

/** 构建路由表。 */
export function makeRoutes(deps: RoutesDeps): { routes: WebRoute[] } {
  const { install } = deps

  const handler = async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
    let pathname: string
    try {
      pathname = new URL(req.url ?? '/', 'http://localhost').pathname
    } catch {
      writeError(res, 400, '请求地址不合法')
      return
    }

    try {
      if (pathname === '/api/dsh-datascience/environment') {
        if (req.method !== 'GET') {
          writeError(res, 405, '只支持 GET')
          return
        }
        writeJson(res, 200, await probeEnvironment(install.getState()))
        return
      }

      if (pathname === '/api/dsh-datascience/install') {
        if (req.method === 'GET') {
          writeJson(res, 200, install.getState())
          return
        }
        if (req.method === 'POST') {
          // 请求体可以缺省；只有 indexUrl 是字符串时才作为自定义源传入。
          const body = await readJsonBody(req).catch(() => null)
          const indexUrl =
            typeof body === 'object' && body !== null
              ? (body as { indexUrl?: unknown }).indexUrl
              : undefined
          writeJson(res, 202, install.start(typeof indexUrl === 'string' ? { indexUrl } : {}))
          return
        }
        writeError(res, 405, '只支持 GET 或 POST')
        return
      }

      if (pathname === '/api/dsh-datascience/dataset') {
        if (req.method !== 'GET') {
          writeError(res, 405, '只支持 GET')
          return
        }
        writeJson(res, 200, await describeDataset())
        return
      }

      if (pathname === '/api/dsh-datascience/dataset/query') {
        if (req.method !== 'POST') {
          writeError(res, 405, '只支持 POST')
          return
        }
        const body = await readJsonBody(req)
        const sql =
          typeof body === 'object' && body !== null ? (body as { sql?: unknown }).sql : undefined
        if (typeof sql !== 'string' || sql.trim() === '') {
          writeError(res, 400, '缺少 SQL 语句')
          return
        }
        try {
          writeJson(res, 200, await runDatasetQuery(sql))
        } catch (failure) {
          // SQL 校验失败与 SQLite 语法错误都属于可预期的用户输入错误，按 400 返回。
          writeError(res, 400, errorMessage(failure))
        }
        return
      }

      if (pathname === '/api/dsh-datascience/docs') {
        if (req.method !== 'GET') {
          writeError(res, 405, '只支持 GET')
          return
        }
        writeJson(res, 200, DATA_DOCS)
        return
      }

      if (pathname === '/api/dsh-datascience/doc') {
        if (req.method !== 'GET') {
          writeError(res, 405, '只支持 GET')
          return
        }
        const target = new URL(req.url ?? '/', 'http://localhost').searchParams.get('path')
        if (target === null || target.trim() === '') {
          writeError(res, 400, '缺少文档路径')
          return
        }
        try {
          writeJson(res, 200, await readDoc(target))
        } catch (failure) {
          writeError(res, 404, errorMessage(failure))
        }
        return
      }

      if (pathname === '/api/dsh-datascience/doc-asset') {
        if (req.method !== 'GET') {
          writeError(res, 405, '只支持 GET')
          return
        }
        const target = new URL(req.url ?? '/', 'http://localhost').searchParams.get('path')
        if (target === null || target.trim() === '') {
          writeError(res, 400, '缺少资源路径')
          return
        }
        try {
          const asset = await readDocAsset(target)
          res.writeHead(200, {
            'content-type': asset.mime,
            'cache-control': 'public, max-age=3600',
          })
          res.end(asset.content)
        } catch (failure) {
          writeError(res, 404, errorMessage(failure))
        }
        return
      }

      writeError(res, 404, '接口不存在')
    } catch (failure) {
      writeError(res, 500, errorMessage(failure))
    }
  }

  return { routes: [{ kind: 'prefix', path: '/api/dsh-datascience', handler }] }
}
