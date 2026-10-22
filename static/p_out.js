/* 出库：单笔 + 批量 + 出库记录 */
'use strict';
const Out = { tab: 'single', form: null, batches: {} };
function newOutForm() {
  const df = defs(); const kinds = S.boot.settings.out_kinds || [];
  // 设置里选「（不选）」时 out_kind 为空：新单不预选类型；未配置或配置值已删则回退客户自提
  const kind = df.out_kind === '' ? '' : (kinds.includes(df.out_kind) ? df.out_kind : '客户自提');
  return { date: today(), kind, source: df.out_source || '', u8_no: '', u8_type: '', customer: '', contact: '', phone: '', recipient: '', purpose: '', remark: '', items: [], token: Math.random().toString(36).slice(2, 12) };
}
async function loadBatches() { const r = await api('/api/batches'); Out.batches = {}; Out.trusted = {}; r.items.forEach(p => { Out.batches[p.id] = p.batches.filter(b => b.id); Out.trusted[p.id] = !!(p.batch_trusted || batchIsTrusted(p.id, p.batches, p)); }); }

Pages.out = async (el, arg) => {
  if (['list', 'batch', 'single', 'ly'].includes(arg)) Out.tab = arg;
  else if (!arg) Out.tab = 'single';   // 默认单笔
  if (!Out.form) Out.form = newOutForm();
  el.innerHTML = UI.ph('出库', '单笔照单录 · 批量一次出完 · 手写单只拍照', '不做文字识别，拍完自动出现在本单。批量适合把一张配送表一次出完。',
    `<div class="seg" id="outTabs"><button data-t="single">单笔</button><button data-t="batch">批量</button><button data-t="list">出库记录</button><button data-t="ly">领用出库单</button></div>`)
    + `<div id="outBody"></div>`;
  $$('#outTabs button', el).forEach(b => {
    b.classList.toggle('on', b.dataset.t === Out.tab);
    b.onclick = async () => {
      if (b.dataset.t === Out.tab) return;
      if (App.guard && !await confirmDirty(App.guard, App.guardSave)) return;
      App.guard = null; App.guardSave = null; Out._dirty = false;
      Out.tab = b.dataset.t; App.tab('out/' + Out.tab);
    };
  });
  await loadBatches();
  const body = $('#outBody', el);
  if (Out.tab === 'single') return outSingle(body);
  if (Out.tab === 'batch') return outBatch(body);
  if (Out.tab === 'ly') return outLy(body);
  return outList(body);
};

