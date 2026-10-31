# -*- coding: utf-8 -*-
"""生成结果校验：外键完整性 + 金额一致性 + 分布抽查。"""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ecommerce.db')
c = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)

fk = c.execute('PRAGMA foreign_key_check').fetchall()
print('FK违规:', fk[:5] if fk else '无')

bad = c.execute("""
SELECT COUNT(*) FROM orders o
WHERE o.order_status != '待付款'
  AND ABS(o.total_amount - (
        (SELECT ROUND(SUM(oi.subtotal),2) FROM order_items oi WHERE oi.order_id=o.order_id)
        + o.freight_amount)) > 0.01
""").fetchone()[0]
print('金额不一致订单:', bad)

print('待付款却有支付记录:',
      c.execute("SELECT COUNT(*) FROM payments p JOIN orders o ON p.order_id=o.order_id "
                "WHERE o.order_status='待付款'").fetchone()[0])
print('状态分布:', c.execute('SELECT order_status, COUNT(*) FROM orders GROUP BY 1').fetchall())
print('评价星级:', c.execute('SELECT rating, COUNT(*) FROM reviews GROUP BY 1 ORDER BY 1').fetchall())
print('渠道分布:', c.execute('SELECT channel, COUNT(*) FROM orders GROUP BY 1').fetchall())
print('GMV(已完成+已发货):', c.execute(
    "SELECT ROUND(SUM(total_amount),2) FROM orders WHERE order_status IN ('已完成','已发货')"
).fetchone()[0])
print('用券订单:', c.execute('SELECT COUNT(*) FROM orders WHERE coupon_id IS NOT NULL').fetchone()[0])
print('大促峰值示例:')
for r in c.execute("SELECT substr(created_at,1,10) d, COUNT(*) n, ROUND(SUM(total_amount),0) gmv "
                   "FROM orders WHERE substr(created_at,1,10) IN "
                   "('2024-11-11','2025-06-15','2025-02-01') GROUP BY 1").fetchall():
    print('  ', r)
c.close()
