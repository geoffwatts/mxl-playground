# Offline developer build

Tested development tools: Python 3.14.8, cryptography 50.0.2, Node.js for pure
frontend tests. Endpoint instruction verification used Ghidra 12.1.4 with Sony
ARCv2 support. Tool binaries and dependencies are not bundled.

The endpoint builders use committed, independently decoded opcode/branch
fixtures. They reproduce only the known instruction plans; changed branches
must be assembled and independently decoded again with Ghidra. They are not a
general ARC assembler. The Ghidra scripts remain included for that review.

## Source-only UI and native endpoints

From the extracted source root:

```sh
python3 tools/build_native_ui.py --without-cli --output-dir artifacts/ui
python3 tools/prepare_jumbo_endpoint.py
python3 tools/build_jumbo_endpoint.py
python3 tools/prepare_sfp_endpoint.py
python3 tools/build_sfp_endpoint.py
python3 tools/prepare_inventory_endpoint.py
python3 tools/build_inventory_endpoint.py
node --test tests/sfp.test.mjs tests/inventory.test.mjs tests/qos.test.mjs tests/live-session.test.mjs
```

Expected native endpoint hashes:

- Jumbo alone: `a2ea068058ce6d5ec8b5c6e062af449b8ba8d489d32b2bad89c8335f73d5cedb`
- Jumbo + SFP: `c44640e73f83f70e1ecdfcf9eb66cf68b44998389aeba219788645703dac033d`
- Jumbo + SFP + inventory: `805babe78b646e39445bc2654951c27c50f6337bf16ab981e9a600a884378081`

These include the populated-module fix: sixteen 16-byte I2C reads per EEPROM
page. The vendor driver's eight-bit read counter cannot represent 256. The
initial chunk-loop comparison also exposed an instruction encoding that Ghidra
decoded but this silicon rejected; it was replaced with the vendor short form
and removed from the opcode fixtures. Independent decoding is required, but
does not replace real-device execution tests.

The shared browser/UART terminal is compiled with the pinned ARC EM4 toolchain
in `toolchain/arc`. Build it with `python3 tools/build_console_endpoint.py
--output-dir artifacts/console/endpoint`, then independently decode its emitted
instruction plan before installation. The exact supported extension SHA-256 is
`bb5d240444e9f007f98108ff549829de1f6b559f7c67925bf4d7f940f918f91c`.
Pass `--console-endpoint artifacts/console/endpoint/endpoint.bin` to the native
or clean developer update builder, together with the audited full management
runtime. The builder rejects HTML that overlaps its reserved code window.
See [terminal operation and validation](TERMINAL.md).

To build the current full management-VLAN/terminal profile, first create the
jumbo/SFP/inventory endpoints above, then:

```sh
docker build --platform linux/amd64 -t mxl-arc-build:bookworm toolchain/arc
python3 tools/build_management_runtime.py --full --output-dir artifacts/management-vlan/native-runtime-full
python3 tools/build_console_endpoint.py --output-dir artifacts/console/endpoint
```

The management runtime must have SHA-256
`3fe9c6d5a16293ee7c28edb90389d5800293637edb5a08c98111763ac091c819`.
Its C/header/linker sources are included. The toolchain build downloads Debian
packages; subsequent extension compilation runs with container networking off.
The pinned toolchain and exact output hashes are part of this target profile;
unexpected output is a stop condition, not a reason to relax admission.

## Where to get factory firmware 2.0.0.4

This build targets **XikeStor SKS3200-8E2X, non-PoE, V2.0.0.4**. It does
not accept an arbitrary "latest" firmware or the similarly named `-P` model.

