#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电商分析数据集生成器（DataClerk 式确定性生成）

确定性机制：
  1. 显式随机源：全程只用一个 rng = random.Random(42)，不触碰全局 random
  2. 锚定"今天"：ANCHOR_TODAY = date(2025, 6, 15)，所有日期相对它生成
  3. 固定生成顺序与迭代顺序：类 -> 客户 -> 商品 -> 订单 -> 支付 -> 评价 -> 行为事件
  4. 金额一律 round(2)，避免浮点尾差

=> 同一代码在任何时间、任何机器上运行，产出字节级一致的 ecommerce.db。

用法：
  python generate_dataset.py            # 生成 ecommerce.db（已存在则拒绝覆盖）
  python generate_dataset.py --force    # 删除旧库重新生成
"""

import argparse
import bisect
import hashlib
import os
import random
import sqlite3
from datetime import date, datetime, time, timedelta

# ================== 确定性配置 ==================
SEED = 42
ANCHOR_TODAY = date(2025, 6, 15)          # 锁死的"今天"
START_DATE = date(2024, 1, 1)             # 业务数据起始日

N_CUSTOMERS = 3000
REVIEW_RATE = 0.35                        # 已签收订单的评价率
ANOMALY_BULK_RATE = 0.012                 # 批发型异常订单比例（数量异常）
ANOMALY_PRICE_RATE = 0.005                # 价格异常订单比例（单价×10）

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "ecommerce.db")
SCHEMA_PATH = os.path.join(SCRIPT_DIR, "schema.sql")


# ================== 基础词库（合成数据用，非业务数据） ==================
SURNAMES = list("王李张刘陈杨黄赵吴周徐孙马朱胡郭何罗高林郑梁谢宋唐许韩冯邓曹彭")
GIVEN_CHARS = list("伟芳娜敏静丽强磊军洋勇艳杰娟涛明超秀兰霞平刚桂英华玉梅浩宇欣怡子轩雨桐诗涵梓")

PROVINCES = [
    ("广东省", ["广州市", "深圳市", "东莞市"], 0.16),
    ("浙江省", ["杭州市", "宁波市", "温州市"], 0.13),
    ("江苏省", ["南京市", "苏州市", "无锡市"], 0.12),
    ("北京市", ["北京市"], 0.09),
    ("上海市", ["上海市"], 0.09),
    ("四川省", ["成都市", "绵阳市"], 0.09),
    ("湖北省", ["武汉市", "宜昌市"], 0.08),
    ("湖南省", ["长沙市", "株洲市"], 0.08),
    ("福建省", ["福州市", "厦门市"], 0.08),
    ("山东省", ["济南市", "青岛市"], 0.08),
]

# 一级类目 -> (二级类目列表, 品牌列表, 价格带)
CATEGORY_TREE = {
    "手机数码": (["手机", "耳机", "智能手表", "充电器"],
                 ["华为", "小米", "荣耀", "OPPO", "vivo"], (99, 6999)),
    "家用电器": (["冰箱", "洗衣机", "空调", "电饭煲"],
                 ["美的", "海尔", "格力", "苏泊尔"], (199, 8999)),
    "服装鞋帽": (["T恤", "牛仔裤", "运动鞋", "外套"],
                 ["李宁", "安踏", "森马", "以纯"], (59, 1299)),
    "美妆个护": (["面膜", "口红", "洗面奶", "洗发水"],
                 ["珀莱雅", "自然堂", "百雀羚", "完美日记"], (29, 599)),
    "食品饮料": (["坚果", "咖啡", "茶叶", "巧克力"],
                 ["三只松鼠", "良品铺子", "雀巢", "德芙"], (19, 399)),
    "母婴用品": (["奶粉", "纸尿裤", "玩具", "婴儿车"],
                 ["飞鹤", "帮宝适", "贝亲", "好孩子"], (39, 2999)),
}

MEMBER_LEVELS = [("普通", 0.60), ("白银", 0.25), ("黄金", 0.10), ("钻石", 0.05)]
CHANNELS = [("APP", 0.55), ("小程序", 0.25), ("网页", 0.15), ("线下", 0.05)]
PAY_METHODS = [("微信支付", 0.55), ("支付宝", 0.30), ("银行卡", 0.10), ("余额", 0.05)]
FREIGHT_OPTIONS = [6.0, 8.0, 10.0, 12.0]

REVIEW_TEMPLATES = {
    5: ["{p}质量很好，物流也快，非常满意", "第二次购买了，{p}一如既往地好", "性价比很高，{p}超出预期", "包装严实，{p}做工精细，推荐购买"],
    4: ["{p}整体不错，小瑕疵不影响使用", "质量可以，就是物流稍慢", "{p}还行，价格再优惠点就更好了", "基本满意，{p}符合描述"],
    3: ["{p}一般般，没有想象中好", "中规中矩，{p}凑活用", "做工一般，{p}这个价位能接受", "感觉一般，{p}有待改进"],
    2: ["{p}不太满意，与描述有差距", "质量堪忧，{p}用几天就出问题", "{p}失望，不会再买了", "客服态度可以，但{p}本身不行"],
    1: ["{p}质量太差，强烈要求退货", "完全是次品，{p}浪费钱", "极差体验，{p}与宣传严重不符", "踩雷了，{p}千万别买"],
}


# ================== 确定性辅助函数 ==================
def weighted_pick(rng, pairs):
    """pairs: [(item, weight), ...] 按权重选一个，纯 rng 流实现。"""
    total = sum(w for _, w in pairs)
    r = rng.random() * total
    acc = 0.0
    for item, w in pairs:
        acc += w
        if r < acc:
            return item
    return pairs[-1][0]


class WeightedPool:
    """大列表加权抽样：预计算累积权重，之后 O(log n) 一次 rng.random() 抽样。"""

    def __init__(self, items, weights):
        self.items = items
        self.cum = []
        acc = 0.0
        for w in weights:
            acc += w
            self.cum.append(acc)
        self.total = acc

    def pick(self, rng):
        return self.items[bisect.bisect_left(self.cum, rng.random() * self.total)]


def money(x):
    return round(float(x) + 1e-9, 2)


def dt_str(d, t):
    return "%s %s" % (d.isoformat(), t.strftime("%H:%M:%S"))


def rand_clock(rng):
    """下单时钟：向 10-12 点、20-22 点倾斜。"""
    hour_weights = [(h, 1.0) for h in range(24)]
    for h in (10, 11, 12, 20, 21, 22):
        hour_weights[h] = (h, 3.0)
    hour = weighted_pick(rng, hour_weights)
    return time(hour, rng.randrange(60), rng.randrange(60))


# ================== 各实体生成 ==================
def gen_categories():
    """两级类目：1-6 为一级，之后每个一级类目下 4 个二级。"""
    rows = []
    cid = 0
    for top, (subs, _, _) in CATEGORY_TREE.items():
        cid += 1
        top_id = cid
        rows.append((top_id, None, top, 1))
        for sub in subs:
            cid += 1
            rows.append((cid, top_id, sub, 2))
    return rows


def gen_customers(rng, provinces):
    province_pool = WeightedPool(provinces, [w for _, _, w in provinces])
    rows = []
    reg_start = date(2023, 1, 1).toordinal()
    reg_end = date(2025, 3, 1).toordinal()
    for cid in range(1, N_CUSTOMERS + 1):
        name = rng.choice(SURNAMES) + "".join(rng.choice(GIVEN_CHARS) for _ in range(rng.randint(1, 2)))
        gender = "男" if rng.random() < 0.52 else "女"
        age = int(rng.triangular(18, 65, 32))
        prov, cities, _ = province_pool.pick(rng)
        city = cities[rng.randrange(len(cities))]
        register_date = date.fromordinal(rng.randint(reg_start, reg_end)).isoformat()
        member_level = weighted_pick(rng, MEMBER_LEVELS)
        activity = round(rng.betavariate(0.7, 2.5), 4)
        rows.append((cid, name, gender, age, prov, city, register_date, member_level, activity))
    return rows


def gen_products(rng, categories):
    rows = []
    pid = 0
    leaf_cats = [c for c in categories if c[3] == 2]
    created_start = date(2023, 6, 1).toordinal()
    created_end = date(2024, 12, 31).toordinal()
    for cat_id, parent_id, cat_name, _level in leaf_cats:
        top_name = categories[parent_id - 1][2]
        _subs, brands, (p_lo, p_hi) = CATEGORY_TREE[top_name]
        for _ in range(25):  # 每个二级类目 25 个商品
            pid += 1
            brand = rng.choice(brands)
            model = "%s%d" % (chr(65 + rng.randrange(26)), rng.randint(100, 999))
            product_name = "%s%s%s" % (brand, cat_name, model)
            list_price = money(rng.uniform(p_lo, p_hi))
            cost = money(list_price * rng.uniform(0.45, 0.70))
            stock = rng.randint(0, 500)
            status = "在售" if rng.random() < 0.95 else "下架"
            created_date = date.fromordinal(rng.randint(created_start, created_end)).isoformat()
            popularity = round(rng.betavariate(0.6, 3.0), 4)
            quality = round(rng.uniform(3.5, 5.0), 2)
            rows.append((pid, cat_id, product_name, brand, list_price, cost, stock,
                         status, created_date, popularity, quality))
    return rows


def gen_coupons():
    """券规则手工定义（不消耗 rng），有效期覆盖全年/618/双11 三类。"""
    full = ("2024-01-01", "2025-06-15")
    d11 = ("2024-11-01", "2024-11-15")
    f618 = ("2025-05-25", "2025-06-20")
    return [
        (1, "满99减10",   "满减",   99.0,  10.0,  *full),
        (2, "满199减20",  "满减",  199.0,  20.0,  *full),
        (3, "满399减50",  "满减",  399.0,  50.0,  *full),
        (4, "满999减150", "满减",  999.0, 150.0,  *d11),
        (5, "满299打9折", "折扣",  299.0,  0.90,  *full),
        (6, "无门槛减10", "无门槛",  0.0,  10.0,  *f618),
        (7, "全场95折",   "折扣",    0.0,  0.95,  *d11),
        (8, "满599减80",  "满减",  599.0,  80.0,  *f618),
    ]


def daily_order_count(rng, d):
    """每日订单量：基础量 + 周末效应 + 月度增长 + 大促/春节波动。"""
    n = 26.0
    if d.weekday() >= 5:
        n += 8.0
    n += (d.year - 2024) * 12 + d.month * 0.4           # 缓慢增长趋势
    if (d.month == 11 and 8 <= d.day <= 14) or (d.month == 6 and 1 <= d.day <= 18):
        n *= 2.4                                         # 双11 / 618
    if (d.month == 2 and 8 <= d.day <= 16 and d.year == 2024) or \
       (d.month == 1 and 27 <= d.day <= 31 and d.year == 2025) or \
       (d.month == 2 and 1 <= d.day <= 4 and d.year == 2025):
        n *= 0.4                                         # 春节低谷
    return max(1, int(rng.gauss(n, n * 0.12)))


def gen_orders(rng, customers, products, coupons):
    """订单 + 明细，一次遍历完成，返回 (orders, order_items)。"""
    customer_pool = WeightedPool(customers, [c[8] for c in customers])   # activity_score
    product_pool = WeightedPool(products, [p[9] for p in products])      # popularity

    orders, items = [], []
    oid, iid = 0, 0
    day = START_DATE
    while day <= ANCHOR_TODAY:
        for _ in range(daily_order_count(rng, day)):
            oid += 1
            cust = customer_pool.pick(rng)

            # 近期订单更可能处于"已发货/待付款"
            if day >= ANCHOR_TODAY - timedelta(days=5):
                status = weighted_pick(rng, [("已完成", 0.25), ("已发货", 0.40),
                                             ("待付款", 0.30), ("已取消", 0.05)])
            else:
                status = weighted_pick(rng, [("已完成", 0.90), ("已发货", 0.03),
                                             ("待付款", 0.015), ("已取消", 0.055)])
            channel = weighted_pick(rng, CHANNELS)
            created_t = rand_clock(rng)
            created_at = dt_str(day, created_t)

            # ---- 明细行 ----
            n_items = weighted_pick(rng, [(1, 0.45), (2, 0.30), (3, 0.17), (4, 0.08)])
            chosen = []
            for _ in range(n_items):
                prod = product_pool.pick(rng)
                if prod[0] not in [p[0] for p in chosen]:
                    chosen.append(prod)
            raw_rows = []
            for prod in chosen:
                qty = weighted_pick(rng, [(1, 0.55), (2, 0.30), (3, 0.15)])
                unit_price = money(prod[4] * rng.uniform(0.85, 1.0))     # 促销浮动
                raw_rows.append([prod[0], qty, unit_price])

            # ---- 异常注入（确定性）：批发数量 / 单价异常 ----
            r_anom = rng.random()
            if r_anom < ANOMALY_BULK_RATE:
                raw_rows[0][1] = rng.randint(30, 200)
            elif r_anom < ANOMALY_BULK_RATE + ANOMALY_PRICE_RATE:
                raw_rows[0][2] = money(raw_rows[0][2] * 10)

            subtotal_sum = money(sum(q * u for _, q, u in raw_rows))

            # ---- 优惠券 ----
            coupon_id, discount = None, 0.0
            if status != "待付款" and rng.random() < 0.22:
                day_s = day.isoformat()
                eligible = [c for c in coupons
                            if c[5] <= day_s <= c[6] and subtotal_sum >= c[3]]
                if eligible:
                    cp = eligible[rng.randrange(len(eligible))]
                    coupon_id = cp[0]
                    if cp[2] == "折扣":
                        discount = money(subtotal_sum * (1 - cp[4]))
                    else:
                        discount = money(min(cp[4], subtotal_sum))

            freight = 0.0 if (subtotal_sum - discount) >= 99 else rng.choice(FREIGHT_OPTIONS)
            total = money(subtotal_sum - discount + freight)

            # ---- 状态时间链 ----
            paid_at = shipped_at = delivered_at = None
            if status != "待付款":
                paid_at = dt_str(day, time(created_t.hour,
                                           min(59, created_t.minute + rng.randint(1, 25)),
                                           created_t.second))
            if status in ("已发货", "已完成"):
                ship_day = day + timedelta(hours=rng.randint(6, 48))
                shipped_at = dt_str(ship_day, rand_clock(rng))
            if status == "已完成":
                base = datetime.strptime(shipped_at, "%Y-%m-%d %H:%M:%S")
                delivered_at = dt_str((base + timedelta(days=rng.randint(1, 5))).date(),
                                      rand_clock(rng))

            orders.append((oid, cust[0], coupon_id, status, channel, created_at,
                           paid_at, shipped_at, delivered_at, freight, discount, total))

            # ---- 明细落库（优惠按比例分摊，末行兜底保证合计一致） ----
            remaining = discount
            for idx, (pid, qty, unit) in enumerate(raw_rows):
                iid += 1
                row_sum = money(qty * unit)
                if idx < len(raw_rows) - 1 and subtotal_sum > 0:
                    d_share = money(discount * row_sum / subtotal_sum)
                    remaining = money(remaining - d_share)
                else:
                    d_share = remaining
                items.append((iid, oid, pid, qty, unit, d_share,
                              money(row_sum - d_share)))
        day += timedelta(days=1)
    return orders, items


def gen_payments(rng, orders):
    rows = []
    pid = 0
    for o in orders:
        if o[6] is None:          # 未支付
            continue
        pid += 1
        method = weighted_pick(rng, PAY_METHODS)
        pstatus = weighted_pick(rng, [("成功", 0.965), ("已退款", 0.025), ("失败", 0.01)])
        rows.append((pid, o[0], method, o[11], o[6], pstatus))
    return rows


def gen_reviews(rng, orders, items, products):
    quality_map = {p[0]: p[10] for p in products}
    order_items = {}
    for it in items:
        order_items.setdefault(it[1], []).append(it)
    rows = []
    rid = 0
    for o in orders:
        if o[3] != "已完成" or rng.random() >= REVIEW_RATE:
            continue
        its = order_items.get(o[0])
        if not its:
            continue
        it = its[rng.randrange(len(its))]
        rating = int(round(rng.gauss(quality_map[it[2]], 0.8)))
        rating = max(1, min(5, rating))
        tpl = rng.choice(REVIEW_TEMPLATES[rating])
        prod_name = "这件商品"  # 模板占位，避免名称过长
        content = tpl.format(p=prod_name)
        base = datetime.strptime(o[8], "%Y-%m-%d %H:%M:%S")
        created = dt_str((base + timedelta(days=rng.randint(1, 7))).date(), rand_clock(rng))
        rid += 1
        rows.append((rid, o[0], it[2], o[1], rating, content, created))
    return rows


def gen_events(rng, orders, items, products):
    """下单前的浏览/加购行为：每单 2-6 个事件，时间前移到下单前 7 天内。"""
    product_pool = WeightedPool(products, [p[9] for p in products])
    order_items = {}
    for it in items:
        order_items.setdefault(it[1], []).append(it)
    rows = []
    eid = 0
    for o in orders:
        if o[6] is None:          # 只给已支付订单配行为轨迹
            continue
        created = datetime.strptime(o[5], "%Y-%m-%d %H:%M:%S")
        bought = [it[2] for it in order_items.get(o[0], [])]
        for _ in range(rng.randint(2, 6)):
            eid += 1
            if bought and rng.random() < 0.6:
                pid = bought[rng.randrange(len(bought))]
            else:
                pid = product_pool.pick(rng)[0]
            etype = "view" if rng.random() < 0.75 else "cart"
            etime = created - timedelta(hours=rng.randint(1, 168))
            rows.append((eid, o[1], pid, etype,
                         etime.strftime("%Y-%m-%d %H:%M:%S")))
    return rows


# ================== 落库 ==================
def build_db(db_path):
    rng = random.Random(SEED)     # 全程唯一的显式随机源

    categories = gen_categories()
    customers = gen_customers(rng, PROVINCES)
    products = gen_products(rng, categories)
    coupons = gen_coupons()
    orders, items = gen_orders(rng, customers, products, coupons)
    payments = gen_payments(rng, orders)
    reviews = gen_reviews(rng, orders, items, products)
    events = gen_events(rng, orders, items, products)

    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema_sql)
        conn.executemany("INSERT INTO categories VALUES (?,?,?,?)", categories)
        conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?,?,?,?)", customers)
        conn.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?)", products)
        conn.executemany("INSERT INTO coupons VALUES (?,?,?,?,?,?,?)", coupons)
        conn.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", orders)
        conn.executemany("INSERT INTO order_items VALUES (?,?,?,?,?,?,?)", items)
        conn.executemany("INSERT INTO payments VALUES (?,?,?,?,?,?)", payments)
        conn.executemany("INSERT INTO reviews VALUES (?,?,?,?,?,?,?)", reviews)
        conn.executemany("INSERT INTO user_events VALUES (?,?,?,?,?)", events)
        conn.commit()

        counts = {}
        for t in ("categories", "customers", "products", "coupons", "orders",
                  "order_items", "payments", "reviews", "user_events"):
            counts[t] = conn.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
    finally:
        conn.close()
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="覆盖已存在的 ecommerce.db")
    args = ap.parse_args()

    if os.path.exists(DB_PATH):
        if not args.force:
            raise SystemExit("ecommerce.db 已存在，加 --force 重新生成")
        os.remove(DB_PATH)

    counts = build_db(DB_PATH)

    with open(DB_PATH, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()

    print("生成完成: %s" % DB_PATH)
    for t, n in counts.items():
        print("  %-12s %8d 行" % (t, n))
    print("SHA256: %s" % digest)


if __name__ == "__main__":
    main()
