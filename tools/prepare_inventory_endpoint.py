#!/usr/bin/env python3
"""Exact-build native inventory GET/POST plan, offline only.

Only the vendor's location/contact descriptors and NVS keys can be accessed.
POST is exactly 512 bytes, two bounded NUL-terminated 256-byte strings.
Uses vendor string-copy/get and settings-save routines, not direct NVS writes.
"""
import json
from pathlib import Path
from build_dma_trace_candidate import limm,mov,jump
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/inventory/endpoint'
BASE=0x402c0000
ENTRY=BASE+0x2000
HANDLER=BASE+0x2100
HEADER=BASE+0x2900
BAD=BASE+0x2a00
METHOD=BASE+0x2b00
ERROR=BASE+0x2c00
ROUTE=BASE+0x2d00


def main():
    OUT.mkdir(parents=True,exist_ok=True);table=json.loads((ROOT/'tools/native_arc_opcodes.json').read_text())
    plan=[];labels={};fixups=[];pc=ENTRY
    def emit(raw,source):
        nonlocal pc
        plan.append({'address':pc,'source':source,'hex':raw.hex()});pc+=len(raw)
    def op(source):emit(bytes.fromhex(table[''.join(source.split())]),source)
    def constant(reg,value):emit(mov(reg,value),f'mov r{reg},{hex(value)}')
    def call(address):emit(bytes.fromhex('2220800f')+limm(address),'jl '+hex(address))
    def label(name):labels[name]=pc
    def goto(name):fixups.append((len(plan),name));emit(jump(0),'j '+name)
    def when(inverse,target):emit(b'\0\0',inverse+' '+hex(pc+10));goto(target)
    def pointer(offset):
        op('mov_s r0,sp')
        if offset:constant(1,offset);op('add r0,r0,r1')
    def get_field(offset,descriptor):
        pointer(offset);op('mov_s r1,r0');constant(0,descriptor);constant(2,256);call(0x4000b3b0)
    constant(2,HANDLER);constant(1,ROUTE);op('mov_s r3,0x0');op('mov_s r0,r13');op('jl_s [r14]');op('mov_s r0,r13');emit(jump(0x4001650c),'j original continuation')
    entry_end=pc;pc=HANDLER
    op('enter_s {r13-r17,blink}');op('mov_s r13,r0')
    for _ in range(4):op('sub_s sp,0x7c')
    op('sub_s sp,0x20');op('mov_s r0,sp');constant(1,0);constant(2,528);call(0x400351b0)
    op('mov_s r0,r13');call(0x400db838);op('mov_s r17,r0');op('ld_s r0,[r0,0x0]');constant(1,0x40223988);call(0x4003508c);op('cmp_s r0,0x0');when('bne_s','read')
    op('mov_s r0,r17');op('ld_s r0,[r0,0x0]');constant(1,0x401006e0);call(0x4003508c);op('cmp_s r0,0x0');when('beq_s','method')
    op('mov_s r0,r17');op('ld_s r0,[r0,0x4c]');constant(1,512);op('cmp_s r1,r0');when('beq_s','bad')
    op('mov_s r0,r17');op('ld_s r0,[r0,0x50]');op('cmp_s r0,0x0');when('beq_s','bad')
    pointer(8);op('mov_s r1,r0');op('mov_s r0,r13');constant(2,512);call(0x400dc048);constant(1,512);op('cmp_s r1,r0');when('beq_s','bad')
    for offset in (263,519):
        pointer(offset);op('ldb_s r0,[r0,0x0]');op('cmp_s r0,0x0');when('beq_s','bad')
    for offset,descriptor,key in [(8,0x20f608df,0x400fdd90),(264,0x20f608d3,0x400fdd34)]:
        pointer(offset);op('mov_s r1,r0');constant(0,descriptor);op('mov_s r2,0x0');op('mov_s r3,0x0');call(0x4000b224);op('cmp_s r0,0x0');when('beq_s','error')
        # Canonicalise through the vendor getter before saving: bytes following
        # an early input NUL must never leak into the NVS padding.
        pointer(offset);constant(1,0);constant(2,256);call(0x400351b0);get_field(offset,descriptor)
        pointer(offset);op('mov_s r1,r0');constant(0,key);constant(2,256);call(0x400331d4);op('cmp_s r0,0x0');when('beq_s','error')
    label('read');get_field(8,0x20f608df);get_field(264,0x20f608d3)
    pointer(0);constant(1,0x564e494d);op('st_s r1,[r0,0x0]');constant(1,0x01000201);op('st_s r1,[r0,0x4]')
    op('mov_s r0,r13');constant(1,HEADER);call(0x400dc3c8);op('mov_s r0,r13');op('mov_s r1,sp');constant(2,520);call(0x400dc1f4);op('mov_s r0,0xc8');goto('return')
    for name,address,status in [('bad',BAD,400),('method',METHOD,405),('error',ERROR,503)]:
        label(name);op('mov_s r0,r13');constant(1,address);call(0x400dc3c8);constant(0,status);goto('return')
    label('return');op('add_s sp,0x20')
    for _ in range(4):op('add_s sp,0x7c')
    op('leave_s {r13-r17,blink,pcl}')
    for index,name in fixups:plan[index]['hex']=jump(labels[name]).hex()
    if entry_end>HANDLER or pc>HEADER:raise ValueError('Inventory code exceeds bounded region')
    data={HEADER:b'HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\nContent-Length: 520\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n\0',ROUTE:b'/inventory.json\0'}
    for address,status,message in [(BAD,400,'Expected two terminated 256-byte fields'),(METHOD,405,'Only GET and POST are supported'),(ERROR,503,'Inventory may be partially applied; refresh before retrying')]:
        data[address]=f'HTTP/1.1 {status} Error\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{{"error":"{message}"}}\0'.encode()
    (OUT/'assembly-plan.json').write_text(json.dumps({'plan':plan,'labels':labels,'data':{hex(k):v.hex() for k,v in data.items()},'entry_end':hex(entry_end),'handler_end':hex(pc),'stack_bytes':528},indent=2)+'\n')
    (OUT/'branches.asm').write_text('\n'.join(f"{hex(x['address'])}|{x['source']}" for x in plan if x['hex']=='0000')+'\n')
    print('Prepared',hex(pc-HANDLER),'byte inventory handler')

if __name__=='__main__':main()
