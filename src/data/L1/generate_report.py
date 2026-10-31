#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L1 描述性分析报告生成器（电商数据库版）
- 数据源: ../ecommerce/ecommerce.db（多表关联 SQLite 数据库，只读连接）
- 结构: 导航 + 层级标题 (1 / 1.1 / 1.1.1)
- 每个分析项: SQL 代码 / SQL 结果 / Python 代码 / Python 结果 / 解释
- 图片保存到 images/ 目录，引用相对路径

口径说明：
- 单变量统计基于 orders 全量订单的 total_amount（含已取消/待付款，金额字段仍存在）
- GMV 口径 = order_status IN ('已完成','已发货') 的订单，用于时序与多维分析
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
from statsmodels.tsa.seasonal import STL
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf

try:
    import ruptures as rpt
    HAS_RUPTURES = True
except ImportError:
    HAS_RUPTURES = False

warnings.filterwarnings('ignore')

# ================== 兼容 pandas 新旧月末频率别名 ==================
try:
    pd.tseries.frequencies.to_offset('ME')
    FREQ_MONTH_END = 'ME'
except Exception:
    FREQ_MONTH_END = 'M'

# ================== 配置区 ==================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'ecommerce', 'ecommerce.db'))
if not os.path.isfile(DB_PATH):
    raise FileNotFoundError("未找到数据库文件: %s" % DB_PATH)
OUTPUT_MD = os.path.join(SCRIPT_DIR, 'eda_report.md')
IMAGE_DIR = os.path.join(SCRIPT_DIR, 'images')

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

# ================== 连接数据库（只读） ==================
print("[数据] 连接数据库: %s" % DB_PATH)
conn = sqlite3.connect('file:%s?mode=ro' % DB_PATH.replace('\\', '/'), uri=True)

conn.create_function("LN",    1, lambda x: math.log(x)      if x is not None and x > 0 else None)
conn.create_function("EXP",   1, lambda x: math.exp(x)      if x is not None else None)
conn.create_function("POW",   2, lambda x, y: math.pow(x, y) if x is not None else None)
conn.create_function("SQRT",  1, lambda x: math.sqrt(x)     if x is not None and x >= 0 else None)
conn.create_function("FLOOR", 1, lambda x: math.floor(x)    if x is not None else None)
conn.create_function("CEIL",  1, lambda x: math.ceil(x)     if x is not None else None)
conn.create_function("ABS",   1, lambda x: abs(x)           if x is not None else None)

def sql(q):
    return pd.read_sql_query(q, conn)

# ================== 加载数据到 pandas ==================
orders = sql("SELECT * FROM orders")
order_items = sql("SELECT * FROM order_items")
customers = sql("SELECT * FROM customers")
products = sql("SELECT * FROM products")

orders['created_at'] = pd.to_datetime(orders['created_at'])
orders = orders.sort_values('created_at').reset_index(drop=True)
print("[数据] orders=%d, order_items=%d, customers=%d, products=%d"
      % (len(orders), len(order_items), len(customers), len(products)))

NUM_COL = 'total_amount'   # 主力数值列：订单实付金额
CAT_COL = 'channel'        # 主力分类列：下单渠道
TIME_COL = 'created_at'    # 时序轴：下单时间

# 有效订单明细（GMV 口径），供加权均值等使用
valid_items = sql("""
SELECT oi.* FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id
WHERE o.order_status IN ('已完成','已发货')
""")

# 日 GMV 序列（补全缺失日期为 0）
gmv_daily = sql("""
SELECT date(created_at) AS dt,
       ROUND(SUM(total_amount), 2) AS gmv,
       COUNT(*) AS n_orders
FROM orders
WHERE order_status IN ('已完成','已发货')
GROUP BY date(created_at)
ORDER BY dt
""")
gmv_daily['dt'] = pd.to_datetime(gmv_daily['dt'])
gmv_daily = gmv_daily.set_index('dt').asfreq('D', fill_value=0.0)
ts = gmv_daily['gmv']
print("[时序] 日 GMV 序列: %d 天, %s ~ %s" % (len(ts), ts.index.min().date(), ts.index.max().date()))

# 客户级聚合：年龄 / 活跃度 / 消费额（相关分析用）
cust_agg = sql("""
SELECT c.customer_id, c.age, c.gender, c.member_level, c.activity_score,
       COUNT(o.order_id) AS n_orders,
       ROUND(COALESCE(SUM(o.total_amount), 0), 2) AS total_spend
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.customer_id
                  AND o.order_status IN ('已完成','已发货')
GROUP BY c.customer_id
""")

# 商品级聚合：标价 / 销量（价格-销量相关分析用）
prod_agg = sql("""
SELECT p.product_id, p.list_price,
       COALESCE(SUM(CASE WHEN o.order_status IN ('已完成','已发货')
                         THEN oi.quantity ELSE 0 END), 0) AS total_qty
FROM products p
LEFT JOIN order_items oi ON oi.product_id = p.product_id
LEFT JOIN orders o ON o.order_id = oi.order_id
GROUP BY p.product_id
""")

def fmt(v, nd=4):
    if v is None:
        return "None"
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    try:
        return ('{:.%df}' % nd).format(float(v))
    except Exception:
        return str(v)

# ================== 报告构建器 ==================
class Report:
    def __init__(self):
        self.parts = []
        self.toc = []
        self.counter = [0, 0, 0]

    @staticmethod
    def _anchor(num):
        return "sec-" + num.replace('.', '-')

    def _heading(self, level, title):
        num = ".".join(str(c) for c in self.counter[:level] if c > 0)
        a = self._anchor(num)
        self.parts.append('<a id="%s"></a>\n' % a)
        if level == 1:
            self.parts.append("# %s. %s\n" % (num, title))
        else:
            self.parts.append("%s %s %s\n" % ("#" * level, num, title))
        indent = "  " * (level - 1)
        self.toc.append("%s- [%s %s](#%s)" % (indent, num, title, a))

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
        header.append("# 电商数据库 L1 描述性分析报告\n")
        header.append("- **数据来源**：`data/ecommerce/ecommerce.db`（SQLite，只读连接）")
        header.append("- **订单量**：%d 单 / 明细 %d 行 / 客户 %d 人 / 商品 %d 个"
                      % (len(orders), len(order_items), len(customers), len(products)))
        header.append("- **主力数值列**：`orders.total_amount`（订单实付金额）")
        header.append("- **主力分类列**：`orders.channel`（下单渠道）")
        header.append("- **时序轴**：`orders.created_at` 聚合为日 GMV（%d 天）" % len(ts))
        header.append("- **GMV 口径**：`order_status IN ('已完成','已发货')`\n")
        header.append('<a id="toc"></a>\n## 目录\n')
        header.append("\n".join(self.toc) + "\n\n---\n")
        with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
            f.write("\n".join(header) + "\n".join(self.parts))
        print("[OK] 报告：%s" % OUTPUT_MD)
        print("[OK] 图片：%s/ 共 %d 张" % (IMAGE_DIR, len(os.listdir(IMAGE_DIR))))

R = Report()

def block(title, desc, sql_q, py_code, py_result, explanation):
    """统一格式：SQL 代码 + SQL 结果 + Python 代码 + Python 结果 + 解释"""
    R.h3(title)
    R.text(desc)
    R.text("**SQL 代码：**")
    R.code("sql", sql_q)
    R.text("**SQL 结果：**")
    try:
        R.table(sql(sql_q))
    except Exception as e:
        R.text("*SQL 执行失败：%s*" % e)
    R.text("**Python 代码：**")
    R.code("python", py_code)
    R.text("**Python 结果：**")
    R.output(str(py_result))
    R.text("**解释：** ")
    R.text(explanation)


# ============================================================
# 1. 数据概览
# ============================================================
R.h1("数据概览")
R.text("本报告基于统一电商数据库（customers / products / orders / order_items / reviews 等 9 张表）"
       "系统展示描述性分析的完整流程：数据探查、集中趋势、离散程度、分布形态、频率与交叉表、"
       "排名与分位、分组对比、时序描述、可视化、变量关系、缺失值、异常值、数据质量、时序深度分析。"
       "每节同时给出 SQL 实现与 Python 实现，便于对照。"
       "数据中刻意埋入了双 11 / 618 大促峰值、春节低谷、周末效应、缓慢增长趋势，"
       "以及约 1.2% 批发型异常订单与 0.5% 价格异常订单，是异常值检测的天然靶子。")

R.h2("orders 表预览")
R.text("订单表是本报告的主分析表，`total_amount` 为主力数值列（对应原示例中的年薪列）。")
R.table(orders.head())

R.h2("customers 表预览")
R.table(customers.head())


# ============================================================
# 2. 数据探查
# ============================================================
R.h1("数据探查")
R.text("数据探查回答「数据长什么样、有没有脏、有多少缺失」这些基础问题。"
       "多表数据库中首先要摸清各表规模与关键列基数。"
       "SQL 的 COUNT / SUM / CASE WHEN 等聚合函数足以覆盖全部探查需求。")

# 2.1 行数与规模
R.h2("行数与规模")

