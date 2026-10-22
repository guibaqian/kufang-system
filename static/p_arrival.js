/* 到货（= 报表「库存及到货总数」）：快速登记、待入U8、U8 截图离线识别、批次 */
'use strict';
const AR = { f: 'pending', q: '', lines: null, sel: new Set() };
function newArrLine() { return { product_id: null, name: '', spec: '', unit: '', qty: '', dest: '', remark: '', batch_no: '', prod_date: '', expiry: '', u8: '' }; }
const U8CN = { '待入U8': '待入U8', '已入U8': '已入U8', '不入U8': '不用入U8' };

Pages.arrival = async (el) => {
  if (!AR.lines) AR.lines = [newArrLine()];
  if (!AR.head) AR.head = { date: today(), kind: '到货', supplier: '', u8_status: '待入U8' };
  if (!['待入U8', '不入U8'].includes(AR.head.u8_status)) AR.head.u8_status = '待入U8';
  // 首页「待入U8」KPI：强制筛待入U8
  try {
    if (sessionStorage.getItem('homeArrivalU8') === '1') {
      sessionStorage.removeItem('homeArrivalU8');
      AR.f = 'pending';
    }
  } catch (e) { }
  el.innerHTML = UI.ph('到货', '到货算进库存 · 待入U8 记单号', '包括直接送外单位的。入完 U8 后记存货号、入库单号。',
    `<button class="btn" id="arOcr">识别 U8 入库单截图</button>`)
    + `<div class="grid2 page-entry"><div class="card page-card" id="arForm"></div><div class="sticky page-side-col"><div class="card page-card page-side"><div class="card-h"><h2>到货单照片</h2><small class="muted">可多张 · 照片库 / 持续拍</small></div><div id="arPh"></div></div>
      <div class="card page-card page-act"><button class="btn pri big full" id="arSave">登记到货</button></div></div></div>
    <div class="card page-card" style="margin-top:14px"><div class="tools">
      <div class="tg"><div class="seg" id="arF"><button data-f="">全部</button><button data-f="pending">待入U8 <b id="arPN"></b></button><button data-f="done">已入U8</button><button data-f="no">不用入U8</button><button data-f="other">其他入库</button></div>
      <input class="inp" id="arQ" placeholder="搜名称、规格、存货单位、批号、入库单号、备注" style="width:240px" value="${esc(AR.q)}"></div>
      <span class="sp"></span><div class="ar-ops tg acts" title="U8 与打印">
        <button class="btn sm" id="arMark" disabled>标记已入U8</button>
        <button class="btn sm" id="arNo" disabled>标记不用入U8</button>
        <button class="btn sm" id="arPrint">打印</button>${LC.btn('arrival')}
      </div></div><div id="arT"></div></div>`;
  const ph = photoBox($('#arPh', el), AR.photos || [], { onchange: p => AR.photos = p, title: '到货单照片', label: '到货单照片' });
  drawArrForm($('#arForm', el));
  $('#arSave', el).onclick = async () => {
    try {
      const ls = AR.lines.filter(l => (l.product_id || l.name.trim()) && +l.qty > 0);
      if (!ls.length) return toast('请选产品并填数量', true);
      const lines = ls.map(l => Object.assign({}, AR.head, l, { qty: +l.qty, u8_status: l.u8 || AR.head.u8_status }));
      await save('/api/arrival/save', { lines, photo_ids: ph.ids }, '登记到货');
      toast('已登记 ' + ls.length + ' 行'); AR.lines = [newArrLine()]; AR.photos = []; Pages.arrival(el);
    } catch (e) { fail(e); }
  };
  $$('#arF button', el).forEach(b => { b.classList.toggle('on', b.dataset.f === AR.f); b.onclick = () => { AR.f = b.dataset.f; AR.sel.clear(); $$('#arF button', el).forEach(x => x.classList.toggle('on', x === b)); loadArr(el); }; });
  let tm; $('#arQ', el).oninput = e => { clearTimeout(tm); tm = setTimeout(() => { AR.q = e.target.value; loadArr(el); }, 250); };
  $('#arMark', el).onclick = () => markU8(el, [...AR.sel]);
  $('#arNo', el).onclick = () => setU8(el, [...AR.sel].map(id => ({ id, u8_status: '不入U8' })), '标记不用入U8');
  $('#arOcr', el).onclick = () => ocrU8(el).catch(fail);
  $('#arPrint', el).onclick = () => printHtml(`<div class="ttl">库存及到货总数</div><table><tr><th>日期</th><th>存货名称</th><th>规格型号</th><th>单位</th><th>数量</th><th>存货单位</th><th>备注</th><th>状态</th><th>存货号</th><th>入库单号</th><th>入库单拿走情况</th></tr>${(AR.data || []).map(a => `<tr><td>${esc(a.date)}</td><td class="l">${esc(a.name)}</td><td>${esc(a.spec)}</td><td>${esc(a.unit)}</td><td>${fmtN(a.qty)}</td><td>${esc(a.dest)}</td><td class="l">${esc(a.remark)}</td><td>${esc(U8CN[a.u8_status] || a.u8_status)}</td><td>${esc(a.inv_code)}</td><td>${esc(a.receipt_no)}</td><td>${esc(a.taken_note)}</td></tr>`).join('')}</table>`, { landscape: true, font: '7pt', margin: '6mm', fit: true, titleSize: '12pt', dense: true });
  await loadArr(el);
};

