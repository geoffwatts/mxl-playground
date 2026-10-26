#!/usr/bin/env python3
"""Check tracked source hashes and documentation links; never reads device inputs."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess


def tracked_files(root):
    raw = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z'])
    return set(raw.decode().rstrip('\0').split('\0')) if raw else set()


def read_source(root, name):
    p = PurePosixPath(name)
    if (p.is_absolute() or '..' in p.parts or '\\' in name or name != str(p)
            or any(part in ('.git', 'artifacts', 'input', 'upstream', 'IMSProg') for part in p.parts)
            or p.suffix.lower() in ('.bin', '.log', '.pem', '.key', '.pcap', '.pcapng', '.zip')
            or p.name == '.env' or p.name.startswith('.env.')):
        raise ValueError('Unsafe/private source path: ' + name)
    path = root / name
    if path.is_symlink() or not path.is_file() or root not in path.resolve().parents:
        raise ValueError('Unsafe source path: ' + name)
    if path.stat().st_size > 2_000_000:
        raise ValueError('Oversized source member: ' + name)
    return path.read_bytes()


def check_links(contents):
    for name, data in contents.items():
        if not name.endswith('.md'):
            continue
        for link in re.findall(r'\]\(([^)]+)\)', data.decode()):
            if ':' in link or link.startswith('#'):
                continue
            target = posixpath.normpath(posixpath.join(posixpath.dirname(name), link.split('#')[0]))
            if target not in contents:
                raise ValueError('Broken documentation link: ' + name + ' -> ' + link)


def refresh(root):
    """Inventory explicitly tracked files, never a recursive workspace copy."""
    root = Path(root).resolve()
    names = tracked_files(root) - {'source-manifest.json'}
    if not names:
        raise ValueError('No tracked source files')
    contents = {name: read_source(root, name) for name in sorted(names)}
    check_links(contents)
    manifest = {'format': 'mxl-source-review/v1', 'firmware_included': False,
                'captured_configuration_included': False, 'licence_for_new_source': 'MIT',
                'files': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                          for name, data in contents.items()}}
    (root / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


def check(root, git=False):
    root = Path(root).resolve()
    manifest = json.loads((root / 'source-manifest.json').read_text())
    if (manifest.get('format') != 'mxl-source-review/v1'
            or manifest.get('firmware_included') is not False
            or manifest.get('captured_configuration_included') is not False):
        raise ValueError('Unexpected source manifest')
    contents = {}
    for name, expected in manifest['files'].items():
        data = read_source(root, name)
        if len(data) != expected['bytes'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
            raise ValueError('Source manifest mismatch: ' + name)
        contents[name] = data
    names = set(contents) | {'source-manifest.json'}
    check_links({**contents, 'source-manifest.json': b''})
    if git and tracked_files(root) != names:
        raise ValueError('Git and source manifest differ: ' + repr(sorted(tracked_files(root) ^ names)))
    return {'source_files': len(names), 'manifest_and_links_verified': True,
            'git_file_set_verified': git}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--git', action='store_true', help='Require exact tracked-file match')
    p.add_argument('--refresh', action='store_true', help='Update manifest from staged/tracked files; stage new source first')
    args = p.parse_args()
    if args.refresh:
        refresh(args.root)
    print(json.dumps(check(args.root, args.git), indent=2))


if __name__ == '__main__':
    main()
