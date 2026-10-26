"""Build "Morrowind Workshop Setup.exe": a per-user installer with its own copy of Python.

Run with the Python the Workshop is developed with:  py -3 packaging\\build.py
Output goes to packaging\\out. Nothing is downloaded: Python comes from this computer's
own installation, and the two small programs (launcher and setup) are compiled with the
C# compiler that ships with Windows.

The package:
  python\\              Python with only what the Workshop needs (standard library, the AI
                       assistant's library and its dependencies, and the DLLs they use)
  app\\                 the Workshop itself
  Morrowind Workshop.exe   starts it (tray icon: open, show log, quit) and uninstalls it
"""
import importlib.metadata as md
import os
import re
import shutil
import struct
import subprocess
import sys
import zipfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP = os.path.join(ROOT, 'app')
OUT = os.path.join(HERE, 'out')
STAGE = os.path.join(OUT, 'stage')
CSC = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), r'Microsoft.NET\Framework64\v4.0.30319\csc.exe')
VERSION_FILE = os.path.join(HERE, 'version.txt')

PY = sys.base_prefix
PYVER = 'python%d%d' % sys.version_info[:2]
# parts of the standard library the Workshop never uses
LIB_SKIP = {'site-packages', 'test', 'tests', 'idlelib', 'tkinter', 'turtledemo', 'ensurepip', 'lib2to3',
            '__pycache__', 'venv', 'pydoc_data', 'distutils', 'turtle.py'}
DLL_SKIP = re.compile(r'^(_test|xxlimited|_tkinter|_ctypes_test)', re.I)
# the AI assistant's library, and zstandard (opens Blender's compressed .blend files); everything they
# need is found from their package metadata
PACKAGES = ['anthropic', 'zstandard']
APP_SKIP = {'__pycache__'}


def log(*a):
    print(*a, flush=True)


# ------------------------------------------------------------------ Python
def copy_tree(src, dst, skip=()):
    for name in os.listdir(src):
        if name in skip or name.endswith(('.pyc', '.pyo')):
            continue
        s, d = os.path.join(src, name), os.path.join(dst, name)
        if os.path.isdir(s):
            os.makedirs(d, exist_ok=True)
            copy_tree(s, d, skip)
        else:
            shutil.copy2(s, d)


def dists_needed(names):
    seen, out, todo = set(), [], list(names)
    while todo:
        n = todo.pop()
        key = re.sub(r'[-_.]+', '-', n).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            d = md.distribution(n)
        except md.PackageNotFoundError:
            continue                  # only needed on other Python versions / platforms
        out.append(d)
        for r in d.requires or []:
            if 'extra ==' in r:
                continue
            todo.append(re.split(r'[\s;<>=!~\[(]', r.strip())[0])
    return out


def pe_imports(path):
    """DLL names a Windows program or DLL loads (its import table)."""
    with open(path, 'rb') as f:
        data = f.read()
    try:
        pe = struct.unpack_from('<I', data, 0x3C)[0]
        if data[pe:pe + 4] != b'PE\0\0':
            return []
        nsec = struct.unpack_from('<H', data, pe + 6)[0]
        optsize = struct.unpack_from('<H', data, pe + 20)[0]
        opt = pe + 24
        magic = struct.unpack_from('<H', data, opt)[0]
        dd = opt + (112 if magic == 0x20B else 96)
        imp_rva = struct.unpack_from('<I', data, dd + 8)[0]
        secs = []
        for i in range(nsec):
            s = opt + optsize + i * 40
            vsize, va, rsize, rptr = struct.unpack_from('<IIII', data, s + 8)
            secs.append((va, max(vsize, rsize), rptr))

        def off(rva):
            for va, size, rptr in secs:
                if va <= rva < va + size:
                    return rva - va + rptr
            return None
        out, p = [], off(imp_rva)
        while p is not None:
            name_rva = struct.unpack_from('<I', data, p + 12)[0]
            if not name_rva:
                break
            q = off(name_rva)
            out.append(data[q:data.index(b'\0', q)].decode('ascii', 'replace'))
            p += 20
        return out
    except (struct.error, ValueError):
        return []


