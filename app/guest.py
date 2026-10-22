# -*- coding: utf-8 -*-
"""访客借用登记（手机 /m/guest，不用密码）
- 访客只能用这里的 /api/guest/* 两个接口（取表单选项 / 提交）；有单独的路由表 GUEST_ROUTES，跟员工接口互不相通；按 IP 限流、限大小。
- 提交后是一张「待确认」的借用申请（loan_requests），不动库存；员工在「借用归还 → 访客登记」里核对、可修改，
  确认后变成正式借用单（自动编号，照常扣库存），或者拒绝。"""
import json, re, time, base64, os, uuid, datetime, threading, collections
import db, logic, importers, loans
from db import row, rows, now, today, save_row, audit
from web import route, ApiError, photos_of, attach_photos

db.ENTITY_TABLE['loan_req'] = 'loan_requests'; db.ENTITY_CN['loan_req'] = '访客借用登记'
SCHEMA = f"""CREATE TABLE IF NOT EXISTS loan_requests(id INTEGER PRIMARY KEY, status TEXT DEFAULT '待确认', name TEXT DEFAULT '', phone TEXT DEFAULT '',
  orgs TEXT DEFAULT '[]', escort TEXT DEFAULT '', escort_phone TEXT DEFAULT '', remark TEXT DEFAULT '', items TEXT DEFAULT '[]', ip TEXT DEFAULT '',
  loan_id INTEGER, handled_by TEXT DEFAULT '', handled_at REAL, reject_reason TEXT DEFAULT '', {db.AUD});"""

# v1.1.1：只有单位必填；客户、销售人、取货人（可多个）都可不填。老登记的 name/phone 当作客户
NEW_COLS = [('loan_requests', 'cust_name', "TEXT DEFAULT ''"), ('loan_requests', 'cust_phone', "TEXT DEFAULT ''"), ('loan_requests', 'sales_name', "TEXT DEFAULT ''"),
            ('loan_requests', 'sales_phone', "TEXT DEFAULT ''"), ('loan_requests', 'pickups', "TEXT DEFAULT '[]'")]
def ensure_schema(c):
    c.executescript(SCHEMA)
    for t, col, decl in NEW_COLS:
        if col not in db.cols(c, t): c.execute(f'ALTER TABLE {t} ADD COLUMN {col} {decl}')
    # 老登记：姓名 / 电话 → 客户（只补空的，可重复跑）
    c.execute("UPDATE loan_requests SET cust_name=name, cust_phone=phone WHERE IFNULL(cust_name,'')='' AND IFNULL(cust_phone,'')='' AND (IFNULL(name,'')!='' OR IFNULL(phone,'')!='')")
if 'loan_requests' not in db.SCHEMA: db.SCHEMA += '\n' + SCHEMA   # db.init() 也一起建
for _x in NEW_COLS:
    if _x not in db.ADD_COLS: db.ADD_COLS.append(_x)

# ---------------- 限流（内存里，按 IP） ----------------
_hits = collections.defaultdict(collections.deque); _hl = threading.Lock()
LIMITS = {'form': (60, 60), 'submit': (5, 600), 'submit_all': (60, 3600)}   # 次数, 秒
def rate_ok(kind, key):
    n, sec = LIMITS[kind]; t = time.time()
    with _hl:
        d = _hits[(kind, key)]
        while d and d[0] < t - sec: d.popleft()
        if len(d) >= n: return False
        d.append(t); return True
def reset_limits():
    with _hl: _hits.clear()

GUEST_ROUTES = {}
def groute(method, path):
    def deco(fn): GUEST_ROUTES[(method, path)] = fn; return fn
    return deco
MAX_BODY = 16 * 1024 * 1024; MAX_PHOTO = 5 * 1024 * 1024; MAX_PHOTOS = 4; MAX_ITEMS = 30

