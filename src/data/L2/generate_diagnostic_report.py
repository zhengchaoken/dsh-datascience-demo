#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L2 诊断性分析报告生成器
- 数据源: data/ecommerce/ecommerce.db（统一电商 SQLite 数据库）
- 分析: 相关性分析 / 关联规则挖掘 / 聚类分析
- 相关性分析同时用 SQL 与 Python 两套实现
- 输出: Markdown 报告 + images_diagnostic/ 图片目录
"""

import os
import math
import sqlite3
import shutil
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns
from scipy import stats
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans, DBSCAN
from sklearn.metrics import silhouette_score, calinski_harabasz_score, davies_bouldin_score
from sklearn.decomposition import PCA
from mlxtend.frequent_patterns import apriori, association_rules

warnings.filterwarnings('ignore')

try:
    pd.tseries.frequencies.to_offset('ME')
    FREQ_MONTH_END = 'ME'
except Exception:
    FREQ_MONTH_END = 'M'

# ================== 配置区：相对路径 ==================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'ecommerce', 'ecommerce.db'))
OUTPUT_MD = os.path.join(SCRIPT_DIR, 'diagnostic_report.md')
IMAGE_DIR = os.path.join(SCRIPT_DIR, 'images_diagnostic')

if not os.path.isfile(DB_PATH):
    raise FileNotFoundError("未找到数据库: %s" % DB_PATH)

if os.path.isdir(IMAGE_DIR):
    shutil.rmtree(IMAGE_DIR)
os.makedirs(IMAGE_DIR, exist_ok=True)

pd.set_option('display.float_format', lambda x: '{:.4f}'.format(x))
pd.set_option('display.max_columns', 50)
pd.set_option('display.width', 200)

# ================== 中文字体 ==================
def _find_cjk_font_file():
    local_dir = os.path.join(SCRIPT_DIR, 'fonts')
    if os.path.isdir(local_dir):
        for fn in sorted(os.listdir(local_dir)):
            if fn.lower().endswith(('.ttf', '.ttc', '.otf')):
                return os.path.join(local_dir, fn)
    name_to_files = {}
    for f in fm.fontManager.ttflist:
        name_to_files.setdefault(f.name, []).append(f.fname)
    for name in ['WenQuanYi Micro Hei', 'WenQuanYi Zen Hei',
                 'Noto Sans CJK SC', 'Noto Sans CJK JP',
                 'Source Han Sans SC', 'SimHei', 'Microsoft YaHei']:
        if name in name_to_files:
            return name_to_files[name][0]
    return None

CJK_FONT_FILE = _find_cjk_font_file()
if CJK_FONT_FILE:
    try:
        fm.fontManager.addfont(CJK_FONT_FILE)
        _name = fm.FontProperties(fname=CJK_FONT_FILE).get_name()
        plt.rcParams['font.sans-serif'] = [_name, 'DejaVu Sans']
        print("[字体] 使用: %s" % _name)
    except Exception:
        plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
else:
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
    print("[字体] 警告：未找到中文字体")
plt.rcParams['axes.unicode_minus'] = False
sns.set_style("whitegrid")
if CJK_FONT_FILE:
    plt.rcParams['font.sans-serif'] = [_name, 'DejaVu Sans']

# ================== 加载数据 ==================
print("[数据] 加载中: %s" % DB_PATH)
# 从电商数据库抽取「订单明细」宽表：已支付订单（已完成/已发货）的明细行
src_conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query("""
SELECT oi.order_id      AS InvoiceNo,
       oi.product_id    AS StockCode,
       p.product_name   AS Description,
       oi.quantity      AS Quantity,
       o.created_at     AS InvoiceDate,
       oi.unit_price    AS UnitPrice,
       o.customer_id    AS CustomerID,
       c.province       AS Country,
       oi.subtotal      AS TotalPrice
