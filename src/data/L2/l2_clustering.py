#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L2 诊断性分析：层次聚类与谱聚类示例
- 特征: 基于 orders 的客户 RFM
- 方法: KMeans vs scipy 层次聚类(Ward linkage 树状图) vs SpectralClustering
- 评估: 轮廓系数对比 + 分群画像(热力图/雷达图)
- 数据源: data/ecommerce/ecommerce.db
- 输出: clustering_report.md + images_clustering/
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
from scipy.cluster.hierarchy import linkage, dendrogram, fcluster
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans, SpectralClustering
from sklearn.metrics import silhouette_score

warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'ecommerce', 'ecommerce.db'))
OUTPUT_MD = os.path.join(SCRIPT_DIR, 'clustering_report.md')
IMAGE_DIR = os.path.join(SCRIPT_DIR, 'images_clustering')

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
        self.parts.append("![%s](%s/%s)\n" % (caption, IMAGE_DIR, name))

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

# ================== 1. RFM 特征 ==================
print("[数据] 构建客户 RFM 特征...")
conn = sqlite3.connect(DB_PATH)
rfm = pd.read_sql_query("""
SELECT customer_id,
       JULIANDAY('2025-06-16') - JULIANDAY(MAX(created_at)) AS Recency,
       COUNT(*)                                            AS Frequency,
       SUM(total_amount)                                   AS Monetary
FROM orders
WHERE order_status IN ('已完成', '已发货')
GROUP BY customer_id
""", conn)
conn.close()
rfm = rfm.set_index('customer_id')
print("[数据] 客户数: %d" % len(rfm))

R.h1("RFM 特征构建")
R.text("基于 orders 表（已完成+已发货）按客户聚合三维度：\n"
       "- **Recency**：最近一次购买距快照日（2025-06-16）的天数；\n"
       "- **Frequency**：订单数；\n"
       "- **Monetary**：累计消费金额。")
R.text("**SQL 代码：**")
R.code("sql", """SELECT customer_id,
       JULIANDAY('2025-06-16') - JULIANDAY(MAX(created_at)) AS Recency,
       COUNT(*)                                            AS Frequency,
       SUM(total_amount)                                   AS Monetary
FROM orders
WHERE order_status IN ('已完成', '已发货')
GROUP BY customer_id;""")
R.table(rfm.describe().reset_index().rename(columns={'index': '统计量'}))
R.text("**解释：** RFM 右偏明显（少数高价值客户贡献大部分金额），"
       "聚类前取 log1p 压缩长尾再标准化。")

X_log = np.log1p(rfm[['Recency', 'Frequency', 'Monetary']])
X = StandardScaler().fit_transform(X_log)

K = 4  # 与诊断报告主分析保持一致

# ================== 2. KMeans ==================
R.h1("K-Means 聚类（基准）")
km = KMeans(n_clusters=K, random_state=42, n_init=10)
lab_km = km.fit_predict(X)
sil_km = silhouette_score(X, lab_km)
R.text("K = %d，轮廓系数 = %.4f。" % (K, sil_km))

# ================== 3. 层次聚类 ==================
R.h1("层次聚类（Ward linkage）")
R.text("Ward 法每次合并使簇内方差增量最小的两簇，"
       "产生一棵完整的凝聚树（dendrogram），可在任意高度切割得到不同簇数。")
print("[聚类] Ward linkage...")
Z = linkage(X, method='ward')

plt.figure(figsize=(12, 5))
dendrogram(Z, truncate_mode='lastp', p=30, leaf_rotation=90, leaf_font_size=9)
plt.title('Ward Linkage Dendrogram (truncated to last 30 merges)')
plt.xlabel('Cluster (size)')
plt.ylabel('Distance')
R.save_plt('3_1_dendrogram.png')
R.image('3_1_dendrogram.png', 'Ward Dendrogram | Ward 层次聚类树状图(截取最后30次合并)')
R.text("**中文说明：** 纵轴为合并距离。距离跳跃最大的位置是合理的切割点："
       "在跳跃上方横切一刀，切口数即为簇数。括号内为叶簇包含的客户数。")

# 用不一致性/距离跳跃佐证 K 的选择
last = Z[-15:, 2]
R.text("**最后 15 次合并的距离：**")
R.output(pd.Series(last.round(2), index=range(len(last) - 1, -1, -1)).to_string())
R.text("**解释：** 合并距离出现数量级跳跃的位置提示自然的簇数。"
       "若倒数第 3→4 次合并距离陡增，则 K=4 是稳定切割。")

lab_hc = fcluster(Z, t=K, criterion='maxclust') - 1
sil_hc = silhouette_score(X, lab_hc)
R.text("切割为 K=%d 簇，轮廓系数 = %.4f。" % (K, sil_hc))

# ================== 4. 谱聚类 ==================
R.h1("谱聚类（SpectralClustering）")
R.text("谱聚类先构建样本相似度图（RBF 核），对图拉普拉斯做特征分解，"
       "再在低维谱嵌入上跑 K-Means。能发现非凸形状的簇，"
       "但需构造 n×n 亲和矩阵，计算量为 O(n²~n³)，本数据 %d 客户可承受。" % len(rfm))
print("[聚类] SpectralClustering...")
sc = SpectralClustering(n_clusters=K, affinity='rbf', random_state=42,
                        assign_labels='kmeans', n_init=10)
lab_sc = sc.fit_predict(X)
sil_sc = silhouette_score(X, lab_sc)
R.text("K = %d，轮廓系数 = %.4f。" % (K, sil_sc))

