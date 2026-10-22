# -*- coding: utf-8 -*-
"""领用出库单：保存即扣库存（出库 kind=领用出库）；可下载/打印；签字后拍照回传，没回传的进待补全"""
import logic
from db import row, rows, now, today
from web import route, ApiError, attach_photos, photos_of, table_result

KIND = '领用出库'
def slip_no(o): return 'LY%s-%04d' % (o['date'].replace('-', ''), o['id'])

def sign_sync(c, oid):
    o = row(c.execute('SELECT * FROM out_orders WHERE id=?', (oid,)).fetchone())
    if not o: return
    key = 'out_sign:%d' % oid
    p = row(c.execute('SELECT * FROM pending WHERE auto_key=? AND deleted_at IS NULL', (key,)).fetchone())
    if o['kind'] != KIND:
        if p and p['status'] == '待补全': c.execute("UPDATE pending SET status='已补全', close_note='自动：已不是领用出库', updated_at=? WHERE id=?", (now(), p['id']))
        return
    signed = 1 if photos_of(c, 'out', oid, 'sign') else 0
    c.execute('UPDATE out_orders SET sign_needed=1, signed=? WHERE id=?', (signed, oid))
    need = not signed and not o['deleted_at']
    if need:
        its = logic.items_of(c, oid)
        what = '领用出库单 %s 未回传签字照片：%s' % (slip_no(o), '、'.join('%s×%g' % (i['product_name'], i['qty']) for i in its[:4]))
        if not p:
            c.execute("INSERT INTO pending(date,taker,what,qty,customer,handler,status,link_type,link_id,auto_key,created_at,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                      (o['date'], o['recipient'], what, '', o['purpose'] or '', o['created_by'], '待补全', 'out', oid, key, now(), '系统'))
        elif p['status'] != '待补全' or p['what'] != what:
            c.execute("UPDATE pending SET status='待补全', what=?, close_note='' WHERE id=?", (what, p['id']))
    elif p and p['status'] == '待补全':
        c.execute("UPDATE pending SET status='已补全', close_note=?, updated_at=? WHERE id=?", ('自动：已回传签字照片' if signed else '自动：出库单已删除', now(), p['id']))

_orig = logic.rebuild_out
def _rebuild_out(c, oid):
    _orig(c, oid); sign_sync(c, oid)
logic.rebuild_out = _rebuild_out          # save_out / 删除 / 恢复 都会走到这里
logic.REBUILD['out'] = _rebuild_out

def sheet(c, oid):
    o = row(c.execute('SELECT * FROM out_orders WHERE id=?', (oid,)).fetchone())
    if not o: raise ApiError('没有这张单', 404)
    if o['kind'] != KIND: raise ApiError('这张不是领用出库单')
    its = logic.items_of(c, oid)
    units = {r[0]: r[1] for r in c.execute('SELECT id, unit FROM products')}
    rs = [[i + 1, it['product_name'], it['qty'], units.get(it['product_id'], ''), it['batch_no'], it['note']] for i, it in enumerate(its)]
    pre = ['单号：%s        日期：%s' % (slip_no(o), o['date']), '领用人：%s        用途：%s' % (o['recipient'] or '', o['purpose'] or '')]
    if o['remark']: pre.append('备注：%s' % o['remark'])
    post = ['领用人签字：________________        库管：%s        日期：________________' % (o['created_by'] or '')]
    return o, ('领用出库单', '领用出库单', ['序号', '物品', '数量', '单位', '批号', '说明'], rs, [6, 30, 9, 7, 12, 22], {'pre': pre, 'post': post})

@route('GET', '/api/out/slip.xlsx')
def api_out_slip(c, q, b, me):
    o, sh = sheet(c, int(q['id']))
    return table_result(q, '领用出库单_%s_%s.xlsx' % (slip_no(o), o['recipient'] or ''), [sh])

@route('POST', '/api/out/sign', 'entry')
def api_out_sign(c, q, b, me):
    oid = int(b['id'])
    if not b.get('photo_ids'): raise ApiError('请拍签字后的单子')
    for pid in b['photo_ids']:
        c.execute("UPDATE photos SET entity='out', entity_id=?, tag='sign' WHERE id=?", (oid, int(pid)))
    from db import audit
    audit(c, me['name'], '修改', 'out', oid, '回传签字照片 %d 张' % len(b['photo_ids']))
    sign_sync(c, oid)
    return {'ok': 1}

def rmk(o):
    xs = [o.get('remark') or ''] + [i.get('note') or '' for i in o.get('items', [])]
    return '；'.join(x.strip() for x in xs if x and x.strip())

@route('GET', '/api/out/lingyong')
def api_out_lingyong(c, q, b, me):
    """领用出库单清单：按人 / 日期 / 是否已回传签字"""
    w = ["o.deleted_at IS NULL", "o.kind=?"]; a = [KIND]
    if q.get('who'): w.append('o.recipient LIKE ?'); a.append('%' + q['who'] + '%')
    if q.get('q'):
        w.append('(o.purpose LIKE ? OR o.remark LIKE ? OR o.recipient LIKE ? OR EXISTS(SELECT 1 FROM out_items i WHERE i.order_id=o.id AND (i.product_name LIKE ? OR i.note LIKE ?)))'); a += ['%' + q['q'] + '%'] * 5
    if q.get('from'): w.append('o.date>=?'); a.append(q['from'])
    if q.get('to'): w.append('o.date<=?'); a.append(q['to'])
    if q.get('sign') == 'todo': w.append('o.signed=0')
    if q.get('sign') == 'done': w.append('o.signed=1')
    os_ = rows(c.execute('SELECT o.* FROM out_orders o WHERE %s ORDER BY o.date DESC, o.id DESC LIMIT 500' % ' AND '.join(w), a))
    for o in os_:
        o['slip_no'] = slip_no(o); o['items'] = logic.items_of(c, o['id']); o['sign_photos'] = photos_of(c, 'out', o['id'], 'sign')
    if q.get('fmt') == 'json' or q.get('xlsx'):
        rs = [[o['date'], o['slip_no'], o['recipient'], o['purpose'], '、'.join('%s×%g' % (i['product_name'], i['qty']) for i in o['items']), rmk(o), '已回传' if o['signed'] else '未回传', o['created_by']] for o in os_]
        return table_result(q, '领用出库单清单_%s.xlsx' % today(), [('领用出库单', '领用出库单清单', ['日期', '单号', '领用人', '用途', '物品', '备注', '签字', '库管'], rs, [11, 17, 10, 16, 36, 24, 8, 8])])
    return {'items': os_, 'people': [r[0] for r in c.execute("SELECT recipient, COUNT(*) n FROM out_orders WHERE kind=? AND deleted_at IS NULL AND recipient<>'' GROUP BY recipient ORDER BY n DESC", (KIND,))]}
