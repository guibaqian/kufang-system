# -*- coding: utf-8 -*-
"""称重计量单（照搬 v82）：净重自动算、流水号自动 +1、「下一张」同车续卸；下载 = 原 Word 模板填值；可登记到液氧表"""
import os, re, io, json, zipfile, datetime
import db
from db import row, rows, now, today, save_row, soft_delete
from web import route, ApiError, readb, table_result

TPL = os.path.join(db.BASE, 'templates', '称重计量单.docx')
KEYS = ['TIME', 'SN', 'PLATE', 'GROSS', 'GOODS', 'TARE', 'SENDER', 'NET', 'RECV', 'GT', 'DRIVER', 'TT', 'OPER', 'NOTE']
FIRST_SN = 'CT20260100110'

def next_sn(sn):
    m = re.match(r'^(.*?)(\d+)$', sn or '')
    if not m: return sn or ''
    return m.group(1) + str(int(m.group(2)) + 1).zfill(len(m.group(2)))

def dt(v):
    """模板里的写法：2026-10-18  11:36:00（日期和时间之间两个空格）"""
    if not v: return ''
    m = re.match(r'^(\d{4}-\d{2}-\d{2})[T ]+(\d{2}:\d{2})(?::(\d{2}))?', str(v))
    return '%s  %s:%s' % (m.group(1), m.group(2), m.group(3) or '00') if m else str(v)

def fnum(v):
    try: return float(v)
    except (TypeError, ValueError): return None
def gnum(v):
    if v is None or v == '': return ''
    v = float(v); return str(int(v)) if v.is_integer() else ('%.2f' % v).rstrip('0').rstrip('.')
def net_of(g, t):
    g, t = fnum(g), fnum(t)
    return round(g - t, 2) if g is not None and t is not None else None

def full(s):
    d = json.loads(s.get('data') or '{}')
    return {'id': s['id'], 'sn': s['serial'], 'time': d.get('time') or s['date'], 'plate': s['car_no'], 'goods': d.get('goods', '液氧'), 'sender': d.get('sender', ''),
            'recv': d.get('recv', ''), 'gross': s['gross'], 'tare': s['tare'], 'net': s['net'], 'gt': s['gross_time'], 'tt': s['tare_time'],
            'driver': d.get('driver', ''), 'oper': d.get('oper', ''), 'note': d.get('note', ''), 'used_at': s.get('used_at'), 'lox_row': s.get('lox_row'),
            'created_by': s.get('created_by'), 'created_at': s.get('created_at'), 'deleted_at': s.get('deleted_at')}

def values(s):
    return {'TIME': dt(s['time']), 'SN': s['sn'] or '', 'PLATE': s['plate'] or '', 'GROSS': gnum(s['gross']), 'GOODS': s['goods'] or '', 'TARE': gnum(s['tare']),
            'SENDER': s['sender'] or '', 'NET': gnum(net_of(s['gross'], s['tare'])), 'RECV': s['recv'] or '', 'GT': dt(s['gt']), 'DRIVER': s['driver'] or '',
            'TT': dt(s['tt']), 'OPER': s['oper'] or '', 'NOTE': s['note'] or ''}

def docx(s):
    src = zipfile.ZipFile(io.BytesIO(readb(TPL)))
    xml = src.read('word/document.xml').decode('utf-8')
    val = values(s)
    esc = lambda v: str(v).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    # 一个值在模板里分成几段（每段保留原来的字体）：{{键.序号.字数}}，按字数切，最后一段放剩下的
    segs = {}
    for k, i, n in re.findall(r'\{\{(\w+)\.(\d+)\.(\d+)\}\}', xml): segs.setdefault(k, {})[int(i)] = int(n)
    def rep(m):
        k, i = m.group(1), int(m.group(2)); v = str(val.get(k, '')); L = segs[k]
        st = sum(L[q] for q in range(i))
        return esc(v[st:] if i == len(L) - 1 else v[st:st + L[i]])
    xml = re.sub(r'\{\{(\w+)\.(\d+)\.(\d+)\}\}', rep, xml)
    for k in KEYS: xml = xml.replace('{{%s}}' % k, esc(val[k]))
    out = io.BytesIO(); z = zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED)
    for it in src.infolist(): z.writestr(it, xml.encode('utf-8') if it.filename == 'word/document.xml' else src.read(it.filename))
    z.close(); return out.getvalue()

def last_sn(c):
    r = c.execute("SELECT serial FROM weigh_slips WHERE deleted_at IS NULL AND serial<>'' ORDER BY id DESC LIMIT 1").fetchone()
    return r[0] if r else FIRST_SN

def nowdt(): return datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

