// ---------- Icons from pictures, and models from the Library ----------
// "🖼 From a picture…" beside an Icon box (your own magic effects, items): a picture from the Library (any
// of .png, .jpg, .tga, .dds, .bmp) or straight from your PC, made into the sizes the game wants and named its
// way (an effect's small icon and its "b_" large twin; an item's inventory icon), kept in icons\wslib and the
// Library (library.make_icon). "📦 From the Library…" beside a Model box: one of your Library's models.
const IC = {r: null};
const IC_SIZES = {effect: [32, 64], item: [64]};
const IC_NOTE = {effect: 'a small icon for the spell list and the active effects, and a large one for the spell and enchanting windows',
                 item: 'an inventory icon'};

function icLoadImage(url){
  return new Promise((res, rej) => { const im = new Image(); im.onload = () => res(im); im.onerror = () => rej(new Error('That picture could not be read.')); im.src = url; });
}
// a picture's pixels as something a canvas can draw: an <img> for what the browser reads, else (.dds, .tga)
// drawn by the 3D view's loaders on a canvas of its own
async function icSource(src){
  const path = (src.path || '').toLowerCase(), game = /\.(dds|tga)$/.test(path) || /\.(dds|tga)$/i.test(src.name || '');
  if (!game){
    const im = await icLoadImage(src.url || '/api/file?path=' + encodeURIComponent(path));
    return {w: im.naturalWidth, h: im.naturalHeight, draw: (ctx, x, y, w, h) => ctx.drawImage(im, x, y, w, h)};
  }
  await ensureThree();                // (the 3D view's loaders, fetched the first time anything needs them)
  // (a .dds or .tga from your PC read by the same loaders: the browser's own reader can't, and "Use it" stayed grey)
  const tex = src.url
    ? await new Promise((res, rej) => (/\.dds$/i.test(src.name) ? new THREE.DDSLoader() : new THREE.TGALoader()).load(src.url, res, undefined, () => rej(new Error('That picture could not be read.'))))
    : await new Promise((res, rej) => v3Tex(path, res, () => rej(new Error('That picture could not be read.'))));
  const T = THREE, iw = (tex.image && tex.image.width) || 256, ih = (tex.image && tex.image.height) || 256;
  if (!IC.r){
    IC.r = new T.WebGLRenderer({alpha: true, preserveDrawingBuffer: true}); IC.r.setClearColor(0x000000, 0);
    IC.scene = new T.Scene(); IC.cam = new T.OrthographicCamera(-1, 1, 1, -1, 0, 2); IC.cam.position.z = 1;
    IC.mesh = new T.Mesh(new T.PlaneGeometry(2, 2), new T.MeshBasicMaterial({transparent: true})); IC.scene.add(IC.mesh);
  }
  const s = Math.min(1024, Math.max(iw, ih));
  IC.r.setSize(Math.round(s * iw / Math.max(iw, ih)), Math.round(s * ih / Math.max(iw, ih)), false);
  IC.mesh.material.map = tex; IC.mesh.material.needsUpdate = true;
  IC.r.render(IC.scene, IC.cam);
  // (the game's pictures come up the other way round from WebGL: turned the right way up here)
  const c = document.createElement('canvas'); c.width = IC.r.domElement.width; c.height = IC.r.domElement.height;
  const g = c.getContext('2d'); g.translate(0, c.height); g.scale(1, -1); g.drawImage(IC.r.domElement, 0, 0);
  return {w: c.width, h: c.height, draw: (ctx, x, y, w, h) => ctx.drawImage(c, x, y, w, h)};
}
// one size of the icon, as a PNG data URL: the whole picture fitted in the square, or the square filled
function icRender(S, size, mode){
  // (halved step by step down to near the size: a big picture shrunk at once comes out grainy)
  let cur = {w: S.w, h: S.h, draw: S.draw};
  while (Math.max(cur.w, cur.h) > size * 2){
    const w = Math.max(1, Math.round(cur.w / 2)), h = Math.max(1, Math.round(cur.h / 2));
    const c = document.createElement('canvas'); c.width = w; c.height = h;
    const g = c.getContext('2d'); g.imageSmoothingQuality = 'high'; cur.draw(g, 0, 0, w, h);
    cur = {w, h, draw: (ctx, x, y, ww, hh) => ctx.drawImage(c, x, y, ww, hh)};
  }
  const c = document.createElement('canvas'); c.width = c.height = size;
  const g = c.getContext('2d'); g.imageSmoothingQuality = 'high';
  const k = mode === 'fill' ? Math.max(size / cur.w, size / cur.h) : Math.min(size / cur.w, size / cur.h);
  const w = cur.w * k, h = cur.h * k;
  cur.draw(g, (size - w) / 2, (size - h) / 2, w, h);
  return c.toDataURL('image/png');
}

