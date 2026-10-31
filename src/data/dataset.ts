/**
 * 示例数据集（src/data/ecommerce.db）的只读访问层。
 *
 * 查询引擎用 Node 内置的 `node:sqlite`，零第三方依赖；宿主 Node 版本过旧
 * （没有内置 sqlite）时动态导入失败，路由层返回可读错误而不是让插件崩溃。
 *
 * 只读保证有三层：
 *  1. 打开后立即 `PRAGMA query_only = ON`，任何写操作都会被 SQLite 拒绝；
 *  2. {@link runDatasetQuery} 只接受单条 `SELECT` / `WITH` 语句；
 *  3. 用户语句被包进 `SELECT * FROM (...) LIMIT n+1` 子查询再执行，返回行数
 *     恒有上限，避免大结果集拖垮面板。
 */

import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import type {
  DatasetColumnInfo,
  DatasetInfo,
  DatasetQueryResult,
  DatasetTableInfo,
} from '../protocol.ts'

/** 单次查询最多返回的行数；超出部分截断并在响应里标记。 */
export const MAX_ROWS = 1000

/** 表元信息：中文名称、说明与逐字段注释，与 src/data/schema.sql 保持一致。 */
interface TableMeta {
  name: string
  label: string
  description: string
  /** 字段名 → 注释；类型在运行时从 PRAGMA table_info 读取。 */
  comments: Record<string, string>
}

/** 九张表的静态元信息，菜单与概览页共用同一份。 */
export const TABLE_METAS: TableMeta[] = [
  {
    name: 'categories',
    label: '类目表',
    description: '两级类目树（parent_id 为 NULL 表示一级类目）',
    comments: {
      category_id: '类目ID',
      parent_id: '父类目ID，NULL=一级类目',
      category_name: '类目名称，如「手机数码/手机」',
      level: '层级：1=一级，2=二级',
    },
  },
  {
    name: 'customers',
    label: '客户表',
    description: '注册会员主数据（10 省 23 市，会员等级四档）',
    comments: {
      customer_id: '客户ID',
      customer_name: '客户姓名（脱敏合成）',
      gender: '性别：男 / 女',
      age: '年龄（18-65）',
      province: '省份',
      city: '城市',
      register_date: '注册日期',
      member_level: '会员等级：普通/白银/黄金/钻石',
      activity_score: '活跃度评分（0-1，生成参数，决定下单频率）',
    },
  },
  {
    name: 'products',
    label: '商品表',
    description: 'SPU 级商品主数据（每个二级类目 25 个商品）',
    comments: {
      product_id: '商品ID',
      category_id: '所属二级类目ID',
      product_name: '商品名称（品牌+品类词+型号）',
      brand: '品牌',
      list_price: '标价（元）',
      cost: '成本价（元），毛利率分析用',
      stock: '当前库存件数',
      status: '在售 / 下架',
      created_date: '上架日期',
      popularity: '受欢迎度（0-1，生成参数）',
      quality_score: '质量评分（3.5-5.0，影响评价星级，生成参数）',
    },
  },
  {
    name: 'coupons',
    label: '优惠券表',
    description: '满减 / 折扣 / 无门槛三类营销券，分全年 / 双11 / 618 三档',
    comments: {
      coupon_id: '券ID',
      coupon_name: '券名称，如「满199减20」',
      coupon_type: '券类型：满减 / 折扣 / 无门槛',
      threshold_amount: '使用门槛金额（元），无门槛为 0',
      discount_value: '优惠力度：满减=减免金额；折扣=折扣率',
      valid_from: '生效日期',
      valid_to: '失效日期',
    },
  },
  {
    name: 'orders',
    label: '订单表',
    description: '订单主表（2024-01-01 ~ 2025-06-15，一单可含多商品）',
    comments: {
      order_id: '订单ID',
      customer_id: '下单客户ID',
      coupon_id: '使用的券ID，未用券为 NULL',
      order_status: '已完成 / 已发货 / 待付款 / 已取消',
      channel: '下单渠道：APP / 小程序 / 网页 / 线下',
      created_at: '下单时间',
      paid_at: '支付时间，未支付为 NULL',
      shipped_at: '发货时间，未发货为 NULL',
      delivered_at: '签收时间，未签收为 NULL',
      freight_amount: '运费（元），满 99 免运费',
      discount_amount: '优惠金额（元）',
      total_amount: '实付总额（元）= 明细小计 - 优惠 + 运费',
    },
  },
  {
    name: 'order_items',
    label: '订单明细表',
    description: '订单-商品多对多连接表，分析销量必须 JOIN 此表',
    comments: {
      item_id: '明细行ID',
      order_id: '所属订单ID',
      product_id: '商品ID',
      quantity: '购买件数',
      unit_price: '成交单价（元，含促销浮动）',
      item_discount: '该行分摊优惠（元，末行兜底）',
      subtotal: '小计（元）= 单价×数量 - 分摊优惠',
    },
  },
  {
    name: 'payments',
    label: '支付表',
    description: '已支付订单的支付记录（一笔成功订单对应一条）',
    comments: {
      payment_id: '支付ID',
      order_id: '关联订单ID',
      payment_method: '微信支付 / 支付宝 / 银行卡 / 余额',
      payment_amount: '支付金额（元）',
      paid_at: '支付时间',
      payment_status: '成功 / 失败 / 已退款',
    },
  },
  {
    name: 'reviews',
    label: '评价表',
    description: '已签收订单的中文评价（L1 文本分析语料）',
    comments: {
      review_id: '评价ID',
      order_id: '关联订单ID',
      product_id: '被评价商品ID',
      customer_id: '评价客户ID',
      rating: '评分 1-5 星，由商品质量分驱动',
      review_content: '评价正文（中文短文本）',
      created_at: '评价时间',
    },
  },
  {
    name: 'user_events',
    label: '行为事件表',
    description: '浏览 / 加购埋点，下单前 7 天内的行为轨迹',
    comments: {
      event_id: '事件ID',
      customer_id: '客户ID',
      product_id: '触达商品ID',
      event_type: 'view=浏览 / cart=加购',
      event_time: '事件时间',
    },
  },
]

