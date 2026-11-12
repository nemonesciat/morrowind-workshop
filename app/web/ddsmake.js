// Pictures to DDS, in the page (tosky0890 on Discord, 2026-11-11: "allow that (optional) DDS conversion when the mod
// enters the publication phase, rather than every time a PNG or TGA comes into the Library"; the user: "i agree").
// A picture going into a release zip becomes a DDS with its whole mip chain: DXT1, or DXT5 when it has see-through
// parts. The page does it because the browser reads PNG, JPG and BMP itself (the Workshop ships no picture
// library); a TGA is read here. The server packs the DDS in the picture's place (release.py); your own files stay.
const DDSM = {gl: null};

// a TGA's pixels: plain, grey or with a colour map, packed or not, from either corner
function ddsTga(buf){
  const d = new Uint8Array(buf);
  if (d.length < 18) return null;
  const type = d[2], kind = type & 7, rle = !!(type & 8), cmLen = d[5] | d[6] << 8, cmBytes = (d[7] + 7) >> 3;
  const w = d[12] | d[13] << 8, h = d[14] | d[15] << 8, bytes = (d[16] + 7) >> 3, desc = d[17];
  if (!w || !h || type > 11 || kind < 1 || kind > 3) return null;
  if ((kind === 1 && (bytes !== 1 || !d[1] || cmBytes < 2 || cmBytes > 4)) || (kind === 2 && (bytes < 2 || bytes > 4)) || (kind === 3 && bytes !== 1)) return null;
  let p = 18 + d[0], pal = null;
  if (d[1]){ pal = d.subarray(p, p + cmLen * cmBytes); p += cmLen * cmBytes; }
  const n = w * h * bytes, src = new Uint8Array(n);
  if (!rle){ if (p + n > d.length) return null; src.set(d.subarray(p, p + n)); }
  else {
    let o = 0;
    while (o < n && p < d.length){
      const c = d[p++], k = (c & 127) + 1;
      if (c & 128){ for (let i = 0; i < k && o < n; i++) for (let b = 0; b < bytes; b++) src[o++] = d[p + b]; p += bytes; }
      else { const len = Math.min(k * bytes, n - o, d.length - p); src.set(d.subarray(p, p + len), o); o += len; p += len; }
    }
  }
  const out = new Uint8Array(w * h * 4), top = !!(desc & 32), right = !!(desc & 16), seeThrough = (desc & 15) > 0;
  for (let y = 0; y < h; y++){
    const sy = top ? y : h - 1 - y;
    for (let x = 0; x < w; x++){
      const o = (y * w + x) * 4;
      let s = (sy * w + (right ? w - 1 - x : x)) * bytes, q = src, b = bytes;
      if (kind === 3){ out[o] = out[o + 1] = out[o + 2] = src[s]; out[o + 3] = 255; continue; }
      if (kind === 1){ q = pal; b = cmBytes; s = src[s] * b; if (s + b > pal.length) s = 0; }
      if (b === 2){
        const v = q[s] | q[s + 1] << 8;
        out[o] = ((v >> 10) & 31) * 255 / 31; out[o + 1] = ((v >> 5) & 31) * 255 / 31; out[o + 2] = (v & 31) * 255 / 31; out[o + 3] = 255;
      } else { out[o] = q[s + 2]; out[o + 1] = q[s + 1]; out[o + 2] = q[s]; out[o + 3] = b === 4 && seeThrough ? q[s + 3] : 255; }
    }
  }
  return {w, h, data: out};
}

// a picture's pixels, top row first, colours as they are in the file (kind: png, jpg, bmp or tga)
async function ddsPixels(buf, kind){
  if (kind === 'tga') return ddsTga(buf);
  const type = {png: 'image/png', jpg: 'image/jpeg', bmp: 'image/bmp'}[kind];
  if (!type) return null;
  let bmp;
  try { bmp = await createImageBitmap(new Blob([buf], {type}), {premultiplyAlpha: 'none', colorSpaceConversion: 'none'}); }
  catch (e){ return null; }
  const w = bmp.width, h = bmp.height;
  if (!w || !h || w > 8192 || h > 8192) return null;
  // read back through WebGL: a 2D canvas keeps colours times their alpha, which loses those of see-through pixels
  try {
    if (!DDSM.gl) DDSM.gl = document.createElement('canvas').getContext('webgl', {premultipliedAlpha: false, antialias: false});
    const gl = DDSM.gl;
    if (gl && !gl.isContextLost() && Math.max(w, h) <= gl.getParameter(gl.MAX_TEXTURE_SIZE)){
      const t = gl.createTexture(), fb = gl.createFramebuffer();
      gl.bindTexture(gl.TEXTURE_2D, t);
      gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
      gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, bmp);
      gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0);
      const ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE, data = new Uint8Array(w * h * 4);
      if (ok) gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, data);
      const bad = !ok || gl.getError() !== gl.NO_ERROR;
      gl.bindFramebuffer(gl.FRAMEBUFFER, null); gl.deleteFramebuffer(fb); gl.deleteTexture(t);
      if (!bad) return {w, h, data};
    }
  } catch (e){}
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  const g = c.getContext('2d');
  g.drawImage(bmp, 0, 0);
  return {w, h, data: g.getImageData(0, 0, w, h).data};
}

