// How the Workshop looks: a few themes, your own accent and background colours, and calmer
// animations. Kept in this browser (localStorage "ws-theme") and put on before the page shows, so
// there's no flash of the old colours. Settings → Appearance.
const TH_THEMES = {
  ashlands: {label: 'Ashlands', about: 'The usual: dark ash and gold', v: {}},
  telvanni: {label: 'Telvanni', about: 'Mushroom-tower purple', v: {
    bg: '#120f17', panel: '#1a1621', panel2: '#221c2b', line: '#322a3d', line2: '#45395a', text: '#e9e1f2', muted: '#a097b2', faint: '#837999',
    gold: '#b98be0', gold2: '#d9b8ff', hover: '#261f30', sel: '#33264a', deep: '#0d0b11', bg2: '#16121c', bg3: '#1c1724', line0: '#1f1a27', goldline: '#6e4f8f'}},
  redoran: {label: 'Redoran', about: 'Red-brown, like their bug-shell armour', v: {
    bg: '#150f0c', panel: '#1e1511', panel2: '#281c17', line: '#3c2a22', line2: '#523a2f', text: '#efe0d4', muted: '#a99183', faint: '#8b7467',
    gold: '#d9824f', gold2: '#f4ac7c', hover: '#2d1f19', sel: '#40271b', deep: '#100b09', bg2: '#19110e', bg3: '#211713', line0: '#251a15', goldline: '#8d5233'}},
  hlaalu: {label: 'Hlaalu', about: 'Olive and amber, like their halls in Balmora', v: {
    bg: '#11130d', panel: '#191c13', panel2: '#212519', line: '#313724', line2: '#444c31', text: '#e6e8d6', muted: '#9ea38a', faint: '#80876c',
    gold: '#d6b44a', gold2: '#f1d77e', hover: '#23271b', sel: '#333a1f', deep: '#0d0f0a', bg2: '#15180f', bg3: '#1b1f14', line0: '#1f2318', goldline: '#8a7a34'}},
  dagoth: {label: 'Dagoth', about: 'Black, with the glow of Red Mountain', v: {
    // (the user's own "New Dagoth", 2026-10-24: pure black, the deep red of the accents and lines, near-black
    // main buttons, a blood-dark 3D view)
    bg: '#000000', panel: '#000000', panel2: '#0f0e0e', line: '#4d0009', line2: '#713339', text: '#f2e6e4', muted: '#a58d8d', faint: '#8c7878',
    gold: '#c70a00', gold2: '#d8544c', hover: '#181717', sel: '#380300', deep: '#000000', bg2: '#000000', bg3: '#000000', line0: '#2a0005', goldline: '#770600',
    red: '#ff5a3c', amber: '#ff9a3c', blue: '#7fa7d6', green: '#8fbf7a', view3d: '#330000'}, btn: '#110403'},
  dwemer: {label: 'Dwemer', about: 'Bronze and verdigris', v: {
    bg: '#0e1211', panel: '#151b19', panel2: '#1c2421', line: '#2b3833', line2: '#3c4d46', text: '#e1ebe5', muted: '#93a49b', faint: '#788a80',
    gold: '#c8964a', gold2: '#e8bd78', hover: '#1f2925', sel: '#2e3426', deep: '#0b0e0d', bg2: '#121816', bg3: '#18201d', line0: '#1b2420', goldline: '#7d6033'}},
  imperial: {label: 'Imperial', about: 'Ivory marble, Septim red and old gold', light: true, v: {
    // (marble rather than parchment: cooler ivory panels with firm warm lines, the Legion's red for what
    // matters and a deep gold for the rest)
    bg: '#e4dccb', panel: '#f3eee3', panel2: '#e9e1d0', line: '#c9b994', line2: '#a9956a', text: '#221a12', muted: '#5c4d36', faint: '#6c5d45',
    gold: '#8e1d1d', gold2: '#5f1010', hover: '#e4d9c0', sel: '#e2c9a2', deep: '#faf7f0', bg2: '#dfd5c0', bg3: '#ece5d5', line0: '#d7cbb0', goldline: '#b8902f',
    red: '#9f2d1d', amber: '#9c6a0c', blue: '#2e5d97', green: '#4b7833'}},
  indoril: {label: 'Indoril', about: 'Light: Mournhold grey stone and pale blue panels, with deep Almalexia blue', light: true, v: {
    // (the user's own theme, made from High contrast and liked enough to be the light preset, 2026-10-24:
    // near-black text and lines on grey and pale blue, white main buttons, a dark 3D view)
    bg: '#afadb3', panel: '#dce0ea', panel2: '#d0d4dd', line: '#0d0326', line2: '#100823', text: '#1a1919', muted: '#121212', faint: '#2a292a',
    gold: '#12327d', gold2: '#0d2358', hover: '#c9ccd5', sel: '#a3afcb', deep: '#c7c6ca', bg2: '#bcbcc4', bg3: '#ced1da', line0: '#565065', goldline: '#516393',
    red: '#df2201', amber: '#8d6411', blue: '#4480c5', green: '#2e8f05', view3d: '#171717'}, btn: '#ffffff'},
  contrast: {label: 'High contrast', about: 'Black, white and bright yellow: easiest to read', v: {
    bg: '#000000', panel: '#0a0a0a', panel2: '#161616', line: '#5c5c5c', line2: '#8c8c8c', text: '#ffffff', muted: '#e2e2e2', faint: '#bdbdbd',
    gold: '#ffd23f', gold2: '#ffe680', hover: '#232323', sel: '#3d3400', deep: '#000000', bg2: '#0a0a0a', bg3: '#111111', line0: '#333333', goldline: '#b39400'}},
};

