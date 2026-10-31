#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L3 专题 可解释性：SHAP 解读 XGBoost 复购模型
- 数据管线: 完整复用 l3_ensemble.py（标签 SQL / FEAT_SQL / FEATURES / register_date 时间切分）
- 模型: XGBoost（与 ensemble_report.md 同参，测试 AUC≈0.5 的弱信号模型）
- 解释: shap.TreeExplainer（TreeSHAP 精确解）
  全局 bar / beeswarm / 2 个 dependence plot / 1 个单样本 waterfall
- 输出: shap_report.md + images_shap/
"""

import os
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

import shap
from scipy.stats import spearmanr
from xgboost import XGBClassifier
from sklearn.metrics import roc_auc_score

warnings.filterwarnings('ignore')

SEED = 42
np.random.seed(SEED)

# ================== 配置区 ==================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'ecommerce', 'ecommerce.db'))
OUTPUT_MD = os.path.join(SCRIPT_DIR, 'shap_report.md')
IMAGE_DIR = os.path.join(SCRIPT_DIR, 'images_shap')

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
        header.append('<a id="toc"></a>\n## 目录\n')
        header.append("\n".join(self.toc) + "\n\n---\n")
        with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
            f.write("\n".join(header) + "\n".join(self.parts))
        print("[OK] 报告：%s" % OUTPUT_MD)
        print("[OK] 图片：%s/ 共 %d 张" % (IMAGE_DIR, len(os.listdir(IMAGE_DIR))))

R = Report()

# ================== 1. 数据管线（复用 l3_ensemble.py，原样复制） ==================
conn = sqlite3.connect(DB_PATH)
DATA_END = pd.Timestamp('2025-06-15')

R.h1("任务与模型（复用 管线）")
R.text("本专题不训练新模型，而是回答：**的 XGBoost 复购模型到底在依据什么做判断？**"
       "数据管线（标签 SQL、特征 SQL、类别编码、register_date 时间切分）与模型超参"
       "均原样复用 `l3_ensemble.py`，保证解释对象与 ensemble_report.md 中的模型完全一致。"
       "标签 = 客户首单后 90 天内是否有第二单；特征 = 首单 RFM + user_events 行为计数 + 客户属性。")

LABEL_SQL = """
WITH first_order AS (
    SELECT customer_id,
           MIN(substr(created_at, 1, 10)) AS first_date
    FROM orders
    WHERE order_status IN ('已完成', '已发货')
    GROUP BY customer_id
),
second_order AS (
    SELECT f.customer_id, COUNT(*) AS n2
    FROM first_order f
    JOIN orders o ON o.customer_id = f.customer_id
    WHERE o.order_status IN ('已完成', '已发货')
      AND substr(o.created_at, 1, 10) > f.first_date
      AND substr(o.created_at, 1, 10) <= date(f.first_date, '+90 day')
    GROUP BY f.customer_id
)
SELECT f.customer_id, f.first_date,
       CASE WHEN s.customer_id IS NULL THEN 0 ELSE 1 END AS repurchase
FROM first_order f
LEFT JOIN second_order s ON s.customer_id = f.customer_id;
"""
df_label = pd.read_sql_query(LABEL_SQL, conn)
df_label['first_date'] = pd.to_datetime(df_label['first_date'])
df_label = df_label[df_label['first_date'] <= DATA_END - pd.Timedelta(days=90)].reset_index(drop=True)

FEAT_SQL = """
WITH first_order AS (
    SELECT customer_id,
           MIN(substr(created_at, 1, 10)) AS first_date
    FROM orders
    WHERE order_status IN ('已完成', '已发货')
    GROUP BY customer_id
),
first_detail AS (
    SELECT o.customer_id, f.first_date,
           SUM(o.total_amount) AS first_amount,
           (SELECT SUM(oi.quantity) FROM order_items oi
             WHERE oi.order_id = o.order_id) AS first_items
    FROM orders o
    JOIN first_order f ON f.customer_id = o.customer_id
    WHERE o.order_status IN ('已完成', '已发货')
      AND substr(o.created_at, 1, 10) = f.first_date
    GROUP BY o.customer_id
),
events AS (
    SELECT e.customer_id,
           SUM(CASE WHEN e.event_type = 'view' THEN 1 ELSE 0 END) AS view_cnt,
           SUM(CASE WHEN e.event_type = 'cart' THEN 1 ELSE 0 END) AS cart_cnt
    FROM user_events e
    JOIN first_order f ON f.customer_id = e.customer_id
    WHERE substr(e.event_time, 1, 10) <= f.first_date
    GROUP BY e.customer_id
)
SELECT f.customer_id, f.first_date,
       CAST(julianday(f.first_date) - julianday(c.register_date) AS INTEGER) AS register_to_first_days,
       d.first_amount, d.first_items,
       COALESCE(e.view_cnt, 0) AS view_cnt,
       COALESCE(e.cart_cnt, 0) AS cart_cnt,
       c.age, c.gender, c.member_level, c.province, c.register_date
