# -*- coding: utf-8 -*-
"""共享照片库：手机扫一次码（长会话）可持续上传；电脑加附件时从库里挑。
复用 upq.save_photo；照片先落 entity='lib'，选用后变空实体，保存单据时再 attach。"""
import time, secrets
import upq
from db import rows, row, now, audit
from web import route, ApiError

SESSION_TTL = 30 * 86400   # 30 天；每次上传再续 30 天
MAX_LIB = 300              # 库里最多留这么多张（超了提示清一下）
MAX_PER_SESSION = 2000     # 一个会话累计张数上限（防刷）
EXEMPT = ('/api/lib/session', '/api/lib/photo', '/api/lib/info', '/api/lib/touch', '/api/lib/take')

def ensure(c):
    c.execute('CREATE TABLE IF NOT EXISTS lib_sessions(token TEXT PRIMARY KEY, by TEXT, label TEXT, created_at REAL, expires_at REAL, last_seen REAL, state TEXT DEFAULT "open", n INTEGER DEFAULT 0)')
    upq.ensure(c)

def _sess(c, t, need_open=True):
    ensure(c)
    x = c.execute('SELECT * FROM lib_sessions WHERE token=?', (t or '',)).fetchone()
    if not x: raise ApiError('照片库二维码无效，请在电脑「设置 → 手机与访客二维码」重新生成', 404)
    x = dict(x)
    if need_open:
        if x['state'] != 'open': raise ApiError('这个照片库会话已关闭，请在电脑上重新生成二维码', 410)
        if time.time() > x['expires_at']: raise ApiError('照片库会话已过期（长时间没用），请在电脑上重新扫码', 410)
    return x

def _extend(c, token):
    c.execute('UPDATE lib_sessions SET expires_at=?, last_seen=? WHERE token=? AND state="open"',
              (time.time() + SESSION_TTL, time.time(), token))

@route('POST', '/api/lib/session')
def api_session(c, q, b, me):
    """电脑：取当前有效会话，没有或 force 则新建。扫一次可连用约 30 天。"""
    ensure(c)
    by = str((b or {}).get('by') or '')[:40]
    force = bool((b or {}).get('force'))
    if not force:
        cur = c.execute('SELECT * FROM lib_sessions WHERE state="open" AND expires_at>? ORDER BY created_at DESC LIMIT 1',
                        (time.time() + 3600,)).fetchone()  # 至少还剩 1 小时才复用
        if cur:
            x = dict(cur)
            left = max(0, int(x['expires_at'] - time.time()))
            return {'token': x['token'], 'ttl': left, 'expires_at': x['expires_at'], 'n': x['n'], 'reused': 1}
    # 关掉旧的 open 会话
    c.execute('UPDATE lib_sessions SET state="closed" WHERE state="open"')
    t = secrets.token_urlsafe(16)
    exp = time.time() + SESSION_TTL
    c.execute('INSERT INTO lib_sessions(token,by,label,created_at,expires_at,last_seen,state,n) VALUES(?,?,?,?,?,?,?,0)',
              (t, by, '照片库', time.time(), exp, time.time(), 'open'))
    c.execute('DELETE FROM lib_sessions WHERE expires_at < ?', (time.time() - 90 * 86400,))
    audit(c, by or '电脑', '新增', 'lib', 0, '生成照片库会话（约 30 天有效，手机可持续上传）')
    return {'token': t, 'ttl': SESSION_TTL, 'expires_at': exp, 'n': 0, 'reused': 0}

@route('GET', '/api/lib/info')
def api_info(c, q, b, me):
    x = _sess(c, q.get('t'), need_open=False)
    left = max(0, int(x['expires_at'] - time.time()))
    st = x['state']
    if st == 'open' and not left: st = 'expired'
    n_lib = c.execute("SELECT COUNT(*) FROM photos WHERE entity='lib' AND deleted_at IS NULL").fetchone()[0]
    return {'label': x.get('label') or '照片库', 'left': left, 'n': x['n'], 'state': st, 'lib_n': n_lib, 'max': MAX_LIB}

@route('POST', '/api/lib/touch')
def api_touch(c, q, b, me):
    x = _sess(c, (b or {}).get('t'))
    _extend(c, x['token'])
    left = SESSION_TTL
    return {'ok': 1, 'left': left, 'expires_at': time.time() + left}

