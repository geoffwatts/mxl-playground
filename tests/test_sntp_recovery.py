import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import sntp_recovery as patch


class SntpRecovery(unittest.TestCase):
    def reference(self):
        data=bytearray(b'\xff'*0x2d6000)
        for at,before,_ in patch.PATCHES:data[at:at+len(before)]=before
        return data

    def test_complete_patch_round_trip_preserves_all_other_native_bytes(self):
        data=self.reference();original=bytes(data)
        patch.apply(data)
        self.assertTrue(patch.normalize(data))
        data[patch.OFFSET:patch.OFFSET+len(patch.CODE)]=b'\xff'*len(patch.CODE)
        self.assertEqual(data,original)
        self.assertFalse(patch.normalize(data))

    def test_foreign_sites_or_occupied_padding_fail_without_partial_mutation(self):
        for at in [*(at for at,_,_ in patch.PATCHES),patch.OFFSET]:
            data=self.reference();data[at]^=1;before=bytes(data)
            with self.assertRaises(ValueError):patch.apply(data)
            self.assertEqual(data,before)

    def test_partial_patch_and_code_mutations_are_not_admitted(self):
        for at in [*(at for at,_,_ in patch.PATCHES),patch.OFFSET]:
            data=self.reference();patch.apply(data);data[at]^=1
            with self.assertRaisesRegex(ValueError,'SNTP'):patch.normalize(data)


if __name__=='__main__':unittest.main()
