"""Asking the home router to let others in (UPnP), for building together from other networks.

Most home routers will open a port when a program on the network asks them to (UPnP). This finds the
router, asks it to pass one port to this PC while hosting (and to stop again afterwards), and asks
it for the home's public address, which goes into the invite. Some routers have it switched off, and
some internet providers share one address between many homes; then it can't work, and Tailscale is
the way."""
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

ST = ('urn:schemas-upnp-org:device:InternetGatewayDevice:1', 'urn:schemas-upnp-org:service:WANIPConnection:1',
      'urn:schemas-upnp-org:service:WANIPConnection:2', 'urn:schemas-upnp-org:service:WANPPPConnection:1')
_found = {}


def _local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))           # (no packet is sent: it only picks the way out)
        return s.getsockname()[0]
    finally:
        s.close()


def find(timeout=2.5):
    """The router's control address: (url, service type, this PC's address) or None."""
    if _found.get('ok'):
        return _found['ok']
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.settimeout(timeout)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    locations = []
    try:
        for st in ST:
            msg = ('M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\nMX: 2\r\nST: %s\r\n\r\n' % st)
            sock.sendto(msg.encode('ascii'), ('239.255.255.250', 1900))
        while True:
            try:
                data, _a = sock.recvfrom(4096)
            except socket.timeout:
                break
            m = re.search(rb'(?im)^location:\s*(\S+)', data)
            if m and m.group(1).decode('ascii', 'replace') not in locations:
                locations.append(m.group(1).decode('ascii', 'replace'))
    except OSError:
        pass
    finally:
        sock.close()
    for loc in locations:
        try:
            with urllib.request.urlopen(loc, timeout=4) as r:
                xml = r.read().decode('utf-8', 'replace')
        except Exception:
            continue
        for svc in re.findall(r'<service>(.*?)</service>', xml, re.S | re.I):
            t = re.search(r'<serviceType>\s*([^<]+?)\s*</serviceType>', svc, re.I)
            c = re.search(r'<controlURL>\s*([^<]+?)\s*</controlURL>', svc, re.I)
            if t and c and ('WANIPConnection' in t.group(1) or 'WANPPPConnection' in t.group(1)):
                base = re.search(r'<URLBase>\s*([^<]+?)\s*</URLBase>', xml, re.I)
                url = urllib.parse.urljoin(base.group(1) if base else loc, c.group(1))
                _found['ok'] = (url, t.group(1), _local_ip())
                return _found['ok']
    return None


def _soap(action, args, timeout=5):
    got = find()
    if not got:
        raise OSError('No router answered (UPnP is off, or there isn\'t one).')
    url, st, _ip = got
    body = ''.join('<%s>%s</%s>' % (k, v, k) for k, v in args)
    env = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
           's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:%s xmlns:u="%s">%s</u:%s></s:Body></s:Envelope>'
           % (action, st, body, action))
    req = urllib.request.Request(url, data=env.encode('utf-8'), method='POST',
                                 headers={'Content-Type': 'text/xml; charset="utf-8"', 'SOAPAction': '"%s#%s"' % (st, action)})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', 'replace')
        code = re.search(r'<errorDescription>([^<]+)</errorDescription>', detail)
        raise OSError(code.group(1) if code else 'the router said no (%s)' % e.code)


def public_address():
    """The home's address on the internet, as the router sees it, or None."""
    try:
        xml = _soap('GetExternalIPAddress', [])
    except (OSError, ValueError):
        return None
    m = re.search(r'<NewExternalIPAddress>\s*([0-9.]+)\s*<', xml)
    ip = m.group(1) if m else None
    # (an address the internet can't reach: the provider shares one between many homes)
    if not ip or ip.startswith(('10.', '192.168.', '127.', '0.')) or re.match(r'^(172\.(1[6-9]|2\d|3[01])|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7]))\.', ip):
        return None
    return ip


def open_port(port, minutes=0):
    """Ask the router to pass this port to this PC (until closed; minutes=0: no time limit)."""
    _url, _st, ip = find() or (None, None, None)
    if not ip:
        raise OSError('No router answered (UPnP is off, or there isn\'t one).')
    _soap('AddPortMapping', [('NewRemoteHost', ''), ('NewExternalPort', port), ('NewProtocol', 'TCP'), ('NewInternalPort', port),
                             ('NewInternalClient', ip), ('NewEnabled', 1), ('NewPortMappingDescription', 'Morrowind Workshop (building together)'),
                             ('NewLeaseDuration', minutes * 60)])


def close_port(port):
    try:
        _soap('DeletePortMapping', [('NewRemoteHost', ''), ('NewExternalPort', port), ('NewProtocol', 'TCP')])
    except OSError:
        pass
