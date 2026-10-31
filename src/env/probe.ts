/**
 * 本地环境探测：系统信息、Python 解释器、conda/mamba、依赖清单。
 *
 * 所有外部命令都通过 child_process 执行，超时且不弹窗口。探测本身永不抛错：
 * 任何一步失败都会变成报告里的「未找到 / 错误」，让界面始终能渲染。
 */

import { execFile } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import os from 'node:os'
import { dirname, join } from 'node:path'
import { promisify } from 'node:util'
import { fileURLToPath } from 'node:url'
import type {
  DependencyInfo,
  EnvironmentReport,
  InstallState,
  ManagerInfo,
  PythonInfo,
} from '../protocol.ts'

const execFileAsync = promisify(execFile)

/** 向上查找插件根目录：从 lib/index.js 或 src/env/probe.ts 出发都能命中。 */
function packageRoot(): string {
  let current = dirname(fileURLToPath(import.meta.url))
  for (let depth = 0; depth < 6; depth += 1) {
    const manifest = join(current, 'package.json')
    if (existsSync(manifest)) {
      try {
        const parsed = JSON.parse(readFileSync(manifest, 'utf8')) as { name?: unknown }
        if (parsed.name === 'dsh-datascience-demo') return current
      } catch {
        // 忽略损坏的 package.json，继续向上找
      }
    }
    const parent = dirname(current)
    if (parent === current) break
    current = parent
  }
  return dirname(fileURLToPath(import.meta.url))
}

/** 依赖清单的绝对路径（打包后位于插件根目录）。 */
export const REQUIREMENTS_FILE = join(packageRoot(), 'requirements.txt')

/** 一条命令的输出。 */
interface Capture {
  ok: boolean
  stdout: string
  stderr: string
}

/** 执行一条命令；失败也返回输出，不抛错。 */
export async function capture(
  file: string,
  args: readonly string[],
  timeoutMs = 15000,
  shell = false,
): Promise<Capture> {
  try {
    const { stdout, stderr } = await execFileAsync(file, args, {
      timeout: timeoutMs,
      windowsHide: true,
      maxBuffer: 16 * 1024 * 1024,
      shell,
    })
    return { ok: true, stdout: String(stdout), stderr: String(stderr) }
  } catch (failure) {
    const value = failure as { stdout?: unknown; stderr?: unknown }
    const stderr =
      typeof value.stderr === 'string' && value.stderr !== ''
        ? value.stderr
        : failure instanceof Error
          ? failure.message
          : String(failure)
    return {
      ok: false,
      stdout: typeof value.stdout === 'string' ? value.stdout : '',
      stderr,
    }
  }
}

/** 从文本里取第一个类版本号。 */
function firstVersion(text: string): string | null {
  const match = text.match(/[0-9]+\.[0-9]+(?:\.[0-9]+)?/)
  return match === null ? null : match[0]
}

/** 读取并解析依赖清单。 */
export function readRequirements(path = REQUIREMENTS_FILE): {
  entries: { name: string; requirement: string }[]
  error: string | null
} {
  let text: string
  try {
    text = readFileSync(path, 'utf8')
  } catch (failure) {
    return {
      entries: [],
      error: `无法读取依赖清单 ${path}：${failure instanceof Error ? failure.message : String(failure)}`,
    }
  }

  const entries: { name: string; requirement: string }[] = []
  for (const rawLine of text.split(/\r?\n/u)) {
    const line = rawLine.split('#')[0]!.trim()
    if (line === '' || line.startsWith('-')) continue
    const match = line.match(/^([A-Za-z0-9][A-Za-z0-9._-]*)/u)
    if (match === null) continue
    const name = match[1]!
    const requirement = line
      .slice(name.length)
      .replace(/^\s*;\s*.*$/u, '')
      .trim()
    entries.push({ name, requirement })
  }
  return { entries, error: null }
}

/** pip 包名比较用的规范化形式。 */
function normalizeName(name: string): string {
  return name.toLowerCase().replace(/[-_.]+/gu, '-')
}

