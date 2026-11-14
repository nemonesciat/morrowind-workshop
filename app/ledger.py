"""The places ledger: every town, castle, dungeon, interior and land stage a maker makes is written down in the project
(project.places) with what it was made from and which pieces are its own.

Before, nothing knew what a Make had made. Whether a town stood at an outline, and which things were its to take away,
was worked out again each time from where things stood and the run of their numbers (townbuild.made_inside, the two
remove()s): a walled town beside a castle read as the castle, a second city was built over a first, and a castle's
remove lost eleven wall pieces (2026-11-01 to 2026-11-09). With a record it is a look-up, and one place can be taken
away or made again on its own however much was built after it.

A record: {'id': 'pl7', 'kind': 'town'|'castle'|'dungeon'|'interior'|'land', 'name', 'outline': [[x, y], ...],
'seed', 'opts': the maker's own arguments, 'state': 'making'|'made'|'part', 'parent': the record it was made inside,
'refs': [[first, last], ...] the numbers of the ref keys handed out while it was open, 'cells': the interiors put in
new, 'recs': the people, creatures and containers put in new}.

The pieces are written in by the project itself (project.LEDGER: Project.new_ref_key, Tracked's new keys), so a maker
only opens its record:  with ledger.open(db, 'town', name, outline, seed, opts): ...   Records opened inside another
are its children (a town's own-made interiors), and a place's pieces are its family's.

The ledger is part of the mod's state: Undo and Redo put it back with the things themselves, and it is saved with the
project. A place made before the ledger has no record; the old ways of finding it still serve those."""
import contextlib
import json
import math
import threading

import project
from project import quiet

KINDS = ('town', 'castle', 'dungeon', 'interior', 'land')
OWN_RECS = ('NPC_', 'CREA', 'CONT')       # (records a place may take with it: never land, textures or regions; of talk
                                          # only the lines one of its own people alone could say, _own_lines)


def _own_lines(p, recs):
    """The mod's dialogue lines whose speaker, by ID, is one of the people about to go: {topic key: [record keys]}.
    Nobody else can say them: a town of 20 people removed left 85 such lines in the mod (2026-11-13)."""
    ids = {k.split('|', 1)[1].lower() for k in recs if k.startswith('NPC_|')}
    out = {}
    if not ids:
        return out
    from esm import iter_subrecords
    for k, r in list(p.records.items()):
        if not k.startswith('INFO|') or k.count('|') < 2:
            continue
        try:
            who = next((project.zstr(bytes(d)) for t, d in iter_subrecords(project.unb64(r['data'])) if t == 'ONAM'), '')
        except Exception:
            continue
        if who.lower() in ids:
            out.setdefault(k.split('|')[1], []).append(k)
    return out
NOUN = {'town': 'the town', 'castle': 'the castle', 'dungeon': 'the dungeon', 'interior': 'the interior', 'land': 'the land stage'}


def _places(p):
    pl = getattr(p, 'places', None)
    if pl is None:
        pl = p.places = {}
    return pl


def _plain(v):
    """v if it can be saved as it is, else None."""
    try:
        json.dumps(v)
        return v
    except (TypeError, ValueError):
        return None


def _new_id(pl):
    n = 1 + max([int(k[2:]) for k in pl if k[:2] == 'pl' and k[2:].isdigit()] or [0])
    return 'pl%d' % n


def _empty(rec):
    return not (rec.get('refs') or rec.get('cells') or rec.get('recs'))


