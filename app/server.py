# -*- coding: utf-8 -*-
"""库房出入库系统 · 局域网服务（只用 Python 标准库）
   启动：python app/server.py  → 浏览器打开 http://本机IP:8080  手机打开 http://本机IP:8080/m/"""
import sys, os, json, re, time, datetime, socket, mimetypes, base64, uuid, traceback, io, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vendor'))
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import db, logic, xlsxio, importers, backup, u8
from db import row, rows, now, today, save_row, soft_delete, restore, audit, meta_get, meta_set

STATIC = os.path.join(db.BASE, 'static')
TPL_DAILY = os.path.join(db.BASE, 'templates', '产品出入库情况_原表.xlsx')

from web import ApiError, ROUTES, route, attach_photos, photos_of, table_result, readb as _readb
import loans  # 借用归还（注册路由）
import reports, slips, outslip, paper  # 报表 / 称重单 / 领用出库单 / 纸质交接表
import guest  # 访客借用登记（/m/guest，独立路由表）
import printpage  # 打印页模板 + data/print_files
import links  # 删除影响清单 / 记录来源查看
import moves  # 库存变化记录（全部产品）
import version
def _reload_ver():
    import importlib
    try: importlib.reload(version)
    except Exception: pass
    return version
import upq  # 手机拍照上传（临时上传码）
import plib  # 共享照片库（长会话持续上传）

# ---------------- 身份 / 权限 ----------------
def person_by_pin(c, pin):
    if not pin: raise ApiError('请输入密码', 401)
    p = row(c.execute('SELECT * FROM people WHERE pin_hash=? AND active=1', (db.pin_hash(c, pin),)).fetchone())
    if not p: raise ApiError('密码不对', 401)
    return p

def check_perm(p, perm):
    if not perm: return
    perms = json.loads(p['perms'] or '{}')
    if meta_get(db_c(), 'perms_all_open', True): return   # 已确认：权限暂时全开（仍保留按人设置）
    if p['role'] == '管理员' or perms.get(perm, perm == 'entry'): return
    raise ApiError('「%s」没有%s权限' % (p['name'], dict(db.PERM_KEYS).get(perm, perm)), 403)

_tl = {}
def db_c():
    import threading
    k = threading.get_ident()
    if k not in _tl: _tl[k] = db.connect()
    return _tl[k]

def plabel(p): return logic.product_label(p)

# ---------------- 基础 ----------------
@route('GET', '/api/boot')
def api_boot(c, q, b, me):
    version = _reload_ver()
    s = logic.settings(c)
    prods = rows(c.execute('SELECT id,name,spec,category,unit,batch_managed,temp_name,no_u8,sort,u8_code,u8_wh FROM products WHERE deleted_at IS NULL AND merged_into IS NULL ORDER BY sort, id'))
    use = {r[0]: r[1] for r in c.execute('SELECT product_id, COUNT(*) FROM out_items GROUP BY product_id')}
    for p in prods: p['label'] = plabel(p); p['uses'] = use.get(p['id'], 0)
    return {'settings': s, 'products': prods, 'people': [r['name'] for r in c.execute('SELECT name FROM people WHERE active=1 ORDER BY sort,id')],
            'couriers': rows(c.execute('SELECT id,name,kind,sort,active FROM couriers WHERE deleted_at IS NULL ORDER BY sort,id')),
            'daily_cols': {'cyl': logic.CYL, 'cyl_cn': logic.CYL_CN, 'other': [o[:2] for o in logic.OTHER], 'map': logic.daily_map(c)},
            'today': today(), 'lan': lan_urls(), 'salespeople': s.get('salespeople', []), 'loan_req': guest.pending_count(c),
            'version': version.VERSION, 'build_date': version.BUILD_DATE}

@route('GET', '/api/autostart')
def api_autostart(c, q, b, me):
    import autostart
    return autostart.status()

@route('POST', '/api/autostart/set', 'settings')
def api_autostart_set(c, q, b, me):
    import autostart
    if not autostart.IS_WIN: raise ApiError('只有 Windows 主机能设置开机自动启动')
    try: st = autostart.install() if b.get('on') else autostart.remove()
    except OSError as e: raise ApiError('设置失败：%s' % e)
    audit(c, me['name'], '修改', 'settings', 0, '开机自动启动：' + ('开启' if st['on'] else '关闭'))
    return st

@route('GET', '/api/version')
def api_version(c, q, b, me):
    version = _reload_ver()
    sz = os.path.getsize(db.DB_PATH) if os.path.exists(db.DB_PATH) else 0
    return {'name': version.NAME, 'version': version.VERSION, 'build_date': version.BUILD_DATE, 'author': version.AUTHOR, 'changelog': version.CHANGELOG,
            'data_dir': os.path.abspath(db.DATA), 'db_size': sz, 'lan': lan_urls(), 'port': PORT,
            'site_name': logic.settings(c).get('site_name')}

@route('GET', '/api/ping')
def api_ping(c, q, b, me): return {'ok': 1, 'app': 'warehouse', 'port': PORT}

@route('POST', '/api/whoami')
def api_whoami(c, q, b, me): return {'name': me['name'], 'role': me['role']}

@route('GET', '/api/customers')
def api_customers(c, q, b, me):
    k = (q.get('q') or '').strip()
    rs = rows(c.execute("SELECT name,contact,phone,last_date,uses FROM customers WHERE deleted_at IS NULL AND (name LIKE ? OR contact LIKE ? OR phone LIKE ?) ORDER BY uses DESC, last_date DESC LIMIT 12",
                        ('%' + k + '%',) * 3))
    return {'items': rs}

# ---------------- 首页 ----------------
def age_days(d):
    try: return (datetime.date.today() - datetime.date.fromisoformat(d[:10])).days
    except Exception: return 0

@route('GET', '/api/home')
def api_home(c, q, b, me):
    s = logic.settings(c)
    pend = rows(c.execute("SELECT * FROM pending WHERE deleted_at IS NULL AND status='待补全' ORDER BY date"))
    loans = rows(c.execute("SELECT * FROM loans WHERE deleted_at IS NULL AND status IN ('未归还','部分归还') ORDER BY date"))
    arr = rows(c.execute("SELECT * FROM arrivals WHERE deleted_at IS NULL AND u8_status='待入U8' ORDER BY date"))
    st = logic.stock_all(c, [r[0] for r in c.execute('SELECT id FROM products WHERE deleted_at IS NULL AND merged_into IS NULL')])
    unknown = sum(1 for v in st.values() if not v['known']); warn = sum(1 for v in st.values() if v.get('warn'))
    def ages(lst, key='date'):
        a = [age_days(x[key]) for x in lst]
        return {'n': len(lst), 'over7': sum(1 for x in a if 7 < x <= 30), 'over30': sum(1 for x in a if x > 30), 'oldest': max(a) if a else 0}
    # 临近效期批次
    lim = (datetime.date.today() + datetime.timedelta(days=int(s.get('expiry_alert_days') or 90))).isoformat()
    exp = []
    for bt in rows(c.execute("SELECT b.*, p.name pname FROM batches b JOIN products p ON p.id=b.product_id WHERE b.deleted_at IS NULL AND b.expiry<>'' AND b.expiry<=? ORDER BY b.expiry", (lim,))):
        rem = [x for x in logic.batch_stock(c, bt['product_id']) if x['batch_no'] == bt['batch_no']]
        if rem and rem[0]['remain'] > 0: exp.append({'product': bt['pname'], 'batch_no': bt['batch_no'], 'expiry': bt['expiry'], 'remain': rem[0]['remain']})
    # 今日出库（按产品合计）
    t = today()
    tod = rows(c.execute("SELECT p.id, p.name, p.spec, p.unit, -SUM(m.qty) q FROM moves m JOIN products p ON p.id=m.product_id WHERE m.date=? AND m.qty<0 GROUP BY m.product_id ORDER BY q DESC LIMIT 6", (t,)))
    # 最近记录
    rec = []
    for o in rows(c.execute('SELECT * FROM out_orders WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT 8')):
        its = logic.items_of(c, o['id'])
        ph = photos_of(c, 'out', o['id'])
        rec.append({'type': '出库', 'kind': o['kind'], 'id': o['id'], 'date': o['date'], 'title': o['customer'] or o['recipient'] or o['kind'], 'by': o['created_by'],
                    'desc': '、'.join('%s %g' % (i['product_name'], i['qty']) for i in its[:3]) + (' 等 %d 项' % len(its) if len(its) > 3 else ''),
                    'ts': o['created_at'], 'photo': ph[0]['path'] if ph else '', 'remark': o['remark'] or ''})
    for a in rows(c.execute('SELECT * FROM arrivals WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT 5')):
        rec.append({'type': '到货', 'kind': a['kind'], 'id': a['id'], 'date': a['date'], 'title': '%s %s' % (a['name'], a['spec']), 'by': a['created_by'],
                    'desc': '%g %s · %s' % (a['qty'] or 0, a['unit'], a['u8_status']), 'ts': a['created_at'], 'photo': '', 'remark': a['remark'] or ''})
    for e in rows(c.execute('SELECT e.*, k.name cname FROM daily_entries e JOIN couriers k ON k.id=e.courier_id WHERE e.deleted_at IS NULL ORDER BY e.created_at DESC LIMIT 5')):
        v = json.loads(e['vals'] or '{}')
        rec.append({'type': '出入库情况', 'kind': '产品出入库情况', 'id': e['id'], 'date': e['book_date'] or e['out_date'], 'title': e['cname'], 'by': e['created_by'],
                    'desc': '出 40L %s · 10L %s' % (logic.num(v.get('o40')), logic.num(v.get('o10'))) + ('' if e['book_date'] else ' · 在外未交回'), 'ts': e['created_at'], 'photo': '', 'remark': e['note'] or ''})
    rec.sort(key=lambda r: -(r['ts'] or 0))
    lb = meta_get(c, 'last_backup', None)
    return {'pending': ages(pend), 'loans': ages(loans), 'u8': ages(arr), 'unknown': unknown, 'stock_warn': warn, 'products': len(st),
            'expiring': exp[:8], 'today_out': tod, 'recent': rec[:8], 'last_backup': lb,
            'loans_list': [{'id': l['id'], 'date': l['date'], 'who': l['user_to'] or l['unit'] or l['handler'], 'unit': l['unit'], 'status': l['status'],
                            'items': '、'.join('%s %g' % (importers.pname(c, i['product_id']), i['qty'] - (i['returned'] or 0)) for i in rows(c.execute('SELECT * FROM loan_items WHERE loan_id=?', (l['id'],))) if i['qty'] - (i['returned'] or 0) > 0)}
                           for l in sorted(loans, key=lambda x: x['date'], reverse=True)[:6]],
            'pending_list': [{'id': p['id'], 'date': p['date'], 'taker': p['taker'], 'what': p['what'], 'qty': p['qty'], 'age': age_days(p['date'])} for p in pend[:6]],
            'outside': logic.outside_total(c), 'loan_req': guest.pending_count(c),
            'version': version.VERSION, 'build_date': version.BUILD_DATE}

