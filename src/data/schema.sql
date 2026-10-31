-- ============================================================================
-- 电商分析数据集 DDL（DataClerk 式确定性生成，SQLite 方言）
-- 生成方式：python generate_dataset.py（种子固定 42，锚定日期 2025-06-15，
--           同一代码在任何机器上产出字节级一致的 ecommerce.db）
-- 说明：SQLite 不支持 COMMENT 关键字，字段注释以行内注释形式给出。
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- 类目表：两级类目树（parent_id 为 NULL 表示一级类目）
-- ----------------------------------------------------------------------------
CREATE TABLE categories (
    category_id   INTEGER PRIMARY KEY,          -- 类目ID
    parent_id     INTEGER REFERENCES categories(category_id),  -- 父类目ID，一级类目为NULL
    category_name TEXT NOT NULL,                -- 类目名称，如"手机数码/手机"
    level         INTEGER NOT NULL              -- 层级：1=一级类目，2=二级类目
);

-- ----------------------------------------------------------------------------
-- 客户表：注册会员主数据
-- ----------------------------------------------------------------------------
CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,          -- 客户ID
    customer_name TEXT NOT NULL,                -- 客户姓名（脱敏合成）
    gender        TEXT NOT NULL,                -- 性别：男 / 女
    age           INTEGER NOT NULL,             -- 年龄（18-65）
    province      TEXT NOT NULL,                -- 省份，如"广东省"
    city          TEXT NOT NULL,                -- 城市，如"深圳市"
    register_date TEXT NOT NULL,                -- 注册日期 YYYY-MM-DD
    member_level  TEXT NOT NULL,                -- 会员等级：普通/白银/黄金/钻石
    activity_score REAL NOT NULL                -- 活跃度评分（0-1，越高下单越频繁，生成参数非业务字段）
);

-- ----------------------------------------------------------------------------
-- 商品表：SPU 级商品主数据
-- ----------------------------------------------------------------------------
CREATE TABLE products (
    product_id    INTEGER PRIMARY KEY,          -- 商品ID
    category_id   INTEGER NOT NULL REFERENCES categories(category_id),  -- 所属二级类目ID
    product_name  TEXT NOT NULL,                -- 商品名称（品牌+品类词+型号）
    brand         TEXT NOT NULL,                -- 品牌
    list_price    REAL NOT NULL,                -- 标价（元）
    cost          REAL NOT NULL,                -- 成本价（元），毛利率分析用
    stock         INTEGER NOT NULL,             -- 当前库存件数
    status        TEXT NOT NULL,                -- 上架状态：在售 / 下架
    created_date  TEXT NOT NULL,                -- 上架日期 YYYY-MM-DD
    popularity    REAL NOT NULL,                -- 受欢迎度（0-1，生成参数非业务字段）
    quality_score REAL NOT NULL                 -- 质量评分（3.5-5.0，影响评价分布，生成参数）
);

-- ----------------------------------------------------------------------------
-- 优惠券表：营销券规则
-- ----------------------------------------------------------------------------
CREATE TABLE coupons (
    coupon_id       INTEGER PRIMARY KEY,        -- 券ID
    coupon_name     TEXT NOT NULL,              -- 券名称，如"满199减20"
    coupon_type     TEXT NOT NULL,              -- 券类型：满减 / 折扣 / 无门槛
    threshold_amount REAL NOT NULL,             -- 使用门槛金额（元），无门槛为0
    discount_value  REAL NOT NULL,              -- 优惠力度：满减=减免金额；折扣=折扣率(如0.9)
    valid_from      TEXT NOT NULL,              -- 生效日期 YYYY-MM-DD
    valid_to        TEXT NOT NULL               -- 失效日期 YYYY-MM-DD
);

