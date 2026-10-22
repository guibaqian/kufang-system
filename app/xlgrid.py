# -*- coding: utf-8 -*-
"""报表引擎（移植 v82 O2 核心）：读原表为网格 / 公式平移 / 公式计算 / 以原工作簿为模板生成单表 xlsx。
网格结构 tab = {'rows': [ {'c': {'A': {'v':..,'f':..,'s':..}}, 'ra': '行属性'} | None ], 'merges': ['A1:B2']}"""
import re, io, zipfile, math
from xml.sax.saxutils import escape

def col2n(c):
    n = 0
    for ch in c: n = n * 26 + ord(ch) - 64
    return n
def n2col(n):
    s = ''
    while n > 0: n, m = divmod(n - 1, 26); s = chr(65 + m) + s
    return s
def split_addr(a):
    m = re.match(r'^\$?([A-Z]{1,3})\$?(\d+)$', a)
    return (m.group(1), int(m.group(2))) if m else None
def unesc(s):
    s = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), s)
    s = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)), s)
    return s.replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&apos;', "'").replace('&amp;', '&')
def xesc(s): return escape(str(s), {'"': '&quot;'})

# ---------------- 公式引用平移 ----------------
_REF = re.compile(r'("(?:[^"]|"")*")|((?:\'[^\']+\'|[A-Za-z_\u4e00-\u9fa5][\w\u4e00-\u9fa5.]*)!)?(\$?)([A-Z]{1,3})(\$?)(\d+)(?![\w(])')
def map_refs(f, fn, qualified=False):
    """fn(col, col_abs, row, row_abs) -> (col, row) 或 None(#REF!)"""
    def rep(m):
        if m.group(1): return m.group(0)
        st = m.start(); prev = f[st - 1] if st > 0 else ''
        if re.match(r'[A-Za-z_\d.]', prev): return m.group(0)
        if m.group(2) and not qualified: return m.group(0)
        r = fn(m.group(4), m.group(3) == '$', int(m.group(6)), m.group(5) == '$')
        if r is None: return '#REF!'
        return (m.group(2) or '') + m.group(3) + r[0] + m.group(5) + str(r[1])
    return _REF.sub(rep, f)
def shift_formula(f, at, delta):
    def fn(c, ca, r, ra):
        if delta > 0: return (c, r + delta if r >= at else r)
        if r == at: return None
        return (c, r + delta if r > at else r)
    return map_refs(f, fn)
def offset_formula(f, dr, dc):
    """共享公式展开：相对引用按行列偏移"""
    return map_refs(f, lambda c, ca, r, ra: (c if ca else n2col(col2n(c) + dc), r if ra else r + dr), qualified=True)
def shift_range(ref, at, delta):
    a, _, b = ref.partition(':'); A = split_addr(a); B = split_addr(b or a)
    r1, r2 = A[1], B[1]
    if delta > 0:
        if r1 >= at: r1 += delta
        if r2 >= at: r2 += delta
    else:
        if r1 == at and r2 == at: return None
        if r1 > at: r1 += delta
        if r2 >= at: r2 += delta
    if r2 < r1: return None
    return '%s%d:%s%d' % (A[0], r1, B[0], r2)
def insert_row(tab, at, row=None):
    tab['rows'].insert(at - 1, row or {'c': {}})
    for r in tab['rows']:
        if r:
            for c in r['c'].values():
                if c.get('f'): c['f'] = shift_formula(c['f'], at, 1)
    tab['merges'] = [x for x in (shift_range(m, at, 1) for m in tab['merges']) if x]
def delete_row(tab, at):
    del tab['rows'][at - 1]
    for r in tab['rows']:
        if r:
            for c in r['c'].values():
                if c.get('f'): c['f'] = shift_formula(c['f'], at, -1)
    tab['merges'] = [x for x in (shift_range(m, at, -1) for m in tab['merges']) if x]

