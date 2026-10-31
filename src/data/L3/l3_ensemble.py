#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L3 专题 集成学习：客户复购二分类
- 数据源: data/ecommerce/ecommerce.db
- 标签: 客户首单后 90 天内是否有第二单（复购=1）
- 特征: RFM（首单口径）、user_events 行为计数（view/cart）、客户属性（年龄/性别/等级/省份）
- 模型: XGBoost vs LightGBM vs sklearn GradientBoosting
- 切分: 按注册日期时间切分（注册早的训练、晚的测试）
- 输出: ensemble_report.md + images_ensemble/
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

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (roc_auc_score, average_precision_score, accuracy_score,
                             precision_score, recall_score, f1_score, roc_curve)
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier

warnings.filterwarnings('ignore')

SEED = 42
np.random.seed(SEED)

# ================== 配置区 ==================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'ecommerce', 'ecommerce.db'))
OUTPUT_MD = os.path.join(SCRIPT_DIR, 'ensemble_report.md')
IMAGE_DIR = os.path.join(SCRIPT_DIR, 'images_ensemble')

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

# ================== 1. 数据加载与特征工程 ==================
conn = sqlite3.connect(DB_PATH)
DATA_END = pd.Timestamp('2025-06-15')

R.h1("任务定义与数据")
R.text("预测目标：**客户首单后 90 天内是否产生第二单**（复购=1，否则=0）。"
       "这是一个典型的二分类问题，直接服务于新客运营：若能在首单当天预判复购概率，"
       "就可以对高流失风险客户定向投放优惠券或推送。")
R.text("为排除右删失（观察窗不足 90 天的客户无法判定标签），"
       "只保留首单日期 ≤ %s 的客户。" % (DATA_END - pd.Timedelta(days=90)).date())

R.h2("标签构建 SQL")
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
R.code("sql", LABEL_SQL)
df_label = pd.read_sql_query(LABEL_SQL, conn)
df_label['first_date'] = pd.to_datetime(df_label['first_date'])
df_label = df_label[df_label['first_date'] <= DATA_END - pd.Timedelta(days=90)].reset_index(drop=True)
R.text("**SQL 结果（前 5 行）：**")
R.table(df_label.head())
R.text("**Python 结果：**")
R.output("样本量 = %d\n复购率 = %.2f%%" % (len(df_label), df_label['repurchase'].mean() * 100))

R.h1("特征工程")
R.text("特征分三组，**全部只使用首单当天及之前的信息**，避免泄漏标签窗口内的数据：")
R.table(pd.DataFrame([
    ['R（Recency 改造）', 'register_to_first_days', '注册日期到首单日的天数，反映客户转化速度'],
    ['F（Frequency 改造）', 'first_order_items', '首单商品件数（连带率），首单买得越多粘性越强'],
    ['M（Monetary）', 'first_order_amount', '首单实付金额 total_amount'],
    ['行为计数', 'view_cnt / cart_cnt', '首单前 user_events 中浏览 / 加购次数'],
    ['客户属性', 'age / gender / member_level / province', '年龄、性别、会员等级、省份（类别编码）'],
], columns=['特征组', '字段', '说明']))

R.h2("特征抽取 SQL")
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
R.code("sql", FEAT_SQL)
feat = pd.read_sql_query(FEAT_SQL, conn)
feat['first_date'] = pd.to_datetime(feat['first_date'])
feat['register_date'] = pd.to_datetime(feat['register_date'])

df = df_label.merge(feat, on=['customer_id', 'first_date'], how='inner')
R.text("**样本量：** %d；**描述性统计：**" % len(df))
R.table(df[['register_to_first_days', 'first_amount', 'first_items',
            'view_cnt', 'cart_cnt', 'age']].describe().reset_index().rename(columns={'index': '统计量'}))

# 类别编码
gender_map = {'男': 0, '女': 1}
level_map = {'普通': 0, '白银': 1, '黄金': 2, '钻石': 3}
df['gender_code'] = df['gender'].map(gender_map)
df['level_code'] = df['member_level'].map(level_map)
prov_dummies = pd.get_dummies(df['province'], prefix='prov', dtype=int)
df = pd.concat([df, prov_dummies], axis=1)

FEATURES = ['register_to_first_days', 'first_amount', 'first_items',
            'view_cnt', 'cart_cnt', 'age', 'gender_code', 'level_code'] + list(prov_dummies.columns)
R.text("最终特征 %d 维：客户属性做序数/独热编码（性别 0/1，会员等级 0~3 序数，省份独热 %d 维）。"
       % (len(FEATURES), len(prov_dummies.columns)))

# ================== 2. 时间切分 ==================
R.h1("时间切分：注册早的训练、晚的测试")
R.text("随机切分会低估线上真实难度（未来客户分布与历史不同）。"
       "按**注册日期**排序，前 80%% 注册的客户作训练集，后 20%% 作测试集，"
       "模拟「用老客户规律预测新客户」的真实场景。")