/**
 * 数据库文件：构建产物在 lib/ 下（向上一级即包根），tsx 直跑源码时在 src/data/ 下
 * （向上两级），按存在性取第一个命中。
 */
const DB_FILE = ['../src/data/ecommerce.db', '../../src/data/ecommerce.db']
  .map(candidate => fileURLToPath(new URL(candidate, import.meta.url)))
  .find(candidate => existsSync(candidate))!

/** `node:sqlite` 的连接类型（动态导入，无法在类型层直接引用）。 */
type Database = InstanceType<typeof import('node:sqlite').DatabaseSync>

let database: Promise<Database> | null = null

/** 惰性打开数据库并强制只读；失败时重置缓存以便下次重试。 */
function openDatabase(): Promise<Database> {
  if (database === null) {
    database = (async () => {
      if (!existsSync(DB_FILE)) {
        throw new Error(`示例数据库不存在：${DB_FILE}`)
      }
      let DatabaseSync: typeof import('node:sqlite').DatabaseSync
      try {
        ;({ DatabaseSync } = await import('node:sqlite'))
      } catch {
        throw new Error('当前宿主 Node 版本过低，没有内置 node:sqlite，无法打开示例数据集')
      }
      const db = new DatabaseSync(DB_FILE)
      db.exec('PRAGMA query_only = ON')
      return db
    })()
    database.catch(() => {
      database = null
    })
  }
  return database
}

/** 读取一张表的字段类型（PRAGMA table_info）。 */
function describeColumns(db: Database, meta: TableMeta): DatasetColumnInfo[] {
  const rows = db
    .prepare(`SELECT name, type FROM pragma_table_info('${meta.name}')`)
    .all() as { name: string; type: string }[]
  return rows.map(row => ({
    name: row.name,
    type: row.type,
    comment: meta.comments[row.name] ?? '',
  }))
}

/** 数据集整体描述：九张表的元信息 + 实时行数。 */
export async function describeDataset(): Promise<DatasetInfo> {
  const db = await openDatabase()
  const tables: DatasetTableInfo[] = TABLE_METAS.map(meta => {
    const { count } = db
      .prepare(`SELECT COUNT(*) AS count FROM "${meta.name}"`)
      .get() as { count: number }
    return {
      name: meta.name,
      label: meta.label,
      description: meta.description,
      rowCount: count,
      columns: describeColumns(db, meta),
    }
  })
  return { engine: 'node:sqlite', dbFile: DB_FILE, tables }
}

/**
 * 校验用户输入：只允许单条 SELECT / WITH 语句，返回去掉尾部分号的语句。
 * 注意 WITH 在 SQLite 里可以接写操作，真正的兜底是连接的 query_only 模式。
 */
function normalizeSelect(sql: string): string {
  const body = sql.trim().replace(/;+\s*$/, '')
  if (body === '') {
    throw new Error('请输入 SQL 语句')
  }
  if (!/^(select|with)\b/i.test(body)) {
    throw new Error('只允许 SELECT 查询，不支持写入或 DDL 语句')
  }
  if (body.includes(';')) {
    throw new Error('只允许单条 SELECT 语句，请勿输入多条 SQL')
  }
  return body
}

/** 执行只读查询：包装 LIMIT 子查询后 prepare，超出行数上限时截断。 */
export async function runDatasetQuery(sql: string): Promise<DatasetQueryResult> {
  const body = normalizeSelect(sql)
  const db = await openDatabase()

  const wrapped = `SELECT * FROM (\n${body}\n) LIMIT ${MAX_ROWS + 1}`
  const statement = db.prepare(wrapped)

  const started = performance.now()
  const rawRows = statement.all() as Record<string, unknown>[]
  const elapsedMs = performance.now() - started

  const truncated = rawRows.length > MAX_ROWS
  const visible = truncated ? rawRows.slice(0, MAX_ROWS) : rawRows
  const columns = visible.length > 0 ? Object.keys(visible[0]!) : []
  const rows = visible.map(row =>
    columns.map(column => {
      const value = row[column]
      return typeof value === 'bigint' ? Number(value) : (value as string | number | null)
    }),
  )

  return { columns, rows, rowCount: rows.length, truncated, maxRows: MAX_ROWS, elapsedMs }
}
