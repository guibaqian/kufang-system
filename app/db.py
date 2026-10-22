# -*- coding: utf-8 -*-
"""数据库：SQLite 表结构（覆盖整份需求清单）+ 留痕/软删除通用函数"""
import sqlite3, json, os, time, hashlib, threading, datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get('WH_DATA') or os.path.join(BASE, 'data')
DB_PATH = os.path.join(DATA, 'warehouse.db')
PHOTO_DIR = os.path.join(DATA, 'photos')
WRITE_LOCK = threading.RLock()

AUD = "created_at REAL, created_by TEXT, updated_at REAL, updated_by TEXT, deleted_at REAL, deleted_by TEXT"
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
-- 经办人（PIN 即身份；权限按人设置）
CREATE TABLE IF NOT EXISTS people(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, pin_hash TEXT, role TEXT DEFAULT '录入',
  perms TEXT DEFAULT '{{}}', active INTEGER DEFAULT 1, sort INTEGER DEFAULT 0, {AUD});
-- 配送员 / 点瓶点位（建行等）
CREATE TABLE IF NOT EXISTS couriers(id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT DEFAULT '配送员', phone TEXT DEFAULT '',
  remark TEXT DEFAULT '', active INTEGER DEFAULT 1, sort INTEGER DEFAULT 0, {AUD});
-- 产品（分类含「工程材料」；temp_name=暂用叫法；batch_managed=批次管理）
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT NOT NULL, spec TEXT DEFAULT '', category TEXT DEFAULT '其他',
  unit TEXT DEFAULT '个', batch_managed INTEGER DEFAULT 0, temp_name INTEGER DEFAULT 0, location TEXT DEFAULT '', approx_qty TEXT DEFAULT '',
  remark TEXT DEFAULT '', u8_wh TEXT DEFAULT '', u8_code TEXT DEFAULT '', aliases TEXT DEFAULT '[]', legacy_ids TEXT DEFAULT '[]', sort INTEGER DEFAULT 0, merged_into INTEGER, {AUD});
-- U8 账面（参考，不是实际库存）：同一编码可在多个 U8 库出现；match 自动匹配/待确认/新产品/已确认/不对应
CREATE TABLE IF NOT EXISTS u8_items(id INTEGER PRIMARY KEY, wh TEXT NOT NULL, code TEXT NOT NULL, name TEXT DEFAULT '', spec TEXT DEFAULT '', unit TEXT DEFAULT '',
  qty REAL, product_id INTEGER, suggest_id INTEGER, match TEXT DEFAULT '', note TEXT DEFAULT '', as_of TEXT DEFAULT '', {AUD}, UNIQUE(wh, code));
CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY, name TEXT NOT NULL, contact TEXT DEFAULT '', phone TEXT DEFAULT '',
  remark TEXT DEFAULT '', last_date TEXT DEFAULT '', uses INTEGER DEFAULT 0, {AUD});
-- 出库单（单笔/批量/客户自提/厂内自用/领用出库…）；source=单据来源 app手工单/U8单/无单
CREATE TABLE IF NOT EXISTS out_orders(id INTEGER PRIMARY KEY, date TEXT NOT NULL, kind TEXT NOT NULL, source TEXT DEFAULT '', u8_no TEXT DEFAULT '', u8_type TEXT DEFAULT '',
  customer TEXT DEFAULT '', contact TEXT DEFAULT '', phone TEXT DEFAULT '', salesperson TEXT DEFAULT '', courier TEXT DEFAULT '',
  recipient TEXT DEFAULT '', purpose TEXT DEFAULT '', remark TEXT DEFAULT '', mode TEXT DEFAULT 'single', batch_key TEXT DEFAULT '',
  signed INTEGER DEFAULT 0, legacy_id TEXT DEFAULT '', legacy_subtype TEXT DEFAULT '', {AUD});
CREATE TABLE IF NOT EXISTS out_items(id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL, product_id INTEGER, product_name TEXT DEFAULT '',
  qty REAL NOT NULL, batch_no TEXT DEFAULT '', note TEXT DEFAULT '', side TEXT DEFAULT 'out');  -- out=发出/换出；in=收回/换入（换货）