# ---------------- 读原表 ----------------
def open_pkg(data):
    z = zipfile.ZipFile(io.BytesIO(data)); files = {n: z.read(n) for n in z.namelist()}
    get = lambda p: files[p].decode('utf-8') if p in files else None
    wb = get('xl/workbook.xml'); relx = get('xl/_rels/workbook.xml.rels') or ''
    rels = {}
    for t in re.findall(r'<Relationship\b[^>]*>', relx):
        i = re.search(r'\bId="([^"]+)"', t); tg = re.search(r'\bTarget="([^"]+)"', t); ty = re.search(r'\bType="([^"]+)"', t)
        if i: rels[i.group(1)] = {'target': tg.group(1) if tg else '', 'type': ty.group(1) if ty else '', 'raw': t}
    sheets = []
    for i, t in enumerate(re.findall(r'<sheet\b[^>]*>', wb)):
        name = unesc((re.search(r'\bname="([^"]*)"', t) or [None, ''])[1])
        rid = (re.search(r'\br:id="([^"]+)"', t) or re.search(r'\bid="([^"]+)"', t)).group(1)
        tg = rels.get(rid, {}).get('target', '')
        path = tg[1:] if tg.startswith('/') else 'xl/' + re.sub(r'^\./', '', tg)
        sheets.append({'name': name, 'rid': rid, 'path': path, 'tag': t, 'index': i})
    return {'files': files, 'get': get, 'wb': wb, 'relx': relx, 'rels': rels, 'sheets': sheets, 'order': z.namelist(), 'info': {i.filename: i for i in z.infolist()}}

def _sst(xml):
    out = []
    for si in re.findall(r'<si>(.*?)</si>', xml or '', re.S):
        si = re.sub(r'<rPh\b.*?</rPh>', '', si, flags=re.S)
        out.append(unesc(''.join(re.findall(r'<t(?:\s[^>]*)?>(.*?)</t>', si, re.S))))
    return out
def _num(s):
    x = float(s)
    return int(x) if x.is_integer() and abs(x) < 1e15 and 'e' not in s.lower() and '.' not in s else x

def read_sheet(data, sheet_name, pkg=None):
    pkg = pkg or open_pkg(data)
    sh = next((s for s in pkg['sheets'] if s['name'] == sheet_name), None)
    if not sh: return None
    sst = _sst(pkg['get']('xl/sharedStrings.xml'))
    xml = pkg['get'](sh['path']) or ''
    rows = []; shared = {}
    for m in re.finditer(r'<row\b([^>]*?)(/>|>(.*?)</row>)', xml, re.S):
        attrs = m.group(1); rn = re.search(r'\br="(\d+)"', attrs)
        if not rn: continue
        r = int(rn.group(1))
        ra = re.sub(r'\s*\bx14ac:dyDescent="[^"]*"', '', re.sub(r'\s*\bspans="[^"]*"', '', re.sub(r'\s*\br="\d+"', '', attrs))).strip()
        row = {'c': {}}
        if ra: row['ra'] = ra
        for cm in re.finditer(r'<c\b([^>]*?)(?:/>|>(.*?)</c>)', m.group(3) or '', re.S):
            ca, body = cm.group(1), cm.group(2) or ''
            ref = re.search(r'\br="([A-Z]+)(\d+)"', ca)
            if not ref: continue
            col = ref.group(1); o = {}
            s = re.search(r'\bs="(\d+)"', ca)
            if s and s.group(1) != '0': o['s'] = int(s.group(1))
            t = (re.search(r'\bt="(\w+)"', ca) or [None, 'n'])[1]
            fm = re.search(r'<f\b([^>]*?)(?:/>|>(.*?)</f>)', body, re.S)
            if fm:
                fa, ft = fm.group(1), unesc(fm.group(2) or '')
                si = re.search(r'\bsi="(\d+)"', fa)
                if 't="shared"' in fa and si:
                    if ft: shared[si.group(1)] = (ft, r, col2n(col))
                    elif si.group(1) in shared:
                        f0, r0, c0 = shared[si.group(1)]; ft = offset_formula(f0, r - r0, col2n(col) - c0)
                if ft: o['f'] = ft
            if 'f' not in o:
                v = re.search(r'<v>(.*?)</v>', body, re.S)
                if t == 's' and v: val = sst[int(v.group(1))]; val and o.update(v=val)
                elif t == 'inlineStr':
                    val = unesc(''.join(re.findall(r'<t(?:\s[^>]*)?>(.*?)</t>', body, re.S)))
                    if val: o['v'] = val
                elif t == 'str' and v and v.group(1): o['v'] = unesc(v.group(1))
                elif t == 'b' and v: o['v'] = 1 if v.group(1) == '1' else 0
                elif t == 'n' and v and v.group(1) != '': o['v'] = _num(v.group(1))
            row['c'][col] = o
        while len(rows) < r: rows.append(None)
        rows[r - 1] = row
    merges = re.findall(r'<mergeCell ref="([^"]+)"', xml)
    return {'rows': rows, 'merges': merges}

