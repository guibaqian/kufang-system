# -*- coding: utf-8 -*-
"""业务逻辑：库存（盘点锚点 + 流水）、批次先进先出、各单据生成流水、产品出入库情况汇总"""
import json, datetime
from db import row, rows, now, today, save_row, soft_delete, restore, audit, meta_get, meta_set, cols

# ---------- 产品出入库情况列定义（与 产品出入库情况 原表列一一对应） ----------
CYL = [('o40', 'B'), ('o10', 'C'), ('e40', 'D'), ('f40', 'E'), ('e10', 'F'), ('f10', 'G'), ('r40', 'H'), ('r10', 'I'),
       ('hc40', 'N'), ('hc10', 'O'), ('hn40', 'P'), ('hn10', 'Q')]
CYL_CN = {'o40': '出库40L', 'o10': '出库10L', 'e40': '入库40L空', 'f40': '入库40L满', 'e10': '入库10L空', 'f10': '入库10L满',
          'r40': '回收40L', 'r10': '回收10L', 'hc40': '手工单更换40L', 'hc10': '手工单更换10L', 'hn40': '手工单新送40L', 'hn10': '手工单新送10L'}
# 其他产品：key, 表头名, 领取列, 入库列, 当天总出库列, 默认对应产品名
OTHER = [('shb', '湿化杯', 'T', 'AI', 'AW', '湿化杯'), ('xyg', '小氧罐', 'U', 'AJ', 'AX', '便携式医用供氧器'),
         ('byg', '鼻氧管', 'V', 'AK', 'AY', '3M鼻氧管'), ('tc', '40L推车', 'W', 'AL', 'AZ', '40L钢瓶推车'),
         ('zt', '枕头', 'X', 'AM', 'BA', '富氧枕'), ('emi', '耳麦式', 'Y', 'AN', 'BB', '耳麦式鼻氧管'),
         ('xyy', '血氧仪', 'Z', 'AO', 'BC', '指甲式脉搏血氧仪'), ('txw', '碳纤维', 'AA', 'AP', 'BD', '1.6L碳纤维'),
         ('m3', '医用3L', 'AB', 'AQ', 'BE', '3L医用制氧机'), ('m5', '医用5L', 'AC', 'AR', 'BF', '5L医用制氧机'),
         ('cz', '车载', 'AD', 'AS', 'BG', '车载制氧机'), ('jy', '家用', 'AE', 'AT', 'BH', '家用制氧机'),
         ('bx', '便携式', 'AF', 'AU', 'BI', '便携式制氧机'), ('j1', '家用1L', 'AG', 'AV', 'BJ', '家用制氧机1L')]
CYL_PRODUCTS = {'c40': '40L钢瓶', 'c10': '10L钢瓶'}
CYL_KEYS = [k for k, _ in CYL]
VAL_KEYS = ['s' + k for k in CYL_KEYS] + [k for k, _ in CYL] + ['t_' + o[0] for o in OTHER] + ['i_' + o[0] for o in OTHER] + ['si_' + o[0] for o in OTHER]   # si_ = 只进库存的退（次日早上表写了「退」的：当天入库，不进财务表）

DEFAULT_SETTINGS = {
    'paper_plates': ['6922', '6720', '9255', '2880', '2335', '9881', '6984', '14k00', '1664c', '0668', '0928', '5928', '0910', '7539'],  # 纸质交接表的车牌行（顺序同纸）；配送员每张表每行自己填
    'site_name': '库房出入库', 'lan_port': 8080,
    'moves_show_daily': True,   # 库存流水 / 库存变化记录里显示交接表批量配送（只影响显示，库存、结存照算）
    'backup_dir': '', 'backup_keep': 30,
    'expiry_alert_days': 90, 'pin_cache_minutes': 5,
    'outside_base': {'40': None, '10': None},  # 在外钢瓶起始数（未设置=未知）
    'u8_types': ['外来客户购买', '后台客户购买', 'app客户氧补不足'],  # 仅当单据来源=U8单时的细分（不是出库类型）
    'out_kinds': ['客户自提', '销售出库', '厂内自用', '领用出库', '换货', '其他出库'],  # 1.1.34：去掉与客户自提重复的「自提出库」
    'sources': ['app手工单', 'U8单', '无单'],
    'categories': ['钢瓶', '制氧机', '配件', '血氧仪', '液氧罐', '碳纤维', '厂内自用', '工程材料', '其他'],
    'misc_categories': ['暂存', '工程', '未知'],
    'guest_orgs': ['一院', '二院'],               # 访客页 / 借用单常用单位
    'ui_names': {},                                # 名称设置：{原名称: 显示名称}，只改显示（前端默认把「产品出入库情况」显示成「日表」）
    'report_order': [],                            # 报表页签顺序（空 = 默认）
    'nav_order': [],                               # 顶部导航顺序（空 = 默认 home→daily→out→…；settings 固定靠右）
    'nav_hidden': ['misc', 'slip', 'backup'],      # 顶栏默认隐藏（杂物/称重/备份）；路由仍可用，设置里可再显示
    'print': {'company': '', 'footer': True},      # 打印抬头（公司名）、页脚打印人/时间
    'print_templates': {},                         # 打印页出库单/入库单模板（空=内置默认；见 printpage.DEFAULT_TEMPLATES）
    'defaults': {'session': '早上', 'out_kind': '客户自提', 'out_source': '', 'list_days': 0},
    'ocr': {'ask_push': True, 'default_rate': 8, 'ledger_auto_next': True, 'ledger_prefer_next': ''},  # 识别；换算表→入出库旧批不够自动接下一批；优先新批号可空
}

# 名称设置里曾误加的别名键（用途曾写做出库待提/明细/核销）。只清显示映射。
BAD_UI_NAME_KEYS = frozenset({'待提出库'})

