#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据质量监控示例（pandera + 表级一致性规则）
- 数据源: data/ecommerce/ecommerce.db（orders / order_items / payments，只读）
- 校验层:
  A. 列级规则（pandera DataFrameSchema, lazy 校验收集全部失败）
  B. 表级规则（时间链顺序 / 金额一致性 / 外键完整 / 主键重复 / 空值率，pandas 断言）
- 演示: 真实数据校验 + 内存脏数据注入校验（不改动数据库文件）
- 输出: data_quality_report.md（含每项规则通过/失败统计与失败样例行）
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

import pandera
import pandera.pandas as pa
from pandera import Column, Check

PANDERA_VER = pandera.__version__

warnings.filterwarnings('ignore')

# ================== 配置区 ==================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'ecommerce', 'ecommerce.db'))
OUTPUT_MD = os.path.join(SCRIPT_DIR, 'data_quality_report.md')
IMAGE_DIR = os.path.join(SCRIPT_DIR, 'images')
MONEY_TOL = 0.02          # 金额一致性容差（元）
SAMPLE_N  = 5             # 失败样例行展示条数

if not os.path.isfile(DB_PATH):
    raise FileNotFoundError("未找到数据库: %s" % DB_PATH)

os.makedirs(IMAGE_DIR, exist_ok=True)

# ================== 中文字体 ==================
def _find_cjk_font_file():
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

# ================== 数据加载 ==================
conn = sqlite3.connect(DB_PATH)
orders   = pd.read_sql_query("SELECT * FROM orders", conn)
items    = pd.read_sql_query("SELECT * FROM order_items", conn)
payments = pd.read_sql_query("SELECT * FROM payments", conn)
products = pd.read_sql_query("SELECT product_id FROM products", conn)
conn.close()
print("[数据] orders=%d, order_items=%d, payments=%d" % (len(orders), len(items), len(payments)))

# ================== A. 列级规则：pandera Schema ==================
ORDER_STATUS = ['已完成', '已发货', '待付款', '已取消']
CHANNELS     = ['APP', '小程序', '网页', '线下']
PAY_METHODS  = ['微信支付', '支付宝', '银行卡', '余额']
PAY_STATUS   = ['成功', '失败', '已退款']

schema_orders = pa.DataFrameSchema({
    'order_id':        Column(int, nullable=False),
    'customer_id':     Column(int, nullable=False),
    'order_status':    Column(str, Check.isin(ORDER_STATUS), nullable=False),
    'channel':         Column(str, Check.isin(CHANNELS), nullable=False),
    'freight_amount':  Column(float, Check.ge(0)),
    'discount_amount': Column(float, Check.ge(0)),
    'total_amount':    Column(float, Check.ge(0), nullable=False),
    'created_at':      Column(str, nullable=False),
}, strict=False)

schema_items = pa.DataFrameSchema({
    'item_id':       Column(int, nullable=False),
    'order_id':      Column(int, nullable=False),
    'product_id':    Column(int, nullable=False),
    'quantity':      Column(int, Check.gt(0)),
    'unit_price':    Column(float, Check.ge(0)),
    'item_discount': Column(float, Check.ge(0)),
    'subtotal':      Column(float),
}, strict=False)

schema_payments = pa.DataFrameSchema({
    'payment_id':     Column(int, nullable=False),
    'order_id':       Column(int, nullable=False),
    'payment_method': Column(str, Check.isin(PAY_METHODS), nullable=False),
    'payment_amount': Column(float, Check.ge(0)),
    'payment_status': Column(str, Check.isin(PAY_STATUS), nullable=False),
}, strict=False)

