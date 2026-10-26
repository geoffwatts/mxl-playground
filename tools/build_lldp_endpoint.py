#!/usr/bin/env python3
"""Compile the portable LLDP cache plus exact WSP adapter; offline only."""
import argparse,hashlib,json,os,struct,subprocess
from pathlib import Path
from build_management_probe import FLAGS,disassembly_rows
from build_dma_trace_candidate import jump,limm
from wsp_profile import load,header
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
 profile,_=load();base,size=profile['lldp_region'];(out/'wsp_profile.h').write_text(header())
 modules=['wsp_platform','wsp_arithmetic','lldp_cache','lldp_native'];script=['set -eu']
 for name in modules:script+=[' '.join(['arc-linux-gnu-gcc-12',*FLAGS,'-I/out','-fstack-usage','-c','/src/'+name+'.c','-o','/out/'+name+'.o'])]
 script+=[f'arc-linux-gnu-ld --gc-sections --defsym MXL_LLDP_CODE={hex(base+32)} --defsym MXL_LLDP_END={hex(base+size)} -T /src/lldp_native.ld -u mxl_lldp_receive_native '+ ' '.join('/out/'+n+'.o' for n in modules)+' -o /out/lldp.elf','arc-linux-gnu-nm -u /out/lldp.elf > /out/undefined.txt','arc-linux-gnu-nm -n /out/lldp.elf > /out/symbols.txt','arc-linux-gnu-objdump -d --insn-width=16 /out/lldp.elf > /out/lldp.dis','arc-linux-gnu-objcopy -O binary /out/lldp.elf /out/lldp.bin']
 subprocess.run(['docker','run','--rm','--platform','linux/amd64','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/tmp:rw,size=32m','--user',str(os.getuid())+':'+str(os.getgid()),'-v',str(ROOT/'firmware')+':/src:ro','-v',str(out)+':/out','mxl-arc-build:bookworm','sh','-c','\n'.join(script)],check=True,timeout=90)
 if (out/'undefined.txt').read_text().strip():raise ValueError('Unresolved LLDP symbols')
 syms={p[2]:int(p[0],16) for line in (out/'symbols.txt').read_text().splitlines() if len(p:=line.split())==3};raw=(out/'lldp.bin').read_bytes();entry=syms['mxl_lldp_register'];receive=syms['mxl_lldp_receive_native']
 wrapper=bytes.fromhex('a1402220800f')+limm(entry)+bytes.fromhex('a140')+jump(profile['symbols']['registration_continue'])
 blob=bytearray(b'\xff'*size);blob[:len(wrapper)]=wrapper;blob[0x14:0x20]=struct.pack('<4sII',b'LLDP',receive,len(raw));blob[0x20:0x20+len(raw)]=raw
 rows=[(base,wrapper[:2],'mov_s r0,r13'),(base+2,wrapper[2:10],'jl LLDP registration'),(base+10,wrapper[10:12],'mov_s r0,r13'),(base+12,wrapper[12:20],'j native continuation')]+disassembly_rows((out/'lldp.dis').read_text(),raw,base=base+32)
 (out/'endpoint.bin').write_bytes(blob);(out/'instructions.tsv').write_text('\n'.join(f'{hex(at)}|{b.hex()}|{s}' for at,b,s in rows)+'\n')
 report={'profile':profile['id'],'sha256':hashlib.sha256(blob).hexdigest(),'compiled_bytes':len(raw),'receive_entry':hex(receive),'instructions':len(rows),'independent_decode_required':True,'stack_usage':{n:(out/(n+'.su')).read_text() for n in modules}}
 (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
