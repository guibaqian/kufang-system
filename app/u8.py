# -*- coding: utf-8 -*-
"""U8 账面目录：照片转录的种子 + 以后用 Excel 重新导入（只作参考，不当实际库存）"""
import json, os, re
from db import save_row, rows, row, now, audit
import logic, xlsxio

SEED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'seed', 'u8_catalog.json')

def _find_exact(c, name, spec):
    """仅「完全一致」才自动匹配：名称相同（且旧产品无型号或型号相同），或型号与旧产品型号相同"""
    ps = rows(c.execute('SELECT * FROM products WHERE deleted_at IS NULL AND merged_into IS NULL'))
    same = [p for p in ps if p['name'] == name and (not p['spec'] or not spec or p['spec'] == spec)]
    if len(same) == 1: return same[0]
    if spec and re.search(r'[A-Za-z]{2,}', spec) and len(spec) >= 5:   # 只认像 CWO-S5A 这样的型号，不认 40L/10L 这类容量
        bys = [p for p in ps if p['spec'] and p['spec'].replace(' ', '').upper() == spec.replace(' ', '').upper()]
        if len(bys) == 1: return bys[0]
    return None

def sync_product_codes(c, pid):
    if not pid: return
    us = rows(c.execute("SELECT wh, code FROM u8_items WHERE product_id=? AND deleted_at IS NULL ORDER BY wh, code", (pid,)))
    whs = '、'.join(sorted(set(u['wh'] for u in us))); codes = '、'.join(sorted(set(u['code'] for u in us)))
    c.execute('UPDATE products SET u8_wh=?, u8_code=? WHERE id=?', (whs, codes, pid))

def upsert(c, wh, code, name, spec, unit, qty, person, note='', as_of='', hint=None):
    wh = str(wh).strip(); code = str(code).strip()
    if isinstance(qty, str):
        try: qty = float(qty.replace(',', ''))
        except ValueError: qty = None
    ex = row(c.execute('SELECT * FROM u8_items WHERE wh=? AND code=?', (wh, code)).fetchone())
    d = {'wh': wh, 'code': code, 'name': name, 'spec': spec, 'unit': unit, 'as_of': as_of}
    if qty is not None or as_of: d['qty'] = qty
    if note: d['note'] = note
    if ex:
        d['id'] = ex['id']
        save_row(c, 'u8', d, person)
        return ex['id'], 'update'
    # 新编码：先找同编码的其他库已关联产品，再精确匹配，否则按提示列为待确认，最后建新产品
    other = row(c.execute("SELECT product_id FROM u8_items WHERE code=? AND product_id IS NOT NULL AND match IN ('自动匹配','已确认') LIMIT 1", (code,)).fetchone())
    pid = None; sug = None; match = ''
    if hint and hint[0] == 'review':
        p = logic.find_product(c, hint[1]); sug = p['id'] if p else None; match = '待确认' if sug else ''
    if not match:
        if other: pid = other['product_id']; match = '自动匹配'
        else:
            p = _find_exact(c, name, spec) if not hint or hint[0] != 'review' else None
            if hint and hint[0] == 'auto': p = logic.find_product(c, hint[1]) or p
            if p: pid = p['id']; match = '自动匹配'
    if not match:
        pid = save_row(c, 'product', {'name': name, 'spec': spec, 'unit': unit or '个', 'category': guess_cat(name), 'remark': '来自 U8 账面'}, person, 'U8 账面新增产品')
        match = '新产品'
    d.update(product_id=pid, suggest_id=sug, match=match)
    i = save_row(c, 'u8', d, person, f'U8 {wh} {code} {name} → {match}')
    sync_product_codes(c, pid)
    return i, match

def guess_cat(n):
    for k, v in (('制氧机', '制氧机'), ('钢瓶', '钢瓶'), ('氧气瓶', '钢瓶'), ('气瓶', '钢瓶'), ('碳纤', '碳纤维'), ('碳钎', '碳纤维'), ('液氧罐', '液氧罐'),
                 ('杜瓦', '液氧罐'), ('血氧仪', '血氧仪'), ('鼻', '配件'), ('推车', '配件'), ('电池', '配件')):
        if k in n: return v
    return '其他'

