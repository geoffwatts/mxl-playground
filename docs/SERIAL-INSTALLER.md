# Experimental serial installer

**Only flash if you have a compatible SPI programmer, or can obtain one quickly
(for example overnight from Amazon where available).** Delivery availability
varies. Check supply and logic voltages; a supply labelled 3.3 V alone is not
enough. The Zephyr UART shell lives inside WSP. It can recover a broken web UI,
but if WSP fails before the shell starts, serial flashing is unavailable and
external SPI recovery may be needed.

This tool supports only the audited factory **2.0.0.4 / WSP 1.0.79.79 / GPHY
0063**, 8 MiB V2 layout described in README.md. It does not migrate V1 units,
replace executable bootloader code, alter partitions or reverse the boot patch.
First installation is experimental: the stock-to-custom write branch has local
simulation tests; the development switch is already patched and is never
unpatched to rehearse that transition. See [RECOVERY.md](RECOVERY.md).

## Prepare everything before writing

Have this unit's own verified full **V2** SPI backup. A V1 backup or a web export
does not satisfy that input. Supply the exact factory update and build a clean
custom update with the full management runtime and terminal using BUILD.md.
The installer checks the explicit custom SHA-256, container CRCs, unchanged GPHY,
DMA relocation, pinned extension code, hooks and factory-derived base. It does
not sign custom firmware. Trust/review the UI source you build.

Connect a 3.3 V TTL UART at 115200 8N1 without flow control. Do not connect the
adapter's power output. Close picocom/screen and other serial clients. Keep a
stable HTTP management path and power. For an already-custom unit, disable and
save management-VLAN isolation first. Avoid other logins during installation.
The installer uses Python's Unix serial APIs on macOS/Linux, plus `curl` for
HTTP and optional OpenSSH for a remote UART. It needs no administrator access
when your account can already open the UART device.

## Default: serial bootstrap, then HTTP image upload

First run without `--install`:

```sh
python3 tools/install_serial.py \
  --vendor input/vendor-v2.bin \
  --image artifacts/developer-update/native-ui-update-EXPERIMENTAL.bin \
  --expected-sha256 EXACT_CUSTOM_BUILD_SHA256 \
  --backup input/OWN_FACTORY_V2_SPI_BACKUP.bin \
  --port /dev/YOUR_UART --address SWITCH_IPV4 \
  --output-dir artifacts/install-dry-run
```

The password is prompted, or read from `MXL_UI_PASSWORD`. Credentials/cookies
stay in memory. To access a UART on an authorized SSH host, add `--ssh USER@HOST`
and use its serial path. Optional `--ssh-interface en0` binds the SSH connection
to a local interface on platforms supporting `ssh -B`. SSH runs only the UART
agent, not the HTTP uploader or filesystem inspection. Logs remain local.

The dry run captures the complete boot area, checks it against the own-device
backup, pins the boot executable and both partition maps, reads the active WSP
base using the native updater's register, and matches UART/HTTP MAC identities.
It checks the running native firmware export against the factory or audited
custom profile. It never writes flash or RAM or reboots.

For the write run, repeat with a **new** output directory and append:

```text
--install --spi-recovery-available
```

The tool saves a private journal and boot backup before mutation. A stock record
receives exactly the documented 40-byte edit. It requires the native Read/Erase/
Write/Verified acknowledgements and compares the entire first sector afterward.
An already-patched record is left alone. The matched WSP/GPHY is then uploaded
in sequential native HTTP chunks without an intermediate reboot or prompt.
Only the native updater schedules a reboot. The tool checks the served UI hash,
complete boot-area preservation, new active slot and UART DMA startup. This does
not validate packet forwarding or power-loss recovery.

Any timeout, lost reply, unexpected bytes or failed readback stops without a
write retry, boot-record rollback or forced reboot. The first-sector erase and
HTTP upload are **not transactional**. Keep the journal, inspect UART and follow
RECOVERY.md; do not blindly restart an ambiguous operation.

## Optional: serial-only WSP transfer

Use this when HTTP is unavailable but the native shell and flash driver still
work on an **already-patched V2** unit:

```sh
python3 tools/install_serial.py \
  --vendor input/vendor-v2.bin \
  --image artifacts/developer-update/native-ui-update-EXPERIMENTAL.bin \
  --expected-sha256 EXACT_CUSTOM_BUILD_SHA256 \
  --backup input/OWN_FACTORY_V2_SPI_BACKUP.bin \
  --port /dev/YOUR_UART --serial-wsp --wsp-slot 1 \
  --output-dir artifacts/serial-wsp-dry-run
```

Choose slot **1 or 3** explicitly; the tool rejects the running slot. The dry run
reports the active slot and checks the native flash-shell/slot-reader code and
both live GPHY banks, including their end markers. An interrupted web update
that also damaged GPHY needs a separate recovery plan; this WSP-only mode will
refuse it. Repeat with a new directory and `--install --spi-recovery-available`
to program. No HTTP connection or password is used in this mode.

Only the selected inactive WSP is erased/programmed, in 4 KiB sectors and bounded
128-byte writes. Each sector is read back byte-for-byte. The destination's end
marker is invalidated first and committed only after all body sectors verify.
The running WSP, GPHY, boot area and settings are not programmed. This is slow:
expect tens of minutes or longer at 115200 baud. There is no
automatic resume after interruption.

Success means **staged and read back**, not selected or booted. This mode does
not reboot, force slot selection or establish automatic fallback. Full-size
transfer/commit sequencing is covered by a simulated flash test; a complete
serial-only hardware upload and subsequent boot remain a separate validation
gate. Do not describe it as boot-ROM recovery or a substitute for a programmer.

## Validation so far

The development unit passed both live dry runs: serial + HTTP identity/export
admission, and serial-only flash-shell/active-slot/both-GPHY-bank admission without HTTP.
The write-enabled coordinator then completed all 77 native upload chunks,
changed the running WSP slot from 3 to 1, observed UART DMA startup, matched the
new UI hash and verified the entire boot area was unchanged. The record was
already patched, so this run deliberately issued no boot-record write.
The serial-only erase/write/readback mechanism was also exercised on one 4 KiB
UI sector of the inactive slot, restoring its exact original bytes. The running
slot and boot sector remained unchanged and no reboot was issued. This checks
the actual native acknowledgements and bounded write size; it is not a complete
serial-only image installation or boot test.

Local tests cover the stock-record write/readback sequence, false verification
acknowledgements, changed sectors, transport permissions, active-slot rejection,
full-size simulated serial programming and interrupted/premature HTTP replies.
The actual initial stock-to-custom transition remains untested on a stock unit.

## Private outputs

Each new output directory is private (0700); captures/journal files are 0600.
It contains `state.json`, `uart.log`, boot-area captures and, in HTTP mode, the
running firmware export. Do not commit or post these files: they may contain
device identity, vendor firmware and board-specific records. Source packaging
excludes them.
