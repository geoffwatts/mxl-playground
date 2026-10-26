# MxL Playground release scope

Owner direction, 25 October 2026: use **MxL Playground** as the project name and
`mxl-playground` as the intended repository name. No public repository has been
created or renamed yet.

## One supported firmware baseline first

Initially target the exact factory 2.0.0.4 update already audited and used on
the development GoodTop ZX310S-8T2XS / reported A0 board: WSP 1.0.79 and GPHY
0063, with the 8 MiB V2 layout. The vendor input SHA-256 is
`085ce44aeffe82b75676c5784b915ab80cfa0262a1ec5356a47832a45af07426`.
Similar branding, port counts or chipset names do not establish compatibility.
Different factory revisions and vendor images are outside the first target.

## Installation paths to document

1. **Original 1.x switch → factory 2.0.0.4.** Document the full SPI acquisition,
   offline layout migration, preservation of board-specific data and settings,
   verified SPI programming and factory V2 boot checks. This path changes the
   partition map and moves persistent areas. Keep it separate from routine web
   updates. The existing experimental migration succeeded on one unit; full
   backup restoration and independent reproduction still need validation.
2. **Supported factory V2 → custom UI.** Provide a guarded serial bootstrap
   script and a coordinated first WSP installation. The serial change patches
   the external boot-configuration record, preserving bootloader executable
   code. Capture the original sector, admit only expected records/layouts,
   require verified write/readback and stop on unexpected output. Do not turn
   the intermediate boot-record-only state into a finished/rebooted installation:
   the custom WSP's DMA relocation is part of the coordinated procedure.
3. **Already bootstrapped V2 → subsequent MxL Playground updates.** Use the
   existing scripted native web uploader: explicit target and build hash,
   software/port-profile checks, sequential chunks, no automatic retries,
   inactive-slot update and postboot verification. This does not migrate a
   partition table or bootstrap an unmodified switch by itself.

## What exists and what remains

The clean WSP/UI builder, deterministic manifests, native web uploader and exact
manual UART instructions exist and have been exercised. The experimental
`tools/install_serial.py` now coordinates serial admission, boot-record readback
and the matched web upload. See [SERIAL-INSTALLER.md](SERIAL-INSTALLER.md) for
dry-run and serial-only WSP options. Simulated stock-record/failure-path tests
pass; actual stock-to-custom rehearsal and complete serial-only hardware
upload/boot remain open. It never reverses the patch or forces a reboot.

The read-only serial preflight is now implemented and exercised on the development
unit. It compares the entire boot area against an own-device V2 backup, pins the
boot executable and checks both partition maps. The separate MIGRATION.md guide
documents the original 1.x experiment and its whole-backup admission restriction.
The coordinator builds on that preflight; its initial stock-to-custom hardware
transition remains unvalidated.

Owner also requested native firmware download/upload in the replacement web UI:
export the current WSP/GPHY and provide a checked update/restore flow through
the existing manufacturer endpoints. This should serve units initially installed
over SPI/UART and allow returning to the exact supported factory V2 WSP/GPHY
without opening the switch. Native download and the new JavaScript custom
update flow now pass on hardware; the exact factory-image admission is tested
offline, with a browser factory/custom round trip still pending. A native export
is not a full SPI recovery image; a factory WSP/GPHY upload leaves the V2 layout.
Per the owner's explicit instruction, retain the boot-record patch permanently
for both custom and exact supported factory V2 firmware. Do not implement
boot-record reversal as part of update or restoration. Pin the factory image
and verify its management/forwarding behavior after reboot. Restoring the vendor
WSP/GPHY does not restore the original partition layout.

The current migration builder pins the development unit's entire original SPI
hash. It therefore intentionally rejects another owner's backup, including one
with different MAC/settings bytes. A public migration tool needs independently
audited checks of immutable code/layout regions while preserving that owner's
variable board/NVS data. Do not remove the whole-image guard without replacing
it with those checks. The migration how-to should distinguish a documented
one-unit experiment from a supported installer.

The first publication should contain source, build/patch tools and the how-to,
with the vendor image supplied separately. No device-specific full SPI image or
vendor binary redistribution is implied by the repository name or MIT licence.

See INSTALL.md for the currently demonstrated commands and recovery limits,
BUILD.md for the reproducible factory input, and REVIEW.md for publication scope.
