---
name: data-engineering
description: 运行数据工程化专题（分布式计算、A/B 测试、数据质量监控）并解读报告。当用户说「做工程化报告」「对比 pandas 和 Dask」「做一次 A/B 检验」「数据质量规则校验」时使用。
whenToUse: 用户需要工程化层面的验证：计算性能、实验显著性、质量规则命中情况，或要生成工程化报告时。
---

# 数据工程化

专题入口：`src/data/engineering/README.md`。三个脚本共用电商数据 `src/data/ecommerce/ecommerce.db`。

## 什么时候用

- 「跑一下工程化」「做个 A/B 测试」「数据质量规则检查」
- 需要判断一条 SQL / 一个口径能否在规模化数据上稳定运行
- 需要给出实验结论（显著性、置信区间）或质量打分

## 调用方式

1. 分布式计算对比（pandas vs Dask 的耗时与内存）：
   ```
   ds_run_analysis({ analysis: "ENG-distributed" })
   ```
2. A/B 测试框架（分组、检验、结论）：
   ```
   ds_run_analysis({ analysis: "ENG-ab" })
   ```
3. 数据质量监控（规则集、命中率、阻断项）：
   ```
   ds_run_analysis({ analysis: "ENG-quality" })
   ```
4. 读已有报告：
   ```
   ds_read_report({ path: "engineering/data_quality_report.md" })
   ```

## 结果怎么读

- 分布式：看耗时、峰值内存、加速比，并说明数据量级与是否值得上分布式。
- A/B：先看样本量与分组均衡，再看 p 值、效应量；结论必须带「显著 / 不显著」与业务解读。
- 质量：看规则总数、通过数、命中明细；失败规则要给出可执行的修复建议。

## 命令行等价写法

在项目根目录、激活 `.venv` 后：

```
python src/data/engineering/eng_distributed.py
python src/data/engineering/eng_ab_test.py
python src/data/engineering/eng_data_quality.py
```

## 边界

- 工程化脚本只读样例数据，不写生产库。
- 分布式对比在单机上跑多分区，结论用于方法演示，不作为容量规划依据。
- 面板入口：示例数据 → 数据科学 → 工程化。
