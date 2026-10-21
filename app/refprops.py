"""What a placed object carries besides its spot: who owns it (a person, or a faction from a rank),
the global variable that overrides the owner (the game's rentable beds), the lock on a door or
container and the key that opens it, the trap spell, how many uses or how much condition an item
has left, and the soul in a soul gem.

In the placed object's bytes: ANAM owner, BNAM owner global, XSOL soul, CNAM faction + INDX rank,
XCHG enchantment charge, INTV uses/condition/time left, NAM9 gold value, DODT/DNAM where a door
leads, FLTV lock level, KNAM key, TNAM trap spell. The game writes them in that order."""
import struct

import editing
from editing import EditError, cell_label, commit, _cell, _store
from esm import iter_subrecords, zstr
from project import ref_info, zs

OWN_TAGS = ('ANAM', 'BNAM', 'XSOL', 'CNAM', 'INDX', 'XCHG', 'INTV', 'NAM9')
LOCK_TAGS = ('FLTV', 'KNAM', 'TNAM')
# what the "uses" number means for each kind of item
USES = {'LOCK': 'Uses left', 'PROB': 'Uses left', 'REPA': 'Uses left', 'WEAP': 'Condition', 'ARMO': 'Condition',
        'LIGH': 'Time left (seconds)'}
NO_OWNER = ('NPC_', 'CREA', 'STAT')


def _ref(db, cell_key, refkey):
    c, refs = _cell(db, cell_key)
    ref = refs.get(refkey)
    if not ref:
        raise EditError('That object is no longer in this cell.')
    return c, ref


def read(db, cell_key, refkey):
    editing._require_project(db)
    refs, _hdr = db.cell_refs(cell_key)
    ref = refs.get(refkey)
    if not ref:
        raise EditError('That object is no longer in this cell.')
    rid = ref_info(ref['subs'])[0]
    ri = db.resolve_id(rid)
    tag = db.recs[ri][0] if ri is not None else ''
    o = {'cell': cell_key, 'ref': refkey, 'id': rid, 'type': tag, 'owner': '', 'faction': '', 'rank': 0, 'global': '',
         'soul': '', 'lock': 0, 'key': '', 'trap': '', 'uses': None, 'charge': None,
         'can_own': tag not in NO_OWNER, 'can_lock': tag in ('DOOR', 'CONT'),
         'uses_label': USES.get(tag), 'can_soul': tag == 'MISC', 'teleport': False}
    for t, d in ref['subs']:
        if t == 'ANAM':
            o['owner'] = zstr(d)
        elif t == 'BNAM':
            o['global'] = zstr(d)
        elif t == 'XSOL':
            o['soul'] = zstr(d)
        elif t == 'CNAM':
            o['faction'] = zstr(d)
        elif t == 'INDX' and len(d) >= 4:
            o['rank'] = struct.unpack_from('<i', d)[0]
        elif t == 'XCHG' and len(d) >= 4:
            o['charge'] = round(struct.unpack_from('<f', d)[0], 1)
        elif t == 'INTV' and len(d) >= 4:
            o['uses'] = struct.unpack_from('<i', d)[0]
        elif t == 'FLTV' and len(d) >= 4:
            o['lock'] = struct.unpack_from('<i', d)[0]
        elif t == 'KNAM':
            o['key'] = zstr(d)
        elif t == 'TNAM':
            o['trap'] = zstr(d)
        elif t == 'DODT':
            o['teleport'] = True
    # names, so the panel can show "Ra'Virr" rather than only the ID
    for f in ('owner', 'faction', 'key', 'trap', 'soul'):
        if o[f]:
            i = db.resolve_id(o[f])
            o[f + '_name'] = db.recs[i][2] if i is not None else ''
            o[f + '_missing'] = i is None
    if o['faction']:
        o['ranks'] = faction_ranks(db, o['faction'])
    return o


def faction_ranks(db, fid):
    fi = db.resolve_id(fid)
    if fi is None or db.recs[fi][0] != 'FACT':
        return []
    return [zstr(d) for t, d in iter_subrecords(db.files[db.recs[fi][3]].record_at(db.recs[fi][4])[2]) if t == 'RNAM']


def _check(db, rid, tags, what):
    rid = (rid or '').strip()
    if not rid:
        return ''
    i = db.resolve_id(rid)
    if i is None or db.recs[i][0] not in tags:
        raise EditError('"%s" is not %s.' % (rid, what))
    return db.recs[i][1]


