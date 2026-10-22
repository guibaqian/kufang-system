/* 打印页：出库单 / 入库单（字段尽量全、可不填、布局分区）+ 液氧表纸质对照 + 上传文件。不动业务库。 */
'use strict';
const Pr = { tab: 'out', tpl: null, draft: null, files: [], groups: null };

const PR_GROUPS = {
  out: [
    ['基本信息', ['date', 'party', 'dept', 'handler', 'out_no']],
    ['取货与送达', ['picker', 'phone', 'contact', 'dest', 'purpose', 'leader']],
  ],
  in: [
    ['基本信息', ['date', 'party', 'dept', 'handler', 'in_no']],
    ['收货信息', ['receiver', 'phone', 'contact', 'location']],
  ],
};

function prCompany(tpl) {
  const co = (tpl && tpl.company) || '';
  if (co) return co;
  return ((S.boot && S.boot.settings && S.boot.settings.print) || {}).company || '';
}

function prBlankLine() {
  return { name: '', spec: '', qty: '', unit: '', batch: '' };
}

function prBlankLines(n) {
  return Array.from({ length: Math.max(1, n || 5) }, () => prBlankLine());
}

function prDefaultDraft(kind) {
  const d = {
    date: today(), party: '', dept: '', picker: '', phone: '', purpose: '', dest: '',
    leader: '', handler: (PIN.get() || {}).name || '', contact: '', out_no: '', in_no: '',
    receiver: '', location: '', remark: '', lines: prBlankLines(5),
  };
  return d;
}
/** 常用字段记忆（localStorage，不写库）：客户/单位、部门、经办、电话、联系人等 */
const PR_MEM_KEYS = ['party', 'dept', 'handler', 'picker', 'phone', 'contact', 'receiver', 'dest', 'purpose', 'leader', 'location'];
function prMemLoad(kind) {
  try {
    const o = JSON.parse(localStorage.getItem('print_mem_' + kind) || '{}') || {};
    return o;
  } catch (e) { return {}; }
}
function prMemSave(kind, d) {
  try {
    const o = {};
    PR_MEM_KEYS.forEach(k => { if (d[k]) o[k] = d[k]; });
    localStorage.setItem('print_mem_' + kind, JSON.stringify(o));
  } catch (e) { }
}
function prApplyMem(kind, d) {
  const m = prMemLoad(kind);
  PR_MEM_KEYS.forEach(k => {
    if (!d[k] && m[k]) d[k] = m[k];
  });
  if (!d.handler) d.handler = (PIN.get() || {}).name || m.handler || '';
  return d;
}

function prFieldKeys(kind, tpl) {
  const fields = (tpl && tpl.fields) || {};
  const groups = (Pr.groups && Pr.groups[kind]) || PR_GROUPS[kind] || [];
  const ordered = [];
  const seen = new Set();
  groups.forEach(([, keys]) => keys.forEach(k => {
    if (fields[k] && !seen.has(k)) { ordered.push(k); seen.add(k); }
  }));
  Object.keys(fields).forEach(k => {
    if (k !== 'remark' && !seen.has(k)) { ordered.push(k); seen.add(k); }
  });
  return ordered;
}

Pages.print = async (el, arg) => {
  const want = (arg || 'out').split('?')[0];
  Pr.tab = ['out', 'in', 'lox', 'files'].includes(want) ? want : 'out';
  if (!Pr.draft || Pr.draft._kind !== Pr.tab) {
    if (Pr.tab === 'out' || Pr.tab === 'in') {
      Pr.draft = Object.assign(prApplyMem(Pr.tab, prDefaultDraft(Pr.tab)), { _kind: Pr.tab });
    }
  }
  let pack;
  try { pack = await api('/api/print/templates'); } catch (e) { fail(e); return; }
  Pr.tpl = pack.templates || {};
  Pr.groups = pack.field_groups || PR_GROUPS;
  el.innerHTML = UI.ph('打印', '出/入库单不入账 · 液氧表纸质对照 · 上传文件',
    '出库单/入库单与上传文件：只走浏览器打印，不写入出库/到货业务表，不改库存。液氧打印表：打印「报表 · 液氧表」纸质对照（与下载 Excel 一致），本次打印不改表数据；改数/登记到车请到报表。正式进库存请用「到货」；正式出库请用「出库」。',
    `<div class="seg" id="prTabs"><button data-t="out">出库单</button><button data-t="in">入库单</button><button data-t="lox">液氧表</button><button data-t="files">上传文件</button></div>`)
    + (Pr.tab === 'lox'
      ? `<div class="banner print-note" style="margin:0 0 10px">液氧打印表：打印「报表 · 液氧表」纸质对照（与下载 Excel 一致）。<b>本次打印不改表数据、不进到货/库存</b>；改数或登记到车请到「报表 · 液氧表」。出库单/入库单仍是不入账纸单。</div>`
      : `<div class="banner print-note" style="margin:0 0 10px">打印页说明：出库单/入库单 <b>不入账、不进库存</b>。纸单签字用；与「到货进库存 / 出库扣库存」无关。液氧表请切「液氧表」页签。</div>`)
    + `<div id="prBody"></div>`;
  $$('#prTabs button', el).forEach(b => {
    b.classList.toggle('on', b.dataset.t === Pr.tab);
    b.onclick = () => App.tab('print/' + b.dataset.t);
  });
  const body = $('#prBody', el);
  if (Pr.tab === 'files') await prFiles(body);
  else if (Pr.tab === 'lox') await prLox(body);
  else await prForm(body, Pr.tab);
};

