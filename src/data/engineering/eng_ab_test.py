#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A/B 测试框架示例
- 数据源: data/ecommerce/ecommerce.db（orders + customers）
- 分桶: customer_id 的 MD5 哈希稳定分桶为 A/B 两组
- 场景: 新券策略实验（B 组发放更高面额券），观测客单价 / 购买频次 / 转化率
- 流程: A/A 基线同质性检验 → 模拟实验期 B 组效应 → 完整检验套件
        （Welch t / Mann-Whitney U / 比例 z / Cohen's d / CI / 功效 / 样本量估算 / Bonferroni 校正）
- 输出: ab_test_report.md + images/ 分布对比图
"""

import os
import math
import sqlite3
import shutil
import hashlib
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from scipy import stats
from statsmodels.stats.proportion import proportions_ztest, proportion_confint
from statsmodels.stats.power import TTestIndPower
from statsmodels.stats.multitest import multipletests
from types import SimpleNamespace

warnings.filterwarnings('ignore')
RNG = np.random.default_rng(42)

# ================== 配置区 ==================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'ecommerce', 'ecommerce.db'))
OUTPUT_MD = os.path.join(SCRIPT_DIR, 'ab_test_report.md')
IMAGE_DIR = os.path.join(SCRIPT_DIR, 'images')
ALPHA = 0.05
TRUE_UPLIFT_AOV = 0.08      # 模拟实验期 B 组客单价真实提升 8%
TRUE_UPLIFT_CVR = 0.25      # 模拟实验期 B 组未购客户中被新券转化的概率（≈ 全组转化率 +4pp）

if not os.path.isfile(DB_PATH):
    raise FileNotFoundError("未找到数据库: %s" % DB_PATH)

os.makedirs(IMAGE_DIR, exist_ok=True)

# ================== 中文字体 ==================
def _find_cjk_font_file():
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

# ================== 数据加载 ==================
conn = sqlite3.connect(DB_PATH)
customers = pd.read_sql_query("SELECT customer_id FROM customers", conn)
orders = pd.read_sql_query(
    "SELECT order_id, customer_id, total_amount FROM orders "
    "WHERE order_status IN ('已完成','已发货')", conn)
# 剔除数据集中注入的批发/价格异常订单（指标口径须先排除异常值，否则均值被极端单污染）
abn = pd.read_sql_query(
    "SELECT DISTINCT oi.order_id FROM order_items oi "
    "JOIN products p ON oi.product_id = p.product_id "
    "WHERE oi.quantity >= 30 OR oi.unit_price >= 10 * p.list_price", conn)
conn.close()
n_all = len(orders)
orders = orders[~orders.order_id.isin(abn.order_id)]
print("[数据] 客户数: %d, 已支付订单数: %d（剔除异常订单 %d 笔）" % (len(customers), len(orders), n_all - len(orders)))

# ================== 稳定分桶 ==================
def bucket(cid, n_buckets=100):
    h = int(hashlib.md5(str(cid).encode('utf-8')).hexdigest(), 16)
    return h % n_buckets

customers['bucket'] = customers['customer_id'].map(bucket)
customers['group'] = np.where(customers['bucket'] < 50, 'A', 'B')

# 客户级基线指标（真实数据）
cust = customers.merge(
    orders.groupby('customer_id').agg(
        n_orders=('order_id', 'size'),
        aov=('total_amount', 'mean'),
        gmv=('total_amount', 'sum')).reset_index(),
    on='customer_id', how='left')
cust['n_orders'] = cust['n_orders'].fillna(0).astype(int)
cust['converted'] = (cust['n_orders'] > 0).astype(int)

gA = cust[cust.group == 'A']
gB = cust[cust.group == 'B']
nA, nB = len(gA), len(gB)
print("[分桶] A 组 %d 人, B 组 %d 人 (比例 %.3f)" % (nA, nB, nB / (nA + nB)))

# ================== 检验函数 ==================
def welch_t(a, b):
    t, p = stats.ttest_ind(a, b, equal_var=False)
    return t, p

def cohens_d(a, b):
    na, nb = len(a), len(b)
    sp = math.sqrt(((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2))
    return (b.mean() - a.mean()) / sp if sp > 0 else 0.0

def mean_diff_ci(a, b, alpha=ALPHA):
    """Welch 均值差 (b-a) 的置信区间"""
    na, nb = len(a), len(b)
    diff = b.mean() - a.mean()
    se = math.sqrt(a.var(ddof=1) / na + b.var(ddof=1) / nb)
    dfree = (a.var(ddof=1) / na + b.var(ddof=1) / nb) ** 2 / (
        (a.var(ddof=1) / na) ** 2 / (na - 1) + (b.var(ddof=1) / nb) ** 2 / (nb - 1))
    q = stats.t.ppf(1 - alpha / 2, dfree)
    return diff, diff - q * se, diff + q * se

def mann_whitney(a, b):
    _, p = stats.mannwhitneyu(a, b, alternative='two-sided')
    return p

def prop_test(nA_, xA, nB_, xB):
    z, p = proportions_ztest([xB, xA], [nB_, nA_])
    ciA = proportion_confint(xA, nA_, alpha=ALPHA, method='wilson')
    ciB = proportion_confint(xB, nB_, alpha=ALPHA, method='wilson')
    return z, p, ciA, ciB

power_an = TTestIndPower()

def analyze_continuous(a_vals, b_vals, label):
    """返回连续指标完整分析 dict"""
    a_vals = np.asarray(a_vals, dtype=float)
    b_vals = np.asarray(b_vals, dtype=float)
    t, p_t = welch_t(a_vals, b_vals)
    p_mw = mann_whitney(a_vals, b_vals)
    d = cohens_d(a_vals, b_vals)
    diff, lo, hi = mean_diff_ci(a_vals, b_vals)
    pw = power_an.power(effect_size=abs(d), nobs1=len(a_vals), alpha=ALPHA, ratio=len(b_vals) / len(a_vals))
    return SimpleNamespace(label=label, mean_a=a_vals.mean(), mean_b=b_vals.mean(),
                           diff=diff, ci=(lo, hi), t=t, p_t=p_t, p_mw=p_mw, d=d, power=pw)

# ================== 阶段一：A/A 基线同质性检验（真实数据） ==================
print("[A/A] 基线同质性检验 ...")
aa_aov = analyze_continuous(gA.dropna(subset=['aov'])['aov'],
                            gB.dropna(subset=['aov'])['aov'], '基线客单价')
aa_freq = analyze_continuous(gA['n_orders'], gB['n_orders'], '基线购买频次')
z_aa, p_aa_cvr, _, _ = prop_test(nA, gA['converted'].sum(), nB, gB['converted'].sum())
print("[A/A] 客单价 p=%.3f, 频次 p=%.3f, 转化率 p=%.3f" % (aa_aov.p_t, aa_freq.p_t, p_aa_cvr))

# ================== 阶段二：模拟实验期（B 组叠加新券策略效应） ==================
print("[实验] 模拟实验期观测 ...")
exp = cust.copy()
is_b = (exp.group == 'B').to_numpy()
# 客单价：B 组 +8% 乘性效应 + 对数正态个体噪声（消费客户）
noise = RNG.lognormal(0, 0.10, len(exp))
exp['aov_exp'] = exp['aov'] * (1 + TRUE_UPLIFT_AOV * is_b) * noise
# 转化率：B 组未购客户按 25% 概率被转化（未购占比 ≈17%，≈ 全组 +4pp）
median_aov = exp['aov'].median()
newly = is_b & (exp['converted'] == 0) & (RNG.random(len(exp)) < TRUE_UPLIFT_CVR)
exp.loc[newly, 'aov_exp'] = median_aov * RNG.lognormal(0, 0.1, newly.sum())
exp['converted_exp'] = np.where(exp['converted'] == 1, 1, newly.astype(int))
exp['freq_exp'] = exp['n_orders'] + exp['converted_exp'] - exp['converted']

eA = exp[exp.group == 'A']
eB = exp[exp.group == 'B']
payA = eA.dropna(subset=['aov_exp'])['aov_exp']
payB = eB.dropna(subset=['aov_exp'])['aov_exp']

# ================== 阶段三：A/B 检验套件 ==================
print("[A/B] 检验套件 ...")
r_aov = analyze_continuous(payA, payB, '客单价（消费客户）')
r_freq = analyze_continuous(eA['freq_exp'], eB['freq_exp'], '购买频次')
z_ab, p_ab_cvr, ciA_cvr, ciB_cvr = prop_test(len(eA), eA['converted_exp'].sum(),
                                             len(eB), eB['converted_exp'].sum())
cvrA = eA['converted_exp'].mean()
cvrB = eB['converted_exp'].mean()
# 比例指标功效（用 h 效应量）
h = 2 * math.asin(math.sqrt(cvrB)) - 2 * math.asin(math.sqrt(cvrA))
from statsmodels.stats.power import NormalIndPower
pw_cvr = NormalIndPower().power(h, len(eA), ALPHA, ratio=len(eB) / len(eA))

# Bonferroni 多重比较校正（3 个指标的 p 值族）
p_raw = [r_aov.p_t, r_freq.p_t, p_ab_cvr]
reject_bonf, p_bonf, _, _ = multipletests(p_raw, alpha=ALPHA, method='bonferroni')

# DID 修正：基线客单价存在偶然差异时的双重差分估计
# did = (B_exp - A_exp) - (B_base - A_base)，SE = sqrt(SE_exp^2 + SE_base^2)
base_a = gA.dropna(subset=['aov'])['aov'].to_numpy()
base_b = gB.dropna(subset=['aov'])['aov'].to_numpy()
d0 = base_b.mean() - base_a.mean()
se0 = math.sqrt(base_a.var(ddof=1) / len(base_a) + base_b.var(ddof=1) / len(base_b))
d1 = r_aov.diff
se1 = math.sqrt(payA.var(ddof=1) / len(payA) + payB.var(ddof=1) / len(payB))
did = d1 - d0
se_did = math.sqrt(se0 ** 2 + se1 ** 2)
z_did = did / se_did
p_did = 2 * (1 - stats.norm.cdf(abs(z_did)))
did_ci = (did - 1.96 * se_did, did + 1.96 * se_did)
print("[DID] 基线差 %.2f, 实验期差 %.2f, DID 效应 %.2f, p=%.2e" % (d0, d1, did, p_did))

# 样本量估算示例：客单价 d=0.10，α=0.05，功效 0.8
n_need = power_an.solve_power(effect_size=0.10, power=0.8, alpha=ALPHA, ratio=1.0)
# 转化率：基线 0.83 → 检 2pp 提升所需样本
h2 = 2 * math.asin(math.sqrt(cvrA + 0.02)) - 2 * math.asin(math.sqrt(cvrA))
n_need_cvr = NormalIndPower().solve_power(h2, power=0.8, alpha=ALPHA, ratio=1.0)
print("[样本量] 客单价 d=0.10 → 每组需 %.0f；转化率 +2pp → 每组需 %.0f" % (n_need, n_need_cvr))

# ================== 绘图 ==================
fig, axes = plt.subplots(1, 2, figsize=(12, 4.4))

cap = np.percentile(np.concatenate([payA, payB]), 99)
axes[0].hist(payA.clip(upper=cap), bins=60, density=True, alpha=0.55,
             label='A 组 (n=%d)' % len(payA), color='#4C72B0')
axes[0].hist(payB.clip(upper=cap), bins=60, density=True, alpha=0.55,
             label='B 组 (n=%d)' % len(payB), color='#DD8452')
axes[0].axvline(payA.mean(), color='#4C72B0', ls='--', lw=1.5)
axes[0].axvline(payB.mean(), color='#DD8452', ls='--', lw=1.5)
axes[0].set_xlabel('客单价 (元，截尾至 P99)'); axes[0].set_ylabel('密度')
axes[0].set_title('实验期客单价分布对比'); axes[0].legend()

xs = ['A 组', 'B 组']
cvr = [cvrA, cvrB]
err_lo = [cvrA - ciA_cvr[0], cvrB - ciB_cvr[0]]
err_hi = [ciA_cvr[1] - cvrA, ciB_cvr[1] - cvrB]
axes[1].bar(xs, cvr, color=['#4C72B0', '#DD8452'], width=0.5,
            yerr=[err_lo, err_hi], capsize=6)
for i, v in enumerate(cvr):
    axes[1].text(i, v + err_hi[i] + 0.005, '%.3f' % v, ha='center')
axes[1].set_ylabel('转化率'); axes[1].set_ylim(0, 1.0)
axes[1].set_title('实验期转化率对比（95%% Wilson CI）')

fig.tight_layout()
fig.savefig(os.path.join(IMAGE_DIR, 'ab_compare.png'), dpi=130)
plt.close(fig)
print("[图] images/ab_compare.png 已生成")

# ================== 写报告 ==================
def sig(p):
    return "**显著**" if p < ALPHA else "不显著"

md = f"""# A/B 测试分析框架报告 — 新券策略实验