# 历史出库类型合并：界面/默认/筛选只保留「客户自提」；库内旧「自提出库」升级时写入合并，读时也归一。
OUT_KIND_MERGE = {'自提出库': '客户自提'}

def normalize_out_kind(k, default='客户自提'):
    k = (k or '').strip()
    k = OUT_KIND_MERGE.get(k, k)
    return k or default

def name_originals(s=None):
    """界面上会出现的「原名称」集合（选项 / 常用菜单），用于发现「显示为」撞到另一条原名。"""
    s = s or DEFAULT_SETTINGS
    out = set()
    for k in ('out_kinds', 'sources', 'u8_types', 'categories', 'misc_categories', 'guest_orgs'):
        for x in (s.get(k) or DEFAULT_SETTINGS.get(k) or []):
            if x: out.add(str(x).strip())
    # 菜单/分页等常见原名（与 p_sys nmGroups 对齐的一小部分，够抓撞名）
    out.update(['首页', '出库', '到货', '借用归还', '产品与库存', '库房杂物', '报表', '打印', '称重单', '数据备份', '设置',
                '产品出入库情况', '单笔', '批量', '出库记录', '领用出库单',
                '未归还', '部分归还', '已归还', '待入U8', '已入U8', '不入U8', '配送员', '点位'])
    return {x for x in out if x}

def clean_names(m, known_originals=None, out_kinds=None):
    """去掉空/同名；再清掉会让两条原名显示成同一个字的错误别名（如 待提出库→客户自提）。"""
    out = {}
    for k, v in (m or {}).items():
        k = str(k).strip()[:60]; v = str(v if v is not None else '').strip()[:60]
        if k and v and v != k: out[k] = v
        if len(out) >= 500: break
    kinds = {str(x).strip() for x in (out_kinds or DEFAULT_SETTINGS.get('out_kinds') or []) if x}
    known = set(known_originals) if known_originals is not None else None
    scrubbed = {}
    for k, v in out.items():
        if k in BAD_UI_NAME_KEYS:
            continue
        # 两个出库类型互相改显示名撞成同一个字
        if k in kinds and v in kinds and k != v:
            continue
        # 其它已知原名之间互撞（来源/分类/菜单等）
        if known is not None and k in known and v in known and k != v:
            continue
        # 「其他」自造名显示成某个出库类型原名（待提出库→客户自提）→ 和芯片撞名
        if k not in kinds and v in kinds and k != v:
            continue
        scrubbed[k] = v
    return scrubbed

def _merge_default_list(cur, base, before=None):
    """补上默认列表里新增的项（不改已有顺序；有 before 时插到它前面）。"""
    cur = list(cur or [])
    for x in base or []:
        if x in cur: continue
        if before and before in cur: cur.insert(cur.index(before), x)
        else: cur.append(x)
    return cur

def settings(c):
    s = dict(DEFAULT_SETTINGS); s.update(meta_get(c, 'settings', {}) or {})
    # 出库类型等固定选项：升级后默认里新增的项自动出现（如「换货」）；并去掉已合并的历史类型
    kinds = _merge_default_list(s.get('out_kinds'), DEFAULT_SETTINGS['out_kinds'], before='其他出库')
    s['out_kinds'] = [k for k in kinds if k not in OUT_KIND_MERGE]
    s['sources'] = _merge_default_list(s.get('sources'), DEFAULT_SETTINGS['sources'])
    s['u8_types'] = _merge_default_list(s.get('u8_types'), DEFAULT_SETTINGS['u8_types'])
    d = dict(s.get('defaults') or {})
    if d.get('out_kind') in OUT_KIND_MERGE:
        d['out_kind'] = OUT_KIND_MERGE[d['out_kind']]
        s['defaults'] = d
    # 名称设置：读时也清掉撞名别名；不把已合并类型再塞回芯片
    s['ui_names'] = clean_names(s.get('ui_names') or {}, name_originals(s), s.get('out_kinds'))
    return s

def daily_map(c):
    """日表列 → 产品 id（可在设置里改）"""
    m = meta_get(c, 'daily_map', None)
    if m: return m
    m = {}
    byname = {r['name']: r['id'] for r in c.execute('SELECT id,name FROM products WHERE deleted_at IS NULL AND merged_into IS NULL ORDER BY id')}
    for k, n in CYL_PRODUCTS.items(): m[k] = byname.get(n)
    for o in OTHER: m[o[0]] = byname.get(o[5])
    return m

def num(v):
    try:
        if v in (None, ''): return 0
        f = float(v); return int(f) if f == int(f) else f
    except Exception: return 0

# ---------- 库存 ----------
def _after(m_date, m_ts, c_date, c_ts):
    return m_date > c_date or (m_date == c_date and m_ts > c_ts)

def stock_all(c, product_ids=None):
    """返回 {pid: {'known':bool,'qty':x,'count_date':..,'count_qty':..,'since':..,'warn':bool}}"""
    counts = {}
    for r in c.execute("SELECT * FROM stock_counts WHERE deleted_at IS NULL AND (batch_no='' OR batch_no IS NULL) ORDER BY date, created_at"):
        counts[r['product_id']] = dict(r)
    mv = {}
    for r in c.execute('SELECT product_id,qty,date,ts FROM moves'):
        mv.setdefault(r['product_id'], []).append(r)
    pids = product_ids or [r[0] for r in c.execute('SELECT id FROM products')]
    out = {}
    for pid in pids:
        cn = counts.get(pid); ms = mv.get(pid, [])
        if not cn:
            out[pid] = {'known': False, 'qty': None, 'moves': len(ms)}
            continue
        q = cn['qty'] + sum(m['qty'] for m in ms if _after(m['date'], m['ts'], cn['date'], cn['created_at']))
        q = round(q, 3)
        out[pid] = {'known': True, 'qty': q, 'warn': q < 0, 'count_date': cn['date'], 'count_qty': cn['qty'], 'count_by': cn['created_by']}
    return out

