/* 报表：照搬 v82 的 5 张表（换算表 / 入出库记录 / 到货总数 / 液氧表 / 4号院）
   双击或直接打字编辑，方向键/Enter/Tab 移动；改完点「保存」输密码；下载 = 原 Excel 格式（服务器生成） */
'use strict';
const RT = {
  conv:   { short: '换算表', title: '液态原料换算表', start: 4, head: 3, mode: 'date', sticky: 'A', computed: ['G', 'S', 'T', 'U', 'V'], hl: ['V'], hideCols: ['AC'], maxCol: 'AB', dec2: ['G', 'S', 'T', 'U', 'V'] },
  ledger: { short: '入出库记录', title: '液态氧原料入出库记录', start: 3, head: 2, mode: 'content', sticky: 'A', computed: [], hl: ['L'], maxCol: 'N', dec2: ['L'] },
  stock:  { short: '到货总数', title: '库存及到货总数', start: 3, head: 2, mode: 'all', sticky: 'A', computed: [], hl: [], ro: true },
  lox:    { short: '液氧表', title: '液氧表', start: 13, head: 12, early: [2, 11], mode: 'all', sticky: 'A', computed: [], hl: ['D'], att: true },
  yard4:  { short: '4号院', title: '4号院', start: 2, head: 1, mode: 'all', sticky: 'A', computed: [], hl: ['D'], att: true }
};
Object.values(RT).forEach(c => { c.short = c.title; });   // 每张报表只有一个名称（页签、标题、打印都用全称）
const RORDER0 = ['conv', 'ledger', 'stock', 'lox', 'yard4'];
/** 页签顺序：设置 → 报表 里可调；没列到的按默认顺序接在后面 */
function rOrder() { const o = ((S.boot && S.boot.settings.report_order) || []).filter(k => RORDER0.includes(k)); return [...new Set(o.concat(RORDER0))]; }
const R_PLACES = ['本库D', '本库C', '本库B', '本库', '示例机关', '示例电厂', '示例单位甲', '示例县', '示例部委', '四号库'];
const RP = { k: null, tabs: {}, dirty: {}, sel: null, showTail: {}, scrolled: {}, el: null, undo: [], redo: [] };
const rC = n => O2.numToCol(n), rN = c => O2.colToNum(c);
const rTab = k => RP.tabs[k || RP.k];

