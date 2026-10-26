#!/usr/bin/env python3
"""Capture known read endpoints of ZX310S 1.0.0.6. Never applies settings."""
import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import subprocess

# GET alone does not imply a read: clear_statistics.json is deliberately absent.
READ_PATHS = (
    '/status.json', '/network_settings.json', '/port_setting_load.json',
    '/port_statistics.json', '/port_vlan_cfg.json', '/tag_vlan_cfg.json',
    '/port_trunk_cfg.json', '/port_mirror.json', '/stp.json',
    '/igmp_config.json', '/storm_ctrl_cfg.json',
)


def split_response(raw):
    """This firmware sometimes includes another complete HTTP header in its body."""
    headers = []
    while raw.startswith(b'HTTP/1.') and b'\r\n\r\n' in raw:
        header, raw = raw.split(b'\r\n\r\n', 1)
        headers.append(header)
    return headers, raw


def transfer(url, cookie=None):
    # URLs are assembled solely from validated numeric IP and fixed paths.
    config = f'url="{url}"\n'
    if cookie:
        if any(c in cookie for c in '\r\n"\\'):
            raise ValueError('Unsupported cookie encoding')
        config += f'header="Cookie: {cookie}"\n'
    result = subprocess.run(
        ['curl', '--noproxy', '*', '--max-time', '15', '--max-filesize', '1048576',
         '-sS', '-i', '--config', '-'],
        input=config.encode(), capture_output=True, timeout=20,
    )
    if result.returncode:
        # Do not echo URLs, credentials, hashes, cookies or raw curl diagnostics.
        raise RuntimeError(f'curl failed with exit {result.returncode}')
    return split_response(result.stdout)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('address', help='numeric management IP')
    p.add_argument('--user', default='admin')
    p.add_argument('--output', type=Path, required=True, help='new directory')
    a = p.parse_args()
    ip = ipaddress.ip_address(a.address)
    host = f'[{ip}]' if ip.version == 6 else str(ip)
    password = getpass.getpass('Switch password: ')
    base = f'http://{host}'
    usr = hashlib.md5(a.user.encode()).hexdigest()
    pwd = hashlib.md5(password.encode()).hexdigest()
    headers, body = transfer(f'{base}/authorize?loginusr={usr}&loginpwd={pwd}')
    cookies = {}
    for header in headers:
        for match in re.finditer(rb'(?im)^Set-Cookie:\s*([^\r\n]+)', header):
            value = match[1].split(b';', 1)[0].decode('ascii')
            key, sep, value = value.partition('=')
            if sep:
                cookies[key] = value
    if b'login.html' in body or 'session' not in cookies:
        raise RuntimeError('Login failed or session cookie absent')
    cookie = '; '.join(k + '=' + v for k, v in cookies.items())
    a.output.mkdir(parents=True, exist_ok=False)
    records = []
    for endpoint in READ_PATHS:
        headers, data = transfer(base + endpoint, cookie)
        target = a.output / endpoint[1:]
        target.write_bytes(data)
        parsed = False
        if b'window.location.href' not in data[:400]:
            try:
                json.loads(data)
                parsed = True
            except ValueError:
                pass
        records.append({
            'endpoint': endpoint, 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest(),
            'valid_json': parsed,
            'http_status_line': headers[-1].split(b'\r\n', 1)[0].decode('ascii') if headers else None,
        })
        print(endpoint, len(data), 'JSON' if parsed else 'non-JSON')
    (a.output / 'manifest.json').write_text(json.dumps({
        'address': str(ip), 'captured_at': datetime.now(timezone.utc).isoformat(),
        'operations': records,
        'limitations': ['Observed reads only; no write, save, reboot or update requests sent.',
                        'No credentials or session cookies retained in capture.'],
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