// the next mip level: each pixel the mean of four, colours weighed by how solid they are (no dark fringes)
function ddsHalf(src, w, h){
  const w2 = Math.max(1, w >> 1), h2 = Math.max(1, h >> 1), out = new Uint8Array(w2 * h2 * 4);
  for (let y = 0; y < h2; y++){
    const y0 = Math.min(y * 2, h - 1) * w, y1 = Math.min(y * 2 + 1, h - 1) * w;
    for (let x = 0; x < w2; x++){
      const x0 = Math.min(x * 2, w - 1), x1 = Math.min(x * 2 + 1, w - 1);
      const a = (y0 + x0) * 4, b = (y0 + x1) * 4, c = (y1 + x0) * 4, d = (y1 + x1) * 4, o = (y * w2 + x) * 4;
      const sa = src[a + 3] + src[b + 3] + src[c + 3] + src[d + 3];
      if (sa === 1020 || sa === 0){
        out[o] = (src[a] + src[b] + src[c] + src[d] + 2) >> 2; out[o + 1] = (src[a + 1] + src[b + 1] + src[c + 1] + src[d + 1] + 2) >> 2;
        out[o + 2] = (src[a + 2] + src[b + 2] + src[c + 2] + src[d + 2] + 2) >> 2;
      } else for (let k = 0; k < 3; k++)
        out[o + k] = (src[a + k] * src[a + 3] + src[b + k] * src[b + 3] + src[c + k] * src[c + 3] + src[d + k] * src[d + 3]) / sa + 0.5;
      out[o + 3] = (sa + 2) >> 2;
    }
  }
  return out;
}

const ddsTo565 = (r, g, b) => (Math.round(r * 31 / 255) << 11) | (Math.round(g * 63 / 255) << 5) | Math.round(b * 31 / 255);

// the four colours of a block's two ends, and each pixel's nearest of them: returns the error, fills idx
function ddsMatch(px, c0, c1, pal, idx){
  for (let k = 0; k < 2; k++){
    const c = k ? c1 : c0, r = c >> 11, g = (c >> 5) & 63, b = c & 31;
    pal[k * 3] = (r << 3) | (r >> 2); pal[k * 3 + 1] = (g << 2) | (g >> 4); pal[k * 3 + 2] = (b << 3) | (b >> 2);
  }
  for (let k = 0; k < 3; k++){ pal[6 + k] = (2 * pal[k] + pal[3 + k] + 1) / 3 | 0; pal[9 + k] = (pal[k] + 2 * pal[3 + k] + 1) / 3 | 0; }
  let err = 0;
  for (let i = 0; i < 16; i++){
    const r = px[i * 4], g = px[i * 4 + 1], b = px[i * 4 + 2];
    let best = 1e9, at = 0;
    for (let k = 0; k < 4; k++){
      const dr = r - pal[k * 3], dg = g - pal[k * 3 + 1], db = b - pal[k * 3 + 2], e = dr * dr + dg * dg + db * db;
      if (e < best){ best = e; at = k; }
    }
    idx[i] = at;
    err += best;
  }
  return err;
}

