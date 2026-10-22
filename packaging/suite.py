"""The detector suite: run before every build, so a fix in one place can't quietly break another.

On a COPY of one of the user's projects (nothing of theirs is touched: the project file and plugin are
copied into a scratch home under %TEMP%\\morrowind-workshop-suite, which also keeps the surveys' cache
between runs) it runs, and prints as one table:

  1. the tile check: every building style's tile size and storey height against the last build's
     staged kits.py (packaging/out/stage/app/kits.py), so no kit's grid changed by accident;
  2. the all-styles build: a two-floor house (living room, study, bedroom, kitchen) built from pieces
     in each style, furnished (one seed), then Find gaps (gaps, doorways, ceilings, posts, see-through
     holes, clips and flicker beyond the game's rate) and the place check (chairs, floating things,
     things through walls, shelves and tapestries hung on nothing, lights hung from nothing, things
     taller than the room, counters into tapestries, books leaning on nothing);
  3. the same two checks on every furnished house of the project as it is.

How to run (the Workshop's own python is never used; anaconda's or any Python 3.9+ will do):

  C:\\anaconda3\\python.exe -I packaging\\suite.py
  C:\\anaconda3\\python.exe -I packaging\\suite.py --project "Awful Ruined Project" --seed 5
  C:\\anaconda3\\python.exe -I packaging\\suite.py --styles in_hlaalu,in_c_plain --no-houses
  C:\\anaconda3\\python.exe -I packaging\\suite.py --no-build          (the houses only: a minute)

The first run on a cold cache re-surveys the game (room, arrangement, placement, catalogue, shelf
dressings: twenty minutes or more, in the background threads Auto-furnish starts); with --warm-from
<folder> the cache files of another home (a lab's, the installed Workshop's) are copied in first.
Options: --project NAME (default "Awful Ruined Project"; from the installed Workshop's projects folder,
or a path to a .json), --styles a,b,c (default the nine major styles), --seed N (default 5),
--no-build, --no-houses, --no-tiles, --out FILE (the table is also written there)."""
import argparse
import os
import shutil
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STYLES = 'in_hlaalu,t_imp_setgc_i,in_c_stone,in_c_plain,t_de_setind_i,in_mh_int,t_imp_setstr_i,in_v_s_int,in_r_l_int'
TWO = [{'name': 'Living room', 'x': 0, 'y': 0, 'w': 3, 'h': 3, 'floor': 0}, {'name': 'Study', 'x': 3, 'y': 0, 'w': 3, 'h': 3, 'floor': 0},
       {'name': 'Bedroom', 'x': 0, 'y': 0, 'w': 3, 'h': 3, 'floor': 1}, {'name': 'Kitchen', 'x': 3, 'y': 0, 'w': 3, 'h': 3, 'floor': 1}]
DOORS = [{'rooms': ['Living room', 'Study'], 'at': {'x': 2, 'y': 1, 'side': 'E'}}, {'rooms': ['Bedroom', 'Kitchen'], 'at': {'x': 2, 'y': 1, 'side': 'E'}}]
ENTRANCE = {'room': 'Living room', 'side': 'S', 'x': 1, 'y': 0}


def args():
    p = argparse.ArgumentParser(description='The detector suite (see the file header).')
    p.add_argument('--project', default='Awful Ruined Project')
    p.add_argument('--styles', default=STYLES)
    p.add_argument('--seed', type=int, default=5)
    p.add_argument('--no-build', action='store_true')
    p.add_argument('--no-houses', action='store_true')
    p.add_argument('--no-tiles', action='store_true')
    p.add_argument('--warm-from', default=None)
    p.add_argument('--out', default=None)
    return p.parse_args()


def scratch_home(a):
    """A scratch Workshop home with a copy of the project, its plugins and the user's openmw.cfg."""
    home = os.path.join(os.environ.get('TEMP') or os.environ.get('TMP') or HERE, 'morrowind-workshop-suite')
    for d in ('projects', 'data', 'cache', 'omwuser'):
        os.makedirs(os.path.join(home, d), exist_ok=True)
    with open(os.path.join(home, 'workshop_settings.json'), 'w') as f:
        f.write('{"guide_seen": true, "ai_ack": true}')
    open(os.path.join(home, 'game.log'), 'a').close()
    src = a.project if a.project.lower().endswith('.json') else os.path.join(
        os.path.expandvars(r'%LOCALAPPDATA%\Programs\Morrowind Workshop\projects'), a.project + '.json')
    if not os.path.exists(src):
        sys.exit('No project file at %s' % src)
    dst = os.path.join(home, 'projects', 'Suite.json')
    shutil.copy(src, dst)
    userdocs = os.path.join(os.path.expanduser('~'), 'Documents', 'My Games', 'OpenMW')
    cfg = os.path.join(userdocs, 'openmw.cfg')
    if os.path.exists(cfg):
        shutil.copy(cfg, os.path.join(home, 'omwuser', 'openmw.cfg'))
    data = os.path.join(userdocs, 'data')
    if os.path.isdir(data):
        for fn in os.listdir(data):
            if fn.lower().endswith(('.omwaddon', '.esp', '.esm', '.omwscripts')):
                shutil.copy(os.path.join(data, fn), os.path.join(home, 'data', fn))
    if a.warm_from and os.path.isdir(a.warm_from):
        for fn in os.listdir(a.warm_from):
            if fn.endswith('.json') and not os.path.exists(os.path.join(home, 'cache', fn)):
                shutil.copy(os.path.join(a.warm_from, fn), os.path.join(home, 'cache', fn))
    os.environ['WORKSHOP_HOME'] = home
    os.environ['WORKSHOP_PLUGIN_DIR'] = os.path.join(home, 'data')
    os.environ['WORKSHOP_GAME_LOG'] = os.path.join(home, 'game.log')
    os.environ['WORKSHOP_OPENMW_USERDIR'] = os.path.join(home, 'omwuser')
    os.environ['WORKSHOP_PORT'] = '0'
    return home, dst


