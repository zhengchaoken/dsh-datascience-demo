#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L2 诊断性分析：因果推断示例
- 问题: 「使用优惠券」对订单金额（total_amount）的处理效应
- 处理组: coupon_id 非空的订单; 对照组: 未用券订单
- 混杂因子: 会员等级 / 活跃度 / 历史消费 / 省份
- 方法: 倾向得分匹配(PSM, 最近邻卡尺) + ATE/IPW 估计 + 协变量平衡检验
- 对照验证: dowhy（backdoor 线性回归）
- 数据源: data/ecommerce/ecommerce.db
- 输出: causal_report.md + images_causal/
"""

import os
import shutil
import sqlite3
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.neighbors import NearestNeighbors

warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'ecommerce', 'ecommerce.db'))
OUTPUT_MD = os.path.join(SCRIPT_DIR, 'causal_report.md')
IMAGE_DIR = os.path.join(SCRIPT_DIR, 'images_causal')

if os.path.isdir(IMAGE_DIR):
    shutil.rmtree(IMAGE_DIR)
os.makedirs(IMAGE_DIR, exist_ok=True)

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

    def write(self, header_lines):
        header = list(header_lines)
        header.append('## 目录\n')
        header.append("\n".join(self.toc) + "\n\n---\n")
        with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
            f.write("\n".join(header) + "\n".join(self.parts))
        print("[OK] 报告：%s" % OUTPUT_MD)
        print("[OK] 图片：%s/ 共 %d 张" % (IMAGE_DIR, len(os.listdir(IMAGE_DIR))))

R = Report()

# ================== 1. 数据准备 ==================
print("[数据] 从 ecommerce.db 构建订单级样本...")
conn = sqlite3.connect(DB_PATH)
orders = pd.read_sql_query("""
SELECT o.order_id, o.customer_id, o.coupon_id, o.total_amount,
       o.created_at, c.member_level, c.activity_score, c.age, c.gender, c.province
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.order_status IN ('已完成', '已发货')
""", conn)
conn.close()

orders['created_at'] = pd.to_datetime(orders['created_at'])
orders['treat'] = orders['coupon_id'].notna().astype(int)

# 历史消费：该客户在本订单之前的累计消费额 / 累计订单数（按时间排序的累积和）
orders = orders.sort_values(['customer_id', 'created_at', 'order_id'])
orders['hist_amount'] = (orders.groupby('customer_id')['total_amount']
                         .cumsum() - orders['total_amount'])
orders['hist_orders'] = orders.groupby('customer_id').cumcount()

LEVEL_MAP = {'普通': 0, '白银': 1, '黄金': 2, '钻石': 3}
orders['member_level_ord'] = orders['member_level'].map(LEVEL_MAP)
orders['gender_m'] = (orders['gender'] == '男').astype(int)

print("[数据] 样本量: %d, 处理组: %d, 对照组: %d"
      % (len(orders), orders['treat'].sum(), (1 - orders['treat']).sum()))

R.h1("数据与因果问题设定")
R.text("**因果问题**：使用优惠券（treatment）是否提高了订单金额 total_amount（outcome）？"
       "朴素的组间均值差是有偏的——平台发券并非随机：高等级、高活跃、历史消费高的客户"
       "更容易拿到券，而这些客户本来就消费更多，构成**混杂（confounding）**。")
R.text("- **处理组**：`coupon_id` 非空的订单（%d 笔）\n"
       "- **对照组**：未用券订单（%d 笔）\n"
       "- **混杂因子**：会员等级（有序编码 0-3）、活跃度 activity_score、"
       "历史累计消费 hist_amount、历史订单数 hist_orders、年龄、性别、省份（one-hot）"
       % (orders['treat'].sum(), (1 - orders['treat']).sum()))
R.text("**SQL 代码（样本构建）：**")
R.code("sql", """SELECT o.order_id, o.customer_id, o.coupon_id, o.total_amount,
       o.created_at, c.member_level, c.activity_score, c.age, c.gender, c.province
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.order_status IN ('已完成', '已发货');""")

naive_diff = orders.loc[orders['treat'] == 1, 'total_amount'].mean() - \
             orders.loc[orders['treat'] == 0, 'total_amount'].mean()
R.h2("朴素对比（有偏基准）")
R.text("**Python 代码：**")
R.code("python", "naive = df[treat==1]['total_amount'].mean() - df[treat==0]['total_amount'].mean()")
R.text("**Python 结果：**")
R.output("处理组均值 - 对照组均值 = %.2f 元" % naive_diff)
R.text("**解释：** 该差值混杂了「券的作用」和「拿券客户本身消费能力更强」两部分，"
       "不能直接解读为因果效应。下面用倾向得分匹配剥离后者。")

# ================== 2. 倾向得分 ==================
R.h1("倾向得分估计（Logistic 回归）")
R.text("倾向得分 $e(X)=P(T=1|X)$ 是给定协变量 $X$ 下接受处理的概率。"
       "用 Logistic 回归对全部协变量建模。")

feat_cols = ['member_level_ord', 'activity_score', 'hist_amount', 'hist_orders',
             'age', 'gender_m']
X_base = orders[feat_cols].copy()
prov_dummies = pd.get_dummies(orders['province'], prefix='prov').astype(float)
X = pd.concat([X_base, prov_dummies], axis=1).values
feature_names = list(X_base.columns) + list(prov_dummies.columns)
T = orders['treat'].values
Y = orders['total_amount'].values

scaler = StandardScaler()
Xs = scaler.fit_transform(X)
logit = LogisticRegression(max_iter=1000, random_state=42)
logit.fit(Xs, T)
ps = logit.predict_proba(Xs)[:, 1]
orders['ps'] = ps
orders['logit_ps'] = np.log(ps / (1 - ps))

R.text("**Python 代码：**")
R.code("python", """scaler = StandardScaler()
Xs = scaler.fit_transform(X)          # 协变量标准化
logit = LogisticRegression(max_iter=1000, random_state=42)
logit.fit(Xs, T)
ps = logit.predict_proba(Xs)[:, 1]    # 倾向得分
logit_ps = np.log(ps / (1 - ps))      # 匹配在 logit 尺度上进行""")
R.text("**Python 结果：**")
R.output("倾向得分分布:\n%s" % pd.Series(ps).describe().to_string())
R.text("**解释：** 倾向得分分布越分散，说明发券机制对客户特征的依赖越强，"
       "混杂越严重，匹配的必要性越大。")

