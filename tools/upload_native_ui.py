#!/usr/bin/env python3
"""Install one exact validated native-UI update using the OEM 41,000-byte protocol.

Writes the switch's inactive update slots and lets its updater reboot it.
No retries, bootloader writes, partition migration, or arbitrary upload URLs.
The supplied password environment variable is read only into process memory.
"""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import struct
import time

from native_layout import inspect
from switch_transport import SwitchTransport, SwitchError


class ChunkClient:
    """One sequential HTTP stream; a failed POST is never replayed.

    Avoid starting curl for every 41 KB chunk: on a slow Wi-Fi path that
    overhead can consume the factory updater's short inter-chunk deadline.
    HTTPConnection reconnects after a server-requested close, but does not
    retry a request that failed while sending or receiving.
    """
    def __init__(self, address, cookie):
        self.connection = http.client.HTTPConnection(address, timeout=90)
        self.cookie = cookie

    def close(self):
        self.connection.close()

    def post(self, payload, timeout):
        connection = self.connection
        connection.timeout = timeout
        if connection.sock is not None:
            connection.sock.settimeout(timeout)
        started = time.monotonic()
        try:
            connection.request('POST', '/firmware/upgrade', body=payload,
                               headers={'Cookie': self.cookie,
                                        'Content-Type': 'application/octet-stream'})
            response = connection.getresponse()
            body = response.read(16385)
            if len(body) > 16384:
                raise ValueError('Updater response exceeds 16 KB')
            return {'http_status': response.status,
                    'response': body.decode(errors='replace'),
                    'elapsed_seconds': time.monotonic() - started,
                    'transport_error': None}
        except (OSError, http.client.HTTPException, ValueError) as error:
            # Do not include connection headers/cookies in diagnostic output.
            self.close()
            return {'http_status': None, 'response': '',
                    'elapsed_seconds': time.monotonic() - started,
                    'transport_error': type(error).__name__}


def validate_target(status,ports):
    if (status.get('fw_ver'),status.get('hw_ver'),status.get('des'))!=('2.0.0.4','A0','SKS3200-8E2X'):
        raise ValueError('Only the tested GoodTop V2 A0 / SKS3200-8E2X software profile is admitted')
    if ports.get('PortNum') not in (10,'10') or ports.get('PortMode')!='PORT_MODE_8_PLUS_2':
        raise ValueError('Unexpected physical port count')



def expected_ui_digest(image):
    """Read the fixed audited ARC pointer/length operands, not a sidecar claim."""
    wsp = image[20:20+0x2d6000]
    def immediate(offset):
        high,low = struct.unpack_from('<HH',wsp,offset)
        return (high << 16) | low
    size = immediate(0x15f72)
    if (not 1 <= size <= 0x56000 or immediate(0x15f78) != 0x4026a000
            or immediate(0x1600e) != size or immediate(0x16014) != 0x4026a000):
        raise ValueError('Expected matching standalone setup/login asset operands')
    html = wsp[0x26a000:0x26a000+size]
    if b'<meta name="mxl-transport" content="native">' not in html:
        raise ValueError('Expected a native standalone UI asset')
    return hashlib.sha256(html).hexdigest()


