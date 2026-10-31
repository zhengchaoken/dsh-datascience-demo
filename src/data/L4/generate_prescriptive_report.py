#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L4 规范性分析报告生成器
- 数据源: 统一电商数据库 data/ecommerce/ecommerce.db (SQLite)
- 隐式评分: 用户-商品购买次数（按订单去重），cap 5
- 分析: 协同过滤 / 矩阵分解 / 序列推荐 / RL策略优化
- 输出: Markdown 报告 + images_prescriptive/ 图片目录
- 图片引用使用相对路径
"""

import os
import math
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

# 推荐系统
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.decomposition import TruncatedSVD
from sklearn.model_selection import train_test_split

# 评估
from sklearn.metrics import mean_squared_error, mean_absolute_error

warnings.filterwarnings('ignore')

# ================== 配置区：相对路径 ==================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'ecommerce', 'ecommerce.db'))
if not os.path.isfile(DB_PATH):
    raise FileNotFoundError("未找到电商数据库: %s" % DB_PATH)

OUTPUT_MD = os.path.join(SCRIPT_DIR, 'prescriptive_report.md')
IMAGE_DIR = os.path.join(SCRIPT_DIR, 'images_prescriptive')

# 只清理本报告生成的图片（数字章节前缀），保留 9.4 专题脚本（dqn_/bandit_/ips_/mo_）的图
os.makedirs(IMAGE_DIR, exist_ok=True)
for fn in os.listdir(IMAGE_DIR):
    if fn.endswith('.png') and fn[0].isdigit():
        os.remove(os.path.join(IMAGE_DIR, fn))

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

# ================== 加载数据 ==================
print("[数据] 加载中: %s" % DB_PATH)
conn = sqlite3.connect(DB_PATH)

def sql(q):
    return pd.read_sql_query(q, conn)

# 有效成交订单（已完成+已发货）的明细作为用户-商品交互
interactions = sql("""
SELECT o.customer_id, oi.product_id, o.created_at, oi.quantity
FROM order_items oi
JOIN orders o ON oi.order_id = o.order_id
WHERE o.order_status IN ('已完成','已发货')
""")
interactions['created_at'] = pd.to_datetime(interactions['created_at'])

# 隐式评分：同一用户对同一商品的购买订单数，cap 5
ratings = (interactions
           .groupby(['customer_id', 'product_id'])
           .agg(rating=('created_at', 'count'),
                last_ts=('created_at', 'max'))
           .reset_index())
ratings['rating'] = ratings['rating'].clip(upper=5).astype(float)
ratings = ratings.rename(columns={'customer_id': 'userId', 'product_id': 'movieId',
                                  'last_ts': 'timestamp'})

products = sql("SELECT product_id, product_name, brand, list_price, cost FROM products")

print("[数据] 交互行数: %d, 用户数: %d, 商品数: %d"
      % (len(ratings), ratings['userId'].nunique(), ratings['movieId'].nunique()))

# 过滤冷门商品（购买记录少于 min_ratings 的商品）
min_ratings = 20
item_counts = ratings['movieId'].value_counts()
popular_items = item_counts[item_counts >= min_ratings].index
ratings = ratings[ratings['movieId'].isin(popular_items)]
print("[数据] 过滤后交互行数: %d, 商品数: %d"
      % (len(ratings), ratings['movieId'].nunique()))

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

    def write(self):
        header = []
        header.append("# 规范性分析报告 - 电商订单数据\n")
        header.append("- **数据来源**：`data/ecommerce/ecommerce.db`（orders + order_items，已完成/已发货订单）")
        header.append("- **隐式评分口径**：用户-商品购买订单数，cap 5")
        header.append("- **交互行数**：%d" % len(ratings))
        header.append("- **用户数**：%d" % ratings['userId'].nunique())
        header.append("- **商品数**：%d\n" % ratings['movieId'].nunique())
        header.append('<a id="toc"></a>\n## 目录\n')
        header.append("\n".join(self.toc) + "\n\n---\n")
        with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
            f.write("\n".join(header) + "\n".join(self.parts))
        print("[OK] 报告：%s" % OUTPUT_MD)
        print("[OK] 图片：%s/ 共 %d 张" % (IMAGE_DIR, len(os.listdir(IMAGE_DIR))))

R = Report()

# ================== 评估指标函数 ==================
def precision_at_k(actual_set, recs, k):
    recs_k = recs[:k]
    return len(actual_set.intersection(recs_k)) / max(1, k)

def recall_at_k(actual_set, recs, k):
    recs_k = recs[:k]
    return len(actual_set.intersection(recs_k)) / max(1, len(actual_set))

def dcg_at_k(recs, actual_set, k):
    dcg = 0.0
    for i, r in enumerate(recs[:k], start=1):
        dcg += (1.0 if r in actual_set else 0.0) / np.log2(i + 1)
    return dcg

def ndcg_at_k(actual_set, recs, k):
    ideal = sum(1.0 / np.log2(i + 2) for i in range(min(len(actual_set), k)))
    return 0.0 if ideal == 0 else dcg_at_k(recs, actual_set, k) / ideal

def hit_rate_at_k(actual_set, recs, k):
    recs_k = recs[:k]
    return 1.0 if len(actual_set.intersection(recs_k)) > 0 else 0.0


# ============================================================
# 1. 数据概览
# ============================================================
R.h1("数据概览")
R.text("本报告基于统一电商数据库 `ecommerce.db`，以有效成交订单（已完成/已发货）的明细"
       "构造用户-商品隐式评分矩阵：同一用户对同一商品的购买订单数作为评分，cap 5。"
       "规范性分析从**协同过滤**、**矩阵分解**、**序列推荐**、"
       "**强化学习策略优化**四个维度展开。")

R.h2("字段说明")
R.table(pd.DataFrame([
    ['userId', '客户ID', 'orders.customer_id'],
    ['movieId', '商品ID', 'order_items.product_id（沿用推荐脚本变量名）'],
    ['rating', '隐式评分', '购买订单数，cap 5'],
    ['timestamp', '最近购买时间', '该用户购买该商品的最后一次下单时间'],
], columns=['字段', '中文说明', '描述']))

R.h2("样本预览")
R.table(ratings[['userId', 'movieId', 'rating', 'timestamp']].head())

R.h2("隐式评分分布")
R.text("**SQL 代码：**")
R.code("sql",
       "SELECT cnt AS rating, COUNT(*) AS users_items\n"
       "FROM (SELECT o.customer_id, oi.product_id, COUNT(*) AS cnt\n"
       "      FROM order_items oi JOIN orders o ON oi.order_id = o.order_id\n"
       "      WHERE o.order_status IN ('已完成','已发货')\n"
       "      GROUP BY o.customer_id, oi.product_id)\n"
       "GROUP BY cnt ORDER BY cnt;")
R.table(sql("""
SELECT cnt AS rating, COUNT(*) AS users_items
FROM (SELECT o.customer_id, oi.product_id, COUNT(*) AS cnt
      FROM order_items oi JOIN orders o ON oi.order_id = o.order_id
      WHERE o.order_status IN ('已完成','已发货')
      GROUP BY o.customer_id, oi.product_id)