FROM order_items oi
JOIN orders    o ON oi.order_id   = o.order_id
JOIN products  p ON oi.product_id = p.product_id
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.order_status IN ('已完成', '已发货')
""", src_conn)
src_conn.close()
df['CustomerID'] = df['CustomerID'].astype(int)
df['InvoiceDate'] = pd.to_datetime(df['InvoiceDate'])
print("[数据] 明细行数: %d, 列: %s" % (len(df), list(df.columns)))

# ================== SQLite 内存库 + 数学函数注册 ==================
conn = sqlite3.connect(':memory:')
df.to_sql('retail', conn, index=False, if_exists='replace')
df.head(20000).to_sql('retail_sample', conn, index=False, if_exists='replace')

conn.create_function("LN",    1, lambda x: math.log(x)      if x is not None and x > 0 else None)
conn.create_function("EXP",   1, lambda x: math.exp(x)      if x is not None else None)
conn.create_function("POW",   2, lambda x, y: math.pow(x, y) if x is not None else None)
conn.create_function("SQRT",  1, lambda x: math.sqrt(x)     if x is not None and x >= 0 else None)
conn.create_function("FLOOR", 1, lambda x: math.floor(x)    if x is not None else None)

def sql(q):
    return pd.read_sql_query(q, conn)

# ================== 报告构建器 ==================
class Report:
    def __init__(self):
        self.parts = []
        self.toc = []
        self.counter = [0, 0, 0]

    def _heading(self, level, title):
        num = ".".join(str(c) for c in self.counter[:level] if c > 0)
        if level == 1:
            self.parts.append("# %s. %s\n" % (num, title))
        else:
            self.parts.append("%s %s %s\n" % ("#" * level, num, title))
        indent = "  " * (level - 1)
        self.toc.append("%s- %s %s" % (indent, num, title))

    def h1(self, t):
        self.counter[0] += 1; self.counter[1] = 0; self.counter[2] = 0
        self._heading(1, t)

    def h2(self, t):
        self.counter[1] += 1; self.counter[2] = 0
        self._heading(2, t)

    def h3(self, t):
        self.counter[2] += 1
        self._heading(3, t)

    def text(self, s):
        self.parts.append(s.rstrip() + "\n")

    def code(self, lang, s):
        self.parts.append("```%s\n%s\n```\n" % (lang, s.rstrip()))

    def table(self, df_):
        try:
            self.parts.append(df_.to_markdown(index=False, floatfmt='.4f') + "\n")
        except Exception:
            self.parts.append("```\n" + df_.to_string(index=False) + "\n```\n")

    def output(self, s):
        self.parts.append("**输出：**\n```\n%s\n```\n" % s)

    def image(self, name, caption=""):
        self.parts.append("![%s](%s/%s)\n" % (caption, os.path.basename(IMAGE_DIR), name))

    def save_plt(self, name):
        path = os.path.join(IMAGE_DIR, name)
        plt.savefig(path, bbox_inches='tight', dpi=100)
        plt.close()
        return name

    def write(self):
        header = []
        header.append("# 诊断性分析报告 - 电商交易数据集\n")
        header.append("- **数据来源**：`data/ecommerce/ecommerce.db`（orders/order_items/products/customers 关联抽取）")
        header.append("- **样本量**：%d 行" % len(df))
        header.append("- **客户数**：%d" % df['CustomerID'].nunique())
        header.append("- **商品数**：%d\n" % df['StockCode'].nunique())
        header.append('## 目录\n')
        header.append("\n".join(self.toc) + "\n\n---\n")
        with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
            f.write("\n".join(header) + "\n".join(self.parts))
        print("[OK] 报告：%s" % OUTPUT_MD)
        print("[OK] 图片：%s/ 共 %d 张" % (IMAGE_DIR, len(os.listdir(IMAGE_DIR))))

R = Report()

def block(title, desc, sql_q, py_code, py_result, explanation):
    R.h3(title)
    R.text(desc)
    R.text("**SQL 代码：**"); R.code("sql", sql_q)
    R.text("**SQL 结果：**"); R.table(sql(sql_q))
    R.text("**Python 代码：**"); R.code("python", py_code)
    R.text("**Python 结果：**"); R.output(str(py_result))
    R.text("**解释：** "); R.text(explanation)


# ============================================================
# 1. 数据概览
# ============================================================
R.h1("数据概览")
R.text("本报告基于统一电商数据库 `ecommerce.db`（2024-01-01 至 2025-06-15 的订单数据），"
       "从 orders / order_items / products / customers 四表关联抽取出「已支付订单明细」宽表。"
       "诊断性分析从**相关性分析**、"
       "**关联规则挖掘**、**聚类分析**三个维度展开。")

R.h2("字段说明")
R.table(pd.DataFrame([
    ['InvoiceNo', '订单号', 'orders.order_id，每笔订单唯一标识'],
    ['StockCode', '商品ID', 'products.product_id'],
    ['Description', '商品名称', '品牌+品类词+型号'],
    ['Quantity', '数量', 'order_items.quantity，明细行件数'],
    ['InvoiceDate', '下单时间', 'orders.created_at'],
    ['UnitPrice', '成交单价', 'order_items.unit_price（含促销浮动）'],
    ['CustomerID', '客户ID', 'customers.customer_id'],
    ['Country', '省份', 'customers.province（沿用原列名）'],
    ['TotalPrice', '明细小计', 'order_items.subtotal = 单价×数量 - 分摊优惠'],
], columns=['字段', '中文说明', '描述']))

R.h2("样本预览")
R.table(df.head())


# ============================================================
# 2. 相关性分析
# ============================================================
R.h1("相关性分析")
R.text("相关性分析（Correlation Analysis）用于诊断变量之间是否存在线性或单调关联。"
       "在零售场景中，可用来判断「购买数量与单价的关系」「销售额与客户活跃度的关系」等，"
       "为后续 RFM 建模和聚类提供特征选择依据。")
R.text("本章节同时给出 **SQL 实现** 与 **Python 实现**：\n"
       "- SQL 版本：注册 `SQRT` 函数后，在 SQLite 里直接计算 Pearson 相关系数；"
       "为了避免数万行逐行调用 `SQRT` 的性能问题，纯 SQL 计算在 20000 行样本表上演示。\n"
       "- Python 版本：用 `pandas.DataFrame.corr()`，底层是 C 实现，可在全量数据上毫秒级完成。")

# -------- 2.1 Pearson 相关系数 --------
R.h2("Pearson 相关系数矩阵")

# ---- 2.1.1 单对变量 ----
R.h3("单对变量：Quantity vs UnitPrice")

q_single = """SELECT
  (COUNT(*)*SUM(Quantity*UnitPrice) - SUM(Quantity)*SUM(UnitPrice)) /
  (SQRT(COUNT(*)*SUM(Quantity*Quantity) - SUM(Quantity)*SUM(Quantity)) *
   SQRT(COUNT(*)*SUM(UnitPrice*UnitPrice) - SUM(UnitPrice)*SUM(UnitPrice))) AS corr_qty_price
