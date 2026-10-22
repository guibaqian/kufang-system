# -*- coding: utf-8 -*-
"""导入：每日「产品出入库情况」Excel（历史 + 配送员名单）、v82 合并数据迁移、到货总数表历史"""
import json, re, base64, os, uuid, datetime
from db import save_row, now, meta_set, meta_get, PHOTO_DIR, audit, row, rows
import logic, xlsxio

def parse_daily_xlsx(data):
    sh = xlsxio.read_sheet(data); cells = sh['cells']
    title = str(cells.get('A1', ''))
    m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})', title)
    date = '%s-%02d-%02d' % (m.group(1), int(m.group(2)), int(m.group(3))) if m else ''
    maxr = max([int(re.sub(r'[A-Z]+', '', k)) for k in cells if k != '_f'] + [5])
    people = []; cur = None
    for r in range(5, maxr + 1):
        name = cells.get('A%d' % r) or cells.get('AH%d' % r)
        vals = {}
        for k, col in logic.CYL:
            v = cells.get('%s%d' % (col, r))
            if isinstance(v, (int, float)) and v: vals[k] = v
        for o in logic.OTHER:
            for pre, col in (('t_', o[2]), ('i_', o[3])):
                v = cells.get('%s%d' % (col, r))
                if isinstance(v, (int, float)) and v: vals[pre + o[0]] = v
        note = cells.get('BK%d' % r) or ''
        if name:
            cur = {'name': str(name).strip(), 'vals': vals, 'note': str(note), 'row': r}; people.append(cur)
        elif (vals or note) and cur:   # 第二行（中午回来一次等）并入上一位
            for k, v in vals.items(): cur['vals'][k] = cur['vals'].get(k, 0) + v
            if note: cur['note'] = (cur['note'] + '；' + str(note)).strip('；')
    return {'date': date, 'title': title, 'people': people}

def import_daily(c, data, person, as_history=True, date_override=None):
    p = parse_daily_xlsx(data)
    date = date_override or p['date']
    if not date: raise ValueError('读不出表头日期（应为「2026年10月17号产品出入库情况」）')
    added = []; n = 0
    for i, pp in enumerate(p['people']):
        k = c.execute('SELECT id FROM couriers WHERE name=? AND deleted_at IS NULL', (pp['name'],)).fetchone()
        if k: cid = k[0]
        else:
            mx = c.execute('SELECT COALESCE(MAX(sort),0) FROM couriers').fetchone()[0]
            cid = save_row(c, 'courier', {'name': pp['name'], 'kind': '点位' if re.search(r'建行|银行|点', pp['name']) and not re.search(r'\d', pp['name']) else '配送员', 'sort': mx + 10}, person, '从日表导入配送员')
            added.append(pp['name'])
        if as_history and (pp['vals'] or pp['note']):
            logic.save_daily(c, {'courier_id': cid, 'out_date': date, 'book_date': date, 'vals': pp['vals'], 'note': pp['note']}, person)
            c.execute("UPDATE daily_entries SET source='import' WHERE id=(SELECT MAX(id) FROM daily_entries)")
            n += 1
    return {'date': date, 'couriers_added': added, 'entries': n, 'people': len(p['people'])}

# ---------------- v82 合并数据迁移 ----------------
LEGACY_KIND = {'自提出库（后台客户）': ('客户自提', ''), '自提出库': ('客户自提', ''), '销售出库（u8）': ('销售出库', 'U8单'), '批量配送': ('批量配送', ''),
               '混合出库': ('混合出库', ''), '其他出库1': ('其他出库', '')}

def save_dataurl(c, entity, eid, att, person, ts, tag=''):
    d = att.get('data') or ''
    m = re.match(r'data:([^;]+);base64,(.*)', d, re.S)
    if not m: return None
    raw = base64.b64decode(m.group(2))
    ext = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}.get(m.group(1), '.bin')
    sub = datetime.datetime.fromtimestamp(ts).strftime('%Y%m') if ts else 'legacy'
    os.makedirs(os.path.join(PHOTO_DIR, sub), exist_ok=True)
    rel = '%s/%s%s' % (sub, uuid.uuid4().hex[:16], ext)
    open(os.path.join(PHOTO_DIR, rel), 'wb').write(raw)
    c.execute('INSERT INTO photos(entity,entity_id,tag,path,name,size,legacy,created_at,created_by) VALUES(?,?,?,?,?,?,?,?,?)',
              (entity, eid, tag, rel, att.get('name', ''), len(raw), 'v82', ts or now(), person))
    return rel