GROUP BY cnt ORDER BY cnt;
"""))

plt.figure(figsize=(10, 4))
ratings['rating'].value_counts().sort_index().plot(kind='bar')
plt.title('Implicit Rating Distribution')
plt.xlabel('Rating (purchase count, capped at 5)')
plt.ylabel('Count')
R.save_plt('1_2_rating_dist.png')
R.image('1_2_rating_dist.png', 'Implicit Rating Distribution | 隐式评分分布')
R.text("**中文说明：** 横轴 = 隐式评分（购买次数，cap 5）；纵轴 = 用户-商品对数量。"
       "绝大多数用户-商品对只购买 1 次，复购 2 次以上的长尾是推荐系统要挖掘的信号。")


# ============================================================
# 2. 协同过滤
# ============================================================
R.h1("协同过滤")
R.text("协同过滤（Collaborative Filtering）基于用户或物品的相似性进行推荐。"
       "分为 UserCF（基于用户）和 ItemCF（基于物品）两种。")

# 构建用户-物品评分矩阵
user_item = ratings.pivot_table(index='userId', columns='movieId',
                                 values='rating', fill_value=0)
print("[协同过滤] 用户-物品矩阵: %s" % str(user_item.shape))

R.h2("UserCF 用户相似度")
R.text("计算用户之间的余弦相似度，找出购物偏好相似的用户群体。")
R.text("**SQL 代码（用户共同购买统计）：**")
R.code("sql",
       "SELECT a.customer_id AS u1, b.customer_id AS u2, COUNT(*) AS common_items\n"
       "FROM (SELECT DISTINCT o.customer_id, oi.product_id\n"
       "      FROM order_items oi JOIN orders o ON oi.order_id=o.order_id\n"
       "      WHERE o.order_status IN ('已完成','已发货')) a\n"
       "JOIN (SELECT DISTINCT o.customer_id, oi.product_id\n"
       "      FROM order_items oi JOIN orders o ON oi.order_id=o.order_id\n"
       "      WHERE o.order_status IN ('已完成','已发货')) b\n"
       "  ON a.product_id = b.product_id AND a.customer_id < b.customer_id\n"
       "GROUP BY u1, u2 ORDER BY common_items DESC LIMIT 10;")
R.table(sql("""
SELECT a.customer_id AS u1, b.customer_id AS u2, COUNT(*) AS common_items
FROM (SELECT DISTINCT o.customer_id, oi.product_id
      FROM order_items oi JOIN orders o ON oi.order_id=o.order_id
      WHERE o.order_status IN ('已完成','已发货')) a
