# -*- coding: utf-8 -*-
"""纯标准库的 xlsx 读写：
   - fill_daily(): 以原表为模板，只改单元格值（样式/合并/列宽/公式全部保留）
   - read_sheet(): 读取 xlsx 第一个（或指定）工作表为 {坐标: 值}
   - simple_xlsx(): 生成简单表格（批次追溯、盘点清单等）"""
import zipfile, re, io, os
from xml.sax.saxutils import escape

def col2n(s):
    n = 0
    for ch in s: n = n * 26 + ord(ch) - 64
    return n
def n2col(n):
    s = ''
    while n: n, r = divmod(n - 1, 26); s = chr(65 + r) + s
    return s

def _unesc(s): return s.replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&apos;', "'").replace('&amp;', '&')

def _sst(xml):
    out = []
    for si in re.findall(r'<si>(.*?)</si>', xml, re.S):
        out.append(_unesc(''.join(re.findall(r'<t[^>]*>(.*?)</t>', si, re.S))))
    return out

def read_sheet(data, sheet_index=0):
    z = zipfile.ZipFile(io.BytesIO(data) if isinstance(data, bytes) else data)
    names = z.namelist()
    sst = _sst(z.read('xl/sharedStrings.xml').decode('utf-8')) if 'xl/sharedStrings.xml' in names else []
    wb = z.read('xl/workbook.xml').decode('utf-8')
    rels = z.read('xl/_rels/workbook.xml.rels').decode('utf-8')
    sheets = re.findall(r'<sheet [^>]*?name="([^"]*)"[^>]*?r:id="([^"]+)"', wb)
    name, rid = sheets[sheet_index]
    tgt = re.search(r'<Relationship [^>]*Id="%s"[^>]*Target="([^"]+)"' % rid, rels) or re.search(r'<Relationship [^>]*Target="([^"]+)"[^>]*Id="%s"' % rid, rels)
    path = tgt.group(1).lstrip('/'); path = path if path.startswith('xl/') else 'xl/' + path
    xml = z.read(path).decode('utf-8')
    cells = {}
    for m in re.finditer(r'<c r="([A-Z]+\d+)"([^>]*?)(?:/>|>(.*?)</c>)', xml, re.S):
        ref, attrs, inner = m.group(1), m.group(2), m.group(3) or ''
        t = re.search(r' t="(\w+)"', attrs); t = t.group(1) if t else 'n'
        v = re.search(r'<v>(.*?)</v>', inner, re.S)
        f = re.search(r'<f[^>]*>(.*?)</f>', inner, re.S)
        if t == 's' and v: val = sst[int(v.group(1))]
        elif t == 'inlineStr': val = _unesc(''.join(re.findall(r'<t[^>]*>(.*?)</t>', inner, re.S)))
        elif t == 'str' and v: val = _unesc(v.group(1))
        elif v:
            try:
                x = float(v.group(1)); val = int(x) if x == int(x) else x
            except ValueError: val = _unesc(v.group(1))
        else: val = None
        if val is not None and val != '': cells[ref] = val
        if f and f.group(1): cells.setdefault('_f', {})[ref] = _unesc(f.group(1))
    return {'name': name, 'cells': cells}

# ---------------- 钢瓶日表：模板填写 ----------------
INPUT_COLS = set(['A', 'AH', 'BK'] + [n2col(i) for i in range(col2n('B'), col2n('I') + 1)] + [n2col(i) for i in range(col2n('N'), col2n('Q') + 1)]
                 + [n2col(i) for i in range(col2n('T'), col2n('AG') + 1)] + [n2col(i) for i in range(col2n('AI'), col2n('AV') + 1)])
FIRST, STEP = 5, 2

def _fmt(x):
    if isinstance(x, float) and x == int(x): x = int(x)
    return repr(x) if isinstance(x, float) else str(x)

NOTE_FIT = 28   # 备注格（BK 列宽 28.25）一行放得下的宽度：汉字算 2、数字字母算 1，约 14 个汉字
def text_w(t): return sum(2 if ord(ch) > 0x2e7f else 1 for ch in str(t or ''))
def note_long(t): return text_w(t) > NOTE_FIT

