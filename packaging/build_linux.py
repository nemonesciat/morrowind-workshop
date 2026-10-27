"""Build "Morrowind Workshop <version> linux.tar.gz": the Workshop for Linux, made on Windows with nothing downloaded.

Run with the Python the Workshop is developed with:  py -3 packaging\\build_linux.py
Output goes to packaging\\out_linux (packaging\\out is the Windows build's, which empties it). As build.py, it can
build from a snapshot:  py -3 -c "import build_linux as b; b.APP = r'<snapshot>\\app'; b.SUFFIX = 'linux-beta'; b.main()"

Unlike the Windows build there is no Python inside: Linux has its own python3, and the Workshop itself is plain
Python and web pages. The AI assistant's packages are set up on the person's computer when they ask
(morrowind-workshop --install-ai). The package:
  Morrowind Workshop/
    morrowind-workshop     starts it (a shell script: finds python3, runs launcher.py)
    launcher.py            the window, the app menu entry, quitting, --install-ai
    app/                   the Workshop itself
    README.txt, THIRD_PARTY_NOTICES.txt
"""
import io
import os
import sys
import tarfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP = os.path.join(ROOT, 'app')
LINUX = os.path.join(HERE, 'linux')
OUT = os.path.join(HERE, 'out_linux')
VERSION_FILE = os.path.join(HERE, 'version.txt')
TOP = 'Morrowind Workshop'
SUFFIX = 'linux'                  # (the file's last word: "linux-beta" while Linux is new)
APP_SKIP = {'__pycache__'}
# (Windows-only files in app that Linux has no use for)
APP_SKIP_FILES = {'workshop.ico'}
TEXT_EXT = ('.py', '.sh', '.md', '.txt', '.desktop')


def log(*a):
    print(*a, flush=True)


def notices(version):
    """THIRD_PARTY_NOTICES.txt for Linux: what is bundled is only the page's own libraries and fonts; Python and
    the AI assistant's packages come from the person's own system (or from PyPI with --install-ai)."""
    sys.path.insert(0, APP)
    import helpinfo
    lines = ['Morrowind Workshop %s for Linux: third-party software' % version, '=' * 60, '',
             'The Workshop includes the following, each under its own licence.', '']
    for c in helpinfo.components():
        if not c.get('text'):
            continue
        lines.append('%s %s' % (c['name'], c['version']) + ('  by %s' % c['by'] if c.get('by') else ''))
        lines.append('    Licence: %s%s' % (c['license'], ('    ' + c['url']) if c.get('url') else ''))
        try:
            with open(os.path.join(helpinfo.LICENSES, c['text']), encoding='utf-8') as f:
                lines += ['', '    ' + '\n    '.join(f.read().strip().splitlines()), '']
        except OSError:
            pass
        lines.append('')
    lines.append('Python is not included: the Workshop runs on your system\'s own python3. The AI assistant\'s packages '
                 '(anthropic and what it needs, and zstandard) are installed from PyPI when you run '
                 'morrowind-workshop --install-ai, each under its own licence (in python-env/lib/.../site-packages).')
    lines.append('Morrowind Workshop is not made by or affiliated with Bethesda Softworks or the OpenMW project.')
    return '\n'.join(lines) + '\n'


def add_bytes(tar, name, data, mode=0o644):
    ti = tarfile.TarInfo(name)
    ti.size = len(data)
    ti.mode = mode
    ti.mtime = int(time.time())
    tar.addfile(ti, io.BytesIO(data))


def add_file(tar, src, name, mode=0o644):
    with open(src, 'rb') as f:
        data = f.read()
    if src.lower().endswith(TEXT_EXT) or mode == 0o755:
        data = data.replace(b'\r\n', b'\n')            # (Linux line ends: a shell script with \r doesn't run)
    add_bytes(tar, name, data, mode)


def main():
    version = open(VERSION_FILE, encoding='ascii').read().strip()
    log('Morrowind Workshop', version, 'for Linux, from', APP)
    os.makedirs(OUT, exist_ok=True)
    out = os.path.join(OUT, 'Morrowind Workshop %s %s.tar.gz' % (version, SUFFIX))
    n = 0
    with tarfile.open(out, 'w:gz', compresslevel=9, format=tarfile.PAX_FORMAT) as tar:
        add_file(tar, os.path.join(LINUX, 'morrowind-workshop'), TOP + '/morrowind-workshop', 0o755)
        add_file(tar, os.path.join(LINUX, 'launcher.py'), TOP + '/launcher.py', 0o755)
        add_file(tar, os.path.join(LINUX, 'README.md'), TOP + '/README.txt')
        add_bytes(tar, TOP + '/THIRD_PARTY_NOTICES.txt', notices(version).encode('utf-8'))
        add_bytes(tar, TOP + '/app/version.txt', version.encode('ascii'))
        for dp, dirs, files in os.walk(APP):
            dirs[:] = sorted(d for d in dirs if d not in APP_SKIP)
            for fn in sorted(files):
                if fn.endswith(('.pyc', '.pyo')) or fn in APP_SKIP_FILES or fn == 'version.txt' and dp == APP:
                    continue
                full = os.path.join(dp, fn)
                rel = os.path.relpath(full, APP).replace(os.sep, '/')
                add_file(tar, full, TOP + '/app/' + rel)
                n += 1
    log('Done: %s (%.1f MB, %d app files)' % (out, os.path.getsize(out) / 1e6, n))
    return out


if __name__ == '__main__':
    main()
