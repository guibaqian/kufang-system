# -*- coding: utf-8 -*-
"""纸质交接表（照纸录）：「氧气钢瓶出入库交接表」「出入库交接表（其他产品）」。
一张表 = 日期 + 场次 + 哪种表；一行 = 一个车牌 + 当天开这辆车的配送员（每张表每行自己记，不绑定，历史不改）。
只录纸上的原始数，可写 10+2、10-2。表格（列、车牌行、场次）可在「表格设置」里改，只影响新表；旧表按它当时的样子。
钢瓶表左边全部算退回库房；产品表左边写「5退」才算退回（= 入库），没写「退」= 留在车上（只记录）。右边 = 新装（= 领取 / 出库）。
保存后自动生成「产品出入库情况」记录（daily_entries，source='paper'），下载格式不变，库存照扣。
保存后再改（如对账后）：每个格子的旧值→新值、谁、什么时候都记下（edits）。"""
import json, re, datetime
from db import row, rows, now, today, save_row, soft_delete, audit, meta_get, meta_set
from web import ApiError, route, attach_photos, photos_of
import logic

FORMS = {'cyl': '氧气钢瓶出入库交接表', 'prod': '出入库交接表'}
DEFAULT_SESSIONS = [{'n': '早上', 'on': True}, {'n': '中午', 'on': True}, {'n': '晚上', 'on': True}]
DEFAULT_PLATES = ['6922', '6720', '9255', '2880', '2335', '9881', '6984', '14k00', '1664c', '0668', '0928', '5928', '0910', '7539']
# 钢瓶表的固定列 → 财务表字段
FIXED = {'e40': '入库 40L空', 'f40': '入库 40L满', 'e10': '入库 10L空', 'f10': '入库 10L满', 'r40': '回收 40L', 'r10': '回收 10L',
         'hc40': '手工单更换 40L', 'hc10': '手工单更换 10L', 'hn40': '手工单新送 40L', 'hn10': '手工单新送 10L', 'o40': '出库 40L', 'o10': '出库 10L'}
PAPER_NAME = {'jy': '家用3L'}
# 次日清点规则：某天 D 要等 D+1 第一场（早上）交接表录完才算定。D+1 早上表的「左边」（钢瓶退库 / 产品写了退的、车上剩余）算 D 的。
# 只从这一天起用（以前的日期照旧：每张表左右都记在表的日期），可在 meta 'nextday_from' 改
NEXTDAY_FROM = '2026-10-19'
def nextday_from(c): return meta_get(c, 'nextday_from', None) or NEXTDAY_FROM
def day_add(d, n): return (datetime.date.fromisoformat(d) + datetime.timedelta(days=n)).isoformat()
def first_session(c):
    ss = sessions_cfg(c); return (ss[0].get('n') if ss else '') or '早上'
def shifts_left(c, sh):
    """这张表的左边要不要记到前一天：第一场（早上）且前一天在规则开始日以后"""
    return sh['session'] == first_session(c) and day_add(sh['date'], -1) >= nextday_from(c)

def default_layout(c):
    m = logic.daily_map(c)
    P = lambda k, n, g='': {'k': k, 'n': n, 'g': g, 't': 'p', 'pid': m.get(k), 'fk': k}
    F = lambda k, n, g='': {'k': k, 'n': n, 'g': g, 't': 'f'}
    prod = [P(o[0], PAPER_NAME.get(o[0], o[1]), '制氧机' if i >= 8 else '') for i, o in enumerate(logic.OTHER)]
    return {'cyl': {'lt': '早上剩余钢瓶（退库）', 'rt': '新装车数量', 'lmode': 'all',
                    'L': [F('e40', '40L空瓶'), F('f40', '40L满瓶'), F('e10', '10L空瓶'), F('f10', '10L满瓶'), P('xyg', '小氧罐'),
                          F('r40', '40L', '回收'), F('r10', '10L', '回收'), F('hc40', '40L', '手工单更换'), F('hc10', '10L', '手工单更换'),
                          F('hn40', '40L', '手工单新送'), F('hn10', '10L', '手工单新送')],
                    'R': [F('o40', '40L满瓶'), F('o10', '10L满瓶'), P('xyg', '小氧罐')]},
            'prod': {'lt': '早上剩余其他产品（不退库）', 'rt': '新装数量', 'lmode': 'mark', 'L': [dict(x) for x in prod], 'R': [dict(x) for x in prod]}}

def cur_layout(c):
    return meta_get(c, 'paper_layout', None) or default_layout(c)

def sessions_cfg(c): return meta_get(c, 'paper_sessions', None) or DEFAULT_SESSIONS
def plates_cfg(c):
    s = logic.settings(c); return list(s.get('paper_plates') if s.get('paper_plates') is not None else DEFAULT_PLATES)

def sheet_layout(c, sh):
    """旧表按它保存时的样子；第一版（还没有表格设置时）的表 = 默认样子"""
    lay = json.loads(sh['layout']) if sh.get('layout') else None
    return lay or default_layout(c)[sh['form']]

def col_labels(lay):
    lab = {}
    for side, pre in (('L', '剩余'), ('R', '新装')):
        for x in lay[side]: lab[side + '.' + x['k']] = pre + (x.get('g') or '') + x['n']
    return lab

_EXPR = re.compile(r'^\d+(\.\d+)?([+\-]\d+(\.\d+)?)*$')
def parse_cell(raw):
    """'10+2' → (12, False)；'5退' / '5t' → (5, True)；'' → (None, False)。看不懂抛 ValueError"""
    s = str(raw if raw is not None else '').strip()
    if not s: return None, False
    s = s.replace('＋', '+').replace('－', '-').replace('—', '-').replace(' ', '')
    ret = bool(re.search(r'(退|[tT])$', s))
    s = re.sub(r'(退|[tT])$', '', s)
    if not _EXPR.match(s): raise ValueError(raw)
    v = 0.0; sign = 1
    for tok in re.findall(r'[+\-]|\d+(?:\.\d+)?', s):
        if tok == '+': sign = 1
        elif tok == '-': sign = -1
        else: v += sign * float(tok)
    return (int(v) if v == int(v) else round(v, 3)), ret

def row_has_data(r):
    return any(str(v or '').strip() for v in (r.get('cells') or {}).values()) or (r.get('hand') or []) or (r.get('note_l') or '').strip() or (r.get('note_r') or '').strip()

def ctx_of(c):
    m = logic.daily_map(c)
    inv = {}
    for k, pid in m.items():
        if pid and k not in ('c40', 'c10') and pid not in inv: inv[pid] = k
    bm = {r[0] for r in c.execute('SELECT id FROM products WHERE batch_managed=1 AND deleted_at IS NULL')}
    return {'inv': inv, 'bm': bm}

