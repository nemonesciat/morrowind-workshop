"""The surveys that learn from the game's places, run in the background without slowing the Workshop.

Before this, each survey started its own thread the first time it was asked for, and after an install
or a change of load order (every cache is keyed by the load order) a first Auto-furnish set eleven of
them running at once in the server's own process: with Python's one interpreter lock the server's
requests got a sliver of the time, a nine-room house took a quarter of an hour to build, and the 3D
view starved and stayed black. Now a survey given as a task (module, function, args) runs in a process
of its own (surveyworker.py, below-normal priority, one task after another), which writes its result to
the cache folder for the server's modules to find on disk; a survey given only as a function runs in
one worker thread here, one at a time. /api/status says what is running so the page can say so."""
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
_batch = []                   # the jobs handed to the survey process now (the ones after the first are still to come)
SUBPROCESS = True             # (False: every task runs in the worker thread, as in the lab)
project_path = [None]         # set by the server when a project is open (the surveys skip its own cells)


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
        for j in list(_queue):
            if j.name == name:
                return j                  # (the same survey asked for twice: once is enough)
        r = _running[0]
        if r is not None and r.name == name:
            return r
        _queue.append(job)
        if _worker[0] is None or not _worker[0].is_alive():
            t = threading.Thread(target=_run, name='surveys', daemon=True)
            _worker[0] = t
            t.start()
    return job


def _run():
    try:
        sys.setswitchinterval(0.002)      # (a survey run here hands the interpreter over more often)
    except Exception:
        pass
    while True:
        time.sleep(0.5)                   # (the surveys a furnish asks for all arrive at once: one process for all)
        with _lock:
            if not _queue:
                _running[0] = None
                return
            job = _queue.popleft()
            _running[0] = job
            job.state = 'running'
            job.t0 = time.time()
        batch = [job]
        if SUBPROCESS and job.task:
            # (every queued survey with a task goes to the one process: it loads the game's data once)
            with _lock:
                more = [j for j in _queue if j.task]
                for j in more:
                    _queue.remove(j)
                    j.state = 'running'
                    j.t0 = job.t0
                batch += more
                _batch[:] = batch
            finished = _in_process(batch)
            with _lock:
                _batch[:] = []
            for j in batch:
                if j in finished:
                    continue
                with _lock:
                    _running[0] = j
                    j.t0 = time.time()
                try:                            # (the process failed it: here, then)
                    j.fn()
                    j.state = 'done'
                except Exception as e:
                    j.state = 'failed'
                    print('background survey %s failed: %s' % (j.name, e))
        else:
            try:
                job.fn()
                job.state = 'done'
            except Exception as e:          # (a survey that fails stays out of the way of the next)
                job.state = 'failed'
                print('background survey %s failed: %s' % (job.name, e))
        with _lock:
            _done.extend(j.name for j in batch if j.name not in _done)
            del _done[:-20]
        time.sleep(0.05)


def _in_process(jobs):
    """Run these jobs' tasks in one survey process; the set of jobs it reported done."""
    here = os.path.dirname(os.path.abspath(__file__))
    exe = sys.executable
    if os.path.basename(exe).lower() == 'pythonw.exe':
        alt = os.path.join(os.path.dirname(exe), 'python.exe')
        if os.path.isfile(alt):
            exe = alt
    args = [exe, os.path.join(here, 'surveyworker.py'), project_path[0] or '-', json.dumps([list(j.task) for j in jobs])]
    flags = 0
    if os.name == 'nt':
        flags = getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0x00004000) | getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
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
                    _done.append(j.name)
                    left = [k for k in jobs if k not in finished]
                    if left:
                        _running[0] = left[0]
                        left[0].t0 = time.time()
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
