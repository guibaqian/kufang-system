# -*- coding: utf-8 -*-
"""借用归还：多物品借用单（自动编号）、多借用单位（每项标归属或「共用」）、小件「若干」归还后定数、
随车技术人员、多次部分归还（按单或按单位合计分摊）、按单位查历史、批量补录手写借用本"""
import json, datetime
import logic, importers
from db import row, rows, now, today, save_row, soft_delete, audit
from web import route, ApiError, attach_photos, photos_of, table_result


SHARED = '共用'

def _nr(v, default=1):
    """归一成 0/1；空/缺省用 default"""
    if v is None or v == '': return 1 if default in (1, True, '1') else 0
    return 1 if v in (1, True, '1') else 0

def item_need_return(it, loan=None):
    """明细级要还：显式 0/1 用明细；NULL/缺字段继承整单（旧单兼容）"""
    if it is None: return _nr(None, 1 if not loan else loan.get('need_return', 1))
    if 'need_return' in it and it.get('need_return') is not None and it.get('need_return') != '':
        return _nr(it.get('need_return'))
    if loan is not None: return _nr(loan.get('need_return', 1))
    return 1

def _items(c, lid): return rows(c.execute('SELECT * FROM loan_items WHERE loan_id=? ORDER BY id', (lid,)))
def _returns(c, lid): return rows(c.execute('SELECT * FROM loan_returns WHERE loan_id=? AND deleted_at IS NULL ORDER BY date, id', (lid,)))
def orgs_of(l):
    o = json.loads(l.get('orgs') or '[]')
    if not o and l.get('unit'): o = [l['unit']]
    return o

