#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L3 预测性分析报告生成器
- 数据源: data/ecommerce/ecommerce.db（统一电商数据库）
- 目标序列: 日 GMV（orders.created_at 按日聚合 total_amount，状态限 已完成/已发货）
- 分析: 时序分解 / ARIMA / SARIMA / LSTM / GRU / 大促峰值影响讨论 / 峰值日分类
- 输出: Markdown 报告 + images_predictive/ 图片目录
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

from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.seasonal import STL
from statsmodels.tsa.stattools import adfuller
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf

import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, GRU, Dense, Dropout

from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.preprocessing import MinMaxScaler
from sklearn.linear_model import LogisticRegression

warnings.filterwarnings('ignore')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
tf.get_logger().setLevel('ERROR')

SEED = 42
np.random.seed(SEED)
tf.random.set_seed(SEED)

# ================== 配置区 ==================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'ecommerce', 'ecommerce.db'))
OUTPUT_MD = os.path.join(SCRIPT_DIR, 'predictive_report.md')
IMAGE_DIR = os.path.join(SCRIPT_DIR, 'images_predictive')

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
    print("[字体] 警告：未找到中文字体")
plt.rcParams['axes.unicode_minus'] = False
sns.set_style("whitegrid")
if CJK_FONT_FILE:
    plt.rcParams['font.sans-serif'] = [_name, 'DejaVu Sans']

# ================== 加载数据（电商日 GMV） ==================
print("[数据] 加载中: %s" % DB_PATH)
conn = sqlite3.connect(DB_PATH)

GMV_SQL = """
SELECT substr(created_at, 1, 10) AS day,
       SUM(total_amount)         AS gmv,
       COUNT(*)                  AS order_cnt
FROM orders
WHERE order_status IN ('已完成', '已发货')
GROUP BY day
ORDER BY day;
"""
df_gmv = pd.read_sql_query(GMV_SQL, conn)
df_gmv['day'] = pd.to_datetime(df_gmv['day'])

# 补齐缺失日期（GMV=0 的日期也保留，保证时序连续）
full_idx = pd.date_range(df_gmv['day'].min(), df_gmv['day'].max(), freq='D')
df_gmv = df_gmv.set_index('day').reindex(full_idx).fillna(0.0)
df_gmv.index.name = 'day'
ts_daily = df_gmv['gmv'].astype(float)
print("[数据] 日 GMV 序列: %d 天, %s ~ %s" % (len(ts_daily), ts_daily.index.min().date(), ts_daily.index.max().date()))
print("[数据] GMV 均值 %.2f, 最大 %.2f, 最小 %.2f" % (ts_daily.mean(), ts_daily.max(), ts_daily.min()))

def sql(q):
    return pd.read_sql_query(q, conn)

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

    def write(self):
        header = []
        header.append("# 预测性分析报告 - 电商日 GMV\n")
        header.append("- **数据来源**：`data/ecommerce/ecommerce.db`（orders 表）")
        header.append("- **GMV 口径**：`SUM(total_amount) WHERE order_status IN ('已完成','已发货')`，按日聚合")
        header.append("- **样本量**：%d 天" % len(ts_daily))
        header.append("- **时间范围**：%s ~ %s" % (ts_daily.index.min().date(), ts_daily.index.max().date()))
        header.append("- **目标序列**：日 GMV（元）\n")
        header.append('## 目录\n')
        header.append("\n".join(self.toc) + "\n\n---\n")
        with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
            f.write("\n".join(header) + "\n".join(self.parts))
        print("[OK] 报告：%s" % OUTPUT_MD)
        print("[OK] 图片：%s/ 共 %d 张" % (IMAGE_DIR, len(os.listdir(IMAGE_DIR))))

R = Report()

# ================== 工具函数 ==================
def mape(y_true, y_pred):
    y_true, y_pred = np.array(y_true), np.array(y_pred)
    mask = y_true != 0
    return np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100

def evaluate_forecast(name, y_true, y_pred):
    return {
        'Model': name,
        'RMSE': np.sqrt(mean_squared_error(y_true, y_pred)),
        'MAE':  mean_absolute_error(y_true, y_pred),
        'MAPE(%)': mape(y_true, y_pred),
        'R2':   r2_score(y_true, y_pred),
    }


