#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L1 主题示例：文本数据描述
- 数据源: ../ecommerce/ecommerce.db 的 reviews.review_content（只读）
- 内容: jieba 分词；总词频 Top50；bigram Top20；5星 vs 1-2星分组词频对比；词云（可选）
- 输出: text_report.md + images/text_*.png
"""

import os
import re
import sqlite3
import warnings
from collections import Counter

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns
import jieba

try:
    from wordcloud import WordCloud
    HAS_WORDCLOUD = True
except ImportError:
    HAS_WORDCLOUD = False

warnings.filterwarnings('ignore')
jieba.setLogLevel(20)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'ecommerce', 'ecommerce.db'))
OUTPUT_MD = os.path.join(SCRIPT_DIR, 'text_report.md')
IMAGE_DIR = os.path.join(SCRIPT_DIR, 'images')
os.makedirs(IMAGE_DIR, exist_ok=True)

# ================== 中文字体（与 generate_report.py 相同） ==================
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
    fm.fontManager.addfont(CJK_FONT_FILE)
    _name = fm.FontProperties(fname=CJK_FONT_FILE).get_name()
    plt.rcParams['font.sans-serif'] = [_name, 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
sns.set_style("whitegrid")

conn = sqlite3.connect('file:%s?mode=ro' % DB_PATH.replace('\\', '/'), uri=True)

def sql(q):
    return pd.read_sql_query(q, conn)

class Report:
    def __init__(self):
        self.parts = []
        self.toc = []
        self.n = 0

    def h1(self, t):
        self.n += 1
        self.parts.append('<a id="sec-%d"></a>\n' % self.n)
        self.parts.append("# %d. %s\n" % (self.n, t))
        self.toc.append("- [%d %s](#sec-%d)" % (self.n, t, self.n))

    def text(self, s):
        self.parts.append(s.rstrip() + "\n")

    def code(self, lang, s):
        self.parts.append("```%s\n%s\n```\n" % (lang, s.rstrip()))

    def table(self, df_):
        try:
            self.parts.append(df_.to_markdown(index=False, floatfmt='.2f') + "\n")
        except Exception:
            self.parts.append("```\n" + df_.to_string(index=False) + "\n```\n")

    def image(self, name, caption=""):
        self.parts.append("![%s](%s/%s)\n" % (caption, os.path.basename(IMAGE_DIR), name))

    def save_plt(self, name):
        plt.savefig(os.path.join(IMAGE_DIR, name), bbox_inches='tight', dpi=100)
        plt.close()

    def write(self, title, intro_lines):
        header = ["# %s\n" % title] + intro_lines + ['<a id="toc"></a>\n## 目录\n']
        header.append("\n".join(self.toc) + "\n\n---\n")
        with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
            f.write("\n".join(header) + "\n".join(self.parts))
        print("[OK] 报告：%s" % OUTPUT_MD)

R = Report()

# ================== 停用词 ==================
STOPWORDS = set("""
的 了 和 是 在 我 也 就 都 很 还 有 没 不 这 那 你 他 她 它 们 个 之 与 及 等 把 被 让 给
但 而 或 且 因为 所以 如果 虽然 一个 一些 什么 怎么 这个 那个 可以 就是 还是 不是 没有
真的 感觉 非常 比较 有点 实在 太 更 最 再 又 也 已 已经 正在 将 会 能 要 想 得 着 过
件 这款 这件 这件商品 商品 东西 产品 卖家 店家 客服 本次 这次 一次
""".split())

CJK_RE = re.compile(r'[一-鿿]')

def tokenize(text):
    """jieba 分词 + 过滤：去停用词、单字、非中文词"""
    words = jieba.lcut(str(text))
    return [w.strip() for w in words
            if len(w.strip()) >= 2 and CJK_RE.search(w) and w.strip() not in STOPWORDS]

def bigrams(tokens):
    return list(zip(tokens[:-1], tokens[1:]))

# ================== 加载语料 ==================
reviews = sql("SELECT review_id, rating, review_content FROM reviews")
reviews['tokens'] = reviews['review_content'].map(tokenize)
reviews['text_len'] = reviews['review_content'].str.len()

all_tokens = [t for toks in reviews['tokens'] for t in toks]
freq_all = Counter(all_tokens)

# ============================================================
# 1. 语料概况
# ============================================================
R.h1("语料概况")
R.text("文本是描述性分析里最容易被跳过的一类数据——它不能求均值，"
       "但分词后的**词频**就是文本世界的“频率分布”，分析套路与分类变量完全一致。"
       "本报告语料为 `reviews.review_content`（%d 条已签收订单评价），"
       "星级 `rating` 是天然的情绪标签。" % len(reviews))

rating_dist = reviews['rating'].value_counts().sort_index()
R.text("**星级分布：**")
R.table(pd.DataFrame({'星级': rating_dist.index, '评价数': rating_dist.values,
                      '占比%': (rating_dist.values / len(reviews) * 100).round(1)}))
R.text("**文本长度（字符数）：** 均值 %.1f，中位数 %d，最短 %d，最长 %d。"
       % (reviews['text_len'].mean(), reviews['text_len'].median(),
          reviews['text_len'].min(), reviews['text_len'].max()))
R.text("星级分布明显左偏（好评多）：5 星 + 4 星占绝大多数，1-2 星合计仅 %d 条。"
       "差评样本少是电商文本的常态，后文分组对比会专门说明其对词频稳定性的影响。"
       % int((reviews['rating'] <= 2).sum()))

# ============================================================
# 2. 分词方法
# ============================================================
R.h1("分词与停用词")
R.text("**Python 代码：**")
R.code("python", """import jieba
def tokenize(text):
    words = jieba.lcut(str(text))
    return [w.strip() for w in words
            if len(w.strip()) >= 2           # 去单字（“很/不/了”噪声大）
            and CJK_RE.search(w)             # 去标点与纯数字
            and w.strip() not in STOPWORDS]  # 去停用词""")
