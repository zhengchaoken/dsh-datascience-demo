# 独立 Web 部署方案

## 1 结论

可行，且不需要动核心代码的业务逻辑。当前工程本来就分成三块：

- 面板 UI（`src/client/*`）：纯 React，所有请求走相对地址 `/api/dsh-datascience/...`
- 后端能力（`src/routes.ts`、`src/env/*`、`src/data/ecommerce/dataset.ts`、`src/docs/docs.ts`）：纯 Node 的 `(req, res)` 处理函数
- DSH 适配层（`src/index.ts`、`src/client/index.ts`、`src/tools.ts`）：只做「注册到宿主」

只有第三块与 DSH 绑定。换一个外壳：新写一个浏览器入口 + 一个自己的 HTTP 服务，把前两块原样挂上去，就得到一个可独立部署的 Web 工程。插件产物 `lib/index.js`、`lib/client.js` 与 `dsh` 配置完全不变。

## 2 可行性依据

### 2.1 路由不依赖宿主

`makeRoutes()` 返回的是 `{ kind: 'prefix', path: '/api/dsh-datascience', handler }`，`handler` 自己解析 `req.url`、自己写响应头，没有任何 cordis 上下文。DSH 侧只是把它注册进 `ctx.webServer`，Web 侧直接把它交给 `createServer` 的回调即可。

### 2.2 前端不依赖宿主

`App` 只用到两样东西：React 和 `/api/dsh-datascience` 相对接口。`api.ts` 里的 `const BASE = '/api/dsh-datascience'` 在同源 Web 服务下天然成立，图片与 HTML 报告通过 `/doc-asset` 相对地址加载。原先「宿主提供 react」的约定，在独立部署时改成「构建时把 react 打进自己的 bundle」，对 `lib/client.js` 没有影响。

### 2.3 数据与文档路径自适应

`src/docs/docs.ts` 与 `src/data/ecommerce/dataset.ts` 都用候选路径按存在性定位：

- `dist-web/server.mjs` → `../src/data/...` 命中工程根的 `src/data`
- 源码直跑 → `../../src/data/...` 命中

`src/env/probe.ts` 的 `packageRoot()` 从运行文件向上找 `package.json`，在 `dist-web/` 下同样命中工程根，因此 `requirements.txt` 与工作区 `.venv` 的定位规则不变。`resolveWorkspace()` 仍支持 `DSD_WORKSPACE` 覆盖。

### 2.4 复用边界

