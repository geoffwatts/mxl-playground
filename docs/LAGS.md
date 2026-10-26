# LAGs, LACP and VLAN membership

The supported V2 backend already implements static aggregation and LACP.
MxL Playground exposes them under **LAGs & LACP**, with a configured-group
summary and a per-port editor. This feature does not install TP-Link firmware.

## Configure a group

1. Configure identical VLAN membership, PVID and accepted-frame settings for
   the proposed member ports before enabling aggregation. Match their link
   settings and configure the peer's aggregation mode appropriately.
2. Under **LAGs & LACP**, choose **Static LAG** or **LACP** for at least two
   ports and assign the same group ID. IDs 0–15 are the backend's native IDs;
   **Independent** disables aggregation on a port.
3. Apply aggregation and review the readback. Save configuration to retain it
   after reboot. Applying changes may interrupt traffic or management access.
4. Use the collapsed negotiated-state diagnostics to inspect what the backend
   reports. A configured group is not proof of successful LACP negotiation or
   aggregated forwarding.

Before sending a group change, the native browser transport and Python backend
read current VLAN membership and port defaults. They reject incomplete VLAN
reads and proposed members with different VLAN/PVID/frame policies. The backend
also requires at least two ports in a group using the same aggregation mode.
A speed/duplex match and the peer's settings still need operator verification.

## Edit VLANs as a group

The VLAN matrix labels member ports with their configured LAG. The VLAN editor
provides a U/T/excluded control for each group, plus **Assign PVID to group**.
Changing an individual member's membership changes every member of that LAG.
Group PVID checkboxes and per-port PVID/frame controls also update together.

A group with inconsistent existing membership shows **Mixed**; choose one
consistent membership before applying. The native API still receives physical
port membership, not a fabricated extra switch port. Groups remain configured
through the manufacturer's existing aggregation API.

Immediately before VLAN/PVID changes, the transport re-reads aggregation
configuration and validates group consistency. It does not trust a stale LAG
snapshot supplied by the browser form. Multiple operations remain sequential,
and a failed operation is not automatically retried. A separate management client
can still race a configuration change; the vendor provides no atomic transaction
covering aggregation, VLANs and PVIDs together.

## Validation limits

Synthetic tests cover group extraction, malformed/mixed/single-member groups,
VLAN and PVID consistency, native/Python parity, fresh-state checks and rejection
before writes. Local DOM tests exercise group/member controls and PVID/frame
propagation. A desktop preview used synthetic LACP membership on ports 9 and 10.
The development switch's real aggregation configuration was read successfully;
it currently has no configured LAGs. The UI update was installed through the
native web updater and its served asset matched the build hash after reboot.
The native configuration export remained byte-identical and aggregation
configuration remained unchanged. No group was created merely to test the UI.

LACP negotiation, member failure/recovery, forwarding/hash distribution and
aggregation persistence still require a correctly configured peer and hardware
testing. HTTP readback is not a substitute for those tests.
