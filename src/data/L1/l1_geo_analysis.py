#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L1 主题示例：地理空间描述
- 数据源: ../ecommerce/ecommerce.db（只读）
- 内容: 省级 GMV/订单量/客户数排名横向条形图；城市级气泡图；南北方消费对比
- 说明: 不引入地图库，用 matplotlib 表达；报告中注明可替换 pyecharts 地图
- 输出: geo_report.md + images/geo_*.png
"""

import os
import sqlite3
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns

warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'ecommerce', 'ecommerce.db'))
OUTPUT_MD = os.path.join(SCRIPT_DIR, 'geo_report.md')
IMAGE_DIR = os.path.join(SCRIPT_DIR, 'images')
os.makedirs(IMAGE_DIR, exist_ok=True)

# ================== 中文字体（与 generate_report.py 相同） ==================
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
    fm.fontManager.addfont(CJK_FONT_FILE)
    _name = fm.FontProperties(fname=CJK_FONT_FILE).get_name()
    plt.rcParams['font.sans-serif'] = [_name, 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
sns.set_style("whitegrid")

conn = sqlite3.connect('file:%s?mode=ro' % DB_PATH.replace('\\', '/'), uri=True)

def sql(q):
    return pd.read_sql_query(q, conn)

class Report:
    def __init__(self):
        self.parts = []
        self.toc = []
        self.n = 0

    def h1(self, t):
        self.n += 1
        self.parts.append('<a id="sec-%d"></a>\n' % self.n)
        self.parts.append("# %d. %s\n" % (self.n, t))
        self.toc.append("- [%d %s](#sec-%d)" % (self.n, t, self.n))

    def text(self, s):
        self.parts.append(s.rstrip() + "\n")

    def code(self, lang, s):
        self.parts.append("```%s\n%s\n```\n" % (lang, s.rstrip()))

    def table(self, df_):
        try:
            self.parts.append(df_.to_markdown(index=False, floatfmt='.2f') + "\n")
        except Exception:
            self.parts.append("```\n" + df_.to_string(index=False) + "\n```\n")

    def image(self, name, caption=""):
        self.parts.append("![%s](%s/%s)\n" % (caption, os.path.basename(IMAGE_DIR), name))

    def save_plt(self, name):
        plt.savefig(os.path.join(IMAGE_DIR, name), bbox_inches='tight', dpi=100)
        plt.close()

    def write(self, title, intro_lines):
        header = ["# %s\n" % title] + intro_lines + ['<a id="toc"></a>\n## 目录\n']
        header.append("\n".join(self.toc) + "\n\n---\n")
        with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
            f.write("\n".join(header) + "\n".join(self.parts))
        print("[OK] 报告：%s" % OUTPUT_MD)

R = Report()

# ============================================================
# 1. 数据与口径
# ============================================================
R.h1("数据与口径")
R.text("地理维度的描述性分析回答三个问题：生意在哪里（区域排名）、"
       "城市之间什么结构（规模 × 质量）、大区域之间有没有差异（南北方对比）。\n\n"
       "**口径**：GMV / 订单量 = 有效订单（已完成 + 已发货）按下单客户归属地汇总；"
       "客户数 = customers 表按注册地统计；客单价 = GMV / 订单数。"
       "本数据集覆盖 10 省 23 市。")

# ============================================================
# 2. 省级排名
# ============================================================
R.h1("省级排名：GMV / 订单量 / 客户数")

q_prov = """WITH oc AS (
  SELECT c.province,
         ROUND(SUM(o.total_amount), 2) AS gmv,
         COUNT(o.order_id) AS n_orders
  FROM orders o
  JOIN customers c ON c.customer_id = o.customer_id
  WHERE o.order_status IN ('已完成','已发货')
  GROUP BY c.province
),
cc AS (
  SELECT province, COUNT(*) AS n_customers FROM customers GROUP BY province
)
SELECT oc.province, oc.gmv, oc.n_orders, cc.n_customers,
       ROUND(oc.gmv / oc.n_orders, 2) AS aov,
       ROUND(oc.gmv / cc.n_customers, 2) AS gmv_per_customer