def computed_now(c, pid, date=None, ts=None):
    st = stock_all(c, [pid])[pid]
    return st['qty'] if st['known'] else None

def batch_stock(c, pid):
    """批次剩余：有批次盘点则以盘点为锚，否则 = 该批次全部流水之和（到货 − 出库）"""
    bs = rows(c.execute('SELECT * FROM batches WHERE product_id=? AND deleted_at IS NULL ORDER BY COALESCE(NULLIF(expiry,""),"9999"), COALESCE(NULLIF(prod_date,""),"9999"), id', (pid,)))
    known = {b['batch_no'] for b in bs}
    extra = [r[0] for r in c.execute("SELECT DISTINCT batch_no FROM moves WHERE product_id=? AND batch_no<>''", (pid,)) if r[0] not in known]
    for e in extra: bs.append({'id': None, 'product_id': pid, 'batch_no': e, 'prod_date': '', 'expiry': '', 'remark': '（流水中出现，未登记）'})
    for b in bs:
        cn = row(c.execute("SELECT * FROM stock_counts WHERE deleted_at IS NULL AND product_id=? AND batch_no=? ORDER BY date DESC, created_at DESC LIMIT 1", (pid, b['batch_no'])).fetchone())
        ms = rows(c.execute('SELECT qty,date,ts,src FROM moves WHERE product_id=? AND batch_no=?', (pid, b['batch_no'])))
        b['in_qty'] = round(sum(m['qty'] for m in ms if m['qty'] > 0), 3)
        b['out_qty'] = round(-sum(m['qty'] for m in ms if m['qty'] < 0), 3)
        if cn: b['remain'] = round(cn['qty'] + sum(m['qty'] for m in ms if _after(m['date'], m['ts'], cn['date'], cn['created_at'])), 3); b['counted'] = True
        else: b['remain'] = round(sum(m['qty'] for m in ms), 3); b['counted'] = False
    return bs

def batch_remain_trusted(c, pid):
    """产品级盘点过，或任一登记批次做过批次盘点 → 批次余量可信。
    可信时出库启用「不够接下一批」，禁止再扣成负；未盘点仍可随便扣（现场未整理）。
    历史已有负批不在此抹平。"""
    st = stock_all(c, [pid]).get(pid) or {}
    if st.get('known'):
        return True
    for b in batch_stock(c, pid):
        if b.get('id') and b.get('counted'):
            return True
    return False

def fifo_pick(c, pid, qty, prefer='', next_prefer='', allow_short=None, exclude_src=None, ignore_out_id=None):
    """按规则分配批次：返回 [(batch_no, qty)]。
    - 只从剩余>0 的批次扣，绝不加深已有负批；
    - prefer：首选批（有正剩余才先扣）；next_prefer：不够时优先的下一批；其余按效期/生产日期 FIFO；
    - allow_short：None=未可信余量时允许把差额扣在末批（未盘点随便扣）；
      False=正剩余不够则 ValueError（可信余量，堵住新负批）；True=强制允许短扣。
    ignore_out_id：改旧出库单时加回该单已扣量，避免「含本单流水」误判无剩余。
    exclude_src 保留兼容，未使用。"""
    qty = float(num(qty))
    if qty <= 0:
        return []
    bs = [dict(b) for b in batch_stock(c, pid) if b.get('id')]
    if ignore_out_id:
        for m in c.execute("SELECT batch_no, qty FROM moves WHERE src='out' AND src_id=? AND product_id=?", (ignore_out_id, pid)):
            for b in bs:
                if b['batch_no'] == m['batch_no']:
                    b['remain'] = round(float(b.get('remain') or 0) - float(m['qty'] or 0), 3)
                    break
    trusted = batch_remain_trusted(c, pid)
    if allow_short is None:
        allow_short = not trusted
    by_no = {b['batch_no']: b for b in bs}
    ordered, seen = [], set()
    def push(bn):
        bn = (bn or '').strip()
        if not bn or bn in seen:
            return
        b = by_no.get(bn)
        if not b:
            return
        if float(b.get('remain') or 0) <= 0:
            return
        ordered.append(b); seen.add(bn)
    push(prefer)
    push(next_prefer)
    for b in bs:
        push(b['batch_no'])
    res, left = [], qty
    for b in ordered:
        if left <= 0:
            break
        avail = float(b.get('remain') or 0)
        if avail <= 0:
            continue
        take = min(avail, left)
        # 合并同批连续段
        if res and res[-1][0] == b['batch_no']:
            res[-1] = (res[-1][0], round(res[-1][1] + take, 3))
        else:
            res.append((b['batch_no'], take))
        left = round(left - take, 3)
    if left > 0:
        if not allow_short:
            pos = [b for b in bs if float(b.get('remain') or 0) > 0]
            avail_txt = '、'.join('%s剩%g' % (b['batch_no'], b['remain']) for b in pos) or '无'
            got = qty - left
            pref = (prefer or '').strip()
            tip = ('当前首选 %s 不够；' % pref) if pref else ''
            raise ValueError('批次正剩余不够：需要 %g，可扣合计 %g（还差 %g）。正剩余：%s。%s请换批、拆行或减少数量（负批不计入可扣，历史负批不自动抹平）。' % (qty, got, left, avail_txt, tip))
        dump = (prefer or '').strip() or (res[-1][0] if res else (bs[-1]['batch_no'] if bs else ''))
        if res and res[-1][0] == dump:
            res[-1] = (res[-1][0], round(res[-1][1] + left, 3))
        else:
            res.append((dump, left))
    return res

