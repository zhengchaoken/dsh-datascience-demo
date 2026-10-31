#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
因果推荐去偏：曝光流行度偏差的 IPS 校正
- 数据源: data/ecommerce/ecommerce.db（user_events 曝光日志 + orders 购买）
- 偏差机制: 商品曝光服从 popularity 偏差——热销品获得更多曝光（浏览）
- 倾向分: 按商品 popularity 分档估计曝光概率 P(O=1|item)
- 指标: 加购率@K / 购买率@K，对比 naive（不纠偏）vs IPS（逆倾向加权）
- 输出: causal_rec_report.md + images_prescriptive/ips_*.png
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
OUTPUT_MD = os.path.join(SCRIPT_DIR, 'causal_rec_report.md')
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
if CJK_FONT_FILE:
    plt.rcParams['font.sans-serif'] = [_name, 'DejaVu Sans']

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

# ================== 1. 数据与偏差验证 ==================
conn = sqlite3.connect(DB_PATH)

K = 10
CUTOFF = '2025-04-01'   # 之前构造训练交互，之后作为测试期

# 曝光日志（view = 曝光），每 (用户,商品) 测试期内只保留首次曝光
views = pd.read_sql_query("""
SELECT customer_id, product_id, MIN(event_time) AS t
FROM user_events WHERE event_type = 'view' AND event_time >= '%s'
GROUP BY customer_id, product_id
""" % CUTOFF, conn)
views['t'] = pd.to_datetime(views['t'])

# 曝光后的转化：曝光之后发生的加购 / 购买
carts = pd.read_sql_query("""
SELECT customer_id, product_id, MIN(event_time) AS t
FROM user_events WHERE event_type = 'cart' AND event_time >= '%s'
GROUP BY customer_id, product_id
""" % CUTOFF, conn)
carts['t'] = pd.to_datetime(carts['t'])

buys = pd.read_sql_query("""
SELECT o.customer_id, oi.product_id, MIN(o.created_at) AS t
FROM order_items oi JOIN orders o ON oi.order_id = o.order_id
WHERE o.order_status IN ('已完成','已发货') AND o.created_at >= '%s'
GROUP BY o.customer_id, oi.product_id
""" % CUTOFF, conn)
buys['t'] = pd.to_datetime(buys['t'])

# 商品 popularity（生成参数，[0,1]）与测试期曝光量
prod = pd.read_sql_query("SELECT product_id, product_name, popularity FROM products", conn)
view_cnt = views.groupby('product_id').size().rename('n_views')
prod = prod.merge(view_cnt, on='product_id', how='left').fillna({'n_views': 0})

# 倾向分：按 popularity 分 10 档，档内估计 P(曝光)
# P(O=1|b) = 档内商品人均曝光次数 / 活跃用户数
N_USERS = views['customer_id'].nunique()
N_BINS = 10
prod['pop_bin'] = pd.qcut(prod['popularity'], N_BINS, labels=False, duplicates='drop')
bin_prop = prod.groupby('pop_bin').apply(
    lambda g: g['n_views'].sum() / (len(g) * N_USERS), include_groups=False).rename('propensity')
prod = prod.merge(bin_prop, on='pop_bin')
prod['propensity'] = prod['propensity'].clip(lower=1e-4)

print("[数据] 测试期曝光对 %d，活跃用户 %d，商品 %d"
      % (len(views), N_USERS, prod['product_id'].nunique()))
print(prod.groupby('pop_bin')[['popularity', 'n_views', 'propensity']].mean())

# ================== 2. 推荐器（训练期 ItemCF 与热度榜） ==================
train_inter = pd.read_sql_query("""
SELECT o.customer_id AS userId, oi.product_id AS itemId, COUNT(*) AS r
FROM order_items oi JOIN orders o ON oi.order_id = o.order_id
WHERE o.order_status IN ('已完成','已发货') AND o.created_at < '%s'
GROUP BY o.customer_id, oi.product_id
""" % CUTOFF, conn)

