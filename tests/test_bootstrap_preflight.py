import hashlib
import os
from pathlib import Path
import pty
import struct
import sys
import termios
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import inspect_bootstrap as subject


def boot_fixture():
    data=bytearray(subject.BOOT_SIZE)
    rows=b''.join(struct.pack('>III',*row) for row in subject.V2_MAP)
    data[:128]=struct.pack('>HHI',0xa700,0x58ff,len(rows))+rows
    length=0x264-128-8
    data[128:0x264]=struct.pack('>HHI',0xa500,0x5aff,length)+bytes(length)
    data[0x264:0x28c]=subject.STOCK_RECORD
    return bytes(data)


def hexdump(data,start=0):
    return '\n'.join(f'{start+i:08X}: '+data[i:i+16].hex(' ')+' |................|' for i in range(0,len(data),16))


class HexParserTests(unittest.TestCase):
    def test_ansi_echo_ascii_and_prompt_are_not_bytes(self):
        data=bytes(range(256))
        text='flash read flash_mxl 0x100 -d 0x100\r\n'+hexdump(data,256)+'\r\n\x1b[1;32muart:~$ \x1b[m'
        self.assertEqual(subject.parse_hex(text,256,256),data)

    def test_missing_duplicate_reordered_oversize_and_bad_hex_rejected(self):
        valid=hexdump(bytes(range(32)))
        a,b=valid.splitlines()
        for text in [a,a+'\n'+a,b+'\n'+a,valid+'\n'+b,valid.replace('01','gg',1)]:
            with self.subTest(text=text),self.assertRaises(ValueError):
                subject.parse_hex(text,0,32)


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.boot=boot_fixture()
        self.backup=self.boot+bytes(0x800000-len(self.boot))
        self.mapping='\n'.join(f'{i} 0 flash_mxl {o:#x} {s:#x}' for i,o,s in subject.V2_MAP)
        self.guard=patch.object(subject,'BOOT_CODE_SHA',hashlib.sha256(self.boot[0x400:0x7000]).hexdigest())
        self.guard.start();self.addCleanup(self.guard.stop)

    def test_stock_and_exact_patched_record_admitted_as_read_only(self):
        for record,state in [(subject.STOCK_RECORD,'stock'),(subject.PATCH_RECORD,'experimental-skip')]:
            live=self.boot[:0x264]+record+self.boot[0x28c:]
            result=subject.validate(self.backup,live,self.mapping)
            self.assertEqual(result['live_record'],state)
            self.assertFalse(result['installation_ready'])
            self.assertTrue(result['read_only'])

    def test_unknown_record_not_normalized_away(self):
        live=bytearray(self.boot);live[0x270]^=1
        with self.assertRaisesRegex(ValueError,'Unknown boot record'):
            subject.validate(self.backup,live,self.mapping)

    def test_foreign_board_record_and_unaudited_code_rejected(self):
        for address,message in [(200,'differs from own backup'),(0x500,'bootloader executable differs')]:
            live=bytearray(self.boot);live[address]^=1
            with self.subTest(address=address),self.assertRaisesRegex(ValueError,message):
                subject.validate(self.backup,live,self.mapping)

    def test_truncated_backup_and_live_rejected(self):
        for backup,live in [(self.backup[:-1],self.boot),(self.backup,self.boot[:-1])]:
            with self.assertRaisesRegex(ValueError,'complete live'):
                subject.validate(backup,live,self.mapping)

    def test_v1_duplicate_extra_or_wrong_device_map_rejected(self):
        for text in [self.mapping.replace('0x2d6000','0x220000'),self.mapping+'\n'+self.mapping.splitlines()[0],self.mapping.replace('flash_mxl','other_flash')]:
            with self.subTest(text=text),self.assertRaises(ValueError):
                subject.validate(self.backup,self.boot,text)

    def test_boot_map_independently_checked(self):
        live=bytearray(self.boot);struct.pack_into('>I',live,20,0x220000)
        with self.assertRaisesRegex(ValueError,'boot configuration is not'):
            subject.validate(self.backup,live,self.mapping)

    def test_malformed_tag_and_missing_terminator_rejected(self):
        for address in [0,0x264]:
            live=bytearray(self.boot);live[address]^=1
            with self.assertRaises(ValueError):subject.boot_map(live)


class SerialTests(unittest.TestCase):
    def setUp(self):
        self.master,self.slave=pty.openpty()
        self.addCleanup(os.close,self.master);self.addCleanup(os.close,self.slave)
        self.port=os.ttyname(self.slave)

    def assert_restored(self, original):
        actual=termios.tcgetattr(self.slave)
        # Darwin PTYs set PENDIN when canonical input processing is restored.
        # It requests pending-input redisplay, rather than changing port format.
        actual[3] &= ~getattr(termios,'PENDIN',0)
        original[3] &= ~getattr(termios,'PENDIN',0)
        self.assertEqual(actual,original)

    def test_fragmented_prompt_command_and_termios_restoration(self):
        original=termios.tcgetattr(self.slave)
        received=[]
        def peer():
            raw=bytearray()
            while not raw.endswith(b'\r'):raw.extend(os.read(self.master,1024))
            received.append(bytes(raw))
            for part in [b'kernel version\r\nZephyr version 3.1.0\r\n',b'\x1b[1;32muart:',b'~$ \x1b[m']:
                os.write(self.master,part)
        with subject.SerialShell(self.port,timeout=1) as shell:
            worker=threading.Thread(target=peer);worker.start()
            self.assertIn('Zephyr version 3.1.0',shell.command('kernel version'))
            worker.join(timeout=1)
        self.assertEqual(received,[b'\x15kernel version\r'])
        self.assert_restored(original)

    def test_mutations_injection_and_reads_outside_area_rejected_before_io(self):
        with subject.SerialShell(self.port,timeout=.05) as shell:
            for command in ['kernel reboot','flash mod flash_mxl 0x264 0','chiptest mem_wr 0x1 0','kernel version\rreboot','flash read flash_mxl 0xa000 -d 0x100','flash read flash_mxl 0x1 -d 0x100']:
                with self.subTest(command=command),self.assertRaises(ValueError):shell.command(command)

    def test_timeout_restores_port_and_does_not_retry(self):
        original=termios.tcgetattr(self.slave)
        with self.assertRaises(TimeoutError):
            with subject.SerialShell(self.port,timeout=.05) as shell:shell.command('kernel version')
        self.assert_restored(original)
        self.assertEqual(os.read(self.master,1024),b'\x15kernel version\r')


if __name__=='__main__':unittest.main()