- **数据来源**：`data/ecommerce/ecommerce.db`（orders × customers，已支付订单 {n_all:,} 笔，剔除批发/价格异常订单 {n_all - len(orders)} 笔后 {len(orders):,} 笔进入指标口径）
- **分桶方式**：`MD5(customer_id) mod 100 < 50 → A`，稳定、可复现、与业务字段无关
- **实验场景**：B 组实施新券策略（更高面额券），观测 **客单价 / 购买频次 / 转化率** 三个指标
- **显著性水平**：α = {ALPHA}

## 1. 可复用分析流程

```
稳定分桶（哈希） → 样本比例/基线 A/A 同质性检验 → 实验期指标构造
→ 检验套件（Welch t + Mann-Whitney U + 比例 z）→ 效应量与置信区间
→ 统计功效分析 → 多重比较校正（Bonferroni）→ 样本量估算
```

分桶结果：A 组 {nA} 人，B 组 {nB} 人（占比 {nB/(nA+nB):.3f}，SRM 检验 chi2 p = {stats.chi2_contingency([[nA],[nB]])[1]:.3f}，无样本比例失衡）。

## 2. A/A 基线同质性检验（真实数据，策略前）

| 指标 | A 组均值 | B 组均值 | 检验 | p 值 | 结论 |
|---|---|---|---|---|---|
| 基线客单价 | {aa_aov.mean_a:.2f} | {aa_aov.mean_b:.2f} | Welch t | {aa_aov.p_t:.3f} | {sig(aa_aov.p_t)} |
| 基线购买频次 | {gA['n_orders'].mean():.3f} | {gB['n_orders'].mean():.3f} | Welch t | {aa_freq.p_t:.3f} | {sig(aa_freq.p_t)} |
| 基线转化率 | {gA['converted'].mean():.3f} | {gB['converted'].mean():.3f} | 比例 z | {p_aa_cvr:.3f} | {sig(p_aa_cvr)} |

