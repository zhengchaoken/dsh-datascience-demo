/**
 * 环境自动安装任务。
 *
 * 流程：
 *  1. 确认可用的 Python（最低 3.12，更高版本同样接受）：优先复用本机解释器，
 *     缺失或版本过低时依次尝试 conda/mamba、系统包管理器（apt/dnf/yum/apk/pkg）、
 *     Homebrew、Windows 官方安装包；
 *  2. 在当前工作目录创建 `.venv`（已存在则复用，缺 pip 时用 ensurepip 自愈）；
 *  3. 升级 venv 的 pip / setuptools / wheel；
 *  4. 按用户选择的 PyPI 源（默认国内镜像）安装 requirements.txt 中的依赖。
 *
 * 全程同步记录日志，接口只负责读取快照；安装过程永不抛出未捕获异常。
 */

import { spawn } from 'node:child_process'
import { createWriteStream, existsSync, mkdirSync, rmSync } from 'node:fs'
import os from 'node:os'
import { join } from 'node:path'
import { Readable } from 'node:stream'
import { pipeline } from 'node:stream/promises'
import type { InstallRequest, InstallState } from '../protocol.ts'
import { errorMessage } from '../http.ts'
import {
  MINIMUM_PYTHON,
  REQUIREMENTS_FILE,
  capture,
  probeManagers,
  probePython,
  resolveWorkspace,
  venvPaths,
  venvPythonPath,
} from './probe.ts'

/** Windows 官方安装包使用的版本号（仅该平台自动安装时使用）。 */
const WINDOWS_INSTALL_VERSION = '3.12.10'

/** python.org 官方 Windows x64 安装包地址。 */
const PYTHON_INSTALLER_URL =
  `https://www.python.org/ftp/python/${WINDOWS_INSTALL_VERSION}/python-${WINDOWS_INSTALL_VERSION}-amd64.exe`

/** 默认 PyPI 源：国内镜像，界面留空时使用。 */
const DEFAULT_INDEX_URL = 'https://pypi.tuna.tsinghua.edu.cn/simple'

/** 默认源对应的可信主机。 */
const DEFAULT_TRUSTED_HOST = 'pypi.tuna.tsinghua.edu.cn'

/** 日志上限，避免长安装把内存撑大。 */
const MAX_LOG_LINES = 800

/** 插件数据目录：`$DSH_HOME/dsh-datascience-demo`。 */
export function resolveDataDir(): string {
  const home = process.env['DSH_HOME'] ?? join(os.homedir(), '.dsh')
  return join(home, 'dsh-datascience-demo')
}

/** 两段补零。 */
function pad(value: number): string {
  return String(value).padStart(2, '0')
}

