"""截图/联调用演示数据（全假名）。用法: python tests/demo_data.py http://127.0.0.1:8080
依赖库里已有演示产品（先跑 tools/seed_demo.py）。PIN 默认 1002=演示录入甲。"""
import sys, json, urllib.request, datetime
U = sys.argv[1]
def call(p, b, pin='1002'):
    b = dict(b, pin=pin)
    r = urllib.request.Request(U + p, json.dumps(b).encode(), {'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(r).read())
t = datetime.date.today().isoformat()
boot = json.loads(urllib.request.urlopen(U + '/api/boot').read())
ps = {p['name']: p['id'] for p in boot['products']}
call('/api/out/save', {'data': {
    'date': t, 'kind': '销售出库', 'source': 'app手工单',
    'customer': '示例医院甲', 'contact': '演示联系人',
    'items': [{'product_id': ps.get('演示鼻氧管'), 'qty': 3}],
}})
print('demo ok (fake only)')
