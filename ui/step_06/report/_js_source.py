"""Embedded JavaScript for the Data Quality Report.

``REPORT_JS`` is the design handoff's ``reference/report.js``
embedded verbatim: drill-down tables built with
``createElement``/``textContent`` only (no ``innerHTML``), per-list
sort/filter, global search, expand/collapse all, click-to-expand
truncated values, and before/afterprint handlers.
"""

# The leading newline of the literal is sliced off so the constant
# matches the handoff file byte-for-byte.
REPORT_JS = """
(function(){
'use strict';
document.documentElement.classList.add('js');
var DATA = JSON.parse(document.getElementById('report-data').textContent);
var CAP = DATA.caps.drill_rows;
function el(tag, cls, text){ var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
function fmt(n){ return Number(n).toLocaleString('en-US'); }
function bucket(s,g,y){ return s>=g?'green':s>=y?'yellow':'red'; }
function badge(s){ var b = bucket(s, DATA.green, DATA.yellow); var sp = el('span','badge b-'+b); sp.appendChild(el('i')); sp.appendChild(document.createTextNode({green:'Green',yellow:'Yellow',red:'Red'}[b])); return sp; }
function cellFor(v){ var td = el('td'); if (v === null || v === undefined || v === '') { td.className = 'null'; td.textContent = 'null'; } else if (typeof v === 'number') { td.className = 'num'; td.textContent = String(v); } else { var sp = el('span','tv', String(v)); sp.title = String(v); td.appendChild(sp); } return td; }
// ---- drill-down: rows stored once per DP, filtered client-side by rule / CDE / dimension
function renderDrill(box){
  if (box.dataset.done) return; box.dataset.done = '1';
  var parts = box.dataset.drill.split('|'), dp = DATA.dps[parts[0]], key = parts[1], kind = key.split(':')[0], name = key.slice(kind.length+1);
  var ruleIdx = [];
  dp.ruleColumns.forEach(function(rc, i){ var r = dp.rules[rc.id]; if (!r) return; if (kind === 'rule' ? rc.id === name : kind === 'cde' ? r.cdes.indexOf(name) >= 0 : r.dim === name) ruleIdx.push(i); });
  var rows = dp.store.filter(function(r){ return ruleIdx.some(function(i){ return r.f[i] === 0; }); }).slice(0, CAP);
  var total = Number(box.dataset.total);
  var cap = el('p','cap');
  cap.textContent = rows.length < total ? 'Showing the ' + fmt(rows.length) + ' lowest-scoring of ' + fmt(total) + ' failing rows (the report embeds the ' + fmt(DATA.caps.row_store) + ' lowest-scoring rows of this Data Product once; the CSV export carries every row).' : 'Showing all ' + fmt(rows.length) + ' failing rows, worst first.';
  if (!rows.length) { cap.textContent = fmt(total) + ' rows fail ' + box.dataset.label + ', but none of them is among the ' + fmt(DATA.capsrow_store || DATA.caps.row_store) + ' lowest-scoring rows embedded in this report - use the CSV export to inspect them.'; box.appendChild(cap); return; }
  var tw = el('div','tw'), table = el('table','rows'), thead = el('thead'), trh = el('tr');
  var heads = ['row_score','status'].concat(dp.columns, dp.refColumns, dp.ruleColumns.map(function(c){return c.header;}));
  var nBase = 2 + dp.columns.length, nRef = nBase + dp.refColumns.length;
  heads.forEach(function(h, i){ var th = el('th', i >= nRef ? 'th-rule' : i >= nBase ? 'th-ref' : ''); if (i >= nRef && ruleIdx.indexOf(i - nRef) >= 0) th.classList.add('hl'); var sp = el('span','tv',h); sp.title = h; th.appendChild(sp); trh.appendChild(th); });
  thead.appendChild(trh); table.appendChild(thead);
  var tb = el('tbody');
  rows.forEach(function(r){ var tr = el('tr'); var t0 = el('td','num'); var b = el('b', null, r.s.toFixed(2)); t0.appendChild(b); tr.appendChild(t0); var t1 = el('td'); t1.appendChild(badge(r.s)); tr.appendChild(t1); r.v.forEach(function(v){ tr.appendChild(cellFor(v)); }); r.r.forEach(function(v){ tr.appendChild(cellFor(v)); }); r.f.forEach(function(f){ var td = el('td','num flag ' + (f ? 'f-pass' : 'f-fail'), f ? '100' : '0'); tr.appendChild(td); }); tb.appendChild(tr); });
  table.appendChild(tb); tw.appendChild(table); box.appendChild(cap); box.appendChild(tw);
}
document.querySelectorAll('details').forEach(function(d){ d.addEventListener('toggle', function(){ if (d.open) d.querySelectorAll('.drill').forEach(renderDrill); }); });
// ---- truncated values: click to expand (never alters the data)
document.addEventListener('click', function(e){ var tv = e.target.closest('.tv'); if (tv && tv.closest('td,th,summary')) { tv.classList.toggle('open'); } });
// ---- per-list sort / filter
document.querySelectorAll('.toolbar').forEach(function(tb){
  var list = tb.nextElementSibling; if (!list || !list.classList.contains('gl')) return;
  var rows = function(){ return Array.prototype.slice.call(list.querySelectorAll('.gl-row')); };
  var state = { filter: 'all', issues: false };
  function apply(){ var n = 0; rows().forEach(function(r){ var ok = true; if (state.filter === 'evaluated') ok = r.dataset.status === 'evaluated'; else if (state.filter === 'not-computed' || state.filter === 'not-evaluated') ok = r.dataset.status === state.filter; else if (state.filter === 'below') ok = r.dataset.below === '1'; else if (state.filter === 'blocking') ok = r.dataset.blocking === '1'; if (state.issues && r.dataset.below !== '1') ok = false; if (r.dataset.searchHide === '1') ok = false; r.classList.toggle('hidden', !ok); if (ok) n++; }); var c = tb.querySelector('.tb-count'); if (c) c.textContent = n + ' of ' + rows().length + ' shown'; }
  tb.querySelectorAll('[data-filter]').forEach(function(b){ b.addEventListener('click', function(){ tb.querySelectorAll('[data-filter]').forEach(function(x){ x.classList.remove('on'); }); b.classList.add('on'); state.filter = b.dataset.filter; apply(); }); });
  var chk = tb.querySelector('[data-only-issues]'); if (chk) chk.addEventListener('change', function(){ state.issues = chk.checked; apply(); });
  tb.querySelectorAll('[data-sort]').forEach(function(b){ b.addEventListener('click', function(){ var key = b.dataset.sort, dir = b.dataset.dir || 'asc'; var rs = rows(); rs.sort(function(a, c){ var x = a.dataset[key], y = c.dataset[key]; if (key !== 'name') { x = Number(x); y = Number(y); return dir === 'asc' ? x - y : y - x; } return x < y ? -1 : x > y ? 1 : 0; }); rs.forEach(function(r){ list.appendChild(r); }); b.dataset.dir = key === 'name' ? 'asc' : (dir === 'asc' ? 'desc' : 'asc'); if (key !== 'name') b.textContent = b.textContent.replace(/[↑↓]/, dir === 'asc' ? '↓' : '↑'); }); });
  list.__apply = apply; apply();
});
// ---- global search across CDEs, dimensions and rules (all Data Products)
var search = document.querySelector('.tn-search input'), hits = document.querySelector('.tn-hits');
if (search) search.addEventListener('input', function(){ var q = search.value.trim().toLowerCase(), n = 0; document.querySelectorAll('.gl-row').forEach(function(r){ var hide = q && (r.dataset.search || '').indexOf(q) < 0; r.dataset.searchHide = hide ? '1' : '0'; if (q && !hide) n++; }); document.querySelectorAll('.gl').forEach(function(l){ if (l.__apply) l.__apply(); }); hits.textContent = q ? n + ' hit' + (n === 1 ? '' : 's') : ''; });
// ---- expand / collapse all
document.querySelectorAll('[data-expand]').forEach(function(b){ b.addEventListener('click', function(){ var open = b.dataset.expand === '1'; document.querySelectorAll('details').forEach(function(d){ if (open && d.classList.contains('gl-row') && d.classList.contains('hidden')) return; d.open = open; }); }); });
// ---- print: open every section so the PDF is complete, then restore
var wasOpen = null;
window.addEventListener('beforeprint', function(){ wasOpen = []; document.querySelectorAll('details').forEach(function(d){ wasOpen.push(d.open); d.open = true; }); });
window.addEventListener('afterprint', function(){ if (!wasOpen) return; var i = 0; document.querySelectorAll('details').forEach(function(d){ d.open = wasOpen[i++]; }); wasOpen = null; });
})();
"""[1:]
