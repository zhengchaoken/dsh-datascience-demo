# 诊断性分析报告 - 电商交易数据集

- **数据来源**：`data/ecommerce/ecommerce.db`（orders/order_items/products/customers 关联抽取）
- **样本量**：34059 行
- **客户数**：2493
- **商品数**：558

## 目录

- 1 数据概览
  - 1.1 字段说明
  - 1.2 样本预览
- 2 相关性分析
  - 2.1 Pearson 相关系数矩阵
    - 2.1.1 单对变量：Quantity vs UnitPrice
    - 2.1.2 三变量相关矩阵：SQL 逐对计算
    - 2.1.3 全量数据上的 SQL 版：聚合 + Python 组装
    - 2.1.4 Python 版：pandas 全量相关矩阵
  - 2.2 Spearman 秩相关（Python 补充）
  - 2.3 相关热力图
- 3 关联规则挖掘
  - 3.1 数据准备：构建购物篮矩阵
  - 3.2 Apriori 频繁项集
  - 3.3 关联规则生成与评估
  - 3.4 关联规则可视化
- 4 聚类分析
  - 4.1 RFM 特征工程
  - 4.2 数据标准化
  - 4.3 确定最优聚类数 K
  - 4.4 K-Means 聚类
  - 4.5 DBSCAN 聚类对比
  - 4.6 聚类可视化（PCA 降维）

---
# 1. 数据概览

本报告基于统一电商数据库 `ecommerce.db`（2024-01-01 至 2025-06-15 的订单数据），从 orders / order_items / products / customers 四表关联抽取出「已支付订单明细」宽表。诊断性分析从**相关性分析**、**关联规则挖掘**、**聚类分析**三个维度展开。

## 1.1 字段说明

| 字段          | 中文说明   | 描述                                  |
|:------------|:-------|:------------------------------------|
| InvoiceNo   | 订单号    | orders.order_id，每笔订单唯一标识            |
| StockCode   | 商品ID   | products.product_id                 |
| Description | 商品名称   | 品牌+品类词+型号                           |
| Quantity    | 数量     | order_items.quantity，明细行件数          |
| InvoiceDate | 下单时间   | orders.created_at                   |
| UnitPrice   | 成交单价   | order_items.unit_price（含促销浮动）       |
| CustomerID  | 客户ID   | customers.customer_id               |
| Country     | 省份     | customers.province（沿用原列名）           |
| TotalPrice  | 明细小计   | order_items.subtotal = 单价×数量 - 分摊优惠 |

## 1.2 样本预览

|   InvoiceNo |   StockCode | Description   |   Quantity | InvoiceDate         |   UnitPrice |   CustomerID | Country   |   TotalPrice |
|------------:|------------:|:--------------|-----------:|:--------------------|------------:|-------------:|:----------|-------------:|
|           1 |         209 | 安踏T恤P797      |          1 | 2024-01-01 15:53:49 |     92.9500 |          578 | 湖北省       |      92.9500 |
|           1 |         316 | 自然堂面膜K962     |          1 | 2024-01-01 15:53:49 |    222.9700 |          578 | 湖北省       |     222.9700 |
|           2 |          42 | 小米耳机A555      |          1 | 2024-01-01 19:30:04 |   1417.1100 |         1210 | 江苏省       |    1417.1100 |
|           2 |         350 | 百雀羚口红B506     |          1 | 2024-01-01 19:30:04 |    492.3300 |         1210 | 江苏省       |     492.3300 |
|           3 |         586 | 飞鹤婴儿车N424     |          2 | 2024-01-01 01:15:15 |   2570.7200 |          471 | 湖南省       |    5091.4400 |

# 2. 相关性分析

相关性分析（Correlation Analysis）用于诊断变量之间是否存在线性或单调关联。在零售场景中，可用来判断「购买数量与单价的关系」「销售额与客户活跃度的关系」等，为后续 RFM 建模和聚类提供特征选择依据。

本章节同时给出 **SQL 实现** 与 **Python 实现**：
- SQL 版本：注册 `SQRT` 函数后，在 SQLite 里直接计算 Pearson 相关系数；为了避免数万行逐行调用 `SQRT` 的性能问题，纯 SQL 计算在 20000 行样本表上演示。
- Python 版本：用 `pandas.DataFrame.corr()`，底层是 C 实现，可在全量数据上毫秒级完成。