@contextlib.contextmanager
def open(db, kind, name='', outline=None, seed=None, opts=None, resume=None):
    """A record open while its maker works: what is made meanwhile, in this thread, is its own. resume: the id of a
    record to go on with (a town's interiors made later). Yields the record (None with no project open); a maker
    that learns its place's name as it goes sets rec['name']."""
    p = getattr(db, 'project', None)
    if p is None:
        yield None
        return
    pl = _places(p)
    ident = threading.get_ident()
    st = project.LEDGER.setdefault(ident, [])
    fresh = not (resume and resume in pl)
    if fresh:
        rec = {'id': _new_id(pl), 'kind': kind, 'name': name or '', 'state': 'making'}
        if outline:
            rec['outline'] = [[round(float(q[0]), 1), round(float(q[1]), 1)] for q in outline]
        if seed is not None:
            rec['seed'] = seed
        o = {k: v for k, v in (opts or {}).items() if _plain(v) is not None}      # (what cannot be saved is left out)
        if o:
            rec['opts'] = o
        if st and st[-1].get('kind') != 'land':                # (a land stage owns its scattered things, never a place)
            rec['parent'] = st[-1]['id']
        pl[rec['id']] = rec
    else:
        rec = pl[resume]
    was = rec.get('state')
    st.append(rec)
    try:
        yield rec
    except BaseException:
        rec['state'] = 'part'               # (it stopped half way: what it made stands, and is still its own)
        raise
    else:
        rec['state'] = 'made' if fresh or was != 'part' else was
    finally:
        st.pop()
        if not st:
            project.LEDGER.pop(ident, None)
        for k in ('cells', 'recs'):
            if rec.get(k):
                rec[k] = list(dict.fromkeys(rec[k]))
        p = getattr(db, 'project', None)
        seen_ = _GROUND.pop((ident, rec.get('id')), None)
        if p is not None and seen_:
            try:
                _ground_close(db, rec, seen_)          # (the ground as it lay before, kept with the place)
            except Exception as e:
                print('ledger: ground:', repr(e))
        if p is not None:
            pl = _places(p)                 # (an Undo meanwhile put another table in: the record goes into that one)
            if fresh and _empty(rec):
                pl.pop(rec['id'], None)
                # (what was made inside it is the next record's out: an interior of the Workshop's own layout is made
                # by one maker inside another's record, the outer one holding nothing itself; dropped, it left the
                # interior with no town, and removing the town left that interior standing, 2026-11-13)
                for r_ in pl.values():
                    if r_.get('parent') == rec['id']:
                        if rec.get('parent'):
                            r_['parent'] = rec['parent']
                        else:
                            r_.pop('parent', None)
            else:
                pl[rec['id']] = rec
            if not st:
                _tidy(db)
                _amend(db)


def _tidy(db):
    """Records nothing is left of taken out: a roll not kept, a place whose every thing was deleted by hand."""
    p = db.project
    pl = _places(p)
    if not pl:
        return
    idx = _standing(db, fresh=True)
    live = set()
    for k, r in pl.items():
        if r.get('state') == 'making' or any(c in p.cells for c in r.get('cells') or ()) or \
                any(n in idx for lo, hi in r.get('refs') or () for n in range(int(lo), int(hi) + 1)):
            # (and the records it was made inside: a town whose walls are gone still holds its interiors)
            while k in pl and k not in live:
                live.add(k)
                k = pl[k].get('parent')
    for k in [k for k in pl if k not in live]:
        pl.pop(k)


def _amend(db):
    """The last state kept for Undo told how the ledger stands now: a maker's record is closed after its last change,
    and without this a Redo brought the place back as still 'making'. No Undo step of its own."""
    p = db.project
    ls = p.__dict__.get('last_state')
    if isinstance(ls, project.Snap):
        m = json.dumps(p.meta())
        if m != ls.m:
            p.last_state = project.Snap(ls.r, ls.c, ls.g, m, ls.size)
            p.__dict__.pop('_ledger_idx', None)
            try:
                import editing
                editing._write_soon(db)
            except Exception as e:
                print('ledger:', e)


# The ground as it lay before a place was made, kept with its record: landscape.write tells note_ground of each cell
# before it changes it; when the record closes, the land points and ground textures that differ are packed into
# rec['ground'] ({'gx,gy': {'h': packed (point, before, after), 't': {patch: [before, after]}}}). Drop can then put the
# ground back where it still lies as the place left it (_ground_back). A land stage keeps none: its own Undo is its
# way back, and it would hold every point of every cell.
GROUND_CELLS = 40               # (a place keeps the ground of this many cells at most)
GROUND_SAME = 4.0               # (a land point this near where the place left it has not been reshaped since)
_GROUND = {}                    # (thread, record id) -> {(gx, gy): (heights before, textures before)}