function drawArrForm(box) {
  const h = AR.head;
  box.innerHTML = `<div class="row r4"><div><span class="lab">日期</span><input class="inp" type="date" data-h="date" value="${esc(h.date)}"></div>
    <div><span class="lab">类型</span><select class="inp" data-h="kind"><option ${h.kind === '到货' ? 'selected' : ''}>到货</option><option ${h.kind === '其他入库' ? 'selected' : ''}>其他入库</option></select></div>
    <div><span class="lab">供应商 / 退回人</span><input class="inp" data-h="supplier" value="${esc(h.supplier)}" placeholder="可空"></div>
    <div><span class="lab">要不要入U8</span><div class="seg" id="arU8"><button data-u="待入U8" class="${h.u8_status === '待入U8' ? 'on' : ''}">需要入U8</button><button data-u="不入U8" class="${h.u8_status === '不入U8' ? 'on' : ''}">不用入U8</button></div></div></div>
    <div class="sec-h" style="margin-top:16px"><h2>到了什么</h2><small>${h.kind === '其他入库' ? '如：客户退回空瓶' : '一张到货单可以几行'}</small></div>
    <div id="arLines"></div><button class="btn sm" id="arAddL" style="margin-top:8px">＋ 再加一行</button>`;
  $$('[data-h]', box).forEach(i => i.onchange = () => { h[i.dataset.h] = i.value; if (i.dataset.h === 'kind') { h.u8_status = i.value === '其他入库' ? '不入U8' : '待入U8'; AR.lines.forEach(l => l.u8 = ''); drawArrForm(box); } });
  $('#arU8', box).onclick = e => { const b = e.target.closest('[data-u]'); if (!b) return; h.u8_status = b.dataset.u; AR.lines.forEach(l => l.u8 = ''); drawArrForm(box); };
  const L = $('#arLines', box);
  const draw = () => {
    L.innerHTML = AR.lines.map((l, i) => {
      const p = l.product_id ? P.byId(l.product_id) : null;
      return `<div style="padding:10px 0;border-top:${i ? '1px solid var(--line2)' : '0'}"><div class="row" style="grid-template-columns:2fr 1fr .7fr .8fr 1.2fr auto;gap:8px;align-items:end">
        <div><span class="lab">产品（选清单里的，或直接写存货名称）</span><input class="inp" data-i="${i}" data-k="pname" value="${esc(p ? p.label : l.name)}" autocomplete="off"></div>
        <div><span class="lab">规格型号</span><input class="inp" data-i="${i}" data-k="spec" value="${esc(l.spec)}"></div>
        <div><span class="lab">单位</span><input class="inp" data-i="${i}" data-k="unit" value="${esc(l.unit)}"></div>
        <div><span class="lab">数量</span><input class="inp num" data-i="${i}" data-k="qty" value="${esc(l.qty)}" inputmode="decimal"></div>
        <div><span class="lab">存货单位（送外单位才填）</span><input class="inp" data-i="${i}" data-k="dest" value="${esc(l.dest)}" list="arDest"></div>
        <button class="link d" data-x="${i}" style="height:36px">✕</button></div>
        ${p && p.batch_managed ? `<div class="row r4" style="margin-top:8px"><div><span class="lab">批号</span><input class="inp" data-i="${i}" data-k="batch_no" value="${esc(l.batch_no)}"></div>
          <div><span class="lab">生产日期</span><input class="inp" type="date" data-i="${i}" data-k="prod_date" value="${esc(l.prod_date)}"></div>
          <div><span class="lab">有效期至</span><input class="inp" type="date" data-i="${i}" data-k="expiry" value="${esc(l.expiry)}"></div><div class="hint" style="align-self:center">批次管理产品：出库默认先进先出</div></div>` : ''}
        ${!p && l.name ? '<div class="hint">不在产品清单里：只记到货表，不进库存。要进库存请选清单里的产品（没有就先在「产品与库存」里加）。</div>' : ''}
        <div class="split" style="margin-top:8px"><input class="inp sm" data-i="${i}" data-k="remark" value="${esc(l.remark)}" placeholder="备注" style="flex:1">
          <label class="muted w" style="font-size:13px" title="这一行单独设置"><input type="checkbox" data-nu="${i}" ${(l.u8 || h.u8_status) === '不入U8' ? 'checked' : ''}> 不用入U8${p && p.no_u8 ? '（产品默认）' : ''}</label></div></div>`;
    }).join('') + `<datalist id="arDest"><option value="示例医院甲"><option value="示例单位乙"></datalist>`;
    $$('[data-k="pname"]', L).forEach(inp => autoComplete(inp, async q => P.search(q).slice(0, 10), p => {
      const l = AR.lines[+inp.dataset.i]; l.product_id = p.id; l.name = p.name; l.spec = p.spec || ''; l.unit = p.unit || ''; l.u8 = p.no_u8 ? '不入U8' : ''; draw();
    }, (p, q) => `<span>${hl(p.label, q)}</span><small>${esc(p.category)}${p.batch_managed ? ' · 批次' : ''}</small>`));
  };
  L.addEventListener('input', e => { const t = e.target; if (!t.dataset.k) return; const l = AR.lines[+t.dataset.i]; if (t.dataset.k === 'pname') { l.product_id = null; l.name = t.value; } else l[t.dataset.k] = t.value; });
  L.addEventListener('change', e => { if (e.target.dataset.k === 'pname') draw(); if (e.target.dataset.nu) AR.lines[+e.target.dataset.nu].u8 = e.target.checked ? '不入U8' : '待入U8'; });
  L.addEventListener('click', e => { if (e.target.dataset.x) { AR.lines.splice(+e.target.dataset.x, 1); if (!AR.lines.length) AR.lines.push(newArrLine()); draw(); } });
  $('#arAddL', box).onclick = () => { AR.lines.push(newArrLine()); draw(); };
  draw();
}

