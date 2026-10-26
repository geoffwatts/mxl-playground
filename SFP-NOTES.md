# Native SFP diagnostics — 25 October 2026

The GoodTop V2 device inventory establishes this front-panel mapping:

| UI port | Native cage | Device | Bus | MAC |
| --- | --- | --- | --- | --- |
| 9 | 1 | SFP_1 | I2C_1 | 13 |
| 10 | 0 | SFP_0 | I2C_0 | 9 |

Initial testing used empty cages. Later on 25 October, an owner-supplied BiDi
module passed identity/DOM, repeated-read and hotplug checks on both cages; see
the populated-module results below. Link down alone is never used to infer absence.

## Implementation

`tools/prepare_sfp_endpoint.py` constructs a bounded GET `/sfp.json` callback
alongside the existing jumbo endpoint. It accepts no bus/address/command input.
The existing JSON-route authentication applies. Other methods receive 405.

Native state getter `400d84c8` supplies presence: state 0 is unplugged, states
1/2 are plugged/link-up, other states remain unknown. Only a present module
triggers I2C reads. `device_get_binding` at `400df324` selects the fixed bus;
`4006d428` calls the native Zephyr I2C transfer operation with two 12-byte
messages per 16-byte chunk: one EEPROM offset byte, followed by a repeated-start
16-byte read. Sixteen chunks cover each 256-byte page. The vendor driver truncates
its outstanding receive count to eight bits, so the original single 256-byte
request wrapped to zero and returned a controller timeout (-116).
Addresses are fixed at seven-bit `0x50` (A0) and `0x51` (A2). No EEPROM content,
page selector, transmitter control or calibration setting is written. A2 is
requested only for identifier 3 with DDM advertised and no address-change flag.

The request uses 1088 bytes of local stack, plus 24 bytes of saved registers.
UART reports 6144-byte CivetWeb worker stacks. The tested populated-module workload retains 1744 bytes of worker stack headroom;
this observation does not bound every possible module/driver fault case.

The response is exactly 1056 bytes of `application/octet-stream`. Its eight-byte
header contains ASCII `MSFP`, version 1, count 2, and little-endian record size
524. Each record is: port, cage, presence (0 absent/1 present/2 unknown), native
state, A0 read state, A2 read state (0 unread/1 success/2 failure), signed 16-bit
A0/A2 errors, reserved 16-bit zero, 256 A0 bytes, 256 A2 bytes. All multibyte wire
fields are little-endian. EEPROM words and calibration floats are big-endian.

`designs/mxl-management/sfp.mjs` checks framing, fixed cage mapping, identifiers,
identity/calibration checksums, calibration flags and data readiness. Internal
and external calibration are handled; unknown/contradictory modes are withheld.
Zero power has no finite dBm representation and remains unavailable in dBm.
Transmitter-disabled power is withheld. Alarms and calibrated thresholds are
shown separately from current readings.