def note_ground(db, gx, gy, cur):
    """A cell's land is about to change (landscape.write; cur: landscape.read's answer): kept as it is for every
    record open in this thread, the first time each sees the cell."""
    ident = threading.get_ident()
    st = project.LEDGER.get(ident)
    if not st:
        return
    for rec in st:
        if rec.get('kind') == 'land' or not rec.get('id'):
            continue
        g = _GROUND.setdefault((ident, rec['id']), {})
        if (gx, gy) not in g and len(g) < GROUND_CELLS:
            g[(gx, gy)] = (list(cur.get('h') or ()), list(cur.get('t') or ()))


def _pack(rows):
    """[(point, before, after)] as text for the mod's file."""
    import base64
    import struct
    import zlib
    n = len(rows)
    raw = struct.pack('<%dH' % n, *[r[0] for r in rows]) + struct.pack('<%df' % n, *[r[1] for r in rows]) + struct.pack('<%df' % n, *[r[2] for r in rows])
    return {'n': n, 'd': base64.b64encode(zlib.compress(raw, 6)).decode('ascii')}


def _unpack(v):
    import base64
    import struct
    import zlib
    if not v or not v.get('n'):
        return []
    n = int(v['n'])
    raw = zlib.decompress(base64.b64decode(v['d']))
    idx = struct.unpack_from('<%dH' % n, raw, 0)
    bef = struct.unpack_from('<%df' % n, raw, 2 * n)
    aft = struct.unpack_from('<%df' % n, raw, 6 * n)
    return list(zip(idx, bef, aft))


def _ground_close(db, rec, seen):
    """A record closing: what its making changed of the ground it saw, into rec['ground'] (added to what an earlier
    making of the same record kept: the first 'before' stands)."""
    if not seen:
        return
    import landscape
    G = dict(rec.get('ground') or {})
    for (gx, gy), (hb, tb) in seen.items():
        key = '%d,%d' % (gx, gy)
        try:
            now = landscape.read(db, gx, gy)
        except Exception:
            continue
        if not now.get('exists'):
            continue
        old = G.get(key) or {}
        ha, ta = now.get('h') or (), now.get('t') or ()
        rows = {}
        if hb and len(hb) == len(ha):
            for i in range(len(ha)):
                if abs(ha[i] - hb[i]) >= 1.0:
                    rows[i] = (hb[i], ha[i])
        for i, b, a in _unpack(old.get('h')):
            # (seen before by this record: its first 'before', and where it lies now)
            if i < len(ha) and abs(ha[i] - b) >= 1.0:
                rows[i] = (b, ha[i])
            else:
                rows.pop(i, None)
        tex = {}
        if tb and len(tb) == len(ta):
            for i in range(len(ta)):
                if (ta[i] or '') != (tb[i] or ''):
                    tex[str(i)] = [tb[i] or '', ta[i] or '']
        for i, ba in (old.get('t') or {}).items():
            if int(i) < len(ta) and (ta[int(i)] or '') != (ba[0] or ''):
                tex[i] = [ba[0] or '', ta[int(i)] or '']
            else:
                tex.pop(i, None)
        if rows or tex:
            G[key] = {'h': _pack([(i, b, a) for i, (b, a) in sorted(rows.items())]), 't': tex}
        else:
            G.pop(key, None)
    if G:
        rec['ground'] = G
    else:
        rec.pop('ground', None)