def derive(lay, r, batches=None, ctx=None, side_only=None):
    """一行 → (财务表 vals, 另记的产品 extra[{product_id,qty,batch_no}], 车上剩余 info{pid: 数})；side_only='L'/'R' 只算一边"""
    ctx = ctx or {'inv': {}, 'bm': set()}
    cells = r.get('cells') or {}
    vals, take, ret, info = {}, {}, {}, {}
    def addv(k, x):
        if x: vals[k] = logic.num(vals.get(k)) + x
    fks = {}
    for side in ((side_only,) if side_only else ('L', 'R')):
        for col in lay[side]:
            v, mk = parse_cell(cells.get(side + '.' + col['k']))
            if not v: continue
            if col['t'] == 'f': addv(col['k'], v); continue
            pid = col.get('pid'); key = pid or ('fk:' + col.get('fk', ''))
            fks[key] = col.get('fk') if col.get('fk') else ctx['inv'].get(pid)
            if side == 'R': take[key] = take.get(key, 0) + v
            elif lay.get('lmode') == 'all' or mk: ret[key] = ret.get(key, 0) + v
            else: info[str(pid)] = info.get(str(pid), 0) + v
    bt = dict(batches or {}); bt.update({k: v for k, v in (r.get('batches') or {}).items() if v})
    extra = []
    for key in set(take) | set(ret):
        fk = fks.get(key); pid = key if isinstance(key, int) else None
        b = (bt.get(str(pid)) or '') if pid else ''
        if fk:
            addv('t_' + fk, take.get(key, 0)); addv('i_' + fk, ret.get(key, 0))
            if b and pid in ctx['bm']: vals['b_' + fk] = b
        elif pid:
            net = take.get(key, 0) - ret.get(key, 0)
            if net: extra.append({'product_id': pid, 'qty': net, 'batch_no': b if pid in ctx['bm'] else '', 'extra': True})
    extra.sort(key=lambda x: x['product_id'])
    return vals, extra, info

def row_pids(lay, r):
    """这一行填了数的产品（用于两张表都记了同一产品的核对提醒）"""
    out = set()
    for side in ('L', 'R'):
        for col in lay[side]:
            if col['t'] == 'p' and str((r.get('cells') or {}).get(side + '.' + col['k']) or '').strip(): out.add(col.get('pid') or col.get('fk'))
    return out

# ---------- 车牌 / 配送员 ----------
def last_drivers(c, upto=None):
    """车牌 → (配送员 id, 名称)：upto 日（含）以前最近一张表里这个车牌那一行的配送员。只用来预填"""
    res = {}
    names = {r[0]: r[1] for r in c.execute('SELECT id,name FROM couriers')}
    q = 'SELECT rows FROM paper_sheets WHERE deleted_at IS NULL' + (' AND date<=?' if upto else '') + ' ORDER BY date DESC, id DESC LIMIT 400'
    for (rj,) in c.execute(q, (upto,) if upto else ()):
        for r in json.loads(rj or '[]'):
            k = (r.get('plate') or '').lower()
            cid = r.get('courier_id_r') or r.get('courier_id')   # 新装换了人：之后开这辆车的是右边那位
            if k and k not in res and cid and row_has_data(r): res[k] = (cid, names.get(cid, r.get('driver_r') or r.get('driver') or ''))
    return res

def plates(c, upto=None):
    last = last_drivers(c, upto)
    cs = rows(c.execute('SELECT id,name FROM couriers WHERE deleted_at IS NULL ORDER BY sort,id'))
    out = []
    for p in plates_cfg(c):
        cid, nm = last.get(p.lower(), (None, ''))
        if not cid:   # 从没录过：按名称开头猜（6922 → 6922丁增），猜不到就空着
            hit = [x for x in cs if x['name'].replace(' ', '').lower().startswith(p.lower())]
            if hit: cid, nm = hit[0]['id'], hit[0]['name']
        out.append({'plate': p, 'courier_id': cid, 'name': nm})
    return out

def resolve_courier(c, r, person):
    """这一行的配送员：本行填的名字（新名字自动加进配送员名单）；没填才按车牌猜"""
    norm = lambda x: (x or '').replace(' ', '').lower()
    dn = (r.get('driver') or '').strip()
    if r.get('courier_id'):
        k = row(c.execute('SELECT id,name FROM couriers WHERE id=? AND deleted_at IS NULL', (int(r['courier_id']),)).fetchone())
        if k and (not dn or norm(k['name']) == norm(dn)): return k['id']
    cs = rows(c.execute('SELECT id,name FROM couriers WHERE deleted_at IS NULL ORDER BY sort,id'))
    new = lambda n, why: save_row(c, 'courier', {'name': n, 'kind': '配送员', 'active': 1, 'sort': (c.execute('SELECT COALESCE(MAX(sort),0) FROM couriers').fetchone()[0] or 0) + 10}, person, why)
    if dn:
        for x in cs:
            if norm(x['name']) == norm(dn): return x['id']
        return new(dn, '交接表新配送员：%s' % dn)
    p = norm(r.get('plate'))
    if not p: return None
    for x in plates(c):
        if norm(x['plate']) == p and x['courier_id']: return x['courier_id']
    for x in cs:
        if norm(x['name']).startswith(p): return x['id']
    return new(r['plate'].strip(), '交接表新车牌：%s（没填配送员）' % r['plate'])

def bm_info(c, lay_all):
    """表里出现的批次管理产品（如小氧罐）：可选批次 + 先进先出建议"""
    pids = []
    for lay in lay_all:
        for side in ('L', 'R'):
            for col in lay[side]:
                if col['t'] == 'p' and col.get('pid') and col['pid'] not in pids: pids.append(col['pid'])
    out = {}
    for pid in pids:
        p = row(c.execute('SELECT id,name,batch_managed FROM products WHERE id=?', (pid,)).fetchone())
        if not p or not p['batch_managed']: continue
        bs = [{'batch_no': b['batch_no'], 'remain': b['remain'], 'expiry': b.get('expiry') or ''} for b in logic.batch_stock(c, pid) if b['batch_no']]
        out[str(pid)] = {'name': p['name'], 'batches': bs, 'fifo': next((b['batch_no'] for b in bs if b['remain'] > 0), bs[0]['batch_no'] if bs else '')}
    return out

# ---------- 保存 / 同步 ----------
def check(lay, rws):
    errs = []; lab = col_labels(lay)
    for r in rws:
        for k, v in (r.get('cells') or {}).items():
            if k not in lab: continue
            try: parse_cell(v)
            except ValueError: errs.append('%s「%s」：%s' % (r.get('plate') or '?', lab[k], v))
    if errs: raise ApiError('有格子看不懂（只能写数字、10+2、10-2，产品表左边可写 5退）：' + '；'.join(errs[:6]) + ('……' if len(errs) > 6 else ''))

