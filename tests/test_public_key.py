import struct
import sys
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from read_public_key import from_uart, validate_key_tag


class PublicKeyCapture(unittest.TestCase):
    def setUp(self):
        payload = bytes(range(64))  # Synthetic data; not a vendor key.
        self.tag = bytes.fromhex('a0005fff00000044') + payload + struct.pack('<I', zlib.crc32(payload))
        self.rows = []
        for offset in range(0, len(self.tag), 16):
            chunk = self.tag[offset:offset+16]
            words = struct.unpack('<' + 'I' * (len(chunk) // 4), chunk)
            self.rows.append(f'Mem(0x{0x00107000+offset:08x}): ' + ' '.join(f'0x{x:08x}' for x in words))

    def test_word_order_and_ansi(self):
        self.assertEqual(from_uart('\x1b[32muart:~$\x1b[0m\r\n' + '\r\n'.join(self.rows)), self.tag)

    def test_reject_incomplete_duplicate_reordered_and_bad_header(self):
        for rows in (self.rows[:-1], self.rows + self.rows, self.rows[::-1],
                     [self.rows[0].replace('0xff5f00a0', '0xff5f00a1')] + self.rows[1:]):
            with self.assertRaises(ValueError):
                from_uart('\n'.join(rows))

    def test_reject_corruption_and_oversized_read(self):
        corrupt = bytearray(self.tag)
        corrupt[20] ^= 1
        with self.assertRaises(ValueError):
            validate_key_tag(corrupt)
        with self.assertRaises(ValueError):
            from_uart('\n'.join(self.rows) + ' 0x00000000')