def verify_served_ui(transport, expected, timeout=180, interval=3):
    """Retry anonymous reads only. Asset availability does not prove boot/traffic."""
    deadline = time.monotonic() + timeout
    attempts = 0
    observed = None
    last_error = None
    while time.monotonic() < deadline:
        attempts += 1
        try:
            result = transport.request('/login.html',binary=True,authenticate=False)
            observed = hashlib.sha256(result['bytes']).hexdigest()
            if observed == expected:
                return {'matched':True,'attempts':attempts,'ui_sha256':observed,
                        'uart_boot_verified':False,'forwarding_verified':False}
            last_error = 'Served UI differs from the selected update'
        except (SwitchError, subprocess.TimeoutExpired) as error:
            last_error = str(error)
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(interval,remaining))
    return {'matched':False,'attempts':attempts,'expected_ui_sha256':expected,
            'last_observed_ui_sha256':observed,'last_error':last_error,
            'uart_boot_verified':False,'forwarding_verified':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image',type=Path,required=True)
    p.add_argument('--expected-sha256',required=True)
    p.add_argument('--address',required=True,help='Explicit IPv4 management address')
    p.add_argument('--username',default='admin')
    p.add_argument('--password-env',default='MXL_UI_PASSWORD')
    p.add_argument('--report',type=Path,default=Path('artifacts/native-ui/upload-result.json'))
    p.add_argument('--verify-ui',action='store_true',help='After upload, poll anonymous login asset for the image hash; UART boot/forwarding checks remain separate')
    p.add_argument('--verify-timeout',type=float,default=180,help='Post-upload HTTP read polling limit in seconds (1..600)')
    a=p.parse_args()
    if not 1 <= a.verify_timeout <= 600:raise ValueError('Verification timeout must be 1..600 seconds')
    image=a.image.read_bytes();digest=hashlib.sha256(image).hexdigest()
    if digest!=a.expected_sha256:
        raise ValueError('Image differs from explicitly selected hash')
    framing=inspect(a.image)
    if [c['size'] for c in framing['components']]!=[0x2d6000,0x29f40]:
        raise ValueError('Expected the audited V2 WSP/GPHY component sizes')
    ui_digest=expected_ui_digest(image) if a.verify_ui else None
    password=os.environ.get(a.password_env)
    if password is None:
        raise ValueError('Password environment variable is required')
    transport=SwitchTransport(a.address,timeout=12)
    status=transport.login(a.username,password);del password
    validate_target(status,transport.request('/port_setting_load.json')['data'])
    report={'image_sha256':digest,'image_bytes':len(image),'framing':framing,
            'target':transport.address,'chunk_bytes':41000,'chunks':[],
            'status':'IN PROGRESS; DO NOT RESTART AN INCOMPLETE UPLOAD'}
    a.report.parent.mkdir(parents=True,exist_ok=True)
    def save():a.report.write_text(json.dumps(report,indent=2)+'\n')
    save()
    client = ChunkClient(transport.address, transport.cookie)
    report['upload_transport'] = 'stdlib HTTP/1.1; sequential; no retries'
    try:
        for offset in range(0,len(image),41000):
            part=image[offset:offset+41000]
            # Match the current OEM page: sequential raw Blob POSTs, no
            # multipart wrapper and no automatic retries after a failed chunk.
            entry=client.post(part,90 if offset==0 else 20)
            code=entry['http_status'];body=entry['response'].encode()
            entry.update(offset=offset,bytes=len(part))
            report['chunks'].append(entry);save()
            if entry['transport_error'] or code!=200 or b'Failure' in body or b'400' in body:
                report['status']='STOPPED AFTER FAILED CHUNK; NO RETRY';save()
                raise RuntimeError('Update stopped at offset '+hex(offset)+'; inspect the UART and saved report before taking further action')
            print(f'Uploaded {offset+len(part)}/{len(image)} bytes',flush=True)
            if b'Verification: Success. System is rebooting.' in body:
                if offset+len(part)!=len(image):
                    raise RuntimeError('Unexpected success before end of image')
                report['status']='UPDATER REPORTED SUCCESS; BOOT NOT YET VERIFIED';save()
                print(report['status'],flush=True)
                if a.verify_ui:
                    # The server schedules reset one second after the final response.
                    # Do not immediately mistake the still-running old app for a boot.
                    time.sleep(8)
                    report['http_ui_verification']=verify_served_ui(transport,ui_digest,a.verify_timeout)
                    report['status']=('UPDATER SUCCESS; SERVED UI HASH VERIFIED; UART BOOT/FORWARDING NOT VERIFIED'
                        if report['http_ui_verification']['matched'] else
                        'UPDATER SUCCESS; HTTP UI VERIFICATION FAILED; NO UPDATE RETRY')
                    save();print(report['status'],flush=True)
                    if not report['http_ui_verification']['matched']:raise RuntimeError(report['status'])
                return
    finally:
        client.close()
    report['status']='ALL CHUNKS SENT WITHOUT EXPECTED FINAL SUCCESS; BOOT NOT VERIFIED';save()
    raise RuntimeError(report['status'])


if __name__=='__main__':
    main()
