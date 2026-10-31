/**
 * 宿主端与浏览器端共享的协议类型：环境检查与安装任务。
 *
 * 这个文件不能引用 node 内置模块，浏览器端的 bundler 会一并打包它。
 */

/** 依赖清单里的一条要求。 */
export interface DependencyInfo {
  /** pip 包名。 */
  name: string
  /** requirements.txt 中的原始版本约束，例如 `>=2.2`。 */
  requirement: string
  /** 是否已安装。 */
  installed: boolean
  /** 已安装版本，未安装时为 null。 */
  version: string | null
}

/** 探测到的 Python 解释器。 */
export interface PythonInfo {
  found: boolean
  /** 解释器绝对路径。 */
  executable: string | null
  /** 例如 `3.12.10`。 */
  version: string | null
  /** 是否为 3.12.x。 */
  versionOk: boolean
  /** pip 版本，例如 `24.0`。 */
  pipVersion: string | null
}

/** 探测到的环境管理器。 */
export interface ManagerInfo {
  /** `conda` / `mamba` / `micromamba`。 */
  name: string
  version: string
}

/** 宿主系统信息。 */
export interface SystemInfo {
  /** 例如 `Windows_NT`。 */
  type: string
  /** 例如 `10.0.22631`。 */
  release: string
  /** 例如 `x64`。 */
  arch: string
  /** 例如 `win32`。 */
  platform: string
  /** node 运行时版本。 */
  node: string
}

/** 当前工作区与其中的 `.venv`。 */
export interface WorkspaceInfo {
  /** 工作目录绝对路径：默认是宿主进程 cwd，可用 DSD_WORKSPACE 覆盖。 */
  path: string
  /** `.venv` 目录绝对路径。 */
  venvPath: string
  /** `.venv` 是否已创建。 */
  venvExists: boolean
  /** `.venv` 里的 Python 解释器路径。 */
  python: string | null
  /** `.venv` 的 Python 版本。 */
  pythonVersion: string | null
  /** `.venv` 的 pip 版本。 */
  pipVersion: string | null
}

/** pip 已安装的一个包。 */
export interface InstalledPackage {
  name: string
  version: string
}

/** 安装任务的公开状态。 */
export type InstallStatus = 'idle' | 'running' | 'succeeded' | 'failed'

/** 安装任务快照。 */
export interface InstallState {
  status: InstallStatus
  /** 开始时间（ISO）。 */
  startedAt: string | null
  /** 结束时间（ISO）。 */
  finishedAt: string | null
  /** 失败原因，仅 failed 时有值。 */
  error: string | null
  /** 过程日志，按时间顺序。 */
  logs: string[]
}

/** 示例数据集里一个字段的说明。 */
export interface DatasetColumnInfo {
  name: string
  /** SQLite 声明类型，例如 INTEGER / TEXT / REAL。 */
  type: string
  /** 字段业务含义（与 schema.sql 行内注释一致）。 */
  comment: string
}

/** 示例数据集中一张表的元信息。 */
export interface DatasetTableInfo {
  /** SQL 表名，例如 orders。 */
  name: string
  /** 中文名称，例如「订单表」。 */
  label: string
  /** 一句话业务说明。 */
  description: string
  /** 当前行数。 */
  rowCount: number
  columns: DatasetColumnInfo[]
}

/** `GET /dataset` 的响应：数据集整体描述。 */
export interface DatasetInfo {
  /** 查询引擎标识，当前为 node:sqlite。 */
  engine: string
  /** 数据库文件的包内相对路径，例如 `src/data/ecommerce/ecommerce.db`。 */
  dbFile: string
  tables: DatasetTableInfo[]
}

/** `POST /dataset/query` 的响应。 */
export interface DatasetQueryResult {
  columns: string[]
  /** 按 columns 顺序排列的行值；SQLite NULL 序列化为 null。 */
  rows: (string | number | null)[][]
  /** 本次返回的行数（= rows.length）。 */
  rowCount: number
  /** 命中行数超过单次上限被截断。 */
  truncated: boolean
  /** 单次返回行数上限。 */
  maxRows: number
  /** 查询耗时（毫秒）。 */
  elapsedMs: number
}

/** 「数据科学」菜单里的一篇主文档。 */
export interface DataDocEntry {
  /** 稳定标识，例如 `framework`、`L4`。 */
  id: string
  /** 菜单显示名称，例如「L4 规范性分析」。 */
  label: string
  /** 相对 `src/data` 的文档路径，例如 `L4/README.md`。 */
  path: string
  /** 一句话说明。 */
  summary: string
}

/** `GET /doc` 的响应：一篇 Markdown 文档。 */
export interface DataDocContent {
  /** 相对 `src/data` 的路径。 */
  path: string
  /** 文档标题（取首个一级标题）。 */
  title: string
  /** Markdown 原文。 */
  markdown: string
}

/** 一次环境检查的完整结果。 */
export interface EnvironmentReport {
  system: SystemInfo
  python: PythonInfo
  managers: ManagerInfo[]
  /** 当前工作目录与其 `.venv`。 */
  workspace: WorkspaceInfo
  dependencies: DependencyInfo[]
  /** `.venv` 中的完整 pip 包列表。 */
  installedPackages: InstalledPackage[]
  /** Python 3.12 可用、`.venv` 已创建且依赖齐全。 */
  ready: boolean
  /** 读取依赖清单或 pip 列表时的错误。 */
  dependenciesError: string | null
  /** 依赖清单文件绝对路径。 */
  requirementsFile: string
  /** 检查时间（ISO）。 */
  checkedAt: string
  install: InstallState
}
