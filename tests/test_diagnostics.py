from pathlib import Path
import struct
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from collect_diagnostics import sfp_summary

class Diagnostics(unittest.TestCase):
    def snapshot(self):
        data=bytearray(1056);data[:8]=bytes.fromhex('4d53465001020c02');data[8:10]=bytes([9,1]);data[532:534]=bytes([10,0]);return data
    def test_summary_excludes_raw_eeprom_even_when_present(self):
        data=self.snapshot();data[10]=1;data[11]=2;data[12]=1;data[13]=1;data[20:25]=b'OWNER'
        summary=sfp_summary(data)
        self.assertEqual(summary[0]['presence'],'present')
        self.assertNotIn('OWNER',str(summary));self.assertNotIn('serial',str(summary));self.assertEqual(summary[1]['port'],10)
    def test_malformed_states_and_mapping_are_rejected(self):
        for offset,value in [(8,10),(9,0),(10,4),(11,8),(12,1),(13,1),(18,1)]:
            data=self.snapshot();data[offset]=value
            with self.assertRaises(ValueError):sfp_summary(data)
        with self.assertRaises(ValueError):sfp_summary(b'bad')