R.text("三条过滤规则的理由：\n"
       "1. **去单字**：中文单字大多无语义信息量（的/了/很），留着会淹没词频榜；\n"
       "2. **只留含中文的词**：标点、数字、型号串不进入词频统计；\n"
       "3. **停用词**：虚词 + 语料特有无信息词（“这件商品”“卖家”在每条评价中都出现，"
       "留着会让 Top 榜失去区分度）。停用词表应根据语料迭代，这里是小型内置表。\n\n"
       "分词后共得到 %d 个有效词，去重后 %d 个。" % (len(all_tokens), len(freq_all)))

# ============================================================
# 3. 总词频 Top50
# ============================================================
R.h1("总词频 Top 50")
top50 = freq_all.most_common(50)
top_df = pd.DataFrame(top50, columns=['词', '频次'])
R.table(top_df)

words, counts = zip(*top50)
plt.figure(figsize=(9, 12))
plt.barh(range(len(words)), counts, color='steelblue', alpha=0.85)
plt.yticks(range(len(words)), words, fontsize=8)
plt.gca().invert_yaxis()
plt.xlabel('frequency')
plt.title('Top 50 Word Frequency (all reviews)')
plt.tight_layout()
R.save_plt('text_top50_freq.png')
R.image('text_top50_freq.png', 'Top50 Word Frequency | 全部评价词频 Top 50')
R.text("**解释：** 词频榜就是文本的“一维频率分布”，读法与分类变量频率表相同。"
       "头部词（质量/物流/性价比/满意一类）刻画了评价语料的整体基调——以满意向词汇为主，"
       "与星级左偏相互印证。词频呈长尾分布：Top 10 之后的词衰减很快，"
       "符合齐夫定律（Zipf's law）的典型形态。")

# ============================================================
# 4. Bigram Top 20
# ============================================================
R.h1("Bigram Top 20")
R.text("单个词会丢失搭配信息（“物流”+“快”和“物流”+“慢”是两种评价）。"
       "bigram（相邻二元词组）保留局部语序，是关键词向短语迈出的最小一步。")
bi_all = Counter(b for toks in reviews['tokens'] for b in bigrams(toks))
top_bi = bi_all.most_common(20)
bi_df = pd.DataFrame([(' '.join(b), c) for b, c in top_bi], columns=['bigram', '频次'])
R.text("**Python 代码：**")
R.code("python", "bigrams = list(zip(tokens[:-1], tokens[1:]))\nCounter(bigrams).most_common(20)")
R.table(bi_df)

bi_labels = ['/'.join(b) for b, c in top_bi]
bi_counts = [c for b, c in top_bi]
plt.figure(figsize=(9, 7))
plt.barh(range(len(bi_labels)), bi_counts, color='seagreen', alpha=0.85)
plt.yticks(range(len(bi_labels)), bi_labels, fontsize=9)
plt.gca().invert_yaxis()
plt.xlabel('frequency')
plt.title('Top 20 Bigrams (all reviews)')
plt.tight_layout()
R.save_plt('text_top20_bigram.png')
R.image('text_top20_bigram.png', 'Top20 Bigrams | 全部评价 bigram Top 20')
R.text("**解释：** bigram 榜比单词榜更接近“观点”：能看到「质量 + 不错」这类属性-评价搭配。"
       "频次天然低于单词榜（搭配更稀疏），所以只看 Top 20。"
       "再往上是 trigram / 依存分析，收益递减，L1 层到 bigram 为止。")

# ============================================================
# 5. 分组词频对比：5星 vs 1-2星
# ============================================================
R.h1("分组词频对比：5 星 vs 1-2 星")
R.text("词频按星级分组后才能回答“好评在夸什么、差评在骂什么”。"
       "两组样本量悬殊（5 星 %d 条 vs 1-2 星 %d 条），直接比原始频次不公平，"
       "统一换算为**每千条评价的归一化频次**再对比。"
       % (int((reviews['rating'] == 5).sum()), int((reviews['rating'] <= 2).sum())))

