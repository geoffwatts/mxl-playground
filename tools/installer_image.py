"""Strict, offline admission for the supported full-runtime installer profile."""
import hashlib
import struct
import zlib
from build_dma_trace_candidate import jump, limm
from build_dns_guard_candidate import GUARD, PATCHED_CALL
from prepare_native_base import prepare
from upload_native_ui import expected_ui_digest

WSP_SIZE = 0x2d6000
RUNTIME_SHA = '3fe9c6d5a16293ee7c28edb90389d5800293637edb5a08c98111763ac091c819'
CONSOLE_SHA = 'bb5d240444e9f007f98108ff549829de1f6b559f7c67925bf4d7f940f918f91c'
RANGES = [(0x26a000,0x56000),(0x2c0000,0x7000),(0x15f72,4),(0x15f78,4),
          (0x1600e,4),(0x16014,4),(0x1528c,2),(0x1b434,2),(0x1b582,2),
          (0x16504,8),(0x2479c,4),(0x2474e,8),(0x377e6,8),(0x1559a,8),
          (0x2d5fe0,32),(0x56a14,8)]
CANONICAL = {'b28b7d1b3142686fb8b401aaef7dbc843daf92d8e3e8e3d57b243154470ffbab',
             'd3c930f31f5aa5ee9270549c12e724b643b7874f32ede6508fe5b764474731ea'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def components(image):
    if len(image) < 20:
        raise ValueError('Truncated update')
    magic,ws,wc,gs,gc = struct.unpack_from('<5I',image)
    if (magic,ws,gs) != (0xf48bf48b,WSP_SIZE,0x29f40) or len(image) != 20+ws+gs:
        raise ValueError('Expected exact supported V2 update layout')
    wsp,gphy = image[20:20+ws],image[20+ws:]
    if zlib.crc32(wsp) != wc or zlib.crc32(gphy) != gc:
        raise ValueError('Update CRC mismatch')
    return wsp,gphy


def canonical(wsp):
    data = bytearray(wsp)
    for offset,size in RANGES:
        data[offset:offset+size] = bytes(size)
    return sha(data)


def validate_custom(image, vendor, expected=None, allow_development=False):
    if expected is not None and sha(image) != expected:
        raise ValueError('Selected update SHA-256 mismatch')
    base,_ = prepare(vendor)  # Pins exact factory input and DMA original bytes.
    reference = base[0xa000:0x2e0000]
    wsp,gphy = components(image)
    _,factory_gphy = components(vendor)
    if gphy != factory_gphy:
        raise ValueError('GPHY differs from audited factory component')
    digest = canonical(wsp)
    if digest not in CANONICAL or (not allow_development and digest != canonical(reference)):
        raise ValueError('WSP differs outside admitted patch areas / clean build required')
    if wsp[0x600:0x66c] != reference[0x600:0x66c] or wsp[0xf170c:0xf1778] != reference[0xf170c:0xf1778]:
        raise ValueError('DMA relocation differs')
    ui_sha = expected_ui_digest(image)
    size = (struct.unpack_from('<H',wsp,0x15f72)[0]<<16)|struct.unpack_from('<H',wsp,0x15f74)[0]
    if size > 0x46000:
        raise ValueError('UI overlaps terminal window')
    if sha(wsp[0x2b0000:0x2b4000]) != CONSOLE_SHA:
        raise ValueError('Expected audited terminal extension')
    runtime = bytearray(wsp[0x2c0000:0x2c7000])
    if runtime[0x300c:0x3014] != jump(0x402b0000) or runtime[0x6f00:0x6f00+len(GUARD)] != GUARD:
        raise ValueError('Registration chain / DNS guard differs')
    runtime[0x300c:0x3014] = jump(0x4001650c)
    runtime[0x6f00:0x6f00+len(GUARD)] = b'\xff'*len(GUARD)
    if sha(runtime) != RUNTIME_SHA:
        raise ValueError('Expected audited full management runtime')
    event,writer,magic = struct.unpack_from('<II4s',runtime,0x3014)
    marker,tx,constructor,version = struct.unpack_from('<4sIII',runtime,len(runtime)-16)
    if (magic,marker,version) != (b'MVHI',b'MVRT',2):
        raise ValueError('Unexpected runtime entry table')
    patches = [(0x16504,jump(0x402c0000)),(0x2479c,limm(event)),
               (0x2474e,b'\x22\x20\x80\x0f'+limm(writer)),
               (0x377e6,b'\x22\x20\x80\x0f'+limm(tx)),
               (0x1559a,b'\x22\x20\x80\x0f'+limm(constructor)),
               (0x56a14,PATCHED_CALL),(0x1528c,bytes.fromhex('00da')),
               (0x1b434,bytes.fromhex('00da')),(0x1b582,bytes.fromhex('00da'))]
    for offset,value in patches:
        if wsp[offset:offset+len(value)] != value:
            raise ValueError('Unexpected hook/instruction at '+hex(offset))
    if wsp[-16:] != reference[-16:]:
        raise ValueError('Selected update end marker differs')
    if wsp[-32:-16] != b'\xff'*16:
        raise ValueError('Selected update must have cleared slot-local metadata')
    return {'sha256':sha(image),'ui_sha256':ui_sha,'clean_build':digest==canonical(reference),
            'DMA_relocation_verified':True,'native_extensions_verified':True,'GPHY_unchanged':True}


def validate_running(image, vendor, record):
    wsp,gphy = components(image)
    factory_wsp,factory_gphy = components(vendor)
    if gphy != factory_gphy:
        raise ValueError('Running export GPHY differs')
    if wsp[:-32] == factory_wsp[:-32] and wsp[-16:] == factory_wsp[-16:]:
        return 'factory'
    if record != 'experimental-skip':
        raise ValueError('Stock boot record requires exact factory WSP export')
    # Exports carry destination-local metadata; only this 16-byte field differs.
    normalized = wsp[:-32]+b'\xff'*16+wsp[-16:]
    custom = struct.pack('<5I',0xf48bf48b,len(normalized),zlib.crc32(normalized),len(gphy),zlib.crc32(gphy))+normalized+gphy
    validate_custom(custom,vendor,allow_development=True)
    return 'audited-custom'