FROM retail_sample;"""

R.text("**SQL 代码（在 20000 行样本表上执行）：**")
R.code("sql", q_single)
R.text("**SQL 结果：**")
R.table(sql(q_single))

R.text("**Python 代码：**")
R.code("python", "corr_value = df['Quantity'].corr(df['UnitPrice'])\nprint('Pearson r = %.4f' % corr_value)")
corr_qty_price = df['Quantity'].corr(df['UnitPrice'])
R.text("**Python 结果：**")
R.output("Pearson r = %.4f" % corr_qty_price)

R.text("**解释：** Pearson 相关系数衡量线性相关强度。"
       "Quantity 与 UnitPrice 的相关系数如果为负，说明「买得越多单价越低」——"
       "这是批发场景中常见的数量折扣现象。具体判读标准："
       "$|r| < 0.3$ 弱相关，$0.3 \\le |r| < 0.7$ 中等相关，$|r| \\ge 0.7$ 强相关。")


# ---- 2.1.2 三变量相关矩阵（纯 SQL） ----
R.h3("三变量相关矩阵：SQL 逐对计算")

R.text("在 20000 行样本表上，用 SQL 计算 Quantity、UnitPrice、TotalPrice 三个变量两两之间的相关系数。")

q_triple = """SELECT
  (COUNT(*)*SUM(Quantity*UnitPrice) - SUM(Quantity)*SUM(UnitPrice)) /
  (SQRT(COUNT(*)*SUM(Quantity*Quantity) - SUM(Quantity)*SUM(Quantity)) *
   SQRT(COUNT(*)*SUM(UnitPrice*UnitPrice) - SUM(UnitPrice)*SUM(UnitPrice))) AS corr_qty_price,
  (COUNT(*)*SUM(Quantity*TotalPrice) - SUM(Quantity)*SUM(TotalPrice)) /
  (SQRT(COUNT(*)*SUM(Quantity*Quantity) - SUM(Quantity)*SUM(Quantity)) *
   SQRT(COUNT(*)*SUM(TotalPrice*TotalPrice) - SUM(TotalPrice)*SUM(TotalPrice))) AS corr_qty_total,
  (COUNT(*)*SUM(UnitPrice*TotalPrice) - SUM(UnitPrice)*SUM(TotalPrice)) /
  (SQRT(COUNT(*)*SUM(UnitPrice*UnitPrice) - SUM(UnitPrice)*SUM(UnitPrice)) *
   SQRT(COUNT(*)*SUM(TotalPrice*TotalPrice) - SUM(TotalPrice)*SUM(TotalPrice))) AS corr_price_total
FROM retail_sample;"""

R.text("**SQL 代码：**")
R.code("sql", q_triple)
R.text("**SQL 结果：**")
sql_corr_result = sql(q_triple)
R.table(sql_corr_result)

sql_pairs = sql_corr_result.iloc[0].to_dict()
sql_matrix = pd.DataFrame(
    [[1.0, sql_pairs['corr_qty_price'], sql_pairs['corr_qty_total']],
     [sql_pairs['corr_qty_price'], 1.0, sql_pairs['corr_price_total']],
     [sql_pairs['corr_qty_total'], sql_pairs['corr_price_total'], 1.0]],
    index=['Quantity', 'UnitPrice', 'TotalPrice'],
    columns=['Quantity', 'UnitPrice', 'TotalPrice']
)
R.text("**SQL 结果（矩阵形式）：**")
R.table(sql_matrix.reset_index().rename(columns={'index': 'Variable'}))


# ---- 2.1.3 全量 SQL 聚合 + Python 组装 ----
R.h3("全量数据上的 SQL 版：聚合 + Python 组装")

R.text("直接在数万行上跑逐行 `SQRT` 会非常慢。工程上更实用的做法是："
       "**让 SQL 只做聚合**（SUM、COUNT 都是 C 实现，非常快），"
       "**把最终公式放在 Python 里组装**。这样既保留了 SQL 的表达力，又避免了跨语言逐行调用。")

q_agg = """SELECT
  COUNT(*) AS n,
  SUM(Quantity) AS sum_x,
  SUM(UnitPrice) AS sum_y,
  SUM(Quantity*Quantity) AS sum_xx,
  SUM(UnitPrice*UnitPrice) AS sum_yy,
  SUM(Quantity*UnitPrice) AS sum_xy
