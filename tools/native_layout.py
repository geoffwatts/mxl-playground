#!/usr/bin/env python3
"""Validate GoodTop backup framing without executing or modifying firmware."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib


def inspect(path, extract=None):
    data = path.read_bytes()
    if len(data) < 20:
        raise ValueError("Incomplete backup header")
    magic, wsp_len, wsp_crc, gphy_len, gphy_crc = struct.unpack_from("<5I", data)
    if magic != 0xF48BF48B:
        raise ValueError("Unrecognized backup magic")
    if len(data) != 20 + wsp_len + gphy_len:
        raise ValueError("Declared lengths do not exactly cover the backup")
    result = {"path": str(path), "size": len(data),
              "sha256": hashlib.sha256(data).hexdigest(),
              "magic": f"0x{magic:08x}", "components": []}
    start = 20
    for name, size, expected in [("wsp", wsp_len, wsp_crc), ("gphy", gphy_len, gphy_crc)]:
        component = data[start:start + size]
        actual = zlib.crc32(component)
        if actual != expected:
            raise ValueError(f"{name}: CRC32 mismatch")
        item = {"name": name, "file_offset": start, "size": size,
                "end_exclusive": start + size,
                "crc32": f"0x{actual:08x}", "crc32_valid": True,
                "sha256": hashlib.sha256(component).hexdigest()}
        if extract:
            extract.mkdir(parents=True, exist_ok=True)
            output = extract / f"{name}.bin"
            if output.resolve() == path.resolve():
                raise ValueError("Refusing to overwrite input")
            output.write_bytes(component)
            item["extracted_path"] = str(output)
        result["components"].append(item)
        start += size
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--extract", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.image, args.extract), indent=2))
