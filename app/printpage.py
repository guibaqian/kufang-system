# -*- coding: utf-8 -*-
"""打印页：出库单/入库单可编辑模板 + data/print_files 上传区。
模板进 settings.print_templates（经 /api/settings/save 审计）。
上传文件只写 data/print_files/ + index.json，不碰 warehouse.db 业务表。"""
import os, json, re, uuid, base64, mimetypes, time
import db
from db import now, audit
from web import route, ApiError

PRINT_DIR = os.path.join(db.DATA, 'print_files')
INDEX = os.path.join(PRINT_DIR, 'index.json')
MAX_BYTES = 25 * 1024 * 1024
ALLOWED_EXT = {
    '.pdf', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp',
    '.xlsx', '.xls', '.docx', '.doc', '.csv', '.txt', '.rtf',
}

# 默认模板（字段尽量全、可不填；公司可改标签/显隐；默认布局分区整齐）
DEFAULT_TEMPLATES = {
    'out': {
        'key': 'out',
        'title': '出库单',
        'company': '',  # 空 = 用 settings.print.company
        'fields': {
            'date': {'label': '日期', 'show': True},
            'party': {'label': '客户/单位', 'show': True},
            'dept': {'label': '部门', 'show': True},
            'picker': {'label': '取货人', 'show': True},
            'phone': {'label': '电话', 'show': True},
            'purpose': {'label': '用途', 'show': True},
            'dest': {'label': '送达地点', 'show': True},
            'leader': {'label': '批准领导', 'show': True},
            'handler': {'label': '经办人', 'show': True},
            'contact': {'label': '联系人', 'show': True},
            'out_no': {'label': '单号', 'show': False},
            'remark': {'label': '备注', 'show': True},
        },
        'line_cols': [
            {'key': 'name', 'label': '产品名称', 'show': True},
            {'key': 'spec', 'label': '规格', 'show': True},
            {'key': 'qty', 'label': '数量', 'show': True},
            {'key': 'unit', 'label': '单位', 'show': True},
            {'key': 'batch', 'label': '批号', 'show': True},
        ],
        'show_lines': True,
        'show_remark_area': True,
        'show_sign_area': True,
        'blank_rows': 5,
    },
    'in': {
        'key': 'in',
        'title': '入库单',
        'company': '',
        'fields': {
            'date': {'label': '日期', 'show': True},
            'party': {'label': '送来处/供货方', 'show': True},
            'dept': {'label': '部门', 'show': True},
            'handler': {'label': '经办人', 'show': True},
            'phone': {'label': '电话', 'show': True},
            'receiver': {'label': '收货人', 'show': True},
            'location': {'label': '存放位置', 'show': True},
            'contact': {'label': '来方联系人', 'show': False},
            'in_no': {'label': '单号', 'show': False},
            'remark': {'label': '备注', 'show': True},
        },
        'line_cols': [
            {'key': 'name', 'label': '产品名称', 'show': True},
            {'key': 'spec', 'label': '规格', 'show': True},
            {'key': 'qty', 'label': '数量', 'show': True},
            {'key': 'unit', 'label': '单位', 'show': True},
            {'key': 'batch', 'label': '批号', 'show': True},
        ],
        'show_lines': True,
        'show_remark_area': True,
        'show_sign_area': True,
        'blank_rows': 5,
    },
}

# 录入/打印表头分区顺序（不含 remark；备注单独区）
FIELD_GROUPS = {
    'out': [
        ('基本信息', ['date', 'party', 'dept', 'handler', 'out_no']),
        ('取货与送达', ['picker', 'phone', 'contact', 'dest', 'purpose', 'leader']),
    ],
    'in': [
        ('基本信息', ['date', 'party', 'dept', 'handler', 'in_no']),
        ('收货信息', ['receiver', 'phone', 'contact', 'location']),
    ],
}


def ensure_dir():
    os.makedirs(PRINT_DIR, exist_ok=True)
    if not os.path.isfile(INDEX):
        with open(INDEX, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False)


