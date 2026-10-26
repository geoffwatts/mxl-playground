#!/usr/bin/env python3
"""Offline ARC EM4 C probe build; no device access or firmware installation.

Requires the local toolchain/arc Docker image. The container gets read-only C
sources, one output directory, no network, and no Linux-host/UART access.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import struct
from build_dma_trace_candidate import limm, jump

ROOT = Path(__file__).resolve().parents[1]
BASE = 0x402c3000
CODE = BASE + 0x20
PRIOR_SHA = '805babe78b646e39445bc2654951c27c50f6337bf16ab981e9a600a884378081'
FLAGS = ['-mcpu=em4', '-mcode-density', '-mlittle-endian', '-mno-sdata',
         '-mno-millicode', '-mno-ll64', '-Os', '-ffreestanding', '-fno-builtin',
         '-fno-pic', '-fno-stack-protector', '-fno-asynchronous-unwind-tables',
         '-ffunction-sections', '-fdata-sections', '-Wall', '-Wextra', '-Werror', '-std=c11']


def disassembly_rows(disassembly, binary, base=CODE):
    rows = []
    for line in disassembly.splitlines():
        match = re.match(r'^\s*([0-9a-f]+):(.*)$', line)
        if not match:
            continue
        fields = [field.strip() for field in match[2].split('\t') if field.strip()]
        if len(fields) < 2 or not re.fullmatch(r'[0-9a-f]{4}(?: +[0-9a-f]{4})*', fields[0]):
            continue
        at = int(match[1], 16)
        size = len(''.join(fields[0].split())) // 2
        offset = at - base
        if offset < 0 or offset + size > len(binary) or size not in (2, 4, 6, 8):
            raise ValueError('Unexpected GNU instruction bounds: ' + line)
        raw = binary[offset:offset + size]
        # GNU displays each ARC halfword as a number; compare its actual bytes.
        words = fields[0].split()
        expected = b''.join(int(word, 16).to_bytes(2, 'little') for word in words)
        if raw != expected:
            raise ValueError('GNU disassembly bytes do not match the linked binary')
        rows.append((at, raw, ' '.join(fields[1:])))
    if not rows:
        raise ValueError('No linked ARC instructions found')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler-image', default='mxl-arc-build:bookworm')
    parser.add_argument('--timer-observer', action='store_true',
                        help='Include the boot-lifetime timer smoke test; still no policy/NVS writes')
    parser.add_argument('--ip-hook-observer', action='store_true',
                        help='Observe pass-through native IP callbacks/writes; implies timer observer')
    parser.add_argument('--egress-observer', action='store_true',
                        help='Observe pass-through TX/startup state; implies IP/timer observers')
    parser.add_argument('--prior', type=Path, default=ROOT / 'artifacts/inventory/endpoint/endpoint.bin')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'artifacts/management-vlan/native-platform-probe')
    args = parser.parse_args()
    if args.egress_observer:args.ip_hook_observer=True
    if args.ip_hook_observer:args.timer_observer=True
    prior = args.prior.read_bytes()
    if len(prior) != 0x3000 or hashlib.sha256(prior).hexdigest() != PRIOR_SHA:
        raise ValueError('Expected the exact verified jumbo/SFP/inventory endpoint')
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if output == (ROOT / 'firmware').resolve() or (ROOT / 'firmware').resolve() in output.parents:
        raise ValueError('Output must not overlap C sources')
    image = subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', args.compiler_image],
                           check=True, capture_output=True, text=True, timeout=10).stdout.strip()
    script = ['set -eu', 'arc-linux-gnu-gcc-12 --version > /out/compiler-version.txt']
    modules = ['management_vlan_probe', 'management_vlan_pce', 'management_vlan_native',
               'management_vlan_store', 'management_vlan_tx', 'management_vlan_owner']
    flags = FLAGS + (['-DMXL_MGMT_TIMER_OBSERVER=1'] if args.timer_observer else [])
    if args.ip_hook_observer:flags += ['-DMXL_MGMT_IP_HOOK_OBSERVER=1']
    if args.egress_observer:
        flags += ['-DMXL_MGMT_EGRESS_OBSERVER=1']
        modules.append('management_vlan_egress_gate')
    if args.timer_observer:modules.append('management_vlan_observer')
    for name in modules:
        script.append(' '.join(['arc-linux-gnu-gcc-12', *flags,
                                '-c', '/src/' + name + '.c', '-o', '/out/' + name + '.o']))
    script += [
        'arc-linux-gnu-ld --gc-sections -T /src/management_vlan_probe.ld ' +
        ('-u mxl_mgmt_observer_ip_event -u mxl_mgmt_observer_ip_write ' if args.ip_hook_observer else '') +
        ('-u mxl_mgmt_observer_tx ' if args.egress_observer else '') +
        ' '.join('/out/' + name + '.o' for name in modules) + ' -o /out/probe.elf',
        'arc-linux-gnu-nm -u /out/probe.elf > /out/undefined.txt',
        'arc-linux-gnu-nm -n /out/probe.elf > /out/symbols.txt',
        'arc-linux-gnu-objdump -d --insn-width=16 /out/probe.elf > /out/probe.dis',
        'arc-linux-gnu-objcopy -O binary /out/probe.elf /out/probe.bin',
        'arc-linux-gnu-size /out/probe.elf',
    ]
    command = ['docker', 'run', '--rm', '--platform', 'linux/amd64', '--network', 'none',
               '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
               '--tmpfs', '/tmp:rw,noexec,nosuid,size=16777216',
               '--user', str(os.getuid()) + ':' + str(os.getgid()),
               '--mount', 'type=bind,src=' + str(ROOT / 'firmware') + ',dst=/src,readonly',
               '--mount', 'type=bind,src=' + str(output) + ',dst=/out', image,
               'sh', '-c', '\n'.join(script)]
    subprocess.run(command, check=True, timeout=90)
    if (output / 'undefined.txt').read_text().strip():
        raise ValueError('Linked probe has unresolved external symbols')
    symbols = {}
    for line in (output / 'symbols.txt').read_text().splitlines():
        fields = line.split()
        if len(fields) == 3:
            symbols[fields[2]] = int(fields[0], 16)
    forbidden = {'mxl_mgmt_native_pce_write', 'mxl_mgmt_native_store_write',
                 'mxl_mgmt_store_persist', 'mxl_mgmt_pce_apply',
                 'mxl_mgmt_native_tx_insert', 'mxl_mgmt_tx_dispatch',
                 'mxl_mgmt_native_work_init', 'mxl_mgmt_native_reschedule'}
    forbidden |= {'mxl_mgmt_native_owner_claim', 'mxl_mgmt_owner_claim'}
    forbidden |= {'mxl_mgmt_native_owner_find_locked', 'mxl_mgmt_owner_find_locked'}
    forbidden |= {'mxl_mgmt_native_trylock','mxl_mgmt_native_owner_try_find',
                  'mxl_mgmt_egress_gate_send','mxl_mgmt_native_tx_original'}
    if args.timer_observer:
        forbidden -= {'mxl_mgmt_native_work_init', 'mxl_mgmt_native_reschedule',
                      'mxl_mgmt_native_owner_claim', 'mxl_mgmt_owner_claim'}
    if args.ip_hook_observer:
        forbidden -= {'mxl_mgmt_native_owner_find_locked', 'mxl_mgmt_owner_find_locked'}
    if args.egress_observer:
        forbidden -= {'mxl_mgmt_native_trylock','mxl_mgmt_native_owner_try_find',
                      'mxl_mgmt_egress_gate_send','mxl_mgmt_native_tx_original'}
    if forbidden.intersection(symbols):
        raise ValueError('Read-only probe linked a forbidden write/timer function')
    binary = (output / 'probe.bin').read_bytes()
    blob_size = 0x5000 if args.timer_observer else 0x4000
    if len(binary) > blob_size - 0x3020 - (8 if args.egress_observer else 0):
        raise ValueError('C probe overlaps the next reserved page')
    register = symbols['mxl_mgmt_probe_register']
    if not CODE <= register < CODE + len(binary):
        raise ValueError('Registration function is outside the compiled blob')
    move = bytes.fromhex('a140')  # decoded mov_s r0,r13
    call = bytes.fromhex('2220800f') + limm(register)
    wrapper = move + call + move + jump(0x4001650c)
    blob = bytearray(b'\xff' * blob_size)
    blob[:0x3000] = prior
    continuation = prior.find(jump(0x4001650c), 0x2000, 0x2100)
    if continuation < 0 or prior.find(jump(0x4001650c), continuation + 1, 0x2100) >= 0:
        raise ValueError('Expected one inventory registration continuation')
    blob[continuation:continuation + 8] = jump(BASE)
    blob[0x3000:0x3000 + len(wrapper)] = wrapper
    blob[0x3020:0x3020 + len(binary)] = binary
    if args.ip_hook_observer:
        hooks=[symbols[name] for name in ['mxl_mgmt_observer_ip_event','mxl_mgmt_observer_ip_write']]
        if any(not CODE<=at<CODE+len(binary) for at in hooks):
            raise ValueError('IP observer hook is outside compiled code')
        blob[0x3014:0x3020]=struct.pack('<II4s',*hooks,b'MVHI')
    if args.egress_observer:
        at=symbols['mxl_mgmt_observer_tx']
        if not CODE<=at<CODE+len(binary):raise ValueError('TX observer outside compiled code')
        blob[-8:]=struct.pack('<4sI',b'MVTG',at)
    rows = [(BASE, move, 'mov_s r0,r13'), (BASE + 2, call, 'jl ' + hex(register)),
            (BASE + 10, move, 'mov_s r0,r13'),
            (BASE + 12, jump(0x4001650c), 'j original registration continuation')]
    rows += disassembly_rows((output / 'probe.dis').read_text(), binary)
    (output / 'instructions.tsv').write_text('\n'.join(
        f'{hex(at)}|{raw.hex()}|{source}' for at, raw, source in rows) + '\n')
    (output / 'endpoint.bin').write_bytes(blob)
    report = {'status': 'OFFLINE COMPILED; NOT INSTALLED; PENDING INDEPENDENT DECODE',
              'read_only': True, 'transaction_core_included': False,
              'policy_writes_possible': False, 'platform_probe': True,
              'timer_observer': args.timer_observer,
              'ip_hook_observer': args.ip_hook_observer,
              'egress_observer': args.egress_observer,
              'forbidden_functions_absent': sorted(forbidden), 'compiler_image': image,
              'compiler_version': (output / 'compiler-version.txt').read_text().splitlines()[0],
              'compiler_flags': flags, 'compiled_bytes': len(binary), 'endpoint_bytes': len(blob),
              'endpoint_sha256': hashlib.sha256(blob).hexdigest(), 'instruction_count': len(rows),
              'prior_sha256': PRIOR_SHA, 'registration_continuation_offset': hex(continuation),
              'symbols': symbols,
              'sources': {name: hashlib.sha256((ROOT / 'firmware' / name).read_bytes()).hexdigest()
                          for name in [item + suffix for item in modules for suffix in ['.c', '.h']
                                       if (ROOT / 'firmware' / (item + suffix)).exists()] +
                                      ['management_vlan_probe.ld']}}
    (output / 'build-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['compiled_bytes', 'endpoint_bytes',
                                          'endpoint_sha256', 'instruction_count']}, indent=2))


if __name__ == '__main__':
    main()
