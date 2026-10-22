/* 访客登记借用（不用密码）：只调用 /api/guest/form 和 /api/guest/submit；提交后等库房人员确认，确认前不动库存 */
'use strict';
(function () {
  const $ = (s, el) => (el || document).querySelector(s), $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const app = $('#app');
  async function req(path, body) {
    const r = await fetch(path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
    let d = {}; try { d = await r.json(); } catch (e) { }
    if (!r.ok) throw new Error(d.error || ('出错了（' + r.status + '）'));
    return d;
  }
  function err(msg) { const t = document.createElement('div'); t.className = 'g-err'; t.textContent = msg; document.body.appendChild(t); setTimeout(() => t.remove(), 3500); }
  function compress(file) {
    return new Promise((res, rej) => {
      const fr = new FileReader();
      fr.onload = () => { const img = new Image(); img.onload = () => { const k = Math.min(1, 1600 / Math.max(img.width, img.height)); const c = document.createElement('canvas'); c.width = Math.round(img.width * k); c.height = Math.round(img.height * k); c.getContext('2d').drawImage(img, 0, 0, c.width, c.height); res(c.toDataURL('image/jpeg', 0.8)); }; img.onerror = () => rej(new Error('图片打不开')); img.src = fr.result; };
      fr.onerror = () => rej(new Error('图片读不了')); fr.readAsDataURL(file);
    });
  }
  let F = null, opt = null;
  // 这台手机上次用的单位、销售人：下次自动带上（员工自己也用这个页面，要快）
  const LS = 'wh_guest_last';
  const last = () => { try { return JSON.parse(localStorage.getItem(LS) || '{}') || {}; } catch (e) { return {}; } };
  const remember = () => { try { localStorage.setItem(LS, JSON.stringify({ orgs: F.orgs, sales_name: F.sales_name, sales_phone: F.sales_phone })); } catch (e) { } };
  const fresh = () => { const l = last(); return { orgs: (l.orgs || []).slice(0, 5), cust_name: '', cust_phone: '', sales_name: l.sales_name || '', sales_phone: l.sales_phone || '', pickups: [], escort: '', escort_phone: '', remark: '', items: [], photos: [], sig: false, more: false }; };
  const yiyuan = () => F.orgs.some(o => /一院/.test(o));
  const fmt = n => String(Math.round(n * 1000) / 1000);
  const PH_OK = /^[\d\-+ ()（）转]{3,30}$/;

  async function start() {
    try { opt = await req('/api/guest/form'); if (typeof nmSet === 'function') try { nmSet(opt.names); } catch (e) { } } catch (e) { app.innerHTML = `<div class="empty" style="padding:60px 20px;text-align:center">打不开登记页：${esc(e.message)}</div>`; return; }
    F = fresh(); render();
  }
  const two = (a, b) => `<div class="two">${a}${b}</div>`;
  const fld = (lab, id, v, extra) => `<div><span class="lab">${lab}</span><input class="inp" id="${id}" value="${esc(v)}" ${extra || ''}></div>`;
  function render() {
    const lo = last().orgs || [];
    const orgList = lo.concat(opt.orgs.filter(o => !lo.includes(o))).concat(F.orgs.filter(o => !lo.includes(o) && !opt.orgs.includes(o)));
    const freq = opt.products.filter(p => p.uses > 0).sort((a, b) => b.uses - a.uses).slice(0, 12);
    app.innerHTML = `<div class="wrap"><div class="g-h"><h1>访客登记借用</h1><div class="d">${esc(opt.site)} · 只有<b>单位</b>和<b>借什么</b>必填，提交后等库房确认</div></div>
      <div class="sec"><span class="lab">借用单位 <span class="req">*</span><small class="muted">　可多选</small></span>
        <div class="chips g-big" id="gO">${orgList.map(o => `<button data-o="${esc(o)}" class="${F.orgs.includes(o) ? 'on' : ''}">${esc(o)}</button>`).join('')}</div>
        <div style="display:flex;gap:8px;margin-top:10px"><input class="inp" id="gOn" placeholder="其他单位，写上后点「加上」"><button class="btn" id="gOa" style="padding:0 18px;white-space:nowrap;flex:none">加上</button></div>
        <div id="gE" style="display:${yiyuan() ? '' : 'none'}">${two(fld('随车技术人员', 'gEn', F.escort), fld('随车人员电话', 'gEp', F.escort_phone, 'inputmode="tel"'))}</div></div>
      <div class="sec"><h2>借什么 <span class="req">*</span><small>点一下加 1，数不清可点「若干」</small></h2>
        ${freq.length ? `<div class="picks g-picks" id="gPk">${freq.map(p => `<div class="pick ${F.items.some(i => i.product_id === p.id) ? 'on' : ''}" data-p="${p.id}">${esc(p.label)}<small>${esc(p.unit)}</small></div>`).join('')}</div>` : ''}
        <div class="ac" style="margin-top:10px"><input class="inp" id="gQ" placeholder="搜物品名称，找不到就直接写" autocomplete="off"><div class="drop" id="gD" style="display:none"></div></div>
        <div id="gL" style="margin-top:8px"></div></div>
      <div class="sec"><h2>联系人 <small>都可以不填</small></h2>
        ${two(fld('客户姓名', 'gCn', F.cust_name, 'autocomplete="name"'), fld('客户电话', 'gCp', F.cust_phone, 'inputmode="tel" autocomplete="tel"'))}
        ${two(fld('销售人姓名', 'gSn', F.sales_name), fld('销售人电话', 'gSp', F.sales_phone, 'inputmode="tel"'))}
        <div id="gPu">${F.pickups.map((p, i) => `<div class="g-pu">${two(fld('取货人姓名' + (F.pickups.length > 1 ? ' ' + (i + 1) : ''), 'gPn' + i, p.name), fld('取货人电话', 'gPp' + i, p.phone, 'inputmode="tel"'))}<button class="x g-pux" data-pux="${i}" aria-label="去掉这个取货人">×</button></div>`).join('')}</div>
        <button class="btn g-add" id="gPa">＋ 添加取货人</button></div>
      <div class="sec"><button class="g-more" id="gMore">${F.more ? '收起' : '备注 / 照片 / 签名（可不填）'} <span>${F.more ? '▴' : '▾'}</span></button>
        <div id="gMoreB" style="display:${F.more ? '' : 'none'}"><span class="lab">备注</span><input class="inp" id="gR" value="${esc(F.remark)}" maxlength="300">
        <span class="lab">照片（最多 3 张）</span><div class="photos" id="gPh"></div><button class="btn" id="gCam" style="margin-top:8px">拍照 / 选照片</button>
        <span class="lab">签名</span><canvas class="sig" id="gS"></canvas><div class="sigbar"><span>用手指在灰色框里签名</span><a id="gSc">重签</a></div></div></div>
      <div style="height:8px"></div></div>
      <div class="bar"><div class="sum"><b id="gSum">0 样</b><small id="gSumO">${esc(F.orgs.join('、') || '还没选单位')}</small></div><button class="btn pri" id="gGo">提交登记</button></div>`;
    bind(); drawItems(); drawPhotos();
  }
  function keep() {
    const v = id => { const e = $('#' + id); return e ? e.value.trim() : null; };
    ['cust_name:gCn', 'cust_phone:gCp', 'sales_name:gSn', 'sales_phone:gSp', 'escort:gEn', 'escort_phone:gEp', 'remark:gR'].forEach(x => { const [k, id] = x.split(':'); const y = v(id); if (y !== null) F[k] = y; });
    F.pickups.forEach((p, i) => { const n = v('gPn' + i), ph = v('gPp' + i); if (n !== null) p.name = n; if (ph !== null) p.phone = ph; });
    if (F.sig && $('#gS')) F.sigData = $('#gS').toDataURL('image/png');
  }
  function drawItems() {
    const multi = F.orgs.length > 1;
    $('#gL').innerHTML = F.items.map((it, i) => `<div class="ln" data-i="${i}"><div class="nm">${esc(it.label)}${multi ? `<br><select data-org="${i}">${[''].concat(F.orgs, [opt.shared]).map(o => `<option value="${esc(o)}" ${it.org === o ? 'selected' : ''}>${o ? esc(o) : '归属哪个单位…'}</option>`).join('')}</select>` : ''}</div>
      <button class="btn ${it.approx ? 'pri' : ''}" data-ap="${i}" style="height:40px;padding:0 12px">若干</button>
      ${it.approx ? '' : `<div class="step"><button data-d="-1">−</button><input inputmode="decimal" data-q="${i}" value="${it.qty ? fmt(it.qty) : ''}"><button data-d="1">+</button></div>`}<button class="x" data-rm="${i}" aria-label="去掉">×</button></div>`).join('');
    $('#gSum').textContent = F.items.length + ' 样';
    const so = $('#gSumO'); if (so) so.textContent = F.orgs.join('、') || '还没选单位';
    $$('#gPk .pick').forEach(d => d.classList.toggle('on', F.items.some(x => x.product_id === +d.dataset.p)));
  }
  function drawPhotos() { $('#gPh').innerHTML = F.photos.map((p, i) => `<div class="ph-w"><img class="ph-i" src="${p}"><b data-pr="${i}">×</b></div>`).join(''); }
  function add(p, name) {
    const it = p && F.items.find(x => x.product_id === p.id);
    if (it) { if (!it.approx) it.qty = (+it.qty || 0) + 1; }
    else if (F.items.length >= 30) return err('一次最多 30 样');
    else F.items.push(p ? { product_id: p.id, label: p.label, qty: 1, approx: 0, org: '' } : { product_name: name, label: name, qty: 1, approx: 0, org: '' });
    drawItems();
  }
  function bind() {
    $('#gO').onclick = e => { const b = e.target.closest('[data-o]'); if (!b) return; keep(); const o = b.dataset.o; F.orgs = F.orgs.includes(o) ? F.orgs.filter(x => x !== o) : F.orgs.concat([o]); render(); };
    $('#gOa').onclick = () => { const v = $('#gOn').value.trim(); if (!v) return; keep(); if (!F.orgs.includes(v)) F.orgs.push(v); render(); };
    const q = $('#gQ'), D = $('#gD');
    const show = () => {
      const k = q.value.trim().toLowerCase(); if (!k) { D.style.display = 'none'; return; }
      const xs = opt.products.filter(p => p.label.toLowerCase().includes(k)).slice(0, 8);
      const exact = xs.some(p => p.label.toLowerCase() === k);
      D.innerHTML = xs.map(p => `<div data-p="${p.id}">${esc(p.label)} <small>${esc(p.unit)}</small></div>`).join('') + (exact ? '' : `<div data-new="1">写的是：「${esc(q.value.trim())}」<small>　（列表里没有就用这个）</small></div>`);
      D.style.display = '';
    };
    let bt = 0; const show2 = () => { clearTimeout(bt); show(); };
    q.oninput = show2; q.onfocus = show2; q.onblur = () => { clearTimeout(bt); bt = setTimeout(() => { D.style.display = 'none'; }, 200); };
    D.onmousedown = e => e.preventDefault();
    D.onclick = e => { const d = e.target.closest('div[data-p],div[data-new]'); if (!d) return; if (d.dataset.new) add(null, q.value.trim().slice(0, 60)); else add(opt.products.find(p => p.id === +d.dataset.p)); q.value = ''; D.style.display = 'none'; q.blur(); };
    const pk = $('#gPk'); if (pk) pk.onclick = e => { const d = e.target.closest('[data-p]'); if (d) add(opt.products.find(p => p.id === +d.dataset.p)); };
    const L = $('#gL');
    L.onclick = e => {
      const t = e.target;
      if (t.dataset.rm !== undefined) { F.items.splice(+t.dataset.rm, 1); drawItems(); return; }
      if (t.dataset.ap !== undefined) { const it = F.items[+t.dataset.ap]; it.approx = it.approx ? 0 : 1; it.qty = it.approx ? 0 : 1; drawItems(); return; }
      const b = t.closest('.step button'); if (b) { const i = +b.parentElement.querySelector('input').dataset.q; const it = F.items[i]; it.qty = Math.max(0, (+it.qty || 0) + (+b.dataset.d)); if (!it.qty) F.items.splice(i, 1); drawItems(); }
    };
    L.oninput = e => { if (e.target.dataset.q !== undefined) F.items[+e.target.dataset.q].qty = +e.target.value || 0; };
    L.onchange = e => { if (e.target.dataset.org !== undefined) F.items[+e.target.dataset.org].org = e.target.value; };
    $('#gCam').onclick = () => {
      if (F.photos.length >= 3) return err('最多 3 张照片');
      const i = document.createElement('input'); i.type = 'file'; i.accept = 'image/*'; i.capture = 'environment';
      i.onchange = async () => { for (const f of Array.from(i.files || []).slice(0, 3 - F.photos.length)) { try { F.photos.push(await compress(f)); } catch (e) { err(e.message); } } drawPhotos(); };
      i.click();
    };
    $('#gPh').onclick = e => { const b = e.target.dataset.pr; if (b !== undefined) { F.photos.splice(+b, 1); drawPhotos(); } };
    sigPad($('#gS'));
    $('#gSc').onclick = () => { const c = $('#gS'); c.getContext('2d').clearRect(0, 0, c.width, c.height); F.sig = false; F.sigData = ''; };
    $('#gPa').onclick = () => { keep(); F.pickups.push({ name: '', phone: '' }); render(); const i = $('#gPn' + (F.pickups.length - 1)); if (i) i.focus(); };
    $('#gPu').onclick = e => { const x = e.target.dataset.pux; if (x === undefined) return; keep(); F.pickups.splice(+x, 1); render(); };
    $('#gMore').onclick = () => { keep(); F.more = !F.more; render(); };
    $('#gGo').onclick = submit;
  }
  function sigPad(c) {
    const r = window.devicePixelRatio || 1; c.width = c.clientWidth * r; c.height = c.clientHeight * r;
    const g = c.getContext('2d'); g.scale(r, r); g.lineWidth = 2.4; g.lineCap = 'round'; g.lineJoin = 'round'; g.strokeStyle = '#1d2129';
    if (F.sigData) { const im = new Image(); im.onload = () => g.drawImage(im, 0, 0, c.clientWidth, c.clientHeight); im.src = F.sigData; }
    let on = false; const pos = e => { const b = c.getBoundingClientRect(); return [e.clientX - b.left, e.clientY - b.top]; };
    c.onpointerdown = e => { on = true; c.setPointerCapture(e.pointerId); const [x, y] = pos(e); g.beginPath(); g.moveTo(x, y); };
    c.onpointermove = e => { if (!on) return; const [x, y] = pos(e); g.lineTo(x, y); g.stroke(); F.sig = true; };
    c.onpointerup = c.onpointercancel = () => { on = false; };
  }
  let busy = false;
  async function submit() {
    if (busy) return; keep();
    if (!F.orgs.length) { const v = $('#gOn').value.trim(); if (v) F.orgs.push(v); }
    if (!F.orgs.length) return err('请选或填借用单位');
    if (!F.items.length) return err('请至少选一样要借的东西');
    if (F.items.some(i => !i.approx && !(+i.qty > 0))) return err('有物品没填数量（数不清可点「若干」）');
    if (F.orgs.length > 1 && F.items.some(i => !i.org)) return err('借了多个单位，请给每样东西选归属（或「' + opt.shared + '」）');
    const bad = [['客户', F.cust_phone], ['销售人', F.sales_phone]].concat(F.pickups.map(p => ['取货人', p.phone])).find(([, v]) => v && !PH_OK.test(v));
    if (bad) return err(bad[0] + '电话不对（可以不填）');
    busy = true; const btn = $('#gGo'); btn.disabled = true; btn.textContent = '正在提交…';
    try {
      const body = { orgs: F.orgs, cust_name: F.cust_name, cust_phone: F.cust_phone, sales_name: F.sales_name, sales_phone: F.sales_phone,
        pickups: F.pickups.filter(p => p.name || p.phone), escort: yiyuan() ? F.escort : '', escort_phone: yiyuan() ? F.escort_phone : '', remark: F.remark,
        items: F.items.map(i => ({ product_id: i.product_id || null, product_name: i.product_name || '', qty: i.qty, approx: i.approx, org: F.orgs.length > 1 ? i.org : '' })),
        photos: F.photos, signature: F.sig && $('#gS') ? $('#gS').toDataURL('image/png') : '' };
      const r = await req('/api/guest/submit', body); remember();
      app.innerHTML = `<div class="ok-big"><div class="c">✓</div><h2>已提交</h2><div class="muted" style="margin-top:8px;line-height:1.7">登记号 #${esc(r.no)}<br>请等库房人员核对确认后再拿东西</div>
        <button class="btn pri blk" id="gAgain" style="margin-top:28px">再登记一笔</button><div class="muted" style="font-size:13px;margin-top:10px">单位、销售人会自动带上</div></div>`;
      $('#gAgain').onclick = () => { F = fresh(); render(); window.scrollTo(0, 0); };
      window.scrollTo(0, 0);
    } catch (e) { err(e.message); btn.disabled = false; btn.textContent = '提交登记'; }
    busy = false;
  }
  start();
})();