def sync(c, sid, person):
    """交接表 → 产品出入库情况记录（一行一条，按 legacy 键对应；没变的不动）。配送员用本行当天填的。
    次日清点：第一场（早上）的表，左边（退库、回收、手工单更换/新送、产品写了退的）另记一条到前一天（legacy 后缀 :L），右边新装记当天；
    「在外未交回」整行挂起不拆；人手「记到哪天」已取消（1.1.46），跨日只靠次日清点"""
    sh = row(c.execute('SELECT * FROM paper_sheets WHERE id=?', (sid,)).fetchone())
    pre = 'paper:%d:' % sid
    old = {r['legacy']: r for r in rows(c.execute("SELECT * FROM daily_entries WHERE legacy LIKE ? AND deleted_at IS NULL", (pre + '%',)))}
    keep = set()
    if sh and not sh['deleted_at']:
        lay = sheet_layout(c, sh); ctx = ctx_of(c); bts = json.loads(sh.get('batches') or '{}')
        rws = json.loads(sh['rows'] or '[]'); shift = shifts_left(c, sh); prev = day_add(sh['date'], -1)
        for r in rws:
            if not row_has_data(r): continue
            cid = resolve_courier(c, r, person)
            if not cid: continue
            r['courier_id'] = cid; r['driver'] = (c.execute('SELECT name FROM couriers WHERE id=?', (cid,)).fetchone() or [''])[0]
            cr = cid   # 右边（新装）的配送员：一般同左边；「新装换人」时是另一位
            if (r.get('driver_r') or '').strip() or r.get('courier_id_r'):
                cr = resolve_courier(c, {'driver': r.get('driver_r'), 'courier_id': r.get('courier_id_r'), 'plate': r.get('plate')}, person) or cid
            if cr != cid: r['courier_id_r'] = cr; r['driver_r'] = (c.execute('SELECT name FROM couriers WHERE id=?', (cr,)).fetchone() or [''])[0]
            else: r.pop('courier_id_r', None); r.pop('driver_r', None)
            key = pre + str(r.get('rid'))
            hand = [h for h in (r.get('hand') or []) if h.get('product_id') and logic.num(h.get('qty'))]
            nl, nr = (r.get('note_l') or '').strip(), (r.get('note_r') or '').strip()
            bd0 = None if r.get('open') else (r.get('book_date') or sh['date'])
            if shift and not r.get('open') and not r.get('book_date'):
                vl, xl, _ = derive(lay, r, bts, ctx, 'L'); vr, xr, _ = derive(lay, r, bts, ctx, 'R')
                if lay.get('lmode') != 'all':   # 产品表：次日早上左边整块（写没写退都算）= 前一天的「次日车上剩余」（v1，现算）；
                    for k in [k for k in vl if k.startswith(('i_', 'b_'))]:   # 写了退的那部分是当天（实际交回那天）入库，只进库存（si_），不进财务
                        x = vl.pop(k)
                        if k.startswith('b_'): vr.setdefault(k, x)
                        else: vr['s' + k] = logic.num(vr.get('s' + k)) + x
                    hand2, xl = hand + xr + xl, []
                    parts = [(key, cr, sh['date'], sh['date'], vr, hand2, '；'.join(x for x in [nl, nr] if x))] + ([(key + ':L', cid, prev, prev, vl, [], '')] if vl else [])
                else:
                    parts = [(key, cr, sh['date'], sh['date'], vr, hand + xr, nr), (key + ':L', cid, prev, prev, vl, xl, nl)]
            elif cr != cid:   # 同一天、左右两个人：左边记左边的人，右边记右边的人
                vl, xl, _ = derive(lay, r, bts, ctx, 'L'); vr, xr, _ = derive(lay, r, bts, ctx, 'R')
                parts = [(key, cr, sh['date'], bd0, vr, hand + xr, nr), (key + ':Ls', cid, sh['date'], bd0, vl, xl, nl)]
            else:
                vals, extra, info = derive(lay, r, bts, ctx)
                if sh['session'] == first_session(c) and sh['date'] == nextday_from(c) and not r.get('open') and not r.get('book_date'):
                    if lay.get('lmode') != 'all':
                        # 规则第一天早上的产品表：左边没写退的 = 当天起点（v0，现算），写了退的 = 当天入库，只进库存（si_），不再从当天用量里减（同以后每天）
                        for k in [k for k in vals if k.startswith('i_')]: vals['s' + k] = logic.num(vals.get('s' + k)) + vals.pop(k)
                    else:
                        # 规则第一天早上的钢瓶表：左边（退库、回收、手工单）是 18 号的车（旧规则那天，不动）→ 只进库存（s 前缀），不进 19 号财务表。
                        # 19 号 = 19 早上出库 + 19 中午入库出库 + 20 早上入库（用户定的）
                        vl, xl, _ = derive(lay, r, bts, ctx, 'L'); vals, xr, _ = derive(lay, r, bts, ctx, 'R'); extra = xr + xl
                        for k, x in vl.items():
                            if k in logic.CYL_KEYS: vals['s' + k] = logic.num(vals.get('s' + k)) + x
                            else: vals[k] = logic.num(vals.get(k)) + x
                parts = [(key, cid, sh['date'], bd0, vals, hand + extra, '；'.join(x for x in [nl, nr] if x))]
            for k, pc, od, bd, vals, hh, note in parts:
                if k != key and not vals and not hh and not note: continue
                if k == key and not vals and not hh and not note and len(parts) > 1: continue
                keep.add(k); o = old.get(k)
                if o:
                    ov = json.loads(o['vals'] or '{}')
                    if (o['courier_id'] == pc and o['out_date'] == od and o['book_date'] == bd and (o['note'] or '') == note
                            and {kk: v for kk, v in ov.items() if not kk.startswith('b_') or kk in vals} == vals and json.loads(o['hand'] or '[]') == hh): continue
                did = logic.save_daily(c, {'id': o['id'] if o else None, 'courier_id': pc, 'out_date': od, 'book_date': bd or od, 'open': bd is None,
                                           'vals': vals, 'hand': hh, 'note': note}, person)
                c.execute("UPDATE daily_entries SET source='paper', legacy=? WHERE id=?", (k, did))
        c.execute('UPDATE paper_sheets SET rows=? WHERE id=?', (json.dumps(rws, ensure_ascii=False), sid))
    for k, o in old.items():
        if k not in keep:
            soft_delete(c, 'daily', o['id'], person, '交接表里删掉/清空了这一行')
            logic.rebuild_daily(c, o['id'])

def migrate_nextday(c):
    """升级时做一次：规则开始日以后已录的早上表按次日清点规则重算（以前的日期不动）"""
    n = 0
    if not meta_get(c, 'nextday_v1'):
        for sh in rows(c.execute('SELECT id, date, session FROM paper_sheets WHERE deleted_at IS NULL')):
            if shifts_left(c, sh): sync(c, sh['id'], '系统'); n += 1
        meta_set(c, 'nextday_v1', True)
    if not meta_get(c, 'nextday_v2'):   # 1.1.2：规则第一天早上的产品表，写了退的改成只进库存（同以后每天），没写退的做当天起点
        for sh in rows(c.execute('SELECT id, date, session FROM paper_sheets WHERE deleted_at IS NULL AND date=? AND session=?', (nextday_from(c), first_session(c)))):
            sync(c, sh['id'], '系统'); n += 1
        meta_set(c, 'nextday_v2', True)
    if not meta_get(c, 'nextday_v3'):   # 1.1.2：规则第一天早上的钢瓶表左边也只进库存（同产品）
        for sh in rows(c.execute('SELECT id FROM paper_sheets WHERE deleted_at IS NULL AND date=? AND session=?', (nextday_from(c), first_session(c)))):
            sync(c, sh['id'], '系统'); n += 1
        meta_set(c, 'nextday_v3', True)
    if not meta_get(c, 'nextday_v4'):   # 1.1.46：去掉人手「记到哪天」，跨日只靠次日清点；清掉行上残留 book_date 并重算受影响表
        touched = []
        for sh in rows(c.execute('SELECT id, date, session, form, rows FROM paper_sheets WHERE deleted_at IS NULL')):
            rws = json.loads(sh['rows'] or '[]'); ch = False
            for r in rws:
                if r.get('book_date') and not r.get('open'):
                    r['book_date'] = None; ch = True
            if ch:
                c.execute('UPDATE paper_sheets SET rows=? WHERE id=?', (json.dumps(rws, ensure_ascii=False), sh['id']))
                sync(c, sh['id'], '系统'); n += 1
                touched.append('%s %s %s' % (sh['date'], sh['session'], {'cyl': '钢瓶', 'prod': '产品'}.get(sh['form'], sh['form'])))
        if touched:
            audit(c, '系统', '修改', 'paper', 0,
                  '1.1.46 去掉人手记到哪天：已清 %d 张表行上的 book_date 并按次日清点重算（%s）' % (len(touched), '、'.join(touched[:12]) + ('…' if len(touched) > 12 else '')),
                  {'book_dates_cleared': True}, {'sheets': touched})
        meta_set(c, 'nextday_v4', True)
    return n

