/* ===== v82 离线识别（内置 Tesseract，无需联网、无需百度 Key） ===== */
const O2OCR = (function () {
  let workerP = null;
  function txt(id) { const el = document.getElementById(id); if (!el) throw new Error('识别组件缺失：' + id); return el.textContent; }
  function b64ToU8(b) { const s = atob(b.replace(/\s+/g, '')); const u = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); return u; }
  function getWorker(onProgress) {
    if (workerP) return workerP;
    workerP = (async () => {
      if (!window.TesseractOffline) throw new Error('离线识别组件未加载');
      // 核心(wasm) 与 worker 拼成同一个 Blob，避免 file:// 下跨源 importScripts 被拦截
      const workerURL = URL.createObjectURL(new Blob([txt('o2-ocr-core'), '\n;self.TesseractCore=TesseractCore;\n', txt('o2-ocr-worker')], { type: 'text/javascript' }));
      const coreURL = 'inline-core.js';
      const eng = b64ToU8(txt('o2-ocr-eng'));
      return await window.TesseractOffline.createWorker([{ code: 'eng', data: eng }], 1, {
        workerPath: workerURL, corePath: coreURL, workerBlobURL: false, cacheMethod: 'none', gzip: false,
        logger: m => { try { onProgress && onProgress(m); } catch (e) {} }
      });
    })();
    workerP.catch(() => { workerP = null; });
    return workerP;
  }
  function loadImg(src) {
    return new Promise((res, rej) => { const im = new Image(); im.onload = () => res(im); im.onerror = () => rej(new Error('图片无法读取')); im.src = src; });
  }
  // 放大 + 灰度 + 拉伸对比度：U8 截图字很小，放大后识别率明显提高
  async function prep(src, scaleWanted) {
    const im = await loadImg(src);
    const scale = scaleWanted || (im.width < 1300 ? 3 : (im.width < 2200 ? 2 : 1));
    const c = document.createElement('canvas'); c.width = im.width * scale; c.height = im.height * scale;
    const g = c.getContext('2d'); g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'high';
    g.drawImage(im, 0, 0, c.width, c.height);
    const d = g.getImageData(0, 0, c.width, c.height), p = d.data;
    for (let i = 0; i < p.length; i += 4) {
      let y = 0.299 * p[i] + 0.587 * p[i + 1] + 0.114 * p[i + 2];
      y = y > 200 ? 255 : (y < 90 ? 0 : (y - 90) * 255 / 110);
      p[i] = p[i + 1] = p[i + 2] = y;
    }
    stripLines(p, c.width, c.height, 0, 0, scale);
    g.putImageData(d, 0, 0);
    return { canvas: c, scale, w: im.width, h: im.height };
  }
  // 去掉表格的深色横竖线（截图里表格线是黑色时会干扰识别）：连续深色长度超过 15% 宽/高的线段涂白
  function stripLines(p, W, H, minH, minV, scale) {
    const dark = i => p[i * 4] < 140;
    minH = minH || Math.max(25 * (scale || 1), W * 0.15); minV = minV || Math.max(25 * (scale || 1), H * 0.15);
    const kill = [];
    for (let y = 0; y < H; y++) { let run = 0; for (let x = 0; x <= W; x++) { if (x < W && dark(y * W + x)) run++; else { if (run >= minH) kill.push([y, x - run, x, 0]); run = 0; } } }
    for (let x = 0; x < W; x++) { let run = 0; for (let y = 0; y <= H; y++) { if (y < H && dark(y * W + x)) run++; else { if (run >= minV) kill.push([x, y - run, y, 1]); run = 0; } } }
    kill.forEach(([a, b, e, v]) => { for (let t = b; t < e; t++) { const i = (v ? t * W + a : a * W + t) * 4; p[i] = p[i + 1] = p[i + 2] = 255; } });
  }
  async function recognize(src, onProgress, opt) {
    opt = opt || {};
    const w = await getWorker(onProgress);
    const pr = await prep(src, opt.scale);
    await w.setParameters({ tessedit_pageseg_mode: opt.psm || '11', preserve_interword_spaces: '1' });
    const r = await w.recognize(pr.canvas);
    const words = [];
    (r.data.words || []).forEach(x => {
      const t = (x.text || '').trim(); if (!t) return;
      const b = x.bbox; words.push({ t, x0: b.x0 / pr.scale, x1: b.x1 / pr.scale, y0: b.y0 / pr.scale, y1: b.y1 / pr.scale, conf: x.confidence });
    });
    return { text: r.data.text || '', words, width: pr.w, height: pr.h };
  }

  // 第二遍：逐行把「数量」那一格裁出来、放大，只认数字和小数点，修正首位数字丢失 / 9→3 之类的误读
  const isDec = t => /^[.,]?[0oO]{3}$/.test(t) || /^\d{1,6}[.,][0-9oO]{2,3}$/.test(t);
  async function refineQty(src, res, onProgress) {
    const w = await getWorker(onProgress);
    const im = await loadImg(src);
    const L = lines(res.words);
    const jobs = [];
    L.forEach(l => {
      const ws = l.words;
      // 有编码的行才处理（≥3 位纯数字开头）
      if (!ws.some(x => /^[\dOo]{3,8}$/.test(x.t))) return;
      let di = -1;
      for (let i = 0; i < ws.length; i++) { if (isDec(ws[i].t)) { di = i; break; } }
      if (di < 1) return;
      let li = di - 1;
      if (/^\d{1,6}[.,]?$/.test(ws[li].t) && (ws[di].x0 - ws[li].x1) < (ws[di].y1 - ws[di].y0) * 1.2) li -= 1;
      const leftTok = ws[Math.max(0, li)];
      const h = Math.max(8, ws[di].y1 - ws[di].y0);
      const x0 = Math.max(leftTok.x1 + 1, ws[di].x0 - h * 9), x1 = ws[di].x1 + 2;
      const y0 = Math.max(0, l.cy - h * 0.95), y1 = Math.min(im.height, l.cy + h * 0.95);
      jobs.push({ l, x0, x1, y0, y1 });
    });
    if (!jobs.length) return;
    await w.setParameters({ tessedit_pageseg_mode: '7', tessedit_char_whitelist: '0123456789.' });
    try {
      const VARIANTS = [{ k: 5, th: 185 }, { k: 4, th: 200 }, { k: 5, th: 0 }];
      for (const j of jobs) {
        j.l.qtyCands = [];
        for (const V of VARIANTS) {
          const k = V.k, pad = 14;
          const c = document.createElement('canvas');
          c.width = Math.ceil((j.x1 - j.x0) * k) + pad * 2; c.height = Math.ceil((j.y1 - j.y0) * k) + pad * 2;
          const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height);
          g.imageSmoothingQuality = 'high';
          g.drawImage(im, j.x0, j.y0, j.x1 - j.x0, j.y1 - j.y0, pad, pad, (j.x1 - j.x0) * k, (j.y1 - j.y0) * k);
          const d = g.getImageData(0, 0, c.width, c.height), p = d.data;
          for (let i = 0; i < p.length; i += 4) {
            const y = 0.299 * p[i] + 0.587 * p[i + 1] + 0.114 * p[i + 2];
            const v = V.th ? (y > V.th ? 255 : 0) : y;
            p[i] = p[i + 1] = p[i + 2] = v;
          }
          stripLines(p, c.width, c.height, c.width * 0.9, c.height * 0.75);
          g.putImageData(d, 0, 0);
          const r = await w.recognize(c);
          const t = (r.data.text || '').replace(/\s+/g, '').replace(/\.{2,}/g, '.');
          const m = t.match(/(\d{1,6})\.?(\d{3})$/) || t.match(/(\d{1,6})\.(\d{1,3})/);
          if (m && m[2].length === 3) j.l.qtyCands.push(parseFloat(m[1] + '.' + m[2]));
          j.l.qtyRaw = (j.l.qtyRaw ? j.l.qtyRaw + '|' : '') + t;
        }
      }
    } finally {
      await w.setParameters({ tessedit_pageseg_mode: '11', tessedit_char_whitelist: '' });
    }
    res.lines = L;
  }

  // 数量投票：第一遍整体识别 + 第二遍三种放大方式；再用「合计」行校验，组合出与合计一致的结果
  function voteOf(arr) {
    const m = new Map(); arr.forEach(v => { if (isFinite(v)) m.set(v, (m.get(v) || 0) + 1); });
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }
  function finalizeQty(items, totalCands) {
    items.forEach(it => { it.votes = voteOf(it.cands); it.qty = it.votes.length ? it.votes[0][0] : NaN; it.sure = it.votes.length === 1 || (it.votes.length > 1 && it.votes[0][1] >= 2 * it.votes[1][1]); });
    const tv = voteOf(totalCands || []);
    const total = tv.length ? tv[0][0] : null;
    let checked = null;
    if (total != null && items.length) {
      const sum = items.reduce((a, b) => a + (isFinite(b.qty) ? b.qty : 0), 0);
      if (Math.abs(sum - total) < 1e-6) checked = true;
      else {
        const opts = items.map(it => it.votes.map(v => v[0]).slice(0, 3));
        let n = opts.reduce((a, o) => a * Math.max(1, o.length), 1), best = null;
        if (n <= 20000) {
          const pick = new Array(items.length).fill(0);
          const rec = (i, acc, score) => {
            if (i === items.length) { if (Math.abs(acc - total) < 1e-6 && (!best || score > best.score)) best = { score, sel: pick.slice() }; return; }
            const o = opts[i]; if (!o.length) { rec(i + 1, acc, score); return; }
            for (let k = 0; k < o.length; k++) { pick[i] = k; rec(i + 1, acc + o[k], score + items[i].votes[k][1]); }
          };
          rec(0, 0, 0);
        }
        if (best) { items.forEach((it, i) => { if (opts[i].length) { it.qty = opts[i][best.sel[i]]; it.sure = true; } }); checked = true; }
        else checked = false;
      }
    }
    if (checked) items.forEach(it => { if (isFinite(it.qty)) it.sure = true; });
    return { total, checked };
  }
  function lineQtyCands(l, toks, qi) {
    const c = (l.qtyCands || []).slice();
    const first = qtyOf(toks[qi] + (isQty(toks[qi]) ? '' : (toks[qi + 1] || '')));
    if (isFinite(first) && /[.,]\s*\d{3}$/.test(toks[qi] + (isQty(toks[qi]) ? '' : (toks[qi + 1] || '')))) c.push(first);
    return c;
  }
  async function recognizeTable(src, onProgress) {
    const res = await recognize(src, onProgress);
    try { await refineQty(src, res, onProgress); } catch (e) { console.warn('qty refine fail', e); }
    if (!res.lines) res.lines = lines(res.words);
    return res;
  }
  function lines(words) {
    const ws = words.slice().sort((a, b) => (a.y0 + a.y1) - (b.y0 + b.y1));
    const out = [];
    ws.forEach(w => {
      const cy = (w.y0 + w.y1) / 2, h = Math.max(6, w.y1 - w.y0);
      let L = out.find(l => Math.abs(l.cy - cy) < Math.max(4, h * 0.6));
      if (!L) { L = { cy, words: [] }; out.push(L); }
      L.words.push(w); L.cy = L.words.reduce((s, q) => s + (q.y0 + q.y1) / 2, 0) / L.words.length;
    });
    out.forEach(l => l.words.sort((a, b) => a.x0 - b.x0));
    return out.sort((a, b) => a.cy - b.cy);
  }
  const fixDigits = s => String(s).replace(/[Oo]/g, '0').replace(/[Il|]/g, '1').replace(/[Ss]/g, '5').replace(/B/g, '8');
  const isQty = t => /^\d{1,6}[.,]\d{2,3}$/.test(String(t).replace(/[^\d.,]/g, '')) && /[.,]\d{2,3}$/.test(t);
  const qtyOf = t => parseFloat(String(t).replace(/[^\d.,]/g, '').replace(',', '.'));
  const COMMON_SPECS = ['1.6', '2', '2.4', '6.8', '10', '12', '15', '20', '25', '30', '35', '40', '80', '100', '175', '195', '210', '500', '1000'];
  function specToken(t) {
    t = String(t).trim().replace(/[^\w.|]/g, '');
    let m = t.match(/^(\d{1,4}(?:\.\d)?)[Ll]$/); if (m) return m[1];
    m = t.match(/^(\d{1,4}(?:\.\d)?)[1|I]$/); if (m && COMMON_SPECS.includes(m[1])) return m[1];
    return null;
  }
  // 逐行抽取：返回 {items:[{code,spec,cands,line,cy}], totalCands:[]}
  function scanRows(res, codeRe) {
    const W = res.width || 1000;
    const items = []; let totalCands = [];
    (res.lines || lines(res.words)).forEach(l => {
      const toks = l.words.map(w => w.t);
      let qi = toks.findIndex(isQty);
      if (qi < 0) qi = toks.findIndex(isDec);
      if (qi < 0) return;
      if (qi > 0 && /^\d{1,6}[.,]?$/.test(toks[qi - 1]) && !isQty(toks[qi])) qi -= 1;
      let code = '', spec = '';
      for (let i = 0; i < qi; i++) {
        const w = l.words[i];
        const d = fixDigits(w.t.replace(/[^\w|]/g, ''));
        if (!code && codeRe.test(d) && w.x0 > W * 0.012) { code = d; continue; }
        if (code && !spec) { const sp = specToken(w.t); if (sp) spec = sp; }
      }
      const cands = lineQtyCands(l, toks, qi);
      if (!code) { if (items.length && cands.length) totalCands = cands; return; }  // 「合计」行
      items.push({ code, spec, cands, line: toks.join(' '), cy: l.cy });
    });
    return { items, totalCands };
  }
  /** U8 采购入库单截图：入库单号 + 每行 存货编码 / 规格 / 数量（只用来匹配到货行） */
  function parseU8Inbound(res) {
    const H = res.height || 600;
    let cands = [];
    res.words.forEach(w => {
      if (/[-:\/]/.test(w.t)) return; // 日期、时间
      const t = fixDigits(w.t).replace(/[^\d]/g, '');
      if (/^\d{7,11}$/.test(t)) cands.push({ t, x: w.x0, y: w.y0 });
    });
    cands = cands.filter(c => c.y < H * 0.4).sort((a, b) => (a.y - b.y) || (a.x - b.x));
    let orderNo = '';
    if (cands.length) { const top = cands[0]; orderNo = cands.filter(c => Math.abs(c.y - top.y) < 6).sort((a, b) => a.x - b.x)[0].t; }
    const sc = scanRows(res, /^\d{3,8}$/);
    // 去掉表头区域里误认的行（必须在入库单号下方）
    const items = sc.items.filter(it => !cands.length || it.cy > cands[0].y);
    const chk = finalizeQty(items, sc.totalCands);
    return { orderNo, items: items.map(it => ({ code: it.code, spec: it.spec, qty: it.qty, sure: it.sure, line: it.line })), total: chk.total, totalOk: chk.checked };
  }
  /** 群里每日用量截图（U8 产品出库样式）：编码 01xxx=气态，02xxx=液态；同规格合计 */
  function parseDailyUsage(res) {
    const sc = scanRows(res, /^0[12]\d{3}$/);
    const items = sc.items.filter(it => it.spec);
    const chk = finalizeQty(items, sc.totalCands);
    const gas = {}, liq = {}, rows = [];
    items.forEach(it => {
      const kind = it.code.startsWith('01') ? 'gas' : 'liq';
      const bag = kind === 'gas' ? gas : liq;
      if (isFinite(it.qty)) bag[it.spec] = Math.round(((bag[it.spec] || 0) + it.qty) * 1000) / 1000;
      rows.push({ code: it.code, kind, spec: it.spec, qty: it.qty, sure: it.sure, line: it.line });
    });
    return { gas, liq, rows, total: chk.total, totalOk: chk.checked };
  }

  // ---- 过磅单照片：自动转正（手机横拍）、读 日期 / 车号 / 毛重-皮重=净重 ----
  async function rotScaled(src, deg, maxSide) {
    const im = await loadImg(src);
    const k = Math.min(1, maxSide / Math.max(im.width, im.height));
    const w = Math.round(im.width * k), h = Math.round(im.height * k);
    const c = document.createElement('canvas');
    const sw = deg % 180 !== 0;
    c.width = sw ? h : w; c.height = sw ? w : h;
    const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height);
    g.translate(c.width / 2, c.height / 2); g.rotate(deg * Math.PI / 180); g.drawImage(im, -w / 2, -h / 2, w, h);
    const d = g.getImageData(0, 0, c.width, c.height), p = d.data;
    for (let i = 0; i < p.length; i += 4) { const y = 0.299 * p[i] + 0.587 * p[i + 1] + 0.114 * p[i + 2]; p[i] = p[i + 1] = p[i + 2] = y; }
    g.putImageData(d, 0, 0);
    return c;
  }
  async function wordsOf(w, canvas, psm) {
    await w.setParameters({ tessedit_pageseg_mode: psm || '11', tessedit_char_whitelist: '' });
    const r = await w.recognize(canvas);
    return (r.data.words || []).map(x => ({ t: (x.text || '').trim(), x0: x.bbox.x0, x1: x.bbox.x1, y0: x.bbox.y0, y1: x.bbox.y1, conf: x.confidence })).filter(x => x.t);
  }
  const scoreWords = ws => ws.filter(x => /\d{4,}/.test(x.t) && x.conf > 55).length + ws.filter(x => /20\d\d-\d\d-\d\d/.test(x.t)).length * 3;
  async function recognizeSlip(src, onProgress) {
    const w = await getWorker(onProgress);
    let best = null;
    for (const deg of [0, 270, 90, 180]) {
      const c = await rotScaled(src, deg, 1400);
      const ws = await wordsOf(w, c);
      const sc = scoreWords(ws);
      if (!best || sc > best.sc) best = { deg, sc };
      if (sc >= 12) break;
    }
    const c = await rotScaled(src, best.deg, 2600);
    const words = await wordsOf(w, c);
    return { words, deg: best.deg, width: c.width, height: c.height };
  }
  function parseSlips(res, knownPlates) {
    const ws = res.words;
    // 日期：取出现最多的 yyyy-mm-dd
    const dc = {};
    ws.forEach(x => { const m = /(20\d\d)[-.\/](\d{1,2})[-.\/](\d{1,2})/.exec(x.t); if (m) { const k = m[1] + '-' + m[2].padStart(2, '0') + '-' + m[3].padStart(2, '0'); dc[k] = (dc[k] || 0) + 1; } });
    const date = Object.keys(dc).sort((a, b) => dc[b] - dc[a])[0] || '';
    // 车号：字母+5位（省份汉字识别不了，用历史车号补全）
    const pc = {};
    ws.forEach(x => { const m = /([A-Z])[\s·.]?([A-Z0-9]{5})$/.exec(x.t.replace(/[^A-Z0-9·.]/g, '')); if (m && /\d{3,}/.test(m[2])) { const k = m[1] + m[2]; pc[k] = (pc[k] || 0) + 1; } });
    const plates = Object.keys(pc).sort((a, b) => pc[b] - pc[a]).map(p => {
      const full = (knownPlates || []).find(k => k.replace(/\s/g, '').endsWith(p));
      return full || p;
    });
    // 重量：4~6 位整数；找 毛重 - 皮重 = 净重 的三元组（同一张单子上位置相近）
    const nums = [];
    ws.forEach((x, i) => {
      const t = x.t.replace(/[,，]/g, '');
      if (/^\d{4,6}$/.test(t) && !/^20[12]\d$/.test(t)) nums.push({ v: +t, i, cx: (x.x0 + x.x1) / 2, cy: (x.y0 + x.y1) / 2 });
    });
    const D = Math.max(res.width, res.height) * 0.35;
    const near = (a, b) => Math.hypot(a.cx - b.cx, a.cy - b.cy) < D;
    const tri = [];
    for (const a of nums) for (const b of nums) for (const c of nums) {
      if (a === b || b === c || a === c) continue;
      if (a.v - b.v === c.v && c.v > 500 && near(a, b) && near(b, c) && near(a, c)) tri.push({ a, b, c, spread: Math.hypot(a.cx - c.cx, a.cy - c.cy) + Math.hypot(a.cx - b.cx, a.cy - b.cy) });
    }
    tri.sort((p, q) => p.spread - q.spread);
    const used = new Set(), slips = [];
    tri.forEach(t => { if (used.has(t.a.i) || used.has(t.b.i) || used.has(t.c.i)) return; used.add(t.a.i); used.add(t.b.i); used.add(t.c.i); slips.push({ gross: t.a.v, tare: t.b.v, net: t.c.v, tons: Math.round(t.c.v / 10) / 100, cx: t.c.cx, cy: t.c.cy }); });
    slips.sort((p, q) => (p.cy - q.cy) || (p.cx - q.cx));
    return { date, plate: plates[0] || '', plates, slips };
  }

  // ================= U8 表格截图：按表格线切格子，逐格识别（修：整图识别漏行、数量读错） =================
  // 1) 用每一行/列像素的「中位数亮度」找表格线（文字只占少数像素，不影响中位数；表格线整行都暗）
  // 2) 线与线之间就是一行/一列；格子里有深色像素 = 非空。编码格非空的行都是数据行，一行不漏
  // 3) 列的用途（编码/规格/数量）看前几行格子的识别结果判断；每格单独裁出、按行高放大、只认数字，多种预处理投票
  // 4) 各行数量之和对不上「合计」时，换更多预处理重试；仍对不上就把看不清的行标出来，并给出差额
  function grayOf(im) {
    const c = document.createElement('canvas'); c.width = im.width; c.height = im.height;
    const g = c.getContext('2d'); g.drawImage(im, 0, 0);
    const d = g.getImageData(0, 0, c.width, c.height).data, L = new Uint8Array(c.width * c.height);
    for (let i = 0, j = 0; j < L.length; i += 4, j++) L[j] = (299 * d[i] + 587 * d[i + 1] + 114 * d[i + 2]) / 1000;
    return { L, W: c.width, H: c.height };
  }
  function median(arr) { const a = Array.from(arr).sort((x, y) => x - y); return a.length ? a[a.length >> 1] : 255; }
  function pct(arr, q) { const a = Array.from(arr).sort((x, y) => x - y); return a.length ? a[Math.min(a.length - 1, Math.floor(a.length * q))] : 255; }
  function findLines(prof, minDrop) {
    // prof[i] = 第 i 行（或列）的中位数亮度；比两侧（±2~3 像素）都暗 minDrop 以上的是线；相邻的合并
    const n = prof.length, hit = [];
    for (let i = 0; i < n; i++) {
      const nb = [i - 3, i - 2, i + 2, i + 3].filter(k => k >= 0 && k < n).map(k => prof[k]);
      const lo = Math.min(...nb.filter((_, q) => q < 2 || nb.length < 4 ? true : true));
      const left = [i - 3, i - 2].filter(k => k >= 0).map(k => prof[k]), right = [i + 2, i + 3].filter(k => k < n).map(k => prof[k]);
      const ok = (!left.length || Math.max(...left) - prof[i] >= minDrop) && (!right.length || Math.max(...right) - prof[i] >= minDrop) && (left.length || right.length);
      void lo; if (ok) hit.push(i);
    }
    const out = [];
    hit.forEach(i => { const l = out[out.length - 1]; if (l && i - l.b <= 2) l.b = i; else out.push({ a: i, b: i }); });
    return out.map(l => (l.a + l.b) / 2);
  }
  function detectGrid(G) {
    const { L, W, H } = G;
    const rowMed = new Float32Array(H);
    const step = Math.max(1, Math.floor(W / 400));
    for (let y = 0; y < H; y++) { const a = []; for (let x = 0; x < W; x += step) a.push(L[y * W + x]); rowMed[y] = median(a); }
    const hl = findLines(rowMed, 12);
    if (hl.length < 4) return null;
    // 行高：取相邻线距的中位数；只保留与它相近的间隔为「行」
    const gaps = []; for (let i = 1; i < hl.length; i++) gaps.push(hl[i] - hl[i - 1]);
    const rh = median(gaps);
    if (!(rh >= 8 && rh <= 120)) return null;
    const rows = [];
    for (let i = 1; i < hl.length; i++) { const g = hl[i] - hl[i - 1]; if (g > rh * 0.6 && g < rh * 1.6) rows.push({ y0: hl[i - 1], y1: hl[i] }); }
    if (rows.length < 3) return null;
    // 列：只在数据行范围内统计每列的中位数
    const y0 = rows[0].y0, y1 = rows[rows.length - 1].y1, colMed = new Float32Array(W);
    const ys = []; for (let y = Math.ceil(y0) + 2; y < y1 - 1; y += Math.max(1, Math.floor((y1 - y0) / 300))) ys.push(y);
    // 用 80% 分位数而不是中位数：U8 表格是一行白一行灰的斑马纹，中位数会被某几行里的字推着在 242/255 之间来回跳，误判成竖线
    //（原图 1623px 宽时第 2 列被切碎，漏了 01002 10L 41 那一行）；真正的竖线几乎每一行都是暗的，80% 分位也还是暗
    for (let x = 0; x < W; x++) { const a = ys.map(y => L[y * W + x]); colMed[x] = pct(a, 0.8); }
    const vl = findLines(colMed, 10);
    const cols = []; const xs = [0].concat(vl, [W - 1]);
    for (let i = 1; i < xs.length; i++) if (xs[i] - xs[i - 1] >= rh * 0.8) cols.push({ x0: xs[i - 1], x1: xs[i] });
    return { rows, cols, rh };
  }
  function inkOf(G, x0, x1, y0, y1) {
    let n = 0; const { L, W } = G;
    for (let y = Math.ceil(y0) + 2; y < y1 - 1; y++) for (let x = Math.ceil(x0) + 2; x < x1 - 1; x++) if (L[y * W + x] < 150) n++;
    return n;
  }
  // 裁一格 → 放大到字高约 48px → 灰度 / 二值化 → 识别（只认白名单字符）
  async function ocrCell(w, im, cell, V, white) {
    const pad = 3, x0 = cell.x0 + pad, y0 = cell.y0 + 2, cw = cell.x1 - cell.x0 - pad - 1.5, ch = cell.y1 - cell.y0 - 3;   // 右边只留 1.5px：U8 数字靠右，切多了会丢最后一位
    if (cw <= 2 || ch <= 2) return '';
    const k = Math.max(2, Math.min(8, (V.h || 64) / ch)), P = 18;
    const c = document.createElement('canvas'); c.width = Math.ceil(cw * k) + P * 2; c.height = Math.ceil(ch * k) + P * 2;
    const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height);
    g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'high';
    g.drawImage(im, x0, y0, cw, ch, P, P, cw * k, ch * k);
    const d = g.getImageData(0, 0, c.width, c.height), p = d.data;
    for (let i = 0; i < p.length; i += 4) {
      const y = 0.299 * p[i] + 0.587 * p[i + 1] + 0.114 * p[i + 2];
      const v = V.th ? (y > V.th ? 255 : 0) : (y > 215 ? 255 : y);
      p[i] = p[i + 1] = p[i + 2] = v;
    }
    g.putImageData(d, 0, 0);
    await w.setParameters({ tessedit_pageseg_mode: V.psm || '7', tessedit_char_whitelist: white });
    const r = await w.recognize(c);
    return (r.data.text || '').replace(/\s+/g, '');
  }
  const CODE_RE = /0[12]\d{3}/, SPEC_RE = /^(\d{1,4}(?:\.\d)?)L/, QTY_RE = /(\d{1,6})\.(\d{2,3})(?!\d)/;
  const VAR_A = [{ h: 64, th: 0 }, { h: 56, th: 185 }, { h: 80, th: 200 }];
  const VAR_B = [{ h: 48, th: 170 }, { h: 96, th: 0 }, { h: 72, th: 215 }, { h: 64, th: 160, psm: '8' }, { h: 110, th: 190 }];
  const parseQty = t => { const m = QTY_RE.exec(t.replace(/,/g, '.')); return m ? parseFloat(m[1] + '.' + m[2]) : NaN; };
  async function recognizeU8Grid(src, onProgress) {
    const w = await getWorker(onProgress);
    const im = await loadImg(src), G = grayOf(im), grid = detectGrid(G);
    if (!grid || grid.cols.length < 3) return null;
    const { rows, cols } = grid;
    const ink = rows.map(r => cols.map(c => inkOf(G, c.x0, c.x1, r.y0, r.y1)));
    const minInk = 6;
    const cell = (ri, ci) => ({ x0: cols[ci].x0, x1: cols[ci].x1, y0: rows[ri].y0, y1: rows[ri].y1 });
    try {
      // 列用途：看前 3 行有内容的格子
      const filled = rows.map((_, ri) => ink[ri].filter(v => v >= minInk).length);
      const sample = rows.map((_, ri) => ri).filter(ri => filled[ri] >= 3).slice(0, 3);
      if (!sample.length) return null;
      const score = cols.map(() => ({ code: 0, spec: 0, qty: 0 }));
      for (const ri of sample) for (let ci = 0; ci < cols.length; ci++) {
        if (ink[ri][ci] < minInk) continue;
        const t = await ocrCell(w, im, cell(ri, ci), VAR_A[0], '0123456789.L-');
        if (/^\D*0[12]\d{3}\D*$/.test(t) || /^0[12]\d{3}0?$/.test(t)) score[ci].code++;
        if (SPEC_RE.test(t) && /L/.test(t)) score[ci].spec++;
        if (/^\d{1,6}\.\d{2,3}$/.test(t)) score[ci].qty++;
      }
      const pickCol = (k, after) => { let b = -1; cols.forEach((_, ci) => { if (ci > after && score[ci][k] > 0 && (b < 0 || score[ci][k] > score[b][k])) b = ci; }); return b; };
      const cCode = pickCol('code', -1); if (cCode < 0) return null;
      const cSpec = pickCol('spec', cCode);
      // 数量：编码列右边第一个像数量的列（单价、金额通常是空的）
      let cQty = -1; for (let ci = cCode + 1; ci < cols.length; ci++) if (score[ci].qty > 0 && ci !== cSpec) { cQty = ci; break; }
      if (cQty < 0) return null;
      // 数据行 = 编码格有内容；合计行 = 数据行之后、编码格空而数量格有内容的那一行
      const data = [], H = rows.length; let totalRow = -1;
      for (let ri = 0; ri < H; ri++) {
        if (ink[ri][cCode] >= minInk && ink[ri][cQty] >= minInk) data.push(ri);
        else if (data.length && ink[ri][cCode] < minInk && ink[ri][cQty] >= minInk) totalRow = ri;
      }
      // 合计行常被挤得很矮（滚动条/最后一行），不在 rows 里时，从最后一条线往下找
      let totalCell = totalRow >= 0 ? cell(totalRow, cQty) : null;
      if (!totalCell) {
        const last = rows[rows.length - 1].y1, y1 = Math.min(G.H - 1, last + grid.rh * 1.6);
        if (inkOf(G, cols[cQty].x0, cols[cQty].x1, last, y1) >= minInk) totalCell = { x0: cols[cQty].x0, x1: cols[cQty].x1, y0: last, y1 };
      }
      const out = data.map((ri, i) => ({ ri, rowNo: i + 1, code: '', spec: '', cands: [], codeC: [], specC: [] }));
      const readRow = async (it, VS) => {
        for (const V of VS) {
          const tc = await ocrCell(w, im, cell(it.ri, cCode), V, '0123456789'); const mc = CODE_RE.exec(tc); if (mc) it.codeC.push(mc[0]);
          if (cSpec >= 0) { const ts = await ocrCell(w, im, cell(it.ri, cSpec), V, '0123456789.L'); const ms = SPEC_RE.exec(ts); if (ms) it.specC.push(ms[1]); }
          const q = parseQty(await ocrCell(w, im, cell(it.ri, cQty), V, '0123456789.')); if (isFinite(q)) it.cands.push(q);
        }
        const top = a => { const v = voteOf(a); return v.length ? v[0][0] : ''; };
        it.code = top(it.codeC); it.spec = String(top(it.specC));
      };
      let done = 0;
      for (const it of out) { await readRow(it, VAR_A); done++; try { onProgress && onProgress({ status: 'recognizing text', progress: done / out.length }); } catch (e) { } }
      const totalC = [];
      if (totalCell) for (const V of VAR_A.concat(VAR_B)) { const q = parseQty(await ocrCell(w, im, totalCell, V, '0123456789.')); if (isFinite(q)) totalC.push(q); }
      let chk = finalizeQty(out, totalC);
      if (chk.checked === false || out.some(it => !it.votes.length)) {   // 对不上：看不准的行再多试几种
        const weak = out.filter(it => !it.votes.length || it.votes.length > 1 || it.votes[0][1] < VAR_A.length);
        for (const it of (weak.length ? weak : out)) await readRow(it, VAR_B);
        chk = finalizeQty(out, totalC);
        if (chk.checked === false) {   // 还是不对：把所有行都补测一遍
          for (const it of out) if (!weak.includes(it)) await readRow(it, VAR_B);
          chk = finalizeQty(out, totalC);
        }
      }
      const sum = out.reduce((a, b) => a + (isFinite(b.qty) ? b.qty : 0), 0);
      return { rows: out.map(it => ({ rowNo: it.rowNo, code: it.code, spec: it.spec, qty: isFinite(it.qty) ? it.qty : null, sure: !!it.sure && isFinite(it.qty), cands: it.cands })),
               total: chk.total, totalOk: chk.checked, diff: chk.total != null ? Math.round((chk.total - sum) * 1000) / 1000 : null };
    } finally {
      await w.setParameters({ tessedit_pageseg_mode: '11', tessedit_char_whitelist: '' });
    }
  }
  /** 每日用量截图：先按表格逐格识别；表格线找不到（比如手机拍的照片）再用整图识别 */
  async function recognizeDaily(src, onProgress) {
    let g = null;
    try { g = await recognizeU8Grid(src, onProgress); } catch (e) { console.warn('grid ocr fail', e); }
    if (g && g.rows.length) return dailyFromRows(g.rows, g);   // 编码没看清的行也留着（标出来让人核对），不悄悄丢掉
    const res = await recognizeTable(src, onProgress);
    return parseDailyUsage(res);
  }
  const KNOWN_SPECS = { gas: ['40', '15', '10', '2'], liq: ['10', '20', '25', '30', '35', '80', '100', '175', '195', '210', '500', '1000'] };
  function dailyFromRows(rows, g) {
    const gas = {}, liq = {}, out = [];
    rows.forEach(it => {
      const code = it.code || '', kind = /^01/.test(code) ? 'gas' : /^02/.test(code) ? 'liq' : null, bag = kind === 'gas' ? gas : liq;
      if (kind && it.spec && it.qty != null) bag[it.spec] = Math.round(((bag[it.spec] || 0) + it.qty) * 1000) / 1000;
      const known = kind && KNOWN_SPECS[kind].includes(String(it.spec));   // 规格认成表里没有的（如 500 认成 00）也标出来让人核对
      out.push({ rowNo: it.rowNo, code, kind, spec: it.spec, qty: it.qty, sure: !!(it.sure && it.spec && kind && known), line: '' });
    });
    return { gas, liq, rows: out, total: g.total, totalOk: g.totalOk, diff: g.diff, mode: 'grid' };
  }
  return { recognizeSlip, parseSlips, getWorker, recognize, recognizeTable, parseU8Inbound, parseDailyUsage, recognizeDaily, recognizeU8Grid, detectGridOf: async src => detectGrid(grayOf(await loadImg(src))), lines, specToken };
})();
