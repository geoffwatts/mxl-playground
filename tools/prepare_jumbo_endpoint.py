#!/usr/bin/env python3
"""Prepare an offline ARC assembly plan for a bounded /jumbo.json handler.

GET reads the vendor's global GSW_CFG. POST accepts exactly two little-endian
bytes (1518..10000), preserves every other config field, sets and reads back.
No register addresses or shell commands come from the HTTP request.
"""
import json
import re
from pathlib import Path
import struct

from build_dma_trace_candidate import limm,mov,jump

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/native-ui/jumbo'
BASE=0x402c0000
HANDLER=BASE+0x100
ROUTE=BASE+0x900
FMT=BASE+0x800
ERRORS={'bad':BASE+0xa00,'method':BASE+0xb00,'get':BASE+0xc00,'set':BASE+0xd00}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    table={k:bytes.fromhex(v) for k,v in json.loads((ROOT/'tools/native_arc_opcodes.json').read_text()).items()}
    plan=[];labels={};fixups=[];pc=HANDLER
    def emit(raw,source='template'):
        nonlocal pc
        plan.append({'address':pc,'source':source,'hex':raw.hex()});pc+=len(raw)
    def op(source):
        key=re.sub(r'\s+', '', source)
        if key not in table:raise ValueError('Unvalidated instruction '+source)
        emit(table[key],source)
    def constant(reg,value):emit(mov(reg,value),f'mov_s r{reg},{hex(value)}')
    def call(value):emit(bytes.fromhex('2220800f')+limm(value),'jl '+hex(value))
    def label(name):labels[name]=pc
    def goto(name):fixups.append((len(plan),name));emit(jump(0),'j '+name)
    def fail_if(inverse,target):
        # Inverse condition skips a full absolute jump. Every short branch is
        # ten bytes forward, so no range-dependent instruction sizing exists.
        emit(b'\0\0',inverse+' '+hex(pc+10));goto(target)
    def cfg(offset):
        op('mov_s r0,r14');op(f'ld_s r0,[r0,{hex(offset)}]')
        # r2 matches the vendor CLI's loaded function pointer at its call site.
        op('mov_s r2,r0')
        constant(0,0x400fa010);op('mov_s r1,sp')
        op('jl_s [r2]')
    # Registration entry replaces exactly the original enter + long mov.
    pc=BASE
    op('enter_s {r13-r14,blink}');op('mov_s r13,r0')
    constant(0,0x400de5c0);op('mov_s r14,r0')
    constant(2,HANDLER);constant(1,ROUTE);op('mov_s r3,0x0');op('mov_s r0,r13')
    op('jl_s [r14]');op('mov_s r0,r13')
    emit(jump(0x4001650c),'j original registration continuation')
    wrapper_end=pc
    pc=HANDLER
    op('enter_s {r13-r17,blink}');op('sub_s sp,0x20');op('mov_s r13,r0')
    call(0x400db838);op('mov_s r17,r0');op('ld_s r0,[r0,0x0]')
    constant(1,0x40223988);call(0x4003508c);op('mov_s r16,r0')
    op('mov_s r0,sp');op('mov_s r1,0x0');op('mov_s r2,0x14');call(0x400351b0)
    call(0x4008eaac);op('mov_s r14,r0');cfg(0x2c)
    op('cmp_s r0,0x0');fail_if('beq_s','get_error')
    op('mov_s r0,r16');op('cmp_s r0,0x0');fail_if('bne_s','send_ok')
    op('mov_s r0,r17');op('ld_s r0,[r0,0x0]');constant(1,0x401006e0);call(0x4003508c)
    op('cmp_s r0,0x0');fail_if('beq_s','method_error')
    op('mov_s r0,r17');op('ld_s r0,[r0,0x4c]');op('cmp_s r0,0x2');fail_if('beq_s','bad_error')
    op('mov_s r0,r17');op('ld_s r0,[r0,0x50]');op('cmp_s r0,0x0');fail_if('beq_s','bad_error')
    op('mov_s r0,r13');op('add_s r1,sp,0x14');op('mov_s r2,0x2');call(0x400dc048)
    op('cmp_s r0,0x2');fail_if('beq_s','bad_error')
    op('mov_s r0,sp');op('add_s r0,r0,0x14');op('ldh_s r0,[r0,0x0]');op('mov_s r17,r0')
    constant(0,1518);op('mov_s r1,r17');op('cmp_s r1,r0');fail_if('bhs_s','bad_error')
    constant(0,10000);op('mov_s r1,r17');op('cmp_s r1,r0');fail_if('bls_s','bad_error')
    op('mov_s r0,sp');op('add_s r0,r0,0x8');op('mov_s r1,r17');op('sth_s r1,[r0,0x0]')
    cfg(0x30);op('cmp_s r0,0x0');fail_if('beq_s','set_error')
    cfg(0x2c);op('cmp_s r0,0x0');fail_if('beq_s','get_error')
    label('send_ok');op('mov_s r0,sp');op('add_s r0,r0,0x8');op('ldh_s r2,[r0,0x0]')
    op('mov_s r0,r13');constant(1,FMT);call(0x400dc3c8);op('mov_s r0,0xc8');goto('return')
    for name,status in [('bad',400),('method',405),('get',503),('set',503)]:
        label(name+'_error');op('mov_s r0,r13');constant(1,ERRORS[name]);call(0x400dc3c8);constant(0,status);goto('return')
    label('return');op('add_s sp,0x20');op('leave_s {r13-r17,blink,pcl}')
    for index,name in fixups:plan[index]['hex']=jump(labels[name]).hex()
    if wrapper_end>HANDLER or pc>FMT:raise ValueError('Native code overlaps reserved data')
    # Every instruction (including templates) is decoded later. Short branch
    # bytes must be obtained from Ghidra at their actual addresses first.
    assembly=[f"{hex(x['address'])}|{x['source']}" for x in plan if x['hex']=='0000']
    (OUT/'branches.asm').write_text('\n'.join(assembly)+'\n')
    data={ROUTE:b'/jumbo.json\0',FMT:b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n{"api_version":1,"max_frame_length":%u,"scope":"global","persistent":false}',}
    for name,status,message in [('bad',400,'Expected a two-byte length from 1518 to 10000'),('method',405,'Only GET and POST are supported'),('get',503,'Switch configuration read failed'),('set',503,'Switch configuration write failed')]:
        data[ERRORS[name]]=f'HTTP/1.1 {status} Error\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{{"error":"{message}"}}'.encode()
    data={address:value if value.endswith(b'\0') else value+b'\0' for address,value in data.items()}
    for address,value in data.items():
        if len(value)>=256:raise ValueError('String exceeds its fixed slot')
    (OUT/'assembly-plan.json').write_text(json.dumps({'plan':plan,'labels':labels,'data':{hex(k):v.hex() for k,v in data.items()},'wrapper_end':hex(wrapper_end),'handler_end':hex(pc)},indent=2)+'\n')
    print('Prepared registration wrapper and',hex(pc-HANDLER),'byte handler; pending branch assembly and instruction validation')


if __name__=='__main__':main()