@route('GET', '/api/version')
def api_version(c, q, b, me):
    version = _reload_ver()
    sz = os.path.getsize(db.DB_PATH) if os.path.exists(db.DB_PATH) else 0
    return {'name': version.NAME, 'version': version.VERSION, 'build_date': version.BUILD_DATE, 'author': version.AUTHOR, 'changelog': version.CHANGELOG,
            'data_dir': os.path.abspath(db.DATA), 'db_size': sz, 'lan': lan_urls(), 'port': PORT,
            'site_name': logic.settings(c).get('site_name')}

# ---------------- 产品与库存 ----------------
@route('GET', '/api/products')
def api_products(c, q, b, me):
    deleted = q.get('deleted') == '1'
    ps = rows(c.execute('SELECT * FROM products WHERE merged_into IS NULL AND deleted_at IS %s ORDER BY sort, id' % ('NOT NULL' if deleted else 'NULL')))
    st = logic.stock_all(c, [p['id'] for p in ps]); ub = u8.by_product(c)
    last_move = {r[0]: r[1] for r in c.execute('SELECT product_id, MAX(date) FROM moves GROUP BY product_id')}
    for p in ps:
        p['label'] = plabel(p); p['stock'] = st[p['id']]; p['last_move'] = last_move.get(p['id'], '')
        p['u8'] = ub.get(p['id'])
        if p['batch_managed']: p['batches'] = logic.batch_stock(c, p['id'])
    return {'items': ps}

@route('POST', '/api/product/save', 'entry')
def api_product_save(c, q, b, me):
    d = b['data']
    if not (d.get('name') or '').strip(): raise ApiError('请填产品名称')
    d['name'] = d['name'].strip()
    dup = c.execute('SELECT id FROM products WHERE name=? AND spec=? AND deleted_at IS NULL AND merged_into IS NULL AND id<>?', (d['name'], d.get('spec', ''), d.get('id') or 0)).fetchone()
    if dup: raise ApiError('已有同名同规格的产品')
    if not d.get('id'): d.setdefault('sort', (c.execute('SELECT COALESCE(MAX(sort),0) FROM products').fetchone()[0] or 0) + 10)
    pid = save_row(c, 'product', d, me['name'], None if d.get('id') else '新增产品 ' + d['name'])
    attach_photos(c, b.get('photo_ids'), 'product', pid)
    return {'id': pid}

@route('POST', '/api/product/delete', 'delete')
def api_product_delete(c, q, b, me):
    soft_delete(c, 'product', int(b['id']), me['name'], b.get('reason', '')); return {'ok': 1}

@route('POST', '/api/product/reorder', 'entry')
def api_product_reorder(c, q, b, me):
    """按传入的 id 顺序重写 products.sort（默认列表顺序）；只动未删除、未合并的产品。"""
    ids = [int(x) for x in (b.get('ids') or [])]
    if not ids: raise ApiError('请给出产品顺序')
    alive = {r[0] for r in c.execute('SELECT id FROM products WHERE deleted_at IS NULL AND merged_into IS NULL')}
    ids = [i for i in ids if i in alive]
    if not ids: raise ApiError('没有可调整的产品')
    # 未出现在列表里的产品（筛选后只传了部分）排到末尾，保留相对顺序
    rest = [r[0] for r in c.execute('SELECT id FROM products WHERE deleted_at IS NULL AND merged_into IS NULL ORDER BY sort, id') if r[0] not in set(ids)]
    full = ids + rest
    for i, pid in enumerate(full):
        c.execute('UPDATE products SET sort=? WHERE id=?', ((i + 1) * 10, pid))
    audit(c, me['name'], '修改', 'product', 0, '调整产品默认顺序 %d 个' % len(full))
    return {'ok': 1, 'n': len(full)}

@route('POST', '/api/product/merge', 'count')
def api_product_merge(c, q, b, me):
    keep = int(b['keep']); drops = [int(x) for x in b['drop'] if int(x) != keep]
    if not drops: raise ApiError('请选要合并掉的产品')
    logic.merge_products(c, keep, drops, me['name']); return {'ok': 1}

@route('POST', '/api/count/save', 'count')
def api_count_save(c, q, b, me):
    pid = int(b['product_id'])
    bc = {k: float(v) for k, v in (b.get('batches') or {}).items() if str(v).strip() != ''} or None
    if not bc and str(b.get('qty', '')).strip() == '': raise ApiError('请填实数')
    if not bc and float(b['qty']) < 0: raise ApiError('实数不能是负数')
    cid = logic.save_count(c, pid, float(b.get('qty') or 0), b.get('date') or today(), me['name'], b.get('note', ''), bc)
    return {'id': cid, 'stock': logic.stock_all(c, [pid])[pid]}

@route('GET', '/api/counts')
def api_counts(c, q, b, me):
    w = 'WHERE c.deleted_at IS NULL AND (c.batch_no="" OR c.batch_no IS NULL)'; args = []
    if q.get('product_id'): w += ' AND c.product_id=?'; args.append(int(q['product_id']))
    return {'items': rows(c.execute('SELECT c.*, p.name pname, p.spec pspec, p.unit FROM stock_counts c JOIN products p ON p.id=c.product_id %s ORDER BY c.date DESC, c.created_at DESC LIMIT 300' % w, args))}

@route('GET', '/api/product/moves')
def api_product_moves(c, q, b, me):
    pid = int(q['id'])
    hide = not logic.settings(c).get('moves_show_daily', True) and q.get('daily') != '1'   # 设置里关了「显示交接表批量配送」：只是不显示
    hid = c.execute("SELECT COUNT(*) FROM moves WHERE product_id=? AND src='daily'", (pid,)).fetchone()[0] if hide else 0
    ms = rows(c.execute('SELECT * FROM moves WHERE product_id=?%s ORDER BY date DESC, ts DESC LIMIT 200' % (" AND src<>'daily'" if hide else ''), (pid,)))
    cs = rows(c.execute('SELECT * FROM stock_counts WHERE product_id=? AND deleted_at IS NULL ORDER BY date DESC, created_at DESC', (pid,)))
    return {'moves': ms, 'hidden_daily': hid, 'counts': cs, 'stock': logic.stock_all(c, [pid])[pid], 'u8': rows(c.execute('SELECT * FROM u8_items WHERE product_id=? AND deleted_at IS NULL', (pid,)))}

def count_sheet_rows(c):
    ps = rows(c.execute('SELECT * FROM products WHERE deleted_at IS NULL AND merged_into IS NULL ORDER BY category, sort, id'))
    st = logic.stock_all(c, [p['id'] for p in ps]); ub = u8.by_product(c); out = []
    for i, p in enumerate(ps):
        s = st[p['id']]
        out.append([i + 1, p['category'], plabel(p), p['unit'], (ub.get(p['id']) or {}).get('qty'),
                    s['qty'] if s['known'] else '未知', s.get('count_date', '') if s['known'] else '', '', ''])
    return out

@route('GET', '/api/count/sheet.xlsx')
def api_count_sheet(c, q, b, me):
    return table_result(q, '盘点清单_%s.xlsx' % today(), [('盘点清单', '盘点清单（%s）' % today(), ['序号', '分类', '产品', '单位', 'U8账面数', '系统库存', '上次盘点', '实盘数', '签字', '备注'],
                                [r + [''] for r in count_sheet_rows(c)], [6, 10, 28, 6, 10, 10, 12, 10, 10, 18])])

# ---------------- U8 账面 ----------------
@route('GET', '/api/u8')
def api_u8(c, q, b, me):
    us = rows(c.execute('SELECT u.*, p.name pname, p.spec pspec, s.name sname, s.spec sspec FROM u8_items u LEFT JOIN products p ON p.id=u.product_id LEFT JOIN products s ON s.id=u.suggest_id WHERE u.deleted_at IS NULL ORDER BY u.wh, u.id'))
    st = logic.stock_all(c)
    for u in us:
        s = st.get(u['product_id']) if u['product_id'] else None
        u['stock'] = s
    return {'items': us}

@route('POST', '/api/u8/confirm', 'entry')
def api_u8_confirm(c, q, b, me):
    u8.confirm(c, int(b['id']), me['name'], b.get('product_id'), b.get('new_product'), b.get('none')); return {'ok': 1}

@route('POST', '/api/u8/import', 'entry')
def api_u8_import(c, q, b, me): return u8.import_excel(c, b['_raw'], me['name'], q.get('as_of', ''))

# ---------------- 出库 ----------------
def out_query(c, q):
    w = ['o.deleted_at IS %s' % ('NOT NULL' if q.get('deleted') == '1' else 'NULL')]; a = []
    if q.get('from'): w.append('o.date>=?'); a.append(q['from'])
    if q.get('to'): w.append('o.date<=?'); a.append(q['to'])
    if q.get('kind'):
        # 客户自提含历史「自提出库」（迁移前/漏迁仍能筛到）
        k = logic.normalize_out_kind(q['kind'], default=q['kind'])
        aliases = [x for x, y in logic.OUT_KIND_MERGE.items() if y == k]
        if aliases:
            w.append('(' + ' OR '.join(['o.kind=?'] * (1 + len(aliases))) + ')'); a.append(k); a.extend(aliases)
        else:
            w.append('o.kind=?'); a.append(k)
    for k in ('source', 'mode'):
        if q.get(k): w.append('o.%s=?' % k); a.append(q[k])
    if q.get('u8_type'): w.append('o.u8_type=?'); a.append(q['u8_type'])
    if q.get('q'):
        w.append("(o.customer LIKE ? OR o.contact LIKE ? OR o.phone LIKE ? OR o.u8_no LIKE ? OR o.remark LIKE ? OR o.recipient LIKE ? OR EXISTS(SELECT 1 FROM out_items i WHERE i.order_id=o.id AND (i.product_name LIKE ? OR i.note LIKE ?)))")
        a += ['%' + q['q'] + '%'] * 8
    os_ = rows(c.execute('SELECT o.* FROM out_orders o WHERE %s ORDER BY o.date DESC, o.created_at DESC LIMIT %d' % (' AND '.join(w), int(q.get('limit') or 300)), a))
    for o in os_:
        if o.get('kind') in logic.OUT_KIND_MERGE:
            o['kind'] = logic.OUT_KIND_MERGE[o['kind']]  # 展示归一；写库合并见 migrate
        o['items'] = logic.items_of(c, o['id']); o['photos'] = photos_of(c, 'out', o['id'])
    return os_