def _write_index(items):
    os.makedirs(PRINT_DIR, exist_ok=True)
    tmp = INDEX + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.replace(tmp, INDEX)


def _read_index():
    ensure_dir()
    try:
        with open(INDEX, encoding='utf-8') as f:
            return json.load(f) or []
    except Exception:
        return []


def merge_templates(saved):
    """把已存模板合并到默认上（只认 out/in）；默认新增字段会补上。"""
    out = {}
    saved = saved or {}
    for k, base in DEFAULT_TEMPLATES.items():
        cur = {
            'key': base['key'],
            'title': base['title'],
            'company': base.get('company') or '',
            'fields': {fk: dict(fv) for fk, fv in base['fields'].items()},
            'line_cols': [dict(c) for c in base['line_cols']],
            'show_lines': bool(base.get('show_lines', True)),
            'show_remark_area': bool(base.get('show_remark_area', True)),
            'show_sign_area': bool(base.get('show_sign_area', True)),
            'blank_rows': int(base.get('blank_rows') or 5),
        }
        s = saved.get(k) if isinstance(saved.get(k), dict) else {}
        if not s:
            out[k] = cur
            continue
        if 'title' in s and str(s['title']).strip():
            cur['title'] = str(s['title']).strip()[:40]
        if 'company' in s:
            cur['company'] = str(s.get('company') or '')[:80]
        if isinstance(s.get('fields'), dict):
            for fk, fv in s['fields'].items():
                if fk not in cur['fields'] or not isinstance(fv, dict):
                    continue
                nf = dict(cur['fields'][fk])
                if 'label' in fv and str(fv['label']).strip():
                    nf['label'] = str(fv['label']).strip()[:30]
                if 'show' in fv:
                    nf['show'] = bool(fv['show'])
                cur['fields'][fk] = nf
        if isinstance(s.get('line_cols'), list) and s['line_cols']:
            by = {c['key']: c for c in cur['line_cols']}
            cols = []
            for c in s['line_cols']:
                if not isinstance(c, dict) or c.get('key') not in by:
                    continue
                base_c = dict(by[c['key']])
                if 'label' in c and str(c['label']).strip():
                    base_c['label'] = str(c['label']).strip()[:30]
                if 'show' in c:
                    base_c['show'] = bool(c['show'])
                cols.append(base_c)
            seen = {c['key'] for c in cols}
            for c in cur['line_cols']:
                if c['key'] not in seen:
                    cols.append(c)
            cur['line_cols'] = cols
        if 'show_lines' in s:
            cur['show_lines'] = bool(s['show_lines'])
        if 'show_remark_area' in s:
            cur['show_remark_area'] = bool(s['show_remark_area'])
        if 'show_sign_area' in s:
            cur['show_sign_area'] = bool(s['show_sign_area'])
        if 'blank_rows' in s:
            try:
                cur['blank_rows'] = max(1, min(20, int(s['blank_rows'])))
            except Exception:
                pass
        out[k] = cur
    return out


def clean_templates(d):
    """供 settings/save 写入前清洗。"""
    return merge_templates(d if isinstance(d, dict) else {})


def _safe_name(name):
    name = os.path.basename(str(name or 'file')).strip() or 'file'
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', name)[:120]
    return name or 'file'


@route('GET', '/api/print/templates')
def api_templates(c, q, b, me):
    import logic
    s = logic.settings(c)
    t = merge_templates(s.get('print_templates'))
    co = (s.get('print') or {}).get('company') or ''
    return {'templates': t, 'company_default': co, 'field_groups': FIELD_GROUPS}


@route('GET', '/api/print/files')
def api_files_list(c, q, b, me):
    items = _read_index()
    items = sorted(items, key=lambda x: x.get('uploaded_at') or 0, reverse=True)
    return {'items': items}


