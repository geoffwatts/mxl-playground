import contextlib
import io
import os
from pathlib import Path
import pty
import re
import select
import struct
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from inspect_bootstrap import BOOT_SIZE, PATCH_RECORD, STOCK_RECORD, V2_MAP
from installer_uart import PATCH_COMMAND, WSP_AREAS, allowed
from install_serial import (Journal, UART, active_slot, interface_identity, patch_boot,
                            read_flash, run, serial_wsp, unrestricted_policy, verify_write, web_upload)
from installer_image import components, validate_custom


class MemoryUART:
    def __init__(self,active=3):
        self.memory=bytearray(b'\xff'*0x610000)
        self.memory[0x264:0x28c]=STOCK_RECORD
        self.commands=[];self.active=active;self.fail=None
    def command(self,command):
        self.commands.append(command)
        if self.fail and self.fail in command:return 'Write ERROR.\nuart:~$ '
        if command=='chiptest mem_rd 0xd0e3d424 1':
            return f'Mem(0xd0e3d424): 0x{WSP_AREAS[self.active][0]:08x}\nuart:~$ '
        if command==PATCH_COMMAND:
            self.memory[0x264:0x28c]=PATCH_RECORD
            return 'Read OK.\nErase OK.\nWrite OK.\nVerified.\nuart:~$ '
        parts=command.split();at=int(parts[3],16)
        if parts[1]=='read':
            return '\n'.join(f'{offset:08X}: '+self.memory[offset:offset+16].hex(' ')+' |test|'
                             for offset in range(at,at+256,16))+'\nuart:~$ '
        if parts[1]=='erase':
            self.memory[at:at+4096]=b'\xff'*4096
            return 'Erase success.\nuart:~$ '
        if parts[1]=='write':
            raw=b''.join(struct.pack('<I',int(word,16)) for word in parts[4:])
            assert all((old & new)==new for old,new in zip(self.memory[at:at+len(raw)],raw))
            self.memory[at:at+len(raw)]=raw
            return 'Write OK.\nVerified.\nuart:~$ '
        raise AssertionError(command)


class FakeJournal:
    def __init__(self):self.data={};self.states=[];self.files={}
    def save(self):pass
    def file(self,name,data):self.files[name]=data
    def state(self,state,**fields):self.states.append(state);self.data.update(fields)


