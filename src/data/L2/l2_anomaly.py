#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L2 诊断性分析：异常检测示例
- 背景: 数据中被注入约 1.2% 批发型异常(单行数量30-200)与 0.5% 价格异常(单价×10)
- 真值标签(近似): 明细行 quantity>=30 或 unit_price 超过所属类目价格带3倍
- 特征(订单级): total_amount / 总数量 / 明细行数(连带率) / 最大单价
- 方法: IsolationForest + LOF，报告 precision/recall，散点可视化
- 数据源: data/ecommerce/ecommerce.db
- 输出: anomaly_report.md + images_anomaly/
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
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'ecommerce', 'ecommerce.db'))
OUTPUT_MD = os.path.join(SCRIPT_DIR, 'anomaly_report.md')
IMAGE_DIR = os.path.join(SCRIPT_DIR, 'images_anomaly')

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

# ================== 1. 数据与真值标签 ==================
print("[数据] 加载订单明细并构造订单级特征...")
conn = sqlite3.connect(DB_PATH)
items = pd.read_sql_query("""
SELECT oi.item_id, oi.order_id, oi.quantity, oi.unit_price, oi.subtotal,
       p.list_price, p.category_id
FROM order_items oi
JOIN products p ON oi.product_id = p.product_id
""", conn)
orders = pd.read_sql_query("""
SELECT order_id, total_amount FROM orders
WHERE order_status IN ('已完成', '已发货')
""", conn)
conn.close()

# 类目价格带：二级类目 list_price 的 95 分位作为价格带上沿
band = items.groupby('category_id')['list_price'].quantile(0.95).rename('band_hi')
items = items.merge(band, on='category_id')
items['is_anomaly'] = ((items['quantity'] >= 30) |
                       (items['unit_price'] > 3 * items['band_hi'])).astype(int)
anomaly_orders = set(items.loc[items['is_anomaly'] == 1, 'order_id'])

R.h1("数据与真值标签")
R.text("数据中被刻意注入两类异常：\n"
       "1. **批发型异常**（约 1.2% 订单）：单行数量 30~200 件；\n"
       "2. **价格异常**（约 0.5% 订单）：成交单价 = 正常价 × 10。")
R.text("由于真实注入标记不可见，用规则**近似构造真值标签**：\n"
       "- `quantity >= 30`（批发阈值）；\n"
       "- `unit_price > 3 × 所属二级类目价格带上沿`（价格带上沿取该类目标价的 95 分位）。\n"
       "订单级标签：订单内任一明细行命中即为异常订单。")
n_item_anom = items['is_anomaly'].sum()
R.table(pd.DataFrame([
    ['明细行总数', len(items)],
    ['命中异常的明细行', int(n_item_anom)],
    ['其中 quantity>=30', int((items['quantity'] >= 30).sum())],
    ['其中 单价超价格带3倍', int((items['unit_price'] > 3 * items['band_hi']).sum())],
    ['异常订单数（去重）', len(anomaly_orders)],
], columns=['指标', '数值']))
R.text("**说明：** 该规则是注入模式的近似还原——价格异常的判定依赖类目价格带口径，"
       "个别「10 倍于低价商品」的注入单若未超过类目价格带 3 倍会被漏标，"
       "因此后文的 precision/recall 是对模型效果的近似评估。")

# ================== 2. 订单级特征 ==================
R.h1("订单级特征工程")
feat = items.groupby('order_id').agg(
    n_items=('item_id', 'count'),
    total_qty=('quantity', 'sum'),
    max_qty=('quantity', 'max'),
    max_price=('unit_price', 'max'),
    mean_price=('unit_price', 'mean'),
).reset_index()
feat = feat.merge(orders, on='order_id', how='inner')
feat['attach_rate'] = feat['total_qty'] / feat['n_items']  # 连带率：平均每行件数
feat['is_anomaly'] = feat['order_id'].isin(anomaly_orders).astype(int)

feature_cols = ['total_amount', 'total_qty', 'n_items', 'attach_rate', 'max_price']
R.text("订单级特征：\n"
       "- `total_amount`：订单实付金额；\n"
       "- `total_qty`：订单总件数；\n"
       "- `n_items`：明细行数（商品种数）；\n"
       "- `attach_rate`：连带率 = 总件数 / 明细行数；\n"
       "- `max_price`：订单内最高成交单价。")
R.text("**特征概览：**")
R.table(feat[feature_cols].describe().reset_index().rename(columns={'index': '统计量'}))
R.text("**标签分布：** 异常订单 %d / 总订单 %d（%.2f%%）"
       % (feat['is_anomaly'].sum(), len(feat), 100 * feat['is_anomaly'].mean()))

X = StandardScaler().fit_transform(feat[feature_cols])
y = feat['is_anomaly'].values

# ================== 3. IsolationForest ==================
R.h1("IsolationForest")
print("[模型] IsolationForest...")
CONTAM = 0.02
iso = IsolationForest(n_estimators=300, contamination=CONTAM, random_state=42)
iso_pred = (iso.fit_predict(X) == -1).astype(int)

def pr_metrics(y_true, y_pred):
    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return tp, fp, fn, prec, rec, f1

tp, fp, fn, prec, rec, f1 = pr_metrics(y, iso_pred)
R.text("**Python 代码：**")
R.code("python", """iso = IsolationForest(n_estimators=300, contamination=0.02, random_state=42)
pred = (iso.fit_predict(X_scaled) == -1).astype(int)
# 与近似真值比较
precision = TP / (TP + FP); recall = TP / (TP + FN)""")
R.table(pd.DataFrame([
    ['TP', tp], ['FP', fp], ['FN', fn],
    ['Precision', round(prec, 4)], ['Recall', round(rec, 4)], ['F1', round(f1, 4)],
], columns=['指标', '数值']))
R.text("**解释：** IsolationForest 通过随机切分孤立样本，异常点更容易被孤立。"
       "contamination=0.02 略高于真实异常率（约 1.3%），用召回换覆盖。")