# ---------- 流水生成 ----------
def clear_moves(c, src, sid): c.execute('DELETE FROM moves WHERE src=? AND src_id=?', (src, sid))

def add_move(c, pid, qty, date, ts, src, sid, batch='', label=''):
    if not pid or not qty: return
    c.execute('INSERT INTO moves(product_id,batch_no,qty,date,ts,src,src_id,label) VALUES(?,?,?,?,?,?,?,?)',
              (pid, batch or '', qty, date, ts, src, sid, label))

def rebuild_out(c, oid):
    clear_moves(c, 'out', oid)
    o = row(c.execute('SELECT * FROM out_orders WHERE id=?', (oid,)).fetchone())
    if not o or o['deleted_at']: return
    who = o['customer'] or o['recipient'] or ''
    exch = o['kind'] == '换货'
    for it in c.execute('SELECT * FROM out_items WHERE order_id=?', (oid,)):
        d = dict(it)
        side = (d.get('side') or 'out')
        if side not in ('out', 'in'): side = 'out'
        if side == 'in':
            add_move(c, d['product_id'], float(d['qty']), o['date'], o['created_at'], 'out', oid, d.get('batch_no') or '', '换货 换入 ' + who)
        else:
            lab = ('换货 换出 ' if exch else (o['kind'] + ' ')) + who
            add_move(c, d['product_id'], -float(d['qty']), o['date'], o['created_at'], 'out', oid, d.get('batch_no') or '', lab.strip())

def rebuild_arrival(c, aid):
    clear_moves(c, 'arrival', aid)
    a = row(c.execute('SELECT * FROM arrivals WHERE id=?', (aid,)).fetchone())
    if not a or a['deleted_at'] or not a['product_id']: return
    add_move(c, a['product_id'], float(a['qty'] or 0), a['date'], a['created_at'], 'arrival', aid, a['batch_no'], a['kind'] + ' ' + (a['dest'] or ''))

def rebuild_daily(c, did):
    clear_moves(c, 'daily', did)
    e = row(c.execute('SELECT * FROM daily_entries WHERE id=?', (did,)).fetchone())
    if not e or e['deleted_at']: return
    m = daily_map(c); v = json.loads(e['vals'] or '{}'); d = e['book_date'] or e['out_date']; ts = e['created_at']
    cname = (c.execute('SELECT name FROM couriers WHERE id=?', (e['courier_id'],)).fetchone() or [''])[0]
    lab = '产品出入库情况 ' + cname
    # se40 / sf40 …：只进库存的退（规则第一天早上钢瓶表左边，不进财务表）
    n40 = num(v.get('o40')) - num(v.get('e40')) - num(v.get('f40')) - num(v.get('se40')) - num(v.get('sf40'))
    n10 = num(v.get('o10')) - num(v.get('e10')) - num(v.get('f10')) - num(v.get('se10')) - num(v.get('sf10'))
    add_move(c, m.get('c40'), -n40, d, ts, 'daily', did, '', lab)
    add_move(c, m.get('c10'), -n10, d, ts, 'daily', did, '', lab)
    for o in OTHER:
        net = num(v.get('t_' + o[0])) - num(v.get('i_' + o[0])) - num(v.get('si_' + o[0]))
        pid = m.get(o[0])
        if not net or not pid: continue
        bat = (v.get('b_' + o[0]) or '')
        add_move(c, pid, -net, d, ts, 'daily', did, bat, lab)
    for h in json.loads(e['hand'] or '[]'):
        add_move(c, h.get('product_id'), -num(h.get('qty')), d, ts, 'daily', did, h.get('batch_no', ''), lab + (' 交接表' if h.get('extra') else ' 手工单'))

def rebuild_loan(c, lid):
    clear_moves(c, 'loan', lid)
    l = row(c.execute('SELECT * FROM loans WHERE id=?', (lid,)).fetchone())
    if not l or l['deleted_at']: return
    lab = '借用 ' + (l['user_to'] or l['unit'] or '')
    for it in c.execute('SELECT * FROM loan_items WHERE loan_id=?', (lid,)):
        add_move(c, it['product_id'], -float(it['qty']), l['date'], l['created_at'], 'loan', lid, it['batch_no'], lab)
    for r in c.execute('SELECT * FROM loan_returns WHERE loan_id=? AND deleted_at IS NULL', (lid,)):
        for it in json.loads(r['items'] or '[]'):
            add_move(c, it.get('product_id'), float(num(it.get('qty'))), r['date'], r['created_at'], 'loan', lid, it.get('batch_no', ''), '归还 ' + (l['user_to'] or l['unit'] or ''))

REBUILD = {'out': rebuild_out, 'arrival': rebuild_arrival, 'daily': rebuild_daily, 'loan': rebuild_loan}

def rebuild_all(c):
    c.execute('DELETE FROM moves')
    for src, fn in REBUILD.items():
        t = {'out': 'out_orders', 'arrival': 'arrivals', 'daily': 'daily_entries', 'loan': 'loans'}[src]
        for (i,) in c.execute(f'SELECT id FROM {t}').fetchall(): fn(c, i)

# ---------- 产品 ----------
def product_label(p): return p['name'] + ((' ' + p['spec']) if p.get('spec') else '')

def find_product(c, name):
    """精确匹配（名称、名称+规格、别名），不做前缀匹配——修复旧系统前缀匹配导致库存算错"""
    n = (name or '').strip()
    if not n: return None
    for p in rows(c.execute('SELECT * FROM products WHERE deleted_at IS NULL AND merged_into IS NULL')):
        if n == p['name'] or n == product_label(p) or n.replace(' ', '') == product_label(p).replace(' ', '') or n in json.loads(p['aliases'] or '[]'):
            return p
    return None