@route('GET', '/api/out')
def api_out(c, q, b, me): return {'items': out_query(c, q)}

@route('GET', '/api/out/one')
def api_out_one(c, q, b, me):
    o = row(c.execute('SELECT * FROM out_orders WHERE id=?', (int(q['id']),)).fetchone())
    if o.get('kind') in logic.OUT_KIND_MERGE:
        o['kind'] = logic.OUT_KIND_MERGE[o['kind']]
    o['items'] = logic.items_of(c, o['id']); o['photos'] = photos_of(c, 'out', o['id'])
    o['audit'] = rows(c.execute("SELECT ts,person,action,summary FROM audit WHERE entity='out' AND entity_id=? ORDER BY ts", (o['id'],)))
    return o

@route('POST', '/api/out/save', 'entry')
def api_out_save(c, q, b, me):
    d = b['data']
    if d.get('source') != 'U8单': d['u8_type'] = ''
    if 'kind' in d: d['kind'] = logic.normalize_out_kind(d.get('kind'))
    oid = logic.save_out(c, d, me['name'])
    attach_photos(c, b.get('photo_ids'), 'out', oid, replace=bool(d.get('id')))
    return {'id': oid}

@route('POST', '/api/out/batch', 'entry')
def api_out_batch(c, q, b, me):
    key = uuid.uuid4().hex[:10]; ids = []
    for d in b['orders']:
        d['mode'] = 'batch'; d['batch_key'] = key
        ids.append(logic.save_out(c, d, me['name']))
    if ids: attach_photos(c, b.get('photo_ids'), 'out', ids[0])
    return {'ids': ids, 'batch_key': key}

@route('POST', '/api/out/delete', 'delete')
def api_out_delete(c, q, b, me):
    soft_delete(c, 'out', int(b['id']), me['name'], b.get('reason', '')); logic.rebuild_out(c, int(b['id'])); return {'ok': 1}

@route('GET', '/api/out/export.xlsx')
def api_out_export(c, q, b, me):
    rs = []
    for o in out_query(c, dict(q, limit=5000, fmt='')):
        for i in o['items']:
            side = i.get('side') or 'out'
            dire = '' if o['kind'] != '换货' else ('换入' if side == 'in' else '换出')
            rs.append([o['date'], o['kind'], dire, o['source'], o['u8_no'], o['u8_type'], o['customer'] or o['recipient'], o['contact'], o['phone'], i['product_name'], i['qty'], i['batch_no'], o['remark'], o['created_by']])
    return table_result(q, '出库记录_%s.xlsx' % today(), [('出库记录', '出库记录', ['日期', '类型', '方向', '单据来源', 'U8单号', 'U8单细分', '客户/领用人', '联系人', '电话', '产品', '数量', '批号', '备注', '经办'], rs,
                                [11, 10, 7, 10, 13, 12, 22, 8, 13, 22, 7, 11, 22, 8])])

# ---------------- 产品出入库情况 ----------------
def daily_payload(c, date):
    ents = rows(c.execute('SELECT e.*, k.name cname FROM daily_entries e JOIN couriers k ON k.id=e.courier_id WHERE e.deleted_at IS NULL AND (e.book_date=? OR (e.book_date IS NULL)) ORDER BY e.id', (date,)))
    for e in ents: e['vals'] = json.loads(e['vals'] or '{}'); e['hand'] = json.loads(e['hand'] or '[]')
    merged = logic.daily_rows(c, date)
    for m in merged: m['calc'] = logic.calc_row(m['vals'])
    tot = {}
    for m in merged:
        if m.get('pending') or m.get('merged_into'): continue   # 待清点的、并入后面合计的，不算进合计
        for k, v in list(m['vals'].items()) + list(m['calc'].items()): tot[k] = logic.num(tot.get(k)) + logic.num(v)
    # 1.1.48：核对 = 当天总核对（{ok,by,ts}）；旧版按配送员 map 不再展示（审计仍在）
    raw = meta_get(c, 'daily_verify:' + date, {}) or {}
    if isinstance(raw, dict) and ('ok' in raw or 'by' in raw) and not any(str(k).isdigit() for k in raw):
        ver = {'ok': bool(raw.get('ok')), 'by': raw.get('by') or '', 'ts': raw.get('ts')}
    else:
        ver = {'ok': False}
    return {'date': date, 'entries': [e for e in ents if e['book_date'] == date], 'open': [e for e in ents if e['book_date'] is None],
            'merged': merged, 'total': tot, 'outside': logic.outside_total(c),
            'verify': ver,
            'hand_photos': {str(k): n for k, n in c.execute("SELECT entity_id, COUNT(*) FROM photos WHERE entity='hand' AND tag=? AND deleted_at IS NULL GROUP BY entity_id", (date,))}}

@route('GET', '/api/daily')
def api_daily(c, q, b, me): return daily_payload(c, q.get('date') or today())

@route('POST', '/api/daily/verify', 'entry')
def api_daily_verify(c, q, b, me):
    """汇总页核对情况：按日期整天已核对 / 未核对（一天一个），进操作记录。不改出入库数。"""
    date = (b.get('date') or today()).strip()
    ok = bool(b.get('ok'))
    key = 'daily_verify:' + date
    before = meta_get(c, key, {}) or {}
    if not isinstance(before, dict): before = {}
    # 旧 map（数字键）整包当 before，便于审计对照
    if ok:
        after = {'ok': True, 'by': me['name'], 'ts': now()}
        action, summary = '核对', '%s 当天已核对' % date
    else:
        after = {'ok': False}
        action, summary = '取消核对', '%s 当天未核对' % date
    meta_set(c, key, after)
    audit(c, me['name'], action, 'daily_verify', 0, summary, before, after)
    return {'ok': 1, 'date': date, 'verify': after}

@route('GET', '/api/daily/stats')
def api_daily_stats(c, q, b, me):
    """数量统计：①库房出库（moves 负向）②配送员全部合计配送量（=汇总财务表：每天 daily_rows+calc_row，含实际配送/net）③所有地方出/入库合计。
    from/to 可选筛控件，默认当天；区间合计。只读。前端 1.1.49 起用表格展示。"""
    t = today()
    fr = (q.get('from') or q.get('date') or t).strip(); to = (q.get('to') or fr).strip()
    if to < fr: fr, to = to, fr
    d0 = datetime.date.fromisoformat(fr); d1 = datetime.date.fromisoformat(to)
    if (d1 - d0).days > 92: d0 = d1 - datetime.timedelta(days=92); fr = d0.isoformat()
    # ① 库房出库：区间内 moves.qty<0 按产品合计（含出库单/日表/借用等，与首页今日出库同口径）
    wh = rows(c.execute(
        "SELECT p.id, p.name, p.spec, p.unit, -SUM(m.qty) q FROM moves m JOIN products p ON p.id=m.product_id "
        "WHERE m.date>=? AND m.date<=? AND m.qty<0 GROUP BY m.product_id ORDER BY q DESC, p.name", (fr, to)))
    for x in wh: x['q'] = round(logic.num(x['q']), 3)
    # ② 配送：每天 daily_rows 合计（待清点/并入后面的不算），区间相加
    pname = {r['id']: r['name'] for r in c.execute('SELECT id, name FROM products')}
    cols = [('o40', '40L 出库'), ('o10', '10L 出库'), ('R40', '40L 实际配送'), ('R10', '10L 实际配送'),
            ('T40', '40L 钢瓶总出库'), ('T10', '10L 钢瓶总出库')] + [('net_' + o[0], o[1]) for o in logic.OTHER]
    v = {}; hand = {}; pend_days = []
    d = d0
    while d <= d1:
        ds = d.isoformat(); merged = logic.daily_rows(c, ds)
        day_pend = []
        for m in merged:
            if m.get('pending'): day_pend.append(m.get('label') or m['name']); continue
            if m.get('merged_into'): continue
            cc = logic.calc_row(m['vals'])
            for k, _ in cols:
                if k[0] == 'T':
                    x = logic.num(cc.get('R' + k[1:])) + logic.num(m['vals'].get('hc' + k[1:])) + logic.num(m['vals'].get('hn' + k[1:]))
                elif k in ('o40', 'o10'):
                    x = logic.num(m['vals'].get(k))
                else:
                    x = logic.num(cc.get(k))
                if x: v[k] = logic.num(v.get(k)) + x
        skip = {m['courier_id'] for m in merged if m.get('pending')}
        for e in c.execute('SELECT courier_id, hand FROM daily_entries WHERE deleted_at IS NULL AND book_date=?', (ds,)):
            if e['courier_id'] in skip: continue
            for h in json.loads(e['hand'] or '[]'):
                n = logic.short_name(c, h.get('product_id'), pname)
                hand[n] = logic.num(hand.get(n)) + logic.num(h.get('qty'))
        if day_pend: pend_days.append({'date': ds, 'names': day_pend})
        d += datetime.timedelta(days=1)
    delivery = [{'k': k, 'name': n, 'q': round(logic.num(v.get(k)), 3)} for k, n in cols if logic.num(v.get(k))]
    delivery += [{'k': 'hand:' + n, 'name': n + '（手工单）', 'q': round(logic.num(q), 3)} for n, q in sorted(hand.items()) if q]
    # ③ 所有地方出入库合计（按产品；出=qty<0，入=qty>0；含出库单/日表/到货/借用等）
    all_out = wh  # 与①同口径
    all_in = rows(c.execute(
        "SELECT p.id, p.name, p.spec, p.unit, SUM(m.qty) q FROM moves m JOIN products p ON p.id=m.product_id "
        "WHERE m.date>=? AND m.date<=? AND m.qty>0 GROUP BY m.product_id ORDER BY q DESC, p.name", (fr, to)))
    for x in all_in: x['q'] = round(logic.num(x['q']), 3)
    return {'from': fr, 'to': to, 'warehouse_out': wh, 'delivery': delivery, 'pending_days': pend_days,
            'all_out': all_out, 'all_in': all_in}

