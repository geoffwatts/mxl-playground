from pathlib import Path
import json,re,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from wsp_profile import load,header,admit
class WspProfile(unittest.TestCase):
 def test_board_mapping_matches_front_panel_decoder(self):
  p,b=load();source=(ROOT/'designs/mxl-management/live-model.mjs').read_text();pairs=re.search(r'DRIVER_PORT=\{([^}]+)',source)[1]
  actual={a:int(v) for a,v in re.findall(r'(\d+):(\d+)',pairs)}
  self.assertEqual(actual,b['driver_to_front_panel']);self.assertEqual(b['sfp_buses'],{'9':'I2C_1','10':'I2C_0'})
  self.assertIn('WSP_PACKET_READ',header());self.assertEqual(p['lldp_hook']['offset'],0x3c028)
 def test_unknown_firmware_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'Unknown vendor'):admit(b'not firmware')
