"""换算表「识别用量截图」回归测试（在无头 Chrome 里跑前端离线识别）：python -m unittest tests.test_ocr -v"""
import os, sys, asyncio, unittest, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ocr_harness
WANT = [('01001', '40', 382), ('01002', '10', 41), ('02003', '35', 5), ('02005', '100', 7), ('02001', '20', 3), ('02007', '210', 4), ('02006', '175', 1), ('02008', '500', 1), ('02005', '100', 1)]

IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'u8_daily_20261018.png')
HAVE = os.path.exists(ocr_harness.CHROME)
try: import playwright  # noqa
except ImportError: HAVE = False

@unittest.skipUnless(HAVE, '需要 Chrome + playwright')
class O1_Daily(unittest.TestCase):
    def test_20261018_all_rows(self):
        """2026.10.18 截图：第 2 行（01002 10L 41）以前会漏，还会冒出「?」"""
        (r,), logs = asyncio.run(ocr_harness.run_daily([IMG]))
        self.assertEqual(r['mode'], 'grid')
        self.assertEqual(len(r['rows']), 9, r['rows'])
        self.assertEqual(sum(x['qty'] for x in r['rows']), 445)
        self.assertEqual(r['total'], 445); self.assertTrue(r['totalOk'])
        self.assertEqual(r['gas'], {'10': 41, '40': 382})
        self.assertEqual(r['liq'], {'20': 3, '35': 5, '100': 8, '175': 1, '210': 4, '500': 1})
        row2 = r['rows'][1]; self.assertEqual((row2['code'], row2['spec'], row2['qty']), ('01002', '10', 41))
        self.assertTrue(all(x['sure'] for x in r['rows']))
        self.assertEqual([(x['code'], x['spec'], x['qty']) for x in r['rows']], WANT)
        self.assertEqual([x.get('rowNo') for x in r['rows']], list(range(1, 10)))

    def test_other_scales_never_silently_wrong(self):
        """放大 / 缩小后的截图：要么认对，要么标「请核对」，不能悄悄填错"""
        try: from PIL import Image
        except ImportError: self.skipTest('没有 PIL')
        import tempfile
        im = Image.open(IMG); paths = []
        for k in (0.9, 1.25, 1.5):
            p = os.path.join(tempfile.mkdtemp(), 's%s.png' % k); im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS).save(p); paths.append(p)
        res, _ = asyncio.run(ocr_harness.run_daily(paths))
        for k, r in zip((0.9, 1.25, 1.5), res):
            self.assertEqual(len(r['rows']), 9, k)
            for x in r['rows']:
                if x['sure']: self.assertEqual((x['code'], x['spec'], x['qty']), WANT[x['rowNo'] - 1], (k, x))
            if k >= 1.25: self.assertEqual(r['gas'], {'10': 41, '40': 382}); self.assertTrue(r['totalOk'])

if __name__ == '__main__': unittest.main()
