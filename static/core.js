/* 库房出入库 · 前端公共部分（桌面端、手机端共用） */
'use strict';
const $ = (s, el) => (el || document).querySelector(s);
const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmtN = v => (v === null || v === undefined || v === '') ? '' : (Math.round(Number(v) * 1000) / 1000).toString();
const today = () => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
const md = d => d ? (+d.slice(5, 7)) + '月' + (+d.slice(8, 10)) + '日' : '';
const fmtTs = t => { if (!t) return ''; const d = new Date(t * 1000); return (d.getMonth() + 1) + '-' + d.getDate() + ' ' + String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'); };
const ageCls = d => { const a = (Date.now() - new Date(d + 'T00:00:00').getTime()) / 864e5; return a > 30 ? 'w30' : a > 7 ? 'w7' : ''; };
const S = { boot: null };

/* ========== 桌面页统一骨架（Phase A：4 壳，禁止再发明第五种） ==========
 * 1) Home     ：仅首页（KPI + 主路径四键 + 次要入口 + 最近）
 * 2) List     ：一切列表 / 日表 / 报表（.ph + .card.page-card > .tools + .tw|.r-grid|.pp-tw）
 * 3) Entry    ：一切录入（出库/到货/借用/称重/打印单：主表单 + 侧栏）
 * 4) Settings ：设置 / 备份（.setc 左菜单右内容）
 * 日表·报表 = List 变体（只换 tools 与表组件，不再独立 pp/r 宇宙）
 */
const UI = {
  /* 页头（全站统一压缩规格，与报表 1.1.16 同审美）：
   * 顶栏已显示页名 → 不渲染页内 H1；acts（页签/按钮）在左，短提示+「说明」在右同一行。
   * title 仅作 data-title / 无障碍备用，不占纵向空间。 */
  ph(title, sub, help, acts) {
    const h = help ? `<details class="ph-help"><summary></summary><div class="ph-help-b">${help}</div></details>` : '';
    const hint = (sub || help) ? `<span class="muted r-hint">${sub || ''}${h}</span>` : '';
    if (!acts && !hint) return '';
    return `<div class="ph ph-c" data-title="${esc(title)}">${acts ? `<div class="acts">${acts}</div>` : ''}<span class="sp"></span>${hint}</div>`;
  },
  /** 时序表（上旧下新）滚到最新一行；列表若已是新→旧则不要用 */
  scrollLatest(box) {
    if (!box) return;
    requestAnimationFrame(() => { box.scrollTop = box.scrollHeight; });
  },
  /** 工具栏一行：左筛(filters) · 弹性空位 · 右操作(acts)。两段都可空。 */
  tools(filters, acts) {
    const L = filters ? `<div class="tg">${filters}</div>` : '';
    const R = acts ? `<div class="tg acts">${acts}</div>` : '';
    return `<div class="tools">${L}<span class="sp"></span>${R}</div>`;
  },
  /** List 壳：单卡 + 工具栏槽 + 表体槽（id 给页面填） */
  listShell(toolsInner, bodyId, extraClass) {
    return `<div class="card page-card shell-list${extraClass ? ' ' + extraClass : ''}">${toolsInner || ''}<div class="tw" id="${esc(bodyId || 'listT')}"></div></div>`;
  },
  /** Entry 壳：左主卡(html) + 右侧栏(html) */
  entryShell(mainHtml, sideHtml) {
    return `<div class="grid2 page-entry shell-entry"><div class="card page-card">${mainHtml}</div><div class="sticky"><div class="card page-card page-side">${sideHtml}</div></div></div>`;
  },
  /* Phase A 别名：方案里的 UI.shell* */
  shellList(toolsInner, bodyId, extraClass) { return UI.listShell(toolsInner, bodyId, extraClass); },
  shellEntry(mainHtml, sideHtml) { return UI.entryShell(mainHtml, sideHtml); },
  shellHome(inner) { return `<div class="shell-home">${inner || ''}</div>`; },
};

/** 显示层：历史「自提出库」读作「客户自提」。只改展示，禁止 UPDATE 库。 */
function kindDisp(k) {
  if (!k) return '';
  if (k === '自提出库') return '客户自提';
  return k;
}
/** 流水/说明文案显示层：旧「自提出库」→「客户自提」。只读映射，禁止写库改历史单据/流水文案。 */
function moveLabelDisp(lab) {
  if (lab == null || lab === '') return '';
  const s = String(lab);
  if (s.indexOf('自提出库') < 0) return s;
  return s.split('自提出库').join('客户自提');
}

async function api(path, body, opt) {
  opt = opt || {};
  const init = { method: body === undefined ? 'GET' : 'POST', headers: {} };
  if (body !== undefined) {
    if (body instanceof Blob || body instanceof ArrayBuffer) { init.body = body; init.headers['Content-Type'] = 'application/octet-stream'; if (opt.pin) init.headers['X-PIN'] = opt.pin; }
    else { init.body = JSON.stringify(body); init.headers['Content-Type'] = 'application/json'; }
  }
  const r = await fetch(path, init);
  const ct = r.headers.get('Content-Type') || '';
  const j = ct.includes('json') ? await r.json() : null;
  if (!r.ok) { const e = new Error((j && j.error) || ('出错了 ' + r.status)); e.code = r.status; throw e; }
  return j;
}

/* ---------- 保存时输入 PIN（密码即身份） ---------- */
const PIN = {
  get() { try { const o = JSON.parse(sessionStorage.getItem('pin') || 'null'); if (o && Date.now() < o.exp) return o; } catch (e) { } return null; },
  set(pin, name) { const m = (S.boot && S.boot.settings.pin_cache_minutes) || 5; sessionStorage.setItem('pin', JSON.stringify({ pin, name, exp: Date.now() + m * 60000 })); },
  clear() { sessionStorage.removeItem('pin'); },
  ask(title) {
    return new Promise((resolve, reject) => {
      const phone = document.body.classList.contains('m');
      const ov = document.createElement('div'); ov.className = 'ov';
      if (phone) {
        ov.innerHTML = `<div class="pinpad"><div class="pp-t">${esc(title || '确认保存')}</div><h3>输入密码</h3><div class="pp-s">密码对应经办人，记录自动署名</div>
          <div class="pin-dots">${'<i></i>'.repeat(4)}</div><div class="pp-err"></div>
          <div class="pp-k">${[1, 2, 3, 4, 5, 6, 7, 8, 9].map(n => `<button data-k="${n}">${n}</button>`).join('')}<button data-k="x" class="t">取消</button><button data-k="0">0</button><button data-k="d" class="t">删除</button></div></div>`;
      } else {
        ov.innerHTML = `<div class="dlg" style="width:360px"><div class="dlg-h">${esc(title || '确认保存')}</div><div class="dlg-b">
          <div class="muted" style="font-size:13px">输入你的密码（密码即身份，记录自动署名）</div>
          <input class="inp pin-in" type="password" inputmode="numeric" autocomplete="off" maxlength="4" style="margin-top:12px">
          <div class="pp-err" style="color:var(--bad);font-size:13px;min-height:20px;margin-top:6px"></div></div>
          <div class="dlg-f"><button class="btn" data-x>取消</button><button class="btn pri" data-ok>确定</button></div></div>`;
      }
      document.body.appendChild(ov);
      let v = '';
      const done = async () => {
        try { const r = await api('/api/whoami', { pin: v }); PIN.set(v, r.name); ov.remove(); resolve({ pin: v, name: r.name }); }
        catch (e) { v = ''; draw(); const er = $('.pp-err', ov); er.textContent = e.message; const i = $('.pin-in', ov); if (i) { i.value = ''; i.focus(); } }
      };
      const draw = () => { $$('.pin-dots i', ov).forEach((d, i) => d.classList.toggle('on', i < v.length)); };
      if (phone) {
        ov.addEventListener('click', e => {
          const k = e.target.dataset.k; if (!k) return;
          if (k === 'x') { ov.remove(); reject(new Error('cancel')); return; }
          if (k === 'd') v = v.slice(0, -1); else if (v.length < 8) v += k;
          draw(); if (v.length === 4) setTimeout(done, 120);
        });
      } else {
        const i = $('.pin-in', ov); setTimeout(() => i.focus(), 30);
        i.addEventListener('keydown', e => { if (e.key === 'Enter') { v = i.value; done(); } if (e.key === 'Escape') { ov.remove(); reject(new Error('cancel')); } });
        $('[data-ok]', ov).onclick = () => { v = i.value; done(); };
        $('[data-x]', ov).onclick = () => { ov.remove(); reject(new Error('cancel')); };
      }
    });
  }
};
/** 需要身份的保存：先用缓存的密码，不对或过期就问 */
async function save(path, body, title) {
  let p = PIN.get();
  if (!p) p = await PIN.ask(title);
  try { return await api(path, Object.assign({}, body, { pin: p.pin })); }
  catch (e) {
    if (e.code === 401) { PIN.clear(); p = await PIN.ask(title); return await api(path, Object.assign({}, body, { pin: p.pin })); }
    throw e;
  }
}
async function saveRaw(path, blob, title) {
  let p = PIN.get(); if (!p) p = await PIN.ask(title);
  return api(path, blob, { pin: p.pin });
}
function toast(msg, err) {
  const t = document.createElement('div'); t.className = 'toast' + (err ? ' err' : ''); t.textContent = msg; document.body.appendChild(t);
  setTimeout(() => t.remove(), err ? 4200 : 2200);
}
/** 带「撤销」按钮的提示（8 秒） */
function toastUndo(msg, undo) {
  const t = document.createElement('div'); t.className = 'toast undo'; t.innerHTML = esc(msg) + ' <a>撤销</a>'; document.body.appendChild(t);
  const tm = setTimeout(() => t.remove(), 8000);
  $('a', t).onclick = async () => { clearTimeout(tm); t.remove(); try { await undo(); toast('已撤销'); } catch (e) { fail(e); } };
}
function fail(e) { if (e && e.message === 'cancel') return; console.error(e); toast(e.message || String(e), true); }

/* ---------- 弹窗 ---------- */
function dialog(title, bodyHtml, buttons, opt) {
  opt = opt || {};
  const ov = document.createElement('div'); ov.className = 'ov';
  ov.innerHTML = `<div class="dlg ${opt.wide ? 'wide' : ''}"><div class="dlg-h"><span>${esc(title)}</span><button class="link d" data-close>✕</button></div><div class="dlg-b">${bodyHtml}</div><div class="dlg-f"></div></div>`;
  const f = $('.dlg-f', ov);
  const close = () => { if (!ov.isConnected) return; if (typeof opt.onClose === 'function') try { opt.onClose(); } catch (e) { } ov.remove(); };
  (buttons || [{ t: '关闭' }]).forEach(b => {
    const el = document.createElement('button'); el.className = 'btn ' + (b.cls || ''); el.textContent = b.t;
    el.onclick = async () => { try { if (b.fn) { const r = await b.fn(ov); if (r === false) return; } ov.remove(); } catch (e) { fail(e); } };
    f.appendChild(el);
  });
  $('[data-close]', ov).onclick = close;
  // 点空白遮罩关闭（与 ✕ 同；点对话框本体不关）。opt.noBackdropClose 可关
  if (!opt.noBackdropClose) ov.addEventListener('mousedown', e => { if (e.target === ov) close(); });
  document.body.appendChild(ov);
  const fi = $('input,select,textarea', $('.dlg-b', ov)); if (fi && !opt.nofocus) setTimeout(() => fi.focus(), 30);
  return ov;
}
function confirmBox(msg, okText) {
  return new Promise(res => {
    let done = false; const finish = v => { if (done) return; done = true; res(v); };
    dialog('请确认', `<div style="padding:4px 0 8px">${msg}</div>`,
      [{ t: '取消', fn: () => finish(false) }, { t: okText || '确定', cls: 'pri', fn: () => finish(true) }],
      { onClose: () => finish(false) });
  });
}
/** 未保存离开：弹窗内「取消 / 不保存 / 保存」。返回 'cancel' | 'discard' | 'save' */
function dirtyLeave(msg, opt) {
  opt = opt || {};
  return new Promise(res => {
    let done = false; const finish = v => { if (done) return; done = true; res(v); };
    const btns = [
      { t: '取消', fn: () => finish('cancel') },
      { t: opt.discardText || '不保存', fn: () => finish('discard') },
    ];
    if (opt.noSave !== true) btns.push({ t: opt.saveText || '保存', cls: 'pri', fn: () => finish('save') });
    dialog(opt.title || '有改动没保存', `<div class="dlg-dirty">${msg}</div>`, btns, { onClose: () => finish('cancel'), noBackdropClose: true });
  });
}
/** 有改动时询问；选「保存」则调用 saveFn（或 App.guardSave）。返回是否继续（取消=false） */
async function confirmDirty(msg, saveFn, opt) {
  const act = await dirtyLeave(msg, opt);
  if (act === 'cancel') return false;
  if (act === 'save') {
    const fn = saveFn || (typeof App !== 'undefined' && App.guardSave);
    if (!fn) { toast('请先点页面上的「保存」', true); return false; }
    try { await fn(); } catch (e) { fail(e); return false; }
  } else if (typeof App !== 'undefined') {
    App.guard = null; App.guardSave = null;
  }
  return true;
}
/** 显示「照片库持续拍」二维码（约 30 天）；单据页 / 加附件弹窗共用 */
async function showLibQr(opt) {
  opt = opt || {};
  const ov = dialog(opt.title || '照片库 · 持续拍', '<div class="muted" id="libQrBody">生成中…</div>', [{ t: '关闭', cls: 'pri' }], { wide: true });
  const draw = async (force) => {
    const B = $('#libQrBody', ov); if (!B) return;
    B.innerHTML = '<div class="muted">生成中…</div>';
    try {
      const s = await api('/api/lib/session', Object.assign({ by: (PIN.get() || {}).name || '' }, force ? { force: 1 } : {}));
      const lan = ((S.boot && S.boot.lan) || [])[0] || location.origin, url = lan + '/m/lib.html#' + s.token;
      const left = s.left || s.ttl || 0;
      const days = left >= 86400 ? ('约 ' + Math.ceil(left / 86400) + ' 天') : (left ? (Math.ceil(left / 3600) + ' 小时') : '约 30 天');
      B.innerHTML = `<div class="pk-qr" style="margin:0;border:0;padding:0"><img src="/api/qr.svg?text=${encodeURIComponent(url)}" alt=""><div><b>扫一次，可持续上传 ${esc(days)}</b><div class="muted" style="margin-top:6px">手机和电脑同一 WiFi；传到共享库后，单据页点「照片库」选用即可（选用即完成，不用再点「完成」）。也可在「设置 → 手机与访客二维码」看这个码。</div><a class="link" id="libQrForce" style="display:inline-block;margin-top:8px">重新生成（旧码作废）</a></div></div>`;
      const a = $('#libQrForce', ov); if (a) a.onclick = () => draw(1);
    } catch (e) { B.innerHTML = '<div class="bad">' + esc(e.message) + '</div>'; }
  };
  await draw(0);
  return ov;
}
/** 看大图（全系统共用）：居中的浅色弹窗（约窗口 80%），原图；滚轮 / ＋− / 双击 放大缩小，放大后拖动看；‹ › 和 ← → 翻同一组的照片；可转 90°（点 ⟳ 立刻写入主机，不用另点保存）；Esc / ✕ 关。
 * list 不传：自动取点的那张所在照片组（.photos 等）里的所有图 */
function bigImg(src, list) {
  if (!list) {
    const el = window.event && window.event.target;
    // 全站看大图入口（桌面 / 手机 / 弹窗 / 列表缩略图）共用；组图容器尽量找全
    const box = el && el.tagName === 'IMG' && el.closest('.photos, .hp-grid, .pk-ph, .dlg-b, .rec, .iv-ov');
    const ims = box ? [...box.querySelectorAll('img')].filter(x => x.classList.contains('ph-i') || /bigImg/.test(x.getAttribute('onclick') || '') || /\/photos\//.test(x.getAttribute('src') || '')).map(x => x.getAttribute('src')) : [];
    list = ims.length > 1 ? ims : [src];
  }
  list = list.map(x => x);   // 可变副本：旋转保存后换带缓存戳的地址
  const abs = x => new URL(x, location.href).href;
  const base = u => { try { return abs(u).split('?')[0]; } catch (e) { return String(u || '').split('?')[0]; } };
  let i = list.findIndex(x => base(x) === base(src)); if (i < 0) i = 0;
  let z = 1, rot = 0, tx = 0, ty = 0, saving = false;
  const v = document.createElement('div'); v.className = 'iv-ov';
  v.innerHTML = `<div class="iv"><div class="iv-bar"><span class="iv-n"></span><span class="iv-b"><button data-z="-1" title="缩小">－</button><button data-z="0" class="iv-pc" title="恢复原样">100%</button><button data-z="1" title="放大">＋</button><button data-r title="转 90°（马上保存）">⟳</button><a class="iv-o" target="_blank" title="新窗口打开原图">原图</a><button data-c title="关闭（Esc）">✕</button></span></div>
    <div class="iv-st"><img draggable="false"><button class="iv-p" data-d="-1" title="上一张（←）">‹</button><button class="iv-x" data-d="1" title="下一张（→）">›</button></div></div>`;
  const img = $('img', v), st = $('.iv-st', v), btnR = $('[data-r]', v);
  const apply = () => { img.style.transform = `translate(${tx}px,${ty}px) scale(${z}) rotate(${rot}deg)`; $('.iv-pc', v).textContent = Math.round(z * 100) + '%'; st.classList.toggle('zoomed', z > 1); };
  const reset = () => { z = 1; tx = ty = 0; apply(); };
  const show = () => { img.src = list[i]; $('.iv-o', v).href = list[i]; rot = 0; reset(); $('.iv-n', v).textContent = list.length > 1 ? (i + 1) + ' / ' + list.length : ''; $$('[data-d]', v).forEach(b => b.hidden = list.length < 2); };
  const photoPath = u => { try { const p = new URL(u, location.href).pathname; const m = p.match(/\/photos\/(.+)$/); return m ? decodeURIComponent(m[1]) : ''; } catch (e) { return ''; } };
  const bumpThumbs = (oldSrc, newSrc) => {
    const oAbs = abs(oldSrc), base = oAbs.split('?')[0];
    document.querySelectorAll('img').forEach(im => {
      try { if (abs(im.src).split('?')[0] === base) im.src = newSrc; } catch (e) { }
    });
  };
  const saveRotate = async () => {
    if (saving) return;
    const path = photoPath(list[i]);
    if (!path) { toast('这张图不能旋转保存（不是库房照片）', true); rot = 0; apply(); return; }
    saving = true; btnR.disabled = true; btnR.title = '正在保存…';
    try {
      // 等原图解码完再画，避免 naturalWidth=0
      if (!img.complete || !img.naturalWidth) await new Promise((res, rej) => { img.onload = res; img.onerror = () => rej(new Error('图片打不开')); });
      const w = img.naturalWidth, h = img.naturalHeight;
      const c = document.createElement('canvas');
      if (rot % 180 === 0) { c.width = w; c.height = h; } else { c.width = h; c.height = w; }
      const g = c.getContext('2d'); g.translate(c.width / 2, c.height / 2); g.rotate(rot * Math.PI / 180); g.drawImage(img, -w / 2, -h / 2);
      const data = c.toDataURL('image/jpeg', 0.92);
      const who = (typeof PIN !== 'undefined' && PIN.get && PIN.get()) ? (PIN.get().name || '') : '';
      const r = await api('/api/photo/rotate', { path, data, by: who });
      const oldSrc = list[i];
      const newSrc = '/photos/' + r.path + '?t=' + Date.now();
      list[i] = newSrc; rot = 0; reset(); img.src = newSrc; $('.iv-o', v).href = newSrc;
      bumpThumbs(oldSrc, newSrc);
      toast('已旋转并保存');
    } catch (e) { fail(e); rot = 0; apply(); }
    finally { saving = false; btnR.disabled = false; btnR.title = '转 90°（马上保存）'; }
  };
  const zoom = (f, cx, cy) => {   // 以 (cx,cy)（相对显示区中心）为中心缩放
    const nz = Math.min(8, Math.max(1, z * f)); if (nz === z) return;
    if (cx !== undefined) { tx = cx - (cx - tx) * nz / z; ty = cy - (cy - ty) * nz / z; }
    z = nz; if (z === 1) tx = ty = 0; apply();
  };
  const rel = e => { const r = st.getBoundingClientRect(); return [e.clientX - r.left - r.width / 2, e.clientY - r.top - r.height / 2]; };
  st.addEventListener('wheel', e => { e.preventDefault(); const [x, y] = rel(e); zoom(e.deltaY < 0 ? 1.2 : 1 / 1.2, x, y); }, { passive: false });
  st.addEventListener('dblclick', e => { if (e.target.closest('button')) return; const [x, y] = rel(e); if (z > 1) reset(); else zoom(2.5, x, y); });
  const pts = new Map(); let last = null, pinch = null;
  st.addEventListener('pointerdown', e => { if (e.target.closest('button')) return; st.setPointerCapture(e.pointerId); pts.set(e.pointerId, [e.clientX, e.clientY]); last = [e.clientX, e.clientY]; if (pts.size === 2) { const [a, b] = [...pts.values()]; pinch = Math.hypot(a[0] - b[0], a[1] - b[1]); } });
  st.addEventListener('pointermove', e => {
    if (!pts.has(e.pointerId)) return; pts.set(e.pointerId, [e.clientX, e.clientY]);
    if (pts.size === 2 && pinch) { const [a, b] = [...pts.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]); zoom(d / pinch); pinch = d; return; }   // 手机：两指缩放
    if (z > 1 && last) { tx += e.clientX - last[0]; ty += e.clientY - last[1]; last = [e.clientX, e.clientY]; apply(); }
  });
  const up = e => { pts.delete(e.pointerId); if (pts.size < 2) pinch = null; last = pts.size ? [...pts.values()][0] : null; };
  st.addEventListener('pointerup', up); st.addEventListener('pointercancel', up);
  const go = d => { if (saving) return; i = (i + d + list.length) % list.length; show(); };
  const key = e => { if (e.key === 'ArrowLeft') go(-1); else if (e.key === 'ArrowRight') go(1); else if (e.key === 'Escape') close(); else if (e.key === '+' || e.key === '=') zoom(1.25); else if (e.key === '-') zoom(0.8); else return; e.preventDefault(); e.stopPropagation(); };
  const close = () => { if (saving) return toast('正在保存旋转，稍等', true); v.remove(); document.removeEventListener('keydown', key, true); };
  v.addEventListener('click', e => {
    const t = e.target.closest('button') || e.target;
    if (t === v || t.dataset.c !== undefined) return close();
    if (t.dataset.d) return go(+t.dataset.d);
    if (t.dataset.z !== undefined) return +t.dataset.z ? zoom(+t.dataset.z > 0 ? 1.25 : 0.8) : reset();
    if (t.dataset.r !== undefined) {
      if (saving) return;
      rot = (rot + 90) % 360; apply();
      saveRotate();   // 点一下就写入主机，不用另点保存、也不用等关窗
    }
  });
  document.addEventListener('keydown', key, true); show(); document.body.appendChild(v);
  return v;
}

/* ---------- 照片：压缩后上传，返回 id ---------- */
function compressImage(file, maxSide, q) {
  maxSide = maxSide || 2500; q = q || 0.85;   // 最长边 2500、JPEG 质量 0.85：手写的字放大还看得清，又不太占地方
  return new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => {
      const img = new Image();
      img.onload = () => {
        const s = Math.min(1, maxSide / Math.max(img.width, img.height));
        const c = document.createElement('canvas'); c.width = Math.round(img.width * s); c.height = Math.round(img.height * s);
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height); res(c.toDataURL('image/jpeg', q));
      };
      img.onerror = () => rej(new Error('图片打不开')); img.src = fr.result;
    };
    fr.readAsDataURL(file);
  });
}
async function uploadPhoto(file, extra) {
  const data = await compressImage(file);
  const who = (PIN.get() || {}).name || '';
  return api('/api/photo', Object.assign({ data, name: file.name, by: who }, extra || {}));
}
function pickFiles(accept, multiple, capture) {
  return new Promise(res => {
    const i = document.createElement('input'); i.type = 'file'; i.accept = accept || 'image/*'; if (multiple) i.multiple = true; if (capture) i.capture = 'environment';
    i.onchange = () => res(Array.from(i.files || [])); i.click();
  });
}
/** 加照片 / 附件的小弹窗（v1.1.1）：① Ctrl+V 粘贴截图 ② 选择文件（也可拖进来）③ 照片库（手机扫一次可持续传，电脑选用）④ 手机扫码拍照上传（只传到这一处）。
 * 照片一加进来就传到主机，缩略图马上出现，可以删掉刚加的；点「完成」返回 [{id,path,name}]，取消返回 []。
 * 照片库「选用并完成」会直接关掉弹窗（不必再点完成）。opt.lib / opt.phone 可一打开就进对应面板。
 * opt: {title, label（手机上显示传到哪）, extra（entity / entity_id / tag 等，跟 uploadPhoto 一样）, lib, phone} */
