# 开发指南（Windows）

本文说明如何在 Windows 上获取源码、编译构建、把插件链接到 dsh desktop、
日常开发时如何让改动生效，以及如何手动卸载。

打包与在桌面版安装的完整步骤见 [README.md](README.md)。

## 1. 环境要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10 / 11 |
| Node.js | ≥ 22.5（本工程在 v24.14.0 上验证） |
| 包管理器 | npm（随 Node 安装） |
| 终端 | PowerShell 5.1 或 PowerShell 7 |
| dsh desktop | DeepSeek Harness 已安装（本机位于 `F:\DSH`） |

确认环境：

```powershell
node -v
npm -v
# 查 desktop 安装路径（未运行时跳过）
Get-Process "DeepSeek Harness" -ErrorAction SilentlyContinue |
  Select-Object -First 1 -ExpandProperty Path
```

## 2. 获取源码

```powershell
git clone https://gitee.com/ABCDRD/dsh-datascience-demo.git
cd dsh-datascience-demo
```

也可以从 Gitee/GitHub 页面下载 ZIP 后解压。

## 3. 安装依赖与构建

```powershell
npm install
npm run build
```

构建产物：

| 文件 | 作用 |
| --- | --- |
| `lib/index.js` | 宿主端，在 desktop 的 Node 进程中运行 |
| `lib/client.js` | 浏览器端，由桌面窗口按包名 `dsh-datascience-demo` 加载 |

可选检查：

```powershell
npm run typecheck
```

开发时可让构建常驻：

```powershell
npm run build:watch
```

## 4. 链接到 dsh desktop

dsh desktop 的 profile 默认位于：

```text
%USERPROFILE%\.dsh\profiles\desktop
```

如果设置了 `DSH_HOME`，请换成 `$env:DSH_HOME\profiles\desktop`。

### 4.1 建立目录联接（Junction）

链接指向源码工程，后续改代码不用再复制文件：

```powershell
$dest = "$env:USERPROFILE\.dsh\profiles\desktop\node_modules\dsh-datascience-demo"
$src  = "f:\code\dsh-datascience-demo"   # 改成你的工程目录

if (Test-Path $dest) {
    # 只删链接本身，不碰工程目录
    [System.IO.Directory]::Delete($dest)
}
New-Item -ItemType Junction -Path $dest -Target $src
```

Junction 不需要管理员权限。创建后 `$dest` 下应能直接看到本工程的
`lib/`、`package.json` 等文件。

### 4.2 注册到 profile 的插件清单

先备份：

```powershell
Copy-Item "$env:USERPROFILE\.dsh\profiles\desktop\package.json" `
          "$env:USERPROFILE\.dsh\profiles\desktop\package.json.bak-dsd"
```

编辑 `%USERPROFILE%\.dsh\profiles\desktop\package.json`，在
`dsh.profile.bundles` 末尾追加 `"dsh-datascience-demo"`：

```json
{
  "name": "dsh-profile-desktop",
  "private": true,
  "dependencies": {
    "dsh-database-manager": "^0.1.2"
  },
  "dsh": {
    "profile": {
      "bundles": [
        "@deepseek-ai/dsh-base",
        "@deepseek-ai/dsh-web-app",
        "dsh-database-manager",
        "dsh-datascience-demo"
      ]
    }
  }
}
```

### 4.3 重启 desktop

完全退出 DeepSeek Harness 后重新启动。启动后左侧边栏出现
「数据科学示例」菜单，点击即可打开空白面板。

## 5. 日常开发：编译后如何生效

链接保留后，**不需要重新安装**。每次改完代码只需重新构建，再按改动位置
选择刷新或重启：

| 改动位置 | 生效方式 |
| --- | --- |
| `src/client/`（界面、侧边栏、面板） | `npm run build` → desktop 窗口内按 `Ctrl+R` 刷新；不生效再按 `Ctrl+Shift+R` 强制刷新 |
| `src/index.ts`（宿主端） | `npm run build` → 必须重启 DeepSeek Harness |
| `package.json` 的 `dsh` 字段、`cordis.patch.yml` | 重启 DeepSeek Harness |
| `npm install` 新增依赖、改构建脚本 | `npm run build` → 重启 DeepSeek Harness |

### 一键构建 + 重启 desktop

把下面的片段保存成 PowerShell 函数或在终端里直接执行。把 `$dshExe`
换成实际安装路径：

```powershell
$dshExe = "F:\DSH\DeepSeek Harness.exe"

