# Roadmap to a developer alpha

This source preview is intentionally narrower than a supported public firmware
release. One installed development unit supplies the current hardware evidence.

- [x] On-device UI, native web updates and clean user-supplied-firmware build.
- [x] Identity, jumbo, SFP diagnostics and browser/UART shared terminal.
- [x] LAG/LACP group summary and editor, grouped VLAN/PVID controls and current-state validation.
- [ ] LACP peer negotiation, failure/recovery, forwarding distribution and persistence tests.
- [x] Durable management-VLAN backend and UI with timed rollback; VLAN-1
      confirmation/cancellation and warm-start validation.
- [x] Read-only UART boot-area/partition admission against an own-device backup.
- [x] Source-only repository candidate, build and recovery documentation.
- [x] Experimental guarded serial/web coordinator and optional serial-only
      inactive WSP staging, with dry-run, readback and simulated failure tests.
- [ ] Stock-to-custom hardware rehearsal and complete serial-only WSP upload/boot.
      The coordinator remains experimental until those transitions are tested.
- [ ] Factory/custom/factory web round trip, retaining the boot-record patch.
- [ ] Integrated tagged-client management-VLAN and cold-power isolation tests.
- [ ] Remaining configuration-write, persistence and forwarding matrix.
- [ ] Linked optics, maximum-MTU forwarding and sustained traffic tests.
- [ ] Rejected-image behavior and full own-device SPI recovery rehearsal.
- [ ] Independent installation on a second positively identified unit.
- [x] Source/attribution review for experimental public GitHub source preview.
- [x] Per-region V1 migration admission with owner-data preservation checks.

An SSH server and additional vendors/models are later work. The SNTP/STP startup
timing investigation is deferred. See RELEASE-PLAN.md for the three installation
paths and INSTALL.md for the evidence/limits of the current serial operation.
