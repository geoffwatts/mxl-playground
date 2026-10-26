#!/usr/bin/env python3
"""Merge the ARC plan and independently assembled short branches, offline only.

Run prepare_jumbo_endpoint.py first. Known short branches use the committed
Ghidra-validated fixtures; changed plans require new assembly and independent
instruction decoding before installation.
"""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/native-ui/jumbo'


def main():
    plan=json.loads((OUT/'assembly-plan.json').read_text())
    validated=json.loads((ROOT/'tools/native_arc_branches.json').read_text())
    branches={x['address']:(validated[f"{x['address']:08x}"]['source'],bytes.fromhex(validated[f"{x['address']:08x}"]['hex'])) for x in plan['plan'] if x['hex']=='0000'}
    blob=bytearray(b'\xff'*0xe00)
    used=set()
    def put(address,raw):
        offset=address-0x402c0000
        if offset<0 or offset+len(raw)>len(blob):
            raise ValueError('Endpoint exceeds reserved padding')
        positions=set(range(offset,offset+len(raw)))
        if positions&used:
            raise ValueError('Overlapping endpoint sections')
        used.update(positions)
        blob[offset:offset+len(raw)]=raw
    for item in plan['plan']:
        raw=bytes.fromhex(item['hex'])
        if raw==b'\0\0':
            source,raw=branches.pop(item['address'])
            if source!=item['source'] or len(raw)!=2:
                raise ValueError('Branch assembly does not match the plan')
        put(item['address'],raw)
    if branches:
        raise ValueError('Unexpected branch assembly records')
    for address,raw in plan['data'].items():
        value=bytes.fromhex(raw)
        if not value.endswith(b'\0'):
            raise ValueError('Unterminated endpoint string')
        put(int(address,16),value)
    (OUT/'endpoint.bin').write_bytes(blob)
    (OUT/'registration.bin').write_bytes(blob[:int(plan['wrapper_end'],16)-0x402c0000])
    (OUT/'handler.bin').write_bytes(blob[0x100:int(plan['handler_end'],16)-0x402c0000])
    print(hashlib.sha256(blob).hexdigest())


if __name__=='__main__':
    main()
