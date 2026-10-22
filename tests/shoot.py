"""截图：桌面 1440 宽 + 手机 390 宽。用法：python tests/shoot.py http://127.0.0.1:8091"""
import sys, os, asyncio
from playwright.async_api import async_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8091'
ONLY = sys.argv[2].split(',') if len(sys.argv) > 2 else None   # 只截名字以这些开头的
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'screens')
DESK = [('d01_首页', '#home'), ('d02_出库_单笔', '#out/single'), ('d03_出库_批量', '#out/batch'), ('d04_出库_记录', '#out/list'),
        ('d05a_钢瓶交接表', '#daily/cyl'), ('d05b_产品交接表', '#daily/prod'), ('d05c_产品出入库情况汇总', '#daily/sum'), ('d05d_表格设置', '#daily/layout'), ('d06_到货', '#arrival'), ('d07_产品库存', '#stock/list'), ('d08_盘点', '#stock/count'),
        ('d09_批次追溯', '#stock/batch'), ('d10_U8账面对照', '#stock/u8'), ('d11_库房杂物', '#misc'), ('d12_待补全', '#pending'),
        ('d13_借用_借出登记', '#loan/new'), ('d13b_借用_记录', '#loan/list'), ('d13c_借用_按单位', '#loan/org'), ('d13d_借用_补录', '#loan/batch'), ('d04b_领用出库单', '#out/ly'), ('d14a_报表_换算表', '#report/conv'), ('d14b_报表_入出库记录', '#report/ledger'), ('d14c_报表_到货总数', '#report/stock'), ('d14d_报表_液氧表', '#report/lox'), ('d14e_报表_4号院', '#report/yard4'), ('d15_称重单', '#slip'), ('d16_数据备份', '#backup/backup'),
        ('d17_回收站', '#backup/trash'), ('d18_操作记录', '#backup/audit'), ('d19_设置', '#settings')]
PHONE = [('m01_首页', '#'), ('m02_出库', '#out'), ('m03_出入库情况_钢瓶', '#cyl/cyl:6922'), ('m03b_出入库情况_产品', '#cyl/prod:6984'), ('m04_库房杂物', '#misc'), ('m05_待补全快速记', '#pend'), ('m06_待补全清单', '#mine'), ('m07_扫码拍照', '#cam/abc123'), ('m09_借用归还', '#loan'), ('m10_归还', '#ret/LAST')]
async def main():
    os.makedirs(OUT, exist_ok=True); errs = []
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
        for kind, items, vp, path in (('desk', DESK, {'width': 1440, 'height': 900}, '/'), ('phone', PHONE, {'width': 390, 'height': 844}, '/m/')):
            ctx = await b.new_context(viewport=vp, locale='zh-CN', device_scale_factor=2 if kind == 'phone' else 1, is_mobile=kind == 'phone', has_touch=kind == 'phone')
            pg = await ctx.new_page()
            pg.on('pageerror', lambda e, k=kind: errs.append('%s: %s' % (k, e)))
            pg.on('console', lambda m, k=kind: m.type == 'error' and errs.append('%s console: %s' % (k, m.text)))
            await pg.goto(BASE + path); await pg.wait_for_timeout(800)
            for name, h in items:
                if ONLY and not any(name.startswith(o) for o in ONLY): continue
                if 'LAST' in h: h = h.replace('LAST', str(await pg.evaluate("fetch('/api/loans?status=open').then(r => r.json()).then(d => d.items.find(l => l.orgs.length > 1).id)")))
                await pg.evaluate('h => location.hash = h', h); await pg.wait_for_timeout(1200)
                hgt = await pg.evaluate('document.documentElement.scrollHeight')
                if kind == 'phone':  # 底部固定栏：把视口拉到整页高，截出来才在最底下
                    await pg.set_viewport_size({'width': vp['width'], 'height': min(hgt, 2400)}); await pg.wait_for_timeout(200)
                    hgt = await pg.evaluate('document.documentElement.scrollHeight')
                cap = 1700 if kind == 'desk' else 2400
                await pg.screenshot(path=os.path.join(OUT, name + '.png'), full_page=True, clip={'x': 0, 'y': 0, 'width': vp['width'], 'height': min(hgt, cap)})
                print('saved', name)
                if kind == 'phone': await pg.set_viewport_size(vp)
            if kind == 'phone' and not ONLY:  # PIN 键盘
                await pg.evaluate("location.hash='#pend'"); await pg.wait_for_timeout(600)
                await pg.fill('#pT', '张总'); await pg.fill('#pW', '便携式制氧机'); await pg.click('#pSave'); await pg.wait_for_timeout(500)
                await pg.screenshot(path=os.path.join(OUT, 'm08_输入密码.png')); print('saved m08')
            await ctx.close()
        await b.close()
    print('ERRORS:', len(errs)); [print(' ', e) for e in errs]
asyncio.run(main())
