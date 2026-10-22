# -*- coding: utf-8 -*-
"""1.1.56 hot deploy: loan source chip preserve 借用单位; out syncOutDom.
Restart with --no-browser. Never wipe business rows / photos."""
import os, sys, shutil, hashlib, time, datetime, subprocess, urllib.request, sqlite3, json

def find_root():
    for parent in os.listdir("D:/"):
        p = os.path.join("D:/", parent)
        if not os.path.isdir(p):
            continue
        try: children = os.listdir(p)
        except PermissionError: continue
        for child in children:
            root = os.path.join(p, child)
            v = os.path.join(root, "static", "v.json")
            if os.path.isfile(v) and os.path.isdir(os.path.join(root, "app")) and os.path.isdir(os.path.join(root, "data")):
                return root
    raise SystemExit("warehouse root not found")

_candidates = []
if os.environ.get("WH_DEPLOY_SRC"):
    _candidates.append(os.environ["WH_DEPLOY_SRC"])
_candidates.append(os.path.join(os.environ.get("TEMP", ""), "wh_deploy_1156"))
_candidates.append(os.path.dirname(os.path.abspath(__file__)))
SRC = None
for c in _candidates:
    if os.path.isfile(os.path.join(c, "v.json")) or os.path.isfile(os.path.join(c, "static", "v.json")):
        SRC = c; break
if not SRC:
    raise SystemExit("missing deploy src tried=" + repr(_candidates))
print("SRC_RESOLVED", SRC)
ROOT = find_root()
print("ROOT", ROOT)
print("BEFORE", open(os.path.join(ROOT, "static", "v.json"), encoding="utf-8").read().strip())
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = os.path.join(ROOT, "_bak_1156_" + ts)
os.makedirs(bak, exist_ok=True)
FILES = [
    ("version.py", "app"),
    ("v.json", "static"),
    ("p_loan.js", "static"),
    ("p_out.js", "static"),
    ("app.css", "static"),
    ("AUDIT_1.1.56.md", "docs"),
    ("usage.md", ""),
]
def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()
def find_src(name):
    for c in [os.path.join(SRC, name), os.path.join(SRC, "static", name), os.path.join(SRC, "app", name), os.path.join(SRC, "docs", name)]:
        if os.path.isfile(c): return c
    if name == "usage.md":
        for alt in ("usage.md", "使用说明.md"):
            c = os.path.join(SRC, alt)
            if os.path.isfile(c): return c
    raise SystemExit("missing file " + name)

dbp = os.path.join(ROOT, "data", "warehouse.db")
db_bak = os.path.join(ROOT, "data", "warehouse_pre_1156_" + ts + ".db")
shutil.copy2(dbp, db_bak)
print("DB_BAK", db_bak)
con = sqlite3.connect(dbp)
before = {t: con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0] for t in ("out_orders", "moves", "couriers", "photos")}
print("COUNTS_BEFORE", before)
con.execute(
    "INSERT INTO audit(ts,person,action,entity,entity_id,summary,before,after) VALUES(?,?,?,?,?,?,?,?)",
    (time.time(), "系统", "升级", "settings", 0, "热更 1.1.56：借出登记点U8单保留借用单位（来源不整表重绘）；出库单笔换来源前同步DOM", None, None),
)
con.commit()
print("AUDIT_INSERTED")
con.close()

for name, sub in FILES:
    src_path = find_src(name)
    dest_name = "使用说明.md" if name == "usage.md" else name
    dest_dir = ROOT if sub == "" else os.path.join(ROOT, sub)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, dest_name)
    if os.path.isfile(dest):
        shutil.copy2(dest, os.path.join(bak, dest_name.replace("/", "_")))
    shutil.copy2(src_path, dest)
    print("UPDATED", dest, md5(dest))

print("stopping listeners on 8080...")
try:
    out = subprocess.check_output('powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique"', shell=True, text=True, stderr=subprocess.DEVNULL)
    for pid in [x.strip() for x in out.splitlines() if x.strip().isdigit()]:
        subprocess.call(["taskkill", "/F", "/PID", pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("killed", pid)
except Exception as e:
    print("stop note", e)
time.sleep(2)
pyw = os.path.join(ROOT, "python", "pythonw.exe")
launcher = os.path.join(ROOT, "app", "launcher.py")
if os.path.isfile(pyw) and os.path.isfile(launcher):
    subprocess.Popen([pyw, launcher, "--no-browser"], cwd=ROOT, close_fds=True)
    print("started", pyw, "--no-browser")
else:
    raise SystemExit("no launcher")
ver = None
for i in range(40):
    time.sleep(1)
    try:
        ver = urllib.request.urlopen("http://127.0.0.1:8080/v.json", timeout=2).read().decode()
        print("PROBE", i, ver.strip())
        if "1.1.56" in ver: break
    except Exception as e:
        print("wait", i, type(e).__name__)
else:
    raise SystemExit("v.json not 1.1.56: " + repr(ver))

con = sqlite3.connect(dbp)
after = {t: con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0] for t in ("out_orders", "moves", "couriers", "photos")}
print("COUNTS_AFTER", after)
row = con.execute("SELECT id,summary FROM audit ORDER BY id DESC LIMIT 1").fetchone()
print("AUDIT_LAST", row)
con.close()
if after != before:
    raise SystemExit("DATA CHANGED " + repr(before) + " -> " + repr(after))

pl = urllib.request.urlopen("http://127.0.0.1:8080/p_loan.js", timeout=5).read().decode("utf-8", "replace")
assert "lnU8f" in pl and "syncLoanDom" in pl
assert "禁止整表重绘" in pl
assert "f.source = f.source === c.dataset.k ? '' : c.dataset.k; loanForm(el)" not in pl
po = urllib.request.urlopen("http://127.0.0.1:8080/p_out.js", timeout=5).read().decode("utf-8", "replace")
assert "syncOutDom" in po and "已填被冲掉" in po
cs = urllib.request.urlopen("http://127.0.0.1:8080/app.css", timeout=5).read().decode("utf-8", "replace")
assert "v1.1.56" in cs
# prior markers
assert "v1.1.55" in cs
assert "rLedgerNextCandidates" in urllib.request.urlopen("http://127.0.0.1:8080/p_report.js", timeout=5).read().decode("utf-8", "replace")
print("DATA_UNCHANGED OK")
print("PROBE_JS OK")
print("DONE 1.1.56", ver.strip())
