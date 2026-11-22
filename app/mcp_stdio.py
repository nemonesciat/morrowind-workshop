"""Morrowind Workshop's MCP server over stdio, for coding agents that start a command instead of opening an address.
It passes each JSON-RPC line on to the running Workshop (mcpserver.py, at /mcp) and writes back its answer, one line
each. The Workshop's port and the agents' key are found by themselves (workshop_running.json and the settings beside
the Workshop); --port and --key set them. Nothing else is read.

    "<Workshop>/python/python.exe" "<Workshop>/app/mcp_stdio.py"        (Settings > AI shows the exact line)
"""
import json
import os
import sys
import urllib.error
import urllib.request

HOME = os.environ.get('WORKSHOP_HOME') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _arg(flag):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv[:-1] else None


def _where():
    port, key = _arg('--port'), _arg('--key')
    if not port:
        try:
            with open(os.path.join(HOME, 'workshop_running.json'), encoding='utf-8') as f:
                port = json.load(f).get('port')
        except (OSError, ValueError):
            port = None
    if not key:
        try:
            with open(os.path.join(HOME, 'workshop_settings.json'), encoding='utf-8') as f:
                key = json.load(f).get('mcp_key')
        except (OSError, ValueError):
            key = None
    return port, key


def _send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + '\n')
    sys.stdout.flush()


def main():
    session = None
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            _send({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error.'}})
            continue
        mid = msg.get('id') if isinstance(msg, dict) else None
        port, key = _where()
        if not port:
            if mid is not None:
                _send({'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32000, 'message': 'Morrowind Workshop isn\'t running: start it, '
                                                                                         'then try again.'}})
            continue
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
        if session:
            headers['Mcp-Session-Id'] = session
        url = 'http://127.0.0.1:%s/mcp?key=%s' % (port, key or '')
        req = urllib.request.Request(url, data=line.encode('utf-8'), headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                session = r.headers.get('Mcp-Session-Id') or session
                body = r.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', 'replace')
        except (urllib.error.URLError, OSError):
            if mid is not None:
                _send({'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32000, 'message': 'Morrowind Workshop isn\'t answering: is it '
                                                                                         'running?'}})
            continue
        if not body.strip():
            continue                                 # (a notification: nothing comes back)
        try:
            out = json.loads(body)
        except ValueError:
            continue
        if isinstance(out, dict) and out.get('id') is None and mid is not None and 'error' in out:
            out['id'] = mid                          # (a refusal before the message was read: given its id)
        _send(out)


if __name__ == '__main__':
    main()
