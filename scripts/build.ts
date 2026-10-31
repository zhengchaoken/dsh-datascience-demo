/**
 * dsh-datascience-demo 构建脚本。
 *
 * 产出两个文件，对应 dsh 的双端插件契约：
 *
 *  - `lib/index.js` — 宿主端：ESM、打包，dsh 运行时提供的包保持 external。
 *  - `lib/client.js` — 浏览器端：打包成浏览器可执行的 CJS，再包进 harness 的
 *    `window.__ModuleLoader__.load({ id, factory })` 工厂信封；`react` 保持
 *    external，由模块系统提供 shell 已在用的那一个实例。
 *
 * 用法：npm run build（= npx tsx scripts/build.ts）
 */

import { build } from 'esbuild-wasm'
import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(here, '..')
const OUT = resolve(ROOT, 'lib')

/** 宿主运行时提供的包：打进产物会产生重复状态。 */
const HOST_EXTERNAL = ['@deepseek-ai/cordis', '@deepseek-ai/schemastery', '@deepseek-ai/dsh-tools']

/** 浏览器模块系统拥有的包。 */
const CLIENT_EXTERNAL = ['react', 'react-dom', 'react/jsx-runtime']

/** 把浏览器产物包进 harness 的模块加载器工厂信封。 */
function wrapClientFactory(id: string, code: string): string {
  return `window.__ModuleLoader__.load({\n\tid: ${JSON.stringify(id)},\n\tfactory: (require) => {\n\t\tvar module = { exports: {} };\n\t\tvar exports = module.exports;\n\t\tObject.defineProperty(exports, Symbol.toStringTag, { value: "Module" });\n${indent(code, 2)}\n\t\treturn module.exports;\n\t}\n});\n`
}

/** 给非空行加 N 个 tab 缩进。 */
function indent(code: string, tabs: number): string {
  const prefix = '\t'.repeat(tabs)
  return code
    .split('\n')
    .map(line => (line.trim() === '' ? '' : prefix + line))
    .join('\n')
}

/** 包名，同时作为浏览器端模块 id。 */
function packageName(): string {
  const raw = readFileSync(resolve(ROOT, 'package.json'), 'utf8')
  return (JSON.parse(raw) as { name: string }).name
}

async function main(): Promise<void> {
  const id = packageName()

  console.log('Cleaning lib/ ...')
  rmSync(OUT, { recursive: true, force: true })
  mkdirSync(OUT, { recursive: true })

  console.log('Building host half -> lib/index.js')
  await build({
    entryPoints: [resolve(ROOT, 'src/index.ts')],
    outfile: resolve(OUT, 'index.js'),
    bundle: true,
    platform: 'node',
    target: 'es2022',
    format: 'esm',
    sourcemap: true,
    external: HOST_EXTERNAL,
    logLevel: 'warning',
  })

  console.log('Building browser half -> lib/client.js')
  const clientResult = await build({
    entryPoints: [resolve(ROOT, 'src/client/index.ts')],
    write: false,
    bundle: true,
    platform: 'browser',
    target: 'es2022',
    format: 'cjs',
    sourcemap: false,
    minify: false,
    define: { 'process.env.NODE_ENV': '"production"' },
    external: CLIENT_EXTERNAL,
    logLevel: 'warning',
  })

  const bundled = clientResult.outputFiles[0]!.text
  writeFileSync(resolve(OUT, 'client.js'), wrapClientFactory(id, bundled), 'utf8')

  console.log('Build complete.')
  console.log('  host:   lib/index.js')
  console.log(`  client: lib/client.js  (module id "${id}")`)
}

main().catch((error: unknown) => {
  console.error(error)
  process.exit(1)
})
