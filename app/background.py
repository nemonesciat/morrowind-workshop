"""The surveys that learn from the game's places, run in the background without slowing the Workshop.

Before this, each survey started its own thread the first time it was asked for, and after an install
or a change of load order (every cache is keyed by the load order) a first Auto-furnish set eleven of
them running at once in the server's own process: with Python's one interpreter lock the server's
requests got a sliver of the time, a nine-room house took a quarter of an hour to build, and the 3D
view starved and stayed black. Now a survey given as a task (module, function, args) runs in a process
of its own (surveyworker.py, below-normal priority), which writes its result to the cache folder for
the server's modules to find on disk; a survey given only as a function runs in one worker thread here,
one at a time. /api/status says what is running so the page can say so.

The queued tasks are shared out over up to three survey processes at once (slots(): by the machine's
cores and free memory, each process holds the game's data, about a gigabyte), balanced by what each
survey is known to cost, so the first furnish's twelve surveys take a third of the time they took one
after another; a task queued while processes run starts in a fresh process as soon as a slot is free."""
import json
import os
import subprocess
import sys
import threading
import time
from collections import deque

_lock = threading.Lock()
_queue = deque()              # [Job]
_running = [None]
_worker = [None]
_done = []                    # names finished, newest last (kept short)
_batch = []                   # the jobs handed to survey processes now
_threads = []                 # one thread per survey process running
_round = {'total': 0, 't0': 0.0}  # the surveys queued since the queue was last empty, and when that began (the page's "7 of 26")
SUBPROCESS = True             # (False: every task runs in the worker thread, as in the lab)
PROCESSES = None              # survey processes at once; None: by the machine (slots()), 1 to 3
project_path = [None]         # set by the server when a project is open (the surveys skip its own cells)
# what each survey costs, in seconds on the user's machine (cold, 2026-10-22), for sharing the queue out
COST = {'kits.learn_stairs': 60, 'layoutsurvey.survey': 40, 'catalogue.survey': 45, 'shelfsurvey.interest_survey': 50,
        'gapsurvey.survey': 15, 'hangsurvey.survey': 450, 'landsurvey.survey': 60}
COST_OTHER = 12
IN_WORKER = [False]           # set in a survey process: progress() goes to its output, for the server to read
_tl = threading.local()       # .job: the job this thread runs; .last: when it last reported


def progress(n, total, what='', stage=(0, 1)):
    """How far the survey running now has got: n of total (of what, "buildings"), for the page's Learning bar,
    which otherwise moved only when a survey finished and sat still through a ten-minute one (the user: "people
    may wonder if the process is working"). stage (i, k): this is stage i of k of the survey, so the bar fills
    on across stages. Cheap to call in a loop: reported once a second at most."""
    if not total:
        return
    t = time.time()
    if n < total and t - getattr(_tl, 'last', 0.0) < 1.0:
        return
    _tl.last = t
    frac = (stage[0] + min(1.0, n / float(total))) / max(1, stage[1])
    if IN_WORKER[0]:
        print('progress %d %d %.4f %s' % (n, total, frac, ' '.join(str(what).split())), flush=True)
        return
    job = getattr(_tl, 'job', None)
    if job is not None:
        job.progress = (n, total, what, frac)


class Job:
    """A queued survey; is_alive() while queued or running, so callers that kept a Thread can keep
    their check. start() is a no-op: the job is queued already."""

    def __init__(self, name, fn, task):
        self.name, self.fn, self.task = name, fn, task
        self.state = 'queued'
        self.t0 = None
        self.progress = None          # (n, total, what, share done) while running, from progress()
        self.began = None             # when it really began: a survey process runs its jobs one after another

    def is_alive(self):
        return self.state in ('queued', 'running')

    def start(self):
        pass


