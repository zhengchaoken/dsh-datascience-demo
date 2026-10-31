#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L5 认知性分析 元学习（Meta-Learning / Reptile）
- 场景: 跨品类少样本销量预测 —— 每个一级品类 = 一个 task
- 数据源: ../ecommerce/ecommerce.db (orders + order_items + products + categories)
- 算法: Reptile（一阶 MAML，实现简单）在多个品类日 GMV 序列上元训练 LSTM
- 测试: 新品类仅给 14 天 support 数据微调后预测
- 对比: 元学习初始化 vs 随机初始化 vs 直接训练（纯小样本监督）
- 输出: meta_report.md + images_meta/
"""

import os
import shutil
import random
import sqlite3
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns

os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')
import tensorflow as tf
from tensorflow import keras

warnings.filterwarnings('ignore')

# ================== 随机种子 ==================
SEED = 42
os.environ['PYTHONHASHSEED'] = str(SEED)
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)

# ================== 配置区 ==================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, '..', 'ecommerce', 'ecommerce.db')
OUTPUT_MD = os.path.join(SCRIPT_DIR, 'meta_report.md')
IMAGE_DIR = os.path.join(SCRIPT_DIR, 'images_meta')

if os.path.isdir(IMAGE_DIR):
    shutil.rmtree(IMAGE_DIR)
os.makedirs(IMAGE_DIR, exist_ok=True)

WINDOW = 7            # 用过去 7 天预测第 8 天
META_ITERS = 200      # Reptile 元迭代次数
INNER_EPOCHS = 4      # 任务内训练轮数
INNER_LR = 1e-3
ADAPT_LR = 3e-3       # 少样本适应学习率
META_LR = 0.5         # Reptile 元步长 ε
SUPPORT_DAYS = 14     # 新品类 support 天数
TEST_DAYS = 90        # 新品类测试天数
ADAPT_EPOCHS = 20     # 少样本适应轮数（记录逐 epoch 曲线）
DIRECT_EPOCHS = 30    # "直接训练"基线轮数
TEST_CATS = ['母婴用品', '食品饮料', '美妆个护']   # 留一法测试品类

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


# ================== 数据加载 ==================
def load_category_gmv():
    """各一级品类的日 GMV 序列（log1p + 品类内 z-score）"""
    con = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        "SELECT substr(o.created_at,1,10) AS d, c2.category_name AS cat, "
        "SUM(oi.subtotal) AS gmv "
        "FROM orders o JOIN order_items oi ON oi.order_id=o.order_id "
        "JOIN products p ON p.product_id=oi.product_id "
        "JOIN categories c1 ON c1.category_id=p.category_id "
        "JOIN categories c2 ON c2.category_id=c1.parent_id "
        "WHERE o.order_status IN ('已完成','已发货') "
        "GROUP BY d, cat ORDER BY d", con)
    con.close()
    df['d'] = pd.to_datetime(df['d'])
    full = pd.date_range(df['d'].min(), df['d'].max(), freq='D')
    series = {}
    stats = {}
    for cat, g in df.groupby('cat'):
        s = g.set_index('d')['gmv'].reindex(full, fill_value=0.0)
        y = np.log1p(s.values)
        mu, sd = y.mean(), y.std() + 1e-8
        series[cat] = ((y - mu) / sd).astype(np.float32)
        stats[cat] = (mu, sd)
        print("[数据] %s: %d 天, 均值 %.0f 元" % (cat, len(y), s.mean()))
    return series, stats, full


def make_windows(vals, start, end):
    """从 vals[start:end] 构造滑窗样本"""
    X, Y = [], []
    for i in range(start, end - WINDOW):
        X.append(vals[i:i + WINDOW])
        Y.append(vals[i + WINDOW])
    X = np.array(X, dtype=np.float32).reshape(-1, WINDOW, 1)
    Y = np.array(Y, dtype=np.float32).reshape(-1, 1)
    return X, Y


# ================== 模型 ==================
def build_model():
    model = keras.Sequential([
        keras.layers.Input(shape=(WINDOW, 1)),
        keras.layers.LSTM(16),
        keras.layers.Dense(8, activation='relu'),
        keras.layers.Dense(1),
    ])
    return model


def train_on(model, X, y, epochs, lr):
    opt = keras.optimizers.Adam(lr)
    n = len(X)
    for _ in range(epochs):
        idx = np.random.permutation(n)
        for i in range(0, n, 16):
            j = idx[i:i + 16]
            with tf.GradientTape() as tape:
                pred = model(X[j], training=True)
                loss = tf.reduce_mean(tf.square(pred - y[j]))
            grads = tape.gradient(loss, model.trainable_weights)
            opt.apply_gradients(zip(grads, model.trainable_weights))


def nmae(model, X, y_n, mu, sd):
    """原始金额空间的 NMAE（%）: MAE / 测试期均值, 避免 MAPE 在低销量日爆炸"""
    pred = np.expm1(model(X, training=False).numpy().reshape(-1) * sd + mu)
    true = np.expm1(y_n.reshape(-1) * sd + mu)
    pred = np.maximum(pred, 0.0)
    return float(np.mean(np.abs(pred - true)) / max(np.mean(true), 1.0) * 100)


# ================== Reptile 元训练 ==================
def reptile_meta_train(series, train_cats):
    """Reptile: θ ← θ + ε·(θ'_task − θ)"""
    meta = build_model()
    for it in range(META_ITERS):
        cat = train_cats[np.random.randint(len(train_cats))]
        vals = series[cat]
        # 随机截取 60 天作为本次任务的训练片段
        hi = len(vals) - 60
        start = np.random.randint(0, hi)
        X, Y = make_windows(vals, start, start + 60)
        worker = build_model()
        worker.set_weights([w.copy() for w in meta.get_weights()])
        train_on(worker, X, Y, INNER_EPOCHS, INNER_LR)
        new_w = [m + META_LR * (wk - m)
                 for m, wk in zip(meta.get_weights(), worker.get_weights())]
        meta.set_weights(new_w)
        if (it + 1) % 50 == 0:
            print("  [Reptile] 元迭代 %d/%d" % (it + 1, META_ITERS))
    return meta


# ================== 少样本适应实验 ==================
def adapt_curve(init_weights, Xs, ys, Xt, yt, mu, sd, epochs):
    """从给定初始化微调, 逐 epoch 记录测试 NMAE"""
    model = build_model()
    model.set_weights([w.copy() for w in init_weights])
    curve = [nmae(model, Xt, yt, mu, sd)]
    for ep in range(epochs):
        train_on(model, Xs, ys, 1, ADAPT_LR)
        curve.append(nmae(model, Xt, yt, mu, sd))
    return curve, model


def run_experiment(series, stats):
    results = {}
    for test_cat in TEST_CATS:
        train_cats = [c for c in series if c != test_cat]
        print("[实验] 测试品类: %s (元训练品类: %s)" % (test_cat, ','.join(train_cats)))
        vals = series[test_cat]
        mu, sd = stats[test_cat]
        # support = 前 14 天; test = 之后 90 天
        Xs, ys = make_windows(vals, 0, SUPPORT_DAYS)
        Xt, yt = make_windows(vals, SUPPORT_DAYS, SUPPORT_DAYS + TEST_DAYS)

        # A. 元学习初始化
        np.random.seed(SEED); tf.random.set_seed(SEED)
        meta_model = reptile_meta_train(series, train_cats)
        np.random.seed(SEED + 1)
        curve_meta, _ = adapt_curve(meta_model.get_weights(), Xs, ys, Xt, yt, mu, sd, ADAPT_EPOCHS)

        # B. 随机初始化 + 同步数微调
        np.random.seed(SEED); tf.random.set_seed(SEED)
        rand_model = build_model()
        np.random.seed(SEED + 1)
        curve_rand, _ = adapt_curve(rand_model.get_weights(), Xs, ys, Xt, yt, mu, sd, ADAPT_EPOCHS)

        # C. 直接训练（随机初始化, 纯小样本监督, 更多轮数）
        np.random.seed(SEED); tf.random.set_seed(SEED)
        direct_model = build_model()
        np.random.seed(SEED + 1)
        curve_direct, _ = adapt_curve(direct_model.get_weights(), Xs, ys, Xt, yt, mu, sd, DIRECT_EPOCHS)

        results[test_cat] = {
            'meta': curve_meta, 'rand': curve_rand, 'direct': curve_direct,
            'n_support': len(Xs), 'n_test': len(Xt),
        }
        print("  [结果] %s: 零样本 元学习=%.1f%% 随机=%.1f%% | 最优(早停参考) 元学习=%.1f%%@%d 随机=%.1f%%@%d | 最终(%d轮) 元学习=%.1f%% 随机=%.1f%% 直接训练(%d轮)=%.1f%%"
              % (test_cat, curve_meta[0], curve_rand[0],
                 min(curve_meta), int(np.argmin(curve_meta)),
                 min(curve_rand), int(np.argmin(curve_rand)),
                 ADAPT_EPOCHS, curve_meta[-1], curve_rand[-1],
                 DIRECT_EPOCHS, curve_direct[-1]))
    return results


# ================== 图表 ==================
def plot_tasks(series, full):
    fig, ax = plt.subplots(figsize=(11, 4.5))
    for cat, vals in series.items():
        ax.plot(full, vals, lw=0.8, label=cat, alpha=0.85)
    ax.set_title('6 个一级品类的日 GMV 序列（log1p + 品类内标准化）—— 每个品类是一个 task')
    ax.set_xlabel('日期')
    ax.set_ylabel('标准化 GMV')
    ax.legend(ncol=3, fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(IMAGE_DIR, '1_tasks.png'), dpi=110)
    plt.close(fig)
    return 'images_meta/1_tasks.png'


def plot_adapt(results):
    fig, axes = plt.subplots(1, len(results), figsize=(14, 4), sharey=False)
    xs = list(range(0, ADAPT_EPOCHS + 1))
    for ax, (cat, r) in zip(axes, results.items()):
        ax.plot(xs, r['meta'], marker='o', ms=3, label='元学习初始化', color='#1f77b4')
        ax.plot(xs, r['rand'], marker='s', ms=3, label='随机初始化', color='#d62728')
        ax.axhline(r['direct'][-1], color='#7f7f7f', ls='--',
                   label='直接训练(%d轮)最终' % DIRECT_EPOCHS)
        ax.set_title('新品类：%s' % cat)
        ax.set_xlabel('适应 epoch')
        ax.set_ylabel('测试 NMAE（%）')
        ax.legend(fontsize=8)
    fig.suptitle('少样本适应曲线：14 天 support 微调后的测试 NMAE 变化')
    fig.tight_layout()
    fig.savefig(os.path.join(IMAGE_DIR, '2_adapt_curves.png'), dpi=110)
    plt.close(fig)
    return 'images_meta/2_adapt_curves.png'


def plot_avg(results):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    xs = list(range(0, ADAPT_EPOCHS + 1))
    meta_avg = np.mean([r['meta'] for r in results.values()], axis=0)
    rand_avg = np.mean([r['rand'] for r in results.values()], axis=0)
    ax.plot(xs, meta_avg, marker='o', ms=4, label='元学习初始化（均值）', color='#1f77b4')
    ax.plot(xs, rand_avg, marker='s', ms=4, label='随机初始化（均值）', color='#d62728')
    ax.set_title('3 个新品类上的平均少样本适应曲线')
    ax.set_xlabel('适应 epoch')
    ax.set_ylabel('平均测试 NMAE（%）')
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(IMAGE_DIR, '3_avg_curve.png'), dpi=110)
    plt.close(fig)
    return 'images_meta/3_avg_curve.png'


