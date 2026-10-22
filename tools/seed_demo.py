# -*- coding: utf-8 -*-
"""写入测试数据到 data/warehouse.db。

用法（在仓库根目录）:
  python tools/seed_demo.py           # 若库已有业务数据则拒绝覆盖
  python tools/seed_demo.py --force   # 清空业务表后重写演示数据

测试账号（密码即身份）:
  1001 演示管理员 / 1002 演示录入甲 / 1003 演示录入乙 / 1004 演示录入丙
"""
from __future__ import print_function
import os, sys, json, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'app', 'vendor'))
os.environ['WH_DATA'] = os.path.join(ROOT, 'data')

import db
from db import now, meta_set, meta_get
import server

PRODUCTS = [
    # key, name, spec, category, unit, batch_managed
    ('o40', '演示氧气瓶', '40L', '钢瓶', '瓶', 1),
    ('o10', '演示氧气瓶', '10L', '钢瓶', '瓶', 1),
    ('tube', '演示鼻氧管', '通用', '耗材', '根', 0),
    ('cup', '演示湿化杯', '标准', '耗材', '个', 0),
    ('ox', '演示制氧机', '便携式', '设备', '台', 1),
    ('cart', '演示推车', '40L', '工具', '个', 0),
]
COURIERS = [('演示配送员甲', '配送员'), ('演示配送员乙', '配送员'), ('演示点位-样例', '点瓶')]
CUSTOMERS = ['示例医院甲', '示例医院乙', '示例诊所丙', '示例一院']

BIZ_TABLES = [
    'out_items', 'out_orders', 'arrivals', 'batches', 'daily_entries',
    'stock_counts', 'loan_items', 'loan_returns', 'loans',
    'customers', 'u8_items', 'photos', 'photo_inbox', 'temp_items',
    'pending', 'weigh_slips', 'paper_sheets', 'moves', 'audit',
    'products', 'couriers', 'people', 'report_tabs',
]

def clear_biz(c):
    for t in BIZ_TABLES:
        try:
            c.execute('DELETE FROM %s' % t)
        except Exception:
            pass
    for k in ('seeded', 'initial_pins', 'demo_seed'):
        c.execute('DELETE FROM meta WHERE k=?', (k,))
    c.commit()