function kindFields(f) {
  const self = f.kind === '厂内自用' || f.kind === '领用出库';
  return self;
}
function isExch(f) { return f.kind === '换货'; }
function sideOf(it) { return (it && it.side) === 'in' ? 'in' : 'out'; }
function fmtExchItems(items) {
  const outs = (items || []).filter(i => sideOf(i) === 'out');
  const inns = (items || []).filter(i => sideOf(i) === 'in');
  const one = (lst, tag) => lst.length ? tag + '：' + lst.map(i => esc(i.product_name || (P.byId(i.product_id) || {}).label || '?') + '×' + fmtN(i.qty)).join('、') : '';
  return [one(outs, '换出'), one(inns, '换入')].filter(Boolean).join('；') || '—';
}
function outSingle(el) {
  const f = Out.form; const s = S.boot.settings;
  const exch = isExch(f);
  const prodSec = exch
    ? `<div class="sec"><div class="sec-h"><h2>换货 · 谁换谁</h2><small>左边发出新品（扣库存），右边收回原品（加库存）；一张单两边都要填</small></div>
        <div class="ex-pair">
          <div class="ex-side" data-side="out"><div class="ex-h"><span class="tag warn">换出</span><b>发出新品</b></div>
            <div class="picks" id="picksOut"></div>
            <div style="margin-top:8px"><input class="inp" id="psearchOut" placeholder="搜发出的产品，或新产品名回车"></div>
            <div class="lines" id="linesOut" style="margin-top:8px"></div></div>
          <div class="ex-arrow" title="换">↔</div>
          <div class="ex-side" data-side="in"><div class="ex-h"><span class="tag ok">换入</span><b>收回原品</b></div>
            <div class="picks" id="picksIn"></div>
            <div style="margin-top:8px"><input class="inp" id="psearchIn" placeholder="搜收回的产品，或新产品名回车"></div>
            <div class="lines" id="linesIn" style="margin-top:8px"></div></div>
        </div></div>`
    : `<div class="sec"><div class="sec-h"><h2>选择产品</h2><small>点一下 +1，按常用排序</small></div>
      <div class="picks" id="picks"></div>
      <div style="margin-top:8px"><input class="inp" id="psearch" placeholder="搜其他产品，或直接输入新产品名后回车"></div></div>
    <div class="sec"><div class="sec-h"><h2>本单产品 <small id="lnSum"></small></h2></div><div class="lines" id="lines"></div></div>`;
  // 先选单据来源，再出类型芯片；类型集合按来源过滤（kindsForSource）
  // 改旧单时把已存类型带上，避免不在新集合里时卡死；新单不硬塞
  const showKinds = !!f.source;
  const kindList = showKinds ? kindsForSource(f.source, s.out_kinds || [], f.id ? f.kind : '') : [];
  if (showKinds && f.kind && !kindList.includes(f.kind)) f.kind = '';
  const kindRow = showKinds
    ? `<span class="lab" style="margin:0">类型</span><div class="chips" id="kinds">${kindList.map(k => `<span class="chip ${f.kind === k ? 'on' : ''}" data-k="${esc(k)}">${esc(k)}</span>`).join('')}</div>`
    : `<span class="lab" style="margin:0;color:var(--muted)">类型</span><div class="muted" style="font-size:13px">先选上面的单据来源</div>`;
  el.innerHTML = `<div class="grid2 page-entry">
   <div class="card page-card">
    <div class="sec"><div class="row" style="grid-template-columns:auto 1fr;align-items:center;gap:10px 14px">
      <span class="lab" style="margin:0">单据来源</span><div class="split"><div class="chips" id="srcs">${s.sources.map(k => `<span class="chip ${f.source === k ? 'on' : ''}" data-k="${esc(k)}">${esc(k)}</span>`).join('')}</div>
        <span id="u8f" style="display:${f.source === 'U8单' ? 'flex' : 'none'};gap:8px;margin-left:8px"><input class="inp sm" id="u8no" placeholder="U8单号（可空）" style="width:150px" value="${esc(f.u8_no)}">
        <input class="inp sm" id="u8type" list="u8types" placeholder="U8单细分（可空）" style="width:150px" value="${esc(f.u8_type)}" title="仅单据来源为 U8 单时填写：外来客户购买等"><datalist id="u8types">${(s.u8_types || []).map(t => `<option value="${esc(t)}">`).join('')}</datalist></span></div>
      ${kindRow}
    </div></div>
    <div class="sec" id="whoSec"></div>
    ${prodSec}
    <div class="sec"><input class="inp" id="remark" placeholder="备注（可空）" value="${esc(f.remark)}"></div>
   </div>
   <div class="sticky page-side-col">
    <div class="card page-card page-side"><div class="card-h"><h2>照片</h2><small class="muted">可多张 · 不识别文字</small></div>
      <div class="qr"><img id="qrImg" alt=""><div><div style="font-weight:500">本单扫码拍</div><div class="muted" style="font-size:12.5px">拍完自动出现在下面</div>
        <div class="ph-side-links"><a class="link" id="outLib">照片库选用</a><a class="link" id="outLibQr">持续拍码</a></div></div></div>
      <div id="phBox" style="margin-top:10px"></div></div>
    <div class="card page-card page-act"><div class="sum-line"><span id="sumWho">—</span><b id="sumN">0 件</b></div>
      <button class="btn pri big full" id="saveOut">${f.id ? '保存修改' : (exch ? '保存换货' : '保存出库')}</button>
      <div class="hint" style="text-align:center">Ctrl + Enter 快速保存 ${f.id ? ' · <a class="link" id="cancelEdit">放弃修改</a>' : ''}</div></div>
   </div></div>`;
  const ph = photoBox($('#phBox', el), f.photos || [], { onchange: ps => f.photos = ps, title: '出库单照片', label: '出库单照片' });
  const lan = (S.boot.lan || [])[0] || location.origin;
  $('#qrImg', el).src = '/api/qr.svg?text=' + encodeURIComponent(lan + '/m/#cam/' + f.token);
  const outLib = $('#outLib', el); if (outLib) outLib.onclick = async () => { try { const ps = await photoPick({ title: '照片库', label: '出库单照片', lib: true }); ps.forEach(p => ph.add(p)); f.photos = ph.list; } catch (e) { fail(e); } };
  const outLibQr = $('#outLibQr', el); if (outLibQr) outLibQr.onclick = () => showLibQr().catch(fail);
  const poll = setInterval(async () => {
    if (!document.body.contains(el)) return clearInterval(poll);
    try { const r = await api('/api/inbox?token=' + f.token); r.items.forEach(p => ph.add(p)); f.photos = ph.list; } catch (e) { }
  }, 3000);
  const drawWho = () => {
    const self = kindFields(f);
    $('#whoSec', el).innerHTML = self
      ? `<div class="row r3"><div class="fld"><span class="lab">领用人</span><input class="inp" id="recipient" value="${esc(f.recipient)}"></div>
         <div class="fld"><span class="lab">用途</span><input class="inp" id="purpose" value="${esc(f.purpose)}" placeholder="如：充装车间更换"></div>
         <div class="fld"><span class="lab">日期</span><input class="inp" type="date" id="date" value="${esc(f.date)}"></div></div>`
      : `<div class="row r3"><div class="fld"><span class="lab">客户单位 / 客户</span><input class="inp" id="customer" value="${esc(f.customer)}" autocomplete="off"></div>
         <div class="fld"><span class="lab">联系人</span><input class="inp" id="contact" value="${esc(f.contact)}"></div>
         <div class="fld"><span class="lab">日期</span><input class="inp" type="date" id="date" value="${esc(f.date)}"></div></div>
         <div class="row r3" style="margin-top:10px"><div class="fld"><span class="lab">电话</span><input class="inp" id="phone" value="${esc(f.phone)}"></div>
         <div class="fld"><span class="lab">业务员</span><input class="inp" id="salesperson" list="salesL" value="${esc(f.salesperson || '')}"><datalist id="salesL">${(S.boot.salespeople || []).map(x => `<option value="${esc(x)}">`).join('')}</datalist></div><div></div></div>`;
    $$('#whoSec input', el).forEach(i => i.oninput = () => { f[i.id] = i.value; sum(); });
    const ci = $('#customer', el);
    if (ci) autoComplete(ci, custSource, c => { f.customer = c.name; f.contact = c.contact || f.contact; f.phone = c.phone || f.phone; drawWho(); sum(); },
      (c, q) => `<span>${hl(c.name, q)}${c.contact ? ' · ' + esc(c.contact) : ''}</span><small>${esc(c.phone || '')}${c.last_date ? ' · 上次 ' + md(c.last_date) : ''}</small>`);
  };
  const itemsOf = side => f.items.filter(i => sideOf(i) === side);
  const drawPicks = (side) => {
    const box = $(exch ? (side === 'in' ? '#picksIn' : '#picksOut') : '#picks', el);
    if (!box) return;
    box.innerHTML = P.frequent(10).map(p => {
      const it = itemsOf(side || 'out').find(i => i.product_id === p.id);
      return `<div class="pick ${it ? 'on' : ''}" data-id="${p.id}" data-side="${side || 'out'}">${esc(p.name)}<small>${it ? '已选 ' + fmtN(it.qty) : esc(p.spec || '')}</small></div>`;
    }).join('');
  };
  const addItem = (pid, name, side) => {
    side = side || 'out';
    let it = pid
      ? f.items.find(i => i.product_id === pid && sideOf(i) === side)
      : f.items.find(i => i.product_name === name && sideOf(i) === side);
    if (it) it.qty = (+it.qty || 0) + 1;
    else f.items.push({ product_id: pid || null, product_name: name || '', qty: 1, batch_no: '', side });
    drawAll();
  };
  const lineHtml = (it, i) => {
    const p = it.product_id ? P.byId(it.product_id) : null;
    const bs = p && p.batch_managed ? (Out.batches[p.id] || []) : null;
    const fifo = sideOf(it) === 'out';
    const trusted = p && p.batch_managed && fifo && (Out.trusted[p.id] || batchIsTrusted(p.id, bs, p));
    const prefer = (it.batch_no || '').trim();
    const rem = prefer && bs ? (bs.find(b => b.batch_no === prefer) || {}).remain : null;
    const shortTip = trusted && prefer && rem != null && +it.qty > +rem
      ? `<div class="muted" style="font-size:12px;color:var(--bad);flex-basis:100%">本批剩 ${fmtN(rem)}，不够 ${fmtN(it.qty)}：保存时会弹出接下一批（不会扣成负）</div>`
      : (trusted && prefer && rem != null && +rem <= 0
        ? `<div class="muted" style="font-size:12px;color:var(--bad);flex-basis:100%">此批无正剩余（历史可能扣穿）：保存时改用其它正剩余批</div>` : '');
    const opt = b => {
      const neg = +b.remain < 0;
      return `<option value="${esc(b.batch_no)}" ${it.batch_no === b.batch_no ? 'selected' : ''}>${esc(b.batch_no)}${b.expiry ? ' · 效期' + esc(b.expiry) : ''} · ${neg ? '剩' + fmtN(b.remain) + ' 需核对' : '剩' + fmtN(b.remain)}</option>`;
    };
    return `<div class="ln"><div class="nm">${esc(p ? p.label : it.product_name)} ${p ? '' : '<span class="tag warn">新产品</span>'}${trusted ? ' <span class="tag ac" title="已盘点：不够会接下一批">盘</span>' : (p && p.batch_managed && fifo ? ' <span class="tag" title="未盘点：可随便扣，不强制接下一批">未盘</span>' : '')}</div>
      ${bs ? `<select class="inp sm" style="max-width:100%;width:190px" data-b="${i}"><option value="">${fifo ? '批号：先进先出（自动）' : '批号（可空）'}</option>${bs.map(opt).join('')}</select>` : ''}
      <div class="step"><button data-m="${i}">−</button><input data-q="${i}" value="${fmtN(it.qty)}" inputmode="decimal"><button data-p="${i}">+</button></div>
      <span class="unit">${esc(p ? p.unit : '')}</span><button class="link d" data-x="${i}" title="去掉">✕</button>${shortTip}</div>`;
  };
  const drawLines = (side) => {
    if (exch) {
      const outs = [], inns = [];
      f.items.forEach((it, i) => { (sideOf(it) === 'in' ? inns : outs).push([it, i]); });
      const empty = s => `<div class="muted" style="padding:6px 0">${s}</div>`;
      $('#linesOut', el).innerHTML = outs.map(([it, i]) => lineHtml(it, i)).join('') || empty('还没选发出的产品');
      $('#linesIn', el).innerHTML = inns.map(([it, i]) => lineHtml(it, i)).join('') || empty('还没选收回的产品');
    } else {
      $('#lines', el).innerHTML = f.items.map((it, i) => lineHtml(it, i)).join('') || '<div class="muted" style="padding:6px 0">还没选产品</div>';
    }
    sum();
  };
  const drawAll = () => {
    if (exch) { drawPicks('out'); drawPicks('in'); } else drawPicks('out');
    drawLines();
  };
  const sum = () => {
    const outs = itemsOf('out').filter(i => +i.qty > 0);
    const inns = itemsOf('in').filter(i => +i.qty > 0);
    const nOut = outs.reduce((a, i) => a + (+i.qty || 0), 0);
    const nIn = inns.reduce((a, i) => a + (+i.qty || 0), 0);
    const who = (kindFields(f) ? f.recipient : f.customer) || f.kind;
    if (exch) {
      $('#sumN', el).textContent = `出 ${fmtN(nOut)} · 入 ${fmtN(nIn)}`;
      $('#sumWho', el).textContent = who;
    } else {
      const n = f.items.reduce((a, i) => a + (+i.qty || 0), 0);
      const ls = $('#lnSum', el); if (ls) ls.textContent = f.items.length ? `${f.items.length} 项 · ${fmtN(n)} 件` : '';
      $('#sumN', el).textContent = fmtN(n) + ' 件';
      $('#sumWho', el).textContent = who;
    }
  };
  /* 换来源/类型会整表重绘：先把未 blur 的行数量/批号与客户栏写回 f，避免与借用单同类「已填被冲掉」 */
  const syncOutDom = () => {
    ['#lines', '#linesOut', '#linesIn'].forEach(sel => {
      const n = $(sel, el); if (!n) return;
      $$('[data-q]', n).forEach(i => { if (f.items[+i.dataset.q]) f.items[+i.dataset.q].qty = i.value; });
      $$('[data-b]', n).forEach(i => { if (f.items[+i.dataset.b]) f.items[+i.dataset.b].batch_no = i.value; });
    });
    $$('#whoSec input', el).forEach(i => { if (i.id) f[i.id] = i.value; });
    const u8n = $('#u8no', el); if (u8n) f.u8_no = u8n.value;
    const u8t = $('#u8type', el); if (u8t) f.u8_type = u8t.value;
    const rm = $('#remark', el); if (rm) f.remark = rm.value;
  };
  const kindsEl = $('#kinds', el);
  if (kindsEl) kindsEl.onclick = e => {
    const c = e.target.closest('[data-k]'); if (!c) return;
    syncOutDom();
    const prev = f.kind; f.kind = c.dataset.k;
    if (f.kind === '客户自提' && !f.source) f.source = 'app手工单';
    if (prev === '换货' && f.kind !== '换货') {
      f.items = f.items.filter(i => sideOf(i) === 'out');
      f.items.forEach(i => { delete i.side; });
    }
    if (prev !== '换货' && f.kind === '换货') f.items.forEach(i => { if (!i.side) i.side = 'out'; });
    outSingle(el);
  };
  $('#srcs', el).onclick = e => {
    const c = e.target.closest('[data-k]'); if (!c) return;
    syncOutDom();
    const next = f.source === c.dataset.k ? '' : c.dataset.k;
    f.source = next;
    if (!next) { /* 清来源则藏类型，保留已选 kind 以便再选回来源时预填不丢 */ }
    else {
      const allow = kindsForSource(next, s.out_kinds || [], '');  // 不带当前 kind，换来源时该清就清
      if (f.kind && !allow.includes(f.kind)) f.kind = '';
      // 来源已选且尚无类型：若默认类型落在本集合里则预填，不卡死「（不选）」
      if (!f.kind) {
        const df = defs();
        const want = df.out_kind === '' ? '' : ((s.out_kinds || []).includes(df.out_kind) ? df.out_kind : '客户自提');
        if (want && allow.includes(want)) f.kind = want;
      }
    }
    outSingle(el);
  };
  $('#u8no', el).oninput = e => f.u8_no = e.target.value; $('#u8type', el).oninput = e => f.u8_type = e.target.value;
  $('#remark', el).oninput = e => f.remark = e.target.value;
  const bindPickSearch = (pickId, searchId, side) => {
    const pk = $(pickId, el); if (pk) pk.onclick = e => { const c = e.target.closest('[data-id]'); if (c) addItem(+c.dataset.id, null, side); };
    const ps = $(searchId, el); if (!ps) return;
    autoComplete(ps, async q => P.search(q).slice(0, 12), p => { addItem(p.id, null, side); ps.value = ''; }, (p, q) => `<span>${hl(p.label, q)}</span><small>${esc(p.category)}${p.u8_code ? ' · ' + esc(p.u8_code) : ''}</small>`);
    ps.addEventListener('keydown', e => {
      if (e.key === 'Enter' && ps.value.trim() && !$('.drop', el)) {
        const v = ps.value.trim(); const ex = (S.boot.products || []).find(p => p.label === v || p.name === v);
        if (ex) addItem(ex.id, null, side); else addItem(null, v, side); ps.value = '';
      }
    });
  };
  if (exch) { bindPickSearch('#picksOut', '#psearchOut', 'out'); bindPickSearch('#picksIn', '#psearchIn', 'in'); }
  else bindPickSearch('#picks', '#psearch', 'out');
  const onLineClick = e => {
    const t = e.target; if (t.dataset.m) { const it = f.items[+t.dataset.m]; it.qty = Math.max(0, (+it.qty || 0) - 1); }
    else if (t.dataset.p) { const it = f.items[+t.dataset.p]; it.qty = (+it.qty || 0) + 1; }
    else if (t.dataset.x) f.items.splice(+t.dataset.x, 1); else return;
    drawAll();
  };
  const onLineChange = e => { const t = e.target; if (t.dataset.q) { f.items[+t.dataset.q].qty = t.value; sum(); drawPicks(sideOf(f.items[+t.dataset.q])); } if (t.dataset.b) f.items[+t.dataset.b].batch_no = t.value; };
  ['#lines', '#linesOut', '#linesIn'].forEach(sel => {
    const n = $(sel, el); if (!n) return;
    n.addEventListener('click', onLineClick); n.addEventListener('change', onLineChange);
  });
  const doSave = async () => {
    const outs = itemsOf('out').filter(i => +i.qty > 0);
    const inns = itemsOf('in').filter(i => +i.qty > 0);
    if (exch) {
      if (!outs.length) return toast('请选换出（发出）的产品', true);
      // 新单必须两边；改旧换货单（以前只有发出）可不强迫补换入，避免改库存口径
      const hadIn = !!(f.id && (f.items || []).some(i => sideOf(i) === 'in' && +i.qty > 0) || (f._hadIn));
      if (!inns.length && (!f.id || hadIn)) return toast('请选换入（收回）的产品', true);
    } else if (!f.items.filter(i => +i.qty > 0).length) return toast('还没选产品', true);
    if (!f.source) return toast('请选单据来源', true);
    if (!f.kind) return toast('请选类型', true);
    if (!kindFields(f) && !f.customer.trim() && f.kind !== '其他出库') return toast('请填客户', true);
    const data = Object.assign({}, f); delete data.token; delete data.photos;
    await loadBatches();
    let items = f.items.filter(i => +i.qty > 0).map(i => Object.assign({}, i, { side: exch ? sideOf(i) : 'out' }));
    items = await resolveOutBatchItems(items, Out.batches);
    // 弹窗可能已拆行：写回表单再保存
    f.items = items; drawAll();
    data.items = items;
    const wasId = f.id, keepSrc = f.source, keepKind = f.kind, wasExch = exch, wasLy = f.kind === '领用出库' && !f.id;
    const r = await save('/api/out/save', { data, photo_ids: ph.ids }, f.id ? '保存修改' : (exch ? '保存换货' : '保存出库'));
    App.guard = null; App.guardSave = null; Out._dirty = false;
    toast(wasId ? '已保存修改' : (wasExch ? '已换货' : '已出库'));
    await loadBoot(); App.who();
    if (wasLy) lySaved(r.id);
    if (wasId) { Out.form = newOutForm(); Out.tab = 'list'; App.tab('out/list'); return; }
    // 新单：再来一笔同来源 / 去出库记录
    const nf = Object.assign(newOutForm(), { source: keepSrc || '', kind: '' });
    if (keepSrc) {
      const allow = kindsForSource(keepSrc, (S.boot.settings.out_kinds || []), '');
      if (keepKind && allow.includes(keepKind)) nf.kind = keepKind;
      else {
        const df = defs();
        const want = df.out_kind === '' ? '' : ((S.boot.settings.out_kinds || []).includes(df.out_kind) ? df.out_kind : '客户自提');
        if (want && allow.includes(want)) nf.kind = want;
      }
    }
    Out.form = nf;
    const act = await new Promise(res => {
      dialog(wasExch ? '换货已保存' : '出库已保存',
        `<div>库存已更新。可继续录同来源下一笔，或去出库记录核对。</div>
         <div class="muted" style="margin-top:6px">来源：${esc(keepSrc || '—')}${keepKind ? ' · 类型：' + esc(kindDisp(keepKind)) : ''}</div>`,
        [
          { t: '再来一笔同来源', cls: 'pri', fn: () => res('again') },
          { t: '去出库记录', fn: () => res('list') },
          { t: '关闭', fn: () => res('close') },
        ], { onClose: () => res('close') });
    });
    if (act === 'list') { Out.tab = 'list'; App.tab('out/list'); }
    else outSingle(el);
  };
  $('#saveOut', el).onclick = () => doSave().catch(fail);
  const ce = $('#cancelEdit', el); if (ce) ce.onclick = () => { Out.form = newOutForm(); Out._dirty = false; App.guard = null; App.guardSave = null; outSingle(el); };
  el.onkeydown = e => { if (e.ctrlKey && e.key === 'Enter') doSave().catch(fail); };
  const markDirty = () => {
    Out._dirty = true;
    App.guard = '出库单还有改动没保存。可在本窗点「保存」，或选「不保存」离开。';
    App.guardSave = () => doSave();
  };
  el.addEventListener('input', markDirty);
  el.addEventListener('change', markDirty);
  const wrapChip = (sel) => {
    const n = $(sel, el); if (!n || !n.onclick) return;
    const prev = n.onclick;
    n.onclick = e => { markDirty(); return prev(e); };
  };
  wrapChip('#kinds'); wrapChip('#srcs');
  // 重绘时保留脏标记；新空白单不设护栏，一改就设
  if (f.id || Out._dirty) markDirty();
  else { App.guard = null; App.guardSave = null; }
  drawWho(); drawAll();
}

