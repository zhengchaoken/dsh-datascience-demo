/**
 * 浏览器端 API 客户端：同源 fetch，只访问本插件的路由前缀。
 */

import type {
  DataDocContent,
  DataDocEntry,
  DatasetInfo,
  DatasetQueryResult,
  EnvironmentReport,
  InstallState,
} from '../protocol.ts'

const BASE = '/api/dsh-datascience'

/** 携带服务端错误信息的异常。 */
export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** 解析 JSON 响应，失败时抛出可读错误。 */
async function readJson<T>(response: Response): Promise<T> {
  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new ApiError(`HTTP ${response.status}：响应不是合法 JSON`, response.status)
  }
  if (!response.ok) {
    const message =
      typeof body === 'object' && body !== null && typeof (body as { error?: unknown }).error === 'string'
        ? (body as { error: string }).error
        : `HTTP ${response.status}`
    throw new ApiError(message, response.status)
  }
  return body as T
}

/** 探测环境。 */
export async function fetchEnvironment(): Promise<EnvironmentReport> {
  const response = await fetch(`${BASE}/environment`, {
    headers: { accept: 'application/json' },
  })
  return readJson<EnvironmentReport>(response)
}

/** 读取安装任务状态与日志。 */
export async function fetchInstallState(): Promise<InstallState> {
  const response = await fetch(`${BASE}/install`, {
    headers: { accept: 'application/json' },
  })
  return readJson<InstallState>(response)
}

/** 启动安装任务；`indexUrl` 留空表示使用默认国内镜像。 */
export async function startInstall(indexUrl?: string): Promise<InstallState> {
  const url = (indexUrl ?? '').trim()
  const response = await fetch(`${BASE}/install`, {
    method: 'POST',
    headers: { accept: 'application/json', 'content-type': 'application/json' },
    body: JSON.stringify(url === '' ? {} : { indexUrl: url }),
  })
  return readJson<InstallState>(response)
}

/** 读取示例数据集（九张表的元信息与行数）。 */
export async function fetchDataset(): Promise<DatasetInfo> {
  const response = await fetch(`${BASE}/dataset`, {
    headers: { accept: 'application/json' },
  })
  return readJson<DatasetInfo>(response)
}

/** 执行一条只读 SELECT 查询。 */
export async function runDatasetQuery(sql: string): Promise<DatasetQueryResult> {
  const response = await fetch(`${BASE}/dataset/query`, {
    method: 'POST',
    headers: { accept: 'application/json', 'content-type': 'application/json' },
    body: JSON.stringify({ sql }),
  })
  return readJson<DatasetQueryResult>(response)
}

/** 读取「数据科学」菜单条目。 */
export async function fetchDataDocs(): Promise<DataDocEntry[]> {
  const response = await fetch(`${BASE}/docs`, { headers: { accept: 'application/json' } })
  return readJson<DataDocEntry[]>(response)
}

/** 读取一篇 Markdown 文档。 */
export async function fetchDataDoc(path: string): Promise<DataDocContent> {
  const response = await fetch(`${BASE}/doc?path=${encodeURIComponent(path)}`, {
    headers: { accept: 'application/json' },
  })
  return readJson<DataDocContent>(response)
}

/** 文档内图表的访问地址（相对 `src/data` 的路径）。 */
export function docAssetUrl(path: string): string {
  return `${BASE}/doc-asset?path=${encodeURIComponent(path)}`
}

/** 图表或 HTML 报告的绝对访问地址（供 iframe 等需要独立基址的场景使用）。 */
export function docAssetAbsoluteUrl(path: string): string {
  try {
    return new URL(docAssetUrl(path), window.location.href).href
  } catch {
    return docAssetUrl(path)
  }
}