@route('GET', '/api/daily/panel')
def api_daily_panel(c, q, b, me):
    """每日总出库量（看板）：每天所有配送员加起来 —— 40L/10L 出库、实际配送，其他产品当天用量（同财务表），手工单产品。
    待清点的配送员不算进当天（同财务表合计），这一天标「有待清点」"""
    t = today(); fr = q.get('from') or t[:8] + '01'; to = q.get('to') or t
    if to < fr: fr, to = to, fr
    d0 = datetime.date.fromisoformat(fr); d1 = datetime.date.fromisoformat(to)
    if (d1 - d0).days > 92: d0 = d1 - datetime.timedelta(days=92)
    pname = {r['id']: r['name'] for r in c.execute('SELECT id, name FROM products')}
    # 钢瓶总出库 T = 实际配送（更换 J + 新送 L）+ 手工单更换 hc + 手工单新送 hn；回收 r 另列。
    # 以后「新送」要分 租用 / 购买（现在记在纸上，以后从对方系统导入）：拆分放在 parts 里，现在不给
    cols = [('T40', '40L 钢瓶总出库'), ('T10', '10L 钢瓶总出库'), ('o40', '40L 出库'), ('R40', '40L 实际配送'), ('o10', '10L 出库'), ('R10', '10L 实际配送')] + [('net_' + o[0], o[1]) for o in logic.OTHER]
    sub = [(z + k, None) for z in ('J', 'L', 'r', 'hc', 'hn') for k in ('40', '10')]
    days = []; hand_cols = {}
    d = d0
    while d <= d1:
        ds = d.isoformat(); merged = logic.daily_rows(c, ds)
        v = {}; pend = []; merged_n = 0
        for m in merged:
            if m.get('pending'): pend.append(m.get('label') or m['name']); continue
            if m.get('merged_into'): merged_n += 1; continue
            cc = logic.calc_row(m['vals'])
            for k, _ in cols + sub:
                if k[0] == 'T': x = logic.num(cc.get('R' + k[1:])) + logic.num(m['vals'].get('hc' + k[1:])) + logic.num(m['vals'].get('hn' + k[1:]))
                elif k in ('o40', 'o10') or k[:1] in ('r', 'h'): x = logic.num(m['vals'].get(k))
                else: x = logic.num(cc.get(k))
                if x: v[k] = logic.num(v.get(k)) + x
        skip = {m['courier_id'] for m in merged if m.get('pending')}
        for e in c.execute('SELECT courier_id, hand FROM daily_entries WHERE deleted_at IS NULL AND book_date=?', (ds,)):
            if e['courier_id'] in skip: continue
            for h in json.loads(e['hand'] or '[]'):
                n = logic.short_name(c, h.get('product_id'), pname); k = 'hand:' + n; hand_cols[k] = n + '（手工单）' if not h.get('extra') else n
                v[k] = logic.num(v.get(k)) + logic.num(h.get('qty'))
        bd = {z: {'更换': {'v': v.get('J' + z, 0), 'hand': v.get('hc' + z, 0)}, '新送': {'v': v.get('L' + z, 0), 'hand': v.get('hn' + z, 0), 'parts': []}, '回收': {'v': v.get('r' + z, 0)}} for z in ('40', '10')}
        for k in [k for k, _ in sub]: v.pop(k, None)
        days.append({'date': ds, 'v': {k: round(x, 3) for k, x in v.items()}, 'cyl': bd, 'pending': pend, 'merged': merged_n, 'has': bool(merged)})
        d += datetime.timedelta(days=1)
    return {'from': d0.isoformat(), 'to': d1.isoformat(), 'cols': [{'k': k, 'name': n} for k, n in cols + sorted(hand_cols.items())], 'days': days}

@route('GET', '/api/daily/dates')
def api_daily_dates(c, q, b, me):
    return {'items': rows(c.execute('SELECT book_date date, COUNT(*) n, COUNT(DISTINCT courier_id) people FROM daily_entries WHERE deleted_at IS NULL AND book_date IS NOT NULL GROUP BY book_date ORDER BY book_date DESC LIMIT 120'))}

@route('POST', '/api/daily/save', 'entry')
def api_daily_save(c, q, b, me):
    did = logic.save_daily(c, b['data'], me['name']); attach_photos(c, b.get('photo_ids'), 'daily', did); return {'id': did}

@route('POST', '/api/daily/save_many', 'entry')
def api_daily_save_many(c, q, b, me):
    """表格一次保存多行（同一事务）：每行 = 配送员一趟"""
    ids = []
    for d in b.get('items') or []:
        if not d.get('courier_id'): raise ApiError('有一行没有配送员')
        if d.get('out_date') and d.get('book_date') and d['out_date'] > d['book_date']: raise ApiError('领取日不能晚于交回日')
        ids.append(logic.save_daily(c, d, me['name']))
    return {'ids': ids}

@route('POST', '/api/daily/delete', 'delete')
def api_daily_delete(c, q, b, me):
    im = links.impact(c, 'daily', int(b['id']))
    if im['block']: raise ApiError(im['block'])
    soft_delete(c, 'daily', int(b['id']), me['name']); logic.rebuild_daily(c, int(b['id'])); return {'ok': 1}

@route('GET', '/api/daily/export.xlsx')
def api_daily_export(c, q, b, me):
    date = q.get('date') or today()
    data = daily_xlsx(c, date)
    y, m, d = date.split('-')
    return ('file', '%s年%d月%d号产品出入库情况.xlsx' % (y, int(m), int(d)), data)

@route('GET', '/api/daily/print')
def api_daily_print(c, q, b, me):
    """打印：把下载的 Excel（原表格式）原样转成 HTML —— 打印和下载同一份排版"""
    import xlsxhtml
    return {'html': xlsxhtml.to_html(daily_xlsx(c, q.get('date') or today()))}

def daily_xlsx(c, date):
    y, m, d = date.split('-')
    def show(m):
        if m.get('merged_into'): return dict(m, vals={}, note='并入%s号合计' % int(m['merged_into'][8:]))
        if not m.get('pending'): return m
        if m.get('gap'): return dict(m, vals={}, note='待清点（%s早上没清点到，下次早上清点后几天合起来算）' % logic.md(m['next']))
        return dict(m, vals={}, note='待次日清点（等%s早上%s交接表）' % (logic.md(m['next']), '、'.join(m['pending'])))
    merged = [show(m) for m in logic.daily_rows(c, date)]
    return xlsxio.fill_daily(open(TPL_DAILY, 'rb').read(), '%s年%d月%d号产品出入库情况' % (y, int(m), int(d)), merged, logic.CYL,
                             [(o[0], o[2], o[3], o[4]) for o in logic.OTHER], logic.calc_row)

@route('POST', '/api/daily/import', 'entry')
def api_daily_import(c, q, b, me):
    return importers.import_daily(c, b['_raw'], me['name'], as_history=q.get('history', '1') == '1', date_override=q.get('date') or None)

# ---------------- 到货 / 批次 ----------------
@route('GET', '/api/arrivals')
def api_arrivals(c, q, b, me):
    w = ['a.deleted_at IS %s' % ('NOT NULL' if q.get('deleted') == '1' else 'NULL')]; a = []
    if q.get('status'): w.append('a.u8_status=?'); a.append(q['status'])
    if q.get('kind'): w.append('a.kind=?'); a.append(q['kind'])
    if q.get('q'): w.append('(a.name LIKE ? OR a.spec LIKE ? OR a.dest LIKE ? OR a.remark LIKE ? OR a.batch_no LIKE ? OR a.receipt_no LIKE ?)'); a += ['%' + q['q'] + '%'] * 6
    if q.get('from'): w.append('a.date>=?'); a.append(q['from'])
    rs = rows(c.execute('SELECT a.*, p.name pname, p.spec pspec, p.batch_managed FROM arrivals a LEFT JOIN products p ON p.id=a.product_id WHERE %s ORDER BY a.date DESC, a.id DESC LIMIT %d' % (' AND '.join(w), int(q.get('limit') or 400)), a))
    pc = {r[0]: r[1] for r in c.execute("SELECT entity_id, COUNT(*) FROM photos WHERE entity='arrival' AND deleted_at IS NULL GROUP BY entity_id")}
    for r in rs: r['nphotos'] = pc.get(r['id'], 0)
    return {'items': rs, 'pending_u8': c.execute("SELECT COUNT(*) FROM arrivals WHERE deleted_at IS NULL AND u8_status='待入U8'").fetchone()[0]}

@route('GET', '/api/arrival/one')
def api_arrival_one(c, q, b, me):
    a = row(c.execute('SELECT * FROM arrivals WHERE id=?', (int(q['id']),)).fetchone()); a['photos'] = photos_of(c, 'arrival', a['id'])
    a['audit'] = rows(c.execute("SELECT ts,person,action,summary FROM audit WHERE entity='arrival' AND entity_id=? ORDER BY ts", (a['id'],)))
    return a

@route('POST', '/api/arrival/save', 'entry')
def api_arrival_save(c, q, b, me):
    lines = b.get('lines') or [b['data']]; ids = []
    for d in lines:
        if not d.get('product_id') and not d.get('name'): raise ApiError('请选产品或填存货名称')
        if d.get('product_id') and not d.get('name'):
            p = row(c.execute('SELECT * FROM products WHERE id=?', (int(d['product_id']),)).fetchone())
            d['name'] = p['name']; d.setdefault('spec', p['spec']); d.setdefault('unit', p['unit'])
        ids.append(logic.save_arrival(c, d, me['name']))
    for i in ids[:1]: attach_photos(c, b.get('photo_ids'), 'arrival', i, replace=len(lines) == 1 and bool(lines[0].get('id')))
    return {'ids': ids}