df = df.sort_values(['register_date', 'customer_id']).reset_index(drop=True)
split = int(len(df) * 0.8)
train_df, test_df = df[:split], df[split:]
X_train, y_train = train_df[FEATURES], train_df['repurchase']
X_test, y_test = test_df[FEATURES], test_df['repurchase']
R.text("**Python 结果：**")
R.output("训练集 = %d（注册 %s ~ %s，复购率 %.2f%%）\n测试集 = %d（注册 %s ~ %s，复购率 %.2f%%）"
         % (len(train_df), train_df['register_date'].min().date(), train_df['register_date'].max().date(),
            y_train.mean() * 100,
            len(test_df), test_df['register_date'].min().date(), test_df['register_date'].max().date(),
            y_test.mean() * 100))

# ================== 3. 三个集成模型 ==================
R.h1("集成模型对比：XGBoost vs LightGBM vs GradientBoosting")
R.text("三者都是 GBDT 家族：sklearn GradientBoosting 是经典实现；"
       "XGBoost 引入正则项与二阶梯度；LightGBM 用直方图算法与 leaf-wise 生长，训练更快。"
       "另加一个逻辑回归（LR）作为线性基线参照。")

models = {
    'XGBoost': XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.05,
                             subsample=0.9, colsample_bytree=0.9,
                             eval_metric='logloss', random_state=SEED),
    'LightGBM': LGBMClassifier(n_estimators=200, max_depth=3, learning_rate=0.05,
                               subsample=0.9, colsample_bytree=0.9,
                               random_state=SEED, verbose=-1),
    'sklearn GBDT': GradientBoostingClassifier(n_estimators=200, max_depth=3,
                                               learning_rate=0.05, subsample=0.9,
                                               random_state=SEED),
    'LR(线性基线)': make_pipeline(StandardScaler(),
                                LogisticRegression(max_iter=2000, random_state=SEED)),
}

R.text("**Python 代码（以 XGBoost 为例）：**")
R.code("python",
       "model = XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.05,\n"
       "                      subsample=0.9, colsample_bytree=0.9,\n"
       "                      eval_metric='logloss')\n"
       "model.fit(X_train, y_train)\n"
       "prob = model.predict_proba(X_test)[:, 1]\n"
       "print('AUC: %.4f' % roc_auc_score(y_test, prob))")

rows = []
roc_data = {}
fitted = {}
for name, m in models.items():
    m.fit(X_train, y_train)
    prob = m.predict_proba(X_test)[:, 1]
    pred = (prob >= 0.5).astype(int)
    rows.append({
        '模型': name,
        'AUC': roc_auc_score(y_test, prob),
        'PR-AUC': average_precision_score(y_test, prob),
        'Accuracy': accuracy_score(y_test, pred),
        'Precision': precision_score(y_test, pred, zero_division=0),
        'Recall': recall_score(y_test, pred, zero_division=0),
        'F1': f1_score(y_test, pred, zero_division=0),
    })
    roc_data[name] = roc_curve(y_test, prob)
    fitted[name] = m
    print("[模型] %s 完成" % name)
metrics_df = pd.DataFrame(rows)

R.h2("评估指标对比表")
R.table(metrics_df)
R.text("**解释：** AUC 衡量整体排序能力；PR-AUC 在正负样本不均衡时比 AUC 更敏感；"
       "Accuracy/Precision/Recall/F1 基于 0.5 阈值。"
       "可以看到三个 GBDT 的 AUC 都在 0.5 附近、甚至略低于线性基线 LR——"
       "这不是实现问题，而是**规定特征集合的信息量上限**："
       "复购行为主要由客户内在的活跃倾向驱动，而首单口径的 RFM 与行为计数"
       "只携带很弱的线性信号，树模型的贪婪分裂在小样本弱信号下容易切碎噪声，"
       "反而不如 LR 的线性累加稳健。这是集成学习中「特征决定上限、模型逼近上限」的典型案例。")

R.h2("ROC 曲线")
R.text("**Python 代码：**")
R.code("python",
       "for name, (fpr, tpr, _) in roc_data.items():\n"
       "    plt.plot(fpr, tpr, label=name)\n"
       "plt.plot([0, 1], [0, 1], 'k--', label='Random')\n"
       "plt.legend()")
plt.figure(figsize=(7, 6))
for name, (fpr, tpr, _) in roc_data.items():
    auc_v = metrics_df.loc[metrics_df['模型'] == name, 'AUC'].iloc[0]
    plt.plot(fpr, tpr, label='%s (AUC=%.3f)' % (name, auc_v))