# ---------------- 公式计算（与 v82 相同的子集） ----------------
class _Err(Exception): pass
def _is_err(v): return isinstance(v, str) and v[:1] == '#'
class Evaluator:
    def __init__(self, tab): self.tab = tab; self.cache = {}; self.busy = set()
    def cell(self, col, r):
        k = (col, r)
        if k in self.cache: return self.cache[k]
        rows = self.tab['rows']; row = rows[r - 1] if 0 < r <= len(rows) else None; c = row and row['c'].get(col)
        v = None
        if c:
            if c.get('f'):
                if k in self.busy: v = '#循环'
                else:
                    self.busy.add(k)
                    try: v = self.eval(c['f'])
                    except Exception: v = '#ERR'
                    self.busy.discard(k)
            elif c.get('v') is not None: v = c['v']
        self.cache[k] = v; return v
    def eval(self, f):
        s = f; i = [0]
        def ws():
            while i[0] < len(s) and s[i[0]] == ' ': i[0] += 1
        def ch(): return s[i[0]] if i[0] < len(s) else ''
        def num(v):
            if v is None or v == '': return 0
            if isinstance(v, bool): return 1 if v else 0
            if isinstance(v, (int, float)): return v
            if _is_err(v): raise _Err(v)
            try: return float(v) if str(v).strip() != '' else 0
            except ValueError: raise _Err('#VALUE!')
        def flat(args):
            out = []
            for a in args:
                if isinstance(a, tuple):
                    c1, r1, c2, r2 = a
                    for r in range(min(r1, r2), max(r1, r2) + 1):
                        for cc in range(min(col2n(c1), col2n(c2)), max(col2n(c1), col2n(c2)) + 1):
                            v = self.cell(n2col(cc), r)
                            if _is_err(v): raise _Err(v)
                            if isinstance(v, (int, float)) and not isinstance(v, bool): out.append(v)
                else:
                    if _is_err(a): raise _Err(a)
                    out.append(num(a))
            return out
        def call(n, a):
            if n == 'SUM': return sum(flat(a))
            if n == 'AVERAGE': v = flat(a); return sum(v) / len(v) if v else '#DIV/0!'
            if n == 'MIN': v = flat(a); return min(v) if v else 0
            if n == 'MAX': v = flat(a); return max(v) if v else 0
            if n == 'ABS': return abs(num(a[0]))
            if n == 'ROUND':
                p = 10 ** num(a[1] if len(a) > 1 else 0); x = num(a[0]) * p
                return math.floor(x + 0.5) / p   # 与 JS Math.round 一致
            if n == 'IF': return (a[1] if len(a) > 1 else True) if (a[0] and a[0] != 0) else (a[2] if len(a) > 2 else False)
            raise _Err('#NAME?')
        def primary():
            ws(); c = ch()
            if c == '(':
                i[0] += 1; v = comp(); ws()
                if ch() == ')': i[0] += 1
                return v
            if c == '-': i[0] += 1; return -num(power())
            if c == '+': i[0] += 1; return num(power())
            if c == '"':
                j = i[0] + 1; out = ''
                while j < len(s):
                    if s[j] == '"':
                        if j + 1 < len(s) and s[j + 1] == '"': out += '"'; j += 2; continue
                        break
                    out += s[j]; j += 1
                i[0] = j + 1; return out
            rest = s[i[0]:]
            m = re.match(r'\d+(\.\d+)?([eE][+-]?\d+)?|\.\d+', rest)
            if m: i[0] += len(m.group(0)); return float(m.group(0))
            m = re.match(r'\$?([A-Z]{1,3})\$?(\d+)(?::\$?([A-Z]{1,3})\$?(\d+))?', rest)
            if m and not re.match(r'[A-Z]+\(', rest):
                i[0] += len(m.group(0))
                if m.group(3): return (m.group(1), int(m.group(2)), m.group(3), int(m.group(4)))
                return self.cell(m.group(1), int(m.group(2)))
            m = re.match(r'([A-Z][A-Z0-9.]*)\(', rest)
            if m:
                i[0] += len(m.group(0)); args = []; ws()
                if ch() == ')': i[0] += 1
                else:
                    while True:
                        args.append(comp()); ws()
                        if ch() == ',': i[0] += 1; continue
                        if ch() == ')': i[0] += 1
                        break
                return call(m.group(1), args)
            if rest.startswith('#REF!'): raise _Err('#REF!')
            raise _Err('#NAME?')
        def power():
            v = primary(); ws()
            while ch() == '^': i[0] += 1; v = num(v) ** num(primary()); ws()
            return v
        def term():
            v = power(); ws()
            while ch() in ('*', '/') and ch():
                op = ch(); i[0] += 1; r = power()
                if op == '*': v = num(v) * num(r)
                else:
                    d = num(r)
                    if d == 0: raise _Err('#DIV/0!')
                    v = num(v) / d
                ws()
            return v
        def expr():
            v = term(); ws()
            while ch() in ('+', '-', '&') and ch():
                op = ch(); i[0] += 1; r = term()
                if op == '&': v = ('' if v is None else str(v)) + ('' if r is None else str(r))
                else: v = num(v) + num(r) if op == '+' else num(v) - num(r)
                ws()
            return v
        def comp():
            v = expr(); ws()
            m = re.match(r'<=|>=|<>|=|<|>', s[i[0]:])
            if m:
                i[0] += len(m.group(0)); r = expr(); op = m.group(0)
                try:
                    return {'=': v == r, '<>': v != r, '<': v < r, '>': v > r, '<=': v <= r, '>=': v >= r}[op]
                except TypeError: return False
            return v
        try:
            v = comp()
            return '#VALUE!' if isinstance(v, tuple) else v
        except _Err as e: return str(e)
        except Exception: return '#ERR'

