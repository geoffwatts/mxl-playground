#!/usr/bin/env python3
"""Reconstruct a clean, deterministic WSP build base from user-supplied V2 input.

No device backup, NVS, MAC or previous experimental artifacts are required.
The returned 8 MiB buffer is ONLY an internal build scaffold, never a SPI image.
No file-writing CLI is provided, to avoid mistaking the scaffold for recovery.
"""
import hashlib
import struct
import zlib
from build_dma_trace_candidate import jump,limm
from wsp_profile import load,admit

VENDOR_SHA=load()[0]['vendor_sha256']
CLEAN_SHA='8fe6e6c06a6226fe37814b5c1ae0172fb771a277dda6a17d4e0a22ab467345cb'


def prepare(vendor):
    admit(vendor)
    magic,ws,wcrc,gs,gcrc=struct.unpack_from('<5I',vendor)
    if magic!=0xf48bf48b or ws!=0x2d6000 or len(vendor)!=20+ws+gs:raise ValueError('Unexpected V2 layout')
    wsp=bytearray(vendor[20:20+ws])
    if zlib.crc32(wsp)!=wcrc or zlib.crc32(vendor[20+ws:])!=gcrc:raise ValueError('Invalid component CRC')
    original=bytes(wsp[0xf170c:0xf1778])
    if original[:8]!=bytes.fromhex('e4c228460a250090') or struct.unpack_from('<I',original,0x58)[0]!=0x25800040:raise ValueError('DMA helper differs')
    if any(wsp[0x600:0x66c]) or wsp[0xf198e:0xf1992]!=limm(0x70006ec0):raise ValueError('DMA clone area/caller differs')
    patches=[(0x600,original,'verbatim DMA clone'),(0xf170c,jump(0x40000600),'original DMA entry tail jump'),(0xf1764,struct.pack('<I',0x0001164a),'reserve original overlap as boot data')]
    ledger=[]
    for offset,value,purpose in patches:
        before=bytes(wsp[offset:offset+len(value)]);wsp[offset:offset+len(value)]=value
        ledger.append({'offset':hex(offset),'bytes':len(value),'purpose':purpose,'before_sha256':hashlib.sha256(before).hexdigest(),'after_sha256':hashlib.sha256(value).hexdigest()})
    scaffold=bytearray(b'\xff'*0x800000);scaffold[0xa000:0x2e0000]=wsp
    if hashlib.sha256(scaffold).hexdigest()!=CLEAN_SHA:raise ValueError('Clean scaffold does not match audited construction')
    return bytes(scaffold),ledger