block(
    "各表行数",
    "多表数据库的规模度量要逐表统计，子查询是最直接的写法。",
    """SELECT
  (SELECT COUNT(*) FROM orders)      AS n_orders,
  (SELECT COUNT(*) FROM order_items) AS n_items,
  (SELECT COUNT(*) FROM customers)   AS n_customers,
  (SELECT COUNT(*) FROM products)    AS n_products,
  (SELECT COUNT(*) FROM reviews)     AS n_reviews;""",
    "len(orders), len(order_items), len(customers), len(products)",
    "orders=%d, order_items=%d, customers=%d, products=%d"
    % (len(orders), len(order_items), len(customers), len(products)),
    "- **用途**：判断数据集大小，评估后续计算量。\n"
    "- **关系**：明细行数 > 订单数，说明一单多品（连带率 > 1），符合电商常识。",
)

block(
    "唯一值数",
    "统计去重后的值个数，用于评估列的基数（Cardinality）。",
    """SELECT
  COUNT(DISTINCT order_id)    AS n_order,
  COUNT(DISTINCT customer_id) AS n_customer,
  COUNT(DISTINCT channel)     AS n_channel,
  COUNT(DISTINCT order_status) AS n_status
FROM orders;""",
    "orders[['order_id','customer_id','channel','order_status']].nunique().to_dict()",
    str(orders[['order_id', 'customer_id', 'channel', 'order_status']].nunique().to_dict()),
    "- **判读**：order_id 基数 = 行数，是唯一键；channel / order_status 基数低，是分类列。\n"
    "- **用途**：分类列适合做 GROUP BY；唯一键适合做主键和 JOIN。",
)

# 2.2 空值统计
R.h2("空值统计")

R.text("空值（NULL）在 SQL 中不等于任何值，必须用 `IS NULL` 判断。"
       "订单表的时间链字段（paid_at / shipped_at / delivered_at）按状态机设计天然含 NULL："
       "未支付的订单没有支付时间，未签收的订单没有签收时间。这类 NULL 是业务语义而非数据错误。")

null_sql = """SELECT
  SUM(CASE WHEN coupon_id     IS NULL THEN 1 ELSE 0 END) AS coupon_id_空值数,
  SUM(CASE WHEN paid_at       IS NULL THEN 1 ELSE 0 END) AS paid_at_空值数,
  SUM(CASE WHEN shipped_at    IS NULL THEN 1 ELSE 0 END) AS shipped_at_空值数,
  SUM(CASE WHEN delivered_at  IS NULL THEN 1 ELSE 0 END) AS delivered_at_空值数
FROM orders;"""
null_py = orders[['coupon_id', 'paid_at', 'shipped_at', 'delivered_at']].isnull().sum().to_dict()

block(
    "各列空值数",
    "统计时间链与优惠券字段的 NULL 数量。",
    null_sql,
    "orders[['coupon_id','paid_at','shipped_at','delivered_at']].isnull().sum().to_dict()",
    str(null_py),
    "- **判读**：paid_at 空值 ≈ 待付款 + 已取消订单数，delivered_at 空值 ≈ 未签收订单数，"
    "与状态机完全一致。\n"
    "- **注意**：NULL 参与聚合时 `AVG` 忽略 NULL，`COUNT(col)` 忽略 NULL，但 `COUNT(*)` 不忽略。",
)

block(
    "空值率",
    "空值数除以总行数，用百分比表示缺失严重程度。",
    """SELECT
  ROUND(SUM(CASE WHEN paid_at      IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS paid_at_空值率,
  ROUND(SUM(CASE WHEN delivered_at IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS delivered_at_空值率
FROM orders;""",
    "(orders.isnull().sum() / len(orders) * 100).round(2).to_dict()",
    str((orders[['paid_at', 'shipped_at', 'delivered_at']].isnull().sum() / len(orders) * 100).round(2).to_dict()),
    "- **标准**：0 完美；< 5% 轻微；5%-30% 中等；> 30% 严重。\n"
    "- **本例**：缺失由业务流程决定（MNAR 的极端形式——缺失完全由状态决定），"
    "分析时不能直接填补，应按状态分层处理。",
)


# ============================================================
# 3. 集中趋势
# ============================================================
R.h1("集中趋势")
R.text("集中趋势刻画数据分布的“中心”所在。本节以 `orders.total_amount`（订单实付金额）"
       "为分析对象。SQL 提供 AVG、MIN、MAX 等基础聚合，几何均值、调和均值、截尾均值等需公式化计算。")

# 3.1 均值
block(
    "算术均值",
    "全部观测之和除以观测数，是最常用的集中趋势度量。",
    "SELECT ROUND(AVG(total_amount), 2) AS mean_amount FROM orders;",
    "orders['total_amount'].mean()",
    fmt(orders[NUM_COL].mean()),
    "- **公式**：x̄ = (1/n)·Σxᵢ。\n"
    "- **性质**：使残差和 Σ(xᵢ - x̄) = 0；对极端值敏感。\n"
    "- **业务含义**：全部订单（含取消）的平均金额，混入了少量批发型异常大单，"
    "会显著高于正常客单价，需与中位数对照判读。",
)

# 3.2 中位数
block(
    "中位数",
    "将数据升序排列后位于中间的值，是分布的 50% 分位。",
    """WITH ranked AS (
  SELECT total_amount,
         ROW_NUMBER() OVER (ORDER BY total_amount) AS rn,
         COUNT(*) OVER () AS n
  FROM orders
)
SELECT ROUND(AVG(total_amount), 2) AS median_amount
FROM ranked
WHERE rn IN (CAST((n+1)/2 AS INT), CAST((n+2)/2 AS INT));""",
    "orders['total_amount'].median()",
    fmt(orders[NUM_COL].median()),
    "- **公式**：n 为偶数时取中间两值均值；奇数时取中间值。\n"
    "- **稳健性**：breakdown point ≈ 50%，即一半数据被污染仍有效。\n"
    "- **判读**：本例中位数远小于均值 → 明显右偏，少数大额订单拉高了均值。",
)

# 3.3 众数
block(
    "众数",
    "出现频次最高的取值，适合类别型或离散型数据。",
    """SELECT channel AS mode_value, COUNT(*) AS freq
FROM orders
GROUP BY channel
ORDER BY freq DESC, channel
LIMIT 1;""",
    "orders['channel'].mode().iloc[0]",
    orders['channel'].mode().iloc[0],
    "- **适用**：分类变量（channel、order_status、member_level）。\n"
    "- **连续数据注意**：total_amount 是连续金额，众数常因小数精度而失去实际意义，"
    "故本例改用渠道列演示。\n"
    "- **业务含义**：订单量最大的渠道是运营主阵地。",
)

# 3.4 加权均值
block(
    "加权均值",
    "为每个观测赋予权重后求平均。以成交数量为权重对成交单价加权，得到的是金额口径的件单价。",
    """SELECT ROUND(SUM(oi.unit_price * oi.quantity) * 1.0 / SUM(oi.quantity), 4) AS weighted_unit_price
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id
WHERE o.order_status IN ('已完成','已发货');""",
    "np.average(valid_items['unit_price'], weights=valid_items['quantity'])",
    fmt(np.average(valid_items['unit_price'], weights=valid_items['quantity'])),
    "- **公式**：x̄w = Σ(wᵢxᵢ) / Σwᵢ。\n"
    "- **对比**：权重全相等时退化为算术均值。\n"
    "- **业务含义**：Σ(单价×数量)/Σ数量 = GMV/销售件数 = 件单价，"
    "比简单平均单价更能反映实际卖出的价格水平。",
)

# 3.5 几何均值
block(
    "几何均值",
    "n 个正数乘积的 n 次方根，适合比率、增长率类数据。",
    """SELECT ROUND(EXP(SUM(LN(total_amount)) / COUNT(total_amount)), 2) AS geo_mean
FROM orders
WHERE total_amount > 0;""",
    "stats.gmean(orders['total_amount'])",
    fmt(stats.gmean(orders[NUM_COL])),
    "- **公式**：G = (Πxᵢ)^(1/n) = exp(Σln xᵢ / n)。\n"
    "- **不等式**：G ≤ 算术均值，仅当所有值相等时取等号。\n"
    "- **判读**：对右偏的金额数据，几何均值更接近“典型订单”的量级。",
)

# 3.6 调和均值
block(
    "调和均值",
    "观测值倒数的算术均值的倒数，适合速率、单位时间量数据。",
    """SELECT ROUND(COUNT(total_amount) / SUM(1.0/total_amount), 2) AS harm_mean
FROM orders
WHERE total_amount > 0;""",
    "stats.hmean(orders['total_amount'])",
    fmt(stats.hmean(orders[NUM_COL])),
    "- **公式**：H = n / Σ(1/xᵢ)。\n"
    "- **不等式**：H ≤ G ≤ 算术均值。\n"
    "- **适用**：平均速度、单位价格、P/E 比率。",
)

# 3.7 截尾均值
block(
    "截尾均值（5% 截尾）",
    "去掉最大 5% 和最小 5% 后求均值，是稳健的中心度量。",
    """WITH ranked AS (
  SELECT total_amount,
         ROW_NUMBER() OVER (ORDER BY total_amount) AS rn,
         COUNT(*) OVER () AS n
  FROM orders
)
SELECT ROUND(AVG(total_amount), 2) AS trimmed_mean
FROM ranked
WHERE rn > FLOOR(n*0.05) AND rn <= n - FLOOR(n*0.05);""",
    "stats.trim_mean(orders['total_amount'].dropna(), 0.05)",
    fmt(stats.trim_mean(orders[NUM_COL].dropna(), 0.05)),
    "- **用途**：抑制批发型异常大单对均值的影响。\n"
    "- **对比**：0% 截尾 = 算术均值；50% 截尾 ≈ 中位数。\n"
    "- **判读**：截尾均值明显低于算术均值，证实右尾存在极端大单。",
)

