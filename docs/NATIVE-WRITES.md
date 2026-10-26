# Native write validation — 25 October 2026

These checks used the native V2 HTTP handlers on the development unit. Port 8
was confirmed link-down first; the management link on port 1 remained up. Each
candidate was followed by the contract readback and an independent GET. The
original setting was restored and checked before the next case. No Save
configuration operation was requested, and these checks do not establish
traffic behavior or reboot persistence.

| Operation | Candidate on port 8 | Result |
| --- | --- | --- |
| Default traffic priority | 0 → 1 | Verified; all original port priorities restored |
| Rate limits | Unlimited → ingress 64 / egress 128 Mbit/s | Verified; original full table restored |
| Traffic class → queue | Class 3, queue 3 → 4 | Verified; original full table restored |
| Queue scheduler | Queue 7, value 15 → 16 | Mismatch: readback 0; original full table restored |
| Corrected scheduler bounds | Queue 7, values 0 and 14 separately | Both verified; restored to 15 after each |
| Flow control | On → Off, preserving Auto/enabled | Verified; original configuration restored |

Unselected port configuration remained unchanged in each checked table.
Readback of actual link/EEE/counter telemetry can vary independently and is not
used as evidence of a configuration mutation. The rate-limit readback reports
Mbit/s values; this test does not measure achieved ingress/egress throughput.

## Scheduler mismatch and correction

The former 1..127 input range was wrong for this native interface. A request
with value 16 received HTTP acknowledgement but independently read back as 0.
The backend reported a mismatch rather than claiming success. The UI uses the
equivalent readback comparison and displays mismatch results separately.

Direct analysis of JSON parser `0x400048a0` and hardware helper `0x4000fe00`
shows the scalar being passed to a compact scheduler encoding. Zero selects
type 2; 15 selects type 0; other values select type 1 with a repeated-nibble
weight expression (`value * 0x1111`, truncated to 16 bits). This explains why
an unconstrained wide integer is not a valid proportional weight setting.
The exact traffic semantics of each scheduler type have not been verified.

Both Python and browser request contracts now admit only integer values 0..15.
The UI calls it Scheduler value and explains the special 0/15 cases. The public
pure QoS regression test accepts the valid boundary values and checks that 16
is rejected before any POST, rather than relying on HTTP acknowledgement.
Hardware values 0, 14 and the original 15 round-trip successfully.

The corrected full-CLI UI was installed through the native updater and booted
from slots 1/2. Its served HTML SHA-256 is
`29378646f972f5e3254b9e65bcecb67d1cc431c54649f33d6e9bff2047247976`.
UART confirmed DMA RX/TX, both image_ok flags and management forwarding. A fresh
Chrome login showed the corrected control; an input above 15 was blocked by
browser validation before the apply dialog. That test entry was discarded.

Private baseline, request/readback evidence and independent native analysis
are retained under ignored `artifacts/validation/`. No captured account data,
full configuration export or device identity is needed in this document.

## Remaining write coverage

Global classification, DSCP/CoS mappings, live spanning-tree/loop mode changes,
aggregation, DHCP snooping, management IPv4/VLAN, account changes and reboot
persistence are not established by these spare-port checks. EEE setters submit
port arrays and have not been tested here for possible uplink disturbance.
Keep these limitations separate from the completed 22-page browser/read sweep.
