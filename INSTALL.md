# Experimental installation and recovery

An experimental guarded [serial installer](SERIAL-INSTALLER.md) is now supplied;
stock-to-custom hardware rehearsal remains open. Only flash if you have a
compatible SPI programmer or can obtain one quickly (for example overnight from
Amazon where available). UART recovery depends on WSP still providing its shell.
Use the tested hardware and
V2 layout in the project README. Keep this switch's own
verified full SPI backup and a working programmer available. A web export omits
boot/configuration regions and is not a substitute for that backup.

For the separate, one-unit-tested 1.x-to-factory-V2 path, see
[MIGRATION.md](MIGRATION.md). It changes the full flash layout and is not a web
update or a generally supported migration installer.

## Read-only serial admission check

`tools/inspect_bootstrap.py` compares the entire live 40 KiB boot area with this
switch's own full V2 SPI backup. It requires the audited executable hash and
matching partition maps in both the boot tags and live `flash_map list` output.
Only the exact stock/experimental 40-byte boot record may differ. Unexpected
records, bytes, devices, incomplete hex dumps and timeouts stop the check.

Close picocom/screen before running it. It uses 115200 8N1 without flow control,
restores the port settings on exit, and sends only fixed read commands. Choose a
new private output directory each time; captures may contain board-specific data.

```sh
python3 tools/inspect_bootstrap.py --port /dev/cu.YOUR_UART \
  --backup OWN_FACTORY_V2_SPI_BACKUP.bin --output-dir PRIVATE_PREFLIGHT_DIRECTORY
```

For a UART attached to a Linux host, add `--ssh USER@HOST` and use its serial
device path. SSH runs only the serial reader; it does not copy the backup to the
host or inspect its other devices/files. Outputs remain local. SSH access and
physical UART targeting must already be authorized.

This is admission evidence, not a full device backup, firmware-version check,
power-loss guarantee or installer. It never writes flash/RAM or reboots. The
development unit passed against its factory V2 migration backup: all boot-area
bytes outside the recognized record still match. This does not admit another
unit's backup or establish the stock-to-custom installation sequence.

## Bootstrap: what has actually been demonstrated

An external-flash boot record at 264..28b writes 0001164a to reused boot RAM
70006f18. In the observed early path this changes the WSP verification policy
bit (status word XOR 00020000), while preserving the GPHY verification path.
It does not recover a private key, forge a signature, change OTP or patch the
executable bootloader. No stock HTTP endpoint that writes this record has been
established. Stock web upload alone is therefore not a proven bootstrap.

These addresses and bytes apply only to the exact researched image/layout.
Before any change, capture the full SPI contents, UART boot/version output,
`flash_map list`, and `flash read flash_mxl 0x264 -d 0x28`. On the original
unmodified record the first word is ff5200ad and the following nine words are
zero. An unexpected original value is a stop condition, not permission to reuse
this command on another image.

The demonstrated UART operation is:

```text
flash mod flash_mxl 0x264 ffcc0033 0c000000 04000000 186f0070 4a160100 ff5200ad 00000000 00000000 00000000 00000000
flash read flash_mxl 0x264 -d 0x28
```

`flash mod` performs a sector read/erase/write, preserving the other bytes in
that sector; it must report Read/Erase/Write OK and Verified. The 40-byte edit
is contained in the first 4096-byte erase sector. Power loss while that sector
is erased can remove boot records and require external SPI recovery.

The RAM location overlaps the original DMA helper. Our WSP relocates the helper
before using this arrangement. **Do not reboot an original WSP as a supposed
finished installation after only installing the boot record.** The bootstrap and
custom WSP installation are an experimental coordinated operation with an unsafe
intermediate state. The serial installer coordinates this sequence, but does not
make the flash write and upload transactional.

## Routine native update after a working bootstrap

Use a known-built inactive-slot update, with UART logging and stable power.
The uploader requires an explicit address/hash, authenticates in memory, admits
only the tested V2 software/hardware/port profile, checks framing and sends the
OEM protocol's sequential raw 41000-byte chunks. It never retries a failed chunk
or performs partition migration. A password is taken from MXL_UI_PASSWORD.
Chunk uploads use one standard-library HTTP client instead of launching curl
for each chunk; the report records each request's duration and any transport
error. A timeout still requires inspecting UART and slot state before deciding
whether a fresh transfer is appropriate. Do not resume an uncertain offset.

```sh
python3 tools/upload_native_ui.py --address SWITCH_IPV4 \
  --image artifacts/developer-update/native-ui-update-EXPERIMENTAL.bin \
  --expected-sha256 EXACT_BUILD_HASH --report artifacts/upload-result.json \
  --verify-ui
```

With `--verify-ui`, the uploader derives the expected HTML hash from the actual
image's setup/login pointer and length operands. After the scheduled reset delay,
it polls anonymous read requests until the served login asset matches, or the
verification deadline expires. It does not log in again, resend the update, or
retry a failed write. A matching asset proves management availability and the
served UI contents; it does not prove that a reboot occurred, selected slots,
DMA initialization or packet forwarding. The complete post-upload integration
passed on the development unit: 77 chunks were accepted, UART selected slots
3/4, logged DMA RX/TX UP and both image_ok flags, and port 1 reached FORWARDING.
The anonymous verifier matched the selected UI after six read attempts. This is
warm-update evidence, not a cold start, sustained forwarding test or rejected-image
recovery test.

Do not treat upload success as boot success. Verify selected slots, DMA RX/TX UP,
image_ok/checksum results, forwarding and management access in the boot/runtime
evidence. The development unit has updated in both A/B directions; automatic
fallback from a rejected/damaged image is still untested.

Ordinary inactive-slot updates differ from V1-to-V2 migration. Migration rewrites
the full layout and relocates firmware/settings; an interrupted boot-sector
write can also lose UART startup. Migration remains outside this update tool.

## Recovery and factory firmware

The owner has explicitly chosen to retain the existing boot-record patch
permanently, including when restoring the exact supported factory V2 WSP/GPHY.
The original firmware is reported to boot with the patch. Update and restoration
workflows must not reverse the bootstrap or change partition layout.

Factory firmware restoration means the original WSP/GPHY and vendor interface;
it does not restore the original V1 layout or remove our boot-record patch.
The factory image must match the known supported V2 image exactly. Verify
management, forwarding and UART startup after installation; do not infer all of
those from an HTTP upload acknowledgement. The earlier RAM-overlap investigation
still motivates those checks but is not an instruction to reverse the record.
Automatic fallback from a rejected/damaged image remains untested.

See [RECOVERY.md](RECOVERY.md) for factory defaults and recovery decision paths.
If UART cannot boot, use a reviewed own-device recovery image retaining the
permanent boot-record patch and matching WSP, with external power
disconnected and the programmer's supply/logic voltages checked. In-circuit
programming back-powered this board and produced intermittent CH341 failures;
reads alone did not establish write reliability. Isolation or chip removal may
be necessary. Obtain a post-write readback and compare the entire file against
the intended own-device backup before reconnecting normal power. Never restore
another owner's full dump or a synthetic build scaffold.

Full original-backup restoration remains an explicit hardware release gate;
this guide does not claim that the procedure has already been demonstrated.