function photoPick(opt) {
  opt = opt || {}; const extra = opt.extra || {}, got = []; let tok = null, poll = null, tick = null, done = false, busy = 0;
  return new Promise(resolve => {
    const ov = dialog(opt.title || '添加照片', `<div class="pk" id="pk">
      <div class="pk-drop" id="pkDrop" tabindex="0"><b>Ctrl+V</b> 粘贴截图 / 复制的图片<span>也可以把图片拖到这里</span></div>
      <div class="pk-ways"><button class="btn" id="pkFile">选择文件</button><button class="btn" id="pkLib">照片库</button><button class="btn" id="pkPhone">手机拍照上传</button></div>
      <div class="pk-lib" id="pkLibBox" hidden></div>
      <div class="pk-qr" id="pkQr" hidden></div>
      <div class="photos pk-ph" id="pkPh"></div><div class="muted pk-msg" id="pkMsg"></div></div>`,
      [{ t: '取消', fn: () => { end(false); } }, { t: '完成', cls: 'pri', fn: () => { if (busy) { toast('还有照片在上传，稍等', true); return false; } end(true); } }], { nofocus: true });
    ov.classList.add('pk-ov'); const $o = s => $(s, ov);
    const msg = t => { $o('#pkMsg').textContent = t || ''; };
    const draw = () => { $o('#pkPh').innerHTML = got.map((p, i) => `<div class="ph-w"><img class="ph-i" src="/photos/${esc(p.path)}" data-big="${i}"><b data-rm="${i}" title="删掉这张">×</b></div>`).join('') + (busy ? `<div class="ph-w pk-busy">上传中…</div>` : ''); };
    const add = async files => {
      files = [...files].filter(f => /^image\//.test(f.type || '') || /\.(jpe?g|png|webp|gif|bmp|heic)$/i.test(f.name || ''));
      if (!files.length) return toast('没有图片（只能加图片）', true);
      for (const f of files) { busy++; draw(); try { const p = await uploadPhoto(f, extra); got.push({ id: p.id, path: p.path, name: f.name || '粘贴的图片' }); } catch (e) { fail(e); } busy--; draw(); }
      msg('已加 ' + got.length + ' 张');
    };
    const onPaste = e => { if (!document.body.contains(ov)) return; const fs = [...((e.clipboardData && e.clipboardData.items) || [])].filter(x => x.kind === 'file').map(x => x.getAsFile()).filter(Boolean); if (fs.length) { e.preventDefault(); add(fs); } };
    document.addEventListener('paste', onPaste);
    const dz = $o('.dlg');
    dz.addEventListener('dragover', e => { e.preventDefault(); $o('#pkDrop').classList.add('on'); });
    dz.addEventListener('dragleave', e => { if (e.target === $o('#pkDrop')) $o('#pkDrop').classList.remove('on'); });
    dz.addEventListener('drop', e => { e.preventDefault(); $o('#pkDrop').classList.remove('on'); if (e.dataTransfer.files.length) add(e.dataTransfer.files); });
    $o('#pkFile').onclick = async () => { const fs = await pickFiles('image/*', true); if (fs.length) add(fs); };
    $o('#pkPh').onclick = e => { const t = e.target; if (t.dataset.rm !== undefined) { got.splice(+t.dataset.rm, 1); draw(); msg(got.length ? '已加 ' + got.length + ' 张' : ''); } else if (t.dataset.big !== undefined) bigImg('/photos/' + got[+t.dataset.big].path, got.map(p => '/photos/' + p.path)); };
    const phone = async () => {
      const Q = $o('#pkQr'); Q.hidden = false; Q.innerHTML = '<div class="muted">正在生成二维码…</div>';
      if (tok) api('/api/upq/close', { t: tok, by: (PIN.get() || {}).name || '' }).catch(() => { });
      try { const r = await api('/api/upq/new', Object.assign({ label: opt.label || opt.title || '附件', by: (PIN.get() || {}).name || '' }, extra)); tok = r.token; var left = r.ttl; } catch (e) { Q.innerHTML = '<div class="bad">' + esc(e.message) + '</div>'; return; }
      const lan = ((S.boot && S.boot.lan) || [])[0] || location.origin, url = lan + '/m/up.html#' + tok;
      Q.innerHTML = `<img src="/api/qr.svg?text=${encodeURIComponent(url)}" alt=""><div><b>用手机扫码拍照</b><div class="muted">手机和电脑连同一个网络；拍完照片自动出现在下面</div><div class="muted" id="pkLeft"></div><a class="link" id="pkRe" hidden>重新生成</a></div>`;
      $o('#pkRe').onclick = phone;
      clearInterval(tick); tick = setInterval(() => { left--; const L = $o('#pkLeft'); if (!L) return clearInterval(tick); L.textContent = left > 0 ? Math.floor(left / 60) + ':' + String(left % 60).padStart(2, '0') + ' 内有效，只能往这里传照片' : '二维码已过期'; if (left <= 0) { $o('#pkRe').hidden = false; clearInterval(tick); } }, 1000);
      clearInterval(poll); const my = tok;
      poll = setInterval(async () => {
        if (!document.body.contains(ov)) return end(false);
        try {
          const r = await api('/api/upq/poll?t=' + encodeURIComponent(my)); let n = 0;
          r.items.forEach(p => { if (!got.find(x => x.id === p.id)) { got.push({ id: p.id, path: p.path, name: '手机拍照' }); n++; } });
          if (n) { draw(); msg('手机传来 ' + n + ' 张，共 ' + got.length + ' 张'); }
          if (r.state === 'done') { clearInterval(poll); toast('手机已传完，共 ' + got.length + ' 张'); ov.remove(); end(true); }
          if (r.state === 'expired') { clearInterval(poll); $o('#pkRe').hidden = false; }
        } catch (e) { }
      }, 1500);
    };
    const libPanel = async () => {
      const B = $o('#pkLibBox'); B.hidden = false; B.innerHTML = '<div class="muted">加载照片库…</div>';
      try {
        const r = await api('/api/lib/list');
        const items = r.items || [];
        const left = r.session ? r.session.left : 0;
        const days = left >= 86400 ? ('约 ' + Math.ceil(left / 86400) + ' 天') : (left ? (Math.ceil(left / 3600) + ' 小时') : '无');
        B.innerHTML = `<div class="pk-lib-hd"><b>照片库</b><span class="muted">点选后「选用并完成」· 会话 ${days}</span>
          <a class="link" id="pkLibQr">显示持续拍码</a><a class="link" id="pkLibRef">刷新</a></div>
          <div class="pk-lib-g" id="pkLibG">${items.length ? items.map(p => `<label class="pk-lib-i" data-id="${p.id}"><input type="checkbox" value="${p.id}"><img src="/photos/${esc(p.path)}" alt=""></label>`).join('') : '<div class="muted" style="padding:12px">库里还没有照片。点「显示持续拍码」用手机传，或到设置里扫照片库码。</div>'}</div>
          <div class="pk-lib-bar"><button class="btn sm" id="pkLibAll" ${items.length ? '' : 'disabled'}>全选</button><button class="btn sm pri" id="pkLibTake" disabled>选用并完成（0）</button></div>
          <div class="pk-qr" id="pkLibQrBox" hidden></div>`;
        const sync = () => { const n = B.querySelectorAll('input:checked').length; $o('#pkLibTake').disabled = !n; $o('#pkLibTake').textContent = '选用并完成（' + n + '）'; };
        B.onchange = sync;
        $o('#pkLibAll').onclick = () => { B.querySelectorAll('input[type=checkbox]').forEach(c => { c.checked = true; }); sync(); };
        $o('#pkLibRef').onclick = () => libPanel();
        $o('#pkLibTake').onclick = async () => {
          const ids = [...B.querySelectorAll('input:checked')].map(c => +c.value);
          if (!ids.length) return;
          if (busy) { toast('还有照片在上传，稍等', true); return; }
          try {
            const t = await api('/api/lib/take', { ids, by: (PIN.get() || {}).name || '' });
            (t.items || []).forEach(p => { if (!got.find(x => x.id === p.id)) got.push({ id: p.id, path: p.path, name: p.name || '照片库' }); });
            draw(); msg('已选用 ' + (t.n || 0) + ' 张');
            // 选用即完成：不再要求再点「完成」
            ov.remove(); end(true);
          } catch (e) { fail(e); }
        };
        $o('#pkLibQr').onclick = async () => {
          const Q = $o('#pkLibQrBox'); Q.hidden = false; Q.innerHTML = '<div class="muted">生成中…</div>';
          try {
            const s = await api('/api/lib/session', { by: (PIN.get() || {}).name || '' });
            const lan = ((S.boot && S.boot.lan) || [])[0] || location.origin, url = lan + '/m/lib.html#' + s.token;
            Q.innerHTML = `<img src="/api/qr.svg?text=${encodeURIComponent(url)}" alt=""><div><b>扫一次，可持续上传约 30 天</b><div class="muted">手机和电脑同一 WiFi；传到照片库，加附件时再选用。也可在「设置 → 手机与访客二维码」看这个码。</div><a class="link" id="pkLibNew">重新生成（旧码作废）</a></div>`;
            $o('#pkLibNew').onclick = async () => { await api('/api/lib/session', { by: (PIN.get() || {}).name || '', force: 1 }); $o('#pkLibQr').click(); };
          } catch (e) { Q.innerHTML = '<div class="bad">' + esc(e.message) + '</div>'; }
        };
      } catch (e) { B.innerHTML = '<div class="bad">' + esc(e.message) + '</div>'; }
    };
    $o('#pkLib').onclick = libPanel;
    $o('#pkPhone').onclick = phone;
    const end = ok => {
      if (done) return; done = true; clearInterval(poll); clearInterval(tick); document.removeEventListener('paste', onPaste);
      if (tok) api('/api/upq/close', { t: tok, by: (PIN.get() || {}).name || '' }).catch(() => { });
      resolve(ok ? got.slice() : []);
    };
    // 点右上角 ✕ / 被别的代码关掉：当取消
    new MutationObserver((m, o) => { if (!document.body.contains(ov)) { o.disconnect(); end(false); } }).observe(document.body, { childList: true });
    if (opt.phone) phone();
    else if (opt.lib) libPanel();
    setTimeout(() => $o('#pkDrop').focus(), 30);
  });
}
/** 照片区：photos=[{id,path}]，可加可删；返回控制对象。
 * 快捷：「＋」全功能弹窗；「照片库」直达选用（选用即完成）；「手机拍」本单扫码；「持续拍码」约 30 天共享库。 */
function photoBox(el, photos, opt) {
  opt = opt || {};
  const st = { photos: photos || [] };
  const draw = () => {
    const quick = opt.readonly ? '' : `<div class="ph-quick">
      <button type="button" class="btn sm" data-add title="粘贴 / 选文件 / 照片库 / 手机">＋ 添加</button>
      <button type="button" class="btn sm" data-lib title="从照片库多选，选用即完成">照片库</button>
      <button type="button" class="btn sm" data-phone title="只传到这一处">手机拍</button>
      <button type="button" class="btn sm" data-libqr title="扫一次可持续连拍约 30 天">持续拍码</button>
    </div>`;
    el.innerHTML = `<div class="photos">${st.photos.map((p, i) => `<div class="ph-w"><img class="ph-i" src="/photos/${esc(p.path)}" data-i="${i}">${opt.readonly ? '' : `<b data-del="${i}">×</b>`}</div>`).join('')}
      ${opt.readonly ? '' : `<div class="addph" data-add title="加照片：粘贴 / 选文件 / 照片库 / 手机拍照">+</div>`}</div>${quick}`;
  };
  const absorb = ps => {
    let n = 0;
    (ps || []).forEach(p => { if (!st.photos.find(x => x.id === p.id)) { st.photos.push({ id: p.id, path: p.path }); n++; } });
    if (n) { draw(); opt.onchange && opt.onchange(st.photos); }
    return n;
  };
  el.addEventListener('click', async e => {
    const t = e.target;
    if (t.dataset.i !== undefined) bigImg('/photos/' + st.photos[+t.dataset.i].path, st.photos.map(p => '/photos/' + p.path));
    if (t.dataset.del !== undefined) { st.photos.splice(+t.dataset.del, 1); draw(); opt.onchange && opt.onchange(st.photos); }
    if (t.closest('[data-add]')) {
      const ps = await photoPick({ title: opt.title || '添加照片', label: opt.label, extra: opt.extra });
      absorb(ps);
    }
    if (t.closest('[data-lib]')) {
      const ps = await photoPick({ title: opt.title || '照片库', label: opt.label, extra: opt.extra, lib: true });
      absorb(ps);
    }
    if (t.closest('[data-phone]')) {
      const ps = await photoPick({ title: opt.title || '手机拍照', label: opt.label, extra: opt.extra, phone: true });
      absorb(ps);
    }
    if (t.closest('[data-libqr]')) showLibQr({ title: '照片库 · 持续拍' }).catch(fail);
  });
  draw();
  return { get ids() { return st.photos.map(p => p.id); }, add(p) { if (!st.photos.find(x => x.id === p.id)) { st.photos.push(p); draw(); } }, set(ps) { st.photos = ps || []; draw(); }, get list() { return st.photos; } };
}

/* ---------- 产品 ---------- */
const P = {
  byId(id) { return (S.boot.products || []).find(p => p.id === id); },
  label(id) { const p = P.byId(id); return p ? p.label : ''; },
  search(q) {
    q = (q || '').trim().toLowerCase(); const ps = S.boot.products || [];
    if (!q) return ps.slice().sort((a, b) => b.uses - a.uses);
    return ps.filter(p => (p.label + ' ' + (p.u8_code || '')).toLowerCase().includes(q)).sort((a, b) => (a.label.indexOf(q) - b.label.indexOf(q)) || (b.uses - a.uses));
  },
  frequent(n) { return P.search('').filter(p => p.category !== '工程材料').slice(0, n || 10); }
};
/** 设置里的「常用默认值」 */
function defs() { return Object.assign({ session: '早上', out_kind: '客户自提', out_source: '', list_days: 0 }, (S.boot && S.boot.settings && S.boot.settings.defaults) || {}); }
/** 出库单笔/手机：先选单据来源再出类型芯片；按来源过滤可选类型（与 settings.out_kinds 求交，保序）。
 *  app手工单 → 客户自提、换货、其他出库
 *  U8单     → 销售出库、其他出库
 *  无单     → 厂内自用、其他出库
 *  其它自定义来源 → 全部类型。currentKind 不在集合里时仍带上，避免改旧单卡死。 */
function kindsForSource(source, allKinds, currentKind) {
  const all = allKinds || [];
  const map = {
    'app手工单': ['客户自提', '换货', '其他出库'],
    'U8单': ['销售出库', '其他出库'],
    '无单': ['厂内自用', '其他出库'],
  };
  const allow = source ? map[source] : null;
  let list = allow ? all.filter(k => allow.includes(k)) : all.slice();
  if (currentKind && !list.includes(currentKind) && all.includes(currentKind)) list = list.concat([currentKind]);
  return list;
}
function daysAgo(n) { const d = new Date(Date.now() - n * 864e5); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }
async function loadBoot() {
  S.boot = await api('/api/boot');
  if (typeof nmSet === 'function') try {
    // Sprint A：默认把菜单「产品出入库情况」显示成「日表」（可在名称设置里改；接口里存的仍是用户自定义部分）
    nmSet(Object.assign({ '产品出入库情况': '日表' }, S.boot.settings.ui_names || {}));
  } catch (e) { }
  return S.boot;
}

/** 输入框下拉建议 */
function autoComplete(input, source, onPick, render) {
  const wrap = input.parentElement; wrap.classList.add('ac');
  let box = null, items = [], idx = -1, tm = null;
  const close = () => { if (box) { box.remove(); box = null; } };
  const show = async () => {
    const q = input.value;
    items = await source(q); idx = -1;
    close(); if (!items.length || document.activeElement !== input) return;
    box = document.createElement('div'); box.className = 'drop';
    box.innerHTML = items.map((it, i) => `<div data-i="${i}">${render(it, q)}</div>`).join('');
    box.addEventListener('mousedown', e => { const d = e.target.closest('[data-i]'); if (d) { e.preventDefault(); onPick(items[+d.dataset.i]); close(); } });
    wrap.appendChild(box);
  };
  input.addEventListener('input', () => { clearTimeout(tm); tm = setTimeout(show, 120); });
  input.addEventListener('focus', () => { clearTimeout(tm); tm = setTimeout(show, 60); });
  input.addEventListener('blur', () => setTimeout(close, 120));
  input.addEventListener('keydown', e => {
    if (!box) return;
    const ds = $$('[data-i]', box);
    if (e.key === 'ArrowDown') { idx = Math.min(idx + 1, ds.length - 1); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { idx = Math.max(idx - 1, 0); e.preventDefault(); }
    else if (e.key === 'Enter' && idx >= 0) { e.preventDefault(); onPick(items[idx]); close(); return; }
    else if (e.key === 'Escape') { close(); return; }
    ds.forEach((d, i) => d.classList.toggle('on', i === idx));
  });
}
const hl = (s, q) => { s = esc(s); q = (q || '').trim(); if (!q) return s; const i = s.toLowerCase().indexOf(esc(q).toLowerCase()); return i < 0 ? s : s.slice(0, i) + '<b style="color:var(--ac)">' + s.slice(i, i + esc(q).length) + '</b>' + s.slice(i + esc(q).length); };
const custSource = async q => (await api('/api/customers?q=' + encodeURIComponent(q || ''))).items;

/* ---------- 库存显示：未知 / 数字 / 需复盘 ---------- */
/* ---------- 出库批次：已盘点才「不够接下一批」；未盘点不强制；禁止新扣成负 ---------- */
function batchIsTrusted(pid, batches, product) {
  const p = product || (typeof P !== 'undefined' && P.byId ? P.byId(pid) : null);
  if (p && p.stock && p.stock.known) return true;
  return (batches || []).some(b => b.counted);
}
/** 与后端 fifo_pick 同口径：只扣 remain>0；返回 {parts:[{batch_no,qty}], short} */
function batchPlanSplit(batches, qty, prefer, nextPrefer) {
  qty = +qty || 0;
  const bs = (batches || []).filter(b => b && b.batch_no);
  const by = {}; bs.forEach(b => { by[b.batch_no] = b; });
  const ordered = []; const seen = new Set();
  const push = bn => {
    bn = (bn || '').trim();
    if (!bn || seen.has(bn)) return;
    const b = by[bn]; if (!b) return;
    if (!(+b.remain > 0)) return;
    ordered.push(b); seen.add(bn);
  };
  push(prefer); push(nextPrefer);
  bs.forEach(b => push(b.batch_no));
  const parts = []; let left = qty;
  ordered.forEach(b => {
    if (left <= 0) return;
    const take = Math.min(+b.remain, left);
    if (parts.length && parts[parts.length - 1].batch_no === b.batch_no) parts[parts.length - 1].qty = +(parts[parts.length - 1].qty + take).toFixed(3);
    else parts.push({ batch_no: b.batch_no, qty: take });
    left = +(left - take).toFixed(3);
  });
  return { parts, short: left > 0 ? left : 0 };
}
/** 弹窗：本批不够 → 选下一批并拆行。取消返回 null */
function askBatchOverflow(p, prefer, qty, batches) {
  return new Promise(res => {
    const plan0 = batchPlanSplit(batches, qty, prefer, '');
    if (plan0.short > 0 && !plan0.parts.length) {
      toast('「' + (p.label || p.name) + '」没有正剩余批次可扣（还差 ' + fmtN(plan0.short) + '）。负批不计入，请先到货/盘点或减少数量。', true);
      res(null); return;
    }
    const first = plan0.parts[0] || { batch_no: prefer || '', qty: 0 };
    const rest = +((qty - first.qty) || 0).toFixed(3);
    const others = (batches || []).filter(b => +b.remain > 0 && b.batch_no !== first.batch_no);
    const fifoNext = others[0] ? others[0].batch_no : '';
    const negTip = prefer && !(batches || []).some(b => b.batch_no === prefer && +b.remain > 0)
      ? `<div class="banner" style="margin-bottom:8px">所选批「${esc(prefer)}」已无正剩余（可能是以前扣穿的负批），不会再往这批扣。</div>` : '';
    const body = `${negTip}<p>「${esc(p.label || p.name)}」要出 <b>${fmtN(qty)}</b>：先扣 <b>${esc(first.batch_no || '（先进先出）')}</b> × ${fmtN(first.qty)}，还差 <b>${fmtN(rest)}</b>。</p>
      <div class="fld"><span class="lab">下一批优先用哪个</span>
        <select class="inp" id="nbNext"><option value="">先进先出（自动）</option>
        ${others.map(b => `<option value="${esc(b.batch_no)}" ${b.batch_no === fifoNext ? 'selected' : ''}>${esc(b.batch_no)} · 剩${fmtN(b.remain)}${b.expiry ? ' · 效期' + esc(b.expiry) : ''}</option>`).join('')}
        </select></div>
      <div class="muted" style="margin-top:8px" id="nbPreview"></div>
      <div class="muted" style="margin-top:6px;font-size:12.5px">已盘点产品不会新扣成负；历史负批不自动抹平。</div>`;
    const ov = dialog('批次不够 · 接下一批', body, [
      { t: '取消', fn: () => { res(null); } },
      { t: '按此拆行', cls: 'pri', fn: dlg => {
        const next = ($('#nbNext', dlg) || {}).value || '';
        const plan = batchPlanSplit(batches, qty, prefer || first.batch_no, next);
        if (plan.short > 0) { toast('正剩余仍不够，还差 ' + fmtN(plan.short), true); return false; }
        res(plan.parts);
      } }
    ], { onClose: () => res(null), noBackdropClose: true });
    const upd = () => {
      const next = ($('#nbNext', ov) || {}).value || '';
      const plan = batchPlanSplit(batches, qty, prefer || first.batch_no, next);
      const el = $('#nbPreview', ov); if (!el) return;
      el.textContent = plan.parts.map(x => x.batch_no + '×' + fmtN(x.qty)).join(' + ') + (plan.short ? '（还差 ' + fmtN(plan.short) + '）' : '');
    };
    const sel = $('#nbNext', ov); if (sel) sel.onchange = upd; upd();
  });
}
/** 出库明细：已盘点且本批不够 → 弹窗拆行；未盘点原样。返回新 items 或抛 cancel */
async function resolveOutBatchItems(items, batchesByPid) {
  const out = [];
  for (const it of items) {
    const side = (it.side || 'out') === 'in' ? 'in' : 'out';
    const q = +it.qty || 0;
    if (q <= 0) continue;
    const p = it.product_id && typeof P !== 'undefined' ? P.byId(it.product_id) : null;
    const bs = (p && batchesByPid && batchesByPid[p.id]) || [];
    if (!p || !p.batch_managed || side !== 'out') { out.push(Object.assign({}, it)); continue; }
    if (!batchIsTrusted(p.id, bs, p)) { out.push(Object.assign({}, it)); continue; }
    const prefer = (it.batch_no || '').trim();
    const plan = batchPlanSplit(bs, q, prefer, (it.next_batch_no || '').trim());
    if (plan.short > 0 && plan.parts.length === 0) {
      toast('「' + p.label + '」没有正剩余可扣，还差 ' + fmtN(plan.short) + '（负批不计入）', true);
      throw new Error('cancel');
    }
    // 已选批且只需一批、且就是该批 → 不弹
    if (plan.parts.length <= 1 && (!prefer || (plan.parts[0] && plan.parts[0].batch_no === prefer))) {
      if (plan.short > 0) {
        toast('「' + p.label + '」正剩余不够，还差 ' + fmtN(plan.short), true);
        throw new Error('cancel');
      }
      out.push(Object.assign({}, it)); continue;
    }
    // 空批号且 FIFO 自动多批：直接拆行（不弹），与「先进先出（自动）」一致
    if (!prefer && plan.short === 0 && plan.parts.length >= 1) {
      plan.parts.forEach(part => out.push(Object.assign({}, it, { qty: part.qty, batch_no: part.batch_no, next_batch_no: '' })));
      continue;
    }
    // 手选批不够 / 所选批已无正剩余 → 弹窗选下一批
    const parts = await askBatchOverflow(p, prefer, q, bs);
    if (!parts) throw new Error('cancel');
    parts.forEach(part => out.push(Object.assign({}, it, { qty: part.qty, batch_no: part.batch_no, next_batch_no: '' })));
  }
  return out;
}

function stockHtml(st, unit) {
  if (!st || !st.known) return '<span class="unk">未知</span>';
  if (st.qty < 0) return `<span class="tag bad" title="系统算出 ${fmtN(st.qty)}，请复盘">需复盘</span>`;
  return `<b class="num">${fmtN(st.qty)}</b>`;
}
function download(url) { const a = document.createElement('a'); a.href = url; a.download = ''; document.body.appendChild(a); a.click(); a.remove(); }
/** 打印：把与下载格式一致的 HTML 放进打印区再打印。
 *  @page margin:0 + 内容 padding，避免浏览器自带页眉（时间 + 网页标题「库房出入库」）和页脚 URL。
 *  打印时临时清空 document.title；不另画顶条。设置里的「打印人/时间」仍在页底 .pf（可关）。 */
function printHtml(html, opt) {
  opt = opt || {};
  const mg = opt.margin || '10mm';
  let h = $('.print-host'); if (!h) { h = document.createElement('div'); h.className = 'print-host'; document.body.appendChild(h); }
  h.innerHTML = `<style>@page{size:${opt.landscape ? 'A4 landscape' : 'A4'};margin:0}
    .print-host{font-family:"宋体",SimSun,"Songti SC",serif;color:#000;padding:${mg};box-sizing:border-box}
    .print-host table{border-collapse:collapse;width:100%;font-size:${opt.font || '11pt'}}
    .print-host th,.print-host td{border:1px solid #000;padding:${opt.dense ? "0 2px" : "2px 4px"};text-align:center;line-height:${opt.dense ? "1.15" : "1.3"}}
    .print-host .ttl{font-size:${opt.titleSize || '18pt'};text-align:center;margin-bottom:6px}
    .print-host td.l{text-align:left}.print-host .pre{margin:2px 0 4px}.print-host .post{margin-top:22px}
    .print-host .co{text-align:center;font-size:12pt;margin-bottom:2px}.print-host .pf{margin-top:8px;font-size:9pt;text-align:right}</style>` + html;
  const ps = (S.boot && S.boot.settings && S.boot.settings.print) || {};
  if (ps.company && !opt.noCompany) $$('.ttl', h).forEach(t => t.insertAdjacentHTML('beforebegin', `<div class="co">${esc(ps.company)}</div>`));
  if (ps.footer !== false && !opt.noFooter) {
    const p = (typeof PIN !== 'undefined' && PIN.get && PIN.get()) || null, d = new Date(), pad = x => String(x).padStart(2, '0');
    const f = `<div class="pf">${p ? '打印人：' + esc(p.name) + '　' : ''}打印时间：${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}</div>`;
    $$('div[style*="page-break-after"]', h).forEach(b => b.insertAdjacentHTML('beforebegin', f)); h.insertAdjacentHTML('beforeend', f);
  }
  if (opt.fit) printFit(h, opt);   // 整张缩到一页 A4（横向时 297×210mm）
  document.body.classList.add('printing');
  if (opt.preview) return h;        // 只排版不弹打印（截图 / 预览用）
  const prevTitle = document.title;
  document.title = '\u00a0';
  const done = () => { document.title = prevTitle; document.body.classList.remove('printing'); };
  const onAfter = () => { window.removeEventListener('afterprint', onAfter); done(); };
  window.addEventListener('afterprint', onAfter);
  setTimeout(() => { window.print(); setTimeout(done, 1500); }, 60);
}
/** 缩放到一页：按 A4（横向 297×210mm）减页边距算可打印区域，内容超出就整体缩小（zoom），不分页 */
function printFit(h, opt) {
  const mm = 96 / 25.4, mg = parseFloat(opt.margin || '10mm') || 10;
  const W = ((opt.landscape ? 297 : 210) - 2 * mg) * mm - 2, H = ((opt.landscape ? 210 : 297) - 2 * mg) * mm - 2;
  const body = document.createElement('div'); body.className = 'pfit';
  [...h.childNodes].filter(n => n.nodeName !== 'STYLE').forEach(n => body.appendChild(n)); h.appendChild(body);
  const st = h.getAttribute('style') || '';
  h.setAttribute('style', `display:block;position:absolute;left:-30000px;top:0;width:${W}px`);
  body.style.width = W + 'px';
  let sw = body.scrollWidth, sh = body.scrollHeight;
  let z = Math.min(1, W / sw, H / sh);
  if (z < 1) { body.style.width = (W / z) + 'px'; sw = body.scrollWidth; sh = body.scrollHeight; z = Math.min(1, W / sw, H / sh); body.style.width = (W / z) + 'px'; }
  body.style.zoom = z; h.setAttribute('style', st); h.dataset.zoom = z.toFixed(3);
}
/** 打印服务器给的表（与「导出 Excel」同一份数据、同样的标题/表头/列序） */
async function printApi(url, opt) {
  const r = await api(url + (url.includes('?') ? '&' : '?') + 'fmt=json');
  printHtml(r.sheets.map(s => `<div class="ttl">${esc(s.title || s.name)}</div>${(s.pre || []).map(l => `<div class="pre">${esc(l)}</div>`).join('')}<table><tr>${s.header.map(h => `<th>${esc(h)}</th>`).join('')}</tr>${s.rows.map(rw => `<tr>${rw.map(v => `<td class="${typeof v === 'number' ? '' : 'l'}">${esc(v == null ? '' : (typeof v === 'number' ? fmtN(v) : v))}</td>`).join('')}</tr>`).join('')}</table>${(s.post || []).map(l => `<div class="post">${esc(l)}</div>`).join('')}`).join('<div style="page-break-after:always"></div>'), Object.assign({ font: '10pt' }, opt || {}));
}

/* 备注：表格里单独一列，最多两行，超出省略，悬停看全文（点一下弹出全文）；手机列表里一行灰字 */
function rmkTd(s) { s = (s || '').trim(); return s ? `<td class="rmk"><div class="rmk-t" title="${esc(s)}">${esc(s)}</div></td>` : '<td class="rmk"></td>'; }
function rmkLine(s) { s = (s || '').trim(); return s ? `<small class="rmk-m">备注：${esc(s)}</small>` : ''; }
function rmkJoin(...xs) { return xs.flat().map(x => (x || '').trim()).filter(Boolean).filter((x, i, a) => a.indexOf(x) === i).join('；'); }
document.addEventListener('click', e => {
  const t = e.target.closest && e.target.closest('.rmk-t'); if (!t || t.scrollHeight <= t.clientHeight + 1) return;
  dialog('备注', `<div style="white-space:pre-wrap;line-height:1.7">${esc(t.title)}</div>`, null);
});

/* 操作列（所有列表统一）：照片图标槽（有照片显示图标+张数，没有留空）| 一个主操作 | 「⋯」菜单放其余操作。列宽固定，各行对齐 */
const PH_ICO = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h3l2-2.5h6L17 8h3v11H4z"/><circle cx="12" cy="13" r="3.5"/></svg>';
// o = { ph: [张数, 'data-ph="1"'], main: [文字, 属性] 或 null, menu: [[文字, 属性, 'd'(危险)], ...] }
function rowActs(o) {
  const ph = o.ph && o.ph[0] ? `<a class="ra-ph" ${o.ph[1]} title="看照片">${PH_ICO}<i>${o.ph[0]}</i></a>` : '';
  const mn = o.main ? `<a class="ra-main" ${o.main[1]}>${esc(o.main[0])}</a>` : '';
  const items = (o.menu || []).filter(Boolean);
  const more = items.length ? `<span class="ra-more"><button class="ra-dots" type="button" title="更多">⋯</button><span class="ra-menu">${items.map(([t, a, d]) => `<a ${a} class="${d ? 'd' : ''}">${esc(t)}</a>`).join('')}</span></span>` : '';
  return `<td class="ra"><div class="ra-row"><span class="ra-s1">${ph}</span><span class="ra-s2">${mn}</span><span class="ra-s3">${more}</span></div></td>`;
}
/* 「⋯」菜单：fixed 定位（不被表格滚动区裁掉）；打开时把它外面会「另起一层」的格子（如固定在右边的操作列）临时提到最上层，
   不会被下一行盖住；靠近底部时往上弹；点别处 / 滚动 / 改窗口大小 / Esc / 换页关闭 */
function raClose() {
  document.querySelectorAll('.ra-more.on').forEach(o => o.classList.remove('on'));
  document.querySelectorAll('tr.lc-front').forEach(tr => tr.classList.remove('lc-front'));
  document.querySelectorAll('[data-ra-z]').forEach(el => { el.style.zIndex = el.dataset.raZ === '-' ? '' : el.dataset.raZ; delete el.dataset.raZ; });
  document.querySelectorAll('.ra-menu.up').forEach(mu => mu.classList.remove('up'));
}
function raOpen(m, b) {
  raClose();
  const mu = m.querySelector('.ra-menu'); if (!mu) return;
  m.classList.add('on');
  const tr = m.closest('tr'); if (tr) tr.classList.add('lc-front');
  for (let el = m.parentElement; el && el !== document.body; el = el.parentElement) {
    const cs = getComputedStyle(el);
    if (cs.position !== 'static' && cs.zIndex !== 'auto') { el.dataset.raZ = el.style.zIndex || '-'; el.style.zIndex = '1000'; }
  }
  const r = b.getBoundingClientRect(), h = mu.offsetHeight, w = mu.offsetWidth; raOpen.at = [b, r.top, r.left];
  let top = r.bottom + 4; if (top + h > innerHeight - 8 && r.top - h - 4 >= 8) { top = r.top - h - 4; mu.classList.add('up'); }
  mu.style.top = Math.max(8, Math.min(top, innerHeight - h - 8)) + 'px'; mu.style.left = Math.max(8, Math.min(r.right - w, innerWidth - w - 8)) + 'px';
}
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('.ra-dots');
  if (!b) { if (document.querySelector('.ra-more.on')) setTimeout(raClose, 0); return; }   // 点了菜单里的项：先让原来的处理跑完再关
  const m = b.parentNode; if (m.classList.contains('on')) raClose(); else raOpen(m, b);
}, true);
document.addEventListener('scroll', e => {   // 真的滚动了（按钮位置变了）才关；点按钮时浏览器自己微调的滚动不算
  if (!document.querySelector('.ra-more.on') || (e.target.closest && e.target.closest('.ra-menu'))) return;
  const [b, t, l] = raOpen.at || []; const r = b && b.getBoundingClientRect();
  if (!r || Math.abs(r.top - t) > 2 || Math.abs(r.left - l) > 2) raClose();
}, true);
window.addEventListener('resize', raClose);
document.addEventListener('keydown', e => { if (e.key === 'Escape') raClose(); });
window.addEventListener('hashchange', raClose);
async function auditDlg(entity, id) {
  const r = await api('/api/audit?entity=' + entity + '&id=' + id);
  dialog('留痕', r.items.length ? `<table class="t"><thead><tr><th>时间</th><th>谁</th><th>操作</th><th>内容</th></tr></thead><tbody>${r.items.map(a => `<tr><td class="w">${fmtTs(a.ts)}</td><td class="w">${esc(a.person)}</td><td class="w">${esc(a.action)}</td><td>${esc(a.summary)}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">没有记录</div>', null, { wide: true });
}

/* ---------- 删除前：列出会影响什么，确认 + 密码 ---------- */
async function confirmDelete(entity, id, path, title, extra) {
  let im; try { im = await api('/api/impact?entity=' + entity + '&id=' + id); } catch (e) { im = { title: title || '', effects: [], links: [] }; }
  if (im.block) {
    dialog('不能在这里删除', `<div>${esc(im.block)}</div>${(im.links || []).map(l => `<div style="margin-top:8px"><a class="link" data-go="${esc(l.entity)}:${l.id}">${esc(l.label)} ↗</a></div>`).join('')}`, [{ t: '知道了' }]);
    const ov = $$('.ov').pop(); if (ov) ov.addEventListener('click', e => { const a = e.target.closest('[data-go]'); if (a) { ov.remove(); const [en, i] = a.dataset.go.split(':'); openRecord(en, +i); } });
    return false;
  }
  const eff = (im.effects || []).concat(extra || []);
  const ok = await new Promise(res => {
    let done = false; const finish = v => { if (done) return; done = true; res(v); };
    const ov = dialog('确认删除', `<div>删除：<b>${esc(im.title || title || '')}</b></div>
    ${eff.length ? `<div class="banner" style="margin-top:8px">会影响：<ul style="margin:6px 0 0 18px">${eff.map(x => '<li>' + esc(x) + '</li>').join('')}</ul></div>` : '<div class="muted" style="margin-top:8px">没有其他记录依赖它。</div>'}
    <div class="muted" style="margin-top:8px">删除后所有相关数字自动重算；可在「数据备份 → 回收站」恢复（恢复后也会自动重算、接回关联）。</div>
    <label style="display:block;margin-top:10px"><input type="checkbox" id="cdOk"> 我已看过上面的影响，确定删除</label>`,
      [{ t: '取消', fn: () => finish(false) }, { t: '删除', cls: 'danger', fn: dlg => { if (!$('#cdOk', dlg).checked) { toast('请先勾选「确定删除」', true); return false; } finish(true); } }]);
    // 点 ✕ 也要结束 Promise，否则外层「删除」会一直挂着（产品编辑弹窗里尤其明显）
    const x = $('[data-close]', ov); if (x) x.onclick = () => { ov.remove(); finish(false); };
  });
  if (!ok) return false;
  await save(path, { id }, '删除' + (im.title || title || ''));
  return true;
}

/* ---------- 记录查看：从库存流水 / 报表数字点进去看原始记录 ---------- */
const SRC_CN = { out: '出库单', arrival: '到货', daily: '产品出入库情况', loan: '借用单', count: '盘点', paper: '交接表', slip: '称重单' };
async function recView(entity, id) {
  const r = await api('/api/record?entity=' + entity + '&id=' + id);
  const kv = r.fields.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
  const it = r.items.length ? `<table class="t" style="margin-top:8px"><thead><tr><th>物品</th><th class="n">数量</th><th>批号</th>${entity === 'loan' ? '<th class="n">已还</th>' : ''}</tr></thead><tbody>${r.items.map(i => `<tr><td>${esc(i.name)}</td><td class="n">${esc(i.qty)}</td><td>${esc(i.batch || '')}</td>${entity === 'loan' ? `<td class="n">${esc(i.returned)}</td>` : ''}</tr>`).join('')}</tbody></table>` : '';
  const mv = r.moves.length ? `<div class="sec-h" style="margin-top:12px"><h2>对库存的影响</h2></div><table class="t"><tbody>${r.moves.map(m => `<tr><td class="w">${esc(m.date)}</td><td>${esc(m.product)}</td><td>${esc(m.batch_no || '')}</td><td class="n">${m.qty > 0 ? '+' : ''}${fmtN(m.qty)}</td></tr>`).join('')}</tbody></table>` : '';
  const ln = r.links.length ? `<div class="sec-h" style="margin-top:12px"><h2>关联</h2></div>${r.links.map(l => `<div><a class="link" data-go="${esc(l.entity)}:${l.id || ''}:${esc(l.key || '')}:${l.r || ''}:${esc(l.date || '')}">${esc(l.label)} ↗</a></div>`).join('')}` : '';
  const au = r.audit.length ? `<div class="sec-h" style="margin-top:12px"><h2>修改记录</h2></div><table class="t"><tbody>${r.audit.map(a => `<tr><td class="w">${fmtTs(a.ts)}</td><td>${esc(a.person)}</td><td>${esc(a.action)}</td><td>${esc(a.summary || '')}</td></tr>`).join('')}</tbody></table>` : '';
  const ov = dialog(r.entity_cn + (r.deleted ? '（已删除）' : ''), `${r.deleted ? `<div class="banner">已被 ${esc(r.deleted_by || '')} 删除，可在「数据备份 → 回收站」恢复</div>` : ''}<dl class="kv">${kv}</dl>${it}${mv}${ln}${au}`,
    [{ t: '关闭' }].concat(!r.deleted && ['out', 'loan', 'arrival', 'daily', 'paper', 'slip'].includes(entity) ? [{ t: '去那一页修改', cls: 'pri', fn: () => openRecord(entity, id, r) }] : []), { wide: true });
  ov.addEventListener('click', e => { const a = e.target.closest('[data-go]'); if (!a) return; ov.remove(); const [en, i, key, rr, dt] = a.dataset.go.split(':'); openRecord(en, +i, { key, r: +rr, date: dt }); });
}
/** 跳到某条记录所在的页面并打开它 */
async function openRecord(entity, id, ctx) {
  ctx = ctx || {};
  try {
    if (entity === 'report') { location.hash = '#report/' + ctx.key; setTimeout(() => { if (typeof rSelect === 'function' && ctx.r) { RP.k = ctx.key; rRender(); rSelect(ctx.r, 'A'); } }, 600); return; }
    if (entity === 'loan_req') { location.hash = '#loan/req'; return; }
    if (entity === 'out') { const x = await api('/api/out/one?id=' + id); Out.form = Object.assign(newOutForm(), x, { items: x.items.map(i => ({ product_id: i.product_id, product_name: i.product_name, qty: i.qty, batch_no: i.batch_no, note: i.note })) }); Out.tab = 'single'; location.hash = '#out/single'; return; }
    if (entity === 'loan') { const x = await api('/api/loan/one?id=' + id); LN.form = Object.assign(newLoanForm(), x, { items: x.items.map(i => ({ id: i.id, product_id: i.product_id, product_name: i.product_name, qty: i.qty, approx: i.approx, qty_text: i.qty_text, org: i.org, returned: i.returned, note: i.note, batch_no: i.batch_no })) }); location.hash = '#loan/new'; return; }
    if (entity === 'arrival') { location.hash = '#arrival'; setTimeout(() => { const el = $('#main .page') || $('#main'); if (typeof editArr === 'function') editArr(el, id); }, 500); return; }
    if (entity === 'paper' || entity === 'daily') {
      const r = ctx.fields ? ctx : await api('/api/record?entity=' + entity + '&id=' + id);
      const d = ctx.date || r.date; if (typeof D !== 'undefined' && d) { D.date = d; if (entity === 'paper') D.ses = (r.fields.find(f => f[0] === '班次') || [])[1] || D.ses; }
      location.hash = entity === 'paper' ? '#daily/cyl' : '#daily/sum'; return;
    }
    if (entity === 'slip') { location.hash = '#slip'; return; }
  } catch (e) { fail(e); }
}


/* ---------- 录入表格：当前格所在的行、列淡淡地标出来（表头稍加强调），方便对着纸看。
   gridFocus(table, cell)：cell 为空就清掉。表头有合并格（colspan/rowspan）也能对上列。 ---------- */
function gridMap(table) {
  const occ = [], out = [];
  [...table.rows].forEach((tr, ri) => {
    occ[ri] = occ[ri] || []; let c = 0;
    for (const cell of tr.cells) {
      while (occ[ri][c]) c++;
      const cs = cell.colSpan || 1, rs = cell.rowSpan || 1;
      for (let i = 0; i < rs; i++) { occ[ri + i] = occ[ri + i] || []; for (let j = 0; j < cs; j++) occ[ri + i][c + j] = 1; }
      out.push([cell, c, c + cs - 1]); c += cs;
    }
  });
  return out;
}
function gridFocus(table, cell) {
  if (!table) return;
  // 同一帧内多次触发只算一次，避免焦点跳转时闪一下
  if (table._gfRaf) cancelAnimationFrame(table._gfRaf);
  table._gfRaf = requestAnimationFrame(() => {
    table._gfRaf = 0;
    table.querySelectorAll('.hl-r,.hl-c,.hl-h').forEach(x => x.classList.remove('hl-r', 'hl-c', 'hl-h'));
    if (!cell || !table.contains(cell) || cell.closest('thead')) return;
    const map = gridMap(table), me = map.find(x => x[0] === cell); if (!me) return;
    const [, a, b] = me, tr = cell.parentNode;
    if (!tr.classList.contains('tot')) tr.classList.add('hl-r');
    for (const [x, s, e] of map) {
      if (e < a || s > b || x === cell) continue;
      if (x.tagName === 'TH') x.classList.add('hl-h'); else if (x.parentNode !== tr) x.classList.add('hl-c');
    }
    // 行头：车牌 / 配送员 / 日期（sticky 左列也要强调，对着纸更好找）
    [...tr.cells].forEach(td => {
      if (td !== cell && (td.classList.contains('pl') || td.classList.contains('dv') || td.classList.contains('stk') || td === tr.cells[0]))
        td.classList.add('hl-h');
    });
  });
}
/** 给一张录入表挂上：输入框得到焦点 / 点选格子时高亮 */
function gridFocusOn(table, pick) {
  if (!table || table._gf) return; table._gf = 1;
  const f = e => { const td = pick ? pick(e.target) : e.target.closest('td'); if (td) gridFocus(table, td); };
  table.addEventListener('focusin', f);
  table.addEventListener('mousedown', e => { const td = pick ? pick(e.target) : e.target.closest('td'); if (td && !td.closest('thead')) gridFocus(table, td); });
  table.addEventListener('focusout', e => { if (!e.relatedTarget || !table.contains(e.relatedTarget)) setTimeout(() => { if (!table.contains(document.activeElement) && !table.querySelector('td.sel,td.cell-sel')) gridFocus(table, null); }, 0); });
}


/* ---------- WPS 向表格选区（全局共用）
   拖选矩形多格 · Shift+点扩展 · Ctrl/⌘+点加减 · Esc/点表外清除
   底部状态条：求和 / 计数 / 平均（只计能解析的数字）
   Ctrl+C 复制选区为 TSV（可贴到 WPS/Excel）
   挂接：table.rt / table.pp / table.dt / table.t（data-nosel 退出）
   编辑规则：报表单击选中、拖选不进编辑、双击或 Enter/F2 才编辑；
            日表以 td 为单位选区，编辑态（input 已聚焦）优先输入，拖选不抢焦点。 ---------- */
const CellSel = (() => {
  const st = { table: null, cells: [], focus: null, anchor: null, drag: null, suppressClick: 0, skipClear: 0 };
  let barEl = null;

  const eligible = (table) => {
    if (!table || table.tagName !== 'TABLE' || table.closest('.ov')) return false;
    if (table.dataset.nosel != null) return false;
    return table.classList.contains('rt') || table.classList.contains('pp') || table.classList.contains('dt') || table.classList.contains('t');
  };
  const cellOf = (el, table) => {
    if (!el || !table) return null;
    if (el.closest('button,a,.r-acts,.r-more,.ra-more,.r-u8tag,.r-rz,.rtb')) return null;
    const td = el.closest('td');
    if (!td || !table.contains(td) || td.closest('thead')) return null;
    // 操作列 / 纯按钮格不进选区
    if (td.classList.contains('r-act') || td.classList.contains('ra') || td.querySelector(':scope > .r-acts, :scope > button.r-ib')) return null;
    return td;
  };
  const posOf = (table, td) => {
    const map = gridMap(table), me = map.find(x => x[0] === td);
    if (!me) return null;
    const ri = [...table.rows].indexOf(td.parentNode);
    return { ri, a: me[1], b: me[2], td };
  };
  const rectCells = (table, A, B) => {
    if (!A || !B) return [];
    const r0 = Math.min(A.ri, B.ri), r1 = Math.max(A.ri, B.ri);
    const c0 = Math.min(A.a, B.a), c1 = Math.max(A.b, B.b);
    const map = gridMap(table), out = [];
    for (const [cell, s, e] of map) {
      if (cell.tagName !== 'TD' || cell.closest('thead')) continue;
      const ri = [...table.rows].indexOf(cell.parentNode);
      if (ri < r0 || ri > r1) continue;
      if (e < c0 || s > c1) continue;
      if (cell.classList.contains('r-act') || cell.classList.contains('ra')) continue;
      out.push(cell);
    }
    return out;
  };
  const cellText = (td) => {
    const inp = td.querySelector('input:not([type=checkbox]):not([type=radio]):not([type=button]):not([type=file])');
    if (inp) return String(inp.value || '').trim();
    // 去掉行内按钮 / 标签噪音
    const clone = td.cloneNode(true);
    clone.querySelectorAll('button,a,.tag,.r-acts,.r-ib,.rtb').forEach(x => x.remove());
    return String(clone.innerText || clone.textContent || '').replace(/\s+/g, ' ').trim();
  };
  const cellNum = (td) => {
    let t = cellText(td);
    if (!t) return null;
    t = t.replace(/,/g, '').replace(/退$/i, '').trim();
    if (/^[-+]?\d+(?:\.\d+)?$/.test(t)) { const n = parseFloat(t); return isFinite(n) ? n : null; }
    const m = t.match(/^([-+]?\d+(?:\.\d+)?)\s*([+\-−])\s*(\d+(?:\.\d+)?)$/);
    if (m) {
      const a = parseFloat(m[1]), b = parseFloat(m[3]);
      if (!isFinite(a) || !isFinite(b)) return null;
      return (m[2] === '+' ? a + b : a - b);
    }
    // 带单位 / 前缀：取第一个数（如「剩 12」「12瓶」）
    const m2 = t.match(/[-+]?\d+(?:\.\d+)?/);
    if (!m2) return null;
    // 纯文本日期 / 单号等：含多个非数字字符且不像算式则跳过
    if (/[年\/]/.test(t) || /^\d{4}-\d{2}/.test(t)) return null;
    const n = parseFloat(m2[0]);
    return isFinite(n) ? n : null;
  };
  const ensureBar = () => {
    if (barEl && document.body.contains(barEl)) return barEl;
    barEl = document.getElementById('cellBar');
    if (!barEl) {
      barEl = document.createElement('div');
      barEl.id = 'cellBar';
      barEl.hidden = true;
      const foot = document.getElementById('foot');
      if (foot) foot.parentNode.insertBefore(barEl, foot);
      else document.body.appendChild(barEl);
    }
    return barEl;
  };
  const fmtStat = (n) => {
    if (!isFinite(n)) return '';
    const r = Math.round(n * 1000) / 1000;
    return String(r);
  };
  const paint = () => {
    st.cells = (st.cells || []).filter(td => td && td.isConnected);
    if (st.focus && !st.focus.isConnected) st.focus = st.cells[st.cells.length - 1] || null;
    if (!st.cells.length) { st.table = null; st.anchor = null; }
    document.querySelectorAll('td.cell-sel').forEach(x => x.classList.remove('cell-sel', 'cell-sel-a'));
    st.cells.forEach(td => td.classList.add('cell-sel'));
    if (st.focus) st.focus.classList.add('cell-sel', 'cell-sel-a');
    const bar = ensureBar();
    if (!st.cells.length) { bar.hidden = true; bar.innerHTML = ''; return; }
    const nums = st.cells.map(cellNum).filter(n => n != null);
    const nSel = st.cells.length;
    let html = `<span class="cb-n">已选 ${nSel} 格</span>`;
    if (nums.length) {
      const sum = nums.reduce((a, b) => a + b, 0);
      const avg = sum / nums.length;
      html = `<span class="cb-k">求和</span><b>${fmtStat(sum)}</b>`
        + `<span class="cb-k">计数</span><b>${nums.length}</b>`
        + `<span class="cb-k">平均</span><b>${fmtStat(avg)}</b>`
        + (nums.length !== nSel ? `<span class="cb-m">（${nSel} 格里 ${nums.length} 个数字）</span>` : '');
    }
    bar.innerHTML = html;
    bar.hidden = false;
  };
  const setCells = (table, cells, focus, anchor) => {
    st.table = table || null;
    st.cells = (cells || []).filter(c => c && c.isConnected);
    st.focus = focus && focus.isConnected ? focus : (st.cells[st.cells.length - 1] || null);
    if (anchor) st.anchor = anchor;
    else if (st.focus) st.anchor = posOf(table, st.focus);
    paint();
    if (table && st.focus) gridFocus(table, st.focus);
    if (table && table._csOnActive) {
      try { table._csOnActive(st.focus, st.cells); } catch (e) {}
    }
  };
  const clear = (table) => {
    if (table && st.table && st.table !== table) return;
    st.table = null; st.cells = []; st.focus = null; st.anchor = null; st.drag = null;
    paint();
  };
  const setSingle = (table, td) => {
    if (!table || !td) { clear(); return; }
    setCells(table, [td], td, posOf(table, td));
  };
  const toggleCell = (table, td) => {
    const set = new Set(st.table === table ? st.cells : []);
    if (set.has(td)) set.delete(td); else set.add(td);
    setCells(table, [...set], td, st.anchor || posOf(table, td));
  };
  const extendTo = (table, td) => {
    const A = (st.table === table && st.anchor) ? st.anchor : posOf(table, td);
    const B = posOf(table, td);
    setCells(table, rectCells(table, A, B), td, A);
  };
  const copyTSV = () => {
    if (!st.table || !st.cells.length) return false;
    const table = st.table;
    const poses = st.cells.map(td => posOf(table, td)).filter(Boolean);
    if (!poses.length) return false;
    const r0 = Math.min(...poses.map(p => p.ri)), r1 = Math.max(...poses.map(p => p.ri));
    const c0 = Math.min(...poses.map(p => p.a)), c1 = Math.max(...poses.map(p => p.b));
    const set = new Set(st.cells);
    const lines = [];
    for (let ri = r0; ri <= r1; ri++) {
      const row = [];
      for (let ci = c0; ci <= c1; ci++) {
        const hit = poses.find(p => p.ri === ri && p.a <= ci && p.b >= ci);
        row.push(hit && set.has(hit.td) ? cellText(hit.td) : '');
      }
      lines.push(row.join('\t'));
    }
    const tsv = lines.join('\n');
    const ok = () => { try { toast('已复制 ' + st.cells.length + ' 格'); } catch (e) {} };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(tsv).then(ok).catch(() => {
        const ta = document.createElement('textarea'); ta.value = tsv; document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); ok(); } catch (e) {}
        ta.remove();
      });
    } else {
      const ta = document.createElement('textarea'); ta.value = tsv; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); ok(); } catch (e) {}
      ta.remove();
    }
    return true;
  };
  const consumeClick = () => {
    if (!st.suppressClick) return false;
    st.suppressClick = 0;
    return true;
  };
  const onTable = (table, opts) => {
    if (!table) return;
    if (opts && typeof opts.onActive === 'function') table._csOnActive = opts.onActive;
    table.classList.add('cs-on');
  };

  const down = (e) => {
    if (e.button != null && e.button !== 0) return;
    if (e.target.closest('button,a,.r-rz,.r-u8tag,.ov,.r-acts,.ra-more')) return;
    const table = e.target.closest('table');
    if (!eligible(table)) return;
    const td = cellOf(e.target, table);
    if (!td) return;
    const onField = e.target.closest('input,textarea,select');
    if (e.shiftKey) {
      e.preventDefault();
      extendTo(table, td);
      st.drag = null;
      st.suppressClick = 1;
      return;
    }
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      toggleCell(table, td);
      st.drag = null;
      st.suppressClick = 1;
      return;
    }
    const P = posOf(table, td);
    st.drag = { table, start: P, last: P, x: e.clientX, y: e.clientY, moved: 0, additive: 0 };
    // 点在 input 上：先单选，不 preventDefault，保证能聚焦编辑；一旦拖动再 blur
    if (onField) setSingle(table, td);
    // 空白格 / 报表格：等 mouseup 再定单击或拖选
  };
  const move = (e) => {
    const d = st.drag; if (!d) return;
    const dist = Math.hypot(e.clientX - d.x, e.clientY - d.y);
    if (!d.moved && dist < 4) return;
    if (!d.moved) {
      d.moved = 1;
      document.body.classList.add('cs-dragging');
      // 拖选开始：若焦点在表内 input，先模糊以免乱跳
      const ae = document.activeElement;
      if (ae && d.table.contains(ae) && ['INPUT', 'TEXTAREA'].includes(ae.tagName)) ae.blur();
    }
    e.preventDefault();
    const td = cellOf(document.elementFromPoint(e.clientX, e.clientY), d.table) || d.last.td;
    const P = posOf(d.table, td) || d.last;
    d.last = P;
    setCells(d.table, rectCells(d.table, d.start, P), P.td, d.start);
  };
  const up = (e) => {
    const d = st.drag; st.drag = null;
    document.body.classList.remove('cs-dragging');
    if (!d) return;
    if (!d.moved) {
      // 单击：单选
      setSingle(d.table, d.start.td);
      return;
    }
    st.suppressClick = 1;
    setCells(d.table, rectCells(d.table, d.start, d.last), d.last.td, d.start);
  };
  const key = (e) => {
    if (e.key === 'Escape') {
      if (document.querySelector('.ov')) return; // 弹窗优先关窗
      if (st.cells.length) { clear(); e.preventDefault(); }
      return;
    }
    if ((e.ctrlKey || e.metaKey) && (e.key === 'c' || e.key === 'C')) {
      const ae = document.activeElement;
      if (ae && ['INPUT', 'TEXTAREA'].includes(ae.tagName) && ae.selectionStart !== ae.selectionEnd) return; // 输入框自身复制
      if (st.cells.length > 0) { if (copyTSV()) e.preventDefault(); }
      return;
    }
    // Shift+方向键扩展（报表非编辑态由 rBind 也会处理；这里兜底列表/日表）
    if (!e.shiftKey || !e.key.startsWith('Arrow') || !st.table || !st.focus) return;
    if (document.querySelector('.ov')) return;
    const ae = document.activeElement;
    if (ae && ['INPUT', 'TEXTAREA', 'SELECT'].includes(ae.tagName) && !st.table.classList.contains('pp')) return;
    // 日表 input 编辑中：留给日表自己的方向键
    if (ae && ['INPUT', 'TEXTAREA'].includes(ae.tagName) && st.table.classList.contains('pp')) return;
    if (App && App.cur === 'report') return; // 报表在 rBind 里扩展
    const table = st.table;
    const cur = posOf(table, st.focus); if (!cur) return;
    let ri = cur.ri, ci = cur.a;
    if (e.key === 'ArrowUp') ri--;
    else if (e.key === 'ArrowDown') ri++;
    else if (e.key === 'ArrowLeft') ci--;
    else if (e.key === 'ArrowRight') ci++;
    else return;
    e.preventDefault();
    const map = gridMap(table);
    const hit = map.find(([cell, s, ee]) => {
      if (cell.tagName !== 'TD' || cell.closest('thead')) return false;
      return [...table.rows].indexOf(cell.parentNode) === ri && s <= ci && ee >= ci;
    });
    if (hit) extendTo(table, hit[0]);
  };
  const docDown = (e) => {
    if (!st.cells.length) return;
    if (e.target.closest('#cellBar')) return;
    if (st.table && st.table.contains(e.target)) return;
    if (e.target.closest('.ov,.menu,.pop,.ac-pop,.r-more,.lc-pop')) return;
    clear();
  };

  if (!window._cellSelBound) {
    window._cellSelBound = 1;
    document.addEventListener('mousedown', down, true);
    document.addEventListener('mousemove', move, true);
    document.addEventListener('mouseup', up, true);
    document.addEventListener('keydown', key, true);
    document.addEventListener('mousedown', docDown, false);
  }

  return { on: onTable, clear, setSingle, setCells, extendTo, toggleCell, copyTSV, consumeClick, paint, cellText, cellNum, get: () => ({ table: st.table, cells: st.cells.slice(), focus: st.focus }) };
})();