// The usual look's own colours (index.html :root), for presets that leave some of them alone
const TH_USUAL = {bg: '#13110d', panel: '#1b1813', panel2: '#221e18', line: '#342d23', line2: '#463c2e', text: '#ebe2cf', muted: '#9c917c', faint: '#6e6555',
  gold: '#d2a85a', gold2: '#f0cd87', red: '#e0705b', amber: '#e2b04a', blue: '#7fa7d6', green: '#8fbf7a', btn: '#5a4420', view3d: '#0d0c0a'};
// What you can set in your own (Custom) theme; the in-between shades are worked out from these
const TH_KEYS = [['bg', 'Background'], ['panel', 'Panels and windows'], ['text', 'Text'], ['muted', 'Quieter text (notes, IDs)'],
  ['gold', 'Accent: headings, links, what\'s chosen'], ['line', 'Lines and borders'], ['btn', 'Main buttons'],
  ['red', 'Danger and errors'], ['amber', 'Warnings'], ['green', 'All right, done'], ['blue', 'Notes and information'], ['view3d', '3D view background (indoors)']];
const TH_HEAD_FONTS = {cinzel: ['Cinzel (the usual)', 'Cinzel,serif'], georgia: ['Georgia', 'Georgia,serif'], palatino: ['Palatino', '"Palatino Linotype",Palatino,serif'],
  segoe: ['Segoe UI', '"Segoe UI",system-ui,sans-serif'], verdana: ['Verdana', 'Verdana,sans-serif'], inter: ['Inter', 'Inter,sans-serif']};
const TH_BODY_FONTS = {inter: ['Inter (the usual)', 'Inter,"Segoe UI",system-ui,sans-serif'], segoe: ['Segoe UI', '"Segoe UI",system-ui,sans-serif'],
  verdana: ['Verdana: wide and very clear', 'Verdana,sans-serif'], tahoma: ['Tahoma', 'Tahoma,sans-serif'], georgia: ['Georgia', 'Georgia,serif']};
const TH_SIZES = [[0.9, 'Smaller'], [1, 'The usual'], [1.1, 'A bit bigger'], [1.2, 'Bigger'], [1.35, 'Much bigger']];

function thGet(){ try { return Object.assign({theme: 'ashlands', accent: '', bg: '', calm: false}, JSON.parse(localStorage.getItem('ws-theme') || '{}')); } catch (e){ return {theme: 'ashlands', accent: '', bg: '', calm: false}; } }
// (kept in this browser and in the Workshop's settings file too, so it survives a new port, a new browser and updates)
let thPostT = 0;
function thSave(t){
  try { localStorage.setItem('ws-theme', JSON.stringify(t)); } catch (e){}
  clearTimeout(thPostT);
  thPostT = setTimeout(() => fetch('/api/settings', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({theme: t})}).catch(() => {}), 600);
}

