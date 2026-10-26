#!/usr/bin/env python3
"""Build an OFFLINE, one-unit-tested 8 MiB V2 migration candidate. Never writes hardware.

Uses V2's compiled default map, not a guessed allocation. Keeps boot code,
board data and NVS bytes; relocates areas and writes authenticated V2 payloads.
The owner booted this exact candidate; broad settings/recovery validation remains
incomplete. The exact whole-source hash intentionally excludes other units.
"""
import argparse
import hashlib
import json
import re
import struct
import zlib
from pathlib import Path

from spi_layout import MAGIC, inspect, parse_tags
from verify_firmware_signatures import verify_component

SOURCE_SHA = '5821b39c880c6773adbded270e06121748c428109ed447291f22061b2cce9346'
V2_SHA = '085ce44aeffe82b75676c5784b915ab80cfa0262a1ec5356a47832a45af07426'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def compiled_map(component):
    """Find a complete ten-area Zephyr default map; reject ambiguous matches."""
    found = []
    prefix = struct.pack('<III', 0, 0, 0xa000)
    for match in re.finditer(re.escape(prefix), component):
        off = match.start()
        if off + 160 > len(component):
            continue
        rows = [struct.unpack_from('<4I', component, off+i*16) for i in range(10)]
        if [r[0] for r in rows] != list(range(10)) or len({r[3] for r in rows}) != 1:
            continue
        areas = [{'id': r[0], 'offset': r[1], 'size': r[2]} for r in rows]
        ordered = sorted(areas, key=lambda r: r['offset'])
        if any(r['offset'] % 4096 or r['size'] % 4096 or not r['size']
               or r['offset']+r['size'] > 0x800000 for r in areas):
            continue
        if any(a['offset']+a['size'] > b['offset'] for a, b in zip(ordered, ordered[1:])):
            continue
        found.append((off, areas))
    if len(found) != 1:
        raise ValueError(f'Expected unique compiled map, found {len(found)}')
    return found[0]