@route('POST', '/api/arrival/u8', 'entry')
def api_arrival_u8(c, q, b, me):
    """标记 已入U8 / 不入U8（不用入U8）/ 待入U8（撤销）。返回改前状态，前端可一键撤销"""
    prev = []
    for it in b['items']:
        a = row(c.execute('SELECT id,u8_status,inv_code,receipt_no FROM arrivals WHERE id=?', (int(it['id']),)).fetchone())
        if not a: continue
        prev.append({'id': a['id'], 'u8_status': a['u8_status'], 'inv_code': a['inv_code'], 'receipt_no': a['receipt_no']})
        st = it.get('u8_status', '已入U8')
        if st not in ('已入U8', '不入U8', '待入U8'): raise ApiError('状态不对')
        d = {'id': a['id'], 'u8_status': st}
        for k in ('inv_code', 'receipt_no'):
            if it.get(k) is not None: d[k] = it[k]
        d['u8_at'] = now() if st == '已入U8' else None
        lab = {'已入U8': '标记已入U8', '不入U8': '标记不用入U8', '待入U8': '撤销为待入U8'}[st]
        save_row(c, 'arrival', d, me['name'], ('%s %s' % (lab, ' '.join(str(it.get(k) or '') for k in ('inv_code', 'receipt_no')))).strip() + (('（%s）' % b['note']) if b.get('note') else ''))
    return {'ok': 1, 'prev': prev}

@route('POST', '/api/arrival/delete', 'delete')
def api_arrival_delete(c, q, b, me):
    soft_delete(c, 'arrival', int(b['id']), me['name']); logic.rebuild_arrival(c, int(b['id'])); return {'ok': 1}

@route('GET', '/api/batches')
def api_batches(c, q, b, me):
    ps = rows(c.execute('SELECT * FROM products WHERE batch_managed=1 AND deleted_at IS NULL AND merged_into IS NULL ORDER BY sort,id'))
    lim = (datetime.date.today() + datetime.timedelta(days=int(logic.settings(c).get('expiry_alert_days') or 90))).isoformat()
    for p in ps:
        p['label'] = plabel(p); p['batches'] = logic.batch_stock(c, p['id'])
        p['batch_trusted'] = logic.batch_remain_trusted(c, p['id'])
        for x in p['batches']: x['expiring'] = bool(x.get('expiry')) and x['expiry'] <= lim
    return {'items': ps}

def trace(c, pid, bn):
    p = row(c.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone())
    bt = row(c.execute('SELECT * FROM batches WHERE product_id=? AND batch_no=?', (pid, bn)).fetchone()) or {}
    ms = rows(c.execute('SELECT * FROM moves WHERE product_id=? AND batch_no=? ORDER BY date, ts', (pid, bn)))
    out = []; bal = 0
    for m in ms:
        bal += m['qty']; who = m['label']
        if m['src'] == 'out':
            o = row(c.execute('SELECT * FROM out_orders WHERE id=?', (m['src_id'],)).fetchone())
            who = '%s %s %s' % (o['kind'], o['customer'] or o['recipient'] or '', o['phone'] or '')
        elif m['src'] == 'arrival':
            a = row(c.execute('SELECT * FROM arrivals WHERE id=?', (m['src_id'],)).fetchone())
            who = '%s %s %s' % (a['kind'], a['supplier'] or '', a['dest'] or '')
        out.append({'date': m['date'], 'type': '入' if m['qty'] > 0 else '出', 'who': who.strip(), 'in': m['qty'] if m['qty'] > 0 else '', 'out': -m['qty'] if m['qty'] < 0 else '', 'bal': round(bal, 3)})
    return p, bt, out

@route('GET', '/api/batch/trace')
def api_batch_trace(c, q, b, me):
    p, bt, out = trace(c, int(q['product_id']), q['batch_no'])
    return {'product': plabel(p), 'batch': bt, 'rows': out}

@route('GET', '/api/batch/trace.xlsx')
def api_batch_trace_x(c, q, b, me):
    pid = int(q['product_id']); sheets = []
    bns = [q['batch_no']] if q.get('batch_no') else [x['batch_no'] for x in logic.batch_stock(c, pid)]
    summ = []; p = row(c.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone())
    if not p: raise ApiError('没有这个产品', 404)
    if not bns: return table_result(q, '批次追溯_%s.xlsx' % plabel(p), [('批次汇总', '%s 还没有批次记录' % plabel(p), ['批号', '生产日期', '有效期', '到货', '出库', '剩余', '备注'], [], [14, 12, 12, 9, 9, 9, 24])])
    for bn in bns:
        p, bt, out = trace(c, pid, bn)
        sheets.append((bn or '无批号', '%s 批号 %s 追溯（生产日期 %s，有效期 %s%s）' % (plabel(p), bn, bt.get('prod_date') or '—', bt.get('expiry') or '—', ('，备注：' + bt['remark']) if bt.get('remark') else ''),
                       ['日期', '入/出', '来源/去向（客户、电话）', '入库数', '出库数', '结存'], [[r['date'], r['type'], r['who'], r['in'], r['out'], r['bal']] for r in out], [12, 7, 44, 9, 9, 9]))
        summ.append([bn, bt.get('prod_date', ''), bt.get('expiry', ''), sum(r['in'] or 0 for r in out), sum(r['out'] or 0 for r in out), out[-1]['bal'] if out else 0, bt.get('remark') or ''])
    if len(bns) > 1:
        sheets.insert(0, ('批次汇总', '%s 批次汇总（%s）' % (plabel(p), today()), ['批号', '生产日期', '有效期', '到货', '出库', '剩余', '备注'], summ, [14, 12, 12, 9, 9, 9, 24]))
    return table_result(q, '批次追溯_%s_%s.xlsx' % (plabel(p), q.get('batch_no') or '全部'), sheets)

@route('POST', '/api/batch/save', 'entry')
def api_batch_save(c, q, b, me):
    d = b['data']; return {'id': save_row(c, 'batch', d, me['name'])}

# ---------------- 待补全 ----------------
@route('GET', '/api/pending')
def api_pending(c, q, b, me):
    w = 'deleted_at IS NULL'; a = []
    if q.get('status'): w += ' AND status=?'; a.append(q['status'])
    if q.get('mine'): w += ' AND (handler=? OR created_by=?)'; a += [q['mine'], q['mine']]
    rs = rows(c.execute('SELECT * FROM pending WHERE %s ORDER BY status DESC, date' % w, a))
    np = {r[0]: r[1] for r in c.execute("SELECT entity_id, COUNT(*) FROM photos WHERE entity='pending' AND deleted_at IS NULL GROUP BY entity_id")}
    for r in rs: r['age'] = age_days(r['date']); r['nphotos'] = np.get(r['id'], 0)
    by = {}
    for r in rs:
        if r['status'] != '待补全': continue
        k = r['taker'] or '（未写）'; by.setdefault(k, {'pending': 0}); by[k]['pending'] += 1
    for l in rows(c.execute("SELECT handler, COUNT(*) n FROM loans WHERE deleted_at IS NULL AND status IN ('未归还','部分归还') GROUP BY handler")):
        by.setdefault(l['handler'] or '（未写）', {'pending': 0})['loans'] = l['n']
    return {'items': rs, 'by_person': by}

@route('POST', '/api/pending/save', 'entry')
def api_pending_save(c, q, b, me):
    d = b['data']; d.setdefault('date', today()); d.setdefault('handler', me['name'])
    pid = save_row(c, 'pending', d, me['name'], None if d.get('id') else '待补全：%s 拿 %s %s' % (d.get('taker', ''), d.get('what', ''), d.get('qty', '')))
    attach_photos(c, b.get('photo_ids'), 'pending', pid); return {'id': pid}

@route('GET', '/api/pending/photos')
def api_pending_photos(c, q, b, me): return {'items': photos_of(c, 'pending', int(q['id']))}

@route('POST', '/api/pending/close', 'entry')
def api_pending_close(c, q, b, me):
    save_row(c, 'pending', {'id': int(b['id']), 'status': b.get('status', '已补全'), 'close_note': b.get('note', '')}, me['name'], '%s：%s' % (b.get('status', '已补全'), b.get('note', '')))
    return {'ok': 1}

@route('GET', '/api/pending/list.xlsx')
def api_pending_x(c, q, b, me):
    rs = rows(c.execute("SELECT * FROM pending WHERE deleted_at IS NULL AND date>=? ORDER BY taker, date", (q.get('from') or '2000-01-01',)))
    return table_result(q, '待补全清单_%s.xlsx' % today(), [('待补全', '待补全清单（%s 起）' % (q.get('from') or '全部'), ['日期', '谁拿的', '拿了什么', '数量', '客户/说明', '经手', '状态', '备注'],
                                [[r['date'], r['taker'], r['what'], r['qty'], r['customer'], r['handler'], r['status'], '；'.join(x for x in (r.get('remark'), r['close_note']) if x)] for r in rs], [11, 10, 22, 7, 22, 8, 9, 22])])

# ---------------- 库房杂物（暂存/工程/未知，不计库存） ----------------
@route('GET', '/api/misc')
def api_misc(c, q, b, me):
    w = 'deleted_at IS NULL'; a = []
    if q.get('category'): w += ' AND category=?'; a.append(q['category'])
    if q.get('status'): w += ' AND status=?'; a.append(q['status'])
    if q.get('q'): w += ' AND (name LIKE ? OR descr LIKE ? OR location LIKE ? OR placed_by LIKE ? OR remark LIKE ? OR result_note LIKE ?)'; a += ['%' + q['q'] + '%'] * 6
    rs = rows(c.execute('SELECT * FROM temp_items WHERE %s ORDER BY status="在库" DESC, date DESC, id DESC' % w, a))
    for r in rs: r['photos'] = photos_of(c, 'temp', r['id']); r['age'] = age_days(r['date'])
    return {'items': rs}

@route('POST', '/api/misc/save', 'entry')
def api_misc_save(c, q, b, me):
    d = b['data']; d.setdefault('date', today())
    if not d.get('id') and not (d.get('name') or d.get('descr')) and not b.get('photo_ids'): raise ApiError('拍张照或写个暂用叫法')
    i = save_row(c, 'temp', d, me['name'], None if d.get('id') else '库房杂物登记：%s' % (d.get('name') or d.get('descr') or '（照片）'))
    attach_photos(c, b.get('photo_ids'), 'temp', i, replace=bool(d.get('id'))); return {'id': i}

