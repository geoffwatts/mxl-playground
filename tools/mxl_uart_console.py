#!/usr/bin/env python3
"""Run explicit UART commands locally (also suitable for python -c over SSH).

The remote host is used only as a serial transport. Logs stay in /tmp.
"""
import argparse
import os
import select
import termios
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--wait', type=float, default=3)
    p.add_argument('--require-verified', action='store_true',
                   help='Stop a batch if a flash mod command lacks Verified.')
    p.add_argument('commands', nargs='+')
    a = p.parse_args()
    fd = os.open('/dev/ttyUSB0', os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    original = termios.tcgetattr(fd)
    attrs = termios.tcgetattr(fd)
    attrs[:4] = [0, 0, termios.CS8 | termios.CREAD | termios.CLOCAL, 0]
    attrs[4:6] = [termios.B115200, termios.B115200]
    attrs[6][termios.VMIN] = attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    try:
        with open('/tmp/mxl-uart-session.log', 'ab', buffering=0) as log:
            for cmd in a.commands:
                if '\r' in cmd or '\n' in cmd:
                    raise ValueError('One explicit command per argument')
                print('\n>>> ' + cmd, flush=True)
                os.write(fd, cmd.encode('ascii') + b'\r')
                end = time.monotonic() + a.wait
                response = bytearray()
                while time.monotonic() < end:
                    if select.select([fd], [], [], .1)[0]:
                        data = os.read(fd, 65536)
                        if data:
                            response.extend(data)
                            log.write(data)
                            print(data.decode('utf-8', 'replace'), end='', flush=True)
                if a.require_verified and cmd.startswith('flash mod ') and b'Verified.' not in response:
                    raise RuntimeError('Flash operation did not verify; remaining commands cancelled')
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, original)
        os.close(fd)


if __name__ == '__main__':
    main()