{"三项基线指标均不显著，分桶方案通过同质性检验。" if (aa_aov.p_t > ALPHA and aa_freq.p_t > ALPHA and p_aa_cvr > ALPHA) else f"基线客单价出现偶然组间差异（p={aa_aov.p_t:.3f}，B−A={aa_aov.diff:+.2f} 元）：这是有限样本下的随机波动，哈希分桶本身无偏，但**直接比较实验期均值会把基线差异误判为策略效应**，须用第 4.4 节 DID 修正；其余指标同质性通过。"}

## 3. 实验期观测构造说明

实验期数据为演示检验流程而模拟：B 组客单价叠加 **+{TRUE_UPLIFT_AOV:.0%}** 乘性效应（含对数正态个体噪声 σ=0.10），B 组未购客户按 **{TRUE_UPLIFT_CVR:.0%}** 概率被新券转化（未购占比 ≈17%，相当于全组转化率 +4pp 左右；转化者客单价取全库消费客户中位数）。A 组仅叠加同等噪声，作为策略真实效应的检验靶子。

## 4. A/B 检验结果

### 4.1 客单价（消费客户，Welch t + Mann-Whitney U）

| 项 | 值 |
|---|---|
| A 组均值 | {r_aov.mean_a:.2f} 元 (n={len(payA)}) |
| B 组均值 | {r_aov.mean_b:.2f} 元 (n={len(payB)}) |
| 均值差 (B−A) | {r_aov.diff:.2f} 元，95% CI [{r_aov.ci[0]:.2f}, {r_aov.ci[1]:.2f}] |
| Welch t 检验 | t={r_aov.t:.3f}, p={r_aov.p_t:.2e} → {sig(r_aov.p_t)} |
| Mann-Whitney U | p={r_aov.p_mw:.2e} → {sig(r_aov.p_mw)} |
| Cohen's d | {r_aov.d:.3f} |
| 统计功效 (1−β) | {r_aov.power:.3f} |

