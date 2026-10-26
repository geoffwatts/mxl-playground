#!/usr/bin/env python3
"""Offline DNS lifetime experiment for one exact previously booted UI image.

Does not upload, write SPI, change boot records, or alter GPHY/settings.
The assembly source is firmware/dns_context_guard.S; review its independent
decode before installing. This deliberately is not a general image patcher.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

BASE_SHA = '92216f78380a9a54707fad7b14ac29b8b7363817fe4dae0398638e33433ec434'
GUARD = bytes.fromhex('c341f120b8a9081102001f0880001811020017088000281102000f0880002020800f05409c620c70e07e')
CALL = bytes.fromhex('2220800f05409c62')
PATCHED_CALL = bytes.fromhex('2220800f2c40006f')
SITE = 0x56a14
DEST = 0x2c6f00


def build(image, guard):
    if hashlib.sha256(image).hexdigest() != BASE_SHA:
        raise ValueError('Expected the exact previously booted firmware/UI image')
    if guard != GUARD:
        raise ValueError('Guard differs from the reviewed EM4 assembly')
    magic, ws, wc, gs, gc = struct.unpack_from('<5I', image)
    wsp, gphy = bytearray(image[20:20+ws]), image[20+ws:]
    if ((magic, ws, gs) != (0xf48bf48b, 0x2d6000, 0x29f40)
            or len(gphy) != gs or zlib.crc32(wsp) != wc or zlib.crc32(gphy) != gc):
        raise ValueError('Unexpected update framing/checksums')
    if wsp[SITE:SITE+8] != CALL or wsp[DEST:DEST+len(guard)] != b'\xff'*len(guard):
        raise ValueError('Native call or reserved extension padding differs')
    wsp[SITE:SITE+8] = PATCHED_CALL
    wsp[DEST:DEST+len(guard)] = guard
    return struct.pack('<5I',magic,ws,zlib.crc32(wsp),gs,gc)+wsp+gphy


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--guard', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    a = p.parse_args()
    image = build(a.image.read_bytes(), a.guard.read_bytes())
    a.output_dir.mkdir(parents=True, exist_ok=True)
    (a.output_dir/'dns-guard-update.bin').write_bytes(image)
    (a.output_dir/'manifest.json').write_text(json.dumps({
        'status':'OFFLINE EXPERIMENT; NOT INSTALLED',
        'input_sha256':BASE_SHA, 'output_sha256':hashlib.sha256(image).hexdigest(),
        'guard_sha256':hashlib.sha256(GUARD).hexdigest(),
        'patches':[{'wsp_offset':hex(SITE),'before':CALL.hex(),'after':PATCHED_CALL.hex()},
                   {'wsp_offset':hex(DEST),'before':'erased padding','after':GUARD.hex()}],
        'boot_record_touched':False,'gphy_changed':False,
        'note':'Only DNS-owned context pointers are excluded from native idle reclamation.'
    }, indent=2)+'\n')


if __name__ == '__main__':
    main()
