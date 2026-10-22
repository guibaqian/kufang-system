# -*- coding: utf-8 -*-
"""报表（照搬 v82 的 5 张表）：换算表 / 入出库记录 / 库存及到货总数 / 液氧表 / 4号院
   - 表格数据存 report_tabs（data = {rows, merges}），version 乐观锁，留痕记改了哪些格
   - 下载：以原工作簿为模板只保留这一张表（xlgrid），格式与原表一致
   - 「库存及到货总数」由到货记录生成（到货页登记/改/删/标记U8），报表里只读"""
import os, re, json, copy, datetime, hashlib, math
import db, xlgrid
from db import row, rows, now, today, audit, meta_get
from web import route, ApiError, readb

TPL_DIR = os.path.join(db.BASE, 'templates')
BOOKS = {'A': '报表A_液态原料换算表.xlsx', 'B': '报表B_库存及到货总数.xlsx'}
TABS = {  # 每张报表只有一个名称：short 与 title 相同
    'conv':   dict(title='液态原料换算表', short='液态原料换算表', book='A', sheet='液态原料换算表', start=4, head=3, mode='date'),
    'ledger': dict(title='液态氧原料入出库记录', short='液态氧原料入出库记录', book='A', sheet='液态氧原料入出库记录', start=3, head=2, mode='content'),
    'stock':  dict(title='库存及到货总数', short='库存及到货总数', book='B', sheet='库存及到货总数', start=3, head=2, mode='all'),
    'lox':    dict(title='液氧表', short='液氧表', book='B', sheet='液氧表', start=13, head=12, mode='all', early=[2, 11]),
    'yard4':  dict(title='4号院', short='4号院', book='B', sheet='4号院', start=2, head=1, mode='all'),
}
ORDER = ['conv', 'ledger', 'stock', 'lox', 'yard4']
RSCHEMA = """
CREATE TABLE IF NOT EXISTS report_trash(id INTEGER PRIMARY KEY, key TEXT NOT NULL, r INTEGER, date TEXT DEFAULT '', label TEXT DEFAULT '', row TEXT NOT NULL,
  deleted_at REAL, deleted_by TEXT DEFAULT '', restored_at REAL, restored_by TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS report_prefs(key TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL, updated_by TEXT DEFAULT '');
"""
if 'report_trash' not in db.SCHEMA: db.SCHEMA += RSCHEMA   # 报表行回收站 / 报表显示设置
def ensure_schema(c): c.executescript(RSCHEMA)
EID = {k: i + 1 for i, k in enumerate(ORDER)}

def tpl_dir():
    d = os.path.join(db.DATA, 'report_tpl'); os.makedirs(d, exist_ok=True); return d
def tpl_bytes(tpl):
    """tpl = 'A'/'B'（内置）或导入文件名"""
    if tpl in BOOKS: return readb(os.path.join(TPL_DIR, BOOKS[tpl]))
    p = os.path.join(tpl_dir(), os.path.basename(tpl))
    if os.path.isfile(p): return readb(p)
    raise ApiError('报表模板文件丢失：%s' % tpl)

def seed(c, keys=None, person='系统'):
    by = {}
    for k in keys or ORDER: by.setdefault(TABS[k]['book'], []).append(k)
    for b, ks in by.items():
        data = tpl_bytes(b); pkg = xlgrid.open_pkg(data)
        for k in ks:
            t = xlgrid.read_sheet(data, TABS[k]['sheet'], pkg)
            put(c, k, {'rows': t['rows'], 'merges': t['merges']}, b, person, '内置原表')

def put(c, k, data, tpl, person, summary):
    old = row(c.execute('SELECT version FROM report_tabs WHERE key=?', (k,)).fetchone())
    v = (old['version'] or 0) + 1 if old else 1
    c.execute('INSERT OR REPLACE INTO report_tabs(key,data,updated_at,updated_by,version,tpl) VALUES(?,?,?,?,?,?)',
              (k, json.dumps(data, ensure_ascii=False, separators=(',', ':')), now(), person, v, tpl))
    audit(c, person, '修改' if old else '新增', 'report', EID[k], '%s：%s' % (TABS[k]['title'], summary))
    return v

def get_raw(c, k):
    r = row(c.execute('SELECT * FROM report_tabs WHERE key=?', (k,)).fetchone())
    if not r:
        seed(c, [k]); r = row(c.execute('SELECT * FROM report_tabs WHERE key=?', (k,)).fetchone())
    d = json.loads(r['data']); d['version'] = r['version']; d['tpl'] = r['tpl'] or TABS[k]['book']
    d['updated_at'] = r['updated_at']; d['updated_by'] = r['updated_by']
    return d

def get_tab(c, k):
    d = get_raw(c, k)
    if k == 'stock': d = stock_overlay(c, d)
    return d

# ---------------- 库存及到货总数 ← 到货记录 ----------------
def _v(tab, col, r):
    rs = tab['rows']; x = rs[r - 1] if 0 < r <= len(rs) else None; c = x and x['c'].get(col)
    return c.get('v') if c else None
def _set(tab, col, r, v, style_from=None):
    rs = tab['rows']
    while len(rs) < r: rs.append(None)
    if not rs[r - 1]: rs[r - 1] = {'c': {}}
    cell = rs[r - 1]['c'].setdefault(col, {})
    cell.pop('f', None); cell.pop('v', None)
    if v is None or v == '': return
    cell['v'] = v
def _date_s(iso): return '%d.%d.%d' % (int(iso[:4]), int(iso[5:7]), int(iso[8:10])) if iso and len(iso) >= 10 else ''
def _numish(s):
    s = str(s or '').strip()
    return int(s) if re.fullmatch(r'[1-9]\d{0,15}', s) else s
def _qty(q):
    if q is None: return ''
    return int(q) if float(q).is_integer() else q
def _expect(tab, r):
    """按导入时的规则，从原表这一行推出到货字段（用来判断用户在系统里改过哪些）"""
    g = lambda col: _v(tab, col, r)
    st = str(g('H') or ''); allt = (st + str(g('G') or '')).upper()
    u8 = '已入U8' if ('已' in st and 'U8' in st.upper()) or g('I') or g('J') else '不入U8' if re.search(r'(不用|无需|不需|不)入U8', allt) else '待入U8'
    rem = str(g('G') or '')
    if st and st not in ('已U8入库',): rem = (rem + ' ' + st).strip()
    q = g('E'); q = q if isinstance(q, (int, float)) else 0
    return {'name': str(g('B') or '').strip(), 'spec': str(g('C') or '').strip(), 'unit': str(g('D') or ''), 'qty': float(q), 'dest': str(g('F') or ''),
            'remark': rem, 'u8_status': u8, 'inv_code': str(g('I') or ''), 'receipt_no': str(g('J') or ''), 'taken_note': str(g('K') or '')}
