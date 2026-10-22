/* 产品与库存（含盘点、批次追溯、U8 账面对照） */
'use strict';
const ST = { tab: 'list', cat: '', q: '', unk: false, sort: 'manual', dir: 1 };  // sort=manual 用库里的 sort 默认序；点表头可改
Pages.stock = async (el, arg) => {
  if (['list', 'count', 'batch', 'u8', 'moves'].includes(arg)) ST.tab = arg;
  el.innerHTML = UI.ph('产品与库存', '未盘点显示「未知」· 盘点后自动加减', '没盘点过的不显示 0、也不出负数；填实数后从这个数往后自动加减。',
    `<div class="seg" id="stTabs"><button data-t="list">产品库存</button><button data-t="count">盘点</button><button data-t="batch">批次追溯</button><button data-t="u8">U8 账面对照</button><button data-t="moves">库存变化记录</button></div>`)
    + `<div id="stBody"></div>`;
  $$('#stTabs button', el).forEach(b => { b.classList.toggle('on', b.dataset.t === ST.tab); b.onclick = () => App.tab('stock/' + b.dataset.t); });
  const body = $('#stBody', el);
  if (ST.tab === 'list') return stList(body);
  if (ST.tab === 'count') return stCount(body);
  if (ST.tab === 'batch') return stBatch(body);
  if (ST.tab === 'moves') return stMoves(body);
  return stU8(body);
};
const diffHtml = (a, b) => { if (a === null || a === undefined || b === null || b === undefined) return ''; const d = Math.round((a - b) * 1000) / 1000; return d ? `<span class="${d < 0 ? 'w30' : 'w7'}">${d > 0 ? '+' : ''}${d}</span>` : '<span class="muted">0</span>'; };