# ---------- 次日清点：车上剩余 / 待次日清点 ----------
def _first_sheets(c, date):
    return rows(c.execute('SELECT * FROM paper_sheets WHERE date=? AND session=? AND deleted_at IS NULL', (date, first_session(c))))

def onboard(c, date, ctx=None, who='L'):
    """date 那天第一场（早上）产品表左边 = 车上剩余（who='R' 只算没写「退」的；who='L' 写没写退都算）：{配送员 id: {财务表列: 数}}（只算财务表有列的产品）。
    who='L'：算交回这辆车的人（左边，= 他前一天的「次日车上剩余」）；who='R'：算接着开出去的人（新装换人时是右边那位，= 他当天的「早上车上剩余」）"""
    ctx = ctx or ctx_of(c); out = {}
    for sh in _first_sheets(c, date):
        lay = sheet_layout(c, sh)
        if lay.get('lmode') == 'all': continue
        for r in json.loads(sh['rows'] or '[]'):
            cid = (r.get('courier_id_r') or r.get('courier_id')) if who == 'R' else r.get('courier_id')
            if not cid or r.get('open') or (r.get('book_date') and r['book_date'] != sh['date']): continue
            for col in lay['L']:
                if col['t'] != 'p': continue
                try: v, mk = parse_cell((r.get('cells') or {}).get('L.' + col['k']))
                except ValueError: continue
                fk = col.get('fk') or ctx['inv'].get(col.get('pid'))
                if v and fk and (who == 'L' or not mk): d = out.setdefault(cid, {}); d[fk] = d.get(fk, 0) + v   # 次日早上：整块都算（写了退的也是前一天晚上还在车上）
    return out

def handover(c, date, ctx=None):
    """当天中午 / 晚上「新装换人」的行：左边没写退的车上剩余跟着车交给右边的人 → 左边的人当天的「次日车上剩余」、右边的人当天的「早上车上剩余」"""
    ctx = ctx or ctx_of(c); v1, v0 = {}, {}
    for sh in rows(c.execute('SELECT * FROM paper_sheets WHERE date=? AND session<>? AND deleted_at IS NULL', (date, first_session(c)))):
        lay = sheet_layout(c, sh)
        if lay.get('lmode') == 'all': continue
        for r in json.loads(sh['rows'] or '[]'):
            a, b = r.get('courier_id'), r.get('courier_id_r')
            if not a or not b or a == b or r.get('open') or (r.get('book_date') and r['book_date'] != sh['date']): continue
            for col in lay['L']:
                if col['t'] != 'p': continue
                try: v, mk = parse_cell((r.get('cells') or {}).get('L.' + col['k']))
                except ValueError: continue
                fk = col.get('fk') or ctx['inv'].get(col.get('pid'))
                if v and not mk and fk:
                    v1.setdefault(a, {}); v1[a][fk] = v1[a].get(fk, 0) + v; v0.setdefault(b, {}); v0[b][fk] = v0[b].get(fk, 0) + v
    return v1, v0

def nextday_state(c, date):
    """date 这天：规则有没有用上、每个配送员的早上车上剩余 v0 / 次日早上车上剩余 v1、还在等哪张次日早上表（待次日清点）"""
    if date < nextday_from(c): return {'active': False}
    nxt = day_add(date, 1); ctx = ctx_of(c)
    have = {s['form'] for s in _first_sheets(c, nxt)}
    cand = {}
    for sh in rows(c.execute('SELECT * FROM paper_sheets WHERE date=? AND deleted_at IS NULL', (date,))):
        sft = shifts_left(c, sh)
        for r in json.loads(sh['rows'] or '[]'):
            if not r.get('courier_id') or not row_has_data(r) or r.get('open') or (r.get('book_date') and r['book_date'] != date): continue
            hl = any(k.startswith('L.') and str(v).strip() for k, v in (r.get('cells') or {}).items()) or (r.get('note_l') or '').strip()
            hr = any(k.startswith('R.') and str(v).strip() for k, v in (r.get('cells') or {}).items()) or (r.get('note_r') or '').strip() or r.get('hand')
            who = set()
            if hr: who.add(r.get('courier_id_r') or r['courier_id'])       # 新装的人：等次日早上交回
            if hl and not sft: who.add(r['courier_id'])                    # 中午 / 晚上的左边：也是这一天的
            for k in who: cand.setdefault(k, set()).add(sh['form'])
    # 哪天早上清点到这个人（他是某行左边的配送员、这一行有数）才算定；第二天早上没清点到他 = 接着等，到下次清点时几天合起来算
    pend, settle, gap = {}, {}, {}
    for k, forms in cand.items():
        n = next_count(c, date, k); settle[k] = n
        if n is None: pend[k] = forms; gap[k] = bool(have)
        else:
            miss = forms - {s['form'] for s in _first_sheets(c, n)}
            if miss: pend[k] = miss
    # 早上车上剩余 = 当天早上产品表左边没写「退」的（规则第一天 10-19 也一样：用 19 号早上的数量（不退库的）做起点；
    # 1.1.1 曾把第一天的起点当 0，第二天早上车上剩余照减 → 第一天出了很多负数，1.1.2 改回）
    v0 = onboard(c, date, ctx, 'R')
    v1 = onboard(c, nxt, ctx, 'L')
    for src, dst in zip(handover(c, date, ctx), (v1, v0)):
        for k, d in src.items():
            for fk, q in d.items(): dst.setdefault(k, {}); dst[k][fk] = dst[k].get(fk, 0) + q
    return {'active': True, 'next': nxt, 'v0': v0, 'v1': v1,
            'pending': {k: sorted(v) for k, v in pend.items()}, 'have_next': sorted(have), 'settle': settle, 'gap': gap}

def counted(c, date, cid):
    """date 那天早上的交接表清点到了这个配送员（他在某行左边，这一行有数）"""
    for sh in _first_sheets(c, date):
        for r in json.loads(sh['rows'] or '[]'):
            if r.get('courier_id') == cid and row_has_data(r) and not r.get('open'): return True
    return False

def next_count(c, date, cid, days=40):
    """date 以后第一次早上清点到这个人的日期（没有 = None）"""
    for (d,) in c.execute('SELECT DISTINCT date FROM paper_sheets WHERE date>? AND date<=? AND session=? AND deleted_at IS NULL ORDER BY date', (date, day_add(date, days), first_session(c))).fetchall():
        if counted(c, d, cid): return d
    return None

def period_start(c, date, cid, n):
    """和 date 一起、到 n 那天早上才清点的连续几天：往前找，返回第一天"""
    st = date
    for _ in range(31):
        p = day_add(st, -1)
        if p < nextday_from(c) or nextday_state(c, p).get('settle', {}).get(cid) != n: break
        st = p
    return st