def _h_for(a, old_h):
    if a['u8_status'] == '已入U8': return old_h if old_h and 'U8' in str(old_h).upper() and '不' not in str(old_h) else 'U8到货入库'
    if a['u8_status'] == '不入U8': return '不用入U8'
    return '其他入库' if a['kind'] == '其他入库' else ''

def stock_overlay(c, d):
    tab = {'rows': copy.deepcopy(d['rows']), 'merges': list(d['merges'])}
    out = dict(d, rows=tab['rows'], merges=tab['merges'], row_arrival={})
    ars = rows(c.execute('SELECT * FROM arrivals ORDER BY date, id'))
    pc = {r[0]: r[1] for r in c.execute("SELECT entity_id, COUNT(*) FROM photos WHERE entity='arrival' AND deleted_at IS NULL GROUP BY entity_id")}
    nrows = len(tab['rows'])
    for a in ars:
        r = a['sheet_row'] if (a['legacy_id'] or '').startswith('sheet:') else None
        if not r or r > nrows: continue
        if a['deleted_at']:
            for col in 'BCDEFGHIJK': _set(tab, col, r, None)
            continue
        out['row_arrival'][r] = {'id': a['id'], 'u8': a['u8_status'], 'n': pc.get(a['id'], 0)}
        if not a['updated_at']: continue
        ex = _expect(tab, r)
        if a['name'] != ex['name']: _set(tab, 'B', r, a['name'])
        if (a['spec'] or '') != ex['spec']: _set(tab, 'C', r, a['spec'])
        if (a['unit'] or '') != ex['unit']: _set(tab, 'D', r, a['unit'])
        if float(a['qty'] or 0) != ex['qty']: _set(tab, 'E', r, _qty(a['qty']))
        if (a['dest'] or '') != ex['dest']: _set(tab, 'F', r, a['dest'])
        if (a['remark'] or '') != ex['remark']: _set(tab, 'G', r, a['remark'])
        if a['u8_status'] != ex['u8_status']: _set(tab, 'H', r, _h_for(a, _v(tab, 'H', r)))
        if (a['inv_code'] or '') != ex['inv_code']: _set(tab, 'I', r, _numish(a['inv_code']))
        if (a['receipt_no'] or '') != ex['receipt_no']: _set(tab, 'J', r, _numish(a['receipt_no']))
        if (a['taken_note'] or '') != ex['taken_note']: _set(tab, 'K', r, a['taken_note'])
    # 系统里新登记的到货：接在表后面（迁移来的 v82 旧入库单不在这张表里，不追加）
    last = 0
    for i in range(len(tab['rows']) - 1, 1, -1):
        x = tab['rows'][i]
        if x and any(cc.get('v') not in (None, '') for cc in x['c'].values()): last = i + 1; break
    src = last
    for a in ars:
        if a['deleted_at'] or a['legacy_id'] or a['sheet_row']: continue
        r = last + 1; last = r
        base = tab['rows'][src - 1] if src else None
        while len(tab['rows']) < r: tab['rows'].append(None)
        tab['rows'][r - 1] = {'c': {k: ({'s': v['s']} if v.get('s') else {}) for k, v in (base['c'] if base else {}).items() if k in 'ABCDEFGHIJK'}}
        if base and base.get('ra'): tab['rows'][r - 1]['ra'] = base['ra']
        _set(tab, 'A', r, _date_s(a['date'])); _set(tab, 'B', r, a['name']); _set(tab, 'C', r, a['spec']); _set(tab, 'D', r, a['unit'])
        _set(tab, 'E', r, _qty(a['qty'])); _set(tab, 'F', r, a['dest'] or a['supplier']); _set(tab, 'G', r, a['remark'])
        _set(tab, 'H', r, _h_for(a, '')); _set(tab, 'I', r, _numish(a['inv_code'])); _set(tab, 'J', r, _numish(a['receipt_no'])); _set(tab, 'K', r, a['taken_note'])
        out['row_arrival'][r] = {'id': a['id'], 'u8': a['u8_status'], 'n': pc.get(a['id'], 0)}
    return out

# ---------------- 主数据区（与 v82 o2Ranges 一致） ----------------
def has_val(tab, r, cols=None):
    rs = tab['rows']; x = rs[r - 1] if 0 < r <= len(rs) else None
    if not x: return False
    return any((cols is None or k in cols) and v and ((v.get('v') is not None and str(v.get('v')).strip() != '') or v.get('f')) for k, v in x['c'].items())
_DATE = re.compile(r'^\s*(20\d\d)[.\-/年](\d{1,2})[.\-/月](\d{1,2})日?\s*$')
def content(k, tab, r):
    if k == 'conv':
        return has_val(tab, r) and (bool(_DATE.match(str(_v(tab, 'A', r) or ''))) or has_val(tab, r, set('BDHIJKLMNOPQR')))
    if k == 'ledger': return has_val(tab, r, set('BCDEFGHIJKLMN'))
    return has_val(tab, r)
def ranges(k, tab):
    cfg = TABS[k]; n = len(tab['rows']); last = cfg['start'] - 1
    for r in range(n, 0, -1):
        if has_val(tab, r): last = r; break
    if cfg['mode'] == 'all': return {'start': cfg['start'], 'main_end': max(last, cfg['start'] - 1), 'tail': None, 'last': last}
    main_end = cfg['start'] - 1; gap = 0
    for r in range(cfg['start'], n + 1):
        if content(k, tab, r): main_end = r; gap = 0
        else:
            gap += 1
            if gap >= 3 and main_end >= cfg['start']: break
    tail = None
    for r in range(main_end + 1, n + 1):
        if has_val(tab, r) and (content(k, tab, r) or r > main_end + 2): tail = r; break
    return {'start': cfg['start'], 'main_end': main_end, 'tail': tail, 'last': last}

