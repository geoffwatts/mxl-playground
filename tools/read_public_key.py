#!/usr/bin/env python3
"""Extract the observed public verification record from a user-supplied UART log.

Offline only. Capture `chiptest mem_rd 0x00107000 19` on the supported device.
No private key, vendor firmware, serial access or flash writes are involved.
"""
import re
import struct
import zlib


def validate_key_tag(tag):
    if len(tag) != 76 or tag[:8] != bytes.fromhex('a0005fff00000044'):
        raise ValueError('Expected 76-byte secondary A000 public-key record')
    if zlib.crc32(tag[8:72]) != int.from_bytes(tag[72:], 'little'):
        raise ValueError('Public-key record CRC mismatch')
    return tag


def from_uart(text):
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    data = bytearray()
    for line in text.splitlines():
        match = re.fullmatch(r'\s*Mem\(0x([0-9a-fA-F]+)\):\s*(.*?)\s*', line)
        if not match:
            continue
        address = int(match[1], 16)
        if not 0x00107000 <= address < 0x0010704c:
            continue
        words = match[2].split()
        if address != 0x00107000 + len(data) or not 1 <= len(words) <= 4:
            raise ValueError('Duplicated or out-of-order public-key read')
        if any(not re.fullmatch(r'0x[0-9a-fA-F]{8}', word) for word in words):
            raise ValueError('Malformed public-key word')
        data.extend(b''.join(struct.pack('<I', int(word, 16)) for word in words))
    return validate_key_tag(bytes(data))