def recompute(c, lid):
    """按归还记录重算每项已还数、状态、是否已定数；生成/关闭「待补全」；重建库存流水"""
    l = row(c.execute('SELECT * FROM loans WHERE id=?', (lid,)).fetchone())
    if not l: return
    if not l['slip_no']:
        l['slip_no'] = logic.next_slip_no(c, l['date']); c.execute('UPDATE loans SET slip_no=? WHERE id=?', (l['slip_no'], lid))
    its = _items(c, lid); ret = {i['id']: 0.0 for i in its}
    for r in _returns(c, lid):
        for x in json.loads(r['items'] or '[]'):
            q = float(logic.num(x.get('qty')))
            if x.get('loan_item_id') in ret: ret[x['loan_item_id']] += q; continue
            # 旧数据：按产品分到同产品的项（多出来的记在最后一项上）
            same = [i for i in its if i['product_id'] == x.get('product_id')]
            for i in same:
                if q <= 0: break
                take = min(q, max(i['qty'] - ret[i['id']], 0)); ret[i['id']] += take; q -= take
            if q > 0 and same: ret[same[-1]['id']] += q
    for i in its: c.execute('UPDATE loan_items SET returned=? WHERE id=?', (round(ret[i['id']], 3), i['id']))
    its = _items(c, lid)
    fin = 0 if any(i['approx'] for i in its) else 1
    ret_its = [i for i in its if item_need_return(i, l)]
    # 整单 need_return 由明细汇总：有任一项要还则为 1（兼容旧筛「领用」）
    order_nr = 1 if ret_its else 0
    if not ret_its: st = '领用'
    elif ret_its and fin and all((i['returned'] or 0) >= i['qty'] for i in ret_its): st = '已归还'
    elif any((i['returned'] or 0) > 0 for i in ret_its): st = '部分归还'
    else: st = '未归还'
    c.execute('UPDATE loans SET status=?, finalized=?, need_return=? WHERE id=?', (st, fin, order_nr, lid))
    # 「若干」未定数 → 待补全（自动）
    key = 'loan_final:%d' % lid
    p = row(c.execute("SELECT * FROM pending WHERE auto_key=? AND deleted_at IS NULL", (key,)).fetchone())
    need = not fin and not l['deleted_at']
    if need:
        what = '借用单 %s 小件未定数：%s' % (l['slip_no'], '、'.join('%s %s' % (i['product_name'] or importers.pname(c, i['product_id']), i['qty_text'] or '若干') for i in its if i['approx']))
        if not p:
            c.execute("INSERT INTO pending(date,taker,what,qty,customer,handler,status,link_type,link_id,auto_key,created_at,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                      (l['date'], l['handler'] or l['user_to'], what, '', '、'.join(orgs_of(l)) or l['user_to'], l['handler'], '待补全', 'loan', lid, key, now(), '系统'))
        elif p['status'] != '待补全' or p['what'] != what:
            c.execute("UPDATE pending SET status='待补全', what=?, close_note='' WHERE id=?", (what, p['id']))
    elif p and p['status'] == '待补全':
        c.execute("UPDATE pending SET status='已补全', close_note='自动：借用单已定数', updated_at=? WHERE id=?", (now(), p['id']))
    logic.rebuild_loan(c, lid)

def _rebuild(c, lid): recompute(c, lid)
logic.REBUILD['loan'] = _rebuild

def save_loan(c, d, person):
    items = d.pop('items', None) or []
    items = [i for i in items if (i.get('product_id') or (i.get('product_name') or '').strip())]
    if not items: raise ApiError('请至少填一样借出的物品')
    orgs = [o.strip() for o in (d.get('orgs') or []) if o and o.strip()]
    if isinstance(d.get('orgs'), str): orgs = [x for x in json.loads(d['orgs'])]
    d['orgs'] = json.dumps(orgs, ensure_ascii=False)
    if 'pickups' in d:   # 取货人（可多个）：[{name, phone}]
        pk = d['pickups'] if isinstance(d['pickups'], list) else json.loads(d['pickups'] or '[]')
        d['pickups'] = json.dumps([{'name': str(p.get('name') or '').strip()[:40], 'phone': str(p.get('phone') or '').strip()[:30]} for p in pk if isinstance(p, dict) and (str(p.get('name') or '').strip() or str(p.get('phone') or '').strip())][:6], ensure_ascii=False)
    if orgs and not d.get('unit'): d['unit'] = '、'.join(orgs)
    if not (d.get('user_to') or orgs or d.get('handler')): raise ApiError('请填给谁用（人或单位）')
    d.setdefault('date', today())
    # 整单 need_return：旧客户端仍可传；新客户端按明细汇总（有任一项要还=1）
    order_fallback = _nr(d.get('need_return', 1))
    if d.get('source') != 'U8单': d['u8_type'] = ''
    lid = d.get('id')
    old = _items(c, lid) if lid else []
    if not lid: d['slip_no'] = logic.next_slip_no(c, d['date'])
    norm = []
    for it in items:
        pid = it.get('product_id') or logic.ensure_product(c, it['product_name'], person)
        approx = 1 if it.get('approx') in (1, True, '1') else 0
        qty = float(logic.num(it.get('qty')))
        if not approx and qty <= 0: raise ApiError('「%s」请填数量，小件不确定可勾「若干」' % importers.pname(c, pid))
        org = (it.get('org') or '').strip()
        if org and org != SHARED and orgs and org not in orgs: raise ApiError('物品归属「%s」不在借用单位里' % org)
        # 明细未带 need_return → 继承本次请求的整单值（旧手机/补录兼容）
        if 'need_return' in it and it.get('need_return') is not None and it.get('need_return') != '':
            inr = _nr(it.get('need_return'))
        else:
            inr = order_fallback
        norm.append({'id': it.get('id'), 'product_id': int(pid), 'product_name': importers.pname(c, pid), 'qty': qty, 'approx': approx,
                     'qty_text': (it.get('qty_text') or ('若干' if approx else '')).strip() if approx else '', 'org': org,
                     'batch_no': it.get('batch_no') or '', 'note': it.get('note') or '', 'need_return': inr})
    d['need_return'] = 1 if any(n['need_return'] for n in norm) else 0
    summ = None if lid else '借出 %s → %s：%s' % (d.get('handler', ''), d.get('user_to') or d.get('unit'), '、'.join('%s×%s' % (n['product_name'], n['qty_text'] or '%g' % n['qty']) for n in norm))
    lid = save_row(c, 'loan', d, person, summ, old or None, norm)
    keep = set()
    for n in norm:
        if n['id'] and any(o['id'] == int(n['id']) for o in old):
            c.execute('UPDATE loan_items SET product_id=?,product_name=?,qty=?,approx=?,qty_text=?,org=?,batch_no=?,note=?,need_return=?,final_qty_at=CASE WHEN ?=0 AND approx=1 THEN ? ELSE final_qty_at END WHERE id=?',
                      (n['product_id'], n['product_name'], n['qty'], n['approx'], n['qty_text'], n['org'], n['batch_no'], n['note'], n['need_return'], n['approx'], now(), int(n['id'])))
            keep.add(int(n['id']))
        else:
            cur = c.execute('INSERT INTO loan_items(loan_id,product_id,product_name,qty,approx,qty_text,org,batch_no,note,need_return) VALUES(?,?,?,?,?,?,?,?,?,?)',
                            (lid, n['product_id'], n['product_name'], n['qty'], n['approx'], n['qty_text'], n['org'], n['batch_no'], n['note'], n['need_return']))
            keep.add(cur.lastrowid)
    for o in old:
        if o['id'] not in keep:
            if (o['returned'] or 0) > 0: raise ApiError('「%s」已有归还记录，不能删掉这一项' % (o['product_name'] or importers.pname(c, o['product_id'])))
            c.execute('DELETE FROM loan_items WHERE id=?', (o['id'],))
    recompute(c, lid)
    return lid

def outstanding(c, org=None, lid=None):
    """未还明细：[{loan, item, left}]；org 指定时取该单位的项（归属该单位、共用，或单一单位借用单里未标归属的项）"""
    w = "l.deleted_at IS NULL AND l.need_return=1"; a = []
    if lid: w += ' AND l.id=?'; a.append(lid)
    out = []
    for l in rows(c.execute('SELECT l.* FROM loans l WHERE %s ORDER BY l.date, l.id' % w, a)):
        os_ = orgs_of(l)
        if org and org not in os_: continue
        for i in _items(c, l['id']):
            if not item_need_return(i, l): continue
            if org and not (i['org'] in (org, SHARED) or (not i['org'] and len(os_) <= 1)): continue
            left = round(i['qty'] - (i['returned'] or 0), 3)
            if left > 0 or i['approx']: out.append({'loan': l, 'item': i, 'left': max(left, 0)})
    return out

def save_return(c, b, person):
    """b: {loan_id, date, items:[{loan_item_id, qty, final_qty?}]} 按单；或 {org, date, items:[{product_id, qty}]} 按单位合计分摊"""
    date = b.get('date') or today(); remark = b.get('remark', ''); ids = []
    if b.get('loan_id'):
        lid = int(b['loan_id']); its = {i['id']: i for i in _items(c, lid)}
        l0 = row(c.execute('SELECT * FROM loans WHERE id=?', (lid,)).fetchone())
        got = []
        for x in b.get('items') or []:
            iid = int(x['loan_item_id']); it = its.get(iid)
            if not it: raise ApiError('明细不存在')
            if not item_need_return(it, l0) and str(x.get('final_qty', '')).strip() == '' and float(logic.num(x.get('qty'))) > 0:
                raise ApiError('「%s」标记为不用还，不能记归还' % (it['product_name'] or importers.pname(c, it['product_id'])))
            if str(x.get('final_qty', '')).strip() != '':   # 「若干」清点后定数
                fq = float(x['final_qty'])
                if fq < (it['returned'] or 0) + float(logic.num(x.get('qty'))): raise ApiError('实借数不能小于已还数')
                c.execute('UPDATE loan_items SET qty=?, approx=0, qty_text="", final_qty_at=? WHERE id=?', (fq, now(), iid))
                audit(c, person, '修改', 'loan', lid, '「%s」若干 → 定数 %g' % (it['product_name'], fq)); it = dict(it, qty=fq, approx=0)
            q = float(logic.num(x.get('qty')))
            if q <= 0: continue
            if not it['approx'] and q > it['qty'] - (it['returned'] or 0) + 1e-9: raise ApiError('「%s」还的比没还的多（未还 %g）' % (it['product_name'], it['qty'] - (it['returned'] or 0)))
            got.append({'loan_item_id': iid, 'product_id': it['product_id'], 'qty': q, 'batch_no': it['batch_no']})
        if got:
            l = row(c.execute('SELECT * FROM loans WHERE id=?', (lid,)).fetchone())
            ids.append(save_row(c, 'loan_return', {'loan_id': lid, 'org': b.get('org', ''), 'date': date, 'items': json.dumps(got), 'remark': remark}, person,
                                '归还 %s：%s' % (l['slip_no'], '、'.join('%s×%g' % (its[g['loan_item_id']]['product_name'], g['qty']) for g in got))))
        recompute(c, lid)
        return ids
    org = (b.get('org') or '').strip()
    if not org: raise ApiError('请选借用单或借用单位')
    per = {}
    for x in b.get('items') or []:
        pid = int(x['product_id']); q = float(logic.num(x.get('qty')))
        if q <= 0: continue
        for o in outstanding(c, org):
            if q <= 0: break
            if o['item']['product_id'] != pid: continue
            take = min(q, o['left']) if not o['item']['approx'] else q
            if take <= 0: continue
            per.setdefault(o['loan']['id'], []).append({'loan_item_id': o['item']['id'], 'product_id': pid, 'qty': take, 'batch_no': o['item']['batch_no']}); q -= take
            o['left'] -= take
        if q > 1e-9: raise ApiError('%s 的「%s」还多了 %g（没有那么多未还）' % (org, importers.pname(c, pid), q))
    for lid, got in per.items():
        l = row(c.execute('SELECT * FROM loans WHERE id=?', (lid,)).fetchone())
        ids.append(save_row(c, 'loan_return', {'loan_id': lid, 'org': org, 'date': date, 'items': json.dumps(got), 'remark': remark}, person,
                            '%s 按单位合计归还，分到 %s：%s' % (org, l['slip_no'], '、'.join('%s×%g' % (importers.pname(c, g['product_id']), g['qty']) for g in got))))
        recompute(c, lid)
    if not ids: raise ApiError('没有填归还数量')
    return ids

def loan_full(c, l):
    l = dict(l); l['orgs'] = orgs_of(l); l['items'] = _items(c, l['id'])
    try: l['pickups'] = json.loads(l.get('pickups') or '[]')
    except ValueError: l['pickups'] = []
    for i in l['items']:
        i['label'] = i['product_name'] or importers.pname(c, i['product_id'])
        i['need_return'] = item_need_return(i, l)   # 解析后给前端（旧 NULL → 继承整单）
        i['left'] = round(i['qty'] - (i['returned'] or 0), 3) if i['need_return'] else 0
    l['returns'] = _returns(c, l['id'])
    for r in l['returns']: r['items'] = json.loads(r['items'] or '[]')
    l['photos'] = photos_of(c, 'loan', l['id'])
    return l

def loan_query(c, q):
    w = ['l.deleted_at IS %s' % ('NOT NULL' if q.get('deleted') == '1' else 'NULL')]; a = []
    st = q.get('status')
    if st == 'open': w.append("l.status IN ('未归还','部分归还')")
    elif st == 'unfinal': w.append('l.finalized=0')
    elif st: w.append('l.status=?'); a.append(st)
    for k in ('source', 'use_type'):
        if q.get(k): w.append('l.%s=?' % k); a.append(q[k])
    if q.get('from'): w.append('l.date>=?'); a.append(q['from'])
    if q.get('to'): w.append('l.date<=?'); a.append(q['to'])
    if q.get('q'):
        w.append("(l.user_to LIKE ? OR l.unit LIKE ? OR l.handler LIKE ? OR l.escort LIKE ? OR l.slip_no LIKE ? OR l.u8_no LIKE ? OR l.remark LIKE ? OR EXISTS(SELECT 1 FROM loan_items i WHERE i.loan_id=l.id AND (i.product_name LIKE ? OR i.note LIKE ?)) OR EXISTS(SELECT 1 FROM loan_returns r WHERE r.loan_id=l.id AND r.deleted_at IS NULL AND r.remark LIKE ?)"
                 " OR l.cust_name LIKE ? OR l.cust_phone LIKE ? OR l.salesperson LIKE ? OR l.sales_phone LIKE ? OR l.pickups LIKE ? OR l.phone LIKE ?)")
        a += ['%' + q['q'] + '%'] * 16
    out = [loan_full(c, l) for l in rows(c.execute('SELECT l.* FROM loans l WHERE %s ORDER BY l.date DESC, l.id DESC LIMIT %d' % (' AND '.join(w), int(q.get('limit') or 400)), a))]
    if q.get('org'): out = [l for l in out if q['org'] in l['orgs']]
    return out

def all_orgs(c):
    cnt = {}
    for l in rows(c.execute('SELECT orgs, unit, status FROM loans WHERE deleted_at IS NULL')):
        for o in orgs_of(l):
            x = cnt.setdefault(o, {'org': o, 'loans': 0, 'open': 0}); x['loans'] += 1
            if l['status'] in ('未归还', '部分归还'): x['open'] += 1
    out = sorted(cnt.values(), key=lambda x: (-x['open'], -x['loans'], x['org']))
    import logic  # 设置 → 借用单位：常用单位没借过也列出来
    for o in logic.settings(c).get('guest_orgs') or []:
        if o not in cnt: out.append({'org': o, 'loans': 0, 'open': 0})
    return out

def org_history(c, org):
    """按单位：每张单、每一项（借/还/差）、随车人、归还记录；以及合计未还"""
    loans = [l for l in loan_query(c, {'org': org, 'limit': 5000})]
    lines = []; tot = {}
    for l in sorted(loans, key=lambda x: (x['date'], x['id'])):
        for i in l['items']:
            if not (i['org'] in (org, SHARED) or (not i['org'] and len(l['orgs']) <= 1)): continue
            rd = '；'.join('%s 还%g' % (r['date'], sum(x['qty'] for x in r['items'] if x.get('loan_item_id') == i['id'])) for r in l['returns'] if any(x.get('loan_item_id') == i['id'] for x in r['items']))
            inr = item_need_return(i, l)
            lines.append({'date': l['date'], 'slip_no': l['slip_no'], 'loan_id': l['id'], 'item': i['label'], 'org': i['org'] or org, 'qty': i['qty'], 'qty_text': i['qty_text'],
                          'approx': i['approx'], 'returned': i['returned'] or 0, 'left': i['left'] if inr else 0, 'escort': l['escort'], 'handler': l['handler'],
                          'remark': '；'.join(x for x in [l.get('remark') or '', i.get('note') or ''] + ['%s 归还：%s' % (r['date'], r['remark']) for r in l['returns'] if r.get('remark') and any(x.get('loan_item_id') == i['id'] for x in r['items'])] if x),
                          'returns': rd, 'status': l['status'], 'need_return': inr})
            if inr:
                t = tot.setdefault(i['label'], {'item': i['label'], 'product_id': i['product_id'], 'qty': 0, 'returned': 0, 'left': 0, 'approx': 0})
                t['qty'] += i['qty']; t['returned'] += i['returned'] or 0; t['left'] += max(i['left'], 0); t['approx'] += i['approx']
    return {'org': org, 'lines': lines, 'totals': sorted(tot.values(), key=lambda x: -x['left']), 'loans': len(loans)}

def fmt_q(i): return (i['qty_text'] + ('（约%g）' % i['qty'] if i['qty'] else '')) if i.get('approx') else i['qty']

# ---------------- 接口 ----------------
@route('GET', '/api/loans')
def api_loans(c, q, b, me):
    return {'items': loan_query(c, q), 'orgs': all_orgs(c), 'counts': {r[0]: r[1] for r in c.execute('SELECT status, COUNT(*) FROM loans WHERE deleted_at IS NULL GROUP BY status')},
            'unfinal': c.execute('SELECT COUNT(*) FROM loans WHERE deleted_at IS NULL AND finalized=0').fetchone()[0]}

@route('GET', '/api/loan/one')
def api_loan_one(c, q, b, me):
    l = row(c.execute('SELECT * FROM loans WHERE id=?', (int(q['id']),)).fetchone())
    if not l: raise ApiError('借用单不存在', 404)
    l = loan_full(c, l)
    l['audit'] = rows(c.execute("SELECT ts,person,action,summary FROM audit WHERE (entity='loan' AND entity_id=?) OR (entity='loan_return' AND entity_id IN (SELECT id FROM loan_returns WHERE loan_id=?)) ORDER BY ts", (l['id'], l['id'])))
    return l

@route('POST', '/api/loan/save', 'entry')
def api_loan_save(c, q, b, me):
    d = dict(b['data']); lid = save_loan(c, d, me['name'])
    attach_photos(c, b.get('photo_ids'), 'loan', lid, replace=bool(d.get('id')))
    return {'id': lid, 'slip_no': row(c.execute('SELECT slip_no FROM loans WHERE id=?', (lid,)).fetchone())['slip_no']}

@route('POST', '/api/loan/return', 'entry')
def api_loan_return(c, q, b, me):
    ids = save_return(c, b, me['name'])
    for i in ids[:1]: attach_photos(c, b.get('photo_ids'), 'loan_return', i)
    return {'ids': ids}

@route('POST', '/api/loan/return/delete', 'delete')
def api_loan_return_delete(c, q, b, me):
    r = row(c.execute('SELECT * FROM loan_returns WHERE id=?', (int(b['id']),)).fetchone())
    soft_delete(c, 'loan_return', r['id'], me['name']); recompute(c, r['loan_id']); return {'ok': 1}

@route('POST', '/api/loan/delete', 'delete')
def api_loan_delete(c, q, b, me):
    soft_delete(c, 'loan', int(b['id']), me['name'], b.get('reason', '')); recompute(c, int(b['id'])); return {'ok': 1}

@route('GET', '/api/loan/outstanding')
def api_loan_outstanding(c, q, b, me):
    os_ = outstanding(c, q.get('org') or None, int(q['loan_id']) if q.get('loan_id') else None)
    agg = {}
    for o in os_:
        i = o['item']; a = agg.setdefault(i['product_id'], {'product_id': i['product_id'], 'label': i['product_name'] or importers.pname(c, i['product_id']), 'left': 0, 'approx': 0, 'slips': []})
        a['left'] += o['left']; a['approx'] += i['approx']; a['slips'].append(o['loan']['slip_no'])
    return {'items': [{'loan_id': o['loan']['id'], 'slip_no': o['loan']['slip_no'], 'date': o['loan']['date'], 'item_id': o['item']['id'], 'label': o['item']['product_name'] or importers.pname(c, o['item']['product_id']),
                       'qty': o['item']['qty'], 'returned': o['item']['returned'], 'left': o['left'], 'approx': o['item']['approx'], 'qty_text': o['item']['qty_text'], 'org': o['item']['org']} for o in os_],
            'by_product': list(agg.values())}

@route('GET', '/api/loan/org')
def api_loan_org(c, q, b, me): return org_history(c, q['org'])

@route('GET', '/api/loan/org.xlsx')
def api_loan_org_x(c, q, b, me):
    h = org_history(c, q['org'])
    esc_on = any((x.get('escort') or '').strip() for x in h['lines'])   # 随车技术人员：只有有人填过才出这一列
    hd = ['日期', '借用单号', '物品', '借', '已还', '未还', '随车技术人员', '经手人', '归还记录', '备注']; wd = [11, 15, 22, 8, 7, 7, 12, 8, 30, 24]
    rs = [[x['date'], x['slip_no'], x['item'], x['qty_text'] or x['qty'], x['returned'], x['left'] if x['need_return'] else '不用还', x['escort'], x['handler'], x['returns'], x.get('remark') or ''] for x in h['lines']]
    if not esc_on: hd.pop(6); wd.pop(6); [r.pop(6) for r in rs]
    tt = [[t['item'], t['qty'], t['returned'], t['left'], '有若干未定数' if t['approx'] else ''] for t in h['totals']]
    return table_result(q, '借用历史_%s_%s.xlsx' % (q['org'], today()), [
        ('借用历史', '%s 借用历史（%s 导出）' % (q['org'], today()), hd, rs, wd),
        ('合计未还', '%s 合计' % q['org'], ['物品', '共借', '已还', '未还', '备注'], tt, [24, 9, 9, 9, 16])])

def _np(n, p): return ('%s %s' % (n or '', p or '')).strip()
def people_txt(l, sep='；'):
    """客户 / 销售人 / 取货人 一行说清（打印、导出用）"""
    x = []
    if _np(l.get('cust_name'), l.get('cust_phone')): x.append('客户 ' + _np(l.get('cust_name'), l.get('cust_phone')))
    if _np(l.get('salesperson'), l.get('sales_phone')): x.append('销售 ' + _np(l.get('salesperson'), l.get('sales_phone')))
    pk = [_np(p.get('name'), p.get('phone')) for p in (l.get('pickups') or []) if _np(p.get('name'), p.get('phone'))]
    if pk: x.append('取货 ' + '、'.join(pk))
    return sep.join(x)

@route('GET', '/api/loans.xlsx')
def api_loans_x(c, q, b, me):
    ls = loan_query(c, dict(q, limit=5000)); rs = []
    for l in ls:
        for i in l['items']:
            rs.append([l['date'], l['slip_no'], l['handler'], l['user_to'], '、'.join(l['orgs']), people_txt(l), i['label'], i['qty_text'] or i['qty'], i['org'], i['returned'] or 0,
                       i['left'] if i.get('need_return', l['need_return']) else '不用还', l['escort'], (l['source'] + ' ' + l['u8_no']).strip(), l['status'], l['remark']])
    title = {'open': '未归还清单', 'unfinal': '小件未定数清单'}.get(q.get('status'), '借用记录')
    return table_result(q, '%s_%s.xlsx' % (title, today()), [(title, '%s（%s）' % (title, today()), ['日期', '借用单号', '经手人', '给谁用', '借用单位', '客户 / 销售 / 取货人', '物品', '数量', '归属', '已还', '未还', '随车技术人员', '单据', '状态', '备注'],
                                                          rs, [11, 15, 8, 10, 16, 22, 20, 7, 8, 6, 6, 11, 14, 8, 18])])

@route('GET', '/api/loan/slip.xlsx')
def api_loan_slip_x(c, q, b, me):
    l = loan_full(c, row(c.execute('SELECT * FROM loans WHERE id=?', (int(q['id']),)).fetchone()))
    head = '借用单 %s　日期 %s　经手人 %s　给谁用 %s　借用单位 %s%s%s' % (l['slip_no'], l['date'], l['handler'], l['user_to'], '、'.join(l['orgs']), ('　随车技术人员 %s %s' % (l['escort'], l.get('phone') or '')).rstrip() if (l['escort'] or '').strip() else '',
                                                             ('　单据 %s %s' % (l['source'], l['u8_no'])) if l['source'] else '') + (('　' + people_txt(l, '　')) if people_txt(l) else '')
    rs = [[n + 1, i['label'], i['qty_text'] or i['qty'], i['org'], i['returned'] or 0, i['left'] if i.get('need_return', l['need_return']) else '不用还', i['note']] for n, i in enumerate(l['items'])]
    rs.append(['', head, '', '', '', '', ''])
    return table_result(q, '借用单_%s.xlsx' % l['slip_no'], [('借用单', '借用单 %s' % l['slip_no'], ['序号', '物品', '数量', '归属', '已还', '未还', '备注'], rs, [6, 26, 9, 10, 7, 7, 22])])

@route('POST', '/api/loan/batch', 'entry')
def api_loan_batch(c, q, b, me):
    """批量补录手写借用本：一行一样东西；同日期+经手人+给谁用+单位的连续行合成一张借用单；已还数>0 记归还"""
    groups = []; key = None
    for r in b['rows']:
        if not (r.get('product_id') or (r.get('product_name') or '').strip()): continue
        k = (r.get('date') or today(), r.get('handler', ''), r.get('user_to', ''), r.get('unit', ''))
        if k != key: groups.append({'k': k, 'rows': []}); key = k
        groups[-1]['rows'].append(r)
    ids = []
    for g in groups:
        date, handler, user_to, unit = g['k']; r0 = g['rows'][0]
        d = {'date': date, 'handler': handler, 'user_to': user_to, 'orgs': [unit] if unit else [], 'use_type': '外单位' if unit else (r0.get('use_type') or '自用'),
             'need_return': 0 if all(str(r.get('need_return', 1)) in ('0', 'False', 'false') for r in g['rows']) else 1, 'escort': r0.get('escort', ''),
             'remark': '；'.join(x for x in dict.fromkeys(r.get('remark', '') for r in g['rows']) if x) or '手写借用本补录', 'source': r0.get('source', '')}
        items = []
        for r in g['rows']:
            approx = str(r.get('qty', '')).strip() in ('若干', '') or not str(r.get('qty', '')).replace('.', '', 1).isdigit()
            items.append({'product_id': r.get('product_id'), 'product_name': r.get('product_name', ''), 'qty': 0 if approx else r['qty'], 'approx': approx,
                          'qty_text': str(r.get('qty') or '若干') if approx else '',
                          'need_return': 0 if str(r.get('need_return', 1)) in ('0', 'False', 'false') else 1})
        d['items'] = items; lid = save_loan(c, d, me['name']); ids.append(lid)
        its = _items(c, lid); back = []
        for r, it in zip(g['rows'], its):
            rq = float(logic.num(r.get('returned')))
            if rq > 0: back.append({'loan_item_id': it['id'], 'qty': rq, 'final_qty': rq if it['approx'] else ''})
        if back: save_return(c, {'loan_id': lid, 'date': g['rows'][0].get('return_date') or date, 'items': back, 'remark': '补录'}, me['name'])
    if not ids: raise ApiError('没有可保存的行')
    return {'ids': ids}