async function loadArr(el) {
  const qs = { pending: 'status=待入U8', done: 'status=已入U8', no: 'status=不入U8', other: 'kind=其他入库', '': '' }[AR.f] + (AR.q ? '&q=' + encodeURIComponent(AR.q) : '');
  const r = await api('/api/arrivals?' + qs); AR.data = r.items;
  $('#arPN', el).textContent = r.pending_u8 || '';
  const sel = AR.sel;
  $('#arT', el).innerHTML = r.items.length ? `<div class="tw"><table class="t" id="arTbl"><thead><tr><th style="width:28px"><input type="checkbox" id="arAll"></th><th>日期</th><th>存货名称</th><th>规格型号</th><th>单位</th><th class="n">数量</th><th>存货单位</th><th>备注</th><th>U8</th><th>存货号</th><th>入库单号</th><th>批号</th><th></th></tr></thead><tbody>
    ${r.items.map(a => `<tr><td><input type="checkbox" data-s="${a.id}" ${sel.has(a.id) ? 'checked' : ''}></td><td class="w">${esc(a.date)}</td><td>${esc(a.name)}${a.kind === '其他入库' ? ' <span class="tag">其他入库</span>' : ''}${!a.product_id ? ' <span class="tag" title="没有对应产品，不进库存">未关联</span>' : ''}</td>
      <td>${esc(a.spec)}</td><td>${esc(a.unit)}</td><td class="n">${fmtN(a.qty)}</td><td>${esc(a.dest)}</td>${rmkTd(a.remark)}
      <td class="w">${a.u8_status === '待入U8' ? `<span class="tag warn ${ageCls(a.date)}">待入U8</span><div class="rowacts"><a data-u8="${a.id}">已入U8</a> · <a data-nou8="${a.id}">不用入U8</a></div>` : `<span class="tag ${a.u8_status === '已入U8' ? 'ok' : ''}">${U8CN[a.u8_status]}</span><div class="rowacts"><a class="link d" data-undo="${a.id}" title="改回待入U8">撤销</a></div>`}</td>
      <td>${esc(a.inv_code)}</td><td>${esc(a.receipt_no)}</td><td class="w">${esc(a.batch_no)}${a.expiry ? '<br><span class="muted" style="font-size:12px">效期 ' + esc(a.expiry) + '</span>' : ''}</td>
      ${rowActs({ ph: [a.nphotos, `data-ph="${a.id}"`], main: ['修改', `data-ed="${a.id}"`], menu: [['加照片', `data-addph="${a.id}"`], ['删除', `data-del="${a.id}"`, 1]] })}</tr>`).join('')}</tbody></table></div><div class="hint">${r.items.length} 行 · 点「列」可隐藏批号等</div>` : '<div class="empty">没有记录</div>';
  if (r.items.length) LC.apply($('#arTbl', el), 'arrival', [
    { k: '_ck', label: '选', w: 36 }, { k: 'date', label: '日期', w: 84 },
    { k: 'name', label: '存货名称', w: 130, prod: 1 }, { k: 'spec', label: '规格型号', w: 100, wrap: 1 },
    { k: 'unit', label: '单位', w: 44 }, { k: 'qty', label: '数量', w: 56 },
    { k: 'dest', label: '存货单位', w: 88, hide: 1, wrap: 1 }, { k: 'rmk', label: '备注', w: 100, wrap: 1 },
    { k: 'u8', label: 'U8', w: 100 }, { k: 'inv', label: '存货号', w: 88, hide: 1 },
    { k: 'rcpt', label: '入库单号', w: 96, hide: 1 }, { k: 'batch', label: '批号', w: 88, hide: 1 },
    { k: '_act', label: '操作', w: 120 }
  ]);
  if (typeof CellSel !== 'undefined') CellSel.on($('#arTbl', el));
  const upd = () => { const b = $('#arMark', el), b2 = $('#arNo', el); b.disabled = b2.disabled = !sel.size; b.textContent = sel.size ? `标记已入U8（${sel.size}）` : '标记已入U8'; b2.textContent = sel.size ? `标记不用入U8（${sel.size}）` : '标记不用入U8'; };
  const all = $('#arAll', el); if (all) all.onchange = () => { r.items.forEach(a => all.checked ? sel.add(a.id) : sel.delete(a.id)); loadArr(el); };
  $('#arT', el).onclick = async e => {
    const t = e.target;
    try {
      if (t.dataset.s) { t.checked ? sel.add(+t.dataset.s) : sel.delete(+t.dataset.s); upd(); }
      if (t.dataset.ph) { const a = await api('/api/arrival/one?id=' + t.dataset.ph); dialog('照片', `<div class="photos">${a.photos.map(p => `<img class="ph-i" style="width:180px;height:135px" src="/photos/${esc(p.path)}" onclick="bigImg(this.src)">`).join('')}</div>`, null, { wide: true }); }
      if (t.dataset.addph) { const p = PIN.get() || await PIN.ask('上传照片'); const ps = await photoPick({ title: '到货照片', label: '到货 #' + t.dataset.addph + ' 的照片', extra: { entity: 'arrival', entity_id: +t.dataset.addph, by: p.name } }); if (ps.length) { toast('已上传 ' + ps.length + ' 张'); loadArr(el); } }
      if (t.dataset.ed) editArr(el, +t.dataset.ed);
      if (t.dataset.u8) markU8(el, [+t.dataset.u8]);
      if (t.dataset.nou8) await setU8(el, [{ id: +t.dataset.nou8, u8_status: '不入U8' }], '标记不用入U8');
      if (t.dataset.undo) await setU8(el, [{ id: +t.dataset.undo, u8_status: '待入U8' }], '撤销为待入U8');
      if (t.dataset.del && await confirmDelete('arrival', +t.dataset.del, '/api/arrival/delete')) { toast('已删除'); loadArr(el); }
    } catch (er) { fail(er); }
  };
  upd();
}

