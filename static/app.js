/* 桌面端：路由 + 首页 */
'use strict';
const Pages = {};
const IC = {
  out: '<svg viewBox="0 0 24 24"><path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h4"/></svg>',
  bottle: '<svg viewBox="0 0 24 24"><path d="M9 3h6M10 3v3a5 5 0 0 0-3 4.6V20a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1v-9.4A5 5 0 0 0 14 6V3"/><path d="M7 13h10"/></svg>',
  loan: '<svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3"/><path d="M18 3v4h-4M6 21v-4h4"/></svg>',
  box: '<svg viewBox="0 0 24 24"><path d="M3 7l9-4 9 4-9 4z"/><path d="M3 7v10l9 4 9-4V7M12 11v10"/></svg>',
  note: '<svg viewBox="0 0 24 24"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>'
};
const App = {
  cur: null,
  async start() {
    try { await loadBoot(); } catch (e) { document.getElementById('main').innerHTML = '<div class="page"><div class="empty">连不上主机：' + esc(e.message) + '</div></div>'; return; }
    $('#siteName').textContent = S.boot.settings.site_name || '库房出入库'; document.title = S.boot.settings.site_name || '库房出入库';
    const paintFoot = (ver) => { $('#foot').innerHTML = `${esc(S.boot.settings.site_name || '库房出入库')} · 版本 ${esc(ver || S.boot.version || '')} · <a class="link" href="#settings/about">关于 / 更新记录</a>`; };
    paintFoot(S.boot.version);
    // 热更新静态时：底部版本跟 /v.json，不用重启后台也能看到新号
    fetch('/v.json', { cache: 'no-store' }).then(r => r.ok ? r.json() : null).then(j => { if (j && j.version) { S.boot.version = j.version; if (j.build_date) S.boot.build_date = j.build_date; paintFoot(j.version); } }).catch(() => {});
    App.applyNav();
    $('#tabs').addEventListener('click', e => { const a = e.target.closest('a[data-p]'); if (!a) return; const def = { daily: 'cyl', loan: 'list', out: 'single' }[a.dataset.p]; location.hash = def ? a.dataset.p + '/' + def : a.dataset.p; });
    window.addEventListener('hashchange', () => App.route());
    window.addEventListener('beforeunload', e => { if (App.guard) { e.preventDefault(); e.returnValue = ''; } });
    App.route(); App.who(); Fit.init();
  },
  /** 按设置里的 nav_order / nav_hidden 重排顶栏（设置固定最后；隐藏项不进顶栏，路由仍可用） */
  applyNav() {
    const box = $('#tabs'); if (!box) return;
    const NAVL = { home: '首页', daily: '产品出入库情况', out: '出库', loan: '借用归还', arrival: '到货', stock: '产品与库存', report: '报表', print: '打印', misc: '库房杂物', slip: '称重单', backup: '数据备份', settings: '设置' };
    const def = ['home', 'daily', 'out', 'loan', 'arrival', 'stock', 'report', 'print', 'misc', 'slip', 'backup'];  // Sprint A + 打印
    const st = (S.boot && S.boot.settings) || {};
    const o = (st.nav_order || []).filter(k => def.includes(k));
    const keys = [...new Set(o.concat(def))];
    // 默认藏杂物/称重/备份；设置里关掉「隐藏」或 nav_hidden=[] 后显示。缺字段 = 用默认隐藏
    const hid = Array.isArray(st.nav_hidden) ? st.nav_hidden : ['misc', 'slip', 'backup'];
    const show = keys.filter(k => !hid.includes(k));
    const cur = ($$('a.on', box)[0] || {}).dataset ? ($$('a.on', box)[0].dataset.p) : null;
    const lab = k => esc(typeof nm === 'function' ? nm(NAVL[k] || k) : (NAVL[k] || k));
    box.innerHTML = show.map(k => `<a data-p="${k}">${lab(k)}</a>`).join('') + `<a data-p="settings">${lab('settings')}</a>`;
    if (cur) $$('a', box).forEach(a => a.classList.toggle('on', a.dataset.p === cur || (cur === 'pending' && a.dataset.p === 'home')));
  },
  who() { const p = PIN.get(); $('#who').innerHTML = p ? esc(p.name) + ' <a class="link d" onclick="PIN.clear();App.who()">退出</a>' : '保存时输密码'; },
  guard: null,      // 页面有未保存修改时设为提示文字
  guardSave: null,  // 可选：未保存弹窗点「保存」时调用（日表 / 报表）
  _routeLock: false,
  async route() {
    if (App._routeLock) return;
    if (App.guard && location.hash !== App.curHash) {
      const want = location.hash;
      history.replaceState(null, '', App.curHash);   // 先回到原页，等用户在弹窗里选
      App._routeLock = true;
      try {
        const act = await dirtyLeave(App.guard);
        if (act === 'cancel') return;
        if (act === 'save') {
          if (!App.guardSave) { toast('请先点页面上的「保存」', true); return; }
          try { await App.guardSave(); } catch (e) { fail(e); return; }
        }
        App.guard = null; App.guardSave = null;
        App.curHash = want;
        if (location.hash !== want) history.replaceState(null, '', want);
      } finally { App._routeLock = false; }
    } else {
      App.curHash = location.hash;
    }
    const h = (location.hash || '#home').slice(1); const [p, arg] = h.split('/');
    const page = Pages[p] ? p : 'home';
    $$('#tabs a').forEach(a => a.classList.toggle('on', a.dataset.p === page || (page === 'pending' && a.dataset.p === 'home')));
    if (typeof CellSel !== 'undefined') CellSel.clear();
    const m = $('#main'); m.innerHTML = ''; const el = document.createElement('div'); el.className = 'page'; m.appendChild(el);
    App.cur = page; window.scrollTo(0, 0); m.scrollTop = 0;
    Promise.resolve(Pages[page](el, arg)).catch(fail);
    App.who();
  },
  reloadBoot: async () => { await loadBoot(); },
  // 同一页里切页签 / 保存后跳回列表：换地址但不新增历史记录，浏览器「后退」直接回上一个页面，不会在页签间打转
  tab(h) { h = h.replace(/^#/, ''); if (location.hash.replace(/^#/, '') === h) App.route(); else location.replace('#' + h); }
};


/* ================= 首页便签纸（本机 localStorage，不写业务库） ================= */
const HOME_STICKY_KEY = 'wh_home_sticky_notes';
const HOME_STICKY_COLORS = ['y', 'p', 'b', 'g'];
function homeStickyLoad() {
  try {
    const a = JSON.parse(localStorage.getItem(HOME_STICKY_KEY) || '[]');
    return Array.isArray(a) ? a.filter(x => x && typeof x.text === 'string').slice(0, 12) : [];
  } catch (e) { return []; }
}
function homeStickySave(list) {
  try { localStorage.setItem(HOME_STICKY_KEY, JSON.stringify(list.slice(0, 12))); } catch (e) { }
}
function homeStickyMount(root) {
  const box = root.querySelector('#homeStickies'); if (!box) return;
  const paint = () => {
    const list = homeStickyLoad();
    box.innerHTML = `<div class="home-sticky-h"><b>便签</b><span class="muted">写在本机，不进库</span><button type="button" class="link" id="hsAdd">＋ 贴一张</button></div>
      <div class="home-sticky-grid">${list.map((n, i) => {
        const c = HOME_STICKY_COLORS.includes(n.color) ? n.color : 'y';
        return `<div class="hs-note c-${c}" data-i="${i}"><button type="button" class="sticky-x" data-x="${i}" title="撕掉">×</button>
          <textarea class="sticky-t" data-i="${i}" maxlength="120" rows="3" placeholder="写点什么…">${esc(n.text || '')}</textarea>
          <div class="sticky-cols">${HOME_STICKY_COLORS.map(col => `<button type="button" class="dot c-${col}${c === col ? ' on' : ''}" data-i="${i}" data-c="${col}" title="换色"></button>`).join('')}</div></div>`;
      }).join('') || '<div class="muted home-sticky-empty">空白处可贴便签，例如「今天一院要还罐」</div>'}</div>`;
    const add = $('#hsAdd', box); if (add) add.onclick = () => {
      const list = homeStickyLoad();
      if (list.length >= 12) return toast('最多 12 张便签', true);
      list.push({ id: Date.now().toString(36), text: '', color: HOME_STICKY_COLORS[list.length % HOME_STICKY_COLORS.length], ts: Date.now() });
      homeStickySave(list); paint();
      const ta = box.querySelector('.hs-note:last-of-type textarea'); if (ta) ta.focus();
    };
    box.onchange = e => {
      const t = e.target;
      if (t.classList.contains('sticky-t')) {
        const list = homeStickyLoad(); const i = +t.dataset.i; if (!list[i]) return;
        list[i].text = (t.value || '').slice(0, 120); homeStickySave(list);
      }
    };
    box.oninput = e => { if (e.target.classList.contains('sticky-t')) box.onchange(e); };
    box.onclick = e => {
      const x = e.target.closest('[data-x]');
      if (x) {
        const list = homeStickyLoad(); list.splice(+x.dataset.x, 1); homeStickySave(list); paint(); return;
      }
      const d = e.target.closest('[data-c]');
      if (d) {
        const list = homeStickyLoad(); const i = +d.dataset.i; if (!list[i]) return;
        list[i].color = d.dataset.c; homeStickySave(list); paint();
      }
    };
  };
  paint();
}

/* ================= 首页（Phase A 调度台） ================= */
/** 首页四键：预填出库单笔后进 #out/single（不写库） */
function homeGoOut(source, kind) {
  try {
    if (typeof Out !== 'undefined' && typeof newOutForm === 'function') {
      Out.form = Object.assign(newOutForm(), { source: source || '', kind: kind || '' });
      Out.tab = 'single';
    }
  } catch (e) { }
  location.hash = '#out/single';
}
/** 看出库记录 · 今天 */
function homeGoOutToday() {
  try {
    if (typeof OL !== 'undefined') {
      const d = today();
      OL.from = d; OL.to = d; OL.kind = ''; OL.source = ''; OL.u8_type = ''; OL.q = ''; OL.deleted = '';
      OL.init = 1;
    }
  } catch (e) { }
  location.hash = '#out/list';
}
/** 液氧质检入库：进报表液氧表，并标记滚到待写入提示 */
function homeGoLoxQc() {
  try { sessionStorage.setItem('homeLoxFocus', '1'); } catch (e) { }
  location.hash = '#report/lox';
}
/** 首页「待入U8」→ 到货并筛待入U8 */
function homeGoArrivalU8() {
  try {
    if (typeof AR !== 'undefined') AR.f = 'pending';
    sessionStorage.setItem('homeArrivalU8', '1');
  } catch (e) { }
  location.hash = '#arrival';
}

Pages.home = async el => {
  const d = await api('/api/home');
  const now = new Date(); const wk = '日一二三四五六'[now.getDay()];
  const hr = now.getHours(); const hi = hr < 11 ? '早上好' : hr < 13 ? '中午好' : hr < 18 ? '下午好' : '晚上好';
  const p = PIN.get();
  const kpi = (n, t, o, go) => {
    const s = o ? [o.over30 ? `<span class="w30">${o.over30} 笔超30天</span>` : '', o.over7 ? `<span class="w7">${o.over7} 笔超7天</span>` : ''].filter(Boolean).join(' · ') : '';
    const cls = o && o.over30 ? 'w30' : o && o.over7 ? 'w7' : '';
    return `<div class="kpi" onclick="location.hash='${go}'"><div class="n ${cls}">${n}</div><div class="t">${t}</div><div class="s">${s}</div></div>`;
  };
  const exp = d.expiring.length;
  const inner = `
  <div class="hello"><h1>${hi}${p ? '，' + esc(p.name) : ''}</h1><div class="sub muted">${now.getMonth() + 1}月${now.getDate()}日 星期${wk}</div>
    <div class="guide">调度台：自提 / U8 / 液氧质检入库 / 打印 · 日表与到货在次要入口</div></div>
  <div class="kpis">
    ${kpi(d.pending.n, '待补全', d.pending, 'pending')}
    ${kpi(d.loans.n, '未归还', d.loans, 'loan')}
    <div class="kpi" onclick="homeGoArrivalU8()"><div class="n ${d.u8 && d.u8.over30 ? 'w30' : d.u8 && d.u8.over7 ? 'w7' : ''}">${d.u8.n}</div><div class="t">待入U8</div><div class="s">${[d.u8 && d.u8.over30 ? `<span class="w30">${d.u8.over30} 笔超30天</span>` : '', d.u8 && d.u8.over7 ? `<span class="w7">${d.u8.over7} 笔超7天</span>` : ''].filter(Boolean).join(' · ')}</div></div>
    ${kpi(d.unknown, '库存未知产品', null, 'stock')}
    <div class="kpi" onclick="location.hash='stock/batch'"><div class="n ${exp ? 'w7' : ''}">${exp}</div><div class="t">临近效期批次</div><div class="s">${exp ? esc(d.expiring[0].product + ' ' + d.expiring[0].batch_no + ' ' + d.expiring[0].expiry) : ''}</div></div>
  </div>
  <div class="acts4" title="今日主路径">
    <div class="act pri" onclick="homeGoOut('app手工单','客户自提')"><div class="ic">${IC.out}</div><div><b>客户自提</b><span>预填 app手工单 · 客户自提</span></div></div>
    <div class="act" onclick="homeGoOut('U8单','销售出库')"><div class="ic">${IC.out}</div><div><b>U8出库</b><span>预填 U8单 · 销售出库</span></div></div>
    <div class="act" onclick="homeGoLoxQc()"><div class="ic">${IC.bottle}</div><div><b>液氧质检入库</b><span>报表 · 液氧表 →入库</span></div></div>
    <div class="act" onclick="location.hash='print'"><div class="ic">${IC.note}</div><div><b>打印</b><span>出/入库单 · 液氧表</span></div></div>
  </div>
  <div class="acts-sec">
    <a class="act-mini" onclick="location.hash='daily'"><b>日表</b><span>交接表</span></a>
    <a class="act-mini" onclick="location.hash='arrival'"><b>到货</b><span>进库存</span></a>
    <a class="act-mini" onclick="location.hash='loan'"><b>借用</b><span>借出/归还</span></a>
    <a class="act-mini" onclick="location.hash='slip'"><b>称重单</b><span>液氧过磅</span></a>
    <a class="act-mini" onclick="Pend.quick()"><b>待补全</b><span>十秒记</span></a>
  </div>
  <div class="home-stickies card" id="homeStickies" title="便签纸 · 只存在这台电脑浏览器里"></div>
  <details class="home-phone card">
    <summary><b>连接手机</b><span class="muted">扫码开手机端 / 照片库 · 出库·到货侧栏也有捷径</span></summary>
    <div class="home-phone-body" id="homePhoneQrs"></div>
    <div class="hint" style="margin-top:8px">业务二维码与持续拍已在「出库 / 到货」侧栏；完整设置仍在「设置 → 手机与访客二维码」（全局搜索可用）。</div>
  </details>
  <div class="grid-h">
    <div class="card">
      <div class="card-h"><h2>今日出库</h2>
        <div style="display:flex;gap:10px;align-items:center">
          <span class="muted" style="font-size:12.5px">${hr}:${String(now.getMinutes()).padStart(2, '0')}</span>
          <a class="link" onclick="homeGoOutToday()" title="出库记录筛今天">看出库记录·今天 →</a>
        </div>
      </div>
      ${d.today_out.length ? `<div class="stat4">${d.today_out.slice(0, 4).map(t => `<div style="cursor:pointer" title="点开看这个产品的出入库流水" data-lab="${esc(t.name + (t.spec ? ' ' + t.spec : ''))}" onclick="movesDlg({ id: ${+t.id}, label: this.dataset.lab }).catch(fail)"><div class="n">${fmtN(t.q)}</div><div class="t">${esc(t.name + (t.spec ? ' ' + t.spec : ''))}</div></div>`).join('')}</div>` : '<div class="muted" style="padding:6px 0 4px">今天还没有出库</div>'}
      <div class="card-h" style="margin:18px 0 4px;padding-top:14px;border-top:1px solid var(--line2)"><h2>最近记录</h2></div>
      <div class="lst">${d.recent.map(r => `<div class="it" style="cursor:pointer" title="点开看原始记录" onclick="recView('${{ '出库': 'out', '到货': 'arrival', '出入库情况': 'daily' }[r.type] || 'out'}', ${+r.id}).catch(fail)">${r.photo ? `<img class="th" src="/photos/${esc(r.photo)}">` : `<div class="th" style="display:grid;place-items:center;color:var(--tx3);font-size:12px">${esc(r.type)}</div>`}
        <div class="g"><div class="tt">${esc(r.title)} <span class="tag">${esc(kindDisp(r.kind))}</span></div><div class="dd">${esc(r.desc)}</div>${r.remark ? `<div class="dd rmk-t" title="${esc(r.remark)}">备注：${esc(r.remark)}</div>` : ''}</div><div class="dt">${md(r.date)}<br>${esc(r.by || '')}</div></div>`).join('') || '<div class="muted">没有记录</div>'}</div>
    </div>
    <div>
      <div class="card">
        <div class="card-h"><h2>未归还</h2><a onclick="location.hash='loan'">${d.loans.n} 单 →</a></div>
        <div class="lst">${d.loans_list.map(l => `<div class="it"><div class="g"><div class="tt">${esc(l.who)}</div><div class="dd">${esc(l.items)}</div></div><div class="dt ${ageCls(l.date)}">${md(l.date)}${l.status === '部分归还' ? '<br><span class="tag ac">部分归还</span>' : ''}</div></div>`).join('') || '<div class="muted">没有未归还的借用</div>'}</div>
      </div>
      <div class="card">
        <div class="card-h"><h2>待补全</h2><a onclick="location.hash='pending'">${d.pending.n} 笔 →</a></div>
        <div class="lst">${d.pending_list.map(x => `<div class="it"><div class="g"><div class="tt">${esc(x.taker || '（未写）')}：${esc(x.what)} ${esc(x.qty)}</div></div><div class="dt ${ageCls(x.date)}">${md(x.date)}</div></div>`).join('') || '<div class="muted">没有待补全的记录</div>'}</div>
      </div>
      ${d.stock_warn ? `<div class="note-line"><span class="dot bad"></span><span style="flex:1">${d.stock_warn} 个产品系统数为负，建议复盘</span><a onclick="location.hash='stock'">去看看</a></div>` : ''}
      ${!d.last_backup ? `<div class="note-line"><span class="dot"></span><span style="flex:1">还没有备份过</span><a onclick="location.hash='backup'">去备份</a></div>` : ''}
    </div>
  </div>`;
  el.innerHTML = UI.shellHome(inner);
  homeStickyMount(el);
  const slot = document.getElementById('homePhoneQrs');
  if (slot && typeof phoneQrs === 'function') {
    slot.innerHTML = phoneQrs();
    if (typeof fillLibQr === 'function') fillLibQr().catch(() => {});
  }
};

/* ================= 一屏布局（v1.1.1）=================
 * 页面本身不滚动：顶部导航、页面标题、工具栏固定，页面里最长的那个表格（报表 / 列表）占满剩下的高度，只有它自己滚；
 * 表头固定在表格顶上，横向滚动条就在窗口底部。窗口太矮放不下时（表格不到 200px 高）退回整页滚动（也只有一个滚动条）。 */
const Fit = {
  init() {
    let q = 0; const go = () => { if (!q) q = requestAnimationFrame(() => { q = 0; Fit.run(); }); };
    new MutationObserver(go).observe($('#main'), { childList: true, subtree: true });
    window.addEventListener('resize', go); document.addEventListener('toggle', go, true); Fit.go = go; go();
  },
  run() {
    const B = document.body, main = $('#main'), page = $('#main .page');
    if (!page || B.classList.contains('printing')) return;
    // 左边菜单 + 右边内容（设置）：两块各自滚，菜单不动
    const split = $('.setc', page);
    if (split) {
      B.classList.add('fit'); split.classList.add('fit-split');
      const h = Math.floor(main.getBoundingClientRect().bottom - split.getBoundingClientRect().top - 12) + 'px';
      if (split.style.height !== h) split.style.height = h;
      return;
    }
    const cands = $$('.r-grid, .tw, .pp-tw', page).filter(x => !x.closest('.ov') && x.offsetParent && !(x.parentElement && x.parentElement.closest('.tw, .r-grid, .pp-tw')));
    const old = $$('.fit-on', page);
    if (!cands.length) { old.forEach(Fit.off); B.classList.remove('fit'); return; }
    const big = cands.find(x => x.classList.contains('r-grid')) || cands.sort((a, b) => b.scrollHeight - a.scrollHeight)[0];
    old.filter(x => x !== big).forEach(Fit.off);
    B.classList.add('fit');
    const mb = main.getBoundingClientRect().bottom, br = big.getBoundingClientRect(), below = page.getBoundingClientRect().bottom - br.bottom;
    const h = Math.floor(mb - br.top + main.scrollTop * 0 - below);
    /* 1.1.51：撤回 1.1.50 对 #dSum/.fit-fill 硬设 height；#dSum 自适应（内容多高就多高），行多整页滚、不表内分页；仅 r-grid 强制填满 */
    if (big.id === 'dSum') {
      Fit.off(big);
      big.classList.add('fit-flow');
    } else {
      const fill = big.classList.contains('r-grid');
      const need = fill || big.scrollHeight > h;
      if (h >= 200 && need) {
        big.classList.add('fit-on'); const px = h + 'px';
        if (big.style.maxHeight !== px) big.style.maxHeight = px;
        const hh = fill ? px : '';
        if (big.style.height !== hh) big.style.height = hh;
      } else { Fit.off(big); if (h < 200 && big.classList.contains('tw') && big.scrollWidth <= big.clientWidth + 1) big.classList.add('fit-flow'); }   // 放不下：整页一个滚动条，表头贴在顶上
    }
    // 一屏高度定好后，再按实测行高对齐多行吸顶表头 / 钉左列
    $$('table.rt, table.pp', page).forEach(t => { if (t.tHead && typeof syncStickyHeads === 'function') syncStickyHeads(t); });
  },
  off(x) { x.classList.remove('fit-on', 'fit-flow'); x.style.maxHeight = ''; x.style.height = ''; },
};
