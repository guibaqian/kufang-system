/* 手机端：出库、出入库情况、借用归还、库房杂物拍照登记、待补全快速记、电脑扫码传照片 */
'use strict';
const IC = {
  out: '<svg viewBox="0 0 24 24"><path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4M10 12h5M10 16h5"/></svg>',
  cyl: '<svg viewBox="0 0 24 24"><rect x="8" y="6" width="8" height="15" rx="3"/><path d="M10 6V3h4v3"/></svg>',
  misc: '<svg viewBox="0 0 24 24"><path d="M3 8l9-5 9 5v8l-9 5-9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/></svg>',
  loan: '<svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3"/><path d="M18 3v4h-4M6 21v-4h4"/></svg>',
  cam: '<svg viewBox="0 0 24 24"><path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/></svg>',
  inn: '<svg viewBox="0 0 24 24"><path d="M12 3v12"/><path d="M8 11l4 4 4-4"/><path d="M5 19h14"/></svg>',
  bottle: '<svg viewBox="0 0 24 24"><path d="M9 3h6M10 3v3a5 5 0 0 0-3 4.6V20a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1v-9.4A5 5 0 0 0 14 6V3"/><path d="M7 13h10"/></svg>'
};
const WK = '日一二三四五六';
/* 手机端导航（修「借用归还进去回不来」）：
   - 每次路由给当前历史记录打上序号 mIdx（history.state），并在 sessionStorage 记下每个序号对应的页面；
   - 页面顶部「‹ 返回」= 回到上一级（子页回列表，其余回首页）：上一级若就在历史里，用 history.go(-n) 真后退；不在就 location.replace（不新增记录）；
   - 「回首页」「再记一笔」同理，绝不 push 重复记录，所以系统返回键 / 手势返回不会来回打转；
   - 路由时关掉残留的弹窗（密码框、看大图），免得盖住新页面点不动。 */
