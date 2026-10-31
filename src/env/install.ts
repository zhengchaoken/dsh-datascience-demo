/**
 * 环境自动安装任务。
 *
 * 流程：
 *  1. 确保存在 Python 3.12（复用本机解释器，缺失时用 mamba/conda 或官方安装包）；
 *  2. 在当前工作目录创建 `.venv`（已存在则跳过）；
 *  3. 升级 venv 的 pip / setuptools / wheel；
 *  4. 按清华源安装 requirements.txt 中的依赖。
 *
 * 全程同步记录日志，接口只负责读取快照；安装过程永不抛出未捕获异常。
 */

import { spawn } from 'node:child_process'
import { createWriteStream, existsSync, mkdirSync, rmSync } from 'node:fs'
import os from 'node:os'
import { join } from 'node:path'
import { Readable } from 'node:stream'
import { pipeline } from 'node:stream/promises'
import type { InstallState } from '../protocol.ts'
import {
  REQUIREMENTS_FILE,
  probeManagers,
  probePython,
  resolveWorkspace,
  venvPaths,
  venvPythonPath,
} from './probe.ts'

/** 自动安装固定使用的 Python 版本。 */
const PYTHON_VERSION = '3.12.10'

/** python.org 官方 Windows x64 安装包地址。 */
const PYTHON_INSTALLER_URL =
  `https://www.python.org/ftp/python/${PYTHON_VERSION}/python-${PYTHON_VERSION}-amd64.exe`

/** 依赖安装使用的 PyPI 镜像。 */
const PYPI_INDEX_URL = 'https://pypi.tuna.tsinghua.edu.cn/simple'

/** 镜像对应的可信主机。 */
const PYPI_TRUSTED_HOST = 'pypi.tuna.tsinghua.edu.cn'

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

/** 一次安装任务的状态机。 */
export class InstallController {
  private state: InstallState = {
    status: 'idle',
    startedAt: null,
    finishedAt: null,
    error: null,
    logs: [],
  }

  /** 子进程输出可能被切成半行，留到下次拼接。 */
  private pending = ''

  /** 返回当前快照（深拷贝日志数组，避免调用方改动内部状态）。 */
  getState(): InstallState {
    return { ...this.state, logs: [...this.state.logs] }
  }

