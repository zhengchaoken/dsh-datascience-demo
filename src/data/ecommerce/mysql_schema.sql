-- ============================================================================
-- 电商分析数据集 DDL（MySQL 版本）
--
-- 源文件：src/data/ecommerce/schema.sql（SQLite 方言）+ src/data/ecommerce/ecommerce.db
-- 兼容性：MySQL 5.7 / 8.3（未使用 CHECK 约束、函数索引等 8.0 专有特性）
-- 说明：表与字段均带中文 COMMENT；字符集统一 utf8mb4。
-- ============================================================================

SET NAMES utf8mb4;

-- 重建时先关闭外键检查，按依赖倒序删除，避免残留表导致外键报错。
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS user_events;
DROP TABLE IF EXISTS reviews;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS coupons;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS categories;

SET FOREIGN_KEY_CHECKS = 1;

-- ----------------------------------------------------------------------------
-- 类目表：两级类目树（parent_id 为 NULL 表示一级类目）
-- ----------------------------------------------------------------------------
CREATE TABLE categories (
    category_id   INT          NOT NULL AUTO_INCREMENT COMMENT '类目ID',
    parent_id     INT          NULL     COMMENT '父类目ID，一级类目为NULL',
    category_name VARCHAR(100) NOT NULL COMMENT '类目名称，如“手机数码/手机”',
    level         TINYINT      NOT NULL COMMENT '层级：1=一级类目，2=二级类目',
    PRIMARY KEY (category_id),
    KEY idx_categories_parent (parent_id),
    CONSTRAINT fk_categories_parent
        FOREIGN KEY (parent_id) REFERENCES categories (category_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='类目表：两级类目树';

-- ----------------------------------------------------------------------------
-- 客户表：注册会员主数据
-- ----------------------------------------------------------------------------
CREATE TABLE customers (
    customer_id   INT          NOT NULL AUTO_INCREMENT COMMENT '客户ID',
    customer_name VARCHAR(100) NOT NULL COMMENT '客户姓名（脱敏合成）',
    gender        VARCHAR(10)  NOT NULL COMMENT '性别：男 / 女',
    age           TINYINT UNSIGNED NOT NULL COMMENT '年龄（18-65）',
    province      VARCHAR(50)  NOT NULL COMMENT '省份，如“广东省”',
    city          VARCHAR(50)  NOT NULL COMMENT '城市，如“深圳市”',
    register_date DATE         NOT NULL COMMENT '注册日期',
    member_level  VARCHAR(20)  NOT NULL COMMENT '会员等级：普通/白银/黄金/钻石',
    activity_score DECIMAL(5,4) NOT NULL COMMENT '活跃度评分（0-1，越高下单越频繁，生成参数非业务字段）',
    PRIMARY KEY (customer_id),
    KEY idx_customers_register_date (register_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='客户表：注册会员主数据';

-- ----------------------------------------------------------------------------
-- 商品表：SPU 级商品主数据
-- ----------------------------------------------------------------------------
CREATE TABLE products (
    product_id    INT           NOT NULL AUTO_INCREMENT COMMENT '商品ID',
    category_id   INT           NOT NULL COMMENT '所属二级类目ID',
    product_name  VARCHAR(200)  NOT NULL COMMENT '商品名称（品牌+品类词+型号）',
    brand         VARCHAR(100)  NOT NULL COMMENT '品牌',
    list_price    DECIMAL(14,2) NOT NULL COMMENT '标价（元）',
    cost          DECIMAL(14,2) NOT NULL COMMENT '成本价（元），毛利率分析用',
    stock         INT           NOT NULL COMMENT '当前库存件数',
    status        VARCHAR(10)   NOT NULL COMMENT '上架状态：在售 / 下架',
    created_date  DATE          NOT NULL COMMENT '上架日期',
    popularity    DECIMAL(6,4)  NOT NULL COMMENT '受欢迎度（0-1，生成参数非业务字段）',
    quality_score DECIMAL(3,2)  NOT NULL COMMENT '质量评分（3.5-5.0，影响评价分布，生成参数）',
    PRIMARY KEY (product_id),
    KEY idx_products_category (category_id),
    KEY idx_products_created_date (created_date),
    CONSTRAINT fk_products_category
        FOREIGN KEY (category_id) REFERENCES categories (category_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='商品表：SPU 级商品主数据';

-- ----------------------------------------------------------------------------
-- 优惠券表：营销券规则
-- ----------------------------------------------------------------------------
CREATE TABLE coupons (
    coupon_id        INT           NOT NULL AUTO_INCREMENT COMMENT '券ID',
    coupon_name      VARCHAR(100)  NOT NULL COMMENT '券名称，如“满199减20”',
    coupon_type      VARCHAR(20)   NOT NULL COMMENT '券类型：满减 / 折扣 / 无门槛',
    threshold_amount DECIMAL(12,2) NOT NULL COMMENT '使用门槛金额（元），无门槛为0',
    discount_value   DECIMAL(12,2) NOT NULL COMMENT '优惠力度：满减=减免金额；折扣=折扣率（如0.90）',
    valid_from       DATE          NOT NULL COMMENT '生效日期',
    valid_to         DATE          NOT NULL COMMENT '失效日期',
    PRIMARY KEY (coupon_id),
    KEY idx_coupons_valid (valid_from, valid_to)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='优惠券表：营销券规则';

-- ----------------------------------------------------------------------------
-- 订单表：订单主表（一单可含多商品，明细见 order_items）
-- ----------------------------------------------------------------------------
CREATE TABLE orders (
    order_id        INT           NOT NULL AUTO_INCREMENT COMMENT '订单ID',
    customer_id     INT           NOT NULL COMMENT '下单客户ID',
    coupon_id       INT           NULL     COMMENT '使用的券ID，未用券为NULL',
    order_status    VARCHAR(20)   NOT NULL COMMENT '订单状态：已完成/已发货/待付款/已取消',
    channel         VARCHAR(20)   NOT NULL COMMENT '下单渠道：APP/小程序/网页/线下',
    created_at      DATETIME      NOT NULL COMMENT '下单时间',
    paid_at         DATETIME      NULL     COMMENT '支付时间，未支付为NULL',
    shipped_at      DATETIME      NULL     COMMENT '发货时间，未发货为NULL',
    delivered_at    DATETIME      NULL     COMMENT '签收时间，未签收为NULL',
    freight_amount  DECIMAL(12,2) NOT NULL COMMENT '运费（元），满99免运费',
    discount_amount DECIMAL(14,2) NOT NULL COMMENT '优惠金额（元）',
    total_amount    DECIMAL(14,2) NOT NULL COMMENT '订单实付总额（元）=商品小计-优惠+运费',
    PRIMARY KEY (order_id),
    KEY idx_orders_customer (customer_id),
    KEY idx_orders_created (created_at),
    KEY idx_orders_coupon (coupon_id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers (customer_id),
    CONSTRAINT fk_orders_coupon
        FOREIGN KEY (coupon_id) REFERENCES coupons (coupon_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='订单表：订单主表';

-- ----------------------------------------------------------------------------
-- 订单明细表：订单-商品 多对多关系的连接表
-- ----------------------------------------------------------------------------
CREATE TABLE order_items (
    item_id       INT           NOT NULL AUTO_INCREMENT COMMENT '明细行ID',
    order_id      INT           NOT NULL COMMENT '所属订单ID',
    product_id    INT           NOT NULL COMMENT '商品ID',
    quantity      INT           NOT NULL COMMENT '购买件数',
    unit_price    DECIMAL(14,2) NOT NULL COMMENT '成交单价（元，含促销浮动）',
    item_discount DECIMAL(14,2) NOT NULL COMMENT '该行分摊优惠（元）',
    subtotal      DECIMAL(16,2) NOT NULL COMMENT '小计金额（元）=单价×数量-分摊优惠',
    PRIMARY KEY (item_id),
    KEY idx_items_order (order_id),
    KEY idx_items_product (product_id),
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id) REFERENCES orders (order_id),
    CONSTRAINT fk_items_product
        FOREIGN KEY (product_id) REFERENCES products (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='订单明细表：订单与商品的多对多连接表';

-- ----------------------------------------------------------------------------
-- 支付表：一笔成功订单对应一条支付记录
-- ----------------------------------------------------------------------------
CREATE TABLE payments (
    payment_id     INT           NOT NULL AUTO_INCREMENT COMMENT '支付ID',
    order_id       INT           NOT NULL COMMENT '关联订单ID',
    payment_method VARCHAR(20)   NOT NULL COMMENT '支付方式：微信支付/支付宝/银行卡/余额',
    payment_amount DECIMAL(14,2) NOT NULL COMMENT '支付金额（元）',
    paid_at        DATETIME      NOT NULL COMMENT '支付时间',
    payment_status VARCHAR(20)   NOT NULL COMMENT '支付状态：成功/失败/已退款',
    PRIMARY KEY (payment_id),
    KEY idx_payments_order (order_id),
    CONSTRAINT fk_payments_order
        FOREIGN KEY (order_id) REFERENCES orders (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='支付表：订单支付记录';

-- ----------------------------------------------------------------------------
-- 评价表：已签收订单的客户评价（文本分析语料）
-- ----------------------------------------------------------------------------
CREATE TABLE reviews (
    review_id      INT           NOT NULL AUTO_INCREMENT COMMENT '评价ID',
    order_id       INT           NOT NULL COMMENT '关联订单ID',
    product_id     INT           NOT NULL COMMENT '被评价商品ID',
    customer_id    INT           NOT NULL COMMENT '评价客户ID',
    rating         TINYINT UNSIGNED NOT NULL COMMENT '评分 1-5 星',
    review_content VARCHAR(1000) NOT NULL COMMENT '评价正文（中文短文本）',
    created_at     DATETIME      NOT NULL COMMENT '评价时间',
    PRIMARY KEY (review_id),
    KEY idx_reviews_order (order_id),
    KEY idx_reviews_product (product_id),
    KEY idx_reviews_customer (customer_id),
    CONSTRAINT fk_reviews_order
        FOREIGN KEY (order_id) REFERENCES orders (order_id),
    CONSTRAINT fk_reviews_product
        FOREIGN KEY (product_id) REFERENCES products (product_id),
    CONSTRAINT fk_reviews_customer
        FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='评价表：客户评价文本';

-- ----------------------------------------------------------------------------
-- 用户行为事件表：浏览/加购埋点日志（序列挖掘与推荐场景用）
-- ----------------------------------------------------------------------------
CREATE TABLE user_events (
    event_id     BIGINT          NOT NULL AUTO_INCREMENT COMMENT '事件ID',
    customer_id  INT             NOT NULL COMMENT '客户ID',
    product_id   INT             NOT NULL COMMENT '触达商品ID',
    event_type   VARCHAR(10)     NOT NULL COMMENT '事件类型：view=浏览 / cart=加购',
    event_time   DATETIME        NOT NULL COMMENT '事件时间',
    PRIMARY KEY (event_id),
    KEY idx_events_customer (customer_id),
    KEY idx_events_time (event_time),
    KEY idx_events_product (product_id),
    CONSTRAINT fk_events_customer
        FOREIGN KEY (customer_id) REFERENCES customers (customer_id),
    CONSTRAINT fk_events_product
        FOREIGN KEY (product_id) REFERENCES products (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='用户行为事件表：浏览/加购埋点日志';