async function editArr(el, id) {
  const a = await api('/api/arrival/one?id=' + id);
  const F = [['date', '日期', 'date'], ['name', '存货名称'], ['spec', '规格型号'], ['unit', '单位'], ['qty', '数量'], ['dest', '存货单位'], ['remark', '备注'], ['u8_status', 'U8 状态'], ['inv_code', '存货号'], ['receipt_no', '入库单号'], ['taken_note', '入库单拿走情况'], ['batch_no', '批号'], ['prod_date', '生产日期', 'date'], ['expiry', '有效期至', 'date']];
  const ov = dialog('修改到货', `<div class="row r2">${F.map(([k, l, t]) => `<div><span class="lab">${l}</span>${k === 'u8_status' ? `<select class="inp" data-k="u8_status">${['待入U8', '已入U8', '不入U8'].map(x => `<option value="${x}" ${a.u8_status === x ? 'selected' : ''}>${U8CN[x]}</option>`).join('')}</select>` : `<input class="inp" data-k="${k}" type="${t || 'text'}" value="${esc(a[k] == null ? '' : a[k])}">`}</div>`).join('')}
    <div style="grid-column:1/3"><span class="lab">对应产品（进库存用）</span><input class="inp" id="eaP" value="${esc(P.label(a.product_id))}"></div></div>
    <div style="margin-top:12px"><span class="lab">照片</span><div id="eaPh"></div></div>
    <div class="hint">${a.audit.map(x => fmtTs(x.ts) + ' ' + esc(x.person) + ' ' + esc(x.action) + (x.summary ? '：' + esc(x.summary) : '')).join('<br>')}</div>`,
    [{ t: '取消' }, { t: '保存', cls: 'pri', fn: async ov => {
      const d = { id }; $$('[data-k]', ov).forEach(i => d[i.dataset.k] = i.value); d.qty = +d.qty || 0; d.product_id = ov._pid === undefined ? a.product_id : ov._pid;
      await save('/api/arrival/save', { data: d, photo_ids: ph.ids }, '修改到货'); toast('已保存'); loadArr(el);
    } }], { wide: true });
  const ph = photoBox($('#eaPh', ov), a.photos);
  const pi = $('#eaP', ov); autoComplete(pi, async q => P.search(q).slice(0, 10), p => { ov._pid = p.id; pi.value = p.label; }, (p, q) => hl(p.label, q));
  pi.addEventListener('input', () => { if (!pi.value.trim()) ov._pid = null; });
}