CREATE INDEX IF NOT EXISTS ix_out_items ON out_items(order_id);
-- 到货（= 报表「库存及到货总数」）；kind 到货/其他入库；u8_status 待入U8/已入U8/不入U8
CREATE TABLE IF NOT EXISTS arrivals(id INTEGER PRIMARY KEY, date TEXT NOT NULL, kind TEXT DEFAULT '到货', name TEXT DEFAULT '', spec TEXT DEFAULT '',
  unit TEXT DEFAULT '', qty REAL DEFAULT 0, dest TEXT DEFAULT '', remark TEXT DEFAULT '', u8_status TEXT DEFAULT '待入U8', inv_code TEXT DEFAULT '',
  receipt_no TEXT DEFAULT '', taken_note TEXT DEFAULT '', product_id INTEGER, batch_no TEXT DEFAULT '', prod_date TEXT DEFAULT '', expiry TEXT DEFAULT '',
  supplier TEXT DEFAULT '', u8_at REAL, sheet_row INTEGER, legacy_id TEXT DEFAULT '', {AUD});
CREATE TABLE IF NOT EXISTS batches(id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, batch_no TEXT NOT NULL, prod_date TEXT DEFAULT '',
  expiry TEXT DEFAULT '', remark TEXT DEFAULT '', {AUD}, UNIQUE(product_id, batch_no));
-- 产品出入库情况：一条=配送员一次领取/交回；book_date 为空 = 在外未交回
CREATE TABLE IF NOT EXISTS daily_entries(id INTEGER PRIMARY KEY, courier_id INTEGER NOT NULL, out_date TEXT NOT NULL, book_date TEXT,
  vals TEXT DEFAULT '{{}}', hand TEXT DEFAULT '[]', note TEXT DEFAULT '', source TEXT DEFAULT 'book', legacy TEXT DEFAULT '', {AUD});
CREATE INDEX IF NOT EXISTS ix_daily_book ON daily_entries(book_date);
-- 盘点（锚点）：从该实数往后自动加减；diff=盘点调整
CREATE TABLE IF NOT EXISTS stock_counts(id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, batch_no TEXT DEFAULT '', qty REAL NOT NULL,
  date TEXT NOT NULL, computed_before REAL, diff REAL, note TEXT DEFAULT '', {AUD});