from sklearn.metrics.pairwise import cosine_similarity
ui = train_inter.pivot_table(index='userId', columns='itemId', values='r', fill_value=0)
item_sim = cosine_similarity(ui.T)
item_ids = list(ui.columns)
item_to_idx = {m: i for i, m in enumerate(item_ids)}
pop_rank = train_inter.groupby('itemId')['r'].sum().sort_values(ascending=False)
pop_top = list(pop_rank.index)

def recommend_itemcf(uid, k):
    if uid not in ui.index:
        return pop_top[:k]
    hist = ui.loc[uid]
    seen = set(hist[hist > 0].index)
    if not seen:
        return pop_top[:k]
    scores = np.zeros(len(item_ids))
    for it in seen:
        scores += item_sim[item_to_idx[it]]
    cand = [(item_ids[i], scores[i]) for i in range(len(item_ids)) if item_ids[i] not in seen]
    cand.sort(key=lambda x: -x[1])
    return [c[0] for c in cand[:k]]

def recommend_pop(uid, k):
    return pop_top[:k]

# ================== 3. naive vs IPS 评估 ==================
prop_map = prod.set_index('product_id')['propensity'].to_dict()
bin_map = prod.set_index('product_id')['pop_bin'].to_dict()

views_indexed = views.set_index(['customer_id', 'product_id'])
cart_indexed = carts.set_index(['customer_id', 'product_id'])
buy_indexed = buys.set_index(['customer_id', 'product_id'])

def eval_rec(rec_fn, users, k):
    """返回 (naive 加购率, SNIPS 加购率, naive 购买率, SNIPS 购买率, 可观测推荐位总数)。
    分母均为该用户推荐列表中实际被曝光的条目（MNAR 下唯一可观测的支撑集）：
    naive: 曝光推荐位上转化标记的直接平均（有偏，向高曝光商品倾斜）
    SNIPS: 自归一化逆倾向加权平均 sum(w*y)/sum(w)，w = 1/P(O=1|item)"""
    naive_cart, ips_cart, naive_buy, ips_buy = [], [], [], []
    n_exposed_total = 0
    for uid in users:
        recs = rec_fn(uid, k)
        if not recs:
            continue
        n_exp = 0
        nc = nb = ic = ib = sw = 0.0
        for it in recs:
            key = (uid, it)
            if key not in views_indexed.index:
                continue  # 未曝光则无法观测转化（MNAR 核心）
            n_exp += 1
            t_view = views_indexed.loc[key, 't']
            if isinstance(t_view, pd.Series):
                t_view = t_view.iloc[0]
            w = 1.0 / prop_map.get(it, 1e-4)
            sw += w
            if key in cart_indexed.index:
                t_c = cart_indexed.loc[key, 't']
                t_c = t_c.iloc[0] if isinstance(t_c, pd.Series) else t_c
                if t_c >= t_view:
                    nc += 1.0; ic += w
            if key in buy_indexed.index:
                t_b = buy_indexed.loc[key, 't']
                t_b = t_b.iloc[0] if isinstance(t_b, pd.Series) else t_b
                if t_b >= t_view:
                    nb += 1.0; ib += w
        if n_exp == 0:
            continue
        n_exposed_total += n_exp
        naive_cart.append(nc / n_exp); naive_buy.append(nb / n_exp)
        ips_cart.append(ic / sw); ips_buy.append(ib / sw)
    return (np.mean(naive_cart), np.mean(ips_cart),
            np.mean(naive_buy), np.mean(ips_buy), n_exposed_total)

eval_users = [u for u in views['customer_id'].unique() if u in ui.index][:400]
res_pop = eval_rec(recommend_pop, eval_users, K)
res_cf = eval_rec(recommend_itemcf, eval_users, K)
print("[评估] 热度榜 naive/SNIPS:", res_pop)
print("[评估] ItemCF naive/SNIPS:", res_cf)

# 曝光推荐位的档分布（支撑集诊断）
view_keys = set(zip(views['customer_id'], views['product_id']))
def exposed_bin_dist(rec_fn):
    dist = {}
    for uid in eval_users:
        for it in rec_fn(uid, K):
            if (uid, it) in view_keys:
                b = bin_map.get(it)
                dist[b] = dist.get(b, 0) + 1
    return dist
