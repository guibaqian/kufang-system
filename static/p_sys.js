/* 待补全、借用（第一阶段只读）、报表/称重单（第二阶段）、数据备份、设置 */
'use strict';
const Pend = {
  quick(x) {
    x = x || {};
    dialog(x.id ? '修改待补全' : '待补全快速记', `<div class="row"><div><span class="lab">谁拿的</span><input class="inp" id="qT" placeholder="如：张总" value="${esc(x.taker || '')}"></div>
      <div><span class="lab">拿了什么</span><input class="inp" id="qW" placeholder="如：便携式制氧机" value="${esc(x.what || '')}"></div><div class="row r2"><div><span class="lab">几个</span><input class="inp" id="qQ" value="${esc(x.qty || '')}"></div>
      <div><span class="lab">客户（可空）</span><input class="inp" id="qC" placeholder="如：某某领导介绍" value="${esc(x.customer || '')}"></div></div>
      <div><span class="lab">备注</span><input class="inp" id="qR" placeholder="可不填" value="${esc(x.remark || '')}"></div></div><div class="hint">其他都可以空着，以后补全。</div>`,
      [{ t: '取消' }, { t: x.id ? '保存' : '记下', cls: 'pri', fn: async ov => {
        const d = { taker: $('#qT', ov).value.trim(), what: $('#qW', ov).value.trim(), qty: $('#qQ', ov).value.trim(), customer: $('#qC', ov).value.trim(), remark: $('#qR', ov).value.trim() };
        if (x.id) d.id = x.id;
        if (!d.taker && !d.what) throw new Error('至少写谁拿的或拿了什么');
        await save('/api/pending/save', { data: d }, x.id ? '修改待补全' : '记待补全'); toast(x.id ? '已保存' : '已记下'); if (App.cur === 'home' || App.cur === 'pending') App.route();
      } }]);
  }
};
Pages.pending = async el => {
  const r = await api('/api/pending'); const pq = (Pages.pending.q || '').trim();
  const open = r.items.filter(x => x.status === '待补全');
  const shown = r.items.filter(x => !pq || [x.taker, x.what, x.qty, x.customer, x.handler, x.remark, x.close_note].some(v => String(v || '').includes(pq)));
  el.innerHTML = UI.ph('待补全', '急事先记 · 补全后关掉', '一直挂着提醒；确实查不清可标「无法确认」并写备注。',
    `<button class="btn" id="pdWeek">下载本周清单</button><button class="btn" id="pdMonth">下载本月清单</button><button class="btn" id="pdPrint">打印本月清单</button><button class="btn pri" onclick="Pend.quick()">＋ 快速记</button>`)
    + `<div class="grid2 page-entry page-entry-side"><div class="card page-card"><div class="tools"><div class="tg"><input class="inp" id="pdQ" placeholder="搜人、物品、客户、备注" value="${esc(pq)}" style="width:240px"></div></div><div class="tw"><table class="t"><thead><tr><th>日期</th><th>谁拿的</th><th>拿了什么</th><th>数量</th><th>客户/说明</th><th>经手</th><th>状态</th><th>备注</th><th></th></tr></thead><tbody>
    ${shown.map(x => `<tr class="${x.status !== '待补全' ? 'off' : ''}"><td class="w ${x.status === '待补全' ? ageCls(x.date) : ''}">${esc(x.date)}</td><td>${esc(x.taker)}</td><td>${esc(x.what)}</td><td>${esc(x.qty)}</td><td>${esc(x.customer)}</td><td>${esc(x.handler)}</td>
      <td class="w">${x.status === '待补全' ? '<span class="tag warn">待补全</span>' : `<span class="tag">${esc(x.status)}</span>`}</td>
      ${rmkTd(rmkJoin(x.remark, x.close_note))}
      ${rowActs({ ph: [x.nphotos || 0, `data-pph="${x.id}"`], main: x.status === '待补全' ? ['已补全', `data-done="${x.id}"`] : null,
        menu: [x.status === '待补全' ? ['无法确认', `data-no="${x.id}"`] : null, ['修改', `data-ped="${x.id}"`], ['留痕', `data-phi="${x.id}"`]] })}</tr>`).join('') || '<tr><td colspan="9" class="empty">没有待补全</td></tr>'}</tbody></table></div></div>
    <div class="card"><div class="card-h"><h2>按人</h2></div><table class="t"><tbody>${Object.entries(r.by_person).map(([k, v]) => `<tr><td>${esc(k)}</td><td class="n">${v.pending ? v.pending + ' 笔没补' : ''}${v.loans ? (v.pending ? '，' : '') + v.loans + ' 单没还' : ''}</td></tr>`).join('') || '<tr><td class="muted">无</td></tr>'}</tbody></table></div></div>`;
  const d0 = n => { const d = new Date(); d.setDate(d.getDate() - n); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
  $('#pdPrint', el).onclick = () => printApi('/api/pending/list.xlsx?from=' + d0(31)).catch(fail);
  $('#pdWeek', el).onclick = () => download('/api/pending/list.xlsx?from=' + d0(7));
  $('#pdMonth', el).onclick = () => download('/api/pending/list.xlsx?from=' + d0(31));
  let pt; $('#pdQ', el).oninput = e => { clearTimeout(pt); const v = e.target.value; pt = setTimeout(() => { Pages.pending.q = v; Pages.pending(el).then(() => { const i = $('#pdQ', el); i.focus(); i.setSelectionRange(v.length, v.length); }); }, 300); };
  el.onclick = e => {
    const t = e.target;
    if (t.dataset.ped) return Pend.quick(r.items.find(x => x.id === +t.dataset.ped));
    if (t.dataset.phi) return auditDlg('pending', +t.dataset.phi).catch(fail);
    if (t.dataset.pph) return api('/api/pending/photos?id=' + t.dataset.pph).then(p => dialog('照片', `<div class="photos">${p.items.map(x => `<img class="ph-i" style="width:200px;height:150px" src="/photos/${esc(x.path)}" onclick="bigImg(this.src)">`).join('')}</div>`, null, { wide: true })).catch(fail);
    const id = +(t.dataset.done || t.dataset.no); if (!id) return;
    const st = t.dataset.done ? '已补全' : '无法确认';
    dialog(st, `<span class="lab">备注${st === '无法确认' ? '（必填）' : '（补到哪张单等）'}</span><input class="inp" id="pcN">`, [{ t: '取消' }, { t: st, cls: 'pri', fn: async ov => {
      const n = $('#pcN', ov).value.trim(); if (st === '无法确认' && !n) throw new Error('请写备注');
      await save('/api/pending/close', { id, status: st, note: n }, st); Pages.pending(el);
    } }]);
  };
};


/* ---------- 数据备份 ---------- */
Pages.backup = async (el, arg) => {
  const tab = arg || 'backup';
  el.innerHTML = UI.ph('数据备份', '每天自动备份 · 可拷到 U 盘', '含照片；可另存到共享文件夹。改动留痕，删除可恢复。',
    `<div class="seg" id="bkT"><button data-t="backup">备份与导入</button><button data-t="trash">回收站</button><button data-t="audit">操作记录</button></div>`)
    + `<div id="bkB"></div>`;
  $$('#bkT button', el).forEach(b => { b.classList.toggle('on', b.dataset.t === tab); b.onclick = () => App.tab('backup/' + b.dataset.t); });
  const B = $('#bkB', el);
  if (tab === 'trash') {
    const r = await api('/api/trash');
    B.innerHTML = `<div class="card"><table class="t"><thead><tr><th>删除时间</th><th>谁删的</th><th>类别</th><th>内容</th><th></th></tr></thead><tbody>${r.items.map(x => `<tr><td class="w">${fmtTs(x.deleted_at)}</td><td>${esc(x.deleted_by)}</td><td>${esc(x.entity_cn)}</td><td>${esc(x.label)}</td><td><a data-rs="${x.entity}:${x.id}">恢复</a></td></tr>`).join('') || '<tr><td colspan="5" class="empty">回收站是空的</td></tr>'}</tbody></table></div>`;
    B.onclick = async e => { const v = e.target.dataset.rs; if (!v) return; const [en, id] = v.split(':'); try { await save('/api/restore', { entity: en, id: +id }, '恢复'); toast('已恢复'); Pages.backup(el, 'trash'); } catch (er) { fail(er); } };
    return;
  }
  if (tab === 'audit') {
    const r = await api('/api/audit?limit=400');
    B.innerHTML = `<div class="card"><table class="t"><thead><tr><th>时间</th><th>谁</th><th>操作</th><th>类别</th><th>内容</th></tr></thead><tbody>${r.items.map(a => `<tr><td class="w">${fmtTs(a.ts)}</td><td class="w">${esc(a.person)}</td><td class="w">${esc(a.action)}</td><td class="w">${esc(a.entity_cn)}${a.entity_id ? ' #' + a.entity_id : ''}</td><td>${esc(a.summary)}</td></tr>`).join('')}</tbody></table><div class="hint">最近 400 条；每条记录的完整改前/改后内容都保存在数据库里</div></div>`;
    return;
  }
  const r = await api('/api/backup/list');
  const lb = r.last;
  B.innerHTML = `<div class="grid2" style="grid-template-columns:1fr 1fr"><div class="card"><div class="card-h"><h2>备份</h2></div>
    <div class="kv"><dt>上次备份</dt><dd>${lb ? fmtTs(lb.ts) + ' · ' + esc(lb.reason) : '<span class="w7">还没有</span>'}</dd><dt>另存位置</dt><dd>${r.dir ? esc(r.dir) : '<span class="muted">未设置（在「设置」里填 U 盘或共享文件夹路径）</span>'}${lb && lb.copy_error ? `<br><span class="w30">${esc(lb.copy_error)}</span>` : lb && lb.copied ? '<br><span class="muted">已另存 ✓</span>' : ''}</dd><dt>本机位置</dt><dd class="muted" style="font-size:12.5px">${esc(r.local)}</dd></div>
    <div style="display:flex;gap:8px;margin-top:16px"><button class="btn pri" id="bkNow">立即备份</button><button class="btn" id="bkExp">导出全部数据</button><button class="btn" id="bkImp">导入 / 恢复</button><button class="btn" id="bkLox">旧液氧到货留底</button></div>
    <div class="hint">「导入 / 恢复」会先自动备份当前数据，再用选中的备份文件覆盖。</div></div>
    <div class="card"><div class="card-h"><h2>备份文件 <small>保留最近 ${esc(S.boot.settings.backup_keep)} 份</small></h2></div><table class="t"><tbody>${r.items.slice(0, 12).map(f => `<tr><td>${esc(f.name)}</td><td class="n muted">${(f.size / 1048576).toFixed(1)} MB</td><td><a data-dl="${esc(f.name)}">下载</a></td></tr>`).join('') || '<tr><td class="muted">没有</td></tr>'}</tbody></table></div></div>`;
  $('#bkNow', el).onclick = async () => { try { const x = await save('/api/backup/now', {}, '立即备份'); toast('已备份' + (x.copy_error ? '（另存失败：' + x.copy_error + '）' : x.copied ? '，已另存' : '')); Pages.backup(el); } catch (e) { fail(e); } };
  $('#bkExp', el).onclick = () => download('/api/export.zip');
  $('#bkLox', el).onclick = () => download('/api/legacy/lox.xlsx');
  $('#bkImp', el).onclick = async () => {
    try {
      const [f] = await pickFiles('.zip'); if (!f) return;
      if (!await confirmBox(`用「${esc(f.name)}」覆盖当前全部数据？<br>覆盖前会自动备份当前数据。`, '导入并覆盖')) return;
      const x = await saveRaw('/api/import', f, '导入 / 恢复'); toast('已恢复（导入前备份：' + x.safety_backup + '）'); await loadBoot(); App.route();
    } catch (e) { fail(e); }
  };
  B.addEventListener('click', e => { if (e.target.dataset.dl) download('/api/backup/file?name=' + encodeURIComponent(e.target.dataset.dl)); });
};

/* ---------- 设置中心（左边菜单，右边表单） ---------- */
const SETS = [
  /* 按人找：先界面外观，再表格录入，再名单，最后系统 */
  ['界面与顺序', [['about', '关于'], ['nav', '顶部导航'], ['reportcols', '报表页签与列'], ['names', '名称设置'], ['print', '打印抬头']]],
  ['表格与录入', [['defaults', '常用默认值'], ['layout', '交接表格式'], ['plates', '车牌'], ['daily', '产品出入库情况'], ['ocr', '识别（OCR）'], ['options', '选项列表']]],
  ['名单', [['couriers', '配送员'], ['products', '产品与U8'], ['people', '人员与密码'], ['orgs', '借用单位']]],
  ['系统', [['phone', '手机与访客二维码'], ['autostart', '开机自动启动'], ['backup', '备份与恢复'], ['other', '其他']]]
];
const NAV0 = [
  ['home', '首页'], ['daily', '产品出入库情况'], ['out', '出库'], ['loan', '借用归还'], ['arrival', '到货'],
  ['stock', '产品与库存'], ['report', '报表'], ['print', '打印'], ['misc', '库房杂物'], ['slip', '称重单'], ['backup', '数据备份']
];
const NAV_HIDE0 = ['misc', 'slip', 'backup'];   // 默认不进顶栏（设置里可勾选显示）；路由 #misc / #slip / #backup 仍可用
function navOrder() {
  const o = ((S.boot && S.boot.settings.nav_order) || []).filter(k => NAV0.some(x => x[0] === k));
  return [...new Set(o.concat(NAV0.map(x => x[0])))];
}
function navHidden() {
  const st = (S.boot && S.boot.settings) || {};
  return Array.isArray(st.nav_hidden) ? st.nav_hidden.slice() : NAV_HIDE0.slice();
}
function navLabel(k) { return (NAV0.find(x => x[0] === k) || [k, k])[1]; }
const SET_FN = {};
/* 设置全局搜索：菜单名 + 说明关键词；右侧再按表单项过滤 */
const SET_HINTS = {
  about: '关于 版本号 打包日期 数据文件夹 局域网 端口 开机 更新记录 制作人',
  nav: '顶部导航 顶栏 顺序 显示 隐藏 改名 显示为 杂物 称重 备份 日表',
  reportcols: '报表 页签 列 顺序 筛选 液氧 换算 入出库 4号院 列名',
  names: '名称设置 显示名 菜单 页面 列名 选项 出库类型 改叫法 恢复默认',
  print: '打印抬头 公司名 页脚 打印人 打印时间 Excel Word',
  defaults: '常用默认值 场次 出库类型 单据来源 列表天数 效期 密码缓存 换货',
  layout: '交接表格式 表格设置 钢瓶 产品 列 车牌 场次',
  plates: '车牌 行序 临时车辆',
  daily: '产品出入库情况 日表 库存对应 在外钢瓶 40L 10L 客户自提',
  ocr: '识别 OCR 用量截图 称重单 U8 损耗率 问写入',
  options: '选项列表 U8单细分 U8类型 产品分类 杂物分类 出库类型 单据来源 客户自提',
  couriers: '配送员 名单 顺序 类型',
  products: '产品 U8 仓库 存货编码 默认不入U8',
  people: '人员 密码 4位 身份',
  orgs: '借用单位 访客 常用单位',
  phone: '手机 访客 二维码 WiFi 防火墙 局域网地址',
  autostart: '开机自动启动 托盘 Windows 启动项',
  backup: '备份 恢复 另存 U盘 共享文件夹 保留份数',
  other: '其他 效期 密码缓存 库存流水 交接表批量配送 杂物 称重 备份入口',
};
function setIndex() {
  const out = [];
  SETS.forEach(([g, items]) => items.forEach(([k, t]) => {
    out.push({ k, t, g, hay: (g + ' ' + t + ' ' + (SET_HINTS[k] || '')).toLowerCase() });
  }));
  return out;
}
function setMatch(q) {
  q = String(q || '').trim().toLowerCase();
  if (!q) return setIndex();
  const parts = q.split(/\s+/).filter(Boolean);
  return setIndex().filter(x => parts.every(p => x.hay.includes(p)));
}
function setFilterMenu(el, q, sec) {
  const hits = new Set(setMatch(q).map(x => x.k));
  const empty = q && !hits.size;
  $$('#sMenu .g', el).forEach(g => {
    let any = false, n = g.nextElementSibling;
    while (n && !n.classList.contains('g')) {
      const k = n.dataset.sk;
      const ok = !q || hits.has(k);
      n.style.display = ok ? '' : 'none';
      if (ok) any = true;
      n = n.nextElementSibling;
    }
    g.style.display = (!q || any) ? '' : 'none';
  });
  const tip = $('#sSearchTip', el);
  if (tip) tip.textContent = empty ? '没有匹配的设置项' : (q ? ('找到 ' + hits.size + ' 项 · 点左侧或下方结果直达') : '');
}
function setFilterBody(body, q) {
  q = String(q || '').trim().toLowerCase();
  $$('.set-miss', body).forEach(n => n.classList.remove('set-miss'));
  $$('.set-hit', body).forEach(n => n.classList.remove('set-hit'));
  if (!q) {
    $$('.sform > label, .sform > div, .sbody h3, .sbody .clog, .sbody table, .sbody .sbar, .sbody .hint', body).forEach(n => { n.style.display = ''; });
    return;
  }
  const parts = q.split(/\s+/).filter(Boolean);
  const okText = t => { t = String(t || '').toLowerCase(); return parts.every(p => t.includes(p)); };
  // sform：label + 右侧内容成对
  $$('.sform', body).forEach(form => {
    const kids = [...form.children];
    for (let i = 0; i < kids.length; i++) {
      const lab = kids[i];
      if (lab.tagName !== 'LABEL') continue;
      const val = kids[i + 1];
      const blob = (lab.textContent || '') + ' ' + ((val && val.textContent) || '') + ' ' + ((val && val.querySelector && (val.querySelector('.hint') || {}).textContent) || '');
      const hit = okText(blob);
      lab.classList.toggle('set-hit', hit);
      lab.classList.toggle('set-miss', !hit);
      lab.style.display = hit ? '' : 'none';
      if (val && val.tagName !== 'LABEL') {
        val.classList.toggle('set-miss', !hit);
        val.style.display = hit ? '' : 'none';
      }
    }
  });
  $$('h3', body).forEach(h => {
    const hit = okText(h.textContent);
    h.style.display = hit || !q ? '' : 'none';
    h.classList.toggle('set-hit', hit);
  });
}
Pages.settings = async (el, arg) => {
  if (arg === 'daily') arg = 'daily';
  // 支持 settings/nav?q=打印 或记忆上次搜索
  let q = Pages.settings.q || '';
  if (typeof arg === 'string' && arg.includes('?')) {
    const [a, qs] = arg.split('?');
    arg = a;
    const m = /(?:^|&)q=([^&]*)/.exec(qs || '');
    if (m) q = decodeURIComponent(m[1].replace(/\+/g, ' '));
  }
  const all = SETS.flatMap(g => g[1].map(x => x[0]));
  const sec = all.includes(arg) ? arg : 'about';
  await loadBoot();
  const hits = setMatch(q);
  el.innerHTML = UI.ph('设置', '顶部可搜 · 左边分组 · 保存要密码 · 大家共用', '按名称或说明搜左侧菜单和右侧表单项；点结果直达。改动可在「数据备份 → 操作记录」查看。',
    `<div class="set-search"><input class="inp" id="sQ" placeholder="搜设置：如 打印、密码、配送员、备份…" value="${esc(q)}" autocomplete="off"><button class="btn sm" id="sQClear" title="清空">清除</button></div>`)
    + `<div id="sSearchTip" class="set-search-tip muted"></div>`
    + (q ? `<div class="set-hits" id="sHits">${hits.length ? hits.map(x => `<a data-sk="${esc(x.k)}"><b>${esc(x.t)}</b><small>${esc(x.g)}</small></a>`).join('') : '<span class="muted">没有匹配</span>'}</div>` : '')
    + `<div class="setc page-settings"><div class="smenu" id="sMenu">${SETS.map(g => `<div class="g">${esc(g[0])}</div>${g[1].map(([k, t]) => `<a data-sk="${k}" class="${k === sec ? 'on' : ''}">${esc(t)}</a>`).join('')}`).join('')}</div>
    <div class="sbody card page-card" id="sBody"><div class="empty">加载中…</div></div></div>`;
  const go = k => { Pages.settings.q = ($('#sQ', el) || {}).value || q; App.tab('#settings/' + k); };
  $('#sMenu', el).onclick = e => { const a = e.target.closest('[data-sk]'); if (a) go(a.dataset.sk); };
  $('#sHits', el) && ($('#sHits', el).onclick = e => { const a = e.target.closest('[data-sk]'); if (a) go(a.dataset.sk); });
  const applyQ = () => {
    const v = ($('#sQ', el) || {}).value || '';
    Pages.settings.q = v;
    setFilterMenu(el, v, sec);
    setFilterBody($('#sBody', el), v);
    const box = $('#sHits', el);
    if (box) {
      const hs = setMatch(v);
      box.innerHTML = v ? (hs.length ? hs.map(x => `<a data-sk="${esc(x.k)}"><b>${esc(x.t)}</b><small>${esc(x.g)}</small></a>`).join('') : '<span class="muted">没有匹配</span>') : '';
    } else if (v) {
      // 无结果条时仅过滤菜单/正文
    }
  };
  let tmr;
  $('#sQ', el).oninput = () => { clearTimeout(tmr); tmr = setTimeout(() => {
    const v = $('#sQ', el).value;
    const had = !!$('#sHits', el);
    const needBar = !!String(v || '').trim();
    Pages.settings.q = v;
    // 结果条有无变化才整页重绘；其余就地过滤，避免打断输入
    if (had !== needBar) Pages.settings(el, sec);
    else {
      applyQ();
      const tip = $('#sSearchTip', el);
      const n = setMatch(v).length;
      if (tip) tip.textContent = needBar ? (n ? ('找到 ' + n + ' 项 · 点左侧或下方结果直达') : '没有匹配的设置项') : '';
    }
  }, 180); };
  $('#sQClear', el).onclick = () => { Pages.settings.q = ''; Pages.settings(el, sec); };
  setFilterMenu(el, q, sec);
  const body = $('#sBody', el); const re = () => Pages.settings(el, sec);
  try {
    await SET_FN[sec](body, re);
    setFilterBody(body, q);
    const hit = body.querySelector('.set-hit');
    if (hit && q) try { hit.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } catch (e) { }
  } catch (e) { body.innerHTML = '<div class="empty">' + esc(e.message) + '</div>'; }
  const sq = $('#sQ', el); if (sq && q) { const n = q.length; try { sq.focus(); sq.setSelectionRange(n, n); } catch (e) { } }
};
const sHead = (t, d) => `<h2>${esc(t)}</h2>${d ? `<div class="desc">${d}</div>` : ''}`;
const sLines = v => String(v || '').split(/[\n,，、]/).map(x => x.trim()).filter(Boolean);
async function setSave(data, title, extra) { await save('/api/settings/save', Object.assign({ data }, extra || {}), title || '保存设置'); toast('已保存'); await loadBoot(); }

SET_FN.about = async b => {
  const v = await api('/api/version');
  b.innerHTML = sHead('关于', '') + `<div class="sform">
    <label>系统名称</label><div>${esc(v.site_name || v.name)} <span class="hint">（${esc(v.name)}）</span></div>
    <label>版本号</label><div><b id="abVer">${esc(v.version)}</b>${v.author ? `<span class="muted" id="abAuthor" style="margin-left:12px;font-size:12.5px">${esc(v.author)}</span>` : ''}</div>
    <label>打包日期</label><div>${esc(v.build_date)}</div>
    <label>数据文件夹</label><div><code id="abDir">${esc(v.data_dir)}</code> <span class="hint">数据库 ${(v.db_size / 1048576).toFixed(1)} MB；升级换程序时保留这个文件夹</span></div>
    <label>局域网地址</label><div>${(v.lan || []).map(u => `<div><a class="link" href="${esc(u)}" target="_blank">${esc(u)}</a>　手机：${esc(u)}/m/　访客：${esc(u)}/m/guest</div>`).join('') || '<span class="muted">没有找到局域网地址（只能本机打开）</span>'}</div>
    <label>端口</label><div>${esc(v.port)}</div>
    <label>开机自动启动</label><div id="abAs">…</div></div>
    <h3>更新记录</h3><div class="clog">${v.changelog.map(c => `<div class="v">版本 ${esc(c.version)}　<span class="muted" style="font-weight:400">${esc(c.date)}</span></div><ul>${c.items.map(i => `<li>${esc(i)}</li>`).join('')}</ul>`).join('')}</div>`;
  api('/api/autostart').then(a => { $('#abAs', b).innerHTML = a.supported ? `${a.on ? '已开启' : '已关闭'} <a class="link" href="#settings/autostart">修改</a>` : '<span class="muted">（主机不是 Windows）</span>'; }).catch(() => { });
};

/* 名称设置：可改的原名称。按屏幕上出现的顺序分组；同一个词只出现一次（改一次，所有地方都变），灰字写明影响哪些地方 */
function nmGroups(sessions) {
  const s = S.boot.settings, other = (S.boot.daily_cols.other || []).map(o => o[1]);
  const G = [
    ['菜单和页面', [
      ['首页', '电脑顶部菜单'], ['出库', '电脑顶部菜单、页面标题；手机首页、页面标题；交接表汇总表头'], ['产品出入库情况', '电脑顶部菜单、页面标题'],
      ['借用归还', '电脑顶部菜单、页面标题；手机首页、页面标题'], ['到货', '电脑顶部菜单、页面标题'], ['产品与库存', '电脑顶部菜单、页面标题'],
      ['库房杂物', '电脑顶部菜单、页面标题；手机首页、页面标题'], ['报表', '电脑顶部菜单、页面标题'], ['打印', '电脑顶部菜单、打印页；手机入库单'], ['称重单', '电脑顶部菜单、页面标题'],
      ['数据备份', '电脑顶部菜单、页面标题'], ['设置', '电脑顶部菜单、页面标题'], ['待补全', '电脑首页入口、页面标题'],
      ['出入库情况', '手机首页、页面标题（电脑上叫「产品出入库情况」）'], ['待补全快速记', '手机首页、页面标题'], ['待补全清单', '手机首页、页面标题'],
      ['访客登记借用', '访客页标题、设置里的二维码说明']]],
    ['页面里的分页', [
      ['单笔', '出库 → 分页'], ['批量', '出库 → 分页'], ['出库记录', '出库 → 分页'], ['领用出库单', '出库 → 分页'],
      ['钢瓶交接表', '产品出入库情况 → 分页；手机出入库情况'], ['产品交接表', '产品出入库情况 → 分页；手机出入库情况'], ['汇总（财务表）', '产品出入库情况 → 分页'], ['表格设置', '产品出入库情况 → 按钮、页面标题'],
      ['借出登记', '借用归还 → 分页'], ['借用记录', '借用归还 → 分页'], ['按单位', '借用归还 → 分页'], ['补录借用本', '借用归还 → 分页'], ['访客登记', '借用归还 → 分页'],
      ['产品库存', '产品与库存 → 分页'], ['盘点', '产品与库存 → 分页'], ['批次追溯', '产品与库存 → 分页'], ['U8 账面对照', '产品与库存 → 分页'],
      ['备份与导入', '数据备份 → 分页'], ['回收站', '数据备份 → 分页'], ['操作记录', '数据备份 → 分页']]],
    ['列名', [['领取人信息', '交接表汇总（财务表）表头'], ['出库', '交接表汇总表头'], ['入库', '交接表汇总表头'], ['回收', '交接表汇总表头'], ['更换', '交接表汇总表头'], ['新送', '交接表汇总表头'],
      ['手工单更换', '交接表汇总表头'], ['手工单新送', '交接表汇总表头'], ['实际配送', '交接表汇总表头'], ['其他产品当天总出库', '交接表汇总表头'], ['制氧机', '交接表汇总表头']]
      .concat(other.map(o => [o, '交接表汇总表头（其他产品）'])).concat([['备注', '交接表汇总表头及各处表格']])],
    ['选项', [].concat(
      (s.out_kinds || []).map(o => [o, '出库「类型」、出库记录筛选、首页']), (s.sources || []).map(o => [o, '出库「单据来源」、出库记录筛选']),
      (s.u8_types || []).map(o => [o, '出库选「U8单」时的细分（外来客户购买等）；出库记录仅在筛「U8单」后出现']), (sessions || []).map(o => [o, '交接表场次（电脑、手机）']),
      (s.categories || []).map(o => [o, '产品分类（产品与库存）']), (s.misc_categories || []).map(o => [o, '库房杂物分类']),
      [['未归还', '借用状态'], ['部分归还', '借用状态'], ['已归还', '借用状态'], ['待入U8', '到货 U8 状态'], ['已入U8', '到货 U8 状态'], ['不入U8', '到货 U8 状态'], ['配送员', '配送员类型；表头'], ['点位', '配送员类型']])]
  ];
  // 合并重复：同一个原名称只列一次（放在它最先出现的组），影响的地方合在一起写
  const seen = {}, out = [];
  G.forEach(([t, list]) => { const rows = []; list.forEach(([o, w]) => { if (!o) return; if (seen[o]) { if (!seen[o].w.includes(w)) seen[o].w.push(w); return; } seen[o] = { o, w: [w] }; rows.push(seen[o]); }); out.push([t, rows]); });
  const rep = rOrder().map(k => RT[k].title);   // 报表名称单独一组（每张报表一行）
  rep.forEach(o => { if (!seen[o]) seen[o] = { o, w: ['报表页签、表格标题、打印标题'] }; });
  return { groups: out, known: new Set(Object.keys(seen)), seen };
}
SET_FN.names = async (b, re) => {
  const s = S.boot.settings, cur = Object.assign({}, s.ui_names || {});
  let ses = []; try { ses = (await api('/api/paper/layout')).sessions || []; } catch (e) { }
  const { groups, known, seen } = nmGroups(ses);
  Object.keys(cur).forEach(k => { if ((cur[k] || '').trim() === k) delete cur[k]; });  // 原名=显示名 不算改过
  const custom = Object.keys(cur).filter(k => !known.has(k));
  const wtx = x => `<div class="nmw">${esc(x.w.join('；'))}</div>`;
  // 「显示为」空着=默认；占位符不要再写原名称，否则和左侧看起来像重复
  const nmVal = o => { const v = (cur[o] || '').trim(); return (v && v !== o) ? v : ''; };
  const row = x => `<tr><td class="o">${esc(x.o)}${wtx(x)}</td><td><input class="inp sm" data-o="${esc(x.o)}" value="${esc(nmVal(x.o))}" placeholder="改显示名…"></td></tr>`;
  const rep = rOrder().map(k => seen[RT[k].title]);
  b.setAttribute('data-nonm', '1');
  b.innerHTML = sHead('名称设置', '把界面上的名称改成你们习惯的叫法（电脑、手机、访客页、打印都生效）。<b>只改显示</b>：保存的数据、下载的原格式 Excel / Word 不变。空着 = 用默认名称。每个名称只列一次，灰字是它出现的地方。') +
    `<div class="sform" style="margin-bottom:8px"><label>系统名称</label><div><input class="inp" id="nmSite" value="${esc(s.site_name || '')}" placeholder="库房出入库"><span class="hint">左上角和浏览器标题</span></div></div>
    <input class="inp sm" id="nmQ" placeholder="搜名称…" style="width:220px;margin:6px 0">
    ${groups.slice(0, 2).map(([t, list]) => `<h3>${esc(t)}</h3><table class="t ntab"><thead><tr><th>原名称</th><th>显示为</th></tr></thead><tbody>${list.map(row).join('')}</tbody></table>`).join('')}
    <h3>报表名称 <small class="muted" style="font-weight:400">每张报表一个名称，页签、表格标题、打印标题都用它；顺序同报表页签（在「<a class="link" href="#settings/reportcols">报表页签与列</a>」里调）</small></h3>
    <table class="t ntab" id="nmRep"><thead><tr><th>原名称</th><th>显示为</th></tr></thead><tbody>${rep.map(row).join('')}</tbody></table>
    ${groups.slice(2).map(([t, list]) => `<h3>${esc(t)}${t === '列名' ? ' <small class="muted" style="font-weight:400">报表里的列名在「<a class="link" href="#settings/reportcols">报表页签与列</a>」里按报表改；纸质交接表的列名在「<a class="link" href="#daily/layout">表格设置</a>」里改</small>' : ''}</h3><table class="t ntab"><thead><tr><th>原名称</th><th>显示为</th></tr></thead><tbody>${list.map(row).join('')}</tbody></table>`).join('')}
    <h3>其他（自己加）</h3><div class="hint" style="margin-bottom:6px">界面上任何一段完整的文字都可以改，比如按钮、标题；原名称要和屏幕上的字一模一样。</div>
    <table class="t ntab" id="nmCus"><thead><tr><th>原名称</th><th>显示为</th></tr></thead><tbody>${custom.map(o => `<tr><td><input class="inp sm" data-co value="${esc(o)}"></td><td><input class="inp sm" data-cv value="${esc((cur[o] || '').trim() === o ? '' : (cur[o] || ''))}" placeholder="改显示名…"></td></tr>`).join('')}</tbody></table>
    <button class="btn sm" id="nmAdd" style="margin-top:6px">＋ 加一条</button>
    <div class="sbar"><button class="btn pri" id="nmSave">保存名称</button><button class="btn" id="nmReset">恢复默认</button><span class="muted" id="nmCnt">已改 ${Object.keys(cur).length} 个</span></div>`;
  $('#nmQ', b).oninput = e => { const q = e.target.value.trim(); $$('.ntab tbody tr', b).forEach(tr => { if (tr.closest('#nmCus')) return; tr.style.display = !q || tr.textContent.includes(q) || $('input', tr).value.includes(q) ? '' : 'none'; }); };
  $('#nmAdd', b).onclick = () => { $('#nmCus tbody', b).insertAdjacentHTML('beforeend', '<tr><td><input class="inp sm" data-co></td><td><input class="inp sm" data-cv placeholder="改显示名…"></td></tr>'); $('#nmCus tbody tr:last-child input', b).focus(); };
  $('#nmSave', b).onclick = async () => {
    try {
      const m = {}; $$('[data-o]', b).forEach(i => { const v = i.value.trim(); if (v && v !== i.dataset.o) m[i.dataset.o] = v; });
      $$('#nmCus tbody tr', b).forEach(tr => { const o = $('[data-co]', tr).value.trim(), v = $('[data-cv]', tr).value.trim(); if (o && v && v !== o) m[o] = v; });
      await setSave({ ui_names: m, site_name: $('#nmSite', b).value.trim() || '库房出入库' }, '名称设置'); location.reload();
    } catch (e) { fail(e); }
  };
  $('#nmReset', b).onclick = async () => {
    if (!await confirmBox('所有名称恢复成默认（系统名称也恢复成「库房出入库」）？', '恢复默认')) return;
    try { await setSave({ ui_names: {}, site_name: '库房出入库' }, '名称恢复默认'); location.reload(); } catch (e) { fail(e); }
  };
};

SET_FN.defaults = async b => {
  const d = defs(), s = S.boot.settings; let ses = ['早上', '中午', '晚上'];
  try { ses = (await api('/api/paper/layout')).sessions || ses; } catch (e) { }
  b.innerHTML = sHead('常用默认值', '打开页面时先选好的值，随时可以在页面上改。') + `<div class="sform">
    <label>交接表默认场次</label><div><select class="inp" id="dfSes">${ses.map(x => `<option value="${esc(x)}" ${x === d.session ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select></div>
    <label>新出库单默认类型</label><div><select class="inp" id="dfKind"><option value="">（不选）</option>${(s.out_kinds || []).map(x => `<option value="${esc(x)}" ${x === d.out_kind ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select></div>
    <label>新出库单默认来源</label><div><select class="inp" id="dfSrc"><option value="">（不选）</option>${(s.sources || []).map(x => `<option value="${esc(x)}" ${x === d.out_source ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select></div>
    <label>记录列表默认显示</label><div><select class="inp" id="dfDays">${[[0, '全部日期'], [7, '最近 7 天'], [30, '最近 30 天'], [90, '最近 90 天'], [365, '最近一年']].map(([v, t]) => `<option value="${v}" ${+d.list_days === v ? 'selected' : ''}>${t}</option>`).join('')}</select><span class="hint">出库记录、借用记录</span></div>
    <label>临近效期提醒</label><div><input class="inp num" id="dfExp" value="${esc(s.expiry_alert_days)}" style="width:90px"> 天</div>
    <label>密码记住</label><div><input class="inp num" id="dfPin" value="${esc(s.pin_cache_minutes)}" style="width:90px"> 分钟<span class="hint">输一次密码后这么久内不再问；0 = 每次都问</span></div></div>
    <div class="sbar"><button class="btn pri" id="dfSave">保存</button></div>`;
  $('#dfSave', b).onclick = async () => {
    try { await setSave({ defaults: { session: $('#dfSes', b).value, out_kind: $('#dfKind', b).value, out_source: $('#dfSrc', b).value, list_days: +$('#dfDays', b).value }, expiry_alert_days: +$('#dfExp', b).value || 90, pin_cache_minutes: +$('#dfPin', b).value || 0 }, '常用默认值'); } catch (e) { fail(e); }
  };
};

SET_FN.print = async b => {
  const p = S.boot.settings.print || {};
  b.innerHTML = sHead('打印抬头', '电脑上「打印」出来的报表、记录、单据用这里的抬头。下载的 Excel / Word 文件不受影响。') + `<div class="sform">
    <label>公司名称（抬头）</label><div><input class="inp" id="prCo" value="${esc(p.company || '')}" placeholder="不填就不印"><span class="hint">印在每页标题上方</span></div>
    <label>页脚</label><div><label><input type="checkbox" id="prFt" ${p.footer !== false ? 'checked' : ''}> 印「打印人、打印时间」</label></div></div>
    <div class="sbar"><button class="btn pri" id="prSave">保存</button><button class="btn" id="prTry">打印预览</button></div>`;
  $('#prSave', b).onclick = async () => { try { await setSave({ print: { company: $('#prCo', b).value.trim(), footer: $('#prFt', b).checked } }, '打印设置'); } catch (e) { fail(e); } };
  $('#prTry', b).onclick = () => printHtml('<div class="ttl">打印样张</div><table><tr><th>日期</th><th>产品</th><th>数量</th></tr><tr><td>' + today() + '</td><td class="l">示例</td><td>1</td></tr></table>');
};

SET_FN.nav = async (b, re) => {
  let order = navOrder();
  let hidden = navHidden();
  const navLabs = () => NAV0.concat([['settings', '设置']]).map(x => x[1]);
  const nmMap = () => Object.assign({}, (S.boot && S.boot.settings && S.boot.settings.ui_names) || {});
  let draft = nmMap();   // 顶栏相关显示名草稿（↑↓ 重画时保留刚填的字）
  // 与名称设置同规格：空着=默认；占位符写「改显示名…」，不再回显原名称（避免左右看起来重复）
  Object.keys(draft).forEach(k => { if ((draft[k] || '').trim() === k) delete draft[k]; });
  const navVal = o => { const v = (draft[o] || '').trim(); return (v && v !== o) ? v : ''; };
  const snap = () => {
    $$('[data-nav-nm]', b).forEach(i => { const o = i.dataset.navNm, v = (i.value || '').trim(); if (v && v !== o) draft[o] = v; else delete draft[o]; });
    $$('[data-nav-show]', b).forEach(c => {
      const k = c.dataset.navShow;
      if (c.checked) hidden = hidden.filter(x => x !== k); else if (!hidden.includes(k)) hidden.push(k);
    });
  };
  const draw = () => {
    b.setAttribute('data-nonm', '1');
    b.innerHTML = sHead('顶部导航', '顶栏顺序：默认「首页 · 日表 · 出库 · 借用 · 到货 · 库存 · 报表 · 打印 · 设置」。杂物 / 称重 / 备份默认隐藏（勾选「显示」才进顶栏），直接打开地址仍可用。「设置」固定最右。改名与「名称设置」同一套，只改显示；右边空着 = 用默认名称。') +
      `<table class="t" id="nvT" style="max-width:820px"><thead><tr><th style="width:52px">顺序</th><th>默认名称</th><th>显示为</th><th style="width:72px">显示</th><th style="width:120px"></th></tr></thead><tbody>
      ${order.map((k, i) => { const lab = navLabel(k); const canHide = NAV_HIDE0.includes(k); return `<tr data-k="${k}" class="${hidden.includes(k) ? 'muted' : ''}"><td class="c">${i + 1}</td><td>${esc(lab)}<span class="muted" style="margin-left:8px;font-size:12px">${k}</span></td>
        <td><input class="inp sm" data-nav-nm="${esc(lab)}" value="${esc(navVal(lab))}" placeholder="改显示名…"></td>
        <td class="c">${canHide ? `<label title="勾选后出现在顶栏"><input type="checkbox" data-nav-show="${k}" ${hidden.includes(k) ? '' : 'checked'}> 显示</label>` : '<span class="muted" style="font-size:12px">—</span>'}</td>
        <td class="c"><button class="btn sm" data-up="${i}" ${i ? '' : 'disabled'}>↑</button> <button class="btn sm" data-dn="${i}" ${i < order.length - 1 ? '' : 'disabled'}>↓</button></td></tr>`; }).join('')}
      <tr data-k="settings"><td class="c muted">—</td><td>设置<span class="muted" style="margin-left:8px;font-size:12px">settings</span></td>
        <td><input class="inp sm" data-nav-nm="设置" value="${esc(navVal('设置'))}" placeholder="改显示名…"></td>
        <td class="c muted" style="font-size:12px">—</td>
        <td class="c muted" style="font-size:12px">固定最后</td></tr>
      </tbody></table>
      <div class="hint" style="margin-top:8px">改名举例：把「产品出入库情况」显示成「日表」（默认已是；填着「日表」是正常默认，不是重复）。完整列名 / 选项改名仍在「<a class="link" href="#settings/names">名称设置</a>」。</div>
      <div class="sbar"><button class="btn pri" id="nvSave">保存</button><button class="btn" id="nvDef">恢复默认顺序与显示</button><button class="btn" id="nvNmDef">顶栏名称恢复默认</button></div>`;
  };
  draw();
  b.onclick = async e => {
    const t = e.target.closest('button') || e.target;
    const mv = (i, d) => { snap(); const j = i + d; if (j < 0 || j >= order.length) return; [order[i], order[j]] = [order[j], order[i]]; draw(); };
    if (t.dataset.up !== undefined && t.dataset.up !== '') return mv(+t.dataset.up, -1);
    if (t.dataset.dn !== undefined && t.dataset.dn !== '') return mv(+t.dataset.dn, 1);
    if (t.id === 'nvDef') { snap(); order = NAV0.map(x => x[0]); hidden = NAV_HIDE0.slice(); draw(); return; }
    if (t.id === 'nvNmDef') {
      snap();
      navLabs().forEach(o => { delete draft[o]; });
      draw();
      return;
    }
    if (t.id === 'nvSave') {
      try {
        snap();
        const m = nmMap();
        const labs = navLabs();
        labs.forEach(o => { if (draft[o]) m[o] = draft[o]; else delete m[o]; });
        // 日表：用户没另写时，保留默认显示名（写入 ui_names，刷新也稳）
        if (!m['产品出入库情况']) m['产品出入库情况'] = '日表';
        await setSave({ nav_order: order, nav_hidden: hidden, ui_names: m }, '顶部导航');
        draft = nmMap();
        if (typeof nmSet === 'function') nmSet(Object.assign({ '产品出入库情况': '日表' }, S.boot.settings.ui_names || {}));
        if (typeof App.applyNav === 'function') App.applyNav();
        const sn = (S.boot.settings.site_name || '库房出入库');
        const elN = document.getElementById('siteName'); if (elN) elN.textContent = sn;
        document.title = sn;
        re();
      } catch (er) { fail(er); }
    }
  };
  b.onchange = e => { if (e.target && e.target.dataset && e.target.dataset.navShow !== undefined) { snap(); draw(); } };
};

SET_FN.reportcols = async (b, re) => {
  const pr = (await api('/api/report/prefs')).items || {};
  let order = rOrder();
  const draw = () => {
    b.innerHTML = sHead('报表页签与列', '「报表」页上各表页签的顺序（↑ ↓ 调整后点「保存顺序」）；每张报表显示哪些列、列的顺序、列名、默认筛选点「设置」。只影响屏幕显示、打印和「按当前显示导出」，下载的原表不变。报表的名称在「<a class="link" href="#settings/names">名称设置</a>」里改。') +
      `<table class="t" id="roT" style="max-width:820px"><thead><tr><th style="width:44px">顺序</th><th>报表</th><th>列设置</th><th></th></tr></thead><tbody>${order.map((k, i) => { const x = pr[k] || {}; const tx = [x.hidden && x.hidden.length ? '隐藏 ' + x.hidden.length + ' 列' : '', x.labels && Object.keys(x.labels).length ? '改名 ' + Object.keys(x.labels).length + ' 列' : '', x.order && x.order.length ? '调了列顺序' : '', x.filter && Object.values(x.filter).some(v => v && (v.length || v.from || v.to)) ? '有默认筛选' : ''].filter(Boolean).join('，') || '默认';
        return `<tr data-k="${k}"><td class="c">${i + 1}</td><td>${esc(RT[k].title)}</td><td class="muted">${esc(tx)}</td><td class="c" style="white-space:nowrap"><button class="btn sm" data-up="${i}" ${i ? '' : 'disabled'} title="上移">↑</button> <button class="btn sm" data-dn="${i}" ${i < order.length - 1 ? '' : 'disabled'} title="下移">↓</button>　<button class="btn sm" data-rk="${k}">设置</button> ${pr[k] ? `<button class="btn sm" data-rr="${k}">恢复默认</button>` : ''}</td></tr>`; }).join('')}</tbody></table>
      <div class="sbar"><button class="btn pri" id="roSave" ${order.join() === rOrder().join() ? 'disabled' : ''}>保存顺序</button><button class="btn" id="roDef">恢复默认顺序</button></div>`;
  };
  draw();
  b.onclick = async e => {
    const t = e.target.closest('button') || e.target;
    const mv = (i, d) => { const j = i + d; [order[i], order[j]] = [order[j], order[i]]; draw(); };
    if (t.dataset.up) return mv(+t.dataset.up, -1);
    if (t.dataset.dn) return mv(+t.dataset.dn, 1);
    if (t.id === 'roDef') { order = RORDER0.slice(); draw(); $('#roSave', b).disabled = false; return; }
    if (t.id === 'roSave') { try { await setSave({ report_order: order }, '报表页签顺序'); re(); } catch (er) { fail(er); } return; }
    if (t.dataset.rk) { sessionStorage.setItem('openPrefs', t.dataset.rk); location.hash = '#report/' + t.dataset.rk; }
    if (t.dataset.rr) { try { await save('/api/report/prefs/reset', { key: t.dataset.rr }, '报表显示恢复默认'); toast('已恢复'); re(); } catch (er) { fail(er); } }
  };
};

SET_FN.layout = async b => {
  const l = await api('/api/paper/layout');
  b.innerHTML = sHead('交接表格式', '纸质钢瓶交接表、产品交接表的列、车牌行、场次，在「表格设置」里拖动修改（和纸上一样排）。') + `<div class="sform">
    <label>场次</label><div>${(l.sessions || []).map(esc).join('、')}</div>
    <label>车牌行</label><div>${(l.plates || []).length} 行 <a class="link" href="#settings/plates">改车牌</a></div></div>
    <div class="sbar"><a class="btn pri" href="#daily/layout">打开表格设置</a></div>`;
};

SET_FN.plates = async (b, re) => {
  const l = await api('/api/paper/layout');
  b.innerHTML = sHead('车牌', '纸质交接表上的车牌行，顺序和纸上一样。一行一个。临时车辆不用加，录入时直接写车牌就行。') +
    `<textarea class="inp" id="plT" rows="14" style="width:260px;font-family:inherit">${esc((l.plates || []).join('\n'))}</textarea>
    <div class="sbar"><button class="btn pri" id="plSave">保存车牌</button><span class="muted">共 ${(l.plates || []).length} 个</span></div>`;
  $('#plSave', b).onclick = async () => { try { await save('/api/paper/plates', { plates: sLines($('#plT', b).value) }, '交接表车牌'); toast('已保存'); re(); } catch (e) { fail(e); } };
};

SET_FN.daily = async b => {
  const o = S.boot.settings.outside_base || {};
  b.innerHTML = sHead('产品出入库情况', '日表各列扣哪个产品的库存；在外钢瓶起始数。「客户自提」不计入每日产品出入库情况表（该表全部是配送）。') + `<div id="dailySet"><div class="sform">
    <label>在外 40L 起始数</label><div><input class="inp num" id="sO40" value="${o['40'] ?? ''}" placeholder="未知" style="width:110px"><span class="hint">某天点清后填</span></div>
    <label>在外 10L 起始数</label><div><input class="inp num" id="sO10" value="${o['10'] ?? ''}" placeholder="未知" style="width:110px"></div></div>
    <h3>日表各列对应的产品</h3><div class="sform" id="sMap">${[['c40', '40L 钢瓶'], ['c10', '10L 钢瓶']].concat(S.boot.daily_cols.other).map(([k, l]) => `<label>${esc(l)}</label><div><select class="inp sm" data-mk="${k}"><option value="">（不扣库存）</option>${S.boot.products.map(p => `<option value="${p.id}" ${S.boot.daily_cols.map[k] === p.id ? 'selected' : ''}>${esc(p.label)}</option>`).join('')}</select></div>`).join('')}</div>
    <div class="sbar"><button class="btn pri" id="sSaveD">保存日表设置</button></div></div>`;
  $('#sSaveD', b).onclick = async () => {
    try {
      const m = {}; $$('[data-mk]', b).forEach(s2 => m[s2.dataset.mk] = s2.value ? +s2.value : null);
      const v = id => { const x = $(id, b).value.trim(); return x === '' ? null : +x; };
      await setSave({ outside_base: { '40': v('#sO40'), '10': v('#sO10') } }, '日表设置', { daily_map: m });
    } catch (e) { fail(e); }
  };
};

SET_FN.ocr = async b => {
  const o = S.boot.settings.ocr || {};
  b.innerHTML = sHead('识别（OCR）', '「报表 → 换算表 → 识别用量截图」和称重单、U8 单拍照识别都在本机电脑上完成，不上传。识别后总要人工核对：看不清的格子标黄，和「合计」对不上会显示差多少。称重单页面：<a class="link" href="#slip">打开称重单</a>（顶栏默认隐藏时可从这里进）。换算表「→记录」写入入出库时，旧批不够会接下一批（确认框可选），设置见下方。') + `<div class="sform">
    <label>识别保存后</label><div><label><input type="checkbox" id="ocAsk" ${o.ask_push !== false ? 'checked' : ''}> 问一下是否把当天总计写入「液态氧原料入出库记录」</label></div>
    <label>新增一天默认损耗率</label><div><input class="inp num" id="ocRate" value="${esc(o.default_rate ?? 8)}" style="width:90px"> %<span class="hint">前一天有损耗率时沿用前一天</span></div>
    <label>换算表→入出库</label><div>
      <label><input type="checkbox" id="ocAutoNext" ${o.ledger_auto_next !== false ? 'checked' : ''}> 旧批不够时自动预选下一批（确认框仍可改；始终禁止批次剩余为负）</label>
      <div style="margin-top:6px"><span class="lab">优先新批次</span> <input class="inp" id="ocPreferNext" value="${esc(o.ledger_prefer_next || '')}" placeholder="空=有余量批优先（先已用未尽）" style="width:160px">
      <span class="hint">填批号则优先用它（须在有余量列表里）</span></div>
      <div class="muted" style="margin-top:4px;font-size:12px">不建议关掉「禁止负数」——本版始终不会把批次剩余写成负；取消勾选只表示确认框不自动预选，仍须自选新批才能写入。</div>
    </div></div>
    <div class="sbar"><button class="btn pri" id="ocSave">保存</button></div>`;
  $('#ocSave', b).onclick = async () => {
    const r = parseFloat($('#ocRate', b).value); if (!isFinite(r) || r < 0 || r > 100) return toast('损耗率填 0～100 的数字', true);
    try { await setSave({ ocr: { ask_push: $('#ocAsk', b).checked, default_rate: r, ledger_auto_next: $('#ocAutoNext', b).checked, ledger_prefer_next: ($('#ocPreferNext', b).value || '').trim() } }, '识别设置'); } catch (e) { fail(e); }
  };
};

SET_FN.options = async b => {
  const s = S.boot.settings;
  b.innerHTML = sHead('选项列表', '下拉框和建议里出现的选项。可以加、删、调顺序（一行一个）。出库类型、单据来源有固定用途，不能在这里删；要换叫法请用「<a class="link" href="#settings/names">名称设置</a>」。') + `<div class="sform" style="align-items:start">
    <label>U8单细分建议</label><div><textarea class="inp" id="opU8" rows="4" style="width:280px" title="仅单据来源=U8单时用">${esc((s.u8_types || []).join('\n'))}</textarea><div class="muted" style="margin-top:4px;font-size:12px">不是出库类型。录出库/借用且来源选「U8单」时可填（如外来客户购买）；出库记录工具栏只在筛「U8单」后出现「U8单细分」。</div></div>
    <label>产品分类</label><div><textarea class="inp" id="opCat" rows="8" style="width:280px">${esc((s.categories || []).join('\n'))}</textarea></div>
    <label>杂物分类</label><div><textarea class="inp" id="opMisc" rows="4" style="width:280px">${esc((s.misc_categories || []).join('\n'))}</textarea></div>
    <label>出库类型</label><div class="muted">${(s.out_kinds || []).map(esc).join('、')}</div>
    <label>单据来源</label><div class="muted">${(s.sources || []).map(esc).join('、')}</div></div>
    <div class="sbar"><button class="btn pri" id="opSave">保存</button></div>`;
  $('#opSave', b).onclick = async () => {
    const cat = sLines($('#opCat', b).value); if (!cat.length) return toast('产品分类至少留一个', true);
    try { await setSave({ u8_types: sLines($('#opU8', b).value), categories: cat, misc_categories: sLines($('#opMisc', b).value) }, '选项列表'); } catch (e) { fail(e); }
  };
};

SET_FN.couriers = async (b, re) => {
  b.innerHTML = sHead('配送员', '从日表导入，可增减；顺序即下载时的行序。') + `<table class="t" style="max-width:640px"><thead><tr><th>名称</th><th>类型</th><th class="n">顺序</th><th></th></tr></thead><tbody>${S.boot.couriers.map(c => `<tr class="${c.active ? '' : 'off'}"><td>${esc(c.name)}</td><td>${esc(c.kind)}</td><td class="n">${c.sort}</td>${rowActs({ ph: [0], main: ['修改', `data-ce="${c.id}"`], menu: [['删除', `data-cd="${c.id}"`, 1]] })}</tr>`).join('')}</tbody></table>
    <button class="btn sm" id="sAddC" style="margin-top:10px">＋ 加配送员 / 点位</button>`;
  b.onclick = async e => {
    const t = e.target;
    try {
      if (t.id === 'sAddC') courierDlg(null, re);
      if (t.dataset.ce) courierDlg(S.boot.couriers.find(x => x.id === +t.dataset.ce), re);
      if (t.dataset.cd && await confirmDelete('courier', +t.dataset.cd, '/api/courier/delete')) { await loadBoot(); re(); }
    } catch (er) { fail(er); }
  };
};

SET_FN.products = async (b, re) => {
  const ps = S.boot.products;
  b.innerHTML = sHead('产品与U8', '每个产品在 U8 里的仓库、存货编码，以及是否默认不入 U8（如厂内自用、杂项）。改完点保存，一次输密码。新增、合并产品在「<a class="link" href="#stock">产品与库存</a>」。') +
    `<input class="inp sm" id="puQ" placeholder="搜产品…" style="width:220px;margin-bottom:8px">
    <table class="t" id="puT"><thead><tr><th>产品</th><th>分类</th><th>U8 仓库</th><th>存货编码</th><th class="c">默认不入U8</th></tr></thead><tbody>${ps.map(p => `<tr data-id="${p.id}"><td>${esc(p.label)}</td><td class="muted">${esc(p.category || '')}</td>
      <td><input class="inp sm" data-f="u8_wh" value="${esc(p.u8_wh || '')}" style="width:130px"></td><td><input class="inp sm" data-f="u8_code" value="${esc(p.u8_code || '')}" style="width:130px"></td>
      <td class="c"><input type="checkbox" data-f="no_u8" ${p.no_u8 ? 'checked' : ''}></td></tr>`).join('')}</tbody></table>
    <div class="sbar"><button class="btn pri" id="puSave">保存改动</button><span class="muted" id="puN"></span></div>`;
  const val = (tr, f) => { const i = $(`[data-f="${f}"]`, tr); return i.type === 'checkbox' ? (i.checked ? 1 : 0) : i.value.trim(); };
  const changed = () => $$('#puT tbody tr', b).filter(tr => { const p = ps.find(x => x.id === +tr.dataset.id); return ['u8_wh', 'u8_code'].some(f => (p[f] || '') !== val(tr, f)) || (p.no_u8 ? 1 : 0) !== val(tr, 'no_u8'); });
  b.oninput = b.onchange = e => { if (e.target.id === 'puQ') { const q = e.target.value.trim(); $$('#puT tbody tr', b).forEach(tr => tr.style.display = !q || tr.textContent.includes(q) || $$('input', tr).some(i => i.value.includes(q)) ? '' : 'none'); return; } $('#puN', b).textContent = changed().length ? '改了 ' + changed().length + ' 个产品' : ''; };
  $('#puSave', b).onclick = async () => {
    const ch = changed(); if (!ch.length) return toast('没有改动');
    try {
      for (const tr of ch) { const p = ps.find(x => x.id === +tr.dataset.id); await save('/api/product/save', { data: { id: p.id, name: p.name, spec: p.spec, u8_wh: val(tr, 'u8_wh'), u8_code: val(tr, 'u8_code'), no_u8: val(tr, 'no_u8') } }, '保存产品 U8 设置'); }
      toast('已保存 ' + ch.length + ' 个产品'); await loadBoot(); re();
    } catch (e) { fail(e); }
  };
};

SET_FN.people = async (b, re) => {
  const pp = await api('/api/people');
  b.innerHTML = sHead('人员与密码', '密码 4 位数字，每人一个，不能重复；保存时输入，不用登录。') +
    `<div class="banner" style="background:var(--ac-soft);color:var(--ac)">权限暂时全开（已确认）。下面按人的设置会保留，以后关掉「全开」就按人生效。 <label style="margin-left:8px"><input type="checkbox" id="sAll" ${pp.all_open ? 'checked' : ''}> 全开</label></div>
    <table class="t"><thead><tr><th>姓名</th><th>角色</th>${pp.perm_keys.map(k => `<th class="c">${esc(k[1])}</th>`).join('')}<th></th></tr></thead><tbody>
    ${pp.items.map(p => `<tr class="${p.active ? '' : 'off'}"><td class="w">${esc(p.name)}</td><td class="w">${esc(p.role)}</td>${pp.perm_keys.map(k => `<td class="c"><input type="checkbox" data-pp="${p.id}" data-k="${k[0]}" ${p.perms[k[0]] ? 'checked' : ''}></td>`).join('')}
      ${rowActs({ ph: [0], main: ['修改密码', `data-pin="${p.id}"`], menu: [[p.active ? '停用' : '启用', `data-act="${p.id}"`]] })}</tr>`).join('')}</tbody></table>
    <button class="btn sm" id="sAddP" style="margin-top:10px">＋ 加人</button>`;
  $('#sAll', b).onchange = async e => { try { await save('/api/settings/save', { data: {}, perms_all_open: e.target.checked }, '权限设置'); toast('已保存'); } catch (er) { fail(er); re(); } };
  b.onchange = async e => {
    const t = e.target; if (!t.dataset.pp) return;
    const p = pp.items.find(x => x.id === +t.dataset.pp); p.perms[t.dataset.k] = t.checked;
    try { await save('/api/person/save', { data: { id: p.id, perms: p.perms } }, '改权限'); toast('已保存'); } catch (er) { fail(er); re(); }
  };
  b.onclick = async e => {
    const t = e.target;
    try {
      if (t.id === 'sAddP') dialog('加经办人', `<div class="row r2"><div><span class="lab">姓名</span><input class="inp" id="apN"></div><div><span class="lab">密码（4 位数字）</span><input class="inp" id="apP" inputmode="numeric"></div></div>`,
        [{ t: '取消' }, { t: '保存', cls: 'pri', fn: async ov => { await save('/api/person/save', { data: { name: $('#apN', ov).value.trim(), new_pin: $('#apP', ov).value, perms: JSON.stringify({ entry: true }) } }, '加经办人'); re(); } }]);
      if (t.dataset.pin) { const p = pp.items.find(x => x.id === +t.dataset.pin); dialog('改密码：' + p.name, `<span class="lab">新密码（4 位数字）</span><input class="inp" id="npin" inputmode="numeric" maxlength="4">`, [{ t: '取消' }, { t: '保存', cls: 'pri', fn: async ov => { await save('/api/person/save', { data: { id: p.id, new_pin: $('#npin', ov).value } }, '改密码（输你自己的或管理员密码）'); toast('已改'); } }]); }
      if (t.dataset.act) { const p = pp.items.find(x => x.id === +t.dataset.act); await save('/api/person/save', { data: { id: p.id, active: p.active ? 0 : 1 } }, '启用/停用'); re(); }
    } catch (er) { fail(er); }
  };
};

SET_FN.orgs = async b => {
  const s = S.boot.settings; let used = [];
  try { used = ((await api('/api/loans?status=all')).orgs || []).filter(o => o.loans); } catch (e) { }
  b.innerHTML = sHead('借用单位', '常用单位会出现在借用单的单位建议里和访客登记页上（访客点一下就选好）。借过的单位会自动出现，不用加。') + `<div class="sform" style="align-items:start">
    <label>常用单位</label><div><textarea class="inp" id="ogT" rows="8" style="width:260px">${esc((s.guest_orgs || []).join('\n'))}</textarea><div class="hint" style="margin:4px 0 0">一行一个</div></div>
    <label>借过的单位</label><div class="muted" style="line-height:1.8">${used.map(o => esc(o.org) + (o.open ? `（${o.open} 单未还）` : '')).join('、') || '还没有'}</div></div>
    <div class="sbar"><button class="btn pri" id="ogSave">保存</button></div>`;
  $('#ogSave', b).onclick = async () => { try { await setSave({ guest_orgs: sLines($('#ogT', b).value) }, '借用单位'); } catch (e) { fail(e); } };
};

SET_FN.autostart = async (b, re) => {
  const a = await api('/api/autostart');
  b.innerHTML = sHead('开机自动启动', '开机（登录 Windows）后自动在后台启动库房系统：没有窗口，不弹浏览器，右下角托盘有图标。只对这台主机的当前 Windows 用户生效，不需要管理员。也可以双击程序文件夹里的「开机自动启动.bat」/「取消开机自动启动.bat」。') +
    (a.supported ? `<div class="sform">
      <label>当前状态</label><div id="asSt"><b>${a.on ? '已开启' : '已关闭'}</b>${a.stale ? '<span class="hint" style="color:var(--warn)">程序文件夹搬过位置，请点「重新设置」</span>' : ''}</div>
      <label>启动命令</label><div><code style="font-size:12px;word-break:break-all">${esc(a.command || a.expected)}</code></div>
      ${a.shortcuts.length ? `<label>启动文件夹</label><div>还有快捷方式：${a.shortcuts.map(x => `<div><code style="font-size:12px">${esc(x)}</code></div>`).join('')}<div class="hint" style="margin:4px 0 0">可以留着：系统只会运行一个，不会重复启动；也可以删掉。</div></div>` : ''}</div>
      <div class="sbar">${a.on ? `<button class="btn" id="asOff">关闭开机自动启动</button>${a.stale ? '<button class="btn pri" id="asOn">重新设置</button>' : ''}` : '<button class="btn pri" id="asOn">开启开机自动启动</button>'}</div>`
    : '<div class="empty">主机不是 Windows，不能在这里设置。</div>');
  const set = async on => { try { await save('/api/autostart/set', { on }, on ? '开启开机自动启动' : '关闭开机自动启动'); toast('已' + (on ? '开启' : '关闭')); re(); } catch (e) { fail(e); } };
  if ($('#asOn', b)) $('#asOn', b).onclick = () => set(true);
  if ($('#asOff', b)) $('#asOff', b).onclick = () => set(false);
};

SET_FN.backup = async b => {
  const s = S.boot.settings;
  b.innerHTML = sHead('备份与恢复', '系统每天自动备份一次（打开时也会备份）。立即备份、下载备份、从备份恢复、导入旧数据在「<a class="link" href="#backup">数据备份</a>」页。') + `<div class="sform">
    <label>备份另存到</label><div><input class="inp" id="sBk" value="${esc(s.backup_dir || '')}" placeholder="如 E:\\库房备份（U 盘或共享文件夹）" style="width:360px"><span class="hint">不填只存在数据文件夹里</span></div>
    <label>保留备份份数</label><div><input class="inp num" id="sKeep" value="${esc(s.backup_keep)}" style="width:90px"></div></div>
    <div class="sbar"><button class="btn pri" id="bkSave">保存</button><a class="btn" href="#backup">打开数据备份</a></div>`;
  $('#bkSave', b).onclick = async () => { try { await setSave({ backup_dir: $('#sBk', b).value.trim(), backup_keep: +$('#sKeep', b).value || 30 }, '备份设置'); } catch (e) { fail(e); } };
};

SET_FN.phone = async b => {
  b.innerHTML = sHead('手机与访客二维码', '手机连库房 WiFi 后扫码，或在浏览器输入下面的地址；打不开时在主机上右键「允许手机访问_防火墙.bat」以管理员身份运行一次。') +
    `<div id="phoneAddr">${phoneQrs()}${(S.boot.lan || []).length > 1 ? `<div class="hint" style="margin-top:10px">这台电脑有多个地址，扫不开可以试：${S.boot.lan.map(u => esc(u) + '/m/').join('　')}</div>` : ''}</div>`;
  fillLibQr();
};

SET_FN.other = async b => {
  const s = S.boot.settings;
  const hid = navHidden();
  const tip = k => hid.includes(k) ? '<span class="muted">（顶栏默认隐藏，这里可直接打开）</span>' : '';
  b.innerHTML = sHead('其他', '效期、密码缓存、库存流水显示；下面是顶栏常藏的入口，不改「顶部导航」隐藏设置。') + `<div class="sform">
    <label>临近效期提醒</label><div><input class="inp num" id="sExp" value="${esc(s.expiry_alert_days)}" style="width:90px"> 天</div>
    <label>密码记住</label><div><input class="inp num" id="sPinM" value="${esc(s.pin_cache_minutes)}" style="width:90px"> 分钟</div>
    <label>库存流水</label><div><label><input type="checkbox" id="sMvD" ${s.moves_show_daily !== false ? 'checked' : ''}> 库存流水里显示交接表批量配送</label><span class="hint">关掉后「库存变化记录」和产品的「库存流水」里不列交接表（产品出入库情况）那几笔，只是不显示；库存、结存照算。「库存变化记录」本页也可单独勾选「隐藏交接表批量配送」</span></div>
    <label>不常进顶栏的页</label><div class="split" style="flex-wrap:wrap;gap:8px">
      <a class="btn sm" href="#slip">称重单</a>${tip('slip')}
      <a class="btn sm" href="#backup">数据备份</a>${tip('backup')}
      <a class="btn sm" href="#misc">库房杂物</a>${tip('misc')}
      <span class="hint">要进顶栏：设置 → 顶部导航 → 勾选「显示」</span>
    </div></div>
    <div class="sbar"><button class="btn pri" id="sSaveO">保存</button></div>`;
  $('#sSaveO', b).onclick = async () => { try { await setSave({ expiry_alert_days: +$('#sExp', b).value || 90, pin_cache_minutes: +$('#sPinM', b).value || 0, moves_show_daily: $('#sMvD', b).checked }, '保存设置'); } catch (e) { fail(e); } };
};

function courierDlg(c, done) {
  c = c || { name: '', kind: '配送员', sort: '', active: 1 };
  dialog(c.id ? '改配送员' : '加配送员 / 点位', `<div class="row r2"><div><span class="lab">名称（照日表写法）</span><input class="inp" id="cN" value="${esc(c.name)}"></div>
    <div><span class="lab">类型</span><select class="inp" id="cK"><option ${c.kind === '配送员' ? 'selected' : ''}>配送员</option><option ${c.kind === '点位' ? 'selected' : ''}>点位</option></select></div>
    <div><span class="lab">顺序（小的在前）</span><input class="inp num" id="cS" value="${esc(c.sort)}"></div><div><label style="display:block;margin-top:28px"><input type="checkbox" id="cA" ${c.active ? 'checked' : ''}> 在用</label></div></div>`,
    [{ t: '取消' }, { t: '保存', cls: 'pri', fn: async ov => {
      const d = { id: c.id, name: $('#cN', ov).value.trim(), kind: $('#cK', ov).value, active: $('#cA', ov).checked ? 1 : 0 }; const so = $('#cS', ov).value.trim(); if (so !== '') d.sort = +so;
      if (!d.name) throw new Error('请填名称'); await save('/api/courier/save', { data: d }, '保存配送员'); await loadBoot(); done();
    } }]);
}