const M = {
  idx: 0, started: false, rep: false,
  PARENT: { ret: 'loan', req: 'loan' },             // 其余页面的上一级都是首页
  hist() { try { return JSON.parse(sessionStorage.getItem('mHist') || '[]'); } catch (e) { return []; } },
  page(h) { return (h || '').replace(/^#/, '').split('/')[0]; },
  async start() {
    try { await loadBoot(); } catch (e) { document.getElementById('app').innerHTML = '<div class="empty">连不上电脑上的库房系统：' + esc(e.message) + '</div>'; return; }
    window.addEventListener('hashchange', () => M.route()); M.route();
  },
  track() {
    const st = history.state; let H = M.hist();
    if (st && typeof st.mIdx === 'number') M.idx = st.mIdx;          // 后退 / 前进 / 刷新：沿用
    else {
      if (!M.started) { M.idx = 0; H = []; }                          // 新打开的页面
      else if (!M.rep) M.idx += 1;                                    // 点链接新进入一页
      try { history.replaceState({ mIdx: M.idx }, ''); } catch (e) { }
      H.length = M.idx;                                               // 新进入时，之后的“前进”记录作废
    }
    H[M.idx] = location.hash.replace(/^#/, ''); M.rep = false; M.started = true;
    try { sessionStorage.setItem('mHist', JSON.stringify(H)); } catch (e) { }
  },
  route() {
    M.track();
    document.querySelectorAll('body > .ov, body > .big-img, body > .iv-ov').forEach(x => x.remove());
    const [p, arg] = location.hash.slice(1).split('/');
    // 换一个全新的 #app（旧页面用 addEventListener 挂的事件一起丢掉，不会越积越多）
    const old = document.getElementById('app'), el = old.cloneNode(false); old.replaceWith(el); window.scrollTo(0, 0);
    (MP[p] || MP.home)(el, arg ? decodeURIComponent(arg) : '').catch(fail);
  },
  replace(h) {   // 换页但不新增历史记录
    if (location.hash.replace(/^#/, '') === h) { M.route(); return; }
    M.rep = true; location.replace('#' + h);
  },
  goTo(h) {      // 回到 h：历史里有就真后退过去，没有就 replace
    const H = M.hist(), pg = M.page(h);
    for (let k = M.idx - 1; k >= 0; k--) if (H[k] != null && M.page(H[k]) === pg && (pg !== '' || H[k] === '')) { history.go(k - M.idx); return; }
    M.replace(h);
  },
  back() { const p = M.page(location.hash); M.goTo(p in M.PARENT ? M.PARENT[p] : ''); },
  home() { M.goTo(''); },
  top(title, right) { return `<div class="top"><button class="back" onclick="M.back()" aria-label="返回">‹ 返回</button><h1>${esc(title)}</h1><span class="r">${right || ''}</span></div>`; },
  done(msg, again) {
    const el = document.getElementById('app');
    el.innerHTML = `<div class="ok-big"><div class="c">✓</div><h2>${esc(msg)}</h2>
      <div class="ok-sub muted">已存到电脑主机 · 不用再录一遍</div>
      <div class="ok-acts">
        <button class="btn pri blk" id="again">再记一笔</button>
        <button class="btn blk" id="goHome">回首页</button>
      </div></div>`;
    $('#goHome').onclick = () => M.home();
    $('#again').onclick = () => M.replace(again);
  }
};
function stepper(v) { return `<div class="step"><button data-d="-1">−</button><input inputmode="decimal" value="${v === '' || v == null ? '' : esc(v)}"><button data-d="1">+</button></div>`; }
function bindSteps(el, onChange) {
  el.addEventListener('click', e => {
    const b = e.target.closest('.step button'); if (!b) return;
    const i = $('input', b.parentElement); i.value = Math.max(0, (+i.value || 0) + (+b.dataset.d)) || ''; onChange && onChange(i);
  });
  el.addEventListener('input', e => { if (e.target.closest('.step')) onChange && onChange(e.target); });
}
function camBox(el, opt) {
  el.innerHTML = `<button class="cam" data-shot>${IC.cam}${esc(opt && opt.label || '点这里拍照')}</button><div class="phs"></div>`;
  const ph = photoBox($('.phs', el), [], { capture: true });
  $('[data-shot]', el).onclick = async () => {
    const fs = await pickFiles('image/*', false, true);
    for (const f of fs) { try { ph.add(await uploadPhoto(f, opt && opt.extra)); } catch (e) { fail(e); } }
  };
  return ph;
}

const MP = {};
MP.home = async el => {
  const me = (PIN.get() || {}).name;
  const h = await api('/api/home');
  const d = new Date();
  const mine = h.recent.filter(r => !me || r.by === me).slice(0, 4);
  const loanSub = (h.loans.n ? h.loans.n + ' 单未还' : '借出 / 归还') + (h.loan_req ? ' · 待确认' : '');
  const pendCls = (h.pending.over7 || h.pending.over30) ? 'w' : '';
  el.innerHTML = `<div class="wrap"><div class="hello"><div class="d">${d.getMonth() + 1}月${d.getDate()}日 星期${WK[d.getDay()]}</div>
    <h1>${me ? '你好，' + esc(me) : '库房'}${me ? '<a onclick="PIN.clear();M.route()">换人</a>' : ''}</h1></div>
    <div class="home2">
      <a class="huge pri" href="#out"><span class="ic">${IC.out}</span><b>出库</b><small>客户自提 / 换货 / U8 · 拍单点选</small></a>
      <a class="huge" href="#print/in"><span class="ic">${IC.inn}</span><b>打印入库单</b><small>只打印纸单 · 不入账不进库存</small></a>
    </div>
    <div class="mini mini4" title="次要入口">
      <a href="#cyl"><b>日表</b><small>交接表一车一份</small></a>
      <a class="big-loan" href="#loan"><b>借用</b><small>${esc(loanSub)}</small></a>
      <a href="#pend"><b>待补全</b><small class="${pendCls}">${h.pending.n} 笔</small></a>
      <a href="#more"><b>更多</b><small>杂物 · 打印 · 设置</small></a>
    </div>
    <div class="sec"><h2>${me ? '我最近录的' : '最近记录'}<small>直接存到电脑，无需再录</small></h2>
      ${mine.map(r => `<div class="rec">${r.photo ? `<img src="/photos/${esc(r.photo)}">` : '<span class="np"></span>'}<div class="tx">${esc(r.title)}<small>${esc(r.type)} · ${esc(r.desc)}</small>${rmkLine(r.remark)}</div><span class="dt">${esc(md(r.date))}</span></div>`).join('') || '<div class="empty">还没有记录</div>'}</div>
    <a class="mfoot" href="#settings">设置 · 关于 · 版本 ${esc(S.boot.version || '')}</a></div>`;
};

/* 更多：杂物 / 打印出库单 / 设置（主路径不占迷你四格） */
MP.more = async el => {
  el.innerHTML = M.top('更多') + `<div class="wrap">
    <a class="big" href="#misc"><span class="ic">${IC.misc}</span><div><b>库房杂物</b><small>拍照登记 · 不计库存</small></div><span class="go">›</span></a>
    <a class="big" href="#print/out"><span class="ic">${IC.out}</span><div><b>打印出库单</b><small>只打印纸单 · 不入账</small></div><span class="go">›</span></a>
    <a class="big" href="#print/in"><span class="ic">${IC.inn}</span><div><b>打印入库单</b><small>进库存请用电脑「到货」</small></div><span class="go">›</span></a>
    <a class="big" href="#print/lox"><span class="ic">${IC.bottle}</span><div><b>液氧打印表</b><small>从打印进 · 正式改表用电脑</small></div><span class="go">›</span></a>
    <a class="big" href="#mine"><span class="ic">${IC.cam}</span><div><b>待补全清单</b><small>签字回传等</small></div><span class="go">›</span></a>
    <a class="big" href="#settings"><span class="ic">${IC.cyl}</span><div><b>设置 · 关于</b><small>版本与访客二维码</small></div><span class="go">›</span></a>
    <div class="hint" style="padding:8px 4px 20px">正式进库存的到货、液氧质检入库请在电脑上操作；手机两大钮不会改库存。液氧打印表请用电脑「打印 → 液氧表」。</div>
  </div>`;
};


/* ---------- 打印：出库单 / 入库单（手机填写后浏览器打印；不写业务库存） ---------- */
MP.print = async (el, arg) => {
  if (arg === 'lox') {
    el.innerHTML = M.top('液氧打印表') + `<div class="wrap">
      <div class="sec"><h2>液氧打印表</h2>
        <p style="line-height:1.55;margin:8px 0">用途：打印电脑「报表 · 液氧表」纸质对照（与下载 Excel 一致）。</p>
        <div class="hint"><b>本次打印不改表数据</b>，也不进到货/库存。出库单/入库单才是「不入账」空白纸单。改数、登记到车、质检入库请用电脑「报表 · 液氧表」或「打印 → 液氧表」。</div>
      </div>
      <a class="big" href="#print/in"><span class="ic">${IC.inn}</span><div><b>改打入库单</b><small>不入账纸单</small></div><span class="go">›</span></a>
      <a class="big" href="#print/out"><span class="ic">${IC.out}</span><div><b>改打出库单</b><small>不入账纸单</small></div><span class="go">›</span></a>
      <div class="hint" style="padding:8px 4px 20px">手机端不直接改液氧表；请到电脑主机打开系统 → 顶栏「打印」→「液氧表」→「打印液氧表」。</div>
    </div>`;
    return;
  }
  const kind = (arg === 'out' || arg === 'in') ? arg : 'in';
  let pack; try { pack = await api('/api/print/templates'); } catch (e) { fail(e); return; }
  const tpl = (pack.templates || {})[kind] || {};
  const fields = tpl.fields || {};
  const cols = (tpl.line_cols || []).filter(c => c.show !== false);
  const groups = (pack.field_groups && pack.field_groups[kind]) || (kind === 'out'
    ? [['基本信息', ['date', 'party', 'dept', 'handler', 'out_no']], ['取货与送达', ['picker', 'phone', 'contact', 'dest', 'purpose', 'leader']]]
    : [['基本信息', ['date', 'party', 'dept', 'handler', 'in_no']], ['收货信息', ['receiver', 'phone', 'contact', 'location']]]);
  const st = { date: today(), party: '', dept: '', picker: '', phone: '', purpose: '', dest: '', leader: '',
    handler: (PIN.get() || {}).name || '', contact: '', out_no: '', in_no: '', receiver: '', location: '', remark: '',
    lines: [{ name: '', spec: '', qty: '', unit: '', batch: '' }, { name: '', spec: '', qty: '', unit: '', batch: '' }] };
  const lab = k => (fields[k] || {}).label || k;
  const show = k => (fields[k] || {}).show !== false;
  const title = tpl.title || (kind === 'out' ? '出库单' : '入库单');
  const draw = () => {
    let head = '';
    groups.forEach(([gt, keys]) => {
      const rows = keys.filter(show).map(k => {
        const typ = k === 'date' ? 'date' : 'text';
        return `<span class="lab">${esc(lab(k))}</span><input class="inp" data-f="${k}" type="${typ}" value="${esc(st[k] || '')}" placeholder="可不填">`;
      }).join('');
      if (rows) head += `<div class="sec"><h2>${esc(gt)}<small>可不填</small></h2>${rows}</div>`;
    });
    el.innerHTML = M.top(title, md(st.date)) + `<div class="wrap">${head}
      ${tpl.show_lines !== false ? `<div class="sec"><h2>产品行</h2>
        ${st.lines.map((ln, i) => `<div class="rec" style="display:block;padding:10px 0;border-bottom:1px solid var(--line)">
          ${cols.map(c => `<span class="lab">${esc(c.label)}</span><input class="inp" data-i="${i}" data-k="${c.key}" value="${esc(ln[c.key] || '')}">`).join('')}
        </div>`).join('')}
        <button class="btn sm" id="pAdd" style="margin-top:8px">＋ 加一行</button></div>` : ''}
      ${tpl.show_remark_area !== false && show('remark') ? `<div class="sec"><h2>${esc(lab('remark'))}</h2><input class="inp" data-f="remark" value="${esc(st.remark)}" placeholder="可不填"></div>` : ''}
      <div class="hint" style="padding:4px 2px 20px"><b>不入账、不进库存。</b>正式进库存的到货请用电脑「到货」页；这里只打印纸单（浏览器打印）。</div>
    </div>
    <div class="bar"><div class="sum"><b>${esc(title)}</b><small>浏览器打印</small></div><button class="btn pri" id="pGo">打印</button></div>`;
    const snap = () => {
      $$('[data-f]', el).forEach(i => { st[i.dataset.f] = i.value; });
      $$('[data-k]', el).forEach(i => { const ln = st.lines[+i.dataset.i]; if (ln) ln[i.dataset.k] = i.value; });
    };
    $('#pAdd', el) && ($('#pAdd', el).onclick = () => { snap(); st.lines.push({ name: '', spec: '', qty: '', unit: '', batch: '' }); draw(); });
    $('#pGo', el).onclick = () => {
      snap();
      const co = (tpl.company || ((S.boot.settings.print || {}).company) || '');
      const cell = k => {
        if (!show(k)) return '';
        return `<td class="mk"><span class="mk-l">${esc(lab(k))}</span><span class="mk-v">${esc(st[k] || '')}</span></td>`;
      };
      let meta = '';
      groups.forEach(([, keys]) => {
        const cells = keys.map(cell).filter(Boolean);
        for (let i = 0; i < cells.length; i += 3) {
          const chunk = cells.slice(i, i + 3);
          while (chunk.length < 3) chunk.push('<td class="mk empty"></td>');
          meta += '<tr>' + chunk.join('') + '</tr>';
        }
      });
      let rows = st.lines.slice();
      while (rows.length < (tpl.blank_rows || 5)) rows.push({ name: '', spec: '', qty: '', unit: '', batch: '' });
      let html = `<style>
        .pr-sheet .mk{border:1px solid #000;padding:5px 8px;vertical-align:top;width:33.33%;text-align:left}
        .pr-sheet .mk.empty{border-color:transparent}
        .pr-sheet .mk-l{display:block;font-size:9pt;color:#333;margin-bottom:2px}
        .pr-sheet .mk-v{display:block;min-height:1.2em;font-size:11pt}
        .pr-sheet .meta{border-collapse:collapse;width:100%;margin:6px 0 12px}
        .pr-sheet .sec-t{font-size:10pt;margin:10px 0 4px;font-weight:bold;border-bottom:1px solid #000;padding-bottom:2px;text-align:left}
        .pr-sheet .sign{margin-top:18px;display:flex;justify-content:space-between;gap:12px;font-size:11pt}
        .pr-sheet .sign span{flex:1;text-align:left;border-bottom:1px solid #000;padding:4px 0 2px;min-height:28px}
      </style><div class="pr-sheet">`;
      if (co) html += '<div class="co">' + esc(co) + '</div>';
      html += '<div class="ttl">' + esc(title) + '</div>';
      if (meta) html += '<table class="meta">' + meta + '</table>';
      if (tpl.show_lines !== false && cols.length) {
        html += '<div class="sec-t">产品明细</div><table><thead><tr>' + cols.map(c => '<th>' + esc(c.label) + '</th>').join('') + '</tr></thead><tbody>';
        rows.forEach(ln => { html += '<tr>' + cols.map(c => '<td class="' + (c.key === 'name' || c.key === 'spec' ? 'l' : '') + '">' + esc(ln[c.key] || '') + '</td>').join('') + '</tr>'; });
        html += '</tbody></table>';
      }
      if (tpl.show_remark_area !== false && show('remark')) {
        html += '<div class="post" style="margin-top:12px;text-align:left;border:1px solid #000;padding:6px 8px"><b>' + esc(lab('remark')) + '：</b>' + esc(st.remark) + '</div>';
      }
      if (tpl.show_sign_area !== false) {
        html += kind === 'out'
          ? '<div class="sign"><span>取货人签字：</span><span>经办人：</span><span>日期：</span></div>'
          : '<div class="sign"><span>送货人签字：</span><span>收货/经办：</span><span>日期：</span></div>';
      }
      html += '</div>';
      printHtml(html, { font: '11pt', titleSize: '18pt', noCompany: true });
    };
  };
  draw();
};

/* ---------- 设置（手机简化版：只看，不改；完整设置在电脑上） ---------- */
MP.settings = async el => {
  const v = await api('/api/version'); const s = S.boot.settings; const base = (S.boot.lan || [])[0] || location.origin;
  const nm = Object.entries(s.ui_names || {});
  el.innerHTML = M.top('设置 · 关于') + `<div class="wrap">
    <div class="sec"><h2>关于</h2><div class="kv"><div><span>系统</span><b>${esc(s.site_name || v.name)}</b></div><div><span>版本</span><b id="mVer">${esc(v.version)}</b></div><div><span>打包日期</span><b>${esc(v.build_date)}</b></div><div><span>主机地址</span><b>${esc(base)}</b></div></div></div>
    <div class="sec"><h2>访客登记二维码 <small>外单位来借东西，让对方扫</small></h2><div style="text-align:center"><img src="/api/qr.svg?text=${encodeURIComponent(base + '/m/guest')}" style="width:180px;height:180px;background:#fff;border:1px solid var(--line);border-radius:10px"><div class="muted" style="font-size:13px;word-break:break-all">${esc(base)}/m/guest</div></div></div>
    <div class="sec"><h2>改过的名称 <small>${nm.length} 个</small></h2><div data-nonm>${nm.map(([a, b]) => `<div class="rec"><div class="tx">${esc(b)}<small>原名：${esc(a)}</small></div></div>`).join('') || '<div class="empty">都用默认名称</div>'}</div></div>
    <div class="sec"><h2>更新记录</h2>${v.changelog.map(c => `<div style="margin:6px 0 2px;font-weight:600">${esc(c.version)} <small class="muted" style="font-weight:400">${esc(c.date)}</small></div><ul style="margin:0;padding-left:18px;font-size:14px;line-height:1.7">${c.items.map(i => `<li>${esc(i)}</li>`).join('')}</ul>`).join('')}</div>
    <div class="hint" style="padding:12px 4px 24px">名称、人员和密码、车牌、配送员、打印、备份等设置请在电脑上打开系统 →「设置」修改，手机会跟着变。</div></div>`;
};

/* ---------- 出库（换货=换出↔换入两边） ---------- */
MP.out = async el => {
  const s = S.boot.settings; const kinds = s.out_kinds || [];
  const df = defs();
  const kind = df.out_kind === '' ? '' : (kinds.includes(df.out_kind) ? df.out_kind : (kinds[0] || ''));
  const f = { kind, source: df.out_source || '', u8_no: '', u8_type: '', customer: '', contact: '', phone: '', remark: '', items: [], side: 'out' };
  const freq = P.frequent(10);
  const bat = {};
  try { (await api('/api/batches')).items.forEach(p => { bat[p.id] = p.batches.filter(b => b.id); bat._t = bat._t || {}; bat._t[p.id] = !!p.batch_trusted; }); } catch (e) { }
  const sideOf = it => (it && it.side) === 'in' ? 'in' : 'out';
  const isEx = () => f.kind === '换货';
  const render = () => {
    const ex = isEx();
    const showKinds = !!f.source;
    const kindList = showKinds ? kindsForSource(f.source, kinds, '') : [];
    if (showKinds && f.kind && !kindList.includes(f.kind)) f.kind = '';
    const kindBlock = showKinds
      ? `<span class="lab">类型</span><div class="chips" id="oKind">${kindList.map(k => `<button data-v="${esc(k)}" class="${k === f.kind ? 'on' : ''}">${esc(k)}</button>`).join('')}</div>`
      : `<span class="lab">类型</span><div class="muted" style="font-size:13px;margin:4px 0 8px">先选单据来源</div>`;
    el.innerHTML = M.top(ex ? '换货' : '出库', md(today())) + `<div class="wrap">
    <div class="sec"><h2>单子照片<small>不识别文字，只做备份 · 可选</small></h2><div id="oCam"></div></div>
    <div class="sec"><h2>客户</h2><div><input class="inp" id="oC" placeholder="输入客户名称，能选以前的" value="${esc(f.customer)}"></div>
      <div class="two"><div><span class="lab">联系人</span><input class="inp" id="oK" value="${esc(f.contact)}"></div><div><span class="lab">电话</span><input class="inp" id="oT" inputmode="tel" value="${esc(f.phone)}"></div></div>
      <span class="lab">单据来源</span><div class="chips" id="oSrc">${s.sources.map(k => `<button data-v="${esc(k)}" class="${k === f.source ? 'on' : ''}">${esc(k)}</button>`).join('')}</div>
      <div id="oU8" style="display:${f.source === 'U8单' ? '' : 'none'}"><div class="two"><div><span class="lab">U8单号（可空）</span><input class="inp" id="oU8n" value="${esc(f.u8_no)}"></div><div><span class="lab">U8单细分（可空）</span><input class="inp" id="oU8t" list="u8tl" value="${esc(f.u8_type || '')}"></div></div>
      <datalist id="u8tl">${(s.u8_types || []).map(t => `<option value="${esc(t)}">`).join('')}</datalist></div>
      ${kindBlock}
      <span class="lab">备注（可空）</span><input class="inp" id="oR" value="${esc(f.remark || '')}"></div>
    ${ex ? `<div class="sec"><h2>换货 · 谁换谁<small>先点大按钮再点产品</small></h2>
      <div class="ex-sides" id="oSide">
        <button type="button" data-v="out" class="ex-big ${f.side === 'out' ? 'on' : ''}"><b>① 换出 · 发出</b><small>点这里再选产品 · 扣库存</small></button>
        <button type="button" data-v="in" class="ex-big ${f.side === 'in' ? 'on' : ''}"><b>② 换入 · 收回</b><small>点这里再选产品 · 加库存</small></button>
      </div>
      <div class="picks" id="oPk"></div><div style="margin-top:10px"><input class="inp" id="oQ" placeholder="搜产品 / 新产品名"></div>
      <div id="oLs"></div></div>`
     : `<div class="sec"><h2>点选产品<small>点一下 +1</small></h2><div class="picks" id="oPk"></div><div style="margin-top:10px"><input class="inp" id="oQ" placeholder="搜其他产品，或写新产品名"></div></div>
    <div class="sec" id="oLs"></div>`}
    </div>
    <div class="bar"><div class="sum"><b id="oSum">0 项</b><small id="oWho"></small></div><button class="btn pri" id="oSave">${ex ? '保存换货' : '保存'}</button></div>`;
    bind();
  };
  const bind = () => {
    const ph = camBox($('#oCam', el), { label: '点这里拍单子' });
    const ci = $('#oC', el);
    autoComplete(ci, custSource, c => { ci.value = c.name; f.customer = c.name; $('#oK', el).value = c.contact || ''; $('#oT', el).value = c.phone || ''; f.contact = c.contact || ''; f.phone = c.phone || ''; }, (c, q) => `${hl(c.name, q)}${c.contact ? ' · ' + esc(c.contact) : ''}<br><small>${esc(c.phone || '')}${c.last_date ? ' · 上次 ' + esc(md(c.last_date)) : ''}</small>`);
    const keepFields = () => {
      f.customer = ci.value.trim(); f.contact = $('#oK', el).value.trim(); f.phone = $('#oT', el).value.trim(); f.remark = $('#oR', el).value.trim();
      if (f.source === 'U8单') {
        const n = $('#oU8n', el), tp = $('#oU8t', el);
        if (n) f.u8_no = n.value.trim(); if (tp) f.u8_type = tp.value.trim();
      }
    };
    const kindEl = $('#oKind', el);
    if (kindEl) kindEl.onclick = e => {
      const b = e.target.closest('button'); if (!b) return;
      const prev = f.kind; f.kind = b.dataset.v;
      if (f.kind === '客户自提' && !f.source) f.source = 'app手工单';
      if (prev === '换货' && f.kind !== '换货') { f.items = f.items.filter(i => sideOf(i) === 'out'); f.items.forEach(i => delete i.side); }
      if (prev !== '换货' && f.kind === '换货') { f.items.forEach(i => { if (!i.side) i.side = 'out'; }); f.side = 'out'; }
      keepFields(); return render();
    };
    $('#oSrc', el).onclick = e => {
      const b = e.target.closest('button'); if (!b) return;
      const next = f.source === b.dataset.v ? '' : b.dataset.v;
      keepFields();
      f.source = next;
      if (next) {
        const allow = kindsForSource(next, kinds, '');
        if (f.kind && !allow.includes(f.kind)) f.kind = '';
        if (!f.kind) {
          const df = defs();
          const want = df.out_kind === '' ? '' : (kinds.includes(df.out_kind) ? df.out_kind : (kinds[0] || ''));
          if (want && allow.includes(want)) f.kind = want;
        }
      }
      render();
    };
    const sideEl = $('#oSide', el);
    if (sideEl) sideEl.onclick = e => { const b = e.target.closest('button'); if (!b) return; f.side = b.dataset.v; $$('#oSide button', el).forEach(x => x.classList.toggle('on', x.dataset.v === f.side)); draw(); };
    const curSide = () => isEx() ? f.side : 'out';
    const add = (p, name) => {
      const side = curSide();
      const it = p ? f.items.find(x => x.product_id === p.id && sideOf(x) === side) : f.items.find(x => x.product_name === name && sideOf(x) === side);
      if (it) it.qty = (+it.qty || 0) + 1; else f.items.push(p ? { product_id: p.id, qty: 1, batch_no: '', side } : { product_name: name, qty: 1, side });
      draw();
    };
    const draw = () => {
      const side = curSide();
      const list = isEx() ? f.items.filter(x => sideOf(x) === side) : f.items;
      $('#oPk', el).innerHTML = freq.map(p => { const it = list.find(x => x.product_id === p.id); return `<div class="pick ${it ? 'on' : ''}" data-p="${p.id}">${esc(p.name)}<small>${it ? '已选 ' + fmtN(it.qty) : esc(p.spec || '')}</small></div>`; }).join('');
      const rows = isEx()
        ? `<div class="muted" style="font-size:13px;margin:8px 0">当前在录：<b>${side === 'in' ? '换入（收回）' : '换出（发出）'}</b></div>` +
          (f.items.length ? ['out', 'in'].map(sd => {
            const its = f.items.map((it, i) => [it, i]).filter(([it]) => sideOf(it) === sd);
            if (!its.length) return '';
            return `<h2 style="margin-top:10px">${sd === 'in' ? '换入 · 收回' : '换出 · 发出'} ${its.length} 项</h2>` + its.map(([it, i]) => {
              const p = it.product_id && P.byId(it.product_id); const bs = p && p.batch_managed ? (bat[p.id] || []) : null;
              return `<div class="ln" data-i="${i}"><div class="nm">${esc(p ? p.label : it.product_name)}${p ? '' : '<small>新产品</small>'}</div>${stepper(it.qty)}</div>
                ${bs ? `<div class="bt">批号<select data-b="${i}"><option value="">${sd === 'out' ? '先进先出' : '可空'}</option>${bs.map(b => `<option ${it.batch_no === b.batch_no ? 'selected' : ''} value="${esc(b.batch_no)}">${esc(b.batch_no)} · ${+b.remain < 0 ? '剩' + fmtN(b.remain) + ' 需核对' : '剩 ' + fmtN(b.remain)}</option>`).join('')}</select></div>` : ''}`;
            }).join('');
          }).join('') : '<div class="empty">先点上面的「换出/换入」，再点产品</div>')
        : `<h2>本单 ${f.items.length} 项</h2>` + (f.items.map((it, i) => {
            const p = it.product_id && P.byId(it.product_id); const bs = p && p.batch_managed ? (bat[p.id] || []) : null;
            return `<div class="ln" data-i="${i}"><div class="nm">${esc(p ? p.label : it.product_name)}${p ? '' : '<small>新产品，保存时建档</small>'}</div>${stepper(it.qty)}</div>
              ${bs ? `<div class="bt">批号<select data-b="${i}"><option value="">先进先出（默认）</option>${bs.map(b => `<option ${it.batch_no === b.batch_no ? 'selected' : ''} value="${esc(b.batch_no)}">${esc(b.batch_no)} · ${+b.remain < 0 ? '剩' + fmtN(b.remain) + ' 需核对' : '剩 ' + fmtN(b.remain)}${b.expiry ? ' · ' + esc(b.expiry) : ''}</option>`).join('')}</select></div>` : ''}`;
          }).join('') || '<div class="empty">点上面的产品</div>');
      $('#oLs', el).innerHTML = rows;
      const outs = f.items.filter(x => sideOf(x) === 'out' && +x.qty > 0);
      const inns = f.items.filter(x => sideOf(x) === 'in' && +x.qty > 0);
      if (isEx()) $('#oSum', el).textContent = `出 ${outs.length} · 入 ${inns.length}`;
      else { const n = f.items.reduce((a, b) => a + (+b.qty || 0), 0); $('#oSum', el).textContent = `${f.items.length} 项 · ${fmtN(n)} 件`; }
      $('#oWho', el).textContent = ((PIN.get() || {}).name ? '经办 ' + PIN.get().name + ' · ' : '') + ph.ids.length + ' 张照片';
      bindSteps($('#oLs', el), i => { const ln = i.closest('.ln'); f.items[+ln.dataset.i].qty = +$('input', ln).value || 0; draw(); });
    };
    $('#oPk', el).onclick = e => { const d = e.target.closest('[data-p]'); if (d) add(P.byId(+d.dataset.p)); };
    const qi = $('#oQ', el);
    autoComplete(qi, async q => { const r = P.search(q).slice(0, 8); return q.trim() && !r.find(p => p.label === q.trim()) ? r.concat([{ _new: q.trim() }]) : r; },
      p => { if (p._new) add(null, p._new); else add(p); qi.value = ''; qi.blur(); }, (p, q) => p._new ? `新产品「${esc(p._new)}」` : hl(p.label, q));
    $('#oLs', el).addEventListener('click', e => { if (e.target.closest('.step button')) { const ln = e.target.closest('.ln'); const idx = +ln.dataset.i; if (!(+$('input', ln).value > 0)) f.items.splice(idx, 1); draw(); } });
    $('#oLs', el).addEventListener('change', e => { if (e.target.dataset.b !== undefined) f.items[+e.target.dataset.b].batch_no = e.target.value; });
    $('#oCam', el).addEventListener('click', () => setTimeout(draw, 1500));
    draw();
    $('#oSave', el).onclick = async () => {
      try {
        f.customer = ci.value.trim(); f.contact = $('#oK', el).value.trim(); f.phone = $('#oT', el).value.trim(); f.remark = $('#oR', el).value.trim();
        const items = f.items.filter(x => +x.qty > 0).map(x => Object.assign({}, x, { side: isEx() ? sideOf(x) : 'out' }));
        if (!items.length) throw new Error('还没选产品');
        if (!f.source) throw new Error('请选单据来源');
        if (!f.kind) throw new Error('请选类型');
        if (isEx()) {
          if (!items.some(x => sideOf(x) === 'out')) throw new Error('请选换出（发出）的产品');
          if (!items.some(x => sideOf(x) === 'in')) throw new Error('请选换入（收回）的产品');
        }
        const resolved = await resolveOutBatchItems(items, bat);
        f.items = resolved; draw();
        const d = { date: today(), kind: f.kind, source: f.source, u8_no: f.source === 'U8单' ? $('#oU8n', el).value.trim() : '', u8_type: f.source === 'U8单' ? $('#oU8t', el).value.trim() : '',
          customer: f.customer, contact: f.contact, phone: f.phone, remark: f.remark, items: resolved, mode: 'phone' };
        await save('/api/out/save', { data: d, photo_ids: ph.ids }, isEx() ? '保存换货' : '保存出库'); await loadBoot(); M.done(isEx() ? '换货已保存' : '出库已保存', 'out');
      } catch (e) { fail(e); }
    };
  };
  render();
};

/* ---------- 出入库情况：照纸质交接表，一辆车一份（钢瓶交接表 / 产品交接表） ---------- */
function mpParse(raw) {
  let x = String(raw || '').trim().replace(/＋/g, '+').replace(/\s/g, ''); if (!x) return { ok: true, v: null, txt: '' };
  x = x.replace(/(退|t)$/i, '');
  if (!/^\d+(\.\d+)?([+\-]\d+(\.\d+)?)*$/.test(x)) return { ok: false };
  let v = 0, sg = 1; x.match(/[+\-]|\d+(\.\d+)?/g).forEach(t => { if (t === '+') sg = 1; else if (t === '-') sg = -1; else v += sg * +t; }); return { ok: true, v, txt: x };
}
MP.cyl = async (el, arg) => {
  const st = { date: today(), ses: defs().session, form: 'cyl', plate: '', pd: null };
  const load = async () => { st.pd = await api('/api/paper?date=' + st.date); if (!st.pd.sessions.includes(st.ses)) st.ses = st.pd.sessions[0] || '早上'; };
  await load();
  const [af, ap] = (arg || '').split(':'); if (af === 'prod' || af === 'cyl') st.form = af;
  if (st.pd.plates.find(p => p.plate === (ap || ''))) st.plate = ap;
  const draw = () => {
    const pd = st.pd;
    const sh = pd.sheets.find(x => x.form === st.form && x.session === st.ses);
    const lay = sh ? sh.layout : pd.layout[st.form];
    const cur = sh && st.plate ? sh.rows.find(r => (r.plate || '').toLowerCase() === st.plate.toLowerCase()) : null;
    const cells = (cur && cur.cells) || {};
    const oth = pd.sheets.find(x => x.form !== st.form && x.session === st.ses);
    const orow = oth && st.plate ? oth.rows.find(r => (r.plate || '').toLowerCase() === st.plate.toLowerCase()) : null;
    const lids = new Set(['L', 'R'].flatMap(sd => lay[sd].filter(c => c.t === 'p').map(c => c.pid || c.fk)));
    const opids = new Set((orow ? orow.pids : []).filter(x => lids.has(x)));
    const mark = lay.lmode !== 'all';
    const line = (side, c) => { const k = side + '.' + c.k, raw = cells[k] || '', ret = /退$/.test(raw), id = c.t === 'p' ? (c.pid || c.fk) : null;
      return `<div class="ln pp ${id && opids.has(id) ? 'oth' : ''}" data-k="${k}" data-id="${id || ''}"><div class="nm">${esc((c.g ? c.g + ' ' : '') + c.n)}</div><input class="inp ppi" inputmode="tel" value="${esc(raw.replace(/退$/, ''))}">${side === 'L' && mark && c.t === 'p' ? `<button class="rtg ${ret ? 'on' : ''}" type="button">退</button>` : ''}</div>`; };
    const pinfo = pd.plates.find(p => p.plate === st.plate);
    const drv = (cur && (cur.driver || (S.boot.couriers.find(k => k.id === cur.courier_id) || {}).name)) || (pinfo && pinfo.name) || '';
    const bmP = Object.keys(pd.bm).filter(p => ['L', 'R'].some(sd => lay[sd].some(c => c.pid === +p)));
    const sb = p => (sh && sh.batches[p]) || pd.bm[p].fifo;
    el.innerHTML = M.top('出入库情况', md(st.date)) + `<div class="wrap">
      <div class="sec"><div class="two"><div><span class="lab">日期</span><input class="inp" type="date" id="pD" value="${st.date}"></div><div><span class="lab">场次（纸上表头）</span><div class="chips" id="pS">${pd.sessions.map(s => `<button class="${s === st.ses ? 'on' : ''}" data-v="${esc(s)}">${esc(s)}</button>`).join('')}</div></div></div>
        <span class="lab">哪张表</span><div class="chips" id="pF"><button data-v="cyl" class="${st.form === 'cyl' ? 'on' : ''}">钢瓶交接表</button><button data-v="prod" class="${st.form === 'prod' ? 'on' : ''}">产品交接表</button></div></div>
      <div class="sec"><h2>车牌</h2><div class="chips" id="pP">${pd.plates.map(p => { const done = sh && sh.rows.some(r => (r.plate || '').toLowerCase() === p.plate.toLowerCase()); return `<button class="${p.plate === st.plate ? 'on' : ''}" data-v="${esc(p.plate)}">${esc(p.plate)}${done ? ' ✓' : ''}</button>`; }).join('')}</div>
        <input class="inp" id="pX" placeholder="别的车牌（纸上多写的一行）" value="${esc(pd.plates.some(p => p.plate === st.plate) ? '' : st.plate)}" style="margin-top:8px">
        ${st.plate ? `<span class="lab">配送员（今天开这辆车的人）</span><input class="inp" id="pDv" list="pDl" value="${esc(drv)}"><datalist id="pDl">${S.boot.couriers.filter(k => k.active).map(k => `<option value="${esc(k.name)}">`).join('')}</datalist>` : ''}
        ${cur ? '<div class="muted" style="font-size:12.5px;margin-top:6px">这一行已录过，保存会改成下面的数（改动有记录）</div>' : ''}</div>
      ${st.plate ? `${opids.size ? '<div class="warn-m">另一张表这辆车也记了黄色标出的产品，请核对</div>' : ''}
        <div class="sec"><h2>${esc(lay.lt)}<small>${mark ? '纸上写了「退」的点一下「退」' : '只抄纸上的数，可写 10+2'}</small></h2>
          ${lay.L.map(c => line('L', c)).join('')}<span class="lab">备注</span><input class="inp" id="pNl" value="${esc((cur && cur.note_l) || '')}"></div>
        <div class="sec"><h2>${esc(lay.rt)}</h2>${lay.R.map(c => line('R', c)).join('')}<span class="lab">备注</span><input class="inp" id="pNr" value="${esc((cur && cur.note_r) || '')}"></div>
        ${bmP.length ? `<div class="sec"><h2>批次</h2>${bmP.map(p => `<span class="lab">${esc(pd.bm[p].name)}（整张表：${esc(sb(p) || '未选')}）</span><select class="inp" data-b="${p}"><option value="">跟整张表</option>${pd.bm[p].batches.map(b => `<option value="${esc(b.batch_no)}" ${cur && (cur.batches || {})[p] === b.batch_no ? 'selected' : ''}>${esc(b.batch_no)}（剩 ${b.remain}）</option>`).join('')}</select>`).join('')}</div>` : ''}
        <div class="sec"><h2>签好字的纸<small>可拍照附上</small></h2><div id="pPh"></div></div>` : '<div class="empty">先选车牌</div>'}</div>
      <div class="bar"><div class="sum"><b>${esc(st.plate ? st.plate + ' ' + drv : '未选车牌')}</b><small>${esc(st.ses)} · ${st.form === 'cyl' ? '钢瓶交接表' : '产品交接表'}</small></div><button class="btn pri" id="pSave" ${st.plate ? '' : 'disabled'}>保存</button></div>`;
    $('#pD', el).onchange = async e => { st.date = e.target.value || today(); await load(); draw(); };
    $('#pS', el).onclick = e => { const b = e.target.closest('button'); if (b) { st.ses = b.dataset.v; draw(); } };
    $('#pF', el).onclick = e => { const b = e.target.closest('button'); if (b) { st.form = b.dataset.v; draw(); } };
    $('#pP', el).onclick = e => { const b = e.target.closest('button'); if (b) { st.plate = b.dataset.v; draw(); } };
    $('#pX', el).onchange = e => { const v = e.target.value.trim(); if (v) { st.plate = v; draw(); } };
    el.onclick = e => { const b = e.target.closest('.rtg'); if (b) b.classList.toggle('on'); };
    el.oninput = e => { const t = e.target; if (!t.classList.contains('ppi')) return; const l = t.closest('.ln');
      if (/(退|t)$/i.test(t.value.trim()) && $('.rtg', l)) { $('.rtg', l).classList.add('on'); t.value = t.value.trim().replace(/(退|t)$/i, ''); }
      l.classList.toggle('bad', !mpParse(t.value).ok); };
    const ph = st.plate ? photoBox($('#pPh', el), [], { capture: true }) : null;
    $('#pSave', el).onclick = async () => {
      try {
        const cells = {}; let bad = false;
        $$('.ln.pp', el).forEach(l => { const v = $('input', l).value.trim(); if (!v) return; const p = mpParse(v); if (!p.ok) bad = true; cells[l.dataset.k] = (p.ok ? p.txt : v) + ($('.rtg.on', l) ? '退' : ''); });
        if (bad) throw new Error('有的数看不懂：只能写数字或 10+2');
        const batches = {}; $$('[data-b]', el).forEach(s => { if (s.value) batches[s.dataset.b] = s.value; });
        const row = { plate: st.plate, driver: $('#pDv', el).value.trim(), cells, batches, note_l: $('#pNl', el).value.trim(), note_r: $('#pNr', el).value.trim() };
        if (!Object.keys(cells).length && !row.note_l && !row.note_r && !cur) throw new Error('还没填数');
        await save('/api/paper/row', { data: { date: st.date, session: st.ses, form: st.form, row }, photo_ids: ph.ids }, '保存交接表');
        await loadBoot(); M.done(`${st.plate} ${st.ses}已记入`, 'cyl');
      } catch (e) { fail(e); }
    };
  };
  draw();
};

/* ---------- 借用归还：借出登记 + 未归还（点进去归还） ---------- */
MP.loan = async el => {
  const [r, rq] = await Promise.all([api('/api/loans?status=open'), api('/api/loan_req').catch(() => ({ items: [], pending: 0 }))]);
  const f = { orgs: '', items: [] }; const freq = P.frequent(8);
  el.innerHTML = M.top('借用归还', md(today())) + `<div class="wrap">
    ${rq.pending ? `<div class="sec"><h2>访客登记待确认 <small>${rq.pending} 条，确认前不动库存</small></h2>${rq.items.slice(0, 8).map(q => `<a class="rec" href="#req/${q.id}"><div class="tx">${esc(q.orgs.join("、"))}${q.cust_name || q.name ? " · " + esc(q.cust_name || q.name) : ""}<small>${esc(q.items.map(i => i.product_name + ' ' + (i.approx ? '若干' : fmtN(i.qty))).join('、'))}</small></div><span class="dt">#${q.id}</span></a>`).join('')}</div>` : ''}
    <div class="sec"><h2>未归还 <small>${r.items.length} 单，点一下去归还</small></h2>${r.items.slice(0, 8).map(l => `<a class="rec" href="#ret/${l.id}"><div class="tx">${esc(l.orgs.join('、') || l.user_to || l.handler)}<small>${esc(l.slip_no)} · ${esc(l.items.map(i => i.label + ' ' + (i.approx ? (i.qty_text || '若干') : (i.need_return ? fmtN(i.left) : '不用还'))).join('、'))}</small>${rmkLine(l.remark)}</div><span class="dt ${ageCls(l.date)}">${esc(md(l.date))}</span></a>`).join('') || '<div class="empty">没有未归还</div>'}
      ${r.items.length > 8 ? `<div class="muted" style="font-size:13px">还有 ${r.items.length - 8} 单，请在电脑上看</div>` : ''}</div>
    <div class="sec"><h2>借出登记</h2><span class="lab">给谁用</span><input class="inp" id="lU" placeholder="人名（可空）">
      <span class="lab">借用单位<small class="muted">　多个用顿号隔开</small></span><input class="inp" id="lO" placeholder="如：一院、二院" list="lOl"><datalist id="lOl">${r.orgs.map(o => `<option value="${esc(o.org)}">`).join('')}</datalist>
      <div id="lEw" style="display:none"><div class="two"><div><span class="lab">随车技术人员</span><input class="inp" id="lE"></div><div><span class="lab">电话</span><input class="inp" id="lEp" inputmode="tel"></div></div></div>
      <span class="lab"><a id="lEa" style="font-size:12.5px;font-weight:400">+随车人员</a><small class="muted">　每样东西可单独选要还 / 不用还</small></span>
      <span class="lab">备注（可空）</span><input class="inp" id="lM"></div>
    <div class="sec"><h2>物品<small>点「要还/不用还」；数不清点「若干」</small></h2><div class="picks" id="lPk"></div><div style="margin-top:10px"><input class="inp" id="lQ" placeholder="搜其他产品，或写新名称"></div><div id="lLs" style="margin-top:8px"></div></div>
    <div class="sec"><h2>照片<small>借条（可不拍）</small></h2><div id="lCam"></div></div></div>
    <div class="bar"><div class="sum"><b id="lSum">0 项</b><small>保存后自动编号</small></div><button class="btn pri" id="lSave">保存借出</button></div>`;
  const ph = camBox($('#lCam', el), { label: '拍借条' });
  const orgs = () => $('#lO', el).value.split(/[、,，\s]+/).map(x => x.trim()).filter(Boolean);
  const draw = () => {
    $('#lPk', el).innerHTML = freq.map(p => { const it = f.items.find(x => x.product_id === p.id); return `<div class="pick ${it ? 'on' : ''}" data-p="${p.id}">${esc(p.name)}<small>${it ? (it.approx ? '若干' : '已选 ' + fmtN(it.qty)) : esc(p.spec || '')}</small></div>`; }).join('');
    const os = orgs();
    $('#lLs', el).innerHTML = f.items.map((it, i) => {
      const p = it.product_id && P.byId(it.product_id);
      const nr = it.need_return === 0 || it.need_return === '0' ? 0 : 1; it.need_return = nr;
      return `<div class="ln" data-i="${i}"><div class="nm">${esc(p ? p.label : it.product_name)}
      ${os.length > 1 ? `<select data-org="${i}" style="margin-top:4px">${['', ...os, '共用'].map(o => `<option value="${esc(o)}" ${it.org === o ? 'selected' : ''}>${o ? esc(o) : '归属…'}</option>`).join('')}</select>` : ''}
      <div class="chips" style="margin-top:6px" data-nr="${i}"><button type="button" data-v="1" class="${nr ? 'on' : ''}">要还</button><button type="button" data-v="0" class="${nr ? '' : 'on'}">不用还</button></div></div>
      <button class="btn sm ${it.approx ? 'pri' : ''}" data-ap="${i}" style="margin-right:6px">若干</button>${it.approx ? '' : stepper(it.qty)}</div>`; }).join('');
    $('#lSum', el).textContent = f.items.length + ' 项';
  };
  const add = (p, name) => { const it = p && f.items.find(x => x.product_id === p.id); if (it) { if (!it.approx) it.qty = (+it.qty || 0) + 1; } else f.items.push(p ? { product_id: p.id, qty: 1, approx: 0, org: '', need_return: 1 } : { product_name: name, qty: 1, approx: 0, org: '', need_return: 1 }); draw(); };
  $('#lPk', el).onclick = e => { const d = e.target.closest('[data-p]'); if (d) add(P.byId(+d.dataset.p)); };
  const qi = $('#lQ', el);
  autoComplete(qi, async q => { const x = P.search(q).slice(0, 8); return q.trim() && !x.find(p => p.label === q.trim()) ? x.concat([{ _new: q.trim() }]) : x; },
    p => { if (p._new) add(null, p._new); else add(p); qi.value = ''; qi.blur(); }, (p, q) => p._new ? `新名称「${esc(p._new)}」` : hl(p.label, q));
  // 随车技术人员：只有特定「一院」类单位借用才有；输入含「一院」的单位自动出现，其他情况可点「+随车人员」
  let escMan = false;
  const escSync = () => { const on = escMan || orgs().some(o => /一院/.test(o)) || $('#lE', el).value.trim(); $('#lEw', el).style.display = on ? '' : 'none'; $('#lEa', el).style.display = on ? 'none' : ''; };
  $('#lEa', el).onclick = () => { escMan = true; escSync(); $('#lE', el).focus(); };
  $('#lO', el).addEventListener('input', escSync);
  $('#lO', el).onchange = () => { escSync(); draw(); };
  const L = $('#lLs', el);
  bindSteps(L, i => { const ln = i.closest('.ln'); f.items[+ln.dataset.i].qty = +i.value || 0; });
  L.addEventListener('click', e => {
    const nr = e.target.closest('[data-nr]');
    if (nr && e.target.dataset.v !== undefined) { f.items[+nr.dataset.nr].need_return = +e.target.dataset.v; draw(); return; }
    const a = e.target.dataset.ap; if (a !== undefined) { const it = f.items[+a]; it.approx = it.approx ? 0 : 1; it.qty = it.approx ? 0 : 1; draw(); return; }
    if (e.target.closest('.step button')) { const ln = e.target.closest('.ln'); if (!(+$('input', ln).value > 0)) { f.items.splice(+ln.dataset.i, 1); draw(); } }
  });
  L.addEventListener('change', e => { if (e.target.dataset.org !== undefined) f.items[+e.target.dataset.org].org = e.target.value; });
  $('#lSave', el).onclick = async () => {
    try {
      const os = orgs(); const u = $('#lU', el).value.trim();
      if (!f.items.length) throw new Error('还没选物品');
      if (!u && !os.length) throw new Error('请填给谁用，或借用单位');
      if (os.length > 1 && f.items.some(i => !i.org)) throw new Error('多个单位时，请给每样东西选归属（或「共用」）');
      const d = { date: today(), handler: (PIN.get() || {}).name || '', user_to: u, orgs: os, escort: $('#lE', el).value.trim(), phone: $('#lEp', el).value.trim(), remark: $('#lM', el).value.trim(), use_type: os.length ? '外单位' : '自用',
        items: f.items.map(i => Object.assign({}, i, { qty_text: i.approx ? '若干' : '', need_return: i.need_return === 0 || i.need_return === '0' ? 0 : 1 })) };
      if (!d.handler) { const p = await PIN.ask('保存借出'); d.handler = p.name; }
      const x = await save('/api/loan/save', { data: d, photo_ids: ph.ids }, '保存借出'); M.done('已借出 ' + x.slip_no, 'loan');
    } catch (e) { fail(e); }
  };
  draw();
};
MP.ret = async (el, id) => {
  const l = await api('/api/loan/one?id=' + id);
  const its = l.items.filter(i => (i.need_return ? (i.left > 0 || i.approx) : i.approx));
  el.innerHTML = M.top('归还', l.slip_no) + `<div class="wrap"><div class="sec"><h2>${esc(l.orgs.join('、') || l.user_to)}<small>${esc(l.date)} 借 · 经手 ${esc(l.handler)}${l.escort ? ' · 随车 ' + esc(l.escort) : ''}</small></h2>
    ${[['客户', [l.cust_name, l.cust_phone].filter(Boolean).join(' ')], ['销售人', [l.salesperson, l.sales_phone].filter(Boolean).join(' ')]].concat((l.pickups || []).map(p => ['取货人', [p.name, p.phone].filter(Boolean).join(' ')])).filter(x => x[1]).map(([k, v]) => `<div style="font-size:13.5px;margin-bottom:4px"><span class="muted">${k}</span> ${esc(v)}</div>`).join('')}
    ${its.map(i => `<div class="ln" data-id="${i.id}"><div class="nm">${esc(i.label)}<small>${i.approx ? esc(i.qty_text || '若干') + '，清点后填实借数' : '未还 ' + fmtN(i.left)}${i.org && l.orgs.length > 1 ? ' · ' + esc(i.org) : ''}</small>
      ${i.approx ? `<input class="inp" data-fq="${i.id}" inputmode="decimal" placeholder="实借数" style="margin-top:6px;width:120px">` : ''}</div>${stepper('')}</div>`).join('') || '<div class="empty">都还完了</div>'}
    <div style="margin-top:10px"><a id="rAll">全部还清</a></div>${rmkLine(rmkJoin(l.remark, l.items.map(i => i.note ? i.label + '：' + i.note : '')))}</div>
    <div class="sec"><span class="lab">这次归还备注（可空）</span><input class="inp" id="rM"></div>
    <div class="sec"><h2>照片<small>可不拍</small></h2><div id="rCam"></div></div></div>
    <div class="bar"><div class="sum"><b>这次还回</b><small>可以只还一部分</small></div><button class="btn pri" id="rSave">保存归还</button></div>`;
  bindSteps(el); const ph = camBox($('#rCam', el), { label: '拍一张（可不拍）' });
  $('#rAll', el).onclick = () => its.forEach(i => { if (!i.approx) $(`[data-id="${i.id}"] .step input`, el).value = fmtN(i.left); });
  $('#rSave', el).onclick = async () => {
    try {
      const items = its.map(i => ({ loan_item_id: i.id, qty: $(`[data-id="${i.id}"] .step input`, el).value, final_qty: i.approx ? $(`[data-fq="${i.id}"]`, el).value : '' })).filter(x => +x.qty > 0 || x.final_qty !== '');
      if (!items.length) throw new Error('还没填还了几个');
      await save('/api/loan/return', { loan_id: +id, date: today(), remark: $('#rM', el).value.trim(), items, photo_ids: ph.ids }, '保存归还'); M.done('已归还', 'loan');
    } catch (e) { fail(e); }
  };
};

/* ---------- 访客登记：核对后确认 / 拒绝（要改数量请到电脑上「借用归还 → 访客登记 → 修改后确认」） ---------- */
MP.req = async (el, id) => {
  const q = await api('/api/loan_req/one?id=' + encodeURIComponent(id));
  const open = q.status === '待确认';
  const np = (n, p) => [n, p].filter(Boolean).join(' ');
  const ppl = [['客户', np(q.cust_name, q.cust_phone)], ['销售人', np(q.sales_name, q.sales_phone)]].concat((q.pickups || []).map(p => ['取货人', np(p.name, p.phone)])).filter(x => x[1]);
  el.innerHTML = M.top('访客登记 #' + q.id, q.status) + `<div class="wrap"><div class="sec"><h2>${esc(q.orgs.join('、'))}</h2>
    ${ppl.map(([k, v]) => `<div style="font-size:14px;margin-bottom:4px"><span class="muted">${k}</span> ${esc(v)}</div>`).join('')}
    ${q.escort ? `<div class="muted" style="font-size:13.5px;margin-bottom:6px">随车技术人员：${esc(q.escort)} ${esc(q.escort_phone)}</div>` : ''}
    ${q.items.map(i => `<div class="ln"><div class="nm">${esc(i.product_name)}${i.org ? `<small>${esc(i.org)}</small>` : ''}${i.product_id ? '' : '<small style="color:var(--warn)">访客手写名称，确认后新建产品</small>'}</div><b>${i.approx ? '若干' : fmtN(i.qty)}</b></div>`).join('')}
    ${rmkLine(q.remark)}</div>
    ${q.photos.length ? `<div class="sec"><h2>照片 / 签名</h2><div class="photos">${q.photos.map(p => `<img class="ph-i" src="/photos/${esc(p.path)}" onclick="bigImg('/photos/${esc(p.path)}')">`).join('')}</div></div>` : ''}
    ${open ? '<div class="muted" style="font-size:13px;padding:0 6px">要改数量或物品，请在电脑「借用归还 → 访客登记」里点「修改后确认」。</div>' : `<div class="muted" style="padding:0 6px">${esc(q.handled_by)} ${esc(q.status)}${q.slip_no ? ' → 借用单 ' + esc(q.slip_no) : ''}${q.reject_reason ? '：' + esc(q.reject_reason) : ''}</div>`}</div>
    ${open ? '<div class="bar"><button class="btn" id="qNo">拒绝</button><button class="btn pri blk" id="qOk">确认借出</button></div>' : ''}`;
  if (!open) return;
  $('#qOk', el).onclick = async () => { try { const x = await save('/api/loan_req/confirm', { id: q.id }, '确认访客登记'); M.done('已确认，借用单 ' + x.slip_no, 'loan'); } catch (e) { fail(e); } };
  $('#qNo', el).onclick = async () => {
    const why = prompt('拒绝的原因（可空）'); if (why === null) return;
    try { await save('/api/loan_req/reject', { id: q.id, reason: why }, '拒绝访客登记'); toast('已拒绝'); M.back(); } catch (e) { fail(e); }
  };
};

/* ---------- 库房杂物：拍照快速登记 ---------- */
MP.misc = async el => {
  let cat = '未知';
  const r = await api('/api/misc?status=' + encodeURIComponent('在库'));
  el.innerHTML = M.top('库房杂物', '不计库存') + `<div class="wrap">
    <div class="sec"><h2>拍照<small>拍清楚就行，名字可以以后改</small></h2><div id="xCam"></div></div>
    <div class="sec"><span class="lab">暂用叫法</span><input class="inp" id="xN" placeholder="如：灰色管件">
      <span class="lab">类别</span><div class="chips" id="xC">${['暂存', '工程', '未知'].map(c => `<button data-v="${c}" class="${c === cat ? 'on' : ''}">${c}</button>`).join('')}</div>
      <div class="two"><div><span class="lab">大概数量</span><input class="inp" id="xQ" placeholder="约 20 根"></div><div><span class="lab">放在哪</span><input class="inp" id="xL"></div></div>
      <span class="lab">谁放的</span><input class="inp" id="xP" placeholder="可空">
      <span class="lab">备注（可空）</span><input class="inp" id="xR"></div>
    <div class="sec"><h2>在库的杂物 <small>${r.items.length} 件</small></h2>${r.items.slice(0, 12).map(t => `<div class="rec">${t.photos[0] ? `<img src="/photos/${esc(t.photos[0].path)}" onclick="bigImg(this.src)">` : '<span class="np"></span>'}<div class="tx">${esc(t.name || '（未命名）')}<small>${esc(t.category)} · ${esc(t.qty)} · ${esc(t.location)}</small>${rmkLine(t.remark)}</div><span class="dt ${ageCls(t.date)}">${esc(md(t.date))}</span></div>`).join('') || '<div class="empty">没有记录</div>'}</div></div>
    <div class="bar"><div class="sum"><b>登记一件</b><small>弄清后在电脑上改名 / 已取走 / 转入库</small></div><button class="btn pri" id="xSave">保存</button></div>`;
  const ph = camBox($('#xCam', el));
  $('#xC', el).onclick = e => { const b = e.target.closest('button'); if (!b) return; cat = b.dataset.v; $$('#xC button', el).forEach(x => x.classList.toggle('on', x === b)); };
  $('#xSave', el).onclick = async () => {
    try {
      const d = { name: $('#xN', el).value.trim(), category: cat, qty: $('#xQ', el).value.trim(), location: $('#xL', el).value.trim(), placed_by: $('#xP', el).value.trim(), remark: $('#xR', el).value.trim(), date: today() };
      await save('/api/misc/save', { data: d, photo_ids: ph.ids }, '登记库房杂物'); M.done('已登记', 'misc');
    } catch (e) { fail(e); }
  };
};

/* ---------- 待补全 ---------- */
MP.pend = async el => {
  el.innerHTML = M.top('待补全快速记') + `<div class="wrap"><div class="sec">
    <span class="lab">谁拿的</span><input class="inp" id="pT" placeholder="如：张总">
    <span class="lab">拿了什么</span><input class="inp" id="pW" placeholder="如：便携式制氧机">
    <div class="two"><div><span class="lab">几个</span><input class="inp" id="pQ" inputmode="decimal"></div><div><span class="lab">客户（可空）</span><input class="inp" id="pC"></div></div>
    <span class="lab">备注（可空）</span><input class="inp" id="pR">
    <span class="lab">照片（可空）</span><div id="pCam"></div></div><div class="muted" style="font-size:13px;padding:0 6px">其他都可以空着，会一直挂在「待补全」里提醒，补全后关闭。</div></div>
    <div class="bar"><div class="sum"><b>先记下</b></div><button class="btn pri" id="pSave">记下</button></div>`;
  const ph = camBox($('#pCam', el), { label: '拍一张（可不拍）' });
  $('#pSave', el).onclick = async () => {
    try {
      const d = { taker: $('#pT', el).value.trim(), what: $('#pW', el).value.trim(), qty: $('#pQ', el).value.trim(), customer: $('#pC', el).value.trim(), remark: $('#pR', el).value.trim() };
      if (!d.taker && !d.what) throw new Error('至少写谁拿的或拿了什么');
      await save('/api/pending/save', { data: d, photo_ids: ph.ids }, '记待补全'); M.done('已记下', 'pend');
    } catch (e) { fail(e); }
  };
};
MP.mine = async el => {
  const r = await api('/api/pending?status=' + encodeURIComponent('待补全'));
  const g = {}; r.items.forEach(x => (g[x.taker || '（未写）'] = g[x.taker || '（未写）'] || []).push(x));
  el.innerHTML = M.top('待补全清单', r.items.length + ' 笔') + `<div class="wrap">${Object.entries(g).map(([k, xs]) => `<div class="sec"><h2>${esc(k)}<small>${xs.length} 笔</small></h2>
    ${xs.map(x => `<div class="rec"><div class="tx">${esc(x.what)} ${esc(x.qty)}<small>${esc(x.customer || '')}${x.handler ? ' · 经手 ' + esc(x.handler) : ''}</small>${rmkLine(x.remark)}${/^out_sign:/.test(x.auto_key || '') ? `<button class="btn sm" style="margin-top:6px" data-sg="${esc(x.auto_key.slice(9))}">拍签字单回传</button>` : ''}</div><span class="dt ${ageCls(x.date)}">${esc(md(x.date))}</span></div>`).join('')}</div>`).join('') || '<div class="empty">没有待补全 👍</div>'}
    <div class="muted" style="font-size:13px;padding:0 6px">领用出库单签好字可直接在这里拍照回传；其他补全、关闭在电脑「待补全」页操作。</div></div>`;
  el.onclick = async e => {
    const b = e.target.closest('[data-sg]'); if (!b) return;
    try {
      const fs = await pickFiles('image/*', true, true); if (!fs.length) return;
      const ids = []; for (const f of fs) ids.push((await uploadPhoto(f, { tag: 'sign' })).id);
      await save('/api/out/sign', { id: +b.dataset.sg, photo_ids: ids }, '回传签字照片'); toast('已回传，这一笔已补全'); MP.mine(el);
    } catch (er) { if (er.message !== 'cancel') fail(er); }
  };
};

/* ---------- 电脑扫码：手机拍照直接传到电脑上正在录的单子 ---------- */
MP.cam = async (el, token) => {
  el.innerHTML = M.top('拍照传到电脑') + `<div class="wrap"><div class="sec"><div id="kCam"></div></div>
    <div class="muted" style="font-size:13.5px;padding:0 6px">拍完会自动出现在电脑上正在录的那张单子里，不需要输密码。可连拍多张。</div></div>`;
  const ph = camBox($('#kCam', el), { label: '点这里拍照', extra: { token } });
  void ph;
};
