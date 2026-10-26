# Original 1.x to factory 2.0.0.4: the demonstrated migration

This describes the single GoodTop ZX310S-8T2XS experiment behind MxL Playground.
The offline builder now accepts other owners' backups when their boot area,
V1 partition map and all four firmware banks match the audited V1.0.0.6 profile.
Their own persistent data is preserved. This remains a one-unit-tested experiment:
an independent unit, recovery rehearsal and more configuration/forwarding tests
remain open.

The migration gets the switch onto the **factory** V2 baseline first. Installing
our replacement UI is a separate serial-bootstrap/custom-WSP operation described
in [INSTALL.md](INSTALL.md). A stock V2 image still enforces its signing policy.

## What changed

The development switch originally reported product firmware 1.0.0.6, WSP 1.0.45
and GPHY 0039. It now runs product firmware 2.0.0.4, WSP 1.0.79 and GPHY 0063.
The factory V2 update used here has SHA-256:

```text
085ce44aeffe82b75676c5784b915ab80cfa0262a1ec5356a47832a45af07426
```

Both WSP slots grow in the V2 map, moving the GPHY and persistent areas. The
external flash contains the A700 partition tag; the WSP also contains a compiled
default map. The migration builder requires the stock maps to agree and derives
the destination from the V2 compiled map. Merely copying V2 bytes into an old
WSP slot does not perform this migration. The stock firmware's web updater does
not migrate this partition table. The demonstrated V1 → V2 procedure therefore
requires an external SPI programmer and clip to rewrite the full device-specific
flash image; if in-circuit writes are unreliable, the chip must be isolated or
removed. This is separate from later custom-WSP updates over the web interface.

The boot area stays at 0..0xa000 and its executable bytes remain unchanged. The
builder updates its partition tag, places the vendor WSP/GPHY in both new slot
pairs, adjusts slot trailers and moves persistent areas while preserving their
contents. Area 5 grows from 16 to 32 KiB; its extension is filled with FF. Preserving
NVS bytes does not prove compatibility of every setting between firmware versions.

## Before opening a switch

Establish the actual flash marking, voltage and pin orientation. Our unit has an
8 MiB Winbond W25Q64JV-family SPI NOR. A similar enclosure or product name does
not prove identical internals. Disconnect normal switch power and external
connections before attaching a programmer. Check the programmer's supply **and
signal** voltages; a 3.3 V supply alone does not establish safe signal levels.

In-circuit reads worked on this unit, but writes intermittently failed while the
programmer back-powered the board. A powered USB hub helped some attempts; moving
to Linux did not remove all failures. If writes remain unreliable, isolate the
flash or remove it using suitable rework equipment. Reliable readback is required
before considering programming successful.

Keep a UART connection for boot evidence, but avoid supplying board power from
its adapter. The demonstrated console is 3.3 V TTL, 115200 8N1, without flow control.
Identify pins electrically; do not infer a header pinout from this guide.

## Acquire this switch's own complete backup

The following commands apply to the positively identified chip on our unit.
They read the main flash array, not SoC OTP or chip security registers.

```sh
flashrom -p ch341a_spi -c 'W25Q64JV-.Q' -r own-read1.bin
flashrom -p ch341a_spi -c 'W25Q64JV-.Q' -r own-read2.bin
shasum -a 256 own-read1.bin own-read2.bin
cmp own-read1.bin own-read2.bin
python3 tools/spi_layout.py own-read1.bin
```

Require two matching 8,388,608-byte reads. Store the backup privately, with its
hash, away from the working directory as well. Capture the factory UART boot
versions and `flash_map list`, and make a separate configuration export. A web
firmware export omits boot and persistent areas and cannot replace this backup.

Matching reads establish repeatability, not a proven ability to restore the chip.
A full original-backup restoration has not yet been rehearsed on this project.

## Build the candidate offline: supported source profile

The existing tool is `tools/build_v2_migration_candidate.py`. It verifies the exact
factory V2 input, both component signatures, map consistency, component/trailer
bounds and preservation of relocated data. It requires the separately acquired
76-byte secondary public-key record. That record is not a private signing key.

The `goodtop-zx310s-v1.0.0.6-8mib` source profile requires:

- Exactly 8,388,608 bytes and the audited ten-area V1 partition map.
- The audited complete boot area and each firmware bank, checked by separate
  SHA-256 hashes. These checks include boot tags, unused bank padding and slot
  state, not just a reported version string.
- An erased (`FF`) unpartitioned tail, so unknown data cannot silently be lost.
- The exact V2 factory update and valid WSP/GPHY signatures with the supplied
  public-key record and the source backup's GPHY key.

**The whole backup no longer needs to match ours.** Areas 5–9 may contain the
owner's own board/configuration, NVS and flashless data. The builder relocates
each area's bytes, checks preservation by hash, and verifies that any added
space is erased. The output manifest records those checks and the input hash.
No MAC address or saved settings from the development switch are substituted.

A different bootloader, patched boot record, firmware bank or slot state is
rejected, even if the UI says 1.0.0.6. Another V1 version or another model needs
its own audited source profile. Do not bypass these checks or substitute another
owner's full backup. Matching regions establish software equivalence, not proof
of identical hardware or compatibility of every preserved setting.

Install the dependencies in [BUILD.md](BUILD.md), acquire the public-key record
there, and run:

```sh
python3 tools/build_v2_migration_candidate.py OWN_ORIGINAL_BACKUP.bin \
  EXACT_FACTORY_V2_UPDATE.bin --secondary-key-tag ACQUIRED_PUBLIC_KEY_RECORD.bin \
  --output PRIVATE_V2_MIGRATION.bin
```

Review the generated manifest and independently re-parse the physical layout.
The resulting file is a complete device-specific SPI image, not a web update.
Keep it private. The source-only developer preview contains no vendor firmware
or device backup.

## Programming and checking the factory V2 result

Programming requires a verified **own-device** migration candidate. On the tested
chip the command shape is:

```sh
flashrom -p ch341a_spi -c 'W25Q64JV-.Q' -w PRIVATE_V2_MIGRATION.bin
flashrom -p ch341a_spi -c 'W25Q64JV-.Q' -r own-v2-readback.bin
cmp PRIVATE_V2_MIGRATION.bin own-v2-readback.bin
```

Flashrom normally verifies after writing; the separate full readback checks the
whole intended image again. Do not reconnect normal power while the programmer
is attached. A failed write leaves unknown contents: retain the backup, stabilize
the hardware/USB connection, and obtain readback rather than assuming that no
bytes changed. Never use the internal synthetic build scaffold as a SPI image.

On the demonstrated successful boot, UART reported bootloader 1.0.23, WSP 1.0.79
and GPHY 0063 in both pairs, then started the factory web server. The live
`flash_map list` matched this V2 layout:

| ID | Start | Size |
|---|---|---|
| 0 | 0x000000 | 0x00a000 |
| 1 | 0x00a000 | 0x2d6000 |
| 2 | 0x2e0000 | 0x02d000 |
| 3 | 0x30d000 | 0x2d6000 |
| 4 | 0x5e3000 | 0x02d000 |
| 5 | 0x610000 | 0x008000 |
| 6 | 0x618000 | 0x010000 |
| 7 | 0x628000 | 0x040000 |
| 8 | 0x668000 | 0x080000 |
| 9 | 0x6e8000 | 0x080000 |

Check the actual management address, factory login, model/port profile, link
mapping, retained settings and packet forwarding before attempting the custom UI.
Take a new matching pair of full SPI reads of this working factory V2 state.
This gives the later serial preflight a local V2 backup to compare against.

## Recovery boundary

This migration rewrites the boot sector as well as the partition layout. An
interruption can prevent UART startup; the UART shell cannot recover a switch
that never reaches it. External SPI restoration of this switch's own original
8 MiB image is the recovery path, subject to reliable programming and full
readback verification. Two firmware slot pairs do not prove automatic fallback.

Ordinary custom-WSP web updates after bootstrap use the inactive slots and have a
different failure boundary. Keep the full-layout migration separate from that
routine update path. Follow [INSTALL.md](INSTALL.md) for the current bootstrap
limitations and [RELEASE-PLAN.md](RELEASE-PLAN.md) for the remaining release gates.