@route('POST', '/api/misc/action', 'entry')
def api_misc_action(c, q, b, me):
    i = int(b['id']); act = b['action']; t = row(c.execute('SELECT * FROM temp_items WHERE id=?', (i,)).fetchone())
    if act == 'taken':
        save_row(c, 'temp', {'id': i, 'status': '已取走', 'done_date': b.get('date') or today(), 'result_note': b.get('note', '')}, me['name'], '标记已取走 ' + b.get('note', ''))
    elif act == 'back':
        save_row(c, 'temp', {'id': i, 'status': '在库', 'done_date': ''}, me['name'], '恢复为在库')
    elif act == 'convert':
        pid = b.get('product_id')
        if not pid:
            nm = (b.get('name') or t['name'] or '').strip()
            if not nm: raise ApiError('请填正式产品名称')
            pid = logic.find_product(c, nm)
            pid = pid['id'] if pid else save_row(c, 'product', {'name': nm, 'spec': b.get('spec', ''), 'unit': b.get('unit') or '个',
                                                                  'category': '工程材料' if t['category'] == '工程' else '其他', 'location': t['location']}, me['name'], '由库房杂物转入')
        aid = None; qty = float(b.get('qty') or 0)
        if qty > 0:
            aid = logic.save_arrival(c, {'date': b.get('date') or today(), 'kind': '其他入库', 'product_id': int(pid), 'name': importers.pname(c, int(pid)), 'qty': qty,
                                         'unit': b.get('unit') or '', 'remark': '库房杂物转正式入库（#%d %s）' % (i, t['name'] or t['descr']), 'u8_status': b.get('u8_status') or '待入U8'}, me['name'])
        save_row(c, 'temp', {'id': i, 'status': '已转入库', 'product_id': int(pid), 'arrival_id': aid, 'done_date': today()}, me['name'], '转正式入库 → 产品 #%s 数量 %g' % (pid, qty))
    else: raise ApiError('未知操作')
    return {'ok': 1}

# ---------------- 设置 / 人员 / 配送员 ----------------
@route('GET', '/api/people')
def api_people(c, q, b, me):
    ps = rows(c.execute('SELECT id,name,role,perms,active,sort,pin_hash IS NOT NULL has_pin FROM people ORDER BY sort,id'))
    for p in ps: p['perms'] = json.loads(p['perms'] or '{}')
    return {'items': ps, 'perm_keys': db.PERM_KEYS, 'all_open': meta_get(c, 'perms_all_open', True)}

@route('POST', '/api/person/save', 'settings')
def api_person_save(c, q, b, me):
    d = dict(b['data']); newpin = (d.pop('new_pin', '') or '').strip()
    if 'perms' in d and isinstance(d['perms'], dict): d['perms'] = json.dumps(d['perms'], ensure_ascii=False)
    if newpin:
        if not re.fullmatch(r'\d{4}', newpin): raise ApiError('密码请用 4 位数字')
        h = db.pin_hash(c, newpin)
        if c.execute('SELECT 1 FROM people WHERE pin_hash=? AND id<>?', (h, d.get('id') or 0)).fetchone(): raise ApiError('这个密码已有人用，请换一个（密码即身份，不能重复）')
        d['pin_hash'] = h
    pid = save_row(c, 'person', d, me['name'], ('修改密码 ' if newpin else '') + (d.get('name') or ''))
    return {'id': pid}

@route('POST', '/api/settings/save', 'settings')
def api_settings_save(c, q, b, me):
    s = meta_get(c, 'settings', {}) or {}; before = json.loads(json.dumps(s)); d = dict(b.get('data') or {})
    if 'ui_names' in d:
        tmp = {**s, **{k: v for k, v in d.items() if k != 'ui_names'}}
        d['ui_names'] = logic.clean_names(d['ui_names'], logic.name_originals(tmp), tmp.get('out_kinds') or s.get('out_kinds'))
    for k in ('print', 'defaults', 'ocr'):  # 分组设置：只合并改到的字段
        if isinstance(d.get(k), dict): d[k] = {**logic.DEFAULT_SETTINGS[k], **(s.get(k) or {}), **d[k]}
    if 'print_templates' in d:
        d['print_templates'] = printpage.clean_templates(d.get('print_templates'))
    if 'report_order' in d: d['report_order'] = [k for k in dict.fromkeys(d['report_order'] or []) if k in reports.TABS]
    if 'nav_order' in d:
        NAV = ('home', 'out', 'daily', 'loan', 'arrival', 'stock', 'misc', 'report', 'print', 'slip', 'backup')  # settings 不参与排序
        d['nav_order'] = [k for k in dict.fromkeys(d['nav_order'] or []) if k in NAV]
    if 'nav_hidden' in d:
        NAV = ('home', 'out', 'daily', 'loan', 'arrival', 'stock', 'misc', 'report', 'print', 'slip', 'backup')
        d['nav_hidden'] = [k for k in dict.fromkeys(d['nav_hidden'] or []) if k in NAV and k not in ('home',)]  # 首页不可藏
    if 'guest_orgs' in d: d['guest_orgs'] = list(dict.fromkeys(str(x).strip() for x in d['guest_orgs'] if str(x).strip()))
    if 'site_name' in d: d['site_name'] = str(d['site_name']).strip()[:30] or logic.DEFAULT_SETTINGS['site_name']
    s.update(d); s.pop('self_pickup_in_daily', None); meta_set(c, 'settings', s)
    if 'perms_all_open' in b: meta_set(c, 'perms_all_open', bool(b['perms_all_open']))
    if 'daily_map' in b: meta_set(c, 'daily_map', b['daily_map']); logic.rebuild_all(c)
    s.pop('self_pickup_in_daily', None)
    audit(c, me['name'], '修改', 'settings', 0, settings_summary(before, s) + ('；数据对应已改' if 'daily_map' in b else ''), before, s)
    return {'ok': 1}

SET_CN = {'site_name': '系统名称', 'ui_names': '名称设置', 'print': '打印', 'defaults': '常用默认值', 'ocr': '识别', 'guest_orgs': '借用单位',
          'backup_dir': '备份位置', 'backup_keep': '备份保留份数', 'expiry_alert_days': '效期提醒天数', 'pin_cache_minutes': '密码记住分钟',
          'outside_base': '在外起始数', 'u8_types': 'U8单细分', 'out_kinds': '出库类型', 'sources': '单据来源', 'categories': '产品分类',
          'misc_categories': '杂物分类', 'paper_plates': '车牌', 'report_order': '报表页签顺序', 'nav_order': '顶部导航', 'nav_hidden': '顶栏隐藏项', 'moves_show_daily': '库存流水里显示交接表批量配送',
          'print_templates': '打印单模板'}

def settings_summary(before, after):
    ch = []
    for k in list(dict.fromkeys(list(after) + list(before))):
        a, b_ = before.get(k), after.get(k)
        if json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(b_, sort_keys=True, ensure_ascii=False): continue
        if k == 'ui_names':
            a = a or {}; b_ = b_ or {}
            for o in list(dict.fromkeys(list(b_) + list(a))):
                if a.get(o) != b_.get(o): ch.append('名称「%s」：%s → %s' % (o, a.get(o) or '默认', b_.get(o) or '恢复默认'))
        else: ch.append('%s：%s → %s' % (SET_CN.get(k, k), json.dumps(a, ensure_ascii=False) if a is not None else '默认', json.dumps(b_, ensure_ascii=False)))
    return ('；'.join(ch) or '设置未变')[:900]

@route('POST', '/api/courier/save', 'settings')
def api_courier_save(c, q, b, me):
    d = b['data']
    if not d.get('id'): d.setdefault('sort', (c.execute('SELECT COALESCE(MAX(sort),0) FROM couriers').fetchone()[0] or 0) + 10)
    return {'id': save_row(c, 'courier', d, me['name'])}

@route('POST', '/api/courier/delete', 'delete')
def api_courier_delete(c, q, b, me): soft_delete(c, 'courier', int(b['id']), me['name']); return {'ok': 1}

# ---------------- 照片 ----------------
@route('POST', '/api/photo')
def api_photo(c, q, b, me):
    return upq.save_photo(c, b.get('data'), b.get('name', ''), b.get('entity', ''), b.get('entity_id'), b.get('tag', ''), b.get('by', ''), b.get('token'))

@route('POST', '/api/photo/rotate')
def api_photo_rotate(c, q, b, me):
    """看大图点 ⟳：立刻覆盖原文件（不用另点保存）。免密码，与上传照片相同。"""
    return upq.replace_photo(c, b.get('data'), path=b.get('path'), photo_id=b.get('id'), by=b.get('by', ''))

# 手工单照片：每个配送员每天一组（可多张，对账备用，不打印）。按 日期 + 配送员 存（entity='hand', entity_id=配送员, tag=日期），交接表重算不影响
@route('GET', '/api/hand_photos')
def api_hand_photos(c, q, b, me):
    return {'items': rows(c.execute("SELECT id, path, name, created_at, created_by FROM photos WHERE entity='hand' AND entity_id=? AND tag=? AND deleted_at IS NULL ORDER BY id",
                                    (int(q['courier_id']), q['date'])))}

@route('POST', '/api/hand_photos/attach', 'entry')
def api_hand_photos_attach(c, q, b, me):
    date = str(b.get('date') or ''); cid = int(b['courier_id'])
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date): raise ApiError('日期不对')
    k = row(c.execute('SELECT name FROM couriers WHERE id=?', (cid,)).fetchone())
    if not k: raise ApiError('没有这个配送员')
    n = 0
    for i in b.get('ids') or []:
        n += c.execute("UPDATE photos SET entity='hand', entity_id=?, tag=? WHERE id=? AND deleted_at IS NULL AND (entity='' OR entity IS NULL OR (entity='hand' AND entity_id=? AND tag=?))", (cid, date, int(i), cid, date)).rowcount
    if n: audit(c, me['name'], '新增', 'photo', cid, '手工单照片 %d 张 → %s %s' % (n, date, k['name']))
    return {'n': n}

@route('POST', '/api/photo/delete', 'entry')
def api_photo_delete(c, q, b, me): soft_delete(c, 'photo', int(b['id']), me['name']); return {'ok': 1}

@route('GET', '/api/inbox')
def api_inbox(c, q, b, me):
    return {'items': rows(c.execute('SELECT p.id, p.path FROM photo_inbox i JOIN photos p ON p.id=i.photo_id WHERE i.token=? ORDER BY i.created_at', (q['token'],)))}

@route('GET', '/api/qr.svg')
def api_qr(c, q, b, me):
    import segno
    out = io.BytesIO(); segno.make(q['text'], error='m').save(out, kind='svg', scale=4, border=2, dark='#1d2129')
    return ('raw', 'image/svg+xml', out.getvalue())

