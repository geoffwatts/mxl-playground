from pathlib import Path
import shutil,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class LldpCache(unittest.TestCase):
 def test_compiled_cache(self):
  cc=shutil.which('clang') or shutil.which('cc')
  if not cc:self.skipTest('Host C compiler required')
  with tempfile.TemporaryDirectory() as d:
   exe=Path(d)/'lldp'
   subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'firmware'),str(ROOT/'firmware/lldp_cache.c'),str(ROOT/'firmware/wsp_arithmetic.c'),str(ROOT/'tests/lldp_cache_fixture.c'),'-o',str(exe)],check=True)
   r=subprocess.run([str(exe)],check=True,capture_output=True,text=True);self.assertIn('tests passed',r.stdout)
if __name__=='__main__':unittest.main()
