# 电商数据库 L1 描述性分析报告

- **数据来源**：`data/ecommerce/ecommerce.db`（SQLite，只读连接）
- **订单量**：19669 单 / 明细 36907 行 / 客户 3000 人 / 商品 600 个
- **主力数值列**：`orders.total_amount`（订单实付金额）
- **主力分类列**：`orders.channel`（下单渠道）
- **时序轴**：`orders.created_at` 聚合为日 GMV（532 天）
- **GMV 口径**：`order_status IN ('已完成','已发货')`

## 目录

- 1 数据概览
  - 1.1 orders 表预览
  - 1.2 customers 表预览
- 2 数据探查
  - 2.1 行数与规模
    - 2.1.1 各表行数
    - 2.1.2 唯一值数
  - 2.2 空值统计
    - 2.2.1 各列空值数
    - 2.2.2 空值率
- 3 集中趋势
    - 3.1 算术均值
    - 3.2 中位数
    - 3.3 众数
    - 3.4 加权均值
    - 3.5 几何均值
    - 3.6 调和均值
    - 3.7 截尾均值（5% 截尾）
    - 3.8 中列数
- 4 离散程度
    - 4.1 极差
    - 4.2 方差
    - 4.3 标准差
    - 4.4 平均绝对偏差（MAD Mean）
    - 4.5 中位数绝对偏差（MAD Median）
    - 4.6 四分位距（IQR）
    - 4.7 变异系数（CV）
    - 4.8 相对平均偏差
    - 4.9 极差比
- 5 分布形态
    - 5.1 偏度
    - 5.2 峰度（超额）
    - 5.3 百分位数
  - 5.1 五分位与十分位
    - 5.1.1 五分位汇总
    - 5.1.2 十分位汇总
  - 5.2 多数值列分布对比与正态性检验
- 6 频率与交叉表
  - 6.1 频率分布
    - 6.1.1 一维频率分布
    - 6.1.2 频率占比
    - 6.1.3 累积频率
  - 6.2 交叉表
    - 6.2.1 二维交叉表
    - 6.2.2 透视表
    - 6.2.3 双变量均值交叉
- 7 排名与分位
  - 7.1 排名函数
    - 7.1.1 行号与排名
    - 7.1.2 百分位排名与累积分布
    - 7.1.3 分桶
- 8 分组对比
    - 8.1 分组均值与方差
    - 8.2 组内占比
    - 8.3 组内排名
    - 8.4 组内累计
- 9 时序描述
  - 9.1 日 GMV 走势
  - 9.2 时间聚合
  - 9.3 滚动统计
  - 9.4 环比
  - 9.5 累计和
- 10 可视化
  - 10.1 直方图与 KDE
  - 10.2 经验累积分布（ECDF）
  - 10.3 箱线图
  - 10.4 小提琴图
  - 10.5 QQ 图
  - 10.6 散点图
  - 10.7 配对图
  - 10.8 相关热力图
- 11 变量关系
    - 11.1 协方差（活跃度 × 消费额）
    - 11.2 Pearson 相关系数（活跃度 × 消费额）
    - 11.3 Spearman 秩相关（活跃度 × 消费额）
    - 11.4 简单线性回归（活跃度 → 消费额）
  - 11.1 价格与销量的关系
- 12 缺失值分析
    - 12.1 单变量空值率
    - 12.2 按组空值分布
- 13 异常值检测
    - 13.1 1.5×IQR 异常值边界
    - 13.2 Z-score 异常值边界
- 14 数据质量检查
    - 14.1 主键唯一性
    - 14.2 完全重复行
    - 14.3 金额链路一致性
- 15 时序深度分析
  - 15.1 STL 分解
  - 15.2 ACF / PACF
  - 15.3 结构断点检测
- 16 SQL 描述性分析能力总结

---
# 1. 数据概览

本报告基于统一电商数据库（customers / products / orders / order_items / reviews 等 9 张表）系统展示描述性分析的完整流程：数据探查、集中趋势、离散程度、分布形态、频率与交叉表、排名与分位、分组对比、时序描述、可视化、变量关系、缺失值、异常值、数据质量、时序深度分析。每节同时给出 SQL 实现与 Python 实现，便于对照。数据中刻意埋入了双 11 / 618 大促峰值、春节低谷、周末效应、缓慢增长趋势，以及约 1.2% 批发型异常订单与 0.5% 价格异常订单，是异常值检测的天然靶子。

## 1.1 orders 表预览

订单表是本报告的主分析表，`total_amount` 为主力数值列（对应原示例中的年薪列）。

|   order_id |   customer_id |   coupon_id | order_status   | channel   | created_at          | paid_at             | shipped_at          | delivered_at        |   freight_amount |   discount_amount |   total_amount |
|-----------:|--------------:|------------:|:---------------|:----------|:--------------------|:--------------------|:--------------------|:--------------------|-----------------:|------------------:|---------------:|
|          3 |           471 |      3.0000 | 已完成            | APP       | 2024-01-01 01:15:15 | 2024-01-01 01:40:15 | 2024-01-02 03:34:52 | 2024-01-06 20:05:13 |           0.0000 |           50.0000 |      5091.4400 |
|         20 |          2465 |    nan      | 已完成            | APP       | 2024-01-01 03:20:17 | 2024-01-01 03:38:17 | 2024-01-02 01:30:29 | 2024-01-07 22:45:51 |           0.0000 |            0.0000 |       885.6600 |
|         23 |          2367 |      5.0000 | 已完成            | 网页        | 2024-01-01 03:27:11 | 2024-01-01 03:31:11 | 2024-01-02 11:10:35 | 2024-01-07 08:13:45 |           0.0000 |           76.6300 |       689.6700 |
|          7 |          1882 |    nan      | 已完成            | APP       | 2024-01-01 05:27:19 | 2024-01-01 05:43:19 | 2024-01-02 20:39:30 | 2024-01-06 18:15:54 |           0.0000 |            0.0000 |      2637.3800 |
|         12 |          2890 |    nan      | 已完成            | 小程序       | 2024-01-01 06:18:03 | 2024-01-01 06:25:03 | 2024-01-01 14:09:41 | 2024-01-05 01:44:46 |           0.0000 |            0.0000 |      1298.1600 |

## 1.2 customers 表预览

|   customer_id | customer_name   | gender   |   age | province   | city   | register_date   | member_level   |   activity_score |
|--------------:|:----------------|:---------|------:|:-----------|:-------|:----------------|:---------------|-----------------:|
|             1 | 郑芳              | 女        |    30 | 广东省        | 广州市    | 2024-11-23      | 白银             |           0.0073 |
|             2 | 罗桐              | 男        |    35 | 浙江省        | 杭州市    | 2025-02-16      | 白银             |           0.4363 |
|             3 | 徐丽              | 男        |    33 | 江苏省        | 苏州市    | 2023-02-14      | 白银             |           0.0591 |
|             4 | 冯涵杰             | 女        |    23 | 浙江省        | 宁波市    | 2023-03-23      | 黄金             |           0.3854 |
|             5 | 杨桂娟             | 女        |    43 | 湖北省        | 武汉市    | 2024-09-15      | 白银             |           0.1964 |

# 2. 数据探查

数据探查回答「数据长什么样、有没有脏、有多少缺失」这些基础问题。多表数据库中首先要摸清各表规模与关键列基数。SQL 的 COUNT / SUM / CASE WHEN 等聚合函数足以覆盖全部探查需求。

## 2.1 行数与规模

### 2.1.1 各表行数

多表数据库的规模度量要逐表统计，子查询是最直接的写法。

**SQL 代码：**

```sql
SELECT
  (SELECT COUNT(*) FROM orders)      AS n_orders,
  (SELECT COUNT(*) FROM order_items) AS n_items,
  (SELECT COUNT(*) FROM customers)   AS n_customers,
  (SELECT COUNT(*) FROM products)    AS n_products,
  (SELECT COUNT(*) FROM reviews)     AS n_reviews;
```

**SQL 结果：**

|   n_orders |   n_items |   n_customers |   n_products |   n_reviews |
|-----------:|----------:|--------------:|-------------:|------------:|
|      19669 |     36907 |          3000 |          600 |        5976 |

**Python 代码：**

```python
len(orders), len(order_items), len(customers), len(products)
```

**Python 结果：**

**输出：**
```
orders=19669, order_items=36907, customers=3000, products=600
```

**解释：**

- **用途**：判断数据集大小，评估后续计算量。
- **关系**：明细行数 > 订单数，说明一单多品（连带率 > 1），符合电商常识。

### 2.1.2 唯一值数

统计去重后的值个数，用于评估列的基数（Cardinality）。

**SQL 代码：**

```sql
SELECT
  COUNT(DISTINCT order_id)    AS n_order,
  COUNT(DISTINCT customer_id) AS n_customer,
  COUNT(DISTINCT channel)     AS n_channel,
  COUNT(DISTINCT order_status) AS n_status
FROM orders;
```

**SQL 结果：**

|   n_order |   n_customer |   n_channel |   n_status |
|----------:|-------------:|------------:|-----------:|
|     19669 |         2513 |           4 |          4 |

**Python 代码：**

```python
orders[['order_id','customer_id','channel','order_status']].nunique().to_dict()
```

**Python 结果：**

**输出：**
```
{'order_id': 19669, 'customer_id': 2513, 'channel': 4, 'order_status': 4}
```

**解释：**

- **判读**：order_id 基数 = 行数，是唯一键；channel / order_status 基数低，是分类列。
- **用途**：分类列适合做 GROUP BY；唯一键适合做主键和 JOIN。

## 2.2 空值统计

空值（NULL）在 SQL 中不等于任何值，必须用 `IS NULL` 判断。订单表的时间链字段（paid_at / shipped_at / delivered_at）按状态机设计天然含 NULL：未支付的订单没有支付时间，未签收的订单没有签收时间。这类 NULL 是业务语义而非数据错误。

### 2.2.1 各列空值数

统计时间链与优惠券字段的 NULL 数量。

**SQL 代码：**

```sql
SELECT
  SUM(CASE WHEN coupon_id     IS NULL THEN 1 ELSE 0 END) AS coupon_id_空值数,
  SUM(CASE WHEN paid_at       IS NULL THEN 1 ELSE 0 END) AS paid_at_空值数,
  SUM(CASE WHEN shipped_at    IS NULL THEN 1 ELSE 0 END) AS shipped_at_空值数,
  SUM(CASE WHEN delivered_at  IS NULL THEN 1 ELSE 0 END) AS delivered_at_空值数
FROM orders;
```

**SQL 结果：**

|   coupon_id_空值数 |   paid_at_空值数 |   shipped_at_空值数 |   delivered_at_空值数 |
|----------------:|--------------:|-----------------:|-------------------:|
|           15480 |           488 |             1536 |               2377 |

**Python 代码：**

```python
orders[['coupon_id','paid_at','shipped_at','delivered_at']].isnull().sum().to_dict()
```

**Python 结果：**

**输出：**
```
{'coupon_id': 15480, 'paid_at': 488, 'shipped_at': 1536, 'delivered_at': 2377}
```

**解释：**

- **判读**：paid_at 空值 ≈ 待付款 + 已取消订单数，delivered_at 空值 ≈ 未签收订单数，与状态机完全一致。
- **注意**：NULL 参与聚合时 `AVG` 忽略 NULL，`COUNT(col)` 忽略 NULL，但 `COUNT(*)` 不忽略。

