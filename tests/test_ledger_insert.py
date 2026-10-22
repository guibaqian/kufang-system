"""入出库记录中间插行：批次剩余 L 链接好（与前端 rLedgerRewireL / 回收站 restore 一致）。
python -m unittest tests.test_ledger_insert -v
"""
import os, sys, copy, re, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, setUpModule, tearDownModule  # noqa
import reports, xlgrid

def tab(k): return call('/api/report?key=' + k)[1]

def Lf(t, r):
    c = (t['rows'][r - 1] or {}).get('c', {}).get('L') or {}
    return (c.get('f') or '').replace(' ', '').replace('$', '')

def rewire(t, at):
    """照前端 rLedgerRewireL：本行 L{at-1}-K{at}；下一行若被 insert 平移成 L{at-1}-K{at+1} 则改成 L{at}-K{at+1}"""
    cell = t['rows'][at - 1].setdefault('c', {}).setdefault('L', {})
    cell.pop('v', None); cell['f'] = 'L%d-K%d' % (at - 1, at)
    nxt = t['rows'][at] if at < len(t['rows']) else None
    nl = (nxt or {}).get('c', {}).get('L') if nxt else None
    if nl and nl.get('f') and re.fullmatch(r'L%d-K%d' % (at - 1, at + 1), nl['f'].replace(' ', '').replace('$', '')):
        nl.pop('v', None); nl['f'] = 'L%d-K%d' % (at, at + 1)

class LedgerInsert(unittest.TestCase):
    def test_mid_insert_rewires_L_chain(self):
        t = copy.deepcopy(tab('ledger'))
        rg = reports.ranges('ledger', t)
        # 找一行「L{r-1}-K{r}」链公式，在它前面插空行
        at = None
        for r in range(rg['start'] + 2, rg['main_end'] + 1):
            if Lf(t, r) == 'L%d-K%d' % (r - 1, r):
                at = r; break
        self.assertIsNotNone(at, '测试库里应有批次剩余链公式行')
        prev_f, old_f = Lf(t, at - 1), Lf(t, at)
        old_K = reports._v(t, 'K', at)
        xlgrid.insert_row(t, at, {'c': {}})
        # insert 后：原 at 行下移到 at+1，公式被平移成 L{at-1}-K{at+1}（断链）
        self.assertEqual(Lf(t, at + 1), 'L%d-K%d' % (at - 1, at + 1), 'insert 后下一行应被平移成断链形式')
        rewire(t, at)
        self.assertEqual(Lf(t, at), 'L%d-K%d' % (at - 1, at))
        self.assertEqual(Lf(t, at + 1), 'L%d-K%d' % (at, at + 1))
        # 出库量跟着下移，数值不变
        self.assertEqual(reports._v(t, 'K', at + 1), old_K)
        # 上一行公式不动（若本来有）
        if prev_f:
            self.assertEqual(Lf(t, at - 1), prev_f)
        # 新空行只有 L 公式，没有出库量
        self.assertTrue(t['rows'][at - 1] and t['rows'][at - 1]['c'].get('L', {}).get('f'))
        self.assertIn(reports._v(t, 'K', at), (None, ''))

    def test_restore_also_rewires_L(self):
        """回收站恢复路径已接 L 链（回归：别把 restore 的公式接法改坏）"""
        src = reports.restore_row.__doc__ or ''
        # 直接读源码断言关键逻辑仍在
        import inspect
        src = inspect.getsource(reports.restore_row)
        self.assertIn("L%d-K%d", src)
        self.assertIn("(at-1,at)", src.replace(' ', ''))

if __name__ == '__main__':
    unittest.main()