// one 4x4 block's colours: two ends along the colours' main axis, set right once by least squares
const DDS_T = {pal: new Int32Array(12), idx: new Uint8Array(16), idx2: new Uint8Array(16)};
function ddsColor(px, out, o, skipClear){
  let n = 0, mr = 0, mg = 0, mb = 0;
  for (let pass = 0; pass < 2 && !n; pass++)
    for (let i = 0; i < 16; i++){
      if (skipClear && !pass && px[i * 4 + 3] === 0) continue;
      n++; mr += px[i * 4]; mg += px[i * 4 + 1]; mb += px[i * 4 + 2];
    }
  const all = n === 16 || !skipClear;
  mr /= n; mg /= n; mb /= n;
  let xx = 0, xy = 0, xz = 0, yy = 0, yz = 0, zz = 0;
  for (let i = 0; i < 16; i++){
    if (!all && px[i * 4 + 3] === 0) continue;
    const r = px[i * 4] - mr, g = px[i * 4 + 1] - mg, b = px[i * 4 + 2] - mb;
    xx += r * r; xy += r * g; xz += r * b; yy += g * g; yz += g * b; zz += b * b;
  }
  let c0, c1;
  if (xx + yy + zz < 1){ c0 = c1 = ddsTo565(mr, mg, mb); }
  else {
    let vr = xx > yy && xx > zz ? 1 : 0.5, vg = yy >= xx && yy >= zz ? 1 : 0.5, vb = zz > xx && zz > yy ? 1 : 0.5;
    for (let k = 0; k < 6; k++){
      const r = xx * vr + xy * vg + xz * vb, g = xy * vr + yy * vg + yz * vb, b = xz * vr + yz * vg + zz * vb;
      const m = Math.max(Math.abs(r), Math.abs(g), Math.abs(b)) || 1;
      vr = r / m; vg = g / m; vb = b / m;
    }
    let lo = 1e9, hi = -1e9;
    for (let i = 0; i < 16; i++){
      if (!all && px[i * 4 + 3] === 0) continue;
      const t = (px[i * 4] - mr) * vr + (px[i * 4 + 1] - mg) * vg + (px[i * 4 + 2] - mb) * vb;
      if (t < lo) lo = t;
      if (t > hi) hi = t;
    }
    const L = vr * vr + vg * vg + vb * vb, cl = v => v < 0 ? 0 : v > 255 ? 255 : v;
    c0 = ddsTo565(cl(mr + vr * hi / L), cl(mg + vg * hi / L), cl(mb + vb * hi / L));
    c1 = ddsTo565(cl(mr + vr * lo / L), cl(mg + vg * lo / L), cl(mb + vb * lo / L));
  }
  if (c0 < c1){ const t = c0; c0 = c1; c1 = t; }
  const T = DDS_T;
  let idx = T.idx, err = ddsMatch(px, c0, c1, T.pal, idx);
  if (c0 !== c1 && err > 0){
    // least squares: the two ends that fit best the places the pixels took between them
    let aa = 0, ab = 0, bb = 0, ar = 0, ag = 0, abl = 0, br = 0, bg = 0, bbl = 0;
    for (let i = 0; i < 16; i++){
      if (!all && px[i * 4 + 3] === 0) continue;
      const k = idx[i], a = k === 0 ? 1 : k === 1 ? 0 : k === 2 ? 2 / 3 : 1 / 3, b = 1 - a;
      aa += a * a; ab += a * b; bb += b * b;
      ar += a * px[i * 4]; ag += a * px[i * 4 + 1]; abl += a * px[i * 4 + 2];
      br += b * px[i * 4]; bg += b * px[i * 4 + 1]; bbl += b * px[i * 4 + 2];
    }
    const det = aa * bb - ab * ab;
    if (Math.abs(det) > 1e-6){
      const cl = v => v < 0 ? 0 : v > 255 ? 255 : v;
      let n0 = ddsTo565(cl((ar * bb - br * ab) / det), cl((ag * bb - bg * ab) / det), cl((abl * bb - bbl * ab) / det));
      let n1 = ddsTo565(cl((br * aa - ar * ab) / det), cl((bg * aa - ag * ab) / det), cl((bbl * aa - abl * ab) / det));
      if (n0 < n1){ const t = n0; n0 = n1; n1 = t; }
      if (n0 !== n1 && (n0 !== c0 || n1 !== c1)){
        const e2 = ddsMatch(px, n0, n1, T.pal, T.idx2);
        if (e2 < err){ c0 = n0; c1 = n1; idx = T.idx2; err = e2; }
      }
    }
  }
  // (both ends alike: place 0 for every pixel, since place 3 of such a DXT1 block is see-through black)
  out[o] = c0 & 255; out[o + 1] = c0 >> 8; out[o + 2] = c1 & 255; out[o + 3] = c1 >> 8;
  for (let r = 0; r < 4; r++)
    out[o + 4 + r] = c0 === c1 ? 0 : idx[r * 4] | idx[r * 4 + 1] << 2 | idx[r * 4 + 2] << 4 | idx[r * 4 + 3] << 6;
}