### 2.2.2 空值率

空值数除以总行数，用百分比表示缺失严重程度。

**SQL 代码：**

```sql
SELECT
  ROUND(SUM(CASE WHEN paid_at      IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS paid_at_空值率,
  ROUND(SUM(CASE WHEN delivered_at IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS delivered_at_空值率
FROM orders;
```

**SQL 结果：**

|   paid_at_空值率 |   delivered_at_空值率 |
|--------------:|-------------------:|
|        2.4800 |            12.0900 |

**Python 代码：**

```python
(orders.isnull().sum() / len(orders) * 100).round(2).to_dict()
```

**Python 结果：**

**输出：**
```
{'paid_at': 2.48, 'shipped_at': 7.81, 'delivered_at': 12.09}
```

**解释：**

- **标准**：0 完美；< 5% 轻微；5%-30% 中等；> 30% 严重。
- **本例**：缺失由业务流程决定（MNAR 的极端形式——缺失完全由状态决定），分析时不能直接填补，应按状态分层处理。

# 3. 集中趋势

集中趋势刻画数据分布的“中心”所在。本节以 `orders.total_amount`（订单实付金额）为分析对象。SQL 提供 AVG、MIN、MAX 等基础聚合，几何均值、调和均值、截尾均值等需公式化计算。

### 3.1 算术均值

全部观测之和除以观测数，是最常用的集中趋势度量。

**SQL 代码：**

```sql
SELECT ROUND(AVG(total_amount), 2) AS mean_amount FROM orders;
```

**SQL 结果：**

|   mean_amount |
|--------------:|
|     6962.0400 |

**Python 代码：**

```python
orders['total_amount'].mean()
```

**Python 结果：**

**输出：**
```
6962.0412
```

**解释：**

- **公式**：x̄ = (1/n)·Σxᵢ。
- **性质**：使残差和 Σ(xᵢ - x̄) = 0；对极端值敏感。
- **业务含义**：全部订单（含取消）的平均金额，混入了少量批发型异常大单，会显著高于正常客单价，需与中位数对照判读。

### 3.2 中位数

将数据升序排列后位于中间的值，是分布的 50% 分位。

**SQL 代码：**

```sql
WITH ranked AS (
  SELECT total_amount,
         ROW_NUMBER() OVER (ORDER BY total_amount) AS rn,
         COUNT(*) OVER () AS n
  FROM orders
)
SELECT ROUND(AVG(total_amount), 2) AS median_amount
FROM ranked
WHERE rn IN (CAST((n+1)/2 AS INT), CAST((n+2)/2 AS INT));
```

**SQL 结果：**

|   median_amount |
|----------------:|
|       2894.2500 |

**Python 代码：**

```python
orders['total_amount'].median()
```

**Python 结果：**

**输出：**
```
2894.2500
```

**解释：**

- **公式**：n 为偶数时取中间两值均值；奇数时取中间值。
- **稳健性**：breakdown point ≈ 50%，即一半数据被污染仍有效。
- **判读**：本例中位数远小于均值 → 明显右偏，少数大额订单拉高了均值。

### 3.3 众数

出现频次最高的取值，适合类别型或离散型数据。

**SQL 代码：**

```sql
SELECT channel AS mode_value, COUNT(*) AS freq
FROM orders
GROUP BY channel
ORDER BY freq DESC, channel
LIMIT 1;
```

**SQL 结果：**

| mode_value   |   freq |
|:-------------|-------:|
| APP          |  11107 |

**Python 代码：**

```python
orders['channel'].mode().iloc[0]
```

**Python 结果：**

**输出：**
```
APP
```

**解释：**

- **适用**：分类变量（channel、order_status、member_level）。
- **连续数据注意**：total_amount 是连续金额，众数常因小数精度而失去实际意义，故本例改用渠道列演示。
- **业务含义**：订单量最大的渠道是运营主阵地。

### 3.4 加权均值

为每个观测赋予权重后求平均。以成交数量为权重对成交单价加权，得到的是金额口径的件单价。

**SQL 代码：**

```sql
SELECT ROUND(SUM(oi.unit_price * oi.quantity) * 1.0 / SUM(oi.quantity), 4) AS weighted_unit_price
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id
WHERE o.order_status IN ('已完成','已发货');
```

**SQL 结果：**

|   weighted_unit_price |
|----------------------:|
|             1625.7707 |

**Python 代码：**

```python
np.average(valid_items['unit_price'], weights=valid_items['quantity'])
```

**Python 结果：**

**输出：**
```
1625.7707
```

**解释：**

- **公式**：x̄w = Σ(wᵢxᵢ) / Σwᵢ。
- **对比**：权重全相等时退化为算术均值。
- **业务含义**：Σ(单价×数量)/Σ数量 = GMV/销售件数 = 件单价，比简单平均单价更能反映实际卖出的价格水平。

### 3.5 几何均值

n 个正数乘积的 n 次方根，适合比率、增长率类数据。

**SQL 代码：**

```sql
SELECT ROUND(EXP(SUM(LN(total_amount)) / COUNT(total_amount)), 2) AS geo_mean
FROM orders
WHERE total_amount > 0;
```

**SQL 结果：**

|   geo_mean |
|-----------:|
|  2371.0000 |

**Python 代码：**

```python
stats.gmean(orders['total_amount'])
```

**Python 结果：**

**输出：**
```
2370.9980
```

**解释：**

- **公式**：G = (Πxᵢ)^(1/n) = exp(Σln xᵢ / n)。
- **不等式**：G ≤ 算术均值，仅当所有值相等时取等号。
- **判读**：对右偏的金额数据，几何均值更接近“典型订单”的量级。

### 3.6 调和均值

观测值倒数的算术均值的倒数，适合速率、单位时间量数据。

**SQL 代码：**

```sql
SELECT ROUND(COUNT(total_amount) / SUM(1.0/total_amount), 2) AS harm_mean
FROM orders
WHERE total_amount > 0;
```

**SQL 结果：**

|   harm_mean |
|------------:|
|    786.1200 |

**Python 代码：**

```python
stats.hmean(orders['total_amount'])
```

**Python 结果：**

**输出：**
```
786.1163
```

**解释：**

- **公式**：H = n / Σ(1/xᵢ)。
- **不等式**：H ≤ G ≤ 算术均值。
- **适用**：平均速度、单位价格、P/E 比率。

### 3.7 截尾均值（5% 截尾）

去掉最大 5% 和最小 5% 后求均值，是稳健的中心度量。

**SQL 代码：**

```sql
WITH ranked AS (
  SELECT total_amount,
         ROW_NUMBER() OVER (ORDER BY total_amount) AS rn,
         COUNT(*) OVER () AS n
  FROM orders
)
SELECT ROUND(AVG(total_amount), 2) AS trimmed_mean
FROM ranked
WHERE rn > FLOOR(n*0.05) AND rn <= n - FLOOR(n*0.05);
```

**SQL 结果：**

|   trimmed_mean |
|---------------:|
|      4229.2300 |

**Python 代码：**

```python
stats.trim_mean(orders['total_amount'].dropna(), 0.05)
```

**Python 结果：**

**输出：**
```
4229.2309
```

**解释：**

- **用途**：抑制批发型异常大单对均值的影响。
- **对比**：0% 截尾 = 算术均值；50% 截尾 ≈ 中位数。
- **判读**：截尾均值明显低于算术均值，证实右尾存在极端大单。

### 3.8 中列数

最大值与最小值的平均，是最粗糙的中心度量。

**SQL 代码：**

```sql
SELECT ROUND((MAX(total_amount) + MIN(total_amount)) / 2.0, 2) AS midrange FROM orders;
```

**SQL 结果：**

|    midrange |
|------------:|
| 692542.6000 |

**Python 代码：**

```python
(orders['total_amount'].max() + orders['total_amount'].min()) / 2
```

**Python 结果：**

**输出：**
```
692542.5950
```

**解释：**

- **公式**：Midrange = (max + min) / 2。
- **特点**：仅使用两个极端值，极不稳健；本例最大值是百万级批发异常单，中列数完全失真，仅作教学演示。

# 4. 离散程度

离散程度刻画数据围绕中心的波动大小。SQLite 无内置方差/标准差函数，本节采用公式化计算，保证跨库可移植。分析对象仍为 `orders.total_amount`。

### 4.1 极差

最大值与最小值之差，反映数据跨度。

**SQL 代码：**

```sql
SELECT ROUND(MAX(total_amount) - MIN(total_amount), 2) AS range_val FROM orders;
```

**SQL 结果：**

|    range_val |
|-------------:|
| 1385013.0500 |

**Python 代码：**

```python
orders['total_amount'].max() - orders['total_amount'].min()
```

**Python 结果：**

**输出：**
```
1385013.0500
```

**解释：**

- **公式**：R = max - min。
- **缺点**：仅使用两端值，受极端值影响极大；本例极差被百万级异常单主导。

### 4.2 方差

各观测与均值差的平方的平均，是离散程度的核心度量。

**SQL 代码：**

```sql
SELECT
  ROUND(AVG(total_amount*total_amount) - AVG(total_amount)*AVG(total_amount), 2) AS var_pop,
  ROUND((SUM(total_amount*total_amount) - SUM(total_amount)*SUM(total_amount)*1.0/COUNT(total_amount))
    / (COUNT(total_amount)-1), 2) AS var_samp
FROM orders;
```

**SQL 结果：**

|         var_pop |        var_samp |
|----------------:|----------------:|
| 1021809821.7200 | 1021861774.6200 |

**Python 代码：**

```python
orders['total_amount'].var(ddof=0), orders['total_amount'].var(ddof=1)
```

**Python 结果：**

**输出：**
```
总体方差 = 1021809821.7153
样本方差 = 1021861774.6246
```

**解释：**

- **公式**：总体 σ² = Σ(xᵢ-μ)²/N；样本 s² = Σ(xᵢ-x̄)²/(n-1)。
- **Bessel 校正**：样本方差用 n-1 分母，使其无偏。
- **注意**：SQLite 无 VAR_POP/VAR_SAMP，需公式化。

### 4.3 标准差

方差的平方根，量纲与原数据一致。

**SQL 代码：**

```sql
SELECT
  ROUND(SQRT(AVG(total_amount*total_amount) - AVG(total_amount)*AVG(total_amount)), 2) AS std_pop,
  ROUND(SQRT((SUM(total_amount*total_amount) - SUM(total_amount)*SUM(total_amount)*1.0/COUNT(total_amount))
       / (COUNT(total_amount)-1)), 2) AS std_samp
FROM orders;
```

**SQL 结果：**

|    std_pop |   std_samp |
|-----------:|-----------:|
| 31965.7600 | 31966.5700 |

**Python 代码：**

```python
orders['total_amount'].std(ddof=0), orders['total_amount'].std(ddof=1)
```

**Python 结果：**

**输出：**
```
总体标准差 = 31965.7601
样本标准差 = 31966.5728
```

**解释：**

- **判读**：标准差已超过均值，说明分布离散度极高——正是异常大单所致。
- **性质**：与数据同量纲，可直接描述波动幅度。

### 4.4 平均绝对偏差（MAD Mean）