def _fmt(v):
    v = float('%.15g' % v)
    return str(int(v)) if v.is_integer() and abs(v) < 1e15 else repr(v)

# ---------------- 生成单表工作簿 ----------------
def _cell_xml(ref, c, ev, col, r):
    s = ' s="%d"' % c['s'] if c.get('s') else ''
    if c.get('f'):
        v = ev.cell(col, r); vx = ''; t = ''
        if isinstance(v, bool): t = ' t="b"'; vx = '<v>%d</v>' % v
        elif isinstance(v, (int, float)) and math.isfinite(v): vx = '<v>%s</v>' % _fmt(v)
        elif isinstance(v, str) and v and not _is_err(v): t = ' t="str"'; vx = '<v>%s</v>' % xesc(v)
        return '<c r="%s"%s%s><f>%s</f>%s</c>' % (ref, s, t, xesc(c['f']), vx)
    v = c.get('v')
    if v is None or v == '': return '<c r="%s"%s/>' % (ref, s)
    if isinstance(v, (int, float)) and not isinstance(v, bool): return '<c r="%s"%s><v>%s</v></c>' % (ref, s, _fmt(v) if isinstance(v, float) else v)
    return '<c r="%s"%s t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, s, xesc(v))

def sheet_data_xml(tab):
    ev = Evaluator(tab); out = ['<sheetData>']
    for i, row in enumerate(tab['rows']):
        if not row: continue
        r = i + 1; cols = sorted(row['c'], key=col2n)
        if not cols and not row.get('ra'): continue
        out.append('<row r="%d"%s>' % (r, (' ' + row['ra']) if row.get('ra') else ''))
        for c in cols: out.append(_cell_xml('%s%d' % (c, r), row['c'][c], ev, c, r))
        out.append('</row>')
    out.append('</sheetData>'); return ''.join(out)