// a colour's brightness (0 dark, 1 light)
function thLum(hex){ const n = parseInt(hex.slice(1), 16); return (0.299 * (n >> 16 & 255) + 0.587 * (n >> 8 & 255) + 0.114 * (n & 255)) / 255; }
const thHex = s => /^#[0-9a-f]{6}$/i.test(s || '');
// a in b, p% of the way (as #rrggbb, so it can go in a colour box)
function thMix(a, b, p){
  const x = parseInt(a.slice(1), 16), y = parseInt(b.slice(1), 16), f = p / 100;
  return '#' + [16, 8, 0].map(s => Math.round((x >> s & 255) * (1 - f) + (y >> s & 255) * f).toString(16).padStart(2, '0')).join('');
}
// how readable one colour is on another (the WCAG contrast ratio: 1 none, 21 black on white; 4.5 is easy to read)
function thContrast(a, b){
  const L = h => { const n = parseInt(h.slice(1), 16); return [16, 8, 0].map(s => { const c = (n >> s & 255) / 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); })
    .reduce((t, c, i) => t + c * [0.2126, 0.7152, 0.0722][i], 0); };
  const p = L(a), q = L(b); return (Math.max(p, q) + 0.05) / (Math.min(p, q) + 0.05);
}
// a preset's colours, as a Custom theme starts from them
function thFromPreset(name){
  const T = TH_THEMES[name] || TH_THEMES.contrast, v = Object.assign({}, TH_USUAL, T.v);
  const c = {};
  for (const [k] of TH_KEYS) c[k] = v[k];
  if (T.btn) c.btn = T.btn;
  else if (T.v.gold) c.btn = thMix(v.panel, v.gold, T.light ? 13 : 30);
  if (name === 'contrast') c.view3d = '#000000';
  return {from: TH_THEMES[name] ? name : 'contrast', c, head: 'cinzel', body: 'inter', size: 1};
}
// every shade the pages use, from the Custom theme's few colours
function thCustomVars(cu){
  const c = Object.assign({}, thFromPreset(cu.from).c, cu.c || {});
  for (const k of Object.keys(c)) if (!thHex(c[k])) c[k] = TH_USUAL[k];
  const light = thLum(c.bg) > 0.55, far = light ? '#000000' : '#ffffff';
  return {light, v: {bg: c.bg, deep: thMix(c.bg, light ? '#ffffff' : '#000000', 30), bg2: thMix(c.bg, c.panel, 30), bg3: thMix(c.bg, c.panel, 70),
    panel: c.panel, panel2: thMix(c.panel, c.text, 6), hover: thMix(c.panel, c.text, 10), sel: thMix(c.panel, c.gold, 28),
    line: c.line, line2: thMix(c.line, c.text, 22), line0: thMix(c.line, c.bg, 45),
    text: c.text, muted: c.muted, faint: thMix(c.muted, c.bg, 15),
    gold: c.gold, gold2: thMix(c.gold, far, 30), goldline: thMix(c.gold, c.bg, 40),
    red: c.red, amber: c.amber, green: c.green, blue: c.blue, view3d: c.view3d}, btn: c.btn};
}
// the 3D view's background indoors (world3d.js)
function thView3d(){ const v = getComputedStyle(document.documentElement).getPropertyValue('--view3d').trim(); return thHex(v) ? v : '#0d0c0a'; }

