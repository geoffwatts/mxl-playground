#!/usr/bin/env python3
"""Place the standalone UI in verified WSP padding and retarget /setup.html.

Offline only. Retains the working DMA relocation and early skip arrangement.
Produces an experimental native update container, not a migration image.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

from build_dma_trace_candidate import limm
from build_dma_trace_candidate import jump
from verify_firmware_signatures import verify_component
from wsp_profile import load as load_wsp_profile
from build_dns_guard_candidate import GUARD as DNS_GUARD, CALL as DNS_CALL, PATCHED_CALL as DNS_PATCHED_CALL

CLEAN_BASE_SHA='8fe6e6c06a6226fe37814b5c1ae0172fb771a277dda6a17d4e0a22ab467345cb'
BASE_SHA='527f6dd536808fcfecba420ff5c391ab3a040e1615d328c04cf4fcabe87ab44f'
WSP_START=0xa000
WSP_SIZE=0x2d6000
ASSET=0x26a000
INVENTORY_SHA='805babe78b646e39445bc2654951c27c50f6337bf16ab981e9a600a884378081'
MANAGEMENT_PROBE_SHA='0ddb44e588234a7691fe21be56f0fbac527d6130c7ae5aa56c33378fcd246349'
PLATFORM_PROBE_SHA='180bf7129cc38e88a52aa53d9ab276254ed7a58eeb7928d88a35189d4100683a'
TIMER_OBSERVER_SHA='07732c224452b3897e11c5035e1d38eeeb924d8ea59544226862f09ceed08735'
IP_HOOK_OBSERVER_SHA='bb0f3e0217ec0a5fb7188ea323ef344619395163c00d8d4f3b35613eba3e14ef'
EGRESS_OBSERVER_SHA='f89237aefb4ddd37e1c997aaad92378eefcb58220c66dcad753a6b8b58ae9bf1'
RUNTIME_FULL_SHA='3fe9c6d5a16293ee7c28edb90389d5800293637edb5a08c98111763ac091c819'
RUNTIME_TRIAL_SHA='af04e4358e16d44a13cd83113719167dda3923dfe091fb1c1b7be66492419848'
SFP_SHA='c44640e73f83f70e1ecdfcf9eb66cf68b44998389aeba219788645703dac033d'
JUMBO_SHA='a2ea068058ce6d5ec8b5c6e062af449b8ba8d489d32b2bad89c8335f73d5cedb'
CONSOLE_SHA='bb5d240444e9f007f98108ff549829de1f6b559f7c67925bf4d7f940f918f91c'
LLDP_SHA='2d751cb5ac27c5dd7815136ab05a027553aceee68409ff8c81232ccb9e822a16'


def build(base,html,vendor,key,jumbo=None,console=None,lldp=None):
    base_digest=hashlib.sha256(base).hexdigest()
    if base_digest not in (BASE_SHA,CLEAN_BASE_SHA):
        raise ValueError('Expected the warm-boot-verified DMA relocation image')
    if b'<meta name="mxl-transport" content="native">' not in html or b'<script type="module">' not in html:
        raise ValueError('Expected a standalone native UI build')
    wsp=bytearray(base[WSP_START:WSP_START+WSP_SIZE])
    if wsp[0x15f70:0x15f76]!=bytes.fromhex('c3420000e448') or wsp[0x15f76:0x15f7c]!=bytes.fromhex('c3411e40f438'):
        raise ValueError('Setup callback differs from decoded pointer/length instructions')
    if ASSET+len(html)>WSP_SIZE-32 or any(v!=255 for v in wsp[ASSET:ASSET+len(html)]):
        raise ValueError('UI does not fit entirely in verified unused padding')
    if console is not None and ASSET+len(html)>0x2b0000:
        raise ValueError('UI overlaps the terminal code window')
    wsp[ASSET:ASSET+len(html)]=html
    wsp[0x15f72:0x15f76]=limm(len(html))
    wsp[0x15f78:0x15f7c]=limm(0x40000000+ASSET)
    # Serve the same self-contained application on the unauthenticated login
    # route. Its initial status probe selects sign-in or the authenticated UI.
    if wsp[0x1600c:0x16018]!=bytes.fromhex('c34200005220c3411b4044f4'):
        raise ValueError('Login callback differs from decoded pointer/length instructions')
    wsp[0x1600e:0x16012]=limm(len(html))
    wsp[0x16014:0x16018]=limm(0x40000000+ASSET)
    # The HTTP implementation reuses suffixes of the HTML header string,
    # including its final CRLF. Preserve that entire string; change only the
    # decoded max-age argument, from 0xe1 << 4 (3600 seconds) to zero.
    if wsp[0x1528c:0x1528e]!=bytes.fromhex('e1da'):
        raise ValueError('Unexpected HTML cache-age argument instruction')
    wsp[0x1528c]=0
    if jumbo is not None:
        if ASSET+len(html)>0x2c0000 or len(jumbo) not in (0xe00,0x1e00,0x3000,0x4000,0x5000,0x7000):
            raise ValueError('Jumbo endpoint overlaps UI or has an unexpected size')
        if any(v!=255 for v in wsp[0x2c0000:0x2c0000+len(jumbo)]):
            raise ValueError('Jumbo endpoint area is not unused padding')
        if wsp[0x16504:0x1650c]!=bytes.fromhex('e4c2cb460d40c0e5'):
            raise ValueError('Unexpected CivetWeb route-registration prologue')
        if (len(jumbo),hashlib.sha256(jumbo).hexdigest()) not in ((0xe00,JUMBO_SHA),(0x1e00,SFP_SHA),(0x3000,INVENTORY_SHA),(0x4000,MANAGEMENT_PROBE_SHA),(0x4000,PLATFORM_PROBE_SHA),(0x5000,TIMER_OBSERVER_SHA),(0x5000,IP_HOOK_OBSERVER_SHA),(0x5000,EGRESS_OBSERVER_SHA),(0x7000,RUNTIME_TRIAL_SHA),(0x7000,RUNTIME_FULL_SHA)):
            raise ValueError('Expected the instruction-verified jumbo endpoint')
        wsp[0x2c0000:0x2c0000+len(jumbo)]=jumbo
        wsp[0x16504:0x1650c]=jump(0x402c0000)
        if hashlib.sha256(jumbo).hexdigest() in (IP_HOOK_OBSERVER_SHA,EGRESS_OBSERVER_SHA,RUNTIME_TRIAL_SHA,RUNTIME_FULL_SHA):
            event,writer,magic=struct.unpack_from('<II4s',jumbo,0x3014)
            upper=0x402c6ff0 if hashlib.sha256(jumbo).hexdigest() in (RUNTIME_TRIAL_SHA,RUNTIME_FULL_SHA) else 0x402c5000
            if magic!=b'MVHI' or any(not 0x402c3020<=at<upper or at&1 for at in (event,writer)):
                raise ValueError('Invalid pinned native IP observer entry points')
            if wsp[0x24798:0x247a0]!=bytes.fromhex('0418800f02402043') or wsp[0x2474e:0x24756]!=bytes.fromhex('2220800f0a406c15'):
                raise ValueError('Native IP callback/writer sites differ from decoded instructions')
            wsp[0x2479c:0x247a0]=limm(event)
            wsp[0x2474e:0x24756]=bytes.fromhex('2220800f')+limm(writer)
        if hashlib.sha256(jumbo).hexdigest()==EGRESS_OBSERVER_SHA:
            magic,tx=struct.unpack_from('<4sI',jumbo,len(jumbo)-8)
            if magic!=b'MVTG' or not 0x402c3020<=tx<0x402c4ff8 or tx&1:
                raise ValueError('Invalid pinned TX observer entry')
            if wsp[0x377e6:0x377ee]!=bytes.fromhex('2220800f0440a4ed'):
                raise ValueError('Native bridge call differs from decoded instructions')
            wsp[0x377e6:0x377ee]=bytes.fromhex('2220800f')+limm(tx)
        if hashlib.sha256(jumbo).hexdigest() in (RUNTIME_TRIAL_SHA,RUNTIME_FULL_SHA):
            magic,tx,constructor,trial=struct.unpack_from('<4sIII',jumbo,len(jumbo)-16)
            if magic!=b'MVRT' or trial!=(2 if hashlib.sha256(jumbo).hexdigest()==RUNTIME_FULL_SHA else 1) or any(not 0x402c3020<=at<0x402c6ff0 or at&1 for at in (tx,constructor)):
                raise ValueError('Invalid pinned management trial hook entries')
            if wsp[0x377e6:0x377ee]!=bytes.fromhex('2220800f0440a4ed'):
                raise ValueError('Native bridge call differs from decoded instructions')
            if wsp[0x1559a:0x155a2]!=bytes.fromhex('2220800f0d4018e7'):
                raise ValueError('Native web constructor call differs from decoded instructions')
            wsp[0x377e6:0x377ee]=bytes.fromhex('2220800f')+limm(tx)
            wsp[0x1559a:0x155a2]=bytes.fromhex('2220800f')+limm(constructor)
        if hashlib.sha256(jumbo).hexdigest()==RUNTIME_FULL_SHA:
            if wsp[0x56a14:0x56a1c]!=DNS_CALL or wsp[0x2c6f00:0x2c6f00+len(DNS_GUARD)]!=b'\xff'*len(DNS_GUARD):
                raise ValueError('DNS cleanup call or reserved guard padding differs')
            wsp[0x56a14:0x56a1c]=DNS_PATCHED_CALL
            wsp[0x2c6f00:0x2c6f00+len(DNS_GUARD)]=DNS_GUARD
    if console is not None:
        if len(console)!=0x4000 or hashlib.sha256(console).hexdigest()!=CONSOLE_SHA:
            raise ValueError('Expected the independently decoded terminal endpoint')
        if jumbo is None or hashlib.sha256(jumbo).hexdigest()!=RUNTIME_FULL_SHA:
            raise ValueError('Terminal requires the audited full runtime registration chain')
        if wsp[0x2c300c:0x2c3014]!=jump(0x4001650c) or any(v!=255 for v in wsp[0x2b0000:0x2b4000]):
            raise ValueError('Console continuation or code window differs')
        wsp[0x2b0000:0x2b4000]=console
        wsp[0x2c300c:0x2c3014]=jump(0x402b0000)
    if lldp is not None:
        profile,_=load_wsp_profile();address,size=profile['lldp_region'];lldp_offset=address-profile['wsp_base'];hook=profile['lldp_hook']
        if console is None or len(lldp)!=size or hashlib.sha256(lldp).hexdigest()!=LLDP_SHA:
            raise ValueError('LLDP requires the audited terminal chain and pinned neighbour adapter')
        magic,receive,code_bytes=struct.unpack_from('<4sII',lldp,0x14)
        if magic!=b'LLDP' or not address+32<=receive<address+32+code_bytes or code_bytes>size-32:
            raise ValueError('Invalid LLDP entry table')
        if any(v!=255 for v in wsp[lldp_offset:lldp_offset+size]) or wsp[hook['offset']:hook['offset']+8]!=bytes.fromhex(hook['expected']):
            raise ValueError('LLDP code window or receive hook differs')
        if wsp[0x2b000c:0x2b0014]!=jump(profile['symbols']['registration_continue']):
            raise ValueError('Unexpected terminal registration continuation')
        wsp[lldp_offset:lldp_offset+size]=lldp
        wsp[hook['offset']:hook['offset']+8]=bytes.fromhex('2220800f')+limm(receive)
        wsp[0x2b000c:0x2b0014]=jump(address)
    # An anonymous/stale status request must not clear another user's session.
    # Keep rejection/expiry checks; make only those two failure memsets length 0.
    for off in (0x1b434,0x1b582):
        if wsp[off:off+2]!=bytes.fromhex('80da'):
            raise ValueError('Unexpected session-clear argument instruction')
        wsp[off]=0
    if wsp[:0x6d8]!=base[WSP_START:WSP_START+0x6d8]:
        raise ValueError('DMA relocation header changed')
    # Use precisely the signed, unchanged GPHY component from the vendor update.
    magic,ws,wcrc,gs,gcrc=struct.unpack_from('<5I',vendor)
    if magic!=0xf48bf48b or len(vendor)!=20+ws+gs or zlib.crc32(vendor[20:20+ws])!=wcrc:
        raise ValueError('Invalid vendor update framing')
    gphy=vendor[20+ws:]
    if zlib.crc32(gphy)!=gcrc:
        raise ValueError('Vendor GPHY checksum mismatch')
    signature=verify_component(bytes(wsp),key[8:72])
    if signature['signature_valid']:
        raise ValueError('Unexpected signature success after custom assets')
    # Clear slot-local state/CRC metadata exactly as native update exports do.
    # The updater creates metadata for its destination. This trailer is outside
    # the authenticated coverage and is distinct from the fixed final marker.
    update_wsp=bytearray(wsp)
    update_wsp[-32:-16]=b'\xff'*16
    container=struct.pack('<5I',magic,len(update_wsp),zlib.crc32(update_wsp),len(gphy),gcrc)+bytes(update_wsp)+gphy
    spi=bytearray(base);spi[WSP_START:WSP_START+WSP_SIZE]=wsp
    if spi[:WSP_START]!=base[:WSP_START] or spi[0x2e0000:]!=base[0x2e0000:]:
        raise ValueError('Change escaped active WSP')
    regions=[(ASSET,len(html),'standalone HTML/CSS/JS'),(0x15f72,4,'setup length'),(0x15f78,4,'setup pointer'),(0x1600e,4,'login length'),(0x16014,4,'login pointer'),(0x1528c,2,'cache age'),(0x1b434,2,'session failure clear A'),(0x1b582,2,'session failure clear B')]
    if jumbo is not None:regions.extend([(0x16504,8,'registration entry'),(0x2c0000,len(jumbo),'bounded native endpoints')])
    if jumbo is not None and hashlib.sha256(jumbo).hexdigest() in (IP_HOOK_OBSERVER_SHA,EGRESS_OBSERVER_SHA,RUNTIME_TRIAL_SHA,RUNTIME_FULL_SHA):
        regions.extend([(0x2479c,4,'native IP callback target'),(0x2474e,8,'native IP write call')])
    if jumbo is not None and hashlib.sha256(jumbo).hexdigest() in (EGRESS_OBSERVER_SHA,RUNTIME_TRIAL_SHA,RUNTIME_FULL_SHA):
        regions.append((0x377e6,8,'native bridge call'))
    if jumbo is not None and hashlib.sha256(jumbo).hexdigest() in (RUNTIME_TRIAL_SHA,RUNTIME_FULL_SHA):
        regions.append((0x1559a,8,'native web constructor call'))
    if jumbo is not None and hashlib.sha256(jumbo).hexdigest()==RUNTIME_FULL_SHA:
        regions.append((0x56a14,8,'preserve resolver-owned UDP contexts during idle cleanup'))
    if console is not None:
        regions.extend([(0x2b0000,0x4000,'shared UART terminal endpoint'),(0x2c300c,8,'terminal registration continuation')])
    if lldp is not None:
        regions.extend([(lldp_offset,size,'LLDP neighbour cache and profile adapter'),(hook['offset'],8,'LLDP receive observer'),(0x2b000c,8,'LLDP registration continuation')])
    ledger=[]
    for offset,length,purpose in regions:
        before=base[WSP_START+offset:WSP_START+offset+length];after=bytes(wsp[offset:offset+length])
        ledger.append({'offset':hex(offset),'bytes':length,'purpose':purpose,'before_sha256':hashlib.sha256(before).hexdigest(),'after_sha256':hashlib.sha256(after).hexdigest()})
    return bytes(spi),container,{
        'status':'OFFLINE BUILT; NOT INSTALLED', 'base_sha256':base_digest,'complete_spi_candidate':base_digest==BASE_SHA,'component_patches':ledger,
        'ui_sha256':hashlib.sha256(html).hexdigest(),'ui_bytes':len(html),
        'asset_component_offset':hex(ASSET),'asset_virtual_address':hex(0x40000000+ASSET),
        'callback':'40015f64','route':'/setup.html',
        'login_callback':'40016000','login_reuses_same_standalone_asset':True,
        'html_cache_control':'max-age=0; original header template preserved',
        'sfp_snapshot_endpoint':jumbo is not None and len(jumbo)>=0x1e00,
        'native_inventory_endpoint':jumbo is not None and len(jumbo)>=0x3000,
        'read_only_management_probe':jumbo is not None and len(jumbo) in (0x4000,0x5000),
        'read_only_platform_probe':jumbo is not None and hashlib.sha256(jumbo).hexdigest() in (PLATFORM_PROBE_SHA,TIMER_OBSERVER_SHA,IP_HOOK_OBSERVER_SHA,EGRESS_OBSERVER_SHA),
        'native_timer_observer':jumbo is not None and hashlib.sha256(jumbo).hexdigest() in (TIMER_OBSERVER_SHA,IP_HOOK_OBSERVER_SHA,EGRESS_OBSERVER_SHA),
        'native_ip_hook_observer':jumbo is not None and hashlib.sha256(jumbo).hexdigest() in (IP_HOOK_OBSERVER_SHA,EGRESS_OBSERVER_SHA),
        'native_egress_observer':jumbo is not None and hashlib.sha256(jumbo).hexdigest()==EGRESS_OBSERVER_SHA,
        'management_vlan_runtime_trial':jumbo is not None and hashlib.sha256(jumbo).hexdigest()==RUNTIME_TRIAL_SHA,
        'management_vlan_runtime_full':jumbo is not None and hashlib.sha256(jumbo).hexdigest()==RUNTIME_FULL_SHA,
        'management_vlan_durable_writes':jumbo is not None and hashlib.sha256(jumbo).hexdigest()==RUNTIME_FULL_SHA,
        'dns_context_lifetime_guard':jumbo is not None and hashlib.sha256(jumbo).hexdigest()==RUNTIME_FULL_SHA,
        'shared_uart_terminal':console is not None,
        'lldp_neighbour_cache':lldp is not None,
        'wsp_profile':load_wsp_profile()[0]['id'],
        'jumbo_endpoint_sha256':hashlib.sha256(jumbo).hexdigest() if jumbo is not None else None,
        'patched_literals':{'length':'15f72..15f76','pointer':'15f78..15f7c'},
        'container_sha256':hashlib.sha256(container).hexdigest(),'container_bytes':len(container),
        'spi_candidate_sha256':hashlib.sha256(spi).hexdigest(),
        'WSP_signature':signature,'GPHY_unchanged_from_vendor':True,
        'update_slot_metadata_cleared':True,
        'session_failure_clear_disabled':['1b434: 80da -> 00da','1b582: 80da -> 00da'],
        'boot_configuration_unchanged':True,'DMA_relocation_preserved':True,
        'warning':'Requires the existing experimental WSP verification skip; not for stock signed-only boot.',
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,required=True)
    p.add_argument('--html',type=Path,default=Path('artifacts/native-ui/switch-ui.html'))
    p.add_argument('--vendor',type=Path,default=Path('artifacts/candidates/xikestor-upload/wsp_mxl862xx_update_image_fca.bin'))
    p.add_argument('--key-tag',type=Path,default=Path('artifacts/spi/internal-secondary-a000.bin'))
    p.add_argument('--jumbo-endpoint',type=Path,help='Optional instruction-verified native endpoint binary')
    p.add_argument('--console-endpoint',type=Path,help='Optional instruction-verified shared UART terminal')
    p.add_argument('--lldp-endpoint',type=Path,help='Optional instruction-verified LLDP cache')
    p.add_argument('--output-dir',type=Path,default=Path('artifacts/native-ui'))
    a=p.parse_args()
    spi,update,report=build(a.base.read_bytes(),a.html.read_bytes(),a.vendor.read_bytes(),a.key_tag.read_bytes(),a.jumbo_endpoint.read_bytes() if a.jumbo_endpoint else None,a.console_endpoint.read_bytes() if a.console_endpoint else None,a.lldp_endpoint.read_bytes() if a.lldp_endpoint else None)
    a.output_dir.mkdir(parents=True,exist_ok=True)
    if report['complete_spi_candidate']:(a.output_dir/'native-ui-spi-EXPERIMENTAL.bin').write_bytes(spi)
    (a.output_dir/'native-ui-update-EXPERIMENTAL.bin').write_bytes(update)
    (a.output_dir/'firmware-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