/* ---------- 数据 ---------- */
function rCell(tab, col, r) { const row = tab.rows[r - 1]; return row ? row.c[col] : null; }
function rRaw(tab, col, r) { const c = rCell(tab, col, r); return c ? (c.f != null && c.f !== '' ? '=' + c.f : (c.v == null ? '' : c.v)) : ''; }
function rRow(tab, r) { while (tab.rows.length < r) tab.rows.push(null); return tab.rows[r - 1] || (tab.rows[r - 1] = { c: {} }); }
function rSet(tab, col, r, raw) {
  const row = rRow(tab, r); const c = row.c[col] || (row.c[col] = {});
  delete c.f; delete c.v;
  if (raw === null || raw === undefined) return;
  if (typeof raw === 'number') { c.v = raw; return; }
  const s = String(raw); if (s.trim() === '') return;
  if (s[0] === '=' && s.length > 1) { c.f = s.slice(1).trim().replace(/[a-z]+(?=\d)/g, m => m.toUpperCase()); return; }
  if (/^-?\d+(\.\d+)?$/.test(s.trim()) && !/^-?0\d/.test(s.trim())) { c.v = parseFloat(s); return; }
  c.v = s;
}
function rHasVal(tab, r, cols) { const row = tab.rows[r - 1]; if (!row) return false; return Object.keys(row.c).some(k => (!cols || cols.includes(k)) && row.c[k] && ((row.c[k].v != null && String(row.c[k].v).trim() !== '') || row.c[k].f)); }
const R_DATE = /^\s*(20\d\d)[.\-\/年](\d{1,2})[.\-\/月](\d{1,2})日?\s*$/;
const rParseDate = s => { const m = R_DATE.exec(String(s == null ? '' : s)); return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null; };
const rFmtDate = d => d.getFullYear() + '.' + (d.getMonth() + 1) + '.' + d.getDate();
const rToday = () => rFmtDate(new Date());
const rIso = s => { const d = rParseDate(s); return d ? d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0') : ''; };
const rFromIso = iso => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || ''); return m ? (+m[1]) + '.' + (+m[2]) + '.' + (+m[3]) : ''; };
const rNextDate = s => { const d = rParseDate(s); if (!d) return rToday(); d.setDate(d.getDate() + 1); return rFmtDate(d); };
function rFmt(v, dec2) {
  if (v == null || v === '') return '';
  if (typeof v === 'boolean') return v ? 'TRUE' : 'FALSE';
  if (typeof v === 'number') { if (!isFinite(v)) return '#NUM!'; return dec2 ? v.toFixed(2) : String(+v.toFixed(6)); }
  return String(v);
}
function rContent(k, tab, r) {
  if (k === 'conv') return rHasVal(tab, r, null) && !!(rParseDate(rRaw(tab, 'A', r)) || rHasVal(tab, r, ['B', 'D', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R']));
  if (k === 'ledger') return rHasVal(tab, r, ['B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N']);
  return rHasVal(tab, r, null);
}
function rRanges(k) {
  const cfg = RT[k], tab = rTab(k), n = tab.rows.length; let last = cfg.start - 1;
  for (let r = n; r >= 1; r--) if (rHasVal(tab, r, null)) { last = r; break; }
  if (RP.keepTo && RP.keepTo[k] && RP.keepTo[k] <= n) last = Math.max(last, RP.keepTo[k]);   // 刚插入的空行也要显示出来
  if (cfg.mode === 'all') return { start: cfg.start, mainEnd: Math.max(last, cfg.start - 1), tailStart: null, last };
  let mainEnd = cfg.start - 1, gap = 0;
  for (let r = cfg.start; r <= n; r++) { if (rContent(k, tab, r)) { mainEnd = r; gap = 0; } else if (++gap >= 3 && mainEnd >= cfg.start) break; }
  let tailStart = null;
  for (let r = mainEnd + 1; r <= n; r++) if (rHasVal(tab, r, null) && (rContent(k, tab, r) || r > mainEnd + 2)) { tailStart = r; break; }
  return { start: cfg.start, mainEnd, tailStart, last };
}
const rEval = k => O2.makeEvaluator(rTab(k));
/* 液氧表 / 4号院：按月自动「合计」行（规则与 app/reports.py auto_sums 一致；不存进表，屏幕、打印、下载时现算） */
const R_SUM_FROM = '2026-10', R_SUM_COLS = { lox: ['C', 'D', 'F'], yard4: ['D', 'E', 'F'] };
const R_SUM_A = /^合\s*计$/, R_LEAD_NUM = /^[^\d.+\-=*/]*?(-?\d+(?:\.\d+)?)\s*$/;
function rNumOf(v) { if (v === null || v === undefined || typeof v === 'boolean') return null; if (typeof v === 'number') return v; const m = R_LEAD_NUM.exec(String(v).trim()); return m ? +m[1] : null; }
function rAutoSums(k, ev) {
  if (!R_SUM_COLS[k]) return [];
  const tab = rTab(k), rg = rRanges(k); ev = ev || rEval(k);
  let cur = null, cols = null; const manual = new Set(), recs = {}, order = [];
  for (let r = RT[k].start; r <= rg.mainEnd; r++) {
    const x = tab.rows[r - 1]; if (!x || !Object.values(x.c).some(cc => (cc.v !== null && cc.v !== undefined && cc.v !== '') || cc.f)) continue;
    const a = String(rRaw(tab, 'A', r)).trim();
    if (R_SUM_A.test(a)) { if (cur) manual.add(cur); const cs = Object.keys(x.c).sort().filter(c => c !== 'A' && ((x.c[c].v !== null && x.c[c].v !== undefined && x.c[c].v !== '') || x.c[c].f)); if (cs.length) cols = cs; continue; }
    const d = rIso(a); if (d) cur = d.slice(0, 7);
    if (!cur) continue;
    if (!recs[cur]) { recs[cur] = { after: r, rows: [], skipped: [] }; order.push(cur); }
    const g = recs[cur]; g.after = r;
    (Object.values(x.c).some(cc => String(cc.v == null ? '' : cc.v).includes('不算')) ? g.skipped : g.rows).push(r);
  }
  cols = cols || R_SUM_COLS[k];
  const r2 = v => Math.floor(v * 100 + 0.5 + 1e-9) / 100;
  return order.filter(m => m >= R_SUM_FROM && !manual.has(m)).map(m => {
    const g = recs[m], vals = {};
    cols.forEach(c => { const ns = g.rows.map(r => { const cell = rCell(tab, c, r); return rNumOf(cell && cell.f ? ev.val(c, r) : rRaw(tab, c, r)); }).filter(n => n !== null && !isNaN(n)); if (ns.length || !g.rows.length) vals[c] = r2(ns.reduce((a, b) => a + b, 0)); });
    return { after: g.after, month: m, vals, n: g.rows.length, skipped: g.skipped };
  }).sort((a, b) => a.after - b.after);
}
function rAutoTip(s) { return `自动合计：${+s.month.slice(0, 4)}年${+s.month.slice(5)}月（${s.n} 行${s.skipped.length ? '；写了「不算」的 ' + s.skipped.length + ' 行不计入' : ''}）。随表格修改自动更新，不能直接改。`; }
/** 改几张表并马上保存；保存没成功（取消密码等）就把这几张表恢复原样，避免重复写入 */
async function rAtomic(keys, fn) {
  const snap = {}; keys.forEach(k => { snap[k] = JSON.stringify({ rows: rTab(k).rows, merges: rTab(k).merges, d: RP.dirty[k] || 0 }); });
  try { return await fn(); }
  catch (e) { keys.forEach(k => { const o = JSON.parse(snap[k]); RP.tabs[k].rows = o.rows; RP.tabs[k].merges = o.merges; if (o.d) RP.dirty[k] = o.d; else delete RP.dirty[k]; }); if (!Object.keys(RP.dirty).length) { App.guard = null; App.guardSave = null; } rRender(true); throw e; }
}
function rDirty(k, why) {
  RP.dirty[k] = (RP.dirty[k] || 0) + 1;
  App.guard = '报表有改动还没保存。可在本窗点「保存」，或点顶栏保存后再离开。';
  App.guardSave = () => rSaveTabs(Object.keys(RP.dirty), '修改');
  rBar();
}

/* ---------- 列 / 表头 ---------- */
/* 显示设置（每张表一份，存在服务器，大家共用）：{hidden:[列], order:[列], labels:{列:名}, from, to, filters:[{c,q}]} */
const rPref = k => (RP.prefs || {})[k] || null;
const rCustom = k => { const p = rPref(k); return !!(p && ((p.hidden || []).length || (p.order || []).length || Object.keys(p.labels || {}).length)); };
const rDateCol = k => k === 'ledger' ? 'I' : 'A';
function rFiltered(k) { const p = rPref(k); return !!(p && (p.from || p.to || (p.filters || []).some(f => f.c && f.q))); }
/** 某列当前筛选字（@u8 / 字母列）；日期列另用 from/to */
function rFiltQ(k, c) {
  const p = rPref(k); if (!p) return '';
  if (c === rDateCol(k) && (p.from || p.to)) return (p.from || '…') + '~' + (p.to || '…');
  const f = (p.filters || []).find(x => x.c === c && x.q); return f ? f.q : '';
}
function rFiltOn(k, c) {
  const p = rPref(k); if (!p) return false;
  if (c === rDateCol(k) && (p.from || p.to)) return true;
  return (p.filters || []).some(f => f.c === c && f.q);
}
function rCellText(k, c, r, ev) {
  if (c === '@u8') {
    const a = ((rTab(k) || {}).row_arrival || {})[r];
    if (!a) return '';
    return a.u8 === '不入U8' ? '不用入U8' : (a.u8 || '');
  }
  const tab = rTab(k), cell = rCell(tab, c, r);
  return cell ? (cell.f ? ev.val(c, r) : cell.v) : '';
}
function rRowOk(k, r, ev) {
  const p = rPref(k); if (!p) return true; const tab = rTab(k);
  if (p.from || p.to) { const d = rIso(rRaw(tab, rDateCol(k), r)); if (!d || (p.from && d < p.from) || (p.to && d > p.to)) return false; }
  for (const f of p.filters || []) {
    if (!f.c || !f.q) continue;
    const v = rCellText(k, f.c, r, ev);
    if (!String(v == null ? '' : v).toLowerCase().includes(String(f.q).toLowerCase())) return false;
  }
  return true;
}
function rCols(k, base) {
  let cols = rBaseCols(k); const p = rPref(k); if (base || !p) return cols;
  if ((p.order || []).length) { const pos = c => { const i = p.order.indexOf(c); return i < 0 ? 1000 + rN(c) : i; }; cols = cols.slice().sort((a, b) => pos(a) - pos(b)); }
  const hid = p.hidden || []; const vis = cols.filter(c => !hid.includes(c));
  return vis.length ? vis : cols;
}
function rFullLabel(k, c) {
  const l = rHeadLabel(k, c), n = rN(c);
  if (k === 'conv') { if (c === 'A') return '日期'; if (n >= 2 && n <= 7) return '气态' + l; if (n >= 8 && n <= 19) return '液态' + l; return { T: '合计', U: '损耗', V: '总计', W: '批次' }[c] || (n >= 24 ? '碳纤维瓶' + l : l); }
  if (k === 'ledger') { if (c === 'A') return '序号'; if (n >= 2 && n <= 8) return '入库' + l; if (n >= 9 && n <= 11) return l.startsWith('出') ? l : '出库' + l; if (n >= 12 && n <= 14) return l; }
  return l || c;
}
const rLabel = (k, c) => { const p = rPref(k); return (p && p.labels && p.labels[c]) || rFullLabel(k, c); };
function rBaseCols(k) {
  const cfg = RT[k], tab = rTab(k), rg = rRanges(k);
  if (cfg.maxCol) { const out = []; for (let i = 1; i <= rN(cfg.maxCol); i++) { const c = rC(i); if (!(cfg.hideCols || []).includes(c)) out.push(c); } return out; }
  const used = new Set(); const r0 = Math.min(cfg.head, cfg.early ? cfg.early[0] : cfg.head);
  for (let r = r0; r <= rg.last; r++) { const row = tab.rows[r - 1]; if (!row) continue; Object.keys(row.c).forEach(c => { const x = row.c[c]; if (x && ((x.v != null && String(x.v).trim() !== '') || x.f)) used.add(c); }); }
  let max = 1; used.forEach(c => { max = Math.max(max, rN(c)); });
  const out = []; for (let i = 1; i <= max; i++) { const c = rC(i); if (used.has(c) || i <= 6) out.push(c); }
  return out;
}
function rHeadLabel(k, c) {
  const cfg = RT[k], tab = rTab(k); let v = rRaw(tab, c, cfg.head);
  if ((v === '' || v == null) && k === 'ledger') v = { K: '出库量', M: '当前批次', N: '新批次/备注' }[c] || '';
  if (k === 'ledger' && c === 'J') v = '去向';
  if (k === 'ledger') v = String(v).replace(/\n/g, '').replace('入库量（吨）', '入库量(吨)');
  if (k === 'conv') v = String(v).replace('钢瓶', '').replace('其他规格', '其他');
  if (k === 'stock' && c === 'H' && !v) v = 'U8备注';
  return String(v || '').replace(/\n/g, ' ');
}
function rWidth(k, c) {
  const p = rPref(k);
  if (p && p.widths && p.widths[c] != null) return Math.max(40, Math.min(800, +p.widths[c] || 96));
  const X = { '@u8': 76, '@ph': 44, '@att': 52, '@act': 78, '@rate': 52 };
  if (X[c]) return X[c];
  // 默认更紧：少左右划；名称/备注等可拖宽，设置里可藏列
  const W = {
    conv: { A: 84, W: 96 },
    ledger: { A: 44, B: 72, C: 72, D: 72, E: 72, F: 56, G: 64, H: 120, I: 84, J: 80, K: 64, L: 72, M: 72, N: 100 },
    stock: { A: 64, B: 110, C: 88, D: 36, E: 52, F: 72, G: 72, H: 64, I: 56, J: 64, K: 72 },
    lox: { A: 84, B: 56, C: 56, D: 56, E: 120, F: 56, G: 56, H: 56, I: 56, J: 64, K: 64, L: 140 },
    yard4: { A: 84, B: 56, C: 56, D: 110, E: 56, F: 120 }
  }[k] || {};
  if (W[c]) return W[c];
  if (k === 'conv') return RT.conv.dec2.includes(c) ? 56 : 44;
  return 72;
}
/** 表头格：可拖右边调列宽；data-c 供拖拽识别；opt.filter 显示按表头筛选 ▾ */
function rTh(k, c, label, cls, opt) {
  opt = opt || {};
  const w = rWidth(k, c), rs = opt.rowspan ? ` rowspan="${opt.rowspan}"` : '', cs = opt.colspan ? ` colspan="${opt.colspan}"` : '';
  const tip = opt.title ? ` title="${esc(opt.title)}"` : '';
  const on = opt.filter && rFiltOn(k, c);
  const ff = opt.filter ? `<button type="button" class="r-ff${on ? ' on' : ''}" data-ff="${c}" title="按表头筛选${on ? '：' + esc(rFiltQ(k, c)) : ''}">▾</button>` : '';
  return `<th data-c="${c}" class="${cls || ''}${on ? ' r-ffon' : ''}" style="width:${w}px"${rs}${cs}${tip}>${label}${ff}<i class="r-rz" data-rz="${c}" title="拖动调节列宽"></i></th>`;
}
function rHeadHtml(k, cols) {
  const cfg = RT[k], act = rTh(k, '@act', '', 'r-act', { rowspan: 2 });
  const stockF = k === 'stock';   // 库存及到货总数：表头 ▾ 筛选（与设置里默认筛选同一套 prefs）
  if (rCustom(k)) {   // 自定义了列：简单的一行表头
    let h = ''; cols.forEach(c => { if (k === 'conv' && c === 'U') h += rTh(k, '@rate', '损耗率', 'rate'); h += rTh(k, c, esc(rLabel(k, c)), `${cfg.hl.includes(c) ? 'hl ' : ''}${cfg.computed.includes(c) ? 'comp ' : ''}${c === cfg.sticky ? 'stk' : ''}`, stockF ? { filter: true } : {}); });
    if (cfg.att) h += rTh(k, '@att', '附件', 'r-att');
    if (k === 'stock') h += rTh(k, '@u8', 'U8', '', { filter: true }) + rTh(k, '@ph', '照片', 'r-att');
    return '<tr>' + h + (cfg.ro ? '' : rTh(k, '@act', '', 'r-act')) + '</tr>';
  }
  const th = c => rTh(k, c, esc(rHeadLabel(k, c)), `${cfg.hl.includes(c) ? 'hl ' : ''}${cfg.computed.includes(c) ? 'comp ' : ''}${c === cfg.sticky ? 'stk' : ''}`, stockF ? { filter: true } : {});
  const g = (label, n, title) => `<th colspan="${n}" class="grp"${title ? ` title="${esc(title)}"` : ''}>${label}</th>`;
  if (k === 'conv') {
    const r1 = rTh(k, 'A', '日期', 'stk', { rowspan: 2 }) + g('气态', 6) + g('液态 <span class="r-tip">10L 按 0.5 个 20L 填</span>', 12) +
      rTh(k, 'T', '合计', 'comp', { rowspan: 2 }) + rTh(k, '@rate', '损耗率', 'rate', { rowspan: 2, title: '每行可改' }) + rTh(k, 'U', '损耗', 'comp', { rowspan: 2 }) + rTh(k, 'V', '总计', 'hl comp', { rowspan: 2 }) + rTh(k, 'W', '批次', '', { rowspan: 2 }) + g('碳纤维瓶', 5) + act;
    let r2 = ''; cols.forEach(c => { if (['A', 'T', 'U', 'V', 'W'].includes(c)) return; r2 += `<th data-c="${c}" class="${cfg.computed.includes(c) ? 'comp' : ''}" style="width:${rWidth(k, c)}px">${esc(rHeadLabel(k, c))}<i class="r-rz" data-rz="${c}" title="拖动调节列宽"></i></th>`; });
    return '<tr>' + r1 + '</tr><tr>' + r2 + '</tr>';
  }
  if (k === 'ledger') {
    const r1 = rTh(k, 'A', '序号', 'stk', { rowspan: 2 }) + g('入库', 7) + g('出库', 3) + g('结存', 3) + (cols.length > 14 ? g('其他', cols.length - 14) : '') + act;
    let r2 = ''; cols.forEach(c => { if (c !== 'A') r2 += th(c); });
    return '<tr>' + r1 + '</tr><tr>' + r2 + '</tr>';
  }
  let r = ''; cols.forEach(c => { r += th(c); });
  if (cfg.att) r += rTh(k, '@att', '附件', 'r-att');
  if (k === 'stock') r += rTh(k, '@u8', 'U8', '', { filter: true }) + rTh(k, '@ph', '照片', 'r-att');
  return '<tr>' + r + (cfg.ro ? '' : rTh(k, '@act', '', 'r-act')) + '</tr>';
}
function rTableWidth(k, cols) {
  return rColKeys(k, cols).reduce((a, c) => a + rWidth(k, c), 0);
}
/** 屏幕列序（含特殊列 @rate/@u8…），与表头叶子列一一对应；双行/合并表头靠 <colgroup> 定宽才能拖 */
function rColKeys(k, cols) {
  cols = cols || rCols(k);
  const out = [];
  cols.forEach(c => { if (k === 'conv' && c === 'U') out.push('@rate'); out.push(c); });
  if (RT[k].att) out.push('@att');
  if (k === 'stock') { out.push('@u8'); out.push('@ph'); }
  if (!RT[k].ro) out.push('@act');
  return out;
}
function rColgroup(k, cols) {
  return '<colgroup>' + rColKeys(k, cols).map(c => `<col data-c="${c}" style="width:${rWidth(k, c)}px">`).join('') + '</colgroup>';
}

/* ---------- 渲染 ---------- */
function rRateOf(tab, r) { const c = rCell(tab, 'U', r); if (!c || !c.f) return null; const m = /^T(\d+)\*([\d.]+)$/.exec(c.f.replace(/\s|\$/g, '')); return m && +m[1] === r ? +m[2] : null; }
function rRowsHtml(k, cols, from, to, ev, opt) {
  const cfg = RT[k], tab = rTab(k); opt = opt || {};
  const skip = new Set(), span = {};
  const ordered = rCustom(k) && (rPref(k).order || []).length;
  tab.merges.forEach(m => {
    if (ordered) return;
    const [a, b] = m.split(':'); const A = O2.splitAddr(a), B = O2.splitAddr(b || a);
    if (!A || !B || B.r < from || A.r > to) return;
    const r1 = Math.max(A.r, from), r2 = Math.min(B.r, to);
    const vc = cols.filter(c => rN(c) >= rN(A.c) && rN(c) <= rN(B.c)); if (!vc.length) return;
    for (let r = r1; r <= r2; r++) vc.forEach(c => skip.add(c + r));
    skip.delete(vc[0] + r1); span[vc[0] + r1] = { rs: r2 - r1 + 1, cs: vc.length };
  });
  let h = '';
  for (let r = from; r <= to; r++) {
    if (opt.filter && !rRowOk(k, r, ev)) continue;
    const row = tab.rows[r - 1];
    const isHead = opt.headRows && opt.headRows.includes(r);
    const isSum = /^合\s*计$/.test(String(rRaw(tab, 'A', r)).trim());
    let tr = `<tr data-r="${r}" class="${isHead ? 'subh ' : ''}${isSum ? 'sum ' : ''}">`;
    cols.forEach(c => {
      if (k === 'conv' && c === 'U') {
        const rate = rRateOf(tab, r), lit = rCell(tab, 'U', r);
        tr += `<td class="rate-c" data-r="${r}" data-c="@RATE" title="损耗率（双击修改）">${rate != null ? (+(rate * 100).toFixed(2)) + '%' : (lit && lit.v != null ? '<span class="muted">固定</span>' : '')}</td>`;
      }
      if (skip.has(c + r)) return;
      const sp = span[c + r], cell = row && row.c[c];
      const v = cell ? (cell.f ? ev.val(c, r) : cell.v) : null; const isF = !!(cell && cell.f);
      const ro = (cfg.computed.includes(c) && r >= cfg.start && !isHead) || cfg.ro;
      const cls = [];
      if (c === cfg.sticky) cls.push('stk');
      if (cfg.computed.includes(c) && r >= cfg.start && !isHead) cls.push('comp');
      if (cfg.hl.includes(c)) cls.push('hl');
      if (isF && !ro) cls.push('f');
      if (typeof v === 'number') cls.push('n');
      if (typeof v === 'string' && v[0] === '#') cls.push('err');
      const txt = rFmt(v, (cfg.dec2 || []).includes(c) && isF);
      const title = isF ? '公式：=' + cell.f + (txt ? '  →  ' + txt : '') : (txt.length > 10 ? txt : '');
      tr += `<td data-r="${r}" data-c="${c}"${sp ? ` rowspan="${sp.rs}" colspan="${sp.cs}"` : ''} class="${cls.join(' ')}"${title ? ` title="${esc(title)}"` : ''}>${esc(txt)}</td>`;
    });
    if (cfg.att) { const n = ((row && row.att) || []).length; tr += `<td class="r-att">${n ? `<a data-att="${r}">照片 ${n}</a>` : `<a class="link d" data-addatt="${r}" title="添加照片">＋</a>`}</td>`; }
    if (k === 'stock') {
      const a = (rTab('stock').row_arrival || {})[r];
      const u8tag = a ? (a.u8 === '待入U8' ? 'tag warn' : a.u8 === '已入U8' ? 'tag ok' : 'tag') : '';
      const u8txt = a ? (a.u8 === '不入U8' ? '不用入U8' : a.u8) : '';
      tr += `<td class="w r-u8c">${a ? `<a class="link" data-rec="arrival:${a.id}" title="看原始记录">↗</a> ` : ''}${a ? `<span class="${u8tag} r-u8tag" data-u8menu="${a.id}" data-u8cur="${esc(a.u8)}" title="点这里改：待入U8 / 已入U8 / 不用入U8">${esc(u8txt)}</span>` : ''}</td><td class="r-att">${a && a.n ? `<a data-arph="${a.id}">照片 ${a.n}</a>` : ''}</td>`;
    }
    if (!cfg.ro) tr += `<td class="r-act">${rRowActs(k, r)}</td>`;
    h += tr + '</tr>';
    if (opt.sums && opt.sums[r]) opt.sums[r].forEach(s => {
      let t = `<tr class="sum r-auto" title="${esc(rAutoTip(s))}">`;
      cols.forEach(c => { if (k === 'conv' && c === 'U') t += '<td></td>'; const v = c === 'A' ? '合计' : s.vals[c]; t += `<td class="comp${c === cfg.sticky ? ' stk' : ''}${typeof v === 'number' ? ' n' : ''}">${esc(typeof v === 'number' ? v.toFixed(2) : (v || ''))}</td>`; });
      if (cfg.att) t += '<td class="r-att"></td>'; if (!cfg.ro) t += '<td class="r-act"></td>';
      h += t + '</tr>';
    });
  }
  return h;
}
function rRowActs(k, r) {
  const b = (t, tip, a, cls) => `<button class="r-ib ${cls || ''}" title="${tip}" data-${a}="${r}">${t}</button>`;
  let s = '';
  if (k === 'conv') s += b('→记录', '把这天的总计写入「液态氧原料入出库记录」', 'push');
  const ln = ((rTab(k).rows[r - 1] || {}).link) || null;
  if (k === 'ledger' && !ln && RP.tabs.conv && /本库/.test(String(rRaw(rTab(k), 'J', r))) && rConvRowOf(rIso(rRaw(rTab(k), 'I', r)))) s += b('⇄', '接上换算表：以后这一行的出库量跟着换算表这一天的总计自动变', 'lnk');
  if (k === 'ledger' && ln && ln.k === 'conv') s += b('↗', '出库量来自换算表 ' + esc(ln.date) + '（改换算表会自动更新），点这里去看那一天', 'src');
  if ((k === 'lox' || k === 'yard4') && ln && ln.k === 'slip') { const w = ((rTab(k).slip_state || {})[r] || {}).warn; s += b(w ? '⚠' : '↗', w ? esc(w) + '，请核对这一行' : '用称重单登记的，点这里看称重单', 'src', w ? 'd' : ''); }
  if (k === 'ledger' && ln && ln.k === 'lox') s += b(ln.missing ? '⚠' : '↗', ln.missing ? '液氧表里已找不到 ' + esc(ln.date) + ' 卸' + esc(ln.place) + ' 的那车，请核对' : '来自液氧表 ' + esc(ln.date) + ' 卸' + esc(ln.place) + '（改液氧表会自动更新），点这里去看', 'src', ln.missing ? 'd' : '');
  if (k === 'ledger' && ln && ln.k === 'lox_in') s += b(ln.missing ? '⚠' : '↗入库', ln.missing ? '液氧表里已找不到这批质检入库，请核对' : '左侧入库来自液氧表质检U8（改液氧表会自动更新），点这里去看', 'src', ln.missing ? 'd' : '');
  if (k === 'lox' && rTab(k).rows[r - 1] && rParseDate(rRaw(rTab(k), 'A', r)) && rLoxOut(r).length) {
    const id = rTab(k).rows[r - 1].lx, lk = id ? rLoxLinked(id) : [];
    s += lk.length ? b('↗记录', '已记入「液态氧原料入出库记录」第 ' + lk.join('、') + ' 行，点这里去看', 'lxgo') : b('→记录', '关联到入出库记录：把这车卸到别处的吨数记成出库（不点就不动）', 'lxlnk');
  }
  if (k === 'lox' && rLoxQc(r)) {
    const id = (rTab(k).rows[r - 1] || {}).lx, ik = id ? rLoxInLinked(id) : [];
    s += ik.length ? b('↗入库', '质检U8已写入入出库记录左侧入库第 ' + ik.join('、') + ' 行', 'lxingo') : b('→入库', '把质检U8批次号入库写进入出库记录左侧入库（只加不改空）', 'lxin');
  }
  if (k !== 'conv') s += b('＋', '在下方插入一行', 'ins');   // 入出库记录也可中间插行（换算表按日期插入，不用行上＋）
  s += b('✕', '删除这一行', 'del', 'd');
  return '<div class="r-acts">' + s + '</div>';
}
function rSummary(k) {
  const tab = rTab(k), rg = rRanges(k), ev = rEval(k);
  const chip = (l, v, cls) => `<div class="r-kpi ${cls || ''}"><span>${l}</span><b>${esc(v)}</b></div>`;
  if (k === 'conv') {
    const r = rg.mainEnd, d = rRaw(tab, 'A', r), v = ev.val('V', r), dd = rParseDate(d); let mon = 0;
    if (dd) for (let x = rg.start; x <= rg.mainEnd; x++) { const q = rParseDate(rRaw(tab, 'A', x)); if (q && q.getMonth() === dd.getMonth() && q.getFullYear() === dd.getFullYear()) { const y = ev.val('V', x); if (typeof y === 'number') mon += y; } }
    return chip('最新日期', d || '—') + chip('当天总计', typeof v === 'number' ? v.toFixed(2) + ' 吨' : '—') + chip((dd ? (dd.getMonth() + 1) + '月' : '本月') + '累计', mon.toFixed(2) + ' 吨');
  }
  if (k === 'ledger') { const r = rg.mainEnd, lv = ev.val('L', r), m = rRaw(tab, 'M', r), n = rRaw(tab, 'N', r); const cur = (String(n || '').trim() ? n : m); return chip('最近出库', (rRaw(tab, 'I', r) || '—') + ' ' + rFmt(ev.val('K', r))) + chip('批次剩余', typeof lv === 'number' ? lv.toFixed(2) + ' 吨' : rFmt(lv)) + chip('当前批次', rFmt(cur) || '—'); }
  if (k === 'stock') { let lastD = ''; for (let r = rg.last; r >= 3; r--) { const d = rRaw(tab, 'A', r); if (rParseDate(d)) { lastD = d; break; } } return chip('待入U8', (tab.pending_u8 || 0) + ' 条', tab.pending_u8 ? 'warn' : '') + chip('最近到货', lastD || '—'); }
  const k0 = k === 'lox' ? 13 : 2; let lastR = null; for (let r = rg.last; r >= k0; r--) if (rParseDate(rRaw(tab, 'A', r))) { lastR = r; break; }
  if (!lastR) return '';
  return chip(k === 'lox' ? '最近到车' : '最近卸车', rRaw(tab, 'A', lastR) + ' ' + rRaw(tab, 'B', lastR)) + chip(k === 'lox' ? '过磅合计' : '卸四号库', rFmt(ev.val('D', lastR)) + ' 吨');
}
function rBar() {
  const n = Object.keys(RP.dirty).length, b = $('#rSave'); if (!b) return;
  b.disabled = !n; b.textContent = n ? `保存（${Object.keys(RP.dirty).map(k => RT[k].short).join('、')}）` : '已保存';
  $$('#rTabs button').forEach(x => x.classList.toggle('dirty', !!RP.dirty[x.dataset.k]));
}
function rRender(keep) {
  const box = $('#rGrid'); if (!box) return;
  const k = RP.k, cfg = RT[k];
  $$('#rTabs button').forEach(t => t.classList.toggle('on', t.dataset.k === k));
  $('#rKpis').innerHTML = rSummary(k);
  rTools();
  const sc = box.scrollTop, sl = box.scrollLeft;
  const cols = rCols(k), ev = rEval(k), rg = rRanges(k), span = cols.length + 5;
  let body = '';
  if (cfg.early && RP.showTail[k]) body += rRowsHtml(k, cols, cfg.early[0], cfg.early[1], ev, { headRows: [cfg.early[0]] }) + `<tr class="sep"><td colspan="${span}">以上为早期记录（旧表头）· 以下为当前表</td></tr>`;
  const filt = rFiltered(k), sums = {}; if (!filt) rAutoSums(k, ev).forEach(s => (sums[s.after] = sums[s.after] || []).push(s));
  body += rRowsHtml(k, cols, rg.start, Math.max(rg.mainEnd, rg.start), ev, { filter: filt, sums });
  if (rg.tailStart && RP.showTail[k]) body += `<tr class="sep"><td colspan="${span}">以下是表格下方原有的旧数据 / 备份（第 ${rg.tailStart} 行起），原样保留，也可编辑</td></tr>` + rRowsHtml(k, cols, rg.tailStart, rg.last, ev);
  const thtml = rHeadHtml(k, cols), tw = rTableWidth(k, cols);
  // 列宽合计作表宽（不强制 100%），中间不会出现空白缝；库存表可拖列宽，设置里保存
  box.innerHTML = `<table class="rt rt-${k}${k === 'stock' ? ' stock-fit' : ''}" style="table-layout:fixed;width:${tw}px">${rColgroup(k, cols)}<thead>${thtml}</thead><tbody>${body}</tbody></table>`;
  if (keep) { box.scrollTop = sc; box.scrollLeft = sl; }
  else requestAnimationFrame(rLatest);
  if (RP.sel && RP.sel.k === k) rSelect(RP.sel.r, RP.sel.c, true);
  rBar();
  rAttachResize(box, k);
  requestAnimationFrame(() => {
    const t = box.querySelector('table.rt'); if (!t) return;
    syncStickyHeads(t);
    if (typeof CellSel !== 'undefined') CellSel.on(t, {
      onActive: (td) => {
        if (!td || !td.dataset.c) return;
        $$('#rGrid td.sel').forEach(x => x.classList.remove('sel'));
        td.classList.add('sel');
        RP.sel = { k: RP.k, r: +td.dataset.r, c: td.dataset.c };
      }
    });
  });
}
function rLatest() {
  const box = $('#rGrid'); if (!box) return; const rg = rRanges(RP.k);
  const tr = box.querySelector(`tr[data-r="${rg.mainEnd}"]`);
  box.scrollTop = tr ? Math.max(0, tr.offsetTop - box.clientHeight + 90) : box.scrollHeight;
}
function rTools() {
  const k = RP.k, cfg = RT[k], rg = rRanges(k), t = rTab(k);
  const add = { conv: '＋ 新增一天', ledger: '＋ 新增出库', stock: '去「到货」登记', lox: '＋ 登记到车', yard4: '＋ 新增一行' }[k];
  /* 左：主操作；右：提示 + 最后修改 + 打印组（同一行，不另起说明条） */
  let h = `<button class="btn ${k === 'stock' ? '' : 'pri'} sm" id="rAdd">${add}</button>`;
  if (k === 'conv') h += '<button class="btn sm" id="rOcrD">识别用量截图</button>';
  if (k === 'lox') {
    const nPend = rLoxPendingQc().length;
    h += `<button class="btn sm ${nPend ? 'pri' : ''}" id="rLoxPend" title="质检已齐、尚未写入左侧入库">${nPend ? '待写入质检 ' + nPend : '待写入质检 0'}</button>`;
  }
  if (k === 'ledger') {
    h += `<button class="btn sm" id="rLedNext" title="用未用完的新批次开一行出库">接下一批</button>`;
    h += `<button class="btn sm" id="rLedTwo" title="旧批不够时：剩余+新取=合计">一天两批</button>`;
  }
  if (rg.tailStart || cfg.early) h += `<label class="r-tog"><input type="checkbox" id="rTail" ${RP.showTail[k] ? 'checked' : ''}> ${cfg.early ? '显示早期记录' : '显示下方旧数据'}</label>`;
  if (k === 'stock') h += '<span class="muted r-ro" title="本表由「到货」自动生成；表头 ▾ 可筛选；可拖列宽；点 U8 可改状态。登记、改删请去「到货」页">只读·请在到货页录入</span>';
  h += `<span class="sp"></span>`;
  h += `<span class="muted r-hint">改数后点保存 · 灰列自动算<details class="ph-help"><summary></summary><div class="ph-help-b">双击或直接打字；方向键 / Enter / Tab 移动。下载与原 Excel 格式一致。</div></details></span>`;
  h += `<span class="muted r-ver">${t.updated_by ? '最后修改：' + esc(t.updated_by) + ' ' + fmtTs(t.updated_at) : ''}</span>`;
  h += `<div class="r-ops" title="打印 / 下载 / 显示设置">
    <button class="btn sm" id="rPrint">打印</button>
    <button class="btn sm" id="rDown" title="与原表格式完全一致（不受显示设置影响）">下载 Excel</button>
    <button class="btn sm" id="rSetB" title="列显示、顺序、列名、筛选；列宽可拖表头，也会保存在这里">设置</button>
    <div class="r-more"><button class="btn sm" id="rMoreB">⋯</button><div class="r-menu"><a id="rViewX">按当前显示导出 Excel</a><a id="rImp">导入 Excel（用我的文件替换）</a><a id="rReset">恢复为内置原表（本表）</a><div class="muted">下载的文件与原表格式一致：表头、合并单元格、列宽、数字格式、公式都保留。屏幕列宽拖表头即可，自动保存。</div></div></div>
  </div>`;
  if (rFiltered(k) || rCustom(k) || (rPref(k) && rPref(k).widths && Object.keys(rPref(k).widths).length)) {
    const p = rPref(k) || {}; const fs = []; if (p.from || p.to) fs.push((p.from || '…') + ' ~ ' + (p.to || '…'));
    (p.filters || []).filter(f => f.c && f.q).forEach(f => fs.push(rLabel(k, f.c) + ' 含「' + f.q + '」'));
    const bits = []; if (rCustom(k)) bits.push('自定义列'); if (p.widths && Object.keys(p.widths).length) bits.push('自定义列宽'); if (fs.length) bits.push('筛选 ' + fs.join('，'));
    const hasW = !!(p.widths && Object.keys(p.widths).length);
    h += `<div class="r-note">按「设置」显示${bits.length ? '：' + esc(bits.join('；')) : ''}。<a class="link" id="rSetClr">临时显示全部</a>${hasW ? ' · <a class="link" id="rResetW" title="只清自定义列宽，列显示/筛选保留">重置列宽</a>' : ''}</div>`;
  }
  if (k === 'ledger') { const miss = (t.rows || []).map((x, i) => x && x.link && x.link.missing ? i + 1 : 0).filter(Boolean); if (miss.length) h += `<div class="r-note bad">第 ${miss.join('、')} 行原来来自换算表，但换算表里已经没有那一天了（被删除）。出库量保留原值，请核对；可在「数据备份 → 回收站」恢复换算表那一行。</div>`; }
  $('#rTools').innerHTML = h;
  $('#rAdd').onclick = rAdd; if ($('#rOcrD')) $('#rOcrD').onclick = rOcrDaily;
  if ($('#rLoxPend')) $('#rLoxPend').onclick = () => rLoxPendingPanel();
  if ($('#rLedNext')) $('#rLedNext').onclick = () => rLedgerNextBatchDlg().catch(fail);
  if ($('#rLedTwo')) $('#rLedTwo').onclick = () => rLedgerTwoBatchDlg().catch(fail);
  if ($('#rTail')) $('#rTail').onchange = e => { RP.showTail[k] = e.target.checked; rRender(true); };
  $('#rDown').onclick = () => { if (RP.dirty[k]) return toast('这张表还有改动没保存，先点「保存」再下载', true); download('/api/report.xlsx?key=' + k); };
  $('#rPrint').onclick = () => rPrintDlg(k);
  $('#rMoreB').onclick = e => {
    e.stopPropagation();
    const wrap = $('.r-more'), mu = $('.r-menu', wrap); if (!wrap || !mu) return;
    const on = !wrap.classList.contains('on');
    $$('.r-more.on').forEach(x => x.classList.remove('on'));
    if (!on) return;
    wrap.classList.add('on');
    const r = e.currentTarget.getBoundingClientRect(), w = mu.offsetWidth || 280, h = mu.offsetHeight || 120;
    let top = r.bottom + 4; if (top + h > innerHeight - 8) top = Math.max(8, r.top - h - 4);
    mu.style.top = top + 'px'; mu.style.left = Math.max(8, Math.min(r.right - w, innerWidth - w - 8)) + 'px';
  };
  // 点别处关掉报表 ⋯ 菜单
  if (!window._rMoreDoc) { window._rMoreDoc = 1; document.addEventListener('click', () => $$('.r-more.on').forEach(x => x.classList.remove('on'))); }
  $('#rImp').onclick = rImport; $('#rReset').onclick = rReset;
  $('#rSetB').onclick = () => rPrefsDlg(k); $('#rViewX').onclick = () => rExportView(k).catch(fail);
  if ($('#rSetClr')) $('#rSetClr').onclick = () => { RP.prefsOff = RP.prefsOff || {}; RP.prefsOff[k] = RP.prefs[k]; delete RP.prefs[k]; rRender(true); toast('这次先显示全部（设置没变，刷新后照旧）'); };
  if ($('#rResetW')) $('#rResetW').onclick = () => rResetWidths(k).catch(fail);
}
async function rResetWidths(k) {
  const cur = Object.assign({}, rPref(k) || {});
  if (!cur.widths || !Object.keys(cur.widths).length) { toast('没有自定义列宽'); return; }
  if (!await confirmBox('只把本表屏幕列宽恢复默认？（列显示、顺序、筛选都保留）', '重置列宽')) return;
  delete cur.widths;
  const d = {
    hidden: cur.hidden || [], order: cur.order || [], labels: cur.labels || {},
    from: cur.from || '', to: cur.to || '', filters: cur.filters || [], widths: {}
  };
  await save('/api/report/prefs/save', { key: k, data: d }, '重置列宽');
  RP.prefs[k] = d; if (RP.prefsOff) delete RP.prefsOff[k];
  rRender(true); toast('已重置列宽');
}
async function rLoad(k) { const d = await api('/api/report?key=' + k); RP.tabs[k] = d; delete RP.dirty[k]; if (RP.keepTo) delete RP.keepTo[k]; /* 删行撤销须保留：保存后的 rLoad 不能把 del 清掉 */ RP.undo = RP.undo.filter(x => x.type === 'del' || x.k !== k); RP.redo = RP.redo.filter(x => x.type === 'del' || x.k !== k); return d; }

Pages.report = async (el, arg) => {
  RP.el = el; el.classList.add('wide');
  if (arg && RT[arg]) RP.k = arg; else if (!RP.k) RP.k = rOrder()[0];
  /* 顶栏已有「报表」：无页内大标题；页签行 = 页签 + 摘要 + 保存 */
  el.innerHTML = `<div class="card page-card r-card shell-list"><div class="tools r-top"><div class="seg" id="rTabs">${rOrder().map(k => `<button data-k="${k}">${RT[k].short}</button>`).join('')}</div><div class="r-kpis" id="rKpis"></div><span class="sp"></span><button class="btn pri sm" id="rSave" disabled>已保存</button></div>
    <div class="tools r-tools" id="rTools"></div><div class="r-grid" id="rGrid"></div></div>`;
  $('#rTabs').onclick = async e => { const b = e.target.closest('[data-k]'); if (!b) return; RP.k = b.dataset.k; RP.sel = null; if (typeof CellSel !== 'undefined') CellSel.clear(); history.replaceState(null, '', '#report/' + RP.k); App.curHash = location.hash; await rEnsure(RP.k); rRender(); };
  $('#rSave').onclick = () => rSaveTabs(Object.keys(RP.dirty), '修改').catch(fail);
  rBind();
  try { RP.prefs = (await api('/api/report/prefs')).items || {}; } catch (e) { RP.prefs = {}; }
  await rEnsure(RP.k); rRender();
  const op = sessionStorage.getItem('openPrefs'); if (op) { sessionStorage.removeItem('openPrefs'); if (RT[op]) { RP.k = op; await rEnsure(op); rRender(); rPrefsDlg(op); } }
  if (RP.pendingDlv && RP.k === 'lox') { const p = RP.pendingDlv; RP.pendingDlv = null; rDelivery(p); }
  // 首页「液氧质检入库」：滚到工具条；有待写入则打开列表（不改算法）
  try {
    if (sessionStorage.getItem('homeLoxFocus') === '1') {
      sessionStorage.removeItem('homeLoxFocus');
      requestAnimationFrame(() => {
        const tip = document.querySelector('#rTools .r-note, #rTools, .r-top');
        if (tip) tip.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        const grid = document.querySelector('#rGrid');
        if (grid && typeof UI !== 'undefined' && UI.scrollLatest) UI.scrollLatest(grid);
        if (RP.k === 'lox' && rLoxPendingQc().length) setTimeout(() => rLoxPendingPanel(), 300);
      });
    }
  } catch (e) { }
  // 打印页「液氧表」：若脚本未就绪时跳转过来，自动弹出打印对话框
  try {
    if (sessionStorage.getItem('printLox') === '1' && RP.k === 'lox') {
      sessionStorage.removeItem('printLox');
      setTimeout(() => { try { rPrintDlg('lox'); } catch (err) { } }, 200);
    }
  } catch (e) { }
};
async function rEnsure(k) { if (!RP.tabs[k] || (k === 'stock' && !RP.dirty[k])) await rLoad(k); if (k === 'ledger' && !RP.tabs.conv) await rLoad('conv'); }

/** 保存（可多张一起；slipIds = 登记到液氧表的称重单） */
async function rSaveTabs(keys, summary, slipIds, strict) {
  keys = keys.filter(k => k !== 'stock'); if (!keys.length) return;
  const tabs = {}; keys.forEach(k => { const t = RP.tabs[k]; tabs[k] = { rows: t.rows, merges: t.merges, version: t.version }; });
  const trash = (RP.trash || []).filter(x => keys.includes(x.key));
  try {
    const r = await save('/api/report/save', { tabs, summary, slip_ids: slipIds || [], trash }, '保存报表');
    RP.trash = (RP.trash || []).filter(x => !keys.includes(x.key));
    Object.entries(r.versions).forEach(([k, v]) => { if (!RP.tabs[k]) return; RP.tabs[k].version = v; RP.tabs[k].updated_by = (PIN.get() || {}).name; RP.tabs[k].updated_at = Date.now() / 1000; delete RP.dirty[k]; });
    for (const k of r.synced || []) if (RP.tabs[k] && !RP.dirty[k]) await rLoad(k);
    if (keys.includes('lox') && !RP._qcPrompting) {
      const pend = [];
      const t = rTab('lox'), rg = rRanges('lox');
      for (let rr = rg.start; rr <= rg.mainEnd; rr++) {
        const qc = rLoxQc(rr); if (!qc) continue;
        const id = (t.rows[rr - 1] || {}).lx;
        if (!id || !rLoxInLinked(id).length) pend.push(rr);
      }
      if (pend.length === 1) {
        RP._qcPrompting = true;
        setTimeout(async () => { try { if (await confirmBox('液氧表第 ' + pend[0] + ' 行质检U8已齐，写入「入出库记录」左侧入库？<br><span class="muted">只补空、不覆盖已有；也可稍后点行上「→入库」</span>', '去写入')) await rLoxInLinkDlg(pend[0]); } catch (e) {} finally { RP._qcPrompting = false; } }, 200);
      } else if (pend.length > 1) toast('有 ' + pend.length + ' 行质检U8未写入入库（行 ' + pend.join('、') + '），可点「→入库」');
    }
    if ((r.sync_notes || []).length) toast('入出库记录已跟着更新：' + r.sync_notes.slice(0, 3).join('；'));
    if (!Object.keys(RP.dirty).length) { App.guard = null; App.guardSave = null; }
    toast('已保存：' + keys.map(k => RT[k].short).join('、')); rRender(true);
  } catch (e) {
    if (e.code === 409 && strict) { toast(e.message, true); throw e; }
    if (e.code === 409) dialog('别人刚改过', `<div>${esc(e.message)}</div>`, [{ t: '先不管' }, { t: '下载我改的（未保存）', fn: () => { rPrintDlg(RP.k); return false; } }, { t: '丢掉我的修改，重新载入', cls: 'pri', fn: async () => { for (const k of keys) await rLoad(k); if (!Object.keys(RP.dirty).length) { App.guard = null; App.guardSave = null; } rRender(); } }]);
    else throw e;
  }
}

/* ---------- 选择 / 编辑 ---------- */
const rTd = (r, c) => $(`#rGrid td[data-r="${r}"][data-c="${c}"]`);
function rSelect(r, c, quiet) {
  $$('#rGrid td.sel').forEach(x => x.classList.remove('sel'));
  const td = rTd(r, c); if (!td) return;
  td.classList.add('sel'); RP.sel = { k: RP.k, r, c }; gridFocus(td.closest('table'), td);   // 行、列淡淡标出来
  if (typeof CellSel !== 'undefined') CellSel.setSingle(td.closest('table'), td);
  if (quiet) return;
  const box = $('#rGrid'), tb = td.getBoundingClientRect(), bb = box.getBoundingClientRect(), head = box.querySelector('thead').getBoundingClientRect().height;
  if (tb.top < bb.top + head) box.scrollTop -= (bb.top + head - tb.top + 4); else if (tb.bottom > bb.bottom - 12) box.scrollTop += tb.bottom - bb.bottom + 16;
  const st = box.querySelector('td.stk'); const sw = st ? st.getBoundingClientRect().width : 0;
  if (tb.left < bb.left + sw) box.scrollLeft -= (bb.left + sw - tb.left + 4); else if (tb.right > bb.right - 70) box.scrollLeft += tb.right - bb.right + 80;
}
const rIsRO = (k, r, c) => RT[k].ro || (RT[k].computed.includes(c) && r >= RT[k].start);
function rStartEdit(td, initial) {
  const k = RP.k, r = +td.dataset.r, c = td.dataset.c, tab = rTab(k);
  if (RT[k].ro) { toast('这张表在「到货」页修改'); return; }
  if (c !== '@RATE' && rIsRO(k, r, c)) { toast('这一列是自动计算的'); return; }
  if (td.querySelector('input')) return;
  const rate = rRateOf(tab, r);
  const raw = c === '@RATE' ? (rate != null ? String(+(rate * 100).toFixed(4)) : '') : String(rRaw(tab, c, r));
  const inp = document.createElement('input'); inp.className = 'r-ed'; inp.value = initial != null ? initial : raw;
  if (c === '@RATE') inp.placeholder = '8 = 8%';
  td.appendChild(inp); td.classList.add('ing'); inp.focus();
  if (initial == null) inp.select(); else inp.setSelectionRange(inp.value.length, inp.value.length);
  let done = false;
  const finish = (commit, move) => {
    if (done) return; done = true; const val = inp.value; inp.remove(); td.classList.remove('ing');
    if (commit && val !== raw) rCommit(k, r, c, val); else rSelect(r, c, true);
    if (move) rMove(move);
  };
  inp.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); finish(true, e.shiftKey ? 'up' : 'down'); }
    else if (e.key === 'Tab') { e.preventDefault(); finish(true, e.shiftKey ? 'left' : 'right'); }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); finish(false); }
    else if ((e.key === 'ArrowUp' || e.key === 'ArrowDown') && initial != null) { e.preventDefault(); finish(true, e.key === 'ArrowUp' ? 'up' : 'down'); }
  });
  inp.addEventListener('blur', () => finish(true));
}
function rCommit(k, r, c, val) {
  const tab = rTab(k);
  const oldRaw = c === '@RATE' ? (rRateOf(tab, r) != null ? String(+(rRateOf(tab, r) * 100).toFixed(4)) : '') : rRaw(tab, c, r);
  const oldLink = (tab.rows[r - 1] || {}).link ? JSON.parse(JSON.stringify(tab.rows[r - 1].link)) : null;
  if (c === '@RATE') {
    const s = String(val).trim().replace('%', '');
    if (s === '') rSet(tab, 'U', r, null);
    else {
      let n = parseFloat(s); if (!isFinite(n)) return toast('损耗率请填数字，例如 8 或 0.08', true);
      if (n >= 1) n = n / 100;
      rSet(tab, 'U', r, '=T' + r + '*' + (+n.toFixed(6)));
      const cu = rCell(tab, 'U', r), ct = rCell(tab, 'T', r); if (cu && !cu.s && ct && ct.s) cu.s = ct.s;
    }
  } else {
    const ln = (tab.rows[r - 1] || {}).link;
    if (k === 'ledger' && c === 'K' && ln && ln.k === 'conv' && String(val) !== String(rRaw(tab, 'K', r))) { delete tab.rows[r - 1].link; toast('这一行的出库量改成手填了，以后不再跟着换算表 ' + ln.date + ' 自动变'); }
    if (k === 'ledger' && c === 'K' && ln && ln.k === 'lox' && String(val) !== String(rRaw(tab, 'K', r))) { delete tab.rows[r - 1].link; toast('这一行的出库量改成手填了，以后不再跟着液氧表 ' + ln.date + ' 自动变'); }
    if (k === 'ledger' && c === 'I' && ln && ln.k === 'conv' && rIso(val) !== ln.date) { delete tab.rows[r - 1].link; toast('出库时间改了，不再跟着换算表 ' + ln.date + ' 自动变'); }
    rSet(tab, c, r, val);
  }
  const newLink = (tab.rows[r - 1] || {}).link ? JSON.parse(JSON.stringify(tab.rows[r - 1].link)) : null;
  if (String(oldRaw) !== String(val) || JSON.stringify(oldLink) !== JSON.stringify(newLink))
    rPushUndo({ type: 'cell', k, r, c, oldRaw, oldLink, newRaw: val, newLink });
  rDirty(k); rRender(true); rSelect(r, c, true);
}
function rMove(dir) {
  const s = RP.sel; if (!s) return; const td = rTd(s.r, s.c); if (!td) return;
  if (dir === 'left' || dir === 'right') {
    let n = dir === 'left' ? td.previousElementSibling : td.nextElementSibling;
    while (n && !n.dataset.c) n = dir === 'left' ? n.previousElementSibling : n.nextElementSibling;
    if (n) rSelect(+n.dataset.r, n.dataset.c); return;
  }
  let r = s.r; const max = rTab().rows.length + 2;
  for (let i = 0; i < 400; i++) { r += dir === 'up' ? -1 : 1; if (r < 1 || r > max) return; if (rTd(r, s.c)) { rSelect(r, s.c); return; } }
}
/* ---------- 列宽拖拽（各报表通用；写入 report_prefs.widths）
 * 双行 / 合并表头：宽度写在 <colgroup><col>，不靠第一行 colspan 的 th，否则拖不动或拖了不生效 ---------- */