FROM oc JOIN cc ON cc.province = oc.province
ORDER BY oc.gmv DESC;"""
R.text("**SQL 代码：**")
R.code("sql", q_prov)
prov = sql(q_prov)
R.text("**省级汇总表：**")
R.table(prov.rename(columns={
    'province': '省份', 'gmv': 'GMV(元)', 'n_orders': '订单数',
    'n_customers': '客户数', 'aov': '客单价(元)', 'gmv_per_customer': '人均消费(元)'}))

fig, axes = plt.subplots(1, 3, figsize=(15, 5))
for ax, col, title, color in [
        (axes[0], 'gmv', 'GMV by Province', 'steelblue'),
        (axes[1], 'n_orders', 'Orders by Province', 'seagreen'),
        (axes[2], 'n_customers', 'Customers by Province', 'darkorange')]:
    d = prov.sort_values(col)
    ax.barh(d['province'], d[col], color=color, alpha=0.85)
    ax.set_title(title)
plt.tight_layout()
R.save_plt('geo_province_rank.png')
R.image('geo_province_rank.png', 'Province Ranking | 省级 GMV/订单量/客户数排名')
R.text("**解释：** 横向条形图是排名数据的标配——类目名长时比竖柱好读。"
       "三张图并排的看点是「排名是否一致」：若 GMV 排名与客户数排名基本一致，"
       "说明区域差异主要是客户规模差异；若某省客户数居中但 GMV 靠前（人均消费高），"
       "则是高质量市场。人均消费列（GMV/客户数）就是为剥离规模效应准备的。")

# ============================================================
# 3. 城市级气泡图
# ============================================================
R.h1("城市级气泡图")

q_city = """WITH oc AS (
  SELECT c.province, c.city,
         ROUND(SUM(o.total_amount), 2) AS gmv,
         COUNT(o.order_id) AS n_orders
  FROM orders o
  JOIN customers c ON c.customer_id = o.customer_id
  WHERE o.order_status IN ('已完成','已发货')
  GROUP BY c.province, c.city
),
cc AS (
  SELECT city, COUNT(*) AS n_customers FROM customers GROUP BY city
)
SELECT oc.province, oc.city, oc.gmv, oc.n_orders, cc.n_customers,
       ROUND(oc.gmv / oc.n_orders, 2) AS aov
