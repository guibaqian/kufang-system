"""手机拍照上传（电脑上点「附件 +」→「手机拍照上传」出二维码）。
电脑向主机要一个临时上传码（10 分钟有效，只能往这一个附件位置传照片，不能做别的）；手机扫码打开 /m/up.html#码，
拍照（可多张，手机上先压缩）上传；电脑弹窗每 1.5 秒取一次，照片实时出现；手机点「完成」或电脑关掉弹窗后码作废。全程留痕。"""
import re, os, base64, uuid, datetime, secrets, time
import db
from db import rows, now, audit
from web import route, ApiError

TTL = 600          # 秒
MAX_PHOTOS = 60   # 一个码 10 分钟内可连传多张（手工单多的配送员）
EXEMPT = ('/api/upq/new', '/api/upq/photo', '/api/upq/done', '/api/upq/close')   # 不用密码（和 /api/photo 一样），靠上传码限定范围

def ensure(c):
    c.execute('CREATE TABLE IF NOT EXISTS upload_tokens(token TEXT PRIMARY KEY, label TEXT, entity TEXT, entity_id INTEGER, tag TEXT, by TEXT, created_at REAL, expires_at REAL, state TEXT DEFAULT "open", n INTEGER DEFAULT 0)')

def save_photo(c, data, name='', entity='', entity_id=None, tag='', by='', token=None):
    m = re.match(r'data:(image/[\w.+-]+);base64,(.*)', data or '', re.S)
    if not m: raise ApiError('不是图片')
    raw = base64.b64decode(m.group(2))
    if len(raw) > 15 * 1024 * 1024: raise ApiError('图片太大')
    ext = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}.get(m.group(1), '.jpg')
    sub = datetime.date.today().strftime('%Y%m'); os.makedirs(os.path.join(db.PHOTO_DIR, sub), exist_ok=True)
    rel = '%s/%s%s' % (sub, uuid.uuid4().hex[:16], ext)
    with open(os.path.join(db.PHOTO_DIR, rel), 'wb') as f: f.write(raw)
    cur = c.execute('INSERT INTO photos(entity,entity_id,tag,path,name,size,created_at,created_by) VALUES(?,?,?,?,?,?,?,?)',
                    (entity or '', entity_id, tag or '', rel, name or '', len(raw), now(), by or ''))
    pid = cur.lastrowid
    if entity and entity_id: audit(c, by or '', '新增', 'photo', pid, '照片 → %s #%s' % (entity, entity_id))
    if token: c.execute('INSERT INTO photo_inbox VALUES(?,?,?)', (token, pid, now()))
    return {'id': pid, 'path': rel}

def replace_photo(c, data, path=None, photo_id=None, by=''):
    """用新图覆盖已有照片文件（看大图转 90° 后立刻写入，不另存）。path 或 id 二选一。"""
    m = re.match(r'data:(image/[\w.+-]+);base64,(.*)', data or '', re.S)
    if not m: raise ApiError('不是图片')
    raw = base64.b64decode(m.group(2))
    if len(raw) > 15 * 1024 * 1024: raise ApiError('图片太大')
    if photo_id:
        r = c.execute('SELECT id, path FROM photos WHERE id=? AND deleted_at IS NULL', (int(photo_id),)).fetchone()
    else:
        rel = str(path or '').replace('\\', '/').lstrip('/')
        if rel.startswith('photos/'): rel = rel[7:]
        rel = rel.split('?', 1)[0]
        if not rel or '..' in rel or rel.startswith('/') or ':' in rel:
            raise ApiError('照片路径不对')
        r = c.execute('SELECT id, path FROM photos WHERE path=? AND deleted_at IS NULL ORDER BY id DESC LIMIT 1', (rel,)).fetchone()
    if not r: raise ApiError('没有这张照片', 404)
    r = dict(r) if not isinstance(r, dict) else r
    full = os.path.join(db.PHOTO_DIR, r['path'])
    if not os.path.isfile(full): raise ApiError('照片文件不在了', 404)
    # 原子写：先写临时再替换，避免写一半坏掉
    tmp = full + '.rotating'
    with open(tmp, 'wb') as f: f.write(raw)
    os.replace(tmp, full)
    c.execute('UPDATE photos SET size=? WHERE id=?', (len(raw), r['id']))
    audit(c, by or '', '修改', 'photo', r['id'], '旋转照片并保存')
    return {'id': r['id'], 'path': r['path']}