# ---------------- 液氧表 / 4号院：按月自动「合计」行 ----------------
# 规则（与前端 rAutoSums 完全一致）：从 AUTO_SUM_FROM 这个月起，某月表里没有手写「合计」行时，在这个月最后一行下面显示一行自动合计。
# 合计哪些列：照表里最近一个手写合计行有数的列（没有就用默认）；格子里是「彤华28.63」这种「文字+数字」也算数字；
# 任何一格写了「不算」的行不计入（如「不算，在8.31日28.12T已记账」）。自动合计不存进表里：屏幕、打印、下载 Excel 时现算。
AUTO_SUM_FROM = '2026-10'
AUTO_SUM_COLS = {'lox': ['C', 'D', 'F'], 'yard4': ['D', 'E', 'F']}
_LEAD_NUM = re.compile(r'^[^\d.+\-=*/]*?(-?\d+(?:\.\d+)?)\s*$')
_SUM_A = re.compile(r'^合\s*计$')
def _numof(v):
    if isinstance(v, bool) or v is None: return None
    if isinstance(v, (int, float)): return float(v)
    m = _LEAD_NUM.match(str(v).strip())
    return float(m.group(1)) if m else None
def auto_sums(k, tab):
    if k not in AUTO_SUM_COLS: return []
    ev = xlgrid.Evaluator(tab); rg = ranges(k, tab); start, end = TABS[k]['start'], rg['main_end']
    val = lambda col, r: (ev.cell(col, r) if ((tab['rows'][r - 1] or {}).get('c') or {}).get(col, {}).get('f') else _v(tab, col, r))
    cur = None; manual = set(); recs = {}; cols = None
    for r in range(start, end + 1):
        x = tab['rows'][r - 1] if r <= len(tab['rows']) else None
        if not x or not any(cc.get('v') not in (None, '') or cc.get('f') for cc in x['c'].values()): continue
        a = str(_v(tab, 'A', r) or '').strip()
        if _SUM_A.match(a):
            if cur: manual.add(cur)
            cs = [cc for cc in sorted(x['c']) if cc != 'A' and (x['c'][cc].get('v') not in (None, '') or x['c'][cc].get('f'))]
            if cs: cols = cs
            continue
        d = norm_date(a)
        if d: cur = d[:7]
        if not cur: continue
        g = recs.setdefault(cur, {'after': r, 'rows': [], 'skipped': []}); g['after'] = r
        (g['skipped'] if any('不算' in str(cc.get('v') or '') for cc in x['c'].values()) else g['rows']).append(r)
    cols = cols or AUTO_SUM_COLS[k]; out = []
    for m, g in recs.items():
        if m < AUTO_SUM_FROM or m in manual: continue
        vals = {}
        for col in cols:
            ns = [n for n in (_numof(val(col, r)) for r in g['rows']) if n is not None]
            if ns or not g['rows']: vals[col] = _r2(sum(ns))
        out.append({'after': g['after'], 'month': m, 'vals': vals, 'n': len(g['rows']), 'skipped': g['skipped']})
    return sorted(out, key=lambda s: s['after'])

def with_auto_sums(k, d):
    """下载用：把自动合计行插进表（样式照最近一个手写合计行）"""
    ss = auto_sums(k, d)
    if not ss: return d
    d = dict(d, rows=copy.deepcopy(d['rows']), merges=list(d['merges']))
    style = None
    for r in range(len(d['rows']), 0, -1):
        if _SUM_A.match(str(_v(d, 'A', r) or '').strip()): style = d['rows'][r - 1]; break
    for s_ in reversed(ss):
        row_ = {'c': {cc: ({'s': v['s']} if v.get('s') else {}) for cc, v in ((style or {}).get('c') or {}).items()}}
        if style and style.get('ra'): row_['ra'] = style['ra']
        row_['c'].setdefault('A', {})['v'] = '合计'
        for cc, v in s_['vals'].items(): row_['c'].setdefault(cc, {})['v'] = v
        xlgrid.insert_row(d, s_['after'] + 1, row_)
    return d

def strip_auto_sums(k, tab):
    """导入我们下载的 Excel 时：去掉当初自动加上的合计行（值和现算的一样、位置也对），免得它变成「手写合计」不再自动更新"""
    if k not in AUTO_SUM_COLS: return 0
    n = 0
    for r in range(len(tab['rows']), TABS[k]['start'] - 1, -1):
        if not _SUM_A.match(str(_v(tab, 'A', r) or '').strip()): continue
        x = tab['rows'][r - 1]; t2 = dict(tab, rows=copy.deepcopy(tab['rows']), merges=list(tab['merges'])); xlgrid.delete_row(t2, r)
        hit = [s for s in auto_sums(k, t2) if s['after'] == r - 1]
        mine = {cc: _numof(v.get('v')) for cc, v in x['c'].items() if cc != 'A' and v.get('v') not in (None, '')}
        if hit and not any(v.get('f') for v in x['c'].values()) and mine and all(cc in hit[0]['vals'] and v is not None and abs(v - hit[0]['vals'][cc]) < 0.005 for cc, v in mine.items()):
            tab['rows'], tab['merges'] = t2['rows'], t2['merges']; n += 1
    return n


def fit_one_page(xlsx_bytes, landscape=True):
    """下载的 Excel：横向、页边距收紧、整表缩到一页宽×一页高（打印预览直接一张纸）。"""
    import zipfile, io
    zin = zipfile.ZipFile(io.BytesIO(xlsx_bytes)); buf = io.BytesIO(); zout = zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED)
    orient = 'landscape' if landscape else 'portrait'
    setup = '<pageSetup paperSize="9" orientation="%s" fitToWidth="1" fitToHeight="1"/>' % orient
    margins = '<pageMargins left="0.25" right="0.25" top="0.35" bottom="0.35" header="0.15" footer="0.15"/>'
    for name in zin.namelist():
        data = zin.read(name)
        if name.startswith('xl/worksheets/') and name.endswith('.xml'):
            x = data.decode('utf-8')
            if 'fitToPage' not in x:
                if re.search(r'<sheetPr\b[^>]*/>', x):
                    x = re.sub(r'(<sheetPr\b[^>]*)/>', r'\1><pageSetUpPr fitToPage="1"/></sheetPr>', x, count=1)
                elif re.search(r'<sheetPr\b', x):
                    x = re.sub(r'(<sheetPr\b[^>]*>)', r'\1<pageSetUpPr fitToPage="1"/>', x, count=1)
                else:
                    x = re.sub(r'(<worksheet[^>]*>)', r'\1<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>', x, count=1)
            if re.search(r'<pageSetup\b', x):
                x = re.sub(r'<pageSetup\b[^/]*/>', setup, x)
            else:
                x = x.replace('</worksheet>', setup + '</worksheet>')
            if re.search(r'<pageMargins\b', x):
                x = re.sub(r'<pageMargins\b[^/]*/>', margins, x)
            else:
                x = x.replace('</worksheet>', margins + '</worksheet>')
            # 列宽略收一点，方便缩到一页仍能看清
            def _sw(m):
                w = float(m.group(1)); return 'width="%.3f"' % (max(4.0, w * 0.88))
            x = re.sub(r'width="([\d.]+)"', _sw, x)
            data = x.encode('utf-8')
        zout.writestr(name, data)
    zout.close(); return buf.getvalue()