FROM oc JOIN cc ON cc.city = oc.city;"""
R.text("**SQL 代码：**")
R.code("sql", q_city)
city = sql(q_city)

plt.figure(figsize=(11, 7))
sizes = city['gmv'] / city['gmv'].max() * 2500 + 40
sc = plt.scatter(city['n_customers'], city['aov'], s=sizes,
                 c=city['gmv'], cmap='viridis', alpha=0.65, edgecolors='gray')
for _, r in city.iterrows():
    plt.annotate(r['city'], (r['n_customers'], r['aov']),
                 fontsize=8, ha='center', va='center')
plt.colorbar(sc, label='GMV（元）')
plt.xlabel('Customers (城市客户数)')
plt.ylabel('AOV (客单价)')
plt.title('City Bubble: x=customers, y=AOV, size/color=GMV')
plt.tight_layout()
R.save_plt('geo_city_bubble.png')
R.image('geo_city_bubble.png', 'City Bubble | 城市级气泡图（x=客户数, y=客单价, 气泡=GMV）')

R.text("**Top 10 城市（按 GMV）：**")
R.table(city.sort_values('gmv', ascending=False).head(10).rename(columns={
    'province': '省份', 'city': '城市', 'gmv': 'GMV(元)', 'n_orders': '订单数',
    'n_customers': '客户数', 'aov': '客单价(元)'}))
R.text("**解释：** 气泡图在二维平面上编码四个变量：x=客户规模，y=经营质量（客单价），"
       "气泡大小与颜色=GMV。四象限读法：\n"
       "- 右上（多客户 × 高客单）：核心市场，守住；\n"
       "- 左上（少客户 × 高客单）：小众高质市场，适合拉新；\n"
       "- 右下（多客户 × 低客单）：规模大质量低，适合提客单（连带/套餐）；\n"
       "- 左下：边缘市场，控制投入。\n"
       "注意客户数与 GMV 天然正相关（规模效应），y 轴客单价才是质量维度的信息增量。")

# ============================================================
# 4. 南北方消费对比
# ============================================================
R.h1("区域分组对比：南方 vs 北方")
R.text("把 10 个省份按常见口径粗分为两组做区域对比：\n"
       "- **北方**：北京市、山东省\n"
       "- **南方**：广东省、浙江省、江苏省、上海市、福建省、湖南省、湖北省、四川省\n\n"
       "粗分组的目的是演示「区域分组描述」的做法；真实业务应按公司大区或秦岭-淮河线细分。")

prov2 = prov.copy()
prov2['区域'] = np.where(prov2['province'].isin(['北京市', '山东省']), '北方', '南方')
region = prov2.groupby('区域').agg(
    GMV=('gmv', 'sum'), 订单数=('n_orders', 'sum'), 客户数=('n_customers', 'sum')).reset_index()
region['客单价'] = (region['GMV'] / region['订单数']).round(2)
region['人均消费'] = (region['GMV'] / region['客户数']).round(2)
region['GMV'] = region['GMV'].round(2)

R.text("**Python 代码：**")
R.code("python", """prov['区域'] = np.where(prov['province'].isin(['北京市','山东省']), '北方', '南方')
prov.groupby('区域').agg(GMV=('gmv','sum'), 订单数=('n_orders','sum'), 客户数=('n_customers','sum'))""")
R.text("**区域对比表：**")
R.table(region)

fig, axes = plt.subplots(1, 3, figsize=(13, 4))
for ax, col in zip(axes, ['GMV', '客单价', '人均消费']):
    ax.bar(region['区域'], region[col], color=['#c0504d', '#4bacc6'], alpha=0.85)
    ax.set_title(col)
    for i, v in enumerate(region[col]):
        ax.text(i, v, '%.0f' % v, ha='center', va='bottom', fontsize=9)
plt.tight_layout()
R.save_plt('geo_region_compare.png')
R.image('geo_region_compare.png', 'Region Compare | 南北方消费对比')
R.text("**解释：** 区域对比一定要同时看「总量」与「人均」两个口径："
       "总量反映市场盘子，人均反映消费能力。两组客户基数不同（南方省份多），"
       "GMV 总量不可直接比，人均消费与客单价才是公平比较。"
       "若要进一步检验人均消费差异是否显著，可对客户级消费额做两样本 t 检验或 Mann-Whitney U 检验——"
       "那已进入推断统计，是 L2 的内容。")

# ============================================================
# 5. 关于地图可视化
# ============================================================
R.h1("关于地图可视化")
R.text("本报告刻意不引入地图库（geopandas / pyecharts / folium），全部用 matplotlib 完成，原因有二：\n"
       "1. 地理描述的**信息**在排名、结构与区域对比中已完整表达，地图主要提升的是**呈现**；\n"
       "2. 地图库依赖重（geopandas 需要 GDAL/GEOS），教学环境能跑通比好看更重要。\n\n"
       "若需升级为真实地图，推荐 pyecharts：把第 2 节的省级汇总表喂给 `Map` 类型即可——\n"
       "```python\n"
       "from pyecharts.charts import Map\n"
       "Map().add('GMV', list(zip(prov['province'], prov['gmv'])), 'china')\n"
       "```\n"
       "数据准备代码（SQL 聚合）无需任何改动，只换渲染层。")

R.write("L1 地理空间描述报告", [
    "- **数据来源**：`data/ecommerce/ecommerce.db`（SQLite，只读连接）",
    "- **对应主题**：地理空间描述\n",
])
conn.close()
