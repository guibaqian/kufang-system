# -*- coding: utf-8 -*-
"""1.1.15+：质检入库去重 + 删行撤销；1.1.24：联动出库行可填左侧、preserve 按行身份。
python -m unittest tests.test_lox_in_dedup_undo -v
"""
import os, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = os.path.join(ROOT, 'static', 'p_report.js')
VER = os.path.join(ROOT, 'app', 'version.py')
REP = os.path.join(ROOT, 'app', 'reports.py')

class DedupUndoSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(JS, encoding='utf-8') as f: cls.js = f.read()
        with open(VER, encoding='utf-8') as f: cls.ver = f.read()
        with open(REP, encoding='utf-8') as f: cls.rep = f.read()

    def test_version_at_least_1124(self):
        self.assertIn("VERSION = '1.1.28'", self.ver)

    def test_no_force_insert_duplicate_path(self):
        self.assertNotIn('_forceInsert', self.js)
        self.assertIn('rLedgerExistingInbound', self.js)
        self.assertIn('不会重复写入', self.js)

    def test_fill_linked_outbound_not_skip(self):
        # 1.1.24: must NOT require !lk to fill same-date left-empty row
        self.assertIn("if (leftEmpty && ((eIso && eIso === iso) || (iIso && iIso === iso))) return { r, mode: 'fill' };", self.js)
        self.assertNotIn('leftEmpty && !lk', self.js)

    def test_delete_pushes_undo(self):
        self.assertIn("rPushUndo({ type: 'del', items: deleted })", self.js)
        self.assertIn("e.type === 'del'", self.js)
        self.assertIn('x.type === \'del\' || x.k !== k', self.js)
        self.assertIn('Ctrl+Z 可撤销', self.js)

    def test_preserve_uses_row_fp(self):
        self.assertIn('def _row_fp(', self.rep)
        self.assertIn('preserve_filled(old, t, _PRESERVE_COLS[k], k)', self.rep)
        self.assertIn('ofp != nfp', self.rep)

class PreserveFilledLogic(unittest.TestCase):
    def test_does_not_paste_across_shifted_rows(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, 'app'))
        import reports
        old = {'rows': [
            None, None,
            {'c': {'B': {'v': '20261009'}, 'E': {'v': '2026.10.19'}, 'F': {'v': 29}}, 'link': {'k': 'lox_in', 'id': 'x'}},
            {'c': {'I': {'v': '2026.10.20'}, 'J': {'v': '出创投'}, 'K': {'v': 6.75}}, 'link': {'k': 'conv', 'date': '2026-10-20'}},
        ]}
        # delete row 3 (lox_in): client sends out-10.20 at index 2
        new = {'rows': [
            None, None,
            {'c': {'I': {'v': '2026.10.20'}, 'J': {'v': '出创投'}, 'K': {'v': 6.75}}, 'link': {'k': 'conv', 'date': '2026-10-20'}},
        ]}
        kept = reports.preserve_filled(old, new, tuple('BCDEFGH'), 'ledger')
        self.assertEqual(kept, [])
        b = (new['rows'][2].get('c') or {}).get('B')
        self.assertTrue(b is None or b.get('v') in (None, ''))

    def test_keeps_blanked_cell_on_same_row(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, 'app'))
        import reports
        old = {'rows': [
            None, None,
            {'c': {'B': {'v': '20261009'}, 'E': {'v': '2026.10.19'}, 'F': {'v': 29},
                   'I': {'v': '2026.10.19'}, 'J': {'v': '出创投'}, 'K': {'v': 6.42}},
             'link': {'k': 'conv', 'date': '2026-10-19'}},
        ]}
        new = {'rows': [
            None, None,
            {'c': {'E': {'v': '2026.10.19'}, 'F': {'v': 29},
                   'I': {'v': '2026.10.19'}, 'J': {'v': '出创投'}, 'K': {'v': 6.42}},
             'link': {'k': 'conv', 'date': '2026-10-19'}},
        ]}
        kept = reports.preserve_filled(old, new, tuple('BCDEFGH'), 'ledger')
        self.assertIn('B3', kept)
        self.assertEqual(new['rows'][2]['c']['B']['v'], '20261009')

if __name__ == '__main__':
    unittest.main()