## 2.1 Pearson 相关系数矩阵

### 2.1.1 单对变量：Quantity vs UnitPrice

**SQL 代码（在 20000 行样本表上执行）：**

```sql
SELECT
  (COUNT(*)*SUM(Quantity*UnitPrice) - SUM(Quantity)*SUM(UnitPrice)) /
  (SQRT(COUNT(*)*SUM(Quantity*Quantity) - SUM(Quantity)*SUM(Quantity)) *
   SQRT(COUNT(*)*SUM(UnitPrice*UnitPrice) - SUM(UnitPrice)*SUM(UnitPrice))) AS corr_qty_price
FROM retail_sample;
```

**SQL 结果：**

|   corr_qty_price |
|-----------------:|
|           0.0020 |

**Python 代码：**

```python
corr_value = df['Quantity'].corr(df['UnitPrice'])
print('Pearson r = %.4f' % corr_value)
```

**Python 结果：**

**输出：**
```
Pearson r = 0.0035
```

**解释：** Pearson 相关系数衡量线性相关强度。Quantity 与 UnitPrice 的相关系数如果为负，说明「买得越多单价越低」——这是批发场景中常见的数量折扣现象。具体判读标准：$|r| < 0.3$ 弱相关，$0.3 \le |r| < 0.7$ 中等相关，$|r| \ge 0.7$ 强相关。

### 2.1.2 三变量相关矩阵：SQL 逐对计算

在 20000 行样本表上，用 SQL 计算 Quantity、UnitPrice、TotalPrice 三个变量两两之间的相关系数。

**SQL 代码：**

```sql
SELECT
  (COUNT(*)*SUM(Quantity*UnitPrice) - SUM(Quantity)*SUM(UnitPrice)) /
  (SQRT(COUNT(*)*SUM(Quantity*Quantity) - SUM(Quantity)*SUM(Quantity)) *
   SQRT(COUNT(*)*SUM(UnitPrice*UnitPrice) - SUM(UnitPrice)*SUM(UnitPrice))) AS corr_qty_price,
  (COUNT(*)*SUM(Quantity*TotalPrice) - SUM(Quantity)*SUM(TotalPrice)) /
  (SQRT(COUNT(*)*SUM(Quantity*Quantity) - SUM(Quantity)*SUM(Quantity)) *
   SQRT(COUNT(*)*SUM(TotalPrice*TotalPrice) - SUM(TotalPrice)*SUM(TotalPrice))) AS corr_qty_total,
  (COUNT(*)*SUM(UnitPrice*TotalPrice) - SUM(UnitPrice)*SUM(TotalPrice)) /
  (SQRT(COUNT(*)*SUM(UnitPrice*UnitPrice) - SUM(UnitPrice)*SUM(UnitPrice)) *
   SQRT(COUNT(*)*SUM(TotalPrice*TotalPrice) - SUM(TotalPrice)*SUM(TotalPrice))) AS corr_price_total
FROM retail_sample;
```

**SQL 结果：**

|   corr_qty_price |   corr_qty_total |   corr_price_total |
|-----------------:|-----------------:|-------------------:|
|           0.0020 |           0.6658 |             0.1912 |

**SQL 结果（矩阵形式）：**

| Variable   |   Quantity |   UnitPrice |   TotalPrice |
|:-----------|-----------:|------------:|-------------:|
| Quantity   |     1.0000 |      0.0020 |       0.6658 |
| UnitPrice  |     0.0020 |      1.0000 |       0.1912 |
| TotalPrice |     0.6658 |      0.1912 |       1.0000 |

### 2.1.3 全量数据上的 SQL 版：聚合 + Python 组装

直接在数万行上跑逐行 `SQRT` 会非常慢。工程上更实用的做法是：**让 SQL 只做聚合**（SUM、COUNT 都是 C 实现，非常快），**把最终公式放在 Python 里组装**。这样既保留了 SQL 的表达力，又避免了跨语言逐行调用。

**SQL 代码（全量聚合）：**

```sql
SELECT
  COUNT(*) AS n,
  SUM(Quantity) AS sum_x,
  SUM(UnitPrice) AS sum_y,
  SUM(Quantity*Quantity) AS sum_xx,
  SUM(UnitPrice*UnitPrice) AS sum_yy,
  SUM(Quantity*UnitPrice) AS sum_xy
FROM retail;
```