def build_xlsx(c, k, sums=True):
    d = get_tab(c, k); cfg = TABS[k]
    if sums and k in AUTO_SUM_COLS: d = with_auto_sums(k, d)   # sums=0：只要表里存的原样（核对 / 再导入用）
    rg = ranges(k, d)
    latest = rg['last'] if cfg['mode'] == 'all' else rg['main_end']
    raw = xlgrid.build_workbook(tpl_bytes(d['tpl']), cfg['sheet'], d, top_row=max(cfg['start'], latest - 18), active_row=latest)
    return fit_one_page(raw) if k == 'stock' else raw

def sheet_widths(c, k, tpl):
    """列宽（打印用，与模板一致），单位：Excel 字符宽"""
    data = tpl_bytes(tpl); pkg = xlgrid.open_pkg(data)
    sh = next((s for s in pkg['sheets'] if s['name'] == TABS[k]['sheet']), None)
    x = pkg['get'](sh['path']) if sh else ''
    w = {}
    for m in re.finditer(r'<col\b[^>]*>', x or ''):
        t = m.group(0); mn = re.search(r'\bmin="(\d+)"', t); mx = re.search(r'\bmax="(\d+)"', t); wd = re.search(r'\bwidth="([\d.]+)"', t)
        if mn and wd:
            for i in range(int(mn.group(1)), min(int(mx.group(1)), int(mn.group(1)) + 60) + 1): w[xlgrid.n2col(i)] = float(wd.group(1))
    dw = re.search(r'\bdefaultColWidth="([\d.]+)"', x or '')
    return {'cols': w, 'default': float(dw.group(1)) if dw else 9.0}

def cell_diff(old, new):
    """改了哪些格：返回 (个数, 前几条说明)"""
    def flat(t):
        o = {}
        for i, x in enumerate(t.get('rows') or []):
            if not x: continue
            for col, cc in x['c'].items():
                v = ('=' + cc['f']) if cc.get('f') else cc.get('v')
                if v not in (None, ''): o['%s%d' % (col, i + 1)] = v
        return o
    a, b = flat(old), flat(new); keys = sorted(set(a) | set(b), key=lambda s: (int(re.sub(r'\D', '', s)), s))
    ch = [k for k in keys if a.get(k) != b.get(k)]
    return len(ch), '；'.join('%s: %s→%s' % (k, a.get(k, ''), b.get(k, '')) for k in ch[:12])

# ---------------- 换算表 → 入出库记录：联动（改了换算表，入出库记录里对应那一行的出库量自动跟着变） ----------------
def norm_date(v):
    m = _DATE.match(str(v or ''))
    return '%s-%02d-%02d' % (m.group(1), int(m.group(2)), int(m.group(3))) if m else ''
def _r2(v): return math.floor(v * 100 + 0.5 + 1e-9) / 100
def conv_index(conv):
    """换算表主数据区：日期 → (行号, 总计V)"""
    ev = xlgrid.Evaluator(conv); rg = ranges('conv', conv); out = {}
    for r in range(rg['start'], rg['main_end'] + 1):
        d = norm_date(_v(conv, 'A', r))
        if d: out[d] = (r, ev.cell('V', r))
    return out
_OUT_PART = re.compile(r'^\s*出?(.*?)\s*(\d+(?:\.\d+)?)\s*$')
def lox_index(lox):
    """液氧表里接了入出库记录的车（行上有 lx 编号）：编号 → (日期, {卸点: 吨})；续行（没日期的）算同一车"""
    out = {}; rs = lox['rows']; end = ranges('lox', lox)['main_end']
    for r in range(TABS['lox']['start'], end + 1):
        x = rs[r - 1] if r <= len(rs) else None
        if not x or not x.get('lx'): continue
        places = {}; rr = r
        while rr <= end:
            if rr > r and (_v(lox, 'A', rr) not in (None, '') or not any(_v(lox, cc, rr) not in (None, '') for cc in 'BCDEF')): break
            for p in str(_v(lox, 'E', rr) or '').split('+'):
                m = _OUT_PART.match(p)
                if m and m.group(1).strip(): places[m.group(1).strip()] = places.get(m.group(1).strip(), 0) + float(m.group(2))
            rr += 1
        out[x['lx']] = (norm_date(_v(lox, 'A', r)), places)
    return out

_QC_QTY = re.compile(r'(\d+(?:\.\d+)?)')
# 保存时禁止把已有质检/左侧入库格子抹成空（防旧页面整表覆盖）；只保留，不编造
_PRESERVE_COLS = {'lox': tuple('GHIJ'), 'ledger': tuple('BCDEFGH')}

def _cell_nonempty(cc):
    if not cc: return False
    if cc.get('f') not in (None, ''): return True
    v = cc.get('v')
    return v not in (None, '')