  /** 启动安装；已在运行时直接返回当前状态。 */
  start(): InstallState {
    if (this.state.status === 'running') return this.getState()

    this.state = {
      status: 'running',
      startedAt: new Date().toISOString(),
      finishedAt: null,
      error: null,
      logs: [],
    }
    this.pending = ''
    this.log(`开始准备数据科学环境（目标 Python ${PYTHON_VERSION}）…`)

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

  /** 找到或安装一个可用的 3.12 解释器。 */
  private async ensurePython(): Promise<string> {
    this.log('检查本机 Python…')
    const existing = await probePython()
    if (existing.found && existing.executable !== null && existing.versionOk) {
      this.log(`使用已有 Python ${existing.version}：${existing.executable}`)
      return existing.executable
    }
    if (existing.found) {
      this.log(`已有 Python ${existing.version ?? '未知版本'}，但不是 3.12，继续查找可用方案。`)
    } else {
      this.log('未检测到 Python。')
    }

    this.log('检查 mamba / conda…')
    const managers = await probeManagers()
    const manager = managers[0]
    if (manager !== undefined) {
      this.log(`使用 ${manager.name} ${manager.version} 创建独立环境。`)
      const prefix = join(resolveDataDir(), 'python-env')
      await this.runCommand(manager.name, ['create', '-y', '-p', prefix, 'python=3.12', 'pip'], true)
      const pythonPath = join(prefix, 'python.exe')
      if (!existsSync(pythonPath)) {
        throw new Error(`${manager.name} 执行完成，但没有找到 ${pythonPath}`)
      }
      return pythonPath
    }

    this.log('未检测到 mamba / conda，改用官方安装包。')
    return await this.installBundledPython()
  }

  /** 下载并静默安装 python.org 的 Windows 安装包。 */
  private async installBundledPython(): Promise<string> {
    if (process.platform !== 'win32' || process.arch !== 'x64') {
      throw new Error(
        `当前平台 ${process.platform}/${process.arch} 不在自动安装范围内，` +
          '请先手动安装 Python 3.12 后重试。',
      )
    }

    const dataDir = resolveDataDir()
    mkdirSync(dataDir, { recursive: true })
    const installer = join(dataDir, `python-${PYTHON_VERSION}-amd64.exe`)
    const target = join(dataDir, 'python')

    if (!existsSync(installer)) {
      this.log(`下载 Python 安装包：${PYTHON_INSTALLER_URL}`)
      const response = await fetch(PYTHON_INSTALLER_URL)
      if (!response.ok || response.body === null) {
        throw new Error(`下载 Python 安装包失败：HTTP ${response.status}`)
      }
      await pipeline(
        Readable.fromWeb(response.body as unknown as import('node:stream/web').ReadableStream<Uint8Array>),
        createWriteStream(installer),
      )
      this.log('安装包下载完成。')
    } else {
      this.log('安装包已存在，跳过下载。')
    }

    this.log(`静默安装到 ${target} …`)
    await this.runCommand(installer, [
      '/quiet',
      'InstallAllUsers=0',
      `TargetDir=${target}`,
      'Include_pip=1',
      'Include_launcher=0',
      'PrependPath=0',
      'Shortcuts=0',
      'Include_test=0',
    ])

    const pythonPath = join(target, 'python.exe')
    if (!existsSync(pythonPath)) {
      throw new Error(`安装程序已结束，但没有找到 ${pythonPath}，请查看上方日志。`)
    }
    this.log(`Python 已安装到 ${target}`)
    return pythonPath
  }

  /** 在当前工作目录创建 `.venv`，返回其中的解释器。 */
  private async ensureVenv(systemPython: string, venvPath: string): Promise<string> {
    const venvPython = venvPythonPath(venvPath)
    if (existsSync(venvPython)) {
      this.log(`已有虚拟环境：${venvPath}`)
      return venvPython
    }

    if (existsSync(venvPath)) {
      this.log(`发现不完整的虚拟环境，先清理：${venvPath}`)
      rmSync(venvPath, { recursive: true, force: true })
    }

    this.log('创建虚拟环境：python -m venv .venv')
    await this.runCommand(systemPython, ['-m', 'venv', venvPath])
    if (!existsSync(venvPython)) {
      throw new Error(`venv 创建完成，但没有找到 ${venvPython}`)
    }
    this.log(`虚拟环境已创建：${venvPath}`)
    return venvPython
  }

  /** 升级 venv 的构建工具。 */
  private async upgradePackaging(venvPython: string): Promise<void> {
    this.log('升级 pip / setuptools / wheel…')
    await this.runCommand(venvPython, [
      '-m',
      'pip',
      'install',
      '--disable-pip-version-check',
      '--upgrade',
      'pip',
      'setuptools',
      'wheel',
    ])
  }

  /** 按清华源安装依赖清单。 */
  private async installRequirements(venvPython: string): Promise<void> {
    this.log(`安装依赖清单：${REQUIREMENTS_FILE}`)
    await this.runCommand(venvPython, [
      '-m',
      'pip',
      'install',
      '--disable-pip-version-check',
      '--index-url',
      PYPI_INDEX_URL,
      '--trusted-host',
      PYPI_TRUSTED_HOST,
      '-r',
      REQUIREMENTS_FILE,
    ])
  }

  /** 执行子进程并把输出逐行写进日志。 */
  private runCommand(file: string, args: readonly string[], shell = false): Promise<void> {
    this.log(`$ ${file} ${args.join(' ')}`)
    return new Promise((resolvePromise, reject) => {
      const child = spawn(file, args, {
        windowsHide: true,
        shell,
        env: {
          ...process.env,
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
    const message = failure instanceof Error ? failure.message : String(failure)
    this.state.status = 'failed'
    this.state.error = message
    this.state.finishedAt = new Date().toISOString()
    this.log(`安装失败：${message}`)
  }
}
