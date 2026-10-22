/* 产品出入库情况：照纸质交接表录（钢瓶交接表 / 产品交接表，一天多场次），系统自动合并成财务的「产品出入库情况」，下载原格式 */
'use strict';
const D = { date: today(), tab: 'cyl', ses: '早上', pd: null, dd: null, sh: null, dirty: false, peer: null };
const dnum = v => +v || 0;
function dCalc(v) {
  const g = k => dnum(v[k]);
  const r = { J40: g('e40') - g('r40'), J10: g('e10') - g('r10'), L40: g('o40') + g('r40') - g('e40') - g('f40'), L10: g('o10') + g('r10') - g('e10') - g('f10') };
  r.R40 = r.J40 + r.L40; r.R10 = r.J10 + r.L10; return r;
}
const addDays = (d, n) => { const x = new Date(d + 'T00:00:00'); x.setDate(x.getDate() + n); return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`; };
const dIsDate = s => /^\d{4}-\d{2}-\d{2}$/.test(s || '');
const D_LS = 'daily.date';
/** 记住选中日：URL #daily/页签/日期 + localStorage，刷新后仍打开同一天 */
function dPersist() {
  try { localStorage.setItem(D_LS, D.date); } catch (e) { }
  if (App.cur !== 'daily') return;
  const want = 'daily/' + D.tab + '/' + D.date;
  const cur = (location.hash || '').replace(/^#/, '');
  if (cur === want) { App.curHash = location.hash; return; }
  // replaceState：改地址但不触发 hashchange → 不会整页重绘跳动
  history.replaceState(null, '', '#' + want);
  App.curHash = location.hash;
}
function dRestoreDate() {
  const parts = (location.hash || '').replace(/^#/, '').split('/');
  const hashDate = dIsDate(parts[2]) ? parts[2] : null;
  if (hashDate) { D.date = hashDate; return; }
  try { const ls = localStorage.getItem(D_LS); if (dIsDate(ls)) D.date = ls; } catch (e) { }
}
function dPaintNav(el) {
  const root = el || document;
  const inp = $('#dDate', root); if (inp) inp.value = D.date;
  const peer = $('#dPeer', root); if (peer) { peer.textContent = '↔ ' + md(dPeerOf()); peer.title = '一键切换相邻日（当前 ↔ 次日/已记住的那天）'; }
}
/** 只重绘 #dBody（表内容），页头 / 页签 / 日期条不动，避免整页闪跳 */
async function dReloadBody(page) {
  page = page || $('#main .page');
  if (!page || !$('#dBody', page)) { dPersist(); App.tab('daily/' + D.tab + '/' + D.date); return; }
  dPersist();
  dPaintNav(page);
  const body = $('#dBody', page);
  const sumBtn = $('[data-t="sum"]', page);
  if (sumBtn) { const b = sumBtn.querySelector('b.num'); if (b) b.remove(); }
  $$('#dTabs button', page).forEach(b => b.classList.toggle('on', b.dataset.t === D.tab || (D.tab === 'tot' && b.dataset.t === 'sum')));
  if (D.tab === 'tot') {
    const n = $('#dNav', page); if (n) n.style.visibility = 'hidden';
    return drawDailyPanel(body, page);
  }
  if (D.tab === 'stats') {
    const n = $('#dNav', page); if (n) n.style.visibility = '';
    return drawDailyStats(body, page);
  }
  const n = $('#dNav', page); if (n) n.style.visibility = '';
  [D.pd, D.dd] = await Promise.all([api('/api/paper?date=' + D.date), api('/api/daily?date=' + D.date)]);
  if (!D.pd.sessions.includes(D.ses)) D.ses = D.pd.sessions[0] || '早上';
  const nOpen = D.dd.open.length;
  if (nOpen && sumBtn) sumBtn.insertAdjacentHTML('beforeend', ` <b class="num" style="font-weight:600;color:var(--warn)" title="在外未交回">${nOpen}</b>`);
  if (D.tab === 'sum') return drawDailySum(body, page);
  ppWork(); drawPaper(body, page);
}
/** 日表换日期：‹ › / 日期框 / ↔ 相邻日；dirty 时先确认；只更新表体，不整页重绘 */
async function dSetDate(nd) {
  nd = nd || today(); if (nd === D.date) { dPersist(); dPaintNav($('#main .page')); return false; }
  if (D.dirty && !await confirmDirty('交接表还有改动没保存，换日期前要先处理。', App.guardSave)) return false; D.dirty = false; App.guard = null; App.guardSave = null;
  D.date = nd; D.ses = defs().session;
  const page = $('#main .page');
  if (page && App.cur === 'daily' && $('#dBody', page)) { await dReloadBody(page); return true; }
  dPersist(); App.tab('daily/' + D.tab + '/' + D.date); return true;
}
/** 核对用的「另一天」：有 peer 用 peer，否则默认次日 D+1（通用，不写死某两天） */
const dPeerOf = () => (D.peer && D.peer !== D.date) ? D.peer : addDays(D.date, 1);
const dNavHtml = () => `<span class="dnav" id="dNav" title="换日期：前一天 / 后一天；↔ 在相邻两天之间一键来回（核对次日清点用）；刷新后仍打开选中那天">
  <button type="button" class="btn sm dnav-b" id="dPrev" title="前一天">‹</button>
  <input class="inp" type="date" id="dDate" value="${D.date}">
  <button type="button" class="btn sm dnav-b" id="dNext" title="后一天">›</button>
  <button type="button" class="btn sm" id="dPeer" title="一键切换相邻日（当前 ↔ 次日/已记住的那天）">↔ ${md(dPeerOf())}</button>
</span>`;
const dBindNav = el => {
  const go = async (nd, remember) => {
    const prev = D.date;
    if (!(await dSetDate(nd))) return;
    if (remember) D.peer = prev;
    dPaintNav(el);
  };
  $('#dPrev', el).onclick = () => go(addDays(D.date, -1), true);
  $('#dNext', el).onclick = () => go(addDays(D.date, 1), true);
  $('#dPeer', el).onclick = () => go(dPeerOf(), true);
  $('#dDate', el).onchange = async e => {
    const nd = e.target.value || today();
    D.peer = null;
    if (!(await dSetDate(nd))) e.target.value = D.date;
  };
};
const titleOf = d => `${d.slice(0, 4)}年${+d.slice(5, 7)}月${+d.slice(8, 10)}号产品出入库情况`;
const FORM_CN = { cyl: '氧气钢瓶出入库交接表', prod: '出入库交接表' };
/** 汇总表 / 汇总核对共用表头（列序、名称与财务登记表一致，方便对照） */
function dailyHeadHtml(first) {
  const other = S.boot.daily_cols.other;
  return `<thead><tr><th rowspan="3">${first}</th><th colspan="2">出库</th><th colspan="4">入库</th><th colspan="2">回收</th><th colspan="2">更换</th><th colspan="2">新送</th><th colspan="2">手工单更换</th><th colspan="2">手工单新送</th><th colspan="2">实际配送</th><th colspan="${other.length}">其他产品当天总出库</th><th rowspan="3">备注</th></tr>
    <tr>${['40L', '10L', '40L空', '40L满', '10L空', '10L满', '40L', '10L', '40L', '10L', '40L', '10L', '40L', '10L', '40L', '10L', '40L', '10L'].map(x => `<th rowspan="2">${x}</th>`).join('')}${other.slice(0, 8).map(o => `<th rowspan="2">${esc(o[1])}</th>`).join('')}<th colspan="${other.length - 8}">制氧机</th></tr>
    <tr>${other.slice(8).map(o => `<th>${esc(o[1])}</th>`).join('')}</tr></thead>`;
}

/* 格子：只写纸上的数。10+2、10-2 可以；产品表左边「5退」「5t」= 退回库房 */
function ppParse(raw) {
  let s = String(raw == null ? '' : raw).trim().replace(/＋/g, '+').replace(/[－—]/g, '-').replace(/\s/g, '');
  if (!s) return { v: null, ret: false, ok: true, txt: '' };
  const ret = /(退|t)$/i.test(s); s = s.replace(/(退|t)$/i, '');
  if (!/^\d+(\.\d+)?([+\-]\d+(\.\d+)?)*$/.test(s)) return { v: null, ret, ok: false, txt: s };
  let v = 0, sg = 1; s.match(/[+\-]|\d+(\.\d+)?/g).forEach(t => { if (t === '+') sg = 1; else if (t === '-') sg = -1; else v += sg * +t; });
  return { v: Math.round(v * 1000) / 1000, ret, ok: true, txt: s };
}
const ppHas = r => Object.values(r.cells || {}).some(v => String(v || '').trim()) || (r.hand || []).length || (r.note_l || '').trim() || (r.note_r || '').trim();
const ppSheet = (form, ses) => D.pd.sheets.find(s => s.form === (form || D.tab) && s.session === (ses || D.ses));
const ppLay = () => { const sh = ppSheet(); return sh ? sh.layout : D.pd.layout[D.tab]; };   // 旧表按它当时的样子，新表按现在的表格设置
const colId = c => c.t === 'p' ? (c.pid || c.fk) : null;
function ppFillDriver(r) {
  if (!r.driver && r.courier_id) r.driver = (S.boot.couriers.find(k => k.id === r.courier_id) || {}).name || '';
  return r;
}
/** 车牌行序（钢瓶页 / 产品页共用）：「表格设置」车牌列表顺序 + 表里多出来的车；配送员取表上的（没有则预填上次的人）。产品页跟钢瓶页完全同一套骨架，保证车牌+配送员列一致。 */
function ppOrderRows(sheetRows) {
  const rs = sheetRows ? JSON.parse(JSON.stringify(sheetRows)) : [];
  const used = new Set(); const out = [];
  D.pd.plates.forEach(p => {
    const i = rs.findIndex((r, j) => !used.has(j) && (r.plate || '').toLowerCase() === p.plate.toLowerCase());
    if (i >= 0) { used.add(i); out.push(ppFillDriver(rs[i])); }
    else out.push({ rid: 'p_' + p.plate, plate: p.plate, driver: p.name || '', _pre: true, cells: {}, hand: [] });
  });
  rs.forEach((r, j) => { if (!used.has(j)) out.push(Object.assign(ppFillDriver(r), { extra: true })); });
  return out;
}
function ppWork() {   // 当前表：车牌列表一行一个 + 表里多出来的行；配送员预填这个车牌上次的人
  const sh = ppSheet();
  let out;
  if (D.tab === 'prod') {   // 产品表：车牌、配送员行序与配对 = 同场次钢瓶页（同一套 ppOrderRows）；格子跟产品表自己的
    const cy = ppSheet('cyl');
    const skel = ppOrderRows(cy ? cy.rows : []);   // 与钢瓶页显示完全一致
    const rs = sh ? JSON.parse(JSON.stringify(sh.rows)) : [];
    const used = new Set();
    const take = (pred) => { const i = rs.findIndex((r, j) => !used.has(j) && pred(r)); if (i >= 0) { used.add(i); return rs[i]; } return null; };
    out = skel.map(c => {
      const r = take(r => String(r.crid || '') === String(c.rid)) || take(r => String(r.rid) === String(c.rid)) || take(r => (r.plate || '').toLowerCase() === (c.plate || '').toLowerCase())
        || { rid: c.rid, cells: {}, hand: [] };
      // 车牌 / 配送员 / 换人 一律跟钢瓶页骨架，不用产品表里存的旧值
      Object.assign(r, {
        crid: c._pre ? (r.crid || null) : c.rid,
        plate: c.plate,
        driver: c.driver || '',
        courier_id: c.courier_id || null,
        driver_r: c._pre ? '' : (c.driver_r || ''),
        courier_id_r: c._pre ? null : (c.courier_id_r || null),
        _cyl: !c._pre && !!cy,
        _pre: !!(c._pre || !cy)
      });
      delete r.extra;   // 钢瓶页的 extra 车在产品页仍只读跟车，不加「删除这一行」
      return r;
    });
    // 产品表里对不上钢瓶骨架、但已有数的行：挂在末尾，避免保存时悄悄丢掉（极少见）
    rs.forEach((r, j) => { if (!used.has(j) && ppHas(r)) out.push(Object.assign(ppFillDriver(r), { extra: true })); });
  } else {
    out = ppOrderRows(sh ? sh.rows : []);
  }
  const bts = Object.assign({}, sh ? sh.batches : {});
  Object.entries(D.pd.bm).forEach(([pid, b]) => { if (!bts[pid] && b.fifo && ppLayPids(ppLay()).has(+pid)) bts[pid] = b.fifo; });
  D.sh = { id: sh ? sh.id : null, updated_at: sh ? (sh.updated_at || sh.created_at) : null, rows: out, photos: sh ? sh.photos : [], batches: bts, edits: sh ? sh.edits : [],
    by: sh ? (sh.updated_by || sh.created_by) : '', ts: sh ? (sh.updated_at || sh.created_at) : null, lay: ppLay() };
  D.dirty = false; App.guard = null; App.guardSave = null;
}
function ppLayPids(lay) { const s = new Set(); ['L', 'R'].forEach(sd => lay[sd].forEach(c => { if (c.t === 'p' && c.pid) s.add(c.pid); })); return s; }
function ppDirty() { D.dirty = true; App.guard = '交接表还有改动没保存。可在本窗点「保存」，或回页头点保存后再离开。'; const b = $('#ppSave'); if (b) { b.disabled = false; b.textContent = '保存'; b.classList.add('btn-save-hi'); } const st = $('#ppSt'); if (st) st.innerHTML = '<span class="tag warn">有改动没保存</span>'; }

Pages.daily = async (el, arg) => {
  if (arg) arg = String(arg).split('?')[0];   // 兼容 #daily/cyl?d=… 旧写法
  if (arg === 'layout') return drawLayout(el);
  if (!D.sesInit) { D.sesInit = 1; D.ses = defs().session; }
  if (['cyl', 'prod', 'sum', 'tot', 'stats'].includes(arg)) D.tab = arg;
  // 无 arg 时保留 D.tab（保存后重绘）；顶栏点「日表」走 #daily/cyl
  dRestoreDate();   // URL 第三段 / localStorage → D.date（刷新后仍打开选中天）
  el.classList.add('wide');
  /* 页签并入压缩页头同一行（不另起条），与报表顶栏规格一致；汇总右边第四个「数量统计」（#daily/stats/日期，不踩 tot） */
  /* 1.1.48：日表顶栏不再放「照纸录…/说明」r-hint；汇总页标题与导入/打印/下载并进同一栏 */
  el.innerHTML = UI.ph('日表', '', '',
    `<div class="seg" id="dTabs"><button data-t="cyl">钢瓶交接表</button><button data-t="prod">产品交接表</button><button data-t="sum">汇总（财务表）</button><button data-t="stats">数量统计</button></div>
     ${dNavHtml()}<a class="btn sm" href="#daily/layout">表格设置</a>`)
    + `<div id="dBody"></div>`;
  dBindNav(el);
  dPersist();   // 把当前日写进 #daily/页签/日期 与 localStorage
  $$('#dTabs button', el).forEach(b => {
    b.classList.toggle('on', b.dataset.t === D.tab || (D.tab === 'tot' && b.dataset.t === 'sum'));
    b.onclick = async () => { if (b.dataset.t === D.tab) return; if (D.dirty && !await confirmDirty('交接表还有改动没保存，切换前要先处理。', App.guardSave)) return; D.dirty = false; App.guard = null; App.guardSave = null; D.tab = b.dataset.t; App.tab('daily/' + D.tab + '/' + D.date); };
  });
  if (D.tab === 'tot') { const n = $('#dNav', el); if (n) n.style.visibility = 'hidden'; return drawDailyPanel($('#dBody', el), el); }   // 看板：从汇总里的链接进入，#daily/tot 仍可用
  if (D.tab === 'stats') return drawDailyStats($('#dBody', el), el);
  [D.pd, D.dd] = await Promise.all([api('/api/paper?date=' + D.date), api('/api/daily?date=' + D.date)]);
  if (!D.pd.sessions.includes(D.ses)) D.ses = D.pd.sessions[0] || '早上';
  const nOpen = D.dd.open.length; if (nOpen) $('[data-t="sum"]', el).insertAdjacentHTML('beforeend', ` <b class="num" style="font-weight:600;color:var(--warn)" title="在外未交回">${nOpen}</b>`);
  if (D.tab === 'sum') return drawDailySum($('#dBody', el), el);
  ppWork(); drawPaper($('#dBody', el), el);
};

/* 表头：同一「分组」的相邻列合并（如 回收 40L/10L、制氧机 医用3L…） */
function ppHead(lay, cyl) {
  const grp = cols => { const out = []; cols.forEach(c => { const g = c.g || ''; const l = out[out.length - 1]; if (g && l && l.g === g) l.cols.push(c); else out.push({ g, cols: [c] }); }); return out; };
  const nm = c => esc(c.n).replace(/^(\d+L|医用|家用)(?=.)/, '$1<br>');
  const r1 = side => grp(lay[side]).map(x => x.g ? `<th colspan="${x.cols.length}">${esc(x.g)}</th>` : `<th rowspan="2">${nm(x.cols[0])}</th>`).join('');
  const r2 = side => grp(lay[side]).filter(x => x.g).map(x => x.cols.map(c => `<th>${nm(c)}</th>`).join('')).join('');
  return `<tr><th rowspan="3" class="pl">车牌</th><th rowspan="3" class="dv">配送员</th><th colspan="${lay.L.length}" class="blk">${esc(lay.lt)}</th><th rowspan="3" class="nt">备注</th><th rowspan="3" class="gap"></th><th colspan="${lay.R.length}" class="blk">${esc(lay.rt)}</th><th rowspan="3" class="nt">备注</th><th rowspan="3" class="pm"></th></tr>
    <tr>${r1('L')}${r1('R')}</tr><tr>${r2('L')}${r2('R')}</tr>`;
}

function drawPaper(box, page) {
  const form = D.tab, sh = D.sh, lay = sh.lay;
  const ro = form === 'prod', cyS = ro ? ppSheet('cyl') : null;   // 产品表：车牌、配送员只读，跟钢瓶表
  const sesHas = s => D.pd.sheets.some(x => x.form === form && x.session === s);
  const retCol = k => lay.lmode !== 'all' && k.startsWith('L.');
  const colOf = {}; ['L', 'R'].forEach(sd => lay[sd].forEach(c => colOf[sd + '.' + c.k] = c));
  // 两张表（同一场次、同一车牌）都记了同一产品 → 黄色提醒核对（不拦）
  const other = ppSheet(form === 'cyl' ? 'prod' : 'cyl', D.ses);
  const otherPids = plate => { if (!other) return new Set(); const r = other.rows.find(x => (x.plate || '').toLowerCase() === (plate || '').toLowerCase()); return new Set(r ? r.pids : []); };
  const bothSet = r => { const op = otherPids(r.plate); const s = new Set(); Object.entries(r.cells || {}).forEach(([k, v]) => { const c = colOf[k]; if (v && c && colId(c) && op.has(colId(c))) s.add(colId(c)); }); return s; };
  // 保存后改过的格子：小标记，悬停看原来的数
  const edOf = {}; (sh.edits || []).forEach(e => { (edOf[e.rid + '|' + e.k] = edOf[e.rid + '|' + e.k] || []).push(e); });
  const edTip = (rid, k) => { const es = edOf[rid + '|' + k]; return es ? es.map(e => `${fmtTs(e.ts)} ${e.by}：${e.old || '空'} → ${e.new || '空'}`).join('\n') : ''; };
  const bmPids = Object.keys(D.pd.bm).filter(p => ppLayPids(lay).has(+p));
  const cell = (r, ri, side, c, ci, both) => {
    const k = side + '.' + c.k, p = ppParse((r.cells || {})[k]), tip = edTip(r.rid, k);
    const chk = both.has(colId(c)) && (r.cells || {})[k];
    return `<td class="pc ${p.ret && retCol(k) ? 'ret' : ''} ${p.ok ? '' : 'err'} ${retCol(k) && c.t === 'p' ? 'lp' : ''} ${chk ? 'chk' : ''} ${tip ? 'ed' : ''}" ${tip || chk ? `title="${esc((chk ? '另一张表也记了这个产品，请核对\n' : '') + (tip ? '修改过：\n' + tip : ''))}"` : ''}><input data-r="${ri}" data-c="${ci}" data-k="${k}" value="${esc(p.ok ? p.txt : (r.cells || {})[k])}" autocomplete="off">${retCol(k) && c.t === 'p' ? `<button class="rtb" tabindex="-1" data-rt="${ri}|${k}" title="退回库房（纸上写了「退」）">退</button>` : ''}</td>`;
  };
  const tags = r => [(r.hand || []).length ? `<span class="tag">手工单 ${r.hand.length}</span>` : '', r.open ? '<span class="tag warn">在外未交回</span>' : '',
    !r.open && r.book_date && r.book_date !== D.date ? `<span class="tag" title="旧「记到哪天」已停用，跨日请靠次日清点；保存后会清掉">旧记到 ${md(r.book_date)}</span>` : '', Object.keys(r.batches || {}).length ? '<span class="tag">本行批次</span>' : ''].join('');
  const body = sh.rows.map((r, ri) => {
    let ci = 0; const both = bothSet(r);
    const pl = r.extra && !ro ? `<input class="ppl" data-r="${ri}" data-c="${ci++}" data-pl="1" value="${esc(r.plate || '')}" placeholder="车牌">` : `<b>${esc(r.plate)}</b>`;
    const dtip = edTip(r.rid, 'driver');
    const dvr = r.driver_r ? `<span class="dvr" ${ro ? '' : `data-dvr="${ri}"`} title="新装换人：左边（退库 / 车上剩余）记 ${esc(r.driver || '')}，右边新装记 ${esc(r.driver_r)}">→${esc(r.driver_r)}</span>` : '';
    const dv = ro ? `<td class="dv ro ${r._cyl ? '' : 'pre'}" title="${r._cyl ? '跟钢瓶页（要改请到钢瓶页改）' : '钢瓶页还没有这辆车：先按上次的人显示，请在钢瓶页填'}">${esc(r.driver || '')}${dvr}</td>`
      : `<td class="dv ${dtip ? 'ed' : ''} ${r._pre && !ppHas(r) ? 'pre' : ''} ${r.driver_r ? 'has-r' : ''}" ${dtip ? `title="${esc('修改过：\n' + dtip)}"` : ''}><input data-r="${ri}" data-c="${ci++}" data-dv="1" value="${esc(r.driver || '')}" list="ppCour" placeholder="配送员">${dvr}</td>`;
    const nt = (n) => { const t = edTip(r.rid, n); return `<td class="nt ${t ? 'ed' : ''}" ${t ? `title="${esc('修改过：\n' + t)}"` : ''}><input data-r="${ri}" data-c="${ci++}" data-n="${n}" value="${esc(r[n] || '')}"></td>`; };
    return `<tr class="${ppHas(r) ? 'has' : ''}"><td class="pl">${pl}${tags(r)}${both.size ? '<span class="tag chk" title="同一场次两张表都记了同一产品">核对</span>' : ''}</td>${dv}
      ${lay.L.map(c => cell(r, ri, 'L', c, ci++, both)).join('')}${nt('note_l')}<td class="gap"></td>
      ${lay.R.map(c => cell(r, ri, 'R', c, ci++, both)).join('')}${nt('note_r')}
      <td class="pm"><span class="ra-more"><button class="ra-dots" type="button" title="更多">⋯</button><span class="ra-menu">
        <a data-act="hand" data-r="${ri}">手工单产品…</a><a data-act="book" data-r="${ri}">在外未交回…</a>${ro ? '' : `<a data-act="swap" data-r="${ri}">新装换人…</a>`}${bmPids.length ? `<a data-act="bat" data-r="${ri}">本行批次（例外）…</a>` : ''}<a data-act="clear" data-r="${ri}">清空这一行</a>
        ${r.extra ? `<a data-act="del" data-r="${ri}" class="d">删除这一行</a>` : (ppHas(r) || ro ? '' : `<a data-act="hide" data-r="${ri}">隐藏这个车牌（以后的表不显示）</a>`)}</span></span></td></tr>`;
  }).join('');
  const totRow = () => {
    const t = k => { let a = 0, rt = 0; sh.rows.forEach(r => { const p = ppParse((r.cells || {})[k]); if (p.ok && p.v) { a += p.v; if (p.ret) rt += p.v; } }); return [a, rt]; };
    const td = (sd, c) => { const k = sd + '.' + c.k; const [a, rt] = t(k); return `<td>${a ? fmtN(a) : ''}${retCol(k) && rt ? `<small class="rtt">退${fmtN(rt)}</small>` : ''}</td>`; };
    return `<tr class="tot"><td class="pl">合计</td><td></td>${lay.L.map(c => td('L', c)).join('')}<td></td><td class="gap"></td>${lay.R.map(c => td('R', c)).join('')}<td></td><td></td></tr>`;
  };
  const nChk = sh.rows.filter(r => bothSet(r).size).length;
  box.innerHTML = `<div class="card page-card pp-card shell-list">
    <div class="tools pp-bar"><div class="tg"><div class="pp-ses" id="ppSes">${D.pd.sessions.map(s => `<button class="${s === D.ses ? 'on' : ''}" data-s="${esc(s)}">${esc(s)}${sesHas(s) ? '<i>✓</i>' : ''}</button>`).join('')}<button data-add="1" title="加一个场次">＋</button></div>
      <div class="pp-ttl">${esc(FORM_CN[form])} <small>${md(D.date)} ${esc(D.ses)}</small></div>
      ${bmPids.map(p => `<label class="pp-bat">${esc(D.pd.bm[p].name)} 批次 <select class="inp sm" data-bat="${p}">${D.pd.bm[p].batches.map(b => `<option value="${esc(b.batch_no)}" ${sh.batches[p] === b.batch_no ? 'selected' : ''}>${esc(b.batch_no)}（剩 ${fmtN(b.remain)}${b.batch_no === D.pd.bm[p].fifo ? '，先进先出' : ''}）</option>`).join('')}</select></label>`).join('')}</div>
      <span class="sp"></span><div class="tg acts pp-r">${nChk ? `<span class="tag chk">${nChk} 辆车两张表都记了同一产品，请核对</span>` : ''}<span id="ppSt" class="muted" style="font-size:12.5px">${sh.id ? `已保存 · ${esc(sh.by || '')} ${fmtTs(sh.ts)}` : '这一场还没录'}</span>
        ${(sh.edits || []).length ? `<a class="link" id="ppHist" style="font-size:12.5px">修改记录 ${sh.edits.length}</a>` : ''}
        ${sh.id ? '<a class="link" id="ppMove" style="font-size:12.5px" title="录错了日期 / 场次时用：整张表搬过去，出入库和库存自动重算">改日期 / 场次</a><a class="link d" id="ppDel" style="font-size:12.5px">删除这张表</a>' : ''}<button class="btn" id="ppPrint" title="只打有数的车，每辆车下面空一行，A4 横向一页">打印</button><button class="btn pri" id="ppSave" disabled>${sh.id ? '已保存' : '保存'}</button></div></div>
    ${ro ? `<div class="pp-follow ${cyS ? '' : 'warn'}" title="${cyS ? '车牌、配送员跟钢瓶页，要改请到钢瓶页' : '请先录钢瓶页；录好后这里自动跟上'}">${cyS ? '车牌/配送员跟<a data-gocyl="1">钢瓶页</a>（只读）' : '<b>请先录钢瓶页</b> · 录好<a data-gocyl="1">钢瓶页</a>后自动跟上'}</div>` : ''}
    <div class="tw pp-tw"><table class="pp ${form}" id="ppT"><thead>${ppHead(lay)}</thead><tbody>${body}${totRow()}</tbody></table></div>
    <datalist id="ppCour">${S.boot.couriers.filter(k => k.active).map(k => `<option value="${esc(k.name)}">`).join('')}</datalist>
    <div class="pp-foot">${ro ? '<span class="muted">加车请到钢瓶页加</span>' : '<a class="link" id="ppAdd">＋ 加一行（别的车）</a>'}
      <span class="muted pp-ftip">${lay.lmode !== 'all' ? '写「退」/点「退」=入库，不写=留车上 · Ctrl+S' : '左=入库 · 右=出库 · Ctrl+S'}<details class="ph-help"><summary></summary><div class="ph-help-b">${lay.lmode !== 'all' ? '左边写了「退」的数（输入 5退 或 5t，或点格子右上角「退」）= 退回库房，算入库；没写「退」= 留在车上，只记录不算库存。' : '左边 = 退回库房（入库）；右边新装车 = 出库。'}配送员每次可改（下拉或直接写，新名字自动加进名单）。方向键/回车移动，Ctrl+S 保存。签字留在纸上，可把签好字的纸拍照附上。</div></details></span>
      <div class="pp-ph" id="ppPh"></div></div></div>`;
  const T = $('#ppT', box);
  const pb = photoBox($('#ppPh', box), sh.photos, { onchange: () => ppDirty() });
  const redraw = () => drawPaper(box, page);
  const redrawTot = () => { $('tr.tot', T).outerHTML = totRow(); };
  const setCell = (inp, raw) => {
    const r = sh.rows[+inp.dataset.r]; r.cells = r.cells || {};
    const td = inp.parentNode, p = ppParse(raw);
    if (!retCol(inp.dataset.k)) p.ret = false;
    const store = p.ok ? (p.txt ? p.txt + (p.ret ? '退' : '') : '') : String(raw).trim();
    if (store) r.cells[inp.dataset.k] = store; else delete r.cells[inp.dataset.k];
    td.classList.toggle('ret', !!(p.ret && p.txt)); td.classList.toggle('err', !p.ok);
    inp.closest('tr').classList.toggle('has', !!ppHas(r));
  };
  T.addEventListener('input', e => {
    const t = e.target; if (t.tagName !== 'INPUT') return;
    const r = sh.rows[+t.dataset.r];
    if (t.dataset.n) r[t.dataset.n] = t.value;
    else if (t.dataset.pl) r.plate = t.value.trim();
    else if (t.dataset.dv) { r.driver = t.value.trim(); r.courier_id = null; r._pre = false; t.parentNode.classList.remove('pre'); }
    else {
      if (/(退|t)$/i.test(t.value.trim()) && retCol(t.dataset.k)) { setCell(t, t.value); t.value = ppParse(t.value).txt; }   // 输入 5t / 5退 → 标「退」
      else { const was = ppParse((r.cells || {})[t.dataset.k]).ret; setCell(t, t.value + (was && t.value.trim() ? '退' : '')); }
      redrawTot();
    }
    ppDirty();
  });
  const refreshChk = ri => {   // 改了产品格子：当场更新这一行的「核对」黄色
    if (!other) return; const r = sh.rows[ri], both = bothSet(r);
    $$(`input[data-r="${ri}"][data-k]`, T).forEach(i => { const c = colOf[i.dataset.k]; i.parentNode.classList.toggle('chk', !!(c && both.has(colId(c)) && (r.cells || {})[i.dataset.k])); });
    const pc = $(`input[data-r="${ri}"]`, T).closest('tr').querySelector('td.pl'); const tg = $('.tag.chk', pc);
    if (both.size && !tg) pc.insertAdjacentHTML('beforeend', '<span class="tag chk" title="同一场次两张表都记了同一产品">核对</span>'); else if (!both.size && tg) tg.remove();
  };
  T.addEventListener('input', e => { if (e.target.dataset.k) refreshChk(+e.target.dataset.r); });
  T.addEventListener('click', async e => {
    const dr = e.target.closest('[data-dvr]'); if (dr) return ppSwap(sh.rows[+dr.dataset.dvr], redraw);
    const b = e.target.closest('.rtb');
    if (b) { const [ri, k] = b.dataset.rt.split('|'); const inp = $(`input[data-r="${ri}"][data-k="${k}"]`, T); const p = ppParse((sh.rows[+ri].cells || {})[k]);
      if (!p.txt) { inp.focus(); return toast('先填数，再点「退」', true); } setCell(inp, p.txt + (p.ret ? '' : '退')); redrawTot(); ppDirty(); inp.focus(); return; }
    const a = e.target.closest('[data-act]'); if (!a) return;
    const ri = +a.dataset.r, r = sh.rows[ri];
    const on = document.querySelector('.ra-more.on'); if (on) on.classList.remove('on');
    if (a.dataset.act === 'clear') { r.cells = {}; r.note_l = r.note_r = ''; r.hand = []; r.batches = {}; ppDirty(); redraw(); }
    if (a.dataset.act === 'del') { sh.rows.splice(ri, 1); ppDirty(); redraw(); }
    if (a.dataset.act === 'hand') ppHand(r, redraw);
    if (a.dataset.act === 'book') ppBook(r, redraw);
    if (a.dataset.act === 'swap') ppSwap(r, redraw);
    if (a.dataset.act === 'bat') ppRowBatch(r, bmPids, redraw);
    if (a.dataset.act === 'hide') {
      if (!await confirmBox(`以后的表不再显示车牌「${esc(r.plate)}」？（已录的表不受影响；要恢复可在「表格设置」里加回，或直接「＋ 加一行」写这个车牌）`, '隐藏')) return;
      try { await save('/api/paper/plates', { plates: D.pd.plates.map(p => p.plate).filter(p => p !== r.plate) }, '隐藏车牌'); toast('已隐藏'); D.dirty = false; App.guard = null; App.guardSave = null; Pages.daily(page); } catch (er) { fail(er); }
    }
  });
  T.addEventListener('keydown', e => {
    const t = e.target; if (t.tagName !== 'INPUT') return;
    const r = +t.dataset.r, c = +t.dataset.c;
    const go = (rr, cc) => { const n = $(`input[data-r="${rr}"][data-c="${cc}"]`, T); if (n) { e.preventDefault(); n.focus(); n.select(); return true; } return false; };
    const atS = t.selectionStart === 0 && t.selectionEnd === 0, atE = t.selectionStart === t.value.length;
    if (e.key === 'ArrowDown' && !t.dataset.dv) go(r + 1, c);
    else if (e.key === 'ArrowUp' && !t.dataset.dv) go(r - 1, c);
    else if (e.key === 'ArrowRight' && atE) go(r, c + 1);
    else if (e.key === 'ArrowLeft' && atS) go(r, c - 1);
    else if (e.key === 'Enter') { if (!go(r, c + 1)) go(r + 1, ro ? 0 : (sh.rows[r + 1] && sh.rows[r + 1].extra ? 0 : 1)); }
  });
  T.addEventListener('focusin', e => { if (e.target.tagName === 'INPUT') e.target.closest('tr').classList.add('cur'); });
  T.addEventListener('focusout', e => { if (e.target.tagName === 'INPUT') e.target.closest('tr').classList.remove('cur'); });
  gridFocusOn(T);   // 当前格的行、列淡淡标出来
  if (typeof CellSel !== 'undefined') CellSel.on(T);
  requestAnimationFrame(() => { syncStickyHeads(T); });
  $$('[data-bat]', box).forEach(s => s.onchange = () => { sh.batches[s.dataset.bat] = s.value; ppDirty(); });
  $('#ppSes', box).onclick = async e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.add) {
      return dialog('加一个场次', '<span class="lab">场次名称（纸上表头写的，如「下午」「第二趟」）</span><input class="inp" id="nsN">', [{ t: '取消' }, { t: '确定', cls: 'pri', fn: async ov => {
        const n = $('#nsN', ov).value.trim(); if (!n) throw new Error('请填名称');
        if (D.dirty && !await confirmDirty('当前表还有改动没保存，切换前要先处理。', App.guardSave)) return;
        D.dirty = false; App.guard = null; App.guardSave = null;
        if (!D.pd.sessions.includes(n)) D.pd.sessions.push(n); D.ses = n; ppWork(); drawPaper(box, page); } }]);
    }
    if (b.dataset.s === D.ses) return;
    if (D.dirty && !await confirmDirty('当前表还有改动没保存，切换前要先处理。', App.guardSave)) return;
    D.dirty = false; App.guard = null; App.guardSave = null;
    D.ses = b.dataset.s; ppWork(); drawPaper(box, page);
  };
  $$('[data-gocyl]', box).forEach(a => a.onclick = async () => { if (D.dirty && !await confirmDirty('产品页还有改动没保存，切换前要先处理。', App.guardSave)) return; D.dirty = false; App.guard = null; App.guardSave = null; D.tab = 'cyl'; Pages.daily(page); });
  $('#ppPrint', box).onclick = () => ppPrint(sh, lay, form);
  if ($('#ppAdd', box)) $('#ppAdd', box).onclick = () => { sh.rows.push({ rid: 'x' + Date.now(), extra: true, plate: '', driver: '', cells: {}, hand: [] }); redraw(); const n = $$('input.ppl', box).pop(); n && n.focus(); };
  const hi = $('#ppHist', box); if (hi) hi.onclick = () => ppHistDlg(sh);
  const mv = $('#ppMove', box); if (mv) mv.onclick = () => ppMove(sh, form, page);
  const del = $('#ppDel', box);
  if (del) del.onclick = async () => {
    try { if (!await confirmDelete('paper', sh.id, '/api/paper/delete')) return; App.guard = null; App.guardSave = null; D.dirty = false; toast('已删除'); Pages.daily(page); } catch (er) { fail(er); }
  };
  const doSave = async () => {
    const bad = $$('td.err', T); if (bad.length) { bad[0].querySelector('input').focus(); return toast('红色格子看不懂：只能写数字、10+2、10-2' + (lay.lmode !== 'all' ? '、5退' : ''), true); }
    const noName = sh.rows.find(r => r.extra && ppHas(r) && !(r.plate || '').trim()); if (noName) return toast('新加的行请填车牌', true);
    const rowsOut = sh.rows.filter(r => ppHas(r) || (r.extra && (r.plate || '').trim()) || (sh.id && !r.rid.startsWith('p_')) || (!ro && r.driver && !r._pre && !r.courier_id)).map(r => ({ rid: r.rid, crid: r.crid, driver_r: r.driver_r || '', courier_id_r: r.driver_r ? r.courier_id_r : null, plate: r.plate, driver: r.driver, courier_id: r.courier_id, cells: r.cells, note_l: r.note_l, note_r: r.note_r, hand: r.hand, batches: r.batches, book_date: null, open: !!r.open, extra: !!r.extra }));
    if (!sh.id && !rowsOut.some(ppHas)) return toast('还没填数', true);
    try {
      await save('/api/paper/save', { data: { id: sh.id, date: D.date, session: D.ses, form, rows: rowsOut, batches: sh.batches }, base_ts: sh.updated_at, photo_ids: pb.ids }, '保存' + FORM_CN[form]);
      D.dirty = false; App.guard = null; App.guardSave = null; toast(sh.id ? '已保存修改，库存和汇总已重算' : '已保存，已汇总进产品出入库情况'); await loadBoot(); Pages.daily(page);
    } catch (er) { fail(er); }
  };
  $('#ppSave', box).onclick = doSave;
  App.guardSave = doSave;
  if (D.dirty) ppDirty();
  document.onkeydown = e => { if ((e.ctrlKey || e.metaKey) && e.key === 's' && $('#ppSave')) { e.preventDefault(); if (D.dirty) doSave(); } };
}

/* 打印交接表：只打有数的车（每辆车下面空一行，给核对写字），A4 横向缩到一页 */
function ppPrint(sh, lay, form) {
  const rs = sh.rows.filter(ppHas);
  if (!rs.length) return toast('这张表还没有数', true);
  const hd = ppHead(lay).replace(/<th rowspan="3" class="(gap|pm)"><\/th>/g, '').replace(/ class="[^"]*"/g, '');
  const ncol = 2 + lay.L.length + 1 + lay.R.length + 1;
  const cell = (r, sd, c) => esc((r.cells || {})[sd + '.' + c.k] || '');
  const body = rs.map(r => `<tr><td class="l">${esc(r.plate || '')}</td><td class="l">${esc(r.driver || '')}${r.driver_r ? '→' + esc(r.driver_r) : ''}</td>${lay.L.map(c => `<td>${cell(r, 'L', c)}</td>`).join('')}<td class="l">${esc(r.note_l || '')}</td>${lay.R.map(c => `<td>${cell(r, 'R', c)}</td>`).join('')}<td class="l">${esc(r.note_r || '')}</td></tr><tr class="bl">${'<td>&nbsp;</td>'.repeat(ncol)}</tr>`).join('');
  const sum = (sd, c) => { let a = 0; rs.forEach(r => { const p = ppParse((r.cells || {})[sd + '.' + c.k]); if (p.ok && p.v) a += p.v; }); return a ? fmtN(a) : ''; };
  const tot = `<tr><td colspan="2">合计</td>${lay.L.map(c => `<td>${sum('L', c)}</td>`).join('')}<td></td>${lay.R.map(c => `<td>${sum('R', c)}</td>`).join('')}<td></td></tr>`;
  printHtml(`<style>.print-host table.pprint tr.bl td{height:16px}.print-host table.pprint th{font-weight:bold}</style><div class="ttl">${esc(FORM_CN[form])}　${md(D.date)} ${esc(D.ses)}</div><table class="pprint"><thead>${hd}</thead><tbody>${body}${tot}</tbody></table>`,
    { landscape: true, font: '9pt', titleSize: '16pt', margin: '8mm', fit: true });
}
function ppHistDlg(sh) {
  const es = (sh.edits || []).slice().reverse();
  dialog('修改记录 · ' + md(D.date) + ' ' + D.ses + ' ' + FORM_CN[D.tab], `<div class="hint" style="margin-top:0">第一次保存以后的每次改动（逐格：原来 → 改成）。整张表的保存记录也在「数据备份 → 操作记录」。</div>
    <div class="tw" style="max-height:60vh"><table class="t"><thead><tr><th>时间</th><th>谁</th><th>车牌</th><th>格子</th><th class="n">原来</th><th class="n">改成</th></tr></thead><tbody>
    ${es.map(e => `<tr><td class="w">${fmtTs(e.ts)}</td><td class="w">${esc(e.by)}</td><td class="w">${esc(e.plate)}</td><td>${esc(e.label)}</td><td class="n muted">${esc(e.old || '空')}</td><td class="n"><b>${esc(e.new || '空')}</b></td></tr>`).join('')}</tbody></table></div>`, null, { wide: true });
}
function ppRowBatch(r, pids, redraw) {
  r.batches = r.batches || {};
  dialog('本行批次 · ' + (r.plate || ''), `<div class="hint" style="margin-top:0">一般整张表用同一个批次（表上方选）。这辆车拿的是别的批次时，在这里单独指定。</div>
    ${pids.map(p => `<div style="margin-top:10px"><span class="lab">${esc(D.pd.bm[p].name)}</span><select class="inp" data-b="${p}"><option value="">（跟整张表：${esc(D.sh.batches[p] || '')}）</option>${D.pd.bm[p].batches.map(b => `<option value="${esc(b.batch_no)}" ${r.batches[p] === b.batch_no ? 'selected' : ''}>${esc(b.batch_no)}（剩 ${fmtN(b.remain)}）</option>`).join('')}</select></div>`).join('')}`,
    [{ t: '取消' }, { t: '确定', cls: 'pri', fn: ov => { $$('[data-b]', ov).forEach(s => { if (s.value) r.batches[s.dataset.b] = s.value; else delete r.batches[s.dataset.b]; }); ppDirty(); redraw(); } }]);
}

function ppHand(r, redraw) {
  r.hand = r.hand || [];
  const ov = dialog('手工单产品 · ' + (r.plate || ''), `<div class="hint" style="margin-top:0">纸上手工单写的产品，单独记，照扣库存，下载时写进备注。</div>
    <div id="hdL" style="margin:8px 0"></div><div class="split"><input class="inp sm" id="hdP" placeholder="产品" style="width:220px"><input class="inp sm num" id="hdQ" placeholder="数量" style="width:80px"><button class="btn sm" id="hdA">加入</button></div>`,
    [{ t: '完成', cls: 'pri', fn: () => { redraw(); } }]);
  const dl = () => { $('#hdL', ov).innerHTML = r.hand.length ? r.hand.map((h, i) => `<span class="chip has">${esc(P.label(h.product_id))} ${h.qty} <a class="link d" data-x="${i}">✕</a></span>`).join(' ') : '<span class="muted">还没有</span>'; };
  dl(); let pid = null; const hp = $('#hdP', ov);
  autoComplete(hp, async q => P.search(q).slice(0, 10), p => { pid = p.id; hp.value = p.label; }, (p, q) => hl(p.label, q));
  $('#hdA', ov).onclick = () => { const q = +$('#hdQ', ov).value; if (!pid || !q) return toast('选产品并填数量', true); r.hand.push({ product_id: pid, qty: q }); pid = null; hp.value = ''; $('#hdQ', ov).value = ''; ppDirty(); dl(); };
  $('#hdL', ov).onclick = e => { if (e.target.dataset.x) { r.hand.splice(+e.target.dataset.x, 1); ppDirty(); dl(); } };
}
/* 新装换人：同一辆车这一场左边（交回的）是一个人，右边新装是另一个人 */
/** 改日期 / 场次：录错了日期（如 19 号的数录到了 20 号）。同场次的另一张表默认一起搬；目标已有表就拦住，不覆盖 */
async function ppMove(sh, form, page) {
  if (D.dirty) return toast('这张表还有改动没保存，请先保存或放弃改动，再改日期', true);
  const of = form === 'cyl' ? 'prod' : 'cyl', mate = D.pd.sheets.find(x => x.form === of && x.session === D.ses);
  const sess = [...new Set([...D.pd.sessions, ...((S.boot.settings || {}).paper_sessions || []).map(x => x.n || x)])].filter(Boolean);
  dialog('改日期 / 场次 · ' + FORM_CN[form], `<div class="hint" style="margin-top:0">现在是 <b>${esc(D.date)} ${esc(D.ses)}</b>。整张表（含照片、修改记录）搬到新的日期 / 场次，出入库、库存、次日清点按新日期重算，记进操作记录。</div>
    <div style="display:flex;gap:10px;align-items:end;margin:8px 0"><label style="flex:1"><span class="lab">新日期</span><input class="inp" type="date" id="mvD" value="${esc(addDays(D.date, -1))}"></label>
    <label style="flex:1"><span class="lab">新场次</span><select class="inp" id="mvS">${sess.map(x => `<option ${x === D.ses ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select></label></div>
    ${mate ? `<label style="display:block;margin:6px 0"><input type="checkbox" id="mvP" checked> 同时搬同场次的「${esc(FORM_CN[of])}」（建议，两张是一起录的）</label>` : `<div class="muted" style="font-size:12.5px">同场次没有${esc(FORM_CN[of])}，只搬这一张。</div>`}
    <div id="mvMsg" class="muted" style="font-size:12.5px;margin-top:6px"></div>`,
    [{ t: '取消' }, { t: '改过去', cls: 'pri', fn: async ov => {
      const nd = $('#mvD', ov).value, ns = $('#mvS', ov).value, pair = !!($('#mvP', ov) && $('#mvP', ov).checked);
      const pl = await api('/api/paper/move_check?' + new URLSearchParams({ id: sh.id, date: nd, session: ns, pair: pair ? '1' : '0' }));
      if (pl.clash.length) { $('#mvMsg', ov).innerHTML = '<span style="color:var(--bad)">' + pl.clash.map(esc).join('<br>') + '</span>'; return false; }
      const names = pl.sheets.map(x => FORM_CN[x.form]).join('、');
      let msg = `把 <b>${esc(D.date)} ${esc(D.ses)}</b> 的${esc(names)}改到 <b>${esc(nd)} ${esc(ns)}</b>？`;
      if (pl.warn.length) msg += '<div class="hint" style="margin-top:8px">有几行标过「在外未交回 / 旧记到哪天」：<br>' + pl.warn.map(w => esc(FORM_CN[w.form] + ' ' + w.plate + '：') + (w.open ? '在外未交回（照旧）' : '记到 ' + esc(w.book_date) + (w.fix ? '，<b>早于新日期，改回记当天</b>' : '（照旧）'))).join('<br>') + '</div>';
      if (!await confirmBox(msg, '确定改')) return false;
      await save('/api/paper/move', { id: sh.id, date: nd, session: ns, pair }, '改交接表日期');
      toast('已改到 ' + nd + ' ' + ns + '，出入库和库存已重算'); D.date = nd; D.ses = ns; dPersist(); await loadBoot(); Pages.daily(page);
    } }]);
}
function ppSwap(r, redraw) {
  dialog('新装换人 · ' + (r.plate || ''), `<div class="hint" style="margin-top:0">这辆车这一场换了人：左边（退库、回收、车上剩余）记 <b>${esc(r.driver || '左边的配送员')}</b>，右边新装记下面这位。不换人就清空。</div>
    <span class="lab">右边新装的配送员</span><input class="inp" id="swD" list="ppCour" value="${esc(r.driver_r || '')}" placeholder="如 沈兴德">`,
    [{ t: '取消' }, { t: '不换人', fn: () => { r.driver_r = ''; r.courier_id_r = null; ppDirty(); redraw(); } }, { t: '确定', cls: 'pri', fn: ov => {
      const v = $('#swD', ov).value.trim();
      if (v && v === (r.driver || '').trim()) throw new Error('和左边是同一个人，不用换人');
      if (v !== (r.driver_r || '')) { r.driver_r = v; r.courier_id_r = null; } ppDirty(); redraw();
    } }]);
}
function ppBook(r, redraw) {
  /* 1.1.46：去掉「记到哪天」；跨日只靠次日清点自动合几天。这里只保留在外未交回。 */
  const m = r.open ? 'open' : 'today';
  dialog('在外未交回 · ' + (r.plate || ''), `<div class="lst" style="gap:10px;display:grid">
    <div class="hint" style="margin:0">跨天清点不用手改记账日：第二天早上没清到人会「待清点」，下次早上清到后自动几天合计写入汇总。规则开始日在「表格设置」里改。</div>
    <label><input type="radio" name="bk" value="today" ${m === 'today' ? 'checked' : ''}> 正常记（${md(D.date)}，走次日清点）</label>
    <label><input type="radio" name="bk" value="open" ${m === 'open' ? 'checked' : ''}> 还没交回（挂「在外未交回」，交回时在汇总页点「交回」）</label></div>`,
    [{ t: '取消' }, { t: '确定', cls: 'pri', fn: ov => {
      const v = $('input[name=bk]:checked', ov).value;
      if (v === 'open') { r.open = true; r.book_date = null; } else { r.open = false; r.book_date = null; }
      ppDirty(); redraw();
    } }]);
}

/* 汇总页：财务主表增高占满；底下一根横向长条 = 核对情况（左）+ 外面共有 + 在外未交回（不再右侧竖栏） */
function drawDailySum(box, page) {
  const data = D.dd;
  const dayCn = (+D.date.slice(8)) + '号';
  /* 1.1.48：标题 + 次日清点折叠说明 + 导入/打印/下载 并进顶栏 .ph，与页签同一行；卡内不再叠 card-h */
  const ph = page && $('.ph.ph-c', page);
  if (ph) {
    $$('.d-sum-ph', ph).forEach(n => n.remove());
    let sp = $('.sp', ph);
    if (!sp) { sp = document.createElement('span'); sp.className = 'sp'; ph.appendChild(sp); }
    const mid = document.createElement('div');
    mid.className = 'd-sum-ph d-sum-mid';
    mid.innerHTML = `<h2 class="d-sum-ttl">${esc(titleOf(D.date))}</h2>
      <span class="muted pp-ftip">次日清点 · 同 Excel · 领用人序跟当天钢瓶页<details class="ph-help"><summary></summary><div class="ph-help-b">从 2026-10-19 起：某天要等第二天早上交接表录完才算定。第二天早上表的左边（钢瓶退库、产品写了退的、车上剩余）算前一天；其他产品当天用量 = 早上车上剩余（早上左边没写退的）+ 当天新装 − 中午/晚上退 − 第二天早上左边全部（写没写退都算）；第二天早上没清点到的人接着等，下次清点时几天合起来算。领取人信息顺序 = 当天钢瓶交接表各场次行序（与产品页跟钢瓶同源）。下载与原 Excel 一样（隐藏列不显示）。双击行打开汇总核对。</div></details></span>`;
    const right = document.createElement('div');
    right.className = 'd-sum-ph d-sum-acts';
    right.innerHTML = `<a class="link" id="dTot" style="font-size:12.5px" title="所有配送员加起来的数字卡片和趋势图">每日总出库量 →</a>
      <button class="btn sm" id="dImp">导入日表 Excel</button><button class="btn sm" id="dPrint">打印</button><button class="btn sm pri" id="dDown">下载 Excel</button>`;
    sp.before(mid);
    sp.after(right);
  }
  /* 1.1.51：#dSum 自适应高度（不 fit-fill / 不强制 height）；当天领用人一次显示完，底条跟表后；数量统计不加 fit-fill */
  box.innerHTML = `<div class="card d-sum-main"><div class="tw" id="dSum"></div></div>
    <div class="card d-sum-bot" id="dBot" style="margin:0;margin-top:8px">
      <div class="d-bot-verify" id="dVerify"></div>
      <div class="d-bot-side" id="dSide"></div>
    </div>`;
  $('#dSum', box).innerHTML = dailyTable(data);
  if (typeof CellSel !== 'undefined') { const dt = $('#dSum table.dt', box); if (dt) CellSel.on(dt); }
  $('#dSum', box).onclick = e => { const a = e.target.closest('[data-hp]'); if (!a) return; const m = data.merged.find(x => String(x.courier_id) === a.dataset.hp); handPhotos(+a.dataset.hp, m ? (m.label || m.name) : '', n => { data.hand_photos = Object.assign(data.hand_photos || {}, { [a.dataset.hp]: n }); a.outerHTML = n ? `<a class="hp on" data-hp="${a.dataset.hp}" title="手工单照片 ${n} 张（点开看 / 加）">📎${n}</a>` : `<a class="hp" data-hp="${a.dataset.hp}" title="加手工单照片（可选，对账备用；可多张）">＋</a>`; }); };
  $('#dSum', box).ondblclick = e => { if (e.target.closest('a,button,input')) return; const tr = e.target.closest('tr[data-cid]'); if (!tr || tr.classList.contains('tot')) return; const m = data.merged.find(x => String(x.courier_id) === tr.dataset.cid); if (m) courierSumDetail(m, data, page); };
  drawDailyVerify($('#dVerify', box), data, page, dayCn);
  drawDailySide($('#dSide', box), data, page);
  const bar = ph || box;
  $('#dDown', bar).onclick = () => download('/api/daily/export.xlsx?date=' + D.date);
  $('#dTot', bar).onclick = () => { D.tab = 'tot'; App.tab('daily/tot/' + D.date); };
  $('#dPrint', bar).onclick = async () => {
    try { const r = await api('/api/daily/print?date=' + D.date); printHtml(r.html, { landscape: true, margin: '8mm', fit: true, noCompany: true }); } catch (er) { fail(er); }
  };
  $('#dImp', bar).onclick = async () => {
    try {
      const [f] = await pickFiles('.xlsx'); if (!f) return;
      if (!await confirmBox(`导入「${esc(f.name)}」：表里的配送员会加入名单；数据作为当天历史记录（按表头日期）。<br>同一天已有记录时会重复，请先确认当天没录过。`, '导入')) return;
      const r = await saveRaw('/api/daily/import?history=1', f, '导入日表');
      toast(`已导入 ${r.date}：${r.entries} 条，新增配送员 ${r.couriers_added.length} 人`); await loadBoot(); D.date = r.date; dPersist(); Pages.daily(page);
    } catch (e) { fail(e); }
  };
  if (typeof Fit !== 'undefined' && Fit.go) Fit.go();
}

/** 1.1.48：当天总核对（一天一个已核对/未核对）；矮条不占高度，主表 #dSum 往下多占（Fit 增高，不改字号）。 */
function drawDailyVerify(box, data, page, dayCn) {
  const ver = data.verify || {};
  const on = !!ver.ok;
  const tip = on ? `已核对 · ${esc(ver.by || '')} ${ver.ts ? fmtTs(ver.ts) : ''}（再点取消）` : '点一下标记当天已核对（要密码，进操作记录）';
  box.innerHTML = `<div class="dv-day${on ? ' on' : ''}" title="${tip}">
      <label class="dv-day-lab"><input type="checkbox" id="dvDay" ${on ? 'checked' : ''}> <b>核对情况</b>
        <span class="dv-day-st">${on ? '当天已核对' : '当天未核对'}</span>
        ${on && ver.by ? `<small class="muted">${esc(ver.by)}${ver.ts ? ' · ' + fmtTs(ver.ts) : ''}</small>` : ''}
      </label>
      <small class="muted">双击上表行仍可开汇总核对</small>
    </div>`;
  const inp = $('#dvDay', box);
  if (!inp) return;
  inp.onchange = async () => {
    const want = inp.checked;
    try {
      const r = await save('/api/daily/verify', { date: D.date, ok: want }, want ? (dayCn + ' 当天已核对') : (dayCn + ' 取消核对'));
      data.verify = r.verify || { ok: want };
      toast(want ? (dayCn + ' 当天已核对') : (dayCn + ' 未核对'));
      drawDailyVerify(box, data, page, dayCn);
      if (typeof Fit !== 'undefined' && Fit.go) Fit.go();
    } catch (er) { inp.checked = !want; fail(er); }
  };
}

/** 1.1.49：外面共有 + 在外未交回 → 汇总页底条横向（不再右侧竖栏） */
function drawDailySide(box, data, page) {
  const o = data.outside;
  const outN = z => o[z].total === null ? `<span class="unk" title="在设置里填起始数后显示">未知</span>` : `<b class="num">${o[z].total}</b>`;
  const openHtml = data.open.length
    ? data.open.map(e => `<span class="d-bot-open-it"><span class="tt">${esc(e.cname)}</span><span class="dd muted">${md(e.out_date)} · 40L ${dnum(e.vals.o40)} · 10L ${dnum(e.vals.o10)}</span><button class="btn sm" data-rt="${e.id}">交回</button></span>`).join('')
    : '<span class="muted" style="font-size:12.5px">没有</span>';
  box.innerHTML = `<div class="d-bot-out">
      <div class="d-bot-h"><b>外面共有</b><a onclick="location.hash='settings/daily'" class="link" style="font-size:12px">设起始数</a>
        <span class="muted pp-ftip" style="font-size:12px">= 起始 + 新送 − 回收<details class="ph-help"><summary></summary><div class="ph-help-b">= 起始数 + 累计新送 − 累计回收（新送 ${o['40'].new}/${o['10'].new}，回收 ${o['40'].rec}/${o['10'].rec}）</div></details></span>
      </div>
      <div class="d-bot-out-nums"><span class="d-bot-n">${outN('40')}<small>40L 在外 · 累计 ${o['40'].delta >= 0 ? '+' : ''}${o['40'].delta}</small></span>
        <span class="d-bot-n">${outN('10')}<small>10L 在外 · 累计 ${o['10'].delta >= 0 ? '+' : ''}${o['10'].delta}</small></span></div>
    </div>
    <div class="d-bot-open">
      <div class="d-bot-h"><b>在外未交回</b><small class="muted">${data.open.length}</small>
        <span class="muted pp-ftip" style="font-size:12px">交回记到 ${md(D.date)}<details class="ph-help"><summary></summary><div class="ph-help-b">交回记在当前选的日期（${md(D.date)}），备注自动写「X–Y 合并」。</div></details></span>
      </div>
      <div class="d-bot-open-lst">${openHtml}</div>
    </div>`;
  box.onclick = async e => {
    const id = e.target.dataset.rt; if (!id) return;
    const en = data.open.find(x => x.id === +id);
    if (!await confirmBox(`${esc(en.cname)} ${md(en.out_date)} 领的，交回记到 ${md(D.date)}？`, '交回')) return;
    try {
      const m = /^paper:(\d+):(.+)$/.exec(en.legacy || '');
      if (m) await save('/api/paper/settle', { sheet_id: +m[1], rid: m[2], book_date: D.date }, '交回');
      else await save('/api/daily/save', { data: { id: en.id, courier_id: en.courier_id, out_date: en.out_date, book_date: D.date, vals: en.vals, hand: en.hand, note: en.note } }, '交回');
      toast('已交回，记到 ' + md(D.date)); Pages.daily(page);
    } catch (er) { fail(er); }
  };
}

/** 这个配送员当天有没有数（全是 0、没备注 = 没有数，下载 / 打印不出现） */
/** 备注太长（超过备注格一行，约 14 个汉字；与下载 Excel 同一规则）：打印时放到这人下面那一空行（整行合并、靠左换行），备注格写「见下行」 */
const noteW = t => [...String(t || '')].reduce((n, ch) => n + (ch.codePointAt(0) > 0x2e7f ? 2 : 1), 0), noteLong = t => noteW(t) > 28;
const dHasData = m => Object.entries(m.vals || {}).some(([k, v]) => !k.startsWith('b_') && !k.startsWith('si_') && !k.startsWith('v0_') && dnum(v)) || !!(m.note || '').trim() || !!m.pending || !!m.merged_into || !!m.period;
/** 当天汇总表：列与原 Excel 可见列一致（A–S、AW–BK） */
/** 手工单照片：这个配送员这一天一组，可多张（粘贴 / 选文件 / 手机连拍），缩略图可滚动，点开大图左右翻；删除要密码。不打印 */
async function handPhotos(cid, name, onCount) {
  let list = [];
  const load = async () => { list = (await api('/api/hand_photos?' + new URLSearchParams({ date: D.date, courier_id: cid }))).items; draw(); onCount && onCount(list.length); };
  const ov = dialog('手工单照片 · ' + name + ' · ' + md(D.date), `<div class="hint" style="margin-top:0">这个配送员当天的手工单拍照留底（对账备用，可多张）。只存在电脑主机上，不打印；交接表改了、重算了，照片也还在。</div>
    <div class="hp-grid photos" id="hpG"></div><div class="muted" id="hpN" style="font-size:12.5px;margin-top:6px"></div>`,
    [{ t: '关闭' }, { t: '＋ 加照片', cls: 'pri', fn: async () => {
      const ps = await photoPick({ title: '加手工单照片 · ' + name, label: '手工单 ' + name + ' ' + md(D.date) });
      if (!ps.length) return false;
      const r = await save('/api/hand_photos/attach', { date: D.date, courier_id: cid, ids: ps.map(p => p.id) }, '保存手工单照片');
      toast('已加 ' + r.n + ' 张'); await load(); return false;
    } }], { wide: true, nofocus: true });
  const draw = () => {
    $('#hpG', ov).innerHTML = list.length ? list.map((p, i) => `<div class="ph-w"><img class="ph-i" src="/photos/${esc(p.path)}" data-i="${i}" loading="lazy" title="${esc((p.created_by || '') + ' ' + fmtTs(p.created_at))}"><b data-del="${i}" title="删掉这张（要密码）">×</b></div>`).join('') : '<div class="muted" style="padding:18px 4px">还没有照片。点右下「＋ 加照片」：Ctrl+V 粘贴、选文件（可多选）、手机连拍。</div>';
    $('#hpN', ov).textContent = list.length ? '共 ' + list.length + ' 张 · 点照片看大图（← → 翻页）' : '';
  };
  $('#hpG', ov).onclick = async e => {
    const t = e.target;
    if (t.dataset.i !== undefined) bigImg('/photos/' + list[+t.dataset.i].path, list.map(p => '/photos/' + p.path));
    if (t.dataset.del !== undefined) {
      const p = list[+t.dataset.del]; if (!await confirmBox('删掉这张手工单照片？（回收站可恢复）', '删除')) return;
      try { await save('/api/photo/delete', { id: p.id }, '删除照片'); toast('已删除'); await load(); } catch (er) { fail(er); }
    }
  };
  await load();
}
/** 汇总核对专用表头：钢瓶出入回收 + 更换/新送/手工单（对照财务表手工单相关列）；不含实际配送/其他产品/备注 */
function verifyHeadHtml(first) {
  return `<thead><tr><th rowspan="2">${first}</th><th colspan="2">出库</th><th colspan="4">入库</th><th colspan="2">回收</th><th colspan="2">更换</th><th colspan="2">新送</th><th colspan="2">手工单更换</th><th colspan="2">手工单新送</th></tr>
    <tr>${['40L', '10L', '40L空', '40L满', '10L空', '10L满', '40L', '10L', '40L', '10L', '40L', '10L', '40L', '10L', '40L', '10L'].map(x => `<th>${x}</th>`).join('')}</tr></thead>`;
}
/** 汇总行双击：该配送员当天（或几天合计）登记行明细；列精简为钢瓶+手工单相关，方便对照纸表。
 * 格子可直接改：交接表来源走 /api/paper/save（改 cells，留 edits + 操作记录）；导入/旧录入走 /api/daily/save。
 * 已有数的格子不会被空写掉（可改成 0）；更换/新送为灰列自动算，不可手改。 */
async function courierSumDetail(m, data, page) {
  const other = S.boot.daily_cols.other, cid = m.courier_id, name = m.label || m.name;
  const EDIT_KS = ['o40', 'o10', 'e40', 'f40', 'e10', 'f10', 'r40', 'r10', 'hc40', 'hc10', 'hn40', 'hn10'];
  const z = x => (x === 0 || x === '' || x === undefined || x === null) ? '' : fmtN(x);
  const n0 = x => +x || 0;
  const paperByDate = {};
  const loadPaper = async date => {
    if (date === D.date && D.pd) return D.pd;
    if (!paperByDate[date]) paperByDate[date] = await api('/api/paper?date=' + date);
    return paperByDate[date];
  };
  const parseLeg = leg => {
    const mm = /^paper:(\d+):([^:]+)(:L[s]?)?$/.exec(leg || '');
    return mm ? { sid: +mm[1], rid: mm[2], left: !!mm[3] } : null;
  };
  // 几天合计：把期间每天的登记行都拉来（今天已在 data.entries 里）
  let ents = (data.entries || []).filter(e => e.courier_id === cid).map(e => Object.assign({}, e, { vals: Object.assign({}, e.vals || {}) }));
  const periodNote = [];
  if (m.period && m.period[0] < D.date) {
    let d0 = m.period[0];
    while (d0 < D.date) {
      try {
        const r = await api('/api/daily?date=' + d0);
        ents = ents.concat((r.entries || []).filter(e => e.courier_id === cid).map(e => Object.assign({}, e, { vals: Object.assign({}, e.vals || {}) })));
      } catch (er) { periodNote.push(d0 + ' 加载失败'); }
      d0 = addDays(d0, 1);
    }
    ents.sort((a, b) => (a.book_date || '').localeCompare(b.book_date || '') || a.id - b.id);
    periodNote.push(`${md(m.period[0])}–${md(m.period[1])} 合计（几天登记行都列出）`);
  }
  // 预加载涉及的交接表日期（含次日早上），方便对车牌 / 改 cells
  const needDates = new Set([D.date]);
  ents.forEach(e => {
    const leg = parseLeg(e.legacy);
    if (!leg) return;
    if (leg.left) needDates.add(addDays(e.out_date, 1));
    else { needDates.add(e.out_date); if (e.book_date) needDates.add(e.book_date); }
  });
  await Promise.all([...needDates].map(d => loadPaper(d).catch(() => null)));
  const findSheet = (sid) => {
    for (const d of needDates) {
      const pd = (d === D.date && D.pd) ? D.pd : paperByDate[d];
      const sh = pd && (pd.sheets || []).find(s => s.id === sid);
      if (sh) return { sh, date: d, pd };
    }
    return null;
  };
  const plateOf = e => {
    const leg = parseLeg(e.legacy); if (!leg) return '';
    const hit = findSheet(leg.sid); if (!hit) return '';
    const row = (hit.sh.rows || []).find(r => String(r.rid) === leg.rid); return row ? (row.plate || '') : '';
  };
  const metaOf = e => {
    const leg = parseLeg(e.legacy);
    if (leg && leg.left) return { kind: 'next', next: addDays(e.out_date, 1), label: '次日早上·左边（' + md(addDays(e.out_date, 1)) + '）', leg };
    if (!leg) return { kind: 'other', cn: { import: '导入', book: '旧录入', phone: '手机' }[e.source] || e.source || '登记', editable: true };
    const hit = findSheet(leg.sid);
    if (!hit) return { kind: 'other', cn: '交接表', leg };
    return { kind: 'paper', s: hit.sh, ses: hit.sh.session, formCn: hit.sh.form === 'cyl' ? '钢瓶' : '产品', leg, hit };
  };
  /** 固定列 key → 交接表 cell 键（只认 layout 里有的固定列）；leftOnly 只改左边 */
  const cellKey = (lay, vk, leftOnly) => {
    const prefer = (vk === 'o40' || vk === 'o10') ? 'R' : 'L';
    if (leftOnly && prefer === 'R') return null;
    const sides = leftOnly ? ['L'] : [prefer, prefer === 'L' ? 'R' : 'L'];
    for (const sd of sides) {
      if ((lay[sd] || []).some(c => c.t === 'f' && c.k === vk)) return sd + '.' + vk;
    }
    return null;
  };
  const canEdit = (e, meta) => {
    if (meta.kind === 'other' && meta.editable) return true;
    if (meta.kind === 'paper' || meta.kind === 'next') {
      const hit = meta.hit || (meta.leg && findSheet(meta.leg.sid));
      return !!(hit && hit.sh.form === 'cyl');   // 钢瓶固定列；产品表无这些列
    }
    return false;
  };
  // 可编辑格：input；更换/新送灰列只读自动算
  const zd = x => (x === '' || x === undefined || x === null) ? '' : fmtN(x);   // 录入格：0 显示成 0（z 会把 0 藏成空，改数对不上）
  const cells = (e, vv, cc, meta, editable) => {
    const inp = k => {
      if (!editable) return `<td>${z(vv[k])}</td>`;
      // 次日左边行：出库列本来就没有，保持只读空
      if (meta.kind === 'next' && (k === 'o40' || k === 'o10')) return `<td>${z(vv[k])}</td>`;
      return `<td class="ve"><input data-eid="${e.id}" data-k="${k}" value="${esc(zd(vv[k]))}" inputmode="decimal" autocomplete="off"></td>`;
    };
    return `${['o40', 'o10', 'e40', 'f40', 'e10', 'f10', 'r40', 'r10'].map(inp).join('')}
      <td class="cf" data-cf="J40">${z(cc.J40)}</td><td class="cf" data-cf="J10">${z(cc.J10)}</td><td class="cf" data-cf="L40">${z(cc.L40)}</td><td class="cf" data-cf="L10">${z(cc.L10)}</td>
      ${['hc40', 'hc10', 'hn40', 'hn10'].map(inp).join('')}`;
  };
  const idCell = (e, pl, meta) => {
    const tags = [];
    if (e.book_date && e.out_date !== e.book_date) tags.push(`<span class="tag warn">${md(e.out_date)} 领</span>`);
    if (e.book_date && e.book_date !== D.date) tags.push(`<span class="tag">${md(e.book_date)}</span>`);
    let main;
    if (meta.kind === 'paper' && meta.s) {
      main = `<a data-go="${meta.s.form}|${esc(meta.s.session)}" title="打开对应交接表">${esc(meta.ses)}${pl ? ' · ' + esc(pl) : ''}</a> <span class="muted" style="font-size:12px">${esc(meta.formCn)}</span>`;
    } else if (meta.kind === 'next') {
      main = `<a data-nx="${meta.next}" title="切到次日（并记住今天，方便 ↔ 回来）">${esc(meta.label)}</a>${pl ? ' · ' + esc(pl) : ''}`;
    } else {
      main = `<span class="muted">${esc(meta.cn)}</span>${pl ? ' · ' + esc(pl) : ''}`;
    }
    const tip = (meta.kind === 'paper' && meta.s)
      ? (meta.ses + (pl ? ' · ' + pl : '') + ' · ' + meta.formCn)
      : (meta.kind === 'next' ? (meta.label + (pl ? ' · ' + pl : '')) : (meta.cn + (pl ? ' · ' + pl : '')));
    return `<td class="nm" title="${esc(tip)}">${main}${tags.length ? ' ' + tags.join(' ') : ''}</td>`;
  };
  const v = m.vals || {}, cc = m.calc || dCalc(v);
  const mid = other.filter(o => n0(v['v0_' + o[0]]) || n0(v['v1_' + o[0]]) || n0(v['t_' + o[0]]) || n0(v['i_' + o[0]]) || n0(cc['net_' + o[0]])).map(o => {
    const a = n0(v['v0_' + o[0]]), b = n0(v['t_' + o[0]]), c = n0(v['i_' + o[0]]), d = n0(v['v1_' + o[0]]), net = n0(cc['net_' + o[0]]);
    return `<tr><td class="w">${esc(o[1])}</td><td class="w">${z(a)}</td><td class="w">${z(b)}</td><td class="w">${z(c)}</td><td class="w">${z(d)}</td><td class="w${net < 0 ? ' neg' : ''}" style="${net < 0 ? 'color:#c62828;font-weight:600' : ''}">${z(net)}</td><td class="muted" style="font-size:12px;text-align:left">= 早上车上 ${a} + 领 ${b} − 退 ${c} − 次日车上 ${d}</td></tr>`;
  }).join('');
  const sumCyl = `<div class="hint" style="margin-top:0">财务汇总（本行）· 出库 ${z(v.o40)}/${z(v.o10)} · 入库空/满 40L ${z(v.e40)}/${z(v.f40)} · 10L ${z(v.e10)}/${z(v.f10)} · 回收 ${z(v.r40)}/${z(v.r10)} · 更换 ${z(cc.J40)}/${z(cc.J10)} · 新送 ${z(cc.L40)}/${z(cc.L10)} · 手工单更换 ${z(v.hc40)}/${z(v.hc10)} · 手工单新送 ${z(v.hn40)}/${z(v.hn10)}</div>`;
  const roCells = (vv, ccc) => `${['o40', 'o10', 'e40', 'f40', 'e10', 'f10', 'r40', 'r10'].map(k => `<td>${z(vv[k])}</td>`).join('')}
      <td class="cf">${z(ccc.J40)}</td><td class="cf">${z(ccc.J10)}</td><td class="cf">${z(ccc.L40)}</td><td class="cf">${z(ccc.L10)}</td>
      ${['hc40', 'hc10', 'hn40', 'hn10'].map(k => `<td>${z(vv[k])}</td>`).join('')}`;
  const entRows = ents.map(e => {
    const vv = e.vals || {}, ecc = dCalc(vv), pl = plateOf(e), meta = metaOf(e);
    return `<tr data-row="${e.id}">${idCell(e, pl, meta)}${cells(e, vv, ecc, meta, canEdit(e, meta))}</tr>`;
  }).join('');
  const body = `${periodNote.length ? `<div class="banner">${esc(periodNote.join(' · '))}</div>` : ''}
    ${m.pending ? `<div class="banner">待次日清点：等 ${md(m.next)} 早上录入后才算定</div>` : ''}
    ${m.merged_into ? `<div class="banner">这天并入 ${md(m.merged_into)} 合计，数在那天</div>` : ''}
    ${sumCyl}
    ${m.note ? `<div class="hint">备注：${esc(m.note)}</div>` : ''}
    ${mid ? `<div class="sec-h" style="margin-top:10px"><h2>其他产品用量拆解</h2><small class="muted">（主表已不列其他产品，有用量时单独拆解）</small></div>
      <div class="tw"><table class="t"><thead><tr><th>产品</th><th>早上车上剩余</th><th>当天领</th><th>当天退</th><th>次日车上剩余</th><th>当天总出库</th><th>算式</th></tr></thead><tbody>${mid}</tbody></table></div>` : ''}
    <div class="sec-h" style="margin-top:12px"><h2>登记行 <small class="muted">${ents.length} 条 · 可直接改数 · 更换/新送自动算</small></h2></div>
    ${ents.length ? `<div class="tw" style="max-height:55vh"><table class="dt" id="vkT">${verifyHeadHtml('场次 · 车牌')}<tbody>
      ${entRows}
      <tr class="tot" style="font-weight:600;background:#fafbfc">${'<td class="nm">本行汇总</td>' + roCells(v, cc)}</tr>
    </tbody></table></div>` : '<div class="muted">没有登记行（可能待清点，或数来自次日清点中间量）</div>'}
    <div class="hint" style="margin-top:10px">格子里直接改数后点「保存」（要密码，进操作记录）；已有数的格子不能改成空（可改成 0）。也可点「场次 · 车牌」去交接表改。灰列更换/新送自动算，不能手改。</div>`;
  let dirty = false;
  const markDirty = () => {
    dirty = true;
    const b = ov && ov.querySelector('[data-vk-save]');
    if (b) { b.disabled = false; b.textContent = '保存'; }
  };
  const ov = dialog('汇总核对 · ' + name + ' · ' + md(D.date), body, [
    { t: '关闭' },
    { t: '保存', cls: 'pri', fn: async () => {
      const btn = ov.querySelector('[data-vk-save]');
      try {
        const r = await vkSave();
        if (r === false) return false;
        toast(r || '已保存，汇总已重算');
        ov.remove(); await loadBoot(); Pages.daily(page);
      } catch (er) { fail(er); return false; }
    } }
  ], { wide: true, nofocus: true });
  // 给保存按钮打标，便于 dirty 时启用
  const saveBtn = [...ov.querySelectorAll('.dlg-f .btn')].find(b => b.textContent === '保存');
  if (saveBtn) { saveBtn.dataset.vkSave = '1'; saveBtn.disabled = true; saveBtn.textContent = '已保存'; }

  const readRowVals = (eid) => {
    const out = {};
    $$('#vkT input[data-eid="' + eid + '"]', ov).forEach(inp => {
      const raw = String(inp.value || '').trim();
      out[inp.dataset.k] = raw === '' ? '' : raw;
    });
    return out;
  };
  const refreshCf = (tr, vals) => {
    const c = dCalc(vals);
    [['J40', c.J40], ['J10', c.J10], ['L40', c.L40], ['L10', c.L10]].forEach(([k, x]) => {
      const td = tr.querySelector('[data-cf="' + k + '"]'); if (td) td.textContent = z(x);
    });
  };
  ov.addEventListener('input', ev => {
    const inp = ev.target.closest('input[data-eid]'); if (!inp) return;
    markDirty();
    const tr = inp.closest('tr'); const eid = +inp.dataset.eid;
    const e = ents.find(x => x.id === eid); if (!e) return;
    const edited = readRowVals(eid);
    const merged = Object.assign({}, e.vals || {});
    EDIT_KS.forEach(k => {
      if (!(k in edited)) return;
      const raw = edited[k];
      if (raw === '') { /* 显示空，保存时会保住原值 */ delete merged[k]; }
      else { const p = ppParse(raw); merged[k] = p.ok && p.v != null ? p.v : n0(raw); }
    });
    refreshCf(tr, merged);
  });

  /** 已有数不空写：新值为空且旧有值 → 保留旧；返回 {vals, kept} */
  const mergeNoBlank = (oldVals, edited) => {
    const out = Object.assign({}, oldVals || {}); let kept = 0;
    EDIT_KS.forEach(k => {
      if (!(k in edited)) return;
      const raw = String(edited[k] == null ? '' : edited[k]).trim();
      const old = oldVals && oldVals[k];
      const had = old !== undefined && old !== null && old !== '' && n0(old) !== 0 || (old === 0); // 0 also "filled" as intentional?
      // 「已有数」：旧 vals 里该 key 存在且非空字符串意义；0 算有数（用户写过 0）
      const filled = old !== undefined && old !== null && String(old).trim() !== '';
      if (raw === '') {
        if (filled) { kept++; /* keep out[k] */ }
        else delete out[k];
        return;
      }
      const p = ppParse(raw);
      if (!p.ok) throw new Error('格子「' + k + '」看不懂：' + raw);
      out[k] = p.v;
    });
    return { vals: out, kept };
  };

  async function vkSave() {
    if (!dirty) { toast('没有改动'); return false; }
    // 按行收集；按交接表 sheet 合并一次保存
    const sheetPatch = {}; // sid -> { hit, rowsMap changes rid -> {ck: txt} }
    const dailyPatch = [];
    let keptTotal = 0;
    for (const e of ents) {
      const meta = metaOf(e);
      if (!canEdit(e, meta)) continue;
      const edited = readRowVals(e.id);
      // 有没有相对原 vals 的变化（空对空不算；空对有数 = 想清空，保存时保住）
      let changed = false;
      EDIT_KS.forEach(k => {
        if (!(k in edited)) return;
        const raw = String(edited[k]).trim();
        const ov = e.vals && e.vals[k];
        const oz = (ov === '' || ov === undefined || ov === null) ? '' : String(fmtN(ov));
        if (raw !== oz) changed = true;
      });
      if (!changed) continue;
      if (meta.kind === 'other') {
        const { vals, kept } = mergeNoBlank(e.vals, edited);
        keptTotal += kept;
        dailyPatch.push({ e, vals });
        continue;
      }
      const leg = meta.leg || parseLeg(e.legacy);
      const hit = meta.hit || findSheet(leg.sid);
      if (!hit) throw new Error('找不到交接表，无法保存这一行');
      const lay = hit.sh.layout || {};
      const row = (hit.sh.rows || []).find(r => String(r.rid) === leg.rid);
      if (!row) throw new Error('交接表里找不到这一行（车牌可能已改）');
      const patch = sheetPatch[leg.sid] || (sheetPatch[leg.sid] = { hit, cells: {} });
      const rc = patch.cells[leg.rid] || (patch.cells[leg.rid] = {});
      EDIT_KS.forEach(k => {
        if (!(k in edited)) return;
        if (meta.kind === 'next' && (k === 'o40' || k === 'o10')) return;
        const ck = cellKey(lay, k, meta.kind === 'next' || leg.left);
        if (!ck) return;
        const raw = String(edited[k]).trim();
        const cur = String((row.cells || {})[ck] || '').trim();
        const ov0 = e.vals && e.vals[k];
        const oz = (ov0 === '' || ov0 === undefined || ov0 === null) ? '' : String(fmtN(ov0));
        if (raw === oz) return; // 这一格用户没改（相对汇总显示值）
        if (raw === '' && (cur || oz)) { keptTotal++; return; } // 不空写已有数
        if (raw === '') return;
        const p = ppParse(raw); if (!p.ok) throw new Error((row.plate || '') + '「' + k + '」看不懂：' + raw);
        // 写回纸上：用户输入的数字原文（0 也写）；与 cells 原样相同则跳过
        const store = p.txt || String(raw);
        if (store === cur) return;
        rc[ck] = store;
      });
    }
    // 保存各张交接表
    for (const sid of Object.keys(sheetPatch)) {
      const { hit, cells } = sheetPatch[sid];
      if (!Object.keys(cells).length) continue;
      const sh = hit.sh;
      const rows = JSON.parse(JSON.stringify(sh.rows || []));
      let nCh = 0;
      Object.entries(cells).forEach(([rid, cmap]) => {
        const row = rows.find(r => String(r.rid) === String(rid)); if (!row) return;
        row.cells = row.cells || {};
        Object.entries(cmap).forEach(([ck, txt]) => {
          if (String(row.cells[ck] || '') === String(txt)) return;
          if (txt) row.cells[ck] = txt; else delete row.cells[ck];
          nCh++;
        });
      });
      if (!nCh) continue;
      await save('/api/paper/save', {
        data: { id: sh.id, date: sh.date || hit.date, session: sh.session, form: sh.form, rows, batches: sh.batches || {} },
        base_ts: sh.updated_at || sh.created_at
      }, '汇总核对改交接表');
    }
    for (const { e, vals } of dailyPatch) {
      await save('/api/daily/save', {
        data: { id: e.id, courier_id: e.courier_id, out_date: e.out_date, book_date: e.book_date, vals, hand: e.hand || [], note: e.note || '' }
      }, '汇总核对改登记');
    }
    dirty = false;
    return keptTotal ? ('已保存（' + keptTotal + ' 个已有数的空格已保住未空写）') : '已保存，汇总已重算';
  }

  ov.onclick = async ev => {
    const t = ev.target.closest('a'); if (!t) return;
    if (dirty && (t.dataset.go || t.dataset.nx) && !await confirmDirty('核对里还有改动没保存，离开前要先处理。', vkSave, { saveText: '保存' })) return;
    if (t.dataset.go) { const [f, s] = t.dataset.go.split('|'); ov.remove(); D.tab = f; D.ses = s; Pages.daily(page); }
    if (t.dataset.nx) {
      ov.remove();
      D.peer = D.date;   // 记住今天，页头 ↔ 可一键回来
      D.date = t.dataset.nx; D.tab = 'cyl'; D.ses = (D.pd && D.pd.sessions[0]) || '早上';
      dPersist(); Pages.daily(page);
    }
  };
}


function dailyTable(data, forPrint) {
  const other = S.boot.daily_cols.other;
  const z = x => (x === 0 || x === '' || x === undefined || x === null) ? '' : fmtN(x);
  const hd = dailyHeadHtml('领取人信息');
  // 负数：多半是录错了（比如次日早上车上剩余比当天领的还多）。照样显示，屏幕上标红、鼠标放上去写明是哪几个数算出来的（打印 / Excel 不标）
  const n0 = x => +x || 0;
  const cf = (x, tip) => (!forPrint && n0(x) < 0) ? `<td class="cf neg" title="${esc(tip || '负数：请核对录入')}">${z(x)}</td>` : `<td class="cf">${z(x)}</td>`;
  const negTip = (o, v, net) => n0(net) < 0 ? `${o[1]} = 早上车上剩余（当天早上产品表左边没写退的）${n0(v['v0_' + o[0]])} + 当天领（右边）${n0(v['t_' + o[0]])} − 当天后几场写退的 ${n0(v['i_' + o[0]])} − 次日早上车上剩余（次日早上产品表左边，写没写退都算）${n0(v['v1_' + o[0]])} = ${n0(net)}\n负数：次日早上车上的比当天能用的还多，请核对两天早上的产品表（车牌 / 配送员 / 数量）` : '';
  const cylTip = (v, k, sz) => `负数：请核对钢瓶表 —— 出库${sz}L ${n0(v['o' + sz])}、入库${sz}L空 ${n0(v['e' + sz])}、满 ${n0(v['f' + sz])}、回收 ${n0(v['r' + sz])}、手工单更换 ${n0(v['hc' + sz])}、新送 ${n0(v['hn' + sz])}`;
  const rowAttr = (cls, cid) => { const c = [cls, (!forPrint && cid) ? 'clk' : ''].filter(Boolean).join(' '); return `class="${c}"` + ((!forPrint && cid) ? ` data-cid="${cid}" title="双击查看该配送员登记明细（核对用）"` : ''); };
  const row = (name, v, cc, note, cls, cid) => `<tr ${rowAttr(cls, cid)}><td class="nm" title="${esc(name)}">${esc(name)}</td>${['o40', 'o10', 'e40', 'f40', 'e10', 'f10', 'r40', 'r10'].map(k => `<td>${z(v[k])}</td>`).join('')}
    ${cf(cc.J40, cylTip(v, 'J', '40'))}${cf(cc.J10, cylTip(v, 'J', '10'))}${cf(cc.L40, cylTip(v, 'L', '40'))}${cf(cc.L10, cylTip(v, 'L', '10'))}${['hc40', 'hc10', 'hn40', 'hn10'].map(k => `<td>${z(v[k])}</td>`).join('')}
    ${cf(cc.R40, cylTip(v, 'R', '40'))}${cf(cc.R10, cylTip(v, 'R', '10'))}${other.map(o => cf(dnum(cc['net_' + o[0]]), forPrint ? '' : negTip(o, v, cc['net_' + o[0]]))).join('')}<td class="nt">${esc(note || '')}</td></tr>`;
  // 待次日清点：次日早上交接表还没录，当天的数还没算定 → 不显示数，整行写「待次日清点」
  const pend = m => `<tr ${rowAttr('pend', m.courier_id)}><td class="nm" title="${esc(m.name)}">${esc(m.label || m.name)}</td><td colspan="${18 + other.length}" class="pendc">待次日清点 · 等 ${md(m.next)} 早上${esc(m.pending.join('、'))}交接表录入后算出当天数</td><td class="nt">${esc(m.note || '')}</td></tr>`;
  const pmsg = (m, t) => `<tr ${rowAttr('pend', m.courier_id)}><td class="nm" title="${esc(m.name)}">${esc(m.label || m.name)}</td><td colspan="${18 + other.length}" class="pendc">${t}</td><td class="nt">${esc(m.note || '')}</td></tr>`;
  const one = m => m.merged_into ? pmsg(m, `并入 ${+m.merged_into.slice(8)}号合计 · 这天以后的早上没清点到这个人的车，几天合起来算，数在 ${md(m.merged_into)} 那天`)
    : m.pending && m.gap ? pmsg(m, `待清点 · ${md(m.next)} 早上没清点到这个人 · 不要手改格子；下次早上清到后自动几天合计写入汇总`)
    : m.pending ? pend(m) : row(m.label || m.name, m.vals, m.calc, m.note, '', m.courier_id);   // 领取人信息只写配送员（不写车牌）；双击行看登记明细
  const hp = data.hand_photos || {};   // 手工单照片（屏幕上才有，不打印）
  const badge = m => { const n = hp[m.courier_id] || 0; return n ? `<a class="hp on" data-hp="${m.courier_id}" title="手工单照片 ${n} 张（点开看 / 加）">📎${n}</a>` : `<a class="hp" data-hp="${m.courier_id}" title="加手工单照片（可选，对账备用；可多张）">＋</a>`; };
  const rows = data.merged.map(m => one(m).replace('</td>', badge(m) + '</td>')).join('');
  const t = data.total; const tc = t;
  const tot = data.merged.length ? row('合计', t, tc, '', 'tot') : '';
  if (forPrint) {   // 打印：没有数的配送员不打；每个配送员下面空一行（财务核对写字用），不多留空行
    const ncol = 1 + 18 + other.length + 1, blank = `<tr class="bl">${'<td>&nbsp;</td>'.repeat(ncol)}</tr>`;
    return `<table class="dprint">${hd.replace(/class="[^"]*"/g, '')}<tbody>${data.merged.filter(dHasData).map(m => noteLong(m.note) ? one(Object.assign({}, m, { note: '见下行' })) + `<tr class="bl nl"><td colspan="${ncol}" class="l">${esc(m.note)}</td></tr>` : one(m) + blank).join('').replace(/class="nm"|class="nt"/g, 'class="l"').replace(/ class="cf"/g, '')}</tbody></table>`;
  }
  return data.merged.length ? `<table class="dt">${hd}<tbody>${rows}${tot.replace(/<td/g, '<td style="font-weight:600;background:#fafbfc"')}</tbody></table>` : '<div class="muted" style="padding:6px 0">当天还没有记录</div>';
}

/* ---------- 表格设置：两张纸的列、车牌行、场次（只影响以后新建的表） ---------- */
const PLY = { f: 'cyl', d: null };
async function drawLayout(el) {
  el.classList.add('wide');
  if (!PLY.d) { PLY.d = await api('/api/paper/layout'); PLY.d.layout = JSON.parse(JSON.stringify(PLY.d.layout)); }
  const d = PLY.d, L = d.layout[PLY.f];
  const prods = S.boot.products.slice().sort((a, b) => (a.name || '').localeCompare(b.name || '', 'zh'));
  const colTbl = side => `<table class="t ly-t"><thead><tr><th style="width:56px">顺序</th><th>表头名称</th><th>分组 <small class="muted">（相邻同名合并，如「回收」）</small></th><th>对应</th><th></th></tr></thead><tbody>
    ${L[side].map((c, i) => `<tr><td class="w"><a data-mv="${side}|${i}|-1" title="上移">↑</a> <a data-mv="${side}|${i}|1" title="下移">↓</a></td>
      <td><input class="inp sm" data-e="${side}|${i}|n" value="${esc(c.n)}"></td><td><input class="inp sm" data-e="${side}|${i}|g" value="${esc(c.g || '')}" style="width:110px"></td>
      <td>${c.t === 'f' ? `<span class="muted">固定：${esc(d.fixed[c.k] || c.k)}</span>` : `<select class="inp sm" data-e="${side}|${i}|pid"><option value="">（选库存产品）</option>${prods.map(p => `<option value="${p.id}" ${c.pid === p.id ? 'selected' : ''}>${esc(p.name)}${p.spec ? ' ' + esc(p.spec) : ''}</option>`).join('')}</select>`}</td>
      <td class="w"><a class="link d" data-rm="${side}|${i}">删除</a></td></tr>`).join('')}</tbody></table>
    <div class="split" style="margin-top:8px"><button class="btn sm" data-addp="${side}">＋ 产品列</button>${PLY.f === 'cyl' ? `<select class="inp sm" data-addf="${side}" style="width:auto"><option value="">＋ 固定列…</option>${Object.entries(d.fixed).map(([k, n]) => `<option value="${k}">${esc(n)}</option>`).join('')}</select>` : ''}</div>`;
  el.innerHTML = UI.ph('表格设置', '设置交接表列 / 车牌 / 场次 / 次日清点 · 列与车牌只影响以后新建的表', '照纸上的样子设两张表：列对应库存产品、车牌行、场次。跨日清点规则（开始日）也在这里改，不要在行里手改记账日。已录的表列保持原样。',
    `<div class="seg" id="lyF"><button data-f="cyl" class="${PLY.f === 'cyl' ? 'on' : ''}">钢瓶交接表</button><button data-f="prod" class="${PLY.f === 'prod' ? 'on' : ''}">产品交接表</button></div>
     <a class="btn sm" href="#daily">‹ 返回交接表</a><a class="link" id="lyReset" style="font-size:13px">恢复默认</a><button class="btn pri sm" id="lySave">保存设置</button>`)
    + `
    <div class="card"><div class="card-h"><h2>次日清点</h2><small class="muted">跨日自动：待清点 → 下次早上清到后几天合计；不要在行三点菜单里改记账日</small></div>
      <div class="row" style="align-items:end;gap:12px;flex-wrap:wrap"><label><span class="lab">规则开始日</span><input class="inp" type="date" id="lyNd" value="${esc(d.nextday_from || d.nextday_from_default || '')}" style="width:160px"></label>
        <span class="muted" style="font-size:12.5px">这天起走次日清点；之前的日期左右都记在表的当天。默认 ${esc(d.nextday_from_default || '2026-10-19')}</span></div></div>
    <div class="card"><div class="row r3">
      <div><span class="lab">左边标题</span><input class="inp" data-h="lt" value="${esc(L.lt)}"></div><div><span class="lab">右边标题</span><input class="inp" data-h="rt" value="${esc(L.rt)}"></div>
      <div><span class="lab">左边的数</span><div class="seg" id="lyM"><button data-m="all" class="${L.lmode === 'all' ? 'on' : ''}">全部算退回库房</button><button data-m="mark" class="${L.lmode !== 'all' ? 'on' : ''}">写了「退」才算退回</button></div></div></div>
      <div class="grid2" style="grid-template-columns:1fr 1fr;margin-top:14px"><div><div class="sec-h"><h2>左边：${esc(L.lt)}</h2></div>${colTbl('L')}</div><div><div class="sec-h"><h2>右边：${esc(L.rt)}</h2><small>新装 = 领取 / 出库</small></div>${colTbl('R')}</div></div></div>
    <div class="grid2" style="grid-template-columns:1fr 1fr">
      <div class="card"><div class="card-h"><h2>车牌行</h2><small class="muted">顺序同纸；两张表共用。配送员不在这里定，每张表每行自己填</small></div>
        <div class="ly-pl">${d.plates.map((p, i) => `<span class="chip has">${esc(p)} <a data-pmv="${i}|-1">←</a><a data-pmv="${i}|1">→</a><a class="link d" data-prm="${i}">✕</a></span>`).join('')}</div>
        <div class="split" style="margin-top:10px"><input class="inp sm" id="lyPn" placeholder="车牌" style="width:140px"><button class="btn sm" id="lyPa">加车牌</button></div></div>
      <div class="card"><div class="card-h"><h2>场次</h2><small class="muted">关掉的不在场次里显示（已有的表照常显示）</small></div>
        <div class="lst" style="display:grid;gap:8px">${d.sessions.map((x, i) => `<label class="split"><input type="checkbox" data-son="${i}" ${x.on ? 'checked' : ''}> <span style="min-width:60px">${esc(x.n)}</span><a data-smv="${i}|-1">↑</a><a data-smv="${i}|1">↓</a><a class="link d" data-srm="${i}">删除</a></label>`).join('')}</div>
        <div class="split" style="margin-top:10px"><input class="inp sm" id="lySn" placeholder="如 下午" style="width:140px"><button class="btn sm" id="lySa">加场次</button></div></div></div>`;
  const re = () => drawLayout(el);
  const mv = (arr, i, dlt) => { const j = i + dlt; if (j < 0 || j >= arr.length) return; [arr[i], arr[j]] = [arr[j], arr[i]]; };
  $('#lyF', el).onclick = e => { const b = e.target.closest('button'); if (b) { PLY.f = b.dataset.f; re(); } };
  $('#lyM', el).onclick = e => { const b = e.target.closest('button'); if (b) { L.lmode = b.dataset.m; re(); } };
  el.oninput = e => { const t = e.target;
    if (t.dataset.h) L[t.dataset.h] = t.value;
    if (t.dataset.e) { const [sd, i, f] = t.dataset.e.split('|'); L[sd][+i][f] = f === 'pid' ? (+t.value || null) : t.value; if (f === 'pid') delete L[sd][+i].fk; } };
  el.onchange = e => { const t = e.target;
    if (t.dataset.e && t.dataset.e.endsWith('|pid')) { const [sd, i] = t.dataset.e.split('|'); const c = L[sd][+i]; const p = S.boot.products.find(x => x.id === +t.value); if (p && (!c.n || c._auto)) { c.n = p.name; c._auto = 1; re(); } }
    if (t.dataset.addf && t.value) { L[t.dataset.addf].push({ k: t.value, n: d.fixed[t.value].replace(/^\S+\s/, ''), g: '', t: 'f' }); re(); }
    if (t.dataset.son !== undefined) d.sessions[+t.dataset.son].on = t.checked; };
  el.onclick = async e => { const t = e.target.closest('a,button'); if (!t) return; const ds = t.dataset;
    if (ds.mv) { const [sd, i, dl] = ds.mv.split('|'); mv(L[sd], +i, +dl); re(); }
    if (ds.rm) { const [sd, i] = ds.rm.split('|'); L[sd].splice(+i, 1); re(); }
    if (ds.addp) { L[ds.addp].push({ k: '', n: '', g: '', t: 'p', pid: null, _auto: 1 }); re(); }
    if (ds.pmv) { const [i, dl] = ds.pmv.split('|'); mv(d.plates, +i, +dl); re(); }
    if (ds.prm !== undefined) { d.plates.splice(+ds.prm, 1); re(); }
    if (ds.smv) { const [i, dl] = ds.smv.split('|'); mv(d.sessions, +i, +dl); re(); }
    if (ds.srm !== undefined) { d.sessions.splice(+ds.srm, 1); re(); }
  };
  $('#lyPa', el).onclick = () => { const v = $('#lyPn', el).value.trim(); if (!v) return; if (d.plates.some(p => p.toLowerCase() === v.toLowerCase())) return toast('已经有这个车牌', true); d.plates.push(v); re(); };
  $('#lySa', el).onclick = () => { const v = $('#lySn', el).value.trim(); if (!v) return; if (d.sessions.some(x => x.n === v)) return toast('已经有这个场次', true); d.sessions.push({ n: v, on: true }); re(); };
  $('#lyReset', el).onclick = async () => { if (!await confirmBox('两张表的列恢复成原来纸上的样子？（车牌和场次不变；保存后才生效）', '恢复默认')) return; d.layout = JSON.parse(JSON.stringify(d.default)); re(); };
  $('#lySave', el).onclick = async () => {
    try {
      for (const f of ['cyl', 'prod']) for (const sd of ['L', 'R']) for (const c of d.layout[f][sd]) {
        if (!(c.n || '').trim()) { PLY.f = f; re(); return toast('有一列没写表头名称', true); }
        if (c.t === 'p' && !c.pid && !c.fk) { PLY.f = f; re(); return toast(`「${c.n}」没选对应的库存产品`, true); }
      }
      const nd = ($('#lyNd', el) && $('#lyNd', el).value) || '';
      await save('/api/paper/layout', { layout: d.layout, plates: d.plates, sessions: d.sessions, nextday_from: nd || null }, '保存表格设置');
      PLY.d = null; toast('已保存（新建表按新列；次日清点开始日已更新）'); re();
    } catch (er) { fail(er); }
  };
}


/* ---------- 数量统计（#daily/stats/日期）：三块表格（可对比对齐）；起止日期筛控件；②=汇总财务表 daily_rows+calc_row ---------- */
const DS = { from: '', to: '' };
async function drawDailyStats(box, page) {
  const dayCn = (+D.date.slice(8)) + '号';
  if (!DS.from || !DS.to) { DS.from = D.date; DS.to = D.date; }
  if (DS.from === DS.to && DS.from !== D.date && DS._lock !== D.date) { DS.from = D.date; DS.to = D.date; }
  DS._lock = D.date;
  const q = new URLSearchParams({ from: DS.from, to: DS.to });
  let r;
  try { r = await api('/api/daily/stats?' + q); } catch (e) { fail(e); box.innerHTML = '<div class="muted">加载失败</div>'; return; }
  DS.from = r.from; DS.to = r.to;
  const same = r.from === r.to;
  const rangeCn = same ? ((+r.from.slice(8)) + '号') : (md(r.from) + '–' + md(r.to));
  const wh = r.warehouse_out || [], del = r.delivery || [];
  const allOut = r.all_out || wh, allIn = r.all_in || [];
  const pend = (r.pending_days || []).length ? `<div class="banner ds-w">区间内有待清点日（配送量可能不全）：${r.pending_days.map(d => md(d.date) + ' ' + esc((d.names || []).join('、'))).join('；')}</div>` : '';
  const empty = t => `<tr><td colspan="8" class="muted ds-empty">${t}</td></tr>`;
  const byK = Object.fromEntries(del.map(x => [x.k, x]));
  const pair = (k40, k10) => [byK[k40], byK[k10]];
  const cellQ = x => x && x.q ? fmtN(x.q) : '—';
  const cylRows = [
    ['出库', 'o40', 'o10'],
    ['实际配送', 'R40', 'R10'],
    ['钢瓶总出库', 'T40', 'T10'],
  ].map(([lab, a, b]) => {
    const [x, y] = pair(a, b);
    return `<tr><td class="ds-lab">${lab}</td><td class="num">${cellQ(x)}</td><td class="num">${cellQ(y)}</td></tr>`;
  }).join('');
  const otherDel = del.filter(x => String(x.k || '').startsWith('net_') || String(x.k || '').startsWith('hand:'));
  const otherRows = otherDel.length
    ? otherDel.map(x => `<tr><td class="ds-lab">${esc(x.name || x.k)}</td><td class="num" colspan="2">${fmtN(x.q)}</td></tr>`).join('')
    : '';
  const hasDel = del.some(x => x && x.q);
  const delBody = hasDel
    ? (cylRows + (otherRows ? `<tr class="ds-sec"><td colspan="3">其他产品当天总出库（net = 早上剩余 + 领 − 退 − 次日早上剩余，同汇总表）</td></tr>` + otherRows : ''))
    : empty('这段时间没有配送量');
  const mapOut = Object.fromEntries(allOut.map(x => [x.id, x]));
  const mapIn = Object.fromEntries(allIn.map(x => [x.id, x]));
  const ids = [];
  const seen = new Set();
  [...allOut, ...allIn].forEach(x => { if (x.id && !seen.has(x.id)) { seen.add(x.id); ids.push(x.id); } });
  const ioRows = ids.length
    ? ids.map(id => {
        const o = mapOut[id] || {}, i = mapIn[id] || {};
        const name = o.name || i.name || '?', spec = o.spec || i.spec || '', unit = o.unit || i.unit || '';
        return `<tr data-pid="${id}" class="ds-row"><td class="ds-lab">${esc(name)}</td><td class="muted">${esc(spec)}</td><td class="muted">${esc(unit)}</td><td class="num">${o.q != null ? fmtN(o.q) : '—'}</td><td class="num">${i.q != null ? fmtN(i.q) : '—'}</td></tr>`;
      }).join('')
    : empty('没有出入库');
  const whRows = wh.length
    ? wh.map(x => `<tr data-pid="${x.id || ''}" class="ds-row"><td class="ds-lab">${esc(x.name || '')}</td><td class="muted">${esc(x.spec || '')}</td><td class="muted">${esc(x.unit || '')}</td><td class="num">${fmtN(x.q)}</td></tr>`).join('')
    : empty('这段时间没有库房出库');
  box.innerHTML = `<div class="ds-page">
    <div class="card ds-filter"><div class="tools" style="margin:0"><b>${esc(rangeCn)} 数量统计</b>
      <span class="muted" style="font-size:12.5px">筛 1～3 · 默认当天 · 表格对齐可对比</span>
      <span class="sp"></span>
      <label class="muted" style="font-size:12.5px">起</label><input class="inp" type="date" id="dsFrom" value="${esc(r.from)}" style="width:140px">
      <label class="muted" style="font-size:12.5px">止</label><input class="inp" type="date" id="dsTo" value="${esc(r.to)}" style="width:140px">
      <button class="btn sm" id="dsToday" title="回到日表选中日">当天（${dayCn}）</button>
    </div></div>
    <div class="card ds-mod" data-m="1"><div class="ds-h"><h3>1. 库房${same ? '' : '区间'}各产品出库</h3><small class="muted">同首页「今日出库」· moves 负向 · 点行看流水</small></div>
      <div class="tw ds-tw"><table class="dt ds-tbl"><thead><tr><th>产品</th><th>规格</th><th>单位</th><th>出库量</th></tr></thead><tbody>${whRows}</tbody></table></div></div>
    <div class="card ds-mod" data-m="2"><div class="ds-h"><h3>2. 配送员全部合计配送量</h3><small class="muted">口径 = 汇总财务表（daily_rows + calc_row：实际配送 / net）</small></div>
      <div class="tw ds-tw"><table class="dt ds-tbl ds-del"><thead><tr><th>项目</th><th>40L</th><th>10L</th></tr></thead><tbody>${delBody}</tbody></table></div>${pend}</div>
    <div class="card ds-mod" data-m="3"><div class="ds-h"><h3>3. 所有地方出入库合计</h3><small class="muted">出库单 · 日表 · 到货 · 借用/归还 · 换货 等按产品分栏对比 · 点行看流水</small></div>
      <div class="tw ds-tw"><table class="dt ds-tbl"><thead><tr><th>产品</th><th>规格</th><th>单位</th><th>出库合计</th><th>入库合计</th></tr></thead><tbody>${ioRows}</tbody></table></div></div>
  </div>`;
  const reload = () => drawDailyStats(box, page).catch(fail);
  $('#dsFrom', box).onchange = e => { DS.from = e.target.value || D.date; reload(); };
  $('#dsTo', box).onchange = e => { DS.to = e.target.value || D.date; reload(); };
  $('#dsToday', box).onclick = () => { DS.from = D.date; DS.to = D.date; reload(); };
  $$('tr.ds-row[data-pid]', box).forEach(el => {
    const id = +el.dataset.pid; if (!id) return;
    el.onclick = () => {
      const n = (el.querySelector('.ds-lab') || {}).textContent || '';
      if (typeof movesDlg === 'function') movesDlg({ id, label: n.trim() }).catch(fail);
    };
  });
}

/* ---------- 每日总出库量（看板）：所有配送员加起来；上面是选中那天的数字卡片（和前一天比），下面是这段时间每天的趋势（内嵌 SVG，不联网）。
   点趋势图里某一天 → 跳到那天的「汇总（财务表）」 ---------- */
const DP = { from: '', to: '', day: '', k: 'T40' };
async function drawDailyPanel(box, page) {
  if (!DP.from) { DP.from = today().slice(0, 8) + '01'; DP.to = today(); }
  const r = await api('/api/daily/panel?from=' + DP.from + '&to=' + DP.to);
  const days = r.days, has = days.filter(d => d.has), name = Object.fromEntries(r.cols.map(c => [c.k, c.name]));
  const settled = has.filter(d => Object.keys(d.v).length);   // 默认：最近一个有算定数的日子（有人待清点的标「不全」）
  if (!DP.day || !days.find(d => d.date === DP.day)) DP.day = (settled.length ? settled[settled.length - 1] : has.length ? has[has.length - 1] : days[days.length - 1] || {}).date || today();
  const cyl = ['T40', 'T10', 'o40', 'o10'];   // 钢瓶总出库（点开看 更换 / 新送 / 回收）、出库；实际配送在展开里、趋势图下拉里
  DP.open = DP.open || {};
  const draw = () => {
    const i = days.findIndex(d => d.date === DP.day), day = days[i] || { v: {}, pending: [], merged: 0 };
    const prev = days.slice(0, Math.max(i, 0)).reverse().find(d => d.has && Object.keys(d.v).length);
    const keys = cyl.concat(r.cols.map(c => c.k).filter(k => !cyl.includes(k) && k !== 'R40' && k !== 'R10' && (day.v[k] || (prev && prev.v[k]))));
    // 钢瓶总出库展开：更换（其中手工单）、新送（其中手工单；以后可再分 租用 / 购买 —— parts）、回收
    const bdHtml = z => { const b = (day.cyl || {})[z]; if (!b) return '';
      const ln = (t, o, tip) => `<div class="dp-l" title="${esc(tip || '')}"><span>${t}</span><b>${fmtN(o.v + (o.hand || 0))}</b></div>${o.hand ? `<div class="dp-l s"><span>其中手工单</span><span>${fmtN(o.hand)}</span></div>` : ''}${(o.parts || []).map(p => `<div class="dp-l s"><span>${esc(p.name)}</span><span>${fmtN(p.v)}</span></div>`).join('')}`;
      return `<div class="dp-bd">${ln('更换', b['更换'], '换回空瓶的（含手工单更换）')}${ln('新送', b['新送'], '新送出去的（含手工单新送）')}<div class="dp-l"><span>回收</span><b>${fmtN(b['回收'].v)}</b></div>
        <div class="dp-l s" title="财务表「实际配送」= 更换 + 新送（不含手工单）"><span>实际配送</span><span>${fmtN(day.v['R' + z] || 0)}</span></div></div>`; };
    const card = k => { const x = day.v[k] || 0, p = prev ? (prev.v[k] || 0) : null, dd = p === null ? null : Math.round((x - p) * 1000) / 1000;
      const T = k[0] === 'T', op = T && DP.open[k];
      return `<div class="dp-c${DP.k === k ? ' on' : ''}${T ? ' t' : ''}${op ? ' open' : ''}" data-k="${k}" title="${T ? '点一下：展开 更换 / 新送 / 回收，下面的趋势图看总出库' : `点一下：下面的趋势图看「${esc(name[k])}」`}"><div class="dp-n">${esc(name[k])}${T ? ` <span class="muted">${op ? '▴' : '▾'}</span>` : ''}</div><div class="dp-v">${fmtN(x)}</div>
        <div class="dp-d">${dd === null ? '<span class="muted">—</span>' : dd === 0 ? '<span class="muted">和前一天一样</span>' : `<span class="${dd > 0 ? 'up' : 'dn'}">${dd > 0 ? '▲' : '▼'} ${fmtN(Math.abs(dd))}</span> <span class="muted">比 ${md(prev.date)}</span>`}</div>${op ? bdHtml(k.slice(1)) : ''}</div>`; };
    const warn = day.pending.length ? `<div class="banner dp-w">这一天还有 ${day.pending.length} 人待清点（${esc(day.pending.join('、'))}），下面的数不全，清点后自动补上</div>` : '';
    const mg = day.merged ? `<div class="hint">另有 ${day.merged} 人这天并入后面几天合计</div>` : '';
    // 趋势图
    const W = 1000, H = 190, pl = 34, pb = 22, n = days.length || 1, bw = (W - pl - 6) / n;
    const vals = days.map(d => d.v[DP.k] || 0), mx = Math.max(1, ...vals), nice = (() => { const e = Math.pow(10, Math.floor(Math.log10(mx))); return Math.ceil(mx / e) * e; })();
    const y = v => H - pb - (H - pb - 8) * v / nice;
    const grid = [0, 0.5, 1].map(f => `<line x1="${pl}" x2="${W}" y1="${y(nice * f)}" y2="${y(nice * f)}" class="g"/><text x="${pl - 6}" y="${y(nice * f) + 4}" text-anchor="end">${fmtN(nice * f)}</text>`).join('');
    const bars = days.map((d, j) => { const v = d.v[DP.k] || 0, x = pl + j * bw, h = H - pb - y(v);
      return `<g class="b${d.date === DP.day ? ' on' : ''}${d.pending.length ? ' pd' : ''}" data-day="${d.date}"><title>${md(d.date)} ${esc(name[DP.k])} ${fmtN(v)}${d.pending.length ? '（有待清点，不全）' : ''} · 点开看这天汇总</title>
        <rect class="hit" x="${x}" y="0" width="${bw}" height="${H - pb}"/>${v ? `<rect x="${x + bw * 0.18}" y="${y(v)}" width="${bw * 0.64}" height="${Math.max(h, 1)}" rx="2"/>` : ''}
        ${v && bw > 22 ? `<text x="${x + bw / 2}" y="${y(v) - 4}" text-anchor="middle" class="v">${fmtN(v)}</text>` : ''}
        ${(n <= 16 || j % Math.ceil(n / 16) === 0 || d.date === DP.day) ? `<text x="${x + bw / 2}" y="${H - 6}" text-anchor="middle">${+d.date.slice(8)}</text>` : ''}</g>`; }).join('');
    const sum = vals.reduce((a, b) => a + b, 0);
    box.innerHTML = `<div class="card dp">
      <div class="tools"><a class="link" id="dpBack" style="margin-right:8px">‹ 汇总</a><button class="btn sm" id="dpPrev" ${i > 0 ? '' : 'disabled'}>‹</button><input class="inp" type="date" id="dpDay" value="${DP.day}" min="${r.from}" max="${r.to}" style="width:150px"><button class="btn sm" id="dpNext" ${i < days.length - 1 ? '' : 'disabled'}>›</button>
        <b style="margin-left:6px">${md(DP.day)} 所有配送员合计</b>${day.pending.length ? ' <span class="tag warn">有待清点 · 不全</span>' : ''}<span class="sp"></span><a class="link" id="dpGo">看这天汇总（财务表）↗</a></div>
      ${warn}<div class="dp-cs">${keys.map(card).join('')}</div>${mg}</div>
      <div class="card dp" style="margin-top:12px"><div class="tools"><b>每天趋势</b>
        <select class="inp" id="dpK">${r.cols.map(c => `<option value="${c.k}" ${c.k === DP.k ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}</select>
        <input class="inp" type="date" id="dpFrom" value="${r.from}" style="width:140px"><span class="muted">至</span><input class="inp" type="date" id="dpTo" value="${r.to}" style="width:140px">
        <span class="sp"></span><span class="muted">合计 ${fmtN(sum)} · 浅色 = 有待清点（不全） · 点某一天看那天汇总</span></div>
        <svg class="dp-ch" viewBox="0 0 ${W} ${H}" role="img" aria-label="每日趋势">${grid}${bars}</svg></div>`;
    const go = d => { D.date = d; D.tab = 'sum'; dPersist(); const inp = $('#dDate', page); if (inp) inp.style.visibility = ''; App.tab('daily/sum/' + D.date); };
    $('#dpBack', box).onclick = () => go(DP.day);
    $('#dpPrev', box).onclick = () => { DP.day = days[i - 1].date; draw(); };
    $('#dpNext', box).onclick = () => { DP.day = days[i + 1].date; draw(); };
    $('#dpDay', box).onchange = e => { if (days.find(d => d.date === e.target.value)) { DP.day = e.target.value; draw(); } else { DP.day = e.target.value; DP.from = e.target.value.slice(0, 8) + '01'; DP.to = e.target.value; drawDailyPanel(box, page).catch(fail); } };
    $('#dpGo', box).onclick = () => go(DP.day);
    $('#dpK', box).onchange = e => { DP.k = e.target.value; draw(); };
    $('#dpFrom', box).onchange = e => { DP.from = e.target.value; drawDailyPanel(box, page).catch(fail); };
    $('#dpTo', box).onchange = e => { DP.to = e.target.value; drawDailyPanel(box, page).catch(fail); };
    $$('.dp-c', box).forEach(c => { c.onclick = () => { const k = c.dataset.k; if (k[0] === 'T') DP.open[k] = !DP.open[k]; DP.k = k; draw(); }; });
    $$('.dp-ch g.b', box).forEach(g => { g.onclick = () => go(g.dataset.day); });
  };
  draw();
}