let _rzSave = null;
function rAttachResize(box, k) {
  const table = box.querySelector('table.rt'); if (!table) return;
  table.style.tableLayout = 'fixed';
  // 分组表头（colspan>1）右侧也可拖：拖的是这一组合计下「最后一叶子列」
  table.querySelectorAll('thead th.grp').forEach(th => {
    if (th.querySelector('.r-rz')) return;
    const cs = th.colSpan || 1; if (cs < 1) return;
    // 找这一组在 colgroup 里对应的最后一列
    const keys = rColKeys(k);
    // 按 thead 平面列位置估算：数前面格子占的列
    let idx = 0;
    for (const cell of th.parentNode.children) {
      if (cell === th) break;
      idx += cell.colSpan || 1;
    }
    const leaf = keys[idx + cs - 1]; if (!leaf) return;
    const h = document.createElement('i'); h.className = 'r-rz'; h.dataset.rz = leaf; h.title = '拖动调节列宽'; th.appendChild(h);
  });
  // 保证每列叶子 th 与 colgroup 宽一致（双行表头对齐）
  rColKeys(k).forEach(c => {
    const col = table.querySelector(`colgroup col[data-c="${c}"]`);
    if (!col) return;
    const w = parseInt(col.style.width, 10);
    if (w) table.querySelectorAll(`thead th[data-c="${c}"]`).forEach(x => { if ((x.colSpan || 1) === 1) x.style.width = w + 'px'; });
  });
  box.querySelectorAll('i.r-rz').forEach(h => {
    h.onmousedown = e => {
      e.preventDefault(); e.stopPropagation();
      $$('.r-fpop').forEach(x => x.remove());   // 拖宽时关掉筛选弹层
      const c = h.dataset.rz; if (!c) return;
      const col = table.querySelector(`colgroup col[data-c="${c}"]`);
      const th = h.closest('th');
      const x0 = e.clientX;
      const w0 = col ? (parseInt(col.style.width, 10) || col.getBoundingClientRect().width) : (th ? th.getBoundingClientRect().width : 72);
      let cur = w0;
      const apply = w => {
        cur = w;
        if (col) col.style.width = w + 'px';
        table.querySelectorAll(`thead th[data-c="${c}"]`).forEach(x => { if ((x.colSpan || 1) === 1) x.style.width = w + 'px'; });
        // 表宽 = 所有 col 宽合计（合并表头也准）
        let tw = 0;
        table.querySelectorAll('colgroup col').forEach(x => { tw += parseInt(x.style.width, 10) || x.getBoundingClientRect().width; });
        table.style.width = Math.round(tw) + 'px';
      };
      const onMove = ev => apply(Math.max(40, Math.min(800, Math.round(w0 + ev.clientX - x0))));
      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        document.body.classList.remove('rz-on');
        rPersistWidth(k, c, cur);
        requestAnimationFrame(() => syncStickyHeads(table));
      };
      document.body.classList.add('rz-on');
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    };
  });
}
function rPersistWidth(k, c, w) {
  RP.prefs = RP.prefs || {};
  const cur = Object.assign({}, rPref(k) || {});
  cur.widths = Object.assign({}, cur.widths || {}, { [c]: w });
  RP.prefs[k] = cur;
  clearTimeout(_rzSave);
  _rzSave = setTimeout(async () => {
    try {
      const d = await save('/api/report/prefs/save', { key: k, data: cur }, '保存列宽');
      RP.prefs[k] = d.data || cur;
      // 轻提示，不打扰
      const tip = document.createElement('div'); tip.className = 'toast'; tip.textContent = '列宽已保存'; document.body.appendChild(tip); setTimeout(() => tip.remove(), 1400);
    } catch (e) { fail(e); }
  }, 500);
}

/** 把表头筛选写入 report_prefs（与「设置」同一套：from/to + filters） */
async function rPersistFilt(k, patch) {
  RP.prefs = RP.prefs || {};
  const cur = Object.assign({}, rPref(k) || {});
  if ('from' in patch) cur.from = patch.from || '';
  if ('to' in patch) cur.to = patch.to || '';
  if (patch.clearCol) {
    cur.filters = (cur.filters || []).filter(f => f.c !== patch.clearCol);
  }
  if (patch.setFilt) {
    const { c, q } = patch.setFilt;
    let fl = (cur.filters || []).filter(f => f.c !== c);
    if (q) fl = fl.concat([{ c, q: String(q).slice(0, 40) }]).slice(0, 5);
    cur.filters = fl;
  }
  // 保留列显示相关字段
  const d = {
    hidden: cur.hidden || [], order: cur.order || [], labels: cur.labels || {},
    from: cur.from || '', to: cur.to || '', filters: cur.filters || [],
    widths: cur.widths || {}
  };
  RP.prefs[k] = d;
  if (RP.prefsOff) delete RP.prefsOff[k];
  const saved = await save('/api/report/prefs/save', { key: k, data: d }, '保存筛选');
  let out = saved.data || d;
  // 服务端未重启时旧代码会丢掉 @u8：本会话先保留，重启后即可持久化
  const sentU8 = (d.filters || []).find(f => f.c === '@u8');
  if (sentU8 && !(out.filters || []).some(f => f.c === '@u8')) {
    out = Object.assign({}, out, { filters: (out.filters || []).concat([sentU8]) });
  }
  RP.prefs[k] = out;
  rRender(true);
}

/** 表头 ▾ 弹出筛选（库存及到货总数） */
function rFilterPop(k, c, btn) {
  $$('.r-fpop').forEach(x => x.remove());
  const p = rPref(k) || {}, isDate = c === rDateCol(k), isU8 = c === '@u8';
  const lab = c === '@u8' ? 'U8' : (rLabel(k, c) || c);
  const pop = document.createElement('div'); pop.className = 'r-fpop';
  let body = `<div class="r-fpop-h">筛选 · ${esc(lab)}</div>`;
  if (isDate) {
    body += `<div class="row r2"><div><span class="lab">从</span><input class="inp sm" type="date" id="rfFrom" value="${esc(p.from || '')}"></div>
      <div><span class="lab">到</span><input class="inp sm" type="date" id="rfTo" value="${esc(p.to || '')}"></div></div>
      <div class="hint" style="margin-top:6px">按日期列；也可在「设置」里改。清空起止即取消日期筛选。</div>`;
  } else if (isU8) {
    const cur = ((p.filters || []).find(f => f.c === '@u8') || {}).q || '';
    const opts = [['', '全部'], ['待入U8', '待入U8'], ['已入U8', '已入U8'], ['不用入U8', '不用入U8']];
    body += `<div class="r-fpop-u8">${opts.map(([v, t]) => `<button type="button" class="btn sm${cur === v ? ' pri' : ''}" data-u8q="${esc(v)}">${t}</button>`).join('')}</div>`;
  } else {
    const cur = ((p.filters || []).find(f => f.c === c) || {}).q || '';
    body += `<input class="inp" id="rfQ" value="${esc(cur)}" placeholder="包含…" style="width:100%">
      <div class="hint" style="margin-top:6px">不区分大小写；空 = 取消本列筛选。与「设置 → 默认筛选」共用。</div>`;
  }
  body += `<div class="r-fpop-acts"><button type="button" class="btn sm" data-clr>清除</button><button type="button" class="btn sm pri" data-ok>应用</button></div>`;
  pop.innerHTML = body;
  document.body.appendChild(pop);
  const br = btn.getBoundingClientRect();
  const pw = Math.min(300, Math.max(240, pop.offsetWidth || 260));
  const ph = pop.offsetHeight || 160;
  let left = Math.min(Math.max(8, br.left), innerWidth - pw - 8);
  let top = br.bottom + 4;
  if (top + ph > innerHeight - 8) top = Math.max(8, br.top - ph - 4);
  pop.style.left = left + 'px';
  pop.style.top = top + 'px';
  const grid = btn.closest('.r-grid') || $('#rGrid');
  const close = () => {
    pop.remove();
    document.removeEventListener('mousedown', onDoc);
    if (grid) grid.removeEventListener('scroll', onScroll);
    window.removeEventListener('resize', onScroll);
  };
  const onDoc = ev => { if (!pop.contains(ev.target) && ev.target !== btn && !btn.contains(ev.target)) close(); };
  const onScroll = () => close();   // 表体滚动 / 窗口变化时关掉，避免弹层悬空错位
  setTimeout(() => {
    document.addEventListener('mousedown', onDoc);
    if (grid) grid.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
  }, 0);
  const apply = async (patch) => { try { close(); await rPersistFilt(k, patch); toast('筛选已保存'); } catch (e) { fail(e); } };
  pop.onclick = ev => {
    const u = ev.target.closest('[data-u8q]');
    if (u) { apply({ setFilt: { c: '@u8', q: u.dataset.u8q } }); return; }
    if (ev.target.closest('[data-clr]')) {
      if (isDate) apply({ from: '', to: '' });
      else apply({ clearCol: c });
      return;
    }
    if (ev.target.closest('[data-ok]')) {
      if (isDate) apply({ from: $('#rfFrom', pop).value, to: $('#rfTo', pop).value });
      else if (!isU8) apply({ setFilt: { c, q: ($('#rfQ', pop).value || '').trim() } });
      else close();
    }
  };
  const inp = $('#rfQ', pop) || $('#rfFrom', pop);
  if (inp) setTimeout(() => inp.focus(), 30);
}

/** 库存及到货总数：点 U8 标签改状态（含「不用入U8」） */
function rU8Menu(e, id, cur) {
  e.preventDefault(); e.stopPropagation();
  $$('.r-u8pop').forEach(x => x.remove());
  const pop = document.createElement('div'); pop.className = 'r-u8pop';
  const opts = [['待入U8', '待入U8'], ['已入U8', '已入U8'], ['不入U8', '不用入U8']];
  pop.innerHTML = opts.map(([st, lab]) => `<button type="button" class="btn sm${cur === st ? ' pri' : ''}" data-st="${st}">${lab}</button>`).join('');
  document.body.appendChild(pop);
  const r = e.target.getBoundingClientRect();
  pop.style.left = Math.min(r.left, innerWidth - 200) + 'px';
  pop.style.top = Math.min(r.bottom + 4, innerHeight - 80) + 'px';
  const close = () => { pop.remove(); document.removeEventListener('mousedown', onDoc); };
  const onDoc = ev => { if (!pop.contains(ev.target)) close(); };
  setTimeout(() => document.addEventListener('mousedown', onDoc), 0);
  pop.onclick = async ev => {
    const b = ev.target.closest('[data-st]'); if (!b) return;
    const st = b.dataset.st; close();
    if (st === cur) return;
    try {
      if (st === '已入U8') {
        // 需要时可填存货号/入库单号；也可直接标
        const a = await api('/api/arrival/one?id=' + id);
        const ov = dialog('标记已入U8', `<div class="row r2"><div><span class="lab">存货号</span><input class="inp" id="suInv" value="${esc(a.inv_code || '')}"></div>
          <div><span class="lab">入库单号</span><input class="inp" id="suNo" value="${esc(a.receipt_no || '')}"></div></div>
          <div class="hint">可空，只改状态也可以。</div>`,
          [{ t: '取消' }, { t: '标记已入U8', cls: 'pri', fn: async ov2 => {
            await save('/api/arrival/u8', { items: [{ id, u8_status: '已入U8', inv_code: $('#suInv', ov2).value.trim(), receipt_no: $('#suNo', ov2).value.trim() }] }, '标记已入U8');
            await rLoad('stock'); rRender(true); toast('已标记已入U8');
          } }]);
        return;
      }
      await save('/api/arrival/u8', { items: [{ id, u8_status: st }] }, st === '不入U8' ? '标记不用入U8' : '改回待入U8');
      await rLoad('stock'); rRender(true);
      toast(st === '不入U8' ? '已标记不用入U8' : '已改回待入U8');
    } catch (er) { fail(er); }
  };
}