def _row_fp(row, tab_key):
    """行身份：删行/插行后下标会错位，preserve 必须用身份对齐，不能只按行号。
    指纹只用「不在保住列里」的字段（出库侧 / link / lx），避免误清入库格后指纹变了保不住。"""
    if not row: return ''
    ln = row.get('link') or {}
    k = ln.get('k')
    if k == 'lox_in' and ln.get('id'): return 'lox_in:%s' % ln['id']
    if k == 'lox' and ln.get('id'): return 'lox:%s:%s' % (ln['id'], ln.get('place') or '')
    if k == 'conv' and ln.get('date'): return 'conv:%s' % ln['date']
    if k == 'slip' and ln.get('ids'): return 'slip:%s' % ','.join(str(i) for i in ln['ids'])
    c = row.get('c') or {}
    def vv(col):
        cell = c.get(col) or {}
        v = cell.get('v')
        if v not in (None, ''): return v
        return cell.get('f')
    if tab_key == 'ledger':
        i, j, kk = vv('I'), vv('J'), vv('K')
        if i not in (None, ''): return 'out:%s|%s|%s' % (i, j, kk)
        a = vv('A')
        if a not in (None, ''): return 'A:%s' % a
        return ''
    if tab_key == 'lox':
        if row.get('lx'): return 'lx:%s' % row['lx']
        return 'loxrow:%s|%s' % (vv('A'), vv('B'))
    return ''

def preserve_filled(old, new, cols, tab_key=None):
    """若旧表有值、新表同格被清空 → 写回旧值。返回被保住的格子说明列表。
    仅当同一行身份（link/出库日期等）对上时才保住，避免删行后把上一行的入库格粘到下一行。"""
    kept = []
    old_rows = old.get('rows') or []; new_rows = new.get('rows') or []
    for i, ox in enumerate(old_rows):
        if not ox: continue
        while len(new_rows) <= i: new_rows.append(None)
        nx = new_rows[i]
        if not nx: nx = {'c': {}}; new_rows[i] = nx
        if tab_key:
            ofp, nfp = _row_fp(ox, tab_key), _row_fp(nx, tab_key)
            # 两边都有身份且不一致 → 行已错位（删/插），绝不按行号粘贴
            if ofp and nfp and ofp != nfp: continue
            # 旧行有身份、新行没有（或反过来）也视为错位
            if bool(ofp) != bool(nfp): continue
        oc = ox.get('c') or {}; nc = nx.setdefault('c', {})
        for col in cols:
            ocell = oc.get(col)
            if not _cell_nonempty(ocell): continue
            ncell = nc.get(col)
            if _cell_nonempty(ncell): continue
            nc[col] = dict(ocell)
            kept.append('%s%d' % (col, i + 1))
    new['rows'] = new_rows
    return kept

def parse_lox_qc(lox, r):
    """液氧表一行质检U8：{qty, batch, prod, inbound}；缺批次或入库日期则不算齐"""
    g = str(_v(lox, 'G', r) or '').strip()
    h = _v(lox, 'H', r); j = _v(lox, 'J', r); i = _v(lox, 'I', r)
    if not g or h in (None, '') or not norm_date(j): return None
    m = _QC_QTY.search(g.replace(',', ''))
    if not m: return None
    qty = _r2(float(m.group(1)))
    batch = str(int(h)) if isinstance(h, float) and h == int(h) else str(h).strip()
    return {'qty': qty, 'batch': batch, 'prod': i, 'inbound': norm_date(j), 'inbound_s': _date_s(norm_date(j)),
            'plate': _v(lox, 'B', r), 'date': norm_date(_v(lox, 'A', r))}

def lox_qc_index(lox):
    """lx → 质检入库信息；无 lx 的不进索引（联动前会先编号）"""
    out = {}; end = ranges('lox', lox)['main_end']
    for r in range(TABS['lox']['start'], end + 1):
        x = lox['rows'][r - 1] if r <= len(lox['rows']) else None
        if not x or not x.get('lx'): continue
        qc = parse_lox_qc(lox, r)
        if qc: out[x['lx']] = dict(qc, r=r)
    return out

def sync_links(c, person, summary_prefix='联动表改动，自动更新'):
    """换算表/液氧表出库联动 + 液氧表质检U8→左侧入库联动。批次剩余（L）公式跟出库走。返回改动说明。所有写入走 put→audit。"""
    conv = get_raw(c, 'conv'); led = get_raw(c, 'ledger'); idx = conv_index(conv); ch = []; lidx = None; qidx = None
    for r, x in enumerate(led['rows'], 1):
        ln = x and x.get('link')
        if ln and ln.get('k') == 'lox_in':     # 质检U8 → 左侧入库（只更新有值的字段，从不抹空）
            if qidx is None: qidx = lox_qc_index(get_raw(c, 'lox'))
            hit = qidx.get(ln.get('id'))
            if not hit:
                if not ln.get('missing'): ln['missing'] = 1; ch.append('第%d行：液氧表里已找不到质检入库 %s' % (r, ln.get('batch') or ln.get('id')))
                continue
            if ln.pop('missing', None): ch.append('第%d行：液氧表质检入库 %s 又对上了' % (r, hit['batch']))
            mapping = [('B', hit['batch']), ('E', hit['inbound_s']), ('F', hit['qty'])]
            if hit.get('prod') not in (None, ''): mapping.append(('C', hit['prod']))
            for col, nv in mapping:
                if nv in (None, ''): continue          # 加性：来源空则不动目标
                old = _v(led, col, r)
                if old != nv:
                    _set(led, col, r, nv); ch.append('第%d行入库%s %s→%s' % (r, col, old, nv))
            ln['batch'] = hit['batch']; ln['date'] = hit['inbound']
            continue
        if ln and ln.get('k') == 'lox':            # 液氧表这车卸到别处的吨数 → 出库量
            if lidx is None: lidx = lox_index(get_raw(c, 'lox'))
            hit = lidx.get(ln.get('id')); q = hit and hit[1].get(ln.get('place'))
            if q is None:
                if not ln.get('missing'): ln['missing'] = 1; ch.append('第%d行：液氧表里已找不到 %s 卸%s' % (r, ln.get('date'), ln.get('place')))
                continue
            if ln.pop('missing', None): ch.append('第%d行：液氧表 %s 卸%s 又对上了' % (r, ln.get('date'), ln.get('place')))
            kc = (x.get('c') or {}).get('K') or {}
            if kc.get('f'): continue
            old = _v(led, 'K', r)
            if isinstance(old, str) and '+' in old: continue  # 一天两批「剩余+新取」手写样式，不自动改
            q = _r2(q)
            if not isinstance(old, (int, float)) or isinstance(old, bool) or abs(old - q) > 1e-9:
                _set(led, 'K', r, q); ch.append('第%d行 %s 出%s 出库量 %s→%s' % (r, ln.get('date'), ln.get('place'), old, q))
            if hit[0] and hit[0] != ln.get('date'):
                ln['date'] = hit[0]; _set(led, 'I', r, _date_s(hit[0])); ch.append('第%d行 出库时间→%s' % (r, _date_s(hit[0])))
            continue
        if not ln or ln.get('k') != 'conv': continue
        hit = idx.get(ln.get('date'))
        if not hit:
            if not ln.get('missing'): ln['missing'] = 1; ch.append('第%d行：换算表里已没有 %s' % (r, ln.get('date')))
            continue
        ln.pop('missing', None)
        v = hit[1]
        if not isinstance(v, (int, float)) or isinstance(v, bool): continue
        kc = (x.get('c') or {}).get('K') or {}
        if kc.get('f'): continue                     # 出库量写成了算式：算手填，不自动改
        old = _v(led, 'K', r)
        if isinstance(old, str) and '+' in old: continue  # 一天两批「剩余+新取」，不自动改成纯数字
        q = _r2(v)
        if not isinstance(old, (int, float)) or abs(old - q) > 1e-9:
            _set(led, 'K', r, q); ch.append('第%d行 %s 出库量 %s→%s' % (r, ln.get('date'), old, q))
    if ch:
        put(c, 'ledger', {'rows': led['rows'], 'merges': led['merges']}, led['tpl'], person, '%s：%s' % (summary_prefix, '；'.join(ch[:12])))
    return ch