/* ---------- 批量：一张表一次出完（可粘贴 Excel / 导入 xlsx） ---------- */
const OB = { rows: [], date: today(), kind: null, source: '' };
function outBatch(el) {
  const s = S.boot.settings; const df = defs(); const kinds = s.out_kinds || [];
  if (OB.kind == null) OB.kind = df.out_kind === '' ? (kinds[0] || '客户自提') : (kinds.includes(df.out_kind) ? df.out_kind : (kinds[0] || '客户自提'));
  if (!OB.rows.length) OB.rows = Array.from({ length: 6 }, () => ({ customer: '', product: '', qty: '', batch_no: '', remark: '' }));
  // 类型按来源过滤（与 1.1.35 单笔同一 kindsForSource）；无来源时仍出全部
  const kindOpts = OB.source ? kindsForSource(OB.source, kinds, OB.kind) : kinds.slice();
  if (OB.kind && !kindOpts.includes(OB.kind)) OB.kind = kindOpts[0] || '';
  el.innerHTML = `<div class="card page-card">
    <div class="tools"><div class="tg"><span class="lab">日期</span><input class="inp" type="date" id="obDate" value="${OB.date}" style="width:150px">
      <span class="lab">单据来源</span><select class="inp" id="obSrc" style="width:110px"><option value="">（不填）</option>${s.sources.map(k => `<option ${OB.source === k ? 'selected' : ''}>${esc(k)}</option>`).join('')}</select>
      <span class="lab">类型</span><select class="inp" id="obKind" style="width:120px">${kindOpts.map(k => `<option ${OB.kind === k ? 'selected' : ''}>${esc(k)}</option>`).join('')}</select></div>
      <span class="sp"></span><div class="tg acts"><button class="btn" id="obImp">导入 Excel</button><button class="btn" id="obClear">清空</button></div></div>
    <div class="hint" style="margin:-4px 0 10px">可以从 Excel 里复制「客户 / 产品 / 数量」几列，点表格第一格后 Ctrl+V 粘贴；同一客户的几行会合成一张出库单。换货（谁换谁）请用「单笔」。</div>
    <div class="tw"><table class="t" id="obT" data-nosel><thead><tr><th style="width:36px">#</th><th>客户单位 / 客户</th><th>产品</th><th class="n" style="width:90px">数量</th><th style="width:150px">批号（空=先进先出）</th><th>备注</th><th style="width:40px"></th></tr></thead><tbody></tbody></table></div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px"><button class="btn sm" id="obAdd">＋ 加 5 行</button><span id="obSum" class="muted"></span></div>
    <div style="display:flex;gap:16px;align-items:flex-end;margin-top:16px;padding-top:14px;border-top:1px solid var(--line2)">
      <div style="flex:1"><span class="lab">拍照备份（整批）</span><div id="obPh"></div></div>
      <button class="btn pri big" id="obSave" style="width:220px">一键保存出库</button></div></div>`;
  const ph = photoBox($('#obPh', el), OB.photos || [], { onchange: p => OB.photos = p });
  const tb = $('#obT tbody', el);
  const draw = () => {
    tb.innerHTML = OB.rows.map((r, i) => {
      const p = r.product ? findProd(r.product) : null;
      return `<tr><td class="muted">${i + 1}</td><td><input class="inp sm" data-i="${i}" data-k="customer" value="${esc(r.customer)}"></td>
      <td><input class="inp sm" data-i="${i}" data-k="product" value="${esc(r.product)}" list="obProds" style="${r.product && !p ? 'box-shadow:inset 0 0 0 1px var(--warn)' : ''}" title="${r.product && !p ? '产品清单里没有，将作为新产品加入' : ''}"></td>
      <td><input class="inp sm num" data-i="${i}" data-k="qty" value="${esc(r.qty)}"></td><td><input class="inp sm" data-i="${i}" data-k="batch_no" value="${esc(r.batch_no)}" ${p && p.batch_managed ? '' : 'disabled placeholder="—"'}></td>
      <td><input class="inp sm" data-i="${i}" data-k="remark" value="${esc(r.remark)}"></td><td><button class="link d" data-x="${i}">✕</button></td></tr>`;
    }).join('') + `<datalist id="obProds">${S.boot.products.map(p => `<option value="${esc(p.label)}">`).join('')}</datalist>`;
    sum();
  };
  const sum = () => {
    const ok = OB.rows.filter(r => r.customer.trim() && r.product.trim() && +r.qty > 0);
    const cs = new Set(ok.map(r => r.customer.trim()));
    $('#obSum', el).textContent = ok.length ? `${cs.size} 个客户 · ${ok.length} 行 · ${fmtN(ok.reduce((a, r) => a + (+r.qty), 0))} 件` : '';
  };
  tb.addEventListener('input', e => { const t = e.target; if (t.dataset.k) { OB.rows[+t.dataset.i][t.dataset.k] = t.value; sum(); } });
  tb.addEventListener('change', e => { if (e.target.dataset.k === 'product') draw(); });
  tb.addEventListener('click', e => { if (e.target.dataset.x) { OB.rows.splice(+e.target.dataset.x, 1); draw(); } });
  tb.addEventListener('paste', e => {
    const t = e.target; if (!t.dataset.k) return;
    const txt = (e.clipboardData || window.clipboardData).getData('text'); if (!txt.includes('\t') && !txt.includes('\n')) return;
    e.preventDefault();
    const keys = ['customer', 'product', 'qty', 'batch_no', 'remark']; const k0 = keys.indexOf(t.dataset.k); let i = +t.dataset.i;
    txt.replace(/\r/g, '').split('\n').filter(l => l.trim()).forEach(l => {
      while (OB.rows.length <= i) OB.rows.push({ customer: '', product: '', qty: '', batch_no: '', remark: '' });
      l.split('\t').forEach((v, j) => { const k = keys[k0 + j]; if (k) OB.rows[i][k] = v.trim(); }); i++;
    });
    draw();
  });
  $('#obAdd', el).onclick = () => { for (let i = 0; i < 5; i++) OB.rows.push({ customer: '', product: '', qty: '', batch_no: '', remark: '' }); draw(); };
  $('#obClear', el).onclick = () => { OB.rows = []; OB.photos = []; outBatch(el); };
  $('#obDate', el).onchange = e => OB.date = e.target.value;
  $('#obKind', el).onchange = e => OB.kind = e.target.value;
  $('#obSrc', el).onchange = e => {
    OB.source = e.target.value;
    // 换来源：重绘以刷新类型选项（kindsForSource）
    const allow = OB.source ? kindsForSource(OB.source, kinds, '') : kinds.slice();
    if (OB.kind && !allow.includes(OB.kind)) OB.kind = allow[0] || '';
    else if (!OB.kind && allow.length) {
      const want = df.out_kind === '' ? '' : (kinds.includes(df.out_kind) ? df.out_kind : (kinds[0] || ''));
      OB.kind = (want && allow.includes(want)) ? want : (allow[0] || '');
    }
    outBatch(el);
  };
  $('#obImp', el).onclick = () => importBatchXlsx().then(() => draw()).catch(fail);
  $('#obSave', el).onclick = async () => {
    try {
      if (OB.kind === '换货') return toast('换货是「谁换谁」：请到「单笔」里填换出 + 换入（批量只适合单边出库）', true);
      const ok = OB.rows.filter(r => r.customer.trim() && r.product.trim() && +r.qty > 0);
      if (!ok.length) return toast('表里没有完整的行（客户、产品、数量都要有）', true);
      const by = {};
      ok.forEach(r => { const k = r.customer.trim(); (by[k] = by[k] || []).push(r); });
      const orders = Object.entries(by).map(([cu, rs]) => ({
        date: OB.date, kind: OB.kind, source: OB.source, customer: cu, remark: rs.map(r => r.remark).filter(Boolean).join('；'),
        items: rs.map(r => { const p = findProd(r.product); return p ? { product_id: p.id, qty: +r.qty, batch_no: r.batch_no } : { product_name: r.product.trim(), qty: +r.qty }; })
      }));
      const newP = ok.filter(r => !findProd(r.product)).map(r => r.product.trim());
      if (newP.length && !await confirmBox(`这些产品清单里没有，会作为新产品加入：<br><b>${esc([...new Set(newP)].join('、'))}</b>`, '继续保存')) return;
      const r = await save('/api/out/batch', { orders, photo_ids: ph.ids }, `批量出库 ${orders.length} 张单`);
      toast(`已出库 ${r.ids.length} 张单`); OB.rows = []; OB.photos = []; await loadBoot(); outBatch(el);
    } catch (e) { fail(e); }
  };
  draw();
}
function findProd(name) { name = (name || '').trim(); return S.boot.products.find(p => p.label === name || p.name === name || p.label.replace(/\s/g, '') === name.replace(/\s/g, '')); }
async function loadXlsxLib() { if (window.XLSX) return; await new Promise((res, rej) => { const s = document.createElement('script'); s.src = '/lib/xlsx.full.min.js'; s.onload = res; s.onerror = () => rej(new Error('Excel 组件没加载')); document.head.appendChild(s); }); }
async function importBatchXlsx() {
  const [f] = await pickFiles('.xlsx,.xls,.csv'); if (!f) return;
  await loadXlsxLib();
  const wb = XLSX.read(await f.arrayBuffer(), { type: 'array' });
  const rs = XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]], { header: 1, defval: '' });
  const hi = rs.findIndex(r => r.some(v => /客户|单位/.test(v)) && r.some(v => /产品|存货|名称/.test(v)));
  if (hi < 0) throw new Error('表里没找到「客户」「产品」「数量」表头');
  const h = rs[hi].map(String); const ix = re => h.findIndex(v => re.test(v));
  const ci = ix(/客户|单位/), pi = ix(/产品|存货名称|名称/), qi = ix(/数量/), bi = ix(/批号|批次/), ri = ix(/备注/);
  OB.rows = OB.rows.filter(r => r.customer || r.product);
  rs.slice(hi + 1).forEach(r => { if (!r[pi] && !r[ci]) return; OB.rows.push({ customer: String(r[ci] || ''), product: String(r[pi] || ''), qty: String(qi >= 0 ? r[qi] : ''), batch_no: bi >= 0 ? String(r[bi]) : '', remark: ri >= 0 ? String(r[ri]) : '' }); });
  toast('已读入 ' + (rs.length - hi - 1) + ' 行，请核对');
}