**SQL 结果：**

|          n |      sum_x |         sum_y |       sum_xx |            sum_yy |         sum_xy |
|-----------:|-----------:|--------------:|-------------:|------------------:|---------------:|
| 34059.0000 | 79488.0000 | 54255759.0900 | 3438036.0000 | 257242106847.8677 | 129229263.2000 |

**Python 代码（由聚合值组装 Pearson 公式）：**

```python
n     = agg_df['n'][0]
sum_x = agg_df['sum_x'][0]
sum_y = agg_df['sum_y'][0]
sum_xx = agg_df['sum_xx'][0]
sum_yy = agg_df['sum_yy'][0]
sum_xy = agg_df['sum_xy'][0]

numerator   = n * sum_xy - sum_x * sum_y
denominator = math.sqrt(n * sum_xx - sum_x**2) * math.sqrt(n * sum_yy - sum_y**2)
corr_sql_full = numerator / denominator
print('全量 SQL+Python 组装 r = %.6f' % corr_sql_full)
```

**Python 结果：**

**输出：**
```
全量 SQL+Python 组装 r = 0.003495
```

**解释：** 这个方法把重活（求和）交给 SQLite 的 C 实现，把开方、除法留给 Python，全量数据毫秒级完成，而且精度与直接调用 `df.corr()` 一致。

### 2.1.4 Python 版：pandas 全量相关矩阵

pandas 的 `corr()` 方法一行就能得到完整相关矩阵，底层是 numpy 向量化运算，3.7 万行数据毫秒级完成。

**Python 代码：**

```python
corr_matrix = df[['Quantity', 'UnitPrice', 'TotalPrice']].corr(method='pearson')
print(corr_matrix)
```

**Python 结果：**

**输出：**
```
            Quantity  UnitPrice  TotalPrice
Quantity      1.0000     0.0035      0.6744
UnitPrice     0.0035     1.0000      0.1879
TotalPrice    0.6744     0.1879      1.0000
```

**解释：** 对比上面三节的三种实现（SQL 样本版 / 全量 SQL+Python 组装版 / pandas 版），结果数量级完全一致。实际工程中推荐 **pandas 版**（最简）或 **SQL 聚合 + Python 组装版**（SQL 与 Python 分工明确）。纯 SQL 逐行 `SQRT` 只用于教学演示。

## 2.2 Spearman 秩相关（Python 补充）

Pearson 只度量线性相关。若变量关系是单调但非线性（如指数关系），或存在明显离群值，可用 Spearman 秩相关。Spearman 先把数据转成秩次，再对秩次算 Pearson 相关，对异常值和单调非线性关系更稳健。

**Python 代码：**

```python
spearman_corr = df[['Quantity', 'UnitPrice', 'TotalPrice']].corr(method='spearman')
print(spearman_corr)
```

**Python 结果：**

**输出：**
```
            Quantity  UnitPrice  TotalPrice
Quantity      1.0000     0.0011      0.3052
UnitPrice     0.0011     1.0000      0.9428
TotalPrice    0.3052     0.9428      1.0000
```

**解释：** 对比 Pearson 与 Spearman 的结果差异可以判断关系的性质：若两者接近，说明关系近似线性；若 Spearman 明显高于 Pearson，说明存在单调但非线性的关系（例如 Quantity 翻倍时 TotalPrice 增长更快）。SQL 也可以算 Spearman，但需要用窗口函数 `RANK()` 先转秩次，写法较繁琐，这里用 Python 更简洁。

## 2.3 相关热力图

用热力图直观展示多个数值变量之间的相关结构。以下图同时展示 Pearson 与 Spearman 两套结果。

**Python 代码：**

```python
fig, ax = plt.subplots(1, 2, figsize=(12, 5))
sns.heatmap(df[['Quantity','UnitPrice','TotalPrice']].corr(method='pearson'),
            annot=True, cmap='coolwarm', fmt='.2f', ax=ax[0], vmin=-1, vmax=1)
ax[0].set_title('Pearson Correlation')
sns.heatmap(df[['Quantity','UnitPrice','TotalPrice']].corr(method='spearman'),
            annot=True, cmap='coolwarm', fmt='.2f', ax=ax[1], vmin=-1, vmax=1)
ax[1].set_title('Spearman Correlation')
plt.tight_layout()
```

