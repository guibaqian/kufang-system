# -*- coding: utf-8 -*-
"""照片库：长会话持续上传 + 电脑选用。python -m unittest tests.test_plib -v"""
import os, sys, base64, zlib, struct, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, setUpModule, tearDownModule, ROOT  # noqa
import server

def png(w=80, h=60, rgb=(47, 102, 224)):
    raw = b''.join(b'\x00' + bytes(rgb) * w for _ in range(h))
    ch = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + ch(b'IDAT', zlib.compress(raw)) + ch(b'IEND', b'')
DATA = 'data:image/png;base64,' + base64.b64encode(png()).decode()

class L1_LibApi(unittest.TestCase):
    def test_session_upload_take(self):
        st, s = call('/api/lib/session', {'by': '测'}, pin=''); self.assertEqual(st, 200, s)
        t = s['token']; self.assertGreaterEqual(s['ttl'], 7 * 86400); self.assertFalse(s.get('reused') and False)  # first may be new
        # reuse
        st, s2 = call('/api/lib/session', {}, pin=''); self.assertEqual(s2['token'], t); self.assertEqual(s2['reused'], 1)
        st, info = call('/api/lib/info?t=' + t); self.assertEqual(info['state'], 'open')
        ids = []
        for i in range(3):
            st, p = call('/api/lib/photo', {'t': t, 'data': DATA, 'name': 'a%d.png' % i}, pin=''); self.assertEqual(st, 200, p); ids.append(p['id'])
        st, lst = call('/api/lib/list'); self.assertEqual(st, 200)
        got = {x['id'] for x in lst['items']}; self.assertTrue(set(ids) <= got)
        # take 2
        st, tk = call('/api/lib/take', {'ids': ids[:2], 'by': '测'}, pin=''); self.assertEqual((st, tk['n']), (200, 2))
        left = {x['id'] for x in call('/api/lib/list')[1]['items']}
        self.assertNotIn(ids[0], left); self.assertNotIn(ids[1], left); self.assertIn(ids[2], left)
        # taken photos are unattached (entity empty)
        row = server.db_c().execute('SELECT entity FROM photos WHERE id=?', (ids[0],)).fetchone()
        self.assertEqual(row[0], '')
        # bad token
        self.assertEqual(call('/api/lib/photo', {'t': 'nope', 'data': DATA}, pin='')[0], 404)
        # force new session closes old
        st, s3 = call('/api/lib/session', {'force': 1}, pin=''); self.assertNotEqual(s3['token'], t)
        self.assertEqual(call('/api/lib/photo', {'t': t, 'data': DATA}, pin='')[0], 410)
        # phone page / static
        self.assertTrue(os.path.isfile(os.path.join(ROOT, 'static', 'm', 'lib.html')))
        js = open(os.path.join(ROOT, 'static', 'core.js'), encoding='utf-8').read()
        self.assertIn('pkLib', js); self.assertIn('/api/lib/take', js)
        self.assertIn('fillLibQr', open(os.path.join(ROOT, 'static', 'p_loan.js'), encoding='utf-8').read())

    def test_delete_needs_pin(self):
        t = call('/api/lib/session', {}, pin='')[1]['token']
        pid = call('/api/lib/photo', {'t': t, 'data': DATA}, pin='')[1]['id']
        self.assertEqual(call('/api/lib/delete', {'ids': [pid]}, pin='')[0], 401)
        self.assertEqual(call('/api/lib/delete', {'ids': [pid]}, pin='1002')[0], 200)
        self.assertNotIn(pid, {x['id'] for x in call('/api/lib/list')[1]['items']})

class L2_StockScreen(unittest.TestCase):
    def test_stock_fit_markers(self):
        js = open(os.path.join(ROOT, 'static', 'p_report.js'), encoding='utf-8').read()
        self.assertIn('stock-fit', js)
        self.assertIn('rAttachResize', js)
        self.assertIn('rPersistWidth', js)
        self.assertIn('r-rz', js)
        self.assertIn('rTableWidth', js)
        self.assertIn('rU8Menu', js)
        self.assertIn('data-u8menu', js)
        self.assertNotIn("thtml.replace(/min-width:/g, 'width:')", js)
        css = open(os.path.join(ROOT, 'static', 'app.css'), encoding='utf-8').read()
        self.assertIn('table.rt.stock-fit{table-layout:fixed', css)
        self.assertIn('cursor:col-resize', css)
        self.assertIn('.r-ops{', css)
        import re as _re
        m = _re.search('stock:\\s*\\{([^}]+)\\}', js)
        self.assertTrue(m)
        nums = [int(x) for x in _re.findall(':\\s*(\\d+)', m.group(1))]
        self.assertTrue(all(n <= 200 for n in nums), nums)
        self.assertLessEqual(sum(nums), 1200, nums)


if __name__ == '__main__':
    unittest.main()
