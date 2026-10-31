---
name: data-analysis-l1-l5
description: 按数据科学五层框架（L1 描述性 / L2 诊断性 / L3 预测性 / L4 规范性 / L5 认知性）运行具体分析脚本并解读报告。当用户说「做 Lx 分析」「跑一下某个分析」「看看某份分析报告」时使用。
whenToUse: 用户要做分层分析、运行某一具体分析脚本、或需要引用某个分析的结论与数字时。
---

# 数据科学分层分析

框架入口：`src/data/README.md`（理论），各层详情在 `src/data/L1` ~ `src/data/L5` 的 `README.md`。全部基于同一份电商数据 `src/data/ecommerce/ecommerce.db`。

## 什么时候用

- 「帮我做 L2 诊断分析」「跑一下客户聚类」「生成 SHAP 报告」
- 「L4 有哪些分析」「这层用的是什么方法」
- 需要把某份报告的结论、指标、结论口径复述给用户

## 调用顺序

1. 不确定脚本键时先列清单：
   ```
   ds_list_analyses()
   ```
2. 运行具体分析：
   ```
   ds_run_analysis({ analysis: "L2-causal" })
   ds_run_analysis({ analysis: "L3-shap" })
   ds_run_analysis({ analysis: "L4-dqn" })
   ```
3. 读报告正文（可复用已有报告，不必重跑）：
   ```
   ds_read_report({ path: "L2/causal_report.md" })
   ```
4. 需要核对口径或取样本时查库：
   ```
   ds_query({ sql: "select order_status, count(*) from orders group by 1" })
   ```

## 常用脚本键

| 层 | 键 | 内容 |
|---|---|---|
| L1 | `L1-eda` / `L1-cross` / `L1-geo` / `L1-text` | 描述性主报告、多维交叉、地理、文本 |
| L2 | `L2-diagnostic` / `L2-causal` / `L2-granger` / `L2-anomaly` / `L2-clustering` / `L2-sequence` | 诊断主报告、因果、时序因果、异常、聚类、序列模式 |
| L3 | `L3-predictive` / `L3-ensemble` / `L3-multistep` / `L3-quantile` / `L3-transfer` / `L3-shap` | 预测主报告、集成、多步、区间、迁移、可解释 |
| L4 | `L4-prescriptive` / `L4-dqn` / `L4-bandit` / `L4-multiobjective` / `L4-causal-rec` | 规范性主报告、补货决策、推荐、多目标、因果推荐 |
| L5 | `L5-continual` / `L5-meta` / `L5-multimodal` | 持续学习、元学习、多模态 |

## 结果怎么读

- 每层先用一句话说清「这层回答什么问题」，再给结论和关键数字。
- 引用数字时必须来自报告或 `ds_query` 返回，不要凭记忆。
- 面向非数据同学讲：先说业务结论，再说方法与指标；面向分析师讲：补充假设、口径和局限。

## 边界

- 只运行白名单脚本，不接受自定义脚本路径。
- 训练类分析耗时较长，工具带超时；超时返回会明确标记 `timeout`，可改用已有报告 (`ds_read_report`)。
- 面板入口：示例数据 → 数据科学 → 分析框架 / L1 ~ L5 详情。