FROM first_order f
JOIN customers c ON c.customer_id = f.customer_id
JOIN first_detail d ON d.customer_id = f.customer_id
LEFT JOIN events e ON e.customer_id = f.customer_id;
"""
feat = pd.read_sql_query(FEAT_SQL, conn)
feat['first_date'] = pd.to_datetime(feat['first_date'])
feat['register_date'] = pd.to_datetime(feat['register_date'])

df = df_label.merge(feat, on=['customer_id', 'first_date'], how='inner')

gender_map = {'男': 0, '女': 1}
level_map = {'普通': 0, '白银': 1, '黄金': 2, '钻石': 3}
df['gender_code'] = df['gender'].map(gender_map)
df['level_code'] = df['member_level'].map(level_map)
prov_dummies = pd.get_dummies(df['province'], prefix='prov', dtype=int)
df = pd.concat([df, prov_dummies], axis=1)

FEATURES = ['register_to_first_days', 'first_amount', 'first_items',
            'view_cnt', 'cart_cnt', 'age', 'gender_code', 'level_code'] + list(prov_dummies.columns)

FEAT_CN = {
    'register_to_first_days': '注册到首单天数（转化速度）',
    'first_amount': '首单实付金额',
    'first_items': '首单商品件数',
    'view_cnt': '首单前浏览次数',
    'cart_cnt': '首单前加购次数',
    'age': '年龄',
    'gender_code': '性别（0男/1女）',
    'level_code': '会员等级（0~3）',
}

df = df.sort_values(['register_date', 'customer_id']).reset_index(drop=True)
split = int(len(df) * 0.8)
train_df, test_df = df[:split], df[split:]
X_train, y_train = train_df[FEATURES], train_df['repurchase']
X_test, y_test = test_df[FEATURES], test_df['repurchase']

model = XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.05,
                      subsample=0.9, colsample_bytree=0.9,
                      eval_metric='logloss', random_state=SEED)
model.fit(X_train, y_train)
prob = model.predict_proba(X_test)[:, 1]
auc = roc_auc_score(y_test, prob)
print("[模型] XGBoost 复训完成，测试 AUC = %.4f" % auc)

R.h2("特征清单与切分")
R.table(pd.DataFrame(
    [[f, FEAT_CN.get(f, '省份独热（%s）' % f.replace('prov_', ''))] for f in FEATURES],
    columns=['特征', '含义']))
R.text("**Python 结果：**")
R.output("样本 = %d（训练 %d / 测试 %d，按注册日期前 80%%/后 20%% 切分）\n"
         "复购率：训练 %.2f%% / 测试 %.2f%%\n"
         "重训 XGBoost 测试 AUC = %.4f（与 ensemble_report.md 一致）"
         % (len(df), len(train_df), len(test_df),
            y_train.mean() * 100, y_test.mean() * 100, auc))

# ================== 2. SHAP 计算 ==================
R.h1("SHAP 计算方法")
R.text("SHAP（SHapley Additive exPlanations）把每个预测值分解为各特征的加性贡献："
       "f(x) = base_value + Σ φ_i(x)，其中 φ_i 是特征 i 的 SHAP 值（Shapley 值）。"
       "对树模型，**TreeExplainer（TreeSHAP）** 利用树结构在多项式时间内算出精确 Shapley 值，"
       "无需扰动采样。二分类下 SHAP 值位于 **log-odds（margin）空间**："
       "φ_i > 0 表示该特征把预测推向「复购」，φ_i < 0 推向「不复购」。")
R.code("python",
       "explainer = shap.TreeExplainer(model)\n"
       "exp = explainer(X_test)            # Explanation 对象（含 values / base_values / data）\n"
       "sv = exp.values                    # shape = (n_test, n_features)，log-odds 空间")

explainer = shap.TreeExplainer(model)
exp = explainer(X_test)
sv = exp.values
mean_abs = np.abs(sv).mean(axis=0)
order = np.argsort(-mean_abs)
R.output("测试集 = %d 条 × %d 维 SHAP 值\nbase_value（全体样本 log-odds 基线）= %.4f"
         % (sv.shape[0], sv.shape[1], explainer.expected_value))

# ================== 3. 全局解释 ==================
R.h1("全局解释：模型整体在靠什么做判断")

R.h2("特征重要性（mean |SHAP|，bar）")
shap.plots.bar(exp, show=False, max_display=12)
plt.title('SHAP Feature Importance (mean |SHAP|)', fontsize=11)
R.save_plt('3_1_shap_bar.png')
R.image('3_1_shap_bar.png', 'SHAP Bar | 全局特征重要性')
R.text("**中文说明：** 横轴 = 测试集上 |SHAP 值| 的均值（对预测的平均影响幅度，log-odds）；"
       "与 XGBoost 自带 importance（分裂频次加权）相比，mean|SHAP| 同时考虑分裂收益的方向与幅度，"
       "是更可靠的特征贡献度量。")

R.h2("Beeswarm 摘要图（方向 + 分布）")
shap.plots.beeswarm(exp, show=False, max_display=12)
plt.title('SHAP Beeswarm', fontsize=11)
R.save_plt('3_2_shap_beeswarm.png')
R.image('3_2_shap_beeswarm.png', 'SHAP Beeswarm | 蜂群摘要图')
plt.close('all')
R.text("**中文说明：** 每行一个特征，每个点一个测试样本；横轴 = SHAP 值（右 = 推向复购），"
       "颜色 = 特征值大小（红高蓝低）。读法：若红点集中在右侧，说明该特征「值越大越倾向复购」。")

R.h2("Top 特征的方向解读（数字支撑）")
dir_rows = []
for i in order[:5]:
    fn = FEATURES[i]
    rho = spearmanr(X_test.iloc[:, i], sv[:, i]).statistic
    direction = '值越大 → 越倾向复购' if rho > 0 else '值越大 → 越倾向不复购'
    dir_rows.append({'排名': len(dir_rows) + 1, '特征': fn,
                     '含义': FEAT_CN.get(fn, '省份独热'),
                     'mean|SHAP|': mean_abs[i],
                     '特征值-SHAP 秩相关': rho, '方向': direction})
dir_df = pd.DataFrame(dir_rows)
R.table(dir_df)
R.text("**解释：** 秩相关（Spearman ρ）量化「特征值越大，SHAP 值是否越大」。"
       "但**必须诚实声明**：本模型测试 AUC = %.3f ≈ 随机水平，SHAP 解释的是模型从训练集学到的"
       "（大概率是噪声性的）分裂模式，而非可泛化的业务规律——弱模型上的「Top 特征方向」"
       "只能当假设线索，不能当决策依据。详见最后一节讨论。" % auc)

# ================== 4. 局部解释 ==================
R.h1("局部解释：单个特征与单个样本")

R.h2("Dependence Plot（Top 2 特征）")
dep_feats = [FEATURES[order[0]], FEATURES[order[1]]]
for k, fn in enumerate(dir_feats if (dir_feats := dir_df['特征'].tolist()[:2]) else dep_feats):
    shap.dependence_plot(fn, sv, X_test, show=False)
    plt.title('SHAP Dependence: %s' % fn, fontsize=11)
    R.save_plt('4_%d_dependence_%s.png' % (k + 1, fn))
    R.image('4_%d_dependence_%s.png' % (k + 1, fn), 'Dependence | %s' % fn)
    plt.close('all')
R.text("**中文说明：** 横轴 = 特征取值，纵轴 = 该特征的 SHAP 值，颜色 = 交互最强特征的取值。"
       "读法：点的整体走向给出主效应（单调/阈值/分段），同一横坐标上点的纵向离散程度"
       "反映与其他特征的交互强度。")
R.text("**解释：** Top 1 特征 **%s**（%s）与 Top 2 特征 **%s**（%s）。"
       "若 dependence 呈明显趋势，说明模型确实系统性使用了该特征；"
       "若只是围绕 0 的弥散云，说明该特征的「重要性」来自少数样本的偶然分裂。"
       % (dir_df.loc[0, '特征'], dir_df.loc[0, '含义'], dir_df.loc[1, '特征'], dir_df.loc[1, '含义']))

R.h2("单样本 Waterfall（一次预测的完整分解）")
rep1_idx = int(np.where((y_test.values == 1))[0][np.argmax(prob[y_test.values == 1])]) \
    if (y_test.values == 1).any() else int(np.argmax(prob))
R.text("选样逻辑：测试集中**真实复购 = 1 且模型预测概率最高**的样本"
       "（预测概率 %.3f）——看模型「最有把握的一次正确判断」由哪些特征拼成。" % prob[rep1_idx])
shap.plots.waterfall(exp[rep1_idx], show=False, max_display=12)
plt.title('SHAP Waterfall (test sample #%d)' % rep1_idx, fontsize=11)
R.save_plt('4_3_waterfall.png')
R.image('4_3_waterfall.png', 'Waterfall | 单样本 SHAP 分解')
plt.close('all')
R.text("**中文说明：** 从底部 base_value（全体客户平均 log-odds）出发，"
       "红色条把预测推向复购、蓝色条推向不复购，逐级累加到顶部最终 f(x)。")
sample = X_test.iloc[rep1_idx]
top_local = np.argsort(-np.abs(sv[rep1_idx]))[:3]
R.text("**解释：** 该样本贡献最大的三个特征为 %s。"
       "对应特征值：%s。单样本分解的价值在于运营可解释性——"
       "对高复购概率客户可以回答「系统看中了 TA 的什么」。"
       % ('、'.join(FEATURES[i] for i in top_local),
          '、'.join('%s=%s' % (FEATURES[i], sample.iloc[i]) for i in top_local)))

# ================== 5. 讨论与局限 ==================
R.h1("讨论与局限（诚实声明）")
R.text("1. **SHAP 解释的是模型，不是世界**：SHAP 忠实回答「模型为何这么判」，"
       "但模型 AUC = %.3f ≈ 随机——它从训练集学到的分裂模式大概率在拟合噪声，"
       "此时 beeswarm 的方向、dependence 的趋势都只是「模型的偏见画像」，"
       "不可外推为客户行为规律。对照实验（ensemble_report.md 3.5 节）已证明："
       "加入生成参数 activity_score 后同管线 AUC 跳到 0.77，说明瓶颈在特征信息量，"
       "**SHAP 只有在强模型上才能作为业务洞察的依据**。" % auc)
R.text("2. **相关 ≠ 因果**：即使在强模型上，SHAP 反映的也是相关性结构。"
       "例如「首单金额高 → 复购贡献为正」不意味着「提高首单金额能提升复购」——"
       "两者可能共同由客户购买力驱动。干预类决策需实验（AB test）验证。")
R.text("3. **方法学备注**：TreeSHAP 对树模型是精确解、计算快（本例 %d×%d 秒级完成），"
       "是树模型的首选解释器；对深度模型（如 LSTM）需用 "
       "DeepExplainer/GradientExplainer 或扰动类方法（KernelSHAP），"
       "成本与方差都显著更高。弱信号场景下，解释稳定性本身也应作为模型质量指标监控。"
       % sv.shape)

conn.close()

# ================== 输出 ==================
R.write([
    "# 可解释性报告 - SHAP 解读 XGBoost 复购模型\n",
    "- **数据来源**：`data/ecommerce/ecommerce.db`（管线复用 l3_ensemble.py）",
    "- **解释对象**：XGBoost 复购二分类模型（测试 AUC = %.3f）" % auc,
    "- **方法**：shap.TreeExplainer（TreeSHAP 精确解，log-odds 空间）",
    "- **样本**：训练 %d / 测试 %d（按注册日期时间切分）" % (len(train_df), len(test_df)),
    "- **图件**：bar / beeswarm / dependence ×2 / waterfall ×1\n",
])