def fill_daily(tpl_bytes, title, people, cyl_cols, other_cols, calc):
    """people: [{'name','vals','note'}]；cyl_cols: [(key,col)]；other_cols: [(key,take,ret,net)]；calc(vals)->dict"""
    zin = zipfile.ZipFile(io.BytesIO(tpl_bytes))
    files = {n: zin.read(n) for n in zin.namelist()}
    sheet = files['xl/worksheets/sheet1.xml'].decode('utf-8')
    # 排版（不改原表样式和结构）：A 列（领取人信息）按最长的配送员名字收窄（不写车牌后用不了原来那么宽）；
    # 数字列统一 5.5 宽；两行小表头 12 → 15 磅，字不挤
    aw = max([text_w('领取人信息')] + [text_w(p.get('label') or p['name']) for p in people]) * 1.1 + 2.5
    sheet = sheet.replace('<col min="1" max="1" width="16.75"', '<col min="1" max="1" width="%.2f"' % min(16.75, max(8, aw)), 1)
    sheet = re.sub(r'<col min="(19|49)" max="(19|62)" width="[\d.]+"', r'<col min="\1" max="\2" width="5.5"', sheet)
    sheet = re.sub(r'<row r="([34])" ht="12"', r'<row r="\1" ht="15"', sheet)
    sstx = files['xl/sharedStrings.xml'].decode('utf-8')
    sis = re.findall(r'<si>.*?</si>', sstx, re.S)
    sis[0] = '<si><t>%s</t></si>' % escape(title)
    def sidx(s):
        x = '<si><t%s>%s</t></si>' % (' xml:space="preserve"' if s != s.strip() else '', escape(s))
        if x in sis: return sis.index(x)
        sis.append(x); return len(sis) - 1
    stx = files['xl/styles.xml'].decode('utf-8')   # 加一个「靠左、自动换行、带边框」的格式给长备注
    xfs = re.search(r'<cellXfs count="(\d+)">(.*?)</cellXfs>', stx, re.S); nxf = int(xfs.group(1))
    base = re.findall(r'<xf [^>]*/>|<xf [^>]*[^/]>.*?</xf>', xfs.group(2), re.S)[10]
    lxf = re.sub(r'<alignment[^>]*/>', '<alignment horizontal="left" vertical="center" wrapText="1"/>', base)
    stx = stx[:xfs.start()] + '<cellXfs count="%d">%s%s</cellXfs>' % (nxf + 1, xfs.group(2), lxf) + stx[xfs.end():]
    files['xl/styles.xml'] = stx.encode('utf-8')
    # 每行要写的值
    rowvals = {}; longs = []
    for i, p in enumerate(people):
        r = FIRST + STEP * i
        v = p['vals']; cv = calc(v); d = {}
        nm = p.get('label') or p['name']   # 领取人信息：只写配送员，不写车牌
        d['A'] = ('s', nm); d['AH'] = ('s', nm)
        for k, col in cyl_cols:
            if v.get(k): d[col] = ('n', v[k])
        for k, tc, rc, nc in other_cols:   # 次日清点：领取列含早上车上剩余（v0），入库列含次日早上车上剩余（v1），当天总出库 = 领取 − 入库
            t_ = (v.get('t_' + k) or 0) + (v.get('v0_' + k) or 0); i_ = (v.get('i_' + k) or 0) + (v.get('v1_' + k) or 0)
            if t_: d[tc] = ('n', t_)
            if i_: d[rc] = ('n', i_)
        if p.get('note') and note_long(p['note']):   # 备注太长：放到这人下面那一空行（整行合并、靠左、自动换行），备注格写「见下行」
            d['BK'] = ('s', '见下行'); rowvals[r + 1] = {'A': ('s', p['note']), '_long': p['note']}; longs.append(r + 1)
        elif p.get('note'): d['BK'] = ('s', p['note'])
        d['_calc'] = cv; d['_vals'] = v
        rowvals[r] = d
    last_needed = FIRST + STEP * max(len(people) - 1, 0) + 1
    # 模板行数不够时，按最后一行克隆
    row_re = re.compile(r'<row r="(\d+)"([^>]*)>(.*?)</row>', re.S)
    tpl_rows = {int(m.group(1)): m for m in row_re.finditer(sheet)}
    data_rows = [r for r in tpl_rows if r >= FIRST and re.search(r'<f', tpl_rows[r].group(3))]
    tpl_last = max(data_rows)
    if last_needed > tpl_last:
        proto = tpl_rows[tpl_last]
        extra = ''
        for r in range(tpl_last + 1, last_needed + 1):
            cells = []
            for m in re.finditer(r'<c r="([A-Z]+)\d+"([^>]*?)(?:/>|>(.*?)</c>)', proto.group(3), re.S):
                col, attrs, inner = m.group(1), m.group(2), m.group(3) or ''
                s = re.search(r' s="\d+"', attrs); s = s.group(0) if s else ''
                f = FORMULA.get(col)
                if f: cells.append('<c r="%s%d"%s><f>%s</f><v>0</v></c>' % (col, r, s, f.replace('#', str(r))))
                else: cells.append('<c r="%s%d"%s/>' % (col, r, s))
            attrs = re.sub(r' r="\d+"', '', proto.group(2))
            extra += '<row r="%d"%s>%s</row>' % (r, attrs, ''.join(cells))
        end = proto.end()
        sheet = sheet[:end] + extra + sheet[end:]
    calc_cols = {'J': 'J40', 'K': 'J10', 'L': 'L40', 'M': 'L10', 'R': 'R40', 'S': 'R10'}
    for k, tc, rc, nc in other_cols: calc_cols[nc] = 'net_' + k
    def fix_row(m):
        r = int(m.group(1))
        if r < FIRST: return m.group(0)
        d = rowvals.get(r, {}); cv = d.get('_calc', {})
        have = set()
        def fix_cell(cm):
            col, attrs, inner = cm.group(1), cm.group(2), cm.group(3) or ''
            have.add(col)
            ref = '%s%d' % (col, r)
            attrs_clean = re.sub(r' t="\w+"', '', attrs)
            if d.get('_long'):   # 长备注那一行：A 格写备注（靠左换行），其余格清空（整行合并）
                if col == 'A': return '<c r="%s"%s t="s"><v>%d</v></c>' % (ref, re.sub(r' s="\d+"', ' s="%d"' % nxf, attrs_clean), sidx(d['_long']))
                return '<c r="%s"%s/>' % (ref, attrs_clean)
            if '<f' in inner:
                fpart = re.search(r'<f[^>]*/>|<f[^>]*>.*?</f>', inner, re.S).group(0)
                val = cv.get(calc_cols.get(col), 0) if col in calc_cols else 0
                return '<c r="%s"%s>%s<v>%s</v></c>' % (ref, attrs_clean, fpart, _fmt(val))
            if col in INPUT_COLS:
                if col in d:
                    t, val = d[col]
                    if t == 's': return '<c r="%s"%s t="s"><v>%d</v></c>' % (ref, attrs_clean, sidx(val))
                    return '<c r="%s"%s><v>%s</v></c>' % (ref, attrs_clean, _fmt(val))
                return '<c r="%s"%s/>' % (ref, attrs_clean)
            if col == 'BJ' and r in rowvals and (d['_vals'].get('t_j1') or d['_vals'].get('i_j1')):
                return '<c r="%s"%s><f>AG%d-AV%d</f><v>%s</v></c>' % (ref, attrs_clean, r, r, _fmt(cv.get('net_j1', 0)))
            return cm.group(0)
        body = re.sub(r'<c r="([A-Z]+)%d"([^>]*?)(?:/>|>(.*?)</c>)' % r, fix_cell, m.group(3), flags=re.S)
        ra = m.group(2)
        if d.get('_long'):   # 行高按字数：可见列约 170 个字宽一行
            ht = max(27, 16 * -(-text_w(d['_long']) // 170) + 8)
            ra = re.sub(r' ht="[^"]*"', ' ht="%d"' % ht, ra) if ' ht=' in ra else ra + ' ht="%d" customHeight="1"' % ht
        return '<row r="%s"%s>%s</row>' % (m.group(1), ra, body)
    sheet = row_re.sub(fix_row, sheet)
    sheet, wbfix = trim_daily(sheet, FIRST - 1 + STEP * len(people), ['A%d:BK%d' % (x, x) for x in longs])
    total = len(re.findall(r't="s"', sheet))
    sstx_new = re.sub(r'<sst ([^>]*)>.*</sst>', lambda mm: '<sst %s>%s</sst>' % (
        re.sub(r'uniqueCount="\d+"', 'uniqueCount="%d"' % len(sis), re.sub(r'count="\d+"', 'count="%d"' % total, mm.group(1))), ''.join(sis)), sstx, flags=re.S)
    files['xl/worksheets/sheet1.xml'] = sheet.encode('utf-8')
    files['xl/sharedStrings.xml'] = sstx_new.encode('utf-8')
    wb = files['xl/workbook.xml'].decode('utf-8')
    if 'fullCalcOnLoad' not in wb: wb = re.sub(r'<calcPr ([^>]*?)/>', r'<calcPr \1 fullCalcOnLoad="1"/>', wb)
    wb = wbfix(wb)
    files['xl/workbook.xml'] = wb.encode('utf-8')
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zo:
        for n in zin.namelist(): zo.writestr(zin.getinfo(n), files[n])
    return out.getvalue()

def trim_daily(sheet, last, more_merges=()):
    """下载 / 打印：只留到最后一个配送员下面那一空行（每人一行数 + 一行空行给财务核对），后面多余的空行全部去掉；
    A4 横向、整张缩到一页（宽 1 页 × 高 1 页）、打印区域 = A1:BK最后一行。返回 (sheet, 改 workbook.xml 的函数)"""
    last = max(last, FIRST - 1)
    row_re = re.compile(r'<row r="(\d+)"[^>]*?(?:/>|>.*?</row>)', re.S)
    sheet = row_re.sub(lambda m: m.group(0) if int(m.group(1)) <= last else '', sheet)
    def unshare(m):   # 留下的行里「共享公式」改成普通公式（共享公式的主格可能在删掉的行里）
        col, r = m.group(1), m.group(2)
        f = FORMULA.get(col) or ('AG#-AV#' if col == 'BJ' else None)
        return m.group(0) if not f else m.group(0).replace(m.group(3), '<f>%s</f>' % f.replace('#', r))
    sheet = re.sub(r'<c r="([A-Z]+)(\d+)"[^>]*?>(<f t="shared"[^>]*?(?:/>|>.*?</f>))', unshare, sheet, flags=re.S)
    def merges(m):
        ms = [x for x in re.findall(r'<mergeCell ref="([^"]+)"/>', m.group(0)) if int(re.sub(r'^[A-Z]+', '', x.split(':')[0])) <= last]
        ms += list(more_merges)
        return '<mergeCells count="%d">%s</mergeCells>' % (len(ms), ''.join('<mergeCell ref="%s"/>' % x for x in ms))
    sheet = re.sub(r'<mergeCells [^>]*>.*?</mergeCells>', merges, sheet, flags=re.S)
    sheet = re.sub(r'<dimension ref="[^"]*"/>', '<dimension ref="A1:BK%d"/>' % last, sheet)
    if 'fitToPage' not in sheet: sheet = re.sub(r'<sheetPr([^>]*)/>', r'<sheetPr\1><pageSetUpPr fitToPage="1"/></sheetPr>', sheet)
    sheet = re.sub(r'<pageMargins [^>]*/>', '<pageMargins left="0.4" right="0.4" top="0.4" bottom="0.4" header="0.2" footer="0.2"/>', sheet)
    sheet = re.sub(r'<pageSetup [^>]*/>', '<pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="1"/>', sheet)
    def wbfix(wb):
        wb = re.sub(r'(<definedName name="_xlnm\._FilterDatabase"[^>]*>Sheet1!\$A\$1:\$BK\$)\d+', r'\g<1>%d' % last, wb)
        wb = re.sub(r'<definedName name="_xlnm\.Print_Area"[^>]*>.*?</definedName>', '', wb)
        pa = '<definedName name="_xlnm.Print_Area" localSheetId="0">Sheet1!$A$1:$BK$%d</definedName>' % last
        return wb.replace('</definedNames>', pa + '</definedNames>') if '</definedNames>' in wb else wb.replace('</sheets>', '</sheets><definedNames>%s</definedNames>' % pa)
    return sheet, wbfix

FORMULA = {'J': 'D#-H#', 'K': 'F#-I#', 'L': 'B#+H#-D#-E#', 'M': 'C#+I#-F#-G#', 'R': 'J#+L#', 'S': 'K#+M#'}
for _t, _r, _n in zip(['T', 'U', 'V', 'W', 'X', 'Y', 'Z', 'AA', 'AB', 'AC', 'AD', 'AE', 'AF'],
                      ['AI', 'AJ', 'AK', 'AL', 'AM', 'AN', 'AO', 'AP', 'AQ', 'AR', 'AS', 'AT', 'AU'],
                      ['AW', 'AX', 'AY', 'AZ', 'BA', 'BB', 'BC', 'BD', 'BE', 'BF', 'BG', 'BH', 'BI']):
    FORMULA[_n] = '%s#-%s#' % (_t, _r)

# ---------------- 简单表格导出 ----------------
def simple_xlsx(sheets):
    """sheets: [(name, title, header[], rows[[...]], widths[])]，宋体、细边框、表头加粗，可直接打印"""
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<fonts count="3"><font><sz val="11"/><name val="宋体"/><charset val="134"/></font><font><b/><sz val="11"/><name val="宋体"/><charset val="134"/></font>'
              '<font><b/><sz val="16"/><name val="宋体"/><charset val="134"/></font></fonts>'
              '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
              '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"/><right style="thin"/><top style="thin"/><bottom style="thin"/><diagonal/></border></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
              '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>'
              '<xf numFmtId="0" fontId="1" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
              '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>'
              '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf></cellXfs>'
              '<cellStyles count="1"><cellStyle name="常规" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
    def cell(ref, v, s):
        if v is None or v == '': return '<c r="%s" s="%d"/>' % (ref, s)
        if isinstance(v, (int, float)) and not isinstance(v, bool): return '<c r="%s" s="%d"><v>%s</v></c>' % (ref, s, _fmt(v))
        return '<c r="%s" s="%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, s, escape(str(v)))
    out = io.BytesIO(); z = zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED)
    ct = ''.join('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % (i + 1) for i in range(len(sheets)))
    z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' + ct + '</Types>')
    z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    z.writestr('xl/workbook.xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' +
               ''.join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (escape(s[0][:31]), i + 1, i + 1) for i, s in enumerate(sheets)) + '</sheets></workbook>')
    z.writestr('xl/_rels/workbook.xml.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
               ''.join('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (i + 1, i + 1) for i in range(len(sheets))) +
               '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>' % (len(sheets) + 1))
    z.writestr('xl/styles.xml', styles)
    for i, sh in enumerate(sheets):
        name, title, header, rws, widths = sh[:5]; extra = sh[5] if len(sh) > 5 else {}
        nc = len(header); x = []; r = 1; mg = []
        if title:
            x.append('<row r="1" ht="28" customHeight="1">%s</row>' % cell('A1', title, 3)); mg.append('A1:%s1' % n2col(nc)); r = 1
        else: r = 0
        for line in extra.get('pre') or []:   # 表头上方的信息行（如 单号/日期/领用人）
            r += 1; x.append('<row r="%d" ht="22" customHeight="1">%s</row>' % (r, cell('A%d' % r, line, 4))); mg.append('A%d:%s%d' % (r, n2col(nc), r))
        r += 1
        x.append('<row r="%d" ht="22" customHeight="1">%s</row>' % (r, ''.join(cell('%s%d' % (n2col(j + 1), r), h, 2) for j, h in enumerate(header))))
        for rw in rws:
            r += 1; x.append('<row r="%d" ht="20" customHeight="1">%s</row>' % (r, ''.join(cell('%s%d' % (n2col(j + 1), r), v, 1) for j, v in enumerate(rw))))
        for line in extra.get('post') or []:  # 表下方（如 签字栏）
            r += 1; x.append('<row r="%d" ht="30" customHeight="1">%s</row>' % (r, cell('A%d' % r, line, 4))); mg.append('A%d:%s%d' % (r, n2col(nc), r))
        merges = ('<mergeCells count="%d">%s</mergeCells>' % (len(mg), ''.join('<mergeCell ref="%s"/>' % m for m in mg))) if mg else ''
        colsx = '<cols>%s</cols>' % ''.join('<col min="%d" max="%d" width="%s" customWidth="1"/>' % (j + 1, j + 1, w) for j, w in enumerate(widths or [14] * nc))
        z.writestr('xl/worksheets/sheet%d.xml' % (i + 1), '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   + colsx + '<sheetData>' + ''.join(x) + '</sheetData>' + merges + '<pageMargins left="0.5" right="0.5" top="0.6" bottom="0.6" header="0.3" footer="0.3"/><pageSetup paperSize="9" orientation="portrait" fitToHeight="0"/></worksheet>')
    z.close(); return out.getvalue()
