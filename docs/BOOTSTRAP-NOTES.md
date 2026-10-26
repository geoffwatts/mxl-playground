# First-install coordination: current evidence

26 October follow-up: `tools/install_serial.py` now implements the experimental
coordinator described below, with strict target/image checks, a persistent UART
owner, verified boot-sector readback, sequential HTTP upload and postboot checks.
It also stages an inactive WSP over serial on already-patched units. See
[SERIAL-INSTALLER.md](SERIAL-INSTALLER.md). The dated investigation below remains
the evidence behind the design; actual stock-to-custom hardware rehearsal is
still open and the permanent boot patch is never reversed to test that branch.

25 October 2026. The demonstrated boot-record change and subsequent web updates
are distinct from a validated automated stock-to-custom installation. The latter
remains a release gate. No stock WSP was installed or boot policy changed during
this investigation.

## Admission now checked by a read-only tool

`tools/inspect_bootstrap.py` captures the live 40 KiB boot area with fixed 256-byte
UART reads, plus the live flash map and kernel version. It pins boot executable
bytes 0x400..0x6fff to SHA-256
`15da8f9d2a2e477716bbf163e97ae3d902c5aad2ae4d215cd55fabaca1c902b3`,
requires the exact V2 map in both boot tags and shell output, and compares the
whole boot area with an own-device full V2 backup. Only the exact recognized
stock or experimental 40-byte record at 0x264 is normalized for comparison.

On the development unit, all bytes outside that record matched the local factory
V2 migration backup. The live record was the expected experimental arrangement;
executable bootloader bytes were unchanged. The capture does not verify the
current entire WSP, firmware version, forwarding or recovery. It is deliberately
not a write-capable installer. Captures remain private and are not packaged.

Tests exercise ANSI/echo parsing, missing/duplicate/out-of-order/excess hex rows,
wrong maps/devices, truncated backups, changed boot code, foreign boot data,
unknown records, serial fragmentation, forbidden commands and timeout cleanup.

## Upload integrity and boot authentication are separate paths

The exact factory V2 WSP's recovered HTTP upload chain is:

- `0x40013fec`: POST wrapper into `0x400178e0`.
- `0x400178e0`: parses framing and component lengths, selects destination areas,
  checks slot bounds, erases, streams data, compares accumulated checksums with
  the container fields, handles trailer data and schedules reset on success.
- `0x4001775c`: streams bounded component chunks to flash and updates their
  checksum using `0x40026eb4`.
- `0x40026eb4`: complemented, nibble-table CRC update. The table at component
  offset `0x1febc0` and the recovered algorithm match Python zlib CRC32 on eight
  combinations of payload/initial seed, including `123456789` and firmware bytes.
- `0x4001767c`: reset callback thunk to `0x400851a8`.

No ECDSA validation call was identified in that recovered upload chain. This
supports the interpretation that the response's “Verification: Success” is the
upload CRC/integrity result, rather than proof of a firmware signature. Boot
signature enforcement remains the separate bootloader path already documented.
This analysis applies to the exact factory image, not every vendor's updater.

The upload timeout callback at `0x40017748` logs an upload timeout and calls
`0x400176ac` to clear its transfer state. The engine supplies a 5000-unit timeout
argument between chunks. This is another reason not to insert a lengthy serial
inspection or an operator prompt into an in-progress chunk stream. A hypothetical
“upload most bytes, pause, patch, finish” protocol has not been validated.

Private analysis outputs: `artifacts/validation/bootstrap-preflight/` and the
previous `artifacts/native-ui/v2-upgrade-{engine,writer}.txt`.

## Proposed first-install sequence, still requiring rehearsal

The evidence supports preparing all files and checks before mutation, verifying
serial and HTTP address the same physical unit, saving its boot sector, applying
and reading back the boot record, and uploading the matched DMA-relocated WSP in
the same running stock session. There must be no reboot into the stock WSP with
only the record changed. The updater's reboot should be the first boot using the
new arrangement and custom WSP together.

Before scripting that as an installer, verify the live stock updater against the
audited baseline, bind the UART and HTTP targets, independently check the custom
WSP's DMA relocation and unchanged GPHY, and define failure states after each
operation. Once flash mutation is uncertain, do not blindly retry, roll back or
reboot: the selected image and boot policy must be established first. An active
and alternate slot are not a proven recovery mechanism.

The existing unit is already bootstrapped. Re-running the read-only preflight
cannot rehearse its original stock-to-custom transition. That rehearsal and
original-image recovery remain open; do not mark the public serial installer
complete from the current preflight success.

## Routine update verification improved

`tools/upload_native_ui.py --verify-ui` now reads the fixed setup/login asset
operands from the selected update and derives the expected HTML SHA-256 directly
from its bytes. After upload success and the scheduled reset delay it retries
anonymous reads, not writes, until the served asset matches or a bounded deadline
expires. It does not create another login session. Its read-only verifier matched
the current installed asset on the first request.

A matching asset is evidence of management availability and UI contents. It does
not independently establish a reboot, selected slot, DMA logs or forwarding.
Failure reports retain that distinction, and a failed upload is never retried.
Tests cover temporary unavailability, an old asset followed by the correct one,
timeout/mismatch, matching setup/login pointers and asset bounds.

The timer-observer development upload timed out at offset `0x2bcaf0`; UART
reported `FW upload timeout` and the previous image remained live. Its active
trailer remained populated and the unfinished alternate trailer was erased.
That failed transfer was not resumed. After inspecting this state, a fresh
transfer used the uploader's new sequential standard-library HTTP client,
removing the per-chunk curl process launches. All 77 chunks succeeded: initial
erase/request plus transfer took 56.23 s, of which 13.74 s was after the first
request (slowest later request 0.394 s). This improves transfer overhead; it
does not establish why the earlier transfer exceeded the updater's deadline.
Each request now records elapsed time and a transport-error type. A lost reply
still stops without replaying that POST. Loopback HTTP tests check exact raw
payloads, cookie/content type, server-requested closes and no lost-reply retry.

The complete post-upload integration subsequently passed with the existing
known-good custom image: all 77 chunks returned HTTP 200, UART selected slots
3/4 and logged DMA RX/TX UP, both image_ok flags and port 1 FORWARDING at 37.735
seconds. The anonymous verifier matched the selected UI after six read attempts.
The firmware and UI bytes were unchanged by this test. Machine-readable private
evidence is `artifacts/validation/updater-verify-cycle/validation.json`.
