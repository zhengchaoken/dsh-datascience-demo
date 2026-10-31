---
name: data-profiling
description: 对 SQLite 数据源做数据探查（数据体检 / 质量初筛），产出 Markdown 报告与图表并解读结论。当用户说「对某某数据做探查」「这个库能不能用来建模」「检查一下数据质量」时使用。
whenToUse: 用户需要对一个数据库做整体体检、字段质量核查、跨表一致性校验，或要重新生成探查报告时。
---

# 数据探查

本项目的探查脚本是 `src/data/profiling/data_profiling_report.py`，默认探查电商示例库 `src/data/ecommerce/ecommerce.db`。

## 什么时候用

- 用户说「对 X 数据做探查 / 数据体检 / 质量检查 / 能不能建模」
- 需要给出缺失率、重复、异常值、跨表一致性等客观结论
- 需要把探查结论落到报告里，供后续 L1~L5 分析引用

## 调用方式

优先调用工具，不要手写脚本路径。

1. 默认库（电商示例数据）：

   ```
   ds_profiling()
   ```

2. 指定库或指定表：

   ```
   ds_profiling({ database: "src/data/other/xxx.db" })
   ds_profiling({ database: "src/data/ecommerce/ecommerce.db", tables: "orders,payments" })
   ```

工具会执行脚本并返回：状态、数据库路径、报告路径、报告摘要、执行输出尾部。

## 结果怎么读

- 报告落在 `src/data/profiling/`：`data_profiling_report.md`（主报告）、`report_manager.html`（管理者视角）、`report_analyst.html`（分析师视角）、`images/`（图表）。
- 面板入口：示例数据 → 数据科学 → 探查报告，重新生成后刷新即可看到新内容。
- 解读顺序：数据规模与时间跨度 → 缺失字段的业务含义 → 跨表一致性 → 分布与异常 → 建模就绪度。
- 缺失值先看语义（例如 `paid_at` 为空代表未支付，不是脏数据），再判断是否需要处理。

## 命令行等价写法

在项目根目录、激活 `.venv` 后：

```
python src/data/profiling/data_profiling_report.py --db src/data/ecommerce/ecommerce.db
```

自定义报告目录用 `--out-dir`，只探查部分表用 `--tables orders,payments`。

## 边界

- 只接受只读连接（`mode=ro`），不会改动源库。
- 探查脚本面向 SQLite；其它类型数据库先导出为 SQLite 再探查。