Start at the official [XikeStor Download Center](https://www.xikestor.com/download-center/),
then select **Switch → Smart Managed → SKS3200-8E2X → Firmware / Driver**.
As checked on **26 October 2026**, this page lists versions through V2.0.0.3
and directs owners to their seller or XikeStor support to obtain firmware;
it does not provide a V2.0.0.4 binary link.

The [older official download centre](https://seekswan.com/user/pages/download-center.html?type_id=88)
still has a V2.0.0.4 catalogue record for this model. Its public catalogue API
(`https://seekswan.com/index/DownloadFile/getDownloadFileByType`, POST
`download_type_id=88`) returned entry **326**, file ID **4605**, version
**V2.0.0.4**, dated **2026-10-18**, when rechecked on 26 October 2026.
The older portal may require a CAPTCHA or be unavailable. A catalogue entry
is evidence of the version, not a verified working binary download URL.

If you cannot obtain it through the portal, ask the seller or
[XikeStor support](https://www.xikestor.com/contact-us/)
(`support@xikestor.com`) for this exact input:

> Please supply the original non-PoE SKS3200-8E2X V2.0.0.4 firmware update,
> dated 2026-10-18. The older official catalogue identifies it as entry 326,
> file ID 4605, MD5 `01f2d96d10088761ece67dbf03e08d8d`.
> Our reference file is named `wsp_mxl862xx_update_image_fca.bin` and is
> 3,145,556 bytes. Please confirm the model and version before supplying it.

Our baseline was supplied by the development unit's owner; its MD5 matches
that official catalogue record. We have **not verified a currently working
public direct download**. This repository does not mirror vendor firmware.
Keep your acquired original privately alongside its checksums.

| Check | Required factory input |
| --- | --- |
| Filename of reference input | `wsp_mxl862xx_update_image_fca.bin` |
| Size | 3,145,556 bytes |
| SHA-256 | `085ce44aeffe82b75676c5784b915ab80cfa0262a1ec5356a47832a45af07426` |
| Vendor catalogue MD5 (identification only) | `01f2d96d10088761ece67dbf03e08d8d` |

Save the file as `input/vendor-v2.bin`, then check it locally:

```sh
# macOS
shasum -a 256 input/vendor-v2.bin
# Linux
sha256sum input/vendor-v2.bin
```

The SHA-256 must match exactly; a matching filename/version is insufficient.
A firmware backup exported from a switch may use different packaging and is
not automatically interchangeable with this factory update. Do not relax the
builder's input checks to accommodate a different file.

**The vendor prohibits ordinary V1 ↔ V2 cross-updates.** Obtaining this file
does not migrate a V1 switch's flash layout. Read [MIGRATION.md](MIGRATION.md)
for the separate experimental SPI migration and recovery requirements.

## User-supplied firmware inputs

Supply the unmodified audited V2 update yourself. Its SHA-256 must be exactly
`085ce44aeffe82b75676c5784b915ab80cfa0262a1ec5356a47832a45af07426`.
Also supply the acquired 76-byte secondary A000 public-key record. This is a
public verification key, not a private signing key. No keys from a different
board should be substituted. Alternatively, save the output of the read-only
UART command `chiptest mem_rd 0x00107000 19` to a private text file and pass
`--key-log input/public-key-uart.txt` instead of `--key-tag`. This address is
specific to the supported target. The record is in internal memory; it was not
found in the development unit's SPI backups. The builder checks its framing and
CRC and requires it to verify the exact factory WSP signature before patching.
Vendor firmware redistribution rights have not
been established; the source preview contains none.

Install cryptography in an isolated environment if needed; the tested version
is pinned in `requirements-build.txt`. No installation is needed for HTML or
endpoint assembly alone.

```sh
python3 tools/build_developer_update.py \
  --vendor input/vendor-v2.bin --key-tag input/secondary-public-key-tag.bin \
  --html artifacts/ui/switch-ui.html \
  --endpoints artifacts/management-vlan/native-runtime-full/endpoint.bin \
  --console-endpoint artifacts/console/endpoint/endpoint.bin \
  --output-dir artifacts/developer-update
python3 tools/native_layout.py artifacts/developer-update/native-ui-update-EXPERIMENTAL.bin
```

The published source can contain the factory SHA-256, patch offsets, our own
code and build scripts without containing the vendor firmware payload. Users
supply the factory file locally; no upload to a build service is required.
Avoid distributing whole-image binary deltas: they may embed copied vendor
bytes. This builder copies required vendor code from the user's input at build
time instead. Its generated firmware is a private local output, excluded from
the source archive.

This emits an inactive-slot update and a manifest, **never a full SPI image**.
The build is independent of our device's backup, MAC and saved settings. It
reconstructs the DMA relocation directly from the audited vendor WSP, checks
original instructions, preserves the entire shared HTTP header template, bounds
the UI/code additions and rebuilds container CRCs. Manifests record input/output
hashes and every declared patch region. The WSP signature is intentionally
invalid after editing; the GPHY bytes are unchanged.

Repeat builds with identical inputs must have identical output hashes. Builders
reject unknown vendor input, unexpected original bytes, changed native blobs,
asset overflow and attempts to overwrite inputs. This is a reproducible build,
not evidence that the resulting image is compatible with another physical unit.

## Read-only diagnostics

```sh
python3 tools/collect_diagnostics.py --address SWITCH_IPV4 --output artifacts/diagnostics.json
```

The password is prompted or taken from MXL_UI_PASSWORD. The collector makes one
login followed by fixed read requests. Its report excludes credentials, cookies,
MAC/IP fields, raw module EEPROM and serial numbers. It does not download saved
configuration, firmware or call the LLDP status handler (which has a startup
side effect). Inspect even a sanitised report before sharing it.
