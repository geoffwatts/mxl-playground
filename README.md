# MxL Playground

A replacement management interface and native extensions for a researched
MaxLinear MxL862xx switch, running inside its existing Zephyr/WSP firmware.
Inspired by [RTLPlayground](https://github.com/logicog/RTLPlayground).

**Experimental developer preview.** Running on one GoodTop ZX310S-8T2XS,
originally on 1.0.0.6 and migrated to 2.0.0.4. This is source for local building
and review, not a universal firmware image or a supported stock-switch installer.
No vendor WSP, GPHY, bootloader, device backup or signing key is distributed.

**Only flash if you have a compatible SPI programmer, or can obtain one quickly
(for example overnight from Amazon where available).** A broken WSP may also
remove the UART shell; serial access alone is not guaranteed recovery.

## Features and evidence

- On-switch UI with switch name, location/contact, active navigation and a
  U/T/absent VLAN editor. Saved identity has warm-reboot evidence.
- Management pages for the recovered factory HTTP features, including STP,
  LLDP, aggregation, multicast, QoS and access controls. Not every write,
  persistence path or forwarding behavior has been hardware-verified.
- Jumbo controls and SFP identity/DOM, including both cages, hotplug and absent
  modules. Maximum-MTU forwarding and linked optical traffic remain untested.
- Management VLAN with timed rollback, confirmation and saved policy. Integrated
  VLAN-1 warm-start tests pass; integrated tagged-client/cold-power tests remain.
- Browser access to the real Zephyr shell, sharing the UART transport, behind an
  explicit flash/RAM warning and acknowledgement. No SSH server is installed.
- Native firmware download/upload, a session fix and DNS-context lifetime fix.

This is not Linux. A displayed control is not a claim that its entire feature
has passed validation. The vendor backend has one global login session: another
browser or diagnostic login can invalidate it. The terminal is privileged and
can overwrite flash/RAM or stop the switch booting.

## Supported starting point

| Item | Researched target |
| --- | --- |
| Retail unit | GoodTop ZX310S-8T2XS, 8 copper ports + 2 SFP+ cages |
| Factory-reported model/hardware | SKS3200-8E2X / A0 |
| Product firmware | 2.0.0.4 |
| Components | WSP 1.0.79, GPHY 0063, bootloader 1.0.23 |
| Flash | 8 MiB SPI NOR, V2 partition layout |
| Factory SHA-256 | `085ce44aeffe82b75676c5784b915ab80cfa0262a1ec5356a47832a45af07426` |

Model/hardware strings are software descriptions, not independent board
identification. Similar Horaco, Xikestor or other MaxLinear products are research
leads, not supported targets. A V1 unit needs separate layout migration;
uploading the V2 update alone does not do that.

## Installation path

1. Make two matching full SPI backups of this unit and confirm chip voltage,
   layout and UART access. Keep backups private.
2. Supply the exact factory image locally. Our patcher checks its SHA-256, copies
   vendor bytes from your input, applies the audited patches and inserts our
   UI/extensions. Generated firmware stays local. See [BUILD.md](docs/BUILD.md).
3. On the supported V2 layout, bootstrap over UART by changing the external
   boot-configuration record. Executable bootloader bytes are preserved. The
   matching WSP relocates a DMA helper that overlaps temporary boot RAM. See
   [INSTALL.md](docs/INSTALL.md). This coordinated first install remains experimental;
   the [serial installer](docs/SERIAL-INSTALLER.md) defaults to a read-only dry run;
   stock-to-custom hardware rehearsal remains open.
4. Transfer WSP/GPHY over the native web updater. After bootstrap, routine updates
   use the Firmware page or supplied uploader without repeating the serial patch.
   Verify UART startup and the served UI after each update.
5. Keep recovery available. Read [RECOVERY.md](docs/RECOVERY.md) before writing.
   Retain the boot-record patch for custom and supported factory updates.

The default serial operation changes a small boot record and transfers the image
over HTTP. An optional serial-only mode stages a full inactive WSP when the
shell still works, without rebooting or claiming successful boot. SPI is used for the
V1 layout migration experiment or recovery when boot fails. A/B slots are not
a demonstrated automatic recovery guarantee.

## Documentation

- [Building from source](docs/BUILD.md)
- [Serial admission, bootstrap and web upload](docs/INSTALL.md)
- [Experimental serial installer and serial-only WSP option](docs/SERIAL-INSTALLER.md)
- [Recovery, factory defaults and factory firmware](docs/RECOVERY.md)
- [Original V1 → factory V2 migration experiment](docs/MIGRATION.md)
- [Firmware page](docs/FIRMWARE-UPDATES.md), [management VLAN](docs/MANAGEMENT-VLAN.md)
  and [browser terminal](docs/TERMINAL.md)
- [Release gates](docs/RELEASE-PLAN.md), [roadmap](docs/ROADMAP.md) and
  [publication review](docs/REVIEW.md)
- [Contributing and offline checks](docs/CONTRIBUTING.md)
- [GitHub preview and publication path](docs/GITHUB.md)

## Licence and credits

New code is [MIT licensed](LICENSE). RTLPlayground-derived styling retains its
[original MIT notice](designs/mxl-management/LICENSE-RTLPlayground).
[REA](https://github.com/morluto/rea), Ghidra, Sony ARCv2 support and
[sks32kmon](https://github.com/geoffwatts/sks32kmon) informed the investigation.
See [THIRD_PARTY.md](docs/THIRD_PARTY.md). Our licence does not relicense vendor code.