def main():
    force = '--force' in sys.argv
    c = server.bootstrap()
    n_prod = c.execute('SELECT COUNT(*) FROM products WHERE deleted_at IS NULL').fetchone()[0]
    n_out = c.execute('SELECT COUNT(*) FROM out_orders WHERE deleted_at IS NULL').fetchone()[0]
    if (n_prod or n_out) and not force:
        print('已有产品/出库数据，拒绝覆盖。确认覆盖请加 --force')
        return 1
    if force:
        clear_biz(c)
        c = server.bootstrap()

    ts = now()
    today = datetime.date.today()
    D = lambda n: (today - datetime.timedelta(days=n)).isoformat()

    pids = {}
    for i, (key, name, spec, cat, unit, bm) in enumerate(PRODUCTS):
        cur = c.execute(
            'INSERT INTO products(name,spec,category,unit,batch_managed,sort,created_at,created_by) VALUES(?,?,?,?,?,?,?,?)',
            (name, spec, cat, unit, bm, i, ts, '演示'))
        pids[key] = cur.lastrowid

    for i, (name, kind) in enumerate(COURIERS):
        c.execute('INSERT INTO couriers(name,kind,sort,created_at,created_by) VALUES(?,?,?,?,?)',
                  (name, kind, i, ts, '演示'))
    for name in CUSTOMERS:
        c.execute('INSERT INTO customers(name,uses,created_at,created_by) VALUES(?,?,?,?)',
                  (name, 1, ts, '演示'))

    for key, qty in [('o40', 120), ('o10', 80), ('tube', 500), ('cup', 200), ('ox', 15), ('cart', 10)]:
        c.execute('INSERT INTO stock_counts(product_id,qty,date,created_at,created_by) VALUES(?,?,?,?,?)',
                  (pids[key], qty, D(7), ts, '演示'))

    c.execute('INSERT OR IGNORE INTO batches(product_id,batch_no,created_at,created_by) VALUES(?,?,?,?)',
              (pids['o40'], 'DEMO20260101', ts, '演示'))
    c.execute('INSERT OR IGNORE INTO batches(product_id,batch_no,created_at,created_by) VALUES(?,?,?,?)',
              (pids['ox'], 'DEMO-OX-01', ts, '演示'))

    c.execute('''INSERT INTO arrivals(date,kind,name,spec,unit,qty,dest,u8_status,product_id,batch_no,created_at,created_by)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
              (D(5), '到货', '演示氧气瓶', '40L', '瓶', 30, '本库', '不入U8',
               pids['o40'], 'DEMO20260101', ts, '演示'))
    c.execute('''INSERT INTO arrivals(date,kind,name,spec,unit,qty,dest,u8_status,product_id,created_at,created_by)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
              (D(3), '到货', '演示鼻氧管', '通用', '根', 100, '示例医院甲', '不入U8',
               pids['tube'], ts, '演示'))

    def add_out(date, kind, source, customer, items, u8_no=''):
        cur = c.execute(
            '''INSERT INTO out_orders(date,kind,source,u8_no,customer,created_at,created_by)
               VALUES(?,?,?,?,?,?,?)''',
            (date, kind, source, u8_no, customer, ts, '演示'))
        oid = cur.lastrowid
        for key, qty in items:
            name = next(p[1] for p in PRODUCTS if p[0] == key)
            c.execute('INSERT INTO out_items(order_id,product_id,product_name,qty) VALUES(?,?,?,?)',
                      (oid, pids[key], name, qty))
        return oid

    add_out(D(2), '销售出库', 'U8单', '示例医院甲', [('tube', 20), ('cup', 10)], u8_no='DEMO-U8-001')
    add_out(D(1), '客户自提', 'app手工单', '示例诊所丙', [('ox', 1)])
    add_out(today.isoformat(), '销售出库', '无单', '示例医院乙', [('o40', 6), ('o10', 4)])

    cur = c.execute(
        '''INSERT INTO loans(date,handler,orgs,unit,escort,need_return,source,created_at,created_by)
           VALUES(?,?,?,?,?,?,?,?,?)''',
        (D(10), '演示管理员', json.dumps(['示例一院'], ensure_ascii=False), '示例一院',
         '演示技术员', 1, 'app手工单', ts, '演示'))
    lid = cur.lastrowid
    c.execute('INSERT INTO loan_items(loan_id,product_id,product_name,qty,org,need_return) VALUES(?,?,?,?,?,?)',
              (lid, pids['ox'], '演示制氧机', 2, '示例一院', 1))

    c.execute('''INSERT INTO temp_items(date,category,placed_by,location,name,qty,created_at,created_by)
                 VALUES(?,?,?,?,?,?,?,?)''',
              (D(1), '暂存', '演示录入甲', '门口左侧', '演示纸箱（空）', '2 箱', ts, '演示'))
    c.execute('''INSERT INTO pending(date,taker,what,qty,customer,created_at,created_by)
                 VALUES(?,?,?,?,?,?,?)''',
              (D(4), '演示录入乙', '演示鼻氧管', '若干', '示例医院乙', ts, '演示'))

    meta_set(c, 'seeded', True)
    meta_set(c, 'demo_seed', {
        'note': '测试数据',
        'at': datetime.datetime.now().isoformat(timespec='seconds'),
    })
    s = meta_get(c, 'settings', {}) or {}
    s['salespeople'] = ['演示销售甲', '演示销售乙']
    meta_set(c, 'settings', s)
    c.commit()
    print('测试数据已写入', db.DB_PATH)
    print('产品', c.execute('SELECT COUNT(*) FROM products').fetchone()[0],
          '出库单', c.execute('SELECT COUNT(*) FROM out_orders').fetchone()[0])
    print('人员', [r[0] for r in c.execute('SELECT name FROM people').fetchall()])
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