/** 批量改 U8 状态（需密码，留痕），提示里可撤销 */
async function setU8(el, items, title) {
  const r = await save('/api/arrival/u8', { items }, title); AR.sel.clear(); loadArr(el);
  undoU8(el, r.prev, '已' + title.replace(/^标记/, '标记') + ' ' + items.length + ' 行');
}
function undoU8(el, prev, msg) {
  toastUndo(msg, async () => { await save('/api/arrival/u8', { items: prev, note: '撤销' }, '撤销'); loadArr(el); });
}
function markU8(el, ids) {
  const rs = AR.data.filter(a => ids.includes(a.id));
  dialog('标记已入U8', `<div class="muted" style="font-size:13px;margin-bottom:8px">入完 U8 后填存货号、入库单号（可空）。同一张入库单只有一个入库单号，可统一填。</div>
    <div class="split" style="margin-bottom:10px"><span class="lab" style="margin:0">统一入库单号</span><input class="inp sm" id="muNo" style="width:180px"></div>
    <table class="t"><thead><tr><th>日期</th><th>存货</th><th class="n">数量</th><th>存货号</th><th>入库单号</th></tr></thead><tbody>
    ${rs.map(a => `<tr><td class="w">${esc(a.date)}</td><td>${esc(a.name + ' ' + a.spec)}</td><td class="n">${fmtN(a.qty)}</td><td><input class="inp sm" data-c="${a.id}" value="${esc(a.inv_code)}"></td><td><input class="inp sm" data-n="${a.id}" value="${esc(a.receipt_no)}"></td></tr>`).join('')}</tbody></table>`,
    [{ t: '取消' }, { t: '标记已入U8', cls: 'pri', fn: async ov => {
      const items = rs.map(a => ({ id: a.id, inv_code: $(`[data-c="${a.id}"]`, ov).value.trim(), receipt_no: $(`[data-n="${a.id}"]`, ov).value.trim(), u8_status: '已入U8' }));
      const r = await save('/api/arrival/u8', { items }, '标记已入U8'); AR.sel.clear(); loadArr(el); undoU8(el, r.prev, '已标记已入U8 ' + items.length + ' 行');
    } }], { wide: true, nofocus: true });
  setTimeout(() => { const n = $('#muNo'); if (n) n.oninput = () => $$('[data-n]').forEach(i => i.value = n.value); }, 30);
}