def known_orgs(c):
    os_ = [o['org'] for o in loans.all_orgs(c)][:12]
    for d in (logic.settings(c).get('guest_orgs') or ['一院', '二院']):
        if d not in os_: os_.append(d)
    return os_

@groute('GET', '/api/guest/form')
def g_form(c, q, b, ip):
    if not rate_ok('form', ip): raise ApiError('操作太频繁，请稍后再试', 429)
    used = {r[0]: r[1] for r in c.execute('SELECT product_id, COUNT(*) FROM loan_items GROUP BY product_id')}
    ps = rows(c.execute('SELECT id,name,spec,unit,temp_name,sort FROM products WHERE deleted_at IS NULL AND merged_into IS NULL ORDER BY sort, id'))
    items = [{'id': p['id'], 'label': logic.product_label(p), 'unit': p['unit'] or '', 'uses': used.get(p['id'], 0)} for p in ps]
    s = logic.settings(c)
    return {'site': s.get('site_name') or '库房', 'orgs': known_orgs(c), 'products': items, 'shared': loans.SHARED, 'today': today(), 'names': s.get('ui_names') or {}}

def _s(v, n): return re.sub(r'[\x00-\x1f]', ' ', str(v or '')).strip()[:n]

def _photo(c, data, tag, ip):
    m = re.match(r'data:(image/(?:jpeg|png|webp));base64,(.*)$', data or '', re.S)
    if not m: raise ApiError('照片格式不对')
    raw = base64.b64decode(m.group(2), validate=False)
    if len(raw) > MAX_PHOTO: raise ApiError('照片太大（单张最多 5MB）')
    if not (raw[:3] == b'\xff\xd8\xff' or raw[:8] == b'\x89PNG\r\n\x1a\n' or (raw[:4] == b'RIFF' and raw[8:12] == b'WEBP')): raise ApiError('不是图片')
    ext = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}[m.group(1)]
    sub = datetime.date.today().strftime('%Y%m'); os.makedirs(os.path.join(db.PHOTO_DIR, sub), exist_ok=True)
    rel = '%s/g%s%s' % (sub, uuid.uuid4().hex[:16], ext)
    with open(os.path.join(db.PHOTO_DIR, rel), 'wb') as f: f.write(raw)
    return c.execute('INSERT INTO photos(entity,entity_id,tag,path,name,size,created_at,created_by) VALUES(?,?,?,?,?,?,?,?)',
                     ('loan_req', None, tag, rel, '访客' + ('签字' if tag == 'sign' else '照片'), len(raw), now(), '访客')).lastrowid

PHONE_RE = r'[\d\-+ ()（）转]{3,30}'
def _phone(v, what):
    v = _s(v, 30)
    if v and not re.fullmatch(PHONE_RE, v): raise ApiError('%s电话不对（可以不填）' % what)
    return v
def clean_people(b):
    """客户、销售人、取货人：都可不填；电话填了就检查一下格式"""
    cust = _s(b.get('cust_name', b.get('name')), 40); cphone = _phone(b.get('cust_phone', b.get('phone')), '客户')
    sales = _s(b.get('sales_name'), 40); sphone = _phone(b.get('sales_phone'), '销售人')
    pk = []
    for p in (b.get('pickups') or [])[:6]:
        if not isinstance(p, dict): continue
        n, ph = _s(p.get('name'), 40), _phone(p.get('phone'), '取货人')
        if n or ph: pk.append({'name': n, 'phone': ph})
    return {'cust_name': cust, 'cust_phone': cphone, 'sales_name': sales, 'sales_phone': sphone, 'pickups': pk}
def who_of(d):
    """一句话说清是谁来借（留痕、列表用）"""
    return d.get('cust_name') or next((p['name'] for p in d.get('pickups') or [] if p.get('name')), '') or d.get('sales_name') or ''