def ensure_product(c, name, person, unit='个', category='其他'):
    p = find_product(c, name)
    if p: return p['id']
    return save_row(c, 'product', {'name': name.strip(), 'unit': unit, 'category': category}, person, '出库时新增产品')

def merge_products(c, keep_id, drop_ids, person):
    keep = row(c.execute('SELECT * FROM products WHERE id=?', (keep_id,)).fetchone())
    al = set(json.loads(keep['aliases'] or '[]'))
    for d in drop_ids:
        p = row(c.execute('SELECT * FROM products WHERE id=?', (d,)).fetchone())
        al.add(p['name']); al.add(product_label(p))
        for t, col in (('out_items', 'product_id'), ('arrivals', 'product_id'), ('loan_items', 'product_id'), ('batches', 'product_id'), ('stock_counts', 'product_id'), ('pending', 'product_id')):
            c.execute(f'UPDATE {t} SET {col}=? WHERE {col}=?', (keep_id, d))
        c.execute('UPDATE products SET merged_into=?, deleted_at=?, deleted_by=? WHERE id=?', (keep_id, now(), person, d))
        audit(c, person, '合并', 'product', d, f'并入「{product_label(keep)}」', p, None)
    al.discard(keep['name'])
    c.execute('UPDATE products SET aliases=? WHERE id=?', (json.dumps(sorted(al), ensure_ascii=False), keep_id))
    # 日表映射、归还明细里的产品 id 也一起改
    m = daily_map(c)
    for k, v in list(m.items()):
        if v in drop_ids: m[k] = keep_id
    meta_set(c, 'daily_map', m)
    for r in rows(c.execute('SELECT id,items FROM loan_returns')):
        its = json.loads(r['items'] or '[]'); ch = False
        for it in its:
            if it.get('product_id') in drop_ids: it['product_id'] = keep_id; ch = True
        if ch: c.execute('UPDATE loan_returns SET items=? WHERE id=?', (json.dumps(its, ensure_ascii=False), r['id']))
    for r in rows(c.execute('SELECT id,hand FROM daily_entries')):
        its = json.loads(r['hand'] or '[]'); ch = False
        for it in its:
            if it.get('product_id') in drop_ids: it['product_id'] = keep_id; ch = True
        if ch: c.execute('UPDATE daily_entries SET hand=? WHERE id=?', (json.dumps(its, ensure_ascii=False), r['id']))
    rebuild_all(c)

# ---------- 盘点 ----------
def save_count(c, pid, qty, date, person, note='', batch_counts=None):
    before = computed_now(c, pid)
    ts = now()
    if batch_counts:
        for bn, bq in batch_counts.items():
            save_row(c, 'count', {'product_id': pid, 'batch_no': bn, 'qty': float(bq), 'date': date, 'note': note, 'created_at': ts}, person, f'批次 {bn} 盘点 {bq}')
        qty = sum(float(v) for v in batch_counts.values())
    diff = None if before is None else round(float(qty) - before, 3)
    p = row(c.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone())
    s = f'盘点「{product_label(p)}」实数 {qty}' + ('' if before is None else f'，系统数 {before}，盘点调整 {diff:+g}')
    return save_row(c, 'count', {'product_id': pid, 'batch_no': '', 'qty': float(qty), 'date': date, 'computed_before': before,
                                 'diff': diff, 'note': note, 'created_at': ts}, person, s)

# ---------- 出库 ----------
def items_of(c, oid): return rows(c.execute('SELECT * FROM out_items WHERE order_id=? ORDER BY id', (oid,)))

