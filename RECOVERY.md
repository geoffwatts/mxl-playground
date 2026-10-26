# Recovery

Read this before the first write. HTTP exports contain WSP/GPHY only, not a
complete recovery backup. Keep this unit's full SPI backup, a known-working
bootstrapped recovery image, hashes and UART logs privately. Never substitute
another unit's dump.

## UI unavailable but UART works

Use a 3.3 V TTL adapter at 115200 baud, 8N1, no flow control. Do not connect the
adapter's power output. Identify the header electrically; there is no universal
header pinout. Close other serial clients before opening the port:

```sh
picocom -b 115200 --flow n /dev/YOUR_UART
```

Capture startup and `flash_map list`. Check active slots, WSP/GPHY versions, DMA
initialization and errors. An unfamiliar layout or record is a stop condition.
Automatic rejected-image fallback is untested: do not erase an alternate slot
or use an assumed slot-switch command.

For management-VLAN lockout, follow [MANAGEMENT-VLAN.md](MANAGEMENT-VLAN.md).
If the problem is saved configuration and losing all settings is acceptable,
the supported V2 shell exposes:

```text
chiptest reset_user_settings
chiptest reboot
```

Check the first command for errors before rebooting. It resets saved user
settings, including management addressing and VLAN configuration. Read the new
address from startup. Firmware and the boot-record patch remain installed.
This is not a factory-firmware restoration. The command was identified in live
help and handler analysis; an end-to-end reset/recovery rehearsal remains open.

## Restore the supported factory interface

If HTTP works, the custom Firmware page accepts the exact factory V2 image with
SHA-256 `085ce44aeffe82b75676c5784b915ab80cfa0262a1ec5356a47832a45af07426`.
Supply it yourself. Confirm/save unrestricted management policy first, keep
UART logging and use stable power. See [FIRMWARE-UPDATES.md](FIRMWARE-UPDATES.md).

This replaces WSP/GPHY and the UI. **Retain the boot-record patch permanently.**
It does not restore the V1 partition map. A factory/custom browser round trip
remains a release gate; earlier factory boot experience is separate evidence.

## A write timed out or its reply was lost

Stop, keep power stable and save the uploader report/UART output. Do not replay
a failed chunk, resume from an assumed offset, reboot reflexively or reverse
the boot record. Establish the actual selected slot, boot record and candidate
contents before choosing another operation. A lost reply cannot tell you which
bytes reached flash; no automatic recovery script is provided for this state.

## No boot / no usable UART

External SPI recovery is the remaining path. Disconnect normal power and external
connections. Verify chip marking, orientation, programmer supply and signal
voltages. In-circuit programming back-powered our board and caused intermittent
write/USB failures even when reads matched. Isolate or remove the flash if
programming cannot be made reliable.

Use only a reviewed, complete recovery image for this same device and layout,
containing the permanent boot-record patch and matching WSP. A raw stock backup
may lack the patch: keep it unaltered for evidence and separately prepare/review
a matching recovery target rather than blindly restoring it. The all-FF internal
build scaffold is never a recovery image.

Read the whole chip back after writing and compare every byte with the intended
image before reconnecting normal power. Then capture startup and check management
and forwarding. Full SPI restoration, rejected-image fallback and recovery on a
second unit remain uncompleted hardware gates.
