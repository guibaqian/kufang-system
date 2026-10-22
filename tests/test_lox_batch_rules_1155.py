# -*- coding: utf-8 -*-
"""1.1.55：液氧入出库接下一批规则（对齐 docs/LOX_BATCH_RULES.md）。"""
import os, re, unittest, json

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def norm(v):
    s = str(v if v is not None else '').strip()
    m = re.match(r'^(20\d{6})(?:\.0+)?$', s)
    return m.group(1) if m else ('' if not s or s.startswith('=') else s)

def candidates(rows, start, end, exclude):
    """rows: list of dicts with B,F,M,N,K (1-based index = i+1, only use start..end)."""
    rem, order, used = {}, [], set()
    seen = set()
    for r in range(start, end + 1):
        row = rows[r - 1] or {}
        b = norm(row.get('B'))
        if not b or b in seen: continue
        q = row.get('F')
        if not isinstance(q, (int, float)): continue
        seen.add(b); order.append(b); rem[b] = float(q)
    for r in range(start, end + 1):
        row = rows[r - 1] or {}
        m, n = norm(row.get('M')), norm(row.get('N'))
        ks = str(row.get('K') if row.get('K') is not None else '').strip()
        tw = re.match(r'^(-?\d+(?:\.\d+)?)\s*\+\s*(-?\d+(?:\.\d+)?)', ks)
        if tw and (m or n):
            a, bq = float(tw.group(1)), float(tw.group(2))
            if m:
                used.add(m)
                if m in rem: rem[m] = round(rem[m] - a, 2)
            if n:
                used.add(n)
                if n in rem: rem[n] = round(rem[n] - bq, 2)
            continue
        q = row.get('K')
        if isinstance(q, str) and re.match(r'^-?\d+(\.\d+)?$', q.strip()):
            q = float(q)
        if not isinstance(q, (int, float)) or not m: continue
        used.add(m)
        if m in rem: rem[m] = round(rem[m] - float(q), 2)
    ex = norm(exclude); ex_idx = order.index(ex) if ex in order else -1
    partial, fresh = [], []
    for i, b in enumerate(order):
        if b == ex: continue
        if rem.get(b, 0) <= 1e-9: continue
        if ex_idx >= 0 and i < ex_idx: continue
        (partial if b in used else fresh).append(b)
    return partial + fresh, rem

class LoxBatchRules1155(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, 'static', 'p_report.js'), encoding='utf-8') as f:
            cls.js = f.read()
        with open(os.path.join(ROOT, 'app', 'version.py'), encoding='utf-8') as f:
            cls.ver = f.read()
        with open(os.path.join(ROOT, 'static', 'v.json'), encoding='utf-8') as f:
            cls.vj = json.load(f)
        with open(os.path.join(ROOT, 'docs', 'LOX_BATCH_RULES.md'), encoding='utf-8') as f:
            cls.rules = f.read()

    def test_version(self):
        self.assertIn("VERSION = '1.1.55'", self.ver)
        self.assertEqual(self.vj.get('version'), '1.1.55')
        self.assertIn("'version': '1.1.55'", self.ver)

    def test_js_markers(self):
        for s in ('rLedgerBatchRemains', 'rLedgerNextCandidates', 'rLedgerBatchOptLabel',
                  '优先「还有剩余的批」', 'docs/LOX_BATCH_RULES.md', 'rLedgerTwoBatchWrite'):
            self.assertIn(s, self.js)
        self.assertNotIn('自动选未用批', self.js)
        # chip uses N when present
        self.assertIn("String(n || '').trim() ? n : m", self.js)

    def test_rules_doc(self):
        self.assertIn('单批', self.rules)
        self.assertIn('一天两批', self.rules)
        self.assertIn('20261008', self.rules)
        self.assertIn('不要写成负数', self.rules)
        self.assertIn('不强求每次都公式', self.rules)

    def test_scenario_1021_prefers_1008(self):
        # Minimal fixture mirroring live: 1001 inbound+outs → rem 1.83; 1008 after 市政府 11.69; 1009 unused 29
        rows = [{} for _ in range(20)]
        rows[0] = {'B': '20261001', 'F': 28.72}
        rows[1] = {'B': '20261008', 'F': 28}
        rows[2] = {'B': '20261009', 'F': 29}
        # outs on 1001 totaling 28.72-1.83=26.89
        rows[3] = {'M': '20261001', 'K': 6.48}
        rows[4] = {'M': '20261001', 'K': 6.16}
        rows[5] = {'M': '20261008', 'K': 16.31}  # 市政府
        rows[6] = {'M': '20261001', 'K': 6.42}
        rows[7] = {'M': '20261001', 'K': 6.75}
        # 6.48+6.16+6.42+6.75=25.81; 28.72-25.81=2.91 — adjust to hit 1.83
        # Use exact chain from analysis instead:
        rows = [{} for _ in range(12)]
        rows[0] = {'B': 20261001, 'F': 28.72}
        rows[1] = {'B': 20261008, 'F': 28.0}
        rows[2] = {'B': 20261009, 'F': 29.0}
        rows[3] = {'M': 20261001, 'K': '5.64+1.08=6.72', 'N': 20261001}  # noop weird
        # simpler: direct remains via outs
        rows = [{} for _ in range(10)]
        rows[0] = {'B': '20261001', 'F': 28.72}
        rows[1] = {'B': '20261008', 'F': 28}
        rows[2] = {'B': '20261009', 'F': 29}
        rows[3] = {'M': '20261001', 'K': 26.89}  # leave 1.83
        rows[4] = {'M': '20261008', 'K': 16.31}  # leave 11.69
        lst, rem = candidates(rows, 1, 5, '20261001')
        self.assertEqual(lst[0], '20261008')
        self.assertIn('20261009', lst)
        self.assertAlmostEqual(rem['20261008'], 11.69, places=2)
        self.assertAlmostEqual(rem['20261001'], 1.83, places=2)
        self.assertEqual(lst, ['20261008', '20261009'])

    def test_no_data_touch(self):
        self.assertNotRegex(self.js, r'(?i)DELETE\s+FROM\s+')
        self.assertNotIn('migrate', self.js.lower())

if __name__ == '__main__':
    unittest.main()