# ---------------- 留痕 / 回收站 ----------------
@route('GET', '/api/audit')
def api_audit(c, q, b, me):
    w = '1=1'; a = []
    if q.get('entity'): w += ' AND entity=?'; a.append(q['entity'])
    if q.get('id'): w += ' AND entity_id=?'; a.append(int(q['id']))
    if q.get('person'): w += ' AND person=?'; a.append(q['person'])
    rs = rows(c.execute('SELECT id,ts,person,action,entity,entity_id,summary FROM audit WHERE %s ORDER BY ts DESC LIMIT %d' % (w, int(q.get('limit') or 300)), a))
    for r in rs: r['entity_cn'] = db.ENTITY_CN.get(r['entity'], r['entity'])
    return {'items': rs}

TRASH = [('out', 'out_orders', "kind||' '||customer||recipient"), ('arrival', 'arrivals', "name||' '||spec||' ×'||qty"), ('daily', 'daily_entries', "'产品出入库情况 '||out_date"),
         ('product', 'products', "name||' '||spec"), ('loan', 'loans', "'借用 '||user_to||unit"), ('pending', 'pending', "taker||' '||what"),
         ('temp', 'temp_items', "category||' '||name||descr"), ('courier', 'couriers', 'name'), ('count', 'stock_counts', "'盘点 '||qty"), ('photo', 'photos', 'path'),
         ('slip', 'weigh_slips', "'称重单 '||COALESCE(serial,'')||' '||COALESCE(car_no,'')"), ('paper', 'paper_sheets', "'交接表 '||date||' '||session||' '||CASE form WHEN 'cyl' THEN '钢瓶' ELSE '产品' END"),
         ('loan_return', 'loan_returns', "'归还 '||date")]

@route('GET', '/api/trash')
def api_trash(c, q, b, me):
    out = []
    for ent, t, lab in TRASH:
        extra = ' AND merged_into IS NULL' if t == 'products' else ''
        for r in c.execute('SELECT id, deleted_at, deleted_by, %s FROM %s WHERE deleted_at IS NOT NULL%s ORDER BY deleted_at DESC LIMIT 200' % (lab, t, extra)):
            out.append({'entity': ent, 'entity_cn': db.ENTITY_CN[ent], 'id': r[0], 'deleted_at': r[1], 'deleted_by': r[2], 'label': r[3]})
    reports.ensure_schema(c)
    for t in rows(c.execute('SELECT id,key,label,deleted_at,deleted_by FROM report_trash WHERE restored_at IS NULL ORDER BY deleted_at DESC LIMIT 200')):
        out.append({'entity': 'report_row', 'entity_cn': '报表行', 'id': t['id'], 'deleted_at': t['deleted_at'], 'deleted_by': t['deleted_by'], 'label': t['label']})
    out.sort(key=lambda x: -(x['deleted_at'] or 0))
    return {'items': out}

@route('POST', '/api/restore', 'delete')
def api_restore(c, q, b, me):
    ent = b['entity']; i = int(b['id'])
    if ent == 'report_row': return reports.restore_row(c, i, me['name'])
    if ent == 'daily':   # 交接表生成的记录：交接表还在就以交接表为准（避免重复），交接表也删了就请恢复交接表
        d = row(c.execute('SELECT legacy FROM daily_entries WHERE id=?', (i,)).fetchone()) or {}
        if (d.get('legacy') or '').startswith('paper:'):
            sh = row(c.execute('SELECT date, session, deleted_at FROM paper_sheets WHERE id=?', (int(d['legacy'].split(':')[1]),)).fetchone())
            if sh: raise ApiError('这条是交接表 %s %s 生成的：%s' % (sh['date'], sh['session'], '请恢复那张交接表（会自动重新生成）' if sh['deleted_at'] else '交接表里已经是最新的了，请到交接表里改'))
    restore(c, ent, i, me['name'])
    if ent in logic.REBUILD: logic.REBUILD[ent](c, i)
    if ent == 'paper': paper.sync(c, i, me['name'])
    if ent == 'loan_return': loans.recompute(c, row(c.execute('SELECT loan_id FROM loan_returns WHERE id=?', (i,)).fetchone())['loan_id'])
    return {'ok': 1}

# ---------------- 备份 / 导出导入 ----------------
@route('POST', '/api/backup/now', 'backup')
def api_backup_now(c, q, b, me):
    c.commit(); r = backup.backup_now('手动（%s）' % me['name']); audit(c, me['name'], '备份', 'backup', 0, r['name']); return r

@route('GET', '/api/backup/list')
def api_backup_list(c, q, b, me):
    return {'items': backup.list_backups(), 'last': meta_get(c, 'last_backup', None), 'dir': logic.settings(c).get('backup_dir', ''), 'local': backup.BK_DIR}

@route('GET', '/api/backup/file')
def api_backup_file(c, q, b, me):
    n = os.path.basename(q['name']); p = os.path.join(backup.BK_DIR, n)
    if not os.path.isfile(p): raise ApiError('文件不存在', 404)
    return ('file', n, _readb(p))

@route('GET', '/api/export.zip')
def api_export(c, q, b, me):
    c.commit(); import tempfile
    p = os.path.join(tempfile.mkdtemp(), 'x.zip'); backup.make_zip(p)
    return ('file', '库房全部数据_%s.zip' % datetime.datetime.now().strftime('%Y%m%d_%H%M'), _readb(p))

@route('POST', '/api/import', 'backup')
def api_import(c, q, b, me):
    c.commit(); r = backup.restore_zip(b['_raw'])
    c2 = db.init(); guest.ensure_schema(c2); reports.ensure_schema(c2); upgrade(c2); audit(c2, me['name'], '导入', 'backup', 0, '导入/恢复全部数据（导入前已自动备份 %s）' % r['safety_backup']); c2.commit(); c2.close()
    _tl.clear()
    return r

@route('GET', '/api/legacy/lox.xlsx')
def api_legacy_lox(c, q, b, me):
    lox = meta_get(c, 'legacy_lox_arrivals', []) or []
    rs = [[a.get('date'), a.get('place'), '；'.join('%s %s %s' % (s.get('date', ''), s.get('place', ''), s.get('qty', '')) for s in a.get('stops') or []), a.get('qty'), a.get('remark'), a.get('operator'), len([p for p in a.get('photos') or [] if p])] for a in lox]
    return ('file', '旧系统液氧到货_留底.xlsx', xlsxio.simple_xlsx([('液氧到货', '旧系统「液氧到货」数据留底', ['日期', '卸点', '分段', '合计(吨)', '备注', '经办', '照片数'], rs, [11, 18, 44, 9, 18, 8, 7])]))

# ---------------- 服务 ----------------
def lan_urls():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('10.255.255.255', 1)); ips.add(s.getsockname()[0]); s.close()
    except Exception: pass
    try:
        for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET): ips.add(i[4][0])
    except Exception: pass
    port = PORT
    return ['http://%s:%d' % (ip, port) for ip in sorted(ips) if not ip.startswith('127.')] or ['http://127.0.0.1:%d' % port]