/** 液氧打印表入口：复用报表 · 液氧表的 rPrintDlg / rPrint（与下载 Excel 一致）。不写业务库。 */
async function prLox(box) {
  box.innerHTML = `<div class="card page-card">
    <div class="sec-h"><h2>液氧打印表</h2><small>报表 · 液氧表的纸质对照</small></div>
    <p style="margin:8px 0 12px;line-height:1.55">用途：把「报表 · 液氧表」（到车、过磅、质检等列）打成纸表对照或存档。打印内容与报表里「打印 / 下载 Excel」一致（表头、合并格、列宽、本月自动合计）。</p>
    <div class="banner print-note" style="margin:0 0 14px;font-size:12.5px"><b>本次打印不改表数据</b>，也不进到货 / 库存及到货总数。出库单、入库单那两张才是「不入账」空白纸单；液氧表本身在报表里维护，改数请点下方「打开液氧表」。</div>
    <div class="row r2" style="gap:10px;margin-bottom:12px">
      <button class="btn pri big" id="prLoxPrint" style="flex:1">打印液氧表</button>
      <button class="btn big" id="prLoxOpen" style="flex:1">打开液氧表（改数 / 登记）</button>
    </div>
    <div class="hint">也可从顶栏「报表」→「液氧表」→ 右上「打印」。手机端请从「更多 → 液氧打印表」进本说明，正式改表请用电脑。</div>
  </div>`;
  $('#prLoxOpen', box).onclick = () => { location.hash = '#report/lox'; };
  $('#prLoxPrint', box).onclick = async () => {
    try {
      if (typeof rEnsure !== 'function' || typeof rPrintDlg !== 'function') {
        try { sessionStorage.setItem('printLox', '1'); } catch (e) { }
        location.hash = '#report/lox';
        return;
      }
      await rEnsure('lox');
      RP.k = 'lox';
      rPrintDlg('lox');
    } catch (e) { fail(e); }
  };
}

