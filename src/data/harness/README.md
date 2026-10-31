# Harness 工具与安装指南

本插件除左侧面板外，还向 DeepSeek Harness（DSH）注册了 5 个模型工具。装上插件后，直接在对话里说「跑一下 L2 的因果分析」「对这份数据做个体检」，模型就会调用这里的工具完成分析，并把报告写到 `src/data` 下，与面板里的文档同步。

## 目录

- 1 工具总览
- 2 在 DSH 中安装本插件
- 3 首次使用：准备运行环境
- 4 工具用法与示例（每个工具一节，含可直接复制的调用示例）
- 5 指定自己的数据源
- 6 组装一次完整分析
- 7 常见问题

---

# 1. 工具总览

| 工具 | 用途 | 关键参数 | 产出 |
|:--|:--|:--|:--|
| ds_query | 对电商示例库执行一条只读 SQL，用于核对口径、验证假设、取样本 | `sql` | 结果表（Markdown 表格文本）、行数与是否截断 |
| ds_profiling | 对指定 SQLite 库做数据探查：结构、缺失、一致性、分布、建模就绪度 | `database`、`tables` | `profiling/data_profiling_report.md` 与图表、结论摘要 |
| ds_run_analysis | 运行 L1~L5 与工程化的分析脚本，返回执行输出与报告摘要 | `analysis` | 对应层的报告与图表、运行日志尾部 |
| ds_read_report | 读取 `src/data` 下的报告或方法论文档正文 | `path` | 文档标题与正文（超过 12000 字符截断） |
| ds_list_analyses | 列出全部可运行脚本及报告路径 | 无 | 27 个脚本的清单 |

工具与面板共用同一份资产：脚本、报告、数据库都在工作区 `src/data` 下，工具跑完后面板里打开对应文档即可看到新内容。

安全边界：只运行白名单脚本，只接受只读 `select` / `with` 语句，只读取 `src/data` 下的文档。

# 2. 在 DSH 中安装本插件

DSH Desktop 的 profile 由桌面端独占管理，命令行 `dsh plugin` 改不了 `desktop` profile，因此采用「放文件 + 登记清单」的方式。

默认 profile 目录：`%USERPROFILE%\.dsh\profiles\desktop`；如果设置了 `DSH_HOME`，替换为实际的 `$DSH_HOME\profiles\desktop`。

## 2.1 放入插件目录

开发调试用目录联接，改完代码只需重启桌面端：

```powershell
$dest = "$env:USERPROFILE\.dsh\profiles\desktop\node_modules\dsh-datascience-demo"
Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Junction -Path $dest -Target "f:\code\dsh-datascience-demo"
```

分发给他人时改用打包产物：先 `npm run build` 与 `npm pack`，把 tgz 解包出的 `package/` 目录复制到上面的 `$dest`。

## 2.2 登记到插件清单

备份后编辑 `%USERPROFILE%\.dsh\profiles\desktop\package.json`，在 `dsh.profile.bundles` 数组末尾追加包名：

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

## 2.3 重启桌面端

完全退出 DeepSeek Harness（包括托盘进程）再启动。插件随 profile 在启动时加载，只刷新页面不会加载新的宿主端代码。

安装检查：

- `...\profiles\desktop\node_modules\dsh-datascience-demo\lib\client.js` 存在
- `package.json` 的 `dsh.profile.bundles` 含 `dsh-datascience-demo`
- 启动后左侧边栏出现「数据科学示例」，对话中可调用 `ds_query` 等 5 个工具

命令行 profile（`dsh web` 使用的 `%USERPROFILE%\.dsh\profiles\web`）用同一步骤，把路径中的 `desktop` 换成 `web`，或直接执行 `npx @deepseek-ai/dsh plugin --profile web add <包或路径>`。

# 3. 首次使用：准备运行环境

分析脚本跑在本机 Python 上，插件优先使用工作区的 `.venv`，找不到时退回 PATH 里的 `python`。

1. 面板「环境检查」查看系统信息、Python 版本与环境管理器
2. 点击安装，插件在当前工作目录创建 `.venv`，并用清华 PyPI 镜像安装 `requirements.txt` 中的依赖
3. 安装完成后回到「环境检查」确认依赖清单全部可用

也可以在命令行手动完成同样的事：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt `
  --index-url https://pypi.tuna.tsinghua.edu.cn/simple `
  --trusted-host pypi.tuna.tsinghua.edu.cn