def precompile(py_dir, site):
    """Ship the libraries as compiled files sitting where their source was ("x.pyc" instead of
    "__pycache__/x.cpython-313.pyc"): faster to start, and much shorter paths, which matters
    because some Windows tools still can't handle paths over 260 characters."""
    # (-d: record a neutral path in the compiled files, not the folder they were built in)
    r = subprocess.run([sys.executable, '-m', 'compileall', '-b', '-q', '-j0', '-d', r'python\Lib\site-packages', site],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit('Compiling the libraries failed:\n' + r.stdout + r.stderr)
    for dp, dirs, files in os.walk(site):
        for fn in files:
            if fn.endswith(('.py', '.pyi')) and os.path.exists(os.path.join(dp, os.path.splitext(fn)[0] + '.pyc')) \
                    or fn.endswith('.pyi'):
                os.remove(os.path.join(dp, fn))
    strip_pycache(site)


def strip_pycache(top):
    for dp, dirs, _files in os.walk(top):
        for d in list(dirs):
            if d == '__pycache__':
                shutil.rmtree(os.path.join(dp, d))
                dirs.remove(d)


def collect_dlls(py_dir):
    """Copy the non-Windows DLLs that python.exe, its DLL and the .pyd modules load."""
    search = [PY, os.path.join(PY, 'DLLs'), os.path.join(PY, 'Library', 'bin')]
    sys32 = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'System32')
    have = {n.lower() for n in os.listdir(py_dir)} | {n.lower() for n in os.listdir(os.path.join(py_dir, 'DLLs'))}
    todo = [os.path.join(dp, f) for dp, _d, fs in os.walk(py_dir) for f in fs if f.lower().endswith(('.dll', '.pyd', '.exe'))]
    added = []
    while todo:
        for dep in pe_imports(todo.pop()):
            low = dep.lower()
            if low in have or low.startswith(('api-ms-', 'ext-ms-')) or os.path.exists(os.path.join(sys32, dep)):
                continue
            src = next((os.path.join(d, dep) for d in search if os.path.exists(os.path.join(d, dep))), None)
            have.add(low)
            if not src:
                log('  ! not found:', dep)
                continue
            dst = os.path.join(py_dir, dep)
            shutil.copy2(src, dst)
            added.append(dep)
            todo.append(dst)
    return added


