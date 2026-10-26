#!/usr/bin/env python3
"""Merge instruction plan, short branches and known jumbo endpoint offline."""
import hashlib
import json
from prepare_sfp_endpoint import ROOT,OUT,BASE,ENTRY,JUMBO_SHA
from build_dma_trace_candidate import jump


def main():
    jumbo=(ROOT/'artifacts/native-ui/jumbo/endpoint.bin').read_bytes()
    if hashlib.sha256(jumbo).hexdigest()!=JUMBO_SHA:raise ValueError('Unexpected original jumbo endpoint')
    if jumbo[0x20:0x28]!=jump(0x4001650c):raise ValueError('Registration continuation changed')
    plan=json.loads((OUT/'assembly-plan.json').read_text())
    validated=json.loads((ROOT/'tools/native_arc_branches.json').read_text())
    branches={x['address']:(validated[f"{x['address']:08x}"]['source'],bytes.fromhex(validated[f"{x['address']:08x}"]['hex'])) for x in plan['plan'] if x['hex']=='0000'}
    blob=bytearray(b'\xff'*0x1e00);blob[:len(jumbo)]=jumbo;blob[0x20:0x28]=jump(ENTRY)
    used=set(range(len(jumbo)))
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
    (OUT/'instructions.tsv').write_text('\n'.join(f"{hex(x['address'])}|{x['hex']}|{x['source']}" for x in plan['plan'])+'\n')
    print(hashlib.sha256(blob).hexdigest())

if __name__=='__main__':main()