def save_out(c, data, person):
    """data: 订单字段 + items:[{product_id|product_name, qty, batch_no, note, side}]
    side: out=发出（默认）；in=换货收回。kind=换货 时新单必须两边都有；旧换货单（只有发出）仍可原样改，不强迫补换入。"""
    items = data.get('items') or []
    if not items: raise ValueError('没有产品')
    if not data.get('date'): data['date'] = today()
    kind = normalize_out_kind(data.get('kind'))
    norm = []
    for it in items:
        q = float(num(it.get('qty')))
        if q <= 0: continue
        side = (it.get('side') or 'out')
        if side not in ('out', 'in'): side = 'out'
        if kind != '换货': side = 'out'   # 非换货忽略 side
        pid = it.get('product_id')
        if not pid:
            if not (it.get('product_name') or '').strip(): continue
            pid = ensure_product(c, it['product_name'], person)
        p = row(c.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone())
        if not p: raise ValueError('产品不存在')
        bn = (it.get('batch_no') or '').strip()
        next_bn = (it.get('next_batch_no') or '').strip()
        if p['batch_managed'] and side == 'out':
            # 未盘点且手选了批：整笔扣该批（现场未整理，随便扣），不强制接下一批
            if bn and not batch_remain_trusted(c, pid):
                norm.append({'product_id': pid, 'product_name': product_label(p), 'qty': q, 'batch_no': bn, 'note': it.get('note', ''), 'side': side})
            else:
                # 空批=FIFO；已选批=先扣该批正剩余，不够按 next_batch_no / FIFO 溢出
                # 可信余量时正剩余不够会 ValueError，禁止新扣成负
                for b, bq in fifo_pick(c, pid, q, prefer=bn, next_prefer=next_bn, ignore_out_id=data.get('id')):
                    note = it.get('note', '')
                    norm.append({'product_id': pid, 'product_name': product_label(p), 'qty': bq, 'batch_no': b, 'note': note, 'side': side})
        else:
            # 换入可记批号（选填）；无批号不强制先进先出
            norm.append({'product_id': pid, 'product_name': product_label(p), 'qty': q, 'batch_no': bn, 'note': it.get('note', ''), 'side': side})
    if not norm: raise ValueError('数量都为 0')
    outs = [i for i in norm if i['side'] == 'out']
    inns = [i for i in norm if i['side'] == 'in']
    oid = data.get('id')
    old_items = items_of(c, oid) if oid else None
    if kind == '换货':
        had_in = bool(old_items and any((x.get('side') or 'out') == 'in' for x in old_items))
        # 新单，或旧单已有换入：必须两边齐全（谁换谁）
        if (not oid or had_in or inns) and (not outs or not inns):
            raise ValueError('换货要两边都填：换出（发出新品）和换入（收回原品）')
        if not outs:
            raise ValueError('换货至少要有一样换出（发出）的产品')
    fields = {k: data.get(k) for k in ('id', 'date', 'kind', 'source', 'u8_no', 'u8_type', 'customer', 'contact', 'phone', 'salesperson',
                                       'courier', 'recipient', 'purpose', 'remark', 'mode', 'batch_key') if k in data}
    fields['kind'] = normalize_out_kind(fields.get('kind'))
    who = fields.get('customer') or fields.get('recipient') or ''
    if fields.get('kind') == '换货':
        def _fmt(lst, tag):
            return tag + '：' + '、'.join(f"{i['product_name']}×{i['qty']:g}" for i in lst) if lst else ''
        parts = [p for p in (_fmt(outs, '换出'), _fmt(inns, '换入')) if p]
        summ = f"换货 {who}：" + '；'.join(parts)
    else:
        summ = f"{fields.get('kind')} {who}：" + '、'.join(f"{i['product_name']}×{i['qty']:g}" for i in norm)
    oid = save_row(c, 'out', fields, person, summ if not oid else None, old_items, norm)
    c.execute('DELETE FROM out_items WHERE order_id=?', (oid,))
    has_side = 'side' in cols(c, 'out_items')
    for i in norm:
        if has_side:
            c.execute('INSERT INTO out_items(order_id,product_id,product_name,qty,batch_no,note,side) VALUES(?,?,?,?,?,?,?)',
                      (oid, i['product_id'], i['product_name'], i['qty'], i['batch_no'], i['note'], i['side']))
        else:
            c.execute('INSERT INTO out_items(order_id,product_id,product_name,qty,batch_no,note) VALUES(?,?,?,?,?,?)',
                      (oid, i['product_id'], i['product_name'], i['qty'], i['batch_no'], i['note']))
    if fields.get('customer'): touch_customer(c, fields['customer'], fields.get('contact', ''), fields.get('phone', ''), fields['date'])
    for t in data.get('u8_type', '') and [data['u8_type']] or []:
        s = meta_get(c, 'settings', {}) or {}
        lst = s.get('u8_types') or list(DEFAULT_SETTINGS['u8_types'])
        if t not in lst: lst.append(t); s['u8_types'] = lst; meta_set(c, 'settings', s)
    rebuild_out(c, oid)
    return oid

def touch_customer(c, name, contact, phone, date):
    r = c.execute('SELECT * FROM customers WHERE name=? AND deleted_at IS NULL', (name,)).fetchone()
    if r:
        c.execute('UPDATE customers SET contact=COALESCE(NULLIF(?,""),contact), phone=COALESCE(NULLIF(?,""),phone), last_date=MAX(last_date,?), uses=uses+1 WHERE id=?',
                  (contact or '', phone or '', date, r['id']))
    else:
        c.execute('INSERT INTO customers(name,contact,phone,last_date,uses,created_at) VALUES(?,?,?,?,1,?)', (name, contact or '', phone or '', date, now()))

# ---------- 到货 ----------
def save_arrival(c, data, person):
    if not data.get('date'): data['date'] = today()
    pid = data.get('product_id') or None
    if not data.get('id') and not data.get('u8_status'):   # 没选：按产品「默认不入U8」
        p = row(c.execute('SELECT no_u8 FROM products WHERE id=?', (pid,)).fetchone()) if pid else None
        data['u8_status'] = '不入U8' if (p and p['no_u8']) or data.get('kind') == '其他入库' else '待入U8'
    if pid and data.get('batch_no'):
        b = c.execute('SELECT id FROM batches WHERE product_id=? AND batch_no=?', (pid, data['batch_no'])).fetchone()
        bd = {'product_id': pid, 'batch_no': data['batch_no'], 'prod_date': data.get('prod_date', ''), 'expiry': data.get('expiry', '')}
        if b:
            bd['id'] = b['id']
            if not bd['prod_date']: bd.pop('prod_date')
            if not bd['expiry']: bd.pop('expiry')
        save_row(c, 'batch', bd, person, f"批次 {data['batch_no']}")
        c.execute('UPDATE batches SET deleted_at=NULL WHERE product_id=? AND batch_no=?', (pid, data['batch_no']))
    if data.get('u8_status') == '已入U8' and not data.get('u8_at'): data['u8_at'] = now()
    aid = save_row(c, 'arrival', data, person, None if data.get('id') else f"{data.get('kind','到货')} {data.get('name','')} {data.get('spec','')} ×{num(data.get('qty'))}")
    rebuild_arrival(c, aid)
    return aid

