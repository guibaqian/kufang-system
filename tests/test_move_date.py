"""交接表「改日期 / 场次」：录错日期（19 号的数录到 20 号）时整张搬过去；同场次另一张默认一起搬；目标已有表就拦住；
要密码、记操作记录；新旧两天的出入库、库存、次日清点全部重算；行里「记到哪天」早于新日期的改回记当天（先提示）"""
import os, sys, json, unittest, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, stock, setUpModule, tearDownModule, ROOT  # noqa
import server, logic

def rows_of(date): return {x['name']: x for x in logic.daily_rows(server.db_c(), date)}
def save(date, ses, form, rows): st, r = call('/api/paper/save', {'data': {'date': date, 'session': ses, 'form': form, 'rows': rows}}); assert st == 200, r; return r['id']
def moves(pid, date): return sum(r[0] for r in server.db_c().execute("SELECT qty FROM moves WHERE product_id=? AND date=? AND src='daily'", (pid, date)))
def sheet(i): return dict(server.db_c().execute('SELECT date, session, form, rows FROM paper_sheets WHERE id=?', (i,)).fetchone())
def check(i, d, s, pair=1): return call('/api/paper/move_check?' + urllib.parse.urlencode({'id': i, 'date': d, 'session': s, 'pair': pair}))

class T1_Move(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = logic.daily_map(server.db_c()); call('/api/count/save', {'product_id': cls.m['shb'], 'qty': 500, 'date': '2026-11-01'})

    def test_1_move_pair_wrong_day(self):
        m = self.m; q0 = stock(m['shb'])['qty']
        a = save('2026-11-06', '早上', 'cyl', [{'rid': 'a', 'plate': '6922', 'driver': '改期甲', 'cells': {'L.e40': '5', 'R.o40': '20'}}])
        b = save('2026-11-06', '早上', 'prod', [{'rid': 'a', 'plate': '6922', 'cells': {'L.shb': '2退', 'R.shb': '10'}}])
        self.assertEqual(rows_of('2026-11-05')['改期甲']['vals']['e40'], 5); self.assertEqual((moves(m['shb'], '2026-11-06'), moves(m['shb'], '2026-11-05')), (-8, 0))   # 早上写退的：当天（交回那天）入库
        st, pl = check(a, '2026-11-05', '早上'); self.assertEqual(st, 200); self.assertEqual(pl['clash'], []); self.assertEqual(len(pl['sheets']), 2)
        self.assertEqual(call('/api/paper/move', {'id': a, 'date': '2026-11-05', 'session': '早上'}, pin='0000')[0], 401)   # 要密码
        st, r = call('/api/paper/move', {'id': a, 'date': '2026-11-05', 'session': '早上', 'pair': True}); self.assertEqual(st, 200, r)
        self.assertEqual((sheet(a)['date'], sheet(b)['date']), ('2026-11-05', '2026-11-05'))
        self.assertNotIn('改期甲', rows_of('2026-11-06'))
        v4 = rows_of('2026-11-04')['改期甲']['vals']; v5 = rows_of('2026-11-05')['改期甲']; self.assertEqual((v4['e40'], v4['v1_shb']), (5, 2)); self.assertEqual(v5['vals']['o40'], 20)
        self.assertEqual(v5['pending'], ['钢瓶', '产品'])                         # 11.05 等 11.06 早上清点
        self.assertEqual((moves(m['shb'], '2026-11-06'), moves(m['shb'], '2026-11-05'), moves(m['shb'], '2026-11-04')), (0, -8, 0))
        self.assertEqual(stock(m['shb'])['qty'], q0 - 8)                          # 库存不重复、不丢
        au = [x[0] for x in server.db_c().execute("SELECT summary FROM audit WHERE entity='paper' ORDER BY id")]
        self.assertIn('把 2026-11-06 早上 钢瓶表 改到 2026-11-05 早上', au); self.assertIn('把 2026-11-06 早上 产品表 改到 2026-11-05 早上', au)
        self.assertEqual(json.loads(server.db_c().execute('SELECT edits FROM paper_sheets WHERE id=?', (a,)).fetchone()[0])[-1]['label'], '日期 / 场次')

    def test_2_clash_blocked(self):
        a = save('2026-11-08', '早上', 'cyl', [{'rid': 'a', 'plate': '6720', 'driver': '改期乙', 'cells': {'R.o40': '3'}}])
        save('2026-11-08', '中午', 'cyl', [{'rid': 'a', 'plate': '6720', 'driver': '改期乙', 'cells': {'R.o40': '4'}}])
        st, pl = check(a, '2026-11-08', '中午'); self.assertTrue(pl['clash'] and '不会覆盖' in pl['clash'][0])
        st, r = call('/api/paper/move', {'id': a, 'date': '2026-11-08', 'session': '中午'}); self.assertEqual(st, 409); self.assertIn('已经有', r['error'])
        self.assertEqual(sheet(a)['session'], '早上'); self.assertEqual(rows_of('2026-11-08')['改期乙']['vals']['o40'], 7)   # 什么都没动
        self.assertEqual(check(a, '2026-11-08', '早上')[0], 400)   # 没变

    def test_3_book_date_and_single(self):
        a = save('2026-11-10', '中午', 'cyl', [{'rid': 'a', 'plate': '9255', 'driver': '改期丙', 'cells': {'L.e40': '2', 'R.o40': '6'}, 'book_date': '2026-11-11'},
                                             {'rid': 'b', 'plate': '2880', 'driver': '改期丁', 'cells': {'R.o40': '1'}, 'book_date': '2026-11-20'}])
        b = save('2026-11-10', '中午', 'prod', [{'rid': 'a', 'plate': '9255', 'cells': {'R.shb': '3'}}])
        pl = check(a, '2026-11-12', '中午')[1]; w = {x['plate']: x for x in pl['warn']}
        self.assertTrue(w['9255']['fix']); self.assertFalse(w['2880']['fix'])
        self.assertEqual(call('/api/paper/move', {'id': a, 'date': '2026-11-12', 'session': '中午', 'pair': False})[0], 200)
        rs = {r['rid']: r for r in json.loads(sheet(a)['rows'])}; self.assertIsNone(rs['a'].get('book_date')); self.assertEqual(rs['b']['book_date'], '2026-11-20')
        self.assertEqual(rows_of('2026-11-12')['改期丙']['vals']['o40'], 6); self.assertNotIn('改期丙', rows_of('2026-11-11'))
        self.assertEqual(sheet(b)['date'], '2026-11-10')                          # 没勾「一起搬」：产品表留着
        self.assertEqual(json.loads(sheet(b)['rows'])[0]['plate'], '9255')        # 车牌留着（同场次没钢瓶表了，只读照旧）


from test_nav import HAVE, CHROME, run
import test_all
OUT = os.path.join(ROOT, 'screens')

@unittest.skipUnless(HAVE, '没有 playwright / Chrome')
class T2_UI(unittest.TestCase):
    def test_ui_move(self):
        save('2026-10-20', '早上', 'cyl', [{'rid': 'a', 'plate': '6922', 'driver': '6922丁增', 'cells': {'L.e40': '5', 'R.o40': '20', 'R.o10': '4'}},
                                         {'rid': 'b', 'plate': '9255', 'driver': '9255沈兴德', 'cells': {'L.e40': '3', 'R.o40': '12'}, 'book_date': '2026-10-21'}])
        save('2026-10-20', '早上', 'prod', [{'rid': 'a', 'plate': '6922', 'cells': {'L.shb': '2退', 'R.shb': '10'}}])
        save('2026-10-18', '早上', 'cyl', [{'rid': 'a', 'plate': '6922', 'driver': '6922丁增', 'cells': {'R.o40': '9'}}])
        async def go():
            from playwright.async_api import async_playwright
            pw = await async_playwright().start(); br = await pw.chromium.launch(executable_path=CHROME, args=['--no-sandbox']); errs = []
            try:
                pg = await (await br.new_context(viewport={'width': 1360, 'height': 820}, locale='zh-CN')).new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
                await pg.goto(test_all.URL + '/'); await pg.wait_for_timeout(500)
                await pg.evaluate("location.hash = '#daily/cyl'"); await pg.wait_for_timeout(900)
                await pg.fill('#dDate', '2026-10-20'); await pg.dispatch_event('#dDate', 'change'); await pg.wait_for_timeout(800)
                await pg.click('#ppSes button[data-s="早上"]'); await pg.wait_for_timeout(300)
                await pg.click('#ppMove'); await pg.wait_for_selector('#mvD')
                self.assertEqual(await pg.input_value('#mvD'), '2026-10-19'); self.assertTrue(await pg.is_checked('#mvP'))
                await pg.screenshot(path=os.path.join(OUT, 'move_date_1_dialog.png'))
                await pg.fill('#mvD', '2026-10-18'); await pg.click('.dlg-f button:has-text("改过去")'); await pg.wait_for_timeout(400)
                self.assertIn('已经有', await pg.inner_text('#mvMsg')); await pg.screenshot(path=os.path.join(OUT, 'move_date_2_blocked.png'))
                await pg.fill('#mvD', '2026-10-19'); await pg.click('.dlg-f button:has-text("改过去")'); await pg.wait_for_selector('text=确定改')
                await pg.screenshot(path=os.path.join(OUT, 'move_date_3_confirm.png'))
                await pg.click('button:has-text("确定改")')
                await pg.wait_for_selector('.pin-in', timeout=3000); await pg.fill('.pin-in', '1002'); await pg.press('.pin-in', 'Enter')
                await pg.wait_for_timeout(1200)
                self.assertEqual(await pg.input_value('#dDate'), '2026-10-19')
                await pg.screenshot(path=os.path.join(OUT, 'move_date_4_done.png'))
            finally:
                await br.close(); await pw.stop()
            self.assertEqual(errs, [])
        run(go())
        self.assertEqual(server.db_c().execute("SELECT COUNT(*) FROM paper_sheets WHERE date='2026-10-19' AND session='早上' AND deleted_at IS NULL").fetchone()[0], 2)
        self.assertNotIn('6922丁增', rows_of('2026-10-20'))

if __name__ == '__main__': unittest.main()
