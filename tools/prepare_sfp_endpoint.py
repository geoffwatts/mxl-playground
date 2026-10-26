#!/usr/bin/env python3
"""Offline, exact-build ARC plan for read-only /sfp.json; no device access.

Only fixed buses I2C_1/I2C_0 and EEPROM addresses 0x50/0x51 are reachable.
Wire format is decoded by sfp.mjs. The I2C write phase only selects offset zero.
1088 bytes of request-local stack avoids shared buffers and data races.
"""
import hashlib
import json
from pathlib import Path
from build_dma_trace_candidate import limm,mov,jump

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/sfp/endpoint'
BASE=0x402c0000
ENTRY=BASE+0x1000
HANDLER=BASE+0x1100
HEADER=BASE+0x1900
METHOD=BASE+0x1a00
ROUTE=BASE+0x1b00
BUS0=BASE+0x1b20
BUS1=BASE+0x1b30
JUMBO_SHA='a2ea068058ce6d5ec8b5c6e062af449b8ba8d489d32b2bad89c8335f73d5cedb'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    table=json.loads((ROOT/'tools/native_arc_opcodes.json').read_text())
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
    def pointer(base,offset=0):
        op('mov_s r0,'+base)
        if offset:constant(1,offset);op('add r0,r0,r1')
    def byte(offset,value):pointer('r14');constant(1,value);op(f'stb_s r1,[r0,{hex(offset)}]')
    def transfer(offset,address,prefix):
        # Two struct i2c_msg records: {buf*,len,flags+padding}, each 12 B.
        # The vendor driver truncates its outstanding read count to uint8_t.
        # 256 wraps to zero and times out. Use 16 independently addressed chunks.
        # sp+1056 was the presence-state scratch; it is now the page cursor.
        loop=prefix+'_chunk_'+str(address);done=loop+'_done'
        label(loop+'_start')
        pointer('sp',1056);constant(1,0);op('st_s r1,[r0,0x0]')
        label(loop)
        pointer('sp',1056);op('ld_s r0,[r0,0x0]');op('mov_s r17,r0')
        pointer('sp',1084);op('mov_s r1,r17');op('stb_s r1,[r0,0x0]')
        pointer('sp',1084);op('mov_s r17,r0');pointer('sp',1060);op('mov_s r1,r17');op('st_s r1,[r0,0x0]');constant(1,1);op('st_s r1,[r0,0x4]');constant(1,0);op('st_s r1,[r0,0x8]')
        pointer('r14',offset);op('mov_s r17,r0')
        pointer('sp',1056);op('ld_s r0,[r0,0x0]');op('mov_s r1,r0');op('mov_s r0,r17');op('add r0,r0,r1');op('mov_s r17,r0')
        pointer('sp',1072);op('mov_s r1,r17');op('st_s r1,[r0,0x0]');constant(1,16);op('st_s r1,[r0,0x4]');constant(1,7);op('st_s r1,[r0,0x8]')
        pointer('sp',1060);op('mov_s r1,r0');op('mov_s r0,r16');op('mov_s r2,0x2');op('mov_s r3,'+hex(address));call(0x4006d428)
        op('cmp_s r0,0x0');when('beq_s',done)
        pointer('sp',1056);op('ld_s r0,[r0,0x0]');constant(1,16);op('add r0,r0,r1');op('mov_s r17,r0')
        pointer('sp',1056);op('mov_s r1,r17');op('st_s r1,[r0,0x0]')
        # The extension's wide cmp r17,r0 decodes in Ghidra but traps on this
        # silicon. Move into the low register bank and use the vendor short form.
        constant(0,256);op('mov_s r1,r17');op('cmp_s r1,r0');when('beq_s',loop)
        constant(0,0)
        label(done)
    def read_result(kind,error):
        op('cmp_s r0,0x0');when('beq_s',error)
        byte(4 if kind=='a0' else 5,1)
    # Existing jumbo registration has already saved r13/r14. Continue its
    # prologue and preserve the context and original continuation contract.
    constant(2,HANDLER);constant(1,ROUTE);op('mov_s r3,0x0');op('mov_s r0,r13');op('jl_s [r14]');op('mov_s r0,r13');emit(jump(0x4001650c),'j original continuation')
    entry_end=pc;pc=HANDLER
    op('enter_s {r13-r17,blink}');op('mov_s r13,r0')
    for _ in range(8):op('sub_s sp,0x7c')
    op('sub_s sp,0x60')
    op('mov_s r0,r13');call(0x400db838);op('ld_s r0,[r0,0x0]');constant(1,0x40223988);call(0x4003508c);op('cmp_s r0,0x0');when('beq_s','method')
    op('mov_s r0,sp');constant(1,0);constant(2,1088);call(0x400351b0)
    op('mov_s r0,sp');constant(1,0x5046534d);op('st_s r1,[r0,0x0]');constant(1,0x020c0201);op('st_s r1,[r0,0x4]')
    for port,cage,bus,record in [(9,1,BUS1,8),(10,0,BUS0,532)]:
        prefix='p'+str(port)
        pointer('sp',record);op('mov_s r14,r0');constant(1,0xff020000|cage<<8|port);op('st_s r1,[r0,0x0]')
        pointer('sp',1056);constant(1,255);op('st_s r1,[r0,0x0]');op('mov_s r1,r0');constant(0,cage);op('mov_s r2,0x0');op('mov_s r3,0x0');op('mov_s r4,0x0');op('mov_s r5,0x0');call(0x400d84c8)
        pointer('sp',1056);op('ld_s r0,[r0,0x0]');op('mov_s r17,r0');op('mov_s r1,r0');pointer('r14');op('stb_s r1,[r0,0x3]');op('mov_s r0,r17')
        op('cmp_s r0,0x0');when('bne_s',prefix+'_absent');op('cmp_s r0,0x1');when('bne_s',prefix+'_present');op('cmp_s r0,0x2');when('bne_s',prefix+'_present');goto(prefix+'_next')
        label(prefix+'_absent');byte(2,0);goto(prefix+'_next')
        label(prefix+'_present');byte(2,1);constant(0,bus);call(0x400df324);op('mov_s r16,r0');op('cmp_s r0,0x0');when('bne_s',prefix+'_no_bus')
        transfer(12,0x50,prefix);read_result('a0',prefix+'_a0_error')
        pointer('r14',12);op('ldb_s r0,[r0,0x0]');constant(1,3);op('cmp_s r1,r0');when('beq_s',prefix+'_next')
        pointer('r14',104);op('ldb_s r0,[r0,0x0]');constant(1,0x44);op('and_s r0,r0,r1');op('cmp_s r0,0x40');when('beq_s',prefix+'_next')
        transfer(268,0x51,prefix);read_result('a2',prefix+'_a2_error');goto(prefix+'_next')
        label(prefix+'_no_bus');constant(0,0xffffffed)
        label(prefix+'_a0_error');op('mov_s r1,r0');pointer('r14');op('sth_s r1,[r0,0x6]');byte(4,2);goto(prefix+'_next')
        label(prefix+'_a2_error');op('mov_s r1,r0');pointer('r14');op('sth_s r1,[r0,0x8]');byte(5,2)
        label(prefix+'_next')
    op('mov_s r0,r13');constant(1,HEADER);call(0x400dc3c8);op('mov_s r0,r13');op('mov_s r1,sp');constant(2,1056);call(0x400dc1f4);op('mov_s r0,0xc8');goto('return')
    label('method');op('mov_s r0,r13');constant(1,METHOD);call(0x400dc3c8);constant(0,405)
    label('return');op('add_s sp,0x60')
    for _ in range(8):op('add_s sp,0x7c')
    op('leave_s {r13-r17,blink,pcl}')
    for index,name in fixups:plan[index]['hex']=jump(labels[name]).hex()
    if entry_end>HANDLER or pc>HEADER:raise ValueError('Code exceeds reserved region')
    data={HEADER:b'HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\nContent-Length: 1056\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n\0',METHOD:b'HTTP/1.1 405 Method Not Allowed\r\nAllow: GET\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{"error":"Only GET is supported"}\0',ROUTE:b'/sfp.json\0',BUS0:b'I2C_0\0',BUS1:b'I2C_1\0'}
    (OUT/'assembly-plan.json').write_text(json.dumps({'plan':plan,'labels':labels,'data':{hex(k):v.hex() for k,v in data.items()},'entry_end':hex(entry_end),'handler_end':hex(pc),'stack_bytes':1088},indent=2)+'\n')
    (OUT/'branches.asm').write_text('\n'.join(f"{hex(x['address'])}|{x['source']}" for x in plan if x['hex']=='0000')+'\n')
    print('Prepared',hex(pc-HANDLER),'byte SFP handler')

if __name__=='__main__':main()
