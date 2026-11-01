/**
 * 独立 Web 构建：产出 dist-web/（index.html + assets/app.js + server.mjs）。
 *
 * 与 `npm run build`（DSH 双端插件产物）互不影响，两者可同时保留。
 *
 * 用法：npm run build:web（= npx tsx scripts/build-web.ts）
 */

import { build } from 'esbuild-wasm'
import { mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(here, '..')
const OUT = resolve(ROOT, 'dist-web')

/** 页面外壳：只有一个挂载点与最小基础样式。 */
const INDEX_HTML = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>数据科学示例</title>
<style>
  html, body, #root { height: 100%; margin: 0; }
  body { background: #f5f8fd; }
</style>
</head>
<body>
<div id="root"></div>
<script src="/assets/app.js"></script>
</body>
</html>
`

async function main(): Promise<void> {
  console.log('Cleaning dist-web/ ...')
  rmSync(OUT, { recursive: true, force: true })
  mkdirSync(resolve(OUT, 'assets'), { recursive: true })

  console.log('Building browser bundle -> dist-web/assets/app.js')
  await build({
    entryPoints: [resolve(ROOT, 'src/web/entry.tsx')],
    outfile: resolve(OUT, 'assets/app.js'),
    bundle: true,
    platform: 'browser',
    target: 'es2022',
    format: 'iife',
    sourcemap: true,
    minify: false,
    jsx: 'automatic',
    define: { 'process.env.NODE_ENV': '"production"' },
    logLevel: 'warning',
  })

  console.log('Building web server -> dist-web/server.mjs')
  await build({
    entryPoints: [resolve(ROOT, 'src/web/server.ts')],
    outfile: resolve(OUT, 'server.mjs'),
    bundle: true,
    platform: 'node',
    target: 'node22',
    format: 'esm',
    sourcemap: true,
    logLevel: 'warning',
  })

  writeFileSync(resolve(OUT, 'index.html'), INDEX_HTML, 'utf8')

  console.log('Build complete.')
  console.log('  page:   dist-web/index.html')
  console.log('  client: dist-web/assets/app.js')
  console.log('  server: dist-web/server.mjs')
}

main().catch((error: unknown) => {
  console.error(error)
  process.exit(1)
})
