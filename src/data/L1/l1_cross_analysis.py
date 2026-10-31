#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L1 主题示例：多维交叉分析
- 数据源: ../ecommerce/ecommerce.db（只读）
- 内容: 省份×一级品类 GMV 透视表+热力图；会员等级×渠道交叉表+堆叠柱状图；
        卡方独立性检验（性别×会员等级）
- 输出: cross_report.md + images/cross_*.png
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
from scipy import stats

warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'ecommerce', 'ecommerce.db'))
OUTPUT_MD = os.path.join(SCRIPT_DIR, 'cross_report.md')
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
    print("[字体] 使用: %s" % _name)
    plt.rcParams['font.sans-serif'] = [_name, 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
sns.set_style("whitegrid")
if CJK_FONT_FILE:
    plt.rcParams['font.sans-serif'] = [_name, 'DejaVu Sans']

conn = sqlite3.connect('file:%s?mode=ro' % DB_PATH.replace('\\', '/'), uri=True)

def sql(q):
    return pd.read_sql_query(q, conn)

# ================== 简易报告构建器 ==================
class Report:
    def __init__(self):
        self.parts = []
        self.toc = []
        self.n = 0

    def h1(self, t):
        self.n += 1
        self.parts.append("# %d. %s\n" % (self.n, t))
        self.toc.append("- %d %s" % (self.n, t))

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
        header = ["# %s\n" % title] + intro_lines + ['## 目录\n']
        header.append("\n".join(self.toc) + "\n\n---\n")
        with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
            f.write("\n".join(header) + "\n".join(self.parts))
        print("[OK] 报告：%s" % OUTPUT_MD)

R = Report()

GMV_FILTER = "o.order_status IN ('已完成','已发货')"

# ============================================================
# 1. 数据与口径
# ============================================================
R.h1("数据与口径")
R.text("多维交叉是描述性分析从「单变量」走向「变量组合」的一步：单看各省 GMV 只能回答“哪里卖得多”，"
       "省份 × 品类交叉后才能回答“哪里卖什么多”。本报告完成三组交叉：\n"
       "1. **省份 × 一级品类**：GMV 透视表 + 热力图，观察区域品类结构；\n"
       "2. **会员等级 × 渠道**：订单量交叉表 + 堆叠柱状图，观察不同等级用户的触达渠道偏好；\n"
       "3. **性别 × 会员等级**：卡方独立性检验，判断两分类变量是否相关。\n\n"
       "**口径**：GMV = 有效订单（已完成 + 已发货）的明细小计 `order_items.subtotal` 合计，不含运费；"
       "一级品类经 `categories` 自关联（`c2.parent_id = c1.category_id`）上卷得到。")

# ============================================================
# 2. 省份 × 一级品类 GMV
# ============================================================
R.h1("省份 × 一级品类 GMV")

q_cross = """SELECT cu.province, c1.category_name AS 一级品类,
       ROUND(SUM(oi.subtotal), 2) AS gmv
FROM order_items oi
JOIN orders o     ON o.order_id = oi.order_id AND o.order_status IN ('已完成','已发货')
JOIN customers cu ON cu.customer_id = o.customer_id
JOIN products p   ON p.product_id = oi.product_id
JOIN categories c2 ON c2.category_id = p.category_id
JOIN categories c1 ON c1.category_id = c2.parent_id
GROUP BY cu.province, c1.category_name
ORDER BY cu.province, gmv DESC;"""

R.text("**SQL 代码：**")
R.code("sql", q_cross)
cross_df = sql(q_cross)
pivot_gmv = cross_df.pivot(index='province', columns='一级品类', values='gmv').fillna(0)
pivot_gmv = pivot_gmv.loc[pivot_gmv.sum(axis=1).sort_values(ascending=False).index]
pivot_show = pivot_gmv.copy()
pivot_show['合计'] = pivot_show.sum(axis=1)
R.text("**透视表（pandas `pivot`，单位：元）：**")
R.code("python", "cross_df.pivot(index='province', columns='一级品类', values='gmv')")
R.table(pivot_show.round(0).astype(int).reset_index().rename(columns={'province': '省份'}))

plt.figure(figsize=(10, 6))
sns.heatmap(pivot_gmv / 10000.0, annot=True, fmt='.1f', cmap='YlOrRd',
            linewidths=0.5, cbar_kws={'label': 'GMV（万元）'})
plt.title('Province x Category GMV Heatmap')
plt.ylabel('')
plt.tight_layout()
R.save_plt('cross_prov_cat_heatmap.png')
R.image('cross_prov_cat_heatmap.png', 'Province x Category GMV | 省份×一级品类 GMV 热力图（万元）')
R.text("**解释：** 热力图把透视表变成可直接扫读的矩阵——颜色越深贡献越高。"
       "读法有三种：按行看（某省的消费结构）、按列看（某品类的区域分布）、"
       "找异常深色格子（区域×品类的结构性机会，例如某省在母婴或美妆上显著高于其他省）。"
       "本数据中各省总人口与客户数不同，比较品类结构时建议再看行百分比，避免规模效应淹没结构差异。")

# 行百分比补充
pct = pivot_gmv.div(pivot_gmv.sum(axis=1), axis=0) * 100
R.text("**行百分比（各省 GMV 的品类构成，%）：**")
R.table(pct.round(1).reset_index().rename(columns={'province': '省份'}))

# ============================================================
# 3. 会员等级 × 渠道
# ============================================================
R.h1("会员等级 × 渠道")

q_lc = """SELECT c.member_level, o.channel, COUNT(*) AS n_orders
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
GROUP BY c.member_level, o.channel;"""
R.text("**SQL 代码：**")
R.code("sql", q_lc)
lc = sql(q_lc)
level_order = ['普通', '白银', '黄金', '钻石']
ct = pd.crosstab(lc['member_level'], lc['channel']).reindex(level_order)
R.text("**交叉表（订单数，pandas `crosstab`，等级按业务序排列）：**")
R.table(ct.reset_index().rename(columns={'member_level': '会员等级'}))
ct_pct = ct.div(ct.sum(axis=1), axis=0) * 100
R.text("**行百分比（各等级内部的渠道分布，%）：**")
R.table(ct_pct.round(1).reset_index().rename(columns={'member_level': '会员等级'}))

fig, ax = plt.subplots(figsize=(9, 5))
bottom = np.zeros(len(ct))
colors = sns.color_palette('Set2', len(ct.columns))
for col, color in zip(ct.columns, colors):
    vals = ct[col].values
    ax.bar(ct.index, vals, bottom=bottom, label=col, color=color)
    bottom += vals
ax.set_title('Member Level x Channel (stacked orders)')
ax.set_ylabel('orders')
ax.legend(title='channel')
plt.tight_layout()
R.save_plt('cross_level_channel_stack.png')
R.image('cross_level_channel_stack.png', 'Member Level x Channel | 会员等级×渠道堆叠柱状图')
R.text("**解释：** 堆叠柱状图同时承载两个维度——柱高是该等级订单总量，色带是渠道构成。"
       "若各色带比例在不同等级间几乎一致，说明渠道偏好与会员等级无关（同质）；"
       "若高等级明显偏向某渠道（如 APP 占比随等级上升），说明重度用户沉淀在该渠道，"
       "渠道运营应分层施策。判读比例差异时以行百分比表为准，肉眼容易被柱高差带偏。")

# ============================================================
# 4. 卡方独立性检验：性别 × 会员等级
# ============================================================
R.h1("卡方独立性检验：性别 × 会员等级")
R.text("交叉表只看比例是描述，卡方检验则回答“观察到的分布差异能否用随机波动解释”。"
       "原假设 H₀：性别与会员等级相互独立；p < 0.05 拒绝 H₀，认为两者相关。")

q_gg = "SELECT gender, member_level FROM customers;"
gg = sql(q_gg)
obs = pd.crosstab(gg['gender'], gg['member_level'])[level_order]
R.text("**观察频数表：**")
R.table(obs.reset_index().rename(columns={'gender': '性别'}))

chi2, p, dof, expected = stats.chi2_contingency(obs)
n = obs.values.sum()
k = min(obs.shape) - 1
cramer_v = np.sqrt(chi2 / (n * k))
exp_df = pd.DataFrame(expected, index=obs.index, columns=obs.columns).round(1)

R.text("**Python 代码：**")
R.code("python", """from scipy import stats
obs = pd.crosstab(customers['gender'], customers['member_level'])
chi2, p, dof, expected = stats.chi2_contingency(obs)
cramer_v = np.sqrt(chi2 / (obs.values.sum() * (min(obs.shape)-1)))""")
R.text("**期望频数表（H₀ 成立时的理论值）：**")
R.table(exp_df.reset_index().rename(columns={'gender': '性别'}))
R.text("**检验结果：**")
R.text("- χ² = %.4f，自由度 = %d，p 值 = %.4f\n" % (chi2, dof, p)
       + "- Cramér's V = %.4f\n" % cramer_v
       + ("- 结论：p ≥ 0.05，**不能拒绝**独立性假设，性别与会员等级无显著关联。\n" if p >= 0.05
          else "- 结论：p < 0.05，**拒绝**独立性假设，性别与会员等级存在显著关联。\n"))
R.text("**解释：** 卡方统计量 = Σ(观察-期望)²/期望，自由度 = (行数-1)×(列数-1)。"
       "p 值回答“有没有关系”，Cramér's V 回答“关系有多强”（0.1 弱 / 0.3 中 / 0.5 强），"
       "大样本下微小的真实差异也会得到极小 p 值，所以两个数要一起看。"
       "使用前提：期望频数不宜过小（经验法则：所有格子期望 ≥ 1，且 80%% 格子 ≥ 5），"
       "本表最小期望频数 = %.1f，满足条件。" % expected.min())

# ============================================================
# 5. 小结
# ============================================================
R.h1("小结")
R.text("- **透视表 + 热力图**是多维交叉的标准武器：SQL 出长表，pandas `pivot` 出宽表，seaborn 上色；\n"
       "- **交叉表 + 堆叠柱状图**适合「构成对比」，比例判读以行百分比为准；\n"
       "- **卡方检验**把“看起来有差异”升级为“统计上站得住”，并配 Cramér's V 报告效应量；\n"
       "- 更高维的交叉（省 × 品类 × 等级）透视表会迅速稀疏，应转为分组 Top-N 或留待 L2 建模。")

R.write("L1 多维交叉分析报告", [
    "- **数据来源**：`data/ecommerce/ecommerce.db`（SQLite，只读连接）",
    "- **对应主题**：多维交叉\n",
])
conn.close()