/* ---------- U8 入库单截图离线识别：只填存货号、入库单号 ---------- */
let ocrReady = null;
function loadOcr() {
  if (ocrReady) return ocrReady;
  ocrReady = (async () => {
    const html = await (await fetch('/lib/ocr_bundle.html')).text();
    const host = document.createElement('div'); host.style.display = 'none'; host.innerHTML = html; document.body.appendChild(host);
    const first = host.querySelector('script:not([type])'); const s = document.createElement('script'); s.textContent = first.textContent; document.head.appendChild(s);
    await new Promise((res, rej) => { const s2 = document.createElement('script'); s2.src = '/lib/o2_ocr.js'; s2.onload = res; s2.onerror = rej; document.head.appendChild(s2); });
    // v82 识别代码把 TesseractOffline 挂在 window 上；这里兼容
    if (!window.TesseractOffline && window.Tesseract) window.TesseractOffline = window.Tesseract;
  })();
  ocrReady.catch(() => ocrReady = null);
  return ocrReady;
}
async function ocrU8(el) {
  const [f] = await pickFiles('image/*'); if (!f) return;
  const url = await compressImage(f, 2600, 0.95);
  const ov = dialog('识别 U8 入库单', `<div class="muted">正在离线识别（第一次要加载识别组件，约 10–30 秒）… <span id="ocrP"></span></div>`, [{ t: '取消' }], { nofocus: true });
  await loadOcr();
  const res = await O2OCR.recognizeTable(url, m => { const p = $('#ocrP', ov); if (p && m && m.progress) p.textContent = Math.round(m.progress * 100) + '%'; });
  const p = O2OCR.parseU8Inbound(res); ov.remove();
  const pend = (await api('/api/arrivals?status=待入U8&limit=200')).items;
  const used = new Set();
  const cands = it => pend.map(a => {
    let s = 0; if (isFinite(it.qty) && +a.qty === it.qty) s += 3;
    const sp = String(a.spec || '').replace(/\s/g, '').toUpperCase(); if (it.spec && (sp === it.spec + 'L' || sp === String(it.spec))) s += 2;
    return { a, s };
  }).filter(x => x.s >= 2).sort((x, y) => y.s - x.s).slice(0, 6);
  const lines = p.items.map((it, i) => {
    const cs = cands(it); const pick = cs.find(c => !used.has(c.a.id)); if (pick) used.add(pick.a.id);
    return `<tr><td><input type="checkbox" data-on="${i}" ${pick ? 'checked' : ''}></td><td><input class="inp sm" data-code="${i}" value="${esc(it.code)}" style="width:100px"></td><td>${esc(it.spec ? it.spec + 'L' : '')}</td><td class="n">${fmtN(it.qty)}${it.sure === false ? ' <span class="tag warn">?</span>' : ''}</td>
      <td><select class="inp sm" data-row="${i}"><option value="">（不填）</option>${cs.map(c => `<option value="${c.a.id}" ${pick && pick.a.id === c.a.id ? 'selected' : ''}>${esc(c.a.date + ' ' + c.a.name + ' ' + c.a.spec + ' ×' + fmtN(c.a.qty))}</option>`).join('')}
      <optgroup label="其他待入U8">${pend.filter(a => !cs.some(c => c.a.id === a.id)).slice(0, 40).map(a => `<option value="${a.id}">${esc(a.date + ' ' + a.name + ' ' + a.spec + ' ×' + fmtN(a.qty))}</option>`).join('')}</optgroup></select></td></tr>`;
  }).join('');
  dialog('核对 U8 入库单识别结果', `<div style="display:grid;grid-template-columns:300px 1fr;gap:16px"><img src="${url}" style="width:100%;border-radius:8px;cursor:zoom-in" onclick="bigImg(this.src)">
    <div><span class="lab">入库单号</span><input class="inp" id="ocrNo" value="${esc(p.orderNo)}" style="width:220px">
    ${p.items.length ? `<table class="t" style="margin-top:12px"><thead><tr><th></th><th>存货编码</th><th>规格</th><th class="n">数量</th><th>对应到货行</th></tr></thead><tbody>${lines}</tbody></table>` : '<div class="banner" style="margin-top:12px">没有识别到明细行，请换一张更清晰的截图</div>'}
    <div class="hint">${p.totalOk ? '数量与「合计」' + fmtN(p.total) + ' 一致 ✓ · ' : ''}只写入「存货号」「入库单号」，并标记已入U8。按规格 + 数量自动匹配，请核对。</div></div></div>`,
    [{ t: '取消' }, { t: '确认写入', cls: 'pri', fn: async ov2 => {
      const no = $('#ocrNo', ov2).value.trim(); const items = [];
      $$('[data-on]', ov2).forEach(cb => { if (!cb.checked) return; const i = cb.dataset.on; const id = +$(`[data-row="${i}"]`, ov2).value; if (id) items.push({ id, inv_code: $(`[data-code="${i}"]`, ov2).value.trim(), receipt_no: no, u8_status: '已入U8' }); });
      if (!items.length) throw new Error('没有选要写入的行');
      if (new Set(items.map(x => x.id)).size !== items.length) throw new Error('同一到货行被选了两次');
      await save('/api/arrival/u8', { items }, '写入 U8 识别结果'); toast('已写入 ' + items.length + ' 行'); loadArr(el);
    } }], { wide: true, nofocus: true });
}
