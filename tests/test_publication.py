import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from prepare_github_repo import checked_contents, stage


class SourceStaging(unittest.TestCase):
    def archive(self, directory, files, extra=None):
        manifest = {'format':'mxl-source-review/v1','firmware_included':False,
                    'captured_configuration_included':False,'files':{
                        name:{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
                        for name,data in files.items()}}
        path = directory/'source.zip'
        with zipfile.ZipFile(path,'w') as z:
            for name,data in {**files,'source-manifest.json':json.dumps(manifest).encode(),**(extra or {})}.items():
                info = zipfile.ZipInfo(name)
                info.external_attr = 0o100644 << 16
                z.writestr(info,data)
        return path

    def test_stage_and_refuse_existing_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            archive=self.archive(root,{'README.md':b'[Build](BUILD.md)','BUILD.md':b'Local build'})
            self.assertFalse(stage(archive,root/'repo')['published'])
            self.assertEqual((root/'repo/BUILD.md').read_bytes(),b'Local build')
            with self.assertRaises(FileExistsError):stage(archive,root/'repo')

    def test_reject_before_creating_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for files,extra in [({'README.md':b'[Missing](NO.md)'},None),
                                ({'../escape':b'bad'},None),
                                ({'firmware.bin':b'bad'},None),
                                ({'README.md':b'good'},{'README.md':b'tampered'}),
                                ({'README.md':b'good'},{'unlisted':b'bad'})]:
                archive=self.archive(root,files,extra)
                with self.assertRaises(ValueError):stage(archive,root/'repo')
                self.assertFalse((root/'repo').exists())
