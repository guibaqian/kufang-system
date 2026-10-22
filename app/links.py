# -*- coding: utf-8 -*-
"""数据之间的联系：删除前的「会影响什么」清单、任意记录的来源/去向查看（报表、库存数字点进去看到原始记录）。
原则：库存、批次剩余、换算表→入出库记录、交接表→产品出入库情况 都是由原始记录算出来的（不复制），
所以删除 / 恢复 / 修改原始记录后，重算即可处处一致；这里只负责「说清楚会影响什么」和「从数字找到原始记录」。"""
import json
import db, logic, reports
from db import row, rows, ENTITY_CN, ENTITY_TABLE
from web import route, ApiError

SRC_CN = {'out': '出库', 'arrival': '到货/入库', 'daily': '产品出入库情况', 'loan': '借用/归还', 'count': '盘点'}

def _plabel(c, pid):
    p = row(c.execute('SELECT name, spec FROM products WHERE id=?', (pid,)).fetchone())
    return (p['name'] + ((' ' + p['spec']) if p['spec'] else '')) if p else '#%s' % pid

def _stock_effect(c, mv, sign=-1):
    """mv: [(pid, qty)]，sign=-1 表示删除（把这些流水撤掉）。返回说明行"""
    agg = {}
    for pid, q in mv:
        if pid: agg[pid] = agg.get(pid, 0) + q
    if not agg: return []
    st = logic.stock_all(c, list(agg)); out = []
    for pid, q in agg.items():
        d = round(sign * q, 3)
        if not d: continue
        s = st.get(pid) or {}
        if s.get('known'):
            after = round(s['qty'] + d, 3)
            out.append('库存「%s」%s → %s（%s%g）%s' % (_plabel(c, pid), fmt(s['qty']), fmt(after), '+' if d > 0 else '', d, '　⚠ 会变成负数' if after < 0 else ''))
        else:
            out.append('库存「%s」%s%g（还没盘点过，库存未知）' % (_plabel(c, pid), '+' if d > 0 else '', d))
    return out
def fmt(v): return ('%g' % v) if isinstance(v, (int, float)) else str(v)

def _moves_of(c, src, ids):
    if not ids: return []
    return [(r['product_id'], r['qty']) for r in c.execute('SELECT product_id, qty FROM moves WHERE src=? AND src_id IN (%s)' % ','.join('?' * len(ids)), [src] + list(ids))]

def _lox_rows_for_slip(c, sid):
    out = []
    for k in ('lox', 'yard4'):
        t = reports.get_raw(c, k)
        for r, x in enumerate(t['rows'], 1):
            ln = x and x.get('link')
            if ln and ln.get('k') == 'slip' and sid in (ln.get('ids') or []): out.append((k, r, reports._v(t, 'A', r), reports._v(t, 'B', r)))
    return out