async function icPick(kind, opts){
  opts = opts || {};
  // (once: the Library list was slow to come while the Workshop was busy, a second click opened a second window)
  if (IC.opening || document.querySelector('.modal-bg[data-icpick]')) return;
  IC.opening = true;
  let lib = [];
  try { lib = ((await api('/api/library')).items || []).filter(i => i.type === 'texture' && i.ok !== false); } catch (e){}
  finally { IC.opening = false; }
  // (a picture kept as both .dds and .tga, as the game's icons often are: once, the .dds)
  const rank = f => /\.dds$/i.test(f) ? 0 : /\.(png|jpe?g)$/i.test(f) ? 1 : 2, best = {};
  for (const i of lib){ const k = (i.file || '').toLowerCase().replace(/\.[^./]+$/, ''); if (!best[k] || rank(i.file) < rank(best[k].file)) best[k] = i; }
  lib = lib.filter(i => best[(i.file || '').toLowerCase().replace(/\.[^./]+$/, '')] === i);
  const bg = document.createElement('div'); bg.className = 'modal-bg'; bg.dataset.icpick = '1';
  bg.innerHTML = `<div class="modal" style="width:min(640px,94vw)"><h2>An icon from a picture</h2>
    <div class="msg" style="line-height:1.55">Pick a picture: the Workshop makes ${IC_NOTE[kind]} from it, in the sizes the game wants, and keeps ${kind === 'effect' ? 'them' : 'it'} with your mod.</div>
    <div class="icgrid">${lib.map((i, n) => `<button class="ictile" data-icn="${n}" title="${esc(i.name)}">${/\.(dds|tga)$/i.test(i.file) ? `<img data-swatch="${esc(i.file)}" alt="">` : `<img src="/api/file?path=${encodeURIComponent(i.file)}" alt="">`}<span>${esc(i.name)}</span></button>`).join('')
      || '<div class="msg">Your Library has no pictures yet. Add them on the Library page (drop them there), or pick a file from your PC below.</div>'}</div>
    <label class="msg" style="display:block;margin-top:8px">Or a picture from your PC (.png, .jpg, .dds, .tga, .webp, .bmp): <input type="file" id="ic-file" accept=".png,.jpg,.jpeg,.dds,.tga,.webp,.gif,.bmp,image/*"></label>
    <div id="ic-prev" style="display:none;margin-top:10px">
      <div class="icrow"><div id="ic-imgs" class="icimgs"></div>
        <div><label>Name<input class="inp" id="ic-name"></label>
          <div class="radios" style="margin-top:6px"><label><input type="radio" name="ic-mode" value="fit" checked> The whole picture</label><label><input type="radio" name="ic-mode" value="fill"> Fill the square</label></div></div></div></div>
    <div class="foot"><button class="btn" id="ic-no">Cancel</button><button class="btn primary" id="ic-ok" disabled>Use it</button></div></div>`;
  document.body.appendChild(bg);
  if (!$('#ic-css')){
    const st = document.createElement('style'); st.id = 'ic-css';
    st.textContent = `.icgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(92px,1fr));gap:6px;max-height:260px;overflow:auto;margin-top:8px}
      .ictile{background:var(--panel2);border:1px solid var(--line2);border-radius:8px;padding:4px;cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:3px;color:var(--muted);font:inherit;font-size:11px}
      .ictile.on{border-color:var(--gold)} .ictile img{width:64px;height:64px;object-fit:contain;image-rendering:auto}
      .ictile span{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .icrow{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap} .icimgs{display:flex;gap:12px;align-items:flex-end}
      .icimgs figure{margin:0;text-align:center;font-size:11px;color:var(--faint)} .icimgs img{display:block;background:repeating-conic-gradient(#555 0 25%,#333 0 50%) 0 0/12px 12px;border:1px solid var(--line2)}`;
    document.head.appendChild(st);
  }
  if (typeof v3SwatchScan === 'function' && bg.querySelector('[data-swatch]')) ensureThree().then(() => v3SwatchScan(bg)).catch(() => {});
  let S = null, made = null, source = '';
  const sizes = IC_SIZES[kind];
  const draw = () => {
    if (!S) return;
    // (a picture that came out all black or empty didn't draw: made into an icon anyway, it showed in the game as a
    // black square, 2026-11-02)
    const c = document.createElement('canvas'); c.width = c.height = 16; const g = c.getContext('2d'); S.draw(g, 0, 0, 16, 16);
    const px = g.getImageData(0, 0, 16, 16).data; let lit = 0;
    for (let i = 0; i < px.length; i += 4) if (px[i + 3] > 8 && px[i] + px[i + 1] + px[i + 2] > 24) lit++;
    if (!lit){ $('#ic-prev').style.display = 'none'; $('#ic-ok').disabled = true; made = null; toast('That picture came out all black: the Workshop could not read it. Pick another, or the same one as .png.', true); return; }
    const mode = bg.querySelector('[name=ic-mode]:checked').value;
    made = sizes.map(z => icRender(S, z, mode));
    $('#ic-imgs').innerHTML = made.map((u, n) => `<figure><img src="${u}" width="${sizes[n]}" height="${sizes[n]}">${kind === 'effect' ? (n ? 'large' : 'small') : 'icon'} · ${sizes[n]}×${sizes[n]}</figure>`).join('');
    $('#ic-prev').style.display = ''; $('#ic-ok').disabled = false;
  };
  const use = async (src, name) => {
    try { S = await icSource(src); } catch (e){ toast(e.message, true); return; }
    source = src.path || name; $('#ic-name').value = (opts.name || name || 'icon').replace(/\.[^.]+$/, ''); draw();
  };
  bg.querySelectorAll('[data-icn]').forEach(b => b.onclick = () => {
    bg.querySelectorAll('.ictile').forEach(x => x.classList.toggle('on', x === b));
    const it = lib[+b.dataset.icn]; use({path: it.file}, it.name);
  });
  $('#ic-file').onchange = e => { const f = e.target.files[0]; if (f){ bg.querySelectorAll('.ictile').forEach(x => x.classList.remove('on')); use({url: URL.createObjectURL(f), name: f.name}, f.name); } };
  bg.querySelectorAll('[name=ic-mode]').forEach(r => r.onchange = draw);
  $('#ic-no').onclick = () => bg.remove();
  $('#ic-ok').onclick = async () => {
    if (!made) return;
    const btn = $('#ic-ok'); btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Making it…';
    try {
      const r = await post('/api/library/makeicon', {kind, name: $('#ic-name').value.trim(), pictures: made, source});
      bg.remove();
      toast(kind === 'effect' ? `Made ${r.files.join(' and ')}. New icons show in the game after restarting it.` : `Made ${r.files[0]}. New icons show in the game after restarting it.`);
      if (opts.onDone) opts.onDone(r.icon);
    } catch (e){ toast(e.message, true); btn.disabled = false; btn.textContent = 'Use it'; }
  };
}

// a model from the Library, for a Model box (its path as the record names it)
async function icModelPick(onDone){
  let lib = [];
  try { lib = ((await api('/api/library')).items || []).filter(i => i.type === 'model' && i.ok !== false); } catch (e){}
  if (!lib.length) return toast('Your Library has no models yet: add some on the Library page first.', true);
  const items = lib.map(i => ({label: i.name + (i.model ? '  (' + i.model + ')' : ''), act: () => onDone(i.model || (i.file || '').replace(/^meshes\//, '').replace(/\//g, '\\'))}));
  const b = document.activeElement && document.activeElement.getBoundingClientRect ? document.activeElement.getBoundingClientRect() : {left: 200, bottom: 200};
  pnlMenu({x: b.left, y: b.bottom + 4}, [{label: 'Your Library\'s models', disabled: true, head: true}, ...items]);
}