def migrate_v82(c, js, person='迁移'):
    d = js['data'] if 'data' in js else js
    rep = {'products': 0, 'out': 0, 'loans': 0, 'returns': 0, 'arrivals': 0, 'photos': 0, 'deleted': 0, 'unmatched_items': [], 'self_uses': 0}
    pmap = {}
    cat_map = {'工程': '工程材料'}
    for i, p in enumerate(d.get('products', [])):
        name = p['name'].strip(); spec = (p.get('model') or '').strip()
        ex = c.execute('SELECT id FROM products WHERE name=? AND spec=? AND deleted_at IS NULL', (name, spec)).fetchone()
        if ex:   # 同名同规格（如两条「便携式制氧机电池」）→ 记为同一产品，旧 id 都指向它
            pid = ex[0]; lid = json.loads(c.execute('SELECT legacy_ids FROM products WHERE id=?', (pid,)).fetchone()[0]); lid.append(p['id'])
            c.execute('UPDATE products SET legacy_ids=? WHERE id=?', (json.dumps(lid), pid))
        else:
            pid = save_row(c, 'product', {'name': name, 'spec': spec, 'category': cat_map.get(p.get('category'), p.get('category') or '其他'),
                                          'unit': p.get('unit') or '个', 'remark': p.get('remark', ''), 'sort': i * 10,
                                          'batch_managed': 1 if (p.get('stockBatches') or name == '便携式医用供氧器') and name != '1.6米鼻氧管' else 0,
                                          'legacy_ids': json.dumps([p['id']])}, person, '从 v82 迁移（旧库存 %s 不采用，按「未知」）' % p.get('stock'))
            rep['products'] += 1
        pmap[p['id']] = pid
        for b in p.get('stockBatches') or []:
            if b.get('no') and pid and not c.execute('SELECT 1 FROM batches WHERE product_id=? AND batch_no=?', (pid, b['no'])).fetchone():
                c.execute('INSERT INTO batches(product_id,batch_no,created_at,created_by,remark) VALUES(?,?,?,?,?)', (pid, b['no'], now(), person, '旧系统批次'))
    def pid_of(it):
        if it.get('productId') in pmap: return pmap[it['productId']]
        p = logic.find_product(c, it.get('productName', ''))
        if p: return p['id']
        rep['unmatched_items'].append(it.get('productName'))
        return logic.ensure_product(c, it.get('productName') or '未知产品', person)
    T = d.get('transactions', [])
    loans_by_old = {}
    def ts_of(t): return (t.get('createdAt') or 0) / 1000 or None
    for t in sorted(T, key=lambda t: (t.get('date', ''), t.get('createdAt') or 0)):
        ts = ts_of(t); st = t.get('subtype', '')
        u8no = ''
        mm = re.search(r'单号\s*(\d{6,})', t.get('remark') or '')
        if mm: u8no = mm.group(1)
        items = [{'product_id': pid_of(i), 'qty': i.get('qty') or 0, 'batch_no': i.get('batch') or '', 'note': i.get('note') or '', 'returned': i.get('returnedQty') or 0} for i in t.get('items', [])]
        base = {'created_at': ts, 'created_by': t.get('operator') or person, 'legacy_id': t['id']}
        if t['type'] == 'out' and st.startswith('借用'):
            lid = save_row(c, 'loan', dict(base, date=t['date'], handler=t.get('salesperson') or t.get('operator') or '', user_to=t.get('customerName') or '',
                                           unit=t.get('unit') or '', orgs=json.dumps([t['unit']] if t.get('unit') else [], ensure_ascii=False), slip_no=logic.next_slip_no(c, t['date']), phone=t.get('phone') or '', use_type='外单位', need_return=1, source='U8单' if 'u8' in st.lower() else '',
                                           u8_no=u8no, salesperson=t.get('salesperson') or '', remark=t.get('remark') or '', status='未归还'), person, '从 v82 迁移：' + st)
            for it in items:
                c.execute('INSERT INTO loan_items(loan_id,product_id,product_name,qty,returned,batch_no,note) VALUES(?,?,?,?,?,?,?)',
                          (lid, it['product_id'], '', it['qty'], 0, it['batch_no'], it['note']))
            loans_by_old[t['id']] = lid; ent, eid = 'loan', lid; rep['loans'] += 1
        elif t['type'] == 'in' and st == '归还入库':
            lid = loans_by_old.get(t.get('relatedId'))
            if not lid:   # 找不到对应借用：当「其他入库」到货记
                eid = None
                for it in items:
                    eid = logic.save_arrival(c, dict(base, date=t['date'], kind='其他入库', name=pname(c, it['product_id']), qty=it['qty'], product_id=it['product_id'],
                                                     dest=t.get('unit') or '', remark='旧系统归还入库（未找到对应借用）' + (t.get('remark') or ''), u8_status='不入U8'), person)
                ent = 'arrival'; rep['arrivals'] += 1
            else:
                eid = save_row(c, 'loan_return', dict(base, loan_id=lid, date=t['date'], remark=t.get('remark') or '',
                                                      items=json.dumps([{'product_id': i['product_id'], 'qty': i['qty'], 'batch_no': i['batch_no']} for i in items])), person, '从 v82 迁移：归还')
                for it in items:
                    c.execute('UPDATE loan_items SET returned=returned+? WHERE id=(SELECT id FROM loan_items WHERE loan_id=? AND product_id=? ORDER BY id LIMIT 1)', (it['qty'], lid, it['product_id']))
                ent = 'loan_return'; rep['returns'] += 1
        elif t['type'] == 'in':
            eid = None
            for it in items:
                eid = logic.save_arrival(c, dict(base, date=t['date'], kind='到货', name=pname(c, it['product_id']), qty=it['qty'], product_id=it['product_id'],
                                                 batch_no=it['batch_no'], supplier=t.get('customerName') or '', remark=t.get('remark') or '', u8_status='已入U8'), person)
            ent = 'arrival'; rep['arrivals'] += 1
        else:
            kind, src = LEGACY_KIND.get(st, (st or '其他出库', ''))
            eid = save_row(c, 'out', dict(base, date=t['date'], kind=kind, source=src, u8_no=u8no, customer=t.get('unit') or t.get('customerName') or '',
                                          contact=t.get('customerName') if t.get('unit') else '', phone=t.get('phone') or '', salesperson=t.get('salesperson') or '',
                                          courier=t.get('deliveryPerson') or '', remark=t.get('remark') or '', mode='legacy', legacy_subtype=st), person, '从 v82 迁移：' + st)
            for it in items:
                c.execute('INSERT INTO out_items(order_id,product_id,product_name,qty,batch_no,note) VALUES(?,?,?,?,?,?)',
                          (eid, it['product_id'], pname(c, it['product_id']), it['qty'], it['batch_no'], it['note']))
            ent = 'out'; rep['out'] += 1
        if t.get('deleted') and eid:
            t_ = {'out': 'out_orders', 'loan': 'loans', 'loan_return': 'loan_returns', 'arrival': 'arrivals'}[ent]
            c.execute(f'UPDATE {t_} SET deleted_at=?, deleted_by=? WHERE id=?', ((t.get('deletedAt') or 0) / 1000 or now(), t.get('deletedBy') or person, eid))
            rep['deleted'] += 1
        for a in t.get('attachments') or []:
            if eid and save_dataurl(c, ent, eid, a, t.get('operator') or person, ts): rep['photos'] += 1
    # 员工自用 → 借用（给谁用=自用）
    for s in d.get('selfUses', []):
        ts = (s.get('createdAt') or 0) / 1000 or None
        items = s.get('items', [])
        lid = save_row(c, 'loan', {'slip_no': logic.next_slip_no(c, s['date']), 'date': s['date'], 'handler': s.get('staff', ''), 'user_to': s.get('staff', ''), 'use_type': '自用', 'need_return': 1,
                                   'remark': s.get('remark', ''), 'status': '已归还' if s.get('returned') else '未归还', 'legacy_id': s['id'], 'created_at': ts,
                                   'created_by': s.get('operator') or person}, person, '从 v82 迁移：员工自用')
        ret = []
        for i in items:
            pid = pid_of(i)
            c.execute('INSERT INTO loan_items(loan_id,product_id,qty,returned,batch_no,note) VALUES(?,?,?,?,?,?)', (lid, pid, i.get('qty') or 0, i.get('returnedQty') or 0, i.get('batch') or '', i.get('note') or ''))
            if i.get('returnedQty'): ret.append({'product_id': pid, 'qty': i['returnedQty']})
        if ret:
            save_row(c, 'loan_return', {'loan_id': lid, 'date': s.get('returnDate') or s['date'], 'items': json.dumps(ret), 'remark': '旧系统员工自用归还', 'created_at': ts}, person, '从 v82 迁移')
        rep['self_uses'] += 1
    # 借用状态
    import loans
    for l in rows(c.execute('SELECT id FROM loans')):
        loans.recompute(c, l['id'])
    # 液氧到货旧数据：导出留底（存 meta，另在备份页可下载）；照片也保存
    lox = []
    for a in d.get('loxArrivals', []):
        a2 = dict(a); atts = a2.pop('attachments', []) or []
        a2['photos'] = [save_dataurl(c, 'lox_legacy', 0, x, a.get('operator') or person, (a.get('createdAt') or 0) / 1000 or None) for x in atts]
        rep['photos'] += len([p for p in a2['photos'] if p]); lox.append(a2)
    meta_set(c, 'legacy_lox_arrivals', lox)
    meta_set(c, 'legacy_lists', {k: d.get(k) for k in ('persons', 'operators', 'sales', 'selfStaff', 'batchDefaults', 'aboutNote')})
    # 业务员名单 → 建议
    s = logic.settings(c); s['salespeople'] = sorted(set((d.get('sales') or []) + (d.get('selfStaff') or []))); meta_set(c, 'settings', s)
    for t in ('out_orders',):
        for r in rows(c.execute(f"SELECT DISTINCT customer, contact, phone, date FROM {t} WHERE customer<>'' ORDER BY date")):
            logic.touch_customer(c, r['customer'], r['contact'], r['phone'], r['date'])
    logic.rebuild_all(c)
    rep['unmatched_items'] = sorted(set(x for x in rep['unmatched_items'] if x))
    audit(c, person, '导入', 'migration', 0, 'v82 合并数据迁移：' + json.dumps({k: v for k, v in rep.items() if k != 'unmatched_items'}, ensure_ascii=False))
    return rep

