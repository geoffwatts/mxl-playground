"""Named, exact-input WSP profile. Values describe an audited ABI, not discovery."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PROFILE=ROOT/'firmware/profiles/wsp-1.0.79.json'
BOARD=ROOT/'firmware/profiles/goodtop-zx310s-8t2xs.json'

def load():
    p=json.loads(PROFILE.read_text());b=json.loads(BOARD.read_text())
    if p['id']!='wsp-1.0.79-xikestor-2.0.0.4' or b['id']!='goodtop-zx310s-8t2xs':
        raise ValueError('Unsupported WSP/board profile')
    return p,b

def admit(vendor):
    p,_=load()
    if hashlib.sha256(vendor).hexdigest()!=p['vendor_sha256']:raise ValueError('Unknown vendor input; exact audited V2 update required')
    h=p['lldp_hook'];wsp=vendor[20:20+p['wsp_bytes']]
    if wsp[h['offset']:h['offset']+8]!=bytes.fromhex(h['expected']):raise ValueError('LLDP receive hook differs')
    return p

def header():
    p,b=load();lines=['/* Generated exact WSP ABI; never edit generated output. */','#ifndef MXL_WSP_PROFILE_H','#define MXL_WSP_PROFILE_H']
    lines += ['#define WSP_'+k.upper()+' ((uintptr_t)'+hex(v)+'u)' for k,v in p['symbols'].items()]
    ports=[b['driver_to_front_panel'].get(str(n),0) for n in range(32)]
    lines += ['#define WSP_PORT_MAP {'+','.join(map(str,ports))+'}','#endif','']
    return '\n'.join(lines)