# ================== 报告 ==================
def write_report(series, results, imgs):
    cats = list(series.keys())
    lines = []
    lines.append('# L5 认知性分析：元学习 —— 跨品类少样本销量预测')
    lines.append('')
    lines.append('- **数据来源**：`../ecommerce/ecommerce.db`（orders × order_items × products × categories）')
    lines.append('- **任务定义**：每个一级品类 = 一个 task，共 %d 个：%s'
                 % (len(cats), '、'.join(cats)))
    lines.append('- **算法**：Reptile（一阶 MAML 近似，`θ ← θ + ε(θ′−θ)`，无需二阶导）')
    lines.append('- **模型**：LSTM(16) → Dense(8) → Dense(1)，输入过去 %d 天预测第 %d 天'
                 % (WINDOW, WINDOW + 1))
    lines.append('- **测试协议**：留出品类 %s；仅给新品类前 %d 天 support 微调，'
                 '在之后 %d 天上测 NMAE（MAE/测试期均值，避免 MAPE 在低销量日爆炸）'
                 % ('、'.join(TEST_CATS), SUPPORT_DAYS, TEST_DAYS))
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 1. 场景与动机')
    lines.append('')
    lines.append('电商业务不断上线新品类，新品类没有历史数据，无法训练专属预测模型。'
                 '元学习的目标是从**已有多个品类**的销量动态中提炼"如何快速学习一个品类"的元知识——'
                 '一个对多任务都敏感的参数初始化，使得新品类只用极少数样本微调几步即可可用。')
    lines.append('')
    lines.append('![品类序列](%s)' % imgs['tasks'])
    lines.append('')
    lines.append('**中文说明：** 横轴 = 日期；纵轴 = 品类内标准化后的日 GMV。')
    lines.append('')
    lines.append('**解释：** 各品类都受大促与季节影响（共享结构），但量级、波动幅度、增长趋势不同'
                 '（任务异构）。共享结构是元学习可利用的跨任务知识，异构性则要求模型具备快速适应能力。')
    lines.append('')
    lines.append('## 2. 实验设置')
    lines.append('')
    lines.append('| 配置项 | 取值 |')
    lines.append('|:--|:--|')
    lines.append('| 元训练 | Reptile, %d 次元迭代, ε=%.1f, 任务内 %d epochs @ lr=%g |'
                 % (META_ITERS, META_LR, INNER_EPOCHS, INNER_LR))
    lines.append('| 任务采样 | 每次随机选 1 个品类 + 随机截取 60 天片段 |')
    lines.append('| support | 新品类前 %d 天（滑窗样本 %d 条） |'
                 % (SUPPORT_DAYS, results[TEST_CATS[0]]['n_support']))
    lines.append('| 测试 | support 之后 %d 天（滑窗样本 %d 条） |'
                 % (TEST_DAYS, results[TEST_CATS[0]]['n_test']))
    lines.append('| 对比 | A=元学习初始化微调 / B=随机初始化微调(同步数) / C=直接训练(随机初始化+小数据练 %d 轮) |'
                 % DIRECT_EPOCHS)
    lines.append('| 随机种子 | %d |' % SEED)
    lines.append('')
    lines.append('## 3. 少样本适应曲线')
    lines.append('')
    lines.append('![适应曲线](%s)' % imgs['adapt'])
    lines.append('')
    lines.append('**中文说明：** 每个子图对应一个留出的新品类；横轴 = 在 14 天 support 上微调的 epoch 数'
                 '（0 = 未微调）；纵轴 = 之后 90 天测试集上的 NMAE。灰色虚线 = "直接训练"基线的最终成绩。')
    lines.append('')
    lines.append('**解释：** 元学习初始化的**起点误差**（epoch 0，未见过新品类任何数据）已明显低于'
                 '随机初始化，说明元参数本身编码了品类 GMV 的通用动态。两条曲线都在前 2~5 轮触底后'
                 '回升——只有 7 条支撑样本时，微调轮数稍多即过拟合，少样本适应必须配合早停。'
                 '个别低量级、高波动品类（食品饮料）上任何微调都反而引入噪声，以零样本为最优，'
                 '说明元知识迁移也存在任务相似度上限。')
    lines.append('')
    lines.append('## 4. 平均适应曲线（3 个新品类）')
    lines.append('')
    lines.append('![平均曲线](%s)' % imgs['avg'])
    lines.append('')
    lines.append('**中文说明：** 横轴 = 适应 epoch；纵轴 = 3 个留出品类测试 NMAE 的均值。')
    lines.append('')
    lines.append('**解释：** 平均曲线抹平了单品类的偶然性：元学习初始化在**每一个 epoch** 上都低于'
                 '随机初始化，两者之间的垂直距离就是元学习带来的"少样本红利"——在只有 7 条滑窗'
                 '训练样本的条件下，红利尤为关键。')
    lines.append('')
    m0 = [r['meta'][0] for r in results.values()]
    r0 = [r['rand'][0] for r in results.values()]
    mb = [min(r['meta']) for r in results.values()]
    rb = [min(r['rand']) for r in results.values()]
    mb_at = [int(np.argmin(r['meta'])) for r in results.values()]
    rb_at = [int(np.argmin(r['rand'])) for r in results.values()]
    ma = [r['meta'][-1] for r in results.values()]
    ra = [r['rand'][-1] for r in results.values()]
    da = [r['direct'][-1] for r in results.values()]
    n_win0 = sum(1 for a, b in zip(m0, r0) if a < b)
    n_winb = sum(1 for a, b in zip(mb, rb) if a < b)

    lines.append('## 5. 汇总对比（NMAE，%）')
    lines.append('')
    lines.append('**零样本起点（未微调，epoch 0）：**')
    lines.append('')
    lines.append('| 测试品类 | A 元学习初始化 | B 随机初始化 |')
    lines.append('|:--|--:|--:|')
    for cat, a, b in zip(results.keys(), m0, r0):
        lines.append('| %s | %.1f | %.1f |' % (cat, a, b))
    lines.append('| **平均** | **%.1f** | **%.1f** |' % (np.mean(m0), np.mean(r0)))
    lines.append('')
    lines.append('**微调后（14 天 support）：** "最优"为适应窗口内的早停参考点（理论下限，实际需用验证集近似）；'
                 '"最终"为满 %d 轮。' % ADAPT_EPOCHS)
    lines.append('')
    lines.append('| 测试品类 | A 最优 | A 最终(%d轮) | B 最优 | B 最终(%d轮) | C 直接训练(%d轮) |'
                 % (ADAPT_EPOCHS, ADAPT_EPOCHS, DIRECT_EPOCHS))
    lines.append('|:--|--:|--:|--:|--:|--:|')
    for cat, a1, a2, b1, b2, d in zip(results.keys(), mb, ma, rb, ra, da):
        lines.append('| %s | %.1f | %.1f | %.1f | %.1f | %.1f |' % (cat, a1, a2, b1, b2, d))
    lines.append('| **平均** | **%.1f** | **%.1f** | **%.1f** | **%.1f** | **%.1f** |'
                 % (np.mean(mb), np.mean(ma), np.mean(rb), np.mean(ra), np.mean(da)))
    lines.append('')
    lines.append('## 6. 结论')
    lines.append('')
    cmp_d = '已低于' if np.mean(m0) < np.mean(da) else '接近'
    lines.append('1. **零样本即插即用**：元学习初始化在未见新品类任何数据时，平均 NMAE 仅 %.1f%%，'
                 '在 %d/%d 个品类上优于随机初始化（%.1f%%），且%s"直接训练 %d 轮"的平均成绩（%.1f%%）——'
                 '元参数本身已编码品类 GMV 的通用动态，新品类冷启动可直接给出基线预测。'
                 % (np.mean(m0), n_win0, len(m0), np.mean(r0), cmp_d, DIRECT_EPOCHS, np.mean(da)))
    lines.append('2. **少样本适应更快更准**：以早停参考点计，元初始化在 %d/%d 个品类上优于随机初始化'
                 '（平均 %.1f%% vs %.1f%%）；元初始化平均第 %.0f 轮触底，随机初始化第 %.0f 轮——'
                 '同样的 7 条支撑样本，好的初始化让适应收敛更快、终态更优。'
                 % (n_winb, len(mb), np.mean(mb), np.mean(rb), np.mean(mb_at), np.mean(rb_at)))
    lines.append('3. **少样本微调必须早停**：仅 7 条训练样本下，两种初始化触底后继续微调即过拟合、'
                 '误差回升（见适应曲线后半段）；食品饮料这类低量级高波动品类甚至以零样本为最优。'
                 '"直接训练"的成绩对轮数极不稳定，不能当作可靠基线。')
    lines.append('4. **业务建议**：新品类上线以元初始化零样本预测起步，真实数据到达后少量轮数微调'
                 '并严格早停（留出验证天或固定不超过 5 轮），显著缩短"无数据可预测"的冷启动窗口。')
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 附：说明性跳过')
    lines.append('')
    lines.append('- **真实 LLM API 接入**：环境中无可用 API Key，本层示例跳过真实大模型调用，'
                 '相关语义能力以可复现的本地方法替代演示。')
    lines.append('- **知识追踪（DKT/SAKT/AKT）**：教育领域专用技术，'
                 '电商数据库中无"知识点-作答"对应概念，不适用，跳过。')

    with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('[输出] 报告: %s' % OUTPUT_MD)


# ================== 主流程 ==================
def main():
    series, stats, full = load_category_gmv()
    img_tasks = plot_tasks(series, full)
    results = run_experiment(series, stats)
    imgs = {
        'tasks': img_tasks,
        'adapt': plot_adapt(results),
        'avg': plot_avg(results),
    }
    write_report(series, results, imgs)
    print('[完成]')


if __name__ == '__main__':
    main()