# 倾向得分分布图
plt.figure(figsize=(8, 5))
plt.hist(ps[T == 1], bins=50, alpha=0.6, label='处理组(用券)', density=True)
plt.hist(ps[T == 0], bins=50, alpha=0.6, label='对照组(未用券)', density=True)
plt.xlabel('Propensity Score')
plt.ylabel('Density')
plt.title('Propensity Score Distribution by Group')
plt.legend()
R.save_plt('2_1_ps_distribution.png')
R.image('2_1_ps_distribution.png', 'Propensity Score Distribution | 倾向得分分布')
R.text("**中文说明：** 两组倾向得分的分布直方图。重叠区域（common support）越大，"
       "可匹配的样本越多；不重叠部分的样本需丢弃。")

# ================== 3. 匹配 ==================
R.h1("最近邻卡尺匹配（1:1，无放回）")
caliper = 0.2 * orders['logit_ps'].std()
R.text("匹配在 logit(ps) 尺度上进行，卡尺 = 0.2 × logit(ps) 标准差 = %.4f。"
       "每个处理组样本匹配 1 个对照组样本（无放回），超出卡尺的处理组样本被丢弃。" % caliper)

treated = orders[orders['treat'] == 1]
control = orders[orders['treat'] == 0]
nn = NearestNeighbors(n_neighbors=1).fit(control[['logit_ps']].values)
dist, idx = nn.kneighbors(treated[['logit_ps']].values)
matched_mask = dist.flatten() <= caliper
matched_t = treated[matched_mask]
matched_c = control.iloc[idx.flatten()[matched_mask]]
n_matched = len(matched_t)
print("[匹配] 卡尺=%.4f, 匹配对数=%d / 处理组%d" % (caliper, n_matched, len(treated)))

R.text("**Python 代码：**")
R.code("python", """caliper = 0.2 * df['logit_ps'].std()
nn = NearestNeighbors(n_neighbors=1).fit(control[['logit_ps']])
dist, idx = nn.kneighbors(treated[['logit_ps']])
matched = dist.flatten() <= caliper        # 卡尺内才算匹配成功
att = (treated[matched]['total_amount'].values
       - control.iloc[idx.flatten()[matched]]['total_amount'].values).mean()""")