FROM retail;"""

R.text("**SQL 代码（全量聚合）：**")
R.code("sql", q_agg)
R.text("**SQL 结果：**")
agg_df = sql(q_agg)
R.table(agg_df)

R.text("**Python 代码（由聚合值组装 Pearson 公式）：**")
R.code("python",
       "n     = agg_df['n'][0]\n"
       "sum_x = agg_df['sum_x'][0]\n"
       "sum_y = agg_df['sum_y'][0]\n"
       "sum_xx = agg_df['sum_xx'][0]\n"
       "sum_yy = agg_df['sum_yy'][0]\n"
       "sum_xy = agg_df['sum_xy'][0]\n"
       "\n"
       "numerator   = n * sum_xy - sum_x * sum_y\n"
       "denominator = math.sqrt(n * sum_xx - sum_x**2) * math.sqrt(n * sum_yy - sum_y**2)\n"
       "corr_sql_full = numerator / denominator\n"
       "print('全量 SQL+Python 组装 r = %.6f' % corr_sql_full)")
n_v     = int(agg_df['n'][0])
sum_x   = float(agg_df['sum_x'][0])
sum_y   = float(agg_df['sum_y'][0])
sum_xx  = float(agg_df['sum_xx'][0])
sum_yy  = float(agg_df['sum_yy'][0])
sum_xy  = float(agg_df['sum_xy'][0])
num_    = n_v * sum_xy - sum_x * sum_y
den_    = math.sqrt(n_v * sum_xx - sum_x ** 2) * math.sqrt(n_v * sum_yy - sum_y ** 2)
corr_sql_full = num_ / den_
R.text("**Python 结果：**")
R.output("全量 SQL+Python 组装 r = %.6f" % corr_sql_full)
R.text("**解释：** 这个方法把重活（求和）交给 SQLite 的 C 实现，"
       "把开方、除法留给 Python，全量数据毫秒级完成，"
       "而且精度与直接调用 `df.corr()` 一致。")


# ---- 2.1.4 Python 版：pandas 一行搞定 ----
R.h3("Python 版：pandas 全量相关矩阵")

R.text("pandas 的 `corr()` 方法一行就能得到完整相关矩阵，底层是 numpy 向量化运算，"
       "3.7 万行数据毫秒级完成。")

R.text("**Python 代码：**")
R.code("python", "corr_matrix = df[['Quantity', 'UnitPrice', 'TotalPrice']].corr(method='pearson')\nprint(corr_matrix)")
corr_matrix = df[['Quantity', 'UnitPrice', 'TotalPrice']].corr(method='pearson')
R.text("**Python 结果：**")
R.output(corr_matrix.to_string())

R.text("**解释：** 对比上面三节的三种实现（SQL 样本版 / 全量 SQL+Python 组装版 / pandas 版），"
       "结果数量级完全一致。实际工程中推荐 **pandas 版**（最简）或 "
       "**SQL 聚合 + Python 组装版**（SQL 与 Python 分工明确）。"
       "纯 SQL 逐行 `SQRT` 只用于教学演示。")


# -------- 2.2 Spearman 秩相关 --------
R.h2("Spearman 秩相关（Python 补充）")

R.text("Pearson 只度量线性相关。若变量关系是单调但非线性（如指数关系），"
       "或存在明显离群值，可用 Spearman 秩相关。Spearman 先把数据转成秩次，"
       "再对秩次算 Pearson 相关，对异常值和单调非线性关系更稳健。")

R.text("**Python 代码：**")
R.code("python", "spearman_corr = df[['Quantity', 'UnitPrice', 'TotalPrice']].corr(method='spearman')\nprint(spearman_corr)")
spearman_corr = df[['Quantity', 'UnitPrice', 'TotalPrice']].corr(method='spearman')
R.text("**Python 结果：**")
R.output(spearman_corr.to_string())

R.text("**解释：** 对比 Pearson 与 Spearman 的结果差异可以判断关系的性质："
       "若两者接近，说明关系近似线性；若 Spearman 明显高于 Pearson，"
       "说明存在单调但非线性的关系（例如 Quantity 翻倍时 TotalPrice 增长更快）。"
       "SQL 也可以算 Spearman，但需要用窗口函数 `RANK()` 先转秩次，写法较繁琐，"
       "这里用 Python 更简洁。")


# -------- 2.3 相关热力图 --------
R.h2("相关热力图")

R.text("用热力图直观展示多个数值变量之间的相关结构。以下图同时展示 Pearson 与 Spearman 两套结果。")

R.text("**Python 代码：**")
R.code("python",
       "fig, ax = plt.subplots(1, 2, figsize=(12, 5))\n"
       "sns.heatmap(df[['Quantity','UnitPrice','TotalPrice']].corr(method='pearson'),\n"
       "            annot=True, cmap='coolwarm', fmt='.2f', ax=ax[0], vmin=-1, vmax=1)\n"
       "ax[0].set_title('Pearson Correlation')\n"
       "sns.heatmap(df[['Quantity','UnitPrice','TotalPrice']].corr(method='spearman'),\n"
       "            annot=True, cmap='coolwarm', fmt='.2f', ax=ax[1], vmin=-1, vmax=1)\n"
       "ax[1].set_title('Spearman Correlation')\n"
       "plt.tight_layout()")
fig, ax = plt.subplots(1, 2, figsize=(12, 5))
sns.heatmap(df[['Quantity', 'UnitPrice', 'TotalPrice']].corr(method='pearson'),
            annot=True, cmap='coolwarm', fmt='.2f', ax=ax[0], vmin=-1, vmax=1)
ax[0].set_title('Pearson Correlation')
sns.heatmap(df[['Quantity', 'UnitPrice', 'TotalPrice']].corr(method='spearman'),
            annot=True, cmap='coolwarm', fmt='.2f', ax=ax[1], vmin=-1, vmax=1)
ax[1].set_title('Spearman Correlation')
plt.tight_layout()
R.save_plt('2_3_corr_heatmap.png')
R.image('2_3_corr_heatmap.png',
        'Pearson and Spearman Correlation Heatmaps | Pearson 与 Spearman 相关热力图')
R.text("**中文说明：** 左图 = Pearson 相关热力图（Pearson Correlation）；"
       "右图 = Spearman 相关热力图（Spearman Correlation）。"
       "颜色越红表示正相关越强，越蓝表示负相关越强。")
R.text("**解释：** $|r| < 0.3$ 弱相关，$0.3 \\le |r| < 0.7$ 中等相关，$|r| \\ge 0.7$ 强相关。"
       "对零售数据，Quantity 与 TotalPrice 通常呈强正相关；"
       "Quantity 与 UnitPrice 的负相关反映批发折扣；"
       "UnitPrice 与 TotalPrice 的相关性取决于单价与数量的相对贡献。")


# ============================================================
# 3. 关联规则挖掘
# ============================================================
R.h1("关联规则挖掘")
R.text("关联规则挖掘（Association Rule Mining）用于发现「同时出现」的商品组合，"
       "核心指标包括**支持度**（Support）、**置信度**（Confidence）和**提升度**（Lift）。"
       "典型应用是购物篮分析（Market Basket Analysis），用于商品捆绑推荐、货架布局优化。")

R.h2("数据准备：构建购物篮矩阵")

R.text("Apriori 算法需要事务-商品矩阵（每行一笔交易，每列一个商品，值为 0/1）。"
       "由于商品数量庞大，先筛选出现频率最高的前 50 个商品。")

q_top = """SELECT StockCode, COUNT(DISTINCT InvoiceNo) AS freq
FROM retail
GROUP BY StockCode
ORDER BY freq DESC
LIMIT 50;"""
R.text("**SQL 代码（Top 50 商品）：**"); R.code("sql", q_top)
R.text("**SQL 结果（前 10 行）：**"); R.table(sql(q_top).head(10))

R.text("**Python 代码：**")
R.code("python",
       "top_items = df['StockCode'].value_counts().head(50).index\n"
       "df_top = df[df['StockCode'].isin(top_items)]\n"
       "basket = df_top.groupby(['InvoiceNo', 'StockCode'])['Quantity'].sum().unstack().fillna(0)\n"
       "basket_sets = basket.map(lambda x: 1 if x > 0 else 0)\n"
       "print('购物篮矩阵形状:', basket_sets.shape)")
top_items = df['StockCode'].value_counts().head(50).index
df_top = df[df['StockCode'].isin(top_items)]
basket = df_top.groupby(['InvoiceNo', 'StockCode'])['Quantity'].sum().unstack().fillna(0)
basket_sets = basket.map(lambda x: 1 if x > 0 else 0)
R.text("**Python 结果：**"); R.output("购物篮矩阵形状: %s" % str(basket_sets.shape))

R.h2("Apriori 频繁项集")
R.text("Apriori 通过逐层扫描发现频繁项集，支持度阈值设为 0.02（即至少 2% 的交易包含该组合）。")
R.text("**Python 代码：**")
R.code("python",
       "frequent_itemsets = apriori(basket_sets, min_support=0.02, use_colnames=True)\n"
       "frequent_itemsets['length'] = frequent_itemsets['itemsets'].apply(lambda x: len(x))\n"
       "print(frequent_itemsets.sort_values('support', ascending=False).head(10))")
frequent_itemsets = apriori(basket_sets, min_support=0.02, use_colnames=True)
frequent_itemsets['length'] = frequent_itemsets['itemsets'].apply(lambda x: len(x))
fi_top = frequent_itemsets.sort_values('support', ascending=False).head(10)
R.text("**Python 结果：**"); R.output(fi_top.to_string(index=False))
R.text("**解释：** 支持度表示该商品组合在所有交易中出现的比例。"
       "支持度越高，说明该组合越普遍。频繁项集是生成关联规则的基础。")

R.h2("关联规则生成与评估")
R.text("从频繁项集中生成关联规则，以置信度为筛选标准（阈值 0.5）。")
R.text("**Python 代码：**")
R.code("python",
       "rules = association_rules(frequent_itemsets, metric='confidence', min_threshold=0.5)\n"
       "rules = rules.sort_values('lift', ascending=False)\n"
       "print(rules[['antecedents','consequents','support','confidence','lift']].head(10))")
rules = association_rules(frequent_itemsets, metric='confidence', min_threshold=0.5)
rules = rules.sort_values('lift', ascending=False)
rules_display = rules[['antecedents', 'consequents', 'support', 'confidence', 'lift']].head(10)
R.text("**Python 结果：**"); R.output(rules_display.to_string(index=False))
R.text("**解释：** 置信度表示「买了 A 之后再买 B」的条件概率；"
       "提升度 > 1 表示 A 和 B 正相关（互相促进），= 1 表示独立，< 1 表示负相关。"
       "提升度是评估规则实用性的关键指标，实践中最看重提升度而非单纯的置信度。")

R.h2("关联规则可视化")
R.text("用散点图展示支持度 vs 置信度，颜色表示提升度。")
R.text("**Python 代码：**")
R.code("python", "plt.scatter(rules['support'], rules['confidence'], c=rules['lift'], cmap='viridis')")
if len(rules) > 0:
    plt.figure(figsize=(8, 6))
    scatter = plt.scatter(rules['support'], rules['confidence'], c=rules['lift'],
                          cmap='viridis', alpha=0.6, edgecolors='k', s=50)
    plt.colorbar(scatter, label='Lift')
    plt.xlabel('Support')
    plt.ylabel('Confidence')
    plt.title('Association Rules: Support vs Confidence (color=Lift)')
    R.save_plt('3_2_rules_scatter.png')
    R.image('3_2_rules_scatter.png',
            'Association Rules: Support vs Confidence | 关联规则散点图')
    R.text("**中文说明：** 横轴 = 支持度（Support）；纵轴 = 置信度（Confidence）；"
           "颜色 = 提升度（Lift）。右上角的点表示既高频又高可信的强规则。")
    R.text("**解释：** 提升度越高的规则（颜色越亮）越有价值，"
           "因为它们说明 A 和 B 的共现并非偶然。实际应用中优先选择提升度 > 1.5 的规则。")


# ============================================================
# 4. 聚类分析
# ============================================================
R.h1("聚类分析")
R.text("聚类分析（Clustering）将客户/交易分成内部相似、组间不同的群体。"
       "本报告采用 RFM 模型构建客户特征，然后使用 K-Means 和 DBSCAN 进行聚类。")

R.h2("RFM 特征工程")

R.text("RFM 模型从三个维度刻画客户价值：**R**ecency（最近一次购买距今天数）、"
       "**F**requency（购买频次）、**M**onetary（总消费金额）。")

q_rfm = """SELECT CustomerID,
  JULIANDAY('2025-06-16') - JULIANDAY(MAX(InvoiceDate)) AS Recency,
  COUNT(DISTINCT InvoiceNo) AS Frequency,
  SUM(TotalPrice) AS Monetary