async function prForm(box, kind) {
  const tpl = Pr.tpl[kind] || {};
  const d = Pr.draft;
  const fields = tpl.fields || {};
  const cols = (tpl.line_cols || []).filter(c => c.show !== false);
  const showLines = tpl.show_lines !== false;
  const showRmk = tpl.show_remark_area !== false && (fields.remark || {}).show !== false;
  const groups = (Pr.groups && Pr.groups[kind]) || PR_GROUPS[kind] || [];

  const fld = (k, ph) => {
    const f = fields[k] || { label: k, show: true };
    if (f.show === false) return '';
    const typ = k === 'date' ? 'date' : 'text';
    return `<div class="fld"><span class="lab">${esc(f.label || k)}</span><input class="inp" data-f="${k}" type="${typ}" value="${esc(d[k] || '')}" placeholder="${esc(ph || '可不填')}"></div>`;
  };
  const phMap = kind === 'out'
    ? { party: '客户或单位名称', picker: '谁来取的', phone: '手机/座机', purpose: '领用/用途说明', dest: '送到哪里', leader: '哪个领导批的', dept: '哪个部门', contact: '对接人', out_no: '手写单号可空' }
    : { party: '哪里送来的 / 供货方', dept: '收货部门', receiver: '谁收的', phone: '手机/座机', location: '放哪货位/库区', contact: '来方对接人', in_no: '手写单号可空' };

  let secHtml = '';
  groups.forEach(([title, keys]) => {
    const cells = keys.map(k => fld(k, phMap[k] || '')).filter(Boolean);
    if (!cells.length) return;
    secHtml += `<div class="sec-h" style="margin-top:12px"><h2>${esc(title)}</h2><small class="muted">可不填</small></div>
      <div class="row r3">${cells.join('')}</div>`;
  });

  box.innerHTML = UI.entryShell(
    `<div class="sec-h"><h2>${esc(tpl.title || (kind === 'out' ? '出库单' : '入库单'))}</h2>
      <small class="muted">抬头：${esc(prCompany(tpl) || '（未设公司名，可在右侧改模板或「设置 → 打印抬头」）')}</small></div>
      ${secHtml}
      ${showLines ? `<div class="sec-h" style="margin-top:14px"><h2>产品行</h2><small>空行打印时仍占位，方便手写</small></div>
        <div class="tw"><table class="t" id="prLn" data-nosel><thead><tr>${cols.map(c => `<th>${esc(c.label)}</th>`).join('')}<th style="width:40px"></th></tr></thead>
        <tbody>${(d.lines || []).map((ln, i) => `<tr data-i="${i}">${cols.map(c => `<td><input class="inp sm" data-i="${i}" data-k="${c.key}" value="${esc(ln[c.key] || '')}"></td>`).join('')}
          <td><button class="link d" data-x="${i}">✕</button></td></tr>`).join('')}</tbody></table></div>
        <button class="btn sm" id="prAdd" style="margin-top:8px">＋ 加一行</button>` : ''}
      ${showRmk ? `<div style="margin-top:12px"><span class="lab">${esc((fields.remark || {}).label || '备注')}</span><textarea class="inp" data-f="remark" rows="2" style="width:100%;resize:vertical" placeholder="可不填">${esc(d.remark || '')}</textarea></div>` : ''}`,
    `<div class="card-h"><h2>本单操作</h2></div>
      <div class="banner print-note" style="margin:0 0 10px;font-size:12.5px">预览区 · <b>不入账、不进库存</b>，只出纸质单</div>
      <div class="pr-preview muted" id="prPrev" style="font-size:12.5px;line-height:1.55;margin-bottom:10px;padding:8px 10px;background:var(--fill);border-radius:8px;border:1px dashed var(--line2)">填写左侧后这里摘要</div>
      <button class="btn pri big full" id="prDo">打印</button>
      <button class="btn full" id="prEdit" style="margin-top:8px">改模板（抬头 / 字段）</button>
      <div class="hint" style="margin-top:12px">字段可不写全；常用客户/经办等会记在本机（localStorage，不写库）。打印用浏览器对话框。不写入出库/到货业务记录。</div>`
  );
  const side = $('.page-side', box) || $('.sticky .card', box);
  if (side) side.classList.add('page-act');

  const snap = () => {
    $$('[data-f]', box).forEach(i => { d[i.dataset.f] = i.value; });
    $$('[data-k]', box).forEach(i => {
      const ln = d.lines[+i.dataset.i]; if (!ln) return;
      ln[i.dataset.k] = i.value;
    });
  };
  const paintPrev = () => {
    const pv = $('#prPrev', box); if (!pv) return;
    const bits = [];
    const lab = (k) => ((fields[k] || {}).label || k);
    ['date', 'party', 'dept', 'picker', 'receiver', 'handler', 'dest', 'purpose'].forEach(k => {
      if (d[k] && (fields[k] || {}).show !== false) bits.push(`<div><span class="muted">${esc(lab(k))}</span> ${esc(d[k])}</div>`);
    });
    const nLn = (d.lines || []).filter(ln => ln.name || ln.qty).length;
    bits.push(`<div class="muted" style="margin-top:4px">产品行已填 ${nLn} 行 · 打印仍不入账</div>`);
    pv.innerHTML = bits.join('') || '填写左侧后这里摘要 · <b>不入账</b>';
  };
  box.addEventListener('input', e => {
    const t = e.target;
    if (t.dataset.f) d[t.dataset.f] = t.value;
    if (t.dataset.k) { const ln = d.lines[+t.dataset.i]; if (ln) ln[t.dataset.k] = t.value; }
    paintPrev();
  });
  $('#prAdd', box) && ($('#prAdd', box).onclick = () => { snap(); d.lines.push(prBlankLine()); prForm(box, kind); });
  box.onclick = e => {
    const x = e.target.closest('[data-x]');
    if (x) { snap(); d.lines.splice(+x.dataset.x, 1); if (!d.lines.length) d.lines.push(prBlankLine()); prForm(box, kind); }
  };
  $('#prDo', box).onclick = () => { snap(); prMemSave(kind, d); prPrint(kind, tpl, d); };
  $('#prEdit', box).onclick = () => prEditTpl(kind, tpl, () => App.tab('print/' + kind));
  paintPrev();
}