# ============================================================
# 1. 数据概览
# ============================================================
R.h1("数据概览")
R.text("本报告基于统一电商数据库 `ecommerce.db`，以**日 GMV** 为预测目标。"
       "GMV 口径为订单状态属于「已完成 / 已发货」的 `total_amount` 按下单日求和。"
       "序列覆盖 2024-01-01 ~ 2025-06-15，数据中刻意埋入了**双 11、618 大促峰值**、"
       "**春节低谷**、**周末效应**与**缓慢增长趋势**，是典型的电商经营时序。"
       "预测性分析从**时序分解**、**统计模型（ARIMA/SARIMA）**、"
       "**深度学习模型（LSTM/GRU）** 三个维度展开，并专门讨论异常峰值对预测的影响。")

R.h2("序列构建 SQL")
R.code("sql", GMV_SQL)
R.text("**SQL 结果（前 5 行）：**")
R.table(sql(GMV_SQL).head())

R.h2("描述性统计")
R.table(ts_daily.describe().to_frame('gmv').reset_index().rename(columns={'index': '统计量'}))

# 关键日期定位
top10 = ts_daily.sort_values(ascending=False).head(10)
R.h2("GMV Top 10 峰值日")
R.table(top10.reset_index().rename(columns={'day': '日期', 'gmv': 'GMV（元）'}))
R.text("**解释：** Top 峰值日集中在 11 月上旬（双 11）与 6 月中旬（618）附近，"
       "属于可预期的营销脉冲；这类样本对以 MSE 为损失的模型影响极大，"
       "是后文预测误差的主要来源。")

# 春节低谷
spring = pd.concat([ts_daily['2024-02-05':'2024-02-20'], ts_daily['2025-01-24':'2025-02-08']])
R.h2("春节窗口 GMV（低谷验证）")
R.table(spring.describe().to_frame('gmv').reset_index().rename(columns={'index': '统计量'}))
R.text("**解释：** 春节窗口（2024-02 与 2025-01 末至 02 月初）GMV 显著低于全年均值 %.0f 元，"
       "反映快递停运与消费节奏放缓，构成与峰值相反方向的结构性异常。" % ts_daily.mean())


# ============================================================
# 2. 时序分解
# ============================================================
R.h1("时序分解")
R.text("时序分解把序列拆解为趋势项、季节项、残差项，用于理解数据结构，为建模提供依据。"
       "日度数据样本量 %d 天，不足两个完整年度周期，STL 季节周期取 **7（周周期）**。" % len(ts_daily))

R.h2("趋势与异常峰可视化")
R.text("**Python 代码：**")
R.code("python",
       "ts_daily.plot()\n"
       "plt.axvspan('2024-11-01', '2024-11-15', alpha=0.2, color='red')    # 双11\n"
       "plt.axvspan('2025-06-01', '2025-06-15', alpha=0.2, color='orange') # 618\n"
       "plt.axvspan('2025-01-24', '2025-02-08', alpha=0.2, color='blue')   # 春节")
plt.figure(figsize=(14, 4))
ts_daily.plot()
plt.axvspan(pd.Timestamp('2024-11-01'), pd.Timestamp('2024-11-15'), alpha=0.2, color='red', label='Double 11')
plt.axvspan(pd.Timestamp('2024-06-01'), pd.Timestamp('2024-06-20'), alpha=0.2, color='orange', label='618 (2024)')
plt.axvspan(pd.Timestamp('2025-06-01'), pd.Timestamp('2025-06-15'), alpha=0.2, color='orange')
plt.axvspan(pd.Timestamp('2024-02-05'), pd.Timestamp('2024-02-20'), alpha=0.2, color='blue', label='Spring Festival')
plt.axvspan(pd.Timestamp('2025-01-24'), pd.Timestamp('2025-02-08'), alpha=0.2, color='blue')
plt.legend()
plt.title('Daily GMV with Promotion Peaks and Spring Festival Trough')
plt.ylabel('GMV (CNY)')
R.save_plt('2_1_trend.png')
R.image('2_1_trend.png', 'Daily GMV | 日 GMV 趋势（红=双11，橙=618，蓝=春节）')
R.text("**中文说明：** 横轴 = 日期；纵轴 = 日 GMV（元）。红色阴影 = 双 11 窗口，"
       "橙色 = 618 窗口，蓝色 = 春节窗口。")
R.text("**解释：** 可见（1）整体缓慢上升的长期趋势；（2）双 11、618 两处向上的尖峰；"
       "（3）春节期间向下的深谷；（4）叠加其上的周周期波动。"
       "尖峰与低谷都不属于平稳随机噪声，而是**已知日历事件驱动的结构性偏移**，"
       "纯单变量模型无法预知其发生时点，会在这些位置产生系统性大误差。")

