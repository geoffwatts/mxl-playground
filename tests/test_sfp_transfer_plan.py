"""Exercise generated ARC chunk-loop control flow against an independent I2C ABI.

Instruction semantics are limited to this loop; Ghidra decoding and real-device
execution remain separate checks. No vendor/module EEPROM fixture is required.
"""
import contextlib
import io
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import prepare_sfp_endpoint as subject


class ChunkLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as tmp,patch.object(subject,'OUT',Path(tmp)),contextlib.redirect_stdout(io.StringIO()):
            subject.main()
            cls.plan=json.loads((Path(tmp)/'assembly-plan.json').read_text())

    def run_loop(self,port,address,fail=None):
        stack=0x10000;record=stack+(8 if port==9 else 532)
        regs={'sp':stack,'r14':record,'r16':0x400f9f80};memory={};calls=[];zero=False
        items={x['address']:x for x in self.plan['plan']}
        prefix=f'p{port}_chunk_{address}'
        pc=self.plan['labels'][prefix+'_start'];end=self.plan['labels'][prefix+'_done']
        def value(text):return int(text,16) if text.startswith('0x') else regs[text]
        def store(at,n,v):
            self.assertGreaterEqual(at,stack);self.assertLessEqual(at+n,stack+1088)
            for i in range(n):memory[at+i]=(v>>(i*8))&255
        def load(at,n):return sum(memory.get(at+i,0)<<(i*8) for i in range(n))
        for _ in range(4000):
            if pc==end:return regs['r0'],calls,memory
            item=items[pc];source=item['source'];next_pc=pc+len(bytes.fromhex(item['hex']))
            if match:=re.fullmatch(r'mov(?:_s)? (r\d+),(r\d+|sp|0x[0-9a-f]+)',source):
                regs[match[1]]=value(match[2])
            elif source=='add r0,r0,r1':regs['r0']=(regs['r0']+regs['r1'])&0xffffffff
            elif match:=re.fullmatch(r'st(_s|b_s) r1,\[r0,(0x[0-9a-f]+)\]',source):
                store(regs['r0']+int(match[2],16),1 if match[1]=='b_s' else 4,regs['r1'])
            elif source=='ld_s r0,[r0,0x0]':regs['r0']=load(regs['r0'],4)
            elif match:=re.fullmatch(r'cmp_s (r\d+),(r\d+|0x[0-9a-f]+)',source):zero=regs[match[1]]==value(match[2])
            elif source.startswith('beq_s '):
                if zero:next_pc=int(source.split()[1],16)
            elif source.startswith('j '):
                high,low=struct.unpack('<HH',bytes.fromhex(item['hex'])[4:])
                next_pc=high<<16|low
            elif source=='jl 0x4006d428':
                self.assertEqual(regs['r0'],regs['r16']);self.assertEqual(regs['r2'],2);self.assertEqual(regs['r3'],address)
                messages=regs['r1'];offset=load(load(messages,4),1)
                self.assertEqual(load(messages+4,4),1);self.assertEqual(load(messages+8,4),0)
                destination=load(messages+12,4);length=load(messages+16,4)
                self.assertEqual(length,16);self.assertEqual(load(messages+20,4),7)
                self.assertEqual(destination,record+(12 if address==0x50 else 268)+offset)
                self.assertIn(offset,range(0,256,16));calls.append(offset)
                if len(calls)==fail:regs['r0']=-116
                else:
                    for i in range(length):store(destination+i,1,(offset+i)^0xa5)
                    regs['r0']=0
            else:raise AssertionError('Unexpected instruction: '+source)
            pc=next_pc
        self.fail('Chunk loop did not terminate within its bound')

    def test_both_cages_and_pages_cover_each_byte_once(self):
        for port in (9,10):
            for address in (0x50,0x51):
                with self.subTest(port=port,address=address):
                    result,calls,memory=self.run_loop(port,address)
                    self.assertEqual(result,0);self.assertEqual(calls,list(range(0,256,16)))
                    start=0x10000+(8 if port==9 else 532)+(12 if address==0x50 else 268)
                    self.assertEqual(bytes(memory[start+i] for i in range(256)),bytes(i^0xa5 for i in range(256)))

    def test_first_middle_last_failure_preserves_error_and_stops(self):
        for fail in (1,8,16):
            with self.subTest(fail=fail):
                result,calls,_=self.run_loop(9,0x50,fail)
                self.assertEqual(result,-116);self.assertEqual(len(calls),fail)

    def test_known_silicon_rejected_compare_encoding_is_absent(self):
        self.assertNotIn('0c210020',[x['hex'] for x in self.plan['plan']])


if __name__=='__main__':unittest.main()