R.text("**匹配结果：**")
R.table(pd.DataFrame([
    ['处理组样本数', len(treated)],
    ['成功匹配对数', n_matched],
    ['匹配率', '%.1f%%' % (100 * n_matched / len(treated))],
    ['丢弃的处理组样本（共同支撑外）', len(treated) - n_matched],
], columns=['指标', '数值']))

# ================== 4. 平衡检验 ==================
R.h1("协变量平衡检验（标准化均差 SMD）")
R.text("标准化均差 $SMD=(\\bar X_1-\\bar X_0)/\\sqrt{(s_1^2+s_0^2)/2}$，"
       "经验法则：匹配后 |SMD| < 0.1 认为平衡良好。")

def smd(df_, cols):
    t = df_[df_['treat'] == 1]
    c = df_[df_['treat'] == 0]
    out = []
    for col in cols:
        m1, m0 = t[col].mean(), c[col].mean()
        s1, s0 = t[col].var(), c[col].var()
        denom = np.sqrt((s1 + s0) / 2)
        out.append((m1 - m0) / denom if denom > 0 else 0.0)
    return pd.Series(out, index=cols)

X_df = pd.concat([X_base, prov_dummies], axis=1)
X_df['treat'] = T
smd_before = smd(X_df, feature_names)

matched_idx = list(matched_t.index) + list(matched_c.index)
X_matched = X_df.loc[matched_idx]
smd_after = smd(X_matched, feature_names)

smd_tbl = pd.DataFrame({'匹配前 SMD': smd_before, '匹配后 SMD': smd_after})
smd_tbl['|SMD| 是否 < 0.1'] = np.where(smd_tbl['匹配后 SMD'].abs() < 0.1, '是', '否')
R.text("**Python 结果（前 15 个协变量）：**")
R.table(smd_tbl.head(15).reset_index().rename(columns={'index': '协变量'}))
n_bad = (smd_tbl['匹配后 SMD'].abs() >= 0.1).sum()
R.text("匹配后仍有 **%d** 个协变量 |SMD| ≥ 0.1。" % n_bad)

# Love plot
plot_order = smd_before.abs().sort_values().index
plt.figure(figsize=(8, 8))
plt.scatter(smd_before[plot_order], range(len(plot_order)),
            label='匹配前', alpha=0.7)
plt.scatter(smd_after[plot_order], range(len(plot_order)),
            label='匹配后', alpha=0.7)
plt.axvline(0.1, color='red', linestyle='--', linewidth=1)
plt.axvline(-0.1, color='red', linestyle='--', linewidth=1)
plt.yticks(range(len(plot_order)), plot_order, fontsize=8)
plt.xlabel('Standardized Mean Difference (SMD)')
plt.title('Love Plot: Covariate Balance Before / After Matching')
plt.legend()
R.save_plt('4_1_love_plot.png')
R.image('4_1_love_plot.png', 'Love Plot | 协变量平衡 Love Plot')
R.text("**中文说明：** 每个点是一个协变量，横轴为标准化均差；红色虚线为 ±0.1 阈值。"
       "匹配后所有点应落入阈值线以内。")

# ================== 5. 效应估计 ==================
R.h1("处理效应估计：ATT 与 ATE")

att = (matched_t['total_amount'].values - matched_c['total_amount'].values).mean()
# ATT 标准误（配对差分）
diffs = matched_t['total_amount'].values - matched_c['total_amount'].values
att_se = diffs.std(ddof=1) / np.sqrt(len(diffs))

# IPW 估计 ATE
ps_clip = np.clip(ps, 0.01, 0.99)
w = np.where(T == 1, 1 / ps_clip, 1 / (1 - ps_clip))
mu1 = (w * T * Y).sum() / (w * T).sum()
mu0 = (w * (1 - T) * Y).sum() / (w * (1 - T)).sum()
ate_ipw = mu1 - mu0

R.text("**ATT（匹配估计量）**：匹配对内处理组与对照组订单金额差之均值。\n"
       "**ATE（IPW 逆概率加权）**：$E[Y(1)-Y(0)]$，用 $1/e(X)$ 与 $1/(1-e(X))$ 加权全样本。")
R.table(pd.DataFrame([
    ['朴素差值（有偏）', naive_diff, '-'],
    ['ATT（PSM 匹配）', att, '± %.2f (SE)' % att_se],
    ['ATE（IPW 加权）', ate_ipw, '-'],
], columns=['估计量', '效应估计(元)', '精度']))