R.h2("STL 分解（周期 = 7）")
R.text("STL（Seasonal-Trend decomposition using Loess）把序列拆为趋势、季节、残差三部分。")
R.text("**Python 代码：**")
R.code("python",
       "stl = STL(ts_daily, period=7).fit()\n"
       "stl.plot()")
stl = STL(ts_daily, period=7).fit()
stl.plot()
plt.suptitle('STL Decomposition of Daily GMV (period=7)', y=1.02)
R.save_plt('2_2_stl.png')
R.image('2_2_stl.png', 'STL Decomposition of Daily GMV | 日 GMV 的 STL 分解（周周期）')
R.text("**中文说明：** 自上而下依次为 Observed（观测序列）、Trend（趋势）、"
       "Seasonal（周季节项）、Resid（残差）。")
R.text("**解释：** 趋势项单调缓慢爬升；周季节项振幅稳定，体现周末效应；"
       "残差项在双 11、618 与春节位置出现明显的大幅脉冲——"
       "这说明**周周期+趋势不足以解释大促与春节**，这些事件需要外生日历变量或事件建模才能吸收。")

R.h2("平稳性检验（ADF）")
R.text("ADF 检验判断序列是否平稳，是 ARIMA 建模的前提。")
R.text("**Python 代码：**")
R.code("python",
       "result = adfuller(ts_daily.dropna())\n"
       "print('ADF Statistic: %.4f' % result[0])\n"
       "print('p-value: %.4f' % result[1])")
adf_result = adfuller(ts_daily.dropna())
R.text("**Python 结果：**")
R.output("ADF Statistic: %.4f\np-value: %.4f\nCritical Values: %s"
         % (adf_result[0], adf_result[1], str(adf_result[4])))
R.text("**解释：** 原假设 H0 为「序列存在单位根（非平稳）」。"
       "GMV 序列含上升趋势与大促脉冲，通常需要一阶差分后再建模（ARIMA 的 d=1 即为此）。")


# ============================================================
# 3. 统计模型：ARIMA / SARIMA
# ============================================================
R.h1("统计模型：ARIMA / SARIMA")
R.text("ARIMA 是经典时序预测模型，SARIMA 在其基础上增加季节性成分（s=7 捕捉周周期）。"
       "日 GMV 日间波动极大（见 5.1 的持续法基线），多步一次性外推意义有限，"
       "因此本节采用**滚动一步预测**：每预测一天后把真实值并入样本再预测下一天，"
       "与后文 LSTM/GRU 的滑窗一步预测口径一致。"
       "注意：测试集落在序列末尾 20%（约 2025-03 ~ 2025-06-15），"
       "**恰好覆盖 618 大促段**，可直接观察统计模型在大促峰值上的表现。")

R.h2("ACF / PACF 定阶")
R.text("ACF 和 PACF 用于识别 ARIMA 的 p（自回归阶数）和 q（移动平均阶数）。")
R.text("**Python 代码：**")
R.code("python",
       "plot_acf(ts_daily.dropna(), lags=40)\n"
       "plot_pacf(ts_daily.dropna(), lags=40)")