各观测与均值绝对差的平均，比方差更直观。

**SQL 代码：**

```sql
SELECT ROUND(AVG(ABS(total_amount - (SELECT AVG(total_amount) FROM orders))), 2) AS mad_mean
FROM orders;
```

**SQL 结果：**

|   mad_mean |
|-----------:|
|  7037.7500 |

**Python 代码：**

```python
(orders['total_amount'] - orders['total_amount'].mean()).abs().mean()
```

**Python 结果：**

**输出：**
```
7037.7510
```

**解释：**

- **公式**：MAD = Σ|xᵢ-x̄| / n。
- **优点**：对极端值不如方差敏感，单位与原数据相同。
- **缺点**：绝对值在数学上不可微。

### 4.5 中位数绝对偏差（MAD Median）

各观测与中位数绝对差的中位数，是高度稳健的离散度量。

**SQL 代码：**

```sql
WITH abs_dev AS (
  SELECT ABS(total_amount - (
    SELECT AVG(total_amount) FROM (
      SELECT total_amount, ROW_NUMBER() OVER (ORDER BY total_amount) AS rn,
             COUNT(*) OVER () AS n FROM orders
    ) WHERE rn IN (CAST((n+1)/2 AS INT), CAST((n+2)/2 AS INT))
  )) AS d
  FROM orders
),
ranked AS (
  SELECT d, ROW_NUMBER() OVER (ORDER BY d) AS rn, COUNT(*) OVER () AS n
  FROM abs_dev
)
SELECT ROUND(AVG(d), 2) AS mad_median
FROM ranked
WHERE rn IN (CAST((n+1)/2 AS INT), CAST((n+2)/2 AS INT));
```

**SQL 结果：**

|   mad_median |
|-------------:|
|    2359.9500 |

**Python 代码：**

```python
np.median(np.abs(orders['total_amount'] - orders['total_amount'].median()))
```

**Python 结果：**

**输出：**
```
2359.9500
```

**解释：**

- **公式**：MAD = median(|xᵢ - median(x)|)。
- **稳健性**：breakdown point ≈ 50%，远高于标准差。
- **用途**：稳健 Z-score 计算、离群值检测；对本例强右偏金额数据尤其合适。

### 4.6 四分位距（IQR）

Q3 与 Q1 之差，是中间 50% 数据的跨度。

**SQL 代码：**

```sql
WITH q AS (
  SELECT total_amount, PERCENT_RANK() OVER (ORDER BY total_amount) AS pr
  FROM orders
)
SELECT
  ROUND(MAX(CASE WHEN pr <= 0.25 THEN total_amount END), 2) AS q1,
  ROUND(MAX(CASE WHEN pr <= 0.75 THEN total_amount END), 2) AS q3,
  ROUND(MAX(CASE WHEN pr <= 0.75 THEN total_amount END) -
        MAX(CASE WHEN pr <= 0.25 THEN total_amount END), 2) AS iqr
FROM q;
```

**SQL 结果：**

|       q1 |        q3 |       iqr |
|---------:|----------:|----------:|
| 900.7200 | 6804.6700 | 5903.9500 |

**Python 代码：**

```python
q1,q3 = orders['total_amount'].quantile([0.25,0.75]); q3-q1
```

**Python 结果：**

**输出：**
```
Q1 = 900.7200
Q3 = 6804.6700
IQR = 5903.9500
```

**解释：**

- **性质**：对极端值高度稳健。
- **应用**：1.5×IQR 法则检测异常值（见第 13 节）；箱线图的箱体高度。

### 4.7 变异系数（CV）

标准差除以均值，是无量纲的相对离散程度。

**SQL 代码：**

```sql
SELECT ROUND(SQRT(AVG(total_amount*total_amount) - AVG(total_amount)*AVG(total_amount))
       / AVG(total_amount), 4) AS cv
FROM orders;
```

**SQL 结果：**

|     cv |
|-------:|
| 4.5914 |

**Python 代码：**

```python
orders['total_amount'].std(ddof=0) / orders['total_amount'].mean()
```

**Python 结果：**

**输出：**
```
4.5914
```

**解释：**

- **公式**：CV = σ/μ，要求 μ > 0。
- **判读**：< 0.15 弱变异；0.15-0.35 中等；> 0.35 强变异。本例 CV ≫ 1，属极强变异。
- **优势**：可跨量纲比较（订单金额 vs 年龄的波动性）。

### 4.8 相对平均偏差

平均绝对偏差除以均值，是无量纲的稳健离散度量。

**SQL 代码：**

```sql
SELECT ROUND(AVG(ABS(total_amount - (SELECT AVG(total_amount) FROM orders))) /
       (SELECT AVG(total_amount) FROM orders), 4) AS rel_mad
FROM orders;
```

**SQL 结果：**

|   rel_mad |
|----------:|
|    1.0109 |

**Python 代码：**

```python
(orders['total_amount'] - orders['total_amount'].mean()).abs().mean() / orders['total_amount'].mean()
```

**Python 结果：**

**输出：**
```
1.0109
```

**解释：**

- **公式**：RMD = MAD_mean / mean。
- **用途**：比较不同量纲数据的离散程度。

### 4.9 极差比

最大值与最小值之比，是相对跨度的简单度量。

**SQL 代码：**

```sql
SELECT ROUND(MAX(total_amount) * 1.0 / MIN(total_amount), 2) AS range_ratio FROM orders;
```

**SQL 结果：**

|   range_ratio |
|--------------:|
|    38398.9200 |

**Python 代码：**

```python
orders['total_amount'].max() / orders['total_amount'].min()
```

**Python 结果：**

**输出：**
```
38398.9221
```

**解释：**

- **公式**：RR = max / min（要求 min > 0）。
- **业务含义**：最大单是最小单的数万倍，直观反映订单金额的两极分化。

# 5. 分布形态

分布形态刻画数据分布的对称性与尾部特征，是选择统计模型与检验方法的前提。

### 5.1 偏度

衡量分布的不对称程度：>0 右偏、<0 左偏、≈0 对称。

**SQL 代码：**

```sql
SELECT
  ROUND(AVG(POW(total_amount - (SELECT AVG(total_amount) FROM orders), 3)) /
  POW(SQRT(AVG(total_amount*total_amount) - AVG(total_amount)*AVG(total_amount)), 3), 4) AS skewness
FROM orders;
```

**SQL 结果：**

|   skewness |
|-----------:|
|    20.3148 |

**Python 代码：**

```python
orders['total_amount'].skew()
```

**Python 结果：**

**输出：**
```
20.3163
```

**解释：**

- **公式**：g₁ = (1/n)·Σ((xᵢ-x̄)/s)³。
- **判读**：|g₁| < 0.5 近似对称；0.5-1 中等偏斜；≥1 强偏斜。
- **业务含义**：订单金额极度右偏（大量小额正常单 + 少数批发大单），建模前可做对数变换。

### 5.2 峰度（超额）

衡量分布尾部的厚重程度，正态分布的超额峰度为 0。

**SQL 代码：**

```sql
SELECT
  ROUND(AVG(POW(total_amount - (SELECT AVG(total_amount) FROM orders), 4)) /
  POW(SQRT(AVG(total_amount*total_amount) - AVG(total_amount)*AVG(total_amount)), 4) - 3, 4) AS kurtosis
FROM orders;
```

**SQL 结果：**

|   kurtosis |
|-----------:|
|   531.6585 |

**Python 代码：**

```python
orders['total_amount'].kurtosis()
```

**Python 结果：**

**输出：**
```
531.7940
```

**解释：**

- **公式**：g₂ = (1/n)·Σ((xᵢ-x̄)/s)⁴ - 3。
- **判读**：>0 尖峰厚尾（极端值更多）；<0 平峰薄尾。
- **业务含义**：极高的正峰度说明厚尾严重，异常大单出现的概率远高于正态假设下的预期。

### 5.3 百分位数

第 p 百分位数使至少 p% 观测不超过它。

**SQL 代码：**

```sql
WITH r AS (
  SELECT total_amount, PERCENT_RANK() OVER (ORDER BY total_amount) AS pr FROM orders
)
SELECT
  ROUND(MAX(CASE WHEN pr <= 0.10 THEN total_amount END), 2) AS p10,
  ROUND(MAX(CASE WHEN pr <= 0.25 THEN total_amount END), 2) AS p25,
  ROUND(MAX(CASE WHEN pr <= 0.50 THEN total_amount END), 2) AS p50,
  ROUND(MAX(CASE WHEN pr <= 0.75 THEN total_amount END), 2) AS p75,
  ROUND(MAX(CASE WHEN pr <= 0.90 THEN total_amount END), 2) AS p90
FROM r;
```

**SQL 结果：**

|      p10 |      p25 |       p50 |       p75 |        p90 |
|---------:|---------:|----------:|----------:|-----------:|
| 316.9200 | 900.7200 | 2894.2500 | 6804.6700 | 12642.3300 |

**Python 代码：**

```python
orders['total_amount'].quantile([0.10,0.25,0.50,0.75,0.90]).to_dict()
```

**Python 结果：**

**输出：**
```
{0.1: 317.04, 0.25: 900.72, 0.5: 2894.25, 0.75: 6804.67, 0.9: 12642.35}
```

**解释：**

- **关系**：P25 = Q1，P50 = 中位数，P75 = Q3。
- **业务含义**：P90 与 P50 的差距反映大额订单与典型订单的距离。

## 5.1 五分位与十分位

### 5.1.1 五分位汇总

把订单按金额平均分成 5 组，观察每组的取值区间。

**SQL 代码：**

```sql
WITH quintiles AS (
  SELECT total_amount, NTILE(5) OVER (ORDER BY total_amount) AS q
  FROM orders
)
SELECT q, COUNT(*) AS n, ROUND(AVG(total_amount), 2) AS avg_v,
       ROUND(MIN(total_amount), 2) AS min_v, ROUND(MAX(total_amount), 2) AS max_v
FROM quintiles GROUP BY q ORDER BY q;
```

**SQL 结果：**

|      q |         n |      avg_v |     min_v |        max_v |
|-------:|----------:|-----------:|----------:|-------------:|
| 1.0000 | 3934.0000 |   322.9500 |   36.0700 |     641.6100 |
| 2.0000 | 3934.0000 |  1196.2700 |  641.8000 |    1908.1900 |
| 3.0000 | 3934.0000 |  2950.5700 | 1908.2900 |    4227.4300 |
| 4.0000 | 3934.0000 |  5913.6500 | 4228.4400 |    8148.9300 |
| 5.0000 | 3933.0000 | 24431.2100 | 8149.0300 | 1385049.1200 |

**Python 代码：**

```python
pd.qcut + groupby
```

**Python 结果：**

**输出：**
```
     count       mean       min          max
五分位                                         
Q1    3934   322.9541   36.0700     641.6100
Q2    3934  1196.2715  641.8000    1908.1900
Q3    3933  2950.2442 1908.2900    4227.2700
Q4    3934  5912.6499 4227.4300    8147.9600
Q5    3934 24427.0667 8148.9300 1385049.1200
```

**解释：**

- **用途**：订单分层、客户分层、风险分层。
- **判读**：Q5 组均值远高于 Q1-Q4，再次印证右尾极端值。

### 5.1.2 十分位汇总