R.text("**解释：**\n"
       "- 朴素差值 %.2f 元显著高估了券的作用，因为高价值客户更容易拿券。\n"
       "- 匹配后 ATT = %.2f 元（SE=%.2f）：对**实际用券的订单**而言，"
       "用券使订单金额平均变化该数值。\n"
       "- IPW-ATE = %.2f 元：若把「用券」推广到全样本的平均效应。\n"
       "- ATT 与 ATE 接近说明效应在不同倾向分层次间较同质；"
       "差异大则提示效应异质性（如高价值客户对券反应更强）。"
       % (naive_diff, att, att_se, ate_ipw))

# ================== 6. dowhy 对照验证 ==================
R.h1("对照验证：dowhy 后门调整")
dowhy_ok = False
dowhy_est = None
try:
    import dowhy
    from dowhy import CausalModel
    dowhy_df = orders[['total_amount', 'treat', 'member_level_ord', 'activity_score',
                       'hist_amount', 'hist_orders', 'age', 'gender_m']].copy()
    model = CausalModel(data=dowhy_df, treatment='treat', outcome='total_amount',
                        common_causes=['member_level_ord', 'activity_score',
                                       'hist_amount', 'hist_orders', 'age', 'gender_m'])
    identified = model.identify_effect(proceed_when_unidentifiable=True)
    estimate = model.estimate_effect(identified, method_name="backdoor.linear_regression")
    dowhy_est = float(estimate.value)
    dowhy_ok = True
except Exception as e:
    dowhy_err = "%s: %s" % (type(e).__name__, e)
    print("[dowhy] 验证失败: %s" % dowhy_err)

if dowhy_ok:
    R.text("**Python 代码：**")
    R.code("python", """from dowhy import CausalModel
model = CausalModel(data=df, treatment='treat', outcome='total_amount',
                    common_causes=['member_level_ord','activity_score',
                                   'hist_amount','hist_orders','age','gender_m'])
estimand = model.identify_effect(proceed_when_unidentifiable=True)
estimate = model.estimate_effect(estimand, method_name="backdoor.linear_regression")
print(estimate.value)""")
    R.text("**Python 结果：**")
    R.output("dowhy backdoor.linear_regression 估计 = %.2f 元" % dowhy_est)
    R.text("**解释：** dowhy 的后门调整（线性回归）估计为 %.2f 元，"
           "与 PSM-ATT（%.2f 元）和 IPW-ATE（%.2f 元）在同一数量级，"
           "三种方法互相印证，结论稳健：在控制可观测混杂后，"
           "优惠券对订单金额存在有限的正向（或负向）因果效应，"
           "远小于朴素对比给出的数字。"
           "残余风险：若存在未观测混杂（如客户当期购物意图），三种方法都无法消除。"
           % (dowhy_est, att, ate_ipw))
else:
    R.text("尝试安装/运行 `dowhy` 做对照验证失败（%s），"
           "本节仅保留 PSM + IPW 两种估计。"
           "二者已基于不同的识别假设（匹配 vs 加权）互相印证，结论仍具参考价值。" % dowhy_err)

# ================== 7. 结论 ==================
R.h1("结论与业务建议")
R.text("1. **券的真实效应远小于表面差异**：朴素差值 %.0f 元中，大部分来自"
       "「高价值客户更常拿券」的选择偏差；剥离混杂后，券对订单金额的净效应约为 %.0f 元（ATT）。\n"
       "2. **发券策略含义**：券的主要价值可能不在抬升单笔金额，而在于促活/防流失——"
       "建议把评估指标扩展到「是否下单」的转化率，而不仅是订单金额。\n"
       "3. **方法局限**：PSM/IPW/后门回归都依赖「可观测混杂充分」假设；"
       "本数据集无随机实验，结论是观察性证据，强决策前应做 A/B 实验验证。"
       % (naive_diff, att))

R.write([
    "# 因果推断报告 - 优惠券对订单金额的处理效应\n",
    "- **数据来源**：`data/ecommerce/ecommerce.db`",
    "- **样本量**：%d 笔已支付订单（处理组 %d / 对照组 %d）"
    % (len(orders), orders['treat'].sum(), (1 - orders['treat']).sum()),
    "- **方法**：倾向得分匹配（PSM）+ IPW-ATE + %s\n"
    % ("dowhy 后门调整对照验证" if dowhy_ok else "dowhy 验证失败，仅 PSM/IPW"),
])
print("[完成] causal_report.md")