fig, ax = plt.subplots(2, 1, figsize=(10, 6))
plot_acf(ts_daily.dropna(), lags=min(40, len(ts_daily) // 2 - 1), ax=ax[0])
plot_pacf(ts_daily.dropna(), lags=min(40, len(ts_daily) // 2 - 1), ax=ax[1])
plt.tight_layout()
R.save_plt('3_1_acf_pacf.png')
R.image('3_1_acf_pacf.png', 'ACF and PACF of Daily GMV | 日 GMV 的 ACF 与 PACF')
R.text("**中文说明：** 上图 = ACF；下图 = PACF。蓝色区域为 95% 置信带。")
R.text("**解释：** 若 ACF 截尾、PACF 拖尾 → AR 过程；"
       "若 PACF 截尾、ACF 拖尾 → MA 过程；两者均拖尾 → ARMA。"
       "lag 7 附近的显著凸起对应周周期。")

R.h2("ARIMA 模型")

train_size = int(len(ts_daily) * 0.8)
train, test = ts_daily[:train_size], ts_daily[train_size:]
print("[ARIMA] 训练集: %d, 测试集: %d (%s ~ %s)" % (len(train), len(test), test.index.min().date(), test.index.max().date()))

R.text("**Python 代码：**")
R.code("python",
       "train_size = int(len(ts_daily) * 0.8)\n"
       "train, test = ts_daily[:train_size], ts_daily[train_size:]\n"
       "\n"
       "# log1p 变换压缩大促尖峰、稳定方差，预测后再 expm1 还原\n"
       "# 滚动一步预测：每步把真实值 append 进样本（不重新估计参数）\n"
       "fit_arima = ARIMA(np.log1p(train), order=(2, 1, 2)).fit()\n"
       "res = fit_arima\n"
       "fc = []\n"
       "for obs in np.log1p(test):\n"
       "    fc.append(res.forecast(1).iloc[0])\n"
       "    res = res.append([obs], refit=False)\n"
       "forecast_arima = np.expm1(pd.Series(fc, index=test.index))")
arima_metrics = None
forecast_arima = None
try:
    fit_arima = ARIMA(np.log1p(train), order=(2, 1, 2)).fit()
    res = fit_arima
    fc = []
    for obs in np.log1p(test):
        fc.append(res.forecast(1).iloc[0])
        res = res.append([obs], refit=False)
    forecast_arima = pd.Series(np.expm1(np.array(fc)), index=test.index)
    arima_metrics = evaluate_forecast('ARIMA(2,1,2)', test.values, forecast_arima.values)
    R.text("**Python 结果：**")
    R.output(str(arima_metrics))
    R.text("**解释：** ARIMA(2,1,2) 含 2 阶自回归、1 阶差分、2 阶移动平均。"
           "对 GMV 先做 log1p 变换再建模，可压缩双 11 尖峰对参数估计的拉扯、稳定方差，"
           "预测结果用 expm1 还原到原始金额口径后再计算误差指标。"
           "`append(refit=False)` 只更新状态、不重新估计参数，滚动成本可控。")
except Exception as e:
    R.text("*ARIMA 拟合失败：%s*" % e)

R.h2("SARIMA 模型")
R.text("SARIMA 在 ARIMA 基础上增加季节性参数 (P, D, Q, s)，日度数据取 s=7（周周期）。")
R.text("**Python 代码：**")
R.code("python",
       "fit_sarima = SARIMAX(np.log1p(train), order=(1,1,1),\n"
       "                     seasonal_order=(1,1,1,7)).fit(disp=False)\n"
       "res = fit_sarima\n"
       "fc = []\n"
       "for obs in np.log1p(test):\n"
       "    fc.append(res.forecast(1).iloc[0])\n"
       "    res = res.append([obs], refit=False)\n"
       "forecast_sarima = np.expm1(pd.Series(fc, index=test.index))")
sarima_metrics = None
forecast_sarima = None
try:
    fit_sarima = SARIMAX(np.log1p(train), order=(1, 1, 1), seasonal_order=(1, 1, 1, 7)).fit(disp=False)
    res = fit_sarima
    fc = []
    for obs in np.log1p(test):
        fc.append(res.forecast(1).iloc[0])
        res = res.append([obs], refit=False)
    forecast_sarima = pd.Series(np.expm1(np.array(fc)), index=test.index)
    sarima_metrics = evaluate_forecast('SARIMA(1,1,1)(1,1,1,7)', test.values, forecast_sarima.values)
    R.text("**Python 结果：**")
    R.output(str(sarima_metrics))
    R.text("**解释：** 季节项捕捉周内周期，滚动一步预测能利用最近 7 天的周相位信息。"
           "与 ARIMA 对比，若 SARIMA 的 RMSE 更低，说明周周期建模有效。")
except Exception as e:
    R.text("*SARIMA 拟合失败：%s*" % e)

R.h2("统计模型对比可视化")
R.text("**Python 代码：**")
R.code("python",
       "plt.plot(test.index, test.values, label='Actual')\n"
       "plt.plot(test.index, forecast_arima, label='ARIMA')\n"
       "plt.plot(test.index, forecast_sarima, label='SARIMA')\n"
       "plt.legend()")
plt.figure(figsize=(14, 4))
plt.plot(test.index, test.values, label='Actual', alpha=0.7)
if forecast_arima is not None:
    plt.plot(test.index, forecast_arima.values, label='ARIMA', alpha=0.8)
if forecast_sarima is not None:
    plt.plot(test.index, forecast_sarima.values, label='SARIMA', alpha=0.8)
plt.axvspan(pd.Timestamp('2025-06-01'), pd.Timestamp('2025-06-15'), alpha=0.15, color='orange', label='618 window')
plt.legend()
plt.title('Statistical Model Forecast Comparison (test period covers 618)')
R.save_plt('3_2_stat_models.png')
R.image('3_2_stat_models.png', 'Statistical Model Forecast Comparison | 统计模型预测对比（测试期含 618）')
R.text("**中文说明：** 黑色 = 真实值（Actual）；蓝色 = ARIMA；橙色 = SARIMA；橙色阴影 = 618 窗口。")
R.text("**解释：** 统计模型对日常波动与周周期拟合尚可，但在 618 窗口明显跟不上真实尖峰——"
       "单变量 ARIMA/SARIMA 不知道「今天是 618」，其预测只能从历史惯性外推，"
       "这是 RMSE 被显著拉高的直接原因。")


# ============================================================
# 4. 深度学习：LSTM / GRU
# ============================================================
R.h1("深度学习：LSTM / GRU")
R.text("LSTM 和 GRU 是处理时序数据的经典循环神经网络，能捕捉长期依赖。"
       "本节沿用滑动窗口单变量设定（过去 30 天预测下一天），"
       "以便与统计模型公平对比； epochs ≤ 30，CPU 训练。")

R.h2("数据准备：滑动窗口 + 3D 张量")
R.text("LSTM/GRU 要求输入是 3D 张量 `(样本数, 时间步, 特征数)`。"
       "这里用过去 30 天预测下一天，因此特征数为 1。")

LOOKBACK = 30

R.text("**Python 代码：**")
R.code("python",
       "# 对 GMV 做 log1p 压缩量级，降低尖峰对归一化与梯度的干扰\n"
       "ts_log = np.log1p(ts_daily.values)\n"
       "\n"
       "def create_sequences(data, lookback=30):\n"
       "    X, y = [], []\n"
       "    for i in range(len(data) - lookback):\n"
       "        X.append(data[i:i+lookback])\n"
       "        y.append(data[i+lookback])\n"
       "    return np.array(X), np.array(y)\n"
       "\n"
       "X, y = create_sequences(ts_log, LOOKBACK)\n"
       "X = X.reshape(X.shape[0], LOOKBACK, 1)   # 关键：加 features 维\n"
       "print('X shape:', X.shape, 'y shape:', y.shape)")
ts_log = np.log1p(ts_daily.values)
X_list, y_list = [], []
for i in range(len(ts_log) - LOOKBACK):
    X_list.append(ts_log[i:i + LOOKBACK])
    y_list.append(ts_log[i + LOOKBACK])
X = np.array(X_list).reshape(-1, LOOKBACK, 1)  # 3D
y_log = np.array(y_list)
R.text("**Python 结果：**")
R.output("X shape: %s, y shape: %s" % (X.shape, y_log.shape))

split = int(len(X) * 0.8)
X_train, X_test = X[:split], X[split:]
y_train_log, y_test_log = y_log[:split], y_log[split:]
y_train = np.expm1(y_train_log)   # 原始金额口径，用于最终评估
y_test = np.expm1(y_test_log)

# 输入与目标均在 log 空间归一化，预测后 expm1 还原到原始金额口径
scaler_dl = MinMaxScaler()
scaler_dl.fit(X_train.reshape(-1, 1))
X_train_scaled = scaler_dl.transform(X_train.reshape(-1, 1)).reshape(X_train.shape)
X_test_scaled  = scaler_dl.transform(X_test.reshape(-1, 1)).reshape(X_test.shape)
scaler_y = MinMaxScaler()
y_train_scaled = scaler_y.fit_transform(y_train_log.reshape(-1, 1)).flatten()

R.text("**Python 代码（标准化）：**")
R.code("python",
       "scaler_dl = MinMaxScaler()\n"
       "scaler_dl.fit(X_train.reshape(-1, 1))\n"
       "X_train_scaled = scaler_dl.transform(X_train.reshape(-1, 1)).reshape(X_train.shape)\n"
       "X_test_scaled  = scaler_dl.transform(X_test.reshape(-1, 1)).reshape(X_test.shape)\n"
       "scaler_y = MinMaxScaler()\n"
       "y_train_scaled = scaler_y.fit_transform(y_train_log.reshape(-1, 1)).flatten()\n"
       "# 预测链路: predict -> scaler_y.inverse_transform -> expm1 -> 原始 GMV")

EPOCHS = 30

R.h2("LSTM 模型")

R.text("**Python 代码：**")
R.code("python",
       "model_lstm = Sequential([\n"
       "    LSTM(64, return_sequences=True, input_shape=(LOOKBACK, 1)),\n"
       "    Dropout(0.2),\n"
       "    LSTM(32),\n"
       "    Dropout(0.2),\n"
       "    Dense(1)\n"
       "])\n"
       "model_lstm.compile(optimizer='adam', loss='mse')\n"
       "model_lstm.fit(X_train_scaled, y_train_scaled, epochs=30, batch_size=32,\n"
       "               validation_split=0.1, verbose=0)\n"
       "forecast_lstm = np.expm1(scaler_y.inverse_transform(\n"
       "    model_lstm.predict(X_test_scaled).reshape(-1, 1)).flatten())")
model_lstm = Sequential([
    LSTM(64, return_sequences=True, input_shape=(LOOKBACK, 1)),
    Dropout(0.2),
    LSTM(32),
    Dropout(0.2),
    Dense(1)
])
model_lstm.compile(optimizer='adam', loss='mse')
history_lstm = model_lstm.fit(X_train_scaled, y_train_scaled, epochs=EPOCHS, batch_size=32,
                              validation_split=0.1, verbose=0)

forecast_lstm = np.expm1(scaler_y.inverse_transform(
    model_lstm.predict(X_test_scaled, verbose=0).reshape(-1, 1)).flatten())
lstm_metrics = evaluate_forecast('LSTM', y_test, forecast_lstm)
R.text("**Python 结果：**")
R.output(str(lstm_metrics))
R.text("**解释：** LSTM 通过门控机制选择性记忆/遗忘历史信息，能拟合非线性模式。"
           "但训练集只见过 2024 年的双 11 一次，且归一化被训练集最大值锚定，"
           "面对测试期的 618 新高峰时仍会低估峰值高度。")

R.h2("GRU 模型")

R.text("**Python 代码：**")
R.code("python",
       "model_gru = Sequential([\n"
       "    GRU(64, return_sequences=True, input_shape=(LOOKBACK, 1)),\n"
       "    Dropout(0.2),\n"
       "    GRU(32),\n"
       "    Dropout(0.2),\n"
       "    Dense(1)\n"
       "])\n"
       "model_gru.compile(optimizer='adam', loss='mse')\n"
       "model_gru.fit(X_train_scaled, y_train_scaled, epochs=30, batch_size=32,\n"
       "              validation_split=0.1, verbose=0)\n"
       "forecast_gru = np.expm1(scaler_y.inverse_transform(\n"
       "    model_gru.predict(X_test_scaled).reshape(-1, 1)).flatten())")
model_gru = Sequential([
    GRU(64, return_sequences=True, input_shape=(LOOKBACK, 1)),
    Dropout(0.2),
    GRU(32),
    Dropout(0.2),
    Dense(1)
])
model_gru.compile(optimizer='adam', loss='mse')
history_gru = model_gru.fit(X_train_scaled, y_train_scaled, epochs=EPOCHS, batch_size=32,
                            validation_split=0.1, verbose=0)

forecast_gru = np.expm1(scaler_y.inverse_transform(
    model_gru.predict(X_test_scaled, verbose=0).reshape(-1, 1)).flatten())
gru_metrics = evaluate_forecast('GRU', y_test, forecast_gru)
R.text("**Python 结果：**")
R.output(str(gru_metrics))
R.text("**解释：** GRU 是 LSTM 的简化版本，参数更少、训练更快，"
       "在小样本时序上往往与 LSTM 表现接近。")

R.h2("深度学习模型对比可视化")
test_dates = ts_daily.index[LOOKBACK:][split:]
R.text("**Python 代码：**")
R.code("python",
       "plt.plot(test_dates, y_test, label='Actual')\n"
       "plt.plot(test_dates, forecast_lstm, label='LSTM')\n"
       "plt.plot(test_dates, forecast_gru, label='GRU')\n"
       "plt.legend()")
plt.figure(figsize=(14, 4))
plt.plot(test_dates, y_test, label='Actual', alpha=0.7)
plt.plot(test_dates, forecast_lstm, label='LSTM', alpha=0.8)
plt.plot(test_dates, forecast_gru, label='GRU', alpha=0.8)
plt.axvspan(pd.Timestamp('2025-06-01'), pd.Timestamp('2025-06-15'), alpha=0.15, color='orange', label='618 window')
plt.legend()
plt.title('Deep Learning Model Forecast Comparison (test period covers 618)')
R.save_plt('4_2_dl_models.png')
R.image('4_2_dl_models.png', 'Deep Learning Model Forecast Comparison | 深度学习模型预测对比（测试期含 618）')
R.text("**中文说明：** 黑色 = 真实值；蓝色 = LSTM；橙色 = GRU；橙色阴影 = 618 窗口。")
R.text("**解释：** 深度模型对正常日期拟合良好，但在 618 尖峰处同样低估——"
       "MSE 损失会让模型在「罕见但巨大」的峰面前趋向保守。"
       "春节低谷方向相反：模型基于前期正常水平外推，会**高估**低谷期 GMV。"
       "两个方向的系统性偏差都会体现在 MAPE 上。")

R.h2("训练过程可视化")
R.text("**Python 代码：**")
R.code("python",
       "plt.plot(history_lstm.history['loss'], label='LSTM Train')\n"
       "plt.plot(history_lstm.history['val_loss'], label='LSTM Val')\n"
       "plt.legend()")
plt.figure(figsize=(10, 4))
plt.plot(history_lstm.history['loss'], label='LSTM Train Loss')
plt.plot(history_lstm.history['val_loss'], label='LSTM Val Loss')
plt.plot(history_gru.history['loss'], label='GRU Train Loss', linestyle='--')
plt.plot(history_gru.history['val_loss'], label='GRU Val Loss', linestyle='--')
plt.legend()
plt.title('Training and Validation Loss')
plt.xlabel('Epoch')
plt.ylabel('MSE Loss')
R.save_plt('4_3_training_loss.png')
R.image('4_3_training_loss.png', 'Training and Validation Loss | 训练与验证损失曲线')
R.text("**中文说明：** 横轴 = 训练轮次（Epoch）；纵轴 = MSE 损失。")
R.text("**解释：** 若验证损失在某轮后开始上升，说明模型开始过拟合。"
       "EarlyStopping 回调可在验证损失不再改善时自动停止训练。")


# ============================================================
# 5. 模型综合对比
# ============================================================
R.h1("模型综合对比")

R.h2("指标汇总表")

# 持续法基线（naive persistence）：预测明天 = 今天
naive_fc = ts_daily.shift(1).loc[test.index].values
naive_metrics = evaluate_forecast('Naive(持续法)', test.values, naive_fc)

all_metrics = [naive_metrics]
if arima_metrics is not None:
    all_metrics.append(arima_metrics)
if sarima_metrics is not None:
    all_metrics.append(sarima_metrics)
all_metrics.append(lstm_metrics)
all_metrics.append(gru_metrics)
metrics_df = pd.DataFrame(all_metrics)

R.text("**Python 代码：**")
R.code("python",
       "metrics_df = pd.DataFrame([arima_metrics, sarima_metrics, lstm_metrics, gru_metrics])\n"
       "print(metrics_df)")
R.text("**Python 结果：**")
R.output(metrics_df.to_string(index=False))
R.text("**解释：** RMSE 和 MAE 越小越好；MAPE < 10% 通常认为预测精度可接受；"
       "R² 越接近 1 说明模型解释力越强。"
       "持续法（预测明天=今天）是时序预测的最低基线：日 GMV 日间波动极大，"
       "持续法 MAPE 超过 50%，说明该序列本身预测难度高；"
       "所有模型应显著优于持续法才有采用价值。"
       "本测试期覆盖 618，各模型 MAPE 都会被峰值日拉高，"
       "评估时应同时给出「剔除大促日」的口径（见 5.3）。")

R.h2("模型对比柱状图")
R.text("**Python 代码：**")
R.code("python",
       "metrics_df.set_index('Model')[['RMSE','MAE']].plot(kind='bar')\n"
       "plt.xticks(rotation=30)")
plt.figure(figsize=(10, 5))
metrics_df.set_index('Model')[['RMSE', 'MAE']].plot(kind='bar', ax=plt.gca())
plt.title('Model Comparison: RMSE and MAE')
plt.ylabel('Error')
plt.xticks(rotation=30)
plt.tight_layout()
R.save_plt('5_2_model_comparison.png')
R.image('5_2_model_comparison.png', 'Model Comparison: RMSE and MAE | 模型对比：RMSE 与 MAE')
R.text("**中文说明：** 横轴 = 模型名称；纵轴 = 误差值。蓝色 = RMSE；橙色 = MAE。")
R.text("**解释：** RMSE 对大误差更敏感，MAE 对所有误差一视同仁。"
       "若某模型 RMSE 远大于 MAE，说明存在少量大误差预测——在本数据中即大促峰值日。")

R.h2("大促峰值对指标的影响（全量 vs 剔除事件日）")
R.text("把测试期 6 月 1 日之后的 618 窗口剔除，重新计算各模型误差，"
       "观察峰值对评估口径的影响。")

def _event_mask(idx):
    return (idx >= pd.Timestamp('2025-06-01'))

rows = []
for name, fc, idx in [
        ('Naive(持续法)', naive_fc, test.index),
        ('ARIMA', forecast_arima.values if forecast_arima is not None else None, test.index),
        ('SARIMA', forecast_sarima.values if forecast_sarima is not None else None, test.index),
        ('LSTM', forecast_lstm, test_dates),
        ('GRU', forecast_gru, test_dates)]:
    if fc is None:
        continue
    fc = np.asarray(fc).flatten()
    yt = test.values if idx is test.index else y_test
    m = ~_event_mask(idx)
    rows.append([name, mape(yt, fc), mape(yt[m], fc[m])])
impact_df = pd.DataFrame(rows, columns=['模型', 'MAPE(%) 全量测试期', 'MAPE(%) 剔除618窗口'])
R.table(impact_df)
_delta = (impact_df['MAPE(%) 全量测试期'] - impact_df['MAPE(%) 剔除618窗口']).mean()
R.text("**解释：** 剔除 618 窗口后，各模型 MAPE 平均变动 %.2f 个百分点。"
       "618 峰值日是全量口径误差的重要来源之一；此外测试期整体 GMV 水平高于训练期"
       "（增长趋势 + 训练集未见过 618 量级），也贡献了相当一部分误差。"
       "业务上若要预测大促日 GMV，应引入日历事件特征、营销投放变量，或对峰值单独建模，"
       "而不是指望单变量模型自动学会一年仅出现一两次的模式。" % _delta)


# ============================================================
# 6. 分类任务扩展：高 GMV 峰值日识别
# ============================================================
R.h1("分类任务扩展：高 GMV 峰值日识别")
R.text("将连续预测转化为二分类问题：仅凭过去 30 天的 GMV 窗口，"
       "预测次日是否为高 GMV 峰值日（超过训练口径 90% 分位数，"
       "该分位段基本覆盖双 11、618 等大促日）。")

R.h2("分类标签构建")

threshold = ts_daily.quantile(0.9)

R.text("以日 GMV 的 90%% 分位数（%.0f 元）为阈值，超过则标记为峰值日（1），否则为普通日（0）。" % threshold)
R.text("**Python 代码：**")
R.code("python",
       "threshold = ts_daily.quantile(0.9)\n"
       "labels = (ts_daily > threshold).astype(int)\n"
       "print('峰值日占比: %.2f%%' % (labels.mean() * 100))")
labels = (ts_daily > threshold).astype(int)
R.text("**Python 结果：**")
R.output("阈值 = %.4f\n峰值日样本占比 = %.2f%%" % (threshold, labels.mean() * 100))
R.text("**解释：** 约 10% 的日子为峰值日。由于峰值日由日历事件驱动、"
       "而非由历史 GMV 惯性驱动，纯滑动窗口特征难以提前预判，"
       "预期 Recall 有限——这正是该实验的观察点。")

R.h2("分类模型评估")
R.text("使用逻辑回归作为基线分类器（输入为标准化后的 30 天窗口）。")
R.text("**Python 代码：**")
R.code("python",
       "from sklearn.linear_model import LogisticRegression\n"
       "\n"
       "clf = LogisticRegression(max_iter=1000)\n"
       "clf.fit(X_train_scaled.reshape(X_train_scaled.shape[0], -1), y_train_class)\n"
       "y_pred_class = clf.predict(X_test_scaled.reshape(X_test_scaled.shape[0], -1))\n"
       "print('Accuracy: %.4f' % accuracy_score(y_test_class, y_pred_class))")
try:
    y_class = labels.values[LOOKBACK:]
    y_train_class, y_test_class = y_class[:split], y_class[split:]
    clf = LogisticRegression(max_iter=1000)
    clf.fit(X_train_scaled.reshape(X_train_scaled.shape[0], -1), y_train_class)
    y_pred_class = clf.predict(X_test_scaled.reshape(X_test_scaled.shape[0], -1))
    acc = accuracy_score(y_test_class, y_pred_class)
    prec = precision_score(y_test_class, y_pred_class, zero_division=0)
    rec = recall_score(y_test_class, y_pred_class, zero_division=0)
    f1 = f1_score(y_test_class, y_pred_class, zero_division=0)
    R.text("**Python 结果：**")
    R.output("Accuracy  = %.4f\nPrecision = %.4f\nRecall    = %.4f\nF1-Score  = %.4f"
             % (acc, prec, rec, f1))
    R.text("**解释：** Accuracy 反映整体正确率；Precision 反映「预测为峰值日」的准确性；"
           "Recall 反映「实际峰值日」被检出的比例；F1 是 Precision 和 Recall 的调和均值。"
           "若 Recall 明显偏低，说明窗口内 GMV 惯性信息不足以识别大促日，"
           "需要加入日历事件等外生特征。")
except Exception as e:
    R.text("*分类任务失败：%s*" % e)

conn.close()

# ============================================================
# 输出
# ============================================================
R.write()