tok_5 = [t for toks in reviews.loc[reviews['rating'] == 5, 'tokens'] for t in toks]
tok_12 = [t for toks in reviews.loc[reviews['rating'] <= 2, 'tokens'] for t in toks]
freq_5 = Counter(tok_5)
freq_12 = Counter(tok_12)
n5 = max(1, (reviews['rating'] == 5).sum())
n12 = max(1, (reviews['rating'] <= 2).sum())

top15_5 = [(w, c / n5 * 1000) for w, c in freq_5.most_common(15)]
top15_12 = [(w, c / n12 * 1000) for w, c in freq_12.most_common(15)]

fig, axes = plt.subplots(1, 2, figsize=(14, 7))
for ax, data, title, color in [
        (axes[0], top15_5, '5-star reviews', 'steelblue'),
        (axes[1], top15_12, '1-2 star reviews', 'indianred')]:
    ws = [w for w, _ in data]
    cs = [c for _, c in data]
    ax.barh(range(len(ws)), cs, color=color, alpha=0.85)
    ax.set_yticks(range(len(ws)))
    ax.set_yticklabels(ws, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel('frequency per 1000 reviews')
    ax.set_title(title)
plt.suptitle('Word Frequency by Rating Group (normalized)')
plt.tight_layout()
R.save_plt('text_group_compare.png')
R.image('text_group_compare.png', 'Rating Group Compare | 5星 vs 1-2星分组词频（每千条归一化）')

R.text("**5 星 Top 15：** " + "、".join("%s(%.0f)" % (w, c) for w, c in top15_5))
R.text("**1-2 星 Top 15：** " + "、".join("%s(%.0f)" % (w, c) for w, c in top15_12))
R.text("**解释：** 好评高频词围绕“质量/性价比/物流/满意”，差评高频词围绕“失望/色差/尺码/退货”一类。"
       "方法要点有二：\n"
       "1. **归一化**：样本量差一个数量级时，原始频次的对比毫无意义，按每千条折算后量级才可比；\n"
       "2. **小样本抖动**：1-2 星只有 %d 条，Top 榜尾部几个词的排名对随机波动敏感，"
       "解读时关注头部稳定词，不要过度解读 10 名之后的差异。\n"
       "这种做法就是最简单的“文本分组画像”，再进一步就是 TF-IDF 加权与情感模型（L2/L5 内容）。"
       % int(n12))

# ============================================================
# 6. 词云
# ============================================================
R.h1("词云（可选增强）")
if HAS_WORDCLOUD and CJK_FONT_FILE:
    def make_cloud(freq, path, colormap):
        wc = WordCloud(font_path=CJK_FONT_FILE, width=900, height=450,
                       background_color='white', colormap=colormap,
                       max_words=120, prefer_horizontal=0.95)
        wc.generate_from_frequencies(freq)
        wc.to_file(path)

    make_cloud(dict(freq_5), os.path.join(IMAGE_DIR, 'text_wc_5star.png'), 'Greens')
    make_cloud(dict(freq_12), os.path.join(IMAGE_DIR, 'text_wc_12star.png'), 'Reds')
    plt.close('all')
    R.text("**5 星评价词云：**")
    R.image('text_wc_5star.png', 'WordCloud 5-star | 5星评价词云')
    R.text("**1-2 星评价词云：**")
    R.image('text_wc_12star.png', 'WordCloud 1-2 star | 1-2星评价词云')
    R.text("**解释：** 词云与词频条形图承载完全相同的信息（词 → 频次），"
           "只是用字号换通道、牺牲精确性换取一眼可见的“氛围感”，适合放在汇报首页。"
           "注意词云必须用中文字体文件渲染（本报告复用脚本检测到的 `%s`），"
           "否则中文全部变成方框。" % os.path.basename(CJK_FONT_FILE))
else:
    R.text("*当前环境未安装 wordcloud（`pip install wordcloud` 失败或未执行），本节跳过。*\n"
           "词云与第 3 节词频条形图信息等价，不影响结论；安装后重跑本脚本即可自动补出"
           " 5 星与 1-2 星两张词云。")

# ============================================================
# 7. 小结
# ============================================================
R.h1("小结")
R.text("- 文本描述的主线是「分词 → 词频 → 分组对比」，与分类变量频率分析同构；\n"
       "- 过滤规则（去单字/停用词/非中文）决定词频榜质量，应按语料迭代；\n"
       "- bigram 用最小成本补上搭配信息；\n"
       "- 分组对比务必归一化，并警惕小样本组（差评）的排名抖动；\n"
       "- 词云是呈现层增强，信息量不超词频表。")

R.write("L1 文本数据描述报告", [
    "- **数据来源**：`data/ecommerce/ecommerce.db` 的 `reviews` 表（SQLite，只读连接）",
    "- **对应主题**：文本数据描述",
    "- **分词**：jieba %s；**词云**：%s\n" % (
        jieba.__version__, '已生成（wordcloud）' if HAS_WORDCLOUD and CJK_FONT_FILE else '跳过（依赖缺失）'),
])
conn.close()
