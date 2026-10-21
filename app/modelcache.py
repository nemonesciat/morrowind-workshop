"""Facts about single models that are learnt by walking the game's places and never change for a load
order: how the game dresses a bookshelf model (shelfsurvey.survey), what hangs with a banner
(wallsurvey.survey), which way a model's front points (furnish.front_of), how high it hangs
(furnish.hang_height). Each was kept in memory only, so every Auto-furnish walked the cells again:
57 of a 93-second furnish went on re-reading the shelf dressings of 45 models. They are kept here on
disk, one file per table and load order (cache/<table>_<sig><taste stamp>.json), loaded once, and
written back at the end of a furnish (save()) and whenever a table grows past a few hundred new entries."""
import json
import os
import threading

_tables = {}        # (table, sig+stamp) -> {'path', 'data': {key: value}, 'dirty': n}
_lock = threading.RLock()
FLUSH_EVERY = 200   # new entries between writes


def _key(db, table):
    import taste
    return (table, taste.sig(db) + taste.stamp())


def _load(db, table):
    import taste
    k = _key(db, table)
    with _lock:
        t = _tables.get(k)
        if t is not None:
            return t
        path = taste.cache_file('%s_%s' % (table, k[1]))
        data = {}
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}
        t = {'path': path, 'data': data, 'dirty': 0}
        _tables[k] = t
        return t


def get(db, table, key):
    """The kept value for this model (any JSON value), or None when it was never kept."""
    return _load(db, table)['data'].get(key.lower())


def put(db, table, key, value):
    """Keep a value for this model; written to disk after FLUSH_EVERY new entries, or at save()."""
    t = _load(db, table)
    with _lock:
        t['data'][key.lower()] = value
        t['dirty'] += 1
        if t['dirty'] >= FLUSH_EVERY:
            _write(t)


def _write(t):
    try:
        tmp = t['path'] + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            # (compact and unchecked: a shelf table runs to ten megabytes, and this is written at the
            # end of every furnish that learnt a new model)
            f.write(json.dumps(t['data'], separators=(',', ':'), check_circular=False))
        os.replace(tmp, t['path'])
        t['dirty'] = 0
    except Exception:
        pass


def save():
    """Write every table with new entries (called when a furnish is done)."""
    with _lock:
        for t in _tables.values():
            if t['dirty']:
                _write(t)
