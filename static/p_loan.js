/* 借用归还：借出登记 · 借用记录（归还/部分归还/定数） · 按单位 · 补录手写借用本 */
'use strict';
const LN = { tab: 'list', form: null, f: { status: 'open', source: '', org: '', q: '', from: '', to: '', deleted: '' }, org: '' };
/* 随车技术人员：只有特定「一院」类单位借用才有。默认不显示；选了含「一院」的单位自动出现；已有内容的老单照常显示；也可点「+随车人员」手动打开 */
const hasYiyuan = orgs => (orgs || []).some(o => /一院/.test(o || ''));
const escOn = f => !!(f._esc || hasYiyuan(f.orgs) || (f.escort || '').trim() || (f.phone || '').trim());
function newLoanForm() { return { date: today(), handler: (PIN.get() || {}).name || '', user_to: '', orgs: [], escort: '', phone: '', cust_name: '', cust_phone: '', salesperson: '', sales_phone: '', pickups: [], need_return: 1, source: '', u8_no: '', u8_type: '', remark: '', items: [], photos: [] }; }
/* 客户 / 销售人 / 取货人（v1.1.1，都可不填）：x 是借用单或访客登记（访客登记的销售人字段叫 sales_name） */
const npTxt = (n, p) => [n, p].filter(Boolean).join(' ');
function peopleParts(x) {
  const out = [], c = npTxt(x.cust_name, x.cust_phone), s = npTxt(x.salesperson || x.sales_name, x.sales_phone);
  const pk = (x.pickups || []).map(p => npTxt(p.name, p.phone)).filter(Boolean);
  if (c) out.push(['客户', c]); if (s) out.push(['销售', s]); if (pk.length) out.push(['取货', pk.join('、')]);
  return out;
}
const peopleHtml = (x, sep) => peopleParts(x).map(([k, v]) => `<span class="muted">${k}</span> ${esc(v)}`).join(sep || '　');
const qtyTxt = i => i.approx ? (i.qty_text || '若干') + (i.qty ? '（约' + fmtN(i.qty) + '）' : '') : fmtN(i.qty);
const loanStTag = l => `<span class="tag ${l.status === '已归还' ? 'ok' : l.status === '部分归还' ? 'ac' : l.status === '领用' ? '' : 'warn'}">${esc(l.status)}</span>${l.finalized ? '' : ' <span class="tag warn" title="有「若干」件，归还清点后定数">待定数</span>'}`;

Pages.loan = async (el, arg) => {
  if (['new', 'list', 'org', 'batch', 'req'].includes(arg)) LN.tab = arg;
  else if (!arg) LN.tab = 'list';   // 默认借用记录
  if (!LN.form) LN.form = newLoanForm();
  let nReq = 0; try { nReq = (await api('/api/loan_req')).pending; } catch (e) { }
  el.innerHTML = UI.ph('借用归还', '可多样多单位 · 可部分归还', '小件可写「若干」，还回来清点后定数。可多次部分归还。',
    `<div class="seg" id="lnTabs"><button data-t="new">${LN.form.id ? '修改借用单' : '借出登记'}</button><button data-t="list">借用记录</button><button data-t="org">按单位</button><button data-t="batch">补录借用本</button><button data-t="req">访客登记${nReq ? ` <span class="tag warn">${nReq} 待确认</span>` : ''}</button></div>`)
    + `${nReq && LN.tab !== 'req' ? `<div class="banner" style="cursor:pointer" onclick="App.tab('loan/req')">有 ${nReq} 条访客借用登记等你确认（确认前不动库存）→</div>` : ''}<div id="lnBody"></div>`;
  $$('#lnTabs button', el).forEach(b => { b.classList.toggle('on', b.dataset.t === LN.tab); b.onclick = () => App.tab('loan/' + b.dataset.t); });
  const B = $('#lnBody', el);
  if (LN.tab === 'new') return loanForm(B);
  if (LN.tab === 'org') return loanOrg(B);
  if (LN.tab === 'batch') return loanBatch(B);
  if (LN.tab === 'req') return loanReq(B);
  return loanList(B);
};