把订单按金额平均分成 10 组，更细粒度观察分布。

**SQL 代码：**

```sql
WITH deciles AS (
  SELECT total_amount, NTILE(10) OVER (ORDER BY total_amount) AS d
  FROM orders
)
SELECT d, COUNT(*) AS n, ROUND(MIN(total_amount), 2) AS min_v, ROUND(MAX(total_amount), 2) AS max_v
FROM deciles GROUP BY d ORDER BY d;
```

**SQL 结果：**

|       d |         n |      min_v |        max_v |
|--------:|----------:|-----------:|-------------:|
|  1.0000 | 1967.0000 |    36.0700 |     316.9200 |
|  2.0000 | 1967.0000 |   317.0700 |     641.6100 |
|  3.0000 | 1967.0000 |   641.8000 |    1138.9900 |
|  4.0000 | 1967.0000 |  1139.4100 |    1908.1900 |
|  5.0000 | 1967.0000 |  1908.2900 |    2894.2500 |
|  6.0000 | 1967.0000 |  2894.2500 |    4227.4300 |
|  7.0000 | 1967.0000 |  4228.4400 |    5769.3100 |
|  8.0000 | 1967.0000 |  5769.6600 |    8148.9300 |
|  9.0000 | 1967.0000 |  8149.0300 |   12642.4500 |
| 10.0000 | 1966.0000 | 12643.3400 | 1385049.1200 |

**Python 代码：**

```python
pd.qcut(orders['total_amount'], 10) + groupby
```

**Python 结果：**

**输出：**
```
已执行
```

**解释：**

- **应用**：SLA 分位延迟（P90/P99）、客单价分层运营。

## 5.2 多数值列分布对比与正态性检验

单变量统计不能只盯一列。下面对库中四个核心数值列做横向对比：`orders.total_amount`（订单金额）、`order_items.quantity`（购买件数）、`customers.age`（客户年龄）、`products.list_price`（商品标价）。正态性采用 D'Agostino-Pearson K² 检验（scipy `normaltest`），原假设为“样本来自正态分布”，p < 0.05 拒绝正态性。SQL 无正态性检验函数，这类基于矩的迭代检验只能交给 Python。

**Python 代码：**

```python
for name, s in cols.items():
    stat, p = stats.normaltest(s.dropna())
    # 汇总 均值/中位数/标准差/偏度/峰度/p 值
```

**Python 结果：**

| 列                    |     n |        均值 |       中位数 |        标准差 |      偏度 |       峰度 |   normaltest_p | 正态(α=0.05)   |
|:---------------------|------:|----------:|----------:|-----------:|--------:|---------:|---------------:|:-------------|
| orders.total_amount  | 19669 | 6962.0400 | 2894.2500 | 31966.5700 | 20.3160 | 531.7940 |         0.0000 | 否            |
| order_items.quantity | 36907 |    2.3200 |    1.0000 |     9.6500 | 14.7590 | 231.9160 |         0.0000 | 否            |
| customers.age        |  3000 |   37.9000 |   36.5000 |     9.9500 |  0.3690 |  -0.5910 |         0.0000 | 否            |
| products.list_price  |   600 | 1761.6700 |  797.4600 |  2032.9500 |  1.4450 |   1.1910 |         0.0000 | 否            |

**解释：** 四个列呈现三种典型形态：订单金额强右偏厚尾（批发异常单）、购买件数高度集中于 1-3 件的长尾分布、客户年龄接近均匀/对称分布、商品标价由类目价格带决定呈多峰。normaltest 在大样本下极其敏感，几乎任何真实业务数据都会被判为非正态——p 值只说明“不是严格正态”，偏度/峰度的量级才说明“偏离多远”。

![Distributions of 4 numeric columns | 四个数值列的分布对比](images/05_5_num_cols_hist.png)

订单金额直方图按 P99 截断显示主体，否则右尾会把图形压成一根针。

# 6. 频率与交叉表

频率分布与交叉表是类别型数据的核心描述工具。本节覆盖四个分类列：`channel`（渠道）、`order_status`（订单状态）、`member_level`（会员等级）、`province`（省份）。SQL 的 GROUP BY 天然适合这类分析。

## 6.1 频率分布

### 6.1.1 一维频率分布

按下单渠道统计订单数，是分类变量最常见的描述方式。

**SQL 代码：**

```sql
SELECT channel, COUNT(*) AS cnt
FROM orders
GROUP BY channel
ORDER BY cnt DESC;
```

**SQL 结果：**

| channel   |   cnt |
|:----------|------:|
| APP       | 11107 |
| 小程序       |  4718 |
| 网页        |  2933 |
| 线下        |   911 |

**Python 代码：**

```python
orders['channel'].value_counts().to_dict()
```

**Python 结果：**

**输出：**
```
{'APP': 11107, '小程序': 4718, '网页': 2933, '线下': 911}
```

**解释：**

- **用途**：识别主力渠道，决定运营资源投放。
- **扩展**：可换成任意分类列（order_status、province）。

### 6.1.2 频率占比

每个订单状态的占比，使用窗口函数 `SUM(COUNT(*)) OVER ()` 得到总数。

**SQL 代码：**

```sql
SELECT order_status,
  COUNT(*) AS cnt,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct
FROM orders
GROUP BY order_status
ORDER BY cnt DESC;
```

**SQL 结果：**

| order_status   |   cnt |     pct |
|:---------------|------:|--------:|
| 已完成            | 17292 | 87.9100 |
| 已取消            |  1048 |  5.3300 |
| 已发货            |   841 |  4.2800 |
| 待付款            |   488 |  2.4800 |

**Python 代码：**

```python
(orders['order_status'].value_counts(normalize=True)*100).round(2).to_dict()
```

**Python 结果：**

**输出：**
```
{'已完成': 87.91, '已取消': 5.33, '已发货': 4.28, '待付款': 2.48}
```

**解释：**

- **技巧**：`SUM(COUNT(*)) OVER ()` 在 GROUP BY 之上再做全表汇总。
- **业务含义**：已完成率、取消率是交易健康度的基本盘指标。

### 6.1.3 累积频率

按渠道订单量降序后的累计占比，用于帕累托分析。

**SQL 代码：**

```sql
WITH freq AS (
  SELECT channel, COUNT(*) AS cnt FROM orders GROUP BY channel
)
SELECT channel, cnt,
  SUM(cnt) OVER (ORDER BY cnt DESC) AS cum_cnt,
  ROUND(SUM(cnt) * 100.0 / SUM(cnt) OVER (), 2) AS cum_pct
FROM freq
ORDER BY cnt DESC;
```

**SQL 结果：**

| channel   |   cnt |   cum_cnt |   cum_pct |
|:----------|------:|----------:|----------:|
| APP       | 11107 |     11107 |  177.0900 |

**Python 代码：**

```python
orders['channel'].value_counts().cumsum()
```

**Python 结果：**

**输出：**
```
已执行
```

**解释：**

- **用途**：判断是否满足 80/20 法则。
- **业务含义**：头部两个渠道若占绝大多数订单，渠道集中风险值得关注。

## 6.2 交叉表

### 6.2.1 二维交叉表

按渠道 × 订单状态统计订单数，观察两变量的联合分布。

**SQL 代码：**

```sql
SELECT channel, order_status, COUNT(*) AS cnt
FROM orders
GROUP BY channel, order_status
ORDER BY channel, order_status;
```

**SQL 结果：**

| channel   | order_status   |   cnt |
|:----------|:---------------|------:|
| APP       | 已发货            |   459 |
| APP       | 已取消            |   575 |
| APP       | 已完成            |  9808 |
| APP       | 待付款            |   265 |
| 小程序       | 已发货            |   193 |
| 小程序       | 已取消            |   265 |
| 小程序       | 已完成            |  4131 |
| 小程序       | 待付款            |   129 |
| 线下        | 已发货            |    48 |
| 线下        | 已取消            |    52 |
| 线下        | 已完成            |   785 |
| 线下        | 待付款            |    26 |
| 网页        | 已发货            |   141 |
| 网页        | 已取消            |   156 |
| 网页        | 已完成            |  2568 |
| 网页        | 待付款            |    68 |

**Python 代码：**

```python
pd.crosstab(orders['channel'], orders['order_status'])
```

**Python 结果：**

**输出：**
```
已执行
```

**解释：**

- **用途**：观察两个类别变量的关联，例如某渠道的取消率是否异常偏高。
- **注意**：`GROUP BY a, b` 与 `GROUP BY b, a` 结果等价，只是顺序不同。

### 6.2.2 透视表

把订单状态作为列展开，用 CASE WHEN 手动透视。

**SQL 代码：**

```sql
SELECT channel,
  SUM(CASE WHEN order_status='已完成' THEN 1 ELSE 0 END) AS 已完成,
  SUM(CASE WHEN order_status='已发货' THEN 1 ELSE 0 END) AS 已发货,
  SUM(CASE WHEN order_status='待付款' THEN 1 ELSE 0 END) AS 待付款,
  SUM(CASE WHEN order_status='已取消' THEN 1 ELSE 0 END) AS 已取消
FROM orders
GROUP BY channel;
```

**SQL 结果：**

| channel   |   已完成 |   已发货 |   待付款 |   已取消 |
|:----------|------:|------:|------:|------:|
| APP       |  9808 |   459 |   265 |   575 |
| 小程序       |  4131 |   193 |   129 |   265 |
| 线下        |   785 |    48 |    26 |    52 |
| 网页        |  2568 |   141 |    68 |   156 |

**Python 代码：**

```python
pd.crosstab(orders['channel'], orders['order_status'])
```

**Python 结果：**

**输出：**
```
已执行
```

**解释：**

- **注意**：SQL 标准没有通用的 PIVOT 语法；SQL Server 有 PIVOT，PostgreSQL 有 crosstab 扩展，MySQL/SQLite 需 CASE WHEN 模拟。

### 6.2.3 双变量均值交叉

按会员等级 × 渠道统计平均订单金额（需要 orders JOIN customers）。

**SQL 代码：**

```sql
SELECT c.member_level, o.channel,
  ROUND(AVG(o.total_amount), 2) AS avg_amount,
  COUNT(*) AS n
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
GROUP BY c.member_level, o.channel
ORDER BY c.member_level, o.channel;
```

**SQL 结果：**

| member_level   | channel   |   avg_amount |    n |
|:---------------|:----------|-------------:|-----:|
| 普通             | APP       |    6603.3800 | 6733 |
| 普通             | 小程序       |    8458.3700 | 2827 |
| 普通             | 线下        |    4572.9600 |  560 |
| 普通             | 网页        |    6976.6600 | 1766 |
| 白银             | APP       |    7099.1200 | 2685 |
| 白银             | 小程序       |    6754.9700 | 1149 |
| 白银             | 线下        |    5094.1600 |  217 |
| 白银             | 网页        |    5630.0100 |  749 |
| 钻石             | APP       |    5769.6700 |  555 |
| 钻石             | 小程序       |    7191.7600 |  232 |
| 钻石             | 线下        |    8941.7500 |   38 |
| 钻石             | 网页        |    4678.7700 |  141 |
| 黄金             | APP       |    7211.5600 | 1134 |
| 黄金             | 小程序       |    6972.5400 |  510 |
| 黄金             | 线下        |   12263.4400 |   96 |
| 黄金             | 网页        |    9949.7900 |  277 |

