"""库存变化记录（全部产品）：库存流水 moves + 盘点调整（stock_counts，单独存的）合在一起按时间列出。
GET /api/moves?from&to&product_id&src&q&limit&offset；/api/moves.xlsx 同一份数据下载 / 打印（fmt=json）。
只筛一个产品时给每条之后的「结存」：从盘点实数往后加减（第一次盘点以前不知道，显示空）。"""
import json, datetime
import logic
from db import rows, row
from web import route, table_result

SRC = [('daily', '交接表'),   # 「产品出入库情况」上直接录的（不是交接表来的）显示「出入库情况」，筛选算在一起
       ('out', '出库'), ('xout', '换出'), ('xin', '换入'), ('arrival', '到货'), ('loan', '借用'), ('return', '归还'), ('count', '盘点')]
SRC_CN = dict(SRC)

def _all(c, pid=None):
    """全部变化（时间先后）：[{date, ts, product_id, src, src_id, entity, qty, batch_no, label, kind}]"""
    w, a = '', []
    if pid: w, a = ' WHERE m.product_id=?', [pid]
    out = []
    daily_paper = {r[0] for r in c.execute("SELECT id FROM daily_entries WHERE legacy LIKE 'paper:%'")}
    for m in rows(c.execute('SELECT m.* FROM moves m' + w, a)):
        src = m['src']; lab = m['label'] or ''; ent = m['src']
        if src == 'loan' and m['qty'] > 0: src = 'return'
        # 换货：同一张出库单两边流水都挂 src=out；正数=换入，负数且标签含换货=换出（筛选「出库」仍含换出）
        if src == 'out' and m['qty'] > 0: src = 'xin'
        elif src == 'out' and '换货' in lab: src = 'xout'
        if src == 'daily' or ent == 'daily':
            lab = lab.replace('产品出入库情况 ', '配送员 ', 1)
        out.append({'srcn': '出入库情况' if ent == 'daily' and m['src_id'] not in daily_paper else None,'date': m['date'], 'ts': m['ts'] or 0, 'product_id': m['product_id'], 'src': src, 'entity': ent, 'src_id': m['src_id'],
                    'qty': m['qty'], 'batch_no': m['batch_no'] or '', 'label': lab})
    w2, a2 = ' AND product_id=?' if pid else '', [pid] if pid else []
    for k in rows(c.execute('SELECT * FROM stock_counts WHERE deleted_at IS NULL' + w2, a2)):
        out.append({'date': k['date'], 'ts': k['created_at'] or 0, 'product_id': k['product_id'], 'src': 'count', 'entity': 'count', 'src_id': k['id'],
                    'qty': k['diff'] if k['diff'] is not None else None, 'batch_no': k['batch_no'] or '', 'count_qty': k['qty'],
                    'label': '盘点实数 %g' % k['qty']
                             + ('（当时系统数 %g）' % k['computed_before'] if k['computed_before'] is not None else '（以前不知道库存）')
                             + (' ' + k['note'] if k['note'] else '') + (' ' + (k['created_by'] or '') if k['created_by'] else '')})
    out.sort(key=lambda x: (x['date'], x['ts'], 0 if x['src'] != 'count' else 1))
    return out

def _balance(items):
    """一个产品：每条之后的结存（整产品；批次盘点不当锚点）。第一次盘点以前 None"""
    bal = None
    for x in items:
        if x['src'] == 'count' and not x['batch_no']: bal = x['count_qty']
        elif bal is not None and x['src'] != 'count': bal = round(bal + x['qty'], 3)
        x['bal'] = bal

def query(c, q):
    pid = int(q['product_id']) if q.get('product_id') else None
    items = _all(c, pid)
    if pid: _balance(items)
    t = datetime.date.today()
    fr = q.get('from') if q.get('from') is not None else t.replace(day=1).isoformat()
    to = q.get('to') or ''
    ps = {p['id']: p for p in rows(c.execute('SELECT id, name, spec, unit FROM products'))}
    kw = (q.get('q') or '').strip().lower(); src = q.get('src') or ''
    # 只是不显示（结存上面已经算好）。daily=1 临时/本页强制显示；hide_daily=1 本页强制隐藏；都不传则跟设置
    if q.get('daily') == '1': want_hide = False
    elif q.get('hide_daily') == '1': want_hide = True
    else: want_hide = not logic.settings(c).get('moves_show_daily', True)
    hide = want_hide and src != 'daily'
    res = []; hidden = 0
    for x in items:
        if fr and x['date'] < fr: continue
        if to and x['date'] > to: continue
        if src and x['src'] != src: continue
        p = ps.get(x['product_id']) or {'name': '（已删除的产品）', 'spec': '', 'unit': ''}
        x['product'] = logic.product_label(p) if p.get('id') else p['name']; x['unit'] = p.get('unit') or ''
        x['src_cn'] = x.get('srcn') or SRC_CN.get(x['src'], x['src'])
        if kw and kw not in (x['product'] + ' ' + x['label'] + ' ' + x['batch_no'] + ' ' + x['src_cn']).lower(): continue
        if hide and x['src'] == 'daily': hidden += 1; continue
        res.append(x)
    res.reverse()   # 新的在上面
    return res, fr, to, hidden

@route('GET', '/api/moves')
def api_moves(c, q, b, me):
    res, fr, to, hidden = query(c, q)
    lim = min(int(q.get('limit') or 200), 2000); off = int(q.get('offset') or 0)
    inn = sum(x['qty'] for x in res if x['src'] != 'count' and (x['qty'] or 0) > 0); outq = sum(x['qty'] for x in res if x['src'] != 'count' and (x['qty'] or 0) < 0)
    adj = sum(x['qty'] or 0 for x in res if x['src'] == 'count')
    return {'items': res[off:off + lim], 'total': len(res), 'offset': off, 'limit': lim, 'from': fr, 'to': to,
            'sum': {'in': round(inn, 3), 'out': round(outq, 3), 'adj': round(adj, 3)}, 'single': bool(q.get('product_id')), 'srcs': SRC, 'hidden_daily': hidden}

@route('GET', '/api/moves.xlsx')
def api_moves_xlsx(c, q, b, me):
    res, fr, to, hidden = query(c, q); single = bool(q.get('product_id'))
    hd = ['日期', '产品', '来源', '说明', '批号', '数量'] + (['结存'] if single else [])
    rs = [[x['date'], x['product'], x['src_cn'], x['label'], x['batch_no'], x['qty'] if x['qty'] is not None else ''] + ([x['bal'] if x.get('bal') is not None else ''] if single else []) for x in res[:20000]]
    rng = '%s 至 %s' % (fr or '最早', to or '今天')
    ttl = '库存变化记录（%s）' % rng + ('　' + res[0]['product'] if single and res else '')
    post = ['已隐藏交接表批量配送 %d 条' % hidden] if hidden else []
    return table_result(q, '库存变化记录_%s.xlsx' % (fr or 'all'), [('库存变化记录', ttl, hd, rs, [11, 26, 8, 44, 12, 9] + ([9] if single else []), {'post': post})])