def tile_check(db):
    """Every kit's tile and height against the last build's staged kits.py: the changes, if any."""
    import importlib.util
    import kits as new
    staged = os.path.join(HERE, 'out', 'stage', 'app', 'kits.py')
    if not os.path.exists(staged):
        return ['(no staged kits.py under packaging/out/stage: nothing to compare with)']
    spec = importlib.util.spec_from_file_location('kits_old', staged)
    old = importlib.util.module_from_spec(spec)
    sys.modules['kits_old'] = old
    spec.loader.exec_module(old)
    ko, kn = old.kits(db), new.kits(db)
    out = []
    for pre in sorted(set(ko) | set(kn)):
        a, b = ko.get(pre), kn.get(pre)
        if not a or not b:
            out.append('%-26s only in %s' % (pre, 'the last build' if a else 'this one'))
        elif a['tile'] != b['tile']:
            out.append('%-26s TILE CHANGED %s -> %s' % (pre, a['tile'], b['tile']))
    return out or ['every kit\'s tile is as it was in the last build (%d kits)' % len(kn)]


def row_for(db, key, label, secs, placecheck, extra=''):
    try:
        s = placecheck.summary(db, key)
    except Exception as e:
        return {'label': label, 'secs': secs, 'error': str(e)[:60]}
    s['label'], s['secs'], s['extra'] = label, secs, extra
    return s


def main():
    a = args()
    t_all = time.time()
    home, dst = scratch_home(a)
    sys.path.insert(0, os.path.join(ROOT, 'app'))
    import project
    from database import Database
    print('suite: scratch home %s' % home, flush=True)
    t0 = time.time()
    db = Database()
    db.project = project.Project(dst)
    db._load()
    print('suite: loaded %d records in %.0fs' % (len(db.recs), time.time() - t0), flush=True)
    import placecheck
    import builder
    import furnish
    lines = []
    if not a.no_tiles:
        lines.append('Tile check:')
        for l in tile_check(db):
            lines.append('  ' + l)
    rows = []
    if not a.no_build:
        for st in a.styles.split(','):
            st = st.strip()
            if not st:
                continue
            t0 = time.time()
            try:
                r = builder.build_house(db, 'Suite ' + st, st, TWO, DOORS, ENTRANCE, None, 'normal', True, None, None, 'auto')
                key = r['cells'][0]['key'] if isinstance(r['cells'][0], dict) else r['cells'][0]
                fr = furnish.furnish(db, key, None, seed=a.seed)
                placed = fr.get('placed', 0)
            except Exception as e:
                traceback.print_exc()
                rows.append({'label': st, 'secs': time.time() - t0, 'error': str(e)[:60]})
                continue
            rows.append(row_for(db, key, st, time.time() - t0, placecheck, '%d placed' % placed))
            print('suite: %s done in %.0fs' % (st, time.time() - t0), flush=True)
    if not a.no_houses:
        for key in sorted(db.project.cells):
            if key.startswith('#') or key.startswith('suite ') or len(db.project.cells[key].get('refs') or {}) < 20:
                continue                                 # (not the houses this run just built)
            t0 = time.time()
            rows.append(row_for(db, key, key, time.time() - t0, placecheck))
            rows[-1]['secs'] = time.time() - t0
            print('suite: %s checked in %.0fs' % (key, rows[-1]['secs']), flush=True)
    kinds = [k for k, _l, _w in placecheck.KINDS]
    head = '%-30s %5s %6s %6s | %s' % ('style / house', 'rooms', 'things', 'secs', ' '.join('%-8s' % k for k in kinds))
    lines += ['', head, '-' * len(head)]
    for r in rows:
        if r.get('error'):
            lines.append('%-30s %5s %6s %6.0f | FAILED %s' % (r['label'][:30], '', '', r['secs'], r['error']))
        else:
            lines.append('%-30s %5d %6d %6.0f | %s %s' % (r['label'][:30], r['rooms'], r['things'], r['secs'],
                                                        ' '.join('%-8d' % r.get(k, 0) for k in kinds), r.get('extra', '')))
    lines.append('')
    lines.append('%d rows, %.0fs in all. Kinds: %s.' % (len(rows), time.time() - t_all, '; '.join('%s = %s' % (k, lab.lower()) for k, lab, _w in placecheck.KINDS)))
    text = '\n'.join(lines)
    print()
    print(text)
    out = a.out or os.path.join(home, 'suite-%s.txt' % time.strftime('%Y%m%d-%H%M'))
    with open(out, 'w', encoding='utf-8') as f:
        f.write(text + '\n')
    print('(written to %s)' % out)


if __name__ == '__main__':
    main()
    os._exit(0)