def seed(c, person='系统'):
    d = json.load(open(SEED, encoding='utf-8'))
    auto = d['match']['auto']; rev = d['match']['review']; stat = {}
    for wh, code, name, spec, unit, note in d['items']:
        hint = ('auto', auto[code]) if code in auto else (('review', rev[code]) if code in rev else None)
        _, m = upsert(c, wh, code, name, spec, unit, None, person, note, '', hint)
        stat[m] = stat.get(m, 0) + 1
    return stat

def confirm(c, uid, person, product_id=None, new_product=False, none=False):
    u = row(c.execute('SELECT * FROM u8_items WHERE id=?', (uid,)).fetchone())
    old = u['product_id']
    if none: save_row(c, 'u8', {'id': uid, 'product_id': None, 'match': '不对应'}, person, f'U8 {u["code"]} 设为不对应任何产品')
    elif new_product:
        pid = save_row(c, 'product', {'name': u['name'], 'spec': u['spec'], 'unit': u['unit'] or '个', 'category': guess_cat(u['name']), 'remark': '来自 U8 账面'}, person, 'U8 账面新增产品')
        save_row(c, 'u8', {'id': uid, 'product_id': pid, 'match': '已确认'}, person, f'U8 {u["code"]} 建为新产品')
    else:
        pid = int(product_id or u['suggest_id'])
        save_row(c, 'u8', {'id': uid, 'product_id': pid, 'match': '已确认'}, person, f'U8 {u["code"]} 对应产品 #{pid}')
    for p in (old, row(c.execute('SELECT product_id FROM u8_items WHERE id=?', (uid,)).fetchone())['product_id']):
        sync_product_codes(c, p)

HEAD = {'wh': ['仓库名称', '仓库', 'U8库'], 'code': ['存货编码', '编码'], 'name': ['存货名称', '名称'], 'spec': ['规格型号', '规格'], 'unit': ['单位', '主计量单位'],
        'qty': ['数量', '结存数量', '现存量', '账面数']}

def import_excel(c, data, person, as_of=''):
    sh = xlsxio.read_sheet(data); cells = sh['cells']
    keys = [k for k in cells if k != '_f']
    maxr = max(int(re.sub(r'[A-Z]+', '', k)) for k in keys)
    hdr_row = None; colmap = {}
    for r in range(1, min(maxr, 15) + 1):
        cm = {}
        for k in keys:
            if int(re.sub(r'[A-Z]+', '', k)) != r: continue
            v = str(cells[k]).strip()
            for f, names in HEAD.items():
                if v in names: cm[f] = re.sub(r'\d+', '', k)
        if 'code' in cm and 'qty' in cm: hdr_row = r; colmap = cm; break
    if not hdr_row: raise ValueError('没找到表头（需要「存货编码」和「数量」列）')
    sheet_wh = re.sub(r'\s', '', sh['name']) if '库' in sh['name'] else ''
    n = 0; st = {}
    for r in range(hdr_row + 1, maxr + 1):
        g = lambda f: cells.get('%s%d' % (colmap[f], r)) if f in colmap else None
        code = g('code')
        if code in (None, ''): continue
        code = str(int(code)) if isinstance(code, float) and code == int(code) else str(code)
        wh = str(g('wh') or sheet_wh or '未分库')
        _, m = upsert(c, wh, code, str(g('name') or ''), str(g('spec') or ''), str(g('unit') or ''), g('qty'), person, '', as_of or 'Excel 导入')
        st[m] = st.get(m, 0) + 1; n += 1
    audit(c, person, '导入', 'u8', 0, f'U8 账面 Excel 导入 {n} 行：{st}')
    return {'rows': n, 'stat': st}

def by_product(c):
    out = {}
    for u in rows(c.execute("SELECT * FROM u8_items WHERE deleted_at IS NULL AND product_id IS NOT NULL AND match IN ('自动匹配','已确认','新产品')")):
        o = out.setdefault(u['product_id'], {'qty': None, 'parts': []})
        if u['qty'] is not None: o['qty'] = (o['qty'] or 0) + u['qty']
        o['parts'].append({'wh': u['wh'], 'code': u['code'], 'qty': u['qty']})
    return out