```

# 4. 工具用法与示例

调用方式有两种：在对话里描述需求，让模型自己挑工具；或明确点名工具与参数。每个工具下面给一个可直接复用的例子。

## 4.1 ds_query：只读 SQL 查询

参数 `sql` 必填，只允许单条只读语句，默认库是 `src/data/ecommerce/ecommerce.db`。

**示例（对话）**

> 查一下 2025 年 5 月已完成和已发货订单的日均 GMV。

**示例（调用参数）**

```json
{
  "sql": "select date(created_at) as d, round(sum(total_amount), 2) as gmv, count(*) as orders from orders where order_status in ('已完成', '已发货') and created_at >= '2025-05-01' and created_at < '2025-06-01' group by 1 order by 1 limit 100"
}
```

**返回**

```
d          | gmv       | orders
-----------+-----------+-------
2025-05-01 | 128634.55 | 214
2025-05-02 | 135902.10 | 227
...
```

结果表格最多展示 200 行，超出部分标注「已省略」。

## 4.2 ds_profiling：数据探查

参数都可选：`database` 默认 `src/data/ecommerce/ecommerce.db`，`tables` 为逗号分隔的表名，默认探查全部业务表。

**示例（对话）**

> 对 `src/data/mydata/orders.db` 的 orders、order_items 两张表做一次数据体检。

**示例（调用参数）**

```json
{
  "database": "src/data/mydata/orders.db",
  "tables": "orders,order_items"
}
```

**返回**

- `reportPath`：`src/data/profiling/data_profiling_report.md`
- `summary`：报告开头 26 行，包含规模、字段、风险与建模就绪度结论
- `output`：执行日志尾部

**注意**：报告固定写回 `src/data/profiling/`，探查自己的库时会覆盖示例库的探查报告。需要保留两份时，先把旧报告另存。

## 4.3 ds_run_analysis：运行分析脚本

参数 `analysis` 必填，取值为脚本键。运行超时 30 分钟。

**示例（对话）**

> 重新跑一下 L2 的因果推断，然后告诉我处理效应是多少。

**示例（调用参数）**

```json
{
  "analysis": "L2-causal"
}
```

**返回**

```
[ok] 报告：L2/causal_report.md