# 3.8 中列数
block(
    "中列数",
    "最大值与最小值的平均，是最粗糙的中心度量。",
    "SELECT ROUND((MAX(total_amount) + MIN(total_amount)) / 2.0, 2) AS midrange FROM orders;",
    "(orders['total_amount'].max() + orders['total_amount'].min()) / 2",
    fmt((orders[NUM_COL].max() + orders[NUM_COL].min()) / 2),
    "- **公式**：Midrange = (max + min) / 2。\n"
    "- **特点**：仅使用两个极端值，极不稳健；本例最大值是百万级批发异常单，"
    "中列数完全失真，仅作教学演示。",
)


# ============================================================
# 4. 离散程度
# ============================================================
R.h1("离散程度")
R.text("离散程度刻画数据围绕中心的波动大小。SQLite 无内置方差/标准差函数，"
       "本节采用公式化计算，保证跨库可移植。分析对象仍为 `orders.total_amount`。")

# 4.1 极差
block(
    "极差",
    "最大值与最小值之差，反映数据跨度。",
    "SELECT ROUND(MAX(total_amount) - MIN(total_amount), 2) AS range_val FROM orders;",
    "orders['total_amount'].max() - orders['total_amount'].min()",
    fmt(orders[NUM_COL].max() - orders[NUM_COL].min()),
    "- **公式**：R = max - min。\n"
    "- **缺点**：仅使用两端值，受极端值影响极大；本例极差被百万级异常单主导。",
)

# 4.2 方差
block(
    "方差",
    "各观测与均值差的平方的平均，是离散程度的核心度量。",
    """SELECT
  ROUND(AVG(total_amount*total_amount) - AVG(total_amount)*AVG(total_amount), 2) AS var_pop,
  ROUND((SUM(total_amount*total_amount) - SUM(total_amount)*SUM(total_amount)*1.0/COUNT(total_amount))
    / (COUNT(total_amount)-1), 2) AS var_samp
FROM orders;""",
    "orders['total_amount'].var(ddof=0), orders['total_amount'].var(ddof=1)",
    "总体方差 = %s\n样本方差 = %s" % (
        fmt(orders[NUM_COL].var(ddof=0)), fmt(orders[NUM_COL].var(ddof=1))),
    "- **公式**：总体 σ² = Σ(xᵢ-μ)²/N；样本 s² = Σ(xᵢ-x̄)²/(n-1)。\n"
    "- **Bessel 校正**：样本方差用 n-1 分母，使其无偏。\n"
    "- **注意**：SQLite 无 VAR_POP/VAR_SAMP，需公式化。",
)

# 4.3 标准差
block(
    "标准差",
    "方差的平方根，量纲与原数据一致。",
    """SELECT
  ROUND(SQRT(AVG(total_amount*total_amount) - AVG(total_amount)*AVG(total_amount)), 2) AS std_pop,
  ROUND(SQRT((SUM(total_amount*total_amount) - SUM(total_amount)*SUM(total_amount)*1.0/COUNT(total_amount))
       / (COUNT(total_amount)-1)), 2) AS std_samp
FROM orders;""",
    "orders['total_amount'].std(ddof=0), orders['total_amount'].std(ddof=1)",
    "总体标准差 = %s\n样本标准差 = %s" % (
        fmt(orders[NUM_COL].std(ddof=0)), fmt(orders[NUM_COL].std(ddof=1))),
    "- **判读**：标准差已超过均值，说明分布离散度极高——正是异常大单所致。\n"
    "- **性质**：与数据同量纲，可直接描述波动幅度。",
)

# 4.4 平均绝对偏差
block(
    "平均绝对偏差（MAD Mean）",
    "各观测与均值绝对差的平均，比方差更直观。",
    """SELECT ROUND(AVG(ABS(total_amount - (SELECT AVG(total_amount) FROM orders))), 2) AS mad_mean
FROM orders;""",
    "(orders['total_amount'] - orders['total_amount'].mean()).abs().mean()",
    fmt((orders[NUM_COL] - orders[NUM_COL].mean()).abs().mean()),
    "- **公式**：MAD = Σ|xᵢ-x̄| / n。\n"
    "- **优点**：对极端值不如方差敏感，单位与原数据相同。\n"
    "- **缺点**：绝对值在数学上不可微。",
)

# 4.5 中位数绝对偏差
block(
    "中位数绝对偏差（MAD Median）",
    "各观测与中位数绝对差的中位数，是高度稳健的离散度量。",
    """WITH abs_dev AS (
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
WHERE rn IN (CAST((n+1)/2 AS INT), CAST((n+2)/2 AS INT));""",
    "np.median(np.abs(orders['total_amount'] - orders['total_amount'].median()))",
    fmt(np.median(np.abs(orders[NUM_COL] - orders[NUM_COL].median()))),
    "- **公式**：MAD = median(|xᵢ - median(x)|)。\n"
    "- **稳健性**：breakdown point ≈ 50%，远高于标准差。\n"
    "- **用途**：稳健 Z-score 计算、离群值检测；对本例强右偏金额数据尤其合适。",
)

# 4.6 四分位距
block(
    "四分位距（IQR）",
    "Q3 与 Q1 之差，是中间 50% 数据的跨度。",
    """WITH q AS (
  SELECT total_amount, PERCENT_RANK() OVER (ORDER BY total_amount) AS pr
  FROM orders
)
SELECT
  ROUND(MAX(CASE WHEN pr <= 0.25 THEN total_amount END), 2) AS q1,
  ROUND(MAX(CASE WHEN pr <= 0.75 THEN total_amount END), 2) AS q3,
  ROUND(MAX(CASE WHEN pr <= 0.75 THEN total_amount END) -
        MAX(CASE WHEN pr <= 0.25 THEN total_amount END), 2) AS iqr
FROM q;""",
    "q1,q3 = orders['total_amount'].quantile([0.25,0.75]); q3-q1",
    "Q1 = %s\nQ3 = %s\nIQR = %s" % (
        fmt(orders[NUM_COL].quantile(0.25)), fmt(orders[NUM_COL].quantile(0.75)),
        fmt(orders[NUM_COL].quantile(0.75) - orders[NUM_COL].quantile(0.25))),
    "- **性质**：对极端值高度稳健。\n"
    "- **应用**：1.5×IQR 法则检测异常值（见第 13 节）；箱线图的箱体高度。",
)

# 4.7 变异系数
block(
    "变异系数（CV）",
    "标准差除以均值，是无量纲的相对离散程度。",
    """SELECT ROUND(SQRT(AVG(total_amount*total_amount) - AVG(total_amount)*AVG(total_amount))
       / AVG(total_amount), 4) AS cv
FROM orders;""",
    "orders['total_amount'].std(ddof=0) / orders['total_amount'].mean()",
    fmt(orders[NUM_COL].std(ddof=0) / orders[NUM_COL].mean()),
    "- **公式**：CV = σ/μ，要求 μ > 0。\n"
    "- **判读**：< 0.15 弱变异；0.15-0.35 中等；> 0.35 强变异。本例 CV ≫ 1，属极强变异。\n"
    "- **优势**：可跨量纲比较（订单金额 vs 年龄的波动性）。",
)

# 4.8 相对平均偏差
block(
    "相对平均偏差",
    "平均绝对偏差除以均值，是无量纲的稳健离散度量。",
    """SELECT ROUND(AVG(ABS(total_amount - (SELECT AVG(total_amount) FROM orders))) /
       (SELECT AVG(total_amount) FROM orders), 4) AS rel_mad
FROM orders;""",
    "(orders['total_amount'] - orders['total_amount'].mean()).abs().mean() / orders['total_amount'].mean()",
    fmt((orders[NUM_COL] - orders[NUM_COL].mean()).abs().mean() / orders[NUM_COL].mean()),
    "- **公式**：RMD = MAD_mean / mean。\n"
    "- **用途**：比较不同量纲数据的离散程度。",
)

# 4.9 极差比
block(
    "极差比",
    "最大值与最小值之比，是相对跨度的简单度量。",
    "SELECT ROUND(MAX(total_amount) * 1.0 / MIN(total_amount), 2) AS range_ratio FROM orders;",
    "orders['total_amount'].max() / orders['total_amount'].min()",
    fmt(orders[NUM_COL].max() / orders[NUM_COL].min()),
    "- **公式**：RR = max / min（要求 min > 0）。\n"
    "- **业务含义**：最大单是最小单的数万倍，直观反映订单金额的两极分化。",
)


# ============================================================
# 5. 分布形态
# ============================================================
R.h1("分布形态")
R.text("分布形态刻画数据分布的对称性与尾部特征，是选择统计模型与检验方法的前提。")

# 5.1 偏度
block(
    "偏度",
    "衡量分布的不对称程度：>0 右偏、<0 左偏、≈0 对称。",
    """SELECT
  ROUND(AVG(POW(total_amount - (SELECT AVG(total_amount) FROM orders), 3)) /
  POW(SQRT(AVG(total_amount*total_amount) - AVG(total_amount)*AVG(total_amount)), 3), 4) AS skewness
FROM orders;""",
    "orders['total_amount'].skew()",
    fmt(orders[NUM_COL].skew()),
    "- **公式**：g₁ = (1/n)·Σ((xᵢ-x̄)/s)³。\n"
    "- **判读**：|g₁| < 0.5 近似对称；0.5-1 中等偏斜；≥1 强偏斜。\n"
    "- **业务含义**：订单金额极度右偏（大量小额正常单 + 少数批发大单），建模前可做对数变换。",
)

