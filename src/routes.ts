/**
 * `/api/dsh-datascience` 路由族：环境检查与安装任务。
 *
 * 路由是用户界面触发的操作，与在终端里执行命令同属用户授权范围；模型工具
 * 不经过这里。
 */

import type { IncomingMessage, ServerResponse } from 'node:http'
import type { WebRoute } from './webserver-types.ts'
import { errorMessage, writeError, writeJson } from './http.ts'
import { probeEnvironment } from './env/probe.ts'
import type { InstallController } from './env/install.ts'

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
          writeJson(res, 202, install.start())
          return
        }
        writeError(res, 405, '只支持 GET 或 POST')
        return
      }

      writeError(res, 404, '接口不存在')
    } catch (failure) {
      writeError(res, 500, errorMessage(failure))
    }
  }

  return { routes: [{ kind: 'prefix', path: '/api/dsh-datascience', handler }] }
}
