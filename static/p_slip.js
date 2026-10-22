/* 称重计量单（照搬 v82）：净重自动算、流水号自动 +1、「下一张」同车续卸；下载 Word 与原单一样；打印版式同 Word */
'use strict';
const SL = { form: null, list: [], plates: [], blank: null };
const slNet = f => { const g = parseFloat(f.gross), t = parseFloat(f.tare); return isFinite(g) && isFinite(t) ? Math.round((g - t) * 100) / 100 : ''; };
const slDT = v => { if (!v) return ''; const m = /^(\d{4}-\d{2}-\d{2})[T ]+(\d{2}:\d{2})(?::(\d{2}))?/.exec(v); return m ? m[1] + '  ' + m[2] + ':' + (m[3] || '00') : String(v); };
const slNextSN = sn => { const m = /^(.*?)(\d+)$/.exec(sn || ''); return m ? m[1] + String(BigInt(m[2]) + 1n).padStart(m[2].length, '0') : (sn || ''); };
const slNow = () => { const d = new Date(), p = n => String(n).padStart(2, '0'); return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + 'T' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds()); };

Pages.slip = async el => {
  const r = await api('/api/slips' + (SL.q ? '?q=' + encodeURIComponent(SL.q) : '')); SL.list = r.items; SL.plates = r.plates; SL.blank = r.blank;
  if (!SL.form || !SL.form.id && SL.form.sn !== r.next_sn && !SL.form.plate) SL.form = Object.assign({}, r.blank);
  const un = SL.list.filter(s => !s.used_at).length;
  el.innerHTML = UI.ph('称重单', '净重自动算 · 流水号 +1', '同一辆车卸下一个点用「下一张」。下载的 Word 与原称重计量单一样。',
    `<span class="muted" style="font-size:13px">已开 ${SL.list.length} 张${un ? ` · <span class="w7">${un} 张未登记到液氧表</span>` : ''}</span>`)
    + `<div class="grid2 page-entry page-entry-slip"><div class="card page-card" id="slF"></div><div class="card page-card" id="slH"></div></div>`;
  slForm(el); slHist(el);
};
function slForm(el) {
  const f = SL.form, net = slNet(f), box = $('#slF', el);
  const inp = (lbl, k, attrs, hint) => `<div><span class="lab">${lbl}${hint ? ` <span class="muted">${hint}</span>` : ''}</span><input class="inp" data-f="${k}" ${attrs || ''} value="${esc(f[k] == null ? '' : f[k])}"></div>`;
  box.innerHTML = `<div class="card-h"><h2>${f.id ? '修改称重单 ' + esc(f.sn) : '新开称重单'}</h2>${f.id ? '<a class="link d" id="slNew">新开一张</a>' : ''}</div>
    <div class="row r2">${inp('时间', 'time', 'type="datetime-local" step="1"')}${inp('本单流水号', 'sn', '', '自动 +1，可改')}
      ${inp('车号', 'plate', 'list="slPl" placeholder="如 陕J65758"')}${inp('货名', 'goods')}
      ${inp('毛重（KG）', 'gross', 'inputmode="decimal"')}${inp('皮重（KG）', 'tare', 'inputmode="decimal"')}</div>
    <div class="sl-net"><span>净重（KG）<span class="muted">= 毛重 − 皮重</span></span><b id="slNet">${net === '' ? '—' : fmtN(net)}</b><span class="muted" id="slT">${net === '' ? '' : '= ' + (net / 1000).toFixed(2) + ' 吨'}</span></div>
    <div class="row r2">${inp('毛重时间', 'gt', 'type="datetime-local" step="1"')}${inp('空重时间', 'tt', 'type="datetime-local" step="1"')}
      ${inp('发货单位', 'sender', 'placeholder="可不填"')}${inp('收货单位', 'recv', 'placeholder="可不填"')}
      ${inp('司机', 'driver', 'placeholder="可不填"')}${inp('过磅员', 'oper', 'placeholder="可不填"')}</div>
    <div style="margin-top:10px">${inp('备注', 'note')}</div>
    <datalist id="slPl">${SL.plates.map(p => `<option value="${esc(p)}">`).join('')}</datalist>
    <div class="sl-btns"><button class="btn pri" id="slSD">保存并下载 Word</button><button class="btn" id="slS">只保存</button><button class="btn" id="slP">保存并打印</button>
      <button class="btn" id="slNx" title="同一辆车卸下一个点：毛重 = 这张的皮重，毛重时间 = 这张的空重时间">下一张（同车续卸）</button></div>`;
  $$('[data-f]', box).forEach(i => i.addEventListener('input', () => { f[i.dataset.f] = i.value.trim(); const n = slNet(f); $('#slNet', box).textContent = n === '' ? '—' : fmtN(n); $('#slT', box).textContent = n === '' ? '' : '= ' + (n / 1000).toFixed(2) + ' 吨'; }));
  if ($('#slNew', box)) $('#slNew', box).onclick = () => { SL.form = Object.assign({}, SL.blank, { time: slNow(), tt: slNow() }); slForm(el); };
  $('#slSD', box).onclick = () => slSave(el, 'dl').catch(fail);
  $('#slS', box).onclick = () => slSave(el).catch(fail);
  $('#slP', box).onclick = () => slSave(el, 'print').catch(fail);
  $('#slNx', box).onclick = () => {
    const p = SL.form; const maxSn = SL.list.map(x => x.sn).sort().pop() || p.sn;
    SL.form = Object.assign({}, SL.blank, { time: slNow(), tt: slNow(), plate: p.plate, goods: p.goods, sender: p.sender, recv: p.recv, driver: p.driver, oper: p.oper, gross: p.tare, gt: p.tt, sn: slNextSN(p.id ? (maxSn > p.sn ? maxSn : p.sn) : p.sn) });
    slForm(el); toast('已带入：毛重 = 上一张皮重，毛重时间 = 上一张空重时间');
  };
}
async function slSave(el, then) {
  const f = SL.form;
  if (!f.plate) throw new Error('请填车号');
  if (!(parseFloat(f.gross) > 0) || f.tare === '' || !(parseFloat(f.tare) >= 0)) throw new Error('请填毛重和皮重');
  if (!(slNet(f) > 0)) throw new Error('净重小于等于0，请检查毛重/皮重');
  let r;
  try { r = await save('/api/slip/save', { data: f }, '保存称重单'); }
  catch (e) {
    if (e.code !== 409) throw e;
    if (!await confirmBox(esc(e.message) + '，仍然保存？', '仍然保存')) return;
    r = await save('/api/slip/save', { data: f, force: 1 }, '保存称重单');
  }
  toast('已保存称重单 ' + r.sn);
  SL.form = Object.assign({}, f, { id: r.id, sn: r.sn });
  if (then === 'dl') download('/api/slip.docx?id=' + r.id);
  if (then === 'print') slPrint(r.id);
  await Pages.slip(el);
}
function slHist(el) {
  const box = $('#slH', el), l = SL.list;
  box.innerHTML = `<div class="tools"><div class="tg"><h2 style="margin-right:6px;font-size:15px">已开称重单</h2><span class="muted">${l.length} 张</span><input class="inp sm" id="slQ" placeholder="搜流水号、车号、备注" value="${esc(SL.q || '')}" style="width:170px;margin-left:8px"></div><span class="sp"></span>
      <div class="tg acts"><button class="btn sm" id="slToLox">勾选的 → 登记到液氧表</button><button class="btn sm" id="slPL">打印清单</button><button class="btn sm" id="slXL">导出 Excel</button>${LC.btn('slip')}</div></div>
    ${l.length ? `<div class="tw"><table class="t" id="slTbl"><thead><tr><th></th><th>时间</th><th>流水号</th><th>车号</th><th class="n">毛重</th><th class="n">皮重</th><th class="n">净重</th><th>液氧表</th><th>备注</th><th></th></tr></thead><tbody>
    ${l.map(s => `<tr class="${SL.form && SL.form.id === s.id ? 'cur' : ''}"><td><input type="checkbox" value="${s.id}"></td><td class="w">${esc(slDT(s.time))}</td><td>${esc(s.sn)}</td><td>${esc(s.plate)}</td><td class="n">${fmtN(s.gross)}</td><td class="n">${fmtN(s.tare)}</td><td class="n"><b>${fmtN(s.net)}</b></td>
      <td class="w">${s.used_at ? '<span class="tag ok">已登记</span>' : '<span class="tag warn">未登记</span>'}</td>
      ${rmkTd(s.note)}
      ${rowActs({ ph: [0], main: ['修改', `data-ed="${s.id}"`], menu: [['下载 Word', `data-dl="${s.id}"`], ['打印', `data-pr="${s.id}"`], ['留痕', `data-au="${s.id}"`], ['删除', `data-del="${s.id}"`, 1]] })}</tr>`).join('')}</tbody></table></div>` : '<div class="empty">没有记录 · 还没有称重单</div>'}`;
  if (l.length) LC.apply($('#slTbl', box), 'slip', [
    { k: '_ck', label: '选', w: 36 }, { k: 'time', label: '时间', w: 120 }, { k: 'sn', label: '流水号', w: 100 },
    { k: 'plate', label: '车号', w: 80 }, { k: 'gross', label: '毛重', w: 64 }, { k: 'tare', label: '皮重', w: 64 },
    { k: 'net', label: '净重', w: 64 }, { k: 'lox', label: '液氧表', w: 72 }, { k: 'rmk', label: '备注', w: 120, wrap: 1 },
    { k: '_act', label: '操作', w: 110 }
  ]);
  let qt; $('#slQ', box).oninput = e => { clearTimeout(qt); const v = e.target.value; qt = setTimeout(async () => { SL.q = v; const r = await api('/api/slips' + (v ? '?q=' + encodeURIComponent(v) : '')); SL.list = r.items; slHist(el); const i = $('#slQ', el); i.focus(); i.setSelectionRange(v.length, v.length); }, 300); };
  $('#slPL', box).onclick = () => printApi('/api/slips.xlsx', { landscape: true }).catch(fail);
  $('#slXL', box).onclick = () => download('/api/slips.xlsx');
  $('#slToLox', box).onclick = () => {
    const ids = $$('tbody input:checked', box).map(x => +x.value); if (!ids.length) return toast('请先勾选称重单', true);
    const sel = l.filter(s => ids.includes(s.id)).sort((a, b) => (a.time || '').localeCompare(b.time || '') || (a.sn || '').localeCompare(b.sn || ''));
    RP.pendingDlv = { date: rFromIso((sel[0].time || '').slice(0, 10)) || rToday(), plate: sel[0].plate, lines: sel.map(s => ({ place: '', tons: (s.net / 1000).toFixed(2) })), slipIds: ids, msg: '已从 ' + sel.length + ' 张称重单带入，请选每张卸到哪里' };
    location.hash = 'report/lox';
  };
  box.onclick = async e => {
    const t = e.target;
    if (t.dataset.dl) download('/api/slip.docx?id=' + t.dataset.dl);
    if (t.dataset.pr) slPrint(+t.dataset.pr);
    if (t.dataset.ed) { const s = l.find(x => x.id === +t.dataset.ed); SL.form = Object.assign({}, s, { gross: s.gross, tare: s.tare }); slForm(el); slHist(el); }
    if (t.dataset.au) { const x = await api('/api/slip/one?id=' + t.dataset.au); dialog('留痕 · ' + x.sn, `<table class="t"><tbody>${x.audit.map(a => `<tr><td class="w">${fmtTs(a.ts)}</td><td>${esc(a.person)}</td><td>${esc(a.action)}</td><td>${esc(a.summary)}</td></tr>`).join('')}</tbody></table>`); }
    if (t.dataset.del) { const s = l.find(x => x.id === +t.dataset.del); if (await confirmDelete('slip', s.id, '/api/slip/delete').catch(er => { fail(er); return false; })) { try { if (SL.form && SL.form.id === s.id) SL.form = null; Pages.slip(el); } catch (er) { fail(er); } } }
  };
}
/** 打印：版式同原 Word（A4 竖向，华文中宋，标题 18 号，表格 4 列 1702/3402/1701/2693） */
async function slPrint(id) {
  const s = await api('/api/slip/one?id=' + id), v = s.values;
  const W = [1702, 3402, 1701, 2693], tw = W.reduce((a, b) => a + b, 0);
  const tr = (a, b, c, d, h) => `<tr style="height:${(h / 20 * 0.3528).toFixed(1)}mm"><td class="sk">${a}</td><td>${esc(b)}</td><td class="sk">${c}</td><td>${esc(d)}</td></tr>`;
  printHtml(`<style>.print-host .sl{font-family:"华文中宋","STZhongsong","宋体",serif;font-size:10pt}.print-host .sl h1{font-size:18pt;font-weight:bold;text-align:center;margin:0 0 8px}
    .print-host .sl .info{white-space:pre;margin-bottom:4px}.print-host .sl table{table-layout:fixed;font-size:10pt}.print-host .sl td{text-align:center;vertical-align:middle}.print-host .sl .ft{margin-top:6px;white-space:pre}</style>
    <div class="sl"><h1>演示气体有限公司（称重计量单）</h1><div class="info">时间：${esc(v.TIME)}          本单流水号：${esc(v.SN)}          计量单位：KG</div>
    <table><colgroup>${W.map(w => `<col style="width:${(w / tw * 100).toFixed(2)}%">`).join('')}</colgroup>
    ${tr('车号', v.PLATE, '毛重', v.GROSS, 454)}${tr('货名', v.GOODS, '皮重', v.TARE, 509)}${tr('发货单位', v.SENDER, '净重', v.NET, 474)}${tr('收货单位', v.RECV, '毛重时间', v.GT, 454)}${tr('司机', v.DRIVER, '空重时间', v.TT, 454)}${tr('过磅员', v.OPER, '备注', v.NOTE, 454)}</table>
    <div class="ft">一式三联   第一联称重（白）   第二联客户（红）   第三联财务（黄）</div></div>`, { margin: '6mm 25mm 22mm 25mm' });
}
