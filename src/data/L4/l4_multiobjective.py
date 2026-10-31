#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多目标优化：促销折扣决策
- 数据源: data/ecommerce/ecommerce.db（各一级品类历史量价成本）
- 决策变量: 各一级品类折扣率 d_c ∈ [0.85, 1.00]
- 目标(冲突): GMV 最大化 / 毛利率最大化 / 优惠成本最小化
- 方法: 加权扫描法求帕累托前沿（利用目标按品类可分离性逐品类独立求解），
        二维投影两对目标各一图，标注 knee point 推荐方案
- 输出: multiobjective_report.md + images_prescriptive/mo_*.png
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

SEED = 42
np.random.seed(SEED)

# ================== 配置区 ==================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'ecommerce', 'ecommerce.db'))
OUTPUT_MD = os.path.join(SCRIPT_DIR, 'multiobjective_report.md')
IMAGE_DIR = os.path.join(SCRIPT_DIR, 'images_prescriptive')
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

    def write(self, header_lines):
        header = list(header_lines)
        header.append('<a id="toc"></a>\n## 目录\n')
        header.append("\n".join(self.toc) + "\n\n---\n")
        with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
            f.write("\n".join(header) + "\n".join(self.parts))
        print("[OK] 报告：%s" % OUTPUT_MD)

R = Report()

# ================== 1. 数据：各一级品类的量价成本基线 ==================
conn = sqlite3.connect(DB_PATH)

cat = pd.read_sql_query("""
SELECT pc.category_id AS cid, pc.category_name AS cname,
       SUM(oi.quantity) AS qty,
       SUM(oi.subtotal) AS gmv,
       SUM(p.cost * oi.quantity) AS cost,
       SUM(oi.subtotal) / SUM(oi.quantity) AS avg_price
FROM order_items oi
JOIN orders o ON oi.order_id = o.order_id AND o.order_status IN ('已完成','已发货')
JOIN products p ON oi.product_id = p.product_id
JOIN categories c ON p.category_id = c.category_id
JOIN categories pc ON c.parent_id = pc.category_id
GROUP BY pc.category_id ORDER BY pc.category_id
""", conn)

DAYS = 531  # 数据覆盖天数，用于折算日均基线
cat['daily_qty'] = cat['qty'] / DAYS
cat['daily_cost'] = cat['cost'] / DAYS
N_CAT = len(cat)
print("[数据] 一级品类数 %d" % N_CAT)
print(cat.to_string(index=False))

# ================== 2. 需求弹性与目标函数 ==================
# 价格弹性：业务先验假设（数据库无价格实验，故文档化为假设值）
# 弹性越大，降价带来的销量放大越强。服饰美妆弹性高，母婴/食品相对刚性。
ELASTICITY = {'手机数码': 1.5, '家用电器': 1.2, '服装鞋帽': 2.2,
              '美妆个护': 2.0, '食品饮料': 1.0, '母婴用品': 1.1}
cat['elasticity'] = cat['cname'].map(ELASTICITY).fillna(1.5)

D_GRID = np.round(np.arange(0.85, 1.0001, 0.01), 2)  # 折扣率决策网格

def cat_objectives(row, d):
    """单品类在折扣率 d 下的日度目标：(GMV, 毛利, 优惠成本)"""
    e = row['elasticity']
    mult = 1.0 + e * (1.0 - d)          # 销量放大系数（线性弹性模型）
    qty = row['daily_qty'] * mult
    price = row['avg_price'] * d        # 折后成交价
    gmv = qty * price
    profit = gmv - qty * (row['daily_cost'] / row['daily_qty'])
    promo_cost = qty * row['avg_price'] * (1 - d)  # 让利总额
    return gmv, profit, promo_cost

# 预计算各品类各折扣档的目标
per_cat = []
for _, row in cat.iterrows():
    objs = np.array([cat_objectives(row, d) for d in D_GRID])  # (len(grid), 3)
    per_cat.append({'name': row['cname'], 'grid': D_GRID, 'obj': objs})

def total_objectives(d_vec):
    g = p = c = 0.0
    for i, d in enumerate(d_vec):
        gi, pi, ci = cat_objectives(cat.iloc[i], d)
        g += gi; p += pi; c += ci
    return g, p, c

# ================== 3. 加权扫描法 ==================
# 目标归一化（用两个极端解的值域）
gmv0, prof0, cost0 = total_objectives([1.0] * N_CAT)             # 全原价
gmv1, prof1, cost1 = total_objectives([0.85] * N_CAT)            # 全 85 折
NORM = np.array([gmv1 - gmv0, abs(prof0 - prof1), cost1 - cost0])

def weighted_solve(w):
    """权重 w=(w_gmv, w_profit, w_cost)，最小化 -w1*GMV -w2*PROFIT + w3*COST。
    目标按品类可分离 → 逐品类独立枚举最优折扣。"""
    best_d = []
    for i in range(N_CAT):
        obj = per_cat[i]['obj'] / NORM  # 归一化
        score = -w[0] * obj[:, 0] - w[1] * obj[:, 1] + w[2] * obj[:, 2]
        best_d.append(D_GRID[int(np.argmin(score))])
    return best_d

