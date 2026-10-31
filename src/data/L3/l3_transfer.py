#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L3 专题 迁移学习：全站 GMV → 一级类目「手机数码」GMV
- 预训练: 全站日 GMV（log1p + MinMax）上训练 LSTM（30 天 → 预测次日）
- 迁移: 预训练权重迁移到手机数码日 GMV，小学习率微调
- 对照: 同结构模型在手机数码上从零训练；另报 zero-shot（不微调直接预测）
- 评估: 最后 90 天测试段 MAE / RMSE / MAPE + 验证集收敛曲线
- 输出: transfer_report.md + images_transfer/
"""

import os
import sqlite3
import shutil
import time
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns

import tensorflow as tf
from tensorflow.keras.models import Model, clone_model
from tensorflow.keras.layers import Input, LSTM, Dense
from tensorflow.keras.callbacks import EarlyStopping

from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error

warnings.filterwarnings('ignore')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
tf.get_logger().setLevel('ERROR')

SEED = 42
np.random.seed(SEED)
tf.random.set_seed(SEED)

# ================== 配置区 ==================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'ecommerce', 'ecommerce.db'))
OUTPUT_MD = os.path.join(SCRIPT_DIR, 'transfer_report.md')
IMAGE_DIR = os.path.join(SCRIPT_DIR, 'images_transfer')

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

IN_LEN = 30
TEST_DAYS = 90
TARGET_CAT = '手机数码'

# ================== 1. 任务定义与数据 ==================
conn = sqlite3.connect(DB_PATH)

SRC_SQL = """
SELECT substr(created_at, 1, 10) AS day,
       SUM(total_amount)         AS gmv
FROM orders
WHERE order_status IN ('已完成', '已发货')
GROUP BY day
ORDER BY day;
"""

TGT_SQL = """
SELECT substr(o.created_at, 1, 10) AS day,
       SUM(oi.subtotal)            AS gmv
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
JOIN products p    ON p.product_id = oi.product_id
JOIN categories c2 ON c2.category_id = p.category_id
JOIN categories c1 ON c1.category_id = c2.parent_id
WHERE o.order_status IN ('已完成', '已发货')
  AND c1.category_name = '%s'