def clean_rows(rws):
    out = []
    for i, r in enumerate(rws or []):
        out.append({'rid': str(r.get('rid') or 'r%d' % i), 'plate': (r.get('plate') or '').strip(), 'courier_id': r.get('courier_id') or None,
                    'driver': (r.get('driver') or '').strip(),
                    **({'driver_r': str(r.get('driver_r') or '').strip(), 'courier_id_r': r.get('courier_id_r') or None} if (str(r.get('driver_r') or '').strip() or r.get('courier_id_r')) else {}),
                    'cells': {k: str(v).strip() for k, v in (r.get('cells') or {}).items() if str(v or '').strip()},
                    'note_l': (r.get('note_l') or '').strip(), 'note_r': (r.get('note_r') or '').strip(),
                    'batches': {str(k): str(v).strip() for k, v in (r.get('batches') or {}).items() if str(v or '').strip()},
                    # 1.1.46：人手「记到哪天」取消；仅交回（_settle）可带 book_date；open=在外未交回
                    'book_date': (None if r.get('open') else (r.get('book_date') or None)) if r.get('_settle') else None,
                    'open': bool(r.get('open')), 'hand': r.get('hand') or [], 'extra': bool(r.get('extra')),
                    **({'crid': str(r['crid'])} if r.get('crid') else {})})
    return out

def cell_diffs(lay, before, after, bt0, bt1):
    """保存后再改：逐格比较旧值→新值"""
    lab = col_labels(lay); lab.update({'driver': '配送员', 'note_l': '左备注', 'note_r': '右备注'})
    out = []
    key = lambda r: r.get('rid')
    b = {key(r): r for r in before}; a = {key(r): r for r in after}
    for rid in list(dict.fromkeys(list(b) + list(a))):
        x, y = b.get(rid) or {}, a.get(rid) or {}
        plate = y.get('plate') or x.get('plate') or ''
        xc, yc = x.get('cells') or {}, y.get('cells') or {}
        for k in list(dict.fromkeys(list(xc) + list(yc))):
            if (xc.get(k) or '') != (yc.get(k) or ''): out.append({'rid': rid, 'plate': plate, 'k': k, 'label': lab.get(k, k), 'old': xc.get(k) or '', 'new': yc.get(k) or ''})
        for k in ('note_l', 'note_r'):
            if (x.get(k) or '') != (y.get(k) or ''): out.append({'rid': rid, 'plate': plate, 'k': k, 'label': lab[k], 'old': x.get(k) or '', 'new': y.get(k) or ''})
        if x and y and (y.get('driver') or '') and (x.get('driver') or '') != (y.get('driver') or ''):
            out.append({'rid': rid, 'plate': plate, 'k': 'driver', 'label': '配送员', 'old': x.get('driver') or '', 'new': y.get('driver') or ''})
        if x and (x.get('driver_r') or '') != (y.get('driver_r') or ''):
            out.append({'rid': rid, 'plate': plate, 'k': 'driver_r', 'label': '新装换人', 'old': x.get('driver_r') or '', 'new': y.get('driver_r') or ''})
        xb, yb = x.get('batches') or {}, y.get('batches') or {}
        for k in set(xb) | set(yb):
            if xb.get(k, '') != yb.get(k, ''): out.append({'rid': rid, 'plate': plate, 'k': 'batch:' + k, 'label': '本行批次', 'old': xb.get(k, ''), 'new': yb.get(k, '')})
        for k, lb in (('book_date', '记账日（已停用）'), ('open', '在外未交回')):
            if x and (x.get(k) or None) != (y.get(k) or None): out.append({'rid': rid, 'plate': plate, 'k': k, 'label': lb, 'old': str(x.get(k) or ''), 'new': str(y.get(k) or '')})
        if json.dumps(x.get('hand') or []) != json.dumps(y.get('hand') or []) and x:
            out.append({'rid': rid, 'plate': plate, 'k': 'hand', 'label': '手工单产品', 'old': '%d 项' % len(x.get('hand') or []), 'new': '%d 项' % len(y.get('hand') or [])})
    for k in set(bt0) | set(bt1):
        if bt0.get(k, '') != bt1.get(k, ''): out.append({'rid': '', 'plate': '整张表', 'k': 'sbatch:' + k, 'label': '默认批次', 'old': bt0.get(k, ''), 'new': bt1.get(k, '')})
    return out

def sheet_out(c, sh, ctx=None):
    sh = dict(sh); sh['rows'] = json.loads(sh['rows'] or '[]'); sh['photos'] = photos_of(c, 'paper', sh['id']); sh['form_cn'] = FORMS[sh['form']]
    sh['layout'] = sheet_layout(c, sh); sh['batches'] = json.loads(sh.get('batches') or '{}'); sh['edits'] = json.loads(sh.get('edits') or '[]')
    ctx = ctx or ctx_of(c)
    for r in sh['rows']:
        try: r['vals'], r['extra_items'], r['info'] = derive(sh['layout'], r, sh['batches'], ctx)
        except ValueError: r['vals'], r['extra_items'], r['info'] = {}, [], {}
        r['pids'] = list(row_pids(sh['layout'], r))
    return sh


def cyl_courier_order(c, date):
    """当天钢瓶交接表各场次行序（与产品页跟钢瓶 ppOrderRows 同源思路）。
    场次按表格设置顺序；场内按车牌列表序 + 表里多出来的车；每人首次出现计入（含新装换人右边）。
    没有钢瓶表 / 没人对上时返回 []，调用方回退 couriers.sort。"""
    plates = [str(p).strip() for p in plates_cfg(c) if str(p).strip()]
    ses_order = [x['n'] for x in sessions_cfg(c) if x.get('on')]
    shs = rows(c.execute("SELECT session, rows FROM paper_sheets WHERE date=? AND form='cyl' AND deleted_at IS NULL ORDER BY id", (date,)))
    by_ses = {}
    for sh in shs:
        by_ses.setdefault(sh['session'], []).extend(json.loads(sh['rows'] or '[]'))
    for s in by_ses:
        if s not in ses_order:
            ses_order.append(s)
    seen, seen_set = [], set()
    def add(cid):
        try:
            cid = int(cid) if cid is not None else None
        except (TypeError, ValueError):
            return
        if cid and cid not in seen_set:
            seen_set.add(cid); seen.append(cid)
    for ses in ses_order:
        rws = by_ses.get(ses) or []
        used, ordered = set(), []
        for p in plates:
            pl = p.lower()
            i = next((j for j, r in enumerate(rws) if j not in used and (r.get('plate') or '').strip().lower() == pl), None)
            if i is not None:
                used.add(i); ordered.append(rws[i])
        for j, r in enumerate(rws):
            if j not in used:
                ordered.append(r)
        for r in ordered:
            # 有数或已填配送员才进序（空预填车牌不占汇总位）
            if not row_has_data(r) and not r.get('courier_id') and not (r.get('driver') or '').strip():
                continue
            add(r.get('courier_id'))
            if (r.get('driver_r') or '').strip() or r.get('courier_id_r'):
                add(r.get('courier_id_r'))
    return seen