**Python 代码：**

```python
orders.join(customers.set_index('customer_id'), on='customer_id').pivot_table(values='total_amount', index='member_level', columns='channel', aggfunc='mean')
```

**Python 结果：**

**输出：**
```
已执行
```

**解释：**

- **用途**：发现群体差异（如钻石会员是否在各渠道都消费更高）。
- **注意**：跨表交叉必须先 JOIN，JOIN 键的完整性决定结果可信度。

# 7. 排名与分位

SQL 窗口函数（SQLite 3.25+）提供了 ROW_NUMBER / RANK / DENSE_RANK / PERCENT_RANK / CUME_DIST / NTILE 六个排名函数。本节对订单金额做 Top-N 排名演示。

## 7.1 排名函数

### 7.1.1 行号与排名

ROW_NUMBER 单调递增；RANK 跳号；DENSE_RANK 不跳号。

**SQL 代码：**

```sql
SELECT order_id, total_amount,
  ROW_NUMBER() OVER (ORDER BY total_amount DESC) AS row_num,
  RANK()       OVER (ORDER BY total_amount DESC) AS rank_v,
  DENSE_RANK() OVER (ORDER BY total_amount DESC) AS dense_rank_v
FROM orders
ORDER BY total_amount DESC
LIMIT 10;
```

**SQL 结果：**

|   order_id |   total_amount |   row_num |   rank_v |   dense_rank_v |
|-----------:|---------------:|----------:|---------:|---------------:|
|  6026.0000 |   1385049.1200 |    1.0000 |   1.0000 |         1.0000 |
| 12622.0000 |   1088078.6700 |    2.0000 |   2.0000 |         2.0000 |
| 14127.0000 |    913993.1000 |    3.0000 |   3.0000 |         3.0000 |
|  1798.0000 |    861662.1000 |    4.0000 |   4.0000 |         4.0000 |
|  6474.0000 |    859758.0400 |    5.0000 |   5.0000 |         5.0000 |
| 13926.0000 |    842191.8300 |    6.0000 |   6.0000 |         6.0000 |
| 13902.0000 |    834657.5400 |    7.0000 |   7.0000 |         7.0000 |
|  6036.0000 |    758428.4800 |    8.0000 |   8.0000 |         8.0000 |
| 11928.0000 |    746650.8700 |    9.0000 |   9.0000 |         9.0000 |
| 14467.0000 |    738626.6000 |   10.0000 |  10.0000 |        10.0000 |

**Python 代码：**

```python
orders['total_amount'].rank(method='first'), orders['total_amount'].rank(method='min')
```

**Python 结果：**

**输出：**
```
已执行
```

**解释：**

- **区别**：
  - ROW_NUMBER：无并列，1,2,3,4
  - RANK：并列后跳号，1,1,3,4
  - DENSE_RANK：并列不跳号，1,1,2,3
- **用途**：大额订单 Top-N 榜单、风控重点关注名单。

### 7.1.2 百分位排名与累积分布

PERCENT_RANK 给出行在 [0,1] 的百分位；CUME_DIST 给出累积分布。

**SQL 代码：**

```sql
SELECT order_id, total_amount,
  ROUND(PERCENT_RANK() OVER (ORDER BY total_amount), 4) AS pct_rank,
  ROUND(CUME_DIST()    OVER (ORDER BY total_amount), 4) AS cume_dist
FROM orders
ORDER BY total_amount DESC
LIMIT 10;
```

**SQL 结果：**

|   order_id |   total_amount |   pct_rank |   cume_dist |
|-----------:|---------------:|-----------:|------------:|
|  6026.0000 |   1385049.1200 |     1.0000 |      1.0000 |
| 12622.0000 |   1088078.6700 |     0.9999 |      0.9999 |
| 14127.0000 |    913993.1000 |     0.9999 |      0.9999 |
|  1798.0000 |    861662.1000 |     0.9998 |      0.9998 |
|  6474.0000 |    859758.0400 |     0.9998 |      0.9998 |
| 13926.0000 |    842191.8300 |     0.9997 |      0.9997 |
| 13902.0000 |    834657.5400 |     0.9997 |      0.9997 |
|  6036.0000 |    758428.4800 |     0.9996 |      0.9996 |
| 11928.0000 |    746650.8700 |     0.9996 |      0.9996 |
| 14467.0000 |    738626.6000 |     0.9995 |      0.9995 |

**Python 代码：**

```python
orders['total_amount'].rank(pct=True)
```

**Python 结果：**

**输出：**
```
已执行
```

**解释：**

- **区别**：PERCENT_RANK = (rank-1)/(n-1)；CUME_DIST = rank/n。
- **用途**：ECDF 绘制、百分位分箱。

### 7.1.3 分桶

NTILE(n) 把数据等分成 n 桶。

**SQL 代码：**

```sql
SELECT order_id, total_amount,
  NTILE(10) OVER (ORDER BY total_amount) AS decile
FROM orders
ORDER BY total_amount DESC
LIMIT 10;
```

**SQL 结果：**

|   order_id |   total_amount |   decile |
|-----------:|---------------:|---------:|
|  6026.0000 |   1385049.1200 |  10.0000 |
| 12622.0000 |   1088078.6700 |  10.0000 |
| 14127.0000 |    913993.1000 |  10.0000 |
|  1798.0000 |    861662.1000 |  10.0000 |
|  6474.0000 |    859758.0400 |  10.0000 |
| 13926.0000 |    842191.8300 |  10.0000 |
| 13902.0000 |    834657.5400 |  10.0000 |
|  6036.0000 |    758428.4800 |  10.0000 |
| 11928.0000 |    746650.8700 |  10.0000 |
| 14467.0000 |    738626.6000 |  10.0000 |

**Python 代码：**

```python
pd.qcut(orders['total_amount'], 10, labels=False)
```

**Python 结果：**

**输出：**
```
已执行
```

**解释：**

- **用途**：等频分箱、分层抽样。
- **注意**：NTILE 分桶可能不平衡（n 不能整除行数时）。

# 8. 分组对比

按维度分组后再聚合，是多维描述性分析的核心手段。本节按渠道分组，窗口函数 PARTITION BY 让“组内”与“组间”的比较变得非常自然。

### 8.1 分组均值与方差

按渠道统计订单金额的均值与标准差。

**SQL 代码：**

```sql
SELECT channel,
  COUNT(*) AS n,
  ROUND(AVG(total_amount), 2) AS mean_v,
  ROUND(SQRT(AVG(total_amount*total_amount) - AVG(total_amount)*AVG(total_amount)), 2) AS std_v,
  ROUND(MIN(total_amount), 2) AS min_v,
  ROUND(MAX(total_amount), 2) AS max_v
FROM orders
GROUP BY channel
ORDER BY mean_v DESC;
```

**SQL 结果：**

| channel   |     n |    mean_v |      std_v |   min_v |        max_v |
|:----------|------:|----------:|-----------:|--------:|-------------:|
| 小程序       |  4718 | 7820.6400 | 40309.7000 | 39.5900 | 1385049.1200 |
| 网页        |  2933 | 6803.0900 | 34112.2400 | 41.1700 | 1088078.6700 |
| APP       | 11107 | 6743.6600 | 27632.2300 | 36.0700 |  861662.1000 |
| 线下        |   911 | 5689.7600 | 24180.5700 | 38.2100 |  695650.6700 |

**Python 代码：**

```python
orders.groupby('channel')['total_amount'].agg(['count','mean','std','min','max'])
```

**Python 结果：**

**输出：**
```
已执行
```

**解释：**

- **用途**：组间对比；CV 可比较不同组的相对离散度。
- **判读**：均值接近的组，标准差可能差很多——大额批发单集中在哪个渠道一看便知。

### 8.2 组内占比

每笔订单金额占本渠道总GMV的比例。

**SQL 代码：**

```sql
SELECT order_id, channel, total_amount,
  ROUND(total_amount * 100.0 / SUM(total_amount) OVER (PARTITION BY channel), 4) AS pct_in_channel
FROM orders
ORDER BY channel, pct_in_channel DESC
LIMIT 10;
```

**SQL 结果：**

|   order_id | channel   |   total_amount |   pct_in_channel |
|-----------:|:----------|---------------:|-----------------:|
|       1798 | APP       |    861662.1000 |           1.1504 |
|      13926 | APP       |    842191.8300 |           1.1244 |
|       6036 | APP       |    758428.4800 |           1.0126 |
|      14467 | APP       |    738626.6000 |           0.9861 |
|       4836 | APP       |    647152.8900 |           0.8640 |
|       8461 | APP       |    611205.2500 |           0.8160 |
|       7765 | APP       |    570356.8000 |           0.7615 |
|      10083 | APP       |    560488.1700 |           0.7483 |
|       8692 | APP       |    556756.5400 |           0.7433 |
|      16929 | APP       |    507054.8800 |           0.6770 |

**Python 代码：**

```python
orders['pct'] = orders['total_amount'] / orders.groupby('channel')['total_amount'].transform('sum')
```

**Python 结果：**

**输出：**
```
已执行
```

**解释：**

- **技巧**：`SUM(...) OVER (PARTITION BY g)` 得到组内总和。
- **用途**：贡献度分析，识别单一大客户/大订单依赖。

### 8.3 组内排名

每笔订单在本渠道内的金额排名。

**SQL 代码：**

```sql
SELECT order_id, channel, total_amount,
  ROW_NUMBER() OVER (PARTITION BY channel ORDER BY total_amount DESC) AS rank_in_channel
FROM orders
ORDER BY channel, rank_in_channel
LIMIT 10;
```

**SQL 结果：**

|   order_id | channel   |   total_amount |   rank_in_channel |
|-----------:|:----------|---------------:|------------------:|
|       1798 | APP       |    861662.1000 |                 1 |
|      13926 | APP       |    842191.8300 |                 2 |
|       6036 | APP       |    758428.4800 |                 3 |
|      14467 | APP       |    738626.6000 |                 4 |
|       4836 | APP       |    647152.8900 |                 5 |
|       8461 | APP       |    611205.2500 |                 6 |
|       7765 | APP       |    570356.8000 |                 7 |
|      10083 | APP       |    560488.1700 |                 8 |
|       8692 | APP       |    556756.5400 |                 9 |
|      16929 | APP       |    507054.8800 |                10 |

**Python 代码：**

```python
orders.groupby('channel')['total_amount'].rank(ascending=False, method='first')
```

**Python 结果：**

**输出：**
```
已执行
```

**解释：**

- **用途**：每组的 Top-K、分层对比。
- **扩展**：外层包一层过滤 `WHERE rank_in_channel <= 3` 得每组 Top-3。

### 8.4 组内累计

按渠道内金额降序累积求和。

**SQL 代码：**

```sql
SELECT order_id, channel, total_amount,
  ROUND(SUM(total_amount) OVER (PARTITION BY channel ORDER BY total_amount DESC), 2) AS cum_sum
FROM orders
ORDER BY channel, cum_sum
LIMIT 10;
```

**SQL 结果：**

