"""The surveys that learn from the game's places, run in a process of their own (started by
background.py) so the Workshop's own requests never wait on them: a survey in a thread of the server's
process shares Python's one interpreter lock with every request, and a first Auto-furnish after an
install left the server crawling for ten minutes. This process loads the game's data once (a minute or
so), runs the surveys it was given one after the other, writes each to the cache folder, and exits; the
server's modules find the results on disk the next time they are asked.

    python surveyworker.py <project path or -> <tasks json>

tasks: [[module, function, [args...]], ...], e.g. [["roomsurvey", "survey", [400]]]."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main():
    project_path, tasks = sys.argv[1], json.loads(sys.argv[2])
    try:
        import psutil  # noqa: F401
    except ImportError:
        pass
    import osplat
    osplat.lower_priority()             # (below normal on Windows, nice on Linux)
    import project
    from database import Database
    import mapdata
    import background
    mapdata.EXTRAS = False           # (the surveys never read a place's lighting or path grid: not parsed here)
    background.SUBPROCESS = False    # (a survey process never starts survey processes of its own: whatever a
    #                                  survey asks for on the way runs in a thread here, see gapsurvey.ready)
    t0 = time.time()
    db = Database()
    if project_path and project_path != '-':
        db.project = project.Project(project_path)
    db._load()
    print('loaded in %.0fs' % (time.time() - t0), flush=True)
    import importlib
    for mod, fn, args in tasks:
        t = time.time()
        try:
            m = importlib.import_module(mod)
            getattr(m, fn)(db, *args)
            print('done %s.%s in %.0fs' % (mod, fn, time.time() - t), flush=True)
        except Exception as e:
            print('failed %s.%s: %s' % (mod, fn, e), flush=True)
        try:
            # (what a survey learnt about single models on the way, e.g. how the game dresses each
            # bookshelf, is kept too: a first furnish with it missing walked the cells again, a minute)
            import modelcache
            modelcache.save()
        except Exception:
            pass


if __name__ == '__main__':
    main()