def build(source, update, secondary_tag):
    if sha(source) != SOURCE_SHA or sha(update) != V2_SHA:
        raise ValueError('Only the audited source SPI and V2.0.0.4 update are supported')
    tags = parse_tags(source)
    table = next(t for t in tags if t['tag'] == '0xa700')
    old = {}
    for off in range(table['payload_offset'], table['payload_offset']+table['length'], 12):
        ident, start, size = struct.unpack_from('>III', source, off)
        old[ident] = {'id': ident, 'offset': start, 'size': size}
    magic, ws, wc, gs, gc = struct.unpack_from('<5I', update)
    if magic != 0xf48bf48b or len(update) != 20+ws+gs:
        raise ValueError('Invalid update container')
    wsp, gphy = update[20:20+ws], update[20+ws:]
    if zlib.crc32(wsp) != wc or zlib.crc32(gphy) != gc:
        raise ValueError('Update CRC mismatch')
    map_off, new_rows = compiled_map(wsp)
    new = {p['id']: p for p in new_rows}
    # Confirm the structure decoder against the known stock physical table.
    stock_wsp = source[old[1]['offset']:old[1]['offset']+old[1]['size']]
    _, stock_rows = compiled_map(stock_wsp)
    if {p['id']: p for p in stock_rows} != old:
        raise ValueError('Stock compiled/physical maps disagree')
    if new[0] != old[0]:
        raise ValueError('Boot area would change size or location')
    if len(secondary_tag) != 76 or secondary_tag[:8] != bytes.fromhex('a0005fff00000044'):
        raise ValueError('Expected acquired internal secondary A000 TLV')
    wsp_key = secondary_tag[8:72]
    if zlib.crc32(wsp_key) != int.from_bytes(secondary_tag[72:76], 'little'):
        raise ValueError('Secondary-key CRC mismatch')
    key_off = next(t for t in tags if t['tag'] == '0xa100')['payload_offset']
    gphy_key = source[key_off:key_off+64]
    signatures = {'WSP': verify_component(wsp, wsp_key),
                  'GPHY': verify_component(gphy, gphy_key)}
    if not all(r['signature_valid'] for r in signatures.values()):
        raise ValueError('V2 signature failed')
    out = bytearray(b'\xff' * len(source))
    out[:old[0]['size']] = source[:old[0]['size']]
    payload = b''.join(struct.pack('>III', p['id'], p['offset'], p['size']) for p in new_rows)
    if len(payload) != table['length']:
        raise ValueError('Partition tag size would change')
    out[table['payload_offset']:table['payload_offset']+len(payload)] = payload
    copied = []
    for ident in (5, 6, 7, 8, 9):
        a, b = old[ident], new[ident]
        if b['size'] < a['size']:
            raise ValueError('Persistent/flashless area would be truncated')
        body = source[a['offset']:a['offset']+a['size']]
        out[b['offset']:b['offset']+len(body)] = body
        copied.append({'id': ident, 'old_offset': a['offset'], 'new_offset': b['offset'],
                       'copied_size': len(body), 'new_size': b['size'], 'sha256': sha(body)})
    for ident, component, crc, key in [(1,wsp,wc,wsp_key), (2,gphy,gc,gphy_key),
                                      (3,wsp,wc,wsp_key), (4,gphy,gc,gphy_key)]:
        area = new[ident]
        signed_end = 0x7e0 + int.from_bytes(component[0x798:0x79c], 'big')
        if len(component) > area['size'] or signed_end > min(len(component)-32, area['size']-32):
            raise ValueError('Component/trailer fit check failed')
        start = area['offset']
        out[start:start+len(component)] = component
        trailer = bytearray(source[old[ident]['offset']+old[ident]['size']-32:
                                   old[ident]['offset']+old[ident]['size']])
        trailer[4:8] = struct.pack('<I', crc)
        trailer[16:32] = MAGIC
        out[start+area['size']-32:start+area['size']] = trailer
        if not verify_component(out[start:start+len(component)], key)['signature_valid']:
            raise ValueError('Relocated component no longer authenticates')
    expected_boot = bytearray(source[:old[0]['size']])
    expected_boot[table['payload_offset']:table['payload_offset']+len(payload)] = payload
    if out[:old[0]['size']] != expected_boot or out[0x400:0x7000] != source[0x400:0x7000]:
        raise ValueError('Unexpected boot-code change')
    manifest = {'status': 'EXPERIMENTAL OFFLINE CANDIDATE; NOT BOOT-TESTED',
        'source_sha256': sha(source), 'update_sha256': sha(update), 'candidate_sha256': sha(out),
        'candidate_size': len(out), 'compiled_v2_map_offset': map_off,
        'map': new_rows, 'preserved_areas': copied, 'signatures': signatures,
        'boot_code_unchanged': True, 'boot_code_crc32': hex(zlib.crc32(out[0x400:0x7000])),
        'boot_area_changed_bytes': sum(a != b for a,b in zip(source[:0xa000],out[:0xa000])),
        'trailer_policy': 'Preserve per-slot first 16 bytes except export CRC; install standard end marker in all four firmware slots.',
        'unresolved': ['Runtime boot selection and relocated flash mapping have not been exercised.',
                       'V1 configuration bytes preserved but V2 schema compatibility untested.',
                       'Partition 5 grows from 16 KiB to 32 KiB; extension filled with FF.',
                       'No hardware restore test, flash write, or OTP change performed.',
                       'Contains private board/settings data; do not publish this full image.']}
    return bytes(out), manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('update', type=Path)
    parser.add_argument('--secondary-key-tag', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix('.json').exists():
        raise ValueError('Refusing to overwrite existing candidate or manifest')
    data, manifest = build(args.source.read_bytes(), args.update.read_bytes(),
                           args.secondary_key_tag.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    # Re-parse the produced physical image, independently checking area overlap,
    # headers, extents and the changed A700 map through the existing SPI parser.
    parsed = inspect(args.output)
    manifest['physical_map_reparsed'] = True
    manifest['unpartitioned_tail'] = parsed['unpartitioned_tail']
    args.output.with_suffix('.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps({'output': str(args.output), 'status': manifest['status'],
                      'sha256': manifest['candidate_sha256'], 'size': len(data)}, indent=2))


if __name__ == '__main__':
    main()
