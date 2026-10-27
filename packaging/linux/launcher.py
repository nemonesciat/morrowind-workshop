"""Morrowind Workshop on Linux: what Morrowind Workshop.exe does on Windows. Starts the Workshop, opens it in a
window of its own (a Chromium-family browser in app mode, with a profile of the Workshop's own in the browser
folder here), and quits the Workshop when that window is closed. Without such a browser it opens in your usual
web browser and keeps running until you quit it (--quit, or Ctrl+C in the terminal it was started from).

    ./morrowind-workshop                 start it (or bring it up again if it is running)
    ./morrowind-workshop --quit          quit a running Workshop
    ./morrowind-workshop --browser       open it in your usual web browser instead of its own window
    ./morrowind-workshop --install-ai    set up the AI assistant's Python packages (needs the internet once)
    ./morrowind-workshop --menu          put Morrowind Workshop in your desktop's app menu again
    ./morrowind-workshop --no-menu       take it out of the app menu
    ./morrowind-workshop --log           print where the log is

Only Python's standard library is used here, so any Python 3.10 or newer starts it."""
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
NAME = 'Morrowind Workshop'
RUNNING = os.path.join(ROOT, 'workshop_running.json')
LOG = os.path.join(ROOT, 'workshop.log')
ENV_DIR = os.path.join(ROOT, 'python-env')            # (made by --install-ai: Python with the AI's packages)
PROFILE = os.path.join(ROOT, 'browser')               # (the window's own browser profile: your own browser is left alone)
MENU_FILE = os.path.join(os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share'),
                         'applications', 'morrowind-workshop.desktop')
# (Chromium and the browsers made from it: they open a page as a window of its own with --app)
BROWSERS = ['chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable', 'brave-browser', 'brave',
            'microsoft-edge', 'microsoft-edge-stable', 'vivaldi', 'vivaldi-stable', 'thorium-browser']


def tell(text, error=False):
    """A message where the person will see it: a desktop dialog when there is one, else the terminal."""
    print(text, file=sys.stderr if error else sys.stdout, flush=True)
    if sys.stdout and sys.stdout.isatty():
        return
    for exe, args in (('zenity', ['--error' if error else '--info', '--title=' + NAME, '--no-wrap', '--text=' + text]),
                      ('kdialog', ['--title', NAME, '--error' if error else '--msgbox', text]),
                      ('notify-send', [NAME, text])):
        path = shutil.which(exe)
        if path:
            try:
                subprocess.run([path] + args, timeout=600)
            except Exception:
                pass
            return


# ------------------------------------------------------------------ the running Workshop
def running_url():
    """The address of a Workshop that is running and answering, or None."""
    try:
        with open(RUNNING, encoding='utf-8') as f:
            url = json.load(f)['url']
        with urllib.request.urlopen(url + 'api/link', timeout=2) as r:
            return url if r.status == 200 else None
    except Exception:
        return None


def ask_to_quit(wait=8.0):
    url = running_url()
    if not url:
        return True
    try:
        req = urllib.request.Request(url + 'api/quit', data=b'', method='POST', headers={'X-Workshop-Quit': '1'})
        urllib.request.urlopen(req, timeout=3).close()
    except Exception:
        pass
    t0 = time.time()
    while time.time() - t0 < wait:
        time.sleep(0.25)
        if not running_url():
            return True
    return False


def python():
    p = os.path.join(ENV_DIR, 'bin', 'python3')
    return p if os.access(p, os.X_OK) else sys.executable


