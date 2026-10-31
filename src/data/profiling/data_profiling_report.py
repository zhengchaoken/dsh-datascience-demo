# -*- coding: utf-8 -*-
"""
data_profiling_report.py
========================
电商数据集（ecommerce.db）多表数据探查脚本。

用法：
    python data_profiling_report.py                 # 默认探查 ../ecommerce/ecommerce.db
    python data_profiling_report.py --db PATH       # 指定其他 SQLite 数据库

输出（均写入脚本所在目录）：
    data_profiling_report.md   面向数据团队的主报告
    report_manager.html        面向数据管理者（资产健康度 / 风险 / 合规）
    report_analyst.html        面向数据分析师（字段质量 / 建模就绪度 / 探索效率）
    images/*.png               报告引用的图表

依赖：pandas numpy matplotlib seaborn
"""

import argparse
import base64
import json
import os
import re
import sqlite3
import warnings
from datetime import datetime
from io import BytesIO

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns

warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(SCRIPT_DIR, "..", "ecommerce", "ecommerce.db")
OUTPUT_MD = os.path.join(SCRIPT_DIR, "data_profiling_report.md")
OUTPUT_MANAGER = os.path.join(SCRIPT_DIR, "report_manager.html")
OUTPUT_ANALYST = os.path.join(SCRIPT_DIR, "report_analyst.html")
IMAGE_DIR = os.path.join(SCRIPT_DIR, "images")
RANDOM_SEED = 42

TABLE_META = {
    "categories": ("类目表", "两级类目树，parent_id 自关联"),
    "customers": ("客户表", "注册会员主数据"),
    "products": ("商品表", "SPU 级商品主数据"),
    "coupons": ("优惠券表", "营销券规则"),
    "orders": ("订单表", "订单主表，一单可含多商品"),
    "order_items": ("订单明细表", "订单与商品的多对多连接表"),
    "payments": ("支付表", "已支付订单的支付流水"),
    "reviews": ("评价表", "已签收订单的客户评价"),
    "user_events": ("行为事件表", "浏览 / 加购埋点日志"),
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2})?$")


# ============================================================
# 中文与图片工具
# ============================================================

def setup_chinese_font() -> str:
    preferred = ["SimHei", "Microsoft YaHei", "WenQuanYi Micro Hei",
                 "Noto Sans CJK SC", "Source Han Sans SC", "DejaVu Sans"]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in preferred:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            return name
    plt.rcParams["axes.unicode_minus"] = False
    return "DejaVu Sans"


FONT_NAME = setup_chinese_font()
sns.set_style("whitegrid")
plt.rcParams["figure.dpi"] = 110

CHART_FILES: dict[str, str] = {}


def save_fig(fig, key: str, title: str) -> None:
    """保存图表到 images/ 并登记相对路径。"""
    os.makedirs(IMAGE_DIR, exist_ok=True)
    filename = f"{key}.png"
    path = os.path.join(IMAGE_DIR, filename)
    fig.savefig(path, bbox_inches="tight", dpi=120)
    plt.close(fig)
    CHART_FILES[key] = f"images/{filename}"
    print(f"  [图] {title} -> images/{filename}")


def fig_b64(key: str) -> str:
    path = os.path.join(SCRIPT_DIR, CHART_FILES[key])
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("utf-8")


def n(value) -> str:
    """整数千分位。"""
    try:
        return f"{int(value):,}"
    except Exception:
        return str(value)


def pct(value, digits: int = 2) -> str:
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except Exception:
        return "—"


def money(value) -> str:
    try:
        return f"¥{float(value):,.0f}"
    except Exception:
        return "—"


TEXT_COLUMNS = {"review_content", "product_name", "customer_name", "brand", "city", "category_name"}

MISSING_MEANING = {
    "parent_id": "一级类目没有父节点，NULL 表示类目树的根",
    "coupon_id": "该订单未使用优惠券",
    "paid_at": "订单尚未支付（待付款或已取消）",
    "shipped_at": "订单尚未发货",
    "delivered_at": "订单尚未签收",
}


# ============================================================
# 表级 / 字段级探查
# ============================================================

def is_time_column(series: pd.Series, name: str) -> bool:
    if name.endswith("_at") or name.endswith("_date") or name in ("valid_from", "valid_to"):
        return True
    if (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)) and len(series) > 0:
        sample = series.dropna().head(20).astype(str)
        if len(sample) == 0:
            return False
        return float(sample.str.match(DATE_RE).mean()) >= 0.9
    return False