def build_python(py_dir):
    log('Python from', PY)
    os.makedirs(py_dir)
    for f in os.listdir(PY):
        if re.match(r'^(python(w)?\.exe|python3\d*\.dll|vcruntime140.*\.dll|msvcp140.*\.dll|LICENSE.*)$', f, re.I):
            shutil.copy2(os.path.join(PY, f), os.path.join(py_dir, f))
    os.makedirs(os.path.join(py_dir, 'DLLs'))
    for f in os.listdir(os.path.join(PY, 'DLLs')):
        if f.lower().endswith(('.pyd', '.dll')) and not DLL_SKIP.match(f):
            shutil.copy2(os.path.join(PY, 'DLLs', f), os.path.join(py_dir, 'DLLs', f))
    lib = os.path.join(py_dir, 'Lib')
    os.makedirs(lib)
    copy_tree(os.path.join(PY, 'Lib'), lib, LIB_SKIP)
    site = os.path.join(lib, 'site-packages')
    os.makedirs(site)
    for d in dists_needed(PACKAGES):
        n = 0
        for f in d.files or []:
            src = os.path.abspath(d.locate_file(f))
            if '__pycache__' in str(f) or not os.path.isfile(src):
                continue
            rel = os.path.relpath(src, os.path.join(PY, 'Lib', 'site-packages'))
            if rel.startswith('..'):
                continue                  # (scripts and the like outside site-packages)
            dst = os.path.join(site, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            n += 1
        log('  %s %s (%d files)' % (d.metadata['Name'], d.version, n))
    precompile(py_dir, site)
    added = collect_dlls(py_dir)
    log('  DLLs the modules need:', ', '.join(added) or 'none')
    # a "._pth" file makes this Python ignore any other Python on the computer
    with open(os.path.join(py_dir, PYVER + '._pth'), 'w', encoding='ascii') as f:
        f.write('Lib\nDLLs\nLib\\site-packages\n..\\app\n')


def check_python(py_dir):
    """Import everything the Workshop uses with the bundled Python, with nothing else on PATH."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(('PYTHON', 'CONDA'))}
    env['PATH'] = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'System32')
    mods = sorted(os.path.splitext(f)[0] for f in os.listdir(os.path.join(STAGE, 'app')) if f.endswith('.py'))
    code = ('import sys, ssl, ctypes, sqlite3, zipfile, lzma, bz2, json, http.server, webbrowser, xml.etree.ElementTree\n'
            'import anthropic, zstandard\n'
            'c = anthropic.Anthropic(api_key="test")\n'
            'for m in %r: __import__(m)\n'
            'print("ok", sys.version.split()[0], sys.prefix)\n') % mods
    r = subprocess.run([os.path.join(py_dir, 'python.exe'), '-c', code], env=env, capture_output=True, text=True,
                       cwd=os.path.join(STAGE, 'app'))
    if r.returncode != 0 or not r.stdout.startswith('ok'):
        raise SystemExit('The bundled Python does not work:\n' + r.stdout + r.stderr)
    log('  check:', r.stdout.strip())


# ------------------------------------------------------------------ icon
def png(size, pixels):
    raw = b''.join(b'\0' + bytes(pixels[y * size * 4:(y + 1) * size * 4]) for y in range(size))
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def draw_icon(size):
    """A gold ring with a four-pointed star on dark leather: the Workshop's mark."""
    ss = 4
    n = size * ss
    px = bytearray(size * size * 4)
    bg, gold, rim = (42, 33, 24), (226, 176, 74), (120, 88, 40)
    for y in range(size):
        for x in range(size):
            acc = [0.0, 0.0, 0.0, 0.0]
            for sy in range(ss):
                for sx in range(ss):
                    u = ((x * ss + sx + 0.5) / n) * 2 - 1
                    v = ((y * ss + sy + 0.5) / n) * 2 - 1
                    # rounded square background
                    q = max(abs(u), abs(v))
                    corner = ((max(abs(u) - 0.72, 0)) ** 2 + (max(abs(v) - 0.72, 0)) ** 2) ** 0.5
                    if q > 0.98 or corner > 0.24:
                        continue
                    col = bg
                    if q > 0.90 or corner > 0.17:
                        col = rim
                    r = (u * u + v * v) ** 0.5
                    if 0.56 < r < 0.70:
                        col = gold
                    # four-pointed star
                    if abs(u) ** 0.6 + abs(v) ** 0.6 < 0.62 ** 0.6 * 1.25 and r < 0.62:
                        col = gold
                    acc[0] += col[0]; acc[1] += col[1]; acc[2] += col[2]; acc[3] += 255
            k = ss * ss
            a = acc[3] / k
            if a:
                px[(y * size + x) * 4:(y * size + x + 1) * 4] = bytes(
                    [int(acc[0] / (acc[3] / 255)), int(acc[1] / (acc[3] / 255)), int(acc[2] / (acc[3] / 255)), int(a)])
    return png(size, px)


def write_icon(path):
    sizes = [16, 24, 32, 48, 64, 256]
    imgs = [draw_icon(s) for s in sizes]
    head = struct.pack('<HHH', 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = b''
    for s, img in zip(sizes, imgs):
        entries += struct.pack('<BBBBHHII', s % 256, s % 256, 0, 0, 1, 32, len(img), offset)
        offset += len(img)
    with open(path, 'wb') as f:
        f.write(head + entries + b''.join(imgs))


# ------------------------------------------------------------------ programs
def asm_info(title, description, version):
    """Version details for the .exe (what Windows shows under Properties, Details)."""
    nums = (re.findall(r'\d+', version) + ['0'] * 4)[:4]
    v = '.'.join(nums)
    return ''.join('[assembly: System.Reflection.%s("%s")]\n' % kv for kv in (
        ('AssemblyTitle', title), ('AssemblyDescription', description), ('AssemblyProduct', 'Morrowind Workshop'),
        ('AssemblyCopyright', 'Morrowind Workshop'), ('AssemblyVersion', v), ('AssemblyFileVersion', v),
        ('AssemblyInformationalVersion', version)))


def compile_cs(sources, exe, icon, resources=(), extra_refs=()):
    args = [CSC, '/nologo', '/optimize+', '/target:winexe', '/platform:anycpu', '/out:' + exe, '/win32icon:' + icon,
            '/win32manifest:' + os.path.join(HERE, 'app.manifest'),
            '/r:System.Windows.Forms.dll', '/r:System.Drawing.dll', '/r:System.IO.Compression.dll',
            '/r:System.IO.Compression.FileSystem.dll'] + ['/r:' + r for r in extra_refs]
    args += ['/resource:%s,%s' % (path, name) for path, name in resources]
    args += sources
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit('Compiling %s failed:\n%s' % (os.path.basename(exe), r.stdout + r.stderr))


def main():
    if not os.path.exists(CSC):
        raise SystemExit('The C# compiler that comes with Windows was not found at ' + CSC)
    version = open(VERSION_FILE, encoding='ascii').read().strip()
    log('Morrowind Workshop', version)
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(STAGE)
    # the icon, also used by the page itself (the Workshop window's taskbar button shows it). Since 2026-10-26 it
    # is web/vendor/workshop-icon.svg (the logo's half gear, M over W) rendered at 16-256; draw_icon's ring and
    # star is only the stand-in when the file is missing
    icon = os.path.join(APP, 'web', 'vendor', 'workshop.ico')
    if not os.path.exists(icon):
        write_icon(icon)

    log('App')
    os.makedirs(os.path.join(STAGE, 'app'))
    copy_tree(APP, os.path.join(STAGE, 'app'), APP_SKIP)
    with open(os.path.join(STAGE, 'app', 'version.txt'), 'w', encoding='ascii') as f:
        f.write(version)

    build_python(os.path.join(STAGE, 'python'))
    check_python(os.path.join(STAGE, 'python'))
    strip_pycache(STAGE)                       # (left by the check; Python remakes them as needed)
    longest = max((os.path.relpath(os.path.join(dp, f), STAGE) for dp, _d, fs in os.walk(STAGE) for f in fs), key=len)
    log('  longest path inside: %d characters' % len(longest))
    global LONGEST
    LONGEST = len(longest)

    # the readme and the third-party notices (licences of everything bundled)
    shutil.copy2(os.path.join(HERE, 'README.md'), os.path.join(STAGE, 'README.txt'))
    sys.path.insert(0, os.path.join(STAGE, 'app'))
    import helpinfo
    with open(os.path.join(STAGE, 'THIRD_PARTY_NOTICES.txt'), 'w', encoding='utf-8') as f:
        f.write(helpinfo.notices_text())
    shutil.copy2(os.path.join(HERE, 'README.md'), os.path.join(OUT, 'README.md'))       # (for the download page)

    log('Launcher')
    gen = os.path.join(OUT, 'Version.cs')
    with open(gen, 'w', encoding='utf-8') as f:
        f.write(asm_info('Morrowind Workshop', 'Starts Morrowind Workshop', version))
        f.write('static class BuildInfo { public const string Version = "%s"; }\n' % version)
    compile_cs([os.path.join(HERE, 'launcher.cs'), os.path.join(HERE, 'appwindow.cs'), os.path.join(HERE, 'common.cs'), gen],
               os.path.join(STAGE, 'Morrowind Workshop.exe'), icon)

    log('Payload')
    payload = os.path.join(OUT, 'payload.zip')
    total = 0
    with zipfile.ZipFile(payload, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dp, _dirs, files in os.walk(STAGE):
            for fn in files:
                full = os.path.join(dp, fn)
                z.write(full, os.path.relpath(full, STAGE).replace(os.sep, '/'))
                total += os.path.getsize(full)
    with open(os.path.join(OUT, 'size.txt'), 'w') as f:
        f.write(str(total // 1024))

    log('Setup')
    with open(gen, 'w', encoding='utf-8') as f:
        f.write(asm_info('Morrowind Workshop Setup', 'Installs Morrowind Workshop', version))
        f.write('static class BuildInfo { public const string Version = "%s"; public const long SizeKB = %d; '
                'public const int LongestPath = %d; }\n' % (version, total // 1024, LONGEST))
    setup = os.path.join(OUT, 'Morrowind Workshop Setup.exe')
    compile_cs([os.path.join(HERE, 'setup.cs'), os.path.join(HERE, 'common.cs'), gen], setup, icon,
               resources=[(payload, 'payload.zip')])
    # the same files as a plain zip, for people who'd rather not run an installer
    portable = os.path.join(OUT, 'Morrowind Workshop %s portable.zip' % version)
    with zipfile.ZipFile(portable, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dp, _dirs, files in os.walk(STAGE):
            for fn in files:
                full = os.path.join(dp, fn)
                z.write(full, 'Morrowind Workshop/' + os.path.relpath(full, STAGE).replace(os.sep, '/'))
    log('Done: %s (%.1f MB; %.0f MB installed)' % (setup, os.path.getsize(setup) / 1e6, total / 1e6))
    log('      %s (%.1f MB)' % (portable, os.path.getsize(portable) / 1e6))


if __name__ == '__main__':
    main()