/** 当前时间的 `HH:MM:SS` 前缀。 */
function timeLabel(): string {
  const now = new Date()
  return `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
}

/** 本次安装使用的 PyPI 源。 */
interface IndexTarget {
  /** 传给 `--index-url` 的地址。 */
  url: string
  /** `--trusted-host` 取值；默认源与自建 HTTP 源都需要。 */
  trustedHost: string | null
}

/** 把界面传入的源地址规范化为 pip 可用形式；留空时回落到默认国内镜像。 */
function resolveIndex(raw: string | undefined): IndexTarget {
  const text = (raw ?? '').trim()
  if (text === '') return { url: DEFAULT_INDEX_URL, trustedHost: DEFAULT_TRUSTED_HOST }

  let parsed: URL
  try {
    parsed = new URL(text)
  } catch {
    throw new Error(`PyPI 源地址不是合法 URL：${text}`)
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error('PyPI 源地址必须以 http:// 或 https:// 开头')
  }
  return { url: text, trustedHost: parsed.hostname === '' ? null : parsed.hostname }
}

/** 一条子进程命令。 */
interface Command {
  file: string
  args: string[]
}

/** 一次安装任务的状态机。 */
export class InstallController {
  private state: InstallState = {
    status: 'idle',
    startedAt: null,
    finishedAt: null,
    error: null,
    indexUrl: DEFAULT_INDEX_URL,
    logs: [],
  }

  /** 本次任务生效的源，`start()` 时确定。 */
  private index: IndexTarget = { url: DEFAULT_INDEX_URL, trustedHost: DEFAULT_TRUSTED_HOST }

  /** 子进程输出可能被切成半行，留到下次拼接。 */
  private pending = ''

  /** 返回当前快照（深拷贝日志数组，避免调用方改动内部状态）。 */
  getState(): InstallState {
    return { ...this.state, logs: [...this.state.logs] }
  }

  /** 启动安装；已在运行时直接返回当前状态。 */
  start(options: InstallRequest = {}): InstallState {
    if (this.state.status === 'running') return this.getState()

    let index: IndexTarget
    try {
      index = resolveIndex(options.indexUrl)
    } catch (failure) {
      const message = errorMessage(failure)
      this.state = {
        status: 'failed',
        startedAt: new Date().toISOString(),
        finishedAt: new Date().toISOString(),
        error: message,
        indexUrl: this.state.indexUrl,
        logs: [],
      }
      this.log(`无法开始安装：${message}`)
      return this.getState()
    }

    this.index = index
    this.state = {
      status: 'running',
      startedAt: new Date().toISOString(),
      finishedAt: null,
      error: null,
      indexUrl: index.url,
      logs: [],
    }
    this.pending = ''
    this.log(`开始准备数据科学环境（最低 Python ${MINIMUM_PYTHON}，源 ${index.url}）…`)

    void this.run().catch((failure: unknown) => {
      this.fail(failure)
    })
    return this.getState()
  }

  /** 主流程。 */
  private async run(): Promise<void> {
    const workspace = resolveWorkspace()
    const { venvPath } = venvPaths(workspace)
    mkdirSync(workspace, { recursive: true })
    this.log(`工作目录：${workspace}`)
    this.log(`虚拟环境：${venvPath}`)

    const systemPython = await this.ensurePython()
    const venvPython = await this.ensureVenv(systemPython, venvPath)
    await this.upgradePackaging(venvPython)
    await this.installRequirements(venvPython)

    this.flushPending()
    this.state.status = 'succeeded'
    this.state.finishedAt = new Date().toISOString()
    this.log('环境准备完成，可以开始使用。')
  }

  // ---------------------------------------------------------------- Python

  /** 找到或安装一个满足最低版本的解释器。 */
  private async ensurePython(): Promise<string> {
    this.log(`检查本机 Python（最低要求 ${MINIMUM_PYTHON}）…`)
    const existing = await probePython()
    if (existing.found && existing.executable !== null && existing.versionOk) {
      this.log(`使用已有 Python ${existing.version}：${existing.executable}`)
      return existing.executable
    }
    if (existing.found) {
      this.log(
        `已有 Python ${existing.version ?? '未知版本'} 低于 ${MINIMUM_PYTHON}，继续查找可用方案。`,
      )
    } else {
      this.log('未检测到 Python。')
    }

    this.log('尝试 conda / mamba…')
    for (const manager of await probeManagers()) {
      const python = await this.installWithManager(manager.name, manager.version)
      if (python !== null) return python
    }

    let python: string | null
    if (process.platform === 'win32') {
      python = await this.installWindowsPython()
    } else if (process.platform === 'darwin') {
      python = await this.installWithBrew()
    } else {
      python = await this.installWithLinuxManager()
    }
    if (python !== null) return python

    throw new Error(this.manualInstallHint())
  }

  /** 用 conda / mamba 创建独立环境。 */
  private async installWithManager(name: string, version: string): Promise<string | null> {
    const prefix = join(resolveDataDir(), 'python-env')
    const pythonPath =
      process.platform === 'win32' ? join(prefix, 'python.exe') : join(prefix, 'bin', 'python')

    this.log(`使用 ${name} ${version} 创建独立环境：${prefix}`)
    const ok = await this.tryRun(name, [
      'create',
      '-y',
      '-p',
      prefix,
      `python=${MINIMUM_PYTHON}`,
      'pip',
    ], true)
    if (!ok) return null
    if (!existsSync(pythonPath)) {
      this.log(`未找到 ${pythonPath}，改用其他方案。`)
      return null
    }
    this.log(`Python 已就绪：${pythonPath}`)
    return pythonPath
  }

  /** 下载并静默安装 python.org 的 Windows 安装包。 */
  private async installWindowsPython(): Promise<string | null> {
    if (process.arch !== 'x64') {
      this.log(`Windows ${process.arch} 没有官方安装包（仅提供 x64），请手动安装。`)
      return null
    }

    const dataDir = resolveDataDir()
    mkdirSync(dataDir, { recursive: true })
    const installer = join(dataDir, `python-${WINDOWS_INSTALL_VERSION}-amd64.exe`)
    const target = join(dataDir, 'python')

    if (!existsSync(installer)) {
      this.log(`下载 Python 安装包：${PYTHON_INSTALLER_URL}`)
      try {
        const response = await fetch(PYTHON_INSTALLER_URL)
        if (!response.ok || response.body === null) {
          throw new Error(`HTTP ${response.status}`)
        }
        await pipeline(
          Readable.fromWeb(
            response.body as unknown as import('node:stream/web').ReadableStream<Uint8Array>,
          ),
          createWriteStream(installer),
        )
      } catch (failure) {
        this.log(`下载安装包失败：${errorMessage(failure)}`)
        return null
      }
      this.log('安装包下载完成。')
    } else {
      this.log('安装包已存在，跳过下载。')
    }

    this.log(`静默安装到 ${target} …`)
    const ok = await this.tryRun(installer, [
      '/quiet',
      'InstallAllUsers=0',
      `TargetDir=${target}`,
      'Include_pip=1',
      'Include_launcher=0',
      'PrependPath=0',
      'Shortcuts=0',
      'Include_test=0',
    ])
    if (!ok) return null

    const pythonPath = join(target, 'python.exe')
    if (!existsSync(pythonPath)) {
      this.log(`安装程序已结束，但没有找到 ${pythonPath}。`)
      return null
    }
    this.log(`Python 已安装到 ${target}`)
    return pythonPath
  }

  /** macOS：用 Homebrew 安装 python@3.12。 */
  private async installWithBrew(): Promise<string | null> {
    if (!(await capture('brew', ['--version'], 10000)).ok) {
      this.log('未检测到 Homebrew，跳过 brew 方案。')
      return null
    }
    this.log('使用 Homebrew 安装 python@3.12 …')
    if (!(await this.tryRun('brew', ['install', 'python@3.12']))) return null
    return await this.probeInstalled()
  }

  /** Linux：按发行版选择包管理器安装 python3。 */
  private async installWithLinuxManager(): Promise<string | null> {
    if (this.isTermux()) {
      this.log('检测到 Termux，使用 pkg 安装 python…')
      if (!(await this.tryRun('pkg', ['install', '-y', 'python']))) return null
      return await this.probeInstalled()
    }

    const elevator = await this.elevator()
    if (elevator === null) {
      this.log('当前用户不是 root 且没有免密 sudo，无法自动安装系统软件包。')
      return null
    }

    const apt = await this.tryElevated(
      elevator,
      'apt-get',
      ['update'],
      { DEBIAN_FRONTEND: 'noninteractive' },
    )
    if (apt) {
      const base = await this.tryElevated(elevator, 'apt-get', [
        'install',
        '-y',
        '--no-install-recommends',
        'python3',
        'python3-pip',
        'python3-venv',
      ], { DEBIAN_FRONTEND: 'noninteractive' })
      // 发行版自带的 python3 可能低于 3.12，再尝试显式安装 3.12（支持的版本才有）。
      await this.tryElevated(elevator, 'apt-get', [
        'install',
        '-y',
        'python3.12',
        'python3.12-venv',
      ], { DEBIAN_FRONTEND: 'noninteractive' })
      if (!base) {
        this.log('apt-get 安装 python3 失败。')
        return null
      }
      return await this.probeInstalled()
    }

    if ((await capture('dnf', ['--version'], 8000)).ok) {
      this.log('检测到 dnf，安装 python3 / pip …')
      if (!(await this.tryElevated(elevator, 'dnf', ['install', '-y', 'python3', 'python3-pip']))) {
        return null
      }
      return await this.probeInstalled()
    }

    if ((await capture('yum', ['--version'], 8000)).ok) {
      this.log('检测到 yum，安装 python3 / pip …')
      if (!(await this.tryElevated(elevator, 'yum', ['install', '-y', 'python3', 'python3-pip']))) {
        return null
      }
      return await this.probeInstalled()
    }

    if ((await capture('apk', ['--version'], 8000)).ok) {
      this.log('检测到 apk，安装 python3 / py3-pip …')
      if (!(await this.tryElevated(elevator, 'apk', ['add', '--no-cache', 'python3', 'py3-pip']))) {
        return null
      }
      return await this.probeInstalled()
    }

    this.log('未识别到可用的系统包管理器（apt-get / dnf / yum / apk）。')
    return null
  }

  /** 是否运行在 Termux（Android）环境。 */
  private isTermux(): boolean {
    const prefix = process.env['PREFIX']
    if (prefix !== undefined && prefix.includes('com.termux/files/usr')) return true
    return existsSync('/data/data/com.termux/files/usr/bin')
  }

  /** 提权前缀：root 直接执行，非 root 需要免密 sudo；都不满足返回 null。 */
  private async elevator(): Promise<string[] | null> {
    if (typeof process.getuid === 'function' && process.getuid() === 0) return []
    if ((await capture('sudo', ['-n', 'true'], 8000)).ok) return ['sudo', '-n']
    return null
  }

  /** 安装完成后重新探测解释器。 */
  private async probeInstalled(): Promise<string | null> {
    const probed = await probePython()
    if (probed.found && probed.executable !== null && probed.versionOk) {
      this.log(`检测到 Python ${probed.version}：${probed.executable}`)
      return probed.executable
    }
    this.log(`安装完成后仍未发现 Python ${MINIMUM_PYTHON} 或更高版本。`)
    return null
  }

  /** 自动安装全部失败时给出的手动指引。 */
  private manualInstallHint(): string {
    return (
      `未能在当前平台（${process.platform}/${process.arch}）自动准备好 Python ${MINIMUM_PYTHON} 或更高版本。` +
      '可以手动安装后重试：Linux 用 apt-get / dnf / yum / apk 安装 python3（或 python3.12）；' +
      'macOS 用 brew install python@3.12；Windows 从 python.org 下载 3.12 以上安装包；' +
      '任何平台也可以用 conda / miniconda 创建环境。'
    )
  }

  // ------------------------------------------------------------------ venv

  /** 在当前工作目录创建 `.venv`，返回其中的解释器。 */
  private async ensureVenv(systemPython: string, venvPath: string): Promise<string> {
    const venvPython = venvPythonPath(venvPath)
    if (existsSync(venvPython)) {
      if (await this.hasPip(venvPython)) {
        this.log(`已有虚拟环境：${venvPath}`)
        return venvPython
      }
      this.log('虚拟环境已存在但缺少 pip，尝试修复…')
      if (await this.repairPip(venvPython)) {
        this.log(`虚拟环境已修复：${venvPath}`)
        return venvPython
      }
    }

    if (existsSync(venvPath)) {
      this.log(`清理不可用的虚拟环境：${venvPath}`)
      rmSync(venvPath, { recursive: true, force: true })
    }

    this.log('创建虚拟环境：python -m venv .venv')
    await this.runCommand(systemPython, ['-m', 'venv', venvPath])
    if (!existsSync(venvPython)) {
      throw new Error(`venv 创建完成，但没有找到 ${venvPython}`)
    }
    if (!(await this.hasPip(venvPython))) {
      this.log('虚拟环境缺少 pip，执行 ensurepip 修复…')
      if (!(await this.repairPip(venvPython))) {
        throw new Error(
          '虚拟环境缺少 pip 支持，请先安装 venv 模块后重试' +
            '（Debian/Ubuntu: apt install python3-venv；Alpine: apk add py3-pip）。',
        )
      }
    }
    this.log(`虚拟环境已创建：${venvPath}`)
    return venvPython
  }

  /** venv 中的 pip 是否可用。 */
  private async hasPip(venvPython: string): Promise<boolean> {
    return (await capture(venvPython, ['-m', 'pip', '--version'], 20000)).ok
  }

  /** 用 ensurepip 给 venv 补上 pip。 */
  private async repairPip(venvPython: string): Promise<boolean> {
    if (!(await this.tryRun(venvPython, ['-m', 'ensurepip', '--upgrade']))) return false
    return await this.hasPip(venvPython)
  }

  // ------------------------------------------------------------------- pip

  /** 组装 `pip install` 参数：统一带上源并禁用缓存（全局 cache 目录可能不可写）。 */
  private pipArgs(extra: readonly string[]): string[] {
    const args = [
      '-m',
      'pip',
      'install',
      '--disable-pip-version-check',
      '--no-cache-dir',
      '--index-url',
      this.index.url,
    ]
    if (this.index.trustedHost !== null) args.push('--trusted-host', this.index.trustedHost)
    args.push(...extra)
    return args
  }

  /** 升级 venv 的构建工具。 */
  private async upgradePackaging(venvPython: string): Promise<void> {
    this.log(`升级 pip / setuptools / wheel（源：${this.index.url}）…`)
    await this.runCommand(venvPython, this.pipArgs(['--upgrade', 'pip', 'setuptools', 'wheel']))
  }

  /** 按所选源安装依赖清单。 */
  private async installRequirements(venvPython: string): Promise<void> {
    this.log(`安装依赖清单：${REQUIREMENTS_FILE}`)
    await this.runCommand(
      venvPython,
      this.pipArgs(['--no-build-isolation', '-r', REQUIREMENTS_FILE]),
    )
  }

  // ------------------------------------------------------------- 子进程工具

  /** 执行子进程并把输出逐行写进日志。 */
  private runCommand(
    file: string,
    args: readonly string[],
    shell = false,
    extraEnv?: Record<string, string>,
  ): Promise<void> {
    this.log(`$ ${file} ${args.join(' ')}`)
    return new Promise((resolvePromise, reject) => {
      const child = spawn(file, [...args], {
        windowsHide: true,
        shell,
        env: {
          ...process.env,
          ...extraEnv,
          PYTHONIOENCODING: 'utf-8',
          PYTHONUNBUFFERED: '1',
          PIP_DISABLE_PIP_VERSION_CHECK: '1',
        },
      })

      child.stdout?.on('data', (chunk: Buffer) => this.appendChunk(chunk))
      child.stderr?.on('data', (chunk: Buffer) => this.appendChunk(chunk))
      child.on('error', (failure: Error) => {
        this.flushPending()
        reject(failure)
      })
      child.on('close', (code: number | null) => {
        this.flushPending()
        if (code === 0) resolvePromise()
        else reject(new Error(`命令退出码 ${code ?? '未知'}：${file}`))
      })
    })
  }

  /** 执行命令，失败只记日志并返回 false。 */
  private async tryRun(
    file: string,
    args: readonly string[],
    shell = false,
    extraEnv?: Record<string, string>,
  ): Promise<boolean> {
    try {
      await this.runCommand(file, args, shell, extraEnv)
      return true
    } catch (failure) {
      this.log(`${file} 执行失败：${errorMessage(failure)}`)
      return false
    }
  }

  /** 把提权前缀拼到真实命令前面。 */
  private elevatedCommand(elevator: readonly string[], file: string, args: readonly string[]): Command {
    return elevator.length === 0
      ? { file, args: [...args] }
      : { file: elevator[0]!, args: [...elevator.slice(1), file, ...args] }
  }

  /** 以提权方式执行命令，失败只记日志并返回 false。 */
  private async tryElevated(
    elevator: readonly string[],
    file: string,
    args: readonly string[],
    extraEnv?: Record<string, string>,
  ): Promise<boolean> {
    const command = this.elevatedCommand(elevator, file, args)
    return await this.tryRun(command.file, command.args, false, extraEnv)
  }

  /** 把一段输出按行拆进日志。 */
  private appendChunk(chunk: Buffer | string): void {
    this.pending += String(chunk)
    const lines = this.pending.split(/\r?\n/u)
    this.pending = lines.pop() ?? ''
    for (const line of lines) this.log(line)
  }

  /** 写入最后一段没有换行的输出。 */
  private flushPending(): void {
    if (this.pending.trim() !== '') this.log(this.pending)
    this.pending = ''
  }

  /** 追加一条带时间戳的日志。 */
  private log(message: string): void {
    const line = `[${timeLabel()}] ${message}`
    this.state.logs.push(line)
    if (this.state.logs.length > MAX_LOG_LINES) {
      this.state.logs.splice(0, this.state.logs.length - MAX_LOG_LINES)
    }
  }

  /** 记录失败并收敛状态。 */
  private fail(failure: unknown): void {
    this.flushPending()
    const message = errorMessage(failure)
    this.state.status = 'failed'
    this.state.error = message
    this.state.finishedAt = new Date().toISOString()
    this.log(`安装失败：${message}`)
  }
}
