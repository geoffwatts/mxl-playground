#!/usr/bin/env python3
"""Merge instruction plan, short branches and known SFP/jumbo endpoint offline."""
import hashlib
import json
from prepare_inventory_endpoint import ROOT,OUT,BASE,ENTRY
SFP_SHA="c44640e73f83f70e1ecdfcf9eb66cf68b44998389aeba219788645703dac033d"
from build_dma_trace_candidate import jump


def main():
    prior=(ROOT/'artifacts/sfp/endpoint/endpoint.bin').read_bytes()
    if hashlib.sha256(prior).hexdigest()!=SFP_SHA:raise ValueError('Unexpected original SFP/jumbo endpoint')
    if prior[0x1014:0x101c]!=jump(0x4001650c):raise ValueError('Registration continuation changed')
    plan=json.loads((OUT/'assembly-plan.json').read_text())
    validated=json.loads((ROOT/'tools/native_arc_branches.json').read_text())
    branches={x['address']:(validated[f"{x['address']:08x}"]['source'],bytes.fromhex(validated[f"{x['address']:08x}"]['hex'])) for x in plan['plan'] if x['hex']=='0000'}
    blob=bytearray(b'\xff'*0x3000);blob[:len(prior)]=prior;blob[0x1014:0x101c]=jump(ENTRY)
    used=set(range(len(prior)))
    for item in plan['plan']:
        raw=bytes.fromhex(item['hex'])
        if raw==b'\0\0':
            source,raw=branches.pop(item['address'])
            if source!=item['source'] or len(raw)!=2:raise ValueError('Branch differs from plan')
        item['hex']=raw.hex()
        offset=item['address']-BASE;positions=set(range(offset,offset+len(raw)))
        if offset<0 or offset+len(raw)>len(blob) or positions&used:raise ValueError('Code overlap')
        used.update(positions);blob[offset:offset+len(raw)]=raw
    if branches:raise ValueError('Unexpected branch records')
    for address,raw in plan['data'].items():
        value=bytes.fromhex(raw);offset=int(address,16)-BASE;positions=set(range(offset,offset+len(value)))
        if not value.endswith(b'\0') or offset<0 or offset+len(value)>len(blob) or positions&used:raise ValueError('Data overlap or unterminated string')
        used.update(positions);blob[offset:offset+len(value)]=value
    (OUT/'endpoint.bin').write_bytes(blob)
    (OUT/'resolved-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    (OUT/'instructions.tsv').write_text('0x402c1014|'+jump(ENTRY).hex()+'|j inventory registration\n'+'\n'.join(f"{hex(x['address'])}|{x['hex']}|{x['source']}" for x in plan['plan'])+'\n')
    print(hashlib.sha256(blob).hexdigest())

if __name__=='__main__':main()
