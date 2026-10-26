import base64
import gzip
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_native_ui as builder


class BrowserBundle(unittest.TestCase):
    def test_bootstrap_roundtrip_preserves_unicode_and_source(self):
        source="console.log('☃');\n// </script> stays inside encoded data\n"
        loader=builder.compressed_bootstrap(source)
        encoded=json.loads(re.search(r'atob\(("[^"]+")\)',loader)[1])
        self.assertEqual(gzip.decompress(base64.b64decode(encoded)).decode(),source)
        self.assertNotIn('</script>',loader)
        self.assertEqual(loader,builder.compressed_bootstrap(source))

    def test_embedded_terminal_libraries_match_pinned_npm_bytes(self):
        source=builder.terminal_library()
        packed=json.loads(re.search(r'for\(const packed of (\[[^\n]+\])\)',source)[1])
        for encoded,name in zip(packed,('xterm.js','addon-fit.js')):
            self.assertEqual(gzip.decompress(base64.b64decode(encoded)),
                             (builder.STATIC/'vendor/xterm'/name).read_bytes())
        self.assertNotIn('script.src=',source)

    def test_modified_terminal_dependency_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);shutil.copytree(builder.STATIC/'vendor',root/'vendor')
            (root/'vendor/xterm/xterm.js').write_bytes(b'changed')
            with patch.object(builder,'STATIC',root):
                with self.assertRaisesRegex(ValueError,'Terminal dependency differs'):
                    builder.terminal_library()

    def test_standalone_ui_fits_existing_asset_region_and_builds_reproducibly(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)
            cmd=[sys.executable,str(ROOT/'tools/build_native_ui.py'),'--without-cli','--output-dir',str(target)]
            subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
            first=(target/'switch-ui.html').read_bytes()
            self.assertLessEqual(len(first),0x2b0000-0x26a000)
            self.assertIn(b'Retry loading',first)
            self.assertIn(b'mxlStarted',first)
            self.assertIn(b'gzip',first)
            self.assertNotRegex(first,rb'<script[^>]+src=')
            subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
            self.assertEqual(first,(target/'switch-ui.html').read_bytes())


if __name__=='__main__':unittest.main()