async function stList(el) {
  const r = await api('/api/products'); const cats = [...new Set(r.items.map(p => p.category))];
  el.innerHTML = `<div class="card page-card"><div class="tools">
    <div class="tg"><select class="inp" id="stCat"><option value="">全部分类</option>${cats.map(c => `<option ${ST.cat === c ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select>
    <input class="inp" id="stQ" placeholder="搜产品、U8 编码、备注" value="${esc(ST.q)}" style="width:190px">
    <label class="muted" style="font-size:13px"><input type="checkbox" id="stUnk" ${ST.unk ? 'checked' : ''}> 只看库存未知</label></div>
    <span class="sp"></span>
    <div class="tg acts">
      <button class="btn sm ${ST.sort === 'manual' ? 'pri' : ''}" id="stMan" title="用手动调好的默认顺序（↑↓ / 拖动保存）">手动顺序</button>
      <button class="btn sm" id="stMerge">合并重复产品</button>${LC.btn('stock')}<button class="btn sm pri" id="stNew">＋ 新增产品</button>
    </div></div><div id="stT"></div></div>`;
  const sk = (k, lab, cls) => {
    const on = ST.sort === k; const arrow = on ? (ST.dir > 0 ? ' ▲' : ' ▼') : '';
    return `<th class="sk ${cls || ''} ${on ? 'on' : ''}" data-sk="${k}" title="点击按${lab}排序">${lab}<span class="sa">${arrow}</span></th>`;
  };
  const stockKey = p => p.stock && p.stock.known ? p.stock.qty : -1e15;
  const u8Key = p => (p.u8 && p.u8.qty !== null && p.u8.qty !== undefined) ? p.u8.qty : -1e15;
  const cmp = (a, b) => {
    let va, vb;
    if (ST.sort === 'category') { va = a.category || ''; vb = b.category || ''; }
    else if (ST.sort === 'name') { va = a.name || ''; vb = b.name || ''; }
    else if (ST.sort === 'spec') { va = a.spec || ''; vb = b.spec || ''; }
    else if (ST.sort === 'unit') { va = a.unit || ''; vb = b.unit || ''; }
    else if (ST.sort === 'stock') { va = stockKey(a); vb = stockKey(b); }
    else if (ST.sort === 'u8') { va = u8Key(a); vb = u8Key(b); }
    else if (ST.sort === 'count') { va = (a.stock && a.stock.known) ? (a.stock.count_date || '') : ''; vb = (b.stock && b.stock.known) ? (b.stock.count_date || '') : ''; }
    else if (ST.sort === 'last') { va = a.last_move || ''; vb = b.last_move || ''; }
    else return (a.sort - b.sort) || (a.id - b.id);
    if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * ST.dir || (a.sort - b.sort) || (a.id - b.id);
    return String(va).localeCompare(String(vb), 'zh') * ST.dir || (a.sort - b.sort) || (a.id - b.id);
  };
  const draw = () => {
    const q = ST.q.trim().toLowerCase();
    let ps = r.items.filter(p => (!ST.cat || p.category === ST.cat) && (!q || (p.label + ' ' + p.u8_code + ' ' + p.aliases + ' ' + (p.remark || '')).toLowerCase().includes(q)) && (!ST.unk || !p.stock.known));
    ps = ps.slice().sort(cmp);
    const unk = r.items.filter(p => !p.stock.known).length;
    const man = ST.sort === 'manual';
    const ordTh = man ? '<th class="c" style="width:72px" title="上下调整后自动保存为默认顺序">顺序</th>' : '';
    $('#stT', el).innerHTML = `<div class="tw"><table class="t st-list" id="stTbl"><thead><tr>${ordTh}${sk('category', '分类')}${sk('name', '产品')}${sk('spec', '规格型号')}${sk('unit', '单位')}<th>U8库 · 存货编码</th>${sk('u8', 'U8账面数', 'n')}${sk('stock', '系统库存', 'n')}${sk('count', '上次盘点')}<th class="n">U8−系统</th>${sk('last', '最近变动')}<th>备注</th><th></th></tr></thead><tbody>
      ${ps.map((p, i) => `<tr draggable="${man ? 'true' : 'false'}" data-id="${p.id}">
        ${man ? `<td class="c st-ord"><button class="btn sm" data-up="${p.id}" ${i ? '' : 'disabled'} title="上移">↑</button><button class="btn sm" data-dn="${p.id}" ${i < ps.length - 1 ? '' : 'disabled'} title="下移">↓</button></td>` : ''}
        <td><span class="tag st-cat">${esc(p.category)}</span></td>
        <td class="st-name">${esc(p.name)}${p.batch_managed ? ' <span class="tag ac">批次</span>' : ''}${p.temp_name ? ' <span class="tag warn">暂用名</span>' : ''}${p.no_u8 ? ' <span class="tag">不入U8</span>' : ''}</td>
        <td class="muted">${esc(p.spec)}</td><td>${esc(p.unit)}</td>
        <td class="muted" style="font-size:12.5px">${esc([p.u8_wh, p.u8_code].filter(Boolean).join(' · '))}</td>
        <td class="n">${p.u8 && p.u8.qty !== null ? fmtN(p.u8.qty) : '<span class="unk">—</span>'}</td><td class="n st-stock">${stockHtml(p.stock)}</td>
        <td class="w muted">${p.stock.known ? esc(p.stock.count_date) + ' ' + esc(p.stock.count_by || '') : ''}</td>
        <td class="n">${diffHtml(p.u8 && p.u8.qty, p.stock.known ? p.stock.qty : null)}</td><td class="w muted">${esc(p.last_move)}</td>${rmkTd(p.remark)}
        ${rowActs({ ph: [0], main: ['修改', `data-ed="${p.id}"`], menu: [['盘点', `data-cnt="${p.id}"`], ['库存流水', `data-mv="${p.id}"`], ['删除', `data-del="${p.id}"`, 'd']] })}</tr>`).join('')}</tbody></table></div>
      <div class="hint">${ps.length} 个产品 · ${unk} 个库存未知 · 点表头排序（分类 / 名称 / 库存等）；「手动顺序」下用 ↑↓ 或拖动行，保存为默认顺序 · U8账面数只作参考</div>`;
    $('#stMan', el).classList.toggle('pri', man);
    bindDrag();
    const cols = [];
    if (man) cols.push({ k: '_ord', label: '顺序', w: 72 });
    cols.push(
      { k: 'cat', label: '分类', w: 72 }, { k: 'name', label: '产品', w: 140, prod: 1 },
      { k: 'spec', label: '规格型号', w: 100, wrap: 1 }, { k: 'unit', label: '单位', w: 44 },
      { k: 'u8c', label: 'U8库 · 存货编码', w: 120, hide: 1, wrap: 1 },
      { k: 'u8q', label: 'U8账面数', w: 72 }, { k: 'stk', label: '系统库存', w: 80 },
      { k: 'cnt', label: '上次盘点', w: 100, hide: 1 }, { k: 'diff', label: 'U8−系统', w: 72 },
      { k: 'last', label: '最近变动', w: 88, hide: 1 }, { k: 'rmk', label: '备注', w: 100, wrap: 1, hide: 1 },
      { k: '_act', label: '操作', w: 120 }
    );
    LC.apply($('#stTbl', el), 'stock', cols);
    if (typeof CellSel !== 'undefined') CellSel.on($('#stTbl', el));
  };
  const persistOrder = async (visIds) => {
    // 把可见列表的相对顺序写回完整列表：可见项按新顺序排在它们原先区间，其余不动相对位置
    const full = r.items.map(p => p.id);
    const set = new Set(visIds);
    let k = 0;
    const merged = full.map(id => set.has(id) ? visIds[k++] : id);
    await save('/api/product/reorder', { ids: merged }, '调整产品顺序');
    const order = Object.fromEntries(merged.map((id, i) => [id, (i + 1) * 10]));
    r.items.forEach(p => { p.sort = order[p.id] ?? p.sort; });
    r.items.sort((a, b) => (a.sort - b.sort) || (a.id - b.id));
    toast('已保存顺序');
  };
  const moveBy = async (id, dir) => {
    const q = ST.q.trim().toLowerCase();
    let ps = r.items.filter(p => (!ST.cat || p.category === ST.cat) && (!q || (p.label + ' ' + p.u8_code + ' ' + p.aliases + ' ' + (p.remark || '')).toLowerCase().includes(q)) && (!ST.unk || !p.stock.known));
    ps = ps.slice().sort(cmp);
    const vis = ps.map(p => p.id);
    const i = vis.indexOf(+id); const j = i + dir;
    if (i < 0 || j < 0 || j >= vis.length) return;
    [vis[i], vis[j]] = [vis[j], vis[i]];
    try { await persistOrder(vis); draw(); } catch (e) { fail(e); }
  };
  let dragId = null;
  const bindDrag = () => {
    if (ST.sort !== 'manual') return;
    const tb = $('#stT tbody', el); if (!tb) return;
    tb.ondragstart = e => { const tr = e.target.closest('tr[data-id]'); if (!tr) return; dragId = +tr.dataset.id; e.dataTransfer.effectAllowed = 'move'; tr.classList.add('st-drag'); };
    tb.ondragend = e => { const tr = e.target.closest('tr'); if (tr) tr.classList.remove('st-drag'); $$('.st-over', tb).forEach(x => x.classList.remove('st-over')); dragId = null; };
    tb.ondragover = e => { e.preventDefault(); const tr = e.target.closest('tr[data-id]'); if (!tr || +tr.dataset.id === dragId) return; $$('.st-over', tb).forEach(x => x.classList.remove('st-over')); tr.classList.add('st-over'); };
    tb.ondrop = async e => {
      e.preventDefault();
      const tr = e.target.closest('tr[data-id]'); if (!tr || dragId == null) return;
      const to = +tr.dataset.id; if (to === dragId) return;
      const q = ST.q.trim().toLowerCase();
      let ps = r.items.filter(p => (!ST.cat || p.category === ST.cat) && (!q || (p.label + ' ' + p.u8_code + ' ' + p.aliases + ' ' + (p.remark || '')).toLowerCase().includes(q)) && (!ST.unk || !p.stock.known));
      ps = ps.slice().sort(cmp);
      const vis = ps.map(p => p.id);
      const from = vis.indexOf(dragId), dest = vis.indexOf(to);
      if (from < 0 || dest < 0) return;
      vis.splice(from, 1); vis.splice(dest, 0, dragId);
      try { await persistOrder(vis); draw(); } catch (er) { fail(er); }
    };
  };
  $('#stCat', el).onchange = e => { ST.cat = e.target.value; draw(); };
  $('#stQ', el).oninput = e => { ST.q = e.target.value; draw(); };
  $('#stUnk', el).onchange = e => { ST.unk = e.target.checked; draw(); };
  $('#stMan', el).onclick = () => { ST.sort = 'manual'; ST.dir = 1; draw(); };
  $('#stNew', el).onclick = () => editProduct(null, () => stList(el));
  $('#stMerge', el).onclick = () => mergeDlg(r.items, () => stList(el));
  $('#stT', el).onclick = async e => {
    const t = e.target.closest('[data-sk],[data-ed],[data-cnt],[data-mv],[data-del],[data-up],[data-dn]') || e.target;
    const p = id => r.items.find(x => x.id === +id);
    if (t.dataset && t.dataset.sk) {
      const k = t.dataset.sk;
      if (ST.sort === k) ST.dir = -ST.dir; else { ST.sort = k; ST.dir = 1; }
      draw(); return;
    }
    if (t.dataset && t.dataset.up) return moveBy(t.dataset.up, -1);
    if (t.dataset && t.dataset.dn) return moveBy(t.dataset.dn, 1);
    if (t.dataset && t.dataset.cnt) countDlg(p(t.dataset.cnt), () => stList(el));
    if (t.dataset && t.dataset.ed) editProduct(p(t.dataset.ed), () => stList(el));
    if (t.dataset && t.dataset.mv) movesDlg(p(t.dataset.mv));
    if (t.dataset && t.dataset.del) {
      try {
        if (!await confirmDelete('product', +t.dataset.del, '/api/product/delete')) return;
        toast('已删除'); await loadBoot(); stList(el);
      } catch (er) { fail(er); }
    }
  };
  draw();
}

function editProduct(p, done) {
  const s = S.boot.settings; p = p || { name: '', spec: '', category: '其他', unit: '个', batch_managed: 0, temp_name: 0, location: '', remark: '' };
  dialog(p.id ? '修改产品' : '新增产品', `<div class="row r2">
    <div><span class="lab">名称</span><input class="inp" id="epN" value="${esc(p.name)}"></div><div><span class="lab">规格型号</span><input class="inp" id="epS" value="${esc(p.spec)}"></div>
    <div><span class="lab">分类</span><select class="inp" id="epC">${[...new Set(s.categories.concat([p.category]))].map(c => `<option ${p.category === c ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select></div>
    <div><span class="lab">单位</span><input class="inp" id="epU" value="${esc(p.unit)}"></div>
    <div><span class="lab">存放位置</span><input class="inp" id="epL" value="${esc(p.location || '')}"></div><div><span class="lab">备注</span><input class="inp" id="epR" value="${esc(p.remark || '')}"></div></div>
    <div style="margin-top:12px;display:flex;gap:20px"><label><input type="checkbox" id="epB" ${p.batch_managed ? 'checked' : ''}> 批次管理（批号/生产日期/有效期，出库先进先出）</label>
    <label><input type="checkbox" id="epT" ${p.temp_name ? 'checked' : ''}> 暂用叫法（以后改真名）</label>
    <label title="如厂内自用配件、工程材料：登记到货时默认选「不用入U8」"><input type="checkbox" id="epNU" ${p.no_u8 ? 'checked' : ''}> 默认不入U8</label></div>
    ${p.aliases && p.aliases !== '[]' ? `<div class="hint">曾用名：${esc(JSON.parse(p.aliases).join('、'))}</div>` : ''}`,
    [p.id ? { t: '删除', cls: 'danger', fn: async ov => {
      // 先关掉编辑窗再确认删除，避免三层弹窗叠在一起点 ✕ 把 Promise 挂死
      ov.remove();
      try {
        if (!await confirmDelete('product', p.id, '/api/product/delete')) return false;
        toast('已删除'); await loadBoot(); done();
      } catch (e) { fail(e); }
      return false;
    } } : null, { t: '取消' },
    { t: '保存', cls: 'pri', fn: async ov => {
      const d = { id: p.id, name: $('#epN', ov).value.trim(), spec: $('#epS', ov).value.trim(), category: $('#epC', ov).value, unit: $('#epU', ov).value.trim(), location: $('#epL', ov).value, remark: $('#epR', ov).value, batch_managed: $('#epB', ov).checked ? 1 : 0, temp_name: $('#epT', ov).checked ? 1 : 0, no_u8: $('#epNU', ov).checked ? 1 : 0 };
      await save('/api/product/save', { data: d }, '保存产品'); toast('已保存'); await loadBoot(); done();
    } }].filter(Boolean));
}

function mergeDlg(items, done) {
  dialog('合并重复产品', `<div class="muted" style="font-size:13px">例如「便携式制氧机电池」有两条：选保留哪一条，把另一条的出入库记录都并过来；被并掉的名称记为曾用名。</div>
    <div class="row r2" style="margin-top:12px"><div><span class="lab">保留</span><select class="inp" id="mgK">${items.map(p => `<option value="${p.id}">${esc(p.label)}（${esc(p.category)}）</option>`).join('')}</select></div>
    <div><span class="lab">并掉（并入左边）</span><select class="inp" id="mgD">${items.map(p => `<option value="${p.id}">${esc(p.label)}（${esc(p.category)}）</option>`).join('')}</select></div></div>`,
    [{ t: '取消' }, { t: '合并', cls: 'pri', fn: async ov => {
      const k = +$('#mgK', ov).value, d = +$('#mgD', ov).value; if (k === d) throw new Error('两边选了同一个');
      if (!await confirmBox(`把「${esc(P.label(d))}」并入「${esc(P.label(k))}」？`, '合并')) return false;
      await save('/api/product/merge', { keep: k, drop: [d] }, '合并产品'); toast('已合并'); await loadBoot(); done();
    } }]);
}

function countDlg(p, done) {
  const bs = p.batch_managed ? (p.batches || []).filter(b => b.id) : [];
  dialog('盘点：' + p.label, `<div class="kv"><dt>系统库存</dt><dd>${stockHtml(p.stock)} ${esc(p.unit)}</dd>${p.stock.known ? `<dt>上次盘点</dt><dd>${esc(p.stock.count_date)} 实数 ${fmtN(p.stock.count_qty)}（${esc(p.stock.count_by || '')}）</dd>` : ''}</div>
    ${bs.length ? `<div class="sec-h" style="margin-top:14px"><h2>按批次点数</h2><small>合计即产品实数</small></div><table class="t"><thead><tr><th>批号</th><th>有效期</th><th class="n">系统剩余</th><th style="width:110px">实数</th></tr></thead><tbody>
      ${bs.map(b => `<tr><td>${esc(b.batch_no)}</td><td>${esc(b.expiry)}</td><td class="n">${fmtN(b.remain)}</td><td><input class="inp sm num" data-bn="${esc(b.batch_no)}"></td></tr>`).join('')}</tbody></table>`
      : `<div style="margin-top:14px"><span class="lab">实数（数清楚后填）</span><input class="inp num" id="cQ" inputmode="decimal" style="width:160px;font-size:18px;font-weight:600"></div>`}
    <div class="row r2" style="margin-top:12px"><div><span class="lab">盘点日期</span><input class="inp" type="date" id="cD" value="${today()}"></div><div><span class="lab">备注</span><input class="inp" id="cN"></div></div>
    <div class="hint">盘点日期当天、在这次盘点之前录的单据算在实数里；之后录的单据从实数往后加减。差额记「盘点调整」（谁、哪天）。</div>`,
    [{ t: '取消' }, { t: '保存盘点', cls: 'pri', fn: async ov => {
      const b = {}; $$('[data-bn]', ov).forEach(i => { if (i.value.trim() !== '') b[i.dataset.bn] = +i.value; });
      const q = $('#cQ', ov) ? $('#cQ', ov).value.trim() : '';
      if (!bs.length && q === '') throw new Error('请填实数');
      if (bs.length && !Object.keys(b).length) throw new Error('请至少填一个批次的实数');
      const r = await save('/api/count/save', { product_id: p.id, qty: q, batches: bs.length ? b : null, date: $('#cD', ov).value, note: $('#cN', ov).value }, '保存盘点');
      toast('已盘点：' + p.label + ' ' + fmtN(r.stock.qty)); done();
    } }]);
}

async function movesDlg(p, showDaily) {
  const r = await api('/api/product/moves?id=' + p.id + (showDaily ? '&daily=1' : ''));
  const src = { out: '出库', arrival: '到货', daily: '产品出入库情况', loan: '借用/归还' };
  const ov = dialog('库存流水：' + p.label, `<div class="kv" style="margin-bottom:10px"><dt>系统库存</dt><dd>${stockHtml(r.stock)}</dd><dt>U8</dt><dd>${r.u8.map(u => esc(u.wh + ' ' + u.code + ' ' + u.name + ' ' + u.spec) + (u.qty !== null ? ' 账面 ' + fmtN(u.qty) : '')).join('<br>') || '—'}</dd></div>
    ${r.counts.length ? `<div class="sec-h"><h2>盘点记录</h2></div><table class="t" style="margin-bottom:12px"><thead><tr><th>日期</th><th>批号</th><th class="n">实数</th><th class="n">当时系统数</th><th class="n">盘点调整</th><th>谁</th><th>备注</th></tr></thead><tbody>${r.counts.map(c => `<tr><td>${esc(c.date)}</td><td>${esc(c.batch_no)}</td><td class="n">${fmtN(c.qty)}</td><td class="n">${c.computed_before === null ? '<span class="unk">未知</span>' : fmtN(c.computed_before)}</td><td class="n">${c.diff === null ? '' : (c.diff > 0 ? '+' : '') + fmtN(c.diff)}</td><td>${esc(c.created_by)}</td>${rmkTd(c.note)}</tr>`).join('')}</tbody></table>` : ''}
    <div class="sec-h"><h2>出入库流水</h2><small>最近 200 条${r.hidden_daily ? ` · 已隐藏交接表批量配送 ${r.hidden_daily} 条 <a class="link" data-showd="1">临时显示</a>` : ''}</small></div><table class="t"><thead><tr><th>日期</th><th>来源</th><th>说明</th><th>批号</th><th class="n">数量</th></tr></thead><tbody>
    ${r.moves.map(m => `<tr class="clk" data-src="${esc(m.src)}:${m.src_id}" title="点开看原始记录"><td class="w">${esc(m.date)}</td><td><a class="link">${esc(src[m.src] || m.src)} ↗</a></td><td>${esc(moveLabelDisp(m.label))}</td><td>${esc(m.batch_no)}</td><td class="n" style="color:${m.qty > 0 ? 'var(--ok)' : 'inherit'}">${m.qty > 0 ? '+' : ''}${fmtN(m.qty)}</td></tr>`).join('') || '<tr><td colspan="5" class="muted">没有流水</td></tr>'}</tbody></table>`, null, { wide: true });
  ov.addEventListener('click', e => { if (e.target.dataset.showd) { ov.remove(); return movesDlg(p, true).catch(fail); } const t = e.target.closest('[data-src]'); if (t) { const [k, id] = t.dataset.src.split(':'); recView(k, +id).catch(fail); } });
}

/* ---------- 盘点：一个一个慢慢盘 ---------- */
async function stCount(el) {
  const [r, cs] = await Promise.all([api('/api/products'), api('/api/counts')]);
  el.innerHTML = `<div class="grid2 sc-count"><div class="card"><div class="tools"><input class="inp" id="scQ" placeholder="搜产品" style="width:220px"><label class="muted" style="font-size:13px"><input type="checkbox" id="scU" checked> 先盘未知的</label>
      <span class="sp"></span><button class="btn" id="scPrint">打印盘点清单</button><button class="btn" id="scDown">下载盘点清单</button></div><div id="scT" class="tw sc-main"></div></div>
    <div class="card sc-recent"><div class="card-h"><h2>最近盘点 / 盘点调整</h2><small class="muted">横排 · 悬停看全文</small></div><div class="tw"><table class="t t-side"><thead><tr><th>日期</th><th class="ellip">产品</th><th class="n">实数</th><th class="n">调整</th><th class="ellip-who">谁</th><th>备注</th></tr></thead><tbody>
      ${cs.items.slice(0, 40).map(c => { const nm = (c.pname || '') + (c.pspec ? ' ' + c.pspec : ''); const who = c.created_by || ''; return `<tr><td class="w">${esc(c.date)}</td><td class="ellip" title="${esc(nm)}">${esc(nm)}</td><td class="n">${fmtN(c.qty)}</td><td class="n">${c.diff === null ? '<span class="muted">首次</span>' : (c.diff > 0 ? '+' : '') + fmtN(c.diff)}</td><td class="ellip ellip-who" title="${esc(who)}">${esc(who)}</td>${rmkTd(c.note)}</tr>`; }).join('') || '<tr><td colspan="6" class="muted">还没盘点过</td></tr>'}</tbody></table></div></div></div>`;
  const draw = () => {
    const q = $('#scQ', el).value.trim(); const u = $('#scU', el).checked;
    const ps = r.items.filter(p => !q || p.label.includes(q)).sort((a, b) => u ? (a.stock.known - b.stock.known) : 0);
    $('#scT', el).innerHTML = `<table class="t"><thead><tr><th>产品</th><th>单位</th><th class="n">系统库存</th><th>上次盘点</th><th style="width:120px">实数</th><th style="width:170px">备注</th><th style="width:70px"></th></tr></thead><tbody>
      ${ps.map(p => `<tr><td>${esc(p.label)}${p.batch_managed ? ' <span class="tag ac">批次</span>' : ''}</td><td>${esc(p.unit)}</td><td class="n">${stockHtml(p.stock)}</td><td class="muted w">${p.stock.known ? esc(p.stock.count_date) : ''}</td>
        <td>${p.batch_managed ? '<span class="muted" style="font-size:12.5px">按批次</span>' : `<input class="inp sm num" data-q="${p.id}" inputmode="decimal">`}</td><td>${p.batch_managed ? '' : `<input class="inp sm" data-nq="${p.id}" placeholder="可不填">`}</td><td><button class="btn sm" data-sv="${p.id}">${p.batch_managed ? '盘点…' : '保存'}</button></td></tr>`).join('')}</tbody></table>`;
  };
  $('#scQ', el).oninput = draw; $('#scU', el).onchange = draw;
  $('#scDown', el).onclick = () => download('/api/count/sheet.xlsx');
  $('#scPrint', el).onclick = () => printApi('/api/count/sheet.xlsx', { font: '10.5pt' }).catch(fail);
  $('#scT', el).onclick = async e => {
    const id = +e.target.dataset.sv; if (!id) return; const p = r.items.find(x => x.id === id);
    if (p.batch_managed) return countDlg(p, () => stCount(el));
    const v = $(`[data-q="${id}"]`, el).value.trim(); if (v === '') return toast('请填实数', true);
    try { const x = await save('/api/count/save', { product_id: id, qty: v, date: today(), note: ($(`[data-nq="${id}"]`, el) || {}).value || '' }, '盘点 ' + p.label); toast('已盘点 ' + p.label + '：' + fmtN(x.stock.qty)); stCount(el); } catch (er) { fail(er); }
  };
  draw();
}

/* ---------- 批次追溯 ---------- */
async function stBatch(el) {
  const r = await api('/api/batches'); const bq = (stBatch.q || '').trim();
  const hit = b => !bq || [b.batch_no, b.remark, b.prod_date, b.expiry].some(x => (x || '').includes(bq));
  const prods = r.items.map(p => Object.assign({}, p, { batches: p.batches.filter(hit) })).filter(p => !bq || p.batches.length || p.label.includes(bq));
  const negN = prods.reduce((n, p) => n + p.batches.filter(b => b.remain < 0).length, 0);
  el.innerHTML = `<div class="tools" style="margin-bottom:12px"><input class="inp" id="bQ" placeholder="搜批号、备注" value="${esc(bq)}" style="width:220px">${negN ? `<span class="tag bad" style="margin-left:10px">${negN} 个负批需核对</span><span class="muted" style="margin-left:8px;font-size:12.5px">负库存是错账（以前没换批扣穿），不是功能；新出库已堵住，这里不自动抹平历史</span>` : ''}</div>` + prods.map(p => `<div class="card"><div class="card-h"><h2>${esc(p.label)} <small>${p.batches.length} 个批次</small></h2><div class="split"><button class="btn sm" data-pr="${p.id}">打印全部批次</button><button class="btn sm" data-ex="${p.id}">导出全部批次（药监检查）</button></div></div>
    <table class="t"><thead><tr><th>批号</th><th>生产日期</th><th>有效期至</th><th class="n">到货</th><th class="n">出库</th><th class="n">剩余</th><th>备注</th><th></th></tr></thead><tbody>
    ${p.batches.map(b => `<tr><td>${esc(b.batch_no)}${b.id ? '' : ' <span class="tag warn">未登记</span>'}</td><td>${esc(b.prod_date)}</td><td class="${b.expiring ? 'w7' : ''}">${esc(b.expiry)}${b.expiring ? ' <span class="tag warn">临近效期</span>' : ''}</td>
      <td class="n">${fmtN(b.in_qty)}</td><td class="n">${fmtN(b.out_qty)}</td><td class="n">${b.remain < 0 ? `<span class="tag bad" title="负剩余 ${fmtN(b.remain)}：多半是以前出库没换批扣穿的，不是正常状态；新出库请用正剩余批，本页不自动抹平">${fmtN(b.remain)} 需核对</span>` : fmtN(b.remain)}</td>${rmkTd(b.id ? b.remark : '')}
      ${rowActs({ ph: [0], main: b.id ? ['修改', `data-eb="${b.id}" data-p="${p.id}"`] : null, menu: [['去向', `data-tr="${p.id}" data-bn="${esc(b.batch_no)}"`], ['导出', `data-x1="${p.id}" data-bn="${esc(b.batch_no)}"`]] })}</tr>`).join('') || '<tr><td colspan="8" class="muted">还没有批次（到货时填批号）</td></tr>'}</tbody></table></div>`).join('') || '<div class="card"><div class="empty">没有启用批次管理的产品（在产品「改」里勾选）</div></div>';
  let bt; $('#bQ', el).oninput = e => { clearTimeout(bt); const v = e.target.value; bt = setTimeout(() => { stBatch.q = v; stBatch(el).then(() => { const i = $('#bQ', el); i.focus(); i.setSelectionRange(v.length, v.length); }); }, 300); };
  el.onclick = async e => {
    const t = e.target;
    if (t.dataset.ex) download('/api/batch/trace.xlsx?product_id=' + t.dataset.ex);
    if (t.dataset.pr) printApi('/api/batch/trace.xlsx?product_id=' + t.dataset.pr, { font: '10.5pt' }).catch(fail);
    if (t.dataset.x1) download('/api/batch/trace.xlsx?product_id=' + t.dataset.x1 + '&batch_no=' + encodeURIComponent(t.dataset.bn));
    if (t.dataset.tr) {
      const x = await api('/api/batch/trace?product_id=' + t.dataset.tr + '&batch_no=' + encodeURIComponent(t.dataset.bn));
      const html = `<table class="t"><thead><tr><th>日期</th><th>入/出</th><th>来源 / 去向</th><th class="n">入</th><th class="n">出</th><th class="n">结存</th></tr></thead><tbody>${x.rows.map(r => `<tr><td class="w">${esc(r.date)}</td><td>${r.type}</td><td>${esc(r.who)}</td><td class="n">${fmtN(r.in)}</td><td class="n">${fmtN(r.out)}</td><td class="n">${fmtN(r.bal)}</td></tr>`).join('')}</tbody></table>`;
      dialog(x.product + ' · 批号 ' + t.dataset.bn, html, [{ t: '打印', fn: () => { printApi('/api/batch/trace.xlsx?product_id=' + t.dataset.tr + '&batch_no=' + encodeURIComponent(t.dataset.bn), { font: '10.5pt' }).catch(fail); return false; } }, { t: '导出 Excel', fn: () => { download('/api/batch/trace.xlsx?product_id=' + t.dataset.tr + '&batch_no=' + encodeURIComponent(t.dataset.bn)); return false; } }, { t: '关闭' }], { wide: true });
    }
    if (t.dataset.eb) {
      const p = r.items.find(x => x.id === +t.dataset.p); const b = p.batches.find(x => x.id === +t.dataset.eb);
      dialog('批次 ' + b.batch_no, `<div class="row r2"><div><span class="lab">生产日期</span><input class="inp" type="date" id="bP" value="${esc(b.prod_date)}"></div><div><span class="lab">有效期至</span><input class="inp" type="date" id="bE" value="${esc(b.expiry)}"></div></div><div style="margin-top:10px"><span class="lab">备注</span><input class="inp" id="bR" value="${esc(b.remark || '')}" placeholder="可不填"></div>`,
        [{ t: '取消' }, { t: '保存', cls: 'pri', fn: async ov => { await save('/api/batch/save', { data: { id: b.id, prod_date: $('#bP', ov).value, expiry: $('#bE', ov).value, remark: $('#bR', ov).value.trim() } }, '修改批次'); stBatch(el); } }]);
    }
  };
}

/* ---------- U8 账面对照（疑似匹配待确认） ---------- */
async function stU8(el) {
  const r = await api('/api/u8');
  const rev = r.items.filter(u => u.match === '待确认');
  const tagOf = m => ({ '自动匹配': 'ok', '已确认': 'ok', '新产品': 'ac', '待确认': 'warn', '不对应': '' }[m] || '');
  el.innerHTML = `<div class="card page-card"><div class="tools"><span class="tx2">U8 账面目录（物料库 / 器械库 / 药品原料库）。账面数只作参考，实际库存以盘点为准。</span><span class="sp"></span>
    <button class="btn" id="u8Imp">导入 U8 账面 Excel</button></div>
    ${rev.length ? `<div class="banner">${rev.length} 条疑似对应，需要你确认（不确认就不会合并）</div>` : ''}
    <div class="tw"><table class="t"><thead><tr><th>U8库</th><th>存货编码</th><th>存货名称</th><th>规格型号</th><th>单位</th><th class="n">U8账面数</th><th>对应产品</th><th>状态</th><th class="n">系统库存</th><th class="n">差额</th><th>说明</th><th></th></tr></thead><tbody>
    ${r.items.map(u => `<tr><td class="w">${esc(u.wh)}</td><td>${esc(u.code)}</td><td>${esc(u.name)}</td><td>${esc(u.spec)}</td><td>${esc(u.unit)}</td><td class="n">${u.qty === null ? '<span class="unk">—</span>' : fmtN(u.qty)}</td>
      <td>${u.match === '待确认' ? `<span class="muted">建议：</span>${esc((u.sname || '') + (u.sspec ? ' ' + u.sspec : ''))}` : esc((u.pname || '') + (u.pspec ? ' ' + u.pspec : ''))}</td>
      <td class="w"><span class="tag ${tagOf(u.match)}">${esc(u.match)}</span></td><td class="n">${u.product_id ? stockHtml(u.stock) : ''}</td>
      <td class="n">${u.stock && u.stock.known ? diffHtml(u.qty, u.stock.qty) : ''}</td><td class="muted" style="font-size:12.5px">${esc(u.note)}</td>
      <td class="w">${u.match === '待确认' ? `<a data-ok="${u.id}">确认</a> · ` : ''}<a data-ch="${u.id}">改对应</a></td></tr>`).join('')}</tbody></table></div></div>`;
  $('#u8Imp', el).onclick = async () => {
    try {
      const [f] = await pickFiles('.xlsx'); if (!f) return;
      const x = await saveRaw('/api/u8/import?as_of=' + today(), f, '导入 U8 账面');
      toast(`已导入 ${x.rows} 行`); await loadBoot(); stU8(el);
    } catch (e) { fail(e); }
  };
  el.onclick = async e => {
    const t = e.target; const u = id => r.items.find(x => x.id === +id);
    try {
      if (t.dataset.ok) { await save('/api/u8/confirm', { id: +t.dataset.ok }, '确认对应'); toast('已确认'); await loadBoot(); stU8(el); }
      if (t.dataset.ch) {
        const x = u(t.dataset.ch);
        const ov = dialog(`U8 ${x.wh} ${x.code} ${x.name} ${x.spec}`, `<span class="lab">对应到哪个产品</span><input class="inp" id="u8P" placeholder="搜产品">
          <div class="hint">同一个产品可以对应多个 U8 编码 / 多个 U8 库（如 8062 在物料库、器械库都有）。</div>`,
          [{ t: '不对应任何产品', fn: async () => { await save('/api/u8/confirm', { id: x.id, none: true }, '设为不对应'); stU8(el); } },
           { t: '建为新产品', fn: async () => { await save('/api/u8/confirm', { id: x.id, new_product: true }, '建新产品'); await loadBoot(); stU8(el); } },
           { t: '保存', cls: 'pri', fn: async ov => { if (!ov._pid) throw new Error('先选产品'); await save('/api/u8/confirm', { id: x.id, product_id: ov._pid }, '改对应'); await loadBoot(); stU8(el); } }]);
        const pi = $('#u8P', ov); autoComplete(pi, async q => P.search(q).slice(0, 10), p => { ov._pid = p.id; pi.value = p.label; }, (p, q) => hl(p.label, q));
      }
    } catch (er) { fail(er); }
  };
}

/* ---------- 库存变化记录：全部产品的每一笔变化（交接表、出库、到货、借用、归还、盘点调整），点一行看原始记录 ---------- */
const MV = { from: today().slice(0, 8) + '01', to: '', product_id: '', src: '', q: '', offset: 0, daily: '', hide_daily: '', _inited: false };
async function stMoves(el) {
  // 本页勾选「隐藏交接表批量配送」：只影响这一页显示（可覆盖设置）；第一次进来跟「设置 → 其他」一致
  if (!MV._inited) {
    MV._inited = true;
    if (S.boot.settings.moves_show_daily === false) { MV.hide_daily = '1'; MV.daily = ''; }
  }
  const ps = (await api('/api/products')).items;
  const srcs = [['daily', '交接表 / 出入库情况'], ['out', '出库'], ['arrival', '到货'], ['loan', '借用'], ['return', '归还'], ['count', '盘点']];
  const hideOn = MV.hide_daily === '1' || (MV.hide_daily === '' && MV.daily === '' && S.boot.settings.moves_show_daily === false);
  el.innerHTML = `<div class="card page-card"><div class="tools">
    <div class="tg"><input class="inp" type="date" id="mvFrom" value="${MV.from}" style="width:132px"><span class="muted">至</span><input class="inp" type="date" id="mvTo" value="${MV.to}" style="width:132px">
    <select class="inp" id="mvP" style="max-width:200px"><option value="">全部产品</option>${ps.map(p => `<option value="${p.id}" ${+MV.product_id === p.id ? 'selected' : ''}>${esc(p.label)}</option>`).join('')}</select>
    <select class="inp" id="mvS"><option value="">全部来源</option>${srcs.map(([k, t]) => `<option value="${k}" ${MV.src === k ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select>
    <input class="inp" id="mvQ" placeholder="搜配送员、客户、单位、批号、说明" value="${esc(MV.q)}" style="width:200px">
    <label class="muted" style="font-size:13px;white-space:nowrap" title="只是不显示；库存、结存照算"><input type="checkbox" id="mvHideD" ${hideOn ? 'checked' : ''}> 隐藏交接表批量配送</label></div>
    <span class="sp"></span><div class="tg acts"><button class="btn sm" id="mvPrint">打印</button><button class="btn sm" id="mvExp">下载 Excel</button>${LC.btn('moves')}</div>
  </div><div id="mvT"></div></div>`;
  const qs = (all) => Object.entries(MV).filter(([k, v]) => k[0] !== '_' && (v !== '' || k === 'from') && (!all || k !== 'offset')).map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&');
  const n = x => x === null || x === undefined ? '' : `<span style="color:${x > 0 ? 'var(--ok)' : 'inherit'}">${x > 0 ? '+' : ''}${fmtN(x)}</span>`;
  const hidNote = r => r.hidden_daily ? ` · <span class="muted">已隐藏交接表批量配送 ${r.hidden_daily} 条</span>` : '';
  const load = async () => {
    const r = await api('/api/moves?' + qs() + '&limit=200'); const one = r.single;
    const pg = r.total > r.limit ? `<span class="sp"></span><button class="btn sm" id="mvPrev" ${r.offset ? '' : 'disabled'}>上一页</button><span class="muted">第 ${r.offset + 1}–${Math.min(r.total, r.offset + r.limit)} 条</span><button class="btn sm" id="mvNext" ${r.offset + r.limit < r.total ? '' : 'disabled'}>下一页</button>` : '';
    $('#mvT', el).innerHTML = r.items.length ? `<div class="tw"><table class="t mv" id="mvTbl"><thead><tr><th>日期</th><th>产品</th><th>来源</th><th>说明</th><th>批号</th><th class="n">数量</th>${one ? '<th class="n" title="这一笔之后的库存（从盘点实数往后加减；第一次盘点以前不知道）">结存</th>' : ''}</tr></thead><tbody>
      ${r.items.map(x => `<tr class="clk" data-rec="${esc(x.entity)}:${x.src_id}" title="点开看原始记录"><td class="w">${esc(x.date)}</td><td>${esc(x.product)}</td><td class="w"><a class="link">${esc(x.src_cn)} ↗</a></td><td>${esc(moveLabelDisp(x.label))}</td><td class="w">${esc(x.batch_no)}</td>
        <td class="n">${x.src === 'count' ? (x.qty === null ? '<span class="muted">—</span>' : `<span title="盘点调整（实数 − 当时系统数）">${n(x.qty)}</span>`) : n(x.qty)}</td>${one ? `<td class="n">${x.bal === null || x.bal === undefined ? '<span class="unk">未知</span>' : fmtN(x.bal)}</td>` : ''}</tr>`).join('')}</tbody></table></div>
      <div class="hint" style="display:flex;gap:10px;align-items:center;margin-bottom:2px">共 ${r.total} 条 · 入 <b style="color:var(--ok)">+${fmtN(r.sum.in)}</b> · 出 <b>${fmtN(r.sum.out)}</b>${r.sum.adj ? ' · 盘点调整 ' + n(r.sum.adj) : ''}${one ? '' : ' · 选一个产品可看每笔之后的结存'}${hidNote(r)}${pg}</div>` : `<div class="empty">这段时间没有库存变化${hidNote(r)}</div>`;
    if (r.items.length) {
      const mcols = [
        { k: 'date', label: '日期', w: 88 }, { k: 'prod', label: '产品', w: 140, prod: 1 },
        { k: 'src', label: '来源', w: 100 }, { k: 'lab', label: '说明', w: 180, wrap: 1 },
        { k: 'batch', label: '批号', w: 88, hide: 1 }, { k: 'qty', label: '数量', w: 64 }
      ];
      if (one) mcols.push({ k: 'bal', label: '结存', w: 64 });
      LC.apply($('#mvTbl', el), 'moves', mcols);
    if (typeof CellSel !== 'undefined') CellSel.on($('#mvTbl', el));
    }
    const pv = $('#mvPrev', el), nx = $('#mvNext', el);
    if (pv) pv.onclick = () => { MV.offset = Math.max(0, r.offset - r.limit); load().catch(fail); };
    if (nx) nx.onclick = () => { MV.offset = r.offset + r.limit; load().catch(fail); };
  };
  const bind = (id, k) => { $(id, el).onchange = e => { MV[k] = e.target.value; MV.offset = 0; load().catch(fail); }; };
  bind('#mvFrom', 'from'); bind('#mvTo', 'to'); bind('#mvP', 'product_id'); bind('#mvS', 'src');
  let tm; $('#mvQ', el).oninput = e => { clearTimeout(tm); tm = setTimeout(() => { MV.q = e.target.value; MV.offset = 0; load().catch(fail); }, 250); };
  $('#mvHideD', el).onchange = e => {
    if (e.target.checked) { MV.hide_daily = '1'; MV.daily = ''; }
    else { MV.hide_daily = ''; MV.daily = '1'; }   // 强制显示（覆盖设置里关掉的情况）
    MV.offset = 0; load().catch(fail);
  };
  $('#mvExp', el).onclick = () => download('/api/moves.xlsx?' + qs(true));
  $('#mvPrint', el).onclick = () => printApi('/api/moves.xlsx?' + qs(true), { landscape: true }).catch(fail);
  $('#mvT', el).addEventListener('click', e => { if (e.target.closest('button')) return; const t = e.target.closest('[data-rec]'); if (t) { const [k, id] = t.dataset.rec.split(':'); recView(k, +id).catch(fail); } });
  await load();
}
