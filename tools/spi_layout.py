#!/usr/bin/env python3
"""Inspect the ZX310S SPI dump and compare it with the original web export.

Read-only. Parse the ROM TLV/partition format corroborated by the recovered
application's parse_part_tag function. Do not construct or write flash images.
Reports deliberately omit configuration values and raw key material.
"""
import argparse
import hashlib
import json
import re
import struct
import zlib
from pathlib import Path

try:
    from .native_layout import inspect as inspect_export
except ImportError:
    from native_layout import inspect as inspect_export

MAGIC = bytes.fromhex('77c295f360d2ef7f3552500f2cb67980')
ROLES = {0: 'Boot/tag area', 1: 'WSP A', 2: 'GPHY A', 3: 'WSP B',
         4: 'GPHY B', 5: 'Persistent data (role unresolved)',
         6: 'Tagged board/configuration data (role unresolved)',
         7: 'Zephyr settings keys', 8: 'Flashless A (update-code mapping)',
         9: 'Flashless B (update-code mapping)'}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def parse_tags(data):
    tags = []
    off = 0
    while off + 8 <= min(len(data), 0x1bf8):
        tag, complement, length = struct.unpack_from('>HHI', data, off)
        if tag + complement != 0xffff:
            raise ValueError(f'Invalid tag complement at {off:#x}')
        end = off + 8 + length
        if end > min(len(data), 0x1bf8):
            raise ValueError(f'Tag exceeds scan boundary at {off:#x}')
        tags.append({'offset': off, 'tag': f'0x{tag:04x}', 'length': length,
                     'payload_offset': off + 8, 'payload_sha256': sha(data[off+8:end])})
        if tag == 0xad00 and length == 0:
            return tags
        off = end
    raise ValueError('No end tag in ROM tag scan area')

def diff_runs(a, b):
    if len(a) != len(b):
        raise ValueError('Comparison ranges have different sizes')
    runs = []
    count = 0
    for i, (old, new) in enumerate(zip(a, b)):
        if old == new:
            continue
        count += 1
        if runs and runs[-1]['end_exclusive'] == i:
            runs[-1]['end_exclusive'] += 1
        else:
            runs.append({'offset': i, 'end_exclusive': i+1})
    return {'different_bytes': count, 'runs': runs}

