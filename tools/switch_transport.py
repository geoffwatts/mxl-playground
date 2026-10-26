"""Serialized HTTP transport for the V2 CivetWeb server. Credentials stay in RAM."""
import hashlib
import json
import re
import subprocess
import threading
from urllib.parse import urlencode
from capture_readonly import split_response

class SwitchError(RuntimeError):
    pass

class SwitchTransport:
    def __init__(self, address, timeout=6, interface=None):
        import ipaddress
        self.address = str(ipaddress.IPv4Address(address))
        if interface is not None and not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.:-]{0,63}',interface):
            raise ValueError('Expected a local network interface name')
        self.interface = interface
        self.base = 'http://' + self.address
        self.cookie = None
        self.lock = threading.RLock()
        self.timeout = timeout

    def login(self, username, password):
        with self.lock:
            self.cookie = None
            usr, pwd = (hashlib.md5(x.encode()).hexdigest() for x in (username, password))
            response = self.request('/authorize', query={'loginusr': usr, 'loginpwd': pwd}, authenticate=False)
            cookies = []
            for header in response.pop('_headers'):
                for match in re.finditer(rb'(?im)^Set-Cookie:\s*([^\r\n]+)', header):
                    cookies.append(match[1].split(b';', 1)[0].decode('ascii'))
            if not any(x.startswith('session=') for x in cookies):
                raise SwitchError('Login rejected by the switch')
            cookie = '; '.join(cookies)
            if any(c in cookie for c in '\r\n"\\'):
                raise SwitchError('Unexpected cookie encoding')
            self.cookie = cookie
            check = self.request('/status.json')
            if not isinstance(check['data'], dict) or 'fw_ver' not in check['data']:
                self.cookie = None
                raise SwitchError('Login did not yield authenticated status')
            return check['data']

    def request(self, path, method='GET', body=None, query=None, stream=False,
                allow_empty=False, authenticate=True, binary=False):
        with self.lock:
            if authenticate and not self.cookie:
                raise SwitchError('Connect to the switch first')
            url = self.base + path + ('?' + urlencode(query, doseq=True) if query else '')
            config = f'url="{url}"\n'
            if self.cookie:
                config += f'header="Cookie: {self.cookie}"\n'
            args = ['curl', '--noproxy', '*', '--connect-timeout', '3', '--max-time',
                    str(self.timeout), '--max-filesize', '16777216', '-sS', '-i', '--config', '-']
            if self.interface is not None:
                # if! forces an interface name, rather than a hostname/source
                # address fallback. Essential when testing tagged isolation.
                args += ['--interface', 'if!' + self.interface]
            if method == 'POST':
                args += ['-X', 'POST', '-H', 'Content-Type: application/json',
                         '--data', json.dumps(body) if body is not None else '']
            proc = subprocess.run(args, input=config.encode(), capture_output=True, timeout=self.timeout + 5)
            headers, raw = split_response(proc.stdout)
            if proc.returncode == 52 and allow_empty and not raw:
                return {'status': None, 'data': None, 'empty_reply': True,
                        'warning': 'Switch closed without acknowledging. Readback is required.'}
            if proc.returncode and not (stream and proc.returncode == 28 and raw):
                raise SwitchError(f'Switch transport failed (curl {proc.returncode}); request was not retried')
            if not headers:
                raise SwitchError('No HTTP response from switch')
            match = re.match(rb'HTTP/1\.[01] (\d+)', headers[-1])
            status = int(match[1]) if match else 0
            if raw.lstrip().startswith((b'{',b'<')) and b'login.html' in raw[:500] and (b'window.location' in raw[:500] or re.search(rb'"redirect"\s*:',raw[:500])):
                self.cookie = None
                raise SwitchError('Switch session expired; reconnect')
            if not 200 <= status < 300:
                raise SwitchError(f'Switch HTTP {status}: ' + raw[:200].decode(errors='replace'))
            result = {'status': status, 'empty_reply': False}
            if binary:
                result['bytes'] = raw
            elif stream or raw.lstrip().startswith((b'data:', b'event:')):
                events = []
                for event in re.split(rb'\r?\n\r?\n', raw):
                    payload = b'\n'.join(line[5:].lstrip() for line in event.splitlines() if line.startswith(b'data:'))
                    if payload:
                        try: events.append(json.loads(payload))
                        except ValueError: events.append({'text': payload.decode(errors='replace')})
                result['data'] = events
                result['stream_complete'] = proc.returncode == 0
            elif not raw.strip():
                result['data'] = None
            else:
                try: result['data'] = json.JSONDecoder().raw_decode(raw.decode().lstrip())[0]
                except (ValueError, UnicodeError): result['data'] = raw.decode(errors='replace')
            if not authenticate:
                result['_headers'] = headers
            return result