/** 多行表头吸顶对齐：按实际行高写 top，避免写死 28/30px 与内容换行错位；钉左车牌/配送员按实测宽度写 left */
function syncStickyHeads(table) {
  if (!table || !table.tHead) return;
  const rows = [...table.tHead.rows];
  let top = 0;
  const hs = [];
  rows.forEach((tr, i) => {
    const h = Math.max(1, Math.round(tr.getBoundingClientRect().height) || (i === 0 ? 30 : 28));
    hs.push(h);
    [...tr.cells].forEach(th => { th.style.top = top + 'px'; });
    top += h;
  });
  if (hs[0]) table.style.setProperty('--rt-h1', hs[0] + 'px');
  if (hs[0]) table.style.setProperty('--pp-h1', hs[0] + 'px');
  if (hs.length > 1) {
    const s2 = hs[0] + hs[1];
    table.style.setProperty('--rt-h2', s2 + 'px');
    table.style.setProperty('--pp-h2', s2 + 'px');
  }
  // 交接表：配送员列 left = 车牌列实测宽（含边框）
  if (table.classList.contains('pp')) {
    const pl = table.querySelector('thead th.pl') || table.querySelector('tbody td.pl');
    const w = pl ? Math.max(70, Math.round(pl.getBoundingClientRect().width)) : 88;
    table.querySelectorAll('th.dv, td.dv').forEach(x => { x.style.left = w + 'px'; });
    table.querySelectorAll('th.pl, td.pl').forEach(x => { x.style.left = '0px'; });
    table.style.setProperty('--pp-pl', w + 'px');
  }
  table.dataset.stkSync = '1';
}