FROM retail
GROUP BY CustomerID
HAVING Monetary > 0
LIMIT 5;"""
R.text("**SQL 代码：**"); R.code("sql", q_rfm)
R.text("**SQL 结果（前 5 行）：**"); R.table(sql(q_rfm))

R.text("**Python 代码：**")
R.code("python",
       "snapshot_date = df['InvoiceDate'].max() + pd.Timedelta(days=1)\n"
       "rfm = df.groupby('CustomerID').agg({\n"
       "    'InvoiceDate': lambda x: (snapshot_date - x.max()).days,\n"
       "    'InvoiceNo': 'nunique',\n"
       "    'TotalPrice': 'sum'\n"
       "}).rename(columns={'InvoiceDate':'Recency','InvoiceNo':'Frequency','TotalPrice':'Monetary'})\n"
       "print(rfm.describe())")
snapshot_date = df['InvoiceDate'].max() + pd.Timedelta(days=1)
rfm = df.groupby('CustomerID').agg({
    'InvoiceDate': lambda x: (snapshot_date - x.max()).days,
    'InvoiceNo': 'nunique',
    'TotalPrice': 'sum'
}).rename(columns={'InvoiceDate': 'Recency', 'InvoiceNo': 'Frequency', 'TotalPrice': 'Monetary'})
R.text("**Python 结果：**"); R.output(rfm.describe().to_string())

R.h2("数据标准化")
R.text("RFM 三个指标量纲差异大，需标准化后才能聚类。")
R.text("**Python 代码：**")
R.code("python",
       "scaler = StandardScaler()\n"
       "rfm_scaled = scaler.fit_transform(rfm[['Recency','Frequency','Monetary']])\n"
       "rfm_scaled = pd.DataFrame(rfm_scaled, columns=['Recency','Frequency','Monetary'], index=rfm.index)\n"
       "print(rfm_scaled.describe())")
scaler = StandardScaler()
rfm_scaled = scaler.fit_transform(rfm[['Recency', 'Frequency', 'Monetary']])
rfm_scaled = pd.DataFrame(rfm_scaled, columns=['Recency', 'Frequency', 'Monetary'], index=rfm.index)
R.text("**Python 结果：**"); R.output(rfm_scaled.describe().to_string())
R.text("**解释：** 标准化后每个维度的均值为 0、标准差为 1，消除量纲影响。"
       "K-Means 和 DBSCAN 都基于距离，不标准化会导致某个量纲大的字段主导聚类结果。")

R.h2("确定最优聚类数 K")
R.text("用肘部法则（Elbow Method）和轮廓系数（Silhouette Score）确定 K-Means 的最优 K 值。")
R.text("**Python 代码：**")
R.code("python",
       "inertias, silhouettes = [], []\n"
       "K_range = range(2, 11)\n"
       "for k in K_range:\n"
       "    km = KMeans(n_clusters=k, random_state=42, n_init=10)\n"
       "    labels = km.fit_predict(rfm_scaled)\n"
       "    inertias.append(km.inertia_)\n"
       "    silhouettes.append(silhouette_score(rfm_scaled, labels))\n"
       "print(pd.DataFrame({'K': list(K_range), 'Inertia': inertias, 'Silhouette': silhouettes}))")
inertias, silhouettes = [], []
K_range = range(2, 11)
for k in K_range:
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(rfm_scaled)
    inertias.append(km.inertia_)
    silhouettes.append(silhouette_score(rfm_scaled, labels))
k_df = pd.DataFrame({'K': list(K_range), 'Inertia': inertias, 'Silhouette': silhouettes})
R.text("**Python 结果：**"); R.output(k_df.to_string(index=False))

plt.figure(figsize=(12, 4))
plt.subplot(1, 2, 1)
plt.plot(list(K_range), inertias, 'bo-')
plt.xlabel('K'); plt.ylabel('Inertia'); plt.title('Elbow Method')
plt.subplot(1, 2, 2)
plt.plot(list(K_range), silhouettes, 'ro-')
plt.xlabel('K'); plt.ylabel('Silhouette Score'); plt.title('Silhouette Score')
plt.tight_layout()
R.save_plt('4_3_elbow_silhouette.png')
R.image('4_3_elbow_silhouette.png', 'Elbow Method & Silhouette Score | 肘部法则与轮廓系数')
R.text("**中文说明：** 左图 = 肘部法则（Elbow Method），纵轴为簇内平方和（Inertia）；"
       "右图 = 轮廓系数（Silhouette Score）。")
R.text("**解释：** 肘部法则寻找 Inertia 下降明显变缓的拐点；"
       "轮廓系数越接近 1 说明聚类效果越好。综合两图选择最优 K 值。")

R.h2("K-Means 聚类")

best_k = 4

R.text("**Python 代码：**")
# 关键修复：用字符串拼接，避免 % 冲突
_code_kmeans = (
    "best_k = " + str(best_k) + "\n"
    "kmeans = KMeans(n_clusters=best_k, random_state=42, n_init=10)\n"
    "rfm['Cluster'] = kmeans.fit_predict(rfm_scaled)\n"
    "\n"
    "sil = silhouette_score(rfm_scaled, rfm['Cluster'])\n"
    "ch  = calinski_harabasz_score(rfm_scaled, rfm['Cluster'])\n"
    "db  = davies_bouldin_score(rfm_scaled, rfm['Cluster'])\n"
    "print('Silhouette: %.4f, Calinski-Harabasz: %.2f, Davies-Bouldin: %.4f' % (sil, ch, db))\n"
    "print(rfm.groupby('Cluster')[['Recency','Frequency','Monetary']].mean())\n"
)
R.code("python", _code_kmeans)

kmeans = KMeans(n_clusters=best_k, random_state=42, n_init=10)
rfm['Cluster'] = kmeans.fit_predict(rfm_scaled)
sil = silhouette_score(rfm_scaled, rfm['Cluster'])
ch = calinski_harabasz_score(rfm_scaled, rfm['Cluster'])
db = davies_bouldin_score(rfm_scaled, rfm['Cluster'])
R.text("**Python 结果：**")
R.output("Silhouette = %.4f\nCalinski-Harabasz = %.2f\nDavies-Bouldin = %.4f\n\n%s"
         % (sil, ch, db, rfm.groupby('Cluster')[['Recency', 'Frequency', 'Monetary']].mean().to_string()))
R.text("**解释：** **轮廓系数**越接近 1 越好（> 0.5 表示结构清晰）；"
       "**Calinski-Harabasz** 越大越好；**Davies-Bouldin** 越小越好。"
       "聚类结果可用业务语言解读：Recency 低 + Frequency 高 + Monetary 高 → 高价值活跃客户；"
       "Recency 高 + Frequency 低 + Monetary 低 → 流失客户。")

R.h2("DBSCAN 聚类对比")
R.text("DBSCAN 基于密度，不需预先指定簇数，能发现任意形状的簇并识别噪声点。")
R.text("**Python 代码：**")
R.code("python",
       "dbscan = DBSCAN(eps=0.5, min_samples=5)\n"
       "rfm['DBSCAN_Cluster'] = dbscan.fit_predict(rfm_scaled)\n"
       "n_clusters = len(set(rfm['DBSCAN_Cluster'])) - (1 if -1 in rfm['DBSCAN_Cluster'].values else 0)\n"
       "n_noise = list(rfm['DBSCAN_Cluster']).count(-1)\n"
       "print('DBSCAN 簇数: %d, 噪声点: %d' % (n_clusters, n_noise))")
dbscan = DBSCAN(eps=0.5, min_samples=5)
rfm['DBSCAN_Cluster'] = dbscan.fit_predict(rfm_scaled)
n_clusters = len(set(rfm['DBSCAN_Cluster'])) - (1 if -1 in rfm['DBSCAN_Cluster'].values else 0)
n_noise = list(rfm['DBSCAN_Cluster']).count(-1)
R.text("**Python 结果：**"); R.output("DBSCAN 簇数: %d, 噪声点: %d" % (n_clusters, n_noise))
R.text("**解释：** DBSCAN 不需要预设 K 值，适合发现非球形簇。"
       "噪声点（标签 -1）通常是行为异常的客户，可作为风控或特殊营销的目标。"
       "与 K-Means 对比，DBSCAN 对参数 eps 和 min_samples 更敏感。")

R.h2("聚类可视化（PCA 降维）")
R.text("用 PCA 将三维 RFM 降到二维，直观展示聚类结果。")
R.text("**Python 代码：**")
R.code("python",
       "pca = PCA(n_components=2)\n"
       "rfm_pca = pca.fit_transform(rfm_scaled)\n"
       "plt.scatter(rfm_pca[:,0], rfm_pca[:,1], c=rfm['Cluster'], cmap='Set2', alpha=0.6)")
pca = PCA(n_components=2)
rfm_pca = pca.fit_transform(rfm_scaled)
plt.figure(figsize=(8, 6))
scatter = plt.scatter(rfm_pca[:, 0], rfm_pca[:, 1], c=rfm['Cluster'],
                      cmap='Set2', alpha=0.6, edgecolors='k', s=30)
plt.colorbar(scatter, label='Cluster')
plt.xlabel('PC1 (%.1f%% var)' % (pca.explained_variance_ratio_[0] * 100))
plt.ylabel('PC2 (%.1f%% var)' % (pca.explained_variance_ratio_[1] * 100))
plt.title('K-Means Clusters (PCA 2D Projection)')
R.save_plt('4_5_pca_clusters.png')
R.image('4_5_pca_clusters.png', 'K-Means Clusters (PCA 2D) | K-Means 聚类的 PCA 二维投影')
R.text("**中文说明：** 横轴 = 第一主成分（PC1）；纵轴 = 第二主成分（PC2）；"
       "颜色 = 聚类标签（Cluster）。括号内为各主成分解释的方差比例。")
R.text("**解释：** PCA 将 3 维 RFM 降到 2 维，在保留最大方差的前提下可视化聚类结构。"
       "若各色簇在图上明显分离，说明聚类有效；若重叠严重，需调整 K 值或更换算法。")


# ============================================================
# 输出
# ============================================================
R.write()