# 权重单纯形网格扫描
steps = 10
weight_grid = []
for i in range(steps + 1):
    for j in range(steps + 1 - i):
        k = steps - i - j
        weight_grid.append((i / steps, j / steps, k / steps))

solutions = {}
for w in weight_grid:
    d_vec = weighted_solve(w)
    g, p, c = total_objectives(d_vec)
    solutions[(tuple(d_vec))] = (g, p, c, w)

sdf = pd.DataFrame([
    {'d_vec': k, 'gmv': v[0], 'profit': v[1], 'cost': v[2]}
    for k, v in solutions.items()
])
sdf['margin_rate'] = sdf['profit'] / sdf['gmv']
print("[求解] 权重网格 %d 组 → 去重后方案 %d 个" % (len(weight_grid), len(sdf)))

# ================== 4. 帕累托筛选 ==================
def pareto_mask(df):
    """最大化 gmv、最大化 profit、最小化 cost 意义下的非支配解"""
    pts = df[['gmv', 'profit', 'cost']].values
    n = len(pts)
    mask = np.ones(n, dtype=bool)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if (pts[j, 0] >= pts[i, 0] and pts[j, 1] >= pts[i, 1] and pts[j, 2] <= pts[i, 2]
                    and (pts[j, 0] > pts[i, 0] or pts[j, 1] > pts[i, 1] or pts[j, 2] < pts[i, 2])):
                mask[i] = False
                break
    return mask

sdf['pareto'] = pareto_mask(sdf)
pf = sdf[sdf['pareto']].copy()
print("[帕累托] 非支配解 %d 个" % len(pf))

# Knee point：归一化后离乌托邦点（各目标最优）最近的帕累托解
def knee_point(pf_df):
    pts = pf_df[['gmv', 'profit', 'cost']].values.astype(float)
    lo = pts.min(axis=0); hi = pts.max(axis=0)
    span = np.where(hi - lo > 0, hi - lo, 1)
    # 成本取反向，统一为"越大越好"
    norm = (pts - lo) / span
    norm[:, 2] = 1 - norm[:, 2]
    utopia = np.ones(3)
    dist = np.linalg.norm(utopia - norm, axis=1)
    return pf_df.index[int(np.argmin(dist))], int(np.argmin(dist))

knee_idx, knee_pos = knee_point(pf)
knee = pf.loc[knee_idx]
print("[Knee] GMV=%.0f 毛利=%.0f 成本=%.0f" % (knee['gmv'], knee['profit'], knee['cost']))

# ================== 5. 报告 ==================
R.h1("问题定义：促销折扣的多目标权衡")
R.text("大促期间需要为 6 个一级品类分别设定折扣率 d ∈ [0.85, 1.00]。三个目标互相冲突：")
R.text("1. **GMV 最大化**：降价放量，卖得越多 GMV 越高；")
R.text("2. **毛利最大化**：降价压缩单件毛利，过度放量未必补得回来；")
R.text("3. **优惠成本最小化**：让利总额直接影响营销费用。")
R.text("不存在同时最优的解，目标是求出**帕累托前沿**并给出 knee point 推荐方案。")

R.h2("品类基线（历史 531 天）")
show = cat[['cname', 'qty', 'gmv', 'cost', 'avg_price', 'daily_qty', 'elasticity']].copy()
show.columns = ['一级品类', '累计销量(件)', '累计GMV(元)', '累计成本(元)',
                '件单价(元)', '日均销量(件/天)', '弹性假设']
R.table(show)
R.text("**说明：** 价格弹性为业务先验假设（数据库中无价格实验数据）："
       "服装鞋帽 2.2、美妆个护 2.0（冲动消费型，弹性高），"
       "手机数码 1.5、家用电器 1.2，食品饮料 1.0、母婴用品 1.1（刚需，弹性低）。"
       "销量放大系数 `mult = 1 + e·(1−d)`，线性弹性模型。")

R.h1("方法与求解")
R.text("**加权扫描法**：在权重单纯形 w=(w_GMV, w_毛利, w_成本)、步长 0.1 的 %d 组权重上，"
       "最小化 `−w₁·GMV − w₂·毛利 + w₃·优惠成本`（目标先做极差归一化）。" % len(weight_grid))
R.text("由于目标函数按品类求和、决策变量按品类独立，加权问题**可分离**："
       "每组权重下逐品类在 16 档折扣网格上独立枚举，"
       "避免了 %d^%d 的组合爆炸。" % (len(D_GRID), N_CAT))
R.code("python",
       "for w in weight_grid:                    # 权重单纯形扫描\n"
       "    for c in categories:                 # 可分离：逐品类独立求解\n"
       "        d_c = argmin over grid of (-w1*GMV_c - w2*Profit_c + w3*Cost_c)\n"
       "    solutions[d_vec] = total_objectives(d_vec)\n"
       "pareto_front = non_dominated(solutions)  # 非支配筛选")

