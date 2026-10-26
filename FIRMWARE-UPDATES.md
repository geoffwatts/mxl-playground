# Firmware backup and update

The on-device **Firmware** page uses the existing manufacturer endpoints.
Download exports WSP and GPHY in a V2 update container, not a complete SPI dump.
Bootloader, partition layout and device-specific settings are not backed up by
that export. Keep your original full SPI recovery backup.

For installation, select a supported `.bin` file. The browser verifies component
sizes and CRCs, computes SHA-256 even over plain HTTP, and checks compatibility.
Custom images must retain the exact supported base outside the reserved UI,
native extension and audited patch sites. GPHY must match version 0063. An
optional expected SHA-256 from the build manifest must match before proceeding.
These checks do not authenticate arbitrary code inserted into permitted custom
regions; use firmware from a source you trust.

The original factory V2 image is admitted only by its exact SHA-256:

```text
085ce44aeffe82b75676c5784b915ab80cfa0262a1ec5356a47832a45af07426
```

**The boot-record patch is retained permanently for both custom and factory
firmware, as explicitly requested by the owner.** Neither upload path reverses
it or changes the V2 partition layout. Restoring factory firmware replaces the
custom interface with the original manufacturer interface. This does not return
a migrated unit to its old 1.x layout.

Disable management isolation and confirm/save the unrestricted policy before
using the firmware controls. The installer preflights the exact model/software
profile and current management policy again before sending any firmware bytes.

The transfer sends sequential 41,000-byte binary chunks to `/firmware/upgrade`.
The first request allows the native slot erase time. Later requests proceed
only after the previous response. A failed or ambiguous write is never retried.
Keep the page open and leave power connected until the switch has restarted.
After the native success acknowledgement, only read requests are retried to
check that the served login interface matches the selected image.

An upload acknowledgement, or even a matching interface, does not by itself
verify UART startup, sustained forwarding or alternate-slot fallback. A failed
transfer stops and reports its offset; check the switch and UART before starting
a fresh operation. V1-to-V2 migration is outside this browser installer.

The exact factory image admission and its expected login asset are covered by
offline tests. A factory/custom round trip using this new page has not yet been
performed. The owner's earlier factory boot experience is retained separately
from the latest browser-upload validation.