function prPrint(kind, tpl, d) {
  const co = prCompany(tpl);
  const fields = tpl.fields || {};
  const cols = (tpl.line_cols || []).filter(c => c.show !== false);
  const showLines = tpl.show_lines !== false;
  const rows = (d.lines || []).slice();
  while (rows.length < (tpl.blank_rows || 5)) rows.push(prBlankLine());
  const groups = (Pr.groups && Pr.groups[kind]) || PR_GROUPS[kind] || [];

  const cell = (k) => {
    const f = fields[k]; if (!f || f.show === false) return '';
    const v = d[k] == null ? '' : d[k];
    return `<td class="mk"><span class="mk-l">${esc(f.label)}</span><span class="mk-v">${esc(v)}</span></td>`;
  };

  let meta = '';
  groups.forEach(([, keys]) => {
    const cells = keys.map(cell).filter(Boolean);
    for (let i = 0; i < cells.length; i += 3) {
      const chunk = cells.slice(i, i + 3);
      while (chunk.length < 3) chunk.push('<td class="mk empty"></td>');
      meta += `<tr>${chunk.join('')}</tr>`;
    }
  });

  let html = `<style>
    .pr-sheet{width:100%}
    .pr-sheet .mk{border:1px solid #000;padding:5px 8px;vertical-align:top;width:33.33%;text-align:left}
    .pr-sheet .mk.empty{border-color:transparent}
    .pr-sheet .mk-l{display:block;font-size:9pt;color:#333;margin-bottom:2px}
    .pr-sheet .mk-v{display:block;min-height:1.2em;font-size:11pt}
    .pr-sheet .meta{border-collapse:collapse;width:100%;margin:6px 0 12px}
    .pr-sheet .sec-t{font-size:10pt;margin:10px 0 4px;font-weight:bold;border-bottom:1px solid #000;padding-bottom:2px;text-align:left}
    .pr-sheet .sign{margin-top:18px;display:flex;justify-content:space-between;gap:12px;font-size:11pt}
    .pr-sheet .sign span{flex:1;text-align:left;border-bottom:1px solid #000;padding:4px 0 2px;min-height:28px}
  </style><div class="pr-sheet">`;
  if (co) html += `<div class="co">${esc(co)}</div>`;
  html += `<div class="ttl">${esc(tpl.title || '')}</div>`;
  if (meta) html += `<table class="meta">${meta}</table>`;

  if (showLines && cols.length) {
    html += `<div class="sec-t">产品明细</div><table><thead><tr>${cols.map(c => `<th>${esc(c.label)}</th>`).join('')}</tr></thead><tbody>`;
    rows.forEach(ln => {
      html += `<tr>${cols.map(c => {
        const v = ln[c.key] == null ? '' : ln[c.key];
        const cls = (c.key === 'name' || c.key === 'spec') ? 'l' : '';
        return `<td class="${cls}">${esc(v)}</td>`;
      }).join('')}</tr>`;
    });
    html += `</tbody></table>`;
  }
  if (tpl.show_remark_area !== false && (fields.remark || {}).show !== false) {
    html += `<div class="post" style="margin-top:14px;text-align:left;min-height:40px;border:1px solid #000;padding:6px 8px"><b>${esc((fields.remark || {}).label || '备注')}：</b>${esc(d.remark || '')}</div>`;
  }
  if (tpl.show_sign_area !== false) {
    if (kind === 'out') {
      html += `<div class="sign"><span>取货人签字：</span><span>经办人：</span><span>日期：</span></div>`;
    } else {
      html += `<div class="sign"><span>送货人签字：</span><span>收货/经办：</span><span>日期：</span></div>`;
    }
  }
  html += `</div>`;
  printHtml(html, { font: '11pt', titleSize: '18pt', noCompany: true });
}

