"""把下载用的 xlsx（产品出入库情况，原表格式）原样转成 HTML 表格，打印用 —— 打印和下载出自同一份排版：
列宽（隐藏列不出）、行高、合并格、填充色（含主题色 + 深浅）、字体字号粗细、边框、对齐、不显示 0（原表 showZeros=0）、打印区域。"""
import re, io, zipfile, colorsys
from html import escape

def _col(s):
    n = 0
    for ch in s: n = n * 26 + ord(ch) - 64
    return n

def _theme(z):
    try: t = z.read('xl/theme/theme1.xml').decode('utf-8')
    except KeyError: return []
    cs = re.search(r'<a:clrScheme[^>]*>(.*?)</a:clrScheme>', t, re.S).group(1)
    out = []
    for name in ('dk1', 'lt1', 'dk2', 'lt2', 'accent1', 'accent2', 'accent3', 'accent4', 'accent5', 'accent6', 'hlink', 'folHlink'):
        m = re.search(r'<a:%s>(.*?)</a:%s>' % (name, name), cs, re.S); v = '000000'
        if m:
            x = re.search(r'lastClr="([0-9A-Fa-f]{6})"', m.group(1)) or re.search(r'val="([0-9A-Fa-f]{6})"', m.group(1))
            if x: v = x.group(1)
        out.append(v)
    if len(out) >= 4: out[0], out[1], out[2], out[3] = out[1], out[0], out[3], out[2]   # Excel 主题序号：0=lt1 1=dk1 2=lt2 3=dk2
    return out

def _color(attrs, theme, default=None):
    if not attrs: return default
    m = re.search(r'rgb="([0-9A-Fa-f]{8})"', attrs)
    if m: c = m.group(1)[2:]
    else:
        m = re.search(r'theme="(\d+)"', attrs)
        if not m or int(m.group(1)) >= len(theme): return default
        c = theme[int(m.group(1))]
    t = re.search(r'tint="(-?[\d.]+)"', attrs)
    if t:
        tint = float(t.group(1)); r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        l = l * (1 + tint) if tint < 0 else l * (1 - tint) + tint
        r, g, b = colorsys.hls_to_rgb(h, l, s); c = '%02x%02x%02x' % (round(r * 255), round(g * 255), round(b * 255))
    return '#' + c.lower()

def _styles(z, theme):
    st = z.read('xl/styles.xml').decode('utf-8')
    sect = lambda tag: re.search(r'<%s[^>]*>(.*?)</%s>' % (tag, tag), st, re.S).group(1)
    fonts = []
    for f in re.findall(r'<font>(.*?)</font>|<font/>', sect('fonts'), re.S):
        sz = re.search(r'<sz val="([\d.]+)"', f); col = re.search(r'<color ([^>]*)/>', f)
        fonts.append({'sz': float(sz.group(1)) if sz else 11, 'b': '<b/>' in f, 'i': '<i/>' in f, 'color': _color(col.group(1) if col else '', theme, '#000000')})
    fills = []
    for f in re.findall(r'<fill>(.*?)</fill>', sect('fills'), re.S):
        fg = re.search(r'<fgColor ([^>]*)/>', f)
        fills.append(_color(fg.group(1), theme) if 'patternType="solid"' in f and fg else None)
    borders = []
    for b in re.findall(r'<border>(.*?)</border>|<border/>', sect('borders'), re.S):
        d = {}
        for side in ('left', 'right', 'top', 'bottom'):
            m = re.search(r'<%s style="(\w+)"' % side, b)
            if m: d[side] = '1.5px solid #000' if m.group(1) in ('medium', 'thick') else '1px solid #000'
        borders.append(d)
    xfs = []
    for x in re.findall(r'<xf [^>]*/>|<xf [^>]*[^/]>.*?</xf>', sect('cellXfs'), re.S):
        g = lambda k: int((re.search(r' %s="(\d+)"' % k, x) or [0, 0])[1])
        al = re.search(r'<alignment ([^>]*)/>', x) ; al = al.group(1) if al else ''
        h = re.search(r'horizontal="(\w+)"', al); v = re.search(r'vertical="(\w+)"', al)
        xfs.append({'font': fonts[g('fontId')] if g('fontId') < len(fonts) else fonts[0], 'fill': fills[g('fillId')] if g('fillId') < len(fills) else None,
                    'border': borders[g('borderId')] if g('borderId') < len(borders) else {}, 'h': h.group(1) if h else '', 'v': v.group(1) if v else 'bottom', 'wrap': 'wrapText="1"' in al})
    return xfs