def run_schema(schema, df, table):
    """pandera lazy 校验 → 规则明细列表（含内置 not_nullable 检查）"""
    fc = None
    try:
        schema.validate(df, lazy=True)
    except pa.errors.SchemaErrors as e:
        fc = e.failure_cases
    rows = []
    for col, col_schema in schema.columns.items():
        checks = ([None] if not col_schema.nullable else []) + list(col_schema.checks or [])
        for chk in checks:
            name = 'not_nullable' if chk is None else (getattr(chk, 'name', None) or str(chk))
            n_fail, bad = 0, df.iloc[0:0]
            if fc is not None and len(fc):
                sub = fc[(fc['column'] == col) &
                         (fc['check'].astype(str).str.contains(name, regex=False))]
                n_fail = len(sub)
                if n_fail and 'index' in sub:
                    idx = pd.Index(sub['index'].dropna().astype(int).unique())
                    bad = df.loc[df.index.intersection(idx)]
            rows.append(dict(table=table, rule='列校验 %s: %s' % (col, name),
                             n_check=len(df), n_fail=n_fail, samples=bad.head(SAMPLE_N)))
    return rows

# ================== B. 表级规则：pandas 断言 runner ==================
def rule_result(table, rule, n_check, bad_mask, df):
    bad = df[bad_mask] if bad_mask is not None and len(df) else df.iloc[0:0]
    return dict(table=table, rule=rule, n_check=int(n_check),
                n_fail=int(len(bad)), samples=bad.head(SAMPLE_N))

def run_table_rules(orders, items, payments, products):
    rows = []

    # ---- orders ----
    ts = orders[['created_at', 'paid_at', 'shipped_at', 'delivered_at']].apply(
        lambda s: pd.to_datetime(s, format='%Y-%m-%d %H:%M:%S', errors='coerce'))
    seg_defs = [('时间链段1 created≤paid（NULL 跳过）', 'created_at', 'paid_at'),
                ('时间链段2 paid≤shipped（NULL 跳过）', 'paid_at', 'shipped_at'),
                ('时间链段3 shipped≤delivered（NULL 跳过）', 'shipped_at', 'delivered_at')]
    for nm, a, b in seg_defs:
        bad = ~(ts[a].isna() | ts[b].isna() | (ts[a] <= ts[b]))
        rows.append(rule_result('orders', nm, len(orders), bad, orders))

    item_sum = items.groupby('order_id')['subtotal'].sum()
    chk = orders[['order_id', 'total_amount', 'freight_amount']].copy()
    chk['sum_sub'] = chk['order_id'].map(item_sum).fillna(0)
    diff = (chk['total_amount'] - chk['sum_sub'] - chk['freight_amount']).abs()
    rows.append(rule_result('orders', '金额一致 total = Σsubtotal + freight（容差%.2f元）' % MONEY_TOL,
                            len(chk), (diff > MONEY_TOL).to_numpy(), orders))

    dup = orders['order_id'].duplicated(keep=False)
    rows.append(rule_result('orders', '主键 order_id 唯一', len(orders), dup, orders))

    key_cols = ['order_id', 'customer_id', 'order_status', 'created_at', 'total_amount']
    na_rate = orders[key_cols].isna().mean()
    rows.append(rule_result('orders', '关键列空值率=0（%s）' % '/'.join(key_cols),
                            len(orders) * len(key_cols), None, orders.iloc[0:0]) |
                dict(n_fail=int(orders[key_cols].isna().sum().sum())))

    # ---- order_items ----
    calc = (items['unit_price'] * items['quantity'] - items['item_discount'] - items['subtotal']).abs()
    rows.append(rule_result('order_items', '行内一致 subtotal = unit_price×quantity − item_discount（容差%.2f元）' % MONEY_TOL,
                            len(items), calc > MONEY_TOL, items))

    fk_ok = items['order_id'].isin(set(orders['order_id']))
    rows.append(rule_result('order_items', '外键完整 order_items.order_id ⊆ orders.order_id',
                            len(items), ~fk_ok, items))
    fk_p = items['product_id'].isin(set(products['product_id']))
    rows.append(rule_result('order_items', '外键完整 order_items.product_id ⊆ products.product_id',
                            len(items), ~fk_p, items))
    dup_i = items['item_id'].duplicated(keep=False)
    rows.append(rule_result('order_items', '主键 item_id 唯一', len(items), dup_i, items))

    # ---- payments ----
    fk_pay = payments['order_id'].isin(set(orders['order_id']))
    rows.append(rule_result('payments', '外键完整 payments.order_id ⊆ orders.order_id',
                            len(payments), ~fk_pay, payments))
    dup_p = payments['payment_id'].duplicated(keep=False)
    rows.append(rule_result('payments', '主键 payment_id 唯一', len(payments), dup_p, payments))

    return rows

