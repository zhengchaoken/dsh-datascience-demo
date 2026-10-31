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

/** 一次环境检查的完整结果。 */
export interface EnvironmentReport {
  system: SystemInfo
  python: PythonInfo
  managers: ManagerInfo[]
  dependencies: DependencyInfo[]
  /** Python 3.12 可用且依赖齐全。 */
  ready: boolean
  /** 读取依赖清单或 pip 列表时的错误。 */
  dependenciesError: string | null
  /** 依赖清单文件绝对路径。 */
  requirementsFile: string
  /** 检查时间（ISO）。 */
  checkedAt: string
  install: InstallState
}
