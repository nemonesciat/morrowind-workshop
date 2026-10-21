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


def _names():
    s = background.status()
    return ([s['running']] if s['running'] else []) + list(s['queued'])