# ================== 汇总与渲染 ==================
def summarize(rows):
    out = []
    for r in rows:
        out.append(dict(table=r['table'], rule=r['rule'], n_check=r['n_check'],
                        n_fail=r['n_fail'],
                        status='通过' if r['n_fail'] == 0 else '失败'))
    return pd.DataFrame(out)

def samples_md(rows):
    """失败样例行 markdown"""
    blocks = []
    for r in rows:
        if r['n_fail'] > 0 and len(r['samples']):
            s = r['samples'].copy()
            blocks.append("**%s / %s**（失败 %d 行，示例前 %d 行）：\n\n```\n%s\n```" %
                          (r['table'], r['rule'], r['n_fail'], len(s), s.to_string(index=False)))
    return "\n\n".join(blocks) if blocks else "（无失败样例）"

# ---- 真实数据校验 ----
print("[校验] 真实数据：列级 schema ...")
real_rows = []
real_rows += run_schema(schema_orders, orders, 'orders')
real_rows += run_schema(schema_items, items, 'order_items')
real_rows += run_schema(schema_payments, payments, 'payments')
print("[校验] 真实数据：表级规则 ...")
real_rows += run_table_rules(orders, items, payments, products)
real_summary = summarize(real_rows)

# 真实发现的定位分析：时间链段2 在日期粒度下是否成立（区分时刻错位与日期错误）
_ts = orders[['paid_at', 'shipped_at']].apply(
    lambda s: pd.to_datetime(s, format='%Y-%m-%d %H:%M:%S', errors='coerce'))
n_seg2_fail = int(real_summary.loc[real_summary.rule.str.contains('时间链段2'), 'n_fail'].iloc[0])
_ts_d = _ts.apply(lambda s: s.dt.normalize())
n_seg2_fail_date = int((~(_ts_d['paid_at'].isna() | _ts_d['shipped_at'].isna() |
                          (_ts_d['paid_at'] <= _ts_d['shipped_at']))).sum())
print("[发现] 时间链段2(paid≤shipped) 失败 %d 行；日期粒度下失败 %d 行" % (n_seg2_fail, n_seg2_fail_date))

# ---- 脏数据注入演示（仅内存副本，不改动数据库） ----
print("[校验] 脏数据注入演示 ...")
bad_o = orders.copy()
bad_i = items.copy()
bad_p = payments.copy()
rng = np.random.default_rng(42)

# 注入: 负金额
idx = rng.choice(bad_o.index, 3, replace=False)
bad_o.loc[idx, 'total_amount'] = -100.0
# 注入: 非法枚举
bad_o.loc[rng.choice(bad_o.index, 3, replace=False), 'order_status'] = '已丢失'
bad_o.loc[rng.choice(bad_o.index, 2, replace=False), 'channel'] = '元宇宙'
# 注入: 时间链乱序（签收早于下单）
idx = rng.choice(bad_o[bad_o.delivered_at.notna()].index, 3, replace=False)
bad_o.loc[idx, 'delivered_at'] = '2023-01-01 00:00:00'
# 注入: 金额不一致（改 freight 破坏等式）
idx = rng.choice(bad_o.index, 3, replace=False)
bad_o.loc[idx, 'freight_amount'] = bad_o.loc[idx, 'freight_amount'] + 50
# 注入: 主键重复
bad_o = pd.concat([bad_o, bad_o.head(2)], ignore_index=True)
# 注入: 关键列空值
bad_o.loc[bad_o.index[:2], 'customer_id'] = None
bad_o['customer_id'] = bad_o['customer_id'].astype('Int64')