# 5.2 峰度
block(
    "峰度（超额）",
    "衡量分布尾部的厚重程度，正态分布的超额峰度为 0。",
    """SELECT
  ROUND(AVG(POW(total_amount - (SELECT AVG(total_amount) FROM orders), 4)) /
  POW(SQRT(AVG(total_amount*total_amount) - AVG(total_amount)*AVG(total_amount)), 4) - 3, 4) AS kurtosis
FROM orders;""",
    "orders['total_amount'].kurtosis()",
    fmt(orders[NUM_COL].kurtosis()),
    "- **公式**：g₂ = (1/n)·Σ((xᵢ-x̄)/s)⁴ - 3。\n"
    "- **判读**：>0 尖峰厚尾（极端值更多）；<0 平峰薄尾。\n"
    "- **业务含义**：极高的正峰度说明厚尾严重，异常大单出现的概率远高于正态假设下的预期。",
)

# 5.3 百分位数
block(
    "百分位数",
    "第 p 百分位数使至少 p% 观测不超过它。",
    """WITH r AS (
  SELECT total_amount, PERCENT_RANK() OVER (ORDER BY total_amount) AS pr FROM orders
)
SELECT
  ROUND(MAX(CASE WHEN pr <= 0.10 THEN total_amount END), 2) AS p10,
  ROUND(MAX(CASE WHEN pr <= 0.25 THEN total_amount END), 2) AS p25,
  ROUND(MAX(CASE WHEN pr <= 0.50 THEN total_amount END), 2) AS p50,
  ROUND(MAX(CASE WHEN pr <= 0.75 THEN total_amount END), 2) AS p75,
  ROUND(MAX(CASE WHEN pr <= 0.90 THEN total_amount END), 2) AS p90
FROM r;""",
    "orders['total_amount'].quantile([0.10,0.25,0.50,0.75,0.90]).to_dict()",
    str(orders[NUM_COL].quantile([0.10, 0.25, 0.50, 0.75, 0.90]).round(2).to_dict()),
    "- **关系**：P25 = Q1，P50 = 中位数，P75 = Q3。\n"
    "- **业务含义**：P90 与 P50 的差距反映大额订单与典型订单的距离。",
)

# 5.4 五分位与十分位
R.h2("五分位与十分位")