-- 库存流水（由各单据自动生成，不直接编辑）
CREATE TABLE IF NOT EXISTS moves(id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, batch_no TEXT DEFAULT '', qty REAL NOT NULL, date TEXT NOT NULL,
  ts REAL NOT NULL, src TEXT NOT NULL, src_id INTEGER NOT NULL, label TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS ix_moves_p ON moves(product_id, date);
CREATE INDEX IF NOT EXISTS ix_moves_src ON moves(src, src_id);
-- 借用归还（员工自用并入；单位借用如示例一院/二院）：unit=借用单位，escort=随车技术人员；need_return=0 视为领用出库；finalized=0 有「若干」未定数
CREATE TABLE IF NOT EXISTS loans(id INTEGER PRIMARY KEY, date TEXT NOT NULL, handler TEXT DEFAULT '', user_to TEXT DEFAULT '', unit TEXT DEFAULT '',
  phone TEXT DEFAULT '', use_type TEXT DEFAULT '外单位', need_return INTEGER DEFAULT 1, source TEXT DEFAULT '', u8_no TEXT DEFAULT '', u8_type TEXT DEFAULT '',
  salesperson TEXT DEFAULT '', remark TEXT DEFAULT '', status TEXT DEFAULT '未归还', legacy_id TEXT DEFAULT '',
  escort TEXT DEFAULT '', finalized INTEGER DEFAULT 1, slip_no TEXT DEFAULT '', orgs TEXT DEFAULT '[]', {AUD});
-- 借用单可多个借用单位（orgs JSON，如一院+二院）；slip_no 自动编号
-- 借用明细：org=所属单位或「共用」；need_return 按项（NULL 继承整单）；主件精确数量；小件可写「若干」(approx=1, qty_text)，归还清点后定数；未定数进待补全
CREATE TABLE IF NOT EXISTS loan_items(id INTEGER PRIMARY KEY, loan_id INTEGER NOT NULL, product_id INTEGER, product_name TEXT DEFAULT '',
  qty REAL NOT NULL, returned REAL DEFAULT 0, batch_no TEXT DEFAULT '', note TEXT DEFAULT '', approx INTEGER DEFAULT 0, qty_text TEXT DEFAULT '', org TEXT DEFAULT '',
  need_return INTEGER);  -- 1要还/0不用还；NULL=继承 loans.need_return（旧单兼容）
-- 归还：可按单（loan_id）或按单位总欠数分摊（org + items 里带 loan_item_id 分配结果）
CREATE TABLE IF NOT EXISTS loan_returns(id INTEGER PRIMARY KEY, loan_id INTEGER, org TEXT DEFAULT '', date TEXT NOT NULL, items TEXT DEFAULT '[]',
  remark TEXT DEFAULT '', legacy_id TEXT DEFAULT '', {AUD});
-- 待补全
CREATE TABLE IF NOT EXISTS pending(id INTEGER PRIMARY KEY, date TEXT NOT NULL, taker TEXT DEFAULT '', what TEXT DEFAULT '', qty TEXT DEFAULT '',
  product_id INTEGER, customer TEXT DEFAULT '', handler TEXT DEFAULT '', status TEXT DEFAULT '待补全', close_note TEXT DEFAULT '',
  link_type TEXT DEFAULT '', link_id INTEGER, auto_key TEXT DEFAULT '', {AUD});
-- 库房杂物（暂存物品/工程材料/未知物品合一，不计库存）：category 暂存/工程/未知；status 在库/已取走/已转入库
CREATE TABLE IF NOT EXISTS temp_items(id INTEGER PRIMARY KEY, date TEXT NOT NULL, category TEXT DEFAULT '暂存', placed_by TEXT DEFAULT '', location TEXT DEFAULT '',
  descr TEXT DEFAULT '', name TEXT DEFAULT '', qty TEXT DEFAULT '', status TEXT DEFAULT '在库', result_note TEXT DEFAULT '', product_id INTEGER, arrival_id INTEGER,
  done_date TEXT DEFAULT '', {AUD});
-- 称重计量单
CREATE TABLE IF NOT EXISTS paper_sheets(id INTEGER PRIMARY KEY, date TEXT, session TEXT, form TEXT, rows TEXT DEFAULT '[]', note TEXT DEFAULT '', layout TEXT DEFAULT '', batches TEXT DEFAULT '{{}}', edits TEXT DEFAULT '[]',
  created_at REAL, created_by TEXT, updated_at REAL, updated_by TEXT, deleted_at REAL, deleted_by TEXT);
CREATE TABLE IF NOT EXISTS weigh_slips(id INTEGER PRIMARY KEY, serial TEXT, date TEXT, car_no TEXT DEFAULT '', gross REAL, tare REAL, net REAL,
  gross_time TEXT DEFAULT '', tare_time TEXT DEFAULT '', data TEXT DEFAULT '{{}}', lox_row TEXT DEFAULT '', {AUD});
-- 报表 5 张（换算表/入出库记录/库存及到货总数/液氧表/4号院）：表格数据 JSON
CREATE TABLE IF NOT EXISTS report_tabs(key TEXT PRIMARY KEY, data TEXT, updated_at REAL, updated_by TEXT);
-- 照片（文件存 data/photos）
CREATE TABLE IF NOT EXISTS photos(id INTEGER PRIMARY KEY, entity TEXT DEFAULT '', entity_id INTEGER, tag TEXT DEFAULT '', path TEXT NOT NULL,
  name TEXT DEFAULT '', size INTEGER DEFAULT 0, legacy TEXT DEFAULT '', {AUD});
CREATE INDEX IF NOT EXISTS ix_photos ON photos(entity, entity_id);
CREATE TABLE IF NOT EXISTS photo_inbox(token TEXT, photo_id INTEGER, created_at REAL);
-- 留痕
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, ts REAL, person TEXT, action TEXT, entity TEXT, entity_id INTEGER, summary TEXT,
  before TEXT, after TEXT);