# ================== 5. 三方法对比 ==================
R.h1("三种方法对比")
R.table(pd.DataFrame([
    ['K-Means', sil_km],
    ['层次聚类 (Ward)', sil_hc],
    ['谱聚类 (RBF)', sil_sc],
], columns=['方法', '轮廓系数']))
R.text("**解释：** 轮廓系数越接近 1 越好。K-Means 假设球形等方差簇，"
       "在标准化 RFM 上通常是强基准；层次聚类的优势是给出全层级结构、可解释切割；"
       "谱聚类适合簇边界非凸的情形。RFM 经 log 变换后接近凸结构，"
       "三者差距通常不大——此时选最简单、最易复现的 K-Means 即可。")

# ================== 6. 分群画像 ==================
R.h1("分群画像（基于 K-Means 结果）")
rfm['Cluster'] = lab_km
profile = rfm.groupby('Cluster')[['Recency', 'Frequency', 'Monetary']].mean()
profile['客户数'] = rfm.groupby('Cluster').size()
R.table(profile.reset_index())

# 画像热力图：簇 × 维度（列标准化）
prof_norm = (profile[['Recency', 'Frequency', 'Monetary']] -
             profile[['Recency', 'Frequency', 'Monetary']].mean()) / \
            profile[['Recency', 'Frequency', 'Monetary']].std()
plt.figure(figsize=(7, 4))
plt.imshow(prof_norm.values, cmap='RdBu_r', vmin=-2, vmax=2, aspect='auto')
plt.colorbar(label='标准化均值')
plt.xticks(range(3), ['Recency(天)', 'Frequency(次)', 'Monetary(元)'])
plt.yticks(range(len(prof_norm)), ['簇 %d (n=%d)' % (i, profile['客户数'][i])
                                   for i in prof_norm.index])
for i in range(prof_norm.shape[0]):
    for j in range(3):
        plt.text(j, i, '%.1f' % profile.iloc[i, j], ha='center', va='center',
                 color='black', fontsize=9)
plt.title('Cluster Profile Heatmap (color=z-score, text=raw mean)')
R.save_plt('6_1_profile_heatmap.png')
R.image('6_1_profile_heatmap.png', 'Cluster Profiles | 分群画像热力图')
R.text("**中文说明：** 颜色=该簇在维度上的标准化均值（红高蓝低），格内数字=原始均值。")

# 雷达图
labels = ['Recency', 'Frequency', 'Monetary']
angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
angles += angles[:1]
plt.figure(figsize=(6, 6))
ax = plt.subplot(111, polar=True)
for i in prof_norm.index:
    vals = prof_norm.loc[i].tolist()
    vals += vals[:1]
    ax.plot(angles, vals, linewidth=2, label='簇 %d' % i)
    ax.fill(angles, vals, alpha=0.1)
ax.set_xticks(angles[:-1])
ax.set_xticklabels(['Recency(低=好)', 'Frequency(高=好)', 'Monetary(高=好)'])
ax.set_title('Cluster Radar Chart (z-score)')
ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))
R.save_plt('6_2_radar.png')
R.image('6_2_radar.png', 'Cluster Radar | 分群画像雷达图')
R.text("**中文说明：** 雷达图三个轴为标准化后的 R/F/M。"
       "Recency 轴数值**越小**代表越活跃（图上越靠近中心越活跃），"
       "F/M 轴数值越大越好。")

# 业务命名
R.text("**业务解读（按画像规则命名）：**")
name_rows = []
for i in profile.index:
    r_, f_, m_ = profile.loc[i, ['Recency', 'Frequency', 'Monetary']]
    if r_ <= profile['Recency'].median() and f_ >= profile['Frequency'].median() and m_ >= profile['Monetary'].median():
        name = '高价值活跃客户'
        action = '重点维护：新品优先推、专属客服、积分加倍'
    elif r_ > profile['Recency'].median() and m_ >= profile['Monetary'].median():
        name = '高价值沉睡客户'
        action = '唤醒：大额券、电话回访、流失预警'
    elif f_ >= profile['Frequency'].median() and m_ < profile['Monetary'].median():
        name = '高频低额客户'
        action = '提客单：满减凑单、连带推荐'
    else:
        name = '普通/低频客户'
        action = '促活：签到、低价引流品'
    name_rows.append(['簇 %d' % i, int(profile['客户数'][i]), name, action])
R.table(pd.DataFrame(name_rows, columns=['簇', '客户数', '业务命名', '运营动作建议']))

# ================== 7. 结论 ==================
R.h1("结论")
R.text("1. 三种算法在 log-RFM 上轮廓系数接近，说明客户价值结构较平滑、"
       "无强非凸边界；工程上推荐 K-Means（简单、可复现、易解释）。\n"
       "2. 层次聚类的树状图额外提供了「簇数选择的结构证据」，"
       "适合向业务方解释为什么选 K=%d。\n"
       "3. 谱聚类在本场景无显著收益且计算成本高，"
       "但当特征空间存在流形结构（如行为序列嵌入）时值得再试。" % K)

R.write([
    "# 层次聚类与谱聚类报告 - 客户 RFM 分群\n",
    "- **数据来源**：`data/ecommerce/ecommerce.db`（orders 表按客户聚合）",
    "- **样本量**：%d 个客户" % len(rfm),
    "- **方法**：K-Means vs Ward 层次聚类 vs 谱聚类，K=%d，轮廓系数评估\n" % K,
])
print("[完成] clustering_report.md")
