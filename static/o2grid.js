/* 报表表格核心（移植 v82 O2：地址 / 公式平移 / 公式计算），与服务器 xlgrid.py 同一套规则 */
'use strict';
const O2 = (function () {
  function colToNum(c) { let n = 0; for (let i = 0; i < c.length; i++) n = n * 26 + (c.charCodeAt(i) - 64); return n; }
  function numToCol(n) { let s = ''; while (n > 0) { const m = (n - 1) % 26; s = String.fromCharCode(65 + m) + s; n = Math.floor((n - 1) / 26); } return s; }
  function splitAddr(a) { const m = /^\$?([A-Z]{1,3})\$?(\d+)$/.exec(a); return m ? { c: m[1], r: +m[2] } : null; }
  function mapRefs(f, fn) {
    let out = '', i = 0;
    const re = /("(?:[^"]|"")*")|((?:'[^']+'|[A-Za-z_\u4e00-\u9fa5][\w\u4e00-\u9fa5.]*)!)?(\$?)([A-Z]{1,3})(\$?)(\d+)(?![\w(])/g;
    return String(f).replace(re, (all, str, sheet, d1, col, d2, row, off, whole) => {
      if (str) return all;
      const prev = off > 0 ? whole[off - 1] : '';
      if (/[A-Za-z_\d.]/.test(prev)) return all;
      if (sheet) return all;
      const nr = fn(+row, d2 === '$');
      if (nr == null) return '#REF!';
      return d1 + col + d2 + nr;
    });
  }
  function shiftFormula(f, at, delta) { // 插入：>=at 的行号 +delta；删除(delta<0)：等于被删行 → #REF!
    return mapRefs(f, (r) => {
      if (delta > 0) return r >= at ? r + delta : r;
      if (r === at) return null;
      return r > at ? r + delta : r;
    });
  }
  function shiftRange(ref, at, delta) {
    const [a, b] = ref.split(':'); const A = splitAddr(a), B = splitAddr(b || a);
    let r1 = A.r, r2 = B.r;
    if (delta > 0) { if (r1 >= at) r1 += delta; if (r2 >= at) r2 += delta; }
    else { if (r1 === at && r2 === at) return null; if (r1 > at) r1 += delta; if (r2 >= at) r2 += delta; }
    if (r2 < r1) return null;
    const out = A.c + r1 + ':' + B.c + r2;
    return out;
  }
  function insertRow(tab, at /*1-based*/, rowObj) {
    tab.rows.splice(at - 1, 0, rowObj || { c: {} });
    tab.rows.forEach(r => { if (!r) return; Object.values(r.c).forEach(c => { if (c.f) c.f = shiftFormula(c.f, at, 1); }); });
    tab.merges = tab.merges.map(m => shiftRange(m, at, 1)).filter(Boolean);
  }
  function deleteRow(tab, at) {
    tab.rows.splice(at - 1, 1);
    tab.rows.forEach(r => { if (!r) return; Object.values(r.c).forEach(c => { if (c.f) c.f = shiftFormula(c.f, at, -1); }); });
    tab.merges = tab.merges.map(m => shiftRange(m, at, -1)).filter(Boolean);
  }

  // ---- 公式计算（支持 + - * / ^ 括号、SUM/ROUND/ABS/MIN/MAX/AVERAGE/IF 比较，覆盖原表全部公式）----
  const ERR = v => typeof v === 'string' && v[0] === '#';
  function makeEvaluator(tab) {
    const cache = new Map(), busy = new Set();
    function cellVal(col, r) {
      const key = col + r;
      if (cache.has(key)) return cache.get(key);
      const row = tab.rows[r - 1]; const c = row && row.c[col];
      let v = null;
      if (c) {
        if (c.f != null && c.f !== '') {
          if (busy.has(key)) v = '#循环';
          else { busy.add(key); try { v = evalF(c.f, r); } catch (e) { v = '#ERR'; } busy.delete(key); }
        } else if (c.v != null) v = c.v;
      }
      cache.set(key, v); return v;
    }
    function evalF(f, selfRow) {
      const s = String(f); let i = 0;
      const peek = () => s[i], ws = () => { while (s[i] === ' ') i++; };
      function num(v) { if (v == null || v === '') return 0; if (typeof v === 'number') return v; if (ERR(v)) throw v; const n = Number(v); if (!isNaN(n) && String(v).trim() !== '') return n; throw '#VALUE!'; }
      function primary() {
        ws(); const ch = s[i];
        if (ch === '(') { i++; const v = comp(); ws(); if (s[i] === ')') i++; return v; }
        if (ch === '-') { i++; return -num(power()); }
        if (ch === '+') { i++; return num(power()); }
        if (ch === '"') { let j = i + 1, out = ''; while (j < s.length) { if (s[j] === '"') { if (s[j + 1] === '"') { out += '"'; j += 2; continue; } break; } out += s[j++]; } i = j + 1; return out; }
        let m = /^\d+(\.\d+)?([eE][+-]?\d+)?|^\.\d+/.exec(s.slice(i));
        if (m) { i += m[0].length; return parseFloat(m[0]); }
        m = /^\$?([A-Z]{1,3})\$?(\d+)(?::\$?([A-Z]{1,3})\$?(\d+))?/.exec(s.slice(i));
        if (m && !/^[A-Z]+\(/.test(s.slice(i))) {
          i += m[0].length;
          if (m[3]) return { range: [m[1], +m[2], m[3], +m[4]] };
          return cellVal(m[1], +m[2]);
        }
        m = /^([A-Z][A-Z0-9.]*)\(/.exec(s.slice(i));
        if (m) {
          i += m[0].length; const args = [];
          ws(); if (s[i] === ')') { i++; } else { while (true) { args.push(comp()); ws(); if (s[i] === ',') { i++; continue; } if (s[i] === ')') { i++; } break; } }
          return callFn(m[1], args);
        }
        if (s.slice(i, i + 5) === '#REF!') { i += 5; throw '#REF!'; }
        throw '#NAME?';
      }
      function flat(args) {
        const out = [];
        args.forEach(a => {
          if (a && a.range) { const [c1, r1, c2, r2] = a.range; for (let r = Math.min(r1, r2); r <= Math.max(r1, r2); r++) for (let c = Math.min(colToNum(c1), colToNum(c2)); c <= Math.max(colToNum(c1), colToNum(c2)); c++) { const v = cellVal(numToCol(c), r); if (ERR(v)) throw v; if (typeof v === 'number') out.push(v); } }
          else { if (ERR(a)) throw a; out.push(num(a)); }
        });
        return out;
      }
      function callFn(n, a) {
        switch (n) {
          case 'SUM': return flat(a).reduce((x, y) => x + y, 0);
          case 'AVERAGE': { const v = flat(a); return v.length ? v.reduce((x, y) => x + y, 0) / v.length : '#DIV/0!'; }
          case 'MIN': { const v = flat(a); return v.length ? Math.min(...v) : 0; }
          case 'MAX': { const v = flat(a); return v.length ? Math.max(...v) : 0; }
          case 'ABS': return Math.abs(num(a[0]));
          case 'ROUND': { const p = Math.pow(10, num(a[1] || 0)); return Math.round(num(a[0]) * p) / p; }
          case 'IF': return (a[0] && !(a[0] === 0)) ? (a[1] === undefined ? true : a[1]) : (a[2] === undefined ? false : a[2]);
          default: throw '#NAME?';
        }
      }
      function power() { let v = primary(); ws(); while (s[i] === '^') { i++; v = Math.pow(num(v), num(primary())); ws(); } return v; }
      function term() { let v = power(); ws(); while (s[i] === '*' || s[i] === '/') { const op = s[i++]; const r = power(); if (op === '*') v = num(v) * num(r); else { const d = num(r); if (d === 0) throw '#DIV/0!'; v = num(v) / d; } ws(); } return v; }
      function expr() { let v = term(); ws(); while (s[i] === '+' || s[i] === '-' || s[i] === '&') { const op = s[i++]; const r = term(); if (op === '&') v = String(v ?? '') + String(r ?? ''); else v = op === '+' ? num(v) + num(r) : num(v) - num(r); ws(); } return v; }
      function comp() { let v = expr(); ws(); const m = /^(<=|>=|<>|=|<|>)/.exec(s.slice(i)); if (m) { i += m[0].length; const r = expr(); const a = typeof v === 'number' ? v : v, b = r; switch (m[0]) { case '=': return a == b; case '<>': return a != b; case '<': return a < b; case '>': return a > b; case '<=': return a <= b; case '>=': return a >= b; } } return v; }
      try { const v = comp(); return (v && v.range) ? '#VALUE!' : v; } catch (e) { return typeof e === 'string' ? e : '#ERR'; }
    }
    return { val: cellVal, reset() { cache.clear(); } };
  }
  function lastRow(tab) { for (let i = tab.rows.length - 1; i >= 0; i--) { const r = tab.rows[i]; if (r && Object.keys(r.c).length) return i + 1; } return 1; }
  return { colToNum, numToCol, splitAddr, makeEvaluator, insertRow, deleteRow, shiftFormula, lastRow, ERR };
})();
