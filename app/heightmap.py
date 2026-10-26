"""Height maps in and out (packaging/terrain-shaping-proposal.md §4.4): a range of cells as a 16-bit greyscale PNG
to work on in World Machine, Gaea, GIMP or Krita, and a PNG brought back (or any height map: a real place's
elevation, a painting) as land.

A range of n x m cells is (64n + 1) x (64m + 1) pixels, a pixel a point of the land (128 units), the top row
the north edge, as a map is read. The export says in a text chunk which cells it is and which heights black
and white stand for, so a map edited elsewhere comes back where it was at the same heights; any other map
is placed where you choose, with a top height and a sea level (the grey that is the water line).

Brought back, the land fades over a blend width from what is there (or the sea bed) at the edge of the area
to the map inside, so the edges with the cells round it stay exactly as they are; cells with no land get
it first; steps too steep for the record are eased; settled cells (landsurvey) are refused unless allowed.
One Undo step."""
import base64
import struct
import zlib

import landrange
import landscape
from editing import EditError, commit, _require_project

N = 65
MAX_PX = 64 * 40 + 1                 # (40 cells across, about 6.5 million points: more is a job for the brushes)


def _chunk(t, d):
    return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)


def write_png16(w, h, vals, text=None):
    """A 16-bit greyscale PNG of w x h values 0-65535, rows top first."""
    rows = bytearray()
    for y in range(h):
        rows.append(0)
        rows += struct.pack('>%dH' % w, *vals[y * w:(y + 1) * w])
    out = b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 16, 0, 0, 0, 0))
    if text:
        out += _chunk(b'tEXt', b'MorrowindWorkshop\0' + text.encode('latin-1'))
    return out + _chunk(b'IDAT', zlib.compress(bytes(rows), 6)) + _chunk(b'IEND', b'')


