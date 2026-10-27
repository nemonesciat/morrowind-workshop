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
SUBPROCESS = True             # (False: every task runs in the worker thread, as in the lab)
PROCESSES = None              # survey processes at once; None: by the machine (slots()), 1 to 3
project_path = [None]         # set by the server when a project is open (the surveys skip its own cells)
# what each survey costs, in seconds on the user's machine (cold, 2026-10-22), for sharing the queue out
COST = {'kits.learn_stairs': 60, 'layoutsurvey.survey': 40, 'catalogue.survey': 45, 'shelfsurvey.interest_survey': 50,
        'gapsurvey.survey': 15, 'hangsurvey.survey': 450, 'landsurvey.survey': 60}
COST_OTHER = 12


class Job:
    """A queued survey; is_alive() while queued or running, so callers that kept a Thread can keep
    their check. start() is a no-op: the job is queued already."""

    def __init__(self, name, fn, task):
        self.name, self.fn, self.task = name, fn, task
        self.state = 'queued'
        self.t0 = None

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
            j.t0 = time.time()
            _refresh_running()
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
    try:
        p = subprocess.Popen(args, cwd=here, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=flags)
    except Exception as e:
        print('survey process: %s' % e)
        return set()
    # (the process reports each survey as it finishes: that one is done and the next is "running")
    finished, lines = set(), []
    for line in p.stdout:
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
    p.wait()
    if len(finished) < len(jobs):
        print('survey process left %d of %d undone:\n%s' % (len(jobs) - len(finished), len(jobs), ''.join(lines)[-2000:]))
    return finished


def status():
    """{'running': name or None, 'since': seconds, 'queued': [names], 'done': [names]} for the page."""
    with _lock:
        r = _running[0]
        waiting = [j.name for j in _batch if j.state == 'running' and j is not r] + [j.name for j in _queue]
        return {'running': r.name if r else None, 'since': round(time.time() - r.t0) if r and r.t0 else 0,
                'queued': waiting, 'done': list(_done)}