def clean_request(c, b):
    pp = clean_people(b)
    orgs = [_s(o, 40) for o in (b.get('orgs') or []) if _s(o, 40)][:5]
    if not orgs: raise ApiError('请选或填借用单位')
    items = []
    for it in (b.get('items') or [])[:MAX_ITEMS + 1]:
        pid = it.get('product_id'); pname = _s(it.get('product_name'), 60)
        if pid:
            p = row(c.execute('SELECT * FROM products WHERE id=? AND deleted_at IS NULL', (int(pid),)).fetchone())
            if not p: raise ApiError('有一样物品已不存在，请重新选')
            pname = logic.product_label(p); pid = p['id']
        elif not pname: continue
        approx = 1 if it.get('approx') in (1, True, '1') else 0
        try: qty = float(it.get('qty') or 0)
        except (TypeError, ValueError): raise ApiError('「%s」数量不对' % pname)
        if not approx and not (0 < qty <= 100000): raise ApiError('「%s」请填数量（数不清可选「若干」）' % pname)
        org = _s(it.get('org'), 40)
        if len(orgs) > 1 and org not in orgs + [loans.SHARED]: raise ApiError('借了多个单位时，请给「%s」选归属（或「%s」）' % (pname, loans.SHARED))
        items.append({'product_id': pid, 'product_name': pname, 'qty': 0 if approx else qty, 'approx': approx, 'qty_text': '若干' if approx else '', 'org': org if len(orgs) > 1 else ''})
    if not items: raise ApiError('请至少选一样要借的东西')
    if len(items) > MAX_ITEMS: raise ApiError('一次最多 %d 样' % MAX_ITEMS)
    yiyuan = any('一院' in o for o in orgs)
    return {'name': who_of(pp), 'phone': pp['cust_phone'], 'cust_name': pp['cust_name'], 'cust_phone': pp['cust_phone'], 'sales_name': pp['sales_name'], 'sales_phone': pp['sales_phone'],
            'pickups': json.dumps(pp['pickups'], ensure_ascii=False), 'orgs': json.dumps(orgs, ensure_ascii=False), 'items': json.dumps(items, ensure_ascii=False),
            'escort': _s(b.get('escort'), 40) if yiyuan else '', 'escort_phone': _s(b.get('escort_phone'), 30) if yiyuan else '', 'remark': _s(b.get('remark'), 300)}

@groute('POST', '/api/guest/submit')
def g_submit(c, q, b, ip):
    if not rate_ok('submit', ip) or not rate_ok('submit_all', '*'): raise ApiError('提交太频繁，请稍后再试，或直接找库房人员', 429)
    d = clean_request(c, b); d['ip'] = ip; d['status'] = '待确认'
    phs = (b.get('photos') or [])[:MAX_PHOTOS]
    pids = [_photo(c, x, '', ip) for x in phs]
    if b.get('signature'): pids.append(_photo(c, b['signature'], 'sign', ip))
    rid = save_row(c, 'loan_req', d, ('访客 ' + d['name']).strip(), '访客登记借用：%s%s' % ('、'.join(json.loads(d['orgs'])), ('（%s）' % d['name']) if d['name'] else ''))
    for p in pids: c.execute('UPDATE photos SET entity_id=? WHERE id=?', (rid, p))
    return {'ok': 1, 'no': rid}

# ---------------- 员工端 ----------------
def req_full(c, r):
    r = dict(r); r['orgs'] = json.loads(r['orgs'] or '[]'); r['items'] = json.loads(r['items'] or '[]'); r['photos'] = photos_of(c, 'loan_req', r['id'])
    r['pickups'] = json.loads(r.get('pickups') or '[]')
    if not r.get('cust_name') and not r.get('cust_phone'): r['cust_name'], r['cust_phone'] = r.get('name') or '', r.get('phone') or ''   # 老登记
    if r.get('loan_id'):
        l = row(c.execute('SELECT slip_no FROM loans WHERE id=?', (r['loan_id'],)).fetchone()); r['slip_no'] = l['slip_no'] if l else ''
    return r