def last_row(tab):
    for i in range(len(tab['rows']) - 1, -1, -1):
        r = tab['rows'][i]
        if r and r['c']: return i + 1
    return 1

_AFTER_SD = r'(</sheetData>(?:<sheetCalcPr[^>]*/>)?(?:<sheetProtection[^>]*/>)?(?:<protectedRanges>.*?</protectedRanges>)?(?:<scenarios.*?</scenarios>)?(?:<autoFilter[^>]*/>|<autoFilter.*?</autoFilter>)?(?:<sortState.*?</sortState>)?(?:<dataConsolidate.*?</dataConsolidate>)?(?:<customSheetViews>.*?</customSheetViews>)?)'
def build_sheet_xml(x, tab, top_row=None, active_row=None):
    x = re.sub(r'<sheetData\s*/>|<sheetData>.*</sheetData>', lambda m: sheet_data_xml(tab), x, count=1, flags=re.S)
    lr = last_row(tab); maxc = 1
    for r in tab['rows']:
        if r:
            for c in r['c']: maxc = max(maxc, col2n(c))
    x = re.sub(r'<dimension ref="[^"]*"\s*/>', '<dimension ref="A1:%s%d"/>' % (n2col(maxc), lr), x, count=1)
    mc = ('<mergeCells count="%d">%s</mergeCells>' % (len(tab['merges']), ''.join('<mergeCell ref="%s"/>' % m for m in tab['merges']))) if tab['merges'] else ''
    if re.search(r'<mergeCells\b.*?</mergeCells>', x, re.S): x = re.sub(r'<mergeCells\b.*?</mergeCells>', lambda m: mc, x, count=1, flags=re.S)
    elif mc: x = re.sub(_AFTER_SD, lambda m: m.group(1) + mc, x, count=1, flags=re.S)
    if top_row:
        x = re.sub(r'(<pane\b[^>]*\btopLeftCell=")([A-Z]+)(\d+)(")', lambda m: m.group(1) + m.group(2) + str(top_row) + m.group(4), x, count=1)
        x = re.sub(r'(<selection\b[^>]*pane="bottom(?:Left|Right)"[^>]*\bactiveCell=")[A-Z]+\d+("[^>]*\bsqref=")[^"]*(")', lambda m: m.group(1) + 'A%d' % active_row + m.group(2) + 'A%d' % active_row + m.group(3), x, count=1)
    x = re.sub(r'\btabSelected="1"\s*', '', x)
    x = re.sub(r'<sheetView\b', '<sheetView tabSelected="1"', x, count=1)
    return x

def _norm(p):
    a = []
    for x in p.split('/'):
        if x == '..':
            if a: a.pop()
        elif x and x != '.': a.append(x)
    return '/'.join(a)