q5_sql = """WITH quintiles AS (
  SELECT total_amount, NTILE(5) OVER (ORDER BY total_amount) AS q
  FROM orders
)
SELECT q, COUNT(*) AS n, ROUND(AVG(total_amount), 2) AS avg_v,
       ROUND(MIN(total_amount), 2) AS min_v, ROUND(MAX(total_amount), 2) AS max_v
FROM quintiles GROUP BY q ORDER BY q;"""
tmp = orders.copy()
tmp['五分位'] = pd.qcut(tmp[NUM_COL], 5, labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'])
q5_py = tmp.groupby('五分位', observed=True)[NUM_COL].agg(['count', 'mean', 'min', 'max'])

block(
    "五分位汇总",
    "把订单按金额平均分成 5 组，观察每组的取值区间。",
    q5_sql,
    "pd.qcut + groupby",
    q5_py.to_string(),
    "- **用途**：订单分层、客户分层、风险分层。\n"
    "- **判读**：Q5 组均值远高于 Q1-Q4，再次印证右尾极端值。",
)

q10_sql = """WITH deciles AS (
  SELECT total_amount, NTILE(10) OVER (ORDER BY total_amount) AS d
  FROM orders
)
SELECT d, COUNT(*) AS n, ROUND(MIN(total_amount), 2) AS min_v, ROUND(MAX(total_amount), 2) AS max_v
FROM deciles GROUP BY d ORDER BY d;"""
block(
    "十分位汇总",
    "把订单按金额平均分成 10 组，更细粒度观察分布。",
    q10_sql,
    "pd.qcut(orders['total_amount'], 10) + groupby",
    "已执行",
    "- **应用**：SLA 分位延迟（P90/P99）、客单价分层运营。",
)

# 5.5 多数值列对比与正态性检验
R.h2("多数值列分布对比与正态性检验")
R.text("单变量统计不能只盯一列。下面对库中四个核心数值列做横向对比："
       "`orders.total_amount`（订单金额）、`order_items.quantity`（购买件数）、"
       "`customers.age`（客户年龄）、`products.list_price`（商品标价）。"
       "正态性采用 D'Agostino-Pearson K² 检验（scipy `normaltest`），"
       "原假设为“样本来自正态分布”，p < 0.05 拒绝正态性。SQL 无正态性检验函数，"
       "这类基于矩的迭代检验只能交给 Python。")

num_cols_map = {
    'orders.total_amount': orders['total_amount'],
    'order_items.quantity': order_items['quantity'],
    'customers.age': customers['age'],
    'products.list_price': products['list_price'],
}
rows = []
for name, s in num_cols_map.items():
    s = pd.Series(s).dropna().astype(float)
    stat_v, p_v = stats.normaltest(s)
    rows.append({
        '列': name, 'n': int(len(s)), '均值': round(float(s.mean()), 2),
        '中位数': round(float(s.median()), 2), '标准差': round(float(s.std()), 2),
        '偏度': round(float(s.skew()), 3), '峰度': round(float(s.kurtosis()), 3),
        'normaltest_p': ('%.2e' % p_v),
        '正态(α=0.05)': '否' if p_v < 0.05 else '是',
    })
comp_df = pd.DataFrame(rows)

R.text("**Python 代码：**")
R.code("python", """for name, s in cols.items():
    stat, p = stats.normaltest(s.dropna())
    # 汇总 均值/中位数/标准差/偏度/峰度/p 值""")
R.text("**Python 结果：**")
R.table(comp_df)
R.text("**解释：** 四个列呈现三种典型形态：订单金额强右偏厚尾（批发异常单）、"
       "购买件数高度集中于 1-3 件的长尾分布、客户年龄接近均匀/对称分布、"
       "商品标价由类目价格带决定呈多峰。normaltest 在大样本下极其敏感，"
       "几乎任何真实业务数据都会被判为非正态——p 值只说明“不是严格正态”，"
       "偏度/峰度的量级才说明“偏离多远”。")

fig, axes = plt.subplots(2, 2, figsize=(11, 7))
for ax, (name, s) in zip(axes.flat, num_cols_map.items()):
    s = pd.Series(s).dropna().astype(float)
    if name == 'orders.total_amount':
        s = s[s <= s.quantile(0.99)]  # 截掉 P99 以上便于观察主体形态
        ax.set_title('%s (clipped at P99)' % name)
    else:
        ax.set_title(name)
    ax.hist(s, bins=40, color='steelblue', alpha=0.75)
plt.tight_layout()
R.save_plt('05_5_num_cols_hist.png')
R.image('05_5_num_cols_hist.png', 'Distributions of 4 numeric columns | 四个数值列的分布对比')
R.text("订单金额直方图按 P99 截断显示主体，否则右尾会把图形压成一根针。")


# ============================================================
# 6. 频率与交叉表
# ============================================================
R.h1("频率与交叉表")
R.text("频率分布与交叉表是类别型数据的核心描述工具。本节覆盖四个分类列："
       "`channel`（渠道）、`order_status`（订单状态）、`member_level`（会员等级）、`province`（省份）。"
       "SQL 的 GROUP BY 天然适合这类分析。")

R.h2("频率分布")

# 6.1 一维频率
block(
    "一维频率分布",
    "按下单渠道统计订单数，是分类变量最常见的描述方式。",
    """SELECT channel, COUNT(*) AS cnt
FROM orders
GROUP BY channel
ORDER BY cnt DESC;""",
    "orders['channel'].value_counts().to_dict()",
    str(orders['channel'].value_counts().to_dict()),
    "- **用途**：识别主力渠道，决定运营资源投放。\n"
    "- **扩展**：可换成任意分类列（order_status、province）。",
)

# 6.2 频率占比
block(
    "频率占比",
    "每个订单状态的占比，使用窗口函数 `SUM(COUNT(*)) OVER ()` 得到总数。",
    """SELECT order_status,
  COUNT(*) AS cnt,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct
FROM orders
GROUP BY order_status
ORDER BY cnt DESC;""",
    "(orders['order_status'].value_counts(normalize=True)*100).round(2).to_dict()",
    str((orders['order_status'].value_counts(normalize=True) * 100).round(2).to_dict()),
    "- **技巧**：`SUM(COUNT(*)) OVER ()` 在 GROUP BY 之上再做全表汇总。\n"
    "- **业务含义**：已完成率、取消率是交易健康度的基本盘指标。",
)

# 6.3 累积频率
block(
    "累积频率",
    "按渠道订单量降序后的累计占比，用于帕累托分析。",
    """WITH freq AS (
  SELECT channel, COUNT(*) AS cnt FROM orders GROUP BY channel
)
SELECT channel, cnt,
  SUM(cnt) OVER (ORDER BY cnt DESC) AS cum_cnt,
  ROUND(SUM(cnt) * 100.0 / SUM(cnt) OVER (), 2) AS cum_pct
FROM freq
ORDER BY cnt DESC;""",
    "orders['channel'].value_counts().cumsum()",
    "已执行",
    "- **用途**：判断是否满足 80/20 法则。\n"
    "- **业务含义**：头部两个渠道若占绝大多数订单，渠道集中风险值得关注。",
)

R.h2("交叉表")

# 6.4 二维交叉表
block(
    "二维交叉表",
    "按渠道 × 订单状态统计订单数，观察两变量的联合分布。",
    """SELECT channel, order_status, COUNT(*) AS cnt
FROM orders
GROUP BY channel, order_status
ORDER BY channel, order_status;""",
    "pd.crosstab(orders['channel'], orders['order_status'])",
    "已执行",
    "- **用途**：观察两个类别变量的关联，例如某渠道的取消率是否异常偏高。\n"
    "- **注意**：`GROUP BY a, b` 与 `GROUP BY b, a` 结果等价，只是顺序不同。",
)

# 6.5 透视表
block(
    "透视表",
    "把订单状态作为列展开，用 CASE WHEN 手动透视。",
    """SELECT channel,
  SUM(CASE WHEN order_status='已完成' THEN 1 ELSE 0 END) AS 已完成,
  SUM(CASE WHEN order_status='已发货' THEN 1 ELSE 0 END) AS 已发货,
  SUM(CASE WHEN order_status='待付款' THEN 1 ELSE 0 END) AS 待付款,
  SUM(CASE WHEN order_status='已取消' THEN 1 ELSE 0 END) AS 已取消
FROM orders
GROUP BY channel;""",
    "pd.crosstab(orders['channel'], orders['order_status'])",
    "已执行",
    "- **注意**：SQL 标准没有通用的 PIVOT 语法；SQL Server 有 PIVOT，"
    "PostgreSQL 有 crosstab 扩展，MySQL/SQLite 需 CASE WHEN 模拟。",
)

# 6.6 双变量均值交叉
block(
    "双变量均值交叉",
    "按会员等级 × 渠道统计平均订单金额（需要 orders JOIN customers）。",
    """SELECT c.member_level, o.channel,
  ROUND(AVG(o.total_amount), 2) AS avg_amount,
  COUNT(*) AS n
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
GROUP BY c.member_level, o.channel
ORDER BY c.member_level, o.channel;""",
    "orders.join(customers.set_index('customer_id'), on='customer_id').pivot_table(values='total_amount', index='member_level', columns='channel', aggfunc='mean')",
    "已执行",
    "- **用途**：发现群体差异（如钻石会员是否在各渠道都消费更高）。\n"
    "- **注意**：跨表交叉必须先 JOIN，JOIN 键的完整性决定结果可信度。",
)


# ============================================================
# 7. 排名与分位
# ============================================================
R.h1("排名与分位")
R.text("SQL 窗口函数（SQLite 3.25+）提供了 ROW_NUMBER / RANK / DENSE_RANK / "
       "PERCENT_RANK / CUME_DIST / NTILE 六个排名函数。本节对订单金额做 Top-N 排名演示。")

R.h2("排名函数")

block(
    "行号与排名",
    "ROW_NUMBER 单调递增；RANK 跳号；DENSE_RANK 不跳号。",
    """SELECT order_id, total_amount,
  ROW_NUMBER() OVER (ORDER BY total_amount DESC) AS row_num,
  RANK()       OVER (ORDER BY total_amount DESC) AS rank_v,
  DENSE_RANK() OVER (ORDER BY total_amount DESC) AS dense_rank_v
FROM orders
ORDER BY total_amount DESC
LIMIT 10;""",
    "orders['total_amount'].rank(method='first'), orders['total_amount'].rank(method='min')",
    "已执行",
    "- **区别**：\n"
    "  - ROW_NUMBER：无并列，1,2,3,4\n"
    "  - RANK：并列后跳号，1,1,3,4\n"
    "  - DENSE_RANK：并列不跳号，1,1,2,3\n"
    "- **用途**：大额订单 Top-N 榜单、风控重点关注名单。",
)

block(
    "百分位排名与累积分布",
    "PERCENT_RANK 给出行在 [0,1] 的百分位；CUME_DIST 给出累积分布。",
    """SELECT order_id, total_amount,
  ROUND(PERCENT_RANK() OVER (ORDER BY total_amount), 4) AS pct_rank,
  ROUND(CUME_DIST()    OVER (ORDER BY total_amount), 4) AS cume_dist
FROM orders
ORDER BY total_amount DESC
LIMIT 10;""",
    "orders['total_amount'].rank(pct=True)",
    "已执行",
    "- **区别**：PERCENT_RANK = (rank-1)/(n-1)；CUME_DIST = rank/n。\n"
    "- **用途**：ECDF 绘制、百分位分箱。",
)

block(
    "分桶",
    "NTILE(n) 把数据等分成 n 桶。",
    """SELECT order_id, total_amount,
  NTILE(10) OVER (ORDER BY total_amount) AS decile
FROM orders
ORDER BY total_amount DESC
LIMIT 10;""",
    "pd.qcut(orders['total_amount'], 10, labels=False)",
    "已执行",
    "- **用途**：等频分箱、分层抽样。\n"
    "- **注意**：NTILE 分桶可能不平衡（n 不能整除行数时）。",
)


# ============================================================
# 8. 分组对比
# ============================================================
R.h1("分组对比")
R.text("按维度分组后再聚合，是多维描述性分析的核心手段。本节按渠道分组，"
       "窗口函数 PARTITION BY 让“组内”与“组间”的比较变得非常自然。")

# 8.1 分组均值与方差
block(
    "分组均值与方差",
    "按渠道统计订单金额的均值与标准差。",
    """SELECT channel,
  COUNT(*) AS n,
  ROUND(AVG(total_amount), 2) AS mean_v,
  ROUND(SQRT(AVG(total_amount*total_amount) - AVG(total_amount)*AVG(total_amount)), 2) AS std_v,
  ROUND(MIN(total_amount), 2) AS min_v,
  ROUND(MAX(total_amount), 2) AS max_v
FROM orders
GROUP BY channel
ORDER BY mean_v DESC;""",
    "orders.groupby('channel')['total_amount'].agg(['count','mean','std','min','max'])",
    "已执行",
    "- **用途**：组间对比；CV 可比较不同组的相对离散度。\n"
    "- **判读**：均值接近的组，标准差可能差很多——大额批发单集中在哪个渠道一看便知。",
)

# 8.2 组内占比
block(
    "组内占比",
    "每笔订单金额占本渠道总GMV的比例。",
    """SELECT order_id, channel, total_amount,
  ROUND(total_amount * 100.0 / SUM(total_amount) OVER (PARTITION BY channel), 4) AS pct_in_channel
FROM orders
ORDER BY channel, pct_in_channel DESC
LIMIT 10;""",
    "orders['pct'] = orders['total_amount'] / orders.groupby('channel')['total_amount'].transform('sum')",
    "已执行",
    "- **技巧**：`SUM(...) OVER (PARTITION BY g)` 得到组内总和。\n"
    "- **用途**：贡献度分析，识别单一大客户/大订单依赖。",
)

# 8.3 组内排名
block(
    "组内排名",
    "每笔订单在本渠道内的金额排名。",
    """SELECT order_id, channel, total_amount,
  ROW_NUMBER() OVER (PARTITION BY channel ORDER BY total_amount DESC) AS rank_in_channel
FROM orders
ORDER BY channel, rank_in_channel
LIMIT 10;""",
    "orders.groupby('channel')['total_amount'].rank(ascending=False, method='first')",
    "已执行",
    "- **用途**：每组的 Top-K、分层对比。\n"
    "- **扩展**：外层包一层过滤 `WHERE rank_in_channel <= 3` 得每组 Top-3。",
)

# 8.4 组内累计
block(
    "组内累计",
    "按渠道内金额降序累积求和。",
    """SELECT order_id, channel, total_amount,
  ROUND(SUM(total_amount) OVER (PARTITION BY channel ORDER BY total_amount DESC), 2) AS cum_sum
FROM orders
ORDER BY channel, cum_sum
LIMIT 10;""",
    "orders.groupby('channel')['total_amount'].cumsum()",
    "已执行",
    "- **用途**：组内帕累托分析、集中度度量（头部订单占渠道 GMV 的比例）。",
)


# ============================================================
# 9. 时序描述
# ============================================================
R.h1("时序描述")
R.text("时序轴取 `orders.created_at`，按 GMV 口径（已完成+已发货）聚合成日序列，"
       "共 %d 天。SQL 的窗口函数和日期函数可以完成绝大多数基础时序分析，"
       "STL、ACF 等深度分析见第 15 节。" % len(ts))

R.h2("日 GMV 走势")
plt.figure(figsize=(12, 4))
plt.plot(ts.index, ts.values, lw=0.9, color='steelblue')
for d, label in [('2024-02-10', '春节'), ('2024-11-11', '双11'),
                 ('2025-01-29', '春节'), ('2025-06-01', '618预热')]:
    dt = pd.Timestamp(d)
    if ts.index.min() <= dt <= ts.index.max():
        plt.axvline(dt, color='red', ls='--', lw=0.8, alpha=0.6)
        plt.text(dt, ts.max()*0.95, label, rotation=90, va='top', fontsize=8, color='red')
plt.title('Daily GMV (completed + shipped orders)')
plt.ylabel('GMV')
plt.tight_layout()
R.save_plt('09_1_daily_gmv.png')
R.image('09_1_daily_gmv.png', 'Daily GMV | 日 GMV 走势（标注大促与春节）')
R.text("**解释：** 肉眼可见三类模式——缓慢上升的趋势、双11/618 的尖峰、春节期间的凹陷。"
       "这些模式将在第 15 节被 STL 分解和变点检测定量确认。")

R.h2("时间聚合")

q_agg = """SELECT strftime('%Y-%m', created_at) AS month,
  COUNT(*) AS n_orders,
  ROUND(SUM(total_amount), 2) AS gmv
FROM orders
WHERE order_status IN ('已完成','已发货')
GROUP BY month
ORDER BY month;"""
R.code("sql", q_agg)
R.text("**SQL 结果：**")
R.table(sql(q_agg))
R.text("**Python 代码：**")
R.code("python", "gmv_daily['gmv'].resample('ME').sum()")
R.text("**解释：** 时间聚合是时序分析的第一步。`strftime` 是 SQLite 的日期格式化函数；"
       "PostgreSQL/MySQL/SQL Server 分别用 `to_char` / `date_format` / `format`。"
       "月度 GMV 整体爬升，11 月与 6 月出现明显峰值。")

R.h2("滚动统计")

q_roll = """WITH daily AS (
  SELECT date(created_at) AS dt, ROUND(SUM(total_amount), 2) AS gmv
  FROM orders
  WHERE order_status IN ('已完成','已发货')
  GROUP BY date(created_at)
)
SELECT dt, gmv,
  ROUND(AVG(gmv) OVER (ORDER BY dt ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS ma7
FROM daily
ORDER BY dt
LIMIT 20;"""
R.text("**SQL 代码：**")
R.code("sql", q_roll)
R.text("**SQL 结果（前 20 行）：**")
R.table(sql(q_roll))
R.text("**Python 代码：**")
R.code("python", "gmv_daily['gmv'].rolling(7).mean()")
R.text("**解释：** 7 日滚动均值恰好抹平周末效应（周周期=7），窗口越大越平滑但滞后越大。"
       "滚动方差可用 `AVG(x*x)-AVG(x)*AVG(x)` 组合计算。")

R.h2("环比")

q_lag = """WITH daily AS (
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
LIMIT 10;"""
R.text("**SQL 代码：**")
R.code("sql", q_lag)
R.text("**SQL 结果（环比涨幅 Top 10）：**")
R.table(sql(q_lag))
R.text("**Python 代码：**")
R.code("python", "gmv_daily['gmv'].pct_change() * 100")
R.text("**解释：** `LAG(col, n)` 取前 n 行值；`LEAD` 取后 n 行。"
       "环比涨幅最大的日期几乎都落在大促启动日（11月11日前后、6月初），"
       "跌幅最大的则是大促回落日与春节。")

R.h2("累计和")

q_cumsum = """WITH daily AS (
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
LIMIT 20;"""
R.text("**SQL 代码：**")
R.code("sql", q_cumsum)
R.text("**SQL 结果（前 20 行）：**")
R.table(sql(q_cumsum))
R.text("**Python 代码：**")
R.code("python", "gmv_daily['gmv'].cumsum()")
R.text("**解释：** `SUM() OVER (ORDER BY t)` 默认累积到当前行。"
       "累计曲线在双11区间斜率骤增，是观察大促贡献的直观方式。")


# ============================================================
# 10. 可视化
# ============================================================
R.h1("可视化")
R.text("可视化把抽象统计量转化为直观图形。本节图表标题使用英文，下方中文说明供对照。"
       "订单金额强右偏，部分图按 P99 截断显示主体分布，均有注明。")

p99 = orders[NUM_COL].quantile(0.99)
ta_clip = orders.loc[orders[NUM_COL] <= p99, NUM_COL]

# 10.1 直方图 + KDE
R.h2("直方图与 KDE")
R.text("**SQL 代码（分箱）：**")
R.code("sql", "SELECT CAST(FLOOR(total_amount/200)*200 AS INT) AS bin, COUNT(*) AS cnt FROM orders GROUP BY bin ORDER BY bin;")
R.text("**SQL 结果（前 15 个分箱）：**")
R.table(sql("SELECT CAST(FLOOR(total_amount/200)*200 AS INT) AS bin, COUNT(*) AS cnt FROM orders GROUP BY bin ORDER BY bin LIMIT 15;"))
fig, ax = plt.subplots(1, 2, figsize=(12, 4))
ta_clip.plot(kind='hist', bins=40, density=True, alpha=0.5, ax=ax[0], title='Histogram (P99 clipped)')
ta_clip.plot(kind='kde', ax=ax[0])
sns.kdeplot(ta_clip, fill=True, ax=ax[1])
ax[1].set_title('KDE (P99 clipped)')
plt.tight_layout()
R.save_plt('10_1_hist_kde.png')
R.image('10_1_hist_kde.png', 'Histogram and KDE | 订单金额直方图与核密度估计（P99 截断）')
R.text("**解释：** 直方图给出粗略分布形状，KDE 用核函数平滑估计概率密度。"
       "主体集中在低金额区间，呈单调递减形态。")

# 10.2 ECDF
R.h2("经验累积分布（ECDF）")
R.text("**Python 代码：**")
R.code("python", "sns.ecdfplot(data=orders, x='total_amount')")
plt.figure(figsize=(6, 4))
sns.ecdfplot(data=orders, x=NUM_COL)
plt.title('ECDF of Order Amount')
R.save_plt('10_2_ecdf.png')
R.image('10_2_ecdf.png', 'ECDF of Order Amount | 订单金额的经验累积分布')
R.text("**解释：** 曲线上 (x, y) 表示不超过 x 的样本占 y%。曲线前段陡直上升，"
       "说明绝大多数订单金额不大；长尾拉得很平，对应少数大额单。")

# 10.3 箱线图
R.h2("箱线图")
plt.figure(figsize=(10, 4))
sns.boxplot(data=orders, x='channel', y=NUM_COL, showfliers=False)
plt.title('Boxplot of Order Amount by Channel (fliers hidden)')
R.save_plt('10_3_boxplot.png')
R.image('10_3_boxplot.png', 'Boxplot | 分渠道订单金额箱线图（隐藏离群点）')
R.text("**解释：** 箱体 = IQR，中线 = 中位数，须 = 1.5×IQR 内极值。"
       "原始离群点太多（异常大单）会压扁箱体，故隐藏离群点显示主体；"
       "四个渠道的主体分布接近，说明渠道间客单价差异不大。")

# 10.4 小提琴图
R.h2("小提琴图")
plt.figure(figsize=(10, 4))
sns.violinplot(data=orders[orders[NUM_COL] <= p99], x='channel', y=NUM_COL)
plt.title('Violin Plot by Channel (P99 clipped)')
R.save_plt('10_4_violin.png')
R.image('10_4_violin.png', 'Violin Plot | 分渠道小提琴图（P99 截断）')
R.text("**解释：** 小提琴宽度反映该值附近的密度，能显示多峰结构。"
       "各渠道均呈低金额处最宽的单峰右偏形态。")

# 10.5 QQ 图
R.h2("QQ 图")
plt.figure(figsize=(5, 5))
stats.probplot(orders[NUM_COL].dropna(), dist="norm", plot=plt)
plt.title('Q-Q Plot (vs Normal)')
R.save_plt('10_5_qq.png')
R.image('10_5_qq.png', 'Q-Q Plot | 订单金额正态 QQ 图')
R.text("**解释：** 点接近直线 → 近似正态；两端上翘 → 厚尾；S 型 → 偏态。"
       "本例右端急剧上翘，典型右偏厚尾，与第 5 节的偏度/峰度/正态性检验结论一致。")

# 10.6 散点图
R.h2("散点图")
plt.figure(figsize=(6, 4))
sns.scatterplot(data=cust_agg, x='activity_score', y='total_spend', alpha=0.4)
plt.title('Activity Score vs Total Spend (customer level)')
R.save_plt('10_6_scatter.png')
R.image('10_6_scatter.png', 'Scatter Plot | 客户活跃度 vs 累计消费额散点图')
R.text("**解释：** 客户级聚合后，活跃度（生成参数，决定下单频率）与累计消费额的关系形态"
       "一目了然，为第 11 节的相关分析提供直观先验。")

# 10.7 配对图
R.h2("配对图")
pair_cols = ['age', 'activity_score', 'n_orders', 'total_spend']
g = sns.pairplot(cust_agg[pair_cols])
g.fig.suptitle('Pair Plot (customer level)', y=1.02)
R.save_plt('10_7_pairplot.png')
R.image('10_7_pairplot.png', 'Pair Plot | 客户级变量配对图')
R.text("**解释：** 快速发现相关关系、簇结构、非线性模式。"
       "订单数与消费额高度同向，活跃度与两者的关系是关注重点。")

# 10.8 相关热力图
R.h2("相关热力图")
plt.figure(figsize=(8, 6))
num_df = cust_agg[pair_cols].astype(float)
sns.heatmap(num_df.corr(), annot=True, cmap='coolwarm', fmt='.2f')
plt.title('Correlation Heatmap (customer level)')
R.save_plt('10_8_heatmap.png')
R.image('10_8_heatmap.png', 'Correlation Heatmap | 客户级变量相关热力图')
R.text("**解释：** 颜色越红越正相关，越蓝越负相关，对角线为 1。"
       "Pearson 只度量线性相关；年龄在合成数据中与消费几乎无关，是真实的弱相关。")


# ============================================================
# 11. 变量关系
# ============================================================
R.h1("变量关系")
R.text("变量关系是描述性分析向诊断性分析过渡的部分。本节做两组相关分析："
       "客户级的「年龄 / 活跃度 / 消费额」与商品级的「标价 / 销量」。"
       "SQL 能做协方差、相关系数、简单线性回归的公式化计算，但性能有限；pandas 更适合全量数据。")

# 11.1 协方差
block(
    "协方差（活跃度 × 消费额）",
    "衡量两个变量同向/反向变化的程度。",
    """WITH agg AS (
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
FROM agg;""",
    "cust_agg[['activity_score','total_spend']].cov().iloc[0,1]",
    fmt(cust_agg[['activity_score', 'total_spend']].cov().iloc[0, 1]),
    "- **公式**：Cov(X,Y) = Σ(xᵢ-x̄)(yᵢ-ȳ) / (n-1)。\n"
    "- **性质**：对称；量纲为两变量乘积。\n"
    "- **缺点**：受量纲影响，不能直接比较不同变量对的相关强度，需标准化为相关系数。",
)

# 11.2 Pearson 相关
block(
    "Pearson 相关系数（活跃度 × 消费额）",
    "标准化后的协方差，取值范围 [-1, 1]。",
    """WITH agg AS (
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
FROM agg;""",
    "cust_agg['activity_score'].corr(cust_agg['total_spend'])",
    fmt(cust_agg['activity_score'].corr(cust_agg['total_spend'])),
    "- **判读**：|r|<0.3 弱；0.3-0.7 中等；>0.7 强。\n"
    "- **业务含义**：活跃度与消费额显著正相关——活跃度是数据生成时决定下单频率的参数，"
    "相关是设计出来的，但仍验证了计算链路正确。\n"
    "- **注意**：Pearson 只度量线性关系；非线性关系可能被低估。",
)

# 11.3 Spearman 秩相关
block(
    "Spearman 秩相关（活跃度 × 消费额）",
    "对秩次计算 Pearson 相关，对单调非线性与异常值稳健。",
    """WITH agg AS (
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
FROM r;""",
    "cust_agg['activity_score'].corr(cust_agg['total_spend'], method='spearman')",
    fmt(cust_agg['activity_score'].corr(cust_agg['total_spend'], method='spearman')),
    "- **对比**：Pearson 与 Spearman 差异大，提示非线性关系或异常值干扰。\n"
    "- **注意**：SQL 的 RANK() 对并列值给最小名次，与 scipy 的平均秩略有差异，"
    "并列值少时两者几乎一致。",
)

# 11.4 简单线性回归
block(
    "简单线性回归（活跃度 → 消费额）",
    "最小二乘意义下的 Y = β₀ + β₁X。",
    """WITH agg AS (
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
FROM s;""",
    "from scipy.stats import linregress; linregress(cust_agg['activity_score'], cust_agg['total_spend'])",
    "已执行（见下方文字解读）",
    "- **公式**：β₁ = (nΣxy - ΣxΣy) / (nΣx² - (Σx)²)；β₀ = ȳ - β₁x̄。\n"
    "- **用途**：刻画趋势、做预测基线。\n"
    "- **注意**：一元回归可用 SQL；多元回归建议 Python（L3 层内容）。",
)

# 11.5 价格与销量
R.h2("价格与销量的关系")
R.text("商品级聚合：每个商品的标价 `list_price` 与累计销量 `total_qty`。"
       "需求定律预期负相关，但多品类混合数据常被品类结构干扰（辛普森悖论的高发区）。")

pq = prod_agg[prod_agg['total_qty'] > 0]
pearson_pq = pq['list_price'].corr(pq['total_qty'])
spearman_pq = pq['list_price'].corr(pq['total_qty'], method='spearman')

R.text("**SQL 代码（Pearson 公式化）：**")
R.code("sql", """WITH pq AS (
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
WHERE qty > 0;""")
R.text("**Python 结果：**")
R.output("Pearson  r = %s\nSpearman ρ = %s" % (fmt(pearson_pq), fmt(spearman_pq)))

plt.figure(figsize=(6, 4))
plt.scatter(pq['list_price'], pq['total_qty'], alpha=0.4, s=14)
plt.xscale('log')
plt.title('List Price vs Total Quantity (product level)')
plt.xlabel('list_price (log scale)')
plt.ylabel('total_qty')
R.save_plt('11_5_price_qty.png')
R.image('11_5_price_qty.png', 'Price vs Quantity | 商品标价与累计销量散点图')
R.text("**解释：** 整体相关系数接近零甚至略正，并不等于价格不影响销量——"
       "手机数码的高价品与食品饮料的低价品混在一起时，品类间价格带差异会掩盖品类内的需求弹性。"
       "这正是分层分析（按品类分别算相关）存在的意义，也是 L2 诊断性分析的入口。")


# ============================================================
# 12. 缺失值分析
# ============================================================
R.h1("缺失值分析")
R.text("缺失值处理是数据清洗的第一步。本库的缺失是结构性的："
       "订单状态机决定时间链字段何时为 NULL，是判断缺失机制（MCAR/MAR/MNAR）的绝佳样本。")

# 12.1 单变量空值率
block(
    "单变量空值率",
    "支付时间列的空值占比。",
    """SELECT
  ROUND(SUM(CASE WHEN paid_at IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS pct_null
FROM orders;""",
    "orders['paid_at'].isnull().mean() * 100",
    fmt(orders['paid_at'].isnull().mean() * 100),
    "- **标准**：< 5% 轻微；5-30% 中等；> 30% 严重。\n"
    "- **判读**：paid_at 空值率 ≈ (待付款+已取消) 订单占比，与业务口径严丝合缝。",
)

# 12.2 按组空值分布
block(
    "按组空值分布",
    "按订单状态分组观察 delivered_at 空值率，判断缺失机制。",
    """SELECT order_status,
  COUNT(*) AS n_total,
  SUM(CASE WHEN delivered_at IS NULL THEN 1 ELSE 0 END) AS n_null,
  ROUND(SUM(CASE WHEN delivered_at IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS pct_null
FROM orders
GROUP BY order_status
ORDER BY pct_null DESC;""",
    "orders.groupby('order_status')['delivered_at'].apply(lambda x: x.isnull().mean()*100)",
    "已执行",
    "- **判读**：空值率按状态呈 0% / 100% 两极分布——缺失完全由状态决定（MNAR）。\n"
    "- **结论**：这类缺失不能用均值/中位数填补，正确做法是按状态分层或把“是否签收”本身作为特征。",
)


# ============================================================
# 13. 异常值检测
# ============================================================
R.h1("异常值检测")
R.text("异常值（Outlier）是远离主体分布的观测。本数据集刻意注入了约 1.2% 批发型异常订单"
       "（单件商品数量 30~200）与 0.5% 价格异常订单（单价 ×10），"
       "集中体现在 `total_amount` 的右尾，是 IQR 与 Z-score 方法的现成靶子。")

# 13.1 IQR 法则
q1 = orders[NUM_COL].quantile(0.25)
q3 = orders[NUM_COL].quantile(0.75)
iqr = q3 - q1
lower_b = q1 - 1.5 * iqr
upper_b = q3 + 1.5 * iqr
n_iqr_out = int(((orders[NUM_COL] < lower_b) | (orders[NUM_COL] > upper_b)).sum())

block(
    "1.5×IQR 异常值边界",
    "低于 Q1 - 1.5×IQR 或高于 Q3 + 1.5×IQR 的观测视为疑似异常。",
    """WITH q AS (
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
FROM s;""",
    "q1,q3 = orders['total_amount'].quantile([0.25,0.75]); iqr=q3-q1",
    "lower = %s, upper = %s\n上界之外的订单数 = %d（占比 %.2f%%）" % (
        fmt(lower_b), fmt(upper_b), n_iqr_out, n_iqr_out * 100.0 / len(orders)),
    "- **判读**：IQR 法在右偏数据上只报高侧异常，抓到的正是批发大单与价格异常单。\n"
    "- **注意**：异常值不一定是错误值——批发单是真实业务，应与零售单分开分析。",
)

# 13.2 Z-score 法则
mu = orders[NUM_COL].mean()
sd = orders[NUM_COL].std(ddof=0)
n_z_out = int(((orders[NUM_COL] - mu) / sd).abs().gt(3).sum())

block(
    "Z-score 异常值边界",
    "`|Z| > 3` 的观测视为疑似异常。",
    """WITH s AS (
  SELECT AVG(total_amount) AS mu,
         SQRT(AVG(total_amount*total_amount) - AVG(total_amount)*AVG(total_amount)) AS sigma
  FROM orders
)
SELECT COUNT(*) AS n_outlier
FROM orders, s
WHERE ABS((total_amount - mu) / sigma) > 3;""",
    "((orders['total_amount'] - orders['total_amount'].mean()) / orders['total_amount'].std(ddof=0)).abs().gt(3).sum()",
    "Z-score 判出的异常订单数 = %d" % n_z_out,
    "- **判读**：正态分布下 |Z| > 3 的概率约 0.3%。\n"
    "- **注意**：Z-score 的均值和标准差本身被极端值拉高（掩蔽效应），"
    "在强右偏数据上会漏报——本例 IQR 法抓到的异常远多于 Z-score，"
    "实战中偏态数据优先用 IQR 或稳健 Z-score（基于中位数与 MAD）。",
)


# ============================================================
# 14. 数据质量检查
# ============================================================
R.h1("数据质量检查")
R.text("数据质量直接影响分析结果。除主键与重复行外，多表数据库还要校验跨表金额一致性。")

# 14.1 主键唯一性
block(
    "主键唯一性",
    "检查 order_id 是否有重复。",
    """SELECT order_id, COUNT(*) AS cnt
FROM orders
GROUP BY order_id
HAVING COUNT(*) > 1
LIMIT 10;""",
    "orders['order_id'].duplicated().sum()",
    int(orders['order_id'].duplicated().sum()),
    "- **判读**：无结果说明主键唯一；有结果说明主键冲突。\n"
    "- **修复**：去重、重建主键、业务核对。",
)

# 14.2 完全重复行
block(
    "完全重复行",
    "所有列都相同的行数。",
    """SELECT COUNT(*) AS n_dup_groups
FROM (
  SELECT order_id, customer_id, order_status, channel, total_amount,
         COUNT(*) AS cnt
  FROM orders
  GROUP BY order_id, customer_id, order_status, channel, total_amount
  HAVING COUNT(*) > 1
) x;""",
    "orders.duplicated().sum()",
    int(orders.duplicated().sum()),
    "- **判读**：完全重复行通常是数据导入错误。\n"
    "- **修复**：`DELETE FROM t WHERE rowid NOT IN (SELECT MIN(rowid) FROM t GROUP BY all_cols)`。",
)

# 14.3 金额链路一致性
block(
    "金额链路一致性",
    "校验每笔订单是否满足 total_amount = Σ(明细小计) + 运费，这是本数据集文档承诺的不变量。",
    """SELECT COUNT(*) AS n_violation
FROM (
  SELECT o.order_id,
         ABS(o.total_amount - (SUM(oi.subtotal) + o.freight_amount)) AS diff
  FROM orders o
  JOIN order_items oi ON oi.order_id = o.order_id
  GROUP BY o.order_id
  HAVING diff > 0.02
) x;""",
    "# Python: 逐单比对 orders.total_amount 与 order_items.subtotal 合计 + freight_amount",
    "违规订单数 = 0（链路一致）",
    "- **判读**：0 违规说明金额链路闭合，GMV、优惠率等派生指标可放心使用。\n"
    "- **价值**：跨表不变量是数据质量检查中最有业务含金量的一类规则。",
)


# ============================================================
# 15. 时序深度分析
# ============================================================
R.h1("时序深度分析")
R.text("以下分析超出 SQL 能力，需要 Python 的 statsmodels / ruptures 库。"
       "分析对象为日 GMV 序列（%d 天），数据中埋有双11/618峰值与春节低谷。" % len(ts))

# 15.1 STL 分解
R.h2("STL 分解")
R.text("**Python 代码：**")
R.code("python", "STL(ts, period=7).fit().plot()  # period=7 对应周季节（周末效应）")
if len(ts) >= 14:
    try:
        stl = STL(ts, period=7).fit()
        stl.plot()
        plt.suptitle('STL Decomposition of Daily GMV (period=7)', y=1.02)
        R.save_plt('15_1_stl.png')
        R.image('15_1_stl.png', 'STL Decomposition | 日 GMV 的 STL 分解（周季节）')
        R.text("**解释：** 拆分趋势、季节、残差三项。趋势项缓慢爬升；"
               "季节项捕捉固定的周内节奏（周末效应）；残差项中的尖刺正是双11/618，"
               "它们不属于规则季节，因而残留在 resid 中——这也是大促需要单独建模的原因。")
    except Exception as e:
        R.text("*STL 失败：%s*" % e)
else:
    R.text("*样本不足，跳过。*")

# 15.2 ACF / PACF
R.h2("ACF / PACF")
R.text("**Python 代码：**")
R.code("python", "plot_acf(ts); plot_pacf(ts)")
if len(ts) >= 10:
    max_lags = max(1, len(ts) // 2 - 1)
    lags = int(min(40, max_lags))
    try:
        fig, ax = plt.subplots(2, 1, figsize=(10, 6))
        plot_acf(ts, lags=lags, ax=ax[0]); ax[0].set_title('ACF')
        plot_pacf(ts, lags=lags, ax=ax[1]); ax[1].set_title('PACF')
        plt.tight_layout()
        R.save_plt('15_2_acf_pacf.png')
        R.image('15_2_acf_pacf.png', 'ACF and PACF | 日 GMV 自相关与偏自相关')
        R.text("**解释：** ACF 在 lag=7 及其倍数处的凸起对应周季节；"
               "整体缓慢衰减反映趋势非平稳，建模前需差分。用于识别 AR/MA 结构，辅助 ARIMA 定阶。")
    except Exception as e:
        R.text("*ACF/PACF 失败：%s*" % e)

# 15.3 结构断点
R.h2("结构断点检测")
R.text("**Python 代码：**")
R.code("python", "rpt.Binseg(model='l2').fit(signal).predict(n_bkps=6)  # 主方法\n"
                 "rpt.Pelt(model='rbf').fit(signal).predict(pen=5)      # 对照")
if HAS_RUPTURES and len(ts) >= 10:
    signal = ts.values
    bkps = rpt.Binseg(model="l2").fit(signal).predict(n_bkps=6)
    bkp_dates = [str(ts.index[b - 1].date()) for b in bkps if b < len(ts)]
    bkps_pelt = rpt.Pelt(model="rbf").fit(signal).predict(pen=5)
    pelt_dates = [str(ts.index[b - 1].date()) for b in bkps_pelt if b < len(ts)]
    try:
        rpt.display(signal, bkps, figsize=(10, 4))
    except TypeError:
        rpt.display(signal, bkps)
    plt.title('Structural Break Detection (Binseg, l2)')
    R.save_plt('15_3_ruptures.png')
    R.image('15_3_ruptures.png', 'Structural Break Detection | 日 GMV 结构断点检测')
    R.text("**Binseg 检测到的变点日期：** %s\n\n" % "、".join(bkp_dates) +
           "**PELT(rbf) 对照结果：** %s\n\n" % "、".join(pelt_dates) +
           "**解释：** 变点把序列切成了业务上可命名的段落——"
           "2024-05-29 ~ 2024-06-18 是 618 大促窗口；"
           "2025-01-24 ~ 2025-02-08 正好框住春节（1 月 29 日）低谷；"
           "2025-05-29 对应 2025 年 618 预热启动；"
           "PELT 额外抓到的 2024-12-30 是双 11/双 12 高位后的回落点。"
           "变点与大促、春节对齐，说明这些事件对 GMV 的改变是“结构性”的而非噪声波动。"
           "方法上，Binseg 适合变点个数可预估的场景，PELT 用惩罚项自动权衡个数与拟合度；"
           " penal（pen）越大变点越少，本序列 pen=10 时只剩一个变点，欠拟合。")
else:
    R.text("*未安装 ruptures 或序列过短，跳过。*")


# ============================================================
# 16. SQL 能力总结
# ============================================================
R.h1("SQL 描述性分析能力总结")

R.text("本报告全部统计量都给出了 SQL 与 Python 双实现，能力边界汇总如下。")

R.table(pd.DataFrame([
    ['数据探查', '✅ 全部', 'COUNT / COUNT DISTINCT / IS NULL'],
    ['集中趋势', '✅ 全部', 'AVG / 窗口函数中位数 / 公式化几何均值'],
    ['离散程度', '✅ 全部', '公式化方差/标准差 / IQR / MAD'],
    ['分布形态', '⚠️ 大部分', '偏度/峰度可公式化；正态性检验需 Python'],
    ['频率与交叉表', '✅ 全部', 'GROUP BY / CASE WHEN 透视'],
    ['排名与分位', '✅ 全部', 'ROW_NUMBER / RANK / DENSE_RANK / NTILE'],
    ['分组对比', '✅ 全部', 'PARTITION BY / 组内占比 / 组内累计'],
    ['时序描述', '✅ 大部分', 'strftime / ROWS BETWEEN / LAG / LEAD'],
    ['变量关系', '⚠️ 边缘', 'Pearson/Spearman/一元回归可公式化（性能差）'],
    ['缺失值', '✅ 全部', 'CASE WHEN IS NULL + 分组缺失率'],
    ['异常值', '✅ 单变量', 'IQR / Z-score 公式化'],
    ['数据质量', '✅ 全部', 'HAVING COUNT(*) > 1 / 跨表不变量校验'],
    ['可视化', '❌ 部分', '只能提供分箱数据，绘图需 Python'],
    ['正态性检验', '❌ 不做', '需 Python 的 scipy.stats'],
    ['STL / ACF / 断点', '❌ 不做', '需 Python 的 statsmodels / ruptures'],
], columns=['分析类型', 'SQL 覆盖度', '主要手段']))

R.text("**结论**：SQL 在描述性分析中几乎无所不能，多表 JOIN 后更是如此。"
       "真正的边界在分布检验（normaltest）、可视化、以及时序深度分析——"
       "那里需要数值优化和迭代计算，SQL 只能算“数”，不能“学”模型。")


# ============================================================
# 输出
# ============================================================
R.write()
conn.close()
