"""Exact-build SNTP recovery patch; native timers/resolver remain in charge."""
from build_dma_trace_candidate import limm

OFFSET = 0x2c7000
CODE = bytes.fromhex('f1c0c340f1208c190088e0b82c000100c340f52084ebc3422c4066702220800f0340c80111081000c341f1208c194089a0ba40a9d1c0e07ec340f120b8a9c341f1206c124c716c70c3440240b011c345f1208c19c3460000d0072220800f06400cc2d507cfff13081100c342f1208c19608aa0bb60aa2020800f0240e448c341000000fa2020800f0070b8dc')
# Only these native sites may change. Assembly is firmware/sntp_recovery.S.
PATCHES = (
    (0x248a0, bytes.fromhex('2220800f0340c801'), bytes.fromhex('2220800f') + limm(0x402c7000)),
    (0x2171e, bytes.fromhex('2220800f0070b8dc'), bytes.fromhex('2220800f') + limm(0x402c707e)),
    (0x2158a, bytes.fromhex('97081000'), bytes.fromhex('e078e078')),
    # DNS failure must not leave an enabled client with its periodic timer stopped.
    (0x11a86, bytes.fromhex('dd0910a0'), bytes.fromhex('e078e078')),
)


def apply(wsp):
    """Reject foreign or already-patched input before making any mutation."""
    if wsp[OFFSET:OFFSET+len(CODE)] != b'\xff' * len(CODE):
        raise ValueError('SNTP recovery window is not erased padding')
    for offset, before, _ in PATCHES:
        if wsp[offset:offset+len(before)] != before:
            raise ValueError('Unexpected native SNTP instructions at ' + hex(offset))
    wsp[OFFSET:OFFSET+len(CODE)] = CODE
    for offset, _, after in PATCHES:
        wsp[offset:offset+len(after)] = after


def normalize(wsp):
    """Validate and restore originals in the caller's disposable validation copy."""
    patched = any(wsp[at:at+len(before)] != before for at,before,_ in PATCHES)
    if patched:
        if (wsp[OFFSET:OFFSET+len(CODE)] != CODE or
                any(wsp[at:at+len(after)] != after for at,_,after in PATCHES)):
            raise ValueError('Unsupported SNTP recovery patch')
        for at,before,_ in PATCHES:
            wsp[at:at+len(before)] = before
        wsp[OFFSET:OFFSET+len(CODE)] = b'\xff'*len(CODE)
    return patched