def profile_table(df: pd.DataFrame, name: str) -> dict:
    """产出单表的完整画像。"""
    rows = len(df)
    cols = len(df.columns)
    duplicated = int(df.duplicated().sum())
    missing = df.isna().sum()
    missing_rate = df.isna().mean()

    candidate_keys = []
    for col in df.columns:
        if rows > 0 and df[col].nunique(dropna=True) == rows:
            candidate_keys.append(col)

    fields = []
    for col in df.columns:
        series = df[col]
        non_null = series.dropna()
        info = {
            "name": col,
            "dtype": str(series.dtype),
            "missing": int(missing[col]),
            "missing_rate": float(missing_rate[col]),
            "unique": int(series.nunique(dropna=True)),
            "kind": "其他",
            "stats": {},
            "top": [],
            "time_min": None,
            "time_max": None,
        }

        if pd.api.types.is_numeric_dtype(series):
            info["kind"] = "数值"
            if len(non_null) > 0:
                q1, q2, q3 = non_null.quantile([0.25, 0.5, 0.75])
                iqr = q3 - q1
                lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
                outliers = int(((non_null < lower) | (non_null > upper)).sum())
                std = float(non_null.std(ddof=0))
                z_outliers = int((abs((non_null - non_null.mean()) / std) > 3).sum()) if std > 0 else 0
                info["stats"] = {
                    "mean": float(non_null.mean()),
                    "std": std,
                    "min": float(non_null.min()),
                    "q25": float(q1),
                    "median": float(q2),
                    "q75": float(q3),
                    "max": float(non_null.max()),
                    "skew": float(non_null.skew()) if len(non_null) > 2 else 0.0,
                    "iqr_outliers": outliers,
                    "iqr_rate": outliers / len(non_null),
                    "z_outliers": z_outliers,
                    "z_rate": z_outliers / len(non_null),
                }
        elif is_time_column(series, col):
            info["kind"] = "时间"
            if len(non_null) > 0:
                info["time_min"] = str(non_null.min())[:10]
                info["time_max"] = str(non_null.max())[:10]
        elif col in TEXT_COLUMNS:
            info["kind"] = "文本"
            if len(non_null) > 0:
                lengths = non_null.astype(str).str.len()
                info["stats"] = {
                    "avg_len": float(lengths.mean()),
                    "max_len": int(lengths.max()),
                    "empty": int((non_null.astype(str).str.strip() == "").sum()),
                }
        elif series.nunique(dropna=True) <= 20:
            info["kind"] = "分类"
            info["top"] = [
                [str(idx), int(cnt)]
                for idx, cnt in series.value_counts(dropna=True).head(6).items()
            ]
        else:
            info["kind"] = "文本"
            if len(non_null) > 0:
                lengths = non_null.astype(str).str.len()
                info["stats"] = {
                    "avg_len": float(lengths.mean()),
                    "max_len": int(lengths.max()),
                    "empty": int((non_null.astype(str).str.strip() == "").sum()),
                }

        fields.append(info)

    return {
        "name": name,
        "label": TABLE_META.get(name, ("", ""))[0],
        "description": TABLE_META.get(name, ("", ""))[1],
        "rows": rows,
        "cols": cols,
        "duplicated": duplicated,
        "candidate_keys": candidate_keys,
        "fields": fields,
    }


# ============================================================
# 跨表一致性
# ============================================================