# ================== 4. LOF ==================
R.h1("LOF（局部离群因子）")
print("[模型] LOF...")
lof = LocalOutlierFactor(n_neighbors=20, contamination=CONTAM)
lof_pred = (lof.fit_predict(X) == -1).astype(int)
tp2, fp2, fn2, prec2, rec2, f12 = pr_metrics(y, lof_pred)
R.table(pd.DataFrame([
    ['TP', tp2], ['FP', fp2], ['FN', fn2],
    ['Precision', round(prec2, 4)], ['Recall', round(rec2, 4)], ['F1', round(f12, 4)],
], columns=['指标', '数值']))
R.text("**解释：** LOF 比较样本与其 k 近邻的局部密度。批发单（数量极大）处于稀疏区域，"
       "容易被 LOF 捕获；但 LOF 对全局稀疏异常（如孤立的 10 倍单价）"
       "在标准化空间中可能不如 IsolationForest 稳定。")

# ================== 5. 模型对比与可视化 ==================
R.h1("模型对比与可视化")
R.table(pd.DataFrame([
    ['IsolationForest', prec, rec, f1],
    ['LOF', prec2, rec2, f12],
], columns=['模型', 'Precision', 'Recall', 'F1']))
R.text("**解释：** Precision 回答「报警的订单中有多少是真异常」，决定运营审核成本；"
       "Recall 回答「真异常抓住了多少」，决定风险敞口。业务上风控场景偏 Recall，"
       "审核资源紧张时偏 Precision。")

fig, axes = plt.subplots(1, 3, figsize=(18, 5), sharex=True, sharey=True)
for ax, pred, title in [
    (axes[0], y, 'Ground Truth (近似真值)'),
    (axes[1], iso_pred, 'IsolationForest'),
    (axes[2], lof_pred, 'LOF'),
]:
    normal = pred == 0
    ax.scatter(feat.loc[normal, 'total_qty'], feat.loc[normal, 'total_amount'],
               s=8, alpha=0.3, label='正常', c='steelblue')
    ax.scatter(feat.loc[~normal, 'total_qty'], feat.loc[~normal, 'total_amount'],
               s=25, alpha=0.9, label='异常', c='red', edgecolors='k', linewidths=0.3)
    ax.set_xlabel('total_qty（订单总件数）')
    ax.set_title(title)
    ax.legend()
axes[0].set_ylabel('total_amount（订单金额）')
plt.suptitle('Anomaly Detection: total_qty vs total_amount')
R.save_plt('5_1_scatter.png')
R.image('5_1_scatter.png', 'Anomaly Scatter | 异常检测散点对比')
R.text("**中文说明：** 三张图依次为近似真值、IsolationForest 预测、LOF 预测。"
       "红点=异常。批发单聚集在右侧（总件数 30+），价格异常单分布在上方（金额虚高）。")

# 单价视角
fig, axes = plt.subplots(1, 3, figsize=(18, 5), sharex=True, sharey=True)
for ax, pred, title in [
    (axes[0], y, 'Ground Truth (近似真值)'),
    (axes[1], iso_pred, 'IsolationForest'),
    (axes[2], lof_pred, 'LOF'),
]:
    normal = pred == 0
    ax.scatter(feat.loc[normal, 'max_price'], feat.loc[normal, 'total_amount'],
               s=8, alpha=0.3, label='正常', c='steelblue')
    ax.scatter(feat.loc[~normal, 'max_price'], feat.loc[~normal, 'total_amount'],
               s=25, alpha=0.9, label='异常', c='red', edgecolors='k', linewidths=0.3)
    ax.set_xlabel('max_price（订单最高单价）')
    ax.set_title(title)
    ax.legend()
axes[0].set_ylabel('total_amount（订单金额）')
plt.suptitle('Anomaly Detection: max_price vs total_amount')
R.save_plt('5_2_scatter_price.png')
R.image('5_2_scatter_price.png', 'Anomaly Scatter (price view) | 价格视角异常散点')
R.text("**中文说明：** 横轴换成订单内最高单价后，价格异常单（单价×10）在右侧明显离群，"
       "与批发单（右侧高件数）形成两个不同的异常簇——说明两类异常需要不同特征才能同时捕获。")

# ================== 6. 结论 ==================
R.h1("结论与建议")
R.text("1. 两类注入异常在特征空间中形态不同：批发单靠 `total_qty/max_qty` 捕获，"
       "价格异常单靠 `max_price` 捕获，特征工程比算法选择更关键。\n"
       "2. IsolationForest 与 LOF 在本任务上互补：前者全局切分、对极端值敏感；"
       "后者基于局部密度。生产上可两者取并集提高召回。\n"
       "3. 真值标签是规则近似，评估数字有偏差；若有真实标注（如风控审核记录），"
       "应以其为准并可升级为有监督模型。")

R.write([
    "# 异常检测报告 - 订单异常识别\n",
    "- **数据来源**：`data/ecommerce/ecommerce.db`（order_items/orders/products）",
    "- **样本量**：%d 个已支付订单，近似真值异常 %d 个（%.2f%%）"
    % (len(feat), feat['is_anomaly'].sum(), 100 * feat['is_anomaly'].mean()),
    "- **方法**：IsolationForest + LOF（无监督），规则近似真值评估 precision/recall\n",
])
print("[完成] anomaly_report.md")