# ---------- 产品表的车牌 / 配送员跟同场次钢瓶表 ----------
def _cyl_rows(c, date, ses):
    cy = row(c.execute("SELECT rows FROM paper_sheets WHERE date=? AND session=? AND form='cyl' AND deleted_at IS NULL", (date, ses)).fetchone())
    return json.loads(cy['rows'] or '[]') if cy else None

def follow_cyl(c, date, ses, rws, old_rws=None):
    """产品表每行的车牌、配送员 = 同日同场次钢瓶表那一行的（按钢瓶表行号 crid / rid，再按车牌对上）；客户端在产品表改的不算。
    钢瓶表还没录 / 钢瓶表没有这辆车：保留这行原来存的；新行按车牌预填（上次这个车牌的人）。返回改动 [(行, 旧车牌, 旧配送员)]"""
    crs = _cyl_rows(c, date, ses) or []
    byrid = {str(r.get('rid')): r for r in crs if (r.get('plate') or '').strip()}
    bypl = {}
    for r in crs:
        if (r.get('plate') or '').strip(): bypl.setdefault(r['plate'].strip().lower(), r)
    old = {str(r.get('rid')): r for r in old_rws or []}
    pre = None; ch = []
    for r in rws:
        k = byrid.get(str(r.get('crid') or '')) or byrid.get(str(r.get('rid'))) or bypl.get((r.get('plate') or '').strip().lower())
        before = (r.get('plate'), r.get('driver'), r.get('courier_id'))
        r.pop('driver_r', None); r.pop('courier_id_r', None)          # 新装换人也只跟钢瓶表
        if k:
            r['crid'] = str(k['rid']); r['plate'] = k.get('plate') or r.get('plate'); r['driver'] = k.get('driver') or ''; r['courier_id'] = k.get('courier_id')
            if k.get('driver_r') or k.get('courier_id_r'): r['driver_r'] = k.get('driver_r') or ''; r['courier_id_r'] = k.get('courier_id_r')
        else:
            o = old.get(str(r.get('rid')))
            if o:
                r['plate'] = o.get('plate') or r.get('plate'); r['driver'] = o.get('driver') or ''; r['courier_id'] = o.get('courier_id')
                if o.get('driver_r') or o.get('courier_id_r'): r['driver_r'] = o.get('driver_r') or ''; r['courier_id_r'] = o.get('courier_id_r')
            else:
                if pre is None: pre = {p['plate'].lower(): p for p in plates(c, date)}
                p = pre.get((r.get('plate') or '').strip().lower())
                if p and p['courier_id']: r['driver'] = p['name']; r['courier_id'] = p['courier_id']
        if old.get(str(r.get('rid'))) and (r.get('plate'), r.get('driver'), r.get('driver_r')) != (old[str(r['rid'])].get('plate'), old[str(r['rid'])].get('driver'), old[str(r['rid'])].get('driver_r')): ch.append((r, before))
    return ch

def push_to_prod(c, date, ses, person):
    """钢瓶表存好后：同场次产品表的车牌 / 配送员跟着改（记修改记录），产品出入库情况跟着重算"""
    sh = row(c.execute("SELECT * FROM paper_sheets WHERE date=? AND session=? AND form='prod' AND deleted_at IS NULL", (date, ses)).fetchone())
    if not sh: return 0
    rws = json.loads(sh['rows'] or '[]'); old = json.loads(sh['rows'] or '[]')
    follow_cyl(c, date, ses, rws, old)
    ob = {str(r.get('rid')): r for r in old}; ts = now(); eds = json.loads(sh.get('edits') or '[]'); n = 0
    for r in rws:
        o = ob.get(str(r.get('rid'))) or {}
        for k, lb in (('plate', '车牌'), ('driver', '配送员'), ('driver_r', '新装换人')):
            if (o.get(k) or '') != (r.get(k) or ''):
                eds.append({'rid': r.get('rid'), 'plate': r.get('plate') or '', 'k': k, 'label': lb + '（跟钢瓶页）', 'old': o.get(k) or '', 'new': r.get(k) or '', 'ts': ts, 'by': person}); n += 1
    if rws == old: return 0
    c.execute('UPDATE paper_sheets SET rows=?, edits=?, updated_at=?, updated_by=? WHERE id=?', (json.dumps(rws, ensure_ascii=False), json.dumps(eds, ensure_ascii=False), ts, person, sh['id']))
    sync(c, sh['id'], person)
    return n

def save_sheet(c, d, person, base_ts=None):
    form = d.get('form'); date = d.get('date') or today(); ses = (d.get('session') or '').strip()
    if form not in FORMS: raise ApiError('表的种类不对')
    if not ses: raise ApiError('请选场次（早上 / 中午 …）')
    sid = int(d['id']) if d.get('id') else None
    cur = None
    if sid:
        cur = row(c.execute('SELECT * FROM paper_sheets WHERE id=?', (sid,)).fetchone())
        if not cur or cur['deleted_at']: raise ApiError('这张表已被删除', 404)
        if base_ts is not None and abs((cur['updated_at'] or cur['created_at'] or 0) - float(base_ts)) > 1e-6:
            raise ApiError('这张表刚被别人改过（可能是手机上录的），请重新载入后再改', 409)
    lay = sheet_layout(c, cur) if cur else cur_layout(c)[form]
    rws = clean_rows(d.get('rows')); check(lay, rws)
    if form == 'prod': follow_cyl(c, date, ses, rws, json.loads(cur['rows'] or '[]') if cur else None)   # 车牌、配送员只跟钢瓶表
    dup = c.execute('SELECT id FROM paper_sheets WHERE date=? AND session=? AND form=? AND deleted_at IS NULL AND id<>?', (date, ses, form, sid or 0)).fetchone()
    if dup: raise ApiError('%s %s 的%s已经录过了，请在那张上修改' % (date, ses, FORMS[form]), 409)
    bm = bm_info(c, [lay])
    bts = {str(k): str(v).strip() for k, v in (d.get('batches') or {}).items() if str(v or '').strip()}
    for pid, inf in bm.items():   # 批次产品：没选就用先进先出建议
        if not bts.get(pid) and inf['fifo']: bts[pid] = inf['fifo']
    for pid, b in list(bts.items()) + [(k, v) for r in rws for k, v in r['batches'].items()]:
        if pid in bm and b not in [x['batch_no'] for x in bm[pid]['batches']]: raise ApiError('%s 没有批次「%s」' % (bm[pid]['name'], b))
    n = sum(1 for r in rws if row_has_data(r))
    rec = {'id': sid, 'date': date, 'session': ses, 'form': form, 'rows': json.dumps(rws, ensure_ascii=False), 'note': d.get('note') or '', 'batches': json.dumps(bts, ensure_ascii=False)}
    if cur:
        df = cell_diffs(lay, json.loads(cur['rows'] or '[]'), rws, json.loads(cur.get('batches') or '{}'), bts)
        ts = now()
        eds = json.loads(cur.get('edits') or '[]') + [dict(x, ts=ts, by=person) for x in df]
        rec['edits'] = json.dumps(eds, ensure_ascii=False)
        summ = '修改 %s %s %s：' % (date, ses, FORMS[form]) + ('；'.join('%s %s %s→%s' % (x['plate'], x['label'], x['old'] or '空', x['new'] or '空') for x in df[:20]) or '无格子变化') + ('……' if len(df) > 20 else '')
        sid = save_row(c, 'paper', rec, person, summ)
    else:
        rec['layout'] = json.dumps(lay, ensure_ascii=False); rec['edits'] = '[]'
        sid = save_row(c, 'paper', rec, person, '%s %s %s（%d 行）' % (date, ses, FORMS[form], n))
        c.execute('UPDATE paper_sheets SET updated_at=? WHERE id=?', (now(), sid))
    # 新车牌（加的行）记进车牌列表，下次也显示
    s = logic.settings(c); pl = plates_cfg(c); low = [p.lower() for p in pl]; add = []
    for r in rws:
        if r['plate'] and row_has_data(r) and r['plate'].lower() not in low and not re.search(r'[\u4e00-\u9fff]', r['plate']): add.append(r['plate']); low.append(r['plate'].lower())
    if add: s2 = meta_get(c, 'settings', {}) or {}; s2['paper_plates'] = pl + add; meta_set(c, 'settings', s2)
    sync(c, sid, person)
    if form == 'cyl': push_to_prod(c, date, ses, person)
    return sid