async function prEditTpl(kind, tpl, onDone) {
  const f = JSON.parse(JSON.stringify(tpl || {}));
  const fieldKeys = prFieldKeys(kind, f).concat(['remark']);
  const uniq = [];
  fieldKeys.forEach(k => { if (!uniq.includes(k) && (f.fields || {})[k]) uniq.push(k); });
  Object.keys(f.fields || {}).forEach(k => { if (!uniq.includes(k)) uniq.push(k); });

  const body = `<div class="sform" style="max-width:620px">
    <label>单据标题</label><div><input class="inp" id="ptTitle" value="${esc(f.title || '')}"></div>
    <label>抬头公司名</label><div><input class="inp" id="ptCo" value="${esc(f.company || '')}" placeholder="空 = 用「设置 → 打印抬头」"><span class="hint">只改这一张单的抬头</span></div>
    <label>字段（标签可改 · 勾选是否显示）</label><div id="ptFlds">${uniq.map(k => {
      const x = (f.fields || {})[k] || { label: k, show: true };
      return `<div style="display:flex;gap:8px;align-items:center;margin:4px 0"><label style="width:72px"><input type="checkbox" data-fs="${k}" ${x.show !== false ? 'checked' : ''}> 显示</label>
        <input class="inp sm" data-fl="${k}" value="${esc(x.label || '')}" style="flex:1"></div>`;
    }).join('')}</div>
    <label>产品行</label><div>
      <label><input type="checkbox" id="ptLines" ${f.show_lines !== false ? 'checked' : ''}> 显示产品行表</label>
      <div id="ptCols" style="margin-top:6px">${(f.line_cols || []).map(c => `<div style="display:flex;gap:8px;align-items:center;margin:4px 0"><label style="width:72px"><input type="checkbox" data-cs="${c.key}" ${c.show !== false ? 'checked' : ''}> 显示</label>
        <input class="inp sm" data-cl="${c.key}" value="${esc(c.label || '')}" style="flex:1"></div>`).join('')}</div>
      <div style="margin-top:6px"><span class="muted">空白行数</span> <input class="inp num sm" id="ptBlank" value="${esc(f.blank_rows || 5)}" style="width:64px"></div>
    </div>
    <label>备注 / 签字</label><div>
      <label style="margin-right:16px"><input type="checkbox" id="ptRmk" ${f.show_remark_area !== false ? 'checked' : ''}> 打印备注区</label>
      <label><input type="checkbox" id="ptSign" ${f.show_sign_area !== false ? 'checked' : ''}> 打印签字栏</label>
    </div>
  </div>`;
  const collect = ov => {
    const next = {
      title: ($('#ptTitle', ov) || {}).value || f.title,
      company: ($('#ptCo', ov) || {}).value || '',
      show_lines: !!( $('#ptLines', ov) && $('#ptLines', ov).checked ),
      show_remark_area: !!( $('#ptRmk', ov) && $('#ptRmk', ov).checked ),
      show_sign_area: !!( $('#ptSign', ov) && $('#ptSign', ov).checked ),
      blank_rows: +(($('#ptBlank', ov) || {}).value || 5),
      fields: {},
      line_cols: [],
    };
    uniq.forEach(k => {
      const lab = (($('[data-fl="' + k + '"]', ov) || {}).value) || k;
      const show = !!($('[data-fs="' + k + '"]', ov) && $('[data-fs="' + k + '"]', ov).checked);
      next.fields[k] = { label: lab, show };
    });
    (f.line_cols || []).forEach(c => {
      const lab = (($('[data-cl="' + c.key + '"]', ov) || {}).value) || c.label;
      const show = !!($('[data-cs="' + c.key + '"]', ov) && $('[data-cs="' + c.key + '"]', ov).checked);
      next.line_cols.push({ key: c.key, label: lab, show });
    });
    return next;
  };
  const act = await new Promise(resolve => {
    dialog('改模板 · ' + (kind === 'out' ? '出库单' : '入库单'), body, [
      { t: '取消', fn: () => resolve({ a: 'cancel' }) },
      { t: '恢复默认', fn: () => resolve({ a: 'reset' }) },
      { t: '保存', cls: 'pri', fn: (ov) => resolve({ a: 'save', next: collect(ov) }) },
    ], { wide: true, onClose: () => resolve({ a: 'cancel' }) });
  });
  if (!act || act.a === 'cancel') return;
  try {
    if (act.a === 'reset') {
      const cur = Object.assign({}, (S.boot.settings.print_templates || {}));
      delete cur[kind];
      await setSave({ print_templates: cur }, '打印单模板恢复默认');
      toast('已恢复默认');
    } else {
      const cur = Object.assign({}, (S.boot.settings.print_templates || {}));
      cur[kind] = act.next;
      await setSave({ print_templates: cur }, '打印单模板');
      toast('模板已保存');
    }
    if (onDone) onDone();
  } catch (e) { fail(e); }
}