/* ---------- 借出登记（卡片） ---------- */
async function loanForm(el) {
  const f = LN.form; const s = S.boot.settings;
  const known = (await api('/api/loans?limit=1')).orgs.map(o => o.org);
  el.innerHTML = `<div class="grid2 page-entry"><div class="card page-card">
    <div class="sec"><div class="row r3"><div class="fld"><span class="lab">日期</span><input class="inp" type="date" id="date" value="${esc(f.date)}"></div>
      <div class="fld"><span class="lab">经手人</span><input class="inp" id="handler" list="lnPeople" value="${esc(f.handler)}"><datalist id="lnPeople">${S.boot.people.map(x => `<option value="${esc(x)}">`).join('')}</datalist></div>
      <div class="fld"><span class="lab">给谁用</span><input class="inp" id="user_to" value="${esc(f.user_to)}" placeholder="人名（可空）"></div></div>
      <div class="row" style="margin-top:10px"><div class="fld"><span class="lab">借用单位 <small class="muted">可多个，如一院 + 二院</small></span>
        <div class="split" style="flex-wrap:wrap;gap:6px" id="orgs">${f.orgs.map((o, i) => `<span class="chip on">${esc(o)} <b data-ox="${i}" style="cursor:pointer">×</b></span>`).join('')}
        <span><input class="inp sm" id="orgIn" placeholder="输入单位后回车" style="width:180px" autocomplete="off"></span></div></div></div>
      <div class="row r3" style="margin-top:10px">${escOn(f) ? `<div class="fld"><span class="lab">随车技术人员 <small class="muted">${hasYiyuan(f.orgs) ? '一院借用' : ''}</small></span><input class="inp" id="escort" value="${esc(f.escort)}"></div>
      <div class="fld"><span class="lab">电话</span><input class="inp" id="phone" value="${esc(f.phone)}"></div>` : `<div class="fld"><span class="lab"><a class="link" id="escAdd" style="font-size:12px;font-weight:400">+随车人员</a></span><div class="muted" style="font-size:12.5px;margin-top:4px">每样东西可单独选要还 / 不用还</div></div>`}</div></div>
    <div class="sec"><div class="row r4"><div class="fld"><span class="lab">客户姓名 <small class="muted">可空</small></span><input class="inp" id="cust_name" value="${esc(f.cust_name || '')}"></div>
      <div class="fld"><span class="lab">客户电话</span><input class="inp" id="cust_phone" value="${esc(f.cust_phone || '')}"></div>
      <div class="fld"><span class="lab">销售人</span><input class="inp" id="salesperson" list="lnSales" value="${esc(f.salesperson || '')}"><datalist id="lnSales">${(S.boot.salespeople || []).map(x => `<option value="${esc(x)}">`).join('')}</datalist></div>
      <div class="fld"><span class="lab">销售人电话</span><input class="inp" id="sales_phone" value="${esc(f.sales_phone || '')}"></div></div>
      ${(f.pickups || []).map((p, i) => `<div class="row r4" style="margin-top:8px"><div class="fld"><span class="lab">取货人${f.pickups.length > 1 ? ' ' + (i + 1) : ''}</span><input class="inp" data-pkn="${i}" value="${esc(p.name || '')}"></div>
        <div class="fld"><span class="lab">取货人电话 <a class="link d" data-pkx="${i}" style="font-size:12px;margin-left:8px;font-weight:400">去掉</a></span><input class="inp" data-pkp="${i}" value="${esc(p.phone || '')}"></div></div>`).join('')}
      <a class="link" id="pkAdd" style="display:inline-block;margin-top:8px;font-size:13px">＋ 添加取货人</a></div>
    <div class="sec"><div class="row" style="grid-template-columns:auto 1fr;align-items:center;gap:10px 14px"><span class="lab" style="margin:0">单据来源</span>
      <div class="split"><div class="chips" id="srcs">${s.sources.map(k => `<span class="chip ${f.source === k ? 'on' : ''}" data-k="${esc(k)}">${esc(k)}</span>`).join('')}</div>
      <span id="lnU8f" style="display:${f.source === 'U8单' ? 'flex' : 'none'};gap:8px;margin-left:8px"><input class="inp sm" id="u8_no" placeholder="U8单号（可空）" style="width:150px" value="${esc(f.u8_no)}">
      <input class="inp sm" id="u8_type" list="lnU8t" placeholder="U8单细分（可空）" style="width:150px" value="${esc(f.u8_type)}"><datalist id="lnU8t">${(s.u8_types || []).map(t => `<option value="${esc(t)}">`).join('')}</datalist></span></div></div></div>
    <div class="sec"><div class="sec-h"><h2>选择产品</h2><small>点一下 +1，按常用排序；加完后每项立刻可选「要还 / 不用还」</small></div>
      <div class="picks" id="picks"></div>
      <div style="margin-top:8px"><input class="inp" id="psearch" placeholder="搜其他产品，或输入新名称后回车"></div></div>
    <div class="sec"><div class="sec-h"><h2>借出物品 <small id="lnSum"></small></h2><small>每项可选「要还 / 不用还」；小件数不清可勾「若干」</small></div>
      <div class="lines loan-lines" id="lines"></div></div>
    <div class="sec"><input class="inp" id="remark" placeholder="备注（可空）" value="${esc(f.remark)}"></div>
  </div><div class="sticky page-side-col"><div class="card page-card page-side"><div class="card-h"><h2>照片</h2><small class="muted">借条、清单 · 可多张</small></div><div id="phBox"></div></div>
    <div class="card page-card page-act">${f._req ? `<div class="banner" style="margin-bottom:10px">正在确认访客登记 #${f._req}：核对、修改后点「确认借出」，才生成借用单、扣库存。</div>` : ''}<button class="btn pri big full" id="lnSave">${f._req ? '确认借出' : f.id ? '保存修改' : '保存借出'}</button>
    <div class="hint" style="text-align:center">${f.slip_no ? '借用单 ' + esc(f.slip_no) + ' · ' : '保存后自动编号 · '}Ctrl + Enter 保存${f.id || f._req ? ' · <a class="link" id="lnCancel">' + (f._req ? '先不确认' : '放弃修改') + '</a>' : ''}</div></div></div></div>`;
  const ph = photoBox($('#phBox', el), f.photos, { onchange: p => f.photos = p, title: '借用照片', label: '借用照片' });
  ['date', 'handler', 'user_to', 'escort', 'phone', 'u8_no', 'u8_type', 'remark', 'cust_name', 'cust_phone', 'salesperson', 'sales_phone'].forEach(k => { const i = $('#' + k, el); if (i) i.oninput = () => f[k] = i.value; });
  const oi = $('#orgIn', el);
  /* 全量重绘前把 DOM 未落盘值写回 f，避免点「U8单」等芯片时借用单位草稿/行备注被清空 */
  const syncLoanDom = () => {
    ['date', 'handler', 'user_to', 'escort', 'phone', 'u8_no', 'u8_type', 'remark', 'cust_name', 'cust_phone', 'salesperson', 'sales_phone'].forEach(k => {
      const i = $('#' + k, el); if (i) f[k] = i.value;
    });
    f.pickups = f.pickups || [];
    $$('[data-pkn]', el).forEach(i => { if (f.pickups[+i.dataset.pkn]) f.pickups[+i.dataset.pkn].name = i.value; });
    $$('[data-pkp]', el).forEach(i => { if (f.pickups[+i.dataset.pkp]) f.pickups[+i.dataset.pkp].phone = i.value; });
    const v = ((oi && oi.value) || '').trim();
    if (v && !f.orgs.includes(v)) f.orgs.push(v);
    if (oi) oi.value = '';
    $$('[data-q]', el).forEach(i => { if (f.items[+i.dataset.q]) f.items[+i.dataset.q].qty = i.value; });
    $$('[data-qt]', el).forEach(i => { if (f.items[+i.dataset.qt]) f.items[+i.dataset.qt].qty_text = i.value; });
    $$('[data-nt]', el).forEach(i => { if (f.items[+i.dataset.nt]) f.items[+i.dataset.nt].note = i.value; });
    $$('[data-org]', el).forEach(i => { if (f.items[+i.dataset.org]) f.items[+i.dataset.org].org = i.value; });
  };
  f.pickups = f.pickups || [];
  $$('[data-pkn]', el).forEach(i => i.oninput = () => f.pickups[+i.dataset.pkn].name = i.value);
  $$('[data-pkp]', el).forEach(i => i.oninput = () => f.pickups[+i.dataset.pkp].phone = i.value);
  $$('[data-pkx]', el).forEach(a => a.onclick = () => { syncLoanDom(); f.pickups.splice(+a.dataset.pkx, 1); loanForm(el); });
  $('#pkAdd', el).onclick = () => { syncLoanDom(); f.pickups.push({ name: '', phone: '' }); loanForm(el).then(() => { const x = $$('[data-pkn]', el).pop(); if (x) x.focus(); }); };
  const ea = $('#escAdd', el); if (ea) ea.onclick = () => { syncLoanDom(); f._esc = 1; loanForm(el).then(() => $('#escort', el).focus()); };
  const addOrg = v => { v = (v || '').trim(); if (v && !f.orgs.includes(v)) f.orgs.push(v); if (oi) oi.value = ''; syncLoanDom(); loanForm(el).then(() => $('#orgIn', el).focus()); };
  autoComplete(oi, async q => known.filter(o => o.includes(q.trim()) && !f.orgs.includes(o)).slice(0, 10), o => addOrg(o), (o, q) => `<span>${hl(o, q)}</span>`);
  oi.addEventListener('keydown', e => { if (e.key === 'Enter' && oi.value.trim() && !$('.drop', el)) addOrg(oi.value); });
  $('#orgs', el).onclick = e => { const x = e.target.dataset.ox; if (x !== undefined) { syncLoanDom(); const o = f.orgs.splice(+x, 1)[0]; f.items.forEach(i => { if (i.org === o) i.org = ''; }); loanForm(el); } };
  /* 单据来源只改芯片与 U8 栏显隐，禁止整表重绘——否则未回车的借用单位/行内未 blur 输入会被冲掉 */
  $('#srcs', el).onclick = e => {
    const c = e.target.closest('[data-k]'); if (!c) return;
    f.source = f.source === c.dataset.k ? '' : c.dataset.k;
    $$('#srcs .chip', el).forEach(x => x.classList.toggle('on', x.dataset.k === f.source));
    const u8 = $('#lnU8f', el); if (u8) u8.style.display = f.source === 'U8单' ? 'flex' : 'none';
  };
  const orgOpts = i => f.orgs.length > 1 ? `<select class="inp sm" style="width:110px" data-org="${i}"><option value="">归属…</option>${f.orgs.concat(['共用']).map(o => `<option ${f.items[i].org === o ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>` : '';
  const drawPicks = () => {
    const box = $('#picks', el); if (!box) return;
    box.innerHTML = P.frequent(10).map(p => {
      const it = f.items.find(i => i.product_id === p.id && !i.org);
      return `<div class="pick ${it ? 'on' : ''}" data-id="${p.id}">${esc(p.name)}<small>${it ? '已选 ' + (it.approx ? (it.qty_text || '若干') : fmtN(it.qty)) : esc(p.spec || '')}</small></div>`;
    }).join('');
  };
  const drawLines = () => {
    $('#lines', el).innerHTML = f.items.map((it, i) => {
      const p = it.product_id ? P.byId(it.product_id) : null;
      const nr = it.need_return === 0 || it.need_return === '0' ? 0 : 1;
      it.need_return = nr;
      return `<div class="ln"><div class="nm">${esc(p ? p.label : it.product_name)} ${p ? '' : '<span class="tag warn">新产品</span>'}${it.returned ? ` <span class="muted" style="font-size:12px">已还 ${fmtN(it.returned)}</span>` : ''}</div>${orgOpts(i)}
        <div class="seg" data-nr="${i}" title="这一项要不要还"><button type="button" data-v="1" class="${nr ? 'on' : ''}">要还</button><button type="button" data-v="0" class="${nr ? '' : 'on'}">不用还</button></div>
        <label class="muted w" style="font-size:13px"><input type="checkbox" data-ap="${i}" ${it.approx ? 'checked' : ''}> 若干</label>
        ${it.approx ? `<input class="inp sm" style="width:90px" data-qt="${i}" value="${esc(it.qty_text || '若干')}" title="可写：若干、一包、约20">` : `<div class="step"><button data-m="${i}">−</button><input data-q="${i}" value="${fmtN(it.qty)}" inputmode="decimal"><button data-p="${i}">+</button></div>`}
        <span class="unit">${esc(p ? p.unit : '')}</span><input class="inp sm" style="width:120px" data-nt="${i}" value="${esc(it.note || '')}" placeholder="备注"><button class="link d" data-x="${i}" title="去掉">✕</button></div>`;
    }).join('') || '<div class="muted" style="padding:6px 0">还没加物品 · 点上面产品或搜索加入</div>';
    const n = f.items.filter(i => !i.approx).reduce((a, i) => a + (+i.qty || 0), 0), na = f.items.filter(i => i.approx).length;
    const nrN = f.items.filter(i => i.need_return !== 0 && i.need_return !== '0').length;
    $('#lnSum', el).textContent = f.items.length ? `${f.items.length} 项 · ${fmtN(n)} 件${na ? ' + ' + na + ' 项若干' : ''} · 要还 ${nrN}` : '';
    drawPicks();
  };
  const addItem = (pid, name) => { const it = pid && f.items.find(i => i.product_id === pid && !i.org); if (it && !it.approx) it.qty = (+it.qty || 0) + 1; else f.items.push({ product_id: pid || null, product_name: name || '', qty: 1, approx: 0, qty_text: '', org: '', need_return: 1 }); drawLines(); };
  const pk = $('#picks', el); if (pk) pk.onclick = e => { const c = e.target.closest('[data-id]'); if (c) addItem(+c.dataset.id); };
  const L = $('#lines', el);
  L.addEventListener('click', e => {
    const t = e.target;
    const nrSeg = t.closest('[data-nr]');
    if (nrSeg && t.dataset.v !== undefined) { f.items[+nrSeg.dataset.nr].need_return = +t.dataset.v; drawLines(); return; }
    if (t.dataset.m) { const it = f.items[+t.dataset.m]; it.qty = Math.max(0, (+it.qty || 0) - 1); } else if (t.dataset.p) { const it = f.items[+t.dataset.p]; it.qty = (+it.qty || 0) + 1; }
    else if (t.dataset.x) { if (f.items[+t.dataset.x].returned) return toast('这一项已有归还记录，不能去掉', true); f.items.splice(+t.dataset.x, 1); } else return;
    drawLines();
  });
  L.addEventListener('change', e => {
    const t = e.target;
    if (t.dataset.q) f.items[+t.dataset.q].qty = t.value;
    if (t.dataset.qt) f.items[+t.dataset.qt].qty_text = t.value;
    if (t.dataset.nt) f.items[+t.dataset.nt].note = t.value;
    if (t.dataset.org) f.items[+t.dataset.org].org = t.value;
    if (t.dataset.ap) { const it = f.items[+t.dataset.ap]; it.approx = t.checked ? 1 : 0; if (it.approx) { it.qty_text = it.qty_text || '若干'; it.qty = 0; } else it.qty = 1; drawLines(); }
  });
  const ps = $('#psearch', el);
  autoComplete(ps, async q => P.search(q).slice(0, 12), p => { addItem(p.id); ps.value = ''; }, (p, q) => `<span>${hl(p.label, q)}</span><small>${esc(p.category)}</small>`);
  ps.addEventListener('keydown', e => { if (e.key === 'Enter' && ps.value.trim() && !$('.drop', el)) { const ex = findProd(ps.value); ex ? addItem(ex.id) : addItem(null, ps.value.trim()); ps.value = ''; } });
  const doSave = async () => {
    if (!f.items.length) return toast('还没加物品', true);
    if (!f.user_to.trim() && !f.orgs.length && !oi.value.trim()) return toast('请填给谁用，或借用单位', true);
    if (f.orgs.length > 1 && f.items.some(i => !i.org)) return toast('多个单位时，请给每样东西选归属（或「共用」）', true);
    const data = Object.assign({}, f, { use_type: f.orgs.length || oi.value.trim() ? '外单位' : '自用', pickups: (f.pickups || []).filter(p => (p.name || '').trim() || (p.phone || '').trim()) }); delete data.photos; delete data._req;
    if (oi.value.trim() && !f.orgs.includes(oi.value.trim())) data.orgs = f.orgs.concat([oi.value.trim()]);
    if (f._req) {
      const r = await save('/api/loan_req/confirm', { id: f._req, data, photo_ids: ph.ids }, '确认访客登记');
      toast('已确认，借用单 ' + r.slip_no); LN.form = newLoanForm(); await loadBoot(); App.who(); App.tab('loan/req'); return;
    }
    const r = await save('/api/loan/save', { data, photo_ids: ph.ids }, f.id ? '保存借用单修改' : '保存借出');
    toast((f.id ? '已保存 ' : '已借出，借用单 ') + r.slip_no); LN.form = newLoanForm(); await loadBoot(); App.who();
    if (f.id) App.tab('loan/list'); else loanForm(el);
  };
  $('#lnSave', el).onclick = () => doSave().catch(fail);
  const ce = $('#lnCancel', el); if (ce) ce.onclick = () => { const back = f._req ? 'loan/req' : 'loan/list'; LN.form = newLoanForm(); App.tab(back); };
  el.onkeydown = e => { if (e.ctrlKey && e.key === 'Enter') doSave().catch(fail); };
  drawLines();
}

/* ---------- 归还弹窗：按单 ---------- */
async function returnDialog(lid, done) {
  const l = await api('/api/loan/one?id=' + lid);
  const its = l.items.filter(i => (i.need_return ? (i.left > 0 || i.approx) : i.approx));
  const ov = dialog('归还 · ' + l.slip_no + ' · ' + (l.orgs.join('、') || l.user_to), `
    <div class="row r3" style="margin-bottom:10px"><div class="fld"><span class="lab">归还日期</span><input class="inp" type="date" id="rtDate" value="${today()}"></div><div class="fld" style="grid-column:span 2"><span class="lab">备注</span><input class="inp" id="rtRm"></div></div>
    <table class="t"><thead><tr><th>物品</th><th>归属</th><th class="n">借</th><th class="n">已还</th><th class="n">未还</th><th class="n" style="width:100px">这次还</th><th style="width:120px">实借数（定数）</th></tr></thead><tbody>
    ${its.map(i => `<tr><td>${esc(i.label)}</td><td>${esc(i.org)}</td><td class="n">${esc(qtyTxt(i))}</td><td class="n">${fmtN(i.returned || 0)}</td><td class="n">${i.approx ? '?' : fmtN(i.left)}</td>
      <td><input class="inp sm num" data-rq="${i.id}" placeholder="0"></td><td>${i.approx ? `<input class="inp sm num" data-fq="${i.id}" placeholder="清点后填">` : '<span class="muted">—</span>'}</td></tr>`).join('') || '<tr><td colspan="7" class="empty">都还完了</td></tr>'}</tbody></table>
    <div class="hint">「若干」的小件：还回来清点后，在「实借数」填当初实际借出的数，借用单就定数了；不填的话仍留在待补全。<a id="rtAll">全部还清</a></div>`,
    [{ t: '取消' }, { t: '保存归还', cls: 'pri', fn: async ov => {
      const items = its.map(i => ({ loan_item_id: i.id, qty: $(`[data-rq="${i.id}"]`, ov).value, final_qty: i.approx ? $(`[data-fq="${i.id}"]`, ov).value : '' })).filter(x => +x.qty > 0 || x.final_qty !== '');
      if (!items.length) { toast('没有填这次还的数', true); return false; }
      await save('/api/loan/return', { loan_id: lid, date: $('#rtDate', ov).value, remark: $('#rtRm', ov).value, items }, '保存归还'); toast('已归还'); done && done();
    } }], { wide: true });
  const a = $('#rtAll', ov); if (a) a.onclick = () => its.forEach(i => { if (!i.approx) $(`[data-rq="${i.id}"]`, ov).value = fmtN(i.left); });
}

/* ---------- 借用记录 ---------- */
async function loanList(el) {
  const F = LN.f; const s = S.boot.settings;
  if (!LN.init) { LN.init = 1; const n = +defs().list_days; if (n > 0 && !F.from) F.from = daysAgo(n); }
  el.innerHTML = `<div class="card page-card"><div class="tools">
    <div class="tg"><div class="seg" id="llSt"><button data-v="open">未归还</button><button data-v="unfinal">小件待定数</button><button data-v="已归还">已归还</button><button data-v="领用">不用还</button><button data-v="">全部</button></div>
    <input class="inp" type="date" id="llFrom" value="${F.from}" style="width:124px"><span class="muted">至</span><input class="inp" type="date" id="llTo" value="${F.to}" style="width:124px">
    <select class="inp" id="llSrc"><option value="">全部来源</option>${s.sources.map(k => `<option ${F.source === k ? 'selected' : ''}>${esc(k)}</option>`).join('')}</select>
    <input class="inp" id="llQ" placeholder="搜单号、人、电话、单位、物品、备注" value="${esc(F.q)}" style="width:170px">
    <label class="muted" style="font-size:13px"><input type="checkbox" id="llDel" ${F.deleted ? 'checked' : ''}> 已删除</label></div>
    <span class="sp"></span><div class="tg acts"><button class="btn sm" id="llPrint">打印</button><button class="btn sm" id="llExp">导出 Excel</button>${LC.btn('loan')}</div>
  </div><div id="llT"></div></div>`;
  $$('#llSt button', el).forEach(b => { b.classList.toggle('on', b.dataset.v === F.status); b.onclick = () => { F.status = b.dataset.v; loanList(el); }; });
  const qs = () => Object.entries(F).filter(([k, v]) => v).map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&');
  let data = [];
  const load = async () => {
    const r = await api('/api/loans?' + qs()); data = r.items;
    const eo = data.some(l => (l.escort || '').trim());
    $('#llT', el).innerHTML = data.length ? `<div class="tw"><table class="t" id="llTbl"><thead><tr><th>借用单</th><th>日期</th><th>经手人</th><th>给谁用 / 单位</th>${eo ? '<th>随车技术人员</th>' : ''}<th>物品（借 / 未还）</th><th>单据</th><th>备注</th><th>状态</th><th></th></tr></thead><tbody>
      ${data.map(l => `<tr class="${l.deleted_at ? 'off' : ''}"><td class="w">${esc(l.slip_no)}</td><td class="w ${l.status === '未归还' || l.status === '部分归还' ? ageCls(l.date) : ''}">${esc(l.date)}</td><td class="w">${esc(l.handler)}</td>
        <td>${esc(l.user_to)}${l.orgs.length ? (l.user_to ? '<br>' : '') + '<span class="muted">' + esc(l.orgs.join('、')) + '</span>' : ''}${peopleParts(l).length ? '<div style="font-size:12.5px;line-height:1.5">' + peopleHtml(l, '<br>') + '</div>' : ''}</td>${eo ? `<td class="w">${esc(l.escort)}${l.escort && l.phone ? '<br><span class="muted">' + esc(l.phone) + '</span>' : ''}</td>` : ''}
        <td>${l.items.map(i => `${esc(i.label)} ${esc(qtyTxt(i))}${!i.need_return ? ' <span class="muted">不用还</span>' : (i.left > 0 && (i.returned || 0) > 0 ? ' <span class="muted">未还' + fmtN(i.left) + '</span>' : '')}${i.org && l.orgs.length > 1 ? '<span class="muted">［' + esc(i.org) + '］</span>' : ''}`).join('、')}</td>
        <td class="w">${l.source ? `<span class="tag ${l.source === 'U8单' ? 'ac' : ''}">${esc(l.source)}</span>` : ''}${l.u8_no ? ' <span class="muted">' + esc(l.u8_no) + '</span>' : ''}</td>
        ${rmkTd(rmkJoin(l.remark, l.items.map(i => i.note ? i.label + '：' + i.note : ''), l.returns.map(r => r.remark ? r.date + ' 归还：' + r.remark : '')))}<td class="w">${loanStTag(l)}${l.returns.length ? `<div class="muted" style="font-size:12px">还过 ${l.returns.length} 次</div>` : ''}</td>${rowActs({ ph: [l.photos.length, `data-ph="${l.id}"`],
          main: l.deleted_at ? ['恢复', `data-rs="${l.id}"`] : (l.need_return && l.status !== '已归还' ? ['归还', `data-rt="${l.id}"`] : (l.finalized ? null : ['定数', `data-rt="${l.id}"`])),
          menu: l.deleted_at ? [['打印', `data-pr="${l.id}"`], ['留痕', `data-hi="${l.id}"`]] : [['修改', `data-ed="${l.id}"`], ['打印', `data-pr="${l.id}"`], ['留痕', `data-hi="${l.id}"`], ['删除', `data-del="${l.id}"`, 1]] })}</tr>`).join('')}</tbody></table></div>
      <div class="hint">${data.length} 张借用单 · 点「列」可隐藏列</div>` : '<div class="empty">没有记录</div>';
    if (data.length) {
      const cols = [
        { k: 'no', label: '借用单', w: 100 }, { k: 'date', label: '日期', w: 88 }, { k: 'handler', label: '经手人', w: 72 },
        { k: 'user', label: '给谁用 / 单位', w: 140, wrap: 1 }
      ];
      if (eo) cols.push({ k: 'escort', label: '随车技术人员', w: 100, hide: 1 });
      cols.push({ k: 'items', label: '物品（借 / 未还）', w: 200, prod: 1 },
        { k: 'src', label: '单据', w: 88, hide: 1 }, { k: 'rmk', label: '备注', w: 110, wrap: 1 },
        { k: 'st', label: '状态', w: 88 }, { k: '_act', label: '操作', w: 120 });
      LC.apply($('#llTbl', el), 'loan', cols);
    if (typeof CellSel !== 'undefined') CellSel.on($('#llTbl', el));
    }
  };
  const bind = (id, k) => { $(id, el).onchange = e => { F[k] = e.target.type === 'checkbox' ? (e.target.checked ? '1' : '') : e.target.value; load().catch(fail); }; };
  bind('#llFrom', 'from'); bind('#llTo', 'to'); bind('#llSrc', 'source'); bind('#llDel', 'deleted');
  let tm; $('#llQ', el).oninput = e => { clearTimeout(tm); tm = setTimeout(() => { F.q = e.target.value; load().catch(fail); }, 250); };
  $('#llExp', el).onclick = () => download('/api/loans.xlsx?' + qs());
  $('#llPrint', el).onclick = () => printApi('/api/loans.xlsx?' + qs(), { landscape: true }).catch(fail);
  $('#llT', el).addEventListener('click', async e => {
    const t = e.target; const L = id => data.find(x => x.id === +id);
    try {
      if (t.dataset.rt) returnDialog(+t.dataset.rt, load);
      if (t.dataset.ph) dialog('照片', `<div class="photos">${L(t.dataset.ph).photos.map(p => `<img class="ph-i" style="width:180px;height:135px" src="/photos/${esc(p.path)}" onclick="bigImg(this.src)">`).join('')}</div>`, null, { wide: true });
      if (t.dataset.pr) printApi('/api/loan/slip.xlsx?id=' + t.dataset.pr);
      if (t.dataset.ed) { const x = await api('/api/loan/one?id=' + t.dataset.ed); LN.form = Object.assign(newLoanForm(), x, { items: x.items.map(i => ({ id: i.id, product_id: i.product_id, product_name: i.product_name, qty: i.qty, approx: i.approx, qty_text: i.qty_text, org: i.org, returned: i.returned, note: i.note, batch_no: i.batch_no, need_return: i.need_return ? 1 : 0 })) }); App.tab('loan/new'); }
      if (t.dataset.hi) { const x = await api('/api/loan/one?id=' + t.dataset.hi); dialog('留痕 · ' + x.slip_no, `<table class="t"><thead><tr><th>时间</th><th>谁</th><th>操作</th><th>内容</th></tr></thead><tbody>${x.audit.map(a => `<tr><td class="w">${fmtTs(a.ts)}</td><td>${esc(a.person)}</td><td>${esc(a.action)}</td><td>${esc(a.summary)}</td></tr>`).join('')}</tbody></table>
        ${x.returns.length ? `<h3 style="margin:14px 0 6px;font-size:14px">归还记录</h3><table class="t"><tbody>${x.returns.map(r => `<tr><td class="w">${esc(r.date)}</td><td>${r.items.map(i => esc(P.label(i.product_id) || '') + ' ' + fmtN(i.qty)).join('、')}</td><td class="muted">${esc(r.org ? '按单位合计：' + r.org : '')} ${esc(r.remark)}</td><td class="w">${esc(r.created_by)}</td><td><a class="link d" data-rd="${r.id}">删除</a></td></tr>`).join('')}</tbody></table>` : ''}`, null, { wide: true }).addEventListener('click', async ev => {
          if (ev.target.dataset.rd && await confirmDelete('loan_return', +ev.target.dataset.rd, '/api/loan/return/delete')) { ev.target.closest('.ov').remove(); toast('已删除'); load(); }
        }); }
      if (t.dataset.del && await confirmDelete('loan', +t.dataset.del, '/api/loan/delete')) { toast('已删除'); load(); }
      if (t.dataset.rs) { await save('/api/restore', { entity: 'loan', id: +t.dataset.rs }, '恢复借用单'); toast('已恢复'); load(); }
    } catch (er) { fail(er); }
  });
  await load();
}

/* ---------- 按单位：历史 + 合计未还 + 按合计归还 ---------- */
async function loanOrg(el) {
  const r = await api('/api/loans?limit=1');
  if (!LN.org && r.orgs.length) LN.org = r.orgs[0].org;
  el.innerHTML = `<div style="display:grid;grid-template-columns:260px 1fr;gap:16px;align-items:start">
    <div class="card"><input class="inp sm" id="ogQ" placeholder="找单位" style="margin-bottom:8px"><table class="t" id="ogL"><thead><tr><th>单位</th><th class="n">单数</th><th class="n">未还</th></tr></thead><tbody></tbody></table></div>
    <div class="card" id="ogH" style="margin-top:0"></div></div>`;
  const drawL = q => { $('#ogL tbody', el).innerHTML = r.orgs.filter(o => !q || o.org.includes(q)).map(o => `<tr data-o="${esc(o.org)}" style="cursor:pointer" class="${o.org === LN.org ? 'sel' : ''}"><td>${o.org === LN.org ? '<b>' + esc(o.org) + '</b>' : esc(o.org)}</td><td class="n">${o.loans}</td><td class="n">${o.open ? '<b>' + o.open + '</b>' : '<span class="muted">0</span>'}</td></tr>`).join('') || '<tr><td colspan="3" class="empty">还没有单位借用</td></tr>'; };
  drawL(''); $('#ogQ', el).oninput = e => drawL(e.target.value);
  $('#ogL', el).onclick = e => { const tr = e.target.closest('[data-o]'); if (tr) { LN.org = tr.dataset.o; loanOrg(el); } };
  if (!LN.org) { $('#ogH', el).innerHTML = '<div class="empty">选左边的单位</div>'; return; }
  const h = await api('/api/loan/org?org=' + encodeURIComponent(LN.org)); const u = '/api/loan/org.xlsx?org=' + encodeURIComponent(LN.org);
  const open = h.totals.filter(t => t.left > 0 || t.approx); const heo = h.lines.some(x => (x.escort || '').trim());
  $('#ogH', el).innerHTML = `<div class="card-h"><h2>${esc(LN.org)} <small>${h.loans} 张借用单</small></h2><div class="acts">${open.length ? '<button class="btn pri sm" id="ogRet">按合计归还</button>' : ''}<button class="btn sm" id="ogPr">打印</button><button class="btn sm" id="ogEx">导出 Excel</button></div></div>
    <h3 style="font-size:14px;margin:4px 0 6px">合计未还</h3>${open.length ? `<table class="t" style="max-width:560px"><thead><tr><th>物品</th><th class="n">共借</th><th class="n">已还</th><th class="n">未还</th></tr></thead><tbody>${open.map(t => `<tr><td>${esc(t.item)}</td><td class="n">${fmtN(t.qty)}${t.approx ? ' <span class="tag warn">含若干</span>' : ''}</td><td class="n">${fmtN(t.returned)}</td><td class="n"><b>${fmtN(t.left)}</b></td></tr>`).join('')}</tbody></table>` : '<div class="muted">都还清了</div>'}
    <h3 style="font-size:14px;margin:16px 0 6px">借用历史</h3><div class="tw"><table class="t t-grp"><thead><tr><th>日期</th><th>借用单</th><th>物品</th><th class="n">借</th><th class="n">已还</th><th class="n">未还</th>${heo ? '<th>随车技术人员</th>' : ''}<th>经手人</th><th>归还记录</th><th>备注</th></tr></thead><tbody>
    ${(() => { let prev = null, gi = -1; return h.lines.slice().reverse().map((x, i) => {
      const first = prev !== x.slip_no; if (first) { gi++; prev = x.slip_no; }
      const cls = `g${gi % 2}${first && i ? ' g-sep' : ''}`;
      const d = first ? esc(x.date) : ''; const sn = first ? esc(x.slip_no) : '';
      return `<tr class="${cls}"><td class="w">${d}</td><td class="w">${sn}</td><td>${esc(x.item)}${x.org === '共用' ? ' <span class="muted">［共用］</span>' : ''}</td><td class="n">${esc(x.approx ? x.qty_text : fmtN(x.qty))}</td><td class="n">${fmtN(x.returned)}</td><td class="n">${x.need_return ? (x.left > 0 ? '<b>' + fmtN(x.left) + '</b>' : '0') : '<span class="muted">不用还</span>'}</td>${heo ? `<td class="w">${esc(x.escort)}</td>` : ''}<td class="w">${esc(x.handler)}</td><td class="muted">${esc(x.returns)}</td>${rmkTd(x.remark)}</tr>`;
    }).join(''); })()}</tbody></table></div>`;
  $('#ogPr', el).onclick = () => printApi(u, { landscape: true }).catch(fail);
  $('#ogEx', el).onclick = () => download(u);
  const rb = $('#ogRet', el); if (rb) rb.onclick = async () => {
    const o = await api('/api/loan/outstanding?org=' + encodeURIComponent(LN.org));
    dialog('按合计归还 · ' + LN.org, `<div class="row r3" style="margin-bottom:10px"><div class="fld"><span class="lab">归还日期</span><input class="inp" type="date" id="orD" value="${today()}"></div><div class="fld" style="grid-column:span 2"><span class="lab">备注</span><input class="inp" id="orR"></div></div>
      <table class="t"><thead><tr><th>物品</th><th class="n">合计未还</th><th>涉及借用单</th><th class="n" style="width:110px">这次还</th></tr></thead><tbody>${o.by_product.map(p => `<tr><td>${esc(p.label)}</td><td class="n">${fmtN(p.left)}${p.approx ? ' <span class="tag warn">含若干</span>' : ''}</td><td class="muted">${esc([...new Set(p.slips)].join('、'))}</td><td><input class="inp sm num" data-pq="${p.product_id}"></td></tr>`).join('')}</tbody></table>
      <div class="hint">按借出先后，自动分到各张借用单上（先还最早的）。「若干」件要定数请到借用记录里逐单归还。</div>`,
      [{ t: '取消' }, { t: '保存归还', cls: 'pri', fn: async ov => {
        const items = o.by_product.map(p => ({ product_id: p.product_id, qty: $(`[data-pq="${p.product_id}"]`, ov).value })).filter(x => +x.qty > 0);
        if (!items.length) { toast('没有填数', true); return false; }
        const r2 = await save('/api/loan/return', { org: LN.org, date: $('#orD', ov).value, remark: $('#orR', ov).value, items }, '按单位归还'); toast('已归还，分到 ' + r2.ids.length + ' 张借用单'); loanOrg(el);
      } }], { wide: true });
  };
}

/* ---------- 补录手写借用本（表格快速录） ---------- */
const LB = { rows: [] };
const LB_KEYS = ['date', 'handler', 'user_to', 'unit', 'product', 'qty', 'returned', 'return_date', 'escort', 'remark'];
const lbRow = () => Object.fromEntries(LB_KEYS.map(k => [k, '']));
function loanBatch(el) {
  if (!LB.rows.length) LB.rows = Array.from({ length: 8 }, lbRow);
  el.innerHTML = `<div class="card page-card"><div class="hint" style="margin:0 0 10px">照手写借用本一行一样东西录。可从 Excel 复制整块后，点表格任一格 Ctrl+V 粘贴；Enter 到下一行。数量写不清可填「若干」。<br>同一天、同一经手人、同一给谁用 / 单位的连续几行会合成一张借用单；「已还」有数的会同时记归还。</div>
    <div class="tw"><table class="t grid" id="lbT" data-nosel><thead><tr><th style="width:32px">#</th><th style="width:130px">日期</th><th style="width:80px">经手人</th><th style="width:90px">给谁用</th><th>借用单位</th><th>物品</th><th style="width:70px">数量</th><th style="width:60px">已还</th><th style="width:130px">归还日期</th><th style="width:90px">随车技术人员</th><th>备注</th><th style="width:30px"></th></tr></thead><tbody></tbody></table></div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px"><span><button class="btn sm" id="lbAdd">＋ 加 5 行</button> <button class="btn sm" id="lbClr">清空</button></span><span class="muted" id="lbSum"></span><button class="btn pri" id="lbSave" style="width:200px">保存补录</button></div></div>`;
  const tb = $('#lbT tbody', el);
  const draw = () => {
    tb.innerHTML = LB.rows.map((r, i) => `<tr><td class="muted">${i + 1}</td>${LB_KEYS.map(k => {
      const bad = k === 'product' && r.product && !findProd(r.product);
      return `<td><input class="inp sm ${['qty', 'returned'].includes(k) ? 'num' : ''}" data-i="${i}" data-k="${k}" value="${esc(r[k])}" ${k === 'product' ? 'list="lbProds"' : k === 'handler' ? 'list="lbPeople"' : ''} ${k.includes('date') ? 'placeholder="年-月-日"' : ''} style="${bad ? 'box-shadow:inset 0 0 0 1px var(--warn)' : ''}" title="${bad ? '产品清单里没有，会作为新产品加入' : ''}"></td>`;
    }).join('')}<td><button class="link d" data-x="${i}">✕</button></td></tr>`).join('') +
      `<datalist id="lbProds">${S.boot.products.map(p => `<option value="${esc(p.label)}">`).join('')}</datalist><datalist id="lbPeople">${S.boot.people.map(x => `<option value="${esc(x)}">`).join('')}</datalist>`;
    sum();
  };
  const ok = () => LB.rows.filter(r => r.product.trim() && (r.user_to.trim() || r.unit.trim() || r.handler.trim()));
  const sum = () => { const n = ok().length; $('#lbSum', el).textContent = n ? n + ' 行可保存' : ''; };
  tb.addEventListener('input', e => { const t = e.target; if (t.dataset.k) { LB.rows[+t.dataset.i][t.dataset.k] = t.value; sum(); } });
  tb.addEventListener('change', e => { if (e.target.dataset.k === 'product') { const i = e.target.dataset.i; draw(); $(`[data-i="${i}"][data-k="qty"]`, tb).focus(); } });
  tb.addEventListener('click', e => { if (e.target.dataset.x) { LB.rows.splice(+e.target.dataset.x, 1); draw(); } });
  tb.addEventListener('keydown', e => {
    const t = e.target; if (!t.dataset.k) return;
    const i = +t.dataset.i, k = t.dataset.k;
    if (e.key === 'Enter' || (e.key === 'ArrowDown' && !$('.drop', el))) {
      e.preventDefault(); if (i + 1 >= LB.rows.length) { LB.rows.push(lbRow()); draw(); }
      const nx = LB.rows[i + 1]; ['date', 'handler', 'user_to', 'unit'].forEach(c => { if (!nx[c] && LB.rows[i][c] && !nx.product) nx[c] = LB.rows[i][c]; });   // 同一单连续录：沿用上一行
      draw(); $(`[data-i="${i + 1}"][data-k="${k}"]`, tb).focus();
    } else if (e.key === 'ArrowUp' && i > 0) { e.preventDefault(); $(`[data-i="${i - 1}"][data-k="${k}"]`, tb).focus(); }
  });
  tb.addEventListener('paste', e => {
    const t = e.target; if (!t.dataset.k) return;
    const txt = (e.clipboardData || window.clipboardData).getData('text'); if (!txt.includes('\t') && !txt.includes('\n')) return;
    e.preventDefault(); const k0 = LB_KEYS.indexOf(t.dataset.k); let i = +t.dataset.i;
    txt.replace(/\r/g, '').split('\n').filter(l => l.trim()).forEach(l => { while (LB.rows.length <= i) LB.rows.push(lbRow()); l.split('\t').forEach((v, j) => { const k = LB_KEYS[k0 + j]; if (k) LB.rows[i][k] = v.trim(); }); i++; });
    draw();
  });
  $('#lbAdd', el).onclick = () => { for (let i = 0; i < 5; i++) LB.rows.push(lbRow()); draw(); };
  $('#lbClr', el).onclick = () => { LB.rows = []; loanBatch(el); };
  $('#lbSave', el).onclick = async () => {
    try {
      const rs = ok(); if (!rs.length) return toast('没有完整的行（物品 + 给谁用 / 单位 / 经手人）', true);
      const bad = rs.filter(r => r.date && !/^\d{4}-\d{1,2}-\d{1,2}$/.test(r.date)); if (bad.length) return toast('日期请写成 2026-10-01 这样', true);
      const newP = [...new Set(rs.filter(r => !findProd(r.product)).map(r => r.product.trim()))];
      if (newP.length && !await confirmBox(`这些物品清单里没有，会作为新产品加入：<br><b>${esc(newP.join('、'))}</b>`, '继续保存')) return;
      const rows = rs.map(r => { const p = findProd(r.product); return Object.assign({}, r, { date: r.date ? r.date.replace(/-(\d)(?=-|$)/g, '-0$1') : today(), product_id: p ? p.id : null, product_name: p ? '' : r.product.trim() }); });
      const r = await save('/api/loan/batch', { rows }, '补录借用本');
      toast('已补录 ' + r.ids.length + ' 张借用单'); LB.rows = []; await loadBoot(); loanBatch(el);
    } catch (er) { fail(er); }
  };
  draw();
}

/* ---------- 访客登记（手机 /m/guest 提交，待确认；确认前不动库存） ---------- */
function qrCard(url, title, sub) {
  return `<div style="display:flex;gap:12px;align-items:center"><img src="/api/qr.svg?text=${encodeURIComponent(url)}" alt="" style="width:112px;height:112px;border:1px solid var(--line);border-radius:8px;background:#fff">
    <div><div style="font-weight:600">${esc(title)}</div><div class="muted" style="font-size:12.5px;margin:2px 0 4px">${esc(sub)}</div><a class="link" href="${esc(url)}" target="_blank" style="word-break:break-all">${esc(url)}</a></div></div>`;
}
function phoneQrs() {
  const base = (S.boot.lan || [])[0] || location.origin;
  return `<div style="display:flex;gap:28px;flex-wrap:wrap">${qrCard(base + '/m/', '员工手机', '出库、交接表、借用归还…（保存时输密码）')}${qrCard(base + '/m/guest', '访客登记借用', '外单位来借东西扫这个，不用密码；提交后要你确认')}<div id="libQrSlot"><div class="muted" style="padding:20px 0">照片库二维码加载中…</div></div></div>`;
}
async function fillLibQr() {
  const slot = document.getElementById('libQrSlot'); if (!slot) return;
  try {
    const s = await api('/api/lib/session', { by: (PIN.get() || {}).name || '' });
    const base = (S.boot.lan || [])[0] || location.origin, url = base + '/m/lib.html#' + s.token;
    const days = s.ttl >= 86400 ? ('约 ' + Math.ceil(s.ttl / 86400) + ' 天') : (Math.ceil((s.ttl || 0) / 3600) + ' 小时');
    slot.outerHTML = qrCard(url, '照片库（持续上传）', '扫一次可连用 ' + days + '；传到共享库，电脑加附件时点「照片库」选用。可「重新生成」作废旧码。') +
      `<div style="align-self:center"><a class="link" id="libQrNew">重新生成照片库二维码</a></div>`;
    const a = document.getElementById('libQrNew'); if (a) a.onclick = async () => { await api('/api/lib/session', { force: 1, by: (PIN.get() || {}).name || '' }); fillLibQr(); };
  } catch (e) { slot.innerHTML = '<div class="bad">' + esc(e.message) + '</div>'; }
}
async function loanReq(el) {
  const st = LN.reqSt || '待确认';
  const r = await api('/api/loan_req?status=' + encodeURIComponent(st));
  const qtx = i => i.approx ? '若干' : fmtN(i.qty);
  el.innerHTML = `<div class="card page-card"><div class="card-h"><h2>访客借用登记</h2><div class="seg" id="lrSt">${['待确认', '已确认', '已拒绝'].map(x => `<button data-s="${x}" class="${x === st ? 'on' : ''}">${x}</button>`).join('')}</div></div>
    <div class="hint" style="margin-bottom:12px">访客用手机扫「访客登记借用」二维码填写，不用密码。提交后在这里核对：「确认借出」直接生成借用单（自动编号、扣库存）；要改先点「修改后确认」；不借就「拒绝」。</div>
    ${r.items.map(q => `<div class="note-line" style="align-items:flex-start;padding:12px 0;border-top:1px solid var(--line)"><div style="flex:1">
      <div><b>#${q.id} ${esc(q.orgs.join('、'))}</b> <span class="muted" style="font-size:12.5px">${esc(fmtTs(q.created_at))}</span></div>
      ${peopleParts(q).length || q.escort ? `<div style="font-size:13px;margin-top:2px">${peopleHtml(q)}${q.escort ? '　<span class="muted">随车</span> ' + esc(npTxt(q.escort, q.escort_phone)) : ''}</div>` : ''}
      <div style="margin-top:4px">${q.items.map(i => esc(i.product_name) + ' ' + qtx(i) + (i.org ? '（' + esc(i.org) + '）' : '') + (i.product_id ? '' : ' <span class="tag warn" title="访客手写的名称，确认时会新建产品；可先「修改后确认」改成已有产品">新名称</span>')).join('、')}</div>
      ${q.remark ? `<div class="muted" style="font-size:13px;margin-top:2px">备注：${esc(q.remark)}</div>` : ''}
      ${q.photos.length ? `<div class="photos" style="margin-top:6px">${q.photos.map(p => `<img class="ph-i" src="/photos/${esc(p.path)}" data-big="${esc(p.path)}" title="${p.tag === 'sign' ? '签名' : '照片'}" style="width:64px;height:64px${p.tag === 'sign' ? ';object-fit:contain;background:#fff;border:1px solid var(--line)' : ''}">`).join('')}</div>` : ''}
      ${q.status === '已确认' ? `<div class="muted" style="font-size:13px;margin-top:4px">${esc(q.handled_by)} 已确认 → 借用单 ${esc(q.slip_no || '')}</div>` : ''}
      ${q.status === '已拒绝' ? `<div class="muted" style="font-size:13px;margin-top:4px">${esc(q.handled_by)} 已拒绝${q.reject_reason ? '：' + esc(q.reject_reason) : ''}</div>` : ''}</div>
      ${q.status === '待确认' ? `<div style="display:flex;gap:8px;flex:none"><button class="btn sm pri" data-ok="${q.id}">确认借出</button><button class="btn sm" data-ed="${q.id}">修改后确认</button><button class="btn sm" data-no="${q.id}">拒绝</button></div>` : ''}</div>`).join('') || `<div class="empty">没有${esc(st)}的访客登记</div>`}</div>
    <div class="card"><div class="card-h"><h2>手机二维码</h2><small class="muted">打印出来贴在库房门口；手机要和这台电脑连同一个 WiFi</small></div>${phoneQrs()}</div>`;
  fillLibQr();
  $('#lrSt', el).onclick = e => { const b = e.target.closest('[data-s]'); if (b) { LN.reqSt = b.dataset.s; loanReq(el); } };
  el.onclick = async e => {
    const t = e.target;
    try {
      if (t.dataset.big) bigImg('/photos/' + t.dataset.big);
      if (t.dataset.ok) {
        const q = r.items.find(x => x.id === +t.dataset.ok);
        if (!await confirmBox(`确认借给 <b>${esc(q.orgs.join('、'))} ${esc(q.cust_name || '')}</b>：${q.items.map(i => esc(i.product_name) + ' ' + qtx(i)).join('、')}？<br><span class="muted">确认后生成借用单并扣库存。</span>`, '确认借出')) return;
        const x = await save('/api/loan_req/confirm', { id: q.id }, '确认访客登记'); toast('已确认，借用单 ' + x.slip_no); App.route();
      }
      if (t.dataset.ed) {
        const q = r.items.find(x => x.id === +t.dataset.ed);
        LN.form = Object.assign(newLoanForm(), { user_to: q.cust_name || ((q.pickups || []).find(p => p.name) || {}).name || '', orgs: q.orgs.slice(), escort: q.escort, phone: q.escort_phone, _esc: q.escort ? 1 : 0,
          cust_name: q.cust_name || '', cust_phone: q.cust_phone || '', salesperson: q.sales_name || '', sales_phone: q.sales_phone || '', pickups: (q.pickups || []).map(p => Object.assign({}, p)),
          remark: ['访客登记 #' + q.id, q.remark].filter(Boolean).join('；'),
          items: q.items.map(i => ({ product_id: i.product_id, product_name: i.product_name, qty: i.qty, approx: i.approx, qty_text: i.approx ? '若干' : '', org: i.org, need_return: 1 })),
          photos: q.photos, _req: q.id });
        App.tab('loan/new');
      }
      if (t.dataset.no) {
        dialog('拒绝访客登记 #' + t.dataset.no, `<span class="lab">原因（可空，会记在操作记录里）</span><input class="inp" id="rjR">`, [{ t: '取消' }, { t: '拒绝', cls: 'pri', fn: async ov => {
          await save('/api/loan_req/reject', { id: +t.dataset.no, reason: $('#rjR', ov).value }, '拒绝访客登记'); toast('已拒绝'); App.route(); } }]);
      }
    } catch (er) { fail(er); }
  };
}
