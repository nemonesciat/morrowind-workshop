"""What Auto-furnish has to have learnt from the game's places before it can furnish well.

Each survey keeps its result on disk, keyed by the load order, so after an install or a change of load
order the first Auto-furnish finds nothing learnt yet. 2.2.16 went ahead regardless and furnished with
half its knowledge, and the rooms came out barren; now the furnish request answers with what is still
being learnt (the survey process runs it meanwhile) and the page waits, with a progress line, then asks
again. Once learnt, a survey is there for good."""
import background

# (name as /api/surveys reports it, module, function): the surveys a furnish goes by
_SURVEYS = [
    ('roomsurvey', 'ready'), ('wealthsurvey', 'ready'), ('placesurvey', 'ready'), ('arrangesurvey', 'ready'),
    ('catalogue', 'ready'), ('wallsurvey2', 'ready'), ('decorsurvey', 'ready'), ('shelfsurvey', 'interest_ready'),
    ('countersurvey', 'ready'), ('shrinesurvey', 'ready'), ('roomkindsurvey', 'ready'),
    # (what the game stands at each kind of joint between its floor pieces: Fix here, the finder's "not what
    # the game stands here" and the builder's closing rounds go by it; 77 kits in about 20 s, 2026-10-22)
    ('joints', 'ready'),
    # (which building piece the game joins to which, face by face: the Extend mode's candidates, open edges
    # and patterns; 77 kits in about 40 s, 2026-10-22)
    ('adjacency', 'ready'),
    # (the Redoran manors' islands and rugs, the game's garden beds, its scenes with their kit, 2026-10-22:
    # about 25 s, 2 min and 80 s)
    ('redoransurvey', 'ready'), ('gardensurvey', 'ready'), ('scenesurvey', 'ready'),
    # (how the game dresses its halls, run by run and culture by culture: the hallway round's arrangements;
    # 900 places in about a minute, 2026-10-23)
    ('hallsurvey', 'ready'),
    # (the game's hearths as whole sets: a room's fire comes whole or not at all, and the check's "fire
    # things with no hearth"; v2 reads 274 places in about 70 s, v1's 500 took 270 s in the cold start, 2026-10-23)
    ('hearthsurvey', 'ready'),
    # (how the game furnishes its trades' rooms: a smithy round its forge, the pieces each trade never holds,
    # the forges' whole sets; 600 places in about 25 s once the hearth survey is to hand, 2026-10-23)
    ('tradesurvey', 'ready'),
]


def pending(db):
    """The names (as the survey queue shows them) of the surveys not learnt yet; each is queued by
    asking for it. [] when everything Auto-furnish needs is to hand."""
    before = _names()
    missing = 0
    for mod, fn in _SURVEYS:
        try:
            m = __import__(mod)
            if getattr(m, fn)(db) is None:
                missing += 1
        except Exception:
            missing += 1
    if not missing:
        return []
    names = _names()
    return names or before or ['the game\'s places']


# the surveys Populate goes by (kept apart from a furnish's: a first furnish doesn't wait for them)
_POPULATE = [('castsurvey', 'ready'), ('roomsurvey', 'ready')]


def populate_pending(db):
    """Like pending(), for Populate: [] when who the game's people are (and where they stand) is to hand."""
    before = _names()
    missing = 0
    for mod, fn in _POPULATE:
        try:
            if getattr(__import__(mod), fn)(db) is None:
                missing += 1
        except Exception:
            missing += 1
    if not missing:
        return []
    return _names() or before or ["the game's people"]


def ruin_pending(db, kind='dwemer'):
    """Like pending(), for the dungeon maker: [] when the game's places of the kind are learnt (dwemer.py)."""
    before = _names()
    import dwemer
    try:
        if dwemer.ready(db, kind) is not None:
            return []
    except Exception:
        pass
    return _names() or before or [dwemer.learning_name(kind)]


_warmed = {}


def prewarm(db):
    """Start learning as soon as the Workshop is open (once per load order): the kits' stairs for the
    style list, then every survey Auto-furnish goes by, all in the survey process. By the time a house
    is built and furnished, most of it is there; the rest is a short, visible wait."""
    if _warmed.get('recs') is db.recs:
        return
    _warmed['recs'] = db.recs
    import os
    import kits
    try:
        if not os.path.isfile(kits._stairs_path(db)):
            background.start('the stairs of every building style', lambda: kits.learn_stairs(db), task=('kits', 'learn_stairs', []))
    except Exception:
        pass
    try:
        pending(db)
    except Exception:
        pass
    # (who the game's people are, for Populate: queued after everything a furnish needs, so it never holds
    # one up; every place's people in about 30 s, 2026-10-23)
    try:
        populate_pending(db)
    except Exception:
        pass
    # (the game's Dwemer ruins, for the ruin maker: last, about 17 s, 2026-10-24)
    try:
        ruin_pending(db)
    except Exception:
        pass
    # (the Style palette's themes and what goes with them, stylesurvey.py: after the rest, about 25 s,
    # 2026-10-25; its window waits for it with a progress line if opened before)
    try:
        import stylesurvey
        stylesurvey.ready(db)
    except Exception:
        pass
    # (the style list's own work, every kit's pieces and the Gold Coast dressings, about 4 s: done once
    # here in a thread of the server's, so the list comes in a fraction of a second whenever Create is opened)
    try:
        import threading
        import builder
        def warm():
            try:
                builder.styles(db, wait=False)
            except Exception as e:
                # (the game data reloaded under the walk, say: the list is simply made when next asked for)
                print('style list warm-up stopped:', e)
        threading.Thread(target=warm, name='styles-warm', daemon=True).start()
    except Exception:
        pass


def _names():
    s = background.status()
    return ([s['running']] if s['running'] else []) + list(s['queued'])
