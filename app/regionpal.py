"""A region's own palette for the Style palette window (web/stylepal.js), as a building style has one: what the
game sets over that region's land, learnt from a spread of its cells. The user (2026-10-29): the game's rocks, cliffs
and other statics give land its variety and character; each region should have a relevant palette.

  Rocks & cliffs   the region's rocks (cliffrocks.is_rock), grouped by set: the models of one family, named as the
                   game names them (terrain_rock_ac_02 and _11 are one set, T_Sky_TerrRockRE_RockGrp and _Boulder
                   another), the set used most first
  Trees and plants trees, flowers and plants, grass, logs and stumps (scatter.SETS)

Each row as stylesurvey's (_row): how many of the sampled cells have it, and where to see it."""
import hashlib
import json
import os
import re

import mapdata
import regions
from project import ref_info

VERSION = 2
SAMPLE = 60                     # cells a region, spread over it
SET_MAX = 12                    # sets of rocks shown, the most used first
SECTION_ROCKS, SECTION_GROWING = 'Rocks', 'Growing'
_mem = {}


def family(rid):
    """The set a rock belongs to, by its name without numbers: its first three parts (terrain_rock_ac), or four for
    the T_ names, whose third part is a whole land's rocks (t_sky_terrrockre_rockgrp, _boulder, _rocklrg: as one,
    Druadach's set held 152 models); a name of fewer parts is its own set."""
    parts = [p for p in re.split(r'[_\s]+', rid.lower()) if p and not re.fullmatch(r'\d+[a-z]?', p)]
    if not parts:
        return rid.lower()
    return '_'.join(parts[:4] if parts[0] == 't' else parts[:3])


def _sig(db):
    plugins = db.plugins or []
    parts = sorted('%s:%s' % (p['name'].lower(), p.get('size') or 0) for i, p in enumerate(plugins) if i != db.proj_pidx)
    return hashlib.md5('|'.join(parts).encode('utf-8')).hexdigest()[:12]


def _disk(db):
    import project
    folder = os.path.join(project.APP_DIR, 'cache')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'regionpal_%s_v%d.json' % (_sig(db), VERSION))


def regions_list(db, here_key=None):
    """{'regions': [{region, name, cells}], 'here': the open outdoor place's region or None}: the regions with land
    enough to learn from (4 cells or more), by name."""
    import cliffrocks
    out = cliffrocks.looks(db)
    here = None
    if here_key and here_key.startswith('#'):
        here = regions.region_map(db).get(here_key[1:]) or None
    return {'regions': out, 'here': here}


def _learn(db, region):
    """{'cells', 'rows': {low: {id, name, type, mesh, kind, fam, cells: [keys]}}} from up to SAMPLE of its cells."""
    import cliffrocks
    import scatter
    key = (id(db.recs), region)
    if key in _mem:
        return _mem[key]
    path = _disk(db)
    disk = {}
    try:
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                disk = json.load(f)
    except (OSError, ValueError):
        disk = {}
    if region in disk:
        _mem[key] = disk[region]
        return disk[region]
    rmap = regions.region_map(db)
    cells = sorted((k for k, r in rmap.items() if r == region), key=lambda k: hashlib.md5(k.encode()).hexdigest())[:SAMPLE]
    rows, memo, used = {}, {}, 0
    for ck in cells:
        refs, _h = db.cell_refs('#' + ck)
        if not refs:
            continue
        used += 1
        for ref in refs.values():
            rid, _pos, _s, dead = ref_info(ref['subs'])
            if dead:
                continue
            low = rid.lower()
            kind = 'rocks' if cliffrocks.is_rock(low) else scatter._kind(low)
            if not kind or low.startswith(('sound', 'marker')) or any(w in low for w in ('kelp', 'lily', 'coral', 'seaweed', 'cave_')):
                continue
            if low not in memo:
                ri = db.resolve_id(rid)
                memo[low] = (db.recs[ri][0], db.recs[ri][1], db.recs[ri][2], db.recs[ri][5]) if ri is not None else None
            info = memo[low]
            if not info or info[0] not in ('STAT', 'ACTI', 'CONT'):
                continue
            r = rows.setdefault(low, {'id': info[1], 'name': info[2] or '', 'type': info[0], 'mesh': info[3] or '', 'kind': kind,
                                      'fam': family(info[1]) if kind == 'rocks' else '', 'cells': []})
            if not r['cells'] or r['cells'][-1] != ck:
                r['cells'].append(ck)
    out = {'cells': used, 'rows': rows}
    _mem[key] = out
    disk[region] = out
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(disk, f)
    except OSError:
        pass
    return out


def palette(db, region):
    """The region's palette, shaped as stylesurvey.theme's: {'name', 'places', 'line', 'sections': {Rocks: [{group,
    items}], Growing: [...]}, 'sets': [], 'examples'}."""
    import scatter
    region = (region or '').lower()
    L = _learn(db, region)
    ri = db.resolve_id(region)
    name = (db.recs[ri][2] or db.recs[ri][1]) if ri is not None else region
    n = max(1, L['cells'])

    def row(r):
        return {'id': r['id'], 'name': r['name'], 'type': r['type'], 'mesh': r['mesh'], 'grp': r['fam'] or r['kind'],
                'share': round(len(r['cells']) / float(n), 3), 'places': len(r['cells']), 'lift': None,
                'at': [['#' + ck, mapdata.cell_info(db, '#' + ck).get('name') or ('%s (%s)' % (name, ck))] for ck in r['cells'][:2]
                       if mapdata.cell_info(db, '#' + ck)], 'also': []}
    rocks = {}
    for r in L['rows'].values():
        if r['kind'] == 'rocks' and len(r['cells']) >= 2:
            rocks.setdefault(r['fam'], []).append(r)
    sets = sorted(rocks.items(), key=lambda kv: -sum(len(r['cells']) for r in kv[1]))[:SET_MAX]
    rock_groups = [{'group': fam, 'items': [row(r) for r in sorted(rs, key=lambda r: -len(r['cells']))]} for fam, rs in sets]
    grow = []
    for key, label, _w, _n in scatter.SETS:
        if key == 'rocks':
            continue
        rs = sorted((r for r in L['rows'].values() if r['kind'] == key and len(r['cells']) >= 2), key=lambda r: -len(r['cells']))
        if rs:
            grow.append({'group': label, 'items': [row(r) for r in rs[:30]]})
    ex = []
    if L['rows']:
        best = max(L['rows'].values(), key=lambda r: len(r['cells']))
        ex = [['#' + best['cells'][0], name]]
    return {'name': name, 'region': region, 'places': L['cells'],
            'line': "What the game sets over the %s's land: its rocks and cliffs by set, its trees and plants" % name,
            'sections': {SECTION_ROCKS: rock_groups, SECTION_GROWING: grow}, 'sets': [], 'examples': ex}