def read_png(raw):
    """(w, h, [0..1 per pixel, rows top first], text) of a greyscale or colour PNG, 8 or 16 bits (the first
    channel: grey, or red)."""
    if raw[:8] != b'\x89PNG\r\n\x1a\n':
        raise EditError('That is not a PNG picture.')
    p, idat, hdr, text = 8, bytearray(), None, ''
    while p + 8 <= len(raw):
        n, typ = struct.unpack_from('>I4s', raw, p)
        body = raw[p + 8:p + 8 + n]
        if typ == b'IHDR':
            hdr = struct.unpack('>IIBBBBB', body)
        elif typ == b'IDAT':
            idat += body
        elif typ == b'tEXt' and body.startswith(b'MorrowindWorkshop\0'):
            text = body.split(b'\0', 1)[1].decode('latin-1')
        elif typ == b'IEND':
            break
        p += 12 + n
    if not hdr:
        raise EditError('The PNG has no header.')
    w, h, depth, ctype, _c, _f, inter = hdr
    if inter or depth not in (8, 16) or ctype not in (0, 2, 4, 6):
        raise EditError('Save the height map as a plain (not interlaced) 8- or 16-bit greyscale PNG.')
    if w > MAX_PX or h > MAX_PX:
        raise EditError('The height map is %d x %d; at most %d across (40 cells).' % (w, h, MAX_PX))
    chans = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
    bpp = chans * depth // 8
    stride = w * bpp
    data = zlib.decompress(bytes(idat))
    out, prev, q = [0.0] * (w * h), bytearray(stride), 0
    top = 65535.0 if depth == 16 else 255.0
    for y in range(h):
        f = data[q]
        row = bytearray(data[q + 1:q + 1 + stride])
        q += 1 + stride
        if f == 1:
            for i in range(bpp, stride):
                row[i] = (row[i] + row[i - bpp]) & 255
        elif f == 2:
            for i in range(stride):
                row[i] = (row[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                row[i] = (row[i] + ((row[i - bpp] if i >= bpp else 0) + prev[i]) // 2) & 255
        elif f == 4:
            for i in range(stride):
                a = row[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                row[i] = (row[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        o = y * w
        if depth == 16:
            for x in range(w):
                out[o + x] = ((row[x * bpp] << 8) | row[x * bpp + 1]) / top
        else:
            for x in range(w):
                out[o + x] = row[x * bpp] / top
        prev = row
    return w, h, out, text


def export_png(db, x0, y0, x1, y1):
    """{'png': base64, 'name', 'lo', 'hi', 'cells'}: the land of cells x0..x1, y0..y1 as a 16-bit height map."""
    x0, y0, x1, y1 = min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)
    if (x1 - x0 + 1) * 64 + 1 > MAX_PX or (y1 - y0 + 1) * 64 + 1 > MAX_PX:
        raise EditError('Export at most 40 cells across.')
    G = landrange.Grid(db, x0, y0, x1, y1)
    lo, hi = min(G.z), max(G.z)
    if hi - lo < 1:
        hi = lo + 1
    # (rounded out to 8, the record's own step, so the same numbers come back)
    lo, hi = 8 * int(lo // 8), 8 * int(-(-hi // 8))
    span = float(hi - lo)
    vals = []
    for y in range(G.h - 1, -1, -1):                 # (north at the top)
        row = y * G.w
        vals.extend(int(round((G.z[row + x] - lo) / span * 65535)) for x in range(G.w))
    text = 'cells=%d,%d,%d,%d black=%d white=%d' % (x0, y0, x1, y1, lo, hi)
    png = write_png16(G.w, G.h, vals, text)
    return {'png': base64.b64encode(png).decode('ascii'), 'name': 'land %d,%d to %d,%d.png' % (x0, y0, x1, y1),
            'lo': lo, 'hi': hi, 'cells': (x1 - x0 + 1) * (y1 - y0 + 1), 'size': [G.w, G.h]}


def info(raw_b64):
    """What a PNG holds, for the import box: its size, the cells it covers at a pixel a point, and where and at
    what heights it came from if the Workshop exported it."""
    raw = base64.b64decode(raw_b64)
    w, h, _v, text = read_png(raw)
    out = {'w': w, 'h': h, 'across': max(1, round((w - 1) / 64.0)), 'down': max(1, round((h - 1) / 64.0))}
    meta = _meta(text)
    if meta:
        out.update(meta)
    return out


def _meta(text):
    try:
        d = dict(kv.split('=') for kv in text.split())
        x0, y0, x1, y1 = (int(v) for v in d['cells'].split(','))
        return {'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1, 'black': float(d['black']), 'white': float(d['white'])}
    except Exception:
        return None


def import_png(db, raw_b64, gx0, gy0, across=None, black=-2048.0, white=4096.0, blend=2048.0, allow_settled=False, paint=False):
    """Land from a height map: its bottom-left cell at (gx0, gy0), `across` cells wide (the picture is stretched to
    fit, its shape kept), black and white at those heights; faded in over `blend` from the area's edge."""
    _require_project(db)
    raw = base64.b64decode(raw_b64)
    w, h, vals, _text = read_png(raw)
    n = max(1, int(across or round((w - 1) / 64.0)))
    m = max(1, int(round(n * (h - 1) / float(max(1, w - 1)))))
    if n * m > landrange.MAX_CELLS:
        raise EditError('That is %d cells; bring in at most %d at once.' % (n * m, landrange.MAX_CELLS))
    keys = [(gx0 + i, gy0 + j) for j in range(m) for i in range(n)]
    import landsurvey
    s = landsurvey.ready(db)
    if s and not allow_settled:
        busy = [k for k in keys if (lambda c: c and landsurvey.level(c) == 'settled')(s['cells'].get('%d,%d' % k))]
        if busy:
            c = s['cells']['%d,%d' % busy[0]]
            raise EditError('%d of those cells are settled (%s: %d doors into interiors). Allow settled cells to bring '
                            'the map in over them.' % (len(busy), c['name'] or '%d, %d' % busy[0], c['doors']))
    made = 0
    for gx, gy in keys:
        if landscape.new_land(db, gx, gy, landrange._region_of(db, gx, gy)):
            made += 1
    G = landrange.Grid(db, gx0 - 1, gy0 - 1, gx0 + n, gy0 + m)
    before = {k: G.cell(*k) for k in keys}
    inside = bytearray(G.w * G.h)
    for y in range(65, 65 + 64 * m - 1):
        for x in range(65, 65 + 64 * n - 1):
            inside[y * G.w + x] = 1
    dist = landrange._distance(inside, G.w, G.h)
    span = float(white) - float(black)
    pw, ph = 64 * n + 1, 64 * m + 1
    for y in range(64, 64 + ph):
        py = (ph - 1 - (y - 64)) * (h - 1) / float(ph - 1)     # (picture rows top first: north)
        y0_ = min(h - 2, int(py)) if h > 1 else 0
        fy = py - y0_ if h > 1 else 0.0
        for x in range(64, 64 + pw):
            i = y * G.w + x
            if not inside[i]:
                continue
            px = (x - 64) * (w - 1) / float(pw - 1)
            x0_ = min(w - 2, int(px)) if w > 1 else 0
            fx = px - x0_ if w > 1 else 0.0
            a = vals[y0_ * w + x0_]
            b = vals[y0_ * w + min(w - 1, x0_ + 1)]
            c = vals[min(h - 1, y0_ + 1) * w + x0_]
            d = vals[min(h - 1, y0_ + 1) * w + min(w - 1, x0_ + 1)]
            g = (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy
            want = float(black) + g * span
            t = landrange._smooth(dist[i] * 128.0 / max(128.0, float(blend)))
            G.z[i] = G.z[i] + (want - G.z[i]) * t
    eased = landrange.ease_cliffs(G, inside)
    new_h = {k: G.cell(*k) for k in keys}
    moved = 0
    tables = {}
    for gx, gy in keys:
        tex = None
        if paint:
            r = landrange._region_of(db, gx, gy)
            if r not in tables:
                tables[r] = landrange._texture_table(db, r)
            tex = landrange._paint(G, gx, gy, tables[r])
        after = landscape.write(db, gx, gy, new_h[(gx, gy)], tex, None, around=landscape.around_of(db, gx, gy, new_h))
        moved += landscape._follow_ground(db, gx, gy, before[(gx, gy)], after)
        landscape._follow_paths(db, gx, gy, before[(gx, gy)], after)
    db.sync_project()
    commit(db, 'Brought in a height map over %d cell%s%s' % (len(keys), '' if len(keys) == 1 else 's', (' (%d new)' % made) if made else ''))
    return {'cells': len(keys), 'across': n, 'down': m, 'new': made, 'eased': eased, 'moved': moved}
