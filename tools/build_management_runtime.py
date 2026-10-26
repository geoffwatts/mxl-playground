#!/usr/bin/env python3
"""Build the bounded management-VLAN integration trial offline, never upload.

This trial exposes temporary VID 0/1 proposals and cancellation only. It links
no NVS write implementation. All four native hook targets are exported for
independent decoding and a separately pinned exact-build image builder.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
from build_management_probe import ROOT, BASE, CODE, PRIOR_SHA, FLAGS, disassembly_rows
from build_dma_trace_candidate import jump, limm

MODULES = ('management_vlan_probe', 'management_vlan_pce', 'management_vlan_native',
           'management_vlan_store', 'management_vlan_tx', 'management_vlan_owner',
           'management_vlan_core', 'management_vlan_iprule', 'management_vlan_controller',
           'management_vlan_egress_gate', 'management_vlan_requests', 'management_vlan_runtime')
EXPORTS = ('mxl_mgmt_runtime_ip_event', 'mxl_mgmt_runtime_ip_write',
           'mxl_mgmt_runtime_tx', 'mxl_mgmt_runtime_web_start')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full',action='store_true',help='Build the V2 durable management-VLAN API instead of the bounded trial')
    parser.add_argument('--compiler-image', default='mxl-arc-build:bookworm')
    parser.add_argument('--output-dir', type=Path,
                        default=ROOT/'artifacts/management-vlan/native-runtime-trial')
    args = parser.parse_args()
    prior = (ROOT/'artifacts/inventory/endpoint/endpoint.bin').read_bytes()
    if len(prior) != 0x3000 or hashlib.sha256(prior).hexdigest() != PRIOR_SHA:
        raise ValueError('Expected the exact verified inventory/SFP/jumbo extension')
    output = args.output_dir.resolve()
    if output == ROOT/'firmware' or ROOT/'firmware' in output.parents:
        raise ValueError('Output must not overlap C sources')
    output.mkdir(parents=True, exist_ok=True)
    image = subprocess.run(['docker','image','inspect','--format','{{.Id}}',args.compiler_image],
                           check=True,capture_output=True,text=True,timeout=10).stdout.strip()
    flags = FLAGS + ['-DMXL_MGMT_RUNTIME_TRIAL=1','-fstack-usage']
    if args.full:flags += ['-DMXL_MGMT_RUNTIME_FULL=1']
    modules=MODULES + (('management_vlan_identity',) if args.full else ())
    script = ['set -eu','arc-linux-gnu-gcc-12 --version > /out/compiler-version.txt']
    for name in modules:
        script.append(' '.join(['arc-linux-gnu-gcc-12',*flags,'-c','/src/'+name+'.c',
                                '-o','/out/'+name+'.o']))
    script += [
        'arc-linux-gnu-ld --gc-sections -T /src/management_vlan_runtime.ld ' +
        ' '.join('-u '+name for name in EXPORTS) + ' ' +
        ' '.join('/out/'+name+'.o' for name in modules) + ' -o /out/runtime.elf',
        'arc-linux-gnu-nm -u /out/runtime.elf > /out/undefined.txt',
        'arc-linux-gnu-nm -n /out/runtime.elf > /out/symbols.txt',
        'arc-linux-gnu-objdump -d --insn-width=16 /out/runtime.elf > /out/runtime.dis',
        'arc-linux-gnu-objcopy -O binary /out/runtime.elf /out/runtime.bin',
        'arc-linux-gnu-size /out/runtime.elf > /out/sizes.txt']
    subprocess.run(['docker','run','--rm','--platform','linux/amd64','--network','none',
                    '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
                    '--tmpfs','/tmp:rw,noexec,nosuid,size=16777216',
                    '--user',str(os.getuid())+':'+str(os.getgid()),
                    '--mount','type=bind,src='+str(ROOT/'firmware')+',dst=/src,readonly',
                    '--mount','type=bind,src='+str(output)+',dst=/out',image,
                    'sh','-c','\n'.join(script)],check=True,timeout=90)
    if (output/'undefined.txt').read_text().strip():
        raise ValueError('Runtime has unresolved external symbols')
    symbols = {}
    for line in (output/'symbols.txt').read_text().splitlines():
        parts = line.split()
        if len(parts)==3: symbols[parts[2]]=int(parts[0],16)
    if not args.full and ('mxl_mgmt_native_store_write' in symbols or 'mxl_mgmt_controller_confirm' in symbols):
        raise ValueError('Trial linked a forbidden durable confirmation/write implementation')
    binary = (output/'runtime.bin').read_bytes()
    if len(binary)>0x6ff0-0x3020: raise ValueError('Trial exceeds its code window')
    for name in ('mxl_mgmt_probe_register',*EXPORTS):
        if not CODE<=symbols[name]<CODE+len(binary) or symbols[name]&1:
            raise ValueError('Entry point outside compiled code: '+name)
    register = symbols['mxl_mgmt_probe_register']
    move = bytes.fromhex('a140')
    call = bytes.fromhex('2220800f')+limm(register)
    wrapper = move+call+move+jump(0x4001650c)
    blob = bytearray(b'\xff'*0x7000)
    blob[:len(prior)] = prior
    continuation = prior.find(jump(0x4001650c),0x2000,0x2100)
    if continuation<0 or prior.find(jump(0x4001650c),continuation+1,0x2100)>=0:
        raise ValueError('Expected one inventory registration continuation')
    blob[continuation:continuation+8]=jump(BASE)
    blob[0x3000:0x3000+len(wrapper)]=wrapper
    blob[0x3014:0x3020]=struct.pack('<II4s',*(symbols[name] for name in EXPORTS[:2]),b'MVHI')
    blob[0x3020:0x3020+len(binary)]=binary
    blob[-16:]=struct.pack('<4sIII',b'MVRT',symbols[EXPORTS[2]],symbols[EXPORTS[3]],2 if args.full else 1)
    rows=[(BASE,move,'mov_s r0,r13'),(BASE+2,call,'jl '+hex(register)),
          (BASE+10,move,'mov_s r0,r13'),(BASE+12,jump(0x4001650c),'j native registration continuation')]
    rows += disassembly_rows((output/'runtime.dis').read_text(),binary)
    (output/'instructions.tsv').write_text('\n'.join(
        f'{hex(at)}|{raw.hex()}|{source}' for at,raw,source in rows)+'\n')
    (output/'endpoint.bin').write_bytes(blob)
    report = {'status':'OFFLINE; NOT INSTALLED; INDEPENDENT DECODE REQUIRED',
              'trial_only':not args.full,'allowed_proposal_vids':'0..4094' if args.full else [0,1],'confirmation_available':args.full,
              'native_settings_write_linked':args.full,'compiler_image':image,
              'compiled_bytes':len(binary),'endpoint_bytes':len(blob),
              'endpoint_sha256':hashlib.sha256(blob).hexdigest(),'instruction_count':len(rows),
              'symbols':symbols,'sources':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                  for name in modules for p in (ROOT/'firmware').glob(name+'.[ch]')},
              'stack_usage':{name:(output/(name+'.su')).read_text() for name in modules},
              'linker_script_sha256':hashlib.sha256((ROOT/'firmware/management_vlan_runtime.ld').read_bytes()).hexdigest()}
    (output/'build-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('compiled_bytes','endpoint_bytes','endpoint_sha256','instruction_count')},indent=2))


if __name__=='__main__': main()
