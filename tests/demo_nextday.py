"""次日清点演示数据（只写到临时数据目录）：python tests/demo_nextday.py URL 1|2
阶段 1：10.19 早上 + 中午；阶段 2：10.20 早上（10.19 才算定）；阶段 3：10.21 早上（10.20 才算定）"""
import sys, json, urllib.request
U, PH = sys.argv[1], sys.argv[2]
def call(p, b=None, pin='1002'):
    if b is None: return json.loads(urllib.request.urlopen(U + p).read())
    r = urllib.request.Request(U + p, json.dumps(dict(b, pin=pin)).encode(), {'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(r).read())
boot = call('/api/boot'); m = boot['daily_cols']['map']
def save(date, ses, form, rows): return call('/api/paper/save', {'data': {'date': date, 'session': ses, 'form': form, 'rows': rows}})
if PH == '1':
    for k in ('shb', 'byg', 'xyy', 'zt', 'xyg', 'c40', 'c10'):
        if m.get(k): call('/api/count/save', {'product_id': m[k], 'qty': 300, 'date': '2026-10-18'})
    save('2026-10-19', '早上', 'cyl', [{'rid': 'p_6922', 'plate': '6922', 'driver': '6922丁增', 'cells': {'R.o40': '30', 'R.o10': '8', 'R.xyg': '4'}},
                                       {'rid': 'p_9255', 'plate': '9255', 'driver': '9255沈兴德', 'cells': {'R.o40': '10'}},
                                       {'rid': 'p_5928', 'plate': '5928', 'driver': '5928旦真', 'cells': {'L.e40': '6', 'R.o40': '12'}}])
    save('2026-10-19', '早上', 'prod', [{'rid': 'p_6922', 'plate': '6922', 'cells': {'L.shb': '5', 'L.byg': '3', 'R.shb': '10', 'R.byg': '20', 'R.xyy': '2'}},
                                        {'rid': 'p_9255', 'plate': '9255', 'cells': {'R.shb': '3'}},
                                        {'rid': 'p_5928', 'plate': '5928', 'cells': {'L.shb': '12', 'L.byg': '30', 'L.xyy': '1退', 'R.shb': '4', 'R.byg': '20'}}])   # 旦真：18 号晚上车上还剩 12 个湿化杯、30 根鼻氧管（1.1.1 这天起点当 0 → 负数）
    save('2026-10-19', '中午', 'cyl', [{'rid': 'p_6922', 'plate': '6922', 'driver': '6922丁增', 'cells': {'L.e40': '18', 'L.f40': '1', 'L.e10': '4', 'R.o40': '10', 'R.o10': '2'}},
                                       {'rid': 'p_9255', 'plate': '9255', 'driver': '9255沈兴德', 'driver_r': '6984付伟松', 'cells': {'L.e40': '6', 'R.o40': '8'}}])
    save('2026-10-19', '中午', 'prod', [{'rid': 'p_6922', 'plate': '6922', 'cells': {'L.shb': '4退', 'L.byg': '2', 'R.shb': '5'}, 'hand': [{'product_id': m['zt'], 'qty': 1}]},
                                        {'rid': 'p_9255', 'plate': '9255', 'cells': {'L.shb': '2', 'R.shb': '6'}}])
elif PH == '2':
    save('2026-10-20', '早上', 'cyl', [{'rid': 'p_6922', 'plate': '6922', 'driver': '6922丁增', 'cells': {'L.e40': '20', 'L.f40': '2', 'L.e10': '5', 'L.r40': '1', 'R.o40': '28', 'R.o10': '6'}},
                                       {'rid': 'p_9255', 'plate': '9255', 'driver': '6984付伟松', 'cells': {'L.e40': '7', 'R.o40': '9'}},
                                       {'rid': 'p_5928', 'plate': '5928', 'driver': '5928旦真', 'cells': {'L.e40': '11', 'R.o40': '10'}}])
    save('2026-10-20', '早上', 'prod', [{'rid': 'p_6922', 'plate': '6922', 'cells': {'L.shb': '2退', 'L.byg': '6', 'R.shb': '8', 'R.byg': '10'}},
                                        {'rid': 'p_9255', 'plate': '9255', 'cells': {'L.shb': '3', 'R.shb': '4'}},
                                        {'rid': 'p_5928', 'plate': '5928', 'cells': {'L.shb': '10', 'L.byg': '35', 'R.shb': '2'}}])
else:   # 阶段 3：10.21 早上（10.20 才算定；10.21 早上 6922 写了退的 3 个湿化杯 10.21 入库，写没写退 10.20 都一样）
    save('2026-10-21', '早上', 'cyl', [{'rid': 'p_6922', 'plate': '6922', 'driver': '6922丁增', 'cells': {'L.e40': '25', 'L.e10': '6', 'R.o40': '30'}},
                                       {'rid': 'p_9255', 'plate': '9255', 'driver': '6984付伟松', 'cells': {'L.e40': '9'}}])
    save('2026-10-21', '早上', 'prod', [{'rid': 'p_6922', 'plate': '6922', 'cells': {'L.shb': '3退', 'L.byg': '4', 'R.shb': '6'}},
                                        {'rid': 'p_9255', 'plate': '9255', 'cells': {'L.shb': '1'}}])
DAY = '2026-10-20' if PH == '3' else '2026-10-19'
d = call('/api/daily?date=' + DAY); print(DAY)
for x in d['merged']:
    v = x['vals']; neg = {k[3:]: (x['calc'][k], x['calc'][k] - v.get('v0_' + k[4:], 0)) for k in x['calc'] if k.startswith('net_')}
    print('  用量 1.1.2 / 1.1.1（起点当 0）:', {k: a for k, a in neg.items() if a[0] or a[1]})
    print(x['name'], 'pending' if x.get('pending') else '', {k: v for k, v in x['vals'].items() if not k.startswith('b_')}, {k: v for k, v in x['calc'].items() if v}, x['note'])