# ---------------- 接口 ----------------
@route('GET', '/api/paper')
def api_paper(c, q, b, me):
    date = q.get('date') or today(); ctx = ctx_of(c)
    shs = [sheet_out(c, s, ctx) for s in rows(c.execute('SELECT * FROM paper_sheets WHERE date=? AND deleted_at IS NULL ORDER BY id', (date,)))]
    lay = cur_layout(c)
    ses = [x['n'] for x in sessions_cfg(c) if x.get('on')] + [s['session'] for s in shs]
    return {'date': date, 'sheets': shs, 'sessions': list(dict.fromkeys(ses)), 'plates': plates(c, date), 'layout': lay,
            'bm': bm_info(c, [lay['cyl'], lay['prod']] + [s['layout'] for s in shs])}

@route('POST', '/api/paper/save', 'entry')
def api_paper_save(c, q, b, me):
    sid = save_sheet(c, b['data'], me['name'], b.get('base_ts'))
    if b.get('photo_ids') is not None: attach_photos(c, b.get('photo_ids'), 'paper', sid, replace=True)
    return {'id': sid, 'sheet': sheet_out(c, row(c.execute('SELECT * FROM paper_sheets WHERE id=?', (sid,)).fetchone()))}

@route('POST', '/api/paper/row', 'entry')
def api_paper_row(c, q, b, me):
    """手机：一辆车一行，并进当天该场次的表（没有就新建）"""
    d = b['data']; form = d.get('form'); date = d.get('date') or today(); ses = (d.get('session') or '').strip()
    if form not in FORMS or not ses: raise ApiError('请选表和场次')
    r = clean_rows([d.get('row') or {}])[0]
    if not r['plate']: raise ApiError('请选车牌')
    sh = row(c.execute('SELECT * FROM paper_sheets WHERE date=? AND session=? AND form=? AND deleted_at IS NULL', (date, ses, form)).fetchone())
    rws = json.loads(sh['rows']) if sh else []
    hit = next((i for i, x in enumerate(rws) if (x.get('plate') or '').lower() == r['plate'].lower()), None)
    if hit is None:
        r['rid'] = 'm%d' % int(now() * 1000); r['extra'] = r['plate'].lower() not in [p.lower() for p in plates_cfg(c)]; rws.append(r)
    else:
        o = rws[hit]; r['rid'] = o.get('rid'); r['extra'] = o.get('extra', False); r['hand'] = r['hand'] or o.get('hand') or []
        r['open'] = o.get('open', False); r['book_date'] = None if r['open'] else o.get('book_date')  # 保留交回日；人手记到哪天已由 migrate 清掉
        if not r.get('driver_r') and o.get('driver_r'): r['driver_r'] = o['driver_r']; r['courier_id_r'] = o.get('courier_id_r')   # 电脑上设的「新装换人」保留
        rws[hit] = r
    bts = json.loads(sh['batches'] or '{}') if sh else (d.get('batches') or {})
    sid = save_sheet(c, {'id': sh['id'] if sh else None, 'date': date, 'session': ses, 'form': form, 'rows': rws, 'note': sh['note'] if sh else '', 'batches': bts}, me['name'])
    attach_photos(c, b.get('photo_ids'), 'paper', sid)
    return {'id': sid}

@route('POST', '/api/paper/settle', 'entry')
def api_paper_settle(c, q, b, me):
    """在外未交回的那一行：交回，记到某天（自动写「X–Y 合并」）"""
    sid = int(b['sheet_id']); sh = row(c.execute('SELECT * FROM paper_sheets WHERE id=?', (sid,)).fetchone())
    bd = b.get('book_date') or today()
    if bd < sh['date']: raise ApiError('交回日不能早于领取日')
    rws = json.loads(sh['rows'])
    for r in rws:
        if str(r.get('rid')) == str(b['rid']):
            r['open'] = False; r['book_date'] = bd; r['_settle'] = True   # 交回允许写 book_date；人手记到哪天走不了这条
    save_sheet(c, {'id': sid, 'date': sh['date'], 'session': sh['session'], 'form': sh['form'], 'rows': rws, 'note': sh['note'], 'batches': json.loads(sh['batches'] or '{}')}, me['name'])
    return {'ok': 1}

def move_plan(c, sid, date, ses, pair=True):
    """改日期 / 场次（录错了日期）：要搬哪几张、会不会撞上已有的表、哪些行自己选了「记到哪天」。不改任何东西"""
    sh = row(c.execute('SELECT * FROM paper_sheets WHERE id=?', (int(sid),)).fetchone())
    if not sh or sh['deleted_at']: raise ApiError('这张表已被删除', 404)
    ses = (ses or '').strip()
    if not date or not re.match(r'^\d{4}-\d{2}-\d{2}$', date): raise ApiError('请选新的日期')
    if not ses: raise ApiError('请选新的场次')
    if date == sh['date'] and ses == sh['session']: raise ApiError('日期和场次都没变')
    mates = [sh]
    other = row(c.execute("SELECT * FROM paper_sheets WHERE date=? AND session=? AND form<>? AND deleted_at IS NULL", (sh['date'], sh['session'], sh['form'])).fetchone())
    if pair and other: mates.append(other)
    ids = [x['id'] for x in mates]; clash = []; warn = []
    for x in mates:
        d = c.execute('SELECT id FROM paper_sheets WHERE date=? AND session=? AND form=? AND deleted_at IS NULL AND id NOT IN (%s)' % ','.join('?' * len(ids)), (date, ses, x['form'], *ids)).fetchone()
        if d: clash.append('%s %s 已经有%s了（不会覆盖）。请先打开那张核对；确实多余的话先删掉它，再来改日期' % (date, ses, FORMS[x['form']]))
        for r in json.loads(x['rows'] or '[]'):
            if r.get('book_date') and row_has_data(r):
                warn.append({'form': x['form'], 'plate': r.get('plate') or '', 'book_date': r['book_date'], 'fix': r['book_date'] < date})
            if r.get('open') and row_has_data(r): warn.append({'form': x['form'], 'plate': r.get('plate') or '', 'open': True, 'fix': False})
    return {'sheets': [{'id': x['id'], 'form': x['form'], 'date': x['date'], 'session': x['session']} for x in mates], 'has_other': bool(other),
            'other_form': other['form'] if other else None, 'clash': clash, 'warn': warn}

