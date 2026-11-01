# 跨平台与环境范式

## Python 版本判定

- 最低版本只比 `major.minor`，不要用 `version.startsWith('3.12.')` 这类硬编码。
- 高于最低版本的（如 3.14）视为可用，但要提示「个别依赖可能缺少预编译包」。
- 探测用候选链：`python3.13 → python3.12 → python3 → python → py -3.13/-3.12/-3`，逐个校验版本，不要只探测第一个。

## 虚拟环境

创建 `.venv` 失败不能直接终止，要按发行版补齐支持后重试一次：

| 平台 / 发行版 | 补齐方式 |
|---|---|
| Debian / Ubuntu | 先 `apt-get update`，装 `python3.x-venv`（版本按探测结果拼），失败再试 `python3-venv` |
| Fedora / RHEL | `python3.x-pip` → `python3-pip` |
| Alpine | `apk add --no-cache py3-pip` |
| Termux | 跳过（`pkg install python` 自带 venv） |
| macOS | `brew install python@3.12` |
| Windows x64 | 官方安装包静默安装；非 x64 直接给手动指引 |

- 每装一个包后立刻用 `python -m ensurepip --version` 校验，避免「装了但没生效」被误判成功。
- 补齐后删除残留的半个 `.venv` 再重建，不要在半成品上继续。
- 失败时要给出手动命令，而不是只报退出码。

## 提权

- 先判断是否 root；非 root 再试免密 `sudo -n`；两者都没有就提示用户手动执行，不要反复重试。
- 不要再给用户弹交互式密码输入。

## pip 源

- 默认国内镜像，界面可改；用户留空时回落到默认源。
- 校验协议只允许 `http` / `https`；非法地址直接拒绝并给明确提示。
- 传 `--index-url` 与 `--trusted-host`；`--disable-pip-version-check --no-cache-dir` 减少噪声。
- 装 requirements 时加 `--no-build-isolation`，避免又去拉构建依赖。

## PowerShell（Windows 默认 shell）

- PowerShell 5 不支持 `&&`、`||`、heredoc。用 `;` 串联，用 `$LASTEXITCODE` 判断上一条命令是否成功。
- 路径含空格要加双引号。
- 不要用 `cd` 改变会话状态，用工具提供的 `cwd` 参数。
- 查端口占用：`Get-NetTCPConnection -LocalPort <port> -State Listen`，再 `Stop-Process -Force`；不要靠反复重启碰运气。
- 停服务不要依赖优雅退出，超时后直接强杀进程。

## esbuild 产物排查

esbuild 默认 `charset=ascii`，中文会被转义成 `\uXXXX`，所以在打包产物里搜中文一定搜不到。验证代码是否进包时，搜 ASCII 标识（类名、CSS 类名、属性名）。

## 生效清单（改动后必须执行）

| 改动类型 | 生效步骤 |
|---|---|
| 宿主端插件代码 | 完全退出宿主应用（含托盘进程）→ 重新启动 |
| 独立 Web 服务 | 重启该 node 进程 |
| 数据库结构或初始化脚本 | 停后端 → 删除 sqlite 库文件 → 重启后端 |
| 环境变量 | 重启对应进程（进程内读取的不会热更新） |
| 前端静态产物 | 重新 build 并刷新（注意浏览器缓存） |

## 版本控制

- `git push` 偶发远端瞬时不可达，先校验 SSH 认证正常，再重试一次即可，不要改远端配置。
- 提交信息写「为什么」，不写「改了什么文件」。