def _int(v, lo, hi, what):
    try:
        v = int(round(float(v if v not in (None, '') else 0)))
    except (TypeError, ValueError):
        raise EditError('%s must be a number.' % what)
    return max(lo, min(hi, v))


def save(db, cell_key, refkey, o):
    """o: owner, faction, rank, global, soul, lock, key, trap, uses (None or '' = none)."""
    c, ref = _ref(db, cell_key, refkey)
    cur = read(db, cell_key, refkey)
    owner = _check(db, o.get('owner'), ('NPC_',), 'a person (owners are NPCs)')
    faction = _check(db, o.get('faction'), ('FACT',), 'a faction')
    glob = _check(db, o.get('global'), ('GLOB',), 'a global variable')
    soul = _check(db, o.get('soul'), ('CREA',), 'a creature (a soul gem holds a creature\'s soul)')
    key = _check(db, o.get('key'), ('MISC',), 'a key (keys are miscellaneous items)')
    trap = _check(db, o.get('trap'), ('SPEL',), 'a spell (traps cast a spell on whoever opens them)')
    if owner and faction:
        raise EditError('Pick either a person or a faction as the owner, not both.')
    rank = _int(o.get('rank'), 0, 9, 'The rank') if faction else 0
    lock = _int(o.get('lock'), 0, 1000, 'The lock level')
    uses = o.get('uses')
    uses = None if uses in (None, '') else _int(uses, 0, 2 ** 31 - 1, 'Uses')
    if cur.get('uses_label') is None:
        uses = cur['uses']                  # (not something to set on this kind of object: left as it was)
    if not cur['can_lock']:
        lock, key, trap = 0, '', ''
    if not cur['can_own']:
        owner = faction = glob = ''
    if not cur['can_soul']:
        soul = ''

    own = []
    if owner:
        own.append(('ANAM', zs(owner)))
    if glob:
        own.append(('BNAM', zs(glob)))
    if soul:
        own.append(('XSOL', zs(soul)))
    if faction:
        own.append(('CNAM', zs(faction)))
        own.append(('INDX', struct.pack('<i', rank)))
    old = {t: d for t, d in ref['subs']}
    if 'XCHG' in old:
        own.append(('XCHG', old['XCHG']))
    if uses is not None:
        own.append(('INTV', struct.pack('<i', uses)))
    if 'NAM9' in old:
        own.append(('NAM9', old['NAM9']))
    locks = []
    if lock:
        locks.append(('FLTV', struct.pack('<i', lock)))
    if key:
        locks.append(('KNAM', zs(key)))
    if trap:
        locks.append(('TNAM', zs(trap)))

    subs = [(t, d) for t, d in ref['subs'] if t not in OWN_TAGS and t not in LOCK_TAGS]
    at = next((n for n, (t, _d) in enumerate(subs) if t in ('DODT', 'DNAM', 'UNAM', 'DATA')), len(subs))
    subs[at:at] = own
    at = next((n for n, (t, _d) in enumerate(subs) if t in ('UNAM', 'DATA')), len(subs))
    subs[at:at] = locks
    if subs == list(ref['subs']):
        return cur
    _store(c, refkey, ref['origin'], ref['idx'], subs)

    what = []
    name = db.recs[db.resolve_id(cur['id'])][2] if db.resolve_id(cur['id']) is not None else cur['id']
    name = name or cur['id']
    if (owner, faction, rank, glob) != (cur['owner'], cur['faction'], cur['rank'], cur['global']):
        if owner:
            what.append('now belongs to %s' % owner)
        elif faction:
            what.append('now belongs to %s%s' % (faction, (' from rank %d' % rank) if rank else ''))
        elif glob and not (cur['owner'] or cur['faction']):
            what.append('owner set by %s' % glob)
        else:
            what.append('belongs to no one now')
    if (lock, key, trap) != (cur['lock'], cur['key'], cur['trap']):
        if lock:
            what.append('locked at %d%s' % (lock, (', key ' + key) if key else ''))
        elif key:
            what.append('opened by ' + key)
        else:
            what.append('unlocked')
        if trap != cur['trap']:
            what.append(('trapped with ' + trap) if trap else 'trap removed')
    if uses != cur['uses']:
        what.append('%s %s' % ((cur.get('uses_label') or 'uses').lower(), 'as new' if uses is None else uses))
    if soul != cur['soul']:
        what.append(('holds the soul of ' + soul) if soul else 'soul gone')
    commit(db, '"%s" in %s: %s' % (name, cell_label(db, cell_key), '; '.join(what) or 'ownership changed'))
    return read(db, cell_key, refkey)