/* ---------- 出库记录（朴素表格） ---------- */
const OL = { from: '', to: '', kind: '', source: '', u8_type: '', q: '', deleted: '' };
async function outList(el) {
  const s = S.boot.settings;
  if (!OL.init) { OL.init = 1; const n = +defs().list_days; if (n > 0 && !OL.from) OL.from = daysAgo(n); }
  const kinds = [...new Set(s.out_kinds.concat(['批量配送', '混合出库']))];
  // U8单细分（settings.u8_types：外来客户购买等）只在来源=U8单时有意义；默认不在工具栏常驻，避免当成「出库类型」
  const u8Filter = OL.source === 'U8单'
    ? `<select class="inp" id="olU8t" title="只筛单据来源为 U8 单时填写的细分"><option value="">U8单细分</option>${(s.u8_types || []).map(k => `<option ${OL.u8_type === k ? 'selected' : ''}>${esc(k)}</option>`).join('')}</select>`
    : '';
  if (OL.source !== 'U8单') OL.u8_type = '';
  el.innerHTML = `<div class="card page-card"><div class="tools">
    <div class="tg" title="筛选">
      <input class="inp" type="date" id="olFrom" value="${OL.from}" style="width:132px"><span class="muted">至</span><input class="inp" type="date" id="olTo" value="${OL.to}" style="width:132px">
      <select class="inp" id="olKind"><option value="">全部类型</option>${kinds.map(k => `<option ${OL.kind === k ? 'selected' : ''}>${esc(k)}</option>`).join('')}</select>
      <select class="inp" id="olSrc"><option value="">全部来源</option>${s.sources.map(k => `<option ${OL.source === k ? 'selected' : ''}>${esc(k)}</option>`).join('')}</select>
      ${u8Filter}
      <input class="inp" id="olQ" placeholder="搜客户、电话、产品、U8单号、备注" value="${esc(OL.q)}" style="width:200px">
      <label class="muted" style="font-size:13px"><input type="checkbox" id="olDel" ${OL.deleted ? 'checked' : ''}> 已删除</label>
    </div>
    <span class="sp"></span>
    <div class="tg acts"><button class="btn sm" id="olPrint">打印</button><button class="btn sm" id="olExp">导出 Excel</button>${LC.btn('out')}</div>
  </div><div id="olT"></div></div>`;
  const qs = () => Object.entries(OL).filter(([k, v]) => v && k !== 'data').map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&');
  const load = async () => {
    const r = await api('/api/out?' + qs()); OL.data = r.items;
    $('#olT', el).innerHTML = r.items.length ? `<div class="tw"><table class="t" id="olTbl"><thead><tr><th>日期</th><th>类型</th><th>来源</th><th>客户 / 领用人</th><th>产品</th><th class="n">件数</th><th>备注</th><th>经办</th><th></th></tr></thead><tbody>
      ${r.items.map(o => `<tr class="${o.deleted_at ? 'off' : ''}"><td class="w">${esc(o.date)}</td><td class="w">${esc(kindDisp(o.kind))}</td>
        <td class="w">${o.source ? `<span class="tag ${o.source === 'U8单' ? 'ac' : ''}">${esc(o.source)}</span>` : ''}${o.u8_no ? ' <span class="muted">' + esc(o.u8_no) + '</span>' : ''}${o.u8_type ? '<br><span class="muted" style="font-size:12px">' + esc(o.u8_type) + '</span>' : ''}</td>
        <td>${esc(o.customer || o.recipient)}${o.contact ? ' <span class="muted">' + esc(o.contact) + '</span>' : ''}</td>
        <td>${o.kind === '换货' ? fmtExchItems(o.items) : o.items.map(i => esc(i.product_name) + ' ' + fmtN(i.qty) + (i.batch_no ? '<span class="muted">（' + esc(i.batch_no) + '）</span>' : '')).join('、')}</td>
        <td class="n">${o.kind === '换货' ? ('出' + fmtN(o.items.filter(i => (i.side || 'out') !== 'in').reduce((a, i) => a + i.qty, 0)) + '/入' + fmtN(o.items.filter(i => i.side === 'in').reduce((a, i) => a + i.qty, 0))) : fmtN(o.items.reduce((a, i) => a + i.qty, 0))}</td>${rmkTd(rmkJoin(o.remark, o.items.map(i => i.note ? i.product_name + '：' + i.note : '')))}<td class="w">${esc(o.created_by)}</td>
        ${rowActs({ ph: [o.photos.length, `data-ph="${o.id}"`], main: o.deleted_at ? ['恢复', `data-rs="${o.id}"`] : ['修改', `data-ed="${o.id}"`],
          menu: o.deleted_at ? [['留痕', `data-hi="${o.id}"`]] : [o.kind === '领用出库' ? ['打印领用单', `data-lp="${o.id}"`] : null, ['留痕', `data-hi="${o.id}"`], ['删除', `data-del="${o.id}"`, 1]] })}</tr>`).join('')}</tbody></table></div>
      <div class="hint">${r.items.length} 张单${r.items.length >= 300 ? '（只显示最近 300 张，请缩小日期范围）' : ''} · 点「列」可隐藏不常用列，拖表头调宽</div>` : '<div class="empty">没有记录</div>';
    if (r.items.length) LC.apply($('#olTbl', el), 'out', [
      { k: 'date', label: '日期', w: 88, min: 72 },
      { k: 'kind', label: '类型', w: 88, min: 64 },
      { k: 'src', label: '来源', w: 110, min: 72 },
      { k: 'cust', label: '客户 / 领用人', w: 140, min: 96, wrap: 1 },
      { k: 'prod', label: '产品', w: 220, min: 120, prod: 1 },
      { k: 'qty', label: '件数', w: 56, min: 44 },
      { k: 'rmk', label: '备注', w: 120, min: 72, wrap: 1 },
      { k: 'by', label: '经办', w: 64, min: 48, hide: 1 },
      { k: '_act', label: '操作', w: 120 }
    ]);
    if (typeof CellSel !== 'undefined') CellSel.on($('#olTbl', el));
  };
  const bind = (id, k, ev) => { const n = $(id, el); if (!n) return; n[ev || 'onchange'] = e => { OL[k] = e.target.type === 'checkbox' ? (e.target.checked ? '1' : '') : e.target.value; load().catch(fail); }; };
  bind('#olFrom', 'from'); bind('#olTo', 'to'); bind('#olKind', 'kind'); bind('#olDel', 'deleted');
  const srcEl = $('#olSrc', el);
  if (srcEl) srcEl.onchange = e => { OL.source = e.target.value; if (OL.source !== 'U8单') OL.u8_type = ''; outList(el); };
  bind('#olU8t', 'u8_type');
  let tm; $('#olQ', el).oninput = e => { clearTimeout(tm); tm = setTimeout(() => { OL.q = e.target.value; load().catch(fail); }, 250); };
  $('#olExp', el).onclick = () => download('/api/out/export.xlsx?' + qs());
  $('#olPrint', el).onclick = () => printApi('/api/out/export.xlsx?' + qs(), { landscape: true }).catch(fail);
  $('#olT', el).addEventListener('click', async e => {
    const t = e.target; const o = id => OL.data.find(x => x.id === +id);
    try {
      if (t.dataset.ph) { const ps = o(t.dataset.ph).photos; dialog('照片', `<div class="photos">${ps.map(p => `<img class="ph-i" style="width:180px;height:135px" src="/photos/${esc(p.path)}" onclick="bigImg(this.src)">`).join('')}</div>`, null, { wide: true }); }
      if (t.dataset.ed) { const x = await api('/api/out/one?id=' + t.dataset.ed); Out.form = Object.assign(newOutForm(), x, { items: x.items.map(i => ({ product_id: i.product_id, product_name: i.product_name, qty: i.qty, batch_no: i.batch_no, note: i.note, side: i.side || 'out' })), _hadIn: x.items.some(i => (i.side || 'out') === 'in') }); Out.tab = 'single'; App.tab('out/single'); }
      if (t.dataset.hi) { const x = await api('/api/out/one?id=' + t.dataset.hi); dialog('留痕', `<table class="t"><thead><tr><th>时间</th><th>谁</th><th>操作</th><th>内容</th></tr></thead><tbody>${x.audit.map(a => `<tr><td class="w">${fmtTs(a.ts)}</td><td>${esc(a.person)}</td><td>${esc(a.action)}</td><td>${esc(a.summary)}</td></tr>`).join('')}</tbody></table>`, null, { wide: true }); }
      if (t.dataset.del) { if (await confirmDelete('out', +t.dataset.del, '/api/out/delete')) { toast('已删除'); load(); } }
      if (t.dataset.lp) printApi('/api/out/slip.xlsx?id=' + t.dataset.lp, { font: '11pt' }).catch(fail);
      if (t.dataset.rs) { await save('/api/restore', { entity: 'out', id: +t.dataset.rs }, '恢复出库单'); toast('已恢复'); load(); }
    } catch (er) { fail(er); }
  });
  await load();
}