# ---------- 产品出入库情况 ----------
def save_daily(c, data, person):
    v = {}
    for k in VAL_KEYS:
        x = num((data.get('vals') or {}).get(k))
        if x: v[k] = x
    for o in OTHER:
        b = ((data.get('vals') or {}).get('b_' + o[0]) or '').strip()
        if b: v['b_' + o[0]] = b
    hand = [h for h in (data.get('hand') or []) if h.get('product_id') and num(h.get('qty'))]
    m = daily_map(c)
    # 小氧罐等批次产品：未选批次 → 先进先出
    for o in OTHER:
        pid = m.get(o[0]); net = num(v.get('t_' + o[0])) - num(v.get('i_' + o[0]))
        if pid and net > 0 and not v.get('b_' + o[0]):
            p = row(c.execute('SELECT batch_managed FROM products WHERE id=?', (pid,)).fetchone())
            if p and p['batch_managed']:
                pk = fifo_pick(c, pid, net)
                if pk: v['b_' + o[0]] = pk[0][0]
    rec = {'courier_id': int(data['courier_id']), 'out_date': data.get('out_date') or today(),
           'book_date': data.get('book_date') if data.get('book_date') is not None else data.get('out_date') or today(),
           'vals': json.dumps(v, ensure_ascii=False), 'hand': json.dumps(hand, ensure_ascii=False), 'note': data.get('note', '')}
    if data.get('open'): rec['book_date'] = None
    if data.get('id'): rec['id'] = data['id']
    cn = (c.execute('SELECT name FROM couriers WHERE id=?', (rec['courier_id'],)).fetchone() or [''])[0]
    did = save_row(c, 'daily', rec, person, None if rec.get('id') else f"{cn} {rec['out_date']}" + (' 在外未交回' if rec['book_date'] is None else ''))
    rebuild_daily(c, did)
    return did

def md(d):
    y, m, dd = d.split('-'); return f'{int(m)}.{int(dd)}'

def daily_rows(c, date, raw=False):
    """当天下载用：按配送员合并（多次相加），跨天写备注，手工单产品拼进备注"""
    s = settings(c); m = daily_map(c)
    pname = {r['id']: r['name'] for r in c.execute('SELECT id,name FROM products')}
    ents = rows(c.execute('SELECT e.*, k.name cname, k.sort csort FROM daily_entries e JOIN couriers k ON k.id=e.courier_id WHERE e.deleted_at IS NULL AND e.book_date=? ORDER BY k.sort, k.id, e.id', (date,)))
    by = {}
    for e in ents:
        g = by.setdefault(e['courier_id'], {'name': e['cname'], 'vals': {}, 'notes': [], 'hand': {}, 'extra': {}, 'entries': 0, 'sort': (e['csort'], e['courier_id'])})
        g['entries'] += 1
        for k, x in json.loads(e['vals'] or '{}').items():
            if k.startswith('b_'): continue
            g['vals'][k] = num(g['vals'].get(k)) + num(x)
        if e['out_date'] != e['book_date']:
            t = f"{md(e['out_date'])}–{md(e['book_date'])} 合并".replace('.', '.')
            t = f"{int(e['out_date'][8:])}–{int(e['book_date'][8:])} 合并" if e['out_date'][:7] == e['book_date'][:7] else f"{md(e['out_date'])}–{md(e['book_date'])} 合并"
            if t not in g['notes']: g['notes'].append(t)
        if e['note'] and e['note'] not in g['notes']: g['notes'].append(e['note'])
        for h in json.loads(e['hand'] or '[]'):
            n = short_name(c, h.get('product_id'), pname); t = g['extra'] if h.get('extra') else g['hand']
            t[n] = num(t.get(n)) + num(h.get('qty'))
    # 次日清点（规则开始日以后）：其他产品当天用量 = 早上车上剩余 v0 + 新装 − 退 − 次日早上车上剩余 v1；次日早上表还没录 = 待次日清点
    import paper
    nd = paper.nextday_state(c, date)
    if nd['active']:
        for cid in set(nd['v0']) | set(nd['v1']) | set(nd['pending']):
            if cid not in by:
                k = row(c.execute('SELECT name, sort FROM couriers WHERE id=?', (cid,)).fetchone())
                if not k: continue
                by[cid] = {'name': k['name'], 'vals': {}, 'notes': [], 'hand': {}, 'extra': {}, 'entries': 0, 'sort': (k['sort'], cid)}
            g = by[cid]
            for pre, src in (('v0_', nd['v0']), ('v1_', nd['v1'])):
                for fk, q in (src.get(cid) or {}).items(): g['vals'][pre + fk] = num(g['vals'].get(pre + fk)) + q
            if cid in nd['pending']: g['pending'] = [{'cyl': '钢瓶', 'prod': '产品'}[f] for f in nd['pending'][cid]]
    out = []; pls = sorted({p.lower() for p in (s.get('paper_plates') or []) + DEFAULT_SETTINGS['paper_plates'] if p}, key=len, reverse=True)
    for cid, g in sorted(by.items(), key=lambda kv: kv[1]['sort']):
        note = list(g['notes'])
        if g['hand']: note.append('手工单：' + '、'.join(f'{k}{v:g}' for k, v in g['hand'].items()))
        if any(g['extra'].values()): note.append('另：' + '、'.join(f'{k}{v:g}' for k, v in g['extra'].items() if v))   # 交接表里加的、财务表没有列的产品
        r = {'courier_id': cid, 'name': g['name'], 'label': strip_plate(g['name'], pls), 'vals': g['vals'], 'note': '；'.join(note), 'entries': g['entries']}
        if g.get('pending'):
            r['pending'] = g['pending']; r['next'] = nd['next']
            if nd['gap'].get(cid): r['gap'] = True      # 第二天早上表有了，但没清点到他：接着等，下次清点时几天合起来算
        elif nd['active'] and not raw:
            n = nd['settle'].get(cid)
            if not n:
                # 断档日当天没出车：人不在 settle 候选，但仍可能是合算末日（前几天 settle 落在次日早上，merged_into 指今天）
                for back in range(1, 31):
                    prev = paper.day_add(date, -back)
                    if prev < paper.nextday_from(c): break
                    sn = paper.nextday_state(c, prev).get('settle', {}).get(cid)
                    if sn and paper.day_add(sn, -1) == date:
                        n = sn; break
            if n:
                if n > nd['next']: r['merged_into'] = paper.day_add(n, -1)   # 中间这天：并入那几天的合计
                else:
                    st = paper.period_start(c, date, cid, n)
                    if st < date:   # 几天合起来：最后一天显示合计（含断档日当天没出车、只有次日早上 :L 交回的情况）
                        d0 = st; vs = dict(r['vals']); ns = []
                        while d0 < date:
                            for x in daily_rows(c, d0, raw=True):
                                if x['courier_id'] == cid:
                                    for k, q in x['vals'].items(): vs[k] = num(vs.get(k)) + num(q)
                                    if x['note']: ns.append(x['note'])
                            d0 = paper.day_add(d0, 1)
                        lab = (f"{int(st[8:])}–{int(date[8:])}号合计" if st[:7] == date[:7] else f"{md(st)}–{md(date)}合计")
                        r['vals'] = vs; r['period'] = [st, date]; r['note'] = '；'.join([lab] + ns + ([r['note']] if r['note'] else []))
        if not r.get('pending') and not has_data(r): continue      # 当天没有数的配送员不出现（下载 / 打印 / 汇总）
        out.append(r)
    # 汇总领用人序 = 当天钢瓶交接表各场次行序（与产品页跟钢瓶同源）；没有钢瓶表时回退 couriers.sort
    import paper
    order = paper.cyl_courier_order(c, date)
    if order:
        rank = {cid: i for i, cid in enumerate(order)}
        def _sk(r):
            cid = r['courier_id']
            if cid in rank:
                return (0, rank[cid])
            k = row(c.execute('SELECT sort FROM couriers WHERE id=?', (cid,)).fetchone())
            return (1, (k['sort'] if k else 9999), cid)
        out.sort(key=_sk)
    # 客户自提不计入每日产品出入库情况表（已确认：该表全部是配送）
    return out

