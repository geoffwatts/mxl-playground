#!/usr/bin/env python3
"""Experimental supported-V2 bootstrap + web install, or serial-only WSP staging.

Dry-run by default. No partition migration, boot-record reversal, RAM writes,
blind retries, or forced reboot. Keep an external SPI recovery path available.
"""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shlex
import struct
import subprocess
import sys
import threading
import time

from inspect_bootstrap import BOOT_SIZE, PATCH_RECORD, V2_MAP, clean, parse_hex, parse_map, validate
from installer_uart import PATCH_COMMAND, WSP_AREAS
from installer_image import components, prepare, sha, validate_custom, validate_running
from switch_transport import SwitchTransport
from upload_native_ui import ChunkClient, validate_target, verify_served_ui

WARNING = ('Only flash if you have a compatible SPI programmer, or can obtain one quickly '
           '(for example overnight from Amazon where available). UART recovery needs a '
           'working WSP shell; it cannot rescue a WSP that fails before the shell starts.')


class Journal:
    def __init__(self, directory):
        self.path=Path(directory)
        self.path.mkdir(mode=0o700,parents=True,exist_ok=False)
        self.data={'format':'mxl-serial-installer/v1','state':'PREPARING','boot_patch_reversal':False,
                   'automatic_write_retries':False,'automatic_reboot':False,'events':[]}
        self.save()

    def file(self,name,data):
        fd=os.open(self.path/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as out:
            out.write(data);out.flush();os.fsync(out.fileno())

    def save(self):
        temp=self.path/'state.tmp'
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as out:
            json.dump(self.data,out,indent=2);out.write('\n');out.flush();os.fsync(out.fileno())
        os.replace(temp,self.path/'state.json')

    def state(self,state,**fields):
        self.data.update(fields,state=state)
        self.data['events'].append({'state':state,'time':time.time()})
        self.save()
        if state!='WEB CHUNK MAY BE IN PROGRESS; NO RETRY':print(state,flush=True)


class UART:
    """One persistent local/SSH serial owner; background output is logged locally."""
    def __init__(self,args,journal):
        self.messages=queue.Queue();self.lock=threading.Lock();self.text=''
        fd=os.open(journal.path/'uart.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        self.log=os.fdopen(fd,'w',buffering=1)
        root=Path(__file__).resolve().parent
        inspector=(root/'inspect_bootstrap.py').read_text().split("\nif __name__ == '__main__':")[0]
        agent=(root/'installer_uart.py').read_text().replace('from inspect_bootstrap import SerialShell, BOOT_SIZE\n','')
        agent=agent.split("\nif __name__=='__main__':")[0]
        source=inspector+'\n'+agent+'\nagent()\n'
        command=['python3','-u','-c',source,'--port',args.port]
        if args.install:command+=['--write']
        if args.serial_wsp:command+=['--slot',str(args.wsp_slot)]
        if args.ssh:
            if args.ssh.startswith('-') or not re.fullmatch(r'[\w.@:-]+',args.ssh):
                raise ValueError('Invalid SSH destination')
            remote=shlex.join(command)
            command=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5']
            if args.ssh_interface:command+=['-B',args.ssh_interface]
            command += [args.ssh,remote]
        self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE,text=True,bufsize=1)
        self.thread=threading.Thread(target=self._read,daemon=True);self.thread.start()
        try:
            result=self.messages.get(timeout=15)
            if result != {'ready':True}:raise RuntimeError('UART agent did not start')
        except BaseException:
            self.close();raise

    def _record(self,text):
        with self.lock:
            self.text=(self.text+text)[-2_000_000:]
            self.log.write(text)

    def _read(self):
        try:
            for line in self.process.stdout:
                value=json.loads(line)
                if 'uart' in value:self._record(value['uart'])
                else:
                    if 'response' in value:self._record(value['response'])
                    self.messages.put(value)
        except Exception:
            pass
        finally:
            self.messages.put({'error':'UART transport ended; no command retry'})

    def command(self,command):
        self._record('\n>>> '+command+'\n')
        self.process.stdin.write(json.dumps({'command':command})+'\n');self.process.stdin.flush()
        value=self.messages.get(timeout=30)
        if 'error' in value:raise RuntimeError(value['error'])
        return value['response']

    def close(self):
        if not self.process.stdin.closed:self.process.stdin.close()
        if self.process.poll() is None:
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        self.thread.join(timeout=2)
        self.process.stdout.close()
        self.process.stderr.close()
        self.log.close()


def read_flash(uart,start,size):
    if start%256 or size%256:raise ValueError('Installer reads require aligned 256-byte blocks')
    data=bytearray()
    for offset in range(start,start+size,256):
        data.extend(parse_hex(uart.command(f'flash read flash_mxl {offset:#x} -d 0x100'),offset,256))
    return bytes(data)


def interface_identity(text):
    text=clean(text)
    macs=re.findall(r'^Link addr\s*:\s*([0-9A-Fa-f:]{17})\s*$',text,re.M)
    if len(macs)!=1 or '[1]' not in text:raise ValueError('Expected exactly interface 1 identity')
    return re.sub('[^0-9a-f]','',macs[0].lower())


def active_slot(text):
    match=re.findall(r'^Mem\(0xd0e3d424\):\s*0x([0-9a-fA-F]{8})\s*$',clean(text),re.M)
    if len(match)!=1:raise ValueError('Incomplete active WSP base register read')
    offsets={start:slot for slot,(start,_) in WSP_AREAS.items()}
    if int(match[0],16) not in offsets:raise ValueError('Unknown active WSP base register')
    return offsets[int(match[0],16)]


def verify_write(response,erase=False):
    text=clean(response)
    required=['Erase success.'] if erase else ['Write OK.','Verified.']
    if any(part not in text for part in required) or re.search(r'error|fail',text,re.I):
        raise RuntimeError('Native flash command did not verify; no retry/reboot')


def unrestricted_policy(data):
    if (len(data)!=128 or data[:8]!=b'MVCT\x02\x02\x00\x01'
            or any(data[8:16]) or struct.unpack_from('<I',data,44)[0]
            or struct.unpack_from('<i',data,72)[0]):
        raise ValueError('Disable and save management VLAN isolation before a web install')


def patch_boot(uart,before,journal):
    # Recheck the complete sector immediately before its only permitted edit.
    if read_flash(uart,0,4096)!=before[:4096]:raise ValueError('Boot sector changed since preflight')
    journal.state('BOOT PATCH MAY BE IN PROGRESS; DO NOT REBOOT')
    response=uart.command(PATCH_COMMAND)
    verify_write(response)
    if 'Read OK.' not in clean(response) or 'Erase OK.' not in clean(response):
        raise RuntimeError('Incomplete boot-sector operation acknowledgement')
    after=read_flash(uart,0,4096)
    journal.file('after-boot-sector.bin',after)
    expected=before[:0x264]+PATCH_RECORD+before[0x28c:4096]
    if after!=expected:raise ValueError('Boot sector readback differs; no rollback/reboot')
    journal.state('BOOT PATCH VERIFIED; MATCHING WSP STILL REQUIRED')


def serial_wsp(uart,slot,wsp,journal):
    """Stage only an inactive WSP. Last-sector magic is committed after readback."""
    if active_slot(uart.command('chiptest mem_rd 0xd0e3d424 1'))==slot:
        raise ValueError('Refusing to erase the running WSP slot')
    start,size=WSP_AREAS[slot]
    if len(wsp)!=size:raise ValueError('Wrong WSP size')
    # First invalidate the destination's end marker. Then erase/program each
    # remaining sector once. Never erase/program the active slot or GPHY.
    last=start+size-4096
    journal.state('SERIAL WSP ERASE MAY BE IN PROGRESS',destination_slot=slot)
    verify_write(uart.command(f'flash erase flash_mxl {last:#x} 0x1000'),erase=True)
    for offset in range(0,size,4096):
        at=start+offset
        journal.data['sector_offset']=hex(at);journal.save()
        if at!=last:verify_write(uart.command(f'flash erase flash_mxl {at:#x} 0x1000'),erase=True)
        sector=wsp[offset:offset+4096]
        if at==last:sector=sector[:-16]+b'\xff'*16
        for delta in range(0,4096,128):
            part=sector[delta:delta+128]
            if part==b'\xff'*len(part):continue
            words=struct.unpack('<32I',part)
            command=f'flash write flash_mxl {at+delta:#x} '+' '.join(f'{word:08x}' for word in words)
            verify_write(uart.command(command))
        if read_flash(uart,at,4096)!=sector:raise ValueError('Serial sector readback mismatch; no retry')
        if offset%0x10000==0:print(f'Serial WSP verified {offset+4096}/{size}',flush=True)
    journal.state('SERIAL WSP BODY VERIFIED; COMMITTING END MARKER')
    words=struct.unpack('<4I',wsp[-16:])
    verify_write(uart.command(f'flash write flash_mxl {start+size-16:#x} '+' '.join(f'{word:08x}' for word in words)))
    if read_flash(uart,start+size-256,256)!=wsp[-256:]:raise ValueError('Final serial trailer readback mismatch')
    journal.state('SERIAL WSP STAGED AND READ BACK; NOT REBOOTED OR BOOT-VERIFIED',wsp_sha256=sha(wsp))


def web_upload(image,client,journal):
    for offset in range(0,len(image),41000):
        journal.state('WEB CHUNK MAY BE IN PROGRESS; NO RETRY',chunk_offset=offset)
        part=image[offset:offset+41000]
        result=client.post(part,90 if offset==0 else 20)
        journal.data.setdefault('chunks',[]).append(dict(result,offset=offset,bytes=len(part)));journal.save()
        body=result['response']
        if result['transport_error'] or result['http_status']!=200 or re.search(r'Failure|\b400\b',body,re.I):
            raise RuntimeError('Web upload failed/ambiguous; no retry or forced reboot')
        success='Verification: Success. System is rebooting.' in body
        if success and offset+len(part)!=len(image):raise RuntimeError('Premature updater success')
        if offset+len(part)==len(image) and not success:raise RuntimeError('Missing final updater success')
    journal.state('UPDATER REPORTED SUCCESS; WAITING FOR BOOT')


def run(args,uart,journal,image,vendor,backup,http=None):
    image_info=validate_custom(image,vendor,args.expected_sha256)
    version=uart.command('kernel version')
    firmware=uart.command('chiptest firmware_ver')
    if 'WSP firmware version: 1.0.79.79' not in clean(firmware):raise ValueError('Unsupported running WSP version')
    mapping=uart.command('flash_map list')
    parse_map(mapping)
    boot=read_flash(uart,0,BOOT_SIZE)
    journal.file('before-boot-area.bin',boot)
    admission=validate(backup,boot,mapping)
    journal.data.update(image=image_info,preflight=admission)
    current=active_slot(uart.command('chiptest mem_rd 0xd0e3d424 1'))
    identity=uart.command('net iface show 1')
    mac=interface_identity(identity)
    journal.file('profile.txt',(version+'\n'+firmware+'\n'+mapping+'\n'+identity).encode())
    journal.state('SERIAL TARGET ADMITTED',active_wsp_slot=current)
    if args.serial_wsp:
        if args.wsp_slot==current:raise ValueError('Requested serial destination is the running WSP slot')
        if admission['live_record']!='experimental-skip':
            raise ValueError('Serial-only recovery requires an already-patched boot record; use coordinated web bootstrap first')
        # Pin the native flash shell and active-slot reader before trusting them.
        original,_=components(vendor)
        for lo,hi in [(0x71800,0x72500),(0x88c00,0x89100)]:
            if read_flash(uart,WSP_AREAS[current][0]+lo,hi-lo)!=original[lo:hi]:
                raise ValueError('Running flash shell/slot-reader code differs from audited factory')
        # GPHY is deliberately not programmed; verify its exported component,
        # ignoring only slot-local metadata at the component/area trailers.
        _,factory_gphy=components(vendor)
        for gpstart in (0x2e0000,0x5e3000):
            gphy=read_flash(uart,gpstart,0x2a000)[:0x29f40]
            marker=read_flash(uart,gpstart+0x2cf00,256)[-16:]
            if (gphy[:-32]!=factory_gphy[:-32] or gphy[-16:]!=factory_gphy[-16:]
                    or marker!=factory_gphy[-16:]):
                raise ValueError('Both GPHY banks must match supported 0063; serial mode never repairs GPHY')
        journal.state('SERIAL RECOVERY PLAN READY',destination_slot=args.wsp_slot)
        if not args.install:
            journal.state('SERIAL RECOVERY DRY RUN COMPLETE; NO FLASH OR RAM WRITES')
            return
        serial_wsp(uart,args.wsp_slot,components(image)[0],journal)
        if read_flash(uart,0,BOOT_SIZE)!=boot:raise ValueError('Boot area changed during serial staging')
        return
    status=http.login(args.username,args.password)
    validate_target(status,http.request('/port_setting_load.json')['data'])
    httpmac=re.sub('[^0-9a-f]','',str(status.get('sys_macaddr','')).lower())
    if httpmac!=mac:raise ValueError('UART and HTTP MAC identities differ or are missing')
    running=http.request('/firmware/download',binary=True)['bytes']
    journal.file('running-update.bin',running)
    journal.data['running_kind']=validate_running(running,vendor,admission['live_record'])
    if journal.data['running_kind']=='audited-custom':
        unrestricted_policy(http.request('/management-vlan.json',binary=True)['bytes'])
    journal.state('SERIAL + HTTP TARGET AND RUNNING IMAGE VERIFIED')
    if not args.install:
        journal.state('DRY RUN COMPLETE; NO FLASH OR RAM WRITES')
        return
    # Prepare the HTTP client before boot mutation; never authenticate or prompt
    # between the patch and matched upload. No inter-chunk serial inspection.
    client=ChunkClient(http.address,http.cookie)
    try:
        if admission['live_record']=='stock':patch_boot(uart,boot,journal)
        else:journal.state('BOOT RECORD ALREADY PATCHED; NO BOOT WRITE')
        web_upload(image,client,journal)
    finally:client.close()
    time.sleep(8)
    verification=verify_served_ui(http,image_info['ui_sha256'],timeout=180)
    journal.data['http_ui_verification']=verification
    if not verification['matched']:raise RuntimeError('Post-upload UI not verified; no write retry')
    after=read_flash(uart,0,BOOT_SIZE)
    journal.file('after-boot-area.bin',after)
    expected=boot[:0x264]+PATCH_RECORD+boot[0x28c:]
    if after!=expected:raise ValueError('Postboot boot area differs')
    selected=active_slot(uart.command('chiptest mem_rd 0xd0e3d424 1'))
    uart_boot=(selected!=current and 'Start WSP' in uart.text
               and 'DMA RX UP' in uart.text and 'DMA TX UP' in uart.text)
    journal.data.update(selected_wsp_slot=selected,uart_boot_verified=uart_boot)
    if not uart_boot:raise RuntimeError('UI matches, but new-slot UART startup was not established; no retry/reboot')
    journal.state('INSTALL COMPLETE; NEW-SLOT UART BOOT, UI AND BOOT RECORD VERIFIED; FORWARDING NOT TESTED')


def main():
    p=argparse.ArgumentParser(description=__doc__,epilog=WARNING)
    for name in ('vendor','image','backup'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--expected-sha256',required=True)
    p.add_argument('--port',required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--address',help='HTTP management IPv4; not used with --serial-wsp')
    p.add_argument('--username',default='admin')
    p.add_argument('--password-env',default='MXL_UI_PASSWORD')
    p.add_argument('--ssh',help='Optional host used solely as UART transport')
    p.add_argument('--ssh-interface',help='Local interface for SSH, e.g. en0')
    p.add_argument('--install',action='store_true',help='Enable writes; otherwise read-only dry run')
    p.add_argument('--spi-recovery-available',action='store_true',help='Acknowledge the SPI programmer requirement')
    p.add_argument('--serial-wsp',action='store_true',help='Slow serial-only inactive WSP staging; no HTTP, no reboot, already-patched V2 only')
    p.add_argument('--wsp-slot',type=int,choices=(1,3),help='Explicit inactive WSP slot for serial-only mode')
    args=p.parse_args()
    print(WARNING,flush=True)
    if args.install and not args.spi_recovery_available:p.error('--install requires --spi-recovery-available')
    if args.serial_wsp and args.wsp_slot is None:p.error('--serial-wsp requires --wsp-slot 1 or 3')
    if not args.serial_wsp and (not args.address or args.wsp_slot is not None):p.error('Web bootstrap needs --address and no --wsp-slot')
    if args.ssh_interface and (not args.ssh or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.:-]{0,63}',args.ssh_interface)):
        p.error('--ssh-interface requires --ssh and a local interface name')
    image=args.image.read_bytes();vendor=args.vendor.read_bytes();backup=args.backup.read_bytes()
    validate_custom(image,vendor,args.expected_sha256)
    validate(backup,backup[:BOOT_SIZE],'\n'.join(f'{i} 0 flash_mxl {o:#x} {s:#x}' for i,o,s in V2_MAP))
    http=None
    if not args.serial_wsp:
        http=SwitchTransport(args.address,timeout=20)
        args.password=os.environ.get(args.password_env)
        if args.password is None:args.password=getpass.getpass('Switch password: ')
    journal=Journal(args.output_dir)
    uart=None
    try:
        uart=UART(args,journal)
        run(args,uart,journal,image,vendor,backup,http)
    except BaseException as error:
        journal.state('STOPPED; NO RETRY, ROLLBACK OR FORCED REBOOT',error_type=type(error).__name__,
                      error=str(error),previous_state=journal.data['state'])
        raise
    finally:
        if uart is not None:uart.close()
        if hasattr(args,'password'):args.password=None


if __name__=='__main__':main()