class SerialInstaller(unittest.TestCase):
    def test_command_scope(self):
        encoded=b''.join(struct.pack('<I',int(word,16)) for word in PATCH_COMMAND.split()[4:])
        self.assertEqual(encoded,PATCH_RECORD)
        self.assertFalse(allowed(PATCH_COMMAND))
        self.assertTrue(allowed(PATCH_COMMAND,True))
        self.assertFalse(allowed(PATCH_COMMAND,True,1))
        for command in ['chiptest reboot','chiptest mem_wr 0x70006f18 0','flash erase flash_mxl 0x0 0x1000',
                        'flash erase flash_mxl 0x30d000 0x1000','flash write flash_mxl 0xaffc 00000000 00000000',
                        'flash write flash_mxl 0xa000 '+' '.join(['00000000']*33),
                        'flash write flash_mxl 0xa000 00000000\nchiptest reboot']:
            self.assertFalse(allowed(command,True,1),command)
        self.assertTrue(allowed('flash erase flash_mxl 0xa000 0x1000',True,1))
        self.assertTrue(allowed('flash write flash_mxl 0xa000 00000000',True,1))

    def test_identity_and_active_slot(self):
        self.assertEqual(interface_identity('Interface (Ethernet) [1]\nLink addr : 02:00:00:00:00:01\n'),'020000000001')
        for text in ['', 'Interface [1]\nLink addr : 02:00:00:00:00:01\nLink addr : 02:00:00:00:00:02']:
            with self.assertRaises(ValueError):interface_identity(text)
        self.assertEqual(active_slot('Mem(0xd0e3d424): 0x0030d000\n'),3)
        with self.assertRaises(ValueError):active_slot('Mem(0xd0e3d424): 0x00000000')

    def test_boot_patch_preserves_every_other_byte(self):
        uart=MemoryUART();before=bytes(uart.memory[:BOOT_SIZE]);journal=FakeJournal()
        patch_boot(uart,before,journal)
        expected=before[:0x264]+PATCH_RECORD+before[0x28c:]
        self.assertEqual(bytes(uart.memory[:BOOT_SIZE]),expected)
        self.assertEqual(uart.commands.count(PATCH_COMMAND),1)
        self.assertEqual(journal.files['after-boot-sector.bin'],expected[:4096])

    def test_stop_after_failed_boot_write_no_retry_or_reboot(self):
        uart=MemoryUART();before=bytes(uart.memory[:BOOT_SIZE]);uart.fail='flash mod'
        with self.assertRaises(RuntimeError):patch_boot(uart,before,FakeJournal())
        self.assertEqual(uart.commands[-1],PATCH_COMMAND)
        self.assertEqual(uart.commands.count(PATCH_COMMAND),1)

    def test_stop_if_prewrite_sector_changed(self):
        uart=MemoryUART();before=bytes(uart.memory[:BOOT_SIZE]);uart.memory[1]^=1
        with self.assertRaises(ValueError):patch_boot(uart,before,FakeJournal())
        self.assertNotIn(PATCH_COMMAND,uart.commands)

    def test_false_verified_reply_cannot_hide_corrupt_boot_sector(self):
        class CorruptUART(MemoryUART):
            def command(self,command):
                reply=super().command(command)
                if command==PATCH_COMMAND:self.memory[0x300]^=1
                return reply
        uart=CorruptUART()
        with self.assertRaises(ValueError):patch_boot(uart,bytes(uart.memory[:BOOT_SIZE]),FakeJournal())
        self.assertEqual(uart.commands.count(PATCH_COMMAND),1)

    def test_management_policy_gate(self):
        data=bytearray(128);data[:8]=b'MVCT\x02\x02\x00\x01'
        unrestricted_policy(data)
        for offset in [0,6,7,8,10,12,14,44,72]:
            bad=bytearray(data);bad[offset]^=1
            with self.assertRaises(ValueError):unrestricted_policy(bad)

    def test_coordinated_flow_stock_patched_dryrun_and_wrong_target(self):
        # Test ordering/state transitions with synthetic profiles; real image
        # admission, serial transport and boot-layout parsing have separate tests.
        for stock,install,wrong_mac in [(True,True,False),(False,True,False),
                                         (True,False,False),(True,True,True)]:
            uart=MemoryUART(active=3);uart.text=''
            if not stock:uart.memory[0x264:0x28c]=PATCH_RECORD
            base_command=uart.command
            def command(value):
                special={'kernel version':'Zephyr test',
                         'chiptest firmware_ver':'WSP firmware version: 1.0.79.79',
                         'flash_map list':'\n'.join(f'{i} 0 flash_mxl {at:#x} {size:#x}' for i,at,size in V2_MAP),
                         'net iface show 1':'Interface (Ethernet) [1]\nLink addr : 02:00:00:00:00:01\n'}
                return special[value] if value in special else base_command(value)
            uart.command=command
            status={'fw_ver':'2.0.0.4','hw_ver':'A0','des':'SKS3200-8E2X',
                    'sys_macaddr':'02:00:00:00:00:02' if wrong_mac else '02:00:00:00:00:01'}
            policy=bytearray(128);policy[:8]=b'MVCT\x02\x02\x00\x01'
            def request(path,**kwargs):
                if path=='/port_setting_load.json':return {'data':{'PortNum':10,'PortMode':'PORT_MODE_8_PLUS_2'}}
                return {'bytes':bytes(policy) if path=='/management-vlan.json' else b'synthetic export'}
            http=types.SimpleNamespace(address='192.0.2.1',cookie='synthetic',login=lambda *a:status,request=request)
            posted=[]
            class Client:
                def __init__(self,*args):pass
                def close(self):pass
                def post(self,part,timeout):
                    posted.append(part)
                    final=len(posted)==2
                    if final:
                        uart.active=1;uart.text='Start WSP\nDMA RX UP\nDMA TX UP\n'
                    return {'response':'Verification: Success. System is rebooting.' if final else '',
                            'transport_error':None,'http_status':200}
            args=types.SimpleNamespace(expected_sha256='test',serial_wsp=False,install=install,username='admin',password='test')
            journal=FakeJournal();image=bytes(50000)
            with patch('install_serial.validate_custom',return_value={'ui_sha256':'test'}),\
                 patch('install_serial.validate',return_value={'live_record':'stock' if stock else 'experimental-skip'}),\
                 patch('install_serial.validate_running',return_value='factory' if stock else 'audited-custom'),\
                 patch('install_serial.ChunkClient',Client),patch('install_serial.time.sleep'),\
                 patch('install_serial.verify_served_ui',return_value={'matched':True}):
                if wrong_mac:
                    with self.assertRaises(ValueError):run(args,uart,journal,image,b'factory',b'backup',http)
                else:run(args,uart,journal,image,b'factory',b'backup',http)
            self.assertEqual(uart.commands.count(PATCH_COMMAND),int(stock and install and not wrong_mac))
            self.assertEqual(len(posted),2 if install and not wrong_mac else 0)
            self.assertFalse(any('reboot' in c or 'mem_wr' in c for c in uart.commands))

    def test_serial_full_slot_readback_and_last_marker(self):
        uart=MemoryUART(active=3);journal=FakeJournal()
        wsp=bytearray(b'\xff'*WSP_AREAS[1][1]);wsp[:128]=bytes(range(128));wsp[-32:]=bytes(range(32))
        untouched=bytes(uart.memory[0x30d000:]);boot=bytes(uart.memory[:0xa000])
        with contextlib.redirect_stdout(io.StringIO()):serial_wsp(uart,1,bytes(wsp),journal)
        start,size=WSP_AREAS[1]
        self.assertEqual(uart.memory[start:start+size],wsp)
        self.assertEqual(bytes(uart.memory[:0xa000]),boot)
        self.assertEqual(bytes(uart.memory[0x30d000:]),untouched)
        erase=[c for c in uart.commands if c.startswith('flash erase')]
        self.assertEqual(len(erase),size//4096)
        self.assertEqual(len(set(erase)),len(erase))
        writes=[c for c in uart.commands if c.startswith('flash write')]
        self.assertTrue(writes[-1].startswith(f'flash write flash_mxl {start+size-16:#x} '))
        self.assertTrue(all(len(c)<400 and allowed(c,True,1) for c in writes+erase))

    def test_refuse_active_slot_and_erase_failure(self):
        uart=MemoryUART(active=1)
        with self.assertRaises(ValueError):serial_wsp(uart,1,b'\xff'*WSP_AREAS[1][1],FakeJournal())
        self.assertEqual(len(uart.commands),1)
        uart=MemoryUART(active=3);uart.fail='flash erase'
        with self.assertRaises(RuntimeError):serial_wsp(uart,1,b'\xff'*WSP_AREAS[1][1],FakeJournal())
        self.assertFalse(any(c.startswith('flash write') for c in uart.commands))

    def test_serial_preflight_checks_both_companion_banks_without_http(self):
        for corrupt in (False,True):
            uart=MemoryUART(active=3);uart.memory[0x264:0x28c]=PATCH_RECORD
            if corrupt:uart.memory[0x2e0800]=0
            original=uart.command
            def command(value):
                special={'kernel version':'Zephyr test',
                         'chiptest firmware_ver':'WSP firmware version: 1.0.79.79',
                         'flash_map list':'\n'.join(f'{i} 0 flash_mxl {at:#x} {size:#x}' for i,at,size in V2_MAP),
                         'net iface show 1':'Interface (Ethernet) [1]\nLink addr : 02:00:00:00:00:01\n'}
                return special[value] if value in special else original(value)
            uart.command=command
            args=types.SimpleNamespace(expected_sha256='test',serial_wsp=True,wsp_slot=1,install=False)
            with patch('install_serial.validate_custom',return_value={}),\
                 patch('install_serial.validate',return_value={'live_record':'experimental-skip'}),\
                 patch('install_serial.components',return_value=(b'\xff'*0x2d6000,b'\xff'*0x29f40)):
                if corrupt:
                    with self.assertRaises(ValueError):run(args,uart,FakeJournal(),b'image',b'vendor',b'backup')
                else:run(args,uart,FakeJournal(),b'image',b'vendor',b'backup')
            self.assertFalse(any(c.startswith(('flash erase','flash write','flash mod')) for c in uart.commands))
            if not corrupt:
                self.assertIn('flash read flash_mxl 0x2e0000 -d 0x100',uart.commands)
                self.assertIn('flash read flash_mxl 0x5e3000 -d 0x100',uart.commands)

    def test_web_lost_reply_never_replayed(self):
        class Client:
            def __init__(self):self.calls=[]
            def post(self,payload,timeout):
                self.calls.append(payload)
                return {'response':'','transport_error':'TimeoutError','http_status':None}
        client=Client()
        with self.assertRaises(RuntimeError):web_upload(bytes(50000),client,FakeJournal())
        self.assertEqual(len(client.calls),1)

    def test_web_premature_or_missing_success(self):
        for body,size in [('Verification: Success. System is rebooting.',50000),('',12)]:
            client=types.SimpleNamespace(post=lambda *args:{'response':body,'transport_error':None,'http_status':200})
            with self.assertRaises(RuntimeError):web_upload(bytes(size),client,FakeJournal())

    def test_private_journal_refuses_existing_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'private';journal=Journal(path);journal.file('backup.bin',b'test')
            self.assertEqual(path.stat().st_mode&0o777,0o700)
            self.assertEqual((path/'state.json').stat().st_mode&0o777,0o600)
            self.assertEqual((path/'backup.bin').stat().st_mode&0o777,0o600)
            with self.assertRaises(FileExistsError):Journal(path)

    def test_real_rpc_agent_dry_run_cannot_write(self):
        master,slave=pty.openpty();port=os.ttyname(slave);seen=[];stop=threading.Event()
        def emulator():
            pending=bytearray()
            try:
                while not stop.is_set():
                    if not select.select([master],[],[],.05)[0]:continue
                    data=os.read(master,4096)
                    if not data:return
                    pending.extend(data)
                    if b'\r' in pending:
                        command=bytes(pending).split(b'\r')[0].lstrip(b'\x15').decode();pending.clear()
                        seen.append(command)
                        os.write(master,b'kernel version\r\nZephyr test\r\nuart:~$ ')
            except OSError:pass
        thread=threading.Thread(target=emulator,daemon=True);thread.start()
        args=types.SimpleNamespace(port=port,install=False,serial_wsp=False,ssh=None)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                uart=UART(args,Journal(Path(tmp)/'log'))
                try:
                    self.assertIn('Zephyr test',uart.command('kernel version'))
                    with self.assertRaises(RuntimeError):uart.command(PATCH_COMMAND)
                    self.assertEqual(seen,['kernel version'])
                finally:uart.close()
        finally:
            stop.set();thread.join(timeout=1)
            os.close(master);os.close(slave)


VENDOR=ROOT/'artifacts/candidates/xikestor-upload/wsp_mxl862xx_update_image_fca.bin'
CUSTOM=ROOT/'artifacts/github/mxl-playground-review/artifacts/developer-update/native-ui-update-EXPERIMENTAL.bin'
@unittest.skipUnless(VENDOR.exists() and CUSTOM.exists(),'Private factory/build inputs not distributed')
class ImageAdmission(unittest.TestCase):
    def test_selected_clean_profile_and_corruption(self):
        vendor=VENDOR.read_bytes();image=CUSTOM.read_bytes()
        self.assertTrue(validate_custom(image,vendor)['clean_build'])
        for offset in [20+0xf1764,20+0x2b0000,20+0x2c300c,20+0x2479c,20+0x56a14,20+0x1234]:
            bad=bytearray(image);bad[offset]^=1
            import zlib
            struct.pack_into('<I',bad,8,zlib.crc32(bad[20:20+0x2d6000]))
            with self.assertRaises(ValueError):validate_custom(bytes(bad),vendor)
        with self.assertRaises(ValueError):validate_custom(image,vendor,'0'*64)
