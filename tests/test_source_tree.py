import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from check_source_tree import check, refresh


class SourceTree(unittest.TestCase):
    def fixture(self, root, files):
        manifest = {'format': 'mxl-source-review/v1', 'firmware_included': False,
                    'captured_configuration_included': False, 'files': {}}
        for name, data in files.items():
            path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            manifest['files'][name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        (root/'source-manifest.json').write_text(json.dumps(manifest))

    def test_integrity_and_broken_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, {'README.md': b'[Build](docs/BUILD.md)', 'docs/BUILD.md': b'Local build'})
            self.assertTrue(check(root)['manifest_and_links_verified'])
            (root/'docs/BUILD.md').write_text('Tampered')
            with self.assertRaisesRegex(ValueError, 'manifest mismatch'): check(root)
            self.fixture(root, {'README.md': b'[Missing](missing.md)'})
            with self.assertRaisesRegex(ValueError, 'Broken documentation link'): check(root)

    def test_private_inputs_and_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('firmware.bin', 'capture.log', '.env', 'input/settings.json'):
                self.fixture(root, {name: b'private'})
                with self.assertRaisesRegex(ValueError, 'Unsafe/private'): check(root)
            self.fixture(root, {'README.md': b'Good'})
            (root/'README.md').unlink(); (root/'README.md').symlink_to(root/'source-manifest.json')
            with self.assertRaisesRegex(ValueError, 'Unsafe source path'): check(root)

    def test_refresh_uses_only_tracked_files_and_git_set_is_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            (root/'README.md').write_text('Source')
            (root/'untracked-secret.txt').write_text('Excluded')
            subprocess.run(['git', '-C', str(root), 'add', 'README.md'], check=True)
            refresh(root)
            self.assertEqual(set(json.loads((root/'source-manifest.json').read_text())['files']), {'README.md'})
            subprocess.run(['git', '-C', str(root), 'add', 'source-manifest.json'], check=True)
            self.assertTrue(check(root, git=True)['git_file_set_verified'])
            (root/'new.py').write_text('x=1')
            subprocess.run(['git', '-C', str(root), 'add', 'new.py'], check=True)
            with self.assertRaisesRegex(ValueError, 'Git and source manifest differ'): check(root, git=True)
            refresh(root)
            self.assertTrue(check(root, git=True)['git_file_set_verified'])


if __name__ == '__main__': unittest.main()