def _ground_back(db, rec, look=False):
    """The ground under a made place put back as it lay before the place was made: every land point and ground
    texture its making changed that still is as the making left it (within GROUND_SAME); what was reshaped or painted
    since stays. What stands on the ground rides it. look: only count. The land points put back."""
    G = rec.get('ground') or {}
    if not G:
        return 0
    import landscape
    todo, total = [], 0
    for key, v in G.items():
        gx, gy = (int(t) for t in key.split(','))
        try:
            cur = landscape.read(db, gx, gy)
        except Exception:
            continue
        if not cur.get('exists') or not cur.get('h'):
            continue
        h, n = list(cur['h']), 0
        for i, b, a in _unpack(v.get('h')):
            if i < len(h) and abs(h[i] - a) <= GROUND_SAME and abs(h[i] - b) >= 1.0:
                h[i] = b
                n += 1
        t, nt = list(cur.get('t') or ()), 0
        for i, ba in (v.get('t') or {}).items():
            i = int(i)
            if i < len(t) and (t[i] or '') == (ba[1] or '') and (ba[0] or '') != (ba[1] or ''):
                t[i] = ba[0]
                nt += 1
        if n or nt:
            total += n
            todo.append((gx, gy, h if n else None, t if nt else None, list(cur['h'])))
    if look or not todo:
        return total
    new_h = {(gx, gy): h for gx, gy, h, _t, _b in todo if h is not None}
    for gx, gy, h, t, before in todo:
        after = landscape.write(db, gx, gy, h, t, None, around=landscape.around_of(db, gx, gy, new_h))
        if h is not None:
            landscape._follow_ground(db, gx, gy, before, after, ())
            try:
                landscape._follow_paths(db, gx, gy, before, after)
            except Exception as e:
                print('ledger: ground back, paths:', e)
    db.sync_project()
    return total


def opened():
    """The record open in this thread now (the innermost), or None."""
    st = project.LEDGER.get(threading.get_ident())
    return st[-1] if st else None


# ------------------------------------------------------------------------------------------------------- look-ups
def _standing(db, fresh=False):
    """{ref number: the place it stands in} for the mod's own things."""
    p = db.project
    ls = p.__dict__.get('last_state')
    memo = p.__dict__.get('_ledger_idx')
    if not fresh and memo and ls is not None and memo[0] is ls:
        return memo[1]
    pre = p.plugin.lower() + '|'
    n = len(pre)
    idx = {}
    for ck, c in quiet(p.cells):
        for rk in (c.get('refs') or ()):
            if rk.startswith(pre) and rk[n:].isdigit():
                idx[int(rk[n:])] = ck
    p.__dict__['_ledger_idx'] = (ls, idx)
    return idx


def family(db, pid):
    """A record's id and those of every record made inside it."""
    pl = _places(db.project)
    kids = {}
    for k, r in pl.items():
        if r.get('parent'):
            kids.setdefault(r['parent'], []).append(k)
    out, todo = [], [pid]
    while todo:
        k = todo.pop()
        if k in pl and k not in out:
            out.append(k)
            todo.extend(kids.get(k, ()))
    return out


def _numbers(pl, fam):
    for k in fam:
        for lo, hi in pl[k].get('refs') or ():
            for n in range(int(lo), int(hi) + 1):
                yield n


def pieces(db, pid, fresh=False):
    """[(place, ref key)] of a made place's own things that still stand."""
    p = db.project
    pl = _places(p)
    idx = _standing(db, fresh)
    pre = p.plugin.lower() + '|'
    return [(idx[n], '%s%d' % (pre, n)) for n in _numbers(pl, family(db, pid)) if n in idx]


def _interiors(db, fam):
    p = db.project
    pl = _places(p)
    return list(dict.fromkeys(k for f in fam for k in pl[f].get('cells') or () if k in p.cells))


def _centre(poly):
    return (sum(q[0] for q in poly) / float(len(poly)), sum(q[1] for q in poly) / float(len(poly)))


def _inside(poly, x, y):
    n, c = len(poly), False
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-9) + x1:
            c = not c
    return c


def _top(pl, rec):
    return not rec.get('parent') or rec['parent'] not in pl


def summary(db):
    """The made places, newest first: [{'id', 'kind', 'name', 'state', 'seed', 'things', 'interiors', 'at': [x, y],
    'again'}] for every record not made inside another whose things still stand."""
    p = getattr(db, 'project', None)
    if p is None:
        return []
    pl = _places(p)
    idx = _standing(db)
    out = []
    for k, r in pl.items():
        if not _top(pl, r):
            continue
        fam = family(db, k)
        n = sum(1 for m in _numbers(pl, fam) if m in idx)
        ins = _interiors(db, fam)
        if not n and not ins:
            continue
        row = {'id': k, 'kind': r.get('kind'), 'name': r.get('name') or '', 'state': r.get('state') or 'made', 'seed': r.get('seed'),
               'things': n, 'interiors': len(ins), 'again': r.get('kind') in AGAIN and bool(r.get('outline')) and r.get('state') != 'making'}
        if r.get('outline'):
            row['at'] = [round(v) for v in _centre(r['outline'])]
        elif ins:
            row['cell'] = ins[0]
        if not row['name'] and ins:
            row['name'] = ins[0].title()
        out.append(row)
    out.sort(key=lambda r: -int(r['id'][2:]))
    return out


