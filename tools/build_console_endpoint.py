#!/usr/bin/env python3
"""Compile the exact-build shared UART/browser console. Offline only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from build_management_probe import FLAGS,disassembly_rows
from build_dma_trace_candidate import jump,limm
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--compiler-image',default='mxl-arc-build:bookworm')
    a=p.parse_args();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    script=['set -eu']
    for name in ['console_ring','console_native']:
        script+=[' '.join(['arc-linux-gnu-gcc-12',*FLAGS,'-fstack-usage','-c','/src/'+name+'.c','-o','/out/'+name+'.o'])]
    script += ['arc-linux-gnu-ld --gc-sections -T /src/console_native.ld /out/console_native.o /out/console_ring.o -o /out/console.elf',
        'arc-linux-gnu-nm -u /out/console.elf > /out/undefined.txt',
        'arc-linux-gnu-nm -n /out/console.elf > /out/symbols.txt',
        'arc-linux-gnu-objdump -d --insn-width=16 /out/console.elf > /out/console.dis',
        'arc-linux-gnu-objcopy -O binary /out/console.elf /out/console.bin']
    subprocess.run(['docker','run','--rm','--platform','linux/amd64','--network','none','--read-only',
        '--tmpfs','/tmp:rw,size=32m','--user',str(os.getuid())+':'+str(os.getgid()),
        '-v',str(ROOT/'firmware')+':/src:ro','-v',str(out)+':/out',a.compiler_image,'sh','-c','\n'.join(script)],check=True,timeout=90)
    if (out/'undefined.txt').read_text().strip():raise ValueError('Unresolved console symbols')
    symbols={p[2]:int(p[0],16) for line in (out/'symbols.txt').read_text().splitlines() if len(p:=line.split())==3}
    raw=(out/'console.bin').read_bytes();entry=symbols['mxl_console_register']
    wrapper=bytes.fromhex('a1402220800f')+limm(entry)+bytes.fromhex('a140')+jump(0x4001650c)
    blob=bytearray(b'\xff'*0x4000);blob[:len(wrapper)]=wrapper;blob[0x20:0x20+len(raw)]=raw
    (out/'endpoint.bin').write_bytes(blob)
    rows=[(0x402b0000,wrapper[:2],'mov_s r0,r13'),(0x402b0002,wrapper[2:10],'jl console registration'),
          (0x402b000a,wrapper[10:12],'mov_s r0,r13'),(0x402b000c,wrapper[12:20],'j native continuation')]
    rows+=disassembly_rows((out/'console.dis').read_text(),raw,base=0x402b0020)
    (out/'instructions.tsv').write_text('\n'.join(f'{hex(at)}|{b.hex()}|{s}' for at,b,s in rows)+'\n')
    report={'sha256':hashlib.sha256(blob).hexdigest(),'compiled_bytes':len(raw),'decoded_instructions':len(rows),
        'storage':'One shared UART transport tee/input ring; allocated at registration; no new shell/thread',
        'independent_decode_required':True}
    (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