![Pearson and Spearman Correlation Heatmaps | Pearson 与 Spearman 相关热力图](F:\code\dsh-datascience-demo\src\data\L2\images_diagnostic/2_3_corr_heatmap.png)

**中文说明：** 左图 = Pearson 相关热力图（Pearson Correlation）；右图 = Spearman 相关热力图（Spearman Correlation）。颜色越红表示正相关越强，越蓝表示负相关越强。

**解释：** $|r| < 0.3$ 弱相关，$0.3 \le |r| < 0.7$ 中等相关，$|r| \ge 0.7$ 强相关。对零售数据，Quantity 与 TotalPrice 通常呈强正相关；Quantity 与 UnitPrice 的负相关反映批发折扣；UnitPrice 与 TotalPrice 的相关性取决于单价与数量的相对贡献。

# 3. 关联规则挖掘

关联规则挖掘（Association Rule Mining）用于发现「同时出现」的商品组合，核心指标包括**支持度**（Support）、**置信度**（Confidence）和**提升度**（Lift）。典型应用是购物篮分析（Market Basket Analysis），用于商品捆绑推荐、货架布局优化。

## 3.1 数据准备：构建购物篮矩阵

Apriori 算法需要事务-商品矩阵（每行一笔交易，每列一个商品，值为 0/1）。由于商品数量庞大，先筛选出现频率最高的前 50 个商品。

**SQL 代码（Top 50 商品）：**

```sql
SELECT StockCode, COUNT(DISTINCT InvoiceNo) AS freq
FROM retail
GROUP BY StockCode
ORDER BY freq DESC
LIMIT 50;
```

**SQL 结果（前 10 行）：**

|   StockCode |   freq |
|------------:|-------:|
|         336 |    311 |
|         536 |    304 |
|         164 |    301 |
|          85 |    286 |
|         414 |    258 |
|          28 |    253 |
|         372 |    252 |
|         114 |    238 |
|         323 |    234 |
|         380 |    231 |

**Python 代码：**

```python
top_items = df['StockCode'].value_counts().head(50).index
df_top = df[df['StockCode'].isin(top_items)]
basket = df_top.groupby(['InvoiceNo', 'StockCode'])['Quantity'].sum().unstack().fillna(0)
basket_sets = basket.map(lambda x: 1 if x > 0 else 0)
print('购物篮矩阵形状:', basket_sets.shape)
```

**Python 结果：**

**输出：**
```
购物篮矩阵形状: (8343, 50)
```

## 3.2 Apriori 频繁项集

Apriori 通过逐层扫描发现频繁项集，支持度阈值设为 0.02（即至少 2% 的交易包含该组合）。

**Python 代码：**

```python
frequent_itemsets = apriori(basket_sets, min_support=0.02, use_colnames=True)
frequent_itemsets['length'] = frequent_itemsets['itemsets'].apply(lambda x: len(x))
print(frequent_itemsets.sort_values('support', ascending=False).head(10))
```

**Python 结果：**

**输出：**
```
 support         itemsets  length
  0.0373 frozenset({336})       1
  0.0364 frozenset({536})       1
  0.0361 frozenset({164})       1
  0.0343  frozenset({85})       1
  0.0309 frozenset({414})       1
  0.0303  frozenset({28})       1
  0.0302 frozenset({372})       1
  0.0285 frozenset({114})       1
  0.0280 frozenset({323})       1
  0.0277 frozenset({380})       1
```

**解释：** 支持度表示该商品组合在所有交易中出现的比例。支持度越高，说明该组合越普遍。频繁项集是生成关联规则的基础。

## 3.3 关联规则生成与评估

从频繁项集中生成关联规则，以置信度为筛选标准（阈值 0.5）。

**Python 代码：**

```python
rules = association_rules(frequent_itemsets, metric='confidence', min_threshold=0.5)
rules = rules.sort_values('lift', ascending=False)
print(rules[['antecedents','consequents','support','confidence','lift']].head(10))
```

**Python 结果：**

**输出：**
```
Empty DataFrame
Columns: [antecedents, consequents, support, confidence, lift]
Index: []
```

**解释：** 置信度表示「买了 A 之后再买 B」的条件概率；提升度 > 1 表示 A 和 B 正相关（互相促进），= 1 表示独立，< 1 表示负相关。提升度是评估规则实用性的关键指标，实践中最看重提升度而非单纯的置信度。