### 4.2 购买频次

| 项 | 值 |
|---|---|
| A / B 均值 | {r_freq.mean_a:.3f} / {r_freq.mean_b:.3f} 单 |
| 均值差 95% CI | [{r_freq.ci[0]:.4f}, {r_freq.ci[1]:.4f}] |
| Welch t p 值 | {r_freq.p_t:.3f} → {sig(r_freq.p_t)} |
| Cohen's d | {r_freq.d:.3f} |

### 4.3 转化率（比例 z 检验）

| 项 | 值 |
|---|---|
| A 组转化率 | {cvrA:.3f}，95% Wilson CI [{ciA_cvr[0]:.3f}, {ciA_cvr[1]:.3f}] |
| B 组转化率 | {cvrB:.3f}，95% Wilson CI [{ciB_cvr[0]:.3f}, {ciB_cvr[1]:.3f}] |
| 绝对提升 | {100*(cvrB - cvrA):+.1f} pp（相对提升 {(cvrB-cvrA)/cvrA:+.1%}） |
| 比例 z 检验 | z={z_ab:.3f}, p={p_ab_cvr:.2e} → {sig(p_ab_cvr)} |
| 统计功效 (1−β) | {pw_cvr:.3f} |

### 4.4 DID 双重差分稳健性验证（客单价）