def migrate_links(c):
    """升级时做一次：把以前从换算表写进入出库记录的「出本库」行接上联动，并按换算表现在的数重算（如 10.18 改成 10L=41 的那行）"""
    from db import meta_set
    if meta_get(c, 'report_links_v1'): return []
    ensure_schema(c)
    if not c.execute("SELECT 1 FROM report_tabs WHERE key IN ('conv','ledger')").fetchone(): meta_set(c, 'report_links_v1', True); return []
    conv = get_raw(c, 'conv'); led = get_raw(c, 'ledger'); idx = conv_index(conv); rg = ranges('ledger', led)
    # 只接「用本系统 →记录 按钮从换算表写进去」的那几天（留痕里有记录）；以前手填的（可能只是当天的一部分、或写成算式）一律不动
    pushed = set()
    for (sm,) in c.execute("SELECT summary FROM audit WHERE entity='report' AND summary LIKE '%总计写入入出库记录%'"):
        m = re.search(r'换算表 (\S+) 总计写入入出库记录', sm or '')
        if m and norm_date(m.group(1)): pushed.add(norm_date(m.group(1)))
    by = {}
    for r in range(rg['start'], rg['main_end'] + 1):
        x = led['rows'][r - 1] if r <= len(led['rows']) else None
        if not x or x.get('link') or '本库' not in str(_v(led, 'J', r) or ''): continue
        kc = x['c'].get('K') or {}
        if kc.get('f') or not isinstance(kc.get('v'), (int, float)) or isinstance(kc.get('v'), bool): continue
        d = norm_date(_v(led, 'I', r))
        if d in idx and d in pushed: by.setdefault(d, []).append(r)
    n = 0
    for d, rs in by.items():
        if len(rs) == 1: led['rows'][rs[0] - 1]['link'] = {'k': 'conv', 'date': d}; n += 1
    if n: put(c, 'ledger', {'rows': led['rows'], 'merges': led['merges']}, led['tpl'], '系统', '升级：%d 行出本库记录接上换算表联动' % n)
    ch = sync_links(c, '系统', '升级：按换算表重算') if n else []
    meta_set(c, 'report_links_v1', True)
    return ch

# ---------------- 报表行的回收站 ----------------
def _row_label(k, x, r):
    tab = {'rows': [None] * (r - 1) + [x], 'merges': []}
    if k == 'conv': return '换算表 %s' % (_v(tab, 'A', r) or '第%d行' % r)
    if k == 'ledger': return '入出库记录 %s %s %s' % (_v(tab, 'I', r) or '', _v(tab, 'J', r) or '', _v(tab, 'K', r) or '')
    return '%s 第%d行 %s' % (TABS[k]['short'], r, ' '.join(str(_v(tab, cc, r) or '') for cc in 'ABC').strip())
def trash_rows(c, items, person):
    for it in items or []:
        k = it.get('key'); x = it.get('row'); r = int(it.get('r') or 0)
        if k not in TABS or k == 'stock' or not isinstance(x, dict) or not r: continue
        d = norm_date(_v({'rows': [None] * (r - 1) + [x]}, 'A' if k == 'conv' else 'I', r)) if k in ('conv', 'ledger') else ''
        c.execute('INSERT INTO report_trash(key,r,date,label,row,deleted_at,deleted_by) VALUES(?,?,?,?,?,?,?)',
                  (k, r, d, _row_label(k, x, r), json.dumps(x, ensure_ascii=False), now(), person))