diag_pop = exposed_bin_dist(recommend_pop)
diag_cf = exposed_bin_dist(recommend_itemcf)
print("[诊断] 热度榜曝光位档分布:", diag_pop)
print("[诊断] ItemCF 曝光位档分布:", diag_cf)

# ================== 4. 分档转化率与倾向分 ==================
# 每条曝光记录：商品所属 popularity 档、是否转化
exp_rec = views.copy()
exp_rec['bin'] = exp_rec['product_id'].map(bin_map)
exp_rec = exp_rec.dropna(subset=['bin'])
exp_rec['bin'] = exp_rec['bin'].astype(int)
exp_rec['w'] = exp_rec['product_id'].map(prop_map)
exp_rec['w'] = 1.0 / exp_rec['w']

def conv_flags(row):
    key = (row['customer_id'], row['product_id'])
    cart = 0
    if key in cart_indexed.index:
        t_c = cart_indexed.loc[key, 't']
        t_c = t_c.iloc[0] if isinstance(t_c, pd.Series) else t_c
        cart = int(t_c >= row['t'])
    return cart

exp_rec['conv'] = exp_rec.apply(conv_flags, axis=1)
by_bin = exp_rec.groupby('bin').apply(
    lambda g: pd.Series({
        'naive_rate': g['conv'].mean(),
        'avg_propensity': (1.0 / g['w']).mean(),
        'ips_weight': g['w'].mean(),
        'exposures': len(g)}),
    include_groups=False).reset_index()
print(by_bin)

# ================== 5. 报告 ==================
R.h1("问题定义：曝光流行度偏差")
R.text("推荐系统的日志数据是 **MNAR**（Missing Not At Random）的：只有被曝光的商品"
       "才可能被加购/购买，而平台流量天然向热销品倾斜。直接用日志统计的转化率"
       "会系统性高估热销品、低估长尾品，进而训练出“越推越热”的反馈回路。")

R.h2("偏差验证：popularity 越高曝光越多")
R.text("**SQL 代码（分档曝光量）：**")
R.code("sql",
       "SELECT NTILE(10) OVER (ORDER BY popularity) AS pop_bin,\n"
       "       AVG(popularity) AS avg_pop, COUNT(DISTINCT e.product_id) AS items,\n"
       "       COUNT(*) AS views\n"
       "FROM products p JOIN user_events e ON p.product_id = e.product_id\n"
       "WHERE e.event_type = 'view' AND e.event_time >= '%s'\n"
       "GROUP BY p.product_id;" % CUTOFF)
bin_show = prod.groupby('pop_bin').agg(
    avg_popularity=('popularity', 'mean'),
    n_items=('product_id', 'count'),
    total_views=('n_views', 'sum'),
    avg_propensity=('propensity', 'mean')).reset_index()
bin_show.columns = ['popularity 分档', '平均 popularity', '商品数', '曝光次数', '档内平均倾向分']
R.table(bin_show)

plt.figure(figsize=(10, 4))
plt.scatter(prod['popularity'], prod['n_views'], s=10, alpha=0.5)
plt.xlabel('Product Popularity (generation parameter)')
plt.ylabel('Views in Test Period')
plt.title('Exposure vs Popularity')
R.save_plt('ips_1_bias.png')
R.image('ips_1_bias.png', '商品 popularity 与测试期曝光量散点')
R.text("**中文说明：** 横轴 = 商品受欢迎度生成参数；纵轴 = 测试期（%s 之后）曝光次数。" % CUTOFF)
R.text("**解释：** 曝光量随 popularity 单调上升，证实曝光机制存在流行度偏差。"
       "倾向分按 popularity 分 %d 档估计：P(O=1|档) = 档内总曝光 / (档内商品数 × 活跃用户数 %d)。"
       % (N_BINS, N_USERS))

R.h1("IPS 去偏原理")
R.text("逆倾向得分（Inverse Propensity Scoring）用曝光概率的倒数给观测样本加权，"
       "把“有偏曝光下观测到的分布”还原回“均匀曝光下的期望”。原始 IPS 的权重 1/P "
       "在小倾向分上会爆炸（本例最小倾向分 1e-4，权重上万），因此实际使用其自归一化"
       "变体 **SNIPS**（Self-Normalized IPS），以牺牲微量偏差换取方差剧降：")