// one block's see-through values (DXT5): the most and the least, six steps between
function ddsAlpha(px, out, o){
  let hi = 0, lo = 255;
  for (let i = 0; i < 16; i++){ const a = px[i * 4 + 3]; if (a > hi) hi = a; if (a < lo) lo = a; }
  out[o] = hi; out[o + 1] = lo;
  for (let half = 0; half < 2; half++){
    let bits = 0;
    if (hi > lo) for (let i = 0; i < 8; i++){
      const j = Math.round((hi - px[(half * 8 + i) * 4 + 3]) * 7 / (hi - lo));
      bits |= (j === 0 ? 0 : j === 7 ? 1 : j + 1) << (i * 3);
    }
    out[o + 2 + half * 3] = bits & 255; out[o + 3 + half * 3] = (bits >> 8) & 255; out[o + 4 + half * 3] = (bits >> 16) & 255;
  }
}

function ddsBlocks(src, w, h, alpha){
  const bw = (w + 3) >> 2, bh = (h + 3) >> 2, bs = alpha ? 16 : 8, out = new Uint8Array(bw * bh * bs), px = new Uint8Array(64);
  let o = 0;
  for (let by = 0; by < bh; by++) for (let bx = 0; bx < bw; bx++){
    for (let y = 0; y < 4; y++){
      const row = Math.min(by * 4 + y, h - 1) * w;
      for (let x = 0; x < 4; x++){
        const s = (row + Math.min(bx * 4 + x, w - 1)) * 4, d = (y * 4 + x) * 4;
        px[d] = src[s]; px[d + 1] = src[s + 1]; px[d + 2] = src[s + 2]; px[d + 3] = src[s + 3];
      }
    }
    if (alpha){ ddsAlpha(px, out, o); o += 8; }
    ddsColor(px, out, o, alpha);
    o += 8;
  }
  return out;
}

// the DDS file of a picture ({w, h, data: RGBA rows from the top}): every mip level down to one pixel
async function ddsMake(pix){
  const {w, h} = pix;
  let d = pix.data, lw = w, lh = h, alpha = false;
  for (let i = 3; i < d.length; i += 4) if (d[i] < 255){ alpha = true; break; }
  const levels = [];
  for (;;){
    levels.push(ddsBlocks(d, lw, lh, alpha));
    if (lw === 1 && lh === 1) break;
    d = ddsHalf(d, lw, lh);
    lw = Math.max(1, lw >> 1); lh = Math.max(1, lh >> 1);
    await new Promise(r => setTimeout(r, 0));          // (the window stays alive under a big picture)
  }
  const head = new DataView(new ArrayBuffer(128));
  head.setUint32(0, 0x20534444, true);                 // 'DDS '
  head.setUint32(4, 124, true);
  head.setUint32(8, 0xA1007, true);                    // caps, height, width, pixel format, mip count, linear size
  head.setUint32(12, h, true);
  head.setUint32(16, w, true);
  head.setUint32(20, levels[0].length, true);
  head.setUint32(28, levels.length, true);
  head.setUint32(76, 32, true);
  head.setUint32(80, 4, true);                         // a four-letter code follows
  head.setUint32(84, alpha ? 0x35545844 : 0x31545844, true);   // 'DXT5' or 'DXT1'
  head.setUint32(108, 0x401008, true);                 // a texture with mip levels
  return new Blob([head.buffer, ...levels]);
}

// the pictures a zip would hold ([{file}]) made DDS one by one, each sent to the server; returns how many were not made
async function ddsConvert(pics, say){
  let kept = 0, i = 0;
  for (const p of pics || []){
    if (say) say(++i, pics.length);
    try {
      const kind = p.file.split('.').pop().toLowerCase();
      const r = await fetch('/api/file?path=' + encodeURIComponent(p.file) + '&v=' + Date.now());
      if (!r.ok) throw new Error('not read');
      const pix = await ddsPixels(await r.arrayBuffer(), kind === 'jpeg' ? 'jpg' : kind);
      if (!pix) throw new Error('not a picture the page can read');
      const s = await fetch('/api/release/dds?' + new URLSearchParams({file: p.file}), {method: 'POST', body: await ddsMake(pix)});
      if (!s.ok) throw new Error('not taken');
    } catch (e){ kept++; console.warn('Stays as it is:', p.file, e); }
  }
  return kept;
}