@route('GET', '/api/slips')
def api_slips(c, q, b, me):
    w = ['deleted_at IS %s' % ('NOT NULL' if q.get('deleted') == '1' else 'NULL')]; a = []
    if q.get('unused') == '1': w.append('used_at IS NULL')
    if q.get('q'): w.append('(serial LIKE ? OR car_no LIKE ? OR data LIKE ?)'); a += ['%' + q['q'] + '%'] * 3
    if q.get('from'): w.append('date>=?'); a.append(q['from'])
    if q.get('to'): w.append('date<=?'); a.append(q['to'] + 'T99')
    items = [full(s) for s in rows(c.execute('SELECT * FROM weigh_slips WHERE %s ORDER BY date DESC, id DESC LIMIT 500' % ' AND '.join(w), a))]
    nxt = next_sn(last_sn(c))
    return {'items': items, 'next_sn': nxt, 'blank': {'time': nowdt(), 'sn': nxt, 'plate': '', 'goods': '液氧', 'sender': '', 'recv': '', 'gross': '', 'tare': '', 'gt': '', 'tt': nowdt(), 'driver': '', 'oper': '', 'note': ''},
            'plates': [r[0] for r in c.execute("SELECT car_no, COUNT(*) n FROM weigh_slips WHERE car_no<>'' GROUP BY car_no ORDER BY n DESC LIMIT 30")]}

@route('GET', '/api/slip/one')
def api_slip_one(c, q, b, me):
    s = row(c.execute('SELECT * FROM weigh_slips WHERE id=?', (int(q['id']),)).fetchone())
    if not s: raise ApiError('没有这张称重单', 404)
    o = full(s); o['values'] = values(o)
    o['audit'] = rows(c.execute("SELECT ts,person,action,summary FROM audit WHERE entity='slip' AND entity_id=? ORDER BY ts", (s['id'],)))
    return o

@route('POST', '/api/slip/save', 'entry')
def api_slip_save(c, q, b, me):
    f = b['data']
    if not (f.get('plate') or '').strip(): raise ApiError('请填车号')
    g, t = fnum(f.get('gross')), fnum(f.get('tare'))
    if g is None or g <= 0 or t is None or t < 0: raise ApiError('请填毛重和皮重')
    net = net_of(g, t)
    if net <= 0: raise ApiError('净重小于等于0，请检查毛重/皮重')
    sn = (f.get('sn') or '').strip() or next_sn(last_sn(c))
    dup = c.execute('SELECT id FROM weigh_slips WHERE serial=? AND deleted_at IS NULL AND id<>?', (sn, int(f.get('id') or 0))).fetchone()
    if dup and not b.get('force'): raise ApiError('流水号 %s 已经用过' % sn, 409)
    d = {'serial': sn, 'date': f.get('time') or nowdt(), 'car_no': f['plate'].strip(), 'gross': g, 'tare': t, 'net': net, 'gross_time': f.get('gt') or '', 'tare_time': f.get('tt') or '',
         'data': json.dumps({k: f.get(k, '') for k in ('time', 'goods', 'sender', 'recv', 'driver', 'oper', 'note')}, ensure_ascii=False)}
    if f.get('id'): d['id'] = int(f['id'])
    sid = save_row(c, 'slip', d, me['name'], None if d.get('id') else '称重单 %s %s 净重 %s' % (sn, d['car_no'], gnum(net)))
    return {'id': sid, 'sn': sn, 'net': net}

@route('POST', '/api/slip/delete', 'delete')
def api_slip_delete(c, q, b, me): soft_delete(c, 'slip', int(b['id']), me['name']); return {'ok': 1}

@route('POST', '/api/slip/unuse', 'entry')
def api_slip_unuse(c, q, b, me):
    c.execute('UPDATE weigh_slips SET used_at=NULL WHERE id=?', (int(b['id']),)); return {'ok': 1}

@route('GET', '/api/slip.docx')
def api_slip_docx(c, q, b, me):
    s = row(c.execute('SELECT * FROM weigh_slips WHERE id=?', (int(q['id']),)).fetchone())
    if not s: raise ApiError('没有这张称重单', 404)
    o = full(s)
    return ('file', '称重计量单_%s_%s.docx' % (o['sn'] or '', o['plate'] or ''), docx(o))

@route('GET', '/api/slips.xlsx')
def api_slips_xlsx(c, q, b, me):
    its = api_slips(c, q, b, me)['items']
    rs = [[dt(s['time']), s['sn'], s['plate'], s['goods'], s['sender'], s['recv'], s['gross'], s['tare'], s['net'], dt(s['gt']), dt(s['tt']), s['driver'], s['oper'], s['note'], '已登记' if s['used_at'] else '未登记'] for s in its]
    return table_result(q, '称重单_%s.xlsx' % today(), [('称重单', '称重单', ['时间', '流水号', '车号', '货名', '发货单位', '收货单位', '毛重', '皮重', '净重', '毛重时间', '空重时间', '司机', '过磅员', '备注', '液氧表'], rs,
                                                    [19, 15, 11, 7, 12, 12, 8, 8, 8, 19, 19, 8, 8, 14, 8])])
