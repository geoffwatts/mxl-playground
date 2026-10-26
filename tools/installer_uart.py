"""Bounded UART RPC agent. No network access; only the selected UART is opened."""
import argparse
import json
import re
import select
import sys
from inspect_bootstrap import SerialShell, BOOT_SIZE

PATCH_COMMAND = 'flash mod flash_mxl 0x264 ffcc0033 0c000000 04000000 186f0070 4a160100 ff5200ad 00000000 00000000 00000000 00000000'
WSP_AREAS = {1:(0xa000,0x2d6000),3:(0x30d000,0x2d6000)}


def allowed(command, write=False, slot=None):
    if command in ('kernel version','flash_map list','net iface show 1','chiptest firmware_ver',
                   'chiptest mem_rd 0xd0e3d424 1'):
        return True
    if command == PATCH_COMMAND:
        return write and slot is None
    match = re.fullmatch(r'flash read flash_mxl (0x[0-9a-f]+) -d 0x100',command)
    if match:
        offset = int(match[1],16)
        return offset % 256 == 0 and offset+256 <= 0x610000
    # WSP erase/program permissions are scoped to ONE explicit slot. Never boot,
    # GPHY, configuration, partition tables or arbitrary memory write commands.
    if write and slot in WSP_AREAS:
        start,size = WSP_AREAS[slot]
        match = re.fullmatch(r'flash erase flash_mxl (0x[0-9a-f]+) 0x1000',command)
        if match:
            at=int(match[1],16)
            return at%4096==0 and start<=at and at+4096<=start+size
        match = re.fullmatch(r'flash write flash_mxl (0x[0-9a-f]+)((?: [0-9a-f]{8}){1,32})',command)
        if match:
            at=int(match[1],16);count=len(match[2].split())*4
            return at%4==0 and start<=at and at+count<=start+size and at//4096==(at+count-1)//4096
    return False


def emit(value):
    print(json.dumps(value),flush=True)


def agent():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--write',action='store_true')
    parser.add_argument('--slot',type=int,choices=(1,3))
    args=parser.parse_args()
    # os.read on stdin avoids TextIO buffering hiding a second queued RPC.
    import os
    pending=bytearray()
    with SerialShell(args.port,timeout=20) as shell:
        emit({'ready':True})
        while True:
            ready=select.select([sys.stdin.fileno(),shell.fd],[],[],.1)[0]
            if shell.fd in ready:
                data=os.read(shell.fd,65536)
                if not data:raise RuntimeError('UART disconnected')
                emit({'uart':data.decode('utf-8','replace')})
            if sys.stdin.fileno() in ready:
                chunk=os.read(sys.stdin.fileno(),4096)
                if not chunk:return
                pending.extend(chunk)
                if len(pending)>8192:raise ValueError('Oversized RPC request')
                while b'\n' in pending:
                    line,_,pending=pending.partition(b'\n')
                    request=json.loads(line)
                    command=request['command']
                    if not allowed(command,args.write,args.slot):
                        emit({'error':'Command outside installer allowlist'})
                        return
                    try:
                        response=shell.exchange(command)
                        emit({'response':response})
                    except Exception as error:
                        emit({'error':type(error).__name__+': '+str(error)})
                        return


if __name__=='__main__':
    agent()