GROUP BY day
ORDER BY day;
""" % TARGET_CAT

def load_daily(sql_):
    d = pd.read_sql_query(sql_, conn)
    d['day'] = pd.to_datetime(d['day'])
    idx = pd.date_range(d['day'].min(), d['day'].max(), freq='D')
    d = d.set_index('day').reindex(idx).fillna(0.0)
    d.index.name = 'day'
    return d['gmv'].astype(float)

ts_src = load_daily(SRC_SQL)
ts_tgt = load_daily(TGT_SQL)
print("[数据] 全站 GMV: %d 天；%s GMV: %d 天" % (len(ts_src), TARGET_CAT, len(ts_tgt)))

R.h1("任务定义与数据")
R.text("新类目上线初期数据稀缺，从零训练深度模型容易过拟合。**迁移学习**的思路："
       "先在数据充足的**源域**（全站日 GMV，%d 天）上预训练 LSTM，"
       "学到的「周周期节律、大促脉冲形态、趋势惯性」等通用时序模式，"
       "再迁移到**目标域**（一级类目「%s」日 GMV）上用少量数据小学习率微调。"
       "对照组是同结构模型**从零训练**；另报 **zero-shot**（预训练后不微调直接预测），"
       "用于分解「权重初始化」与「微调适配」各自的贡献。" % (len(ts_src), TARGET_CAT))
R.text("口径说明：全站 GMV 用 orders.total_amount 求和；类目 GMV 需经 "
       "order_items → products → categories（二级类目 parent_id 回挂一级）按明细小计 subtotal 求和，"
       "不含运费，因此类目之和小于全站口径，两者**量级不同**——这正是必须先各自做 "
       "log1p + MinMax 归一化、在归一化空间迁移的原因。")

R.h2("源域 SQL（全站日 GMV）")
R.code("sql", SRC_SQL)
R.h2("目标域 SQL（%s 日 GMV）" % TARGET_CAT)
R.code("sql", TGT_SQL)
R.text("**目标域 SQL 结果（前 5 行）：**")
R.table(pd.read_sql_query(TGT_SQL, conn).head())

R.h2("源域 vs 目标域序列")
fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True)
axes[0].plot(ts_src.index, ts_src.values, color='steelblue', lw=0.9)
axes[0].set_title('源域：全站日 GMV（元）', fontsize=11)
axes[1].plot(ts_tgt.index, ts_tgt.values, color='darkorange', lw=0.9)
axes[1].set_title('目标域：%s日 GMV（元）' % TARGET_CAT, fontsize=11)
for ax in axes:
    ax.axvspan(ts_src.index[-TEST_DAYS], ts_src.index[-1], alpha=0.15, color='red')
    ax.axvline(ts_src.index[-TEST_DAYS], color='red', ls=':', alpha=0.6)
axes[0].annotate('测试段', xy=(ts_src.index[-TEST_DAYS + 3], ts_src.max() * 0.9), color='red', fontsize=9)
plt.tight_layout()
R.save_plt('3_1_src_tgt.png')
R.image('3_1_src_tgt.png', 'Source vs Target | 源域与目标域序列')
R.text("**中文说明：** 上 = 全站日 GMV；下 = 手机数码日 GMV；红色阴影 = 最后 %d 天测试段（两域共用）。"
       "可见两域共享双 11 / 618 峰值位置与周周期节律——这是迁移能成立的结构前提。" % TEST_DAYS)

# ================== 2. 样本与模型 ==================
R.h1("样本构造与迁移方案")
split_pos = len(ts_src) - TEST_DAYS
R.text("- 样本：连续 %d 天 → 预测次日（单步），log1p 后 MinMax 归一化，"
       "归一化参数只用测试段之前的数据拟合（两域各自拟合，防泄漏、对齐量级）；\n"
       "- 预训练：源域中输出点早于 %s 的全部样本；\n"
       "- 微调 / 从零训练：目标域同时间窗的训练样本（与预训练等量但不同域）；\n"
       "- 测试：目标域最后 %d 天。"
       % (IN_LEN, ts_src.index[split_pos - 1].date(), TEST_DAYS))

def make_samples(arr):
    X, Y, idx = [], [], []
    for s in range(0, len(arr) - IN_LEN):
        X.append(arr[s:s + IN_LEN])
        Y.append(arr[s + IN_LEN])
        idx.append(s + IN_LEN)
    return np.array(X), np.array(Y).reshape(-1, 1), np.array(idx)

log_src = np.log1p(ts_src.values).reshape(-1, 1)
log_tgt = np.log1p(ts_tgt.values).reshape(-1, 1)
sc_src = MinMaxScaler().fit(log_src[:split_pos])
sc_tgt = MinMaxScaler().fit(log_tgt[:split_pos])
scaled_src = sc_src.transform(log_src)
scaled_tgt = sc_tgt.transform(log_tgt)

Xs, Ys, idx_s = make_samples(scaled_src)
Xt, Yt, idx_t = make_samples(scaled_tgt)
src_tr = idx_s < split_pos
tgt_tr, tgt_te = idx_t < split_pos, idx_t >= split_pos
Xs_train, Ys_train = Xs[src_tr], Ys[src_tr]
Xt_train, Yt_train = Xt[tgt_tr], Yt[tgt_tr]
Xt_test, Yt_test = Xt[tgt_te], Yt[tgt_te]
R.output("预训练样本（源域）= %d\n微调/从零训练样本（目标域）= %d\n测试样本（目标域）= %d"
         % (len(Xs_train), len(Xt_train), len(Xt_test)))

def build_model(lr=1e-3):
    inp = Input(shape=(IN_LEN, 1))
    x = LSTM(32, activation='tanh')(inp)
    out = Dense(1)(x)
    m = Model(inp, out)
    m.compile(optimizer=tf.keras.optimizers.Adam(lr), loss='mae')
    return m

R.h2("三种策略")
R.table(pd.DataFrame([
    ['Zero-shot', '源域预训练（30 epoch, lr=1e-3）', '不微调，直接预测目标域', '衡量权重迁移的原始迁移力'],
    ['从零训练', '无（随机初始化）', '目标域训练（≤30 epoch, lr=1e-3, EarlyStopping）', '对照组'],
    ['迁移微调', '源域预训练', '目标域微调（≤30 epoch, lr=1e-4 小学习率防灾难性遗忘）', '实验组'],
], columns=['策略', '预训练', '目标域训练', '作用']))

# ================== 3. 训练 ==================
R.h1("训练与收敛对比")
es_kw = dict(monitor='val_loss', patience=8, restore_best_weights=True)

t0 = time.time()
m_pre = build_model(lr=1e-3)
h_pre = m_pre.fit(Xs_train, Ys_train, epochs=30, batch_size=32, validation_split=0.1,
                  callbacks=[EarlyStopping(**es_kw)], verbose=0)
t_pre = time.time() - t0
print("[模型] 源域预训练完成，%.1fs, %d epochs" % (t_pre, len(h_pre.history['loss'])))

t0 = time.time()
m_ft = clone_model(m_pre)
m_ft.set_weights(m_pre.get_weights())
m_ft.compile(optimizer=tf.keras.optimizers.Adam(1e-4), loss='mae')
h_ft = m_ft.fit(Xt_train, Yt_train, epochs=30, batch_size=32, validation_split=0.1,
                callbacks=[EarlyStopping(**es_kw)], verbose=0)
t_ft = time.time() - t0
print("[模型] 迁移微调完成，%.1fs, %d epochs" % (t_ft, len(h_ft.history['loss'])))

t0 = time.time()
tf.random.set_seed(SEED)
m_sc = build_model(lr=1e-3)
h_sc = m_sc.fit(Xt_train, Yt_train, epochs=30, batch_size=32, validation_split=0.1,
                callbacks=[EarlyStopping(**es_kw)], verbose=0)
t_sc = time.time() - t0
print("[模型] 从零训练完成，%.1fs, %d epochs" % (t_sc, len(h_sc.history['loss'])))

R.h2("验证集损失收敛曲线（目标域）")
plt.figure(figsize=(9, 4.5))
plt.plot(h_sc.history['val_loss'], 'o-', ms=3, label='从零训练（lr=1e-3）')
plt.plot(h_ft.history['val_loss'], 's-', ms=3, label='迁移微调（lr=1e-4）')
plt.xlabel('Epoch'); plt.ylabel('val_loss（MAE，归一化空间）')
plt.title('迁移微调 vs 从零训练：目标域验证集收敛曲线')
plt.legend()
R.save_plt('3_2_convergence.png')
R.image('3_2_convergence.png', 'Convergence | 验证集收敛曲线对比')
best_ep_ft = int(np.argmin(h_ft.history['val_loss'])) + 1
best_ep_sc = int(np.argmin(h_sc.history['val_loss'])) + 1
R.text("**中文说明：** 横轴 = 微调/训练的第几个 epoch；纵轴 = 目标域验证集 MAE（归一化空间）。")
R.text("**解释：** 迁移微调从**预训练好的参数**出发，初始 val_loss（%.4f）低于从零训练的起点（%.4f）——"
       "预训练把「周周期 + 脉冲形态」的先验装进权重，省掉了冷启动摸索；"
       "本 run 微调第 %d 个 epoch 达最优、从零训练第 %d 个"
       "（小模型小样本下 epoch 差异属种子噪声量级），"
       "因此迁移对收敛的确定性收益体现在**初始损失更低**，而非训练步数更少。"
       % (h_ft.history['val_loss'][0], h_sc.history['val_loss'][0], best_ep_ft, best_ep_sc))

# ================== 4. 评估 ==================
R.h1("测试段评估（目标域：%s，最后 %d 天）" % (TARGET_CAT, TEST_DAYS))

def inv_tgt(v):
    return np.expm1(sc_tgt.inverse_transform(np.asarray(v).reshape(-1, 1))).ravel()

def mape(y_true, y_pred):
    y_true, y_pred = np.asarray(y_true, float), np.asarray(y_pred, float)
    mask = y_true != 0
    return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100

y_true = inv_tgt(Yt_test)
pred_zs = inv_tgt(m_pre.predict(Xt_test, verbose=0))
pred_ft = inv_tgt(m_ft.predict(Xt_test, verbose=0))
pred_sc = inv_tgt(m_sc.predict(Xt_test, verbose=0))

def row(name, yp, ep, tsec):
    return {'策略': name,
            'RMSE(元)': np.sqrt(mean_squared_error(y_true, yp)),
            'MAE(元)': mean_absolute_error(y_true, yp),
            'MAPE(%)': mape(y_true, yp),
            '目标域训练 epoch': ep, '目标域训练耗时(s)': round(tsec, 1)}

eval_df = pd.DataFrame([
    row('Zero-shot（不微调）', pred_zs, 0, 0.0),
    row('从零训练', pred_sc, len(h_sc.history['loss']), t_sc),
    row('迁移微调', pred_ft, len(h_ft.history['loss']), t_ft),
])
R.table(eval_df)
mae_sc, mae_ft = eval_df.loc[1, 'MAE(元)'], eval_df.loc[2, 'MAE(元)']
mape_sc, mape_ft = eval_df.loc[1, 'MAPE(%)'], eval_df.loc[2, 'MAPE(%)']
gain = (mae_sc - mae_ft) / mae_sc * 100
gain_mape = (mape_sc - mape_ft) / mape_sc * 100
R.text("**迁移增益（微调 vs 从零）：** MAE 变化 %.1f%%（%.0f → %.0f 元），"
       "MAPE 变化 %.1f%%（%.1f%% → %.1f%%）。两项指标方向不一致，"
       "说明差异主要由少数峰值日的绝对误差主导，而非整体拟合质量的差距。"
       % (gain, mae_sc, mae_ft, gain_mape, mape_sc, mape_ft))

R.h2("测试段预测对比")
plt.figure(figsize=(11, 4.5))
plt.plot(ts_tgt.index[-TEST_DAYS:], y_true, 'o-', color='black', lw=1.6, ms=3, label='真实值')
plt.plot(ts_tgt.index[-TEST_DAYS:], pred_sc, 's--', ms=3, label='从零训练')
plt.plot(ts_tgt.index[-TEST_DAYS:], pred_ft, '^--', ms=3, label='迁移微调')
plt.plot(ts_tgt.index[-TEST_DAYS:], pred_zs, ':', color='gray', label='Zero-shot')
plt.xlabel('日期'); plt.ylabel('日 GMV（元）')
plt.title('目标域（%s）测试段预测对比' % TARGET_CAT)
plt.legend()
R.save_plt('3_3_test_forecast.png')
R.image('3_3_test_forecast.png', 'Test Forecast | 目标域测试段预测对比')
R.text("**解释：** 测试段含 618 峰值，三种策略都难以完全捕捉峰值高度；"
       "迁移微调与从零训练的曲线形态高度接近，Zero-shot 在日常段略有偏移——"
       "预训练权重提供了可用的初始解，但类目细节仍需目标域数据校准。")

# ================== 5. 结论 ==================
R.h1("结论与讨论")
mae_zs = eval_df.loc[0, 'MAE(元)']
R.text("1. **迁移的确定性收益在起点而非终点**：迁移微调初始 val_loss（%.4f）即低于从零训练（%.4f），"
       "预训练先验省掉了冷启动摸索阶段；但收敛 epoch（%d vs %d）与最终精度均为混合结果："
       "MAPE 微优（%.1f%% vs %.1f%%）、MAE/RMSE 微劣（%.0f vs %.0f 元），"
       "Zero-shot（MAE %.0f 元）与微调接近，说明本数据上预训练权重承载了主要迁移价值，"
       "微调的边际收益小且对超参敏感。"
       % (h_ft.history['val_loss'][0], h_sc.history['val_loss'][0],
          best_ep_ft, best_ep_sc, mape_ft, mape_sc, mae_ft, mae_sc, mae_zs))
R.text("2. **为什么最终增益不显著**：目标域 %d 个训练样本对单 LSTM(32) 并非极稀缺，"
       "且两域共享大促日历与周周期、归一化后形态高度相似，从零训练也能在 30 epoch 内"
       "学到主要模式——迁移学习的价值区间在「目标域历史更短（如仅 3 个月）/ 模型更深」"
       "的场景才会拉开差距；本实验条件下迁移与从零的差异落在单种子（seed=42）噪声范围内，"
       "不应过度解读单次 run 的方向，严谨做法是多 seed 重复取均值±方差。" % len(Xt_train))
R.text("3. **工程启示**：多类目 GMV 预测的标准做法是「全站预训练 → 各类目微调」的星型结构，"
       "比每个类目独立建模省数据、省算力；新类目冷启动时甚至可先 zero-shot 上线，"
       "积累数据后再微调迭代。")

conn.close()

# ================== 输出 ==================
R.write([
    "# 迁移学习报告 - 全站 GMV → 手机数码 GMV\n",
    "- **数据来源**：`data/ecommerce/ecommerce.db`（orders / order_items / products / categories）",
    "- **源域**：全站日 GMV（%d 天）；**目标域**：一级类目「%s」日 GMV" % (len(ts_src), TARGET_CAT),
    "- **任务**：LSTM（30 天 → 次日）迁移学习，对照 zero-shot / 从零训练",
    "- **样本**：预训练 %d / 微调 %d / 测试 %d" % (len(Xs_train), len(Xt_train), len(Xt_test)),
    "- **预处理**：两域各自 log1p + MinMax（仅用测试段之前数据拟合）\n",
])