def impact(c, ent, i):
    """删除这条记录会影响什么。返回 {title, effects:[...], links:[{entity,id,label}], block:''}"""
    t = ENTITY_TABLE.get(ent)
    if not t: raise ApiError('不认识的记录类型')
    rec = row(c.execute('SELECT * FROM %s WHERE id=?' % t, (i,)).fetchone())
    if not rec: raise ApiError('记录不存在', 404)
    eff, links, block = [], [], ''
    title = ENTITY_CN.get(ent, ent)
    if ent == 'out':
        title = '出库单 %s %s %s' % (rec['date'], rec['kind'], rec['customer'] or rec['recipient'])
        eff += _stock_effect(c, _moves_of(c, 'out', [i]))
        for p in rows(c.execute("SELECT id, what FROM pending WHERE link_type='out' AND link_id=? AND deleted_at IS NULL AND status='待补全'", (i,))):
            eff.append('待补全「%s」会自动关闭' % p['what'][:30]); links.append({'entity': 'pending', 'id': p['id'], 'label': '待补全'})
        eff.append('出库记录 / 导出表里不再有这张单')
    elif ent == 'arrival':
        title = '到货 %s %s %s ×%g' % (rec['date'], rec['name'], rec['spec'] or '', rec['qty'] or 0)
        eff += _stock_effect(c, _moves_of(c, 'arrival', [i]))
        if rec['batch_no']: eff.append('批次 %s 的到货数量' % rec['batch_no'])
        eff.append('「报表 → 到货总数」里这一行')
        for x in rows(c.execute('SELECT id, name, descr FROM temp_items WHERE arrival_id=? AND deleted_at IS NULL', (i,))):
            eff.append('库房杂物「%s」记录的是转成了这条入库（杂物记录保留）' % (x['name'] or x['descr'])); links.append({'entity': 'temp', 'id': x['id'], 'label': '库房杂物'})
    elif ent == 'daily':
        title = '产品出入库情况 %s' % (rec['book_date'] or rec['out_date'])
        lg = rec.get('legacy') or ''
        if lg.startswith('paper:'):
            sid = int(lg.split(':')[1]); sh = row(c.execute('SELECT * FROM paper_sheets WHERE id=?', (sid,)).fetchone())
            if sh and not sh['deleted_at']:
                block = '这条是由「交接表 %s %s」自动生成的，请到交接表里改或清空那一行（直接删这里，下次保存交接表又会生成）' % (sh['date'], sh['session'])
                links.append({'entity': 'paper', 'id': sid, 'label': '交接表 %s %s' % (sh['date'], sh['session'])})
        eff += _stock_effect(c, _moves_of(c, 'daily', [i]))
        eff.append('「产品出入库情况」%s 的合计' % (rec['book_date'] or '未交回'))
    elif ent == 'paper':
        title = '交接表 %s %s' % (rec['date'], rec['session'])
        ds = [r['id'] for r in c.execute("SELECT id FROM daily_entries WHERE legacy LIKE ? AND deleted_at IS NULL", ('paper:%d:%%' % i,))]
        if ds: eff.append('由它生成的 %d 条「产品出入库情况」记录一起删除（恢复交接表时重新生成）' % len(ds))
        eff += _stock_effect(c, _moves_of(c, 'daily', ds))
    elif ent == 'loan':
        title = '借用单 %s %s' % (rec['date'], rec['user_to'] or rec['unit'])
        eff += _stock_effect(c, _moves_of(c, 'loan', [i]))
        n = c.execute('SELECT COUNT(*) FROM loan_returns WHERE loan_id=? AND deleted_at IS NULL', (i,)).fetchone()[0]
        if n: eff.append('它的 %d 条归还记录也不再计入' % n)
        for q in rows(c.execute('SELECT id, name FROM loan_requests WHERE loan_id=?', (i,))):
            eff.append('访客登记 #%d（%s）显示为「借用单已删除」' % (q['id'], q['name']))
    elif ent == 'loan_return':
        l = row(c.execute('SELECT * FROM loans WHERE id=?', (rec['loan_id'],)).fetchone())
        title = '归还记录 %s' % rec['date']
        mv = [(it.get('product_id'), logic.num(it.get('qty'))) for it in json.loads(rec['items'] or '[]')]
        eff += _stock_effect(c, mv)
        if l: eff.append('借用单（%s %s）的已还数量、状态会重算（变回「未还」）' % (l['date'], l['user_to'] or l['unit'])); links.append({'entity': 'loan', 'id': l['id'], 'label': '借用单'})
    elif ent == 'slip':
        title = '称重单 %s %s' % (rec['serial'] or '', rec['car_no'] or '')
        for k, r, d, p in _lox_rows_for_slip(c, i):
            eff.append('「报表 → %s」第 %d 行（%s %s）是用这张单登记的：那一行会标出「称重单已删除」，数字不自动改' % (reports.TABS[k]['short'], r, d or '', p or ''))
    elif ent == 'product':
        title = '产品 ' + logic.product_label(rec)
        st = logic.stock_all(c, [i])[i]
        if st.get('known') and st['qty']: eff.append('当前库存 %s，删除后列表里不再显示' % fmt(st['qty']))
        n = c.execute('SELECT COUNT(*) FROM moves WHERE product_id=?', (i,)).fetchone()[0]
        if n: eff.append('已有 %d 条出入库流水（历史记录保留）' % n)
    elif ent == 'count':
        title = '盘点 %s' % rec['date']
        eff.append('「%s」的库存会按更早的盘点重新推算（没有更早的盘点就变成未知）' % _plabel(c, rec['product_id']))
    elif ent == 'courier':
        title = '配送员 ' + rec['name']
        n = c.execute('SELECT COUNT(*) FROM daily_entries WHERE courier_id=? AND deleted_at IS NULL', (i,)).fetchone()[0]
        if n: eff.append('有 %d 条产品出入库情况记录（历史保留，以后不能再选他）' % n)
    return {'title': title, 'effects': eff, 'links': links, 'block': block}

@route('GET', '/api/impact')
def api_impact(c, q, b, me): return impact(c, q['entity'], int(q['id']))