function rBind() {

  if (window._rBound) return; window._rBound = true;
  document.addEventListener('click', e => {
    if (App.cur !== 'report') return;
    if (!e.target.closest('.r-more')) $$('.r-more.on').forEach(m => m.classList.remove('on'));
    const g = e.target.closest('#rGrid'); if (!g) return;
    const t = e.target, k = RP.k;
    if (t.dataset.push) return rPush(+t.dataset.push);
    if (t.dataset.src) return rOpenSrc(k, +t.dataset.src);
    if (t.dataset.lnk) return rLinkConv(+t.dataset.lnk);
    if (t.dataset.lxlnk) return rLoxLinkDlg(+t.dataset.lxlnk);
    if (t.dataset.lxgo) { const lk = rLoxLinked(rTab('lox').rows[+t.dataset.lxgo - 1].lx); RP.k = 'ledger'; rRender(); requestAnimationFrame(() => rSelect(lk[0], 'K')); return; }
    if (t.dataset.lxin) return rLoxInLinkDlg(+t.dataset.lxin);
    if (t.dataset.lxingo) { const lk = rLoxInLinked(rTab('lox').rows[+t.dataset.lxingo - 1].lx); RP.k = 'ledger'; rRender(); requestAnimationFrame(() => rSelect(lk[0], 'B')); return; }
    if (t.dataset.rec) { const [e, i] = t.dataset.rec.split(':'); return recView(e, +i); }
    if (t.dataset.ins) return rInsertBelow(k, +t.dataset.ins);
    if (t.dataset.del) return rDelRow(k, +t.dataset.del);
    if (t.dataset.att) return rShowAtt(k, +t.dataset.att);
    if (t.dataset.addatt) return rAddAtt(k, +t.dataset.addatt);
    if (t.dataset.arph) return api('/api/arrival/one?id=' + t.dataset.arph).then(a => dialog('到货照片 · ' + a.name + ' ' + a.spec, `<div class="photos">${a.photos.map(p => `<img class="ph-i" src="/photos/${esc(p.path)}" onclick="bigImg(this.src)">`).join('')}</div>`)).catch(fail);
    if (t.dataset.u8menu || t.closest('[data-u8menu]')) { const el = t.dataset.u8menu ? t : t.closest('[data-u8menu]'); return rU8Menu(e, +el.dataset.u8menu, el.dataset.u8cur); }
    if (t.closest('.r-rz')) return;
    const ff = t.closest('[data-ff]'); if (ff) { e.preventDefault(); e.stopPropagation(); return rFilterPop(k, ff.dataset.ff, ff); }
    if (typeof CellSel !== 'undefined' && CellSel.consumeClick()) return;
    const td = t.closest('td[data-c]'); if (td && !t.closest('input,button,a,.r-u8tag')) rSelect(+td.dataset.r, td.dataset.c);
  });
  document.addEventListener('dblclick', e => { if (App.cur !== 'report') return; const td = e.target.closest('#rGrid td[data-c]'); if (td && !e.target.closest('button,a')) rStartEdit(td); });
  document.addEventListener('keydown', e => {
    if (App.cur !== 'report' || document.querySelector('.ov')) return;
    if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); if (Object.keys(RP.dirty).length) rSaveTabs(Object.keys(RP.dirty), '修改').catch(fail); return; }
    const a = document.activeElement; if (a && ['INPUT', 'TEXTAREA', 'SELECT'].includes(a.tagName)) return;   // 编辑中 Ctrl+Z 用输入框自带撤销
    if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z') && !e.shiftKey) { e.preventDefault(); rUndo(); return; }
    if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || e.key === 'Y' || ((e.key === 'z' || e.key === 'Z') && e.shiftKey))) { e.preventDefault(); rRedo(); return; }
    const s = RP.sel; if (!s || s.k !== RP.k) return; const td = rTd(s.r, s.c); if (!td) return;
    if (e.key.startsWith('Arrow')) {
      e.preventDefault();
      if (e.shiftKey && typeof CellSel !== 'undefined') {
        const dir = e.key.slice(5).toLowerCase();
        // 先按方向找到邻居，再扩展选区（锚点保持）
        const cur = td; let n = null;
        if (dir === 'left' || dir === 'right') {
          n = dir === 'left' ? cur.previousElementSibling : cur.nextElementSibling;
          while (n && !n.dataset.c) n = dir === 'left' ? n.previousElementSibling : n.nextElementSibling;
        } else {
          let r = s.r; const max = rTab().rows.length + 2;
          for (let i = 0; i < 400; i++) { r += dir === 'up' ? -1 : 1; if (r < 1 || r > max) break; n = rTd(r, s.c); if (n) break; }
        }
        if (n) {
          CellSel.extendTo(n.closest('table'), n);
          $$('#rGrid td.sel').forEach(x => x.classList.remove('sel'));
          n.classList.add('sel'); RP.sel = { k: RP.k, r: +n.dataset.r, c: n.dataset.c };
          gridFocus(n.closest('table'), n);
        }
      } else rMove(e.key.slice(5).toLowerCase());
    }
    else if (e.key === 'Enter' || e.key === 'F2') { e.preventDefault(); rStartEdit(td); }
    else if (e.key === 'Tab') { e.preventDefault(); rMove(e.shiftKey ? 'left' : 'right'); }
    else if ((e.key === 'Delete' || e.key === 'Backspace') && (s.c === '@RATE' || !rIsRO(RP.k, s.r, s.c))) { e.preventDefault(); rCommit(RP.k, s.r, s.c, ''); }
    else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); rStartEdit(td, e.key); }
  });
}

/* ---------- 新增 / 删除行 ---------- */
function rCopyStyles(tab, fromR, toR) {
  const src = tab.rows[fromR - 1], dst = rRow(tab, toR); if (!src) return;
  Object.keys(src.c).forEach(c => { if (src.c[c] && src.c[c].s) { const d = dst.c[c] || (dst.c[c] = {}); d.s = src.c[c].s; } });
  if (src.ra && !dst.ra) dst.ra = src.ra;
}
/** 新行位置：主数据区后第一行；紧挨着下方旧数据区就插入一行（旧数据整体下移，公式和合并同步调整） */
function rNewRowAt(k) {
  const tab = rTab(k), rg = rRanges(k), r = rg.mainEnd + 1;
  if ((rg.tailStart && r >= rg.tailStart - 1) || rHasVal(tab, r, k === 'ledger' ? ['B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N'] : null)) { O2.insertRow(tab, r, { c: {} }); return r; }
  rRow(tab, r); return r;
}
function rConvFormulas(tab, r, rate) {
  rSet(tab, 'G', r, '=(B' + r + '*5+D' + r + '*1.25+E' + r + '*0.25)*1.141/800');
  rSet(tab, 'S', r, '=(H' + r + '*20+I' + r + '*25+J' + r + '*30+K' + r + '*35+L' + r + '*80+M' + r + '*100+N' + r + '*175+O' + r + '*195+P' + r + '*210+Q' + r + '*500+R' + r + '*1000)*1.141/1000');
  rSet(tab, 'T', r, '=G' + r + '+S' + r); rSet(tab, 'U', r, '=T' + r + '*' + rate); rSet(tab, 'V', r, '=T' + r + '+U' + r);
}
/** 换算表某天在第几行（只看主数据区） */
function rConvRowOf(iso) { const tab = rTab('conv'), rg = rRanges('conv'); for (let r = rg.start; r <= rg.mainEnd; r++) if (rIso(rRaw(tab, 'A', r)) === iso) return r; return null; }
function rAddConvRow(date, vals) {
  const tab = rTab('conv'), rg = rRanges('conv'), lastR = rg.mainEnd;
  date = date || rNextDate(rRaw(tab, 'A', lastR)); const iso = rIso(date);
  // 按日期插到正确的位置（补以前某天也行）；放在最后就用原来的方式接在后面
  let at = null; for (let x = rg.start; x <= rg.mainEnd; x++) { const d = rIso(rRaw(tab, 'A', x)); if (d && iso && d > iso) { at = x; break; } }
  let r, prev;
  if (at) { O2.insertRow(tab, at, { c: {} }); r = at; prev = at - 1 >= rg.start ? at - 1 : at + 1; }
  else { r = rNewRowAt('conv'); prev = lastR; }
  rCopyStyles(tab, prev, r);
  const rate = rRateOf(tab, prev) != null ? rRateOf(tab, prev) : (((S.boot.settings.ocr || {}).default_rate ?? 8) / 100);
  // 新行一律从空白开始：不沿用这一格原来残留的数（以前「识别」时 10L 会带出旧值）
  const row = rRow(tab, r); Object.keys(row.c).forEach(c => { if (row.c[c]) { delete row.c[c].v; delete row.c[c].f; } }); delete row.att; delete row.link;
  rSet(tab, 'A', r, date); rConvFormulas(tab, r, rate);
  const w = rRaw(tab, 'W', prev); if (w !== '' && !String(w).startsWith('=')) rSet(tab, 'W', r, w);
  Object.keys(vals || {}).forEach(c => { if (vals[c] !== '' && vals[c] != null) rSet(tab, c, r, vals[c]); });
  return r;
}
/** 入出库记录里出现过的「当前批次」(M)，新在前 */
function rLedgerBatches() {
  const tab = rTab('ledger'), rg = rRanges('ledger'), out = [], seen = new Set();
  for (let r = rg.mainEnd; r >= rg.start; r--) {
    const m = rLedgerNormBatch(rRaw(tab, 'M', r));
    if (m && !seen.has(m)) { seen.add(m); out.push(m); }
    if (out.length >= 24) break;
  }
  return out;
}
/** 按出库日期插进去时，上一行是谁 → 默认用它的批次 */
function rLedgerPrevAtDate(date) {
  const tab = rTab('ledger'), rg = rRanges('ledger'), iso = rIso(date);
  let prev = 0;
  for (let x = rg.start; x <= rg.mainEnd; x++) {
    const d = rIso(rRaw(tab, 'I', x));
    if (d && iso && d > iso) break;
    prev = x;
  }
  return prev || rg.mainEnd;
}
/** 新增出库行：按出库日期 (I) 插到正确位置（不是永远加在最后）；批次剩余链接好；可指定批次 (M) */
function rAddLedgerRow(o) {
  o = o || {}; const tab = rTab('ledger'), rg = rRanges('ledger'), lastR = rg.mainEnd;
  const date = o.date || rNextDate(rRaw(tab, 'I', lastR));
  const iso = rIso(date);
  let at = null;
  if (iso) {
    for (let x = rg.start; x <= rg.mainEnd; x++) {
      const d = rIso(rRaw(tab, 'I', x));
      if (d && d > iso) { at = x; break; }
    }
  }
  let r, prev;
  if (at) { O2.insertRow(tab, at, { c: {} }); r = at; prev = at - 1 >= rg.start ? at - 1 : at + 1; }
  else { r = rNewRowAt('ledger'); prev = lastR; }
  rCopyStyles(tab, prev, r);
  const row = rRow(tab, r);
  Object.keys(row.c || {}).forEach(c => { if (row.c[c]) { delete row.c[c].v; delete row.c[c].f; } });
  delete row.att; delete row.link;
  if (rRaw(tab, 'A', r) === '') { const pa = rRaw(tab, 'A', prev); if (typeof pa === 'number') rSet(tab, 'A', r, pa + 1); }
  rSet(tab, 'I', r, date); rSet(tab, 'J', r, o.to || '出本库');
  const batch = o.batch !== undefined ? o.batch : rRaw(tab, 'M', prev);
  const prevL = rEval('ledger').val('L', prev);
  const qty = o.qty;
  // nextBatch：旧批不够或已为负时，按历史「剩余+新取」写；剩余按 max(0,prevL)，禁止再扣成负
  if (o.nextBatch && typeof qty === 'number' && (typeof prevL !== 'number' || prevL < -1e-9 || qty > prevL + 1e-9)) {
    const rem = typeof prevL === 'number' ? Math.max(0, Math.round(prevL * 100) / 100) : 0;
    const take = Math.round((qty - rem) * 100) / 100;
    const newRemain = (o.newInbound != null && isFinite(o.newInbound)) ? Math.round((o.newInbound - take) * 100) / 100 : null;
    rLedgerTwoBatchWrite(r, rem, take, batch, o.nextBatch, newRemain);
    // 有新批剩余数字就保留；未知则 L 已留空。下行公式若指向本行，仍接上
    const nxt = rCell(tab, 'L', r + 1);
    if (nxt && nxt.f && nxt.f.replace(/\s/g, '').replace(/\$/g, '') === 'L' + prev + '-K' + (r + 1))
      rSet(tab, 'L', r + 1, '=L' + r + '-K' + (r + 1));
  } else {

    if (o.qty != null) rSet(tab, 'K', r, o.qty);
    rSet(tab, 'L', r, '=L' + prev + '-K' + r);
    if (batch !== '' && batch != null) rSet(tab, 'M', r, batch);
    else { const cell = rCell(tab, 'M', r); if (cell) { delete cell.v; delete cell.f; } }
    rLedgerRewireL(tab, r);
  }
  if (o.link) rRow(tab, r).link = o.link; else delete rRow(tab, r).link;
  return r;
}
function rLastDataRow(k) { const tab = rTab(k); for (let r = tab.rows.length; r >= 1; r--) if (rHasVal(tab, r, ['A', 'B', 'C', 'D', 'E'])) return r; return RT[k].start; }
function rAppendRow(k, afterR) {
  const tab = rTab(k), rg = rRanges(k); let r;
  if (afterR) { r = afterR + 1; O2.insertRow(tab, r, { c: {} }); rCopyStyles(tab, afterR, r); }
  else { const src = rLastDataRow(k); r = rg.last + 1; rRow(tab, r); rCopyStyles(tab, src, r); }
  return r;
}
async function rAdd() {
  const k = RP.k;
  if (k === 'stock') { location.hash = 'arrival'; return; }
  if (k === 'lox') return rDelivery();
  let r, c = 'B';
  if (k === 'conv') return rConvAddDlg();
  else if (k === 'ledger') { r = rAddLedgerRow(); c = 'K'; }
  else { r = rAppendRow(k); rSet(rTab(k), 'A', r, rToday()); }
  rDirty(k); rRender(true);
  rFocusNew(k, r, c);
  toast('已新增第 ' + r + ' 行，填好后点「保存」');
}
/** 新行：滚到看得见、选中第一格、闪一下 */
function rFocusNew(k, r, c) {
  requestAnimationFrame(() => {
    const tr = $(`#rGrid tr[data-r="${r}"]`); if (!tr) return;
    rSelect(r, c || RT[k].sticky || 'A');
    tr.classList.add('r-new'); setTimeout(() => tr.classList.remove('r-new'), 1600);
    const box = $('#rGrid'), tb = tr.getBoundingClientRect(), bb = box.getBoundingClientRect();
    if (tb.top < bb.top || tb.bottom > bb.bottom) box.scrollTop += tb.top - bb.top - bb.height / 2;
    const vr = box.getBoundingClientRect(), pr = tr.getBoundingClientRect();
    if (pr.top < 0 || pr.bottom > innerHeight) tr.scrollIntoView({ block: 'center' });
  });
}
function rKeep(k, r) { RP.keepTo = RP.keepTo || {}; RP.keepTo[k] = Math.max(RP.keepTo[k] || 0, r); }
/** 入出库记录批次剩余链：本行 = 上一行剩余 − 本行出库；插入/恢复后接好本行和下一行（与回收站 restore、删除对称） */
function rLedgerRewireL(tab, at) {
  rSet(tab, 'L', at, '=L' + (at - 1) + '-K' + at);
  const nxt = rCell(tab, 'L', at + 1);
  if (nxt && nxt.f && nxt.f.replace(/\s/g, '').replace(/\$/g, '') === 'L' + (at - 1) + '-K' + (at + 1))
    rSet(tab, 'L', at + 1, '=L' + at + '-K' + (at + 1));
}
function rPushUndo(entry) {
  RP.undo.push(entry);
  if (RP.undo.length > 80) RP.undo.shift();
  RP.redo = [];
}
function rApplyCellSnap(k, r, c, raw, link) {
  const tab = rTab(k); if (!tab) return;
  if (c === '@RATE') {
    if (raw === '' || raw == null) rSet(tab, 'U', r, null);
    else {
      let n = parseFloat(String(raw).trim().replace('%', '')); if (!isFinite(n)) return;
      if (n >= 1) n = n / 100;
      rSet(tab, 'U', r, '=T' + r + '*' + (+n.toFixed(6)));
    }
  } else rSet(tab, c, r, raw === '' || raw == null ? null : raw);
  const row = tab.rows[r - 1];
  if (row) { if (link) row.link = JSON.parse(JSON.stringify(link)); else delete row.link; }
}
async function rUndo() {
  const e = RP.undo.pop(); if (!e) return toast('没有可撤销的操作');
  if (e.type === 'cell') {
    rApplyCellSnap(e.k, e.r, e.c, e.oldRaw, e.oldLink);
    RP.redo.push(e);
    rDirty(e.k); rRender(true); if (RP.k === e.k) rSelect(e.r, e.c === '@RATE' ? 'U' : e.c, true);
    toast('已撤销'); return;
  }
  if (e.type === 'ins') {
    const tab = rTab(e.k); if (!tab) return;
    const nr = e.r;
    const nxt = rCell(tab, 'L', nr + 1);
    const fix = e.k === 'ledger' && nxt && nxt.f && nxt.f.replace(/\s/g, '') === 'L' + nr + '-K' + (nr + 1);
    O2.deleteRow(tab, nr);
    if (RP.keepTo && RP.keepTo[e.k] >= nr) RP.keepTo[e.k]--;
    if (fix) rSet(tab, 'L', nr, '=L' + (nr - 1) + '-K' + nr);
    RP.redo.push(e);
    rDirty(e.k); rRender(true); if (RP.k === e.k) rSelect(Math.max(nr - 1, RT[e.k].start), RT[e.k].sticky || 'A', true);
    toast('已撤销插入'); return;
  }
  if (e.type === 'del') {
    // 按删除的逆序插回（删除时先删大行号）
    const items = e.items.slice().reverse();
    items.forEach(it => {
      const tab = rTab(it.key); if (!tab) return;
      O2.insertRow(tab, it.r, { c: {} });
      tab.rows[it.r - 1] = JSON.parse(JSON.stringify(it.row));
      rKeep(it.key, it.r); rDirty(it.key);
    });
    RP.redo.push(e);
    const keys = [...new Set(e.items.map(x => x.key))];
    rRender(true);
    const focus = e.items[e.items.length - 1];
    if (focus) { RP.k = focus.key; rRender(true); requestAnimationFrame(() => rSelect(focus.r, RT[focus.key].sticky || 'A', true)); }
    try {
      await rSaveTabs(keys, '撤销删除' + keys.map(k => RT[k].short).join('、'), null, true);
      toast('已撤销删除');
    } catch (err) { toast('已恢复到表格，请点保存写回', true); }
    return;
  }
}
async function rRedo() {
  const e = RP.redo.pop(); if (!e) return toast('没有可重做的操作');
  if (e.type === 'cell') {
    rApplyCellSnap(e.k, e.r, e.c, e.newRaw, e.newLink);
    RP.undo.push(e);
    rDirty(e.k); rRender(true); if (RP.k === e.k) rSelect(e.r, e.c === '@RATE' ? 'U' : e.c, true);
    toast('已重做'); return;
  }
  if (e.type === 'ins') {
    const tab = rTab(e.k); O2.insertRow(tab, e.r, { c: {} }); rCopyStyles(tab, e.r - 1, e.r);
    if (e.k === 'ledger') rLedgerRewireL(tab, e.r);
    rKeep(e.k, e.r); RP.undo.push(e); rDirty(e.k); rRender(true); rFocusNew(e.k, e.r);
    toast('已重做插入'); return;
  }
  if (e.type === 'del') {
    RP.trash = RP.trash || [];
    e.items.forEach(it => {
      const t = rTab(it.key); if (!t) return;
      RP.trash.push({ key: it.key, r: it.r, row: JSON.parse(JSON.stringify(t.rows[it.r - 1] || { c: {} })) });
      const nxt = rCell(t, 'L', it.r + 1);
      const fix = it.key === 'ledger' && nxt && nxt.f && nxt.f.replace(/\s/g, '') === 'L' + it.r + '-K' + (it.r + 1);
      O2.deleteRow(t, it.r);
      if (RP.keepTo && RP.keepTo[it.key] >= it.r) RP.keepTo[it.key]--;
      if (fix) rSet(t, 'L', it.r, '=L' + (it.r - 1) + '-K' + it.r);
      rDirty(it.key);
    });
    RP.undo.push(e);
    const keys = [...new Set(e.items.map(x => x.key))];
    rRender(true);
    try {
      await rSaveTabs(keys, '重做删除' + keys.map(k => RT[k].short).join('、'), null, true);
      toast('已重做删除');
    } catch (err) { toast('已删掉，请点保存写回', true); }
    return;
  }
}
function rInsertBelow(k, r) {
  const nr = rAppendRow(k, r);
  if (k === 'ledger') rLedgerRewireL(rTab(k), nr);
  rPushUndo({ type: 'ins', k, r: nr });
  rKeep(k, nr); rDirty(k); rRender(true); rFocusNew(k, nr, k === 'ledger' ? 'B' : null);
  toast('已在第 ' + r + ' 行下方插入一行，填好后点「保存」');
}