def pending_count(c):
    return c.execute("SELECT COUNT(*) FROM loan_requests WHERE deleted_at IS NULL AND status='待确认'").fetchone()[0]

@route('GET', '/api/loan_req')
def api_loan_req(c, q, b, me):
    st = q.get('status', '待确认')
    w = "deleted_at IS NULL" + (" AND status=?" if st else ''); a = [st] if st else []
    return {'items': [req_full(c, r) for r in rows(c.execute('SELECT * FROM loan_requests WHERE %s ORDER BY id DESC LIMIT 200' % w, a))], 'pending': pending_count(c)}

@route('GET', '/api/loan_req/one')
def api_loan_req_one(c, q, b, me):
    r = row(c.execute('SELECT * FROM loan_requests WHERE id=?', (int(q['id']),)).fetchone())
    if not r: raise ApiError('登记不存在', 404)
    return req_full(c, r)

def _open_req(c, rid):
    r = row(c.execute('SELECT * FROM loan_requests WHERE id=? AND deleted_at IS NULL', (rid,)).fetchone())
    if not r: raise ApiError('登记不存在', 404)
    if r['status'] != '待确认': raise ApiError('这条登记已经%s了' % r['status'].replace('已', ''))
    return r

def loan_from_req(r):
    """访客登记 → 借用单表单（员工可再改）"""
    J = lambda v: v if isinstance(v, list) else json.loads(v or '[]')
    orgs = J(r['orgs']); pk = r['pickups'] if isinstance(r.get('pickups'), list) else json.loads(r.get('pickups') or '[]')
    cust = r.get('cust_name') or ('' if r.get('cust_phone') else r.get('name') or ''); cphone = r.get('cust_phone') or ('' if r.get('cust_name') else r.get('phone') or '')
    return {'date': today(), 'user_to': cust or next((p['name'] for p in pk if p.get('name')), ''), 'orgs': orgs, 'escort': r['escort'], 'phone': r['escort_phone'],
            'cust_name': cust, 'cust_phone': cphone, 'salesperson': r.get('sales_name') or '', 'sales_phone': r.get('sales_phone') or '', 'pickups': pk,
            'need_return': 1, 'use_type': '外单位' if orgs else '自用', 'source': '',
            'remark': '；'.join(x for x in ('访客登记 #%d' % r['id'], r['remark']) if x),
            'items': J(r['items'])}

@route('POST', '/api/loan_req/confirm', 'entry')
def api_loan_req_confirm(c, q, b, me):
    rid = int(b['id']); r = _open_req(c, rid)
    d = dict(b.get('data') or loan_from_req(req_full(c, r))); d.pop('id', None)
    d['handler'] = d.get('handler') or me['name']
    lid = loans.save_loan(c, d, me['name'])
    pids = b.get('photo_ids')
    if pids is None: pids = [p['id'] for p in photos_of(c, 'loan_req', rid)]
    attach_photos(c, pids, 'loan', lid)
    slip = row(c.execute('SELECT slip_no FROM loans WHERE id=?', (lid,)).fetchone())['slip_no']
    save_row(c, 'loan_req', {'id': rid, 'status': '已确认', 'loan_id': lid, 'handled_by': me['name'], 'handled_at': now()}, me['name'], '确认访客登记 → 借用单 %s' % slip)
    return {'id': lid, 'slip_no': slip}

@route('POST', '/api/loan_req/reject', 'entry')
def api_loan_req_reject(c, q, b, me):
    rid = int(b['id']); _open_req(c, rid); reason = _s(b.get('reason'), 200)
    save_row(c, 'loan_req', {'id': rid, 'status': '已拒绝', 'reject_reason': reason, 'handled_by': me['name'], 'handled_at': now()}, me['name'], '拒绝访客登记' + ('：' + reason if reason else ''))
    return {'ok': 1}