def build_workbook(tpl, sheet_name, tab, top_row=None, active_row=None):
    pkg = open_pkg(tpl); files = dict(pkg['files'])
    sh = next((s for s in pkg['sheets'] if s['name'] == sheet_name), None)
    if not sh: raise ValueError('模板中没有工作表「%s」' % sheet_name)
    ct = pkg['get']('[Content_Types].xml'); remove = []
    for o in pkg['sheets']:
        if o is sh: continue
        remove.append(o['path'])
        relp = re.sub(r'([^/]+)$', r'_rels/\1.rels', o['path']); rx = pkg['get'](relp)
        if rx:
            remove.append(relp)
            for tg in re.findall(r'Target="([^"]+)"', rx):
                if re.match(r'https?:', tg): continue
                full = _norm(re.sub(r'[^/]+$', '', o['path']) + tg)
                if re.search(r'(drawings|comments|vmlDrawing|printerSettings|tables|threadedComments)', full, re.I): remove.append(full)
    for r in pkg['rels'].values():
        if r['type'].endswith('calcChain'): remove.append('xl/' + re.sub(r'^/?xl/', '', r['target']))
    for p in remove:
        files.pop(p, None); ct = re.sub(r'<Override[^>]*PartName="/%s"[^>]*/>' % re.escape(p), '', ct)
    files['[Content_Types].xml'] = ct.encode()
    wb = pkg['wb']
    wb = re.sub(r'<sheets>.*?</sheets>', lambda m: '<sheets>' + sh['tag'] + '</sheets>', wb, count=1, flags=re.S)
    def dn(m):
        keep = []
        for d in re.findall(r'<definedName\b.*?</definedName>', m.group(1), re.S):
            lid = re.search(r'localSheetId="(\d+)"', d)
            if lid is not None:
                if int(lid.group(1)) == sh['index']: keep.append(re.sub(r'localSheetId="\d+"', 'localSheetId="0"', d))
                continue
            txt = re.sub(r'<[^>]+>', '', d)
            if sheet_name in txt and all(o is sh or (o['name'] + '!') not in txt for o in pkg['sheets']): keep.append(d)
        return '<definedNames>' + ''.join(keep) + '</definedNames>' if keep else ''
    wb = re.sub(r'<definedNames>(.*?)</definedNames>', dn, wb, count=1, flags=re.S)
    wb = re.sub(r'\bactiveTab="\d+"', 'activeTab="0"', wb); wb = re.sub(r'\bfirstSheet="\d+"', 'firstSheet="0"', wb)
    if re.search(r'<calcPr\b', wb):
        wb = re.sub(r'<calcPr\b([^>]*?)/?>', lambda m: '<calcPr' + re.sub(r'\s*fullCalcOnLoad="[^"]*"', '', m.group(1)) + ' fullCalcOnLoad="1"/>', wb, count=1)
    else:
        wb = re.sub(r'</sheets>(.*?)(</workbook>)', lambda m: '</sheets>' + re.sub(r'(<extLst>.*)?$', lambda e: '<calcPr fullCalcOnLoad="1"/>' + (e.group(0) or ''), m.group(1), count=1, flags=re.S) + m.group(2), wb, count=1, flags=re.S)
    files['xl/workbook.xml'] = wb.encode()
    rel = pkg['relx']
    for o in pkg['sheets']:
        if o is not sh and o['rid'] in pkg['rels']: rel = rel.replace(pkg['rels'][o['rid']]['raw'], '')
    for r in pkg['rels'].values():
        if r['type'].endswith('calcChain'): rel = rel.replace(r['raw'], '')
    files['xl/_rels/workbook.xml.rels'] = rel.encode()
    app = pkg['get']('docProps/app.xml')
    if app: files['docProps/app.xml'] = re.sub(r'<TitlesOfParts>.*?</TitlesOfParts>', '', re.sub(r'<HeadingPairs>.*?</HeadingPairs>', '', app, flags=re.S), flags=re.S).encode()
    files[sh['path']] = build_sheet_xml(pkg['get'](sh['path']), tab, top_row, active_row).encode()
    out = io.BytesIO(); z = zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED)
    order = [n for n in pkg['order'] if n in files] + [n for n in files if n not in pkg['order']]
    for n in order: z.writestr(n, files[n])
    z.close(); return out.getvalue()