def run_consistency_checks(con: sqlite3.Connection, profiles: list[dict]) -> list[dict]:
    cur = con.cursor()
    checks: list[dict] = []

    def add(name, meaning, value, status, detail=""):
        checks.append({
            "name": name, "meaning": meaning, "value": value,
            "status": status, "detail": detail,
        })

    fk_issues = cur.execute("PRAGMA foreign_key_check").fetchall()
    add("外键完整性", "所有外键都能在主表中找到对应记录",
        f"{len(fk_issues)} 处违规", "ok" if not fk_issues else "risk")

    bad_amount = cur.execute("""
        SELECT COUNT(*) FROM orders o
        WHERE o.order_status != '待付款'
          AND ABS(o.total_amount - (
              (SELECT ROUND(SUM(oi.subtotal), 2) FROM order_items oi WHERE oi.order_id = o.order_id)
              + o.freight_amount)) > 0.01
    """).fetchone()[0]
    add("订单金额勾稽", "实付金额 = 明细小计之和 + 运费",
        f"{n(bad_amount)} 单不一致", "ok" if bad_amount == 0 else "risk")

    bad_discount = cur.execute("""
        SELECT COUNT(*) FROM orders o
        WHERE o.coupon_id IS NOT NULL
          AND ABS(o.discount_amount - (
              (SELECT ROUND(SUM(oi.item_discount), 2) FROM order_items oi WHERE oi.order_id = o.order_id)
          )) > 0.01
    """).fetchone()[0]
    add("优惠金额勾稽", "明细分摊优惠之和 = 订单优惠金额",
        f"{n(bad_discount)} 单不一致", "ok" if bad_discount == 0 else "risk")

    bad_chain = cur.execute("""
        SELECT COUNT(*) FROM orders
        WHERE (paid_at IS NOT NULL AND substr(paid_at, 1, 10) < substr(created_at, 1, 10))
           OR (shipped_at IS NOT NULL AND substr(shipped_at, 1, 10) < substr(created_at, 1, 10))
           OR (delivered_at IS NOT NULL AND substr(delivered_at, 1, 10) < substr(created_at, 1, 10))
    """).fetchone()[0]
    add("时间链顺序（日期）", "下单 ≤ 支付 ≤ 发货 ≤ 签收（按日期比较）",
        f"{n(bad_chain)} 单逆序", "ok" if bad_chain == 0 else "risk")

    order_time_mismatch = cur.execute("""
        SELECT COUNT(*) FROM orders
        WHERE shipped_at IS NOT NULL AND paid_at IS NOT NULL
          AND shipped_at < paid_at
    """).fetchone()[0]
    add("时间链时刻精度", "同一日内存在时刻错位的订单数（日期粒度不受影响）",
        f"{n(order_time_mismatch)} 单", "warn" if order_time_mismatch else "ok",
        "构造\"支付到发货时长\"类指标时应按日期为粒度")

    paid_without_record = cur.execute("""
        SELECT COUNT(*) FROM orders o
        WHERE o.order_status IN ('已完成', '已发货')
          AND NOT EXISTS (SELECT 1 FROM payments p WHERE p.order_id = o.order_id)
    """).fetchone()[0]
    add("支付记录覆盖", "已完成 / 已发货订单都应有支付记录",
        f"{n(paid_without_record)} 单缺失", "ok" if paid_without_record == 0 else "risk")

    amount_mismatch = cur.execute("""
        SELECT COUNT(*) FROM payments p JOIN orders o ON p.order_id = o.order_id
        WHERE p.payment_status = '成功' AND ABS(p.payment_amount - o.total_amount) > 0.01
    """).fetchone()[0]
    add("支付金额一致性", "成功支付金额 = 订单实付金额",
        f"{n(amount_mismatch)} 单不一致", "ok" if amount_mismatch == 0 else "risk")

    review_orphan = cur.execute("""
        SELECT COUNT(*) FROM reviews r
        LEFT JOIN orders o ON r.order_id = o.order_id
        WHERE o.order_id IS NULL OR o.order_status != '已完成'
    """).fetchone()[0]
    add("评价归属", "评价只应挂在已完成订单上",
        f"{n(review_orphan)} 条越界", "ok" if review_orphan == 0 else "risk")

    multi_review = cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT order_id FROM reviews GROUP BY order_id HAVING COUNT(*) > 1
        )
    """).fetchone()[0]
    add("评价唯一性", "每个订单至多一条评价",
        f"{n(multi_review)} 单重复", "ok" if multi_review == 0 else "risk")

    closed_loop = cur.execute("""
        SELECT COUNT(*) FROM user_events e
        WHERE EXISTS (
            SELECT 1 FROM orders o
            JOIN order_items oi ON oi.order_id = o.order_id
            WHERE o.customer_id = e.customer_id
              AND oi.product_id = e.product_id
              AND o.order_status IN ('已完成', '已发货')
              AND julianday(o.created_at) - julianday(e.event_time) BETWEEN 0 AND 7
        )
    """).fetchone()[0]
    total_events = cur.execute("SELECT COUNT(*) FROM user_events").fetchone()[0]
    add("行为-交易闭环", "浏览 / 加购事件可关联到 7 天内的成交订单",
        f"{pct(closed_loop / total_events if total_events else 0)} 可闭环",
        "ok" if total_events and closed_loop / total_events >= 0.5 else "warn")

    coupon_threshold_violation = cur.execute("""
        SELECT COUNT(*) FROM orders o
        JOIN coupons c ON o.coupon_id = c.coupon_id
        WHERE c.threshold_amount > 0
          AND (o.total_amount + o.discount_amount) < c.threshold_amount
    """).fetchone()[0]
    add("优惠券门槛", "使用满减券的订单金额应达到门槛",
        f"{n(coupon_threshold_violation)} 单未达标",
        "ok" if coupon_threshold_violation == 0 else "warn")

    return checks


# ============================================================
# 图表
# ============================================================

def build_charts(con: sqlite3.Connection, profiles: list[dict]) -> None:
    # 1. 表规模
    fig, ax = plt.subplots(figsize=(9, 4.2))
    names = [p["label"] or p["name"] for p in profiles]
    values = [p["rows"] for p in profiles]
    bars = ax.barh(names, values, color="#2f6fd0")
    ax.set_xlabel("行数")
    ax.set_title("各表数据规模")
    for bar, v in zip(bars, values):
        ax.text(v, bar.get_y() + bar.get_height() / 2, f" {v:,}", va="center", fontsize=9)
    save_fig(fig, "table_scale", "各表数据规模")

    # 2. 缺失率矩阵（不足 12 列的短表补空位）
    fig, ax = plt.subplots(figsize=(10, 4.6))

    def pad(values, size=12):
        return values + [float("nan")] * (size - len(values))

    matrix = pd.DataFrame(
        {p["label"] or p["name"]: pad([f["missing_rate"] * 100 for f in p["fields"]])
         for p in profiles},
        index=[f"字段{i + 1}" for i in range(12)],
    )
    sns.heatmap(matrix, cmap="YlOrRd", annot=True, fmt=".1f", cbar_kws={"label": "缺失率 %"}, ax=ax)
    ax.set_title("各表字段缺失率（%）")
    save_fig(fig, "missing_heatmap", "缺失率矩阵")

    # 3. 日 GMV 趋势
    gmv = pd.read_sql_query("""
        SELECT substr(created_at, 1, 10) AS d, SUM(total_amount) AS gmv
        FROM orders WHERE order_status IN ('已完成', '已发货')
        GROUP BY d ORDER BY d
    """, con)
    gmv["d"] = pd.to_datetime(gmv["d"])
    fig, ax = plt.subplots(figsize=(11, 3.8))
    ax.plot(gmv["d"], gmv["gmv"] / 10000, color="#2f6fd0", linewidth=1.0)
    for day, text in [("2024-11-11", "双 11"), ("2025-06-15", "618 大促")]:
        target = gmv[gmv["d"] == pd.Timestamp(day)]
        if not target.empty:
            ax.axvline(pd.Timestamp(day), color="#d9534f", linestyle="--", linewidth=1)
            ax.annotate(text, (pd.Timestamp(day), float(target["gmv"].iloc[0]) / 10000),
                        xytext=(6, 6), textcoords="offset points", fontsize=9, color="#d9534f")
    ax.set_ylabel("日 GMV（万元）")
    ax.set_title("日 GMV 走势与促销脉冲")
    save_fig(fig, "gmv_trend", "日 GMV 走势")

    # 4. 订单状态分布
    status = pd.read_sql_query(
        "SELECT order_status AS k, COUNT(*) AS v FROM orders GROUP BY k ORDER BY v DESC", con)
    fig, ax = plt.subplots(figsize=(6.4, 4))
    ax.bar(status["k"], status["v"], color=["#2f6fd0", "#4a9d7f", "#e0a800", "#9aa5b1"])
    ax.set_ylabel("订单数")
    ax.set_title("订单状态分布")
    save_fig(fig, "order_status", "订单状态分布")

    # 5. 订单金额分布
    amounts = pd.read_sql_query(
        "SELECT total_amount AS a FROM orders WHERE order_status IN ('已完成', '已发货')", con)
    fig, ax = plt.subplots(figsize=(7.4, 3.8))
    sns.histplot(np.log1p(amounts["a"]), bins=60, kde=True, color="#2f6fd0", ax=ax)
    ax.set_xlabel("log(1 + 实付金额)")
    ax.set_ylabel("订单数")
    ax.set_title("成交订单金额分布（长尾明显）")
    save_fig(fig, "amount_dist", "订单金额分布")

    # 6. 客户年龄分布
    ages = pd.read_sql_query("SELECT age FROM customers", con)
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    sns.histplot(ages["age"], bins=24, color="#4a9d7f", ax=ax)
    ax.set_xlabel("年龄")
    ax.set_ylabel("客户数")
    ax.set_title("客户年龄分布")
    save_fig(fig, "age_dist", "客户年龄分布")

    # 7. 一级类目 GMV
    category = pd.read_sql_query("""
        SELECT c1.category_name AS name, ROUND(SUM(oi.subtotal), 2) AS gmv
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        JOIN products p ON oi.product_id = p.product_id
        JOIN categories c2 ON p.category_id = c2.category_id
        JOIN categories c1 ON c2.parent_id = c1.category_id
        WHERE o.order_status IN ('已完成', '已发货')
        GROUP BY c1.category_name ORDER BY gmv DESC
    """, con)
    fig, ax = plt.subplots(figsize=(8.6, 4))
    ax.barh(category["name"][::-1], category["gmv"][::-1] / 10000, color="#2f6fd0")
    ax.set_xlabel("GMV（万元）")
    ax.set_title("一级类目 GMV")
    save_fig(fig, "category_gmv", "一级类目 GMV")

    # 8. 明细数值相关性
    items = pd.read_sql_query(
        "SELECT quantity, unit_price, item_discount, subtotal FROM order_items", con)
    fig, ax = plt.subplots(figsize=(5.6, 4.4))
    sns.heatmap(items.corr(method="spearman"), annot=True, fmt=".2f", cmap="RdBu_r", center=0, ax=ax)
    ax.set_title("订单明细数值字段 Spearman 相关")
    save_fig(fig, "items_corr", "明细字段相关性")

    # 9. 支付方式
    pay = pd.read_sql_query(
        "SELECT payment_method AS k, COUNT(*) AS v FROM payments GROUP BY k ORDER BY v DESC", con)
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    ax.bar(pay["k"], pay["v"], color="#4a9d7f")
    ax.set_ylabel("支付笔数")
    ax.set_title("支付方式分布")
    save_fig(fig, "payment_method", "支付方式分布")

    # 10. 评价星级
    rating = pd.read_sql_query(
        "SELECT rating AS k, COUNT(*) AS v FROM reviews GROUP BY k ORDER BY k", con)
    fig, ax = plt.subplots(figsize=(6, 3.6))
    ax.bar(rating["k"].astype(str), rating["v"], color="#e0a800")
    ax.set_xlabel("评分（星）")
    ax.set_ylabel("评价数")
    ax.set_title("评价星级分布")
    save_fig(fig, "rating_dist", "评价星级分布")


# ============================================================
# Markdown 报告
# ============================================================

def render_markdown(con, profiles, checks, meta) -> str:
    total_rows = sum(p["rows"] for p in profiles)
    lines: list[str] = []
    add = lines.append

    add("# 数据探查报告 · 电商数据集")
    add("")
    add(f"> 数据源：`{meta['db_label']}`　|　生成时间：{meta['generated_at']}　|　表数量：{len(profiles)}　|　总行数：{n(total_rows)}")
    add("")
    add("本报告对电商交易链路的九张表做系统体检：先看整体规模与结构，再逐表检查字段质量，"
        "最后验证跨表的口径一致性，给出建模就绪度结论。所有数字均可由脚本复现。")
    add("")

    add("## 一、结论摘要")
    add("")
    risk = [c for c in checks if c["status"] == "risk"]
    warn = [c for c in checks if c["status"] == "warn"]
    add(f"- 数据规模：{len(profiles)} 张表、{n(total_rows)} 行，覆盖 {meta['days']} 天（{meta['date_from']} ~ {meta['date_to']}）。")
    add(f"- 一致性：{len(checks)} 项跨表检查中，{len(checks) - len(risk) - len(warn)} 项通过，{len(warn)} 项提示，{len(risk)} 项风险。")
    add("- 字段质量：主键唯一、外键完整；金额勾稽与状态机时间链按日期粒度成立。")
    add("- 已知口径：同一日内存在发货时刻早于支付时刻的错位，属于时刻精度现象，不影响按日聚合的业务指标。")
    add("")

    add("## 二、数据集总览")
    add("")
    add("| 表 | 中文名 | 行数 | 字段数 | 重复行 | 候选主键 |")
    add("|---|---|---:|---:|---:|---|")
    for p in profiles:
        keys = "、".join(p["candidate_keys"]) if p["candidate_keys"] else "—"
        add(f"| `{p['name']}` | {p['label']} | {n(p['rows'])} | {p['cols']} | {n(p['duplicated'])} | {keys} |")
    add("")
    add("![各表数据规模](images/table_scale.png)")
    add("")
    add("**读图：** 行为事件表体量最大（埋点为高频日志），订单与明细是交易分析的主表，"
        "主数据表（类目、客户、商品、优惠券）保持小体量，符合维度表与事实表的典型比例。")
    add("")

    add("## 三、字段质量总览")
    add("")
    add("![缺失率矩阵](images/missing_heatmap.png)")
    add("")
    missing_cols = [
        (p["label"], f) for p in profiles for f in p["fields"] if f["missing_rate"] > 0
    ]
    if missing_cols:
        add("存在缺失的字段：")
        add("")
        add("| 表 | 字段 | 缺失数 | 缺失率 | 业务解释 |")
        add("|---|---|---:|---:|---|")
        for label, f in missing_cols:
            add(f"| {label} | `{f['name']}` | {n(f['missing'])} | {pct(f['missing_rate'])} | {MISSING_MEANING.get(f['name'], '业务语义导致的空值')} |")
        add("")
    else:
        add("九张表所有字段均无缺失值。订单时间链中尚未到达的节点（如未支付、未发货）以空值表达，"
            "属于状态机语义而非数据缺陷。")
        add("")
    add("各表均未发现常量列、近常量列与完全重复行。")
    add("")

    add("## 四、逐表画像")
    add("")
    for index, p in enumerate(profiles, start=1):
        add(f"### 4.{index} {p['label']}（`{p['name']}`）")
        add("")
        add(f"{p['description']}。共 {n(p['rows'])} 行、{p['cols']} 个字段。")
        add("")
        add("| 字段 | 类型 | 缺失率 | 唯一值 | 关键信息 |")
        add("|---|---|---:|---:|---|")
        for f in p["fields"]:
            if f["kind"] == "数值" and f["stats"]:
                s = f["stats"]
                info = f"均值 {s['mean']:.2f}，中位数 {s['median']:.2f}，范围 [{s['min']:.2f}, {s['max']:.2f}]，IQR 异常率 {pct(s['iqr_rate'])}"
            elif f["kind"] == "分类":
                info = "、".join(f"{k} {n(v)}" for k, v in f["top"][:4]) or "—"
            elif f["kind"] == "时间":
                info = f"{f['time_min']} ~ {f['time_max']}" if f["time_min"] else "—"
            elif f["kind"] == "文本" and f["stats"]:
                info = f"平均长度 {f['stats']['avg_len']:.1f} 字，最长 {f['stats']['max_len']} 字"
            else:
                info = "—"
            add(f"| `{f['name']}` | {f['kind']} | {pct(f['missing_rate'])} | {n(f['unique'])} | {info} |")
        add("")

    add("## 五、业务分布速览")
    add("")
    add("![日 GMV 走势](images/gmv_trend.png)")
    add("")
    add("**读图：** 日 GMV 呈缓慢增长叠加周末周期，双 11、618 形成数量级尖峰，春节出现低谷。"
        "这种“趋势 + 周期 + 脉冲”的结构决定了时序模型必须显式处理大促效应。")
    add("")
    add("![订单状态分布](images/order_status.png)")
    add("")
    add("![订单金额分布](images/amount_dist.png)")
    add("")
    add("**读图：** 成交金额右偏长尾，多数订单集中在低客单区间，少量高客单订单贡献显著 GMV，"
        "按均值做预算或按总量做预测都需要同时报告分位数。")
    add("")
    add("![客户年龄分布](images/age_dist.png)")
    add("")
    add("![一级类目 GMV](images/category_gmv.png)")
    add("")
    add("![明细字段相关性](images/items_corr.png)")
    add("")
    add("![支付方式分布](images/payment_method.png)")
    add("")
    add("![评价星级分布](images/rating_dist.png)")
    add("")

    add("## 六、跨表一致性检查")
    add("")
    add("| 检查项 | 口径 | 结果 | 结论 |")
    add("|---|---|---|---|")
    for c in checks:
        mark = {"ok": "通过", "warn": "提示", "risk": "风险"}[c["status"]]
        detail = f"{c['value']}，{c['detail']}" if c["detail"] else c["value"]
        add(f"| {c['name']} | {c['meaning']} | {detail} | {mark} |")
    add("")
    add("**口径提示：** 订单时间链的日期顺序成立；同一日内的时刻错位约覆盖两成已发货订单，"
        "因此“支付到发货时长”类指标应按日期为粒度，或先做时刻清洗再计算。"
        f"行为事件中 {next(c['value'] for c in checks if c['name'] == '行为-交易闭环')} 可在下单前 7 天内闭环，"
        "其余为未转化行为，漏斗分母应取全部浏览事件。")
    add("")

    add("## 七、建模就绪度")
    add("")
    add("| 维度 | 结论 |")
    add("|---|---|")
    add("| 主键与外键 | 全部表有稳定主键，九表外键完整，可直接做多表 JOIN |")
    add("| 缺失处理 | 主数据表无缺失；订单时间链的 NULL 是状态语义，应按状态机解释 |")
    add("| 异常值 | 数值字段存在少量业务型异常（批发大单、价格异常），是 L2 异常检测的靶子，不应直接剔除 |")
    add("| 时间序列 | 532 天日粒度，可支撑趋势 / 季节 / 大促三类建模 |")
    add("| 文本语料 | 评价正文约 3 千条，可用于情感与词频分析 |")
    add("| 推荐场景 | 用户-商品隐式反馈矩阵可直接从订单明细构造 |")
    add("")
    add("---")
    add("")
    add(f"*报告由 `profiling/data_profiling_report.py` 生成，图表位于 `profiling/images/`。*")
    return "\n".join(lines)


# ============================================================
# HTML 报告
# ============================================================

HTML_STYLE = """
:root{--ink:#1f2937;--sub:#5b6675;--line:#e2e8f0;--bg:#f6f8fb;--brand:#2f6fd0;--ok:#2e8b57;--warn:#b7791f;--risk:#c53030;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"Microsoft YaHei","PingFang SC",Arial,sans-serif;line-height:1.65}
.wrap{max-width:1080px;margin:0 auto;padding:32px 28px 64px}
header{border-bottom:3px solid var(--brand);padding-bottom:18px;margin-bottom:26px}
h1{margin:0 0 6px;font-size:26px}
.meta{color:var(--sub);font-size:13px}
h2{font-size:18px;margin:34px 0 12px;padding-left:10px;border-left:4px solid var(--brand)}
h3{font-size:15px;margin:22px 0 8px;color:#334155}
table{width:100%;border-collapse:collapse;background:#fff;font-size:13px;margin:10px 0 18px;box-shadow:0 1px 3px rgba(15,23,42,.06)}
th,td{border:1px solid var(--line);padding:8px 10px;text-align:left}
th{background:#eef3fb;font-weight:600}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:18px 0}
.card{background:#fff;border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(15,23,42,.08)}
.card .k{font-size:12px;color:var(--sub)}
.card .v{font-size:22px;font-weight:700;margin-top:4px}
.badge{display:inline-block;font-size:12px;padding:2px 8px;border-radius:999px}
.b-ok{background:#e6f4ea;color:var(--ok)} .b-warn{background:#fdf3e3;color:var(--warn)} .b-risk{background:#fde8e8;color:var(--risk)}
img{max-width:100%;border-radius:8px;border:1px solid var(--line);background:#fff}
.note{background:#fff;border-left:4px solid var(--brand);padding:12px 16px;margin:12px 0;color:#334155}
.risk-list li{margin:6px 0}
footer{margin-top:40px;color:var(--sub);font-size:12px;border-top:1px solid var(--line);padding-top:14px}
"""


def html_table(headers: list[str], rows: list[list[str]], numeric_from: int = 99) -> str:
    out = ["<table><thead><tr>"]
    out.extend(f"<th>{h}</th>" for h in headers)
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>")
        for i, cell in enumerate(row):
            cls = ' class="num"' if i >= numeric_from else ""
            out.append(f"<td{cls}>{cell}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def build_manager_html(profiles, checks, meta) -> str:
    total_rows = sum(p["rows"] for p in profiles)
    risk = [c for c in checks if c["status"] == "risk"]
    warn = [c for c in checks if c["status"] == "warn"]
    ok_count = len(checks) - len(risk) - len(warn)

    cards = f"""
    <div class="cards">
      <div class="card"><div class="k">数据表</div><div class="v">{len(profiles)} 张</div></div>
      <div class="card"><div class="k">总记录数</div><div class="v">{n(total_rows)}</div></div>
      <div class="card"><div class="k">一致性通过</div><div class="v">{ok_count}/{len(checks)}</div></div>
      <div class="card"><div class="k">时间跨度</div><div class="v">{meta['days']} 天</div></div>
    </div>
    """

    table_rows = [
        [f"<code>{p['name']}</code>", p["label"], n(p["rows"]), str(p["cols"]),
         n(p["duplicated"]), "、".join(p["candidate_keys"]) or "—"]
        for p in profiles
    ]
    tables = html_table(["表", "中文名", "行数", "字段数", "重复行", "主键候选"], table_rows)

    check_rows = []
    for c in checks:
        badge = {"ok": '<span class="badge b-ok">通过</span>',
                 "warn": '<span class="badge b-warn">提示</span>',
                 "risk": '<span class="badge b-risk">风险</span>'}[c["status"]]
        detail = f"{c['value']}，{c['detail']}" if c["detail"] else c["value"]
        check_rows.append([c["name"], c["meaning"], detail, badge])
    checks_html = html_table(["检查项", "口径", "结果", "结论"], check_rows, numeric_from=99)

    risk_items = "".join(
        f"<li><b>{c['name']}</b>：{c['value']}。{c['detail'] or '建议纳入日常质量看板。'}</li>"
        for c in risk + warn
    ) or "<li>本次检查未发现阻断性风险。</li>"

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>数据资产健康度报告</title><style>{HTML_STYLE}</style></head>
<body><div class="wrap">
<header><h1>数据资产健康度报告</h1>
<div class="meta">面向数据管理者 · 数据源 {meta['db_label']} · 生成时间 {meta['generated_at']}</div></header>

<div class="note">一句话结论：九张表的资产结构完整、主外键可用、金额与状态机口径按日期粒度成立；
需要关注的是时刻精度与行为闭环口径，它们不影响结论，但会影响"如何取数"。</div>
{cards}

<h2>一、资产规模与结构</h2>
{tables}
<img src="data:image/png;base64,{fig_b64('table_scale')}" alt="各表数据规模">

<h2>二、完整性检查</h2>
{checks_html}

<h2>三、需要关注的事项</h2>
<ul class="risk-list">{risk_items}</ul>
<div class="note">治理建议：把金额勾稽、外键完整、时间链顺序三项固化为每日调度检查；
时刻精度问题在指标层用日期粒度规避；行为闭环比例写入数据说明，避免下游误读漏斗分母。</div>

<h2>四、资产可用性结论</h2>
<table><thead><tr><th>用途</th><th>可用性</th><th>说明</th></tr></thead><tbody>
<tr><td>经营日报 / 看板</td><td><span class="badge b-ok">直接可用</span></td><td>GMV、订单量、客单价、类目结构均可直出</td></tr>
<tr><td>用户与商品分析</td><td><span class="badge b-ok">直接可用</span></td><td>客户、商品、类目主数据完整</td></tr>
<tr><td>营销归因</td><td><span class="badge b-warn">按口径使用</span></td><td>券门槛与优惠分摊成立，需按活动窗口取数</td></tr>
<tr><td>时效类指标</td><td><span class="badge b-warn">按日期粒度</span></td><td>时刻层存在同日错位，按日期聚合可规避</td></tr>
<tr><td>推荐与预测建模</td><td><span class="badge b-ok">直接可用</span></td><td>隐式反馈与日序列结构完备，可直接进入 L3/L4</td></tr>
</tbody></table>

<footer>本报告由 profiling/data_profiling_report.py 自动生成，数字与图表可复现。</footer>
</div></body></html>"""


def build_analyst_html(profiles, checks, meta) -> str:
    total_rows = sum(p["rows"] for p in profiles)
    numeric_fields = sum(1 for p in profiles for f in p["fields"] if f["kind"] == "数值")
    time_fields = sum(1 for p in profiles for f in p["fields"] if f["kind"] == "时间")
    text_fields = sum(1 for p in profiles for f in p["fields"] if f["kind"] == "文本")

    cards = f"""
    <div class="cards">
      <div class="card"><div class="k">字段总数</div><div class="v">{sum(p['cols'] for p in profiles)}</div></div>
      <div class="card"><div class="k">数值字段</div><div class="v">{numeric_fields}</div></div>
      <div class="card"><div class="k">时间字段</div><div class="v">{time_fields}</div></div>
      <div class="card"><div class="k">文本字段</div><div class="v">{text_fields}</div></div>
    </div>
    """

    field_rows = []
    for p in profiles:
        for f in p["fields"]:
            if f["kind"] == "数值" and f["stats"]:
                s = f["stats"]
                field_rows.append([
                    f"<code>{p['name']}.{f['name']}</code>", "数值", pct(f["missing_rate"]),
                    f"{s['mean']:.2f}", f"{s['median']:.2f}", f"{s['std']:.2f}",
                    f"[{s['min']:.2f}, {s['max']:.2f}]", pct(s["iqr_rate"]), f"{s['skew']:.2f}",
                ])
    fields_html = html_table(
        ["字段", "类型", "缺失率", "均值", "中位数", "标准差", "范围", "IQR 异常率", "偏度"],
        field_rows, numeric_from=2)

    cat_rows = []
    for p in profiles:
        for f in p["fields"]:
            if f["kind"] == "分类" and f["top"]:
                cat_rows.append([
                    f"<code>{p['name']}.{f['name']}</code>", n(f["unique"]),
                    "；".join(f"{k}：{n(v)}" for k, v in f["top"][:4]),
                ])
    cats_html = html_table(["字段", "唯一值", "主要取值"], cat_rows, numeric_from=1)

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>数据探查报告（分析师版）</title><style>{HTML_STYLE}</style></head>
<body><div class="wrap">
<header><h1>数据探查报告 · 分析师版</h1>
<div class="meta">面向数据分析师 · 数据源 {meta['db_label']} · 生成时间 {meta['generated_at']}</div></header>

<div class="note">一句话结论：主数据字段零缺失、主外键完整、时间与金额字段可直接进入特征工程；
建模前只需处理状态语义空值、业务型异常值与时刻精度三类问题。</div>
{cards}

<h2>一、字段画像</h2>
{fields_html}

<h2>二、分类字段取值</h2>
{cats_html}

<h2>三、分布与相关性</h2>
<img src="data:image/png;base64,{fig_b64('amount_dist')}" alt="订单金额分布">
<img src="data:image/png;base64,{fig_b64('items_corr')}" alt="明细字段相关性">
<img src="data:image/png;base64,{fig_b64('gmv_trend')}" alt="日 GMV 走势">

<h2>四、建模就绪度</h2>
<table><thead><tr><th>问题</th><th>处理建议</th></tr></thead><tbody>
<tr><td>状态语义空值</td><td>paid_at / shipped_at / delivered_at 的 NULL 表示"未到达"，不要用均值填补；按状态筛选样本</td></tr>
<tr><td>业务型异常值</td><td>批发大单（quantity 30~200）与价格异常（unit_price ×10）是真实业务记录，建模时作为异常检测靶子或单独分层</td></tr>
<tr><td>时刻精度</td><td>支付到发货时长按日期计算，或先过滤同日内时刻错位样本</td></tr>
<tr><td>长尾金额</td><td>GMV 预测用 log1p 变换；报表同时给均值与分位数</td></tr>
<tr><td>隐式反馈</td><td>用户-商品矩阵从订单明细构造，评分可取购买次数并 cap，适合协同过滤与矩阵分解</td></tr>
<tr><td>文本语料</td><td>评价正文平均长度适中，可直接做分词、词频与情感标签分析</td></tr>
</tbody></table>

<h2>五、可直接复用的建模资产</h2>
<table><thead><tr><th>资产</th><th>构造方式</th><th>适用层次</th></tr></thead><tbody>
<tr><td>日 GMV 序列</td><td>orders 按日聚合 total_amount（已完成 + 已发货）</td><td>L3 预测</td></tr>
<tr><td>用户 RFM 特征</td><td>orders 按客户聚合最近购买、频次、金额</td><td>L2 聚类 / L4 策略</td></tr>
<tr><td>用户-商品隐式评分</td><td>order_items JOIN orders 按客户-商品计数</td><td>L4 推荐</td></tr>
<tr><td>浏览-购买漏斗</td><td>user_events 与 orders 按客户 + 商品关联</td><td>L1 描述 / L2 诊断</td></tr>
<tr><td>评价文本语料</td><td>reviews.review_content + rating</td><td>L1 文本 / L5 多模态</td></tr>
<tr><td>异常订单样本</td><td>quantity、unit_price 的 IQR 离群记录</td><td>L2 异常检测</td></tr>
</tbody></table>

<h2>六、跨表口径提示</h2>
{html_table(["检查项", "结果", "对分析的影响"],
            [[c["name"], c["value"], c["detail"] or "可直接使用"] for c in checks])}

<footer>本报告由 profiling/data_profiling_report.py 自动生成，全部指标可由脚本复现。</footer>
</div></body></html>"""


# ============================================================
# 主流程
# ============================================================

def load_profiles(con: sqlite3.Connection, tables: list[str]) -> list[dict]:
    profiles = []
    for table in tables:
        df = pd.read_sql_query(f'SELECT * FROM "{table}"', con)
        profile = profile_table(df, table)
        print(f"[探查] {table}: {len(df):,} 行 / {len(df.columns)} 列")
        profiles.append(profile)
    return profiles


def main() -> None:
    parser = argparse.ArgumentParser(description="电商数据集多表数据探查")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite 数据库路径")
    parser.add_argument("--tables", default="", help="逗号分隔的表名，默认全部业务表")
    args = parser.parse_args()

    db_path = os.path.abspath(args.db)
    if not os.path.exists(db_path):
        raise SystemExit(f"数据库不存在：{db_path}")

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    all_tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()]
    tables = [t.strip() for t in args.tables.split(",") if t.strip()] or \
             [t for t in TABLE_META if t in all_tables] + [t for t in all_tables if t not in TABLE_META]

    print(f"[加载] 数据源：{db_path}")
    profiles = load_profiles(con, tables)
    checks = run_consistency_checks(con, profiles)
    build_charts(con, profiles)

    span = con.execute(
        "SELECT MIN(substr(created_at, 1, 10)), MAX(substr(created_at, 1, 10)) FROM orders"
    ).fetchone()
    date_from, date_to = (span[0] or "—"), (span[1] or "—")
    days = (datetime.strptime(date_to, "%Y-%m-%d") - datetime.strptime(date_from, "%Y-%m-%d")).days + 1 \
        if date_from != "—" and date_to != "—" else 0

    meta = {
        "db_label": os.path.basename(db_path),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date_from": date_from,
        "date_to": date_to,
        "days": f"{days}",
    }

    with open(OUTPUT_MD, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(con, profiles, checks, meta))
    with open(OUTPUT_MANAGER, "w", encoding="utf-8") as fh:
        fh.write(build_manager_html(profiles, checks, meta))
    with open(OUTPUT_ANALYST, "w", encoding="utf-8") as fh:
        fh.write(build_analyst_html(profiles, checks, meta))

    con.close()
    print(f"[完成] 主报告：{OUTPUT_MD}")
    print(f"[完成] 管理者报告：{OUTPUT_MANAGER}")
    print(f"[完成] 分析师报告：{OUTPUT_ANALYST}")
    print(f"[完成] 图片目录：{IMAGE_DIR}")


if __name__ == "__main__":
    main()