// Fonts and text size: the pages' own rules name Cinzel, Inter and sizes in px, so each style sheet is gone over once
// and those become var(--font-head), var(--font-body) and calc(… * var(--fs)), with the usual ones as the fallback.
const TH_DONE = new WeakSet();
function thFontRules(sheet){
  if (TH_DONE.has(sheet)) return;
  let rules; try { rules = sheet.cssRules; } catch (e){ return; }
  TH_DONE.add(sheet);
  const walk = list => { for (const r of list){
    if (r.cssRules && !r.style) { walk(r.cssRules); continue; }
    const s = r.style; if (!s || r.type === 5) continue;              // (not the @font-face rules themselves)
    if (/^[\d.]+px$/.test(s.fontSize)) s.fontSize = `calc(${s.fontSize} * var(--fs, 1))`;
    if (/Cinzel/.test(s.fontFamily)) s.fontFamily = 'var(--font-head, Cinzel, serif)';
    else if (/^"?Inter/.test(s.fontFamily)) s.fontFamily = 'var(--font-body, Inter, "Segoe UI", system-ui, sans-serif)';
  } };
  walk(rules);
}
function thFontAll(){ for (const s of document.styleSheets) thFontRules(s); }
document.addEventListener('DOMContentLoaded', () => {
  thFontAll();
  // (other pages put in their own style sheets later)
  let pend = 0;
  new MutationObserver(() => { if (!pend) pend = setTimeout(() => { pend = 0; thFontAll(); }, 0); }).observe(document.head, {childList: true});
});

function thApply(t){
  t = t || thGet();
  const root = document.documentElement, custom = t.theme === 'custom' && t.custom, base = TH_THEMES[t.theme] || TH_THEMES.ashlands;
  const names = ['bg', 'panel', 'panel2', 'line', 'line2', 'text', 'muted', 'faint', 'gold', 'gold2', 'hover', 'sel', 'deep', 'bg2', 'bg3', 'line0', 'goldline', 'red', 'amber', 'blue', 'green'];
  for (const k of names.concat(['text-b', 'text-c', 'text-d', 'muted-b', 'muted-c', 'muted-d', 'deep-b', 'deep-c', 'deep-d', 'bg2-b', 'bg3-b',
    'panel2-b', 'panel2-c', 'panel2-d', 'goldline-b', 'sel-b', 'btn-primary', 'btn-primary-hover', 'tag-mine', 'tag-flag', 'tag-flag-p', 'toast-err', 'hl',
    'view3d', 'fs', 'font-head', 'font-body'])) root.style.removeProperty('--' + k);
  let cv = null;
  if (custom) cv = thCustomVars(t.custom);
  const v = Object.assign({}, cv ? cv.v : base.v);
  let light = cv ? cv.light : !!base.light;
  // your own background: the panels, lines and text are worked out from it
  if (!cv && /^#[0-9a-f]{6}$/i.test(t.bg || '')){
    const B = t.bg; light = thLum(B) > 0.55;
    const T = light ? '#000000' : '#ffffff', mix = (p, c) => `color-mix(in srgb, ${B}, ${c || T} ${p}%)`;
    Object.assign(v, {bg: B, panel: mix(4), panel2: mix(8), line: mix(16), line2: mix(24), hover: mix(10), line0: mix(7), bg2: mix(2), bg3: mix(5),
      deep: mix(30, light ? '#ffffff' : '#000000'), text: mix(88), muted: mix(58), faint: mix(40), sel: mix(14)});
  }
  // your own accent (what's gold in the usual look)
  if (!cv && /^#[0-9a-f]{6}$/i.test(t.accent || '')){
    const A = t.accent;
    Object.assign(v, {gold: A, gold2: `color-mix(in srgb, ${A}, ${light ? '#000000' : '#ffffff'} 30%)`, goldline: `color-mix(in srgb, ${A}, ${v.bg || '#13110d'} 40%)`});
  }
  // the close shades and the button and tag colours follow the main ones; the usual look keeps its own exactly
  const fam = {text: ['text-b', 'text-c', 'text-d'], muted: ['muted-b', 'muted-c', 'muted-d'], deep: ['deep-b', 'deep-c', 'deep-d'],
               bg2: ['bg2-b'], bg3: ['bg3-b'], panel2: ['panel2-b', 'panel2-c', 'panel2-d'], goldline: ['goldline-b'], sel: ['sel-b']};
  for (const [k, kids] of Object.entries(fam)) if (v[k]) for (const c of kids) v[c] = `var(--${k})`;
  // (on a light background a paler tint, so the dark accent text on it stays easy to read)
  const tint = light ? [13, 20, 12, 12] : [30, 40, 20, 18];
  if (Object.keys(v).length) Object.assign(v, {
    'btn-primary': `color-mix(in srgb,var(--gold) ${tint[0]}%,var(--panel))`, 'btn-primary-hover': `color-mix(in srgb,var(--gold) ${tint[1]}%,var(--panel))`,
    'tag-mine': `color-mix(in srgb,var(--gold) ${tint[2]}%,var(--panel))`, 'tag-flag': `color-mix(in srgb,var(--red) ${tint[3]}%,var(--panel))`,
    'tag-flag-p': `color-mix(in srgb,var(--blue) ${tint[3]}%,var(--panel))`, 'toast-err': 'var(--red)',
    hl: `color-mix(in srgb,var(--gold) ${light ? 18 : 30}%,var(--panel))`});
  if (!cv && base.btn && !t.accent) Object.assign(v, {'btn-primary': base.btn, 'btn-primary-hover': `color-mix(in srgb,${base.btn},var(--text) 12%)`});
  if (cv){
    Object.assign(v, {'btn-primary': cv.btn, 'btn-primary-hover': `color-mix(in srgb,${cv.btn},var(--text) 12%)`});
    const cu = t.custom, h = TH_HEAD_FONTS[cu.head], b = TH_BODY_FONTS[cu.body];
    if (h && cu.head !== 'cinzel') v['font-head'] = h[1];
    if (b && cu.body !== 'inter') v['font-body'] = b[1];
    if (+cu.size && +cu.size !== 1) v.fs = String(Math.max(0.8, Math.min(1.5, +cu.size)));
  }
  for (const [k, val] of Object.entries(v)) root.style.setProperty('--' + k, val);
  root.dataset.theme = light ? 'light' : 'dark';
  root.classList.toggle('th-calm', !!t.calm);
  let st = document.getElementById('th-css');
  if (!st){ st = document.createElement('style'); st.id = 'th-css'; document.head.appendChild(st); }
  st.textContent = `
    .th-calm *,.th-calm *::before,.th-calm *::after{transition:none!important;animation:none!important}
    html[data-theme=light] header{background:var(--bg2)!important}
    html[data-theme=light] .modal-bg{background:color-mix(in srgb,var(--text) 40%,transparent)}
    html[data-theme=light] ::-webkit-scrollbar-thumb{background-color:var(--line2)}
    html[data-theme=light] .pfloat .pgroup,html[data-theme=light] .pmenu,html[data-theme=light] .modal{box-shadow:0 10px 32px color-mix(in srgb,var(--text) 22%,transparent)}
    [style*="Cinzel"]{font-family:var(--font-head,Cinzel,serif)!important}`;
  // (the 3D view's background, if it's open indoors)
  if (typeof v3ApplyLighting === 'function' && typeof V3 !== 'undefined' && V3.scene) try { v3ApplyLighting(); } catch (e){}
}
thApply();
// The Workshop's settings file has the last look chosen (this browser may not: a new port, or a cleared cache)
fetch('/api/settings').then(r => r.json()).then(s => {
  let mine = ''; try { mine = localStorage.getItem('ws-theme') || ''; } catch (e){}
  if (s.theme && JSON.stringify(s.theme) !== mine){
    try { localStorage.setItem('ws-theme', JSON.stringify(s.theme)); } catch (e){}
    thApply();
    if (document.getElementById('th-grid')) renderSettings();
  } else if (!s.theme && mine) thSave(thGet());             // (a look chosen before it was kept there too)
}).catch(() => {});

// ---------------------------------------------------------------- Settings → Appearance
function thSection(){
  const t = thGet();
  let in3d = false; try { in3d = localStorage.getItem('ws-3d') === '1'; } catch (e){}
  const cu = t.custom || thFromPreset('contrast'), cc = thCustomVars(cu), cv = Object.assign({}, cc.v, {line2: cc.v.line});
  const card = (k, c, label, about, on) => `<button class="th-card ${on ? 'on' : ''}" data-th="${k}" style="background:${c.bg};border-color:${on ? c.gold : c.line2}">
        <span style="background:${c.panel};border-color:${c.line2}"><i style="background:${c.gold}"></i><i style="background:${c.muted}"></i><i style="background:${c.text}"></i></span>
        <b style="color:${c.text}">${esc(label)}</b><small style="color:${c.muted}">${esc(about)}</small></button>`;
  const isCustom = t.theme === 'custom';
  return `<section class="card setsec"><h3>Appearance</h3>
    <div class="th-grid" id="th-grid">${Object.entries(TH_THEMES).map(([k, T]) => card(k, Object.assign({}, TH_USUAL, T.v), T.label, T.about, t.theme === k && !t.bg)).join('')}
      ${card('custom', cv, '✎ Your own', t.custom ? 'Your own colours and fonts, started from ' + ((TH_THEMES[cu.from] || {}).label || 'a theme') : 'Make your own look: colours, fonts and text size', isCustom)}</div>
    ${isCustom ? thEditor(t) : `
    <div class="setrow" style="margin-top:12px"><span>Your own accent colour</span><span><input type="color" id="th-accent" value="${t.accent || '#d2a85a'}"> <button class="btn sm" id="th-accent-x" ${t.accent ? '' : 'disabled'}>Theme's own</button></span></div>
    <div class="setrow"><span>Your own background colour</span><span><input type="color" id="th-bg" value="${t.bg || '#13110d'}"> <button class="btn sm" id="th-bg-x" ${t.bg ? '' : 'disabled'}>Theme's own</button></span></div>
    <div class="msg" style="font-size:12px">The panels, lines and text are worked out from the background, so any colour stays readable. For more, choose ✎ Your own.</div>`}
    <label style="display:flex;gap:8px;align-items:center;margin-top:10px"><input type="checkbox" id="th-calm" ${t.calm ? 'checked' : ''}> Calmer: no fades or movement in menus and windows</label>
    <div class="msg" style="font-size:12px;margin-top:8px">Bigger or smaller: hold Ctrl and turn the mouse wheel (Ctrl+0 for the usual size).</div></section>

  <section class="card setsec"><h3>Working</h3>
    <div class="setrow"><span>The World map opens in</span><span><select id="th-3d" style="width:auto;margin:0"><option value="0" ${in3d ? '' : 'selected'}>the flat map</option><option value="1" ${in3d ? 'selected' : ''}>3D</option></select></span></div>
    <div class="setrow"><span>Keyboard shortcuts</span><span><button class="btn sm" id="th-keys">Change them… (Ctrl+/)</button></span></div>
    <div class="setrow"><span>Panels on every page</span><span><button class="btn sm" id="th-panels">Back to the starting layouts</button></span></div>
    <div class="setrow"><span>Who Play here starts as</span><span><button class="btn sm" id="th-playas">👤 ${esc((typeof QOL !== 'undefined' && QOL.playAs) || 'A new character')}…</button></span></div></section>`;
}
// ----- your own theme: its colours, fonts and size, a sample and a check that it's easy to read
function thEditor(t){
  const cu = t.custom, c = Object.assign({}, thFromPreset(cu.from).c, cu.c);
  const opts = (o, cur) => Object.entries(o).map(([k, [l]]) => `<option value="${k}" ${k === cur ? 'selected' : ''}>${esc(l)}</option>`).join('');
  return `<div class="th-ed">
    <div class="th-edcols"><div>
      <h4>Colours</h4>
      ${TH_KEYS.map(([k, l]) => `<div class="setrow"><span>${esc(l)}</span><span><input type="color" data-thc="${k}" value="${c[k]}"></span></div>`).join('')}
      <h4>Fonts and text size</h4>
      <div class="setrow"><span>Headings</span><span><select id="th-head" style="width:auto;margin:0">${opts(TH_HEAD_FONTS, cu.head || 'cinzel')}</select></span></div>
      <div class="setrow"><span>Everything else</span><span><select id="th-body" style="width:auto;margin:0">${opts(TH_BODY_FONTS, cu.body || 'inter')}</select></span></div>
      <div class="setrow"><span>Text size</span><span><select id="th-size" style="width:auto;margin:0">${TH_SIZES.map(([v, l]) => `<option value="${v}" ${v === (+cu.size || 1) ? 'selected' : ''}>${l} (${Math.round(v * 100)}%)</option>`).join('')}</select></span></div>
    </div><div>
      <h4>How it looks</h4>
      <div class="th-prev"><div class="th-prevpanel">
        <h2 style="font-family:Cinzel,serif;color:var(--gold2);font-weight:600;margin:0 0 4px">Hlaalu Council Manor</h2>
        <div>Ordinary text: a desk, three chairs and a lamp.</div>
        <div class="msg">Quieter text: in_hlaalu_room_01 · 42 objects</div>
        <a href="#" onclick="return false">A link</a>
        <div class="actions" style="margin:8px 0"><button class="btn primary sm" tabindex="-1">Main button</button><button class="btn sm" tabindex="-1">Button</button><button class="btn sm danger" tabindex="-1">Delete</button></div>
        <div class="th-prevrow"><span class="sev-error">● Error</span><span class="sev-warning">● Warning</span><span class="sev-ok">● Done</span><span class="sev-info">● Note</span></div>
        <div class="th-prev3d">The 3D view, indoors</div>
      </div></div>
      <h4>Easy to read?</h4>
      <div id="th-check">${thCheck(cu)}</div>
    </div></div>
    <div class="actions" style="margin-top:12px;align-items:center">Started from <select id="th-from" style="width:auto;margin:0">${Object.entries(TH_THEMES).map(([k, T]) => `<option value="${k}" ${k === cu.from ? 'selected' : ''}>${esc(T.label)}</option>`).join('')}</select>
      <button class="btn sm" id="th-reset">Reset to the preset</button>
      <button class="btn sm" id="th-export">Save to a file…</button><button class="btn sm" id="th-import">Load from a file…</button></div>
    <div class="msg" style="font-size:12px">Kept in the Workshop's settings, so it stays through restarts and updates. A saved file can be shared and loaded on another PC.</div>
  </div>`;
}
function thCheck(cu){
  const {v, btn} = thCustomVars(cu);
  const pairs = [['Text on the background', v.text, v.bg, 4.5], ['Text on panels', v.text, v.panel, 4.5], ['Quieter text', v.muted, v.panel, 4.5],
    ['Headings and links', v.gold2, v.bg, 4.5], ['Accent on panels', v.gold, v.panel, 3], ['Main button text', v.gold2, btn, 4.5],
    ['Danger', v.red, v.panel, 3], ['Warnings', v.amber, v.panel, 3], ['Done', v.green, v.panel, 3], ['Notes', v.blue, v.panel, 3]];
  let bad = 0;
  const rows = pairs.map(([l, a, b, need]) => {
    const r = thContrast(a, b), ok = r >= need, fair = !ok && r >= need * 0.75;
    if (!ok) bad++;
    return `<div class="th-chk ${ok ? 'ok' : fair ? 'fair' : 'bad'}"><span class="th-sw" style="background:${b};color:${a}">Aa</span><span>${l}</span>
      <b>${ok ? '✓ easy' : fair ? '~ a little faint' : '⚠ hard to read'}</b><span class="msg">${r.toFixed(1)}:1</span></div>`;
  }).join('');
  return (bad ? `<div class="th-chkhead">⚠ ${bad === 1 ? 'One thing is' : bad + ' things are'} hard to read: make ${bad === 1 ? 'it' : 'them'} lighter or darker against what ${bad === 1 ? 'it sits' : 'they sit'} on.</div>`
              : '<div class="th-chkhead ok">✓ Everything is easy to read.</div>') + rows;
}
function thExport(t){
  const cu = t.custom, data = {format: 'Morrowind Workshop theme', version: 1, from: cu.from, colours: Object.assign({}, thFromPreset(cu.from).c, cu.c),
    headings: cu.head || 'cinzel', text: cu.body || 'inter', size: +cu.size || 1};
  askText('A name for the file:', 'My Workshop theme').then(name => {
    if (name == null) return;
    data.name = name.trim() || 'My Workshop theme';
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 1)], {type: 'application/json'}));
    a.download = data.name.replace(/[^\w\- ]+/g, '_') + '.theme.json';
    a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    toast('Saved ' + a.download + ' to your Downloads folder.');
  });
}
function thImport(t, done){
  const inp = document.createElement('input'); inp.type = 'file'; inp.accept = '.json,application/json';
  inp.onchange = async () => {
    const f = inp.files[0]; if (!f) return;
    let d; try { d = JSON.parse(await f.text()); } catch (e){ d = null; }
    if (!d || d.format !== 'Morrowind Workshop theme' || typeof d.colours !== 'object') return toast('That file isn\'t a Workshop theme.', true);
    const from = TH_THEMES[d.from] ? d.from : 'contrast', c = {};
    for (const [k] of TH_KEYS) if (thHex(d.colours[k])) c[k] = d.colours[k].toLowerCase();
    t.custom = {from, c, head: TH_HEAD_FONTS[d.headings] ? d.headings : 'cinzel', body: TH_BODY_FONTS[d.text] ? d.text : 'inter',
      size: TH_SIZES.some(([v]) => v === +d.size) ? +d.size : 1};
    t.theme = 'custom';
    done();
    toast('Using the theme' + (d.name ? ' "' + d.name + '"' : '') + '.');
  };
  inp.click();
}