| 模块 | DSH 插件里的角色 | Web 里的角色 | 是否改动 |
|:--|:--|:--|:--|
| src/routes.ts | 注册到宿主 webServer | 交给自己的 http server | 不改 |
| src/env/probe.ts、install.ts | 环境检查与安装 | 同左 | 不改 |
| src/data/ecommerce/dataset.ts | 示例数据接口 | 同左 | 不改 |
| src/docs/docs.ts | 文档与图表接口 | 同左 | 不改 |
| src/client/* | 面板 UI 与 API 客户端 | 同左 | 不改 |
| src/index.ts、src/tools.ts | 宿主端插件 + 模型工具 | 不加载 | 不改 |
| src/client/index.ts | slots 注册 | 不加载，由新入口接管 | 不改 |

## 3 实现

### 3.1 新增文件

```
src/web/entry.tsx     浏览器入口：createRoot + 注入 APP_CSS
src/web/server.ts     独立 HTTP 服务：API + 静态资源
scripts/build-web.ts  Web 构建：dist-web/index.html + assets/app.js + server.mjs
runweb.md             本文档
```

### 3.2 浏览器入口

`src/web/entry.tsx` 做三件事：注入与插件同一份 `APP_CSS`、挂载 `App`、保证容器高度铺满视口。

```tsx
const container = document.getElementById('root')
createRoot(container).render(
  React.createElement('div', { style: { display: 'flex', height: '100vh', minHeight: 0 } },
    React.createElement(App)),
)
```

不复用 `src/client/index.ts`：那里是 slots 注册逻辑，与浏览器入口是两种外壳，互不干扰。

### 3.3 服务端

`src/web/server.ts` 的顺序是：先处理 `/api/dsh-datascience` 前缀，再处理静态资源，其余 404。静态只放行 `/`、`/index.html` 与 `assets/` 下的单层文件名，避免目录穿越。

```ts
const { routes } = makeRoutes({ install })
const apiHandler = routes[0]!.handler

if (pathname === API_PREFIX || pathname.startsWith(`${API_PREFIX}/`)) {
  await apiHandler(req, res)
  return
}
```

### 3.4 构建产物

`npm run build:web` 用与插件同一套 esbuild-wasm：

- `src/web/entry.tsx` → `dist-web/assets/app.js`（iife，react 打进产物）
- `src/web/server.ts` → `dist-web/server.mjs`（ESM，Node 内置模块保持 external）
- 生成 `dist-web/index.html`（一个挂载点 + 基础 reset）

`dist-web/` 已加入 `.gitignore`。插件构建 `lib/` 不受影响，两条产物线可以并行存在。

### 3.5 脚本

```json
"build:web": "tsx scripts/build-web.ts",
"web": "npm run build:web && node dist-web/server.mjs",
"web:serve": "node dist-web/server.mjs"
```

`react`、`react-dom`、`@types/react-dom` 放在 `devDependencies`：只在构建 Web bundle 时使用，运行时由产物自带，插件的 `peerDependencies` 仍只有 `@deepseek-ai/dsh-tools`。

## 4 运行

### 4.1 本机运行

```powershell
npm install
npm run web
```

浏览器打开 `http://127.0.0.1:5180`。首次进入「环境检查」创建 `.venv` 并安装依赖，与 DSH 面板流程一致。

### 4.2 参数与环境变量

| 配置 | 命令行 | 环境变量 | 默认值 |
|:--|:--|:--|:--|
| 端口 | `--port 5180` | `DSD_WEB_PORT` | `5180` |
| 监听地址 | `--host 127.0.0.1` | `DSD_WEB_HOST` | `127.0.0.1` |
| 工作区 | `--workspace <目录>` | `DSD_WORKSPACE` | 当前目录 |

`--workspace` 会切换进程工作目录，`.venv`、Python 脚本的运行位置、`requirements.txt` 的读取基准都随之生效。

### 4.3 部署目录

Web 服务不是纯静态站点：它要读 SQLite、要调 Python，必须有 Node 进程。最小部署目录：

```
你的部署目录/
├─ dist-web/            npm run build:web 的产物
├─ src/data/            数据库、报告、图表、HTML 报告、harness 文档
├─ requirements.txt     环境检查页读取的依赖清单
├─ package.json         probe 用来定位工程根（name 必须为 dsh-datascience-demo）
├─ .venv/               首次安装后生成
└─ node_modules/        仅运行 dist-web/server.mjs 时不需要；跑 tsx 开发模式才需要
```

复制时保留 `dist-web/` 与 `src/data/` 的相对位置即可。

### 4.4 常驻与反向代理

- Windows 常驻：`nssm install dsh-web "node" "dist-web/server.mjs --port 5180"`，工作目录设为部署目录
- Linux 常驻：systemd 或 pm2 `pm2 start dist-web/server.mjs --name dsh-web`
- 反向代理：Nginx `location / { proxy_pass http://127.0.0.1:5180; }`，接口与页面同源，无需额外改 `BASE`

对外暴露前建议加一层鉴权（Nginx Basic Auth 或内网访问控制）：面板能执行安装任务与只读 SQL，不适合直接公网开放。

## 5 与插件的关系

- `npm run build` 仍只产出 `lib/index.js` 与 `lib/client.js`，`npm pack` 的内容不变
- `dsh.profile.bundles` 登记、DSH 侧菜单、5 个模型工具、skills 全部照旧
- 两边读同一份 `src/data`，报告与图表天然同步；同一时刻只建议一个进程跑分析脚本，避免同一份报告被并发覆盖
- 安装任务的状态各自进程独立，DSH 与 Web 互不感知

## 6 验证记录

| 验证项 | 结果 |
|:--|:--|
| `npm run typecheck` | 通过 |
| `npm run build:web` | 产出 index.html、assets/app.js、server.mjs |
| `GET /` | 200，返回页面外壳 |
| `GET /assets/app.js` | 200 |
| `GET /api/dsh-datascience/docs` | 200，返回 8 个文档条目 |
| `GET /api/dsh-datascience/dataset` | 200，engine 为 `node:sqlite` |
| `GET /api/dsh-datascience/doc?path=L2/clustering_report.md` | 200，标题与正文正常 |
| `GET /api/dsh-datascience/doc-asset?path=L2/images_clustering/3_1_dendrogram.png` | 200，`image/png` |
| `GET /api/dsh-datascience/doc-asset?path=profiling/report_analyst.html` | 200，`text/html` |
| `GET /api/dsh-datascience/environment` | 200，工作区解析正确 |
| 浏览器打开 `/#/harness` | 侧边栏五个一级菜单齐全，Harness 文档正常渲染，无白屏 |

## 7 限制

1. 需要 Node 22.5 及以上：查询引擎用内置 `node:sqlite`
2. 数据分析仍依赖本机 Python 与工作区 `.venv`，Web 提供服务入口，不提供 Python 运行时
3. 一个进程对应一个工作区；多套数据请用多个进程 + 不同 `--workspace` 与端口
4. 安装任务是进程内单例，重启服务会丢失安装日志，`.venv` 已生成的部分不受影响
5. 当前不内置登录鉴权，默认只监听 `127.0.0.1`