PORT = int(os.environ.get('WH_PORT') or 8080)
# Windows 注册表里的 MIME 可能被别的软件改坏（如 .js → text/plain），这里固定常用类型
for _ext, _ct in {'.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml', '.png': 'image/png',
                  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.json': 'application/json', '.zip': 'application/zip',
                  '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}.items():
    mimetypes.add_type(_ct, _ext)

class H(BaseHTTPRequestHandler):
    server_version = 'Warehouse/' + version.VERSION
    def log_message(self, fmt, *a):
        if os.environ.get('WH_QUIET') or sys.stderr is None: return
        if getattr(sys.stderr, 'stamped', False): sys.stderr.write('%s %s\n' % (self.client_address[0], fmt % a))
        else: sys.stderr.write('%s %s\n' % (datetime.datetime.now().strftime('%H:%M:%S'), fmt % a))
    def send(self, code, body, ctype='application/json; charset=utf-8', extra=None):
        if isinstance(body, (dict, list)): body = json.dumps(body, ensure_ascii=False, default=str).encode('utf-8')
        elif isinstance(body, str): body = body.encode('utf-8')
        self.send_response(code); self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(body)
    def do_GET(self): self.handle_req('GET')
    def do_POST(self): self.handle_req('POST')
    def handle_req(self, method):
        u = urllib.parse.urlparse(self.path); path = urllib.parse.unquote(u.path)
        q = {k: v[-1] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
        if path.startswith('/api/guest/'): return self.guest_api(method, path, q)
        if path.startswith('/api/'): return self.api(method, path, q)
        if path.startswith('/photos/'):
            p = os.path.normpath(os.path.join(db.PHOTO_DIR, path[8:]))
            if not p.startswith(os.path.normpath(db.PHOTO_DIR)) or not os.path.isfile(p): return self.send(404, '没有这张照片', 'text/plain; charset=utf-8')
            return self.send(200, _readb(p), mimetypes.guess_type(p)[0] or 'image/jpeg', {'Cache-Control': 'max-age=86400'})
        if path.startswith('/print_files/'):
            p = printpage.serve_path(path[len('/print_files/'):])
            if not p: return self.send(404, '没有这个文件', 'text/plain; charset=utf-8')
            ct = mimetypes.guess_type(p)[0] or 'application/octet-stream'
            return self.send(200, _readb(p), ct, {'Cache-Control': 'no-store', 'Content-Disposition': "inline; filename*=UTF-8''" + urllib.parse.quote(os.path.basename(p))})
        if path in ('/', ''): path = '/index.html'
        if path in ('/m', '/m/'): path = '/m/index.html'
        if path in ('/m/guest', '/m/guest/'): path = '/m/guest.html'
        p = os.path.normpath(os.path.join(STATIC, path.lstrip('/')))
        if not p.startswith(os.path.normpath(STATIC)) or not os.path.isfile(p): return self.send(404, 'Not found', 'text/plain')
        ct = mimetypes.guess_type(p)[0] or 'application/octet-stream'
        if ct.startswith('text/') or ct in ('application/javascript',): ct += '; charset=utf-8'
        self.send(200, _readb(p), ct, {'Cache-Control': 'no-cache'})
    def api(self, method, path, q):
        r = ROUTES.get((method, path))
        if not r: return self.send(404, {'error': '没有这个接口：' + path})
        fn, perm = r
        n = int(self.headers.get('Content-Length') or 0); raw = self.rfile.read(n) if n else b''
        ctype = self.headers.get('Content-Type') or ''
        b = {}
        if raw and 'json' in ctype: b = json.loads(raw.decode('utf-8'))
        elif raw: b = {'_raw': raw}
        pin = b.get('pin') if isinstance(b, dict) else None
        pin = pin or self.headers.get('X-PIN') or ''
        c = db_c()
        try:
            with db.WRITE_LOCK if method == 'POST' else _Null():
                me = None
                if method == 'POST' and path not in ('/api/photo', '/api/photo/rotate') + upq.EXEMPT + plib.EXEMPT:
                    me = person_by_pin(c, pin); check_perm(me, perm)
                res = fn(c, q, b, me)
                c.commit()  # GET 也可能写（报表首次播种等），一律提交，免得占着写锁
            if isinstance(res, tuple) and res[0] == 'file':
                _, name, data = res
                ct = mimetypes.guess_type(name)[0] or 'application/octet-stream'
                return self.send(200, data, ct, {'Content-Disposition': "attachment; filename*=UTF-8''" + urllib.parse.quote(name)})
            if isinstance(res, tuple) and res[0] == 'raw': return self.send(200, res[2], res[1])
            return self.send(200, res)
        except ApiError as e:
            c.rollback(); return self.send(e.code, {'error': str(e)})
        except ValueError as e:
            c.rollback(); return self.send(400, {'error': str(e)})
        except Exception as e:
            c.rollback(); traceback.print_exc(); return self.send(500, {'error': '出错了：%s' % e})

    def guest_api(self, method, path, q):
        """访客接口：只认 guest.GUEST_ROUTES 里的，不要密码，不能碰任何员工接口"""
        fn = guest.GUEST_ROUTES.get((method, path))
        if not fn: return self.send(404, {'error': '没有这个接口'})
        n = int(self.headers.get('Content-Length') or 0)
        if n > guest.MAX_BODY: self.close_connection = True; return self.send(413, {'error': '内容太大（照片太多或太大）'})
        b = {}
        if n:
            try: b = json.loads(self.rfile.read(n).decode('utf-8'))
            except Exception: return self.send(400, {'error': '提交的内容不对'})
            if not isinstance(b, dict): return self.send(400, {'error': '提交的内容不对'})
        ip = self.client_address[0]; c = db_c()
        try:
            with db.WRITE_LOCK if method == 'POST' else _Null():
                res = fn(c, q, b, ip); c.commit()
            return self.send(200, res)
        except ApiError as e:
            c.rollback(); return self.send(e.code, {'error': str(e)})
        except Exception as e:
            c.rollback(); traceback.print_exc(); return self.send(500, {'error': '出错了，请找库房人员'})

class _Null:
    def __enter__(self): return self
    def __exit__(self, *a): return False

def bootstrap():
    c = db.init(); guest.ensure_schema(c); reports.ensure_schema(c); printpage.ensure_dir()
    if not c.execute('SELECT 1 FROM people').fetchone():
        for i, (n, pin) in enumerate([('演示管理员', '1001'), ('演示录入甲', '1002'), ('演示录入乙', '1003'), ('演示录入丙', '1004')]):
            c.execute('INSERT INTO people(name,pin_hash,role,perms,sort,created_at,created_by) VALUES(?,?,?,?,?,?,?)',
                      (n, db.pin_hash(c, pin), '管理员' if i == 0 else '录入', json.dumps({k: True for k, _ in db.PERM_KEYS}), i, now(), '系统'))
        meta_set(c, 'initial_pins', '1001/1002/1003/1004')
    c.commit(); return c

def first_run_seed(c):
    """首次启动：若存在 seed/ 下真实迁移文件则导入（公开发布包不含这些文件）。测试数据请用 python tools/seed_demo.py。"""
    if meta_get(c, 'seeded'): return
    base = db.BASE; seed = os.path.join(base, 'seed')
    js = os.path.join(seed, '库房合并数据_v2.json')
    if os.path.isfile(js):
        rep = importers.migrate_v82(c, json.load(open(js, encoding='utf-8')), '迁移'); meta_set(c, 'migration_report', rep); print('迁移 v82 数据：', {k: v for k, v in rep.items() if k != 'unmatched_items'})
    if os.path.isfile(u8.SEED): print('U8 目录：', u8.seed(c, '迁移'))
    dx = os.path.join(seed, '产品出入库情况_10.17.xlsx')
    if os.path.isfile(dx): print('配送员名单：', importers.import_daily(c, open(dx, 'rb').read(), '迁移', as_history=True))
    ax = os.path.join(seed, '库存及到货总数.xlsx')
    if os.path.isfile(ax): print('到货历史行：', importers.import_arrivals_sheet(c, open(ax, 'rb').read(), '迁移'))
    meta_set(c, 'seeded', True); c.commit()

def upgrade(c):
    """每次启动都跑，各项只做一次（有标记）"""
    try:
        ch = reports.migrate_links(c); c.commit()
        if ch: print('升级：换算表 → 入出库记录 已重算：', '；'.join(ch))
    except Exception:
        c.rollback(); traceback.print_exc()
    try:
        n = paper.migrate_nextday(c); c.commit()
        if n: print('升级：次日清点规则重算了 %d 张早上交接表（%s 以后）' % (n, paper.nextday_from(c)))
    except Exception:
        c.rollback(); traceback.print_exc()
    try:
        if migrate_out_kind_exchange(c): c.commit(); print('升级：出库类型已加入「换货」')
        else: c.commit()
    except Exception:
        c.rollback(); traceback.print_exc()
    try:
        dropped = migrate_ui_names_dupes(c)
        c.commit()
        if dropped: print('升级：名称设置已去掉撞名别名：', '、'.join(dropped))
    except Exception:
        c.rollback(); traceback.print_exc()
    try:
        info = migrate_out_kind_ziti_1134(c)
        c.commit()
        if info and info.get('orders'):
            print('升级：出库类型「自提出库」已合并为「客户自提」：%d 张单' % info['orders'])
        elif info is not None:
            print('升级：出库类型「自提出库」→「客户自提」合并标记已写入（无待改单据）')
    except Exception:
        c.rollback(); traceback.print_exc()

def migrate_ui_names_dupes(c):
    """1.1.30：清掉名称设置里会让界面看起来重复的别名（待提出库→自提出库 等）。不删 out_kinds「自提出库」芯片。"""
    if meta_get(c, 'mig_ui_names_dupes_1130'): return []
    s = meta_get(c, 'settings', {}) or {}
    before = dict(s.get('ui_names') or {})
    # 用当前 settings 做撞名扫描（含已 merge 的出库类型）
    kinds = logic._merge_default_list(s.get('out_kinds'), logic.DEFAULT_SETTINGS['out_kinds'], before='其他出库')
    tmp = dict(s); tmp['out_kinds'] = kinds
    after = logic.clean_names(before, logic.name_originals(tmp), kinds)
    dropped = sorted(k for k in before if k not in after)
    if after != before:
        s['ui_names'] = after
        meta_set(c, 'settings', s)
    meta_set(c, 'mig_ui_names_dupes_1130', True)
    return dropped

def migrate_out_kind_exchange(c):
    """1.1.26：已保存的 settings.out_kinds 补上「换货」（读时也会 merge，这里写入以免只靠内存）"""
    if meta_get(c, 'mig_out_kind_exchange'): return False
    s = meta_get(c, 'settings', {}) or {}
    kinds = list(s.get('out_kinds') or [])
    changed = False
    if kinds and '换货' not in kinds:
        if '其他出库' in kinds: kinds.insert(kinds.index('其他出库'), '换货')
        else: kinds.append('换货')
        s['out_kinds'] = kinds; meta_set(c, 'settings', s); changed = True
    meta_set(c, 'mig_out_kind_exchange', True)
    return changed

def migrate_out_kind_ziti_1134(c):
    """1.1.34：全站只保留「客户自提」；历史 kind=自提出库 写入合并；设置 chips/默认去掉自提出库。
    库存流水按订单重算口径不变（只改类型标签）。幂等。"""
    if meta_get(c, 'mig_out_kind_ziti_1134'): return None
    n = c.execute("UPDATE out_orders SET kind='客户自提' WHERE kind='自提出库'").rowcount
    s = meta_get(c, 'settings', {}) or {}
    changed = False
    kinds = [k for k in (s.get('out_kinds') or []) if k and k != '自提出库']
    if '客户自提' not in kinds:
        kinds = logic._merge_default_list(kinds, ['客户自提'], before='其他出库')
    # 再按默认序补上换货等
    kinds = logic._merge_default_list(kinds, logic.DEFAULT_SETTINGS['out_kinds'], before='其他出库')
    kinds = [k for k in kinds if k != '自提出库']
    if kinds != (s.get('out_kinds') or []):
        s['out_kinds'] = kinds; changed = True
    d = dict(s.get('defaults') or {})
    ok = d.get('out_kind')
    if ok == '自提出库' or (ok and ok not in kinds and ok != ''):
        d['out_kind'] = '客户自提'
        s['defaults'] = d
        changed = True
    # 名称设置：去掉以「自提出库」为键或值的映射（已无此芯片）
    names = dict(s.get('ui_names') or {})
    scrub = {k: v for k, v in names.items() if k != '自提出库' and v != '自提出库'}
    if scrub != names:
        s['ui_names'] = scrub; changed = True
    if changed:
        meta_set(c, 'settings', s)
    meta_set(c, 'mig_out_kind_ziti_1134', True)
    return {'orders': n, 'settings_changed': changed}

def create_server():
    """建库 / 首次导入 / 升级 / 绑定端口（端口被占用会抛 OSError）。返回 ThreadingHTTPServer，还没开始服务"""
    global PORT
    c = bootstrap(); first_run_seed(c); upgrade(c)
    PORT = int(os.environ.get('WH_PORT') or logic.settings(c).get('lan_port') or 8080)
    c.close()
    return Srv(('0.0.0.0', PORT), H)

class Srv(ThreadingHTTPServer):
    daemon_threads = True
    if sys.platform == 'win32':
        # Windows 上 SO_REUSEADDR 会让两个进程同时占同一端口（旧版窗口没关时新版也能“启动成功”），改用独占
        allow_reuse_address = False
        def server_bind(self):
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'): self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

def banner():
    print('=' * 52); print(' 库房出入库系统 v%s 已启动' % version.VERSION)
    for u_ in lan_urls(): print('   电脑打开： %s      手机打开： %s/m/' % (u_, u_))
    print('   本机也可打开： http://127.0.0.1:%d' % PORT); print('=' * 52)

def main():
    srv = create_server()
    stop = backup.start_auto() if not os.environ.get('WH_NO_AUTOBACKUP') else None
    banner()
    try: srv.serve_forever()
    except KeyboardInterrupt: pass

if __name__ == '__main__':
    main()
