"""The Use report (F1): everywhere something is used. The places it stands in (and how many),
the characters, containers and lists that carry it, and the scripts and dialogue that name it."""
import re

import mapdata
from database import TYPE_NAMES
from project import ref_info


def _place_label(info):
    if info['interior']:
        return info['name'] or info['id']
    return '%s (%d, %d)' % (info['name'] or info['region'] or 'Wilderness', info['gx'], info['gy'])


def report(db, rid, count_cells=80, text_hits=80):
    low = (rid or '').strip().lower()
    ri = db.resolve_id(low)
    out = {'id': db.recs[ri][1] if ri is not None else rid, 'name': db.recs[ri][2] if ri is not None else '',
           'type': db.recs[ri][0] if ri is not None else '', 'i': ri,
           'type_label': TYPE_NAMES.get(db.recs[ri][0], db.recs[ri][0]) if ri is not None else ''}
    seen, cells, holders = set(), [], []
    for u in sorted(db.used_in.get(low, ())):
        ur = db.recs[u]
        if ur is None or (ur[0], ur[7]) in seen:
            continue
        seen.add((ur[0], ur[7]))
        if ur[0] == 'CELL':
            cells.append(ur[7])
            continue
        w = db.versions(u)[-1]
        if w in db.dead:
            continue
        wr = db.recs[w]
        holders.append({'i': w, 'type': wr[0], 'type_label': TYPE_NAMES.get(wr[0], wr[0]), 'id': wr[1], 'name': wr[2],
                        'mine': wr[3] == db.proj_pidx})
    # the places, and how many stand in each (as the game sees it: a later file may have taken them out)
    places, total = [], 0
    for n, key in enumerate(cells):
        info = mapdata.cell_info(db, key)
        if not info:
            continue
        cnt = None
        if n < count_cells:
            refs, _h = db.cell_refs(key)
            cnt = 0
            for ref in refs.values():
                r_id, _p, _s, deleted = ref_info(ref['subs'])
                if not deleted and r_id.lower() == low:
                    cnt += 1
            if not cnt:
                continue
            total += cnt
        places.append({'key': key, 'label': _place_label(info), 'n': cnt, 'interior': info['interior']})
    places.sort(key=lambda p: (-(p['n'] or 0), p['label'].lower()))
    out['places'], out['placed'], out['places_counted'] = places, total, min(len(cells), count_cells) >= len(cells)
    out['holders'] = holders[:300]
    # scripts and dialogue lines that name it
    pat = re.compile(rb'(?<![\w])' + re.escape(low.encode('cp1252', 'replace')) + rb'(?![\w])') if len(low) >= 3 else None
    texts = []
    if pat:
        for (tag, _key), lst in db.by_key.items():
            if tag not in ('SCPT', 'INFO') or len(texts) >= text_hits:
                continue
            live = [v for v in lst if v not in db.dead]
            if not live:
                continue
            v = live[-1]
            r = db.recs[v]
            data = db.files[r[3]].record_at(r[4])[2]
            if not pat.search(data.lower()):
                continue
            if tag == 'SCPT':
                texts.append({'kind': 'script', 'i': v, 'id': r[1], 'label': r[1]})
            else:
                d = db.info_dial.get(v)
                topic = db.recs[d][1] if d is not None else ''
                texts.append({'kind': 'dialogue', 'i': v, 'id': r[1], 'label': (r[2] or '')[:120], 'topic': topic})
    out['texts'] = texts
    out['texts_more'] = len(texts) >= text_hits
    return out