JOIN (SELECT DISTINCT o.customer_id, oi.product_id
      FROM order_items oi JOIN orders o ON oi.order_id=o.order_id
      WHERE o.order_status IN ('已完成','已发货')) b
  ON a.product_id = b.product_id AND a.customer_id < b.customer_id
GROUP BY u1, u2 ORDER BY common_items DESC LIMIT 10;
"""))

R.text("**Python 代码：**")
R.code("python",
       "user_sim = cosine_similarity(user_item)\n"
       "print('用户相似度矩阵形状:', user_sim.shape)")
user_sim = cosine_similarity(user_item)
R.text("**Python 结果：**")
R.output("用户相似度矩阵形状: %s" % str(user_sim.shape))
R.text("**解释：** 余弦相似度取值范围 [0, 1]，值越大表示两个用户的购买模式越相似。"
       "相似度矩阵可用于找到目标用户的 K 个最近邻，"
       "基于近邻的购买记录预测目标用户对未购商品的兴趣。")

R.h2("ItemCF 物品相似度")
R.text("计算物品之间的余弦相似度，基于物品相似性进行推荐。")
R.text("**Python 代码：**")
R.code("python",
       "item_sim = cosine_similarity(user_item.T)\n"
       "print('物品相似度矩阵形状:', item_sim.shape)")
item_sim = cosine_similarity(user_item.T)
R.text("**Python 结果：**")
R.output("物品相似度矩阵形状: %s" % str(item_sim.shape))

# 可视化物品相似度（取前50个物品）
plt.figure(figsize=(10, 8))
sns.heatmap(item_sim[:50, :50], cmap='coolwarm', center=0)
plt.title('Item Similarity Heatmap (Top 50 Items)')
R.save_plt('2_2_item_sim.png')
R.image('2_2_item_sim.png', 'Item Similarity Heatmap | 物品相似度热力图')
R.text("**中文说明：** 颜色越红表示两个商品越相似，越蓝表示越不相似。")
R.text("**解释：** ItemCF 适合商品数量相对稳定的场景，"
       "可解释性强（“买了 A 的人也买了 B”），是电商详情页相关推荐的常用策略。")


# ============================================================
# 3. 矩阵分解
# ============================================================
R.h1("矩阵分解")
R.text("矩阵分解（Matrix Factorization）通过降维发现潜在特征（Latent Factors），"
       "将用户和商品映射到低维空间，是推荐系统的经典方法。")

R.h2("SVD 降维")

# 使用 TruncatedSVD 分解
n_components = min(50, min(user_item.shape) - 1)
svd = TruncatedSVD(n_components=n_components, random_state=42)
user_factors = svd.fit_transform(user_item)
item_factors = svd.components_.T

print("[SVD] 解释方差比: %.4f" % svd.explained_variance_ratio_.sum())

R.text("**Python 代码：**")
R.code("python",
       "svd = TruncatedSVD(n_components=50, random_state=42)\n"
       "user_factors = svd.fit_transform(user_item)\n"
       "item_factors = svd.components_.T\n"
       "print('解释方差比:', svd.explained_variance_ratio_.sum())")
R.text("**Python 结果：**")
R.output("用户因子形状: %s\n物品因子形状: %s\n解释方差比: %.4f"
         % (str(user_factors.shape), str(item_factors.shape),
            svd.explained_variance_ratio_.sum()))

# 可视化解释方差
plt.figure(figsize=(10, 4))
plt.plot(range(1, n_components + 1), np.cumsum(svd.explained_variance_ratio_), 'bo-')
plt.xlabel('Number of Components')
plt.ylabel('Cumulative Explained Variance')
plt.title('SVD Explained Variance')
R.save_plt('3_1_svd_variance.png')
R.image('3_1_svd_variance.png', 'SVD Explained Variance | SVD 解释方差曲线')
R.text("**中文说明：** 横轴 = 主成分数；纵轴 = 累计解释方差比。")
R.text("**解释：** 电商隐式反馈矩阵比显式评分更稀疏，前 50 个潜在因子解释的方差比偏低"
       "属于正常现象。曲线越陡说明潜在结构越强。")

R.h2("评分预测与评估")
R.text("用矩阵分解重建隐式评分，并在测试集上评估。")

# 划分训练/测试集
train_data, test_data = train_test_split(ratings, test_size=0.2, random_state=42)

# 构建训练集矩阵
train_matrix = train_data.pivot_table(index='userId', columns='movieId',
                                       values='rating', fill_value=0)

R.text("**Python 代码：**")
R.code("python",
       "train_data, test_data = train_test_split(ratings, test_size=0.2, random_state=42)\n"
       "train_matrix = train_data.pivot_table(...)\n"
       "svd_pred = TruncatedSVD(n_components=50, random_state=42)\n"
       "pred_matrix = svd_pred.fit_transform(train_matrix) @ svd_pred.components_")

# 用 SVD 重建
n_comp_pred = min(50, min(train_matrix.shape) - 1)
svd_pred = TruncatedSVD(n_components=n_comp_pred, random_state=42)
user_f = svd_pred.fit_transform(train_matrix)
item_f = svd_pred.components_
pred_matrix = user_f @ item_f

# 评估
test_ratings = []
pred_ratings = []

train_users_list = list(train_matrix.index)
train_items_list = list(train_matrix.columns)
u_pos = {u: i for i, u in enumerate(train_users_list)}
m_pos = {m: i for i, m in enumerate(train_items_list)}

for row in test_data.itertuples():
    u, m, r = row.userId, row.movieId, row.rating
    if u in u_pos and m in m_pos:
        pred = pred_matrix[u_pos[u], m_pos[m]]
        test_ratings.append(r)
        pred_ratings.append(pred)

rmse = np.sqrt(mean_squared_error(test_ratings, pred_ratings))
mae = mean_absolute_error(test_ratings, pred_ratings)

R.text("**Python 结果：**")
R.output("测试样本数 = %d\nRMSE = %.4f\nMAE = %.4f" % (len(test_ratings), rmse, mae))
R.text("**解释：** RMSE 和 MAE 衡量隐式评分的重建误差。"
       "隐式评分集中在 1-2 分（cap 5），误差绝对值天然小于 5 分制显式评分，"
       "RMSE 主要用于不同模型之间的相对比较，不追求绝对小。")


# ============================================================
# 4. 序列推荐
# ============================================================
R.h1("序列推荐")
R.text("序列推荐（Sequential Recommendation）考虑用户购买行为的时序关系，"
       "预测用户下一个可能购买的商品。")

R.h2("用户行为序列构建")

# 按时间排序（粒度到单次购买事件）
events = interactions[['customer_id', 'product_id', 'created_at']].rename(
    columns={'customer_id': 'userId', 'product_id': 'movieId', 'created_at': 'timestamp'})
events = events[events['movieId'].isin(popular_items)]
events_sorted = events.sort_values(['userId', 'timestamp'])
user_sequences = events_sorted.groupby('userId')['movieId'].apply(list)
seq_lengths = user_sequences.apply(len)

R.text("**SQL 代码（用户购买序列）：**")
R.code("sql",
       "SELECT o.customer_id, GROUP_CONCAT(oi.product_id) AS sequence\n"
       "FROM order_items oi JOIN orders o ON oi.order_id = o.order_id\n"
       "WHERE o.order_status IN ('已完成','已发货')\n"
       "GROUP BY o.customer_id\n"
       "LIMIT 5;")
R.table(sql("""
SELECT o.customer_id, GROUP_CONCAT(oi.product_id) AS sequence
FROM order_items oi JOIN orders o ON oi.order_id = o.order_id
WHERE o.order_status IN ('已完成','已发货')
GROUP BY o.customer_id
LIMIT 5;
"""))

R.text("**Python 代码：**")
R.code("python",
       "user_sequences = events.sort_values(['userId','timestamp']).groupby('userId')['movieId'].apply(list)\n"
       "seq_lengths = user_sequences.apply(len)")
R.text("**Python 结果：**")
R.output("平均序列长度: %.2f\n最长序列长度: %d\n最短序列长度: %d"
         % (seq_lengths.mean(), seq_lengths.max(), seq_lengths.min()))

# 序列长度分布
plt.figure(figsize=(10, 4))
plt.hist(seq_lengths, bins=30, edgecolor='k', alpha=0.7)
plt.xlabel('Sequence Length')
plt.ylabel('Number of Users')
plt.title('User Purchase Sequence Length Distribution')
R.save_plt('4_1_seq_length.png')
R.image('4_1_seq_length.png', 'User Purchase Sequence Length Distribution | 用户购买序列长度分布')
R.text("**中文说明：** 横轴 = 序列长度；纵轴 = 用户数量。")
R.text("**解释：** 序列长度右偏分布，少数高频客户贡献了大量订单明细，"
       "他们是序列推荐的主要受益者；短序列用户更适合用热度或 ItemCF 兜底。")

R.h2("基于物品相似度的序列推荐")
R.text("利用物品相似度，根据用户历史购买序列推荐下一个可能购买的商品。")

# 构建物品ID到索引的映射
movie_ids = list(user_item.columns)
movie_to_idx = {m: i for i, m in enumerate(movie_ids)}

def recommend_next(user_seq, item_sim, movie_to_idx, movie_ids, top_k=10):
    """基于序列中最后一个物品的相似度推荐"""
    if len(user_seq) == 0:
        return []
    last_item = user_seq[-1]
    if last_item not in movie_to_idx:
        return []
    idx = movie_to_idx[last_item]
    sim_scores = item_sim[idx]
    # 排除已买过的
    seen = set(user_seq)
    candidates = [(movie_ids[i], sim_scores[i]) for i in range(len(movie_ids))
                  if movie_ids[i] not in seen]
    candidates.sort(key=lambda x: -x[1])
    return [c[0] for c in candidates[:top_k]]

R.text("**Python 代码：**")
R.code("python",
       "def recommend_next(user_seq, item_sim, movie_to_idx, movie_ids, top_k=10):\n"
       "    last_item = user_seq[-1]\n"
       "    idx = movie_to_idx[last_item]\n"
       "    sim_scores = item_sim[idx]\n"
       "    seen = set(user_seq)\n"
       "    candidates = [(movie_ids[i], sim_scores[i]) for i in range(len(movie_ids))\n"
       "                  if movie_ids[i] not in seen]\n"
       "    candidates.sort(key=lambda x: -x[1])\n"
       "    return [c[0] for c in candidates[:top_k]]")

# 评估
K = 10
recall_scores = []
ndcg_scores = []
hit_scores = []

# 取部分用户评估
eval_users = list(user_sequences.index)[:300]
for uid in eval_users:
    seq = user_sequences[uid]
    if len(seq) < 5:
        continue
    train_seq = seq[:-3]
    test_set = set(seq[-3:])
    recs = recommend_next(train_seq, item_sim, movie_to_idx, movie_ids, top_k=K)
    if recs:
        recall_scores.append(recall_at_k(test_set, recs, K))
        ndcg_scores.append(ndcg_at_k(test_set, recs, K))
        hit_scores.append(hit_rate_at_k(test_set, recs, K))

avg_recall = np.mean(recall_scores) if recall_scores else 0
avg_ndcg = np.mean(ndcg_scores) if ndcg_scores else 0
avg_hit = np.mean(hit_scores) if hit_scores else 0

R.text("**Python 结果：**")
R.output("评估用户数 = %d\nRecall@%d  = %.4f\nNDCG@%d    = %.4f\nHitRate@%d = %.4f"
         % (len(recall_scores), K, avg_recall, K, avg_ndcg, K, avg_hit))
R.text("**解释：** Recall@K 衡量推荐列表中命中用户真实购买的比例；"
       "NDCG@K 考虑推荐位置的重要性（越靠前权重越大）；"
       "HitRate@K 反映至少命中一个的比例。"
       "电商购买序列的重复购买与关联购买并存，ItemCF 序列推荐能捕捉到一部分关联信号。")

# 可视化推荐指标
plt.figure(figsize=(8, 4))
metrics_names = ['Recall@10', 'NDCG@10', 'HitRate@10']
metrics_values = [avg_recall, avg_ndcg, avg_hit]
plt.bar(metrics_names, metrics_values, color=['#4C72B0', '#55A868', '#C44E52'])
plt.ylabel('Score')
plt.title('Sequential Recommendation Metrics')
R.save_plt('4_2_seq_metrics.png')
R.image('4_2_seq_metrics.png', 'Sequential Recommendation Metrics | 序列推荐评估指标')
R.text("**中文说明：** 横轴 = 指标名称；纵轴 = 得分。")
R.text("**解释：** 三个指标从不同角度评估推荐质量。"
       "NDCG 通常低于 Recall，因为它惩罚了正确物品排序靠后的情况。")


# ============================================================
# 5. 强化学习策略优化
# ============================================================
R.h1("强化学习策略优化")
R.text("强化学习（Reinforcement Learning）将推荐视为序贯决策问题："
       "Agent（推荐系统）根据用户状态选择动作（推荐商品），"
       "获得奖励（用户是否购买），目标是最大化长期累积收益。")

R.h2("用户环境建模")
R.text("将电商购买数据构建为 RL 环境：用户状态 = 历史购买商品集合，"
       "动作 = 推荐一个商品，奖励 = 用户是否购买过该商品（买过为 1，否则为 0）。")

# 构建 RL 环境所需的数据结构
user_history = user_sequences.to_dict()
user_bought = events.groupby('userId')['movieId'].apply(set).to_dict()

all_movies = list(ratings['movieId'].unique())
n_movies = len(all_movies)

R.text("**Python 代码：**")
R.code("python",
       "user_history = user_sequences.to_dict()\n"
       "user_bought = events.groupby('userId')['movieId'].apply(set).to_dict()\n"
       "all_movies = list(ratings['movieId'].unique())")
R.text("**Python 结果：**")
R.output("用户数: %d\n商品数: %d" % (len(user_history), n_movies))

R.h2("ε-贪心策略评估")
R.text("ε-贪心策略（ε-Greedy）以概率 ε 随机探索，以概率 1-ε 利用当前最优推荐。"
       "用离线评估方法计算不同 ε 下的平均累积奖励。")

def simulate_episode(user_id, eps, item_sim, movie_to_idx, movie_ids,
                     user_history, user_bought, n_steps=20, rng=None):
    """模拟一个用户的交互过程"""
    rng = rng or np.random
    history = list(user_history.get(user_id, []))
    bought = user_bought.get(user_id, set())

    total_reward = 0
    for step in range(n_steps):
        # ε-贪心选择
        if rng.random() < eps:
            # 随机探索
            action = movie_ids[rng.randint(len(movie_ids))]
        else:
            # 利用：基于历史最后一个物品的相似度
            if len(history) > 0 and history[-1] in movie_to_idx:
                idx = movie_to_idx[history[-1]]
                sim_scores = item_sim[idx]
                seen = set(history)
                candidates = [(movie_ids[i], sim_scores[i])
                              for i in range(len(movie_ids)) if movie_ids[i] not in seen]
                if candidates:
                    candidates.sort(key=lambda x: -x[1])
                    action = candidates[0][0]
                else:
                    action = movie_ids[rng.randint(len(movie_ids))]
            else:
                action = movie_ids[rng.randint(len(movie_ids))]

        # 奖励：用户是否购买过
        reward = 1 if action in bought else 0
        total_reward += reward
        history.append(action)

    return total_reward

R.text("**Python 代码：**")
R.code("python",
       "def simulate_episode(user_id, eps, ...):\n"
       "    for step in range(n_steps):\n"
       "        if rng.random() < eps:\n"
       "            action = random_item()          # 探索\n"
       "        else:\n"
       "            action = most_similar_to_last() # 利用\n"
       "        reward = 1 if action in bought else 0\n"
       "    return total_reward")

# 评估不同 ε
rng = np.random.RandomState(42)
eps_values = [0.0, 0.1, 0.2, 0.3, 0.5]
eps_rewards = []

eval_users = list(user_history.keys())[:50]
for eps in eps_values:
    rewards = []
    for uid in eval_users:
        r = simulate_episode(uid, eps, item_sim, movie_to_idx,
                              movie_ids, user_history, user_bought, n_steps=20, rng=rng)
        rewards.append(r)
    eps_rewards.append(np.mean(rewards))

R.text("**Python 结果：**")
for eps, r in zip(eps_values, eps_rewards):
    R.text("- ε = %.1f, 平均累积奖励 = %.2f" % (eps, r))
R.text("**解释：** ε 控制探索-利用权衡。ε=0 纯利用，推荐结果趋同、无法发现新兴趣；"
       "ε 过大则过度探索，浪费曝光机会。最优 ε 通常在 0.1-0.3 之间。")

# 可视化
plt.figure(figsize=(8, 4))
plt.plot(eps_values, eps_rewards, 'bo-', linewidth=2)
plt.xlabel('ε (Exploration Rate)')
plt.ylabel('Average Cumulative Reward')
plt.title('Exploration-Exploitation Trade-off')
R.save_plt('5_2_eps_tradeoff.png')
R.image('5_2_eps_tradeoff.png', 'Exploration-Exploitation Trade-off | 探索-利用权衡')
R.text("**中文说明：** 横轴 = ε 值；纵轴 = 平均累积奖励。")
R.text("**解释：** 纯利用（ε=0）在离线回放中往往分数不低（历史购买集中在热销品），"
       "但线上会造成越推越窄的马太效应；适度探索以牺牲少量短期收益换取长期发现能力。")

R.h2("Q-Learning 策略")
R.text("Q-Learning 通过学习状态-动作价值函数 Q(s, a) 来优化策略。"
       "这里简化状态为用户最近购买商品的哈希表示。")

class QLearningAgent:
    def __init__(self, n_actions, alpha=0.1, gamma=0.9, epsilon=0.2, seed=42):
        self.n_actions = n_actions
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon
        self.q_table = {}
        self.rng = np.random.RandomState(seed)

    def get_state_key(self, history):
        return tuple(sorted(history[-5:]))

    def choose_action(self, state_key, available_actions):
        if self.rng.random() < self.epsilon:
            return available_actions[self.rng.randint(len(available_actions))]
        q_values = [self.q_table.get((state_key, a), 0.0) for a in available_actions]
        return available_actions[int(np.argmax(q_values))]

    def update(self, state_key, action, reward, next_state_key, next_available):
        old_q = self.q_table.get((state_key, action), 0.0)
        next_max_q = max([self.q_table.get((next_state_key, a), 0.0)
                          for a in next_available]) if next_available else 0.0
        new_q = old_q + self.alpha * (reward + self.gamma * next_max_q - old_q)
        self.q_table[(state_key, action)] = new_q

R.text("**Python 代码：**")
R.code("python",
       "class QLearningAgent:\n"
       "    def __init__(self, n_actions, alpha=0.1, gamma=0.9, epsilon=0.2):\n"
       "        self.q_table = {}\n"
       "    def choose_action(self, state_key, available_actions):\n"
       "        if rng.random() < self.epsilon:\n"
       "            return random.choice(available_actions)\n"
       "        q_values = [self.q_table.get((state_key, a), 0.0) for a in available_actions]\n"
       "        return available_actions[argmax(q_values)]\n"
       "    def update(self, state_key, action, reward, next_state_key, next_available):\n"
       "        old_q = self.q_table.get((state_key, action), 0.0)\n"
       "        next_max_q = max([...]) if next_available else 0.0\n"
       "        new_q = old_q + self.alpha * (reward + self.gamma * next_max_q - old_q)\n"
       "        self.q_table[(state_key, action)] = new_q")

# 简化训练
agent = QLearningAgent(n_actions=len(all_movies), alpha=0.1, gamma=0.9, epsilon=0.2, seed=42)

train_users = list(user_history.keys())[50:100]
episode_rewards = []

for episode in range(30):
    total_reward = 0
    for uid in train_users:
        history = list(user_history.get(uid, []))
        bought = user_bought.get(uid, set())

        for step in range(10):
            state_key = agent.get_state_key(history)
            seen = set(history)
            available = [m for m in all_movies if m not in seen][:100]
            if not available:
                break
            action = agent.choose_action(state_key, available)
            reward = 1 if action in bought else 0
            history.append(action)
            next_state_key = agent.get_state_key(history)
            seen2 = set(history)
            next_available = [m for m in all_movies if m not in seen2][:100]
            agent.update(state_key, action, reward, next_state_key, next_available)
            total_reward += reward
    episode_rewards.append(total_reward)

R.text("**Python 结果：**")
R.output("Q-Table 大小: %d\n平均每轮奖励（最后10轮）: %.2f"
         % (len(agent.q_table), np.mean(episode_rewards[-10:])))
R.text("**解释：** Q-Table 随训练增大，说明 Agent 在不断学习新的状态-动作对。"
       "表格法只作原理演示，状态空间巨大时需用 DQN 等函数逼近方法（见《深度强化学习（DQN）》专题）。")

# 可视化学习曲线
plt.figure(figsize=(10, 4))
plt.plot(episode_rewards, 'b-', alpha=0.7)
plt.xlabel('Episode')
plt.ylabel('Cumulative Reward')
plt.title('Q-Learning Training Curve')
R.save_plt('5_3_qlearning_curve.png')
R.image('5_3_qlearning_curve.png', 'Q-Learning Training Curve | Q-Learning 训练曲线')
R.text("**中文说明：** 横轴 = 训练轮次；纵轴 = 累积奖励。")
R.text("**解释：** 曲线震荡是因为每个回合遍历的用户固定、奖励稀疏；"
       "ε-greedy 的探索也会带来波动，平滑趋势比单点数值更重要。")


# ============================================================
# 6. 策略对比
# ============================================================
R.h1("策略对比")

# 收集各策略指标
R.h2("离线评估汇总表")

strategies = pd.DataFrame([
    ['ItemCF 序列推荐', avg_recall, avg_ndcg, avg_hit, '-'],
    ['SVD (50 factors)', rmse, mae, '-', '-'],
    ['ε-Greedy (ε=0.2)', eps_rewards[2] if len(eps_rewards) > 2 else 0, '-', '-', '-'],
    ['Q-Learning', np.mean(episode_rewards[-10:]), '-', '-', '-'],
], columns=['Strategy', 'Metric1', 'Metric2', 'Metric3', 'Metric4'])

R.text("**Python 代码：**")
R.code("python", "strategies = pd.DataFrame([...])")
R.text("**Python 结果：**")
R.output(strategies.to_string(index=False))
R.text("**解释：** 不同策略适用于不同场景。"
       "协同过滤适合冷启动阶段；矩阵分解适合兴趣预测；"
       "序列推荐适合会话式/复购推荐；RL 适合长期用户价值优化。")


# ============================================================
# 7. 9.4 专题分析索引
# ============================================================
R.h1("9.4 专题分析索引")
R.text("以下专题基于同一电商数据库展开，每个专题有独立脚本与报告：")
R.table(pd.DataFrame([
    ['深度强化学习 DQN', '库存补货 MDP：DQN vs (s,S) 基准策略', 'l4_dqn.py', 'dqn_report.md'],
    ['上下文赌博机', '优惠券发放：LinUCB / Thompson Sampling / ε-greedy', 'l4_bandit.py', 'bandit_report.md'],
    ['多目标优化', '品类折扣决策：GMV × 毛利率 × 优惠成本帕累托前沿', 'l4_multiobjective.py', 'multiobjective_report.md'],
    ['因果推荐去偏', '曝光流行度偏差的 IPS 去偏评估', 'l4_causal_rec.py', 'causal_rec_report.md'],
], columns=['专题', '内容', '脚本', '报告']))

R.h2("离线强化学习（说明性跳过）")
R.text("离线 RL（BCQ / CQL / IQL）本节**有意跳过**，原因如下：")
R.text("1. **技术栈冲突**：d3rlpy、BCQ/CQL 的主流实现均基于 PyTorch，"
       "本项目深度学习统一使用 TensorFlow（CPU 版），引入 torch 会造成双框架并存；")
R.text("2. **安装体积大**：torch 及其 CUDA 依赖体积在数 GB 量级，与教学型示例环境不匹配；")
R.text("3. **概念已覆盖**：离线 RL 的核心思想（从历史日志学习、避免分布外动作）"
       "已由 DQN（经验回放 + 目标网络）和上下文赌博机（离线日志评估）覆盖，"
       "读者可在此基础上自行延伸。")


# ============================================================
# 输出
# ============================================================
conn.close()
R.write()