def at(db, outline, kind=None):
    """The made place standing at an outline: the record of that kind whose middle lies inside the outline, or the
    outline's inside its own, the nearest of them; things of it must still stand. None when there is none."""
    p = getattr(db, 'project', None)
    poly = [(float(q[0]), float(q[1])) for q in outline or ()]
    if p is None or len(poly) < 3:
        return None
    pl = _places(p)
    idx = _standing(db)
    cx, cy = _centre(poly)
    best = None
    for k, r in pl.items():
        o = r.get('outline')
        if not o or len(o) < 3 or (kind and r.get('kind') != kind) or not _top(pl, r):
            continue
        ox, oy = _centre(o)
        if not (_inside(poly, ox, oy) or _inside(o, cx, cy)):
            continue
        if not any(m in idx for m in _numbers(pl, family(db, k))):
            continue
        d = math.hypot(ox - cx, oy - cy)
        if best is None or d < best[0]:
            best = (d, k)
    return best and best[1]


def named(db, kind, name):
    """The newest record of a kind with this name (a town kept for its interiors later), or None."""
    p = getattr(db, 'project', None)
    if p is None or not name:
        return None
    pl = _places(p)
    got = [k for k, r in pl.items() if r.get('kind') == kind and (r.get('name') or '').lower() == name.lower() and _top(pl, r)]
    return max(got, key=lambda k: int(k[2:])) if got else None


def owner(db, ref_key):
    """The id of the record a ref key was made in (the innermost), or None."""
    p = getattr(db, 'project', None)
    t = str(ref_key).rsplit('|', 1)[-1]
    if p is None or not t.isdigit():
        return None
    n = int(t)
    for k, r in _places(p).items():
        for lo, hi in r.get('refs') or ():
            if lo <= n <= hi:
                return k
    return None


def top_of(db, pid):
    """The record a record was made inside, all the way up."""
    pl = _places(db.project)
    seen = set()
    while pid in pl and pl[pid].get('parent') in pl and pid not in seen:
        seen.add(pid)
        pid = pl[pid]['parent']
    return pid