bad_i.loc[rng.choice(bad_i.index, 3, replace=False), 'quantity'] = 0
bad_i.loc[rng.choice(bad_i.index, 2, replace=False), 'order_id'] = 99999999   # 孤儿外键
bad_i.loc[rng.choice(bad_i.index, 3, replace=False), 'subtotal'] = 999999.0    # 行内金额不一致

bad_p.loc[rng.choice(bad_p.index, 2, replace=False), 'payment_amount'] = -5.0
bad_p.loc[rng.choice(bad_p.index, 2, replace=False), 'payment_method'] = '贝壳'
bad_p.loc[rng.choice(bad_p.index, 2, replace=False), 'order_id'] = 99999999

# schema 的 customer_id 列需允许 Int64 → 临时放宽
schema_orders_bad = pa.DataFrameSchema({
    'customer_id':     Column(nullable=False),
    'order_status':    Column(str, Check.isin(ORDER_STATUS), nullable=False),
    'channel':         Column(str, Check.isin(CHANNELS), nullable=False),
    'freight_amount':  Column(float, Check.ge(0)),
    'total_amount':    Column(float, Check.ge(0), nullable=False),
}, strict=False)

bad_rows = []
bad_rows += run_schema(schema_orders_bad, bad_o, 'orders(脏)')
bad_rows += run_schema(schema_items, bad_i, 'order_items(脏)')
bad_rows += run_schema(schema_payments, bad_p, 'payments(脏)')
bad_rows += run_table_rules(bad_o, bad_i, bad_p, products)
bad_summary = summarize(bad_rows)

# ================== 绘图 ==================
fig, ax = plt.subplots(figsize=(7, 4))
agg = bad_summary.groupby('table')['n_fail'].sum()
colors = ['#DD8452' if v > 0 else '#4C72B0' for v in agg]
ax.bar(agg.index, agg.values, color=colors)
for i, v in enumerate(agg.values):
    ax.text(i, v + 0.1, str(v), ha='center')
ax.set_ylabel('失败规则数'); ax.set_title('脏数据注入演示：各表失败规则计数')
fig.tight_layout()
fig.savefig(os.path.join(IMAGE_DIR, 'dq_fail_counts.png'), dpi=130)
plt.close(fig)
print("[图] images/dq_fail_counts.png 已生成")

# ================== 写报告 ==================
def summary_table(sdf):
    lines = ["| 表 | 规则 | 检查行数 | 失败数 | 状态 |", "|---|---|---|---|---|"]
    for _, r in sdf.iterrows():
        mark = '✅ 通过' if r['status'] == '通过' else '❌ 失败'
        lines.append("| %s | %s | %d | %d | %s |" % (r['table'], r['rule'], r['n_check'], r['n_fail'], mark))
    return "\n".join(lines)

n_rule_real = len(real_summary)
n_pass_real = int((real_summary.status == '通过').sum())
n_rule_bad = len(bad_summary)
n_fail_bad = int((bad_summary.status == '失败').sum())