async function prFiles(box) {
  box.innerHTML = `<div class="card page-card"><div class="tools"><div class="tg"><span class="muted">pdf / 图片 / xlsx / docx 等 · 存 data/print_files · 不碰业务库</span></div>
    <span class="sp"></span><div class="tg acts"><button class="btn sm pri" id="pfUp">上传文件</button></div></div>
    <div id="pfDrop" class="pr-drop muted">把文件拖到这里，或点「上传文件」</div>
    <div id="pfList" style="margin-top:12px"><div class="empty">加载中…</div></div></div>
    <input type="file" id="pfInp" multiple accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,.bmp,.xlsx,.xls,.docx,.doc,.csv,.txt,.rtf,image/*,application/pdf" style="display:none">`;
  const load = async () => {
    try {
      const r = await api('/api/print/files');
      Pr.files = r.items || [];
      const L = $('#pfList', box);
      if (!Pr.files.length) { L.innerHTML = '<div class="empty">没有记录 · 还没有上传文件</div>'; return; }
      L.innerHTML = `<div class="tw"><table class="t"><thead><tr><th>文件名</th><th>大小</th><th>上传</th><th>经办</th><th></th></tr></thead><tbody>
        ${Pr.files.map(f => `<tr><td class="l">${esc(f.name)}</td><td class="w">${prSize(f.size)}</td><td class="w">${fmtTs(f.uploaded_at)}</td><td>${esc(f.by || '')}</td>
          <td class="w"><a data-open="${esc(f.id)}">打开/打印</a> · <a class="link d" data-del="${esc(f.id)}">删除</a></td></tr>`).join('')}</tbody></table></div>`;
    } catch (e) { fail(e); }
  };
  const uploadFiles = async files => {
    if (!files || !files.length) return;
    try {
      const p = PIN.get() || await PIN.ask('上传打印文件');
      for (const file of files) {
        const data = await prReadFile(file);
        await api('/api/print/files/upload', { name: file.name, data, pin: p.pin });
      }
      toast('已上传 ' + files.length + ' 个');
      await load();
    } catch (e) { fail(e); }
  };
  $('#pfUp', box).onclick = () => $('#pfInp', box).click();
  $('#pfInp', box).onchange = e => { uploadFiles([...e.target.files]); e.target.value = ''; };
  const drop = $('#pfDrop', box);
  drop.ondragover = e => { e.preventDefault(); drop.classList.add('on'); };
  drop.ondragleave = () => drop.classList.remove('on');
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove('on'); uploadFiles([...e.dataTransfer.files]); };
  box.onclick = async e => {
    const t = e.target;
    if (t.dataset.open) {
      const f = Pr.files.find(x => x.id === t.dataset.open);
      if (!f) return;
      const url = '/print_files/' + encodeURIComponent(f.stored) + '?n=' + encodeURIComponent(f.name);
      if (/\.(png|jpe?g|gif|webp|bmp)$/i.test(f.name)) {
        const w = window.open(url, '_blank');
        if (w) setTimeout(() => { try { w.print(); } catch (err) { } }, 400);
      } else if (/\.pdf$/i.test(f.name)) {
        window.open(url, '_blank');
        toast('已打开 PDF，可在预览里打印');
      } else {
        window.open('/api/print/files/one?id=' + encodeURIComponent(f.id), '_blank');
        toast('已下载/打开；若本机装了对应软件即可打印');
      }
    }
    if (t.dataset.del) {
      if (!await confirmBox('删除「' + ((Pr.files.find(x => x.id === t.dataset.del) || {}).name || '') + '」？', '删除文件')) return;
      try {
        await save('/api/print/files/delete', { id: t.dataset.del }, '删除打印文件');
        toast('已删除'); await load();
      } catch (err) { fail(err); }
    }
  };
  await load();
}

function prSize(n) {
  n = +n || 0;
  if (n < 1024) return n + ' B';
  if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
  return (n / 1048576).toFixed(1) + ' MB';
}

function prReadFile(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = () => reject(new Error('读文件失败'));
    r.readAsDataURL(file);
  });
}