|   order_id | channel   |   total_amount |      cum_sum |
|-----------:|:----------|---------------:|-------------:|
|       1798 | APP       |    861662.1000 |  861662.1000 |
|      13926 | APP       |    842191.8300 | 1703853.9300 |
|       6036 | APP       |    758428.4800 | 2462282.4100 |
|      14467 | APP       |    738626.6000 | 3200909.0100 |
|       4836 | APP       |    647152.8900 | 3848061.9000 |
|       8461 | APP       |    611205.2500 | 4459267.1500 |
|       7765 | APP       |    570356.8000 | 5029623.9500 |
|      10083 | APP       |    560488.1700 | 5590112.1200 |
|       8692 | APP       |    556756.5400 | 6146868.6600 |
|      16929 | APP       |    507054.8800 | 6653923.5400 |

**Python 代码：**

```python
orders.groupby('channel')['total_amount'].cumsum()
```

**Python 结果：**

**输出：**
```
已执行
```

**解释：**

- **用途**：组内帕累托分析、集中度度量（头部订单占渠道 GMV 的比例）。

# 9. 时序描述

时序轴取 `orders.created_at`，按 GMV 口径（已完成+已发货）聚合成日序列，共 532 天。SQL 的窗口函数和日期函数可以完成绝大多数基础时序分析，STL、ACF 等深度分析见第 15 节。

## 9.1 日 GMV 走势

![Daily GMV | 日 GMV 走势（标注大促与春节）](images/09_1_daily_gmv.png)

**解释：** 肉眼可见三类模式——缓慢上升的趋势、双11/618 的尖峰、春节期间的凹陷。这些模式将在第 15 节被 STL 分解和变点检测定量确认。

## 9.2 时间聚合

```sql
SELECT strftime('%Y-%m', created_at) AS month,
  COUNT(*) AS n_orders,
  ROUND(SUM(total_amount), 2) AS gmv
FROM orders
WHERE order_status IN ('已完成','已发货')
GROUP BY month
ORDER BY month;
```

**SQL 结果：**

| month   |   n_orders |           gmv |
|:--------|-----------:|--------------:|
| 2024-01 |        844 |  5830105.3600 |
| 2024-02 |        644 |  3742162.7400 |
| 2024-03 |        822 |  5102688.6800 |
| 2024-04 |        814 |  4693495.1800 |
| 2024-05 |        858 |  5175141.2000 |
| 2024-06 |       1501 | 10407727.8000 |
| 2024-07 |        873 |  9149187.4800 |
| 2024-08 |        875 |  6144372.4900 |
| 2024-09 |        868 |  6066172.5800 |
| 2024-10 |        916 |  6168272.7200 |
| 2024-11 |       1252 |  9359922.5100 |
| 2024-12 |       1003 |  6709873.8800 |
| 2025-01 |       1087 |  7960279.0800 |
| 2025-02 |        977 |  9633804.9300 |
| 2025-03 |       1205 |  8352553.6400 |
| 2025-04 |       1154 |  8321412.8300 |
| 2025-05 |       1197 |  8930726.9900 |
| 2025-06 |       1243 |  6799374.2400 |

**Python 代码：**

```python
gmv_daily['gmv'].resample('ME').sum()
```

**解释：** 时间聚合是时序分析的第一步。`strftime` 是 SQLite 的日期格式化函数；PostgreSQL/MySQL/SQL Server 分别用 `to_char` / `date_format` / `format`。月度 GMV 整体爬升，11 月与 6 月出现明显峰值。

## 9.3 滚动统计

**SQL 代码：**

```sql
WITH daily AS (
  SELECT date(created_at) AS dt, ROUND(SUM(total_amount), 2) AS gmv
  FROM orders
  WHERE order_status IN ('已完成','已发货')
  GROUP BY date(created_at)
)
SELECT dt, gmv,
  ROUND(AVG(gmv) OVER (ORDER BY dt ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS ma7
FROM daily
ORDER BY dt
LIMIT 20;
```

**SQL 结果（前 20 行）：**

| dt         |         gmv |         ma7 |
|:-----------|------------:|------------:|
| 2024-01-01 | 130037.8500 | 130037.8500 |
| 2024-01-02 |  89752.7900 | 109895.3200 |
| 2024-01-03 | 141459.2500 | 120416.6300 |
| 2024-01-04 | 144281.9500 | 126382.9600 |
| 2024-01-05 | 138799.3200 | 128866.2300 |
| 2024-01-06 | 129921.5200 | 129042.1100 |
| 2024-01-07 | 988436.8600 | 251812.7900 |
| 2024-01-08 | 101132.6000 | 247683.4700 |
| 2024-01-09 | 157742.7000 | 257396.3100 |
| 2024-01-10 | 141282.7300 | 257371.1000 |
| 2024-01-11 | 146040.8800 | 257622.3700 |
| 2024-01-12 | 121693.7400 | 255178.7200 |
| 2024-01-13 | 214997.2200 | 267332.3900 |
| 2024-01-14 | 154929.8600 | 148259.9600 |
| 2024-01-15 | 132962.5200 | 152807.0900 |
| 2024-01-16 |  98257.2000 | 144309.1600 |
| 2024-01-17 | 117856.3100 | 140962.5300 |
| 2024-01-18 |  78165.0200 | 131265.9800 |
| 2024-01-19 | 135991.5300 | 133308.5200 |
| 2024-01-20 | 504858.7200 | 174717.3100 |

**Python 代码：**

```python
gmv_daily['gmv'].rolling(7).mean()
```

**解释：** 7 日滚动均值恰好抹平周末效应（周周期=7），窗口越大越平滑但滞后越大。滚动方差可用 `AVG(x*x)-AVG(x)*AVG(x)` 组合计算。

## 9.4 环比

**SQL 代码：**

```sql
WITH daily AS (
  SELECT date(created_at) AS dt, ROUND(SUM(total_amount), 2) AS gmv
  FROM orders
  WHERE order_status IN ('已完成','已发货')
  GROUP BY date(created_at)
)
SELECT dt, gmv,
  LAG(gmv, 1) OVER (ORDER BY dt) AS prev_gmv,
  ROUND((gmv - LAG(gmv, 1) OVER (ORDER BY dt)) * 100.0 /
        LAG(gmv, 1) OVER (ORDER BY dt), 2) AS pct_change
FROM daily
ORDER BY pct_change DESC
LIMIT 10;
```

**SQL 结果（环比涨幅 Top 10）：**

| dt         |          gmv |    prev_gmv |   pct_change |
|:-----------|-------------:|------------:|-------------:|
| 2024-07-05 | 2304069.2700 | 148734.5300 |    1449.1200 |
| 2024-11-07 | 1254312.1400 | 135860.2800 |     823.2400 |
| 2024-01-07 |  988436.8600 | 129921.5200 |     660.8000 |
| 2024-07-20 | 1176064.1300 | 156541.4200 |     651.2800 |
| 2024-04-03 |  683512.3800 |  96405.3300 |     609.0000 |
| 2024-03-08 |  963209.0000 | 138399.0200 |     595.9700 |
| 2024-12-27 |  614611.4000 | 100786.5200 |     509.8200 |
| 2024-02-17 |  199109.4900 |  33018.3000 |     503.0300 |
| 2025-02-18 |  983025.7400 | 177118.4600 |     455.0100 |
| 2025-01-13 | 1228891.9800 | 222830.2400 |     451.4900 |

**Python 代码：**

```python
gmv_daily['gmv'].pct_change() * 100
```

**解释：** `LAG(col, n)` 取前 n 行值；`LEAD` 取后 n 行。环比涨幅最大的日期几乎都落在大促启动日（11月11日前后、6月初），跌幅最大的则是大促回落日与春节。

## 9.5 累计和

**SQL 代码：**

```sql
WITH daily AS (
  SELECT date(created_at) AS dt, ROUND(SUM(total_amount), 2) AS gmv
  FROM orders
  WHERE order_status IN ('已完成','已发货')
  GROUP BY date(created_at)
)
SELECT dt, gmv,
  ROUND(SUM(gmv) OVER (ORDER BY dt), 2) AS cum_gmv,
  ROUND(SUM(gmv) OVER (ORDER BY dt) * 100.0 / SUM(gmv) OVER (), 4) AS cum_pct
FROM daily
ORDER BY dt
LIMIT 20;
```

**SQL 结果（前 20 行）：**

| dt         |         gmv |      cum_gmv |   cum_pct |
|:-----------|------------:|-------------:|----------:|
| 2024-01-01 | 130037.8500 |  130037.8500 |    0.1012 |
| 2024-01-02 |  89752.7900 |  219790.6400 |    0.1710 |
| 2024-01-03 | 141459.2500 |  361249.8900 |    0.2810 |
| 2024-01-04 | 144281.9500 |  505531.8400 |    0.3933 |
| 2024-01-05 | 138799.3200 |  644331.1600 |    0.5012 |
| 2024-01-06 | 129921.5200 |  774252.6800 |    0.6023 |
| 2024-01-07 | 988436.8600 | 1762689.5400 |    1.3712 |
| 2024-01-08 | 101132.6000 | 1863822.1400 |    1.4499 |
| 2024-01-09 | 157742.7000 | 2021564.8400 |    1.5726 |
| 2024-01-10 | 141282.7300 | 2162847.5700 |    1.6825 |
| 2024-01-11 | 146040.8800 | 2308888.4500 |    1.7961 |
| 2024-01-12 | 121693.7400 | 2430582.1900 |    1.8908 |
| 2024-01-13 | 214997.2200 | 2645579.4100 |    2.0581 |
| 2024-01-14 | 154929.8600 | 2800509.2700 |    2.1786 |
| 2024-01-15 | 132962.5200 | 2933471.7900 |    2.2820 |
| 2024-01-16 |  98257.2000 | 3031728.9900 |    2.3585 |
| 2024-01-17 | 117856.3100 | 3149585.3000 |    2.4501 |
| 2024-01-18 |  78165.0200 | 3227750.3200 |    2.5109 |
| 2024-01-19 | 135991.5300 | 3363741.8500 |    2.6167 |
| 2024-01-20 | 504858.7200 | 3868600.5700 |    3.0095 |

**Python 代码：**

```python
gmv_daily['gmv'].cumsum()
```

**解释：** `SUM() OVER (ORDER BY t)` 默认累积到当前行。累计曲线在双11区间斜率骤增，是观察大促贡献的直观方式。

# 10. 可视化

可视化把抽象统计量转化为直观图形。本节图表标题使用英文，下方中文说明供对照。订单金额强右偏，部分图按 P99 截断显示主体分布，均有注明。

## 10.1 直方图与 KDE

**SQL 代码（分箱）：**

```sql
SELECT CAST(FLOOR(total_amount/200)*200 AS INT) AS bin, COUNT(*) AS cnt FROM orders GROUP BY bin ORDER BY bin;
```

**SQL 结果（前 15 个分箱）：**

|   bin |   cnt |
|------:|------:|
|     0 |  1223 |
|   200 |  1310 |
|   400 |  1200 |
|   600 |   843 |
|   800 |   764 |
|  1000 |   746 |
|  1200 |   584 |
|  1400 |   481 |
|  1600 |   479 |
|  1800 |   443 |
|  2000 |   440 |
|  2200 |   408 |
|  2400 |   414 |
|  2600 |   341 |
|  2800 |   336 |

![Histogram and KDE | 订单金额直方图与核密度估计（P99 截断）](images/10_1_hist_kde.png)