async function rDelRow(k, r) {
  const tab = rTab(k);
  const desc = [rRaw(tab, 'A', r), rRaw(tab, 'B', r), rRaw(tab, k === 'ledger' ? 'I' : 'C', r), rRaw(tab, k === 'ledger' ? 'K' : 'E', r)].filter(x => x !== '').join('  ');
  const n = ((tab.rows[r - 1] || {}).att || []).length;
  // 会影响到哪些：换算表 → 入出库记录（出库量、之后每行的批次剩余）；入出库记录 → 之后每行的批次剩余
  const eff = []; let linked = [];
  if (k === 'conv') {
    const iso = rIso(rRaw(tab, 'A', r)), v = rEval('conv').val('V', r);
    if (typeof v === 'number') eff.push(`本月累计、当天总计 ${v.toFixed(2)} 吨`);
    await rEnsure('ledger'); const lt = rTab('ledger');
    linked = lt.rows.map((x, i) => x && x.link && x.link.k === 'conv' && x.link.date === iso ? i + 1 : 0).filter(Boolean);
    lt.rows.forEach((x, i) => { const rr = i + 1; if (x && !x.link && rIso(rRaw(lt, 'I', rr)) === iso && /本库/.test(String(rRaw(lt, 'J', rr)))) eff.push(`「液态氧原料入出库记录」第 ${rr} 行也是这天出本库（${esc(rFmt(rEval('ledger').val('K', rr)))} 吨，手填的，不会跟着变，请自己核对）`); });
    linked.forEach(x => eff.push(`「液态氧原料入出库记录」第 ${x} 行（${esc(rRaw(lt, 'I', x))} ${esc(rRaw(lt, 'J', x))} ${esc(rFmt(rEval('ledger').val('K', x)))} 吨）以及它下面每一行的「批次剩余」`));
  }
  if (k === 'lox' && tab.rows[r - 1] && tab.rows[r - 1].lx) {
    await rEnsure('ledger'); const lt = rTab('ledger'); const id = tab.rows[r - 1].lx;
    linked = rLoxLinked(id).concat(rLoxInLinked(id));
    rLoxLinked(id).forEach(x => eff.push(`「液态氧原料入出库记录」第 ${x} 行出库（${esc(rRaw(lt, 'I', x))} ${esc(rRaw(lt, 'J', x))} ${esc(rFmt(rEval('ledger').val('K', x)))} 吨）以及下面「批次剩余」`));
    rLoxInLinked(id).forEach(x => eff.push(`「液态氧原料入出库记录」第 ${x} 行左侧入库（批次 ${esc(rRaw(lt, 'B', x))} ${esc(rRaw(lt, 'E', x))} ${esc(rFmt(rRaw(lt, 'F', x)))} 吨）`));
  }
  if (k === 'ledger') { const rg = rRanges('ledger'), ln = tab.rows[r - 1] && tab.rows[r - 1].link; if (r < rg.mainEnd) eff.push(`下面第 ${r + 1}–${rg.mainEnd} 行的「批次剩余」会重算`); if (ln) eff.push(ln.k === 'lox' ? '这一行来自液氧表 ' + esc(ln.date) + ' 卸' + esc(ln.place) + '（液氧表那一行不受影响）' : ln.k === 'lox_in' ? '这一行左侧入库来自液氧表质检U8（液氧表那一行不受影响）' : '这一行来自换算表 ' + esc(ln.date) + '（换算表那一行不受影响）'); }
  if (n) eff.push('该行的 ' + n + ' 张照片');
  const html = `<div>删除第 ${r} 行：<b>${esc(desc || '（空行）')}</b></div>
    ${eff.length ? `<div class="banner" style="margin-top:8px">会影响：<ul style="margin:6px 0 0 18px">${eff.map(x => '<li>' + x + '</li>').join('')}</ul></div>` : ''}
    ${linked.length ? `<label style="display:block;margin-top:8px"><input type="checkbox" id="dlLinked" checked> 同时删除「液态氧原料入出库记录」里对应的 ${linked.length} 行</label>` : ''}
    <div class="muted" style="margin-top:8px">确定后马上保存（需要密码），这张表还没保存的修改也一起保存。删掉的行进「数据备份 → 回收站」，可以恢复。</div>`;
  const ok = await new Promise(res => dialog('确认删除', html, [{ t: '取消', fn: () => res(null) }, { t: '删除并保存', cls: 'pri', fn: ov => res({ alsoLinked: !!($('#dlLinked', ov) || {}).checked }) }]));
  if (!ok) return;
  RP.trash = RP.trash || [];
  const keys = [k];
  const deleted = [];
  let saved = false;
  await rAtomic(k === 'conv' || (k === 'lox' && linked.length) ? [k, 'ledger'] : [k], async () => {
    const del = (kk, rr) => {
      const t = rTab(kk);
      const rowSnap = JSON.parse(JSON.stringify(t.rows[rr - 1] || { c: {} }));
      deleted.push({ key: kk, r: rr, row: rowSnap });
      RP.trash.push({ key: kk, r: rr, row: rowSnap });
      const nxt = rCell(t, 'L', rr + 1);
      const fix = kk === 'ledger' && nxt && nxt.f && nxt.f.replace(/\s/g, '') === 'L' + rr + '-K' + (rr + 1);
      O2.deleteRow(t, rr);
      if (RP.keepTo && RP.keepTo[kk] >= rr) RP.keepTo[kk]--;   // 刚插入的空行被删掉：不再强制显示
      if (fix) rSet(t, 'L', rr, '=L' + (rr - 1) + '-K' + rr);
      rDirty(kk);
    };
    if ((k === 'conv' || k === 'lox') && ok.alsoLinked && linked.length) { linked.slice().sort((a, b) => b - a).forEach(x => del('ledger', x)); keys.push('ledger'); }
    del(k, r);
    await rSaveTabs(keys, '删除' + RT[k].short + '第 ' + r + ' 行', null, true);
    saved = true;
  }).catch(e => { RP.trash = (RP.trash || []).filter(x => !keys.includes(x.key)); if (e.message !== 'cancel') fail(e); });
  if (saved && deleted.length) {
    const ks = [...new Set(deleted.map(d => d.key))];
    RP.undo = RP.undo.filter(x => x.type === 'del' ? !x.items.some(it => ks.includes(it.key)) : !ks.includes(x.k));
    RP.redo = RP.redo.filter(x => x.type === 'del' ? !x.items.some(it => ks.includes(it.key)) : !ks.includes(x.k));
    rPushUndo({ type: 'del', items: deleted });
    toast('已删除。Ctrl+Z 可撤销');
  }
  rRender(true);
}

async function rLinkConv(r) {
  const lt = rTab('ledger'), iso = rIso(rRaw(lt, 'I', r)), cr = rConvRowOf(iso), v = rEval('conv').val('V', cr), old = rEval('ledger').val('K', r);
  if (!await confirmBox(`第 ${r} 行（${esc(rRaw(lt, 'I', r))} 出本库）接上换算表 ${esc(rFromIso(iso))}？<br>出库量 ${esc(rFmt(old))} → <b>${typeof v === 'number' ? v.toFixed(2) : '?'}</b>，下面每行的批次剩余跟着重算；以后改换算表这天，这里自动跟着变。`, '接上并保存')) return;
  await rAtomic(['ledger'], async () => { rRow(lt, r).link = { k: 'conv', date: iso }; rDirty('ledger'); await rSaveTabs(['ledger'], '入出库记录第 ' + r + ' 行接上换算表 ' + rFromIso(iso), null, true); }).catch(fail);
  rRender(true);
}
/** 报表行 → 它的来源（换算表那天 / 称重单） */
async function rOpenSrc(k, r) {
  const ln = (rTab(k).rows[r - 1] || {}).link; if (!ln) return;
  if (ln.k === 'conv') { await rEnsure('conv'); const x = rConvRowOf(ln.date); if (!x) return toast('换算表里已经没有 ' + ln.date + ' 这一天了（可能被删除，可在回收站恢复）', true); RP.k = 'conv'; rRender(); requestAnimationFrame(() => rSelect(x, 'V')); return; }
  if (ln.k === 'lox' || ln.k === 'lox_in') { await rEnsure('lox'); const x = rTab('lox').rows.findIndex(y => y && y.lx === ln.id) + 1; if (!x) return toast('液氧表里已经没有这车了（可能被删除，可在回收站恢复）', true); RP.k = 'lox'; rRender(); requestAnimationFrame(() => rSelect(x, ln.k === 'lox_in' ? 'G' : 'E')); return; }
  if (ln.k === 'slip') { for (const id of ln.ids) await recView('slip', id); }
}

/* ---------- 换算表：手动新增一天（不用识别；可补以前的日子；回收站里有这天时可直接恢复） ---------- */
async function rConvAddDlg(preset) {
  const tab = rTab('conv'), rg = rRanges('conv');
  const def = rIso(rNextDate(rRaw(tab, 'A', rg.mainEnd)));
  const cell = c => `<div class="oc"><span class="lab">${esc(rHeadLabel('conv', c))}</span><input class="inp sm num" data-c="${c}" autocomplete="off" value=""></div>`;
  const ov = dialog('换算表 · 新增一天', `<div class="row r2"><div><span class="lab">日期</span><input class="inp" type="date" id="caD" value="${esc((preset && preset.date) || def)}"></div><div id="caNote" style="align-self:end"></div></div>
    <div class="lab">气态（个）</div><div class="oc-g">${['B', 'C', 'D', 'E', 'F'].map(cell).join('')}</div>
    <div class="lab" style="margin-top:10px">液态（个） <span class="muted">液态10L按0.5个20L填</span></div><div class="oc-g">${['H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R'].map(cell).join('')}</div>
    <div class="hint">合计、损耗、总计自动算；损耗率沿用前一天。补以前的日子会按日期插到对应位置。</div>`,
    [{ t: '取消' }, { t: '保存', cls: 'pri', fn: async ov => {
      const iso = $('#caD', ov).value; if (!iso) { toast('请选日期', true); return false; }
      const ex = rConvRowOf(iso); if (ex) { toast('换算表第 ' + ex + ' 行已经有这天了', true); return false; }
      const vals = {}; $$('.oc input', ov).forEach(i => { if (i.value.trim() !== '') vals[i.dataset.c] = i.value.trim(); });
      let nr; await rAtomic(['conv'], async () => { nr = rAddConvRow(rFromIso(iso), vals); rDirty('conv'); await rSaveTabs(['conv'], '新增一天 ' + rFromIso(iso), null, true); });
      RP.k = 'conv'; rRender(true); requestAnimationFrame(() => { rSelect(nr, 'B'); });
    } }], { wide: true, nofocus: true });
  const note = async () => {
    const iso = $('#caD', ov).value, N = $('#caNote', ov); N.innerHTML = '';
    if (!iso) return;
    const ex = rConvRowOf(iso);
    if (ex) { N.innerHTML = `<span class="tag warn">第 ${ex} 行已有这天</span> <a class="link" id="caGo">去改那一行</a>`; $('#caGo', ov).onclick = () => { ov.remove(); rSelect(ex, 'B'); }; return; }
    try {
      const t = (await api('/api/report/trash?key=conv&date=' + iso)).items;
      if (t.length) { N.innerHTML = `<span class="tag">回收站里有这天（${esc(t[0].deleted_by)} 删的）</span> <a class="link" id="caRs">从回收站恢复</a>　或填下面新建`; $('#caRs', ov).onclick = async () => { try { await rRestoreRow(t[0].id); ov.remove(); } catch (e) { fail(e); } }; }
    } catch (e) { }
  };
  $('#caD', ov).onchange = note; note();
}
async function rRestoreRow(id) {
  if (Object.keys(RP.dirty).length) throw new Error('报表还有没保存的修改，先保存再恢复');
  const x = await save('/api/restore', { entity: 'report_row', id }, '从回收站恢复');
  await rLoad(x.key); for (const k of x.synced || []) await rLoad(k);
  RP.k = x.key; rRender(true); requestAnimationFrame(() => rSelect(x.r, 'A')); toast('已恢复到第 ' + x.r + ' 行');
}

/* ---------- 显示设置：列显示/顺序/改名、默认筛选（只影响屏幕和打印；「下载 Excel」始终是原表格式） ---------- */
function rPrefsDlg(k) {
  const base = rCols(k, true), p = JSON.parse(JSON.stringify((RP.prefsOff || {})[k] || rPref(k) || {}));
  let order = (p.order && p.order.length ? p.order.filter(c => base.includes(c)).concat(base.filter(c => !p.order.includes(c))) : base.slice());
  const hid = new Set(p.hidden || []), lab = Object.assign({}, p.labels || {});
  const fl = (p.filters || []).concat([{}, {}, {}]).slice(0, 3);
  const ov = dialog('「' + RT[k].short + '」显示设置', `<div class="grid2" style="grid-template-columns:1.3fr 1fr;gap:18px"><div>
      <div class="lab">列（勾选显示；↑↓ 调顺序；右边「显示为」空着=默认列名）</div><div id="psCols" style="max-height:52vh;overflow:auto;border:1px solid var(--line);border-radius:8px"></div></div>
    <div><div class="lab">默认只看这段日期</div><div class="row r2"><input class="inp" type="date" id="psFrom" value="${esc(p.from || '')}"><input class="inp" type="date" id="psTo" value="${esc(p.to || '')}"></div>
      <div class="lab" style="margin-top:12px">默认筛选（某列包含某字；库存及到货总数也可点表头 ▾）${k === 'stock' ? '；U8 列选「不用入U8」等' : ''}</div>
      ${fl.map((f, i) => { const opts = base.map(c => `<option value="${c}" ${f.c === c ? 'selected' : ''}>${esc(rFullLabel(k, c))}（${c}）</option>`).join('') + (k === 'stock' ? `<option value="@u8" ${f.c === '@u8' ? 'selected' : ''}>U8（状态）</option>` : ''); return `<div class="row r2" style="margin-top:6px"><select class="inp sm" data-fc="${i}"><option value="">（不筛选）</option>${opts}</select><input class="inp sm" data-fq="${i}" value="${esc(f.q || '')}" placeholder="包含…"></div>`; }).join('')}
      <div class="hint" style="margin-top:12px">设置存在主机上，所有人看到的一样。列宽：在表头竖线处拖动即可，会自动保存。只影响屏幕显示和打印；「下载 Excel」始终和原表格式一致，另有「⋯ → 按当前显示导出 Excel」。「重置列宽」只清宽度；「恢复默认」会清掉列显示/筛选/列宽。</div></div></div>`,
    [{ t: '重置列宽', fn: async () => { await rResetWidths(k); } },
     { t: '恢复默认', fn: async () => { await save('/api/report/prefs/reset', { key: k }, '恢复默认显示'); delete RP.prefs[k]; if (RP.prefsOff) delete RP.prefsOff[k]; rRender(true); toast('已恢复默认'); } },
     { t: '取消' },
     { t: '保存', cls: 'pri', fn: async ov => {
       const d = { hidden: order.filter(c => hid.has(c)), order: order.join() === base.join() ? [] : order, labels: {}, from: $('#psFrom', ov).value, to: $('#psTo', ov).value,
         filters: [0, 1, 2].map(i => ({ c: $(`[data-fc="${i}"]`, ov).value, q: $(`[data-fq="${i}"]`, ov).value.trim() })).filter(f => f.c && f.q),
         widths: Object.assign({}, ((RP.prefsOff || {})[k] || rPref(k) || {}).widths || {}) };
       Object.keys(lab).forEach(c => { if (lab[c] && lab[c] !== rFullLabel(k, c)) d.labels[c] = lab[c]; });
       if (d.hidden.length >= order.length) { toast('至少留一列', true); return false; }
       await save('/api/report/prefs/save', { key: k, data: d }, '保存显示设置'); RP.prefs[k] = d; if (RP.prefsOff) delete RP.prefsOff[k]; rRender(true); toast('已保存显示设置');
     } }], { wide: true, nofocus: true });
  const colVal = c => { const def = rFullLabel(k, c), v = (lab[c] || '').trim(); return (v && v !== def) ? v : ''; };
  const draw = () => {
    // 与名称设置同规格：左边原列名，右边空着=默认；占位符「改列名…」不再回显原名
    $('#psCols', ov).innerHTML = `<table class="t"><tbody>${order.map((c, i) => `<tr><td style="width:28px"><input type="checkbox" data-v="${c}" ${hid.has(c) ? '' : 'checked'}></td><td class="o">${esc(rFullLabel(k, c))} <span class="muted" style="font-size:12px">${c}</span></td>
      <td><input class="inp sm" data-l="${c}" value="${esc(colVal(c))}" placeholder="改列名…"></td>
      <td class="w" style="width:70px"><button class="btn sm" data-up="${i}" ${i ? '' : 'disabled'}>↑</button><button class="btn sm" data-dn="${i}" ${i < order.length - 1 ? '' : 'disabled'}>↓</button></td></tr>`).join('')}</tbody></table>`;
  };
  draw();
  $('#psCols', ov).addEventListener('click', e => {
    const t = e.target, i = +(t.dataset.up || t.dataset.dn);
    if (t.dataset.up !== undefined && i > 0) { [order[i - 1], order[i]] = [order[i], order[i - 1]]; draw(); }
    if (t.dataset.dn !== undefined && i < order.length - 1) { [order[i + 1], order[i]] = [order[i], order[i + 1]]; draw(); }
  });
  $('#psCols', ov).addEventListener('change', e => { const t = e.target; if (t.dataset.v) { if (t.checked) hid.delete(t.dataset.v); else hid.add(t.dataset.v); } });
  $('#psCols', ov).addEventListener('input', e => { const t = e.target; if (t.dataset.l) lab[t.dataset.l] = t.value.trim(); });
}
/** 按当前显示（列、顺序、列名、筛选）导出：数值是算好的结果，不带公式和原表格式 */
async function rViewRows(k) {
  const tab = rTab(k), ev = rEval(k), rg = rRanges(k), cols = rCols(k), cfg = RT[k], out = [];
  for (let r = rg.start; r <= rg.mainEnd; r++) {
    if (!rHasVal(tab, r, null) || (rFiltered(k) && !rRowOk(k, r, ev))) continue;
    out.push(cols.map(c => { const cell = rCell(tab, c, r); const v = cell ? (cell.f ? ev.val(c, r) : cell.v) : ''; return typeof v === 'number' && (cfg.dec2 || []).includes(c) && cell.f ? Math.round(v * 100) / 100 : (v == null ? '' : v); }));
  }
  return { header: cols.map(c => rLabel(k, c)), rows: out };
}
async function rExportView(k) {
  if (typeof loadXlsxLib === 'function') await loadXlsxLib();
  const v = await rViewRows(k), ws = XLSX.utils.aoa_to_sheet([v.header].concat(v.rows)), wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, RT[k].short.slice(0, 30)); XLSX.writeFile(wb, RT[k].title + '_当前显示_' + rToday() + '.xlsx');
}

/* ---------- 换算表 → 入出库记录 ---------- */
/** 入出库左侧入库量 F（按批号找最近一行）；未知返回 null */
function rLedgerInboundQty(batch) {
  batch = rLedgerNormBatch(batch); if (!batch) return null;
  const lt = rTab('ledger'), rg = rRanges('ledger');
  for (let x = rg.mainEnd; x >= rg.start; x--) {
    if (rLedgerNormBatch(rRaw(lt, 'B', x)) !== batch) continue;
    const q = rEval('ledger').val('F', x);
    if (typeof q === 'number' && isFinite(q)) return q;
  }
  return null;
}
/** 换算表 →记录：旧批不够时确认框可选下一批，按历史「剩余+新取=合计」写，禁止批次剩余为负 */
async function rPush(r) {
  await rEnsure('ledger');
  const ct = rTab('conv'), date = rRaw(ct, 'A', r), v = rEval('conv').val('V', r);
  if (typeof v !== 'number') return toast('这一行没有总计', true);
  const qty = Math.round(v * 100) / 100, lt = rTab('ledger'), lr = rRanges('ledger');
  let dup = null; for (let x = lr.start; x <= lr.mainEnd; x++) if (String(rRaw(lt, 'I', x)) === String(date) && /本库/.test(String(rRaw(lt, 'J', x)))) dup = x;
  const prev = rLedgerPrevAtDate(date);
  const batch = String(rRaw(lt, 'M', prev) || '').trim();
  const prevL = rEval('ledger').val('L', prev);
  const ocr = ((S.boot || {}).settings || {}).ocr || {};
  const autoNext = ocr.ledger_auto_next !== false;
  const prefer = String(ocr.ledger_prefer_next || '').trim();
  const cand = rLedgerNextCandidates(batch);
  const nextList = cand.list.slice();
  const knownLow = typeof prevL === 'number' && qty > prevL + 1e-9;
  const alreadyNeg = typeof prevL === 'number' && prevL < -1e-9;
  const need2 = knownLow || alreadyNeg;
  if (need2 && !nextList.length) {
    return toast('当前批次剩余不够（' + (typeof prevL === 'number' ? prevL.toFixed(2) : '?') + ' < ' + qty + '），且没有可选新批次。请先在入出库记录左侧入库，或点「一天两批」。不会写出负数。', true);
  }
  const rem = typeof prevL === 'number' ? Math.max(0, Math.round(prevL * 100) / 100) : 0;
  const take = Math.round((qty - rem) * 100) / 100;
  const defNext = (() => {
    if (!need2) return '';
    if (prefer && nextList.includes(prefer)) return prefer;
    if (autoNext && nextList[0]) return nextList[0];
    return ''; // 未勾选自动预选：须在确认框自选
  })();
  const remTxt = typeof prevL === 'number' ? prevL.toFixed(2) : '未知';
  const nextOpts = (autoNext ? '' : '<option value="">（请选择新批次）</option>')
    + nextList.map(b => `<option value="${esc(b)}" ${b === defNext ? 'selected' : ''}>${esc(rLedgerBatchOptLabel(b, cand))}</option>`).join('');
  const body = `写入「液态氧原料入出库记录」新的一行：
    <div class="kvs"><div>出库时间</div><b>${esc(date)}</b><div>去向</div><b>出本库</b><div>出库量</div><b>${qty} 吨</b>
    <div>上一行剩余</div><b>${esc(remTxt)}${batch ? ' · 批 ' + esc(batch) : ''}</b></div>
    ${need2 ? `<div class="banner" style="margin-top:8px">旧批不够（不会写成负数）。按历史写法 <b>${rem}+${take}=${qty}</b>，并填「新批次」。下拉只列还有余量的批（含只剩一点点的）。</div>
      <div style="margin-top:8px"><span class="lab">新批次 (N)</span>
        <select class="inp" id="rpNext">${nextOpts || '<option value="">（无）</option>'}</select>
        <div class="muted" style="margin-top:4px;font-size:12px">默认${autoNext ? '优先「还有剩余的批」，再才是未动用新批' : '请自选'}；可在「设置 → 识别（OCR）」改默认/优先批号。</div>
      </div>` : `<div class="kvs" style="margin-top:4px"><div>批次剩余</div><b>= 上一行剩余 − 出库量${typeof prevL === 'number' ? '（' + prevL.toFixed(2) + ' → ' + (prevL - qty).toFixed(2) + '）' : ''}</b><div>批次</div><b>${esc(batch || '（空）')}</b></div>`}
    ${dup ? `<div class="banner">第 ${dup} 行已经有 ${esc(date)} 的出本库记录，确定还要再写一行吗？</div>` : ''}
    <div class="muted">确定后会马上保存（换算表有未保存的修改也一起保存）。</div>`;
  const ov = dialog('请确认', body, [
    { t: '取消' },
    { t: '写入并保存', cls: 'pri', fn: async o => {
      let nextBatch = '', newInbound;
      if (need2) {
        nextBatch = (($('#rpNext', o) || {}).value || '').trim();
        if (!nextBatch) { toast('请选择新批次（旧批不够，禁止写出负数）', true); return false; }
        newInbound = rLedgerInboundQty(nextBatch);
      }
      let nr = 0, ok = false;
      await rAtomic(['ledger'], async () => {
        const opt = { date, qty, link: { k: 'conv', date: rIso(date) }, batch: batch || undefined };
        if (need2) { opt.nextBatch = nextBatch; opt.newInbound = newInbound; }
        nr = rAddLedgerRow(opt);
        rDirty('ledger');
        await rSaveTabs(['ledger'].concat(RP.dirty.conv ? ['conv'] : []), '换算表 ' + date + ' 总计写入入出库记录' + (need2 ? '（接下一批 ' + nextBatch + '）' : ''), null, true);
        ok = true;
      }).catch(fail);
      if (!ok) return false;
      RP.k = 'ledger'; RP.sel = null; rRender(true); requestAnimationFrame(() => { rLatest(); rSelect(nr, 'K'); });
      toast(need2 ? '已写入第 ' + nr + ' 行（两批 ' + rem + '+' + take + '=' + qty + '）' : '已写入第 ' + nr + ' 行');
    } }
  ]);
}