@route('POST', '/api/lib/photo')
def api_photo(c, q, b, me):
    x = _sess(c, (b or {}).get('t'))
    if x['n'] >= MAX_PER_SESSION: raise ApiError('这个会话上传太多了，请在电脑上重新生成二维码')
    n_lib = c.execute("SELECT COUNT(*) FROM photos WHERE entity='lib' AND deleted_at IS NULL").fetchone()[0]
    if n_lib >= MAX_LIB: raise ApiError('照片库已满（%d 张），请在电脑加附件时先选用或删掉一些' % MAX_LIB)
    p = upq.save_photo(c, (b or {}).get('data'), (b or {}).get('name') or 'phone.jpg',
                       'lib', None, '', x.get('by') or '手机照片库')
    c.execute('UPDATE lib_sessions SET n=n+1 WHERE token=?', (x['token'],))
    _extend(c, x['token'])
    audit(c, x.get('by') or '手机', '新增', 'photo', p['id'], '照片库上传')
    return p

@route('GET', '/api/lib/list')
def api_list(c, q, b, me):
    ensure(c)
    lim = min(int(q.get('limit') or 120), 300)
    after = q.get('after')
    if after and str(after).isdigit():
        items = rows(c.execute("SELECT id, path, name, created_at, created_by FROM photos WHERE entity='lib' AND deleted_at IS NULL AND id>? ORDER BY id", (int(after),)))
    else:
        items = rows(c.execute("SELECT id, path, name, created_at, created_by FROM photos WHERE entity='lib' AND deleted_at IS NULL ORDER BY id DESC LIMIT ?", (lim,)))
        items = list(reversed(items))
    sess = c.execute('SELECT token, expires_at, n, state FROM lib_sessions WHERE state="open" ORDER BY created_at DESC LIMIT 1').fetchone()
    s = dict(sess) if sess else None
    left = max(0, int(s['expires_at'] - time.time())) if s else 0
    return {'items': items, 'n': len(items),
            'session': {'token': s['token'], 'left': left, 'n': s['n'], 'state': 'expired' if s and s['state'] == 'open' and not left else (s['state'] if s else 'none')} if s else None}

@route('POST', '/api/lib/take')
def api_take(c, q, b, me):
    """电脑从库里选用：把 entity 从 lib 改成空（待挂到单据），返回照片信息。"""
    ensure(c)
    out = []
    for i in (b or {}).get('ids') or []:
        try: pid = int(i)
        except (TypeError, ValueError): continue
        n = c.execute("UPDATE photos SET entity='', entity_id=NULL, tag='' WHERE id=? AND entity='lib' AND deleted_at IS NULL", (pid,)).rowcount
        if n:
            p = row(c.execute('SELECT id, path, name FROM photos WHERE id=?', (pid,)).fetchone())
            if p: out.append(p)
    if out: audit(c, str((b or {}).get('by') or '电脑')[:40], '修改', 'lib', 0, '从照片库选用 %d 张' % len(out))
    return {'items': out, 'n': len(out)}

@route('POST', '/api/lib/delete', 'entry')
def api_delete(c, q, b, me):
    """从照片库删掉（软删），要密码。"""
    from db import soft_delete
    ensure(c)
    n = 0
    for i in (b or {}).get('ids') or []:
        p = row(c.execute("SELECT id FROM photos WHERE id=? AND entity='lib' AND deleted_at IS NULL", (int(i),)).fetchone())
        if p:
            soft_delete(c, 'photo', p['id'], me['name']); n += 1
    if n: audit(c, me['name'], '删除', 'lib', 0, '从照片库删除 %d 张' % n)
    return {'ok': 1, 'n': n}

@route('POST', '/api/lib/close')
def api_close(c, q, b, me):
    ensure(c)
    t = (b or {}).get('t')
    if t:
        x = _sess(c, t, need_open=False)
        if x['state'] == 'open':
            c.execute('UPDATE lib_sessions SET state="closed" WHERE token=?', (x['token'],))
            audit(c, str((b or {}).get('by') or '电脑')[:40], '修改', 'lib', 0, '关闭照片库会话（已传 %d 张）' % x['n'])
    else:
        c.execute('UPDATE lib_sessions SET state="closed" WHERE state="open"')
        audit(c, str((b or {}).get('by') or '电脑')[:40], '修改', 'lib', 0, '关闭全部照片库会话')
    return {'ok': 1}