CREATE INDEX IF NOT EXISTS ix_audit ON audit(entity, entity_id);
"""

# 后加的列（旧库启动时自动补上）
ADD_COLS = [('products', 'no_u8', 'INTEGER DEFAULT 0'),            # 默认不入U8（如厂内自用配件）
            ('loans', 'cust_name', "TEXT DEFAULT ''"), ('loans', 'cust_phone', "TEXT DEFAULT ''"),   # v1.1.1 客户 / 销售人电话 / 取货人（可多个，JSON）
            ('loans', 'sales_phone', "TEXT DEFAULT ''"), ('loans', 'pickups', "TEXT DEFAULT '[]'"),
            ('loans', 'need_sign', 'INTEGER DEFAULT 0'),
            ('loan_items', 'final_qty_at', 'REAL'),               # 「若干」定数时间
            ('loan_items', 'need_return', 'INTEGER'),             # 1.1.41 按项要还；NULL=继承整单 need_return
            ('out_orders', 'sign_needed', 'INTEGER DEFAULT 0'),   # 领用出库单：要签字回传
            ('out_items', 'side', "TEXT DEFAULT 'out'"),          # 1.1.29 换货：out=换出/发出，in=换入/收回；其它出库一律 out
            ('weigh_slips', 'used_at', 'REAL'),                   # 已登记到液氧表
            ('report_tabs', 'version', 'INTEGER DEFAULT 0'),
            ('report_tabs', 'tpl', "TEXT DEFAULT ''"),
            ('temp_items', 'remark', "TEXT DEFAULT ''"),          # 备注（每类记录都有）
            ('pending', 'remark', "TEXT DEFAULT ''"),
            ('paper_sheets', 'layout', "TEXT DEFAULT ''"), ('paper_sheets', 'batches', "TEXT DEFAULT '{}'"), ('paper_sheets', 'edits', "TEXT DEFAULT '[]'")]

ENTITY_TABLE = {'product': 'products', 'courier': 'couriers', 'customer': 'customers', 'out': 'out_orders', 'arrival': 'arrivals',
                'batch': 'batches', 'daily': 'daily_entries', 'count': 'stock_counts', 'loan': 'loans', 'loan_return': 'loan_returns',
                'pending': 'pending', 'temp': 'temp_items', 'slip': 'weigh_slips', 'photo': 'photos', 'person': 'people', 'u8': 'u8_items', 'paper': 'paper_sheets'}
ENTITY_CN = {'product': '产品', 'courier': '配送员', 'customer': '客户', 'out': '出库单', 'arrival': '到货', 'batch': '批次',
             'daily': '产品出入库情况', 'count': '盘点', 'loan': '借用', 'loan_return': '归还', 'pending': '待补全', 'temp': '库房杂物',
             'slip': '称重单', 'photo': '照片', 'person': '经办人', 'u8': 'U8账面', 'settings': '设置', 'report': '报表', 'paper': '交接表'}

PERM_KEYS = [('entry', '录入/修改'), ('delete', '删除/恢复'), ('count', '盘点/改库存'), ('settings', '设置/人员'), ('backup', '备份/导入')]

def now(): return time.time()
def today(): return datetime.date.today().isoformat()

def connect(path=None):
    c = sqlite3.connect(path or DB_PATH, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA foreign_keys=OFF'); c.execute('PRAGMA busy_timeout=30000')
    return c

def init(path=None):
    os.makedirs(os.path.dirname(path or DB_PATH), exist_ok=True); os.makedirs(PHOTO_DIR, exist_ok=True)
    c = connect(path)
    c.executescript(SCHEMA)
    for t, col, decl in ADD_COLS:   # 老数据库补列
        if col not in cols(c, t): c.execute(f'ALTER TABLE {t} ADD COLUMN {col} {decl}')
    if not c.execute("SELECT 1 FROM meta WHERE k='schema'").fetchone():
        c.execute("INSERT INTO meta VALUES('schema','1')")
        c.execute("INSERT INTO meta VALUES('salt',?)", (hashlib.sha256(os.urandom(16)).hexdigest()[:16],))
    c.commit(); return c

def row(r): return dict(r) if r is not None else None
def rows(rs): return [dict(r) for r in rs]

def meta_get(c, k, default=None):
    r = c.execute('SELECT v FROM meta WHERE k=?', (k,)).fetchone()
    if not r: return default
    try: return json.loads(r[0])
    except Exception: return r[0]
def meta_set(c, k, v): c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', (k, json.dumps(v, ensure_ascii=False)))

def pin_hash(c, pin): return hashlib.sha256((str(meta_get(c, 'salt', '')) + ':' + str(pin)).encode()).hexdigest()

def audit(c, person, action, entity, eid, summary='', before=None, after=None):
    j = lambda o: None if o is None else json.dumps(o, ensure_ascii=False, default=str)
    c.execute('INSERT INTO audit(ts,person,action,entity,entity_id,summary,before,after) VALUES(?,?,?,?,?,?,?,?)',
              (now(), person, action, entity, eid, summary, j(before), j(after)))

def cols(c, table): return [r[1] for r in c.execute(f'PRAGMA table_info({table})')]

def diff_summary(before, after, skip=('updated_at', 'updated_by', 'created_at', 'created_by')):
    if not before: return ''
    ch = []
    for k, v in after.items():
        if k in skip: continue
        if k in before and str(before.get(k) if before.get(k) is not None else '') != str(v if v is not None else ''):
            ch.append(f"{k}: {before.get(k)!r}→{v!r}")
    return '；'.join(ch)[:900]

def save_row(c, entity, data, person, summary=None, extra_before=None, extra_after=None):
    """插入或更新一行（data 含 id 则更新），自动留痕。返回 id"""
    t = ENTITY_TABLE[entity]; cl = set(cols(c, t)); ts = now()
    d = {k: v for k, v in data.items() if k in cl and k not in ('created_at', 'created_by', 'deleted_at', 'deleted_by', 'updated_at', 'updated_by')}
    rid = d.pop('id', None)
    if rid:
        before = row(c.execute(f'SELECT * FROM {t} WHERE id=?', (rid,)).fetchone())
        if not before: raise ValueError('记录不存在')
        d.update(updated_at=ts, updated_by=person)
        if d:
            c.execute(f"UPDATE {t} SET {','.join(k + '=?' for k in d)} WHERE id=?", (*d.values(), rid))
        after = row(c.execute(f'SELECT * FROM {t} WHERE id=?', (rid,)).fetchone())
        b = dict(before); a = dict(after)
        if extra_before is not None: b['_items'] = extra_before
        if extra_after is not None: a['_items'] = extra_after
        s = summary if summary is not None else diff_summary(before, after)
        audit(c, person, '修改', entity, rid, s, b, a)
        return rid
    d.update(created_at=data.get('created_at') or ts, created_by=data.get('created_by') or person)
    cur = c.execute(f"INSERT INTO {t}({','.join(d)}) VALUES({','.join('?' * len(d))})", tuple(d.values()))
    rid = cur.lastrowid
    a = row(c.execute(f'SELECT * FROM {t} WHERE id=?', (rid,)).fetchone())
    if extra_after is not None: a['_items'] = extra_after
    audit(c, person, '新增', entity, rid, summary or '', None, a)
    return rid

def soft_delete(c, entity, rid, person, reason=''):
    t = ENTITY_TABLE[entity]
    before = row(c.execute(f'SELECT * FROM {t} WHERE id=?', (rid,)).fetchone())
    if not before: raise ValueError('记录不存在')
    c.execute(f'UPDATE {t} SET deleted_at=?, deleted_by=? WHERE id=?', (now(), person, rid))
    audit(c, person, '删除', entity, rid, reason, before, None)

def restore(c, entity, rid, person):
    t = ENTITY_TABLE[entity]
    c.execute(f'UPDATE {t} SET deleted_at=NULL, deleted_by=NULL WHERE id=?', (rid,))
    audit(c, person, '恢复', entity, rid, '', None, row(c.execute(f'SELECT * FROM {t} WHERE id=?', (rid,)).fetchone()))