def to_html(xlsx, cls='xl'):
    z = zipfile.ZipFile(io.BytesIO(xlsx)); theme = _theme(z); xfs = _styles(z, theme)
    s = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
    sis = []
    if 'xl/sharedStrings.xml' in z.namelist():
        for si in re.findall(r'<si>(.*?)</si>', z.read('xl/sharedStrings.xml').decode('utf-8'), re.S):
            sis.append(''.join(re.findall(r'<t[^>]*>(.*?)</t>', si, re.S)))
    unesc = lambda t: t.replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&apos;', "'").replace('&amp;', '&')
    zeros = 'showZeros="0"' not in s
    dim = re.search(r'<dimension ref="[A-Z]+\d+:([A-Z]+)(\d+)"', s); maxc, maxr = (_col(dim.group(1)), int(dim.group(2))) if dim else (63, 9999)
    dw = float((re.search(r'defaultColWidth="([\d.]+)"', s) or [0, 9])[1]); dh = float((re.search(r'defaultRowHeight="([\d.]+)"', s) or [0, 13.5])[1])
    widths, hidden = {}, set()
    for m in re.finditer(r'<col ([^>]*)/>', s):
        a = m.group(1); lo, hi = int(re.search(r'min="(\d+)"', a).group(1)), int(re.search(r'max="(\d+)"', a).group(1))
        w = float((re.search(r'width="([\d.]+)"', a) or [0, dw])[1])
        for i in range(lo, min(hi, maxc) + 1):
            widths[i] = w
            if 'hidden="1"' in a: hidden.add(i)
    cols = [i for i in range(1, maxc + 1) if i not in hidden]
    px = lambda w: round(w * 7 + 5)   # Excel 列宽（字符）→ 像素
    merges = {}; covered = set()
    for ref in re.findall(r'<mergeCell ref="([A-Z]+)(\d+):([A-Z]+)(\d+)"/>', s):
        c1, r1, c2, r2 = _col(ref[0]), int(ref[1]), _col(ref[2]), int(ref[3])
        merges[(r1, c1)] = (r2, c2)
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                if (r, c) != (r1, c1): covered.add((r, c))
    out = ['<table class="%s" style="border-collapse:collapse;table-layout:fixed;width:%dpx;font-family:宋体,SimSun,\'Songti SC\',\'Noto Serif CJK SC\',serif;font-variant-numeric:tabular-nums;-webkit-print-color-adjust:exact;print-color-adjust:exact">' % (cls, sum(px(widths.get(i, dw)) for i in cols)),
           '<colgroup>' + ''.join('<col style="width:%dpx">' % px(widths.get(i, dw)) for i in cols) + '</colgroup>']
    for m in re.finditer(r'<row r="(\d+)"([^>]*)>(.*?)</row>|<row r="(\d+)"([^>]*)/>', s, re.S):
        r = int(m.group(1) or m.group(4)); ra = m.group(2) or m.group(5) or ''
        if r > maxr: break
        ht = float((re.search(r' ht="([\d.]+)"', ra) or [0, dh])[1]); rs = re.search(r' s="(\d+)"', ra)
        cells = {}
        for cm in re.finditer(r'<c r="([A-Z]+)\d+"([^>]*?)(?:/>|>(.*?)</c>)', m.group(3) or '', re.S):
            c = _col(cm.group(1)); a = cm.group(2); inner = cm.group(3) or ''
            sx = int((re.search(r' s="(\d+)"', a) or [0, rs.group(1) if rs else 0])[1]); t = (re.search(r' t="(\w+)"', a) or [0, ''])[1]
            v = re.search(r'<v>(.*?)</v>', inner, re.S); val = ''
            if t == 's' and v: val = sis[int(v.group(1))]
            elif t == 'inlineStr': val = ''.join(re.findall(r'<t[^>]*>(.*?)</t>', inner, re.S))
            elif v:
                try:
                    f = float(v.group(1)); val = '' if (f == 0 and not zeros) else ('%d' % f if f == int(f) else ('%g' % f))
                except ValueError: val = v.group(1)
            cells[c] = (sx, unesc(val))
        tds = []
        for c in cols:
            if (r, c) in covered: continue
            sx, val = cells.get(c, (int(rs.group(1)) if rs else 0, ''))
            x = xfs[sx] if sx < len(xfs) else xfs[0]
            span = ''
            if (r, c) in merges:
                r2, c2 = merges[(r, c)]; n = sum(1 for i in cols if c <= i <= c2)
                if n == 0: continue
                if n > 1: span += ' colspan="%d"' % n
                if r2 > r: span += ' rowspan="%d"' % (r2 - r + 1)
                bx = xfs[cells.get(c2, (sx, ''))[0]] if c2 != c else x   # 合并格右边框取最右那格
            else: bx = x
            f = x['font']; b = dict(x['border']); b['right'] = bx['border'].get('right', b.get('right'))
            css = ['font-size:%gpt' % f['sz'], 'color:%s' % f['color'], 'text-align:%s' % {'centerContinuous': 'center', 'general': 'left', '': 'left'}.get(x['h'], x['h']),
                   'vertical-align:%s' % {'center': 'middle'}.get(x['v'], x['v']), 'padding:0 2px', 'overflow:hidden', 'white-space:%s' % ('normal' if x['wrap'] else 'nowrap')]
            if f['b']: css.append('font-weight:bold')
            css.append('background:%s' % (x['fill'] or 'transparent'))
            css += ['border-%s:%s' % (k, b.get(k) or 'none') for k in ('left', 'right', 'top', 'bottom')]
            tds.append('<td%s style="%s">%s</td>' % (span, ';'.join(css), escape(val).replace('\n', '<br>')))
        out.append('<tr style="height:%gpt">%s</tr>' % (ht, ''.join(tds)))
    out.append('</table>')
    return ''.join(out)
