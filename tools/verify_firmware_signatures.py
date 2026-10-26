#!/usr/bin/env python3
"""Read-only verification of observed chain-free F48B/BLp2 firmware.

Requires cryptography. Secondary-key-tag is the acquired 76-byte A000 TLV.
Does not establish boot-ROM policy, board compatibility or flashability.
"""
import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils

from spi_layout import parse_tags


def verify_component(data, key):
    if len(key) != 64 or len(data) < 0x800:
        raise ValueError('Invalid key/component length')
    header = data[0x6d8:0x7e0]
    if header[:4] != b'BLp\x02' or int.from_bytes(header[0x104:0x108], 'big'):
        raise ValueError('Only observed BLp2 components with zero chain depth supported')
    size = int.from_bytes(header[0xc0:0xc4], 'big')
    if not size or 0x7e0 + size > len(data):
        raise ValueError('Signed data outside component')
    digest = hashlib.sha256(header[0xc4:0x104] + data[0x7e0:0x7e0+size]).digest()
    public = ec.EllipticCurvePublicNumbers(
        int.from_bytes(key[:32], 'big'), int.from_bytes(key[32:], 'big'),
        ec.SECP256R1()).public_key()
    signature = utils.encode_dss_signature(
        int.from_bytes(header[8:40], 'big'), int.from_bytes(header[40:72], 'big'))
    try:
        public.verify(signature, digest, ec.ECDSA(utils.Prehashed(hashes.SHA256())))
        valid = True
    except InvalidSignature:
        valid = False
    return {'signature_valid': valid, 'signed_digest': digest.hex(),
            'key_sha256': hashlib.sha256(key).hexdigest(),
            'metadata_prefix_offset': '0x79c', 'metadata_prefix_length': 64,
            'signed_data_offset': '0x7e0', 'signed_data_length': size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spi-dump', type=Path, required=True)
    parser.add_argument('--secondary-key-tag', type=Path, required=True)
    parser.add_argument('images', type=Path, nargs='+')
    args = parser.parse_args()
    spi = args.spi_dump.read_bytes()
    primary = next(t for t in parse_tags(spi) if t['tag'] == '0xa100')
    off = primary['payload_offset']
    gphy_key = spi[off:off+64]
    secondary = args.secondary_key_tag.read_bytes()
    if len(secondary) != 76 or struct.unpack('>HHI', secondary[:8]) != (0xa000, 0x5fff, 68):
        raise ValueError('Invalid secondary A000 TLV')
    wsp_key = secondary[8:72]
    for key, crc in [(wsp_key, secondary[72:76]), (gphy_key, spi[off+64:off+68])]:
        if zlib.crc32(key) != int.from_bytes(crc, 'little'):
            raise ValueError('Key CRC mismatch')
    results = []
    for path in args.images:
        raw = path.read_bytes()
        magic, ws, wc, gs, gc = struct.unpack_from('<5I', raw)
        if magic != 0xf48bf48b or len(raw) != 20+ws+gs:
            raise ValueError('Expected exact-length F48B container')
        wsp, gphy = raw[20:20+ws], raw[20+ws:]
        if zlib.crc32(wsp) != wc or zlib.crc32(gphy) != gc:
            raise ValueError('Component CRC mismatch')
        results.append({'image': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                        'WSP': verify_component(wsp, wsp_key),
                        'GPHY': verify_component(gphy, gphy_key)})
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
