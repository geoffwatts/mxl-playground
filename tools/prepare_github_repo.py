#!/usr/bin/env python3
"""Stage a verified source-only repository locally; never init, commit or push.

Run package_developer_preview.py first. Only its manifested archive is accepted;
the research workspace is never recursively copied.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def checked_contents(archive):
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive members')
        contents = {}
        for info in z.infolist():
            path = PurePosixPath(info.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in info.filename
                    or not path.parts or info.filename != str(path)
                    or '.git' in path.parts or info.is_dir()
                    or (info.external_attr >> 16) & 0o170000 != 0o100000):
                raise ValueError('Unsafe archive member: ' + info.filename)
            if info.file_size > 2_000_000:
                raise ValueError('Oversized source member')
            contents[info.filename] = z.read(info)
    manifest = json.loads(contents['source-manifest.json'])
    if (manifest.get('format') != 'mxl-source-review/v1'
            or manifest.get('firmware_included') is not False
            or manifest.get('captured_configuration_included') is not False):
        raise ValueError('Unexpected source manifest')
    if set(contents) != set(manifest['files']) | {'source-manifest.json'}:
        raise ValueError('Archive and manifest members differ')
    for name, expected in manifest['files'].items():
        data = contents[name]
        if len(data) != expected['bytes'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
            raise ValueError('Source manifest mismatch: ' + name)
        if PurePosixPath(name).suffix.lower() in ('.bin','.log','.pem','.key','.pcap','.pcapng'):
            raise ValueError('Private/generated member: ' + name)
    for name, data in contents.items():
        if not name.endswith('.md'):
            continue
        for link in re.findall(r'\]\(([^)]+)\)', data.decode()):
            if ':' in link or link.startswith('#'):
                continue
            target = posixpath.normpath(posixpath.join(posixpath.dirname(name), link.split('#')[0]))
            if target not in contents:
                raise ValueError('Broken documentation link: ' + name + ' -> ' + link)
    return contents


def stage(archive, destination):
    contents = checked_contents(archive)  # Validate completely before writing.
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in contents.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return {'directory':str(destination), 'source_files':len(contents),
            'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
            'manifest_and_document_links_checked':True,
            'firmware_included':False, 'git_initialized':False, 'published':False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,default=ROOT/'artifacts/developer-preview/mxl-native-ui-source-review.zip')
    p.add_argument('--output-dir',type=Path,required=True,help='New directory; existing trees are never overwritten')
    args = p.parse_args()
    print(json.dumps(stage(args.archive,args.output_dir),indent=2))


if __name__ == '__main__':
    main()