def restore_row(c, tid, person):
    t = row(c.execute('SELECT * FROM report_trash WHERE id=?', (tid,)).fetchone())
    if not t or t['restored_at']: raise ApiError('回收站里没有这一行（可能已经恢复过）')
    k = t['key']; tab = get_raw(c, k); x = json.loads(t['row']); rg = ranges(k, tab)
    if k == 'conv':
        idx = conv_index(tab)
        if t['date'] and t['date'] in idx: raise ApiError('换算表里已经有 %s 这一行了（第 %d 行）。要恢复，请先删掉那一行' % (t['date'], idx[t['date']][0]))
        at = rg['main_end'] + 1
        for r in range(rg['start'], rg['main_end'] + 1):
            d = norm_date(_v(tab, 'A', r))
            if d and t['date'] and d > t['date']: at = r; break
    else:
        at = max(TABS[k]['start'], min(t['r'], rg['main_end'] + 1 if rg['main_end'] >= TABS[k]['start'] else TABS[k]['start']))
    nxt = tab['rows'][at - 1] if at <= len(tab['rows']) else None
    empty = not has_val(tab, at)
    if not empty or at <= rg['main_end']: xlgrid.insert_row(tab, at, {'c': {}})
    while len(tab['rows']) < at: tab['rows'].append(None)
    dr = at - t['r']
    for cc in x['c'].values():
        if cc.get('f'): cc['f'] = xlgrid.offset_formula(cc['f'], dr, 0)
    tab['rows'][at - 1] = x
    if k == 'ledger':   # 批次剩余是「上一行剩余 − 本行出库」的链：接好本行和下一行
        lc = x['c'].get('L')
        if lc and lc.get('f') and re.fullmatch(r'L\d+-K\d+', lc['f'].replace(' ', '').replace('$', '')): lc['f'] = 'L%d-K%d' % (at - 1, at)
        nl = tab['rows'][at]['c'].get('L') if at < len(tab['rows']) and tab['rows'][at] else None
        if nl and nl.get('f') and re.fullmatch(r'L%d-K%d' % (at - 1, at + 1), nl['f'].replace(' ', '')): nl['f'] = 'L%d-K%d' % (at, at + 1)
    put(c, k, {'rows': tab['rows'], 'merges': tab['merges']}, tab['tpl'], person, '从回收站恢复：%s（第 %d 行）' % (t['label'], at))
    c.execute('UPDATE report_trash SET restored_at=?, restored_by=? WHERE id=?', (now(), person, tid))
    audit(c, person, '恢复', 'report', EID[k], '从回收站恢复 %s' % t['label'])
    also = []
    if k == 'conv' and t['date']:   # 删换算表时一起删掉的入出库记录行，一起恢复（接上联动）
        for o in rows(c.execute("SELECT id,row FROM report_trash WHERE key='ledger' AND restored_at IS NULL AND ABS(deleted_at-?)<5 ORDER BY r", (t['deleted_at'],))):
            ln = (json.loads(o['row']) or {}).get('link') or {}
            if ln.get('k') == 'conv' and ln.get('date') == t['date']: restore_row(c, o['id'], person); also.append(o['id'])
    synced = sync_links(c, person) if k in ('conv', 'ledger', 'lox') else []
    return {'key': k, 'r': at, 'synced': ['ledger'] if (synced or also) else [], 'also': also}

@route('GET', '/api/report/trash')
def api_report_trash(c, q, b, me):
    ensure_schema(c)
    w = 'restored_at IS NULL'; a = []
    if q.get('key'): w += ' AND key=?'; a.append(q['key'])
    if q.get('date'): w += ' AND date=?'; a.append(q['date'])
    return {'items': rows(c.execute('SELECT id,key,r,date,label,deleted_at,deleted_by FROM report_trash WHERE %s ORDER BY deleted_at DESC LIMIT 200' % w, a))}

@route('POST', '/api/report/restore_row', 'delete')
def api_report_restore_row(c, q, b, me): ensure_schema(c); return restore_row(c, int(b['id']), me['name'])

@route('GET', '/api/report/prefs')
def api_report_prefs(c, q, b, me):
    ensure_schema(c)
    return {'items': {x['key']: json.loads(x['data']) for x in rows(c.execute('SELECT key,data FROM report_prefs'))}}

def _clean_prefs(d):
    if not isinstance(d, dict): raise ApiError('设置格式不对')
    col = lambda v: isinstance(v, str) and re.fullmatch(r'[A-Z]{1,3}', v)
    out = {'hidden': [x for x in d.get('hidden') or [] if col(x)][:80], 'order': [x for x in d.get('order') or [] if col(x)][:80],
           'labels': {k: str(v)[:40] for k, v in (d.get('labels') or {}).items() if col(k) and str(v).strip()},
           'from': norm_date(d.get('from')) , 'to': norm_date(d.get('to')),
           'filters': [{'c': f['c'], 'q': str(f.get('q') or '')[:40]} for f in (d.get('filters') or [])[:5]
                       if isinstance(f, dict) and (col(f.get('c')) or f.get('c') == '@u8') and str(f.get('q') or '').strip()]}
    # 列宽（可拖表头调节）：字母列 + 特殊列 @u8/@ph/@att/@act/@rate
    widths = {}
    for ck, cv in (d.get('widths') or {}).items():
        if not isinstance(ck, str): continue
        if not (col(ck) or ck in ('@u8', '@ph', '@att', '@act', '@rate')): continue
        try: w = int(round(float(cv)))
        except (TypeError, ValueError): continue
        widths[ck] = max(36, min(800, w))
    out['widths'] = {k: widths[k] for k in list(widths)[:80]}
    return out

@route('POST', '/api/report/prefs/save', 'entry')
def api_report_prefs_save(c, q, b, me):
    ensure_schema(c); k = b.get('key')
    if k not in TABS: raise ApiError('没有这张表')
    d = _clean_prefs(b.get('data'))
    c.execute('INSERT OR REPLACE INTO report_prefs(key,data,updated_at,updated_by) VALUES(?,?,?,?)', (k, json.dumps(d, ensure_ascii=False), now(), me['name']))
    audit(c, me['name'], '修改', 'report', EID[k], '%s 显示设置' % TABS[k]['short'])
    return {'ok': True, 'data': d}

@route('POST', '/api/report/prefs/reset', 'entry')
def api_report_prefs_reset(c, q, b, me):
    ensure_schema(c); k = b.get('key')
    c.execute('DELETE FROM report_prefs WHERE key=?', (k,))
    audit(c, me['name'], '修改', 'report', EID.get(k, 0), '%s 显示设置恢复默认' % TABS.get(k, {}).get('short', k))
    return {'ok': True}

@route('GET', '/api/report/links')
def api_report_links(c, q, b, me):
    """入出库记录里哪些行跟着换算表的哪一天（删除换算表行前提示用）"""
    led = get_raw(c, 'ledger'); out = []
    for r, x in enumerate(led['rows'], 1):
        ln = x and x.get('link')
        if ln and ln.get('k') == 'conv': out.append({'r': r, 'date': ln.get('date'), 'missing': bool(ln.get('missing')), 'qty': _v(led, 'K', r), 'to': _v(led, 'J', r)})
    return {'items': out}

# ---------------- 接口 ----------------
@route('GET', '/api/reports')
def api_reports(c, q, b, me):
    out = []
    for k in ORDER:
        r = row(c.execute('SELECT version, updated_at, updated_by, tpl FROM report_tabs WHERE key=?', (k,)).fetchone()) or {}
        out.append(dict(key=k, **{x: TABS[k][x] for x in ('title', 'short')}, **r))
    return {'tabs': out}