/** 探测 Python 解释器。 */
export async function probePython(): Promise<PythonInfo> {
  const candidates: { file: string; args: string[] }[] = [
    {
      file: 'python',
      args: ['-c', 'import sys,platform;print("EXE:"+sys.executable);print("VER:"+platform.python_version())'],
    },
    {
      file: 'python3',
      args: ['-c', 'import sys,platform;print("EXE:"+sys.executable);print("VER:"+platform.python_version())'],
    },
    {
      file: 'py',
      args: ['-3', '-c', 'import sys,platform;print("EXE:"+sys.executable);print("VER:"+platform.python_version())'],
    },
  ]

  for (const candidate of candidates) {
    const result = await capture(candidate.file, candidate.args)
    if (!result.ok) continue
    const exe = result.stdout.match(/EXE:(.*)/u)?.[1]?.trim()
    const version = result.stdout.match(/VER:(.*)/u)?.[1]?.trim()
    if (exe === undefined || exe === '' || version === undefined || version === '') continue

    const pip = await capture(exe, ['-m', 'pip', '--version'])
    const pipVersion = pip.ok ? firstVersion(pip.stdout) : null

    return {
      found: true,
      executable: exe,
      version,
      versionOk: version.startsWith('3.12.'),
      pipVersion,
    }
  }

  return {
    found: false,
    executable: null,
    version: null,
    versionOk: false,
    pipVersion: null,
  }
}

/** 探测 conda / mamba / micromamba。 */
export async function probeManagers(): Promise<ManagerInfo[]> {
  const found: ManagerInfo[] = []
  for (const name of ['mamba', 'conda', 'micromamba']) {
    const result = await capture(name, ['--version'], 10000, true)
    if (!result.ok) continue
    const version = firstVersion(result.stdout)
    if (version !== null) found.push({ name, version })
  }
  return found
}

/** 读取 pip 已安装列表。 */
async function probeInstalled(python: PythonInfo): Promise<{
  installed: Map<string, string>
  error: string | null
}> {
  if (!python.found || python.executable === null) {
    return { installed: new Map(), error: '未找到可用的 Python 解释器' }
  }
  const result = await capture(
    python.executable,
    ['-m', 'pip', 'list', '--format', 'json', '--disable-pip-version-check'],
    30000,
  )
  if (!result.ok) {
    const firstLine = result.stderr.split(/\r?\n/u).find(line => line.trim() !== '')
    return {
      installed: new Map(),
      error: firstLine === undefined ? '读取 pip 包列表失败' : firstLine.trim(),
    }
  }
  try {
    const parsed = JSON.parse(result.stdout) as { name?: unknown; version?: unknown }[]
    const installed = new Map<string, string>()
    for (const entry of parsed) {
      if (typeof entry.name !== 'string' || typeof entry.version !== 'string') continue
      installed.set(normalizeName(entry.name), entry.version)
    }
    return { installed, error: null }
  } catch {
    return { installed: new Map(), error: 'pip 包列表不是合法 JSON' }
  }
}

/** 执行一次完整环境探测。 */
export async function probeEnvironment(install: InstallState): Promise<EnvironmentReport> {
  const python = await probePython()
  const [managers, packages, requirements] = await Promise.all([
    probeManagers(),
    probeInstalled(python),
    Promise.resolve(readRequirements()),
  ])

  const dependencies: DependencyInfo[] = requirements.entries.map(entry => {
    const version = packages.installed.get(normalizeName(entry.name)) ?? null
    return {
      name: entry.name,
      requirement: entry.requirement,
      installed: version !== null,
      version,
    }
  })

  return {
    system: {
      type: os.type(),
      release: os.release(),
      arch: os.arch(),
      platform: os.platform(),
      node: process.version,
    },
    python,
    managers,
    dependencies,
    ready:
      python.found &&
      python.versionOk &&
      dependencies.length > 0 &&
      dependencies.every(dependency => dependency.installed),
    dependenciesError: requirements.error ?? packages.error,
    requirementsFile: REQUIREMENTS_FILE,
    checkedAt: new Date().toISOString(),
    install,
  }
}