def start_server():
    try:
        if os.path.isfile(LOG):
            shutil.copyfile(LOG, os.path.join(ROOT, 'workshop.previous.log'))
    except OSError:
        pass
    log = open(LOG, 'w', encoding='utf-8')
    log.write('%s %s started %s (Python %s)\n' % (NAME, version(), time.strftime('%Y-%m-%d %H:%M:%S'), sys.version.split()[0]))
    log.flush()
    env = dict(os.environ, PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8', WORKSHOP_NO_BROWSER='1')
    for k in ('PYTHONHOME', 'PYTHONPATH'):
        env.pop(k, None)
    return subprocess.Popen([python(), '-X', 'utf8', os.path.join(ROOT, 'app', 'workshop.py')], cwd=ROOT, env=env,
                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)


def version():
    try:
        with open(os.path.join(ROOT, 'app', 'version.txt'), encoding='ascii') as f:
            return f.read().strip()
    except OSError:
        return ''


def log_tail(n=12):
    try:
        with open(LOG, encoding='utf-8', errors='replace') as f:
            return ''.join(f.readlines()[-n:])
    except OSError:
        return ''


# ------------------------------------------------------------------ its window
def find_browser():
    for b in BROWSERS:
        p = shutil.which(b)
        if p:
            return p
    return None


def open_window(url, wait=False):
    """The Workshop in a window of its own. The browser process when it was opened (and wait: once it closed),
    None when it opened in the usual web browser instead."""
    b = find_browser()
    if not b:
        webbrowser.open(url)
        return None
    os.makedirs(PROFILE, exist_ok=True)
    p = subprocess.Popen([b, '--app=' + url, '--user-data-dir=' + PROFILE, '--window-size=1440,900',
                          '--class=MorrowindWorkshop', '--no-first-run', '--no-default-browser-check'],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if wait:
        p.wait()
    return p


# ------------------------------------------------------------------ the app menu
def install_menu(quiet=False):
    icon = os.path.join(ROOT, 'app', 'web', 'vendor', 'workshop-256.png')
    text = ('[Desktop Entry]\nType=Application\nName=%s\nComment=Make Morrowind mods for OpenMW\n'
            'Exec="%s"\nIcon=%s\nTerminal=false\nCategories=Game;Development;\nStartupWMClass=MorrowindWorkshop\n' % (
                NAME, os.path.join(ROOT, 'morrowind-workshop').replace('"', '\\"'), icon))
    try:
        os.makedirs(os.path.dirname(MENU_FILE), exist_ok=True)
        with open(MENU_FILE, 'w', encoding='utf-8') as f:
            f.write(text)
        os.chmod(MENU_FILE, 0o755)
        if not quiet:
            print('%s is in your app menu now (%s).' % (NAME, MENU_FILE))
    except OSError as e:
        if not quiet:
            print('Could not add it to the app menu: %s' % e, file=sys.stderr)


def ours(path):
    try:
        with open(path, encoding='utf-8') as f:
            return os.path.join(ROOT, 'morrowind-workshop') in f.read()
    except OSError:
        return False


def remove_menu():
    if os.path.isfile(MENU_FILE) and ours(MENU_FILE):
        os.remove(MENU_FILE)
        print('Taken out of the app menu.')
    else:
        print('It was not in the app menu (or that entry belongs to another copy of the Workshop).')


# ------------------------------------------------------------------ the AI assistant's packages
def install_ai():
    """A Python of the Workshop's own (python-env here) with the AI assistant's library and zstandard (Blender's
    compressed .blend files). Your system's Python is not changed."""
    if not os.path.isdir(ENV_DIR):
        print('Making the Workshop\'s own Python environment in %s ...' % ENV_DIR, flush=True)
        r = subprocess.run([sys.executable, '-m', 'venv', ENV_DIR])
        if r.returncode != 0:
            shutil.rmtree(ENV_DIR, ignore_errors=True)
            print('\nThat did not work. On Debian and Ubuntu, install the "python3-venv" package first:\n'
                  '    sudo apt install python3-venv\nthen run this again.', file=sys.stderr)
            return 1
    print('Installing the AI assistant\'s packages (anthropic, zstandard) ...', flush=True)
    r = subprocess.run([os.path.join(ENV_DIR, 'bin', 'python3'), '-m', 'pip', 'install', '--upgrade', 'anthropic', 'zstandard'])
    if r.returncode != 0:
        print('\nInstalling failed (see above). Is the computer online?', file=sys.stderr)
        return 1
    print('\nDone. Restart the Workshop, then add your Anthropic API key in Help > Settings.')
    return 0


# ------------------------------------------------------------------ start
def main(argv):
    if sys.version_info < (3, 10):
        tell('%s needs Python 3.10 or newer; this is Python %s. Install a newer python3 from your system\'s software '
             'centre.' % (NAME, sys.version.split()[0]), error=True)
        return 1
    if '--help' in argv or '-h' in argv:
        print(__doc__)
        return 0
    if '--log' in argv:
        print(LOG)
        return 0
    if '--quit' in argv:
        return 0 if ask_to_quit() else 1
    if '--menu' in argv:
        install_menu()
        return 0
    if '--no-menu' in argv:
        remove_menu()
        return 0
    if '--install-ai' in argv:
        return install_ai()
    in_browser = '--browser' in argv

    url = running_url()
    if url:                                   # (running already: show it again)
        if in_browser:
            webbrowser.open(url)
        else:
            open_window(url)
        return 0
    try:
        probe = os.path.join(ROOT, '.write-test')
        open(probe, 'w').close()
        os.remove(probe)
    except OSError:
        tell("%s can't save in this folder:\n%s\n\nMove the Morrowind Workshop folder somewhere you can save files, "
             "such as your home folder, and start it from there." % (NAME, ROOT), error=True)
        return 1
    if not os.path.isfile(MENU_FILE):
        install_menu(quiet=True)              # (the first start: in the app menu from now on; --no-menu takes it out)

    server = start_server()
    quitting = []

    def stop(*_a):
        quitting.append(1)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    t0 = time.time()
    while not quitting and server.poll() is None and not running_url() and time.time() - t0 < 120:
        time.sleep(0.4)
    url = running_url()
    if not url:
        if server.poll() is None:
            server.terminate()
        if not quitting:
            tell('%s could not start.\n\n%s\nThe whole log is in %s' % (NAME, log_tail(), LOG), error=True)
        return 1
    print('%s is running at %s (log: %s)' % (NAME, url, LOG), flush=True)

    if in_browser:
        webbrowser.open(url)
        window = None
    else:
        window = open_window(url)             # (None: no Chromium-family browser, so it is in the usual one)
    if window is None:
        print('It is open in your web browser. To quit: Ctrl+C here, or run "%s --quit".'
              % os.path.join(ROOT, 'morrowind-workshop'), flush=True)
    opened = time.time()
    while not quitting and server.poll() is None:
        time.sleep(0.5)
        if window is not None and window.poll() is not None:
            if time.time() - opened < 5:
                # (the browser handed the window to one already running with this profile and left: the window
                # can't be watched from here, so the Workshop keeps running until it is quit)
                window = None
                continue
            break                             # (its window was closed)
    if server.poll() not in (None, 0) and not quitting:
        # (0 is a Workshop that was asked to quit: --quit from another terminal)
        if window is not None and window.poll() is None:
            window.terminate()
        tell('%s stopped unexpectedly.\n\n%s\nThe whole log is in %s' % (NAME, log_tail(), LOG), error=True)
        return 1
    if window is not None and window.poll() is None:
        window.terminate()
    ask_to_quit()
    try:
        server.wait(4)
    except subprocess.TimeoutExpired:
        server.kill()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