The decoding reference is the primary [SNIA SFF-8472 draft revision 12.4.5](https://members.snia.org/document/dl/27187).
No document text or vendor decoder code is bundled.

## Validation and limits

- Synthetic tests cover internal/external calibration, negative temperature,
  checksum failures, invalid flags/constants, zero power, disabled TX, not-ready
  state, alarms, malformed frames and both cage mappings.
- DOM tests cover the empty-cage display without invented zero readings.
- The current ARC plan has 558 instructions independently decoded with Ghidra/P-code.
  Registration is chained from the previously verified jumbo route wrapper.
- Native blob SHA-256:
  `c44640e73f83f70e1ecdfcf9eb66cf68b44998389aeba219788645703dac033d`.
- The specific real-module checks below passed. Linked optical traffic, further
  module/calibration types and adversarial error timing remain untested.

Private device/assembly/runtime evidence belongs under `artifacts/sfp/`, not
in a public source package. Installation and runtime results are recorded there
as they are obtained; offline validation alone is not a successful hardware test.

The first installed SFP build passed native authentication, 405 rejection of
POST, 12 repeated identical empty-cage reads and a post-read status check. The
served HTML hash matched the intended build and all 22 pages passed actual
native login/navigation checks. Both workers' measured high-water stack use was
4400/6144 bytes, leaving 1744 bytes unused. This is empty-cage evidence, not a
bound for populated modules. See private `runtime-validation.json`,
`login-and-navigation-validation.txt`, `install-uart.log` and
`postinstall-uart.txt` under `artifacts/sfp/`.


## Populated module, transfer-size fix and hotplug

The owner inserted an ATS-labelled SFP-10G-BX. Its checksummed EEPROM identifies
it as OEM HPBT3R2-LRT revision B, with 1330 nm transmit wavelength and internally
calibrated diagnostics. Serial/date identifiers remain in private captures.

A native 16-byte UART I2C read succeeded while the original web endpoint returned
-116 for a 256-byte request. Driver `4006e240` stores the outstanding read count
with `stb r2,[r13,0x45]` at `4006e464`; 256 becomes zero. The replacement reads
sixteen independently addressed 16-byte chunks at offsets 00..f0, stopping on the
first error and preserving its code. The response format and stack allocation
are unchanged. No EEPROM content or optical control is written.

The first chunk-loop build exposed a separate instruction issue: encoding
`0c210020` decoded as `cmp r17,r0` in Ghidra but triggered a CPU instruction
exception at `402c1322` on this unit. It was replaced by `mov_s r1,r17` followed
by the vendor short `cmp_s r1,r0`; the rejected fixture was removed. The current
build has executed successfully. Decoding alone must not be represented as
silicon execution proof. The failed intermediate build is not a release artifact.

With the corrected build:

- Both A0 identity checksums and the A2 calibration checksum pass.
- Twelve reads on port 9 and twelve after moving the same module to port 10
  pass, taking approximately 69–90 ms each. Identity bytes remain identical.
- Removal from port 9 is reported as empty, and insertion in port 10 as present,
  with identity and DOM, despite no optical link.
- Chrome displays identity, wavelength, live metrics and RX low-power alarm.
- Representative readings: 25.5 degrees C, 3.2977 V, 17.344 mA bias, -1.30 dBm TX;
  RX is at the module's -40 dBm floor with low alarm/warning, not proof of signal.
- Both CivetWeb workers remain at 4400/6144-byte high-water use (1744 unused),
  including after the cage move. Heap remains 9344 free / 23096 allocated,
  maximum allocated 24400. Uptime advanced through the checks without a reset.
- The direct Mac en10/port-8 path serves the expected UI at 100 Mbps full duplex.
  No VLAN, address or saved switch settings were changed for these tests.

Current combined jumbo/SFP/inventory endpoint SHA-256:
`805babe78b646e39445bc2654951c27c50f6337bf16ab981e9a600a884378081`.
Installed update SHA-256:
`bfd3639bf8b3655393ace0e36a395a976a6043b5cc4a56c9f65536e8778b35f5`.
The HTML asset is unchanged by this fix. Private evidence is under
`artifacts/sfp/populated-module/`, particularly `runtime-validation.json`,
`port10-hotplug.json`, `post-hotplug-resources-uart.txt` and the instruction logs.

`tests/test_sfp_transfer_plan.py` executes the generated loop's control flow
against a small independent I2C ABI model. It checks both pages/cages, each
byte covered once, bounds, and first/middle/final chunk failures without a retry.
These tests complement the independent instruction decoding and hardware results;
they are not a general ARC emulator. The full Python suite passes 69 tests.

The owner then performed two power cycles with the module in port 10. Identity
and DOM reads, empty port-9 reporting and UI access explicitly bound to en10 all
recovered after each. The second cycle's full UART header selected slots 3/4,
logged DMA RX/TX UP and ports 1/8 FORWARDING at 32.556 seconds, without the earlier
instruction exception. The first recorder attached after startup, so that cycle
has postboot uptime/HTTP/SFP evidence rather than a captured initial header.
These are two successful power-cycle checks, not a sustained optical traffic test.