npm run build

Get-Process "DeepSeek Harness" -ErrorAction SilentlyContinue |
  Stop-Process -Force
Start-Process $dshExe
```

dsh desktop 会自动持久化会话，强制退出不会丢会话数据。重启后插件才重新
读取 `lib/index.js` 与 `lib/client.js`。

### 更快的本地调试（可选）

desktop 的界面插件调试可以改用命令行 web profile，避免反复重启 desktop：

```powershell
# 只把插件链接到 web profile
$dest = "$env:USERPROFILE\.dsh\profiles\web\node_modules\dsh-datascience-demo"
if (Test-Path $dest) { [System.IO.Directory]::Delete($dest) }
New-Item -ItemType Junction -Path $dest -Target "f:\code\dsh-datascience-demo"

# 在 web profile 的 package.json 里同样追加 bundles 条目，然后启动
npx @deepseek-ai/dsh web --port 3099
```

启动日志会打印带 token 的访问地址，用浏览器打开即可调试。确认功能后，
再重启 desktop 做最终验证。

## 6. 手动卸载

1. 完全退出 DeepSeek Harness。
2. 编辑 `%USERPROFILE%\.dsh\profiles\desktop\package.json`，从
   `dsh.profile.bundles` 中删除 `"dsh-datascience-demo"`。
3. 删除插件目录。**注意区分目录联接与真实复制的目录**：

```powershell
$dest = "$env:USERPROFILE\.dsh\profiles\desktop\node_modules\dsh-datascience-demo"

if (Test-Path $dest) {
    $item = Get-Item $dest -Force
    if ($item.LinkType -eq 'Junction') {
        # 只删除链接本身，源码工程不受影响
        [System.IO.Directory]::Delete($dest)
    } else {
        # 真实复制的插件目录（例如从 tgz 解包安装的），可以递归删除
        Remove-Item $dest -Recurse -Force
    }
}
```

> 不要对 Junction 使用 `Remove-Item -Recurse`：它可能沿着链接把工程目录
> 里的文件一起删掉。

4. 重启 DeepSeek Harness。

如果需要回滚到安装插件前的配置，可用之前备份的 `package.json.bak-dsd`：

```powershell
Copy-Item "$env:USERPROFILE\.dsh\profiles\desktop\package.json.bak-dsd" `
          "$env:USERPROFILE\.dsh\profiles\desktop\package.json" -Force
```

## 7. 常见问题

**左侧没有「数据科学示例」菜单**

- 确认 `package.json` 的 `bundles` 中有 `dsh-datascience-demo`；
- 确认 `node_modules\dsh-datascience-demo\lib\client.js` 存在；
- 确认 desktop 已完全退出并重启（不是只关闭窗口）。

**改了代码，界面没变化**

- 是否执行过 `npm run build`（desktop 读取的是 `lib/`，不是 `src/`）；
- 只改 client 时，先刷新（`Ctrl+R` / `Ctrl+Shift+R`），仍无效就重启；
- 改宿主端时，刷新无效，必须重启进程。

**不要用 npm pack / 复制覆盖已链接的目录**

`npm pack` 只用于分发。日常开发保持 Junction + `npm run build` 即可，避免
把链接替换成静态副本，导致后续改动不生效。

**desktop 升级后插件消失**

desktop 升级可能重建 profile。重新检查 `bundles` 条目和 Junction，按第 4 节
重新链接并重启。