## 3.4 关联规则可视化

用散点图展示支持度 vs 置信度，颜色表示提升度。

**Python 代码：**

```python
plt.scatter(rules['support'], rules['confidence'], c=rules['lift'], cmap='viridis')
```

# 4. 聚类分析

聚类分析（Clustering）将客户/交易分成内部相似、组间不同的群体。本报告采用 RFM 模型构建客户特征，然后使用 K-Means 和 DBSCAN 进行聚类。

## 4.1 RFM 特征工程

RFM 模型从三个维度刻画客户价值：**R**ecency（最近一次购买距今天数）、**F**requency（购买频次）、**M**onetary（总消费金额）。

**SQL 代码：**

```sql
SELECT CustomerID,
  JULIANDAY('2025-06-16') - JULIANDAY(MAX(InvoiceDate)) AS Recency,
  COUNT(DISTINCT InvoiceNo) AS Frequency,
  SUM(TotalPrice) AS Monetary
FROM retail
GROUP BY CustomerID
HAVING Monetary > 0
LIMIT 5;
```

**SQL 结果（前 5 行）：**

|   CustomerID |   Recency |   Frequency |    Monetary |
|-------------:|----------:|------------:|------------:|
|       2.0000 |   14.0502 |     13.0000 | 149034.9600 |
|       3.0000 |   95.4673 |      2.0000 |  31744.3400 |
|       4.0000 |    0.7239 |      9.0000 |  38104.3300 |
|       5.0000 |   12.1621 |      3.0000 |  17649.6000 |
|       7.0000 |   16.0518 |     17.0000 |  64796.7100 |

**Python 代码：**

```python
snapshot_date = df['InvoiceDate'].max() + pd.Timedelta(days=1)
rfm = df.groupby('CustomerID').agg({
    'InvoiceDate': lambda x: (snapshot_date - x.max()).days,
    'InvoiceNo': 'nunique',
    'TotalPrice': 'sum'
}).rename(columns={'InvoiceDate':'Recency','InvoiceNo':'Frequency','TotalPrice':'Monetary'})
print(rfm.describe())
```

**Python 结果：**

**输出：**
```
        Recency  Frequency     Monetary
count 2493.0000  2493.0000    2493.0000
mean    88.2230     7.2736   51561.7771
std    114.7396     6.0624  101716.2341
min      1.0000     1.0000      50.1100
25%     11.0000     2.0000   10082.1500
50%     40.0000     5.0000   26139.8000
75%    114.0000    11.0000   55046.2500
max    530.0000    37.0000 1472994.1200
```

## 4.2 数据标准化

RFM 三个指标量纲差异大，需标准化后才能聚类。

**Python 代码：**

```python
scaler = StandardScaler()
rfm_scaled = scaler.fit_transform(rfm[['Recency','Frequency','Monetary']])
rfm_scaled = pd.DataFrame(rfm_scaled, columns=['Recency','Frequency','Monetary'], index=rfm.index)
print(rfm_scaled.describe())
```

**Python 结果：**

**输出：**
```
        Recency  Frequency  Monetary
count 2493.0000  2493.0000 2493.0000
mean    -0.0000    -0.0000    0.0000
std      1.0002     1.0002    1.0002
min     -0.7603    -1.0350   -0.5065
25%     -0.6732    -0.8701   -0.4079
50%     -0.4204    -0.3751   -0.2500
75%      0.2247     0.6148    0.0343
max      3.8510     4.9044   13.9773
```

**解释：** 标准化后每个维度的均值为 0、标准差为 1，消除量纲影响。K-Means 和 DBSCAN 都基于距离，不标准化会导致某个量纲大的字段主导聚类结果。

## 4.3 确定最优聚类数 K

用肘部法则（Elbow Method）和轮廓系数（Silhouette Score）确定 K-Means 的最优 K 值。

**Python 代码：**

```python
inertias, silhouettes = [], []
K_range = range(2, 11)
for k in K_range:
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(rfm_scaled)
    inertias.append(km.inertia_)
    silhouettes.append(silhouette_score(rfm_scaled, labels))
print(pd.DataFrame({'K': list(K_range), 'Inertia': inertias, 'Silhouette': silhouettes}))
```

**Python 结果：**

