#!/usr/bin/env python3
"""Exact-build buffered execution trace for the early DMA cleanup experiment.

Offline only. No new RAM sentinel. Uses the vendor's existing logger contract.
Opcode templates and register moves are round-trip decoded in dma-trace-evidence.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

BASE_SHA='d84c7985d874d93107d8f6aea0d942c9fabdfa8c1c641d582efaffb180320234'
EXPECTED_SHA='7f463bd821656bbeccbf26552fc753d079a4757cd1b118aed13e02faab7d2f1e'


def limm(value):
    return struct.pack('<HH',value>>16,value&65535)


def mov(reg,value):
    if reg not in (0,1,2):
        raise ValueError('Only decoded low-register immediate templates supported')
    return bytes([0xc3,0x40+reg])+limm(value)


def jump(value):
    return bytes.fromhex('2020800f')+limm(value)


def log_call(package):
    return (mov(0,0x20f64628)+mov(1,0x10c0)+mov(2,package)+
            bytes.fromhex('00db2220800f')+limm(0x70005634))


def build(base):
    if hashlib.sha256(base).hexdigest()!=BASE_SHA:
        raise ValueError('Expected exact prior DMA-wrapper candidate')
    code=(bytes.fromhex('e4c208452846')+log_call(0x400003c0)+
          mov(0,0x70006f18)+mov(1,0x25800040)+bytes.fromhex('20a0')+
          log_call(0x400003c8)+bytes.fromhex('a140c141c4c2')+jump(0x400f170c))
    if len(code)!=90:
        raise ValueError('Unexpected wrapper size')
    blocks=[(0x300,code.ljust(92,b'\0')),
            (0x3c0,struct.pack('<4I',2,0x40000420,2,0x40000450)),
            (0x420,b'DMA cleanup BEFORE restore\0'.ljust(32,b'\0')),
            (0x450,b'DMA cleanup AFTER restore\0'.ljust(32,b'\0')),
            (0x200,jump(0x40000300).ljust(32,b'\0'))]
    out=bytearray(base)
    commands=[]
    for offset,data in blocks:
        start=0xa000+offset
        if offset!=0x200 and any(base[start:start+len(data)]):
            raise ValueError('Trace would overwrite occupied header space')
        out[start:start+len(data)]=data
        for n in range(0,len(data),48):
            part=data[n:n+48]
            words=struct.unpack('<'+'I'*(len(part)//4),part)
            commands.append(f'flash mod flash_mxl {hex(start+n)} '+
                            ' '.join(f'{v:08x}' for v in words))
    out=bytes(out)
    if out[:0xa200]!=base[:0xa200] or out[0xa480:]!=base[0xa480:]:
        raise ValueError('Change escaped bounded unsigned-header padding')
    if hashlib.sha256(out).hexdigest()!=EXPECTED_SHA:
        raise ValueError('Candidate differs from the instruction-validated image')
    return out,code,{
        'status':'OFFLINE INSTRUCTION/P-CODE VALIDATED; SEE SEPARATE RUNTIME RESULT',
        'base_sha256':BASE_SHA,'candidate_sha256':EXPECTED_SHA,'commands':commands,
        'only_changed_region':'active WSP unsigned-header padding a200..a470',
        'signed_bytes_unchanged':True,'backup_bank_unchanged':True,
        'registers':'r13/r14 and blink saved/restored; original r0/r1 restored before tail-call',
        'logger_contract':'driver source 20f64628, flags 10c0, static 8-byte packages; r3=0',
        'RAM_store':'70006f18 <- 25800040',
        'entry_install_last':True,'evidence':'dma-trace-evidence.txt',
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.base.resolve()==a.output.resolve():
        raise ValueError('Output must not overwrite input')
    data,code,report=build(a.base.read_bytes())
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_bytes(data)
    a.output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['candidate_sha256'])


if __name__=='__main__':
    main()
