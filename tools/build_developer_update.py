#!/usr/bin/env python3
"""Offline clean build: user-supplied V2 update + public-key tag + standalone UI.

Only an inactive-slot update is emitted. No full SPI image, boot-record command,
network access or device-specific configuration is generated.
"""
import argparse
import hashlib
import json
from pathlib import Path
from prepare_native_base import prepare
from build_native_ui_firmware import build
from read_public_key import from_uart, validate_key_tag
from verify_firmware_signatures import verify_component


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--vendor',type=Path,required=True)
    keys=p.add_mutually_exclusive_group(required=True)
    keys.add_argument('--key-tag',type=Path,help='Acquired 76-byte secondary public-key record; not a private key')
    keys.add_argument('--key-log',type=Path,help='Own UART capture of chiptest mem_rd 0x00107000 19')
    p.add_argument('--html',type=Path,required=True)
    p.add_argument('--endpoints',type=Path,required=True)
    p.add_argument('--console-endpoint',type=Path,help='Optional independently decoded shared UART terminal')
    p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args()
    inputs=[a.vendor,a.key_tag or a.key_log,a.html,a.endpoints]
    if a.console_endpoint:inputs.append(a.console_endpoint)
    outputs=[a.output_dir/'native-ui-update-EXPERIMENTAL.bin',a.output_dir/'firmware-manifest.json']
    if any(o.resolve()==i.resolve() for o in outputs for i in inputs):raise ValueError('Output would overwrite an input')
    vendor=a.vendor.read_bytes();base,ledger=prepare(vendor)
    key=validate_key_tag(a.key_tag.read_bytes()) if a.key_tag else from_uart(a.key_log.read_text())
    factory_signature=verify_component(vendor[20:20+0x2d6000],key[8:72])
    if not factory_signature['signature_valid']:raise ValueError('Supplied public key does not verify the audited factory WSP')
    _,update,report=build(base,a.html.read_bytes(),vendor,key,a.endpoints.read_bytes(),a.console_endpoint.read_bytes() if a.console_endpoint else None)
    report.update({'clean_vendor_build':True,'vendor_sha256':hashlib.sha256(vendor).hexdigest(),'DMA_patches':ledger,'complete_spi_candidate':False,'boot_configuration_unchanged':True,'requires_existing_bootstrap':True})
    report.pop('spi_candidate_sha256',None)
    report['factory_WSP_signature']=factory_signature
    a.output_dir.mkdir(parents=True,exist_ok=True);outputs[0].write_bytes(update);outputs[1].write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['container_sha256','container_bytes','clean_vendor_build','complete_spi_candidate','requires_existing_bootstrap']},indent=2))

if __name__=='__main__':main()