**输出：**
```
 K   Inertia  Silhouette
 2 4896.5471      0.4227
 3 3256.1363      0.4718
 4 1958.3155      0.4852
 5 1569.6070      0.4149
 6 1254.2343      0.4292
 7  980.3551      0.4329
 8  848.0934      0.3925
 9  770.8072      0.3728
10  703.7357      0.3754
```

![Elbow Method & Silhouette Score | 肘部法则与轮廓系数](F:\code\dsh-datascience-demo\src\data\L2\images_diagnostic/4_3_elbow_silhouette.png)

**中文说明：** 左图 = 肘部法则（Elbow Method），纵轴为簇内平方和（Inertia）；右图 = 轮廓系数（Silhouette Score）。

**解释：** 肘部法则寻找 Inertia 下降明显变缓的拐点；轮廓系数越接近 1 说明聚类效果越好。综合两图选择最优 K 值。

## 4.4 K-Means 聚类

**Python 代码：**

```python
best_k = 4
kmeans = KMeans(n_clusters=best_k, random_state=42, n_init=10)
rfm['Cluster'] = kmeans.fit_predict(rfm_scaled)

sil = silhouette_score(rfm_scaled, rfm['Cluster'])
ch  = calinski_harabasz_score(rfm_scaled, rfm['Cluster'])
db  = davies_bouldin_score(rfm_scaled, rfm['Cluster'])
print('Silhouette: %.4f, Calinski-Harabasz: %.2f, Davies-Bouldin: %.4f' % (sil, ch, db))
print(rfm.groupby('Cluster')[['Recency','Frequency','Monetary']].mean())
```

**Python 结果：**

**输出：**
```
Silhouette = 0.4852
Calinski-Harabasz = 2338.92
Davies-Bouldin = 0.6719

         Recency  Frequency    Monetary
Cluster                                
0        46.9318    11.3636 664352.2741
1       308.5433     1.9832  12402.6521
2        20.3019    15.7028  92409.9542
3        54.8382     4.8826  25325.5377
```

**解释：** **轮廓系数**越接近 1 越好（> 0.5 表示结构清晰）；**Calinski-Harabasz** 越大越好；**Davies-Bouldin** 越小越好。聚类结果可用业务语言解读：Recency 低 + Frequency 高 + Monetary 高 → 高价值活跃客户；Recency 高 + Frequency 低 + Monetary 低 → 流失客户。

## 4.5 DBSCAN 聚类对比

DBSCAN 基于密度，不需预先指定簇数，能发现任意形状的簇并识别噪声点。

**Python 代码：**

```python
dbscan = DBSCAN(eps=0.5, min_samples=5)
rfm['DBSCAN_Cluster'] = dbscan.fit_predict(rfm_scaled)
n_clusters = len(set(rfm['DBSCAN_Cluster'])) - (1 if -1 in rfm['DBSCAN_Cluster'].values else 0)
n_noise = list(rfm['DBSCAN_Cluster']).count(-1)
print('DBSCAN 簇数: %d, 噪声点: %d' % (n_clusters, n_noise))
```

**Python 结果：**

**输出：**
```
DBSCAN 簇数: 3, 噪声点: 66
```

**解释：** DBSCAN 不需要预设 K 值，适合发现非球形簇。噪声点（标签 -1）通常是行为异常的客户，可作为风控或特殊营销的目标。与 K-Means 对比，DBSCAN 对参数 eps 和 min_samples 更敏感。

## 4.6 聚类可视化（PCA 降维）

用 PCA 将三维 RFM 降到二维，直观展示聚类结果。

**Python 代码：**

```python
pca = PCA(n_components=2)
rfm_pca = pca.fit_transform(rfm_scaled)
plt.scatter(rfm_pca[:,0], rfm_pca[:,1], c=rfm['Cluster'], cmap='Set2', alpha=0.6)
```

![K-Means Clusters (PCA 2D) | K-Means 聚类的 PCA 二维投影](F:\code\dsh-datascience-demo\src\data\L2\images_diagnostic/4_5_pca_clusters.png)

**中文说明：** 横轴 = 第一主成分（PC1）；纵轴 = 第二主成分（PC2）；颜色 = 聚类标签（Cluster）。括号内为各主成分解释的方差比例。

**解释：** PCA 将 3 维 RFM 降到 2 维，在保留最大方差的前提下可视化聚类结构。若各色簇在图上明显分离，说明聚类有效；若重叠严重，需调整 K 值或更换算法。
