# -*- coding: utf-8 -*-
"""每日自动备份（本机 data/backups + 另存到 U 盘/共享文件夹）、导出全部数据 zip、导入恢复"""
import os, zipfile, sqlite3, time, datetime, shutil, threading, io, json, tempfile
import db

BK_DIR = os.path.join(db.DATA, 'backups')

def snapshot_db(dst):
    src = sqlite3.connect(db.DB_PATH); out = sqlite3.connect(dst)
    with out: src.backup(out)
    src.close(); out.close()

def make_zip(path, with_photos=True):
    tmp = tempfile.mkdtemp()
    try:
        snap = os.path.join(tmp, 'warehouse.db'); snapshot_db(snap)
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(snap, 'warehouse.db')
            z.writestr('说明.txt', '库房出入库系统 全部数据备份\n生成时间：%s\n恢复：系统「数据备份」页 →「导入/恢复」选择本文件。\n' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
            if with_photos and os.path.isdir(db.PHOTO_DIR):
                for root, _, files in os.walk(db.PHOTO_DIR):
                    for f in files:
                        full = os.path.join(root, f)
                        z.write(full, 'photos/' + os.path.relpath(full, db.PHOTO_DIR).replace('\\', '/'))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return path

def backup_now(reason='手动'):
    os.makedirs(BK_DIR, exist_ok=True)
    name = '库房备份_%s.zip' % datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    p = make_zip(os.path.join(BK_DIR, name))
    res = {'name': name, 'size': os.path.getsize(p), 'copied': None, 'copy_error': None}
    c = db.connect()
    try:
        import logic
        s = logic.settings(c)
        dest = (s.get('backup_dir') or '').strip()
        if dest:
            try:
                if not os.path.isdir(dest): raise OSError('文件夹不存在或 U 盘未插：' + dest)
                shutil.copy2(p, os.path.join(dest, name)); res['copied'] = os.path.join(dest, name)
            except Exception as e:
                res['copy_error'] = str(e)
        keep = int(s.get('backup_keep') or 30)
        fs = sorted(f for f in os.listdir(BK_DIR) if f.endswith('.zip'))
        for f in fs[:-keep]: os.remove(os.path.join(BK_DIR, f))
        db.meta_set(c, 'last_backup', {'ts': time.time(), 'name': name, 'reason': reason, 'copied': res['copied'], 'copy_error': res['copy_error']})
        c.commit()
    finally: c.close()
    return res

def list_backups():
    os.makedirs(BK_DIR, exist_ok=True)
    out = []
    for f in sorted(os.listdir(BK_DIR), reverse=True):
        if f.endswith('.zip'):
            p = os.path.join(BK_DIR, f); out.append({'name': f, 'size': os.path.getsize(p), 'mtime': os.path.getmtime(p)})
    return out

def restore_zip(data):
    """先自动备份当前数据，再用上传的 zip 覆盖"""
    z = zipfile.ZipFile(io.BytesIO(data))
    if 'warehouse.db' not in z.namelist(): raise ValueError('不是本系统的备份文件（缺少 warehouse.db）')
    tmp = tempfile.mkdtemp()
    z.extract('warehouse.db', tmp)
    t = sqlite3.connect(os.path.join(tmp, 'warehouse.db'))
    ok = t.execute("SELECT name FROM sqlite_master WHERE name='out_orders'").fetchone(); t.close()
    if not ok: raise ValueError('备份文件里没有出库数据表')
    safety = backup_now('导入前自动备份')
    with db.WRITE_LOCK:
        src = sqlite3.connect(os.path.join(tmp, 'warehouse.db')); dst = sqlite3.connect(db.DB_PATH)
        with dst: src.backup(dst)
        src.close(); dst.close()
        for n in z.namelist():
            if n.startswith('photos/') and not n.endswith('/'):
                target = os.path.join(db.PHOTO_DIR, n[7:])
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, 'wb') as f: f.write(z.read(n))
    shutil.rmtree(tmp, ignore_errors=True)
    return {'safety_backup': safety['name']}

def auto_loop(stop):
    while not stop.is_set():
        try:
            today = datetime.date.today().strftime('%Y%m%d')
            if not any(f.startswith('库房备份_' + today) for f in (os.listdir(BK_DIR) if os.path.isdir(BK_DIR) else [])):
                backup_now('每日自动')
        except Exception as e:
            print('自动备份失败：', e)
        stop.wait(1800)

def start_auto():
    stop = threading.Event(); th = threading.Thread(target=auto_loop, args=(stop,), daemon=True); th.start(); return stop