# ---------- 记录查看：从报表/库存数字点进去 ----------
FIELDS = {
    'out': [('date', '日期'), ('kind', '类型'), ('source', '单据来源'), ('u8_no', 'U8单号'), ('customer', '客户'), ('recipient', '领用人'), ('courier', '配送员'), ('purpose', '用途'), ('remark', '备注')],
    'arrival': [('date', '日期'), ('kind', '类型'), ('name', '名称'), ('spec', '规格'), ('qty', '数量'), ('unit', '单位'), ('batch_no', '批号'), ('dest', '去向'), ('u8_status', 'U8'), ('remark', '备注')],
    'loan': [('date', '日期'), ('user_to', '借用人'), ('unit', '单位'), ('phone', '电话'), ('status', '状态'), ('handler', '经办'), ('remark', '备注')],
    'daily': [('out_date', '领取日'), ('book_date', '交回日'), ('note', '备注')],
    'paper': [('date', '日期'), ('session', '班次'), ('note', '备注')],
    'slip': [('serial', '流水号'), ('date', '时间'), ('car_no', '车号'), ('gross', '毛重'), ('tare', '皮重'), ('net', '净重')],
    'count': [('date', '日期'), ('qty', '实盘数'), ('computed_before', '当时系统数'), ('diff', '调整'), ('note', '备注')],
}
def record(c, ent, i):
    t = ENTITY_TABLE.get(ent)
    if not t: raise ApiError('不认识的记录类型')
    rec = row(c.execute('SELECT * FROM %s WHERE id=?' % t, (i,)).fetchone())
    if not rec: raise ApiError('记录不存在', 404)
    f = [[lab, rec.get(k)] for k, lab in FIELDS.get(ent, []) if rec.get(k) not in (None, '')]
    items = []; links = []
    if ent == 'out': items = [{'name': x['product_name'], 'qty': x['qty'], 'batch': x['batch_no']} for x in logic.items_of(c, i)]
    if ent == 'loan': items = [{'name': x['product_name'], 'qty': x['qty_text'] or x['qty'], 'batch': x['batch_no'], 'returned': x['returned']} for x in rows(c.execute('SELECT * FROM loan_items WHERE loan_id=?', (i,)))]
    if ent == 'daily':
        cn = row(c.execute('SELECT name FROM couriers WHERE id=?', (rec['courier_id'],)).fetchone()); f.insert(0, ['配送员', cn['name'] if cn else ''])
        lg = rec.get('legacy') or ''
        if lg.startswith('paper:'): sid = int(lg.split(':')[1]); links.append({'entity': 'paper', 'id': sid, 'label': '来源：交接表', 'date': (row(c.execute('SELECT date FROM paper_sheets WHERE id=?', (sid,)).fetchone()) or {}).get('date')})
    if ent == 'paper':
        for d in rows(c.execute("SELECT id, book_date FROM daily_entries WHERE legacy LIKE ? AND deleted_at IS NULL", ('paper:%d:%%' % i,))):
            links.append({'entity': 'daily', 'id': d['id'], 'label': '生成的产品出入库情况 %s' % (d['book_date'] or '未交回')})
    if ent == 'slip':
        for k, r, d, p in _lox_rows_for_slip(c, i): links.append({'entity': 'report', 'key': k, 'r': r, 'label': '%s 第%d行' % (reports.TABS[k]['short'], r)})
    if ent == 'loan':
        for q in rows(c.execute('SELECT id, name FROM loan_requests WHERE loan_id=?', (i,))): links.append({'entity': 'loan_req', 'id': q['id'], 'label': '来源：访客登记 %s' % q['name']})
    src = {'out': 'out', 'arrival': 'arrival', 'daily': 'daily', 'loan': 'loan'}.get(ent)
    mv = [dict(m, product=_plabel(c, m['product_id'])) for m in rows(c.execute('SELECT * FROM moves WHERE src=? AND src_id=? ORDER BY date, ts', (src, i)))] if src else []
    au = rows(c.execute('SELECT ts, person, action, summary FROM audit WHERE entity=? AND entity_id=? ORDER BY ts DESC LIMIT 12', (ent, i)))
    return {'entity': ent, 'entity_cn': ENTITY_CN.get(ent, ent), 'id': i, 'fields': f, 'items': items, 'moves': mv, 'links': links, 'audit': au,
            'deleted': bool(rec.get('deleted_at')), 'deleted_by': rec.get('deleted_by'), 'date': rec.get('date') or rec.get('book_date') or rec.get('out_date')}

@route('GET', '/api/record')
def api_record(c, q, b, me): return record(c, q['entity'], int(q['id']))
