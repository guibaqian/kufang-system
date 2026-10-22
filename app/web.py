# -*- coding: utf-8 -*-
"""路由注册 + 通用小工具（各功能模块共用）"""
from db import rows

class ApiError(Exception):
    def __init__(self, msg, code=400): super().__init__(msg); self.code = code

ROUTES = {}
def route(method, path, perm=None):
    def deco(fn): ROUTES[(method, path)] = (fn, perm); return fn
    return deco

def readb(p):
    with open(p, 'rb') as f: return f.read()

def attach_photos(c, ids, entity, eid, tag='', replace=False):
    if replace and ids is not None:  # 编辑时：去掉的照片解除关联（照片文件保留）
        keep = [int(x) for x in ids] or [0]
        c.execute("UPDATE photos SET entity=?, entity_id=NULL WHERE entity=? AND entity_id=? AND COALESCE(tag,'')<>'sign' AND id NOT IN (%s)" % ','.join('?' * len(keep)), [entity + '_removed', entity, eid] + keep)
    for pid in ids or []:
        c.execute('UPDATE photos SET entity=?, entity_id=?, tag=COALESCE(NULLIF(?,""),tag) WHERE id=?', (entity, eid, tag, int(pid)))

def photos_of(c, entity, eid, tag=None):
    if tag is None:
        return rows(c.execute('SELECT id, path, name, tag FROM photos WHERE entity=? AND entity_id=? AND deleted_at IS NULL ORDER BY id', (entity, eid)))
    return rows(c.execute('SELECT id, path, name, tag FROM photos WHERE entity=? AND entity_id=? AND tag=? AND deleted_at IS NULL ORDER BY id', (entity, eid, tag)))

def table_result(q, filename, sheets):
    """同一份数据：?fmt=json 给打印用（版式与下载一致），否则下载 xlsx。sheets 同 xlsxio.simple_xlsx"""
    if q.get('fmt') == 'json':
        return {'sheets': [{'name': s[0], 'title': s[1], 'header': s[2], 'rows': s[3], 'widths': s[4], 'pre': (s[5] if len(s) > 5 else {}).get('pre', []), 'post': (s[5] if len(s) > 5 else {}).get('post', [])} for s in sheets]}
    import xlsxio
    return ('file', filename, xlsxio.simple_xlsx(sheets))