/* ---------- 照片附件（存照片编号） ---------- */
async function rAddAtt(k, r, after) {
  const ps = await photoPick({ title: '照片 · ' + RT[k].title + ' 第 ' + r + ' 行', label: RT[k].title + ' 第 ' + r + ' 行', extra: { entity: 'report', tag: k } }); if (!ps.length) return;
  const row = rRow(rTab(k), r); row.att = row.att || [];
  ps.forEach(p => row.att.push({ id: p.id, path: p.path, name: p.name }));
  rDirty(k); rRender(true); toast('已添加照片，点「保存」生效'); if (after) after();
}
function rShowAtt(k, r) {
  const tab = rTab(k), row = tab.rows[r - 1], att = (row && row.att) || [];
  const ov = dialog('照片 · 第 ' + r + ' 行 ' + [rRaw(tab, 'A', r), rRaw(tab, 'B', r)].filter(x => x !== '').join(' '),
    `<div class="photos">${att.map((a, i) => `<div class="ph-w"><img class="ph-i" src="/photos/${esc(a.path)}" onclick="bigImg(this.src)"><b data-rm="${i}" title="移除">×</b></div>`).join('') || '<div class="muted">还没有照片</div>'}</div>`,
    [{ t: '＋ 添加照片', fn: () => { ov.remove(); rAddAtt(k, r, () => rShowAtt(k, r)); return false; } }, { t: '关闭', cls: 'pri' }]);
  ov.addEventListener('click', e => { const i = e.target.dataset.rm; if (i === undefined) return; att.splice(+i, 1); rDirty(k); rRender(true); ov.remove(); rShowAtt(k, r); });
}