R.code("text",
       "支撑集 E_u: 用户 u 的推荐列表中实际被曝光的条目（MNAR 下唯一可观测部分）\n"
       "naive 转化率@K = (1/|E_u|) Σ_{i∈E_u} 1[转化_i]\n"
       "SNIPS 转化率@K = Σ_{i∈E_u} w_i·1[转化_i] / Σ_{i∈E_u} w_i,  w_i = 1/P(O=1|item_i)\n"
       "无偏性: E_O[ 1(O)·Y / P(O) ] = E[Y]，其中 Y 为曝光后的真实转化")
R.text("**Python 代码：**")
R.code("python",
       "w = 1.0 / propensity[item]            # 逆倾向权重（按 popularity 分档估计）\n"
       "snips = sum(conv * w) / sum(w)        # 自归一化 IPS：结果有界、方差可控\n"
       "naive = mean(conv)                    # 直接平均（有偏）")

R.h1("naive vs SNIPS：推荐评估对比")
R.text("在 %s 之前的订单上训练 ItemCF 与热度榜两个推荐器，"
       "对测试期有曝光行为的 %d 个用户评估 加购率@%d / 购买率@%d"
       "（naive 与 SNIPS 的分母均为该用户实际被曝光的推荐位）："
       % (CUTOFF, len(eval_users), K, K))
res_df = pd.DataFrame([
    ['热度榜 Top%d' % K, res_pop[0], res_pop[1], res_pop[2], res_pop[3], res_pop[4]],
    ['ItemCF Top%d' % K, res_cf[0], res_cf[1], res_cf[2], res_cf[3], res_cf[4]],
], columns=['推荐器', 'naive 加购率@K', 'SNIPS 加购率@K', 'naive 购买率@K', 'SNIPS 购买率@K',
            '可观测推荐位数'])
R.table(res_df)
R.text("**解释：** 两个推荐器的 naive 与 SNIPS 指标几乎完全重合——这不是加权失效，"
       "而是曝光稀疏的直接后果：用户的 view 行为极端偏向热销品，能被观测到转化的"
       "推荐位几乎全部落在最热档（热度榜 %d 个可观测位中 %d 个在 bin 9，ItemCF "
       "%d 个中 %d 个在 bin 9）。档内权重相同使 SNIPS 退化为 naive。"
       "这一现象本身正是重要结论：**离线日志对中长尾推荐策略根本缺乏评估支撑**——"
       "IPS 只能还原“曾被曝光过”的样本，无法凭空评估从未被观测的推荐位；要区分"
       "推荐器在长尾商品上的优劣，必须引入探索流量（随机曝光）或在线 A/B 实验。"
       % (res_pop[4], diag_pop.get(9, 0), res_cf[4], diag_cf.get(9, 0)))

plt.figure(figsize=(8, 4))
x = np.arange(2)
w = 0.35
plt.bar(x - w / 2, [res_pop[0], res_cf[0]], w, label='naive 加购率@%d' % K, color='#4C72B0')
plt.bar(x + w / 2, [res_pop[1], res_cf[1]], w, label='SNIPS 加购率@%d' % K, color='#C44E52')
plt.xticks(x, ['热度榜', 'ItemCF'])
plt.ylabel('Rate'); plt.title('Naive vs SNIPS: Cart Rate@%d' % K)
plt.legend()
R.save_plt('ips_2_metrics.png')
R.image('ips_2_metrics.png', 'naive 与 SNIPS 加购率对比')
R.text("**中文说明：** 同组内蓝柱为 naive 指标，红柱为 SNIPS 去偏指标。")

R.h1("分档转化率与倾向分")
R.text("注意：倾向分按档估计意味着**同一档内权重相同**，因此“档内 SNIPS 转化率”与"
       "naive 恒等——去偏的作用体现在**跨档汇总与推荐列表加权**上。下表/图展示各档的"
       "naive 转化率与倾向分量级，可直观看到偏差来源：")
