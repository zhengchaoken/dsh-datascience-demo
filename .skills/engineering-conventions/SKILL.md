---
name: engineering-conventions
description: Apply proven TypeScript and Node.js engineering conventions covering delivery, cross-platform setup, UI rendering, and security boundaries. Use when writing, reviewing, or debugging code in this workspace, including build, deploy, environment, or database changes. Do not use for general knowledge questions.
---

# 个人工程经验范式

这些规则来自真实踩坑与用户多次纠正，不是通用建议。动手前先扫「铁律」，再按主题查 references。

## 铁律（违反即为返工）

1. **直接产出**：要文件就给完整文件，不给示例、提纲、占位内容。不提问、不解释计划、不输出与产物无关的话。
2. **先读后改**：改之前读完相关文件。优先编辑现有文件，不新建不必要的文件，不主动创建 README 或文档。
3. **最小改动**：只动被要求的部分。不顺手重构、不提前抽象、不为假想需求加配置。
4. **对外界面零痕迹**：面向最终用户的界面不出现内部校对说明、技术实现细节、AI 味表述。不一致之处只在对话框里说明，不写进界面。
5. **完成前必须真实校验**：跑过 typecheck / build / 实际请求才算完成。没跑过不能说「已通过」。
6. **错误必须可读**：不要只抛「退出码 1」，要带失败命令和最后几行输出；不要吞异常。
7. **不假设 Unix**：命令、路径、可执行文件名都要考虑 Windows 与 PowerShell。
8. **安全默认最小权限**：不拼 shell 字符串，不信任用户传入的地址、路径、命令。
9. **凭证三不**：不进业务数据库、不进前端产物、不进日志。库表里只存引用 ID。
10. **环境改动要重启才生效**：改宿主端代码、改库结构、改环境变量后，按 references/cross-platform-and-env.md 的收尾清单执行。

## 查阅指引

| 正在做的事 | 读这个 |
|---|---|
| 交付节奏、沟通方式、文件产出 | references/delivery-and-communication.md |
| TypeScript / Node 编码、模块、子进程 | references/typescript-node.md |
| 前端界面、Markdown 与报告渲染 | references/frontend-and-rendering.md |
| 跨平台命令、Python 环境、端口、重启 | references/cross-platform-and-env.md |
| 部署形态、鉴权、密钥、外部命令 | references/security-and-architecture.md |
| SQLite 查询、Python 脚本、长任务 | references/data-and-python.md |

## 一页速查

| 现象 | 根因 | 正确做法 |
|---|---|---|
| 图表中文乱码 | seaborn 的 set_style 会重置字体 | set_style 之后再设置中文字体 |
| 报告图片裂开 | 用了绝对路径 | Markdown 图片一律写相对路径 |
| 面板渲染卡死或 OOM | Markdown 里以 `|` 开头的非表格行 | 解析器加容错，或改写该行 |
| 页面显示 `<a id="...">` 原文 | 锚点标签残留且渲染器不解析 | 删除所有锚点残留 |
| Windows 命令报语法错误 | PowerShell 5 不支持 `&&` 和 heredoc | 用 `;` 串联，用 `$LASTEXITCODE` 判断 |
| 构建产物里搜不到中文 | esbuild 默认 charset=ascii 转义成 \uXXXX | 搜 ASCII 类名或属性名来验证 |
| `require is not defined` | ESM 项目里混用 CJS | 全链路统一 ESM 或统一 CJS，不靠改后缀补洞 |
| Ubuntu 建 venv 失败 | ensurepip 被拆到 python3.x-venv 包 | 装对应版本 venv 包，用 ensurepip 校验后重建 |
| 装了依赖但没生效 | 只执行安装，没有校验 | 每步装完立刻跑校验命令 |
| 端口占用起不来 | 旧进程仍在监听 | 先查 Listen 状态再强杀，不要盲目重启 |
| 插件改动不生效 | 宿主常驻进程未退出 | 完全退出宿主（含托盘进程）再启动 |
| 改了库结构没生效 | 旧 sqlite 文件仍在 | 停后端 → 删库文件 → 重启 |
| 长任务把服务卡住 | 没有超时和进程组管理 | 超时 + 杀整个进程组 + 队列限并发 |
