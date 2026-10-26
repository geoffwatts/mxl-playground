#!/usr/bin/env python3
"""Read-only V2 UART admission check. Never writes flash, RAM, or reboots.

Captures only fixed flash-map/version/boot-area reads. A match is NOT permission
for an unattended first install: the stock-to-custom handoff is still unproven.
The optional SSH host is used exclusively as a serial transport.
"""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import shlex
import struct
import subprocess
import sys
import termios
import time

BOOT_SIZE = 0xa000
BOOT_CODE_SHA = '15da8f9d2a2e477716bbf163e97ae3d902c5aad2ae4d215cd55fabaca1c902b3'
STOCK_RECORD = bytes.fromhex('ad0052ff') + bytes(36)
PATCH_RECORD = bytes.fromhex('3300ccff0000000c0000000470006f180001164aad0052ff') + bytes(16)
V2_MAP = [(0,0,0xa000),(1,0xa000,0x2d6000),(2,0x2e0000,0x2d000),
          (3,0x30d000,0x2d6000),(4,0x5e3000,0x2d000),(5,0x610000,0x8000),
          (6,0x618000,0x10000),(7,0x628000,0x40000),(8,0x668000,0x80000),
          (9,0x6e8000,0x80000)]
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
PROMPT = re.compile(r'(?:^|[\r\n])uart:~\$\s*$')


def clean(text):
    return ANSI.sub('', text).replace('\r', '')


def parse_hex(text, start, size):
    """Require complete, ordered, non-duplicated bytes; never infer missing data."""
    result = bytearray()
    for line in clean(text).splitlines():
        match = re.match(r'^([0-9a-fA-F]{8}):\s*(.*?)\s*\|', line)
        if not match:
            continue
        tokens = match[2].split()
        if (int(match[1], 16) != start + len(result) or not tokens
                or len(tokens) > 16 or any(not re.fullmatch(r'[0-9a-fA-F]{2}', x) for x in tokens)):
            raise ValueError('Invalid, duplicated or out-of-order UART hex row')
        result.extend(bytes.fromhex(' '.join(tokens)))
    if len(result) != size:
        raise ValueError('UART flash read is incomplete or exceeds the requested range')
    return bytes(result)


def parse_map(text):
    rows = []
    for line in clean(text).splitlines():
        match = re.fullmatch(r'\s*(\d+)\s+(\d+)\s+(\w+)\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s*', line)
        if match:
            if match[2] != '0' or match[3] != 'flash_mxl':
                raise ValueError('Unexpected flash device')
            rows.append((int(match[1]), int(match[4],16), int(match[5],16)))
    if rows != V2_MAP:
        raise ValueError('UART partition map is not the exact audited V2 map')
    return rows


def boot_map(data):
    offset = 0
    maps = []
    while offset + 8 <= 0x400:
        tag, complement, size = struct.unpack_from('>HHI', data, offset)
        end = offset + 8 + size
        if tag + complement != 0xffff or end > 0x400:
            raise ValueError('Malformed boot configuration tags')
        if tag == 0xa700:
            if size != 120:
                raise ValueError('Unexpected partition tag length')
            maps.append([struct.unpack_from('>III', data, x) for x in range(offset+8,end,12)])
        if tag == 0xad00 and size == 0:
            if maps != [V2_MAP]:
                raise ValueError('Flash boot configuration is not the audited V2 map')
            return
        offset = end
    raise ValueError('Missing boot configuration terminator')


def record_state(data):
    record = data[0x264:0x28c]
    if record == STOCK_RECORD:
        return 'stock'
    if record == PATCH_RECORD:
        return 'experimental-skip'
    raise ValueError('Unknown boot record; no change admitted')


def validate(backup, live, map_text):
    if len(backup) != 0x800000 or len(live) != BOOT_SIZE:
        raise ValueError('Require own full 8 MiB backup and complete live 40 KiB boot area')
    parse_map(map_text)
    for name, data in [('backup', backup), ('live', live)]:
        if hashlib.sha256(data[0x400:0x7000]).hexdigest() != BOOT_CODE_SHA:
            raise ValueError(name + ' bootloader executable differs from the audited image')
        boot_map(data)
    before, current = record_state(backup), record_state(live)
    # A stock backup can be used to inspect this same already-bootstrapped unit.
    # Every other boot-area byte must still match, including board/key records.
    normalized_backup = backup[:0x264] + STOCK_RECORD + backup[0x28c:BOOT_SIZE]
    normalized_live = live[:0x264] + STOCK_RECORD + live[0x28c:]
    if normalized_backup != normalized_live:
        raise ValueError('Live boot area differs from own backup outside the recognized record')
    return {'format':'mxl-bootstrap-preflight/v1', 'read_only':True,
            'backup_sha256':hashlib.sha256(backup).hexdigest(),
            'live_boot_sha256':hashlib.sha256(live).hexdigest(),
            'boot_code_sha256':BOOT_CODE_SHA, 'backup_record':before,
            'live_record':current, 'exact_v2_map':True,
            'boot_area_matches_backup_outside_record':True,
            'installation_ready':False,
            'next_gate':'Coordinated first WSP installation and recovery remain unvalidated; no write or reboot performed.'}