def pname(c, pid):
    r = c.execute('SELECT name, spec FROM products WHERE id=?', (pid,)).fetchone()
    return (r[0] + (' ' + r[1] if r[1] else '')) if r else ''

def update_loan_status(c, lid):
    its = rows(c.execute('SELECT qty, returned FROM loan_items WHERE loan_id=?', (lid,)))
    l = row(c.execute('SELECT need_return FROM loans WHERE id=?', (lid,)).fetchone())
    if not l['need_return']: st = '领用'
    elif its and all((i['returned'] or 0) >= i['qty'] for i in its): st = '已归还'
    elif any((i['returned'] or 0) > 0 for i in its): st = '部分归还'
    else: st = '未归还'
    c.execute('UPDATE loans SET status=? WHERE id=?', (st, lid))

# ---------------- 库存及到货总数 历史行 ----------------
def import_arrivals_sheet(c, xlsx_bytes, person, sheet_index=0):
    sh = xlsxio.read_sheet(xlsx_bytes, sheet_index); cells = sh['cells']
    maxr = max(int(re.sub(r'[A-Z]+', '', k)) for k in cells if k != '_f')
    last_date = ''; n = 0
    for r in range(3, maxr + 1):
        g = lambda col: cells.get('%s%d' % (col, r))
        if not g('B') and not g('E'): continue
        dt = g('A')
        if dt is not None and dt != '':
            last_date = to_date(dt) or last_date
        name = str(g('B') or '').strip(); spec = str(g('C') or '').strip()
        st = str(g('H') or '')
        allt = (st + str(g('G') or '')).upper()
        u8 = '已入U8' if ('已' in st and 'U8' in st.upper()) or g('I') or g('J') else '不入U8' if re.search(r'(不用|无需|不需|不)入U8', allt) else '待入U8'
        p = logic.find_product(c, name + spec) or logic.find_product(c, spec + name) or logic.find_product(c, name)
        qty = g('E'); qty = qty if isinstance(qty, (int, float)) else 0
        data = {'date': last_date or '2026-01-01', 'kind': '到货', 'name': name, 'spec': spec, 'unit': str(g('D') or ''), 'qty': qty,
                'dest': str(g('F') or ''), 'remark': str(g('G') or ''), 'u8_status': u8, 'inv_code': str(g('I') or ''), 'receipt_no': str(g('J') or ''),
                'taken_note': str(g('K') or ''), 'product_id': p['id'] if p else None, 'sheet_row': r, 'legacy_id': 'sheet:%d' % r,
                'remark2': st}
        if st and st not in ('已U8入库',): data['remark'] = (data['remark'] + ' ' + st).strip()
        logic.save_arrival(c, data, person); n += 1
    return n

def to_date(v):
    if isinstance(v, (int, float)) and 30000 < v < 80000:
        return (datetime.date(1899, 12, 30) + datetime.timedelta(days=int(v))).isoformat()
    m = re.match(r'(\d{4})[.\-/年](\d{1,2})[.\-/月](\d{1,2})', str(v).strip())
    if m: return '%s-%02d-%02d' % (m.group(1), int(m.group(2)), int(m.group(3)))
    return None