**解释：** 直方图给出粗略分布形状，KDE 用核函数平滑估计概率密度。主体集中在低金额区间，呈单调递减形态。

## 10.2 经验累积分布（ECDF）

**Python 代码：**

```python
sns.ecdfplot(data=orders, x='total_amount')
```

![ECDF of Order Amount | 订单金额的经验累积分布](images/10_2_ecdf.png)

**解释：** 曲线上 (x, y) 表示不超过 x 的样本占 y%。曲线前段陡直上升，说明绝大多数订单金额不大；长尾拉得很平，对应少数大额单。

## 10.3 箱线图

![Boxplot | 分渠道订单金额箱线图（隐藏离群点）](images/10_3_boxplot.png)

**解释：** 箱体 = IQR，中线 = 中位数，须 = 1.5×IQR 内极值。原始离群点太多（异常大单）会压扁箱体，故隐藏离群点显示主体；四个渠道的主体分布接近，说明渠道间客单价差异不大。

## 10.4 小提琴图

![Violin Plot | 分渠道小提琴图（P99 截断）](images/10_4_violin.png)

**解释：** 小提琴宽度反映该值附近的密度，能显示多峰结构。各渠道均呈低金额处最宽的单峰右偏形态。

## 10.5 QQ 图

![Q-Q Plot | 订单金额正态 QQ 图](images/10_5_qq.png)

**解释：** 点接近直线 → 近似正态；两端上翘 → 厚尾；S 型 → 偏态。本例右端急剧上翘，典型右偏厚尾，与第 5 节的偏度/峰度/正态性检验结论一致。

## 10.6 散点图

![Scatter Plot | 客户活跃度 vs 累计消费额散点图](images/10_6_scatter.png)

**解释：** 客户级聚合后，活跃度（生成参数，决定下单频率）与累计消费额的关系形态一目了然，为第 11 节的相关分析提供直观先验。

## 10.7 配对图

![Pair Plot | 客户级变量配对图](images/10_7_pairplot.png)

**解释：** 快速发现相关关系、簇结构、非线性模式。订单数与消费额高度同向，活跃度与两者的关系是关注重点。

## 10.8 相关热力图

![Correlation Heatmap | 客户级变量相关热力图](images/10_8_heatmap.png)

**解释：** 颜色越红越正相关，越蓝越负相关，对角线为 1。Pearson 只度量线性相关；年龄在合成数据中与消费几乎无关，是真实的弱相关。

# 11. 变量关系

变量关系是描述性分析向诊断性分析过渡的部分。本节做两组相关分析：客户级的「年龄 / 活跃度 / 消费额」与商品级的「标价 / 销量」。SQL 能做协方差、相关系数、简单线性回归的公式化计算，但性能有限；pandas 更适合全量数据。

### 11.1 协方差（活跃度 × 消费额）

衡量两个变量同向/反向变化的程度。

**SQL 代码：**

```sql
WITH agg AS (
  SELECT c.customer_id, c.activity_score,
         COALESCE(SUM(o.total_amount), 0) AS spend
  FROM customers c
  LEFT JOIN orders o ON o.customer_id = c.customer_id
                    AND o.order_status IN ('已完成','已发货')
  GROUP BY c.customer_id
)
SELECT ROUND(
  (SUM(activity_score*spend) - SUM(activity_score)*SUM(spend)*1.0/COUNT(*))
    / (COUNT(*)-1), 2) AS cov_samp
FROM agg;
```

**SQL 结果：**

|   cov_samp |
|-----------:|
|  8051.8900 |

**Python 代码：**

```python
cust_agg[['activity_score','total_spend']].cov().iloc[0,1]
```

**Python 结果：**

**输出：**
```
8051.8922
```

**解释：**

- **公式**：Cov(X,Y) = Σ(xᵢ-x̄)(yᵢ-ȳ) / (n-1)。
- **性质**：对称；量纲为两变量乘积。
- **缺点**：受量纲影响，不能直接比较不同变量对的相关强度，需标准化为相关系数。

### 11.2 Pearson 相关系数（活跃度 × 消费额）

标准化后的协方差，取值范围 [-1, 1]。

**SQL 代码：**

```sql
WITH agg AS (
  SELECT c.customer_id, c.activity_score,
         COALESCE(SUM(o.total_amount), 0) AS spend
  FROM customers c
  LEFT JOIN orders o ON o.customer_id = c.customer_id
                    AND o.order_status IN ('已完成','已发货')
  GROUP BY c.customer_id
)
SELECT ROUND(
  (COUNT(*)*SUM(activity_score*spend) - SUM(activity_score)*SUM(spend)) /
  (SQRT(COUNT(*)*SUM(activity_score*activity_score) - SUM(activity_score)*SUM(activity_score)) *
   SQRT(COUNT(*)*SUM(spend*spend) - SUM(spend)*SUM(spend))), 4) AS r
FROM agg;
```

**SQL 结果：**

|      r |
|-------:|
| 0.4112 |

**Python 代码：**

```python
cust_agg['activity_score'].corr(cust_agg['total_spend'])
```

**Python 结果：**

**输出：**
```
0.4112
```

**解释：**

- **判读**：|r|<0.3 弱；0.3-0.7 中等；>0.7 强。
- **业务含义**：活跃度与消费额显著正相关——活跃度是数据生成时决定下单频率的参数，相关是设计出来的，但仍验证了计算链路正确。
- **注意**：Pearson 只度量线性关系；非线性关系可能被低估。

### 11.3 Spearman 秩相关（活跃度 × 消费额）

对秩次计算 Pearson 相关，对单调非线性与异常值稳健。

**SQL 代码：**

```sql
WITH agg AS (
  SELECT c.customer_id, c.activity_score,
         COALESCE(SUM(o.total_amount), 0) AS spend
  FROM customers c
  LEFT JOIN orders o ON o.customer_id = c.customer_id
                    AND o.order_status IN ('已完成','已发货')
  GROUP BY c.customer_id
),
r AS (
  SELECT RANK() OVER (ORDER BY activity_score) AS rx,
         RANK() OVER (ORDER BY spend) AS ry
  FROM agg
)
SELECT ROUND(
  (COUNT(*)*SUM(rx*ry) - SUM(rx)*SUM(ry)) /
  (SQRT(COUNT(*)*SUM(rx*rx) - SUM(rx)*SUM(rx)) *
   SQRT(COUNT(*)*SUM(ry*ry) - SUM(ry)*SUM(ry))), 4) AS spearman_r
FROM r;
```

**SQL 结果：**

|   spearman_r |
|-------------:|
|       0.8445 |

**Python 代码：**

```python
cust_agg['activity_score'].corr(cust_agg['total_spend'], method='spearman')
```

**Python 结果：**

**输出：**
```
0.8430
```

**解释：**

- **对比**：Pearson 与 Spearman 差异大，提示非线性关系或异常值干扰。
- **注意**：SQL 的 RANK() 对并列值给最小名次，与 scipy 的平均秩略有差异，并列值少时两者几乎一致。

### 11.4 简单线性回归（活跃度 → 消费额）

最小二乘意义下的 Y = β₀ + β₁X。

**SQL 代码：**

```sql
WITH agg AS (
  SELECT c.customer_id, c.activity_score,
         COALESCE(SUM(o.total_amount), 0) AS spend
  FROM customers c
  LEFT JOIN orders o ON o.customer_id = c.customer_id
                    AND o.order_status IN ('已完成','已发货')
  GROUP BY c.customer_id
),
s AS (
  SELECT COUNT(*) AS n, SUM(activity_score) AS sx, SUM(spend) AS sy,
         SUM(activity_score*activity_score) AS sxx,
         SUM(activity_score*spend) AS sxy
  FROM agg
)
SELECT
  ROUND((n*sxy - sx*sy)*1.0 / (n*sxx - sx*sx), 2) AS slope,
  ROUND((sy - (n*sxy - sx*sy)*1.0/(n*sxx - sx*sx) * sx) / n, 2) AS intercept
FROM s;
```

**SQL 结果：**

|       slope |   intercept |
|------------:|------------:|
| 188345.6800 |    975.6800 |

**Python 代码：**

```python
from scipy.stats import linregress; linregress(cust_agg['activity_score'], cust_agg['total_spend'])
```

**Python 结果：**

**输出：**
```
已执行（见下方文字解读）
```

**解释：**

- **公式**：β₁ = (nΣxy - ΣxΣy) / (nΣx² - (Σx)²)；β₀ = ȳ - β₁x̄。
- **用途**：刻画趋势、做预测基线。
- **注意**：一元回归可用 SQL；多元回归建议 Python（L3 层内容）。

## 11.1 价格与销量的关系

商品级聚合：每个商品的标价 `list_price` 与累计销量 `total_qty`。需求定律预期负相关，但多品类混合数据常被品类结构干扰（辛普森悖论的高发区）。

**SQL 代码（Pearson 公式化）：**

```sql
WITH pq AS (
  SELECT p.product_id, p.list_price,
         COALESCE(SUM(CASE WHEN o.order_status IN ('已完成','已发货')
                           THEN oi.quantity ELSE 0 END), 0) AS qty
  FROM products p
  LEFT JOIN order_items oi ON oi.product_id = p.product_id
  LEFT JOIN orders o ON o.order_id = oi.order_id
  GROUP BY p.product_id
)
SELECT ROUND(
  (COUNT(*)*SUM(list_price*qty) - SUM(list_price)*SUM(qty)) /
  (SQRT(COUNT(*)*SUM(list_price*list_price) - SUM(list_price)*SUM(list_price)) *
   SQRT(COUNT(*)*SUM(qty*qty) - SUM(qty)*SUM(qty))), 4) AS r
FROM pq
WHERE qty > 0;
```

**Python 结果：**

**输出：**
```
Pearson  r = 0.0185
Spearman ρ = -0.0047
```

![Price vs Quantity | 商品标价与累计销量散点图](images/11_5_price_qty.png)

**解释：** 整体相关系数接近零甚至略正，并不等于价格不影响销量——手机数码的高价品与食品饮料的低价品混在一起时，品类间价格带差异会掩盖品类内的需求弹性。这正是分层分析（按品类分别算相关）存在的意义，也是 L2 诊断性分析的入口。

# 12. 缺失值分析

缺失值处理是数据清洗的第一步。本库的缺失是结构性的：订单状态机决定时间链字段何时为 NULL，是判断缺失机制（MCAR/MAR/MNAR）的绝佳样本。

### 12.1 单变量空值率

支付时间列的空值占比。

**SQL 代码：**

```sql
SELECT
  ROUND(SUM(CASE WHEN paid_at IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS pct_null
FROM orders;
```

**SQL 结果：**

|   pct_null |
|-----------:|
|     2.4800 |

**Python 代码：**

```python
orders['paid_at'].isnull().mean() * 100
```

**Python 结果：**

**输出：**
```
2.4811
```

**解释：**

- **标准**：< 5% 轻微；5-30% 中等；> 30% 严重。
- **判读**：paid_at 空值率 ≈ (待付款+已取消) 订单占比，与业务口径严丝合缝。

### 12.2 按组空值分布

按订单状态分组观察 delivered_at 空值率，判断缺失机制。

**SQL 代码：**