def start(name, fn, task=None):
    """Queue a survey under this name: fn to run it here, task = (module, function, [args]) to run it
    in the survey process. The Job (with is_alive())."""
    job = Job(name, fn, task)
    with _lock:
        for j in list(_queue) + list(_batch):
            if j.name == name and j.is_alive():
                return j                  # (the same survey asked for twice: once is enough)
        r = _running[0]
        if r is not None and r.name == name and r.is_alive():
            return r
        if not _alive():
            _round['total'], _round['t0'] = 0, time.time()
        _round['total'] += 1
        _queue.append(job)
        if _worker[0] is None or not _worker[0].is_alive():
            t = threading.Thread(target=_run, name='surveys', daemon=True)
            _worker[0] = t
            t.start()
    return job


def slots():
    """How many survey processes may run at once: PROCESSES, else by the machine (one per four cores,
    one per 2.5 GB of free memory, three at most, one at least)."""
    if PROCESSES:
        return max(1, int(PROCESSES))
    n = 3
    try:
        n = min(n, max(1, (os.cpu_count() or 2) // 4))
    except Exception:
        pass
    import osplat
    free = osplat.free_memory()
    if free:
        n = min(n, max(1, int(free / (2.5 * 1024 ** 3))))
    return n


def _cost(job):
    return COST.get('%s.%s' % (job.task[0], job.task[1]), COST_OTHER)


def _split(jobs, n):
    """The jobs shared out over up to n processes, balanced by cost; each part in queue order."""
    n = max(1, min(n, len(jobs)))
    order = {id(j): k for k, j in enumerate(jobs)}
    bins = [[] for _ in range(n)]
    load = [0] * n
    for j in sorted(jobs, key=_cost, reverse=True):
        k = load.index(min(load))
        bins[k].append(j)
        load[k] += _cost(j)
    return [sorted(b, key=lambda j: order[id(j)]) for b in bins if b]


def _refresh_running():
    """(under the lock) the job the page shows as running: the first still running in the processes."""
    for j in _batch:
        if j.state == 'running':
            _running[0] = j
            return
    _running[0] = None


def _run():
    try:
        sys.setswitchinterval(0.002)      # (a survey run here hands the interpreter over more often)
    except Exception:
        pass
    while True:
        time.sleep(0.5)                   # (the surveys a furnish asks for all arrive at once: shared out together)
        with _lock:
            _threads[:] = [t for t in _threads if t.is_alive()]
            if not _queue and not _threads:
                _running[0] = None
                return
            if not _queue:
                continue
            job = _queue[0]
            if SUBPROCESS and job.task:
                free = slots() - len(_threads)
                if free <= 0:
                    continue
                jobs = [j for j in _queue if j.task]
                for j in jobs:
                    _queue.remove(j)
                for part in _split(jobs, free):
                    for j in part:
                        j.state = 'running'
                        j.t0 = time.time()
                    _batch.extend(part)
                    t = threading.Thread(target=_process_batch, args=(part,), name='survey-process', daemon=True)
                    _threads.append(t)
                    t.start()
                _refresh_running()
                continue
            if _threads:
                continue                  # (a job for this thread waits for the processes: one thing at a time here)
            _queue.popleft()
            job.state = 'running'
            job.t0 = time.time()
            _running[0] = job
            job.began = job.t0
        _tl.job = job
        try:
            job.fn()
            job.state = 'done'
        except Exception as e:          # (a survey that fails stays out of the way of the next)
            job.state = 'failed'
            print('background survey %s failed: %s' % (job.name, e))
        with _lock:
            if job.name not in _done:
                _done.append(job.name)
            del _done[:-20]
            _running[0] = None
        time.sleep(0.05)


def _process_batch(part):
    """One survey process for these jobs; what it leaves undone runs here, in this thread."""
    finished = _in_process(part)
    for j in part:
        if j in finished:
            continue
        with _lock:
            j.t0 = j.began = time.time()
            j.progress = None
            _refresh_running()
        _tl.job = j
        try:                            # (the process failed it: here, then)
            j.fn()
            j.state = 'done'
        except Exception as e:
            j.state = 'failed'
            print('background survey %s failed: %s' % (j.name, e))
        with _lock:
            if j.name not in _done:
                _done.append(j.name)
    with _lock:
        for j in part:
            if j in _batch:
                _batch.remove(j)
        del _done[:-20]
        _refresh_running()


def _in_process(jobs):
    """Run these jobs' tasks in one survey process; the set of jobs it reported done."""
    here = os.path.dirname(os.path.abspath(__file__))
    exe = sys.executable
    if os.path.basename(exe).lower() == 'pythonw.exe':
        alt = os.path.join(os.path.dirname(exe), 'python.exe')
        if os.path.isfile(alt):
            exe = alt
    args = [exe, os.path.join(here, 'surveyworker.py'), project_path[0] or '-', json.dumps([list(j.task) for j in jobs])]
    import osplat
    flags = osplat.background_flags()
    # (a fixed hash seed: Python orders sets differently in every process, and the surveys settled ties between
    # equally common pieces by that order, so two first startings learnt different things and furnished 478 to 542)
    env = dict(os.environ, PYTHONHASHSEED='0')
    try:
        p = subprocess.Popen(args, cwd=here, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=flags, env=env)
    except Exception as e:
        print('survey process: %s' % e)
        return set()
    # (the process reports each survey as it finishes: that one is done and the next is "running")
    finished, lines = set(), []
    jobs[0].began = time.time()
    for line in p.stdout:
        if line.startswith('progress '):
            # (how far the survey it is running has got: the first of the jobs not reported done, as it runs
            # them in order)
            parts = line.rstrip('\n').split(' ', 4)
            cur = next((j for j in jobs if j not in finished), None)
            if cur is not None and len(parts) >= 4:
                try:
                    cur.progress = (int(parts[1]), int(parts[2]), parts[4] if len(parts) > 4 else '', float(parts[3]))
                except ValueError:
                    pass
            continue
        lines.append(line)
        if line.startswith(('done ', 'failed ', 'loaded ')):
            print('survey process: ' + line.rstrip(), flush=True)     # (the log keeps each survey's time)
        for j in jobs:
            if j not in finished and line.startswith('done %s.%s' % (j.task[0], j.task[1])):
                finished.add(j)
                with _lock:
                    j.state = 'done'
                    if j.name not in _done:
                        _done.append(j.name)
                    _refresh_running()
                    for k in jobs:
                        if k.state == 'running' and k.t0 is None:
                            k.t0 = time.time()
                    nxt = next((k for k in jobs if k not in finished), None)
                    if nxt is not None and nxt.began is None:
                        nxt.began = time.time()
    p.wait()
    if len(finished) < len(jobs):
        print('survey process left %d of %d undone:\n%s' % (len(jobs) - len(finished), len(jobs), ''.join(lines)[-2000:]))
    return finished


def _alive():
    """(under the lock) how many surveys are queued or running now."""
    n = len(_queue) + sum(1 for j in _batch if j.is_alive())
    r = _running[0]
    if r is not None and r.is_alive() and r not in _batch:
        n += 1
    return n


def status():
    """{'running': name or None, 'since': seconds, 'queued': [names], 'done': [names], 'total', 'left', 'elapsed'}
    for the page: total = the surveys of this round (queued since the queue was last empty), left = those not
    finished yet, elapsed = seconds since the round began."""
    with _lock:
        r = _running[0]
        waiting = [j.name for j in _batch if j.state == 'running' and j is not r] + [j.name for j in _queue]
        left = _alive()
        # (how far each survey running now has got, and their sum as a share of one survey: the bar fills by it
        # between surveys. One that says nothing is reckoned by its time against what it is known to take,
        # never past 90%)
        now = time.time()
        run = [j for j in _batch if j.state == 'running' and j.t0] + ([r] if r is not None and r.state == 'running' and r.t0 and r not in _batch else [])
        prog, part = [], 0.0
        for j in run:
            if j.progress:
                n, tot, what, frac = j.progress
                prog.append({'name': j.name, 'n': n, 'total': tot, 'what': what})
                part += min(1.0, frac)
            elif j.task and j.began:
                part += min(0.9, (now - j.began) / float(_cost(j)))
        return {'running': r.name if r else None, 'since': round(now - r.t0) if r and r.t0 else 0,
                'queued': waiting, 'done': list(_done), 'total': max(_round['total'], left), 'left': left,
                'elapsed': round(now - _round['t0']) if left and _round['t0'] else 0,
                'progress': prog, 'part': round(part, 3)}