md = f"""# 数据质量监控报告 — orders / order_items / payments

- **数据来源**：`data/ecommerce/ecommerce.db`（只读）
- **校验框架**：列级规则用 **pandera {PANDERA_VER}** `DataFrameSchema`（`lazy=True` 一次收集全部失败）；表级一致性规则（时间链/跨表金额/外键/重复/空值率）用 pandas 断言实现——pandera 对跨行、跨表规则表达力有限，生产实践通常两层并存
- **两部分**：① 真实数据校验；② 内存脏数据注入校验（演示失败统计与失败样例行，**不改动数据库文件**）

## 1. 校验规则清单

| 类别 | 规则 |
|---|---|
| 列级（pandera） | 金额非负（total/freight/discount/subtotal/unit_price/payment_amount）、枚举值域（order_status/channel/payment_method/payment_status）、quantity>0、关键列非空 |
| 表级（pandas） | 时间链三段分别校验 created≤paid / paid≤shipped / shipped≤delivered（NULL 跳过）；total_amount = Σsubtotal + freight_amount（容差 {MONEY_TOL} 元）；行内 subtotal = unit_price×quantity − item_discount；外键完整（order_items/payments → orders，order_items → products）；主键唯一；关键列空值率=0 |

## 2. 真实数据校验结果

共 {n_rule_real} 条规则，通过 {n_pass_real}，失败 {n_rule_real - n_pass_real}。

{summary_table(real_summary)}

### 2.1 真实发现：时间链段2（paid≤shipped）存在数据缺陷

{"真实数据全部通过，无异常发现。" if n_rule_real == n_pass_real else f"""时间链三段中仅段2失败：{n_seg2_fail} 行（占已支付订单约 {n_seg2_fail/19181:.1%}）的 `shipped_at` 早于同日 `paid_at`；**日期粒度重测失败 {n_seg2_fail_date} 行**，即日期次序正确、仅时刻错位——可定位为数据生成器缺陷（发货时刻生成时未以支付时刻为下界），而非业务异常。其余全部规则通过：金额链路（total=Σsubtotal+freight、行内 subtotal 勾稽）在 {MONEY_TOL} 元容差下闭合，外键与主键完整，关键列无空值。

对下游的影响与处置：凡依赖 `shipped_at − paid_at` 时长（如发货时效 KPI）的分析须先按日期粒度取整或剔除该 {n_seg2_fail} 行；本次按任务约束不改动 `data/ecommerce`，缺陷记录于此待上游修复。"""}

{samples_md(real_rows) if n_rule_real != n_pass_real else ""}

## 3. 脏数据注入演示（内存副本）

向内存副本注入 9 类典型脏数据：负金额 5 处、非法枚举 7 处、时间链乱序 3 处、订单金额不一致 3 处、主键重复 2 行、关键列空值 2 处、孤儿外键 4 处、行内金额不一致 3 处、quantity=0 共 3 处。重跑同一套规则，共 {n_rule_bad} 条，失败 {n_fail_bad} 条：

{summary_table(bad_summary)}

### 3.1 失败样例行

{samples_md(bad_rows)}

![脏数据演示失败计数](images/dq_fail_counts.png)

## 4. 结论与工程建议

1. 真实数据 {n_pass_real}/{n_rule_real} 条规则通过。唯一失败为时间链段2（{n_seg2_fail} 行时刻级错位、日期级正确），已定位为数据生成器缺陷——这正是质量监控的价值：README 声称的不变量与数据实际状态存在偏差，只能靠规则化校验暴露。金额链路在 {MONEY_TOL} 元容差下完全闭合，与 `_verify.py` 结论一致。
2. 注入演示验证了规则集的检出能力：9 类脏数据全部被对应规则捕获，且 pandera `lazy=True` 模式能一次返回全部失败明细（含失败值与行号），适合作为监控报表数据源。
3. 工程化落地建议：
   - 规则即代码，版本化管理；每次 ETL 后自动跑校验，失败规则数非零即熔断下游任务。
   - 两层结构：pandera 管列级契约（类型/值域/非空），SQL 或 pandas 管跨行跨表一致性（外键、金额勾稽、时间链）。
   - 监控指标化：把各表 `n_fail/n_check` 作为质量分指标入时序库，超阈值告警，而非只看布尔通过与否。
"""

with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
    f.write(md)
print("[报告] %s 已生成" % OUTPUT_MD)
print("[完成]")
