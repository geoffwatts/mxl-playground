"""Synthetic migration admission/preservation tests; no vendor bytes included."""
import hashlib
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import build_v2_migration_candidate as migration


class Migration(unittest.TestCase):
    def setUp(self):
        self.source = bytearray(b'\xff' * 0x800000)
        old = list(migration.SOURCE_MAP.values())
        self.new = [dict(p) for p in old]
        for p, start, size in zip(self.new, [0,0xa000,0x2e0000,0x30d000,0x5e3000,
                                           0x610000,0x618000,0x628000,0x668000,0x6e8000],
                                 [0xa000,0x2d6000,0x2d000,0x2d6000,0x2d000,
                                  0x8000,0x10000,0x40000,0x80000,0x80000]):
            p.update(offset=start, size=size)
        key = bytes(range(64))
        self.key_tag = bytes.fromhex('a0005fff00000044') + key + struct.pack('<I', zlib.crc32(key))
        table = b''.join(struct.pack('>III', p['id'], p['offset'], p['size']) for p in old)
        tags = struct.pack('>HHI',0xa100,0x5eff,68)+key+struct.pack('<I',zlib.crc32(key))
        tags += struct.pack('>HHI',0xa700,0x58ff,len(table))+table
        tags += struct.pack('>HHI',0xad00,0x52ff,0)
        self.source[:len(tags)] = tags
        for p in old[1:5]:
            self.source[p['offset']:p['offset']+32] = bytes([p['id']])*32
        self.hashes = {i: migration.sha(self.source[p['offset']:p['offset']+p['size']])
                       for i,p in migration.SOURCE_MAP.items() if i < 5}
        component = bytes(0x2000)
        self.update = struct.pack('<5I',0xf48bf48b,len(component),zlib.crc32(component),
                                  len(component),zlib.crc32(component))+component*2
        self.profile = patch.object(migration, 'SOURCE_REGION_SHA', self.hashes)
        self.profile.start()
        self.addCleanup(self.profile.stop)

    def test_accept_different_owner_data(self):
        for ident in range(5,10):
            area=migration.SOURCE_MAP[ident]
            self.source[area['offset']:area['offset']+128]=bytes([ident])*128
        migration.validate_source(self.source)

    def test_reject_every_changed_boot_or_firmware_region(self):
        for ident in range(5):
            with self.subTest(region=ident):
                source=bytearray(self.source)
                source[migration.SOURCE_MAP[ident]['offset']+0x400]^=1
                with self.assertRaisesRegex(ValueError, 'boot/firmware region'):
                    migration.validate_source(source)

    def test_reject_wrong_size_tail_layout_and_duplicate_id(self):
        with self.assertRaises(ValueError):migration.validate_source(self.source[:-1])
        source=bytearray(self.source);source[-1]=0
        with self.assertRaisesRegex(ValueError,'outside source partitions'):
            migration.validate_source(source)
        for duplicate in [False,True]:
            source=bytearray(self.source)
            table=next(t for t in migration.parse_tags(source) if t['tag']=='0xa700')
            offset=table['payload_offset']+(12 if duplicate else 4)
            struct.pack_into('>I',source,offset,0 if duplicate else 4096)
            with self.assertRaisesRegex(ValueError,'Duplicate|partition layout'):
                migration.validate_source(source)

    def test_build_preserves_each_owners_regions_and_erases_extension(self):
        # Crypto/map decoding have their own tests; mock only these boundaries.
        # Admission, relocation and preservation use the actual migration code.
        outputs=[]
        for owner in (17,29):
            source=bytearray(self.source)
            for ident in range(5,10):
                p=migration.SOURCE_MAP[ident]
                source[p['offset']:p['offset']+p['size']]=bytes([owner+ident])*p['size']
            with patch.object(migration,'V2_SHA',migration.sha(self.update)), \
                 patch.object(migration,'compiled_map',side_effect=[(0,self.new),(0,list(migration.SOURCE_MAP.values()))]), \
                 patch.object(migration,'verify_component',return_value={'signature_valid':True}):
                out,manifest=migration.build(bytes(source),self.update,self.key_tag)
            self.assertTrue(manifest['owner_data_preservation_verified'])
            for p in self.new[5:]:
                old=migration.SOURCE_MAP[p['id']]
                self.assertEqual(out[p['offset']:p['offset']+old['size']],
                                 source[old['offset']:old['offset']+old['size']])
                self.assertEqual(out[p['offset']+old['size']:p['offset']+p['size']],
                                 b'\xff'*(p['size']-old['size']))
            self.assertEqual(out[0x400:0xa000],source[0x400:0xa000])
            outputs.append(out)
        self.assertNotEqual(outputs[0],outputs[1])

    def test_reject_unknown_update(self):
        with self.assertRaisesRegex(ValueError,'V2.0.0.4'):
            migration.build(bytes(self.source),self.update,self.key_tag)


if __name__=='__main__':unittest.main()
