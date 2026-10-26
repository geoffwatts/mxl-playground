#!/usr/bin/env python3
"""Collect bounded, sanitised management diagnostics; no configuration writes.

No config/firmware export, LLDP status request, raw EEPROM, serial numbers,
MAC/IP fields, HTTP headers, cookies or credentials are retained in the report.
"""
import argparse
from datetime import datetime,timezone
import getpass
import json
import os
from pathlib import Path
import struct
import time
from switch_transport import SwitchTransport


def sfp_summary(raw):
    if len(raw)!=1056 or raw[:8]!=bytes.fromhex('4d53465001020c02'):raise ValueError('Unrecognized SFP snapshot')
    records=[]
    for off,port,cage in [(8,9,1),(532,10,0)]:
        p,c,presence,state,a0,a2,e0,e2,reserved=struct.unpack_from('<6BhhH',raw,off)
        if (p,c)!=(port,cage) or presence>2 or state not in (0,1,2,3,4,255) or a0>2 or a2>2 or reserved:raise ValueError('Invalid SFP record')
        if presence!=1 and (a0 or a2) or a2==1 and a0!=1:raise ValueError('Inconsistent SFP read state')
        records.append({'port':port,'cage':cage,'presence':{0:'absent',1:'present',2:'unknown'}[presence],'driver_state':state,'identity_read_state':a0,'diagnostics_read_state':a2,'identity_errno':e0,'diagnostics_errno':e2})
    return records


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--address',required=True)
    p.add_argument('--username',default='admin')
    p.add_argument('--password-env',default='MXL_UI_PASSWORD')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    password=os.environ.get(a.password_env)
    if password is None:password=getpass.getpass('Switch password: ')
    t=SwitchTransport(a.address);status=t.login(a.username,password);del password
    report={'format':'mxl-sanitised-diagnostics/v1','collected_at':datetime.now(timezone.utc).isoformat(),'status':{k:status.get(k) for k in ['fw_ver','hw_ver','des','temperature']},'reads':{}}
    try:
        for key,path in [('ports','/port_setting_load.json'),('jumbo','/jumbo.json'),('sfp','/sfp.json')]:
            started=time.monotonic()
            try:
                response=t.request(path,binary=key=='sfp')
                if key=='sfp':data=sfp_summary(response['bytes'])
                elif key=='jumbo':data={k:response['data'].get(k) for k in ['api_version','max_frame_length','persistent','scope']}
                else:
                    d=response['data'];data={'port_count':d.get('PortNum'),'port_mode':d.get('PortMode'),'ports':[{'port':n,**{k:d.get('Port_'+str(n),{}).get(k) for k in ['Port_Status','Spd_Duplex_Cfg','Spd_Duplex_Actual','Flow_Ctrl_Cfg']}} for n in range(1,11)]}
                report['reads'][key]={'ok':True,'elapsed_ms':round((time.monotonic()-started)*1000),'data':data}
            except Exception as error:
                report['reads'][key]={'ok':False,'error_type':type(error).__name__,'message':'Read unavailable; credentials and response contents withheld'}
    finally:t.cookie=None
    a.output.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    os.fchmod(fd,0o600)
    with os.fdopen(fd,'w') as file:json.dump(report,file,indent=2);file.write('\n')
    print('Saved sanitised diagnostics to',a.output)

if __name__=='__main__':main()