def inspect(path, exported=None):
    data = path.read_bytes()
    if len(data) != 8 * 1024 * 1024:
        raise ValueError('Expected an 8 MiB W25Q64 main-array dump')
    if data[:4] != bytes.fromhex('a5005aff'):
        raise ValueError('Unrecognized ROM tag prefix')
    tags = parse_tags(data)
    part_tags = [t for t in tags if t['tag'] == '0xa700']
    if len(part_tags) != 1:
        raise ValueError('Expected one partition tag')
    tag = part_tags[0]
    if not tag['length'] or tag['length'] % 12 or tag['length'] > 120:
        raise ValueError('Invalid partition record count')
    partitions, seen = [], set()
    for off in range(tag['payload_offset'], tag['payload_offset']+tag['length'], 12):
        ident, start, size = struct.unpack_from('>III', data, off)
        if ident in seen or not size or start + size > len(data):
            raise ValueError('Invalid, duplicate or out-of-bounds partition')
        seen.add(ident)
        body = data[start:start+size]
        item = {'id': ident, 'role': ROLES.get(ident, 'Unknown'), 'offset': start,
                'size': size, 'end_exclusive': start+size, 'record_offset': off,
                'sha256': sha(body), 'non_ff_bytes': size-body.count(255)}
        if ident in (1, 2, 3, 4):
            if body[0x6d8:0x6dc] != bytes.fromhex('424c7002'):
                raise ValueError(f'Partition {ident} lacks expected ECDSA-header type')
            image_size = struct.unpack_from('>I', body, 0x798)[0]+0x800
            if image_size > size or image_size < 0x800:
                raise ValueError('Embedded image size is out of bounds')
            item['image'] = {'header_offset': start+0x6d8, 'length': image_size,
                             'sha256': sha(body[:image_size]),
                             'signature_verified': False}
            item['slot_trailer'] = {'offset': start+size-32,
                                    'magic_matches': body[-16:] == MAGIC,
                                    'first_16_hex': body[-32:-16].hex()}
        partitions.append(item)
    ordered = sorted(partitions, key=lambda p: p['offset'])
    if any(a['end_exclusive'] > b['offset'] for a, b in zip(ordered, ordered[1:])):
        raise ValueError('Overlapping partition ranges')
    result = {'path': str(path), 'size': len(data), 'sha256': sha(data),
              'tags': tags, 'partitions': partitions,
              'unpartitioned_tail': {'offset': ordered[-1]['end_exclusive'],
                                     'length': len(data)-ordered[-1]['end_exclusive'],
                                     'all_ff': all(x == 255 for x in data[ordered[-1]['end_exclusive']:])},
              'uart_config_candidates': [], 'settings_key_names': [],
              'limitations': ['Main flash array only; chip security/OTP registers, SoC OTP and internal boot ROM are not included.',
                              'Partition names combine content observations and existing static update-code evidence.',
                              'Slot trailer flags do not by themselves prove boot choice or fallback behavior.',
                              'UART byte patterns suggest 115200 8N1, no flow control; physical header and voltage are unverified.',
                              'No boot authentication, firmware execution, device write or recovery test performed.']}
    pattern = struct.pack('<I', 115200)+bytes([0, 1, 3, 0])
    for part in partitions:
        if part['id'] not in (0, 1, 3):
            continue
        body = data[part['offset']:part['end_exclusive']]
        for match in re.finditer(re.escape(pattern), body):
            result['uart_config_candidates'].append({'partition_id': part['id'],
                'offset': part['offset']+match.start(), 'baud': 115200,
                'interpretation': 'Zephyr uart_config byte-pattern candidate: parity=0, stop_bits=1, data_bits=3, flow_ctrl=0'})
    settings = next((p for p in partitions if p['id'] == 7), None)
    if settings:
        body = data[settings['offset']:settings['end_exclusive']]
        for match in re.finditer(rb'[\x20-\x7e]{4,}', body):
            if re.fullmatch(rb'sys/[a-zA-Z0-9_./-]+', match[0]):
                result['settings_key_names'].append({'offset': settings['offset']+match.start(),
                                                    'key': match[0].decode('ascii')})
    if exported:
        reference = inspect_export(exported)
        export_data = exported.read_bytes()
        comparisons = []
        for component, ident in zip(reference['components'], (1, 2)):
            part = next((p for p in partitions if p['id'] == ident), None)
            if part is None or component['size'] > part['size']:
                raise ValueError('Export component does not fit comparison partition')
            old = export_data[component['file_offset']:component['end_exclusive']]
            new = data[part['offset']:part['offset']+component['size']]
            diff = diff_runs(old, new)
            # MCUboot's final marker/trailer is mutable storage metadata; this is
            # a comparison only, not a claim that a modified image will boot.
            normal = bytearray(new)
            trailer_start = part['size']-32
            if trailer_start < len(normal):
                normal[trailer_start:] = old[trailer_start:]
            if len(normal) >= 16:
                normal[-16:] = old[-16:]
            comparisons.append({'component': component['name'], 'partition_id': ident,
                'export_sha256': component['sha256'], 'flash_sha256': sha(new),
                **diff, 'equal_after_restoring_export_trailer_bytes': bytes(normal) == old,
                'export_crc32': component['crc32'],
                'flash_raw_crc32': f'0x{zlib.crc32(new):08x}'})
        result['export_comparison'] = {'sha256': reference['sha256'], 'components': comparisons}
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--export', dest='exported', type=Path)
    args = parser.parse_args()
    try:
        result = inspect(args.image, args.exported)
    except (OSError, ValueError, struct.error) as exc:
        parser.exit(1, f'spi-layout: {exc}\n')
    print(json.dumps(result, indent=2))