class SerialShell:
    def __init__(self, port, timeout=8):
        self.port, self.timeout = port, timeout
        self.fd = None

    def __enter__(self):
        self.fd = os.open(self.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.original = termios.tcgetattr(self.fd)
            attrs = termios.tcgetattr(self.fd)
            attrs[:4] = [0,0,termios.CS8 | termios.CREAD | termios.CLOCAL,0]
            attrs[4:6] = [termios.B115200,termios.B115200]
            attrs[6][termios.VMIN] = attrs[6][termios.VTIME] = 0
            termios.tcsetattr(self.fd,termios.TCSANOW,attrs)
            termios.tcflush(self.fd,termios.TCIFLUSH)
            return self
        except BaseException:
            os.close(self.fd)
            raise

    def command(self, command):
        if command not in ('kernel version','flash_map list') and not re.fullmatch(
                r'flash read flash_mxl 0x[0-9a-f]+ -d 0x100',command):
            raise ValueError('Only fixed read-only preflight commands are allowed')
        if command.startswith('flash read'):
            address = int(command.split()[3],16)
            if address % 0x100 or address + 0x100 > BOOT_SIZE:
                raise ValueError('Read outside boot area')
        return self.exchange(command)

    def exchange(self, command):
        """Transport primitive; callers must validate commands before using it."""
        # Ctrl-U clears any unfinished input without executing it.
        payload = b'\x15' + command.encode('ascii') + b'\r'
        if os.write(self.fd,payload) != len(payload):
            raise RuntimeError('Partial serial command write; stopped')
        response = bytearray()
        end = time.monotonic() + self.timeout
        while time.monotonic() < end:
            if select.select([self.fd],[],[],.05)[0]:
                part = os.read(self.fd,65536)
                if not part:
                    raise RuntimeError('Serial device disconnected')
                response.extend(part)
                if len(response) > 32768:
                    raise RuntimeError('Serial response exceeded its bound')
                text = response.decode('utf-8','replace')
                if PROMPT.search(clean(text)):
                    return text
        raise TimeoutError('UART prompt timeout; stopped without retry')

    def __exit__(self, *args):
        try:
            termios.tcsetattr(self.fd,termios.TCSANOW,self.original)
        finally:
            os.close(self.fd)


def capture(port):
    with SerialShell(port) as shell:
        version = shell.command('kernel version')
        mapping = shell.command('flash_map list')
        parse_map(mapping)  # stop before a long capture on unsupported layouts
        body = bytearray()
        for address in range(0,BOOT_SIZE,0x100):
            response = shell.command(f'flash read flash_mxl {address:#x} -d 0x100')
            body.extend(parse_hex(response,address,0x100))
        return {'version':clean(version),'map':clean(mapping),
                'boot_base64':base64.b64encode(body).decode('ascii')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--backup',type=Path)
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--ssh',help='Optional SSH destination; used only to open the UART')
    parser.add_argument('--capture',action='store_true',help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.capture:
        if args.ssh or args.backup or args.output_dir:
            parser.error('Capture transport accepts only --port')
        print(json.dumps(capture(args.port)))
        return
    if args.backup is None or args.output_dir is None:
        parser.error('--backup and --output-dir are required')
    backup = args.backup.read_bytes()
    # Reject unsupported local backups before touching any serial device.
    validate(backup,backup[:BOOT_SIZE], '\n'.join(f'{i} 0 flash_mxl {o:#x} {s:#x}' for i,o,s in V2_MAP))
    args.output_dir.mkdir(mode=0o700,parents=True,exist_ok=False)
    if args.ssh:
        if args.ssh.startswith('-') or not re.fullmatch(r'[\w.@:-]+',args.ssh):
            raise ValueError('Invalid SSH destination')
        remote = shlex.join(['python3','-u','-c',Path(__file__).read_text(),'--capture','--port',args.port])
        result = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5',args.ssh,remote],
                                capture_output=True,timeout=240,check=True)
        captured = json.loads(result.stdout)
    else:
        captured = capture(args.port)
    live = base64.b64decode(captured.pop('boot_base64'),validate=True)
    def save(name, data):
        fd = os.open(args.output_dir/name,os.O_WRONLY | os.O_CREAT | os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as out:
            out.write(data)
    save('live-boot-area.bin',live)
    save('uart-profile.txt',(captured['version']+'\n'+captured['map']).encode())
    try:
        report = validate(backup,live,captured['map'])
    except ValueError as error:
        save('preflight.json',(json.dumps({'read_only':True,'passed':False,'error':str(error)},indent=2)+'\n').encode())
        raise
    report['passed'] = True
    save('preflight.json',(json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