# ---------------------------------------------------------------------------------------------------- taking away
def drop(db, pid, look=False, ground=False):
    """One made place taken away as one step, whatever was built after it: its own things that still stand, the
    interiors it made (but one a door left standing still leads into stays) and the people, creatures and containers
    it made that nothing left standing uses. What you added stays. The ground stays as it was shaped, or with ground
    goes back to how it lay before the place was made, where nothing has reshaped it since (_ground_back).
    look: only count. {'things', 'interiors', 'name', 'kind', 'ground': land points that would go (or went) back}"""
    import editing
    from editing import EditError
    editing._require_project(db)
    p = db.project
    pl = _places(p)
    if pid not in pl:
        raise EditError('That place is no longer in the mod.')
    rec = pl[pid]
    fam = family(db, pid)
    out = pieces(db, pid, fresh=True)
    gone = {rk for _ck, rk in out}
    inside = _interiors(db, fam)
    recs = [k for f in fam for k in pl[f].get('recs') or () if k in p.records and k[:4] in OWN_RECS]
    # (what is left standing: the interiors its doors lead into, and the things it stands as)
    low = {k.lower(): k for k in inside}
    ids = {k.split('|', 1)[1].lower(): k for k in recs}
    away = set(inside)
    kept, used = set(), set()
    if low or ids:
        for ck, c in quiet(p.cells):
            mine = ck in away
            for rk, r in (c.get('refs') or {}).items():
                if rk in gone or mine:
                    continue
                for tag, b in r.get('subs') or ():
                    if tag == 'DNAM' and low:
                        k = low.get(project.zstr(project.unb64(b)).lower())
                        if k:
                            kept.add(k)
                    elif tag == 'NAME' and ids:
                        k = ids.get(project.zstr(project.unb64(b)).lower())
                        if k:
                            used.add(k)
    inside = [k for k in inside if k not in kept]
    recs = [k for k in dict.fromkeys(recs) if k not in used]
    name = rec.get('name') or ''
    lines = _own_lines(p, recs)
    res = {'things': len(out), 'interiors': len(inside), 'name': name, 'kind': rec.get('kind'), 'id': pid,
           'lines': sum(len(v) for v in lines.values()), 'ground': 0}
    if look:
        try:
            res['ground'] = _ground_back(db, rec, look=True)
        except Exception as e:
            print('ledger: ground:', repr(e))
        return res
    if not out and not inside:
        raise EditError('Nothing of it still stands.')
    for ck, rk in out:
        c = p.cells.get(ck)
        if c and rk in (c.get('refs') or {}):
            c['refs'].pop(rk)
            p.town_parts.pop(rk, None)
            p.scattered.discard(rk)
    for k in inside:
        p.cells.pop(k, None)
        p.records.pop('PGRD|' + k, None)
    for k in recs:
        p.records.pop(k, None)
    if lines:
        # (their lines out of each topic, the mod's other lines there linked up again)
        for ks in lines.values():
            for k in ks:
                p.records.pop(k, None)
        db.sync_project()
        try:
            import dialogue
            for dkey in lines:
                dialogue._relink(db, dkey)
                dialogue._maybe_drop_dial(db, dkey)
        except Exception as e:
            print('ledger: relinking lines:', repr(e))
    if ground:
        try:
            db.sync_project()
            res['ground'] = _ground_back(db, rec)
        except Exception as e:
            print('ledger: ground back:', repr(e))
    for f in fam:
        pl.pop(f, None)
    if rec.get('kind') == 'town' and name:
        later = (getattr(p, 'land', None) or {}).get('towns_later') or {}
        if name in later:
            p.land = dict(p.land, towns_later={k: v for k, v in later.items() if k != name})
            p.save_soon()
    editing.commit(db, 'Removed %s%s: %d things and %d interiors%s' % (NOUN.get(rec.get('kind'), 'the place'), ' ' + name if name else '',
                                                                   len(out), len(inside), ', the ground put back' if res.get('ground') else ''))
    return res


# ---------------------------------------------------------------------------------------------------- made again
def _again_town(db, rec, seed):
    import townbuild
    o = rec.get('opts') or {}
    return townbuild.make(db, rec['outline'], o.get('culture') or '', seed, o.get('walls') or '', o.get('dress', True),
                          o.get('interiors', False), o.get('people', False), rec.get('name') or '', o.get('opts'))


def _again_castle(db, rec, seed):
    import castle
    o = rec.get('opts') or {}
    return castle.make(db, rec['outline'], o.get('style') or 'Imperial', o.get('size') or 'medium', seed, rec.get('name') or '',
                       people=o.get('people', True), rooms=o.get('rooms') or 'furnished', gate=o.get('gate'))


AGAIN = {'town': _again_town, 'castle': _again_castle}


def again(db, pid, seed=None):
    """One made place taken away and made anew where it stood, from what its record keeps: the same outline, name and
    choices, another seed (its own + 1 unless given). The maker's own answer, with 'removed' (drop's)."""
    import editing
    from editing import EditError
    editing._require_project(db)
    pl = _places(db.project)
    rec = pl.get(pid)
    if not rec or rec.get('kind') not in AGAIN or not rec.get('outline'):
        raise EditError('That place cannot be made again from its record.')
    rec = json.loads(json.dumps(rec))
    seed = int(seed) if seed is not None else int(rec.get('seed') or 1) + 1
    stack = db.project.__dict__.setdefault('undo_stack', [])
    s0 = len(stack)
    gone = drop(db, pid)
    res = AGAIN[rec['kind']](db, rec, seed)
    stack = db.project.undo_stack
    if len(stack) - s0 > 1:
        # (the taking away and the making are one step: the removal left on its own was an Undo that did nothing)
        editing.fold(db, len(stack) - s0, 'Made %s again' % (rec.get('name') or NOUN.get(rec.get('kind'), 'the place')))
    if isinstance(res, dict):
        res = dict(res, removed=gone, seed=seed)
    return res