@route('POST', '/api/print/files/upload', 'entry')
def api_files_upload(c, q, b, me):
    """上传：JSON {name, data: dataURL 或 base64}。存 data/print_files，index.json；审计；不写业务表。"""
    ensure_dir()
    name = _safe_name(b.get('name') or 'file')
    root, ext = os.path.splitext(name)
    ext = ext.lower()
    if ext not in ALLOWED_EXT:
        raise ApiError('不支持的格式（可用 pdf / 图片 / xlsx / docx / csv / txt 等）')
    data = b.get('data') or ''
    raw = None
    if isinstance(data, str) and data.startswith('data:'):
        m = re.match(r'data:([^;]+);base64,(.*)', data, re.S)
        if not m:
            raise ApiError('文件内容不对')
        raw = base64.b64decode(m.group(2))
    elif isinstance(data, str) and data:
        try:
            raw = base64.b64decode(data)
        except Exception:
            raise ApiError('文件内容不对')
    elif b.get('_raw'):
        raw = b['_raw']
        if q.get('name'):
            name = _safe_name(q.get('name'))
            root, ext = os.path.splitext(name)
            ext = ext.lower()
            if ext not in ALLOWED_EXT:
                raise ApiError('不支持的格式')
    if not raw:
        raise ApiError('没有文件内容')
    if len(raw) > MAX_BYTES:
        raise ApiError('文件太大（上限 25MB）')
    fid = uuid.uuid4().hex[:16]
    stored = fid + ext
    path = os.path.join(PRINT_DIR, stored)
    with open(path, 'wb') as f:
        f.write(raw)
    item = {
        'id': fid,
        'name': name,
        'stored': stored,
        'size': len(raw),
        'ext': ext,
        'uploaded_at': now(),
        'by': (me or {}).get('name') or '',
    }
    items = _read_index()
    items.append(item)
    _write_index(items)
    audit(c, (me or {}).get('name') or '', '新增', 'settings', 0, '打印页上传文件：%s（%d 字节）' % (name, len(raw)))
    return item


@route('POST', '/api/print/files/delete', 'entry')
def api_files_delete(c, q, b, me):
    ensure_dir()
    fid = str(b.get('id') or '').strip()
    if not fid or not re.fullmatch(r'[0-9a-f]{8,32}', fid):
        raise ApiError('没有这个文件')
    items = _read_index()
    hit = next((x for x in items if x.get('id') == fid), None)
    if not hit:
        raise ApiError('没有这个文件', 404)
    stored = hit.get('stored') or ''
    if stored and '..' not in stored and '/' not in stored and '\\' not in stored:
        p = os.path.join(PRINT_DIR, stored)
        if os.path.isfile(p):
            try:
                os.remove(p)
            except Exception:
                pass
    items = [x for x in items if x.get('id') != fid]
    _write_index(items)
    audit(c, (me or {}).get('name') or '', '删除', 'settings', 0, '打印页删除文件：%s' % (hit.get('name') or fid))
    return {'ok': 1}


@route('GET', '/api/print/files/one')
def api_files_one(c, q, b, me):
    """下载/打开：返回 file 元组。"""
    ensure_dir()
    fid = str(q.get('id') or '').strip()
    items = _read_index()
    hit = next((x for x in items if x.get('id') == fid), None)
    if not hit:
        raise ApiError('没有这个文件', 404)
    stored = hit.get('stored') or ''
    if not stored or '..' in stored or '/' in stored or '\\' in stored:
        raise ApiError('文件路径不对')
    p = os.path.join(PRINT_DIR, stored)
    if not os.path.isfile(p):
        raise ApiError('文件不在了', 404)
    from web import readb
    return ('file', hit.get('name') or stored, readb(p))


def serve_path(rel):
    """供 server 静态路由：/print_files/<stored>。返回绝对路径或 None。"""
    ensure_dir()
    rel = (rel or '').replace('\\', '/').lstrip('/')
    if not rel or '..' in rel or rel.startswith('/') or ':' in rel:
        return None
    p = os.path.normpath(os.path.join(PRINT_DIR, rel))
    if not p.startswith(os.path.normpath(PRINT_DIR)) or not os.path.isfile(p):
        return None
    return p
