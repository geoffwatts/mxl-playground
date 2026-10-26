#!/usr/bin/env python3
"""Validate a staged publication tree and optionally its exact Git file set."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile
from prepare_github_repo import checked_contents


def check(root, git=False):
    root=Path(root).resolve()
    manifest=json.loads((root/'source-manifest.json').read_text())
    names=set(manifest['files'])|{'source-manifest.json'}
    # Reuse archive path, hash, format and Markdown-link checks. Read only
    # root-contained regular files; never follow links into a research tree.
    with tempfile.TemporaryDirectory() as tmp:
        archive=Path(tmp)/'source.zip'
        with zipfile.ZipFile(archive,'w') as out:
            for name in sorted(names):
                path=root/name
                if path.is_symlink() or not path.is_file() or root not in path.resolve().parents:
                    raise ValueError('Unsafe source path: '+name)
                info=zipfile.ZipInfo(name);info.external_attr=0o100644<<16
                out.writestr(info,path.read_bytes())
        checked_contents(archive)
    if git:
        raw=subprocess.check_output(['git','-C',str(root),'ls-files','-z'])
        tracked=set(raw.decode().rstrip('\0').split('\0')) if raw else set()
        if tracked!=names:
            raise ValueError('Git and source manifest differ: '+repr(sorted(tracked^names)))
    return {'source_files':len(names),'manifest_and_links_verified':True,'git_file_set_verified':git}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--git',action='store_true',help='Require exact tracked-file match')
    args=parser.parse_args()
    print(json.dumps(check(args.root,args.git),indent=2))


if __name__=='__main__':main()