def _tok(c, t, need_open=True):
    ensure(c)
    x = c.execute('SELECT * FROM upload_tokens WHERE token=?', (t or '',)).fetchone()
    if not x: raise ApiError('二维码无效，请在电脑上重新点「手机拍照上传」', 404)
    x = dict(x) if not isinstance(x, dict) else x
    if need_open:
        if x['state'] != 'open': raise ApiError('这个二维码已用完（电脑上已关掉或已点完成），请在电脑上重新生成', 410)
        if time.time() > x['expires_at']: raise ApiError('二维码已过期（10 分钟有效），请在电脑上重新生成', 410)
    return x

@route('POST', '/api/upq/new')
def api_new(c, q, b, me):
    ensure(c)
    t = secrets.token_urlsafe(12); label = str(b.get('label') or '附件')[:60]; by = str(b.get('by') or '')[:40]
    eid = b.get('entity_id'); eid = int(eid) if str(eid or '').isdigit() else None
    c.execute('INSERT INTO upload_tokens(token,label,entity,entity_id,tag,by,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?)',
              (t, label, str(b.get('entity') or '')[:30], eid, str(b.get('tag') or '')[:30], by, time.time(), time.time() + TTL))
    c.execute('DELETE FROM upload_tokens WHERE expires_at < ?', (time.time() - 7 * 86400,))
    audit(c, by or '电脑', '新增', 'upload', 0, '生成手机拍照上传码：%s（10 分钟有效）' % label)
    return {'token': t, 'ttl': TTL, 'expires_at': time.time() + TTL}

@route('GET', '/api/upq/info')
def api_info(c, q, b, me):
    x = _tok(c, q.get('t'), need_open=False)
    left = max(0, int(x['expires_at'] - time.time()))
    return {'label': x['label'], 'left': left, 'n': x['n'], 'state': 'expired' if x['state'] == 'open' and not left else x['state'], 'max': MAX_PHOTOS}

@route('POST', '/api/upq/photo')
def api_photo(c, q, b, me):
    x = _tok(c, b.get('t'))
    if x['n'] >= MAX_PHOTOS: raise ApiError('一次最多传 %d 张' % MAX_PHOTOS)
    p = save_photo(c, b.get('data'), b.get('name') or 'phone.jpg', x['entity'], x['entity_id'], x['tag'], x['by'] or '手机', token=x['token'])
    c.execute('UPDATE upload_tokens SET n=n+1 WHERE token=?', (x['token'],))
    audit(c, x['by'] or '手机', '新增', 'photo', p['id'], '手机拍照上传 → %s' % x['label'])
    return p

@route('GET', '/api/upq/poll')
def api_poll(c, q, b, me):
    x = _tok(c, q.get('t'), need_open=False)
    items = rows(c.execute('SELECT p.id, p.path FROM photo_inbox i JOIN photos p ON p.id=i.photo_id WHERE i.token=? ORDER BY i.created_at', (x['token'],)))
    left = max(0, int(x['expires_at'] - time.time()))
    return {'items': items, 'state': 'expired' if x['state'] == 'open' and not left else x['state'], 'left': left}

def _close(c, t, state, who):
    x = _tok(c, t, need_open=False)
    if x['state'] == 'open':
        c.execute('UPDATE upload_tokens SET state=? WHERE token=?', (state, x['token']))
        audit(c, who, '修改', 'upload', 0, '手机拍照上传码%s：%s（传了 %d 张）' % ('已完成' if state == 'done' else '已关闭', x['label'], x['n']))
    return {'ok': 1}

@route('POST', '/api/upq/done')
def api_done(c, q, b, me): return _close(c, b.get('t'), 'done', '手机')

@route('POST', '/api/upq/close')
def api_closetok(c, q, b, me): return _close(c, b.get('t'), 'closed', str(b.get('by') or '电脑'))