# 因果推断报告 - 优惠券对客单价的影响
...
--- 执行输出（尾部） ---
[匹配] 卡尺=0.0137, 匹配对数=3938 / 处理组3938
```

常用键：

| 层次 | 脚本键 |
|:--|:--|
| L1 描述性 | L1-eda、L1-cross、L1-geo、L1-text |
| L2 诊断性 | L2-diagnostic、L2-causal、L2-granger、L2-anomaly、L2-clustering、L2-sequence |
| L3 预测性 | L3-predictive、L3-ensemble、L3-multistep、L3-quantile、L3-transfer、L3-shap |
| L4 规范性 | L4-prescriptive、L4-dqn、L4-bandit、L4-multiobjective、L4-causal-rec |
| L5 认知性 | L5-continual、L5-meta、L5-multimodal |
| 工程化 | ENG-distributed、ENG-ab、ENG-quality |

## 4.4 ds_read_report：读取报告

参数 `path` 必填，相对 `src/data`，只支持 Markdown。

**示例（对话）**

> 把数据探查报告里关于缺失和重复的结论读出来。

**示例（调用参数）**

```json
{
  "path": "profiling/data_profiling_report.md"
}
```

**返回** `title` 与 `content`，正文超过 12000 字符时返回前 12000 字符并标记 `truncated: true`。

## 4.5 ds_list_analyses：查看脚本清单

无参数，返回每个脚本的键、层次、中文名称、脚本路径与报告路径。

**示例（对话）**

> 现在有哪些分析可以跑？

**返回（节选）**

```
27 个分析脚本：
L1-eda | L1 | 描述性主报告 | 脚本 src/data/L1/generate_report.py | 报告 L1/eda_report.md
L2-clustering | L2 | 客户聚类 | 脚本 src/data/L2/l2_clustering.py | 报告 L2/clustering_report.md
...
```

不确定脚本键时先调它，比猜路径可靠。

# 5 指定自己的数据源

分析脚本统一从 `src/data/ecommerce/ecommerce.db` 读数据，因此接入自有数据有三种方式，按改动力度从低到高。

## 5.1 只探查，不动脚本

把自己的 SQLite 库放在 `src/data` 下任意目录，例如 `src/data/mydata/orders.db`，然后调用 `ds_profiling`：

```json
{ "database": "src/data/mydata/orders.db", "tables": "orders,order_items" }
```

适合建模前的体检、把字段含义讲清楚、判断数据能不能支撑后续分析。

## 5.2 替换示例库

把自己的数据整理成与示例库一致的表结构（`orders`、`order_items`、`products`、`customers`、`payments`、`reviews`、`categories`、`coupons`、`user_events`），命名为 `ecommerce.db` 放回 `src/data/ecommerce/`。所有 L1~L5 与工程化脚本、`ds_query` 都不用改就能跑。

字段口径在「示例数据 → 数据集概览」里有完整说明；示例库本身由 `src/data/ecommerce/generate_dataset.py` 生成，可作为建库参考。

## 5.3 改脚本指向新库

脚本顶部都有同一行常量：

```python
DB_PATH = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'ecommerce', 'ecommerce.db'))
```

把它改成新库的相对路径，例如：

```python
DB_PATH = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'mydata', 'orders.db'))
```

接着按新库的字段调整 SQL（每个脚本里都集中写在文件前半段），再重跑一次确认图表与结论正常。

## 5.4 新增一个自己的分析脚本

1. 在 `src/data/<层>/` 下新建脚本，读取 `DB_PATH`、产出 Markdown 报告与 `images_xxx/` 图表
2. 在 `src/tools.ts` 的 `ANALYSIS_SCRIPTS` 里登记键、名称、脚本路径、报告路径
3. `npm run build`，完全退出并重启 DSH Desktop
4. 调用 `ds_run_analysis` 验证，`ds_list_analyses` 里应能看到新键

绘图脚本在 `sns.set_style` 之后要重新设置中文字体，否则中文会显示为方框。

# 6 组装一次完整分析

以「给一份新数据做一轮完整分析」为例，工具之间的衔接如下。

| 步骤 | 指令 | 工具 |
|:--|:--|:--|
| 1 | 看看这份数据长什么样，有哪些表 | ds_profiling |
| 2 | 把探查发现的缺失与异常结论摘出来 | ds_read_report |
| 3 | 先用 SQL 核对几个关键口径 | ds_query |
| 4 | 生成描述性报告 | ds_run_analysis（L1-eda） |
| 5 | 找出原因：相关、因果、异常、聚类 | ds_run_analysis（L2-*） |
| 6 | 做预测并解释模型 | ds_run_analysis（L3-predictive、L3-shap） |
| 7 | 给出决策建议 | ds_run_analysis（L4-bandit、L4-multiobjective） |
| 8 | 上生产前的质量与实验框架 | ds_run_analysis（ENG-quality、ENG-ab） |

每一步的产物都是 `src/data` 下的 Markdown 与图表，面板「数据科学」菜单能直接打开对应报告，对话里也可以用 `ds_read_report` 追问细节。

一段可复制的完整指令：

> 对 `src/data/mydata/orders.db` 做数据探查，重点看订单表与明细表的缺失和重复；体检结论摘给我；再用 SQL 核对 2025 年各月 GMV 与订单量；然后按描述性、诊断性、预测性的顺序生成报告，最后告诉我这组数据适合做哪类分析、还缺哪些字段。

# 7 常见问题

**工具报「未知的分析脚本」**：键名不在清单里，先调 `ds_list_analyses` 确认。

**工具报「只支持 select / with」**：查询工具不接受写操作，需要改数据时用 Python 脚本处理。

**脚本执行失败但面板里还有旧报告**：说明脚本中途退出，报告沿用上一次生成的版本，往上翻执行输出看报错。

**图表显示为裂图**：报告里的图片路径必须是相对路径（`images_xxx/文件名.png`），写成绝对路径后面板无法解析。

**依赖缺失**：`eng_data_quality.py` 需要 `pandera`，`eng_distributed.py` 需要 `dask`，`l2_sequence.py` 需要 `prefixspan`，这些不在固定依赖清单里，按需安装即可：

```powershell
.\.venv\Scripts\python.exe -m pip install prefixspan pandera dask `
  --no-cache-dir --no-build-isolation `
  --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

**改了代码没有生效**：宿主端与浏览器端代码都在启动时加载，必须完全退出 DSH Desktop（含托盘进程）再重启。
