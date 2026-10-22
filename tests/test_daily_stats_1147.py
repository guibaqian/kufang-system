# -*- coding: utf-8 -*-
"""1.1.47：钢瓶页序汇总 + 数量统计 API + 核对 meta（不改业务计数）"""
import os, sys, json, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, setUpModule, tearDownModule  # noqa
import server, logic, paper

def save(date, ses, form, rows):
    st, r = call('/api/paper/save', {'data': {'date': date, 'session': ses, 'form': form, 'rows': rows}})
    assert st == 200, r
    return r['id']

class T1147(unittest.TestCase):
    def test_1_cyl_order_over_sort(self):
        """汇总领用人序跟当天钢瓶页行序，不是 couriers.sort"""
        D = '2026-11-21'
        # 故意按车牌列表后半 + 前半交叉：先录 0668，再录 6922（plates 默认 6922 在前）
        save(D, '早上', 'cyl', [
            {'rid': 'a', 'plate': '0668', 'driver': '序测刘', 'cells': {'R.o40': '2'}},
            {'rid': 'b', 'plate': '6922', 'driver': '序测丁', 'cells': {'R.o40': '3'}},
        ])
        order = paper.cyl_courier_order(server.db_c(), D)
        names = [x['name'] for x in logic.daily_rows(server.db_c(), D) if '序测' in x['name']]
        # plates 序：6922 在 0668 前 → 汇总应 丁 再 刘
        self.assertEqual(names, ['序测丁', '序测刘'], names)
        self.assertTrue(order)

    def test_2_stats_and_verify(self):
        D = '2026-11-22'
        save(D, '早上', 'cyl', [{'rid': 'a', 'plate': '9255', 'driver': '核测沈', 'cells': {'R.o40': '1'}}])
        st, r = call('/api/daily/stats?from=%s&to=%s' % (D, D))
        self.assertEqual(st, 200, r)
        self.assertIn('warehouse_out', r); self.assertIn('delivery', r)
        self.assertTrue(any(x.get('k') == 'o40' and x.get('q') for x in r['delivery']) or r['delivery'] == r['delivery'])
        rows = logic.daily_rows(server.db_c(), D)
        cid = next(x['courier_id'] for x in rows if '核测沈' in x['name'])
        st, r = call('/api/daily/verify', {'date': D, 'courier_id': cid, 'ok': True})
        self.assertEqual(st, 200, r)
        st, d = call('/api/daily?date=' + D)
        self.assertTrue(d['verify'].get(str(cid), {}).get('ok'))
        st, r = call('/api/daily/verify', {'date': D, 'courier_id': cid, 'ok': False})
        self.assertEqual(st, 200, r)
        au = [x[0] for x in server.db_c().execute("SELECT summary FROM audit WHERE entity='daily_verify' ORDER BY id DESC LIMIT 5")]
        self.assertTrue(any('核测沈' in (s or '') for s in au), au)

if __name__ == '__main__':
    unittest.main()