```sql
SELECT order_status,
  COUNT(*) AS n_total,
  SUM(CASE WHEN delivered_at IS NULL THEN 1 ELSE 0 END) AS n_null,
  ROUND(SUM(CASE WHEN delivered_at IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS pct_null
FROM orders
GROUP BY order_status
ORDER BY pct_null DESC;
```

**SQL 结果：**

| order_status   |   n_total |   n_null |   pct_null |
|:---------------|----------:|---------:|-----------:|
| 待付款            |       488 |      488 |   100.0000 |
| 已取消            |      1048 |     1048 |   100.0000 |
| 已发货            |       841 |      841 |   100.0000 |
| 已完成            |     17292 |        0 |     0.0000 |

**Python 代码：**

```python
orders.groupby('order_status')['delivered_at'].apply(lambda x: x.isnull().mean()*100)
```

**Python 结果：**

**输出：**
```
已执行
```

**解释：**

- **判读**：空值率按状态呈 0% / 100% 两极分布——缺失完全由状态决定（MNAR）。
- **结论**：这类缺失不能用均值/中位数填补，正确做法是按状态分层或把“是否签收”本身作为特征。

# 13. 异常值检测

异常值（Outlier）是远离主体分布的观测。本数据集刻意注入了约 1.2% 批发型异常订单（单件商品数量 30~200）与 0.5% 价格异常订单（单价 ×10），集中体现在 `total_amount` 的右尾，是 IQR 与 Z-score 方法的现成靶子。

### 13.1 1.5×IQR 异常值边界

低于 Q1 - 1.5×IQR 或高于 Q3 + 1.5×IQR 的观测视为疑似异常。

**SQL 代码：**

```sql
WITH q AS (
  SELECT total_amount, PERCENT_RANK() OVER (ORDER BY total_amount) AS pr
  FROM orders
), s AS (
  SELECT
    MAX(CASE WHEN pr <= 0.25 THEN total_amount END) AS q1,
    MAX(CASE WHEN pr <= 0.75 THEN total_amount END) AS q3
  FROM q
)
SELECT ROUND(q1, 2) AS q1, ROUND(q3, 2) AS q3, ROUND(q3-q1, 2) AS iqr,
  ROUND(q1 - 1.5*(q3-q1), 2) AS lower_bound,
  ROUND(q3 + 1.5*(q3-q1), 2) AS upper_bound
FROM s;
```

**SQL 结果：**

|       q1 |        q3 |       iqr |   lower_bound |   upper_bound |
|---------:|----------:|----------:|--------------:|--------------:|
| 900.7200 | 6804.6700 | 5903.9500 |    -7955.2000 |    15660.5900 |

**Python 代码：**

```python
q1,q3 = orders['total_amount'].quantile([0.25,0.75]); iqr=q3-q1
```

**Python 结果：**

**输出：**
```
lower = -7955.2050, upper = 15660.5950
上界之外的订单数 = 1196（占比 6.08%）
```

**解释：**

- **判读**：IQR 法在右偏数据上只报高侧异常，抓到的正是批发大单与价格异常单。
- **注意**：异常值不一定是错误值——批发单是真实业务，应与零售单分开分析。

### 13.2 Z-score 异常值边界

`|Z| > 3` 的观测视为疑似异常。

**SQL 代码：**

```sql
WITH s AS (
  SELECT AVG(total_amount) AS mu,
         SQRT(AVG(total_amount*total_amount) - AVG(total_amount)*AVG(total_amount)) AS sigma
  FROM orders
)
SELECT COUNT(*) AS n_outlier
FROM orders, s
WHERE ABS((total_amount - mu) / sigma) > 3;
```

**SQL 结果：**

|   n_outlier |
|------------:|
|         125 |

**Python 代码：**

```python
((orders['total_amount'] - orders['total_amount'].mean()) / orders['total_amount'].std(ddof=0)).abs().gt(3).sum()
```

**Python 结果：**

**输出：**
```
Z-score 判出的异常订单数 = 125
```

**解释：**

- **判读**：正态分布下 |Z| > 3 的概率约 0.3%。
- **注意**：Z-score 的均值和标准差本身被极端值拉高（掩蔽效应），在强右偏数据上会漏报——本例 IQR 法抓到的异常远多于 Z-score，实战中偏态数据优先用 IQR 或稳健 Z-score（基于中位数与 MAD）。

# 14. 数据质量检查

数据质量直接影响分析结果。除主键与重复行外，多表数据库还要校验跨表金额一致性。

### 14.1 主键唯一性

检查 order_id 是否有重复。

**SQL 代码：**

```sql
SELECT order_id, COUNT(*) AS cnt
FROM orders
GROUP BY order_id
HAVING COUNT(*) > 1
LIMIT 10;
```

**SQL 结果：**

| order_id   | cnt   |
|------------|-------|

**Python 代码：**

```python
orders['order_id'].duplicated().sum()
```

**Python 结果：**

**输出：**
```
0
```

**解释：**

- **判读**：无结果说明主键唯一；有结果说明主键冲突。
- **修复**：去重、重建主键、业务核对。

### 14.2 完全重复行

所有列都相同的行数。

**SQL 代码：**

```sql
SELECT COUNT(*) AS n_dup_groups
FROM (
  SELECT order_id, customer_id, order_status, channel, total_amount,
         COUNT(*) AS cnt
  FROM orders
  GROUP BY order_id, customer_id, order_status, channel, total_amount
  HAVING COUNT(*) > 1
) x;
```

**SQL 结果：**

|   n_dup_groups |
|---------------:|
|              0 |

**Python 代码：**

```python
orders.duplicated().sum()
```

**Python 结果：**

**输出：**
```
0
```

**解释：**

- **判读**：完全重复行通常是数据导入错误。
- **修复**：`DELETE FROM t WHERE rowid NOT IN (SELECT MIN(rowid) FROM t GROUP BY all_cols)`。

### 14.3 金额链路一致性

校验每笔订单是否满足 total_amount = Σ(明细小计) + 运费，这是本数据集文档承诺的不变量。

**SQL 代码：**

```sql
SELECT COUNT(*) AS n_violation
FROM (
  SELECT o.order_id,
         ABS(o.total_amount - (SUM(oi.subtotal) + o.freight_amount)) AS diff
  FROM orders o
  JOIN order_items oi ON oi.order_id = o.order_id
  GROUP BY o.order_id
  HAVING diff > 0.02
) x;
```

**SQL 结果：**

|   n_violation |
|--------------:|
|             0 |

**Python 代码：**

```python
# Python: 逐单比对 orders.total_amount 与 order_items.subtotal 合计 + freight_amount
```

**Python 结果：**

**输出：**
```
违规订单数 = 0（链路一致）
```

**解释：**

- **判读**：0 违规说明金额链路闭合，GMV、优惠率等派生指标可放心使用。
- **价值**：跨表不变量是数据质量检查中最有业务含金量的一类规则。

# 15. 时序深度分析

以下分析超出 SQL 能力，需要 Python 的 statsmodels / ruptures 库。分析对象为日 GMV 序列（532 天），数据中埋有双11/618峰值与春节低谷。

## 15.1 STL 分解

**Python 代码：**

```python
STL(ts, period=7).fit().plot()  # period=7 对应周季节（周末效应）
```

![STL Decomposition | 日 GMV 的 STL 分解（周季节）](images/15_1_stl.png)

**解释：** 拆分趋势、季节、残差三项。趋势项缓慢爬升；季节项捕捉固定的周内节奏（周末效应）；残差项中的尖刺正是双11/618，它们不属于规则季节，因而残留在 resid 中——这也是大促需要单独建模的原因。

## 15.2 ACF / PACF

**Python 代码：**

```python
plot_acf(ts); plot_pacf(ts)
```

![ACF and PACF | 日 GMV 自相关与偏自相关](images/15_2_acf_pacf.png)

**解释：** ACF 在 lag=7 及其倍数处的凸起对应周季节；整体缓慢衰减反映趋势非平稳，建模前需差分。用于识别 AR/MA 结构，辅助 ARIMA 定阶。

## 15.3 结构断点检测

**Python 代码：**

```python
rpt.Binseg(model='l2').fit(signal).predict(n_bkps=6)  # 主方法
rpt.Pelt(model='rbf').fit(signal).predict(pen=5)      # 对照
```

![Structural Break Detection | 日 GMV 结构断点检测](images/15_3_ruptures.png)

**Binseg 检测到的变点日期：** 2024-05-29、2024-06-18、2025-01-24、2025-02-08、2025-03-05、2025-05-29

**PELT(rbf) 对照结果：** 2024-05-29、2024-06-18、2024-12-30

**解释：** 变点把序列切成了业务上可命名的段落——2024-05-29 ~ 2024-06-18 是 618 大促窗口；2025-01-24 ~ 2025-02-08 正好框住春节（1 月 29 日）低谷；2025-05-29 对应 2025 年 618 预热启动；PELT 额外抓到的 2024-12-30 是双 11/双 12 高位后的回落点。变点与大促、春节对齐，说明这些事件对 GMV 的改变是“结构性”的而非噪声波动。方法上，Binseg 适合变点个数可预估的场景，PELT 用惩罚项自动权衡个数与拟合度； penal（pen）越大变点越少，本序列 pen=10 时只剩一个变点，欠拟合。

# 16. SQL 描述性分析能力总结

本报告全部统计量都给出了 SQL 与 Python 双实现，能力边界汇总如下。

| 分析类型           | SQL 覆盖度   | 主要手段                                   |
|:---------------|:----------|:---------------------------------------|
| 数据探查           | ✅ 全部      | COUNT / COUNT DISTINCT / IS NULL       |
| 集中趋势           | ✅ 全部      | AVG / 窗口函数中位数 / 公式化几何均值                |
| 离散程度           | ✅ 全部      | 公式化方差/标准差 / IQR / MAD                  |
| 分布形态           | ⚠️ 大部分    | 偏度/峰度可公式化；正态性检验需 Python                |
| 频率与交叉表         | ✅ 全部      | GROUP BY / CASE WHEN 透视                |
| 排名与分位          | ✅ 全部      | ROW_NUMBER / RANK / DENSE_RANK / NTILE |
| 分组对比           | ✅ 全部      | PARTITION BY / 组内占比 / 组内累计             |
| 时序描述           | ✅ 大部分     | strftime / ROWS BETWEEN / LAG / LEAD   |
| 变量关系           | ⚠️ 边缘     | Pearson/Spearman/一元回归可公式化（性能差）         |
| 缺失值            | ✅ 全部      | CASE WHEN IS NULL + 分组缺失率              |
| 异常值            | ✅ 单变量     | IQR / Z-score 公式化                      |
| 数据质量           | ✅ 全部      | HAVING COUNT(*) > 1 / 跨表不变量校验          |
| 可视化            | ❌ 部分      | 只能提供分箱数据，绘图需 Python                    |
| 正态性检验          | ❌ 不做      | 需 Python 的 scipy.stats                 |
| STL / ACF / 断点 | ❌ 不做      | 需 Python 的 statsmodels / ruptures      |

**结论**：SQL 在描述性分析中几乎无所不能，多表 JOIN 后更是如此。真正的边界在分布检验（normaltest）、可视化、以及时序深度分析——那里需要数值优化和迭代计算，SQL 只能算“数”，不能“学”模型。