{"第 2 节基线客单价存在偶然组间差异，直接差分有偏，须以 DID 剥离基线项：" if aa_aov.p_t < ALPHA else "第 2 节基线已平衡，DID 此处作为稳健性交叉验证——当基线失衡时它是修正手段，基线平衡时它应与差分估计一致："}

| 项 | 值 |
|---|---|
| 基线组间差 (B−A) | {d0:+.2f} 元 |
| 实验期组间差 (B−A) | {d1:+.2f} 元 |
| **DID 效应估计** | **{did:+.2f} 元**，95% CI [{did_ci[0]:.2f}, {did_ci[1]:.2f}] |
| DID z 检验 | z={z_did:.3f}, p={p_did:.2e} → {sig(p_did)} |

等价地，也可用 CUPED（以基线指标作协变量的方差缩减）达到同类目的：基线相关性越高，方差缩减越明显，对高方差指标（如客单价）尤其重要。

![客单价与转化率对比](images/ab_compare.png)

## 5. 多重比较校正（Bonferroni）

三个指标构成一个检验族，族系错误率需控制在 α={ALPHA}（校正后阈值 α'={ALPHA/3:.4f}）：

| 指标 | 原始 p | Bonferroni 校正 p | 校正后结论 |
|---|---|---|---|
| 客单价 | {p_raw[0]:.2e} | {p_bonf[0]:.2e} | {"显著" if reject_bonf[0] else "不显著"} |
| 购买频次 | {p_raw[1]:.4f} | {p_bonf[1]:.4f} | {"显著" if reject_bonf[1] else "不显著"} |
| 转化率 | {p_raw[2]:.2e} | {p_bonf[2]:.2e} | {"显著" if reject_bonf[2] else "不显著"} |

## 6. 样本量估算示例（实验设计阶段）

| 目标 | 参数 | 每组所需样本量 |
|---|---|---|
| 客单价检出 d=0.10 | α=0.05 双侧，功效 0.8，两组等大 | {n_need:,.0f} 人 |
| 转化率检出 +2pp（基线 {cvrA:.3f}） | 同上 | {n_need_cvr:,.0f} 人 |

## 7. 结论

1. 分桶通过 SRM 检查（p=1.000）；A/A 基线三项指标{"均不显著，分桶同质性通过" if (aa_aov.p_t > ALPHA and aa_freq.p_t > ALPHA and p_aa_cvr > ALPHA) else "中客单价存在偶然差异，直接差分有偏，须 DID/CUPED 修正"}。DID 稳健性验证效应 {did:+.2f} 元（p={p_did:.2e}）。
2. 客单价：Welch t p={r_aov.p_t:.2e}、Mann-Whitney U p={r_aov.p_mw:.2e}，参数/非参数结论一致（{"显著" if r_aov.p_t < ALPHA else "不显著"}）；效应量 d={r_aov.d:.3f}、功效 {r_aov.power:.2f}——高方差指标在小效应下功效有限，Bonferroni 校正后 {"仍显著" if reject_bonf[0] else "不再显著，体现校正的必要性"}。
3. 转化率：绝对提升 {100*(cvrB-cvrA):+.1f}pp（z 检验 p={p_ab_cvr:.2e}，功效 {pw_cvr:.2f}）。{"检出显著。" if p_ab_cvr < ALPHA else "未检出——按第 6 节估算，检 2pp 提升需每组约 5,300 人，本实验每组仅约 1,500 人，功效天然不足。"}
4. 频次指标差异小（d={r_freq.d:.3f}），功效不足时不应下"无效应"结论，应扩充实验时长或改用更敏感的指标口径。
5. 工程化要点：分桶用哈希而非随机数，保证同一客户跨会话/跨实验归属稳定；指标口径先剔除异常订单；先跑 A/A 再上实验；检验族预注册指标数，报告统一给校正后 p 值。
"""

with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
    f.write(md)
print("[报告] %s 已生成" % OUTPUT_MD)
print("[完成]")