-- ----------------------------------------------------------------------------
-- 订单表：订单主表（一单可含多商品，明细见 order_items）
-- ----------------------------------------------------------------------------
CREATE TABLE orders (
    order_id        INTEGER PRIMARY KEY,        -- 订单ID
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),  -- 下单客户ID
    coupon_id       INTEGER REFERENCES coupons(coupon_id),               -- 使用的券ID，未用券为NULL
    order_status    TEXT NOT NULL,              -- 订单状态：已完成/已发货/待付款/已取消
    channel         TEXT NOT NULL,              -- 下单渠道：APP/小程序/网页/线下
    created_at      TEXT NOT NULL,              -- 下单时间 YYYY-MM-DD HH:MM:SS
    paid_at         TEXT,                       -- 支付时间，未支付为NULL
    shipped_at      TEXT,                       -- 发货时间，未发货为NULL
    delivered_at    TEXT,                       -- 签收时间，未签收为NULL
    freight_amount  REAL NOT NULL,              -- 运费（元），满99免运费
    discount_amount REAL NOT NULL,              -- 优惠金额（元）
    total_amount    REAL NOT NULL               -- 订单实付总额（元）=商品小计-优惠+运费
);

-- ----------------------------------------------------------------------------
-- 订单明细表：订单-商品 多对多关系的连接表
-- ----------------------------------------------------------------------------
CREATE TABLE order_items (
    item_id         INTEGER PRIMARY KEY,        -- 明细行ID
    order_id        INTEGER NOT NULL REFERENCES orders(order_id),        -- 所属订单ID
    product_id      INTEGER NOT NULL REFERENCES products(product_id),    -- 商品ID
    quantity        INTEGER NOT NULL,           -- 购买件数
    unit_price      REAL NOT NULL,              -- 成交单价（元，含促销浮动）
    item_discount   REAL NOT NULL,              -- 该行分摊优惠（元）
    subtotal        REAL NOT NULL               -- 小计金额（元）=单价×数量-分摊优惠
);

-- ----------------------------------------------------------------------------
-- 支付表：一笔成功订单对应一条支付记录
-- ----------------------------------------------------------------------------
CREATE TABLE payments (
    payment_id      INTEGER PRIMARY KEY,        -- 支付ID
    order_id        INTEGER NOT NULL REFERENCES orders(order_id),        -- 关联订单ID
    payment_method  TEXT NOT NULL,              -- 支付方式：微信支付/支付宝/银行卡/余额
    payment_amount  REAL NOT NULL,              -- 支付金额（元）
    paid_at         TEXT NOT NULL,              -- 支付时间 YYYY-MM-DD HH:MM:SS
    payment_status  TEXT NOT NULL               -- 支付状态：成功/失败/已退款
);

-- ----------------------------------------------------------------------------
-- 评价表：已签收订单的客户评价（文本分析语料）
-- ----------------------------------------------------------------------------
CREATE TABLE reviews (
    review_id       INTEGER PRIMARY KEY,        -- 评价ID
    order_id        INTEGER NOT NULL REFERENCES orders(order_id),        -- 关联订单ID
    product_id      INTEGER NOT NULL REFERENCES products(product_id),    -- 被评价商品ID
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),  -- 评价客户ID
    rating          INTEGER NOT NULL,           -- 评分 1-5 星
    review_content  TEXT NOT NULL,              -- 评价正文（中文短文本）
    created_at      TEXT NOT NULL               -- 评价时间 YYYY-MM-DD HH:MM:SS
);

-- ----------------------------------------------------------------------------
-- 用户行为事件表：浏览/加购埋点日志（序列挖掘与推荐场景用）
-- ----------------------------------------------------------------------------
CREATE TABLE user_events (
    event_id        INTEGER PRIMARY KEY,        -- 事件ID
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),  -- 客户ID
    product_id      INTEGER NOT NULL REFERENCES products(product_id),    -- 触达商品ID
    event_type      TEXT NOT NULL,              -- 事件类型：view=浏览 / cart=加购
    event_time      TEXT NOT NULL               -- 事件时间 YYYY-MM-DD HH:MM:SS
);

-- ----------------------------------------------------------------------------
-- 常用查询索引
-- ----------------------------------------------------------------------------
CREATE INDEX idx_orders_customer   ON orders(customer_id);
CREATE INDEX idx_orders_created    ON orders(created_at);
CREATE INDEX idx_items_order       ON order_items(order_id);
CREATE INDEX idx_items_product     ON order_items(product_id);
CREATE INDEX idx_payments_order    ON payments(order_id);
CREATE INDEX idx_reviews_product   ON reviews(product_id);
CREATE INDEX idx_reviews_customer  ON reviews(customer_id);
CREATE INDEX idx_events_customer   ON user_events(customer_id);
CREATE INDEX idx_events_time       ON user_events(event_time);
CREATE INDEX idx_products_category ON products(category_id);