/* ---------- 液氧表：登记到车（一车多卸；四号库的只进 4号院 表） ---------- */
const rIs4 = p => /四号库|4号院/.test(p || '');
/* ---------- 液氧表 → 液态氧原料入出库记录：卸到别处的（不是本库罐、不是4号院）记成出库 ---------- */
const rOwnTank = p => /本库/.test(p || '');
function rLoxRec(r) { const t = rTab('lox'), end = rRanges('lox').mainEnd, out = [r]; for (let x = r + 1; x <= end; x++) { if (rRaw(t, 'A', x) !== '' || !rHasVal(t, x, ['B', 'C', 'D', 'E', 'F'])) break; out.push(x); } return out; }
function rLoxOut(r) {
  const t = rTab('lox'), out = [];
  if (!rParseDate(rRaw(t, 'A', r))) return out;
  rLoxRec(r).forEach(x => String(rRaw(t, 'E', x)).split('+').forEach(p => { const m = /^\s*出?(.*?)\s*(\d+(?:\.\d+)?)\s*$/.exec(p); if (!m || !m[1].trim()) return; const place = m[1].trim(); if (rOwnTank(place) || rIs4(place) || /[\d=（(]/.test(place)) return; out.push({ place, tons: +m[2] }); }));
  return out;
}
const rLxId = () => 'lx' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
function rLoxLinked(id) { const lt = rTab('ledger'); return lt ? lt.rows.map((x, i) => x && x.link && x.link.k === 'lox' && x.link.id === id ? i + 1 : 0).filter(Boolean) : []; }
/** 入出库记录里已手填的同一笔（地点一致、吨数差不到 0.01、日期差 2 天内、没接联动） */
function rLedgerMatch(date, place, tons, used) {
  const lt = rTab('ledger'), rg = rRanges('ledger'), d0 = rParseDate(date);
  for (let r = rg.mainEnd; r >= rg.start; r--) {
    const x = lt.rows[r - 1]; if (!x || x.link || (used && used.has(r))) continue;
    const j = String(rRaw(lt, 'J', r)).replace(/^出/, ''); if (!j.startsWith(place) && !place.startsWith(j.replace(/[\d.+]+$/, '')) ) continue;
    const k = rEval('ledger').val('K', r), d = rParseDate(rRaw(lt, 'I', r));
    if (typeof k === 'number' && Math.abs(k - tons) < 0.01 && d && d0 && Math.abs(d - d0) <= 2 * 864e5) return r;
  }
  return 0;
}
/** 把液氧表一车的「卸到别处」写进入出库记录（或接上已手填的那行）。plan: [{place,tons,act:'new'|'skip'|行号}] */
function rLoxApply(r, plan) {
  const lt = rTab('ledger'), row = rRow(rTab('lox'), r), date = rRaw(rTab('lox'), 'A', r), id = row.lx || (row.lx = rLxId()); const res = [];
  plan.forEach(p => {
    const link = { k: 'lox', id, place: p.place, date: rIso(date) };
    if (p.act === 'skip') return;
    if (p.act === 'new') { const nr = rAddLedgerRow({ date, qty: p.tons, to: '出' + p.place, link, batch: p.batch, nextBatch: p.nextBatch, newInbound: p.newInbound }); res.push(nr); }
    else { rRow(lt, +p.act).link = link; res.push(+p.act); }
  });
  if (res.length) { rDirty('lox'); rDirty('ledger'); }
  return res;
}
async function rLoxLinkDlg(r) {
  await rEnsure('ledger');
  const t = rTab('lox'), lines = rLoxOut(r), used = new Set();
  if (!lines.length) return toast('这一行没有卸到别处的（本库罐、4号院不记出库）', true);
  const opts = lines.map(l => { const m = rLedgerMatch(rRaw(t, 'A', r), l.place, l.tons, used); if (m) used.add(m); return m; });
  const lt = rTab('ledger'), date = rRaw(t, 'A', r), batches = rLedgerBatches();
  const defBatch = (() => { const p = rLedgerPrevAtDate(date); return String(rRaw(lt, 'M', p) || '').trim(); })();
  const unused = rLedgerUnusedBatches();
  const prevL = (() => { const p = rLedgerPrevAtDate(date); return rEval('ledger').val('L', p); })();
  const batchOpts = (sel) => {
    const list = batches.slice(); unused.forEach(b => { if (!list.includes(b)) list.push(b); });
    if (sel && !list.includes(sel)) list.unshift(sel);
    return list.map(b => `<option value="${esc(b)}" ${b === sel ? 'selected' : ''}>${esc(b)}${unused.includes(b) && b !== sel ? '（未用）' : ''}</option>`).join('') + `<option value="" ${!sel ? 'selected' : ''}>（空）</option>`;
  };
  const nextOpts = () => {
    const list = unused.slice(); if (!list.length) batches.forEach(b => { if (b !== defBatch && !list.includes(b)) list.push(b); });
    return list.map(b => `<option value="${esc(b)}">${esc(b)}</option>`).join('') + `<option value="">（不换批）</option>`;
  };
  const ov = dialog('关联到「液态氧原料入出库记录」', `<div>第 ${r} 行 <b>${esc(date)} ${esc(rRaw(t, 'B', r))}</b>：卸到别处的记成出库。以后改液氧表这车的吨数，入出库记录跟着变。</div>
    <table class="t" style="margin-top:8px"><thead><tr><th>卸到</th><th class="n">吨</th><th>怎么记</th><th>用哪一批次</th><th>若旧批不够·新批次</th></tr></thead><tbody>${lines.map((l, i) => {
      const isNew = !opts[i];
      const need2 = isNew && typeof prevL === 'number' && l.tons > prevL + 1e-9;
      return `<tr><td>${esc(l.place)}</td><td class="n">${l.tons.toFixed(2)}</td><td><select class="inp sm" data-li="${i}">
      ${opts[i] ? `<option value="${opts[i]}" selected>接上已手填的第 ${opts[i]} 行（${esc(rRaw(lt, 'I', opts[i]))} ${esc(rRaw(lt, 'J', opts[i]))}）</option>` : ''}<option value="new"${isNew ? ' selected' : ''}>新增一行出库「出${esc(l.place)}」</option><option value="skip">不记</option></select></td>
      <td><select class="inp sm" data-batch="${i}" ${isNew ? '' : 'disabled'}>${batchOpts(defBatch)}</select></td>
      <td><select class="inp sm" data-next="${i}" ${need2 ? '' : 'disabled'}>${nextOpts()}</select>${need2 ? `<div class="muted">剩余 ${prevL.toFixed(2)}，需换批</div>` : ''}</td></tr>`;
    }).join('')}</tbody></table>
    <div class="hint">新增的行会<strong>按出库日期插到入出库记录正确位置</strong>；旧批不够时按历史写法 <b>剩余+新取=合计</b>，并填「新批次」。批次剩余未知则留空。已手填过的会认出来。</div>`,
    [{ t: '取消' }, { t: '关联并保存', cls: 'pri', fn: async o => {
      const plan = lines.map((l, i) => {
        const act = $(`[data-li="${i}"]`, o).value;
        const batchEl = $(`[data-batch="${i}"]`, o);
        const nextEl = $(`[data-next="${i}"]`, o);
        const batch = act === 'new' && batchEl ? batchEl.value : undefined;
        const nextBatch = act === 'new' && nextEl && nextEl.value ? nextEl.value : undefined;
        let newInbound;
        if (nextBatch) {
          const lt2 = rTab('ledger'), rg2 = rRanges('ledger');
          for (let x = rg2.mainEnd; x >= rg2.start; x--) if (String(rRaw(lt2, 'B', x) || '').trim() === nextBatch) { const q = rEval('ledger').val('F', x); if (typeof q === 'number') newInbound = q; break; }
        }
        return { place: l.place, tons: l.tons, act, batch, nextBatch, newInbound };
      });
      let rs = [];
      await rAtomic(['lox', 'ledger'], async () => { rs = rLoxApply(r, plan); if (!rs.length) throw new Error('cancel'); await rSaveTabs(['lox', 'ledger'], '液氧表第 ' + r + ' 行关联到入出库记录', null, true); }).catch(e => { if (e.message !== 'cancel') fail(e); });
      rRender(true); if (rs.length) toast('已关联：入出库记录第 ' + rs.join('、') + ' 行');
    } }], { wide: true });
  ov.addEventListener('change', e => {
    const s = e.target.closest('[data-li]'); if (!s) return;
    const i = s.dataset.li, b = $(`[data-batch="${i}"]`, ov); if (!b) return;
    b.disabled = s.value !== 'new';
  });
}

/* ---------- 液氧质检入库向导（纯前端编排现有 API；不改 parse/sync/preserve） ---------- */
function rLoxPendingQc() {
  const t = rTab('lox'); if (!t) return [];
  const rg = rRanges('lox'), out = [];
  for (let r = rg.start; r <= rg.mainEnd; r++) {
    const qc = rLoxQc(r); if (!qc) continue;
    const id = (t.rows[r - 1] || {}).lx;
    if (id && rLoxInLinked(id).length) continue;
    out.push({ r, qc, id });
  }
  return out;
}
function rLoxFlashLedger(nr) {
  RP.k = 'ledger'; rRender(true);
  requestAnimationFrame(() => {
    rSelect(nr, 'B');
    const tr = document.querySelector(`#rGrid tr[data-r="${nr}"]`);
    if (!tr) return;
    tr.classList.add('r-new');
    'BCDEFGH'.split('').forEach(c => {
      const td = tr.querySelector(`td[data-c="${c}"]`);
      if (td) { td.classList.add('r-flash'); setTimeout(() => td.classList.remove('r-flash'), 2000); }
    });
    setTimeout(() => tr.classList.remove('r-new'), 1600);
    tr.scrollIntoView({ block: 'center', behavior: 'smooth' });
  });
}
function rLoxPendingPanel() {
  const pend = rLoxPendingQc();
  if (!pend.length) return toast('没有待写入的质检行（需填齐质检入库量 / 批次号 / 入库日期，且尚未关联）');
  const body = `<div class="hint" style="margin-bottom:8px">共 <b>${pend.length}</b> 行质检已齐、尚未写入入出库左侧。点「确认写入」打开向导（只补空、不抹空）。</div>
    <div class="tw"><table class="t"><thead><tr><th>行</th><th>日期</th><th>车牌</th><th>批次</th><th>入库日</th><th class="n">量(吨)</th><th></th></tr></thead><tbody>
    ${pend.map(p => `<tr><td class="w">${p.r}</td><td class="w">${esc(p.qc.date)}</td><td>${esc(p.qc.plate || '')}</td>
      <td>${esc(p.qc.batch)}</td><td class="w">${esc(p.qc.inbound)}</td><td class="n">${p.qc.qty}</td>
      <td class="w"><a data-gowrite="${p.r}">确认写入</a></td></tr>`).join('')}</tbody></table></div>`;
  const ov = dialog('待写入质检 · ' + pend.length, body, [{ t: '关闭', cls: 'pri' }], { wide: true });
  ov.addEventListener('click', e => {
    const a = e.target.closest('[data-gowrite]'); if (!a) return;
    ov.remove();
    rLoxInLinkDlg(+a.dataset.gowrite).catch(fail);
  });
}

/* ---------- 液氧表质检U8 → 入出库记录左侧入库（加性联动；从不把已有格子抹空） ---------- */
function rLoxQc(r) {
  const t = rTab('lox'); if (!t || !rParseDate(rRaw(t, 'A', r))) return null;
  const g = String(rRaw(t, 'G', r) || '').trim(), h = rRaw(t, 'H', r), j = rRaw(t, 'J', r);
  if (!g || h === '' || h == null || !rParseDate(j)) return null;
  const m = /(\d+(?:\.\d+)?)/.exec(g.replace(/,/g, '')); if (!m) return null;
  const batch = String(h).trim();
  return { qty: Math.round(parseFloat(m[1]) * 100) / 100, batch, prod: rRaw(t, 'I', r), inbound: rFromIso(rIso(j)) || String(j), inboundIso: rIso(j), plate: rRaw(t, 'B', r), date: rRaw(t, 'A', r) };
}
function rLoxInLinked(id) {
  const lt = rTab('ledger'); return lt ? lt.rows.map((x, i) => x && x.link && x.link.k === 'lox_in' && x.link.id === id ? i + 1 : 0).filter(Boolean) : [];
}
/** 只写入非空：已有值不会被空值盖掉 */
function rSetKeep(tab, col, r, val) {
  if (val === '' || val == null) return false;
  const cur = rRaw(tab, col, r);
  if (cur !== '' && cur != null && String(cur) === String(val)) return false;
  rSet(tab, col, r, val); return true;
}
/** 数量相近（入库量比对用） */
function rQtyClose(a, b) {
  const na = rNumOf(a), nb = typeof b === 'number' ? b : rNumOf(b);
  if (na == null || nb == null) return false;
  return Math.abs(na - nb) < 1e-6;
}
/** 已有左侧入库可复用：同 lx 的 lox_in，或 批次+入库日期+数量 相同，或同批次 */
function rLedgerExistingInbound(o) {
  const lt = rTab('ledger'), rg = rRanges('ledger');
  const batch = String(o.batch || '').trim();
  const iso = rIso(o.date);
  const id = o.link && o.link.id;
  if (id) {
    for (let r = rg.start; r <= rg.mainEnd; r++) {
      const ln = lt.rows[r - 1] && lt.rows[r - 1].link;
      if (ln && ln.k === 'lox_in' && ln.id === id) return { r, how: 'linked' };
    }
  }
  if (batch && iso && o.qty != null && o.qty !== '') {
    for (let r = rg.start; r <= rg.mainEnd; r++) {
      const b = String(rRaw(lt, 'B', r) || '').trim();
      if (b !== batch) continue;
      if (rIso(rRaw(lt, 'E', r)) !== iso) continue;
      if (!rQtyClose(rRaw(lt, 'F', r), o.qty)) continue;
      return { r, how: 'match' };
    }
  }
  if (batch) {
    for (let r = rg.start; r <= rg.mainEnd; r++) {
      if (String(rRaw(lt, 'B', r) || '').trim() === batch) return { r, how: 'same_batch' };
    }
  }
  return null;
}
/** 按入库日期找左侧空行填入，或按日期插入空行（不造批次剩余）；不含“已有批次”——先走 rLedgerExistingInbound */
function rLedgerFindInboundSlot(inboundDate) {
  const lt = rTab('ledger'), rg = rRanges('ledger'), iso = rIso(inboundDate);
  for (let r = rg.start; r <= rg.mainEnd; r++) {
    const eIso = rIso(rRaw(lt, 'E', r)), iIso = rIso(rRaw(lt, 'I', r));
    const leftEmpty = !rHasVal(lt, r, ['B', 'C', 'D', 'E', 'F', 'G', 'H']);
    // 左侧空且日期对上 → 填这一行（即便已有出库联动 conv/lox 也填左侧；不改出库 link，见 rAddLedgerInbound）
    // 旧逻辑 !lk 会跳过已关联出库行，改去插新行 → 同一批入库出现两行（再删行时 preserve 还会把入库格粘到错行）
    if (leftEmpty && ((eIso && eIso === iso) || (iIso && iIso === iso))) return { r, mode: 'fill' };
  }
  let at = null;
  for (let x = rg.start; x <= rg.mainEnd; x++) {
    const d = rIso(rRaw(lt, 'E', x)) || rIso(rRaw(lt, 'I', x));
    if (d && iso && d > iso) { at = x; break; }
  }
  return { r: at || (rg.mainEnd + 1), mode: 'insert', at: at };
}
function rAddLedgerInbound(o) {
  o = o || {}; const tab = rTab('ledger'), rg = rRanges('ledger');
  // 去重：已有同 lx / 同批次+日期+数量 / 同批次 → 接上，绝不因出库 link 冲突再插一行
  const existing = rLedgerExistingInbound(o);
  let r;
  if (existing) {
    r = existing.r;
  } else {
    const slot = rLedgerFindInboundSlot(o.date);
    if (slot.mode === 'insert') {
      const at = slot.at;
      if (at) { O2.insertRow(tab, at, { c: {} }); r = at; rCopyStyles(tab, at - 1 >= rg.start ? at - 1 : at + 1, r); }
      else { r = rNewRowAt('ledger'); rCopyStyles(tab, rg.mainEnd, r); }
      const row = rRow(tab, r);
      Object.keys(row.c || {}).forEach(c => { if (row.c[c] && 'BCDEFGH'.includes(c)) { delete row.c[c].v; delete row.c[c].f; } });
      const nxt = rCell(tab, 'L', r + 1);
      if (nxt && nxt.f && /^L\d+-K\d+$/.test(nxt.f.replace(/\s/g, '').replace(/\$/g, ''))) {
        if (rCell(tab, 'L', r) && rCell(tab, 'L', r).f) rLedgerRewireL(tab, r);
      }
      if (rRaw(tab, 'A', r) === '') { const pa = rRaw(tab, 'A', r - 1); if (typeof pa === 'number') rSet(tab, 'A', r, pa + 1); }
    } else r = slot.r;
  }
  rSetKeep(tab, 'B', r, o.batch);
  rSetKeep(tab, 'E', r, o.date);
  if (o.qty != null) rSetKeep(tab, 'F', r, o.qty);
  if (o.tank) rSetKeep(tab, 'G', r, o.tank);
  if (o.prod) rSetKeep(tab, 'C', r, o.prod);
  if (o.vendor) rSetKeep(tab, 'H', r, o.vendor);
  if (o.link) {
    const row = rRow(tab, r);
    const lk = row.link && row.link.k;
    // 一行一个 link：无 link 或已是 lox_in 才挂上；已有出库联动则不改 link、也不再插重复入库行
    if (!lk || lk === 'lox_in') row.link = o.link;
  }
  return r;
}

function rLoxEnsureId(r) {
  const row = rRow(rTab('lox'), r); if (!row.lx) row.lx = rLxId(); return row.lx;
}
function rLoxInApply(r, opt) {
  opt = opt || {}; const qc = rLoxQc(r); if (!qc) return 0;
  const id = rLoxEnsureId(r);
  const link = { k: 'lox_in', id, batch: qc.batch, date: qc.inboundIso };
  const nr = rAddLedgerInbound({ date: qc.inbound, batch: qc.batch, qty: qc.qty, tank: opt.tank, prod: qc.prod, vendor: opt.vendor, link });
  rDirty('lox'); rDirty('ledger');
  return nr;
}
async function rLoxInLinkDlg(r) {
  await rEnsure('ledger');
  const qc = rLoxQc(r); if (!qc) return toast('请先在液氧表填齐：质检U8入库量、批次号、入库日期', true);
  const id = (rTab('lox').rows[r - 1] || {}).lx, already = id ? rLoxInLinked(id) : [];
  if (already.length) {
    rLoxFlashLedger(already[0]);
    return toast('已关联入出库记录第 ' + already.join('、') + ' 行，不会重复写入');
  }
  const hit = rLedgerExistingInbound({ batch: qc.batch, date: qc.inbound, qty: qc.qty });
  const banner = hit
    ? `<div class="banner">入出库记录第 ${hit.r} 行已有相同入库（批次 ${esc(qc.batch)} / ${esc(qc.inbound)} / ${qc.qty} 吨），将接上该行并补全空着的格（已有内容不覆盖，不新建行）。</div>`
    : '<div class="hint">按入库日期插到入出库记录正确位置；批次剩余未知则留空，不编造。若已有相同批次+日期+数量会自动接上，不会重复。</div>';
  // 确认抽屉：将写入的左侧列明文（B～H）
  const leftPreview = `<div class="sec-h" style="margin-top:10px"><h2>将写入左侧入库列</h2><small class="muted">只补空、不抹空 · 罐/厂家可在下面补</small></div>
    <table class="t" style="margin-top:6px"><thead><tr><th>批号</th><th>生产日期</th><th>有效期</th><th>入库日期</th><th class="n">入库量</th><th>罐</th><th>厂家</th></tr></thead>
    <tbody><tr>
      <td>${esc(qc.batch)}</td>
      <td>${esc(qc.prod || '—')}</td>
      <td class="muted">（不自动填）</td>
      <td>${esc(qc.inbound)}</td>
      <td class="n">${qc.qty}</td>
      <td class="muted" id="liTankPrev">（可空）</td>
      <td class="muted" id="liVendPrev">（可空）</td>
    </tr></tbody></table>`;
  const ov = dialog('质检入库向导 · 确认写入', `<div>液氧表第 ${r} 行 <b>${esc(qc.date)} ${esc(qc.plate || '')}</b></div>
    ${leftPreview}
    ${banner}
    <div class="row r2" style="margin-top:8px"><div><span class="lab">入库罐体（可空）</span><select class="inp" id="liTank"><option value="">（空）</option><option>C罐</option><option>D罐</option></select></div>
    <div><span class="lab">原料厂家（可空）</span><input class="inp" id="liVend" placeholder="可留空" value=""></div></div>`,
    [{ t: '取消' }, { t: '写入并保存', cls: 'pri', fn: async o => {
      const tank = ($('#liTank', o).value || '').trim(), vendor = ($('#liVend', o).value || '').trim();
      let nr = 0;
      const beforeHit = rLedgerExistingInbound({ batch: qc.batch, date: qc.inbound, qty: qc.qty });
      await rAtomic(['lox', 'ledger'], async () => {
        nr = rLoxInApply(r, { tank, vendor });
        if (!nr) throw new Error('cancel');
        await rSaveTabs(['lox', 'ledger'], '液氧表 U8 入库写入：批次 ' + qc.batch + '，入库日期 ' + qc.inbound + '，入库量 ' + qc.qty, null, true);
      }).catch(e => { if (e.message !== 'cancel') fail(e); });
      if (nr) {
        toast((beforeHit ? '已接上' : '已写入') + '入出库记录第 ' + nr + ' 行左侧入库');
        rLoxFlashLedger(nr);
      } else rRender(true);
    } }]);
  ov.addEventListener('input', e => {
    if (e.target.id === 'liVend') { const n = $('#liVendPrev', ov); if (n) n.textContent = e.target.value.trim() || '（可空）'; }
  });
  ov.addEventListener('change', e => {
    if (e.target.id === 'liTank') { const n = $('#liTankPrev', ov); if (n) n.textContent = e.target.value || '（可空）'; }
  });
}

/** 批号规范化（表里可能是数字 20261001） */
function rLedgerNormBatch(v) {
  const s = String(v == null ? '' : v).trim();
  if (!s || s[0] === '=') return '';
  const m = /^(20\d{6})(?:\.0+)?$/.exec(s);
  return m ? m[1] : s;
}
/**
 * 按历史规则算各批物理剩余（主表区）：入库 F − 出库归属。
 * 出库归属：K 为 a+b[=合计] 时 a→M、b→N；否则整笔 →M。
 * 返回 { rem, order(入库先后), inboundQty, used(曾作 M/N) }
 * 规则见 docs/LOX_BATCH_RULES.md
 */
function rLedgerBatchRemains() {
  const tab = rTab('ledger'), rg = rRanges('ledger');
  const rem = {}, inboundQty = {}, order = [], used = new Set();
  const seen = new Set();
  for (let r = rg.start; r <= rg.mainEnd; r++) {
    const b = rLedgerNormBatch(rRaw(tab, 'B', r));
    if (!b || seen.has(b)) continue;
    const q = rEval('ledger').val('F', r);
    if (typeof q !== 'number' || !isFinite(q)) continue;
    seen.add(b); order.push(b); inboundQty[b] = q; rem[b] = q;
  }
  const round2 = x => Math.round(x * 100) / 100;
  for (let r = rg.start; r <= rg.mainEnd; r++) {
    const m = rLedgerNormBatch(rRaw(tab, 'M', r));
    const n = rLedgerNormBatch(rRaw(tab, 'N', r));
    const kRaw = rRaw(tab, 'K', r);
    const ks = String(kRaw == null ? '' : kRaw).trim();
    const tw = /^(-?\d+(?:\.\d+)?)\s*\+\s*(-?\d+(?:\.\d+)?)/.exec(ks);
    if (tw && (m || n)) {
      const a = +tw[1], bq = +tw[2];
      if (m) { used.add(m); if (rem[m] != null) rem[m] = round2(rem[m] - a); }
      if (n) { used.add(n); if (rem[n] != null) rem[n] = round2(rem[n] - bq); }
      continue;
    }
    let q = rEval('ledger').val('K', r);
    if (typeof q !== 'number' || !isFinite(q)) {
      if (/^-?\d+(?:\.\d+)?$/.test(ks)) q = +ks; else continue;
    }
    if (!m) continue;
    used.add(m);
    if (rem[m] != null) rem[m] = round2(rem[m] - q);
  }
  return { rem, order, inboundQty, used };
}
/**
 * 跨批时「新批次」候选：有余量（含差一点点）、不含当前批、入库不早于当前批；
 * 已开过仍有剩的优先，再未动用新批；均按入库 FIFO。
 */
function rLedgerNextCandidates(excludeBatch) {
  const { rem, order, inboundQty, used } = rLedgerBatchRemains();
  const ex = rLedgerNormBatch(excludeBatch);
  const exIdx = ex ? order.indexOf(ex) : -1;
  const partial = [], fresh = [];
  order.forEach((b, i) => {
    if (b === ex) return;
    if (!((rem[b] || 0) > 1e-9)) return;
    if (exIdx >= 0 && i < exIdx) return; // 更早、无关的未用批不进下拉
    if (used.has(b)) partial.push(b); else fresh.push(b);
  });
  return { list: partial.concat(fresh), rem, inboundQty, used };
}
/** 下拉文案：剩 x / 未用·x */
function rLedgerBatchOptLabel(b, info) {
  const r = info && info.rem ? info.rem[b] : null;
  const unused = info && info.used ? !info.used.has(b) : false;
  if (typeof r === 'number' && isFinite(r)) {
    const txt = (Math.round(r * 100) / 100).toFixed(2);
    return unused ? (b + '（未用·' + txt + '）') : (b + '（剩' + txt + '）');
  }
  return unused ? (b + '（未用）') : b;
}
/** 兼容旧调用：真正「未动用且仍有余量」的批（入库先后） */
function rLedgerUnusedBatches() {
  const { list, used } = rLedgerNextCandidates('');
  return list.filter(b => !used.has(b));
}

/** 一天两个批次：出库量写成 旧剩余+新取[=合计]，M=旧批 N=新批；批次剩余按新批剩余写，未知则留空 */
function rLedgerTwoBatchWrite(r, rem, take, oldBatch, newBatch, newRemain) {
  const tab = rTab('ledger');
  const total = Math.round((rem + take) * 100) / 100;
  const kstr = rem + '+' + take + '=' + total;
  rSet(tab, 'K', r, kstr);
  if (oldBatch) rSet(tab, 'M', r, oldBatch);
  if (newBatch) rSet(tab, 'N', r, newBatch);
  if (newRemain != null && newRemain !== '' && isFinite(newRemain)) rSet(tab, 'L', r, Math.round(newRemain * 100) / 100);
  else { const cell = rCell(tab, 'L', r); if (cell) { delete cell.v; delete cell.f; } }
}

/** 入出库记录 · 接下一批：选未用批次，新增出库行（走 rAddLedgerRow，不新算法） */
async function rLedgerNextBatchDlg() {
  await rEnsure('ledger');
  const prev = rRanges('ledger').mainEnd;
  const cur = rLedgerNormBatch(rRaw(rTab('ledger'), 'N', prev) || rRaw(rTab('ledger'), 'M', prev));
  const cand = rLedgerNextCandidates(cur);
  const list = cand.list.length ? cand.list : rLedgerBatches();
  if (!list.length) return toast('入出库记录里还没有可用批次（需左侧有入库且仍有余量）', true);
  const defDate = rToday();
  const ov = dialog('接下一批', `<div class="hint">从「还有余量」的批次里选一个（含只剩一点点的；不堆无关未用），按出库日期插一行（当前批次 M）。不改已有左侧入库格。</div>
    <div class="row r2" style="margin-top:8px">
      <div><span class="lab">出库日期</span><input class="inp" type="date" id="nbDate" value="${esc(rIso(defDate) || defDate)}"></div>
      <div><span class="lab">出库量（吨）</span><input class="inp num" id="nbQty" placeholder="可空，稍后填"></div>
    </div>
    <div style="margin-top:8px"><span class="lab">新批次（当前批次）</span>
      <select class="inp" id="nbBatch">${list.map((b, i) => `<option value="${esc(b)}" ${i === 0 ? 'selected' : ''}>${esc(rLedgerBatchOptLabel(b, cand))}</option>`).join('')}</select>
    </div>
    <div style="margin-top:8px"><span class="lab">去向</span><input class="inp" id="nbTo" value="出本库"></div>`,
    [{ t: '取消' }, { t: '新增并保存', cls: 'pri', fn: async o => {
      const date = rFromIso(($('#nbDate', o).value || '').trim()) || defDate;
      const batch = ($('#nbBatch', o).value || '').trim();
      const qtyRaw = ($('#nbQty', o).value || '').trim();
      const qty = qtyRaw === '' ? undefined : +qtyRaw;
      const to = ($('#nbTo', o).value || '').trim() || '出本库';
      if (!batch) return toast('请选批次', true);
      let nr = 0;
      await rAtomic(['ledger'], async () => {
        nr = rAddLedgerRow({ date, qty, to, batch });
        rDirty('ledger');
        await rSaveTabs(['ledger'], '入出库记录接下一批：' + batch + ' · ' + date, null, true);
      }).catch(fail);
      if (nr) { toast('已新增第 ' + nr + ' 行'); rLoxFlashLedger(nr); }
    } }]);
}
/** 入出库记录 · 一天两批：旧剩余+新取=合计（rLedgerTwoBatchWrite / rAddLedgerRow.nextBatch） */
async function rLedgerTwoBatchDlg() {
  await rEnsure('ledger');
  const rg = rRanges('ledger');
  const prev = rg.mainEnd;
  const defBatch = rLedgerNormBatch(rRaw(rTab('ledger'), 'M', prev) || '');
  const prevL = rEval('ledger').val('L', prev);
  const cand = rLedgerNextCandidates(defBatch);
  const nextList = cand.list.slice();
  if (!nextList.length) return toast('没有可选的新批次（需还有余量的入库批）', true);
  const defDate = rToday();
  const remTxt = typeof prevL === 'number' ? prevL.toFixed(2) : '未知';
  const ov = dialog('一天两批', `<div class="hint">旧批不够时按历史写法 <b>剩余+新取=合计</b>，M=旧批 N=新批。单批仍直接写数量；有余量（含差一点点）才进下拉，不堆无关未用。批次剩余未知则留空。</div>
    <div class="kvs" style="margin-top:8px"><div>上一行剩余</div><b>${esc(remTxt)}</b><div>当前批次</div><b>${esc(defBatch || '—')}</b></div>
    <div class="row r2" style="margin-top:8px">
      <div><span class="lab">出库日期</span><input class="inp" type="date" id="tbDate" value="${esc(rIso(defDate) || defDate)}"></div>
      <div><span class="lab">出库合计（吨）</span><input class="inp num" id="tbQty" placeholder="必填，须大于旧剩余"></div>
    </div>
    <div class="row r2" style="margin-top:8px">
      <div><span class="lab">旧批次 (M)</span><input class="inp" id="tbOld" value="${esc(defBatch)}"></div>
      <div><span class="lab">新批次 (N)</span><select class="inp" id="tbNew">${nextList.map((b, i) => `<option value="${esc(b)}" ${i === 0 ? 'selected' : ''}>${esc(rLedgerBatchOptLabel(b, cand))}</option>`).join('')}</select></div>
    </div>
    <div style="margin-top:8px"><span class="lab">去向</span><input class="inp" id="tbTo" value="出本库"></div>`,
    [{ t: '取消' }, { t: '写入并保存', cls: 'pri', fn: async o => {
      const date = rFromIso(($('#tbDate', o).value || '').trim()) || defDate;
      const qty = +($('#tbQty', o).value || '');
      const oldB = ($('#tbOld', o).value || '').trim();
      const newB = ($('#tbNew', o).value || '').trim();
      const to = ($('#tbTo', o).value || '').trim() || '出本库';
      if (!(qty > 0)) return toast('请填出库合计', true);
      if (!newB) return toast('请选新批次', true);
      if (typeof prevL === 'number' && qty <= prevL + 1e-9) return toast('合计未超过旧剩余，不必两批；请用「接下一批」或普通新增', true);
      let newInbound;
      const lt2 = rTab('ledger'), rg2 = rRanges('ledger');
      for (let x = rg2.mainEnd; x >= rg2.start; x--) if (String(rRaw(lt2, 'B', x) || '').trim() === newB) { const q = rEval('ledger').val('F', x); if (typeof q === 'number') newInbound = q; break; }
      let nr = 0;
      await rAtomic(['ledger'], async () => {
        nr = rAddLedgerRow({ date, qty, to, batch: oldB || undefined, nextBatch: newB, newInbound });
        rDirty('ledger');
        await rSaveTabs(['ledger'], '入出库记录一天两批：' + (oldB || '?') + '+' + newB + ' · ' + qty, null, true);
      }).catch(fail);
      if (nr) { toast('已写入第 ' + nr + ' 行（两批）'); rLoxFlashLedger(nr); }
    } }]);
}

function rKnownPlates() {
  const m = new Map(); const add = v => { v = String(v || '').trim(); if (/^[\u4e00-\u9fa5][A-Z][A-Z0-9]{4,6}$/.test(v)) m.set(v, (m.get(v) || 0) + 1); };
  ['lox', 'yard4'].forEach(k => { const t = rTab(k); if (t) t.rows.forEach((row, i) => { if (row) { add(rRaw(t, 'B', i + 1)); add(rRaw(t, 'K', i + 1)); } }); });
  (RP.slipPlates || []).forEach(add);
  return [...m.entries()].sort((a, b) => b[1] - a[1]).map(x => x[0]);
}
function rKnownPlaces() {
  const cnt = new Map(), t = rTab('lox');
  t.rows.forEach((row, i) => { if (!row || i < 12) return; String(rRaw(t, 'E', i + 1)).split('+').forEach(p => { const m = /^\s*出?([\u4e00-\u9fa5]{2,6}[A-D]{0,2})\s*[\d.]/.exec(p); if (m) cnt.set(m[1], (cnt.get(m[1]) || 0) + 1); }); });
  const list = R_PLACES.slice(); [...cnt.entries()].sort((a, b) => b[1] - a[1]).forEach(x => { if (!list.includes(x[0]) && list.length < 16) list.push(x[0]); });
  return list;
}
let RD = null;
async function rDelivery(pref) {
  await rEnsure('lox'); await rEnsure('yard4'); await rEnsure('ledger');
  RD = Object.assign({ led: true,  date: rToday(), plate: '', med: '', settle: '', qc: '', batch: '', note: '', lines: [{ place: '', tons: '' }], photos: [], slipIds: [], msg: '' }, pref || {});
  rDlvDraw();
}
function rDlvSync(ov) {
  const d = RD, v = s => ($(s, ov) || {}).value;
  if ($('#dvDate', ov)) { d.date = rFromIso(v('#dvDate')) || d.date; d.plate = (v('#dvPlate') || '').trim(); d.med = v('#dvMed') || ''; d.settle = v('#dvSettle') || ''; d.qc = v('#dvQc') || ''; d.batch = v('#dvBatch') || ''; d.note = v('#dvNote') || ''; if ($('#dvLed', ov)) d.led = $('#dvLed', ov).checked; }
  $$('.dv-place', ov).forEach(el => { if (d.lines[+el.dataset.i]) d.lines[+el.dataset.i].place = el.value.trim(); });
  $$('.dv-tons', ov).forEach(el => { if (d.lines[+el.dataset.i]) d.lines[+el.dataset.i].tons = el.value.trim(); });
}
function rDlvOut() { return RD.lines.filter(l => parseFloat(l.tons) > 0 && l.place && !rIs4(l.place) && !rOwnTank(l.place)); }
function rDlvLedHtml() { const o = rDlvOut(); return o.length ? `<label><input type="checkbox" id="dvLed" ${RD.led ? 'checked' : ''}> 同时记入「液态氧原料入出库记录」出库：${o.map(l => esc('出' + l.place + ' ' + (+parseFloat(l.tons).toFixed(2)))).join('、')}</label> <span class="muted">（卸到本库罐、4号院的不记出库）</span>` : ''; }
function rDlvSum() {
  const g = RD.lines.filter(l => parseFloat(l.tons) > 0 && !rIs4(l.place));
  return (g.length > 1 ? '=' + g.map(l => +parseFloat(l.tons).toFixed(2)).join('+') + ' = ' : '') + g.reduce((a, l) => a + parseFloat(l.tons), 0).toFixed(2);
}
function rDlvDraw() {
  $$('.ov.dv').forEach(x => x.remove());
  const d = RD, plates = rKnownPlates(), places = rKnownPlaces();
  const lines = d.lines.map((l, i) => `<div class="dv-line"><div class="dv-row"><span class="dv-no">${i + 1}</span><input class="inp dv-place" data-i="${i}" placeholder="卸到哪里，如 本库D" value="${esc(l.place)}"><input class="inp dv-tons num" data-i="${i}" inputmode="decimal" placeholder="吨数" value="${esc(l.tons)}"><span class="muted">吨</span>${d.lines.length > 1 ? `<a class="link d" data-rml="${i}">删掉</a>` : ''}${rIs4(l.place) ? '<span class="tag">只进 4号院 表</span>' : ''}</div>
    <div class="chips">${places.map(p => `<span class="chip ${l.place === p ? 'on' : ''}" data-pl="${i}" data-v="${esc(p)}">${esc(p)}</span>`).join('')}</div></div>`).join('');
  const html = `<div class="dv-src"><button class="btn sm" data-slips>从称重单带入${RP.unusedSlips ? '（' + RP.unusedSlips + ' 张未用）' : ''}</button><button class="btn sm" data-ocr>识别过磅单照片</button><span class="muted" id="dvMsg">${esc(d.msg || '')}</span></div>
    <div class="row r4"><div><span class="lab">日期</span><input class="inp" id="dvDate" type="date" value="${rIso(d.date)}"></div><div><span class="lab">车牌</span><input class="inp" id="dvPlate" list="dvPl" value="${esc(d.plate)}" placeholder="如 陕J65758"></div>
      <div><span class="lab">医用（装车）<span class="muted">选填</span></span><input class="inp" id="dvMed" value="${esc(d.med)}" placeholder="如 彤华27.9"></div><div><span class="lab">彤华结算数据 <span class="muted">可以以后补</span></span><input class="inp" id="dvSettle" value="${esc(d.settle)}"></div></div>
    <datalist id="dvPl">${plates.map(p => `<option value="${esc(p)}">`).join('')}</datalist>
    <div class="dv-hd">卸车 <span class="muted">一张过磅单一行；选「四号库」的那一行写入「4号院」表，不算过磅合计</span></div>${lines}
    <button class="btn sm" data-addl>＋ 再加一个卸点</button>
    <div class="dv-sum">液氧表「过磅合计」：<b id="dvSum">${rDlvSum()}</b> 吨</div><div class="dv-led" id="dvLedW">${rDlvLedHtml()}</div>
    <details ${d.qc || d.batch || d.note ? 'open' : ''}><summary class="muted">质检 / 批次号 / 备注（选填，以后也可在表里补）</summary><div class="row r3" style="margin-top:8px"><div><span class="lab">质检U8批次号入库</span><input class="inp" id="dvQc" value="${esc(d.qc)}"></div><div><span class="lab">批次号</span><input class="inp" id="dvBatch" value="${esc(d.batch)}"></div><div><span class="lab">备注</span><input class="inp" id="dvNote" value="${esc(d.note)}"></div></div></details>
    <div class="photos" style="margin-top:12px">${d.photos.map((p, i) => `<div class="ph-w"><img class="ph-i" src="/photos/${esc(p.path)}" onclick="bigImg(this.src)"><b data-rmp="${i}">×</b></div>`).join('')}<div class="addph" data-addp title="过磅单照片">+</div></div>`;
  const ov = dialog('登记到车（液氧表）', html, [{ t: '取消' }, { t: '保存', cls: 'pri', fn: async o => { rDlvSync(o); return rDlvSave(); } }], { wide: true, nofocus: true });
  ov.classList.add('dv');
  ov.addEventListener('input', e => { rDlvSync(ov); $('#dvSum', ov).textContent = rDlvSum(); if (e.target.id !== 'dvLed') $('#dvLedW', ov).innerHTML = rDlvLedHtml(); });
  ov.addEventListener('click', async e => {
    const t = e.target;
    if (t.dataset.pl !== undefined) { rDlvSync(ov); RD.lines[+t.dataset.pl].place = t.dataset.v; rDlvDraw(); }
    if (t.dataset.rml !== undefined) { rDlvSync(ov); RD.lines.splice(+t.dataset.rml, 1); rDlvDraw(); }
    if (t.dataset.rmp !== undefined) { rDlvSync(ov); RD.photos.splice(+t.dataset.rmp, 1); rDlvDraw(); }
    if (t.closest('[data-addl]')) { rDlvSync(ov); RD.lines.push({ place: '', tons: '' }); rDlvDraw(); }
    if (t.closest('[data-addp]')) { rDlvSync(ov); const ps = await photoPick({ title: '过磅单照片', label: '液氧表 登记到车 过磅单', extra: { entity: 'report', tag: 'lox' } }); ps.forEach(p => RD.photos.push(p)); rDlvDraw(); }
    if (t.closest('[data-slips]')) { rDlvSync(ov); rPickSlips(); }
    if (t.closest('[data-ocr]')) { rDlvSync(ov); rOcrSlips(); }
  });
}
async function rPickSlips() {
  const r = await api('/api/slips'); const l = r.items.slice(0, 40);
  if (!l.length) return toast('还没有称重单，可以在「称重单」页开单', true);
  const ov = dialog('选择称重单带入（一张 = 一个卸点）', `<table class="t"><thead><tr><th></th><th>时间</th><th>流水号</th><th>车号</th><th class="n">净重(kg)</th><th>状态</th></tr></thead><tbody>${l.map((s, i) => `<tr><td><input type="checkbox" value="${s.id}" ${!s.used_at && i < 6 && s.plate === l[0].plate && (s.time || '').slice(0, 10) === (l[0].time || '').slice(0, 10) ? 'checked' : ''}></td><td class="w">${esc(String(s.time || '').replace('T', ' '))}</td><td>${esc(s.sn)}</td><td>${esc(s.plate)}</td><td class="n">${fmtN(s.net)}</td><td>${s.used_at ? '<span class="tag ok">已登记</span>' : '<span class="tag warn">未登记</span>'}</td></tr>`).join('')}</tbody></table>`,
    [{ t: '返回' }, { t: '带入', cls: 'pri', fn: o => {
      const ids = $$('input:checked', o).map(x => +x.value); if (!ids.length) { toast('请勾选', true); return false; }
      const sel = l.filter(s => ids.includes(s.id)).sort((a, b) => (a.time || '').localeCompare(b.time || '') || (a.sn || '').localeCompare(b.sn || ''));
      Object.assign(RD, { date: rFromIso((sel[0].time || '').slice(0, 10)) || RD.date, plate: sel[0].plate, lines: sel.map(s => ({ place: '', tons: (s.net / 1000).toFixed(2) })), slipIds: ids, slipNet: sel.reduce((a, s) => a + (+s.net || 0), 0), msg: '已从 ' + sel.length + ' 张称重单带入，请选每张卸到哪里' });
      rDlvDraw();
    } }], { wide: true });
}
async function rOcrSlips() {
  const fs = await pickFiles('image/*', true); if (!fs.length) return;
  const msg = t => { RD.msg = t; const m = $('#dvMsg'); if (m) m.textContent = t; };
  msg('正在识别过磅单（本机离线识别，首次要几秒）…');
  try { await loadOcr(); } catch (e) { msg('识别组件没加载上：' + e.message); return; }
  let got = [], date = '', plate = '';
  for (const f of fs) {
    try { RD.photos.push(await uploadPhoto(f, { entity: 'report', tag: 'lox' })); } catch (e) { }
    try {
      const url = await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(f); });
      const res = await O2OCR.recognizeSlip(url, m => { if (m && m.status === 'recognizing text') msg('正在识别过磅单… ' + Math.round((m.progress || 0) * 100) + '%'); });
      const p = O2OCR.parseSlips(res, rKnownPlates());
      if (p.date && !date) date = p.date; if (p.plate && !plate) plate = p.plate; got = got.concat(p.slips);
    } catch (e) { console.error(e); }
  }
  if (date) RD.date = rFromIso(date); if (plate) RD.plate = plate;
  if (got.length) { if (RD.lines.every(l => !l.tons && !l.place)) RD.lines = []; got.forEach(s => RD.lines.push({ place: '', tons: s.tons.toFixed(2) })); }
  RD.msg = got.length ? '识别到 ' + got.length + ' 张单子：' + got.map(s => s.net + 'kg').join('、') + (plate ? '，车号 ' + plate : '') + (date ? '，日期 ' + date : '') + '。请选每张卸到哪里并核对。' : '没识别出净重，请手动填写（照片已附上）';
  rDlvDraw();
}
async function rDlvSave() {
  const d = RD, lines = d.lines.filter(l => l.place || parseFloat(l.tons));
  if (!d.plate) { toast('请填车牌', true); return false; }
  if (!lines.length) { toast('请至少填一个卸点和吨数', true); return false; }
  if (lines.some(l => !l.place)) { toast('有卸点没选地点', true); return false; }
  if (lines.some(l => !(parseFloat(l.tons) > 0))) { toast('有卸点没填吨数', true); return false; }
  const loxL = lines.filter(l => !rIs4(l.place)), y4L = lines.filter(l => rIs4(l.place)), t = x => String(+parseFloat(x).toFixed(2));
  const photos = d.photos.map(p => ({ id: p.id, path: p.path }));
  let firstR = null, ledRows = [];
  const outL = d.led ? loxL.filter(l => !rOwnTank(l.place)) : [];
  await rAtomic(['lox', 'yard4', 'ledger'], async () => {
  // 记下用了哪几张称重单（以后称重单删了/改了，这几行会标出来；称重单详情里也能点回这几行）
  const slipLink = (d.slipIds || []).length ? { k: 'slip', ids: d.slipIds.map(Number), net: d.slipNet != null ? d.slipNet : null } : null;
  if (loxL.length) {
    const tab = rTab('lox'), prevLast = rLastDataRow('lox'), r0 = rRanges('lox').last + 1;
    loxL.forEach((l, i) => { rRow(tab, r0 + i); rCopyStyles(tab, prevLast, r0 + i); });
    rSet(tab, 'A', r0, d.date); rSet(tab, 'B', r0, d.plate); if (d.med) rSet(tab, 'C', r0, d.med);
    rSet(tab, 'D', r0, loxL.length > 1 ? '=' + loxL.map(l => t(l.tons)).join('+') : parseFloat(t(loxL[0].tons)));
    loxL.forEach((l, i) => rSet(tab, 'E', r0 + i, l.place + t(l.tons)));
    if (d.settle) rSet(tab, 'F', r0, d.settle); if (d.qc) rSet(tab, 'G', r0, d.qc); if (d.batch) rSet(tab, 'H', r0, d.batch); if (d.note) rSet(tab, 'L', r0, d.note);
    if (loxL.length > 1) ['A', 'B', 'C', 'D', 'F', 'G', 'H'].forEach(c => tab.merges.push(c + r0 + ':' + c + (r0 + loxL.length - 1)));
    if (photos.length) rRow(tab, r0).att = photos;
    if (slipLink) rRow(tab, r0).link = slipLink;
    firstR = r0; rDirty('lox');
    // 卸到别处的记成入出库记录的出库（已手填过同一笔的就接上那行，不重复记）
    if (outL.length) { const used = new Set(); ledRows = rLoxApply(r0, outL.map(l => { const m = rLedgerMatch(d.date, l.place, +t(l.tons), used); if (m) used.add(m); return { place: l.place, tons: +t(l.tons), act: m || 'new' }; })); }
  }
  if (y4L.length) {
    const tab = rTab('yard4');
    y4L.forEach(l => {
      const r = rAppendRow('yard4');
      rSet(tab, 'A', r, d.date); rSet(tab, 'B', r, d.plate); if (d.med) rSet(tab, 'C', r, d.med);
      rSet(tab, 'D', r, parseFloat(t(l.tons))); if (d.settle) rSet(tab, 'E', r, d.settle); if (d.note) rSet(tab, 'F', r, d.note);
      if (!loxL.length && photos.length) rRow(tab, r).att = photos;
      if (slipLink) rRow(tab, r).link = slipLink;
    });
    rDirty('yard4');
  }
  await rSaveTabs([loxL.length ? 'lox' : null, y4L.length ? 'yard4' : null, ledRows.length ? 'ledger' : null].filter(Boolean), '登记到车 ' + d.date + ' ' + d.plate + (ledRows.length ? '（入出库记录第 ' + ledRows.join('、') + ' 行）' : ''), d.slipIds, true);
  });
  if (ledRows.length) toast('已同时记入「液态氧原料入出库记录」第 ' + ledRows.join('、') + ' 行');
  RP.k = loxL.length ? 'lox' : 'yard4'; RP.sel = null; rRender(true);
  requestAnimationFrame(() => { rLatest(); if (firstR) rSelect(firstR, 'E'); });
}

