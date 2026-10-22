/* 名称设置（显示名称替换），桌面端、手机端、访客页共用；不依赖 core.js */
'use strict';
/* ===== 名称设置：只改界面上显示的文字（数据、下载的表不变） =====
   规则：整段文字完全等于「原名称」时换成新名称；句子里用「」括起来的原名称也换。
   不动：输入框里的内容、可编辑格子、报表数据格、带 data-nonm 的区域；<option> 先把原文记成 value，提交的仍是原值。 */
const NM = { map: {}, re: null, obs: null };
const NM_SKIP = 'script,style,textarea,input,select[data-nonm],[contenteditable="true"],.rt tbody,[data-nonm]';
function nmSet(map) {
  NM.map = {}; Object.entries(map || {}).forEach(([k, v]) => { k = String(k).trim(); v = String(v || '').trim(); if (k && v && k !== v) NM.map[k] = v; });
  const keys = Object.keys(NM.map).sort((a, b) => b.length - a.length);
  NM.re = keys.length ? new RegExp('「(' + keys.map(k => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')」', 'g') : null;
  if (!keys.length) { if (NM.obs) { NM.obs.disconnect(); NM.obs = null; } return; }
  nmApply(document.body); if (document.title && NM.map[document.title]) document.title = NM.map[document.title];
  if (!NM.obs) {
    NM.obs = new MutationObserver(ms => { for (const m of ms) { if (m.type === 'characterData') nmText(m.target); else m.addedNodes.forEach(n => nmApply(n)); } });
    NM.obs.observe(document.body, { childList: true, subtree: true, characterData: true });
  }
}
/** 给一个原名称取当前显示名（JS 里拼字符串时也可以用） */
function nm(t) { return (NM.map && NM.map[t]) || t; }
function nmText(n) {
  const t = n.data; if (!t || n.__nm === t) return;
  const p = n.parentElement; if (!p || p.closest(NM_SKIP)) return;
  const k = t.trim(); let out = t;
  if (NM.map[k]) {
    if (p.tagName === 'OPTION' && !p.hasAttribute('value')) p.setAttribute('value', k);
    out = t.replace(k, NM.map[k]);
  } else if (NM.re && t.includes('「')) out = t.replace(NM.re, (m, o) => '「' + NM.map[o] + '」');
  n.__nm = out; if (out !== t) n.data = out;
}
function nmEl(e) {
  for (const a of ['placeholder', 'title']) { const v = e.getAttribute && e.getAttribute(a); if (v && NM.map[v.trim()]) e.setAttribute(a, NM.map[v.trim()]); }
}
function nmApply(root) {
  if (!root || !NM.re) return;
  if (root.nodeType === 3) return nmText(root);
  if (root.nodeType !== 1 || root.closest(NM_SKIP)) return;
  nmEl(root);
  const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, { acceptNode: n => n.nodeType === 1 && n.matches(NM_SKIP) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
  let n; while ((n = w.nextNode())) { if (n.nodeType === 3) nmText(n); else nmEl(n); }
}