def strip_plate(name, pls):
    """领取人信息只写配送员，不写车牌：名称开头是车牌（如 6922丁增、0668 刘洪江2098）就去掉车牌；只有车牌的照原样"""
    n = (name or '').strip()
    for p in pls:
        if n.lower().startswith(p) and n[len(p):].strip(): return n[len(p):].strip()
    return n

def has_data(m):
    """有没有值得进汇总的数。不能「只有早上车上剩余 v0」就算有数——清点日早上只交回、当天没出车的人否则会在当天汇总冒出一堆用量/红字。"""
    v = m.get('vals') or {}
    if m.get('note') or m.get('pending') or m.get('merged_into') or m.get('period'): return True
    if any(num(v.get(k)) for k, _ in CYL): return True
    for o in OTHER:
        if num(v.get('t_' + o[0])) or num(v.get('i_' + o[0])) or num(v.get('v1_' + o[0])): return True
        if num(v.get('si_' + o[0])) or num(v.get('st_' + o[0])): return True
    return False

def short_name(c, pid, pname):
    m = daily_map(c)
    for o in OTHER:
        if m.get(o[0]) == pid: return o[1]
    for k, n in (('c40', '40L钢瓶'), ('c10', '10L钢瓶')):
        if m.get(k) == pid: return n
    return pname.get(pid, '?')

def calc_row(v):
    g = lambda k: num(v.get(k))
    r = {'J40': g('e40') - g('r40'), 'J10': g('e10') - g('r10'),
         'L40': g('o40') + g('r40') - g('e40') - g('f40'), 'L10': g('o10') + g('r10') - g('e10') - g('f10')}
    r['R40'] = r['J40'] + r['L40']; r['R10'] = r['J10'] + r['L10']
    for o in OTHER: r['net_' + o[0]] = g('t_' + o[0]) + g('v0_' + o[0]) - g('i_' + o[0]) - g('v1_' + o[0])   # v0/v1 = 早上 / 次日早上车上剩余（次日清点）
    return r

def outside_total(c):
    """系统累计新送和回收 → 外面共有多少瓶（起始数 + Σ(新送 − 回收)）。未设起始数时只给累计变化"""
    s = settings(c); base = s.get('outside_base') or {}
    tot = {'40': 0, '10': 0}; new = {'40': 0, '10': 0}; rec = {'40': 0, '10': 0}
    for e in c.execute('SELECT vals FROM daily_entries WHERE deleted_at IS NULL'):
        v = json.loads(e[0] or '{}'); r = calc_row(v)
        for z in ('40', '10'):
            new[z] += r['L' + z]; rec[z] += num(v.get('r' + z)); tot[z] += r['L' + z] - num(v.get('r' + z))
            ls = num(v.get('sr' + z)) - num(v.get('se' + z)) - num(v.get('sf' + z))   # 只进库存的那部分（规则第一天早上钢瓶表左边）：外面的瓶数照样跟着变
            new[z] += ls; rec[z] += num(v.get('sr' + z)); tot[z] += ls - num(v.get('sr' + z))
    res = {}
    for z in ('40', '10'):
        b = base.get(z)
        res[z] = {'new': new[z], 'rec': rec[z], 'delta': tot[z], 'base': b, 'total': None if b in (None, '') else num(b) + tot[z]}
    return res

def next_slip_no(c, date):
    """借用单自动编号：JY + 日期 + 两位序号，如 JY20261018-01"""
    p = 'JY' + date.replace('-', '') + '-'
    n = c.execute("SELECT COUNT(*) FROM loans WHERE slip_no LIKE ?", (p + '%',)).fetchone()[0]
    return p + '%02d' % (n + 1)
