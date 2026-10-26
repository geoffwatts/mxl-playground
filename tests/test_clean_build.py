import hashlib
from pathlib import Path
import struct
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from prepare_native_base import prepare,CLEAN_SHA
from build_dma_trace_candidate import jump
from upload_native_ui import validate_target

VENDOR=ROOT/'artifacts/candidates/xikestor-upload/wsp_mxl862xx_update_image_fca.bin'
class Preflight(unittest.TestCase):
    def test_target_admission_rejects_other_software_hardware_and_port_profiles(self):
        status={'fw_ver':'2.0.0.4','hw_ver':'A0','des':'SKS3200-8E2X'}
        validate_target(status,{'PortNum':'10','PortMode':'PORT_MODE_8_PLUS_2'})
        for key in status:
            wrong=dict(status);wrong[key]='different'
            with self.assertRaises(ValueError):validate_target(wrong,{'PortNum':'10','PortMode':'PORT_MODE_8_PLUS_2'})
        with self.assertRaises(ValueError):validate_target(status,{'PortNum':8})

@unittest.skipUnless(VENDOR.exists(),'User-supplied audited vendor image required')
class CleanBuild(unittest.TestCase):
    def test_clean_base_has_only_declared_dma_patches_and_no_device_configuration(self):
        vendor=VENDOR.read_bytes();base,ledger=prepare(vendor)
        self.assertEqual(hashlib.sha256(base).hexdigest(),CLEAN_SHA)
        self.assertEqual(base[:0xa000],b'\xff'*0xa000)
        self.assertEqual(base[0x2e0000:],b'\xff'*(0x800000-0x2e0000))
        ws=struct.unpack_from('<I',vendor,4)[0];original=vendor[20:20+ws];changed=base[0xa000:0xa000+ws]
        allowed={i for p in ledger for i in range(int(p['offset'],16),int(p['offset'],16)+p['bytes'])}
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(original,changed)) if a!=b))
        self.assertEqual(changed[0xf170c:0xf1714],jump(0x40000600))
        self.assertEqual(changed[0x600:0x66c],original[0xf170c:0xf1778])
        bad=bytearray(vendor);bad[24]^=1
        with self.assertRaises(ValueError):prepare(bad)