/* ---------- 识别群里每日用量截图 → 换算表一行 ---------- */
const R_GAS = { '40': 'B', '15': 'C', '10': 'D', '2': 'E' };
const R_LIQ = { '20': 'H', '25': 'I', '30': 'J', '35': 'K', '80': 'L', '100': 'M', '175': 'N', '195': 'O', '210': 'P', '500': 'Q', '1000': 'R' };
async function rOcrDaily() {
  const tab = rTab('conv'), rg = rRanges('conv'), def = rIso(rNextDate(rRaw(tab, 'A', rg.mainEnd)));
  const ov = dialog('识别每日用量截图 → 换算表', `<div class="row r2"><div><span class="lab">这是哪天的用量</span><input class="inp" type="date" id="odD" value="${def}"></div><div></div></div>
    <div class="r-drop" id="odDrop"><b>点这里选截图</b>，或 Ctrl+V 粘贴 / 拖进来<div class="muted">群里发的产品出库截图：编码 01 开头=气态，02 开头=液态；同规格自动相加；液态10L按0.5个20L填</div></div><div class="muted" id="odP"></div>`, [{ t: '取消' }], { nofocus: true });
  const run = async file => {
    const url = await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(file); });
    $('#odDrop', ov).innerHTML = `<img src="${url}" style="max-height:220px">`; const P = $('#odP', ov); P.textContent = '正在识别（本机离线识别，首次约需几秒加载）…';
    try {
      await loadOcr();
      // 先按表格线找出每一行、每一格单独识别（数字白名单、放大），合计对不上会换几种处理再试
      const res = await O2OCR.recognizeDaily(url, m => { if (m && m.text) P.textContent = m.text; else if (m && m.status === 'recognizing text') P.textContent = '正在识别… ' + Math.round((m.progress || 0) * 100) + '%'; });
      const date = rFromIso($('#odD', ov).value) || rNextDate(rRaw(tab, 'A', rg.mainEnd));
      ov.remove(); rOcrReview(date, res, url, file);
    } catch (e) { P.textContent = '识别失败：' + e.message; }
  };
  $('#odDrop', ov).onclick = async () => { const fs = await pickFiles('image/*'); if (fs[0]) run(fs[0]); };
  $('#odDrop', ov).addEventListener('dragover', e => e.preventDefault());
  $('#odDrop', ov).addEventListener('drop', e => { e.preventDefault(); const f = [...e.dataTransfer.files].find(x => x.type.startsWith('image/')); if (f) run(f); });
  const onPaste = e => { if (!document.body.contains(ov)) return document.removeEventListener('paste', onPaste); const it = [...(e.clipboardData || {}).items || []].find(x => x.type && x.type.startsWith('image/')); if (it) { e.preventDefault(); run(it.getAsFile()); } };
  document.addEventListener('paste', onPaste);
}
function rOcrReview(date, p, url, file) {
  const tab = rTab('conv'), rg = rRanges('conv');
  const exist = rConvRowOf(rIso(date));
  const v = {}; const add = (c, n) => { v[c] = Math.round(((v[c] || 0) + n) * 1000) / 1000; };
  Object.keys(p.gas).forEach(s => add(R_GAS[s] || 'F', p.gas[s]));
  Object.keys(p.liq).forEach(s => { if (s === '10') add('H', p.liq[s] * 0.5); else if (R_LIQ[s]) add(R_LIQ[s], p.liq[s]); else add('_x' + s, p.liq[s]); });
  const unknown = Object.keys(v).filter(k => k.startsWith('_x'));
  // 只填这次识别出来的数；没识别出的格子留空（不沿用以前的数）
  const cell = c => `<div class="oc"><span class="lab">${esc(rHeadLabel('conv', c))}</span><input class="inp sm num ${v[c] != null ? 'hit' : ''}" data-c="${c}" autocomplete="off" value="${v[c] != null ? v[c] : ''}"></div>`;
  const bad = p.rows.filter(x => x.qty == null || x.sure === false);
  const sum = p.rows.reduce((a, x) => a + (typeof x.qty === 'number' ? x.qty : 0), 0);
  const diff = p.total != null ? Math.round((p.total - sum) * 1000) / 1000 : null;
  const st = !p.rows.length ? '<span class="bad">没认出表格。请用电脑截图原尺寸（不要缩小、不要用手机拍屏幕），或直接在右边手填</span>'
    : p.total == null ? '<span class="bad">没找到截图里的「合计」，请逐行核对</span>'
    : p.totalOk && !bad.length ? `与截图「合计」${rFmt(p.total)} 一致 ✓` : `<span class="bad">各行相加 ${rFmt(sum)}，截图「合计」${rFmt(p.total)}${diff ? '，差 ' + rFmt(diff) : ''}。标黄的行请对照截图改右边的数</span>`;
  const html = `<div class="oc-wrap"><div><img src="${url}" class="oc-img" onclick="bigImg(this.src)"><div class="muted">识别到 ${p.rows.length} 行；${st}</div>
      <table class="t"><thead><tr><th>行</th><th>编码</th><th>类别</th><th>规格</th><th class="n">数量</th></tr></thead><tbody>${p.rows.map((r, i) => { const w = r.qty == null || r.sure === false; return `<tr${w ? ' style="background:#fff4d6"' : ''}><td class="muted">${r.rowNo || i + 1}</td><td>${esc(r.code || '')}</td><td>${r.kind === 'gas' ? '气态' : r.kind === 'liq' ? '液态' : '?'}</td><td>${r.spec ? esc(r.spec) + 'L' : '<span class="bad">没看清</span>'}</td><td class="n">${r.qty == null ? '<span class="bad">没看清</span>' : esc(rFmt(r.qty))}${r.qty != null && r.sure === false ? ' <span class="tag warn" title="几种处理识别的结果不一致，请核对">请核对</span>' : ''}</td></tr>`; }).join('')}</tbody></table></div>
    <div><div class="banner" style="background:#f5f6f8;color:var(--tx2)">日期 <b>${esc(date)}</b>${exist ? `：换算表第 ${exist} 行已有这天，保存会覆盖这几格` : '：保存后在换算表新增一行（损耗率沿用上一行）'}</div>
      <div class="lab">气态（个）</div><div class="oc-g">${['B', 'C', 'D', 'E', 'F'].map(cell).join('')}</div>
      <div class="lab" style="margin-top:10px">液态（个） <span class="muted">液态10L按0.5个20L填</span></div><div class="oc-g">${['H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R'].map(cell).join('')}</div>
      ${unknown.length ? `<div class="banner">有表里没有的液态规格：${unknown.map(k => k.slice(2) + 'L×' + v[k]).join('，')}（未填入）</div>` : ''}</div></div>`;
  dialog('核对识别结果 · ' + date, html, [{ t: '取消' }, { t: '保存到换算表', cls: 'pri', fn: async ov => {
    const vals = {}; $$('.oc input', ov).forEach(i => { vals[i.dataset.c] = i.value.trim(); });
    let r = exist, ph = null;
    try { ph = await uploadPhoto(file, { entity: 'report', tag: 'conv' }); } catch (e) { }
    await rAtomic(['conv'], async () => {
      let rr = exist; if (rr) Object.keys(vals).forEach(c => rSet(tab, c, rr, vals[c])); else rr = rAddConvRow(date, vals); r = rr;
      if (ph) { const row = rRow(tab, r); row.att = (row.att || []).concat([{ id: ph.id, path: ph.path, name: '用量截图' }]); }
      rDirty('conv'); await rSaveTabs(['conv'], '识别用量截图 ' + date, null, true);
    });
    RP.k = 'conv'; rRender(true); requestAnimationFrame(() => { rLatest(); rSelect(r, 'V'); });
    const tv = rEval('conv').val('V', r);
    if ((S.boot.settings.ocr || {}).ask_push !== false) setTimeout(async () => { if (await confirmBox(`${esc(date)} 当天总计 <b>${typeof tv === 'number' ? tv.toFixed(2) : rFmt(tv)}</b> 吨。<br>要把这个数写入「液态氧原料入出库记录」（出本库）吗？`, '写入入出库记录')) rPush(r); }, 60);
  } }], { wide: true });
}

/* ---------- 导入 / 恢复 ---------- */
async function rImport() {
  const fs = await pickFiles('.xlsx'); if (!fs[0]) return;
  if (!await confirmBox(`用「${esc(fs[0].name)}」替换文件里同名的表？<br><span class="muted">以后下载也以这个文件为格式模板；行照片按内容尽量保留；操作留痕。</span>`, '导入')) return;
  try { const r = await saveRaw('/api/report/import?name=' + encodeURIComponent(fs[0].name), fs[0], '导入报表'); for (const k of r.keys) { await rLoad(k); RP.scrolled[k] = false; } toast('已导入：' + r.keys.map(k => RT[k].short).join('、')); rRender(); } catch (e) { fail(e); }
}
async function rReset() {
  const k = RP.k; if (k === 'stock') return toast('到货总数由到货记录生成，不用恢复', true);
  if (!await confirmBox(`把「${RT[k].title}」恢复为系统内置的原表？<br><span class="muted">你对这张表的修改会被替换（建议先下载一份；操作留痕）。</span>`, '恢复')) return;
  try { await save('/api/report/reset', { key: k }, '恢复报表'); await rLoad(k); RP.scrolled[k] = false; rRender(); toast('已恢复'); } catch (e) { fail(e); }
}

/* ---------- 打印：表头行 + 选中的行，列宽 / 合并单元格与下载的 Excel 一致 ---------- */
function rPrintDlg(k) {
  const rg = rRanges(k);
  dialog('打印 ' + RT[k].title, `<div class="row r2"><div><span class="lab">打印哪些行</span><select class="inp" id="ppR"><option value="31">最近 31 行</option><option value="62">最近 62 行</option><option value="0">全部（第 ${RT[k].start}–${rg.mainEnd} 行）</option></select></div>
    <div><span class="lab">纸张</span><select class="inp" id="ppO"><option value="1">横向</option><option value="0">竖向</option></select></div></div><div class="hint">打印内容与下载的 Excel 一致（表头、合并单元格、列宽）。${RP.dirty[k] ? '<br>包含还没保存的修改。' : ''}</div>`,
    [{ t: '取消' }, { t: '打印', cls: 'pri', fn: ov => { rPrint(k, +$('#ppR', ov).value, $('#ppO', ov).value === '1'); } }]);
}
function rPrint(k, n, landscape) {
  const cfg = RT[k], tab = rTab(k), ev = rEval(k), rg = rRanges(k), W = tab.widths || { cols: {}, default: 9 };
  let cols = rCols(k); if (cfg.hideCols) cols = cols.filter(c => !cfg.hideCols.includes(c));
  const custom = rCustom(k), filt = rFiltered(k);
  const head = []; if (!custom) for (let r = 1; r <= cfg.head; r++) if (rHasVal(tab, r, cols)) head.push(r);
  const sums = {}; if (!filt) rAutoSums(k, ev).forEach(s => (sums[s.after] = sums[s.after] || []).push(s));
  let body = []; for (let r = cfg.start; r <= rg.mainEnd; r++) if (!filt || rRowOk(k, r, ev)) { body.push(r); (sums[r] || []).forEach(s => body.push(s)); }
  if (n) body = body.slice(-n);
  const show = head.concat(body), set = new Set(show);
  const skip = new Set(), span = {};
  tab.merges.forEach(m => {
    if (custom && (rPref(k).order || []).length) return;
    const [a, b] = m.split(':'); const A = O2.splitAddr(a), B = O2.splitAddr(b || a); if (!A || !B) return;
    const rs = show.filter(r => r >= A.r && r <= B.r), vc = cols.filter(c => rN(c) >= rN(A.c) && rN(c) <= rN(B.c)); if (!rs.length || !vc.length) return;
    rs.forEach(r => vc.forEach(c => skip.add(c + r))); skip.delete(vc[0] + rs[0]); span[vc[0] + rs[0]] = { rs: rs.length, cs: vc.length };
  });
  const tw = cols.reduce((a, c) => a + (W.cols[c] || W.default), 0);
  let h = `<div class="ttl">${esc(cfg.title)}</div><table style="table-layout:fixed"><colgroup>${cols.map(c => `<col style="width:${((W.cols[c] || W.default) / tw * 100).toFixed(2)}%">`).join('')}</colgroup>`;
  if (custom) h += '<tr style="font-weight:bold">' + cols.map(c => `<td>${esc(rLabel(k, c))}</td>`).join('') + '</tr>';
  show.forEach(r => {
    if (typeof r === 'object') { h += '<tr>' + cols.map(c => { const v = c === 'A' ? '合计' : r.vals[c]; return `<td>${esc(typeof v === 'number' ? v.toFixed(2) : (v || ''))}</td>`; }).join('') + '</tr>'; return; }
    const row = tab.rows[r - 1]; let tr = `<tr${r <= cfg.head ? ' style="font-weight:bold"' : ''}>`;
    cols.forEach(c => {
      if (skip.has(c + r)) return; const sp = span[c + r], cell = row && row.c[c];
      const v = cell ? (cell.f ? ev.val(c, r) : cell.v) : null;
      tr += `<td${sp ? ` rowspan="${sp.rs}" colspan="${sp.cs}"` : ''}${typeof v === 'string' && v.length > 6 ? ' class="l"' : ''}>${esc(rFmt(v, (cfg.dec2 || []).includes(c) && cell && cell.f))}</td>`;
    });
    h += tr + '</tr>';
  });
  printHtml(h + '</table>', { font: cols.length > 16 ? '7.5pt' : '9pt', landscape });
}
