# dsh-datascience-demo

DSH（DeepSeek Harness）的「数据科学示例」插件（英文名 `datascience-demo`，包名 `dsh-datascience-demo`）。

安装后，左侧边栏「插件」区域会出现「数据科学示例」菜单；点击它，右侧中央区域会打开一个空白面板。

## 工程结构

```text
src/
  index.ts         宿主端入口（cordis 插件行，目前无宿主能力）
  client/index.ts  浏览器端入口：侧边栏入口 + 空白主面板
scripts/build.ts   构建脚本（esbuild）
cordis.patch.yml   bundle patch：把插件行插入 profile 的插件清单
lib/               构建产物（index.js 宿主端 / client.js 浏览器端）
```

插件走 dsh 官方扩展点，未修改 harness 本身：

| 槽位 | 用途 |
| --- | --- |
| `sidebar.panellist` | 左侧边栏的「数据科学示例」入口，id 为 `datascience-demo` |
| `main`（keyed） | 右侧空白面板，key 同为 `datascience-demo` |

侧边栏条目的 id 与 `main` 槽位的 key 相同，shell 点击条目时会调用
`layout.selectPanel('datascience-demo')`；点击任意会话行则自动回到会话。

## 环境要求

- Node.js ≥ 22.5
- dsh 0.2.x（本插件在 dsh 0.2.1-rc.5 上验证）

## 开发与构建

```bash
npm install
npm run build      # 产出 lib/index.js 与 lib/client.js
npm run typecheck  # TypeScript 类型检查
```

`npm run build` 必须在打包前执行一次；`lib/` 是构建产物，已加入 `.gitignore`。

## 打包

```bash
npm run build
npm pack
```

产物为 `dsh-datascience-demo-0.1.0.tgz`，其中包含 `package.json`、`lib/`、
`cordis.patch.yml`、`src/` 与 README 等运行所需文件。

## 在 dsh desktop 中手动安装

dsh desktop 的 profile 由 Electron 独占管理，命令行 `dsh plugin` 不能操作
`desktop` profile，因此采用「放文件 + 改 bundles」的手动方式。

> 默认 profile 目录：`%USERPROFILE%\.dsh\profiles\desktop`
> 如果设置了 `DSH_HOME`，请把它替换为实际的 `$DSH_HOME\profiles\desktop`。

### 1. 放入插件目录

**方式 A：用打包产物（推荐，适合分发）**

```powershell
npm run build
npm pack

$dest = "$env:USERPROFILE\.dsh\profiles\desktop\node_modules\dsh-datascience-demo"
$tmp  = "$env:TEMP\dsh-datascience-demo"

Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
tar -xzf .\dsh-datascience-demo-0.1.0.tgz -C $tmp
Copy-Item "$tmp\package" $dest -Recurse
```

tgz 解包后是 `package/` 目录，复制到 `node_modules\dsh-datascience-demo` 即可。

**方式 B：开发调试（目录联接，改代码后只需重启 desktop）**

```powershell
$dest = "$env:USERPROFILE\.dsh\profiles\desktop\node_modules\dsh-datascience-demo"
Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Junction -Path $dest -Target "f:\code\dsh-datascience-demo"
```

### 2. 注册到 profile 的插件清单

先备份，再编辑
`%USERPROFILE%\.dsh\profiles\desktop\package.json`，在 `dsh.profile.bundles`
数组末尾追加 `"dsh-datascience-demo"`：

```powershell
Copy-Item "$env:USERPROFILE\.dsh\profiles\desktop\package.json" `
          "$env:USERPROFILE\.dsh\profiles\desktop\package.json.bak"
```

```json
{
  "dsh": {
    "profile": {
      "bundles": [
        "@deepseek-ai/dsh-base",
        "@deepseek-ai/dsh-web-app",
        "dsh-datascience-demo"
      ]
    }
  }
}
```

### 3. 重启 desktop

完全退出 DeepSeek Harness（包括托盘进程），再重新启动。插件在启动时随
profile 加载，重启后左侧边栏「插件」区域会出现「数据科学示例」菜单，
点击即可在右侧打开空白面板。

### 安装检查

- 目录存在：`...\profiles\desktop\node_modules\dsh-datascience-demo\lib\client.js`
- `package.json` 的 `dsh.profile.bundles` 含 `dsh-datascience-demo`
- desktop 启动后侧边栏出现「数据科学示例」

> 这套步骤同样适用于其他 dsh profile（如命令行 `dsh web` 使用的
> `%USERPROFILE%\.dsh\profiles\web`），把路径中的 `desktop` 换成 `web` 即可；
> 也可以直接用 `npx @deepseek-ai/dsh plugin --profile web add <包或路径>`。

## 卸载

1. 从 `%USERPROFILE%\.dsh\profiles\desktop\package.json` 的
   `dsh.profile.bundles` 中删除 `"dsh-datascience-demo"`；
2. 删除 `...\profiles\desktop\node_modules\dsh-datascience-demo`；
3. 重启 DeepSeek Harness。