def move_sheet(c, sid, date, ses, pair, person):
    """把表（和同场次的另一张）改到新的日期 / 场次；记操作记录；新旧两天的出入库、库存、次日清点全部重算。
    行里自己选的「记到哪天」：比新日期还早的（不可能早于领取日）改回记当天，其余照旧"""
    pl = move_plan(c, sid, date, ses, pair); ses = ses.strip()
    if pl['clash']: raise ApiError('；'.join(pl['clash']), 409)
    ts = now(); olds = set()
    for x in pl['sheets']:
        sh = row(c.execute('SELECT * FROM paper_sheets WHERE id=?', (x['id'],)).fetchone())
        rws = json.loads(sh['rows'] or '[]'); fixed = []
        for r in rws:
            if r.get('book_date') and r['book_date'] < date: fixed.append(r.get('plate') or ''); r['book_date'] = None
        eds = json.loads(sh.get('edits') or '[]') + [{'rid': '', 'plate': '', 'k': 'date', 'label': '日期 / 场次', 'old': '%s %s' % (sh['date'], sh['session']), 'new': '%s %s' % (date, ses), 'ts': ts, 'by': person}]
        c.execute('UPDATE paper_sheets SET date=?, session=?, rows=?, edits=?, updated_at=?, updated_by=? WHERE id=?',
                  (date, ses, json.dumps(rws, ensure_ascii=False), json.dumps(eds, ensure_ascii=False), ts, person, sh['id']))
        summ = '把 %s %s %s 改到 %s %s' % (sh['date'], sh['session'], {'cyl': '钢瓶表', 'prod': '产品表'}[sh['form']], date, ses) + ('（%s 原来「记到」的日期早于新日期，改回记当天）' % '、'.join(fixed) if fixed else '')
        audit(c, person, '修改', 'paper', sh['id'], summ, {'date': sh['date'], 'session': sh['session']}, {'date': date, 'session': ses})
        olds.add((sh['date'], sh['session']))
    for x in pl['sheets']: sync(c, x['id'], person)   # 出入库、库存按新日期重算（旧日期的记录随之移走）
    for d0, s0 in olds | {(date, ses)}: push_to_prod(c, d0, s0, person)   # 产品表的车牌、配送员重新跟同场次钢瓶表
    return pl

@route('GET', '/api/paper/move_check')
def api_paper_move_check(c, q, b, me):
    return move_plan(c, q.get('id'), q.get('date'), q.get('session'), q.get('pair', '1') != '0')

@route('POST', '/api/paper/move', 'entry')
def api_paper_move(c, q, b, me):
    pl = move_sheet(c, b['id'], b.get('date'), b.get('session') or '', b.get('pair', True), me['name'])
    return {'ok': 1, 'moved': pl['sheets']}

@route('POST', '/api/paper/delete', 'delete')
def api_paper_delete(c, q, b, me):
    sid = int(b['id']); soft_delete(c, 'paper', sid, me['name']); sync(c, sid, me['name']); return {'ok': 1}

@route('POST', '/api/paper/plates', 'entry')
def api_paper_plates(c, q, b, me):
    """在表上直接隐藏 / 加车牌（只改以后的表）"""
    pl = [str(p).strip() for p in b.get('plates') or [] if str(p).strip()]
    s = meta_get(c, 'settings', {}) or {}; before = plates_cfg(c); s['paper_plates'] = list(dict.fromkeys(pl)); meta_set(c, 'settings', s)
    audit(c, me['name'], '修改', 'settings', 0, '交接表车牌：' + '、'.join(before) + ' → ' + '、'.join(s['paper_plates']), {'paper_plates': before}, {'paper_plates': s['paper_plates']})
    return {'ok': 1}

# ---------- 表格设置 ----------
@route('GET', '/api/paper/layout')
def api_paper_layout(c, q, b, me):
    return {'layout': cur_layout(c), 'default': default_layout(c), 'plates': plates_cfg(c), 'sessions': sessions_cfg(c),
            'fixed': FIXED, 'nextday_from': nextday_from(c), 'nextday_from_default': NEXTDAY_FROM}

@route('POST', '/api/paper/layout', 'settings')
def api_paper_layout_save(c, q, b, me):
    lay = b['layout']; out = {}
    for f in FORMS:
        L = lay.get(f) or {}; o = {'lt': (L.get('lt') or '').strip() or '剩余', 'rt': (L.get('rt') or '').strip() or '新装', 'lmode': 'all' if L.get('lmode') == 'all' else 'mark'}
        for side in ('L', 'R'):
            cols, seen = [], set()
            for x in L.get(side) or []:
                n = (x.get('n') or '').strip()
                if not n: raise ApiError('%s 有一列没有名称' % FORMS[f])
                if x.get('t') == 'f':
                    if x.get('k') not in FIXED: raise ApiError('固定列不对')
                    col = {'k': x['k'], 'n': n, 'g': (x.get('g') or '').strip(), 't': 'f'}
                else:
                    pid = int(x['pid']) if x.get('pid') else None
                    if not pid and not x.get('fk'): raise ApiError('%s「%s」没选对应的库存产品' % (FORMS[f], n))
                    if pid and not c.execute('SELECT 1 FROM products WHERE id=? AND deleted_at IS NULL', (pid,)).fetchone(): raise ApiError('产品不存在：%s' % n)
                    k = x.get('k') or ('p%d' % pid)
                    col = {'k': k, 'n': n, 'g': (x.get('g') or '').strip(), 't': 'p', 'pid': pid}
                    if x.get('fk') and (not pid or pid == logic.daily_map(c).get(x['fk'])): col['fk'] = x['fk']
                while col['k'] in seen: col['k'] += '_'
                seen.add(col['k']); cols.append(col)
            o[side] = cols
        out[f] = o
    before = cur_layout(c)
    meta_set(c, 'paper_layout', out)
    ses = [{'n': str(x.get('n') or '').strip(), 'on': bool(x.get('on'))} for x in b.get('sessions') or [] if str(x.get('n') or '').strip()]
    if ses: meta_set(c, 'paper_sessions', ses)
    if b.get('plates') is not None:
        s = meta_get(c, 'settings', {}) or {}; s['paper_plates'] = list(dict.fromkeys(str(p).strip() for p in b['plates'] if str(p).strip())); meta_set(c, 'settings', s)
    nd_before = nextday_from(c)
    if 'nextday_from' in b:
        nd = (b.get('nextday_from') or '').strip() or None
        if nd:
            try: datetime.date.fromisoformat(nd)
            except ValueError: raise ApiError('次日清点开始日格式不对（要用 YYYY-MM-DD）')
        meta_set(c, 'nextday_from', nd)
    desc = lambda L: '；'.join('%s：左 %s｜右 %s' % (FORMS[f], '、'.join(x['n'] for x in L[f]['L']), '、'.join(x['n'] for x in L[f]['R'])) for f in FORMS)
    audit(c, me['name'], '修改', 'settings', 0, '交接表表格设置（只影响新表）：' + desc(out)
          + ('；次日清点开始日 %s → %s' % (nd_before, nextday_from(c)) if nextday_from(c) != nd_before else ''),
          dict(before, nextday_from=nd_before) if isinstance(before, dict) else before,
          dict(out, nextday_from=nextday_from(c)))
    return {'ok': 1}