/* ---------- 领用出库单：打印/下载 → 领用人签字 → 拍照回传（没回传的挂待补全） ---------- */
let LYD = [];
const LY = { q: '', who: '', from: '', to: '', sign: '' };
function lySaved(id) {
  dialog('领用出库单已保存', '<div>库存已扣。请打印（或下载）领用出库单给领用人签字，签好后拍照回传；没回传前会一直挂在「待补全」。</div>',
    [{ t: '以后再说' }, { t: '下载', fn: () => { download('/api/out/slip.xlsx?id=' + id); return false; } }, { t: '打印', cls: 'pri', fn: () => { printApi('/api/out/slip.xlsx?id=' + id, { font: '11pt' }).catch(fail); } }]);
}
async function lySign(id, after) {
  const ids = (await photoPick({ title: '回传签字照片', label: '领用出库单签字照片', extra: { tag: 'sign' } })).map(p => p.id);
  if (!ids.length) return;
  await save('/api/out/sign', { id, photo_ids: ids }, '回传签字照片'); toast('已回传签字照片'); after && after();
}
async function outLy(el) {
  el.innerHTML = `<div class="card page-card"><div class="tools">
    <div class="tg"><input class="inp" id="lyQ" placeholder="搜用途、物品、备注" value="${esc(LY.q || '')}" style="width:160px"><input class="inp" id="lyWho" placeholder="领用人" value="${esc(LY.who)}" list="lyPpl" style="width:120px"><datalist id="lyPpl"></datalist>
    <input class="inp" type="date" id="lyFrom" value="${LY.from}" style="width:132px"><span class="muted">至</span><input class="inp" type="date" id="lyTo" value="${LY.to}" style="width:132px">
    <div class="seg" id="lyS"><button data-s="">全部</button><button data-s="todo">未回传签字</button><button data-s="done">已回传</button></div></div>
    <span class="sp"></span><div class="tg acts"><button class="btn sm" id="lyPr">打印清单</button><button class="btn sm" id="lyX">导出 Excel</button>${LC.btn('ly')}<button class="btn sm pri" id="lyNew">＋ 开领用出库单</button></div></div><div id="lyT"></div></div>`;
  const qs = () => Object.entries(LY).filter(([k, v]) => v).map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&');
  const load = async () => {
    const r = await api('/api/out/lingyong?' + qs()); LYD = r.items;
    $('#lyPpl', el).innerHTML = r.people.map(p => `<option value="${esc(p)}">`).join('');
    $$('#lyS button', el).forEach(b => b.classList.toggle('on', b.dataset.s === LY.sign));
    $('#lyT', el).innerHTML = r.items.length ? `<div class="tw"><table class="t" id="lyTbl"><thead><tr><th>日期</th><th>单号</th><th>领用人</th><th>用途</th><th>物品</th><th>备注</th><th>签字</th><th>库管</th><th></th></tr></thead><tbody>
      ${r.items.map(o => `<tr><td class="w ${o.signed ? '' : ageCls(o.date)}">${esc(o.date)}</td><td class="w">${esc(o.slip_no)}</td><td>${esc(o.recipient)}</td><td>${esc(o.purpose)}</td>
        <td>${o.items.map(i => esc(i.product_name) + ' ' + fmtN(i.qty)).join('、')}</td>${rmkTd(rmkJoin(o.remark, o.items.map(i => i.note || '')))}
        <td class="w">${o.signed ? '<span class="tag ok">已回传</span>' : '<span class="tag warn">未回传</span>'}</td><td class="w">${esc(o.created_by)}</td>
        ${rowActs({ ph: [o.sign_photos.length, `data-sp="${o.id}"`], main: o.signed ? ['打印', `data-pr="${o.id}"`] : ['回传签字', `data-sg="${o.id}"`],
          menu: [o.signed ? ['再传签字照片', `data-sg="${o.id}"`] : ['打印', `data-pr="${o.id}"`], ['下载', `data-dl="${o.id}"`], ['修改', `data-ed="${o.id}"`]] })}</tr>`).join('')}</tbody></table></div>` : '<div class="empty">没有领用出库单（出库时类型选「领用出库」）</div>'
    if (r.items.length) LC.apply($('#lyTbl', el), 'ly', [
      { k: 'date', label: '日期', w: 88 }, { k: 'no', label: '单号', w: 100 }, { k: 'who', label: '领用人', w: 88 },
      { k: 'pur', label: '用途', w: 120, wrap: 1 }, { k: 'prod', label: '物品', w: 180, prod: 1 },
      { k: 'rmk', label: '备注', w: 100, wrap: 1 }, { k: 'sign', label: '签字', w: 72 },
      { k: 'by', label: '库管', w: 64, hide: 1 }, { k: '_act', label: '操作', w: 120 }
    ]);
    if (typeof CellSel !== 'undefined') CellSel.on($('#lyTbl', el));;
  };
  const bind = (id, k) => { $(id, el).onchange = e => { LY[k] = e.target.value.trim(); load().catch(fail); }; };
  bind('#lyWho', 'who'); bind('#lyQ', 'q'); bind('#lyFrom', 'from'); bind('#lyTo', 'to');
  $('#lyS', el).onclick = e => { const b = e.target.closest('[data-s]'); if (b) { LY.sign = b.dataset.s; load().catch(fail); } };
  $('#lyPr', el).onclick = () => printApi('/api/out/lingyong?' + qs(), { landscape: true }).catch(fail);
  $('#lyX', el).onclick = () => download('/api/out/lingyong?xlsx=1&' + qs());
  $('#lyNew', el).onclick = () => { Out.form = Object.assign(newOutForm(), { kind: '领用出库' }); App.tab('out/single'); };
  $('#lyT', el).onclick = e => {
    const t = e.target;
    if (t.dataset.pr) printApi('/api/out/slip.xlsx?id=' + t.dataset.pr, { font: '11pt' }).catch(fail);
    if (t.dataset.dl) download('/api/out/slip.xlsx?id=' + t.dataset.dl);
    if (t.dataset.sg) lySign(+t.dataset.sg, () => load()).catch(fail);
    if (t.dataset.sp) { const o = LYD.find(x => x.id === +t.dataset.sp); dialog('签字照片 · ' + o.slip_no, `<div class="photos">${o.sign_photos.map(p => `<img class="ph-i" style="width:220px;height:165px" src="/photos/${esc(p.path)}" onclick="bigImg(this.src)">`).join('')}</div>`, null, { wide: true }); }
    if (t.dataset.ed) api('/api/out/one?id=' + t.dataset.ed).then(x => { Out.form = Object.assign(newOutForm(), x, { items: x.items.map(i => ({ product_id: i.product_id, product_name: i.product_name, qty: i.qty, batch_no: i.batch_no, note: i.note, side: i.side || 'out' })), _hadIn: x.items.some(i => (i.side || 'out') === 'in') }); Out.tab = 'single'; App.tab('out/single'); }).catch(fail);
  };
  await load();
}