R.h1("帕累托前沿")
R.text("去重后共 %d 个方案，其中非支配（帕累托）解 %d 个。" % (len(sdf), len(pf)))

R.h2("投影一：GMV × 毛利率")
plt.figure(figsize=(8, 6))
plt.scatter(sdf['gmv'] / 1e4, sdf['margin_rate'] * 100, s=18, c='#BBBBBB', label='被支配解')
plt.scatter(pf['gmv'] / 1e4, pf['margin_rate'] * 100, s=40, c='#4C72B0', label='帕累托前沿')
plt.scatter([knee['gmv'] / 1e4], [knee['margin_rate'] * 100], s=200, marker='*',
            c='#C44E52', label='Knee Point', zorder=5)
plt.xlabel('GMV（万元/天）'); plt.ylabel('毛利率（%）')
plt.title('Pareto Front: GMV vs Margin Rate')
plt.legend()
R.save_plt('mo_1_pareto_gmv_margin.png')
R.image('mo_1_pareto_gmv_margin.png', '帕累托前沿投影：GMV × 毛利率')
R.text("**中文说明：** 横轴 = 日 GMV（万元）；纵轴 = 毛利率（%%）。灰色为被支配解，"
       "蓝色为非支配解，红星为 knee point。")
R.text("**解释：** 前沿呈左上-右下走向：GMV 越高毛利率越低，二者此消彼长。"
       "前沿中段斜率最大的位置（knee）意味着“再压 1 个点毛利率换来的 GMV 增量开始锐减”。")

R.h2("投影二：GMV × 优惠成本")
plt.figure(figsize=(8, 6))
plt.scatter(sdf['gmv'] / 1e4, sdf['cost'] / 1e4, s=18, c='#BBBBBB', label='被支配解')
plt.scatter(pf['gmv'] / 1e4, pf['cost'] / 1e4, s=40, c='#55A868', label='帕累托前沿')
plt.scatter([knee['gmv'] / 1e4], [knee['cost'] / 1e4], s=200, marker='*',
            c='#C44E52', label='Knee Point', zorder=5)
plt.xlabel('GMV（万元/天）'); plt.ylabel('优惠成本（万元/天）')
plt.title('Pareto Front: GMV vs Promotion Cost')
plt.legend()
R.save_plt('mo_2_pareto_gmv_cost.png')
R.image('mo_2_pareto_gmv_cost.png', '帕累托前沿投影：GMV × 优惠成本')
R.text("**中文说明：** 横轴 = 日 GMV（万元）；纵轴 = 日优惠成本（万元）。")
R.text("**解释：** GMV 与优惠成本同向增长——高 GMV 方案必然伴随高让利。"
       "该投影帮助回答“每多花 1 万元让利能换回多少 GMV”的预算效率问题。")

R.h1("Knee Point 推荐方案")
R.text("Knee point 定义：三目标归一化后（成本取反向）离乌托邦点 (1,1,1) 欧氏距离最近的帕累托解，"
       "代表三目标最均衡的折中。")
knee_d = knee['d_vec']
plan = pd.DataFrame({
    '一级品类': cat['cname'],
    '推荐折扣率': ['%.2f' % d for d in knee_d],
    '折扣力度': ['%.0f 折' % (d * 10) for d in knee_d],
})
R.table(plan)
base_gmv = gmv0
R.table(pd.DataFrame([
    ['日 GMV', '%.0f 元' % knee['gmv'], '原价基线 %.0f 元，提升 %.1f%%' % (base_gmv, (knee['gmv'] / base_gmv - 1) * 100)],
    ['日毛利', '%.0f 元' % knee['profit'], '毛利率 %.2f%%' % (knee['margin_rate'] * 100)],
    ['日优惠成本', '%.0f 元' % knee['cost'], '占 GMV %.2f%%' % (knee['cost'] / knee['gmv'] * 100)],
], columns=['指标', '推荐方案取值', '说明']))
R.text("**解读：** 高弹性品类（服装鞋帽、美妆个护）应给到更深折扣以换取放量；"
       "刚需品类（食品饮料、母婴用品）保持接近原价，避免无效让利。"
       "若业务方更偏 GMV（如冲榜）或更偏毛利（如季末利润考核），"
       "可沿前沿向相应方向移动选点。")

R.write([
    "# 多目标优化：促销折扣决策\n",
    "- **数据来源**：`data/ecommerce/ecommerce.db`（6 个一级品类历史量价成本）",
    "- **决策变量**：各品类折扣率 d ∈ [0.85, 1.00]，共 %d 档" % len(D_GRID),
    "- **方法**：加权扫描 + 非支配筛选，权重单纯形 %d 组 → 帕累托解 %d 个\n" % (len(weight_grid), len(pf)),
])

conn.close()
print("[OK] 图片新增：mo_*.png")