function thBind(w){
  thCss();
  const t = thGet(), upd = ch => { Object.assign(t, ch); thSave(t); thApply(t); renderSettings(); };
  w.querySelectorAll('[data-th]').forEach(b => b.onclick = () => b.dataset.th === 'custom'
    ? upd({theme: 'custom', custom: t.custom || thFromPreset('contrast')}) : upd({theme: b.dataset.th, bg: '', accent: ''}));
  const ac = w.querySelector('#th-accent'), bgc = w.querySelector('#th-bg');
  if (ac){
    ac.oninput = () => { t.accent = ac.value; thSave(t); thApply(t); };
    ac.onchange = () => upd({accent: ac.value});
    bgc.oninput = () => { t.bg = bgc.value; thSave(t); thApply(t); };
    bgc.onchange = () => upd({bg: bgc.value});
    w.querySelector('#th-accent-x').onclick = () => upd({accent: ''});
    w.querySelector('#th-bg-x').onclick = () => upd({bg: ''});
  }
  if (t.theme === 'custom' && t.custom){
    const cu = t.custom, chk = w.querySelector('#th-check');
    cu.c = Object.assign({}, thFromPreset(cu.from).c, cu.c);
    // (live while the colour box is open; the custom card's swatches catch up when the page is drawn again)
    w.querySelectorAll('[data-thc]').forEach(inp => inp.oninput = () => { cu.c[inp.dataset.thc] = inp.value; thSave(t); thApply(t); chk.innerHTML = thCheck(cu); });
    w.querySelector('#th-head').onchange = e => { cu.head = e.target.value; thSave(t); thApply(t); };
    w.querySelector('#th-body').onchange = e => { cu.body = e.target.value; thSave(t); thApply(t); };
    w.querySelector('#th-size').onchange = e => { cu.size = +e.target.value; thSave(t); thApply(t); };
    w.querySelector('#th-from').onchange = e => {
      const k = e.target.value;
      if (!confirm(`Start your own theme again from ${TH_THEMES[k].label}? Its colours replace yours (the fonts and text size stay).`)){ e.target.value = cu.from; return; }
      upd({custom: Object.assign(thFromPreset(k), {head: cu.head, body: cu.body, size: cu.size})});
    };
    w.querySelector('#th-reset').onclick = () => {
      if (!confirm(`Put your own theme back to ${(TH_THEMES[cu.from] || {}).label}'s colours, with the usual fonts and text size?`)) return;
      upd({custom: thFromPreset(cu.from)});
    };
    w.querySelector('#th-export').onclick = () => thExport(t);
    w.querySelector('#th-import').onclick = () => thImport(t, () => upd({}));
  }
  w.querySelector('#th-calm').onchange = e => upd({calm: e.target.checked});
  w.querySelector('#th-3d').onchange = e => { try { localStorage.setItem('ws-3d', e.target.value); } catch (x){} toast(e.target.value === '1' ? 'The World map opens in 3D from now on.' : 'The World map opens flat from now on.'); };
  w.querySelector('#th-keys').onclick = () => cfKeysModal();
  w.querySelector('#th-playas').onclick = () => qsPlayAs();
  w.querySelector('#th-panels').onclick = () => {
    if (!confirm('Put the panels on every page back where they started? (Your saved layouts stay in the Panels menu.)')) return;
    for (const [name, sp] of Object.entries(PNL.spaces)) PNL.useLayout(name, sp.opts.presets[sp.opts.start]);
    try { for (const k of Object.keys(localStorage)) if (k.startsWith('ws-panels-') && !Object.keys(PNL.spaces).includes(k.slice(10))) localStorage.removeItem(k); } catch (e){}
    toast('Panels are back where they started.');
  };
}
function thCss(){
  if (document.getElementById('th-css2')) return;
  const c = document.createElement('style'); c.id = 'th-css2';
  c.textContent = `
  .th-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
  .th-card{display:flex;flex-direction:column;gap:3px;text-align:left;border:2px solid;border-radius:10px;padding:10px;cursor:pointer;font:inherit}
  .th-card.on{box-shadow:0 0 0 2px var(--gold)}
  .th-card span{display:flex;gap:4px;border:1px solid;border-radius:6px;padding:6px;margin-bottom:4px}
  .th-card i{display:block;width:18px;height:10px;border-radius:3px}
  .th-card b{font-size:13px}.th-card small{font-size:11px;line-height:1.35}
  input[type=color]{width:44px;height:28px;padding:0;border:1px solid var(--line2);border-radius:6px;background:none;cursor:pointer;vertical-align:middle}
  .th-ed{margin-top:14px;border-top:1px solid var(--line);padding-top:6px}
  .th-ed h4{margin:12px 0 4px;color:var(--gold2)}
  .th-edcols{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:8px 28px}
  .th-prev{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:12px}
  .th-prevpanel{background:var(--panel);border:1px solid var(--line2);border-radius:8px;padding:12px}
  .th-prevrow{display:flex;gap:14px;flex-wrap:wrap}
  .th-prev3d{margin-top:10px;background:var(--view3d,#0d0c0a);border:1px solid var(--line);border-radius:6px;height:54px;display:flex;align-items:flex-end;padding:6px 8px;font-size:12px;color:#ffffffcc;text-shadow:0 1px 2px #000}
  .th-chkhead{margin:2px 0 6px;color:var(--amber);font-weight:600}.th-chkhead.ok{color:var(--green)}
  .th-chk{display:grid;grid-template-columns:44px 1fr auto 52px;gap:8px;align-items:center;padding:3px 0;border-bottom:1px solid var(--line0)}
  .th-chk .th-sw{border:1px solid var(--line2);border-radius:5px;text-align:center;font-weight:600;padding:1px 0}
  .th-chk.ok b{color:var(--green)}.th-chk.fair b{color:var(--amber)}.th-chk.bad b{color:var(--red)}
  .th-chk .msg{text-align:right}`;
  document.head.appendChild(c);
}