@route('GET', '/api/report')
def api_report(c, q, b, me):
    k = q.get('key')
    if k not in TABS: raise ApiError('没有这张表')
    d = get_tab(c, k); d['key'] = k; d['cfg'] = TABS[k]; d['widths'] = sheet_widths(c, k, d['tpl'])
    d['readonly'] = k == 'stock'
    if k == 'stock':
        d['pending_u8'] = c.execute("SELECT COUNT(*) FROM arrivals WHERE deleted_at IS NULL AND u8_status='待入U8'").fetchone()[0]
    if k in ('lox', 'yard4'): d['slip_state'] = slip_state(c, d)
    return d

def slip_state(c, tab):
    """液氧表 / 4号院：用称重单登记的行，称重单后来被删了或净重改了，标出来（行里的吨数是人分到各卸点的，不自动改）"""
    out = {}
    for r, x in enumerate(tab['rows'], 1):
        ln = x and x.get('link')
        if not ln or ln.get('k') != 'slip' or not ln.get('ids'): continue
        ids = [int(i) for i in ln['ids']]
        ss = {s['id']: s for s in rows(c.execute('SELECT id, serial, net, deleted_at FROM weigh_slips WHERE id IN (%s)' % ','.join('?' * len(ids)), ids))}
        msg = []
        for i in ids:
            s = ss.get(i)
            if not s or s['deleted_at']: msg.append('称重单 %s 已删除' % ((s or {}).get('serial') or '#%d' % i))
        net = sum((ss[i]['net'] or 0) for i in ids if i in ss and not ss[i]['deleted_at'])
        if ln.get('net') is not None and not msg and abs(net - float(ln['net'])) > 0.5: msg.append('称重单净重已改为 %gkg（登记时 %gkg）' % (net, float(ln['net'])))
        out[r] = {'ids': ids, 'warn': '；'.join(msg)}
    return out

@route('POST', '/api/report/save', 'entry')
def api_report_save(c, q, b, me):
    """b.tabs = {key: {rows, merges, version}}；一次可存多张（如 换算表→入出库记录、登记到车→液氧表+4号院）"""
    tabs = b.get('tabs') or {}
    if not tabs: raise ApiError('没有要保存的内容')
    res = {}
    for k, t in tabs.items():
        if k not in TABS: raise ApiError('没有这张表：%s' % k)
        if k == 'stock': raise ApiError('「库存及到货总数」由到货记录生成，请在「到货」页修改')
        old = get_raw(c, k)
        if int(t.get('version') or 0) != int(old['version'] or 0):
            raise ApiError('「%s」刚被 %s 改过，请刷新后再改（你的修改还在页面上，可以先下载一份）' % (TABS[k]['title'], old.get('updated_by') or '别人'), 409)
        if not isinstance(t.get('rows'), list) or not isinstance(t.get('merges'), list): raise ApiError('表格数据不对')
        kept = preserve_filled(old, t, _PRESERVE_COLS[k], k) if k in _PRESERVE_COLS else []
        n, s = cell_diff(old, t)
        note = b.get('summary') or '修改'
        if kept: note += '（已保住未空写：%s）' % '、'.join(kept[:8])
        res[k] = put(c, k, {'rows': t['rows'], 'merges': t['merges']}, old['tpl'], me['name'], ('%s（改 %d 格）%s' % (note, n, ('：' + s) if s else '')))
    for sid in b.get('slip_ids') or []:
        c.execute('UPDATE weigh_slips SET used_at=? WHERE id=?', (now(), int(sid)))
    ensure_schema(c); trash_rows(c, b.get('trash'), me['name'])
    ch = sync_links(c, me['name']) if ('conv' in tabs or 'ledger' in tabs or 'lox' in tabs) else []
    if ch: res['ledger'] = get_raw(c, 'ledger')['version']
    return {'versions': res, 'synced': ['ledger'] if ch else [], 'sync_notes': ch}

@route('GET', '/api/report.xlsx')
def api_report_xlsx(c, q, b, me):
    k = q.get('key')
    if k not in TABS: raise ApiError('没有这张表')
    return ('file', '%s_%s.xlsx' % (TABS[k]['title'], today().replace('-', '')), build_xlsx(c, k, q.get('sums') != '0'))

@route('POST', '/api/report/import', 'backup')
def api_report_import(c, q, b, me):
    """用户自己的 Excel 替换表（按表名匹配），之后下载也以这个文件为模板"""
    raw = b.get('_raw') or b''
    try: pkg = xlgrid.open_pkg(raw)
    except Exception: raise ApiError('不是 xlsx 文件')
    names = [s['name'] for s in pkg['sheets']]
    only = [x for x in (q.get('keys') or '').split(',') if x]
    hit = [k for k in ORDER if TABS[k]['sheet'] in names and (not only or k in only)]
    if not hit: raise ApiError('文件里没有可导入的表。需要的表名：%s；文件里的表：%s' % ('、'.join(TABS[k]['sheet'] for k in ORDER), '、'.join(names)))
    fn = 'imp_%s_%s.xlsx' % (datetime.datetime.now().strftime('%Y%m%d%H%M%S'), hashlib.md5(raw).hexdigest()[:6])
    with open(os.path.join(tpl_dir(), fn), 'wb') as f: f.write(raw)
    for k in hit:
        t = xlgrid.read_sheet(raw, TABS[k]['sheet'], pkg); strip_auto_sums(k, t)
        old = get_raw(c, k)   # 行附件按内容尽量保留
        sig = lambda x: '|'.join(str((x['c'].get(cc) or {}).get('v', (x['c'].get(cc) or {}).get('f', ''))) for cc in 'ABCDEI') if x else ''
        att = {sig(x): x['att'] for x in old['rows'] if x and x.get('att')}
        for x in t['rows']:
            if x and sig(x) in att: x['att'] = att[sig(x)]
        put(c, k, {'rows': t['rows'], 'merges': t['merges']}, fn, me['name'], '导入 Excel（%s）' % (q.get('name') or fn))
    return {'keys': hit}

@route('POST', '/api/report/reset', 'backup')
def api_report_reset(c, q, b, me):
    k = b.get('key')
    if k not in TABS: raise ApiError('没有这张表')
    data = tpl_bytes(TABS[k]['book']); t = xlgrid.read_sheet(data, TABS[k]['sheet'])
    put(c, k, {'rows': t['rows'], 'merges': t['merges']}, TABS[k]['book'], me['name'], '恢复为内置原表')
    return {'ok': 1}
