/* 库房杂物：暂存 / 工程 / 未知，不计库存 */
'use strict';
const MI = { cat: '', st: '在库', q: '' };
Pages.misc = async el => {
  el.innerHTML = UI.ph('库房杂物', '拍照登记 · 不计库存', '别人放的、来路不明的、工程材料：拍照 + 暂用叫法 + 大概数量 + 位置。弄清后改名、标已取走或转正式入库。',
    `<button class="btn pri" id="miNew">＋ 登记一件</button>`)
    + `<div class="card page-card"><div class="tools"><div class="tg"><div class="seg" id="miC"><button data-c="">全部</button><button data-c="暂存">暂存</button><button data-c="工程">工程</button><button data-c="未知">未知</button></div>
      <div class="seg" id="miS"><button data-s="在库">在库</button><button data-s="已取走">已取走</button><button data-s="已转入库">已转入库</button><button data-s="">全部</button></div><input class="inp" id="miQ" placeholder="搜叫法、描述、位置、备注" value="${esc(MI.q)}" style="width:190px"></div>
      <span class="sp"></span><div class="tg acts"><button class="btn sm" id="miPrint">打印</button>${LC.btn('misc')}</div></div>
    <div id="miT"></div></div>`;
  $$('#miC button', el).forEach(b => { b.classList.toggle('on', b.dataset.c === MI.cat); b.onclick = () => { MI.cat = b.dataset.c; Pages.misc(el); }; });
  $$('#miS button', el).forEach(b => { b.classList.toggle('on', b.dataset.s === MI.st); b.onclick = () => { MI.st = b.dataset.s; Pages.misc(el); }; });
  $('#miNew', el).onclick = () => miEdit(null, () => Pages.misc(el));
  const r = await api('/api/misc?' + (MI.cat ? 'category=' + encodeURIComponent(MI.cat) + '&' : '') + (MI.st ? 'status=' + encodeURIComponent(MI.st) : '') + (MI.q ? '&q=' + encodeURIComponent(MI.q) : ''));
  let mt; $('#miQ', el).oninput = e => { clearTimeout(mt); const v = e.target.value; mt = setTimeout(() => { MI.q = v; Pages.misc(el).then(() => { const i = $('#miQ', el); i.focus(); i.setSelectionRange(v.length, v.length); }); }, 300); };
  $('#miT', el).innerHTML = r.items.length ? `<div class="tw"><table class="t" id="miTbl"><thead><tr><th style="width:70px">照片</th><th>暂用叫法 / 描述</th><th>类别</th><th>大概数量</th><th>位置</th><th>谁放的</th><th>日期</th><th>状态</th><th>备注</th><th></th></tr></thead><tbody>
    ${r.items.map(t => `<tr><td>${t.photos[0] ? `<img src="/photos/${esc(t.photos[0].path)}" style="width:56px;height:42px;object-fit:cover;border-radius:6px;cursor:zoom-in" onclick="bigImg(this.src)">` : ''}${t.photos.length > 1 ? `<span class="muted" style="font-size:12px"> +${t.photos.length - 1}</span>` : ''}</td>
      <td><b style="font-weight:500">${esc(t.name || '（未命名）')}</b>${t.descr ? '<br><span class="muted" style="font-size:12.5px">' + esc(t.descr) + '</span>' : ''}</td><td><span class="tag">${esc(t.category)}</span></td>
      <td>${esc(t.qty)}</td><td>${esc(t.location)}</td><td>${esc(t.placed_by)}</td><td class="w ${t.status === '在库' ? ageCls(t.date) : ''}">${esc(t.date)}</td>
      <td class="w">${t.status === '在库' ? '<span class="tag ac">在库</span>' : `<span class="tag">${esc(t.status)}</span> <span class="muted" style="font-size:12px">${esc(t.done_date)}</span>`}</td>
      ${rmkTd(rmkJoin(t.remark, t.result_note))}
      ${rowActs({ ph: [0], main: ['修改', `data-ed="${t.id}"`], menu: t.status === '在库' ? [['已取走', `data-tk="${t.id}"`], ['转正式入库', `data-cv="${t.id}"`], ['留痕', `data-hi="${t.id}"`]] : [['恢复在库', `data-bk="${t.id}"`], ['留痕', `data-hi="${t.id}"`]] })}</tr>`).join('')}</tbody></table></div><div class="hint">${r.items.length} 件 · 在库超过 30 天的日期标红 · 点「列」可隐藏列</div>` : '<div class="empty">没有记录</div>';
  if (r.items.length) LC.apply($('#miTbl', el), 'misc', [
    { k: 'ph', label: '照片', w: 70 }, { k: 'name', label: '暂用叫法 / 描述', w: 180, prod: 1 },
    { k: 'cat', label: '类别', w: 64 }, { k: 'qty', label: '大概数量', w: 80 },
    { k: 'loc', label: '位置', w: 88, wrap: 1 }, { k: 'by', label: '谁放的', w: 72, hide: 1 },
    { k: 'date', label: '日期', w: 88 }, { k: 'st', label: '状态', w: 88 },
    { k: 'rmk', label: '备注', w: 100, wrap: 1, hide: 1 }, { k: '_act', label: '操作', w: 110 }
  ]);
  if (typeof CellSel !== 'undefined') CellSel.on($('#miTbl', el));
  $('#miPrint', el).onclick = () => printHtml(`<div class="ttl">库房杂物（${esc(MI.cat || '全部')} · ${esc(MI.st || '全部')}）</div><table><tr><th>暂用叫法</th><th>描述</th><th>类别</th><th>数量</th><th>位置</th><th>谁放的</th><th>日期</th><th>状态</th><th>备注</th></tr>${r.items.map(t => `<tr><td class="l">${esc(t.name)}</td><td class="l">${esc(t.descr)}</td><td>${esc(t.category)}</td><td>${esc(t.qty)}</td><td>${esc(t.location)}</td><td>${esc(t.placed_by)}</td><td>${esc(t.date)}</td><td>${esc(t.status)}</td><td class="l">${esc(rmkJoin(t.remark, t.result_note))}</td></tr>`).join('')}</table>`, { font: '10.5pt' });
  $('#miT', el).onclick = async e => {
    const t = e.target; const it = id => r.items.find(x => x.id === +id); const re = () => Pages.misc(el);
    try {
      if (t.dataset.ed) miEdit(it(t.dataset.ed), re);
      if (t.dataset.hi) auditDlg('temp', +t.dataset.hi);
      if (t.dataset.tk) dialog('标记已取走', `<span class="lab">谁取走的 / 说明</span><input class="inp" id="tkN">`, [{ t: '取消' }, { t: '已取走', cls: 'pri', fn: async ov => { await save('/api/misc/action', { id: +t.dataset.tk, action: 'taken', note: $('#tkN', ov).value }, '标记已取走'); re(); } }]);
      if (t.dataset.bk) { await save('/api/misc/action', { id: +t.dataset.bk, action: 'back' }, '恢复在库'); re(); }
      if (t.dataset.cv) {
        const x = it(t.dataset.cv);
        const ov = dialog('转正式入库', `<div class="row r2"><div style="grid-column:1/3"><span class="lab">正式产品（选已有的，或写新名称）</span><input class="inp" id="cvP" value="${esc(x.name)}"></div>
          <div><span class="lab">规格</span><input class="inp" id="cvS"></div><div><span class="lab">单位</span><input class="inp" id="cvU" value="个"></div>
          <div><span class="lab">入库数量（点清后填）</span><input class="inp num" id="cvQ" inputmode="decimal"></div><div><span class="lab">U8</span><select class="inp" id="cvU8"><option>待入U8</option><option>不入U8</option><option>已入U8</option></select></div></div>
          <div class="hint">会记一笔「其他入库」到货。数量空着则只建产品，库存仍为未知，等盘点。</div>`,
          [{ t: '取消' }, { t: '转入库', cls: 'pri', fn: async ov => {
            await save('/api/misc/action', { id: x.id, action: 'convert', product_id: ov._pid || null, name: $('#cvP', ov).value, spec: $('#cvS', ov).value, unit: $('#cvU', ov).value, qty: $('#cvQ', ov).value, u8_status: $('#cvU8', ov).value }, '转正式入库');
            toast('已转入库'); await loadBoot(); re();
          } }]);
        const pi = $('#cvP', ov); autoComplete(pi, async q => P.search(q).slice(0, 10), p => { ov._pid = p.id; pi.value = p.label; $('#cvU', ov).value = p.unit; }, (p, q) => hl(p.label, q));
        pi.addEventListener('input', () => ov._pid = null);
      }
    } catch (er) { fail(er); }
  };
};
function miEdit(t, done) {
  t = t || { category: '未知', name: '', descr: '', qty: '', location: '', placed_by: '', date: today(), photos: [] };
  const ov = dialog(t.id ? '修改库房杂物' : '登记库房杂物', `<div style="margin-bottom:12px"><span class="lab">照片</span><div id="miPh"></div></div>
    <div class="row r2"><div><span class="lab">暂用叫法（如「灰色管件」）</span><input class="inp" id="mN" value="${esc(t.name)}"></div>
    <div><span class="lab">类别</span><div class="seg" id="mC">${['暂存', '工程', '未知'].map(c => `<button data-c="${c}" class="${t.category === c ? 'on' : ''}">${c}</button>`).join('')}</div></div>
    <div><span class="lab">大概数量</span><input class="inp" id="mQ" value="${esc(t.qty)}" placeholder="如：约 20 根"></div><div><span class="lab">存放位置</span><input class="inp" id="mL" value="${esc(t.location)}"></div>
    <div><span class="lab">谁放的</span><input class="inp" id="mP" value="${esc(t.placed_by)}"></div><div><span class="lab">日期</span><input class="inp" type="date" id="mD" value="${esc(t.date)}"></div>
    <div style="grid-column:1/3"><span class="lab">大概描述</span><input class="inp" id="mR" value="${esc(t.descr)}"></div>
    <div style="grid-column:1/3"><span class="lab">备注</span><input class="inp" id="mRk" value="${esc(t.remark || '')}" placeholder="可不填"></div></div>`,
    [{ t: '取消' }, { t: '保存', cls: 'pri', fn: async ov => {
      const d = { id: t.id, name: $('#mN', ov).value.trim(), category: ov._c || t.category, qty: $('#mQ', ov).value, location: $('#mL', ov).value, placed_by: $('#mP', ov).value, date: $('#mD', ov).value, descr: $('#mR', ov).value, remark: $('#mRk', ov).value.trim() };
      await save('/api/misc/save', { data: d, photo_ids: ph.ids }, '保存库房杂物'); toast('已保存'); done();
    } }], { wide: true, nofocus: true });
  const ph = photoBox($('#miPh', ov), t.photos);
  $('#mC', ov).onclick = e => { const b = e.target.closest('[data-c]'); if (!b) return; ov._c = b.dataset.c; $$('#mC button', ov).forEach(x => x.classList.toggle('on', x === b)); };
}