/* ---------- 列表表：列显示/隐藏 + 拖宽（本机记住；报表另有「设置」） ---------- */
const LC = {
  get(key) { try { return JSON.parse(localStorage.getItem('lc:' + key) || '{}') || {}; } catch (e) { return {}; } },
  set(key, o) { localStorage.setItem('lc:' + key, JSON.stringify(o)); },
  btn(key) { return `<button type="button" class="btn sm" data-lc-btn="${esc(key)}" title="显示/隐藏列；表头竖线可拖列宽">列</button>`; },
  /** cols: [{k,label,w,min,hide,wrap,prod}]  hide=默认隐藏；k 以 _ 开头不可藏（如 _act/_ck） */
  apply(table, key, cols) {
    if (!table || !cols || !cols.length) return;
    const pref = LC.get(key), hid = new Set(pref.hidden || cols.filter(x => x.hide).map(x => x.k));
    (pref.hidden || []).forEach(k => hid.add(k));
    // 若从未存过，用默认 hide
    if (!pref.hidden && !pref.widths) cols.filter(x => x.hide).forEach(x => hid.add(x.k));
    const widths = Object.assign({}, pref.widths || {});
    cols.forEach(x => { if (widths[x.k] == null && x.w) widths[x.k] = x.w; });
    // colgroup
    let cg = table.querySelector('colgroup'); if (cg) cg.remove();
    cg = document.createElement('colgroup');
    cols.forEach(x => {
      const col = document.createElement('col'); col.dataset.c = x.k;
      if (hid.has(x.k) && x.k[0] !== '_') col.classList.add('lc-hide');
      const w = widths[x.k]; if (w) col.style.width = (+w) + 'px';
      cg.appendChild(col);
    });
    table.insertBefore(cg, table.firstChild);
    table.style.tableLayout = 'fixed';
    // th/td 标记
    const ths = [...table.tHead.querySelectorAll('th')];
    ths.forEach((th, i) => {
      const def = cols[i]; if (!def) return;
      th.dataset.c = def.k;
      th.classList.toggle('lc-hide', hid.has(def.k) && def.k[0] !== '_');
      if (def.wrap) th.classList.add('wrap');
      if (def.prod) th.classList.add('prod');
      if (widths[def.k]) th.style.width = widths[def.k] + 'px';
      if (!th.querySelector('.lc-rz') && def.k[0] !== '_') {
        // sticky 本身就是绝对定位手柄的包含块；不要改成 relative，否则表头吸顶失效、与数据列错位
        const h = document.createElement('i'); h.className = 'lc-rz'; h.dataset.rz = def.k; h.title = '拖动调节列宽'; th.appendChild(h);
      }
    });
    [...table.tBodies].forEach(tb => [...tb.rows].forEach(tr => {
      [...tr.cells].forEach((td, i) => {
        const def = cols[i]; if (!def) return;
        td.dataset.c = def.k;
        td.classList.toggle('lc-hide', hid.has(def.k) && def.k[0] !== '_');
        if (def.wrap) td.classList.add('wrap');
        if (def.prod) td.classList.add('prod');
        // 裁切时悬停看全文
        if ((def.wrap || def.prod) && td.scrollWidth > td.clientWidth + 1) {
          if (!td.title) td.title = (td.innerText || '').trim();
        }
      });
    }));
    // 拖宽
    table.querySelectorAll('i.lc-rz').forEach(h => {
      h.onmousedown = e => {
        e.preventDefault(); e.stopPropagation();
        const ck = h.dataset.rz, col = table.querySelector(`colgroup col[data-c="${ck}"]`);
        const def = cols.find(x => x.k === ck) || {};
        const min = def.min || 40;
        const x0 = e.clientX, w0 = (col && parseInt(col.style.width, 10)) || h.closest('th').getBoundingClientRect().width;
        let cur = w0;
        const move = ev => {
          cur = Math.max(min, Math.min(640, Math.round(w0 + ev.clientX - x0)));
          if (col) col.style.width = cur + 'px';
          table.querySelectorAll(`th[data-c="${ck}"]`).forEach(x => x.style.width = cur + 'px');
          let tw = 0; table.querySelectorAll('colgroup col').forEach(x => { if (!x.classList.contains('lc-hide')) tw += parseInt(x.style.width, 10) || x.getBoundingClientRect().width; });
          if (tw) table.style.width = Math.round(tw) + 'px';
        };
        const up = () => {
          document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up);
          document.body.classList.remove('rz-on');
          const p2 = LC.get(key); p2.widths = Object.assign({}, p2.widths || {}, { [ck]: cur }); LC.set(key, p2);
        };
        document.body.classList.add('rz-on');
        document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
      };
    });
    table.dataset.lcKey = key;
    table._lcCols = cols;
  },
  open(btn) {
    const key = btn.dataset.lcBtn, table = document.querySelector(`table[data-lc-key="${key}"]`) || (function () { var r = btn.closest('.card, .page'); return r ? r.querySelector('table.t') : null; })();
    const cols = (table && table._lcCols) || null;
    if (!cols) return toast('这一页还没有可调的列', true);
    const pref = LC.get(key);
    const hid = new Set(pref.hidden || cols.filter(x => x.hide).map(x => x.k));
    if (!pref.hidden) cols.filter(x => x.hide).forEach(x => hid.add(x.k));
    document.querySelectorAll('.lc-pop').forEach(x => x.remove());
    const pop = document.createElement('div'); pop.className = 'lc-pop';
    pop.innerHTML = `<div class="lc-pop-h">显示列</div>${cols.filter(x => x.k[0] !== '_').map(x =>
      `<label><input type="checkbox" data-k="${esc(x.k)}" ${hid.has(x.k) ? '' : 'checked'}>${esc(x.label)}</label>`).join('')}
      <div class="lc-tip">表头右侧竖线可拖列宽。设置只存在这台电脑。「重置列宽」只清宽度，不改显示列。</div>
      <div class="lc-acts"><button type="button" class="btn sm" data-rzw title="只清自定义列宽，显示列保留">重置列宽</button><button type="button" class="btn sm" data-rst>恢复默认</button><button type="button" class="btn sm pri" data-ok>确定</button></div>`;
    document.body.appendChild(pop);
    const r = btn.getBoundingClientRect();
    pop.style.top = Math.min(r.bottom + 4, innerHeight - pop.offsetHeight - 8) + 'px';
    pop.style.left = Math.max(8, Math.min(r.right - pop.offsetWidth, innerWidth - pop.offsetWidth - 8)) + 'px';
    const close = () => { pop.remove(); document.removeEventListener('click', out); };
    const out = e => { if (!pop.contains(e.target) && e.target !== btn) close(); };
    setTimeout(() => document.addEventListener('click', out), 0);
    pop.addEventListener('click', e => {
      if (e.target.dataset.rzw != null) {
        const p2 = LC.get(key); delete p2.widths; LC.set(key, p2); close();
        LC.apply(table, key, table._lcCols.map(x => Object.assign({}, x)));
        toast('已重置列宽');
        return;
      }
      if (e.target.dataset.rst != null) {
        LC.set(key, {}); close();
        const card = table.closest('.card, #olT, #llT, #arT, #stT, #miT, #mvT, #lyT') || table.parentElement;
        // 触发所在页重绘：点一下不会；直接 apply 默认
        const defs = table._lcCols.map(x => Object.assign({}, x));
        // 清 hide 用默认
        LC.apply(table, key, defs);
        toast('已恢复默认列');
        return;
      }
      if (e.target.dataset.ok == null) return;
      const hidden = [...pop.querySelectorAll('input[data-k]')].filter(i => !i.checked).map(i => i.dataset.k);
      if (hidden.length >= cols.filter(x => x.k[0] !== '_').length) { toast('至少留一列', true); return; }
      const p2 = LC.get(key); p2.hidden = hidden; LC.set(key, p2);
      LC.apply(table, key, cols); close(); toast('已保存列显示');
    });
  }
};
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('[data-lc-btn]');
  if (b) { e.preventDefault(); LC.open(b); }
});