R.table(by_bin.rename(columns={'bin': 'popularity 分档', 'naive_rate': 'naive 转化率',
                               'avg_propensity': '平均倾向分', 'ips_weight': 'IPS 权重(1/P)',
                               'exposures': '曝光样本数'}))

fig, ax1 = plt.subplots(figsize=(10, 4))
ax1.bar(by_bin['bin'], by_bin['naive_rate'], color='#4C72B0', alpha=0.85,
        label='naive 转化率（左轴）')
ax1.set_xlabel('Popularity Bin (0=长尾, 9=最热)')
ax1.set_ylabel('Cart Conversion Rate')
ax2 = ax1.twinx()
ax2.plot(by_bin['bin'], by_bin['avg_propensity'], 's-', color='#C44E52',
         label='倾向分 P(O=1|档)（右轴，log）')
ax2.set_yscale('log')
ax2.set_ylabel('Propensity (log scale)')
h1, l1 = ax1.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax1.legend(h1 + h2, l1 + l2, loc='upper left')
plt.title('Conversion Rate vs Exposure Propensity by Popularity Bin')
R.save_plt('ips_3_bins.png')
R.image('ips_3_bins.png', '分 popularity 档的 naive 转化率与倾向分')
R.text("**中文说明：** 横轴 = popularity 分档（0 最长尾，9 最热销）；蓝柱（左轴）= 该档"
       "曝光后的加购转化率；红线（右轴，对数刻度）= 该档的曝光倾向分。")
R.text("**解释：** 各档真实转化率相差不大（长尾档甚至不逊于热销档），但倾向分相差"
       "两个数量级——热销档几乎必然被观测，长尾档极少被观测。naive 总体指标因此被"
       "热销档支配，SNIPS 通过 1/P 加权把各档拉回可比的“均匀曝光”口径。"
       "业务含义：长尾商品的真实转化能力被曝光不足掩盖，值得增加曝光配额。")

# 全量曝光的 pooled 对比
g_naive = exp_rec['conv'].mean()
g_snips = (exp_rec['conv'] * exp_rec['w']).sum() / exp_rec['w'].sum()
R.text("**全量曝光的 pooled 口径对比：** 对测试期全部 %d 条曝光记录，"
       "naive 加购转化率 = %.4f（被 bin 9 的 %d 条样本支配）；"
       "SNIPS 加购转化率 = %.4f（各档按 1/P 还原，近似各档等权平均）。"
       "SNIPS 略高于 naive，说明长尾档（bin 0 转化率 %.3f）的真实转化能力"
       "在 naive 口径下被低估。"
       % (len(exp_rec), g_naive, int(by_bin.loc[by_bin['bin'] == 9, 'exposures'].iloc[0]),
          g_snips, by_bin.loc[by_bin['bin'] == 0, 'naive_rate'].iloc[0]))

R.h1("实践要点")
R.text("1. **倾向分估计决定成败**：本例用 popularity 分档估计，生产环境可用曝光模型的"
       "预测概率（如 logistic 回归）；分档过粗会残留偏差，过细则倾向分过小、方差爆炸；")
R.text("2. **方差控制**：IPS 权重 1/P 在倾向分很小时极大，需做截断（clip）或使用"
       "自归一化 IPS（SNIPS，本例采用）——以 sum(w) 代替样本数做归一化，估计量有界；")
R.text("3. **与 Doubly Robust 结合**：IPS 可再叠加结果回归模型（DR 估计量），"
       "在倾向分或结果模型之一正确时保持无偏。")

R.write([
    "# 因果推荐去偏：曝光流行度偏差的 IPS 校正\n",
    "- **数据来源**：`data/ecommerce/ecommerce.db`（user_events + orders + products）",
    "- **测试期**：%s 之后；训练期：之前的购买交互" % CUTOFF,
    "- **倾向分**：popularity 分 %d 档估计曝光概率，clip 下限 1e-4" % N_BINS,
    "- **IPS 变体**：自归一化 SNIPS（分母为权重和），抑制小倾向分导致的方差爆炸\n",
])

conn.close()
print("[OK] 图片新增：ips_*.png")