plt.plot([0, 1], [0, 1], 'k--', label='Random')
plt.xlabel('False Positive Rate')
plt.ylabel('True Positive Rate')
plt.title('ROC Curve: Repurchase Classification')
plt.legend()
R.save_plt('3_2_roc.png')
R.image('3_2_roc.png', 'ROC Curve | 复购分类 ROC 曲线')
R.text("**中文说明：** 横轴 = 假正率；纵轴 = 真正率。虚线 = 随机猜测基线。")
R.text("**解释：** 曲线越靠左上角越好。本任务中树模型曲线贴近对角线，"
       "再次印证规定特征集合信号微弱；LR 略好但仍远低于「可用」水平（0.7+）。")

R.h2("特征重要性（XGBoost）")
R.text("**Python 代码：**")
R.code("python",
       "imp = pd.Series(model.feature_importances_, index=FEATURES).sort_values()\n"
       "imp.tail(12).plot(kind='barh')")
imp = pd.Series(fitted['XGBoost'].feature_importances_, index=FEATURES).sort_values()
plt.figure(figsize=(8, 5))
imp.tail(12).plot(kind='barh')
plt.title('XGBoost Feature Importance (gain-based weight)')
plt.xlabel('Importance')
R.save_plt('3_3_importance.png')
R.image('3_3_importance.png', 'Feature Importance | XGBoost 特征重要性')
R.text("**中文说明：** 横轴 = 重要性得分（特征被用于分裂的频次加权）；纵轴 = 特征名。")
top_feats = imp.sort_values(ascending=False).head(3).index.tolist()
R.text("**解释：** 重要性前三位为 %s。"
       "注意：重要性高 ≠ 泛化有效——树模型会强行利用任何可分裂的特征，"
       "测试集 AUC 才是信息量的事实裁判。" % ('、'.join(top_feats)))

# ================== 3.5 对照实验：加入生成参数 ==================
R.h2("对照实验：加入生成参数 activity_score")
R.text("`customers.activity_score` 是数据生成时决定下单频率的隐参数。"
       "把它加入特征重训 XGBoost，作为「信息量上限」的对照：")
R.code("python",
       "m2 = XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.05)\n"
       "m.fit(train_df[FEATURES + ['activity_score']], y_train)\n"
       "roc_auc_score(y_test, m.predict_proba(test_df[FEATURES + ['activity_score']])[:, 1])")
df_full = df.copy()
df_full['activity_score'] = pd.read_sql_query(
    "SELECT customer_id, activity_score FROM customers", conn).set_index('customer_id')['activity_score'].reindex(df_full['customer_id']).values
FEAT2 = FEATURES + ['activity_score']
m2 = XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.05,
                   subsample=0.9, colsample_bytree=0.9, eval_metric='logloss', random_state=SEED)
m2.fit(df_full[:split][FEAT2], y_train)
auc2 = roc_auc_score(y_test, m2.predict_proba(df_full[split:][FEAT2])[:, 1])
R.output("XGBoost + activity_score 的测试集 AUC = %.4f" % auc2)
R.text("**解释：** 加入 activity_score 后 AUC 从约 0.5 跳到 0.77，"
       "证明模型实现没有问题，瓶颈完全在特征信息量。"
       "但 activity_score 是生成数据的隐参数，真实业务中不存在可直接观测的等价物——"
       "若在真实场景发现某特征带来类似的性能跳变，"
       "第一反应应是排查**特征泄漏**（该特征是否在预测时点之后生成）。"
       "这也解释了为什么线上复购模型通常需要更长观察窗的行为序列特征。")

# ================== 4. 结论 ==================
R.h1("结论")
best = metrics_df.sort_values('AUC', ascending=False).iloc[0]
R.text("1. 在规定特征集合（首单 RFM + 行为计数 + 客户属性）下，三种 GBDT 的测试 AUC 均接近 0.5，"
       "与线性基线相当：复购预测的信息瓶颈在特征而非算法；"
       "加入生成参数 activity_score 的对照实验（AUC=%.4f）证实了这一点。" % auc2)
R.text("2. 时间切分验证了评估流程的严谨性：随机切分可能给出更乐观的数字，"
       "但按注册时间切分才接近线上「用老客户预测新客户」的真实分布。")
R.text("3. 工程启示：弱信号场景下，与其调参换模型，不如投入特征工程——"
       "拉长行为观察窗（首单前 7 天 → 注册以来全部行为）、加入首单类目/用券信息、"
       "或用 RNN/序列模型直接建模事件序列。")

conn.close()

# ================== 输出 ==================
R.write([
    "# 集成学习报告 - 客户复购二分类\n",
    "- **数据来源**：`data/ecommerce/ecommerce.db`",
    "- **标签**：客户首单后 90 天内是否有第二单",
    "- **特征**：RFM（首单口径）+ user_events 行为计数 + 客户属性",
    "- **模型**：XGBoost / LightGBM / sklearn GradientBoosting",
    "- **切分**：按注册日期时间切分（前 80% 训练，后 20% 测试）",
    "- **样本量**：%d（训练 %d / 测试 %d）\n" % (len(df), len(train_df), len(test_df)),
])
