# Management VLAN on the development V2 build

The native management-VLAN API and its on-device UI are integrated for the
GoodTop development unit running the supported 2.0.0.4 baseline. This remains
an experimental, exact-firmware feature; it is not a stock firmware option.

## Configure through the UI

1. While management isolation is disabled, create the VLAN and configure its
   tagged/untagged membership and port PVIDs on **VLANs & PVID**.
2. Open **Identity & management**, then **Management VLAN**. Select an existing
   VLAN, or **Unrestricted (disabled)** to remove isolation.
3. Choose **Apply with automatic rollback** and review the change. Application
   is delayed by one second, followed by a 60-second confirmation window.
4. Check management connectivity on the intended VLAN. Choose **Keep and save
   policy** in the same login session before the timer expires.

Keeping a policy saves and verifies the current native VLAN/PVID configuration
before saving the private management policy. It does not save every unrelated
running setting. Without confirmation, the switch's work timer restores the
previous policy independently of the browser. **Restore previous policy**
performs that restoration immediately. A lost command response is never replayed.

The UI shows current and saved policy separately. A browser countdown reaching
zero does not establish that restoration succeeded; the UI waits for switch
readback. Reconnecting with a new login cannot confirm an earlier session's
proposal; it can restore the previous policy or wait for expiry.

While isolation is enabled, forwarding/network mutations are blocked by the
native request gate. Disable isolation before changing VLAN membership, PVIDs,
management addressing or other forwarding configuration. Read-only monitoring,
identity/inventory, jumbo frame controls and normal configuration saving remain
available. During confirmation, use the policy's own Keep/Restore controls.

## UART recovery

To remove the **saved** custom management restriction at 115200 baud, 8N1:

```text
settings delete mxl/management-vlan
chiptest reboot
```

Deleting the key does not change the running policy; reboot reloads the missing
key as unrestricted management. This preserves ordinary VLANs/PVIDs and the
management IP, so their configuration must still permit access. These commands
were used to recover the development unit during saved-policy boot testing.
For a complete user configuration reset, see the main README's factory-defaults
commands. Neither procedure restores original firmware or the bootloader.

## Implementation and validation scope

The module uses the existing WSP VLAN hardware table and native TX insertion,
restricts native CPU/ARP PCE rules 6/7, guards native IP rule updates, and owns a
boot-lifetime timer and mutex. No GPHY or bootloader change is part of this
feature. Its versioned CRC-protected NVS record is separate from the vendor's
VLAN records. Proposal nonces and authenticated login ownership prevent stale
confirmation after a replacement proposal, reboot or new login.

Native NVS callbacks advertise a nominal 256-byte value size. The adapter checks
the actual reader result with a byte beyond its permitted capacity, detecting
oversized records rather than accepting truncated data. Fresh ARP write
verification accounts for the observed CPU-map and disabled application-data
mask normalization; enabled match fields remain checked.

Portable controller/store/identity/IP/TX/request tests, image-region checks and
browser wire/transport/DOM tests accompany this integration. The earlier
physical VID 4093 experiments established tagged/PVID HTTP and fresh ARP
isolation with native rules. A full durable-policy tagged-client test, cold
power-cycle check and second-unit reproduction remain separate validation
items. This unit currently exposes IPv4 management; IPv6 isolation has not been
verified and is not claimed.

## Development-unit results, 25 October

The installed full runtime passed VLAN 1 confirmation, direct NVS readback,
warm reboot with VLAN 1 restored, disable/confirm, and another warm reboot with
unrestricted management restored. A new login was rejected when attempting to
confirm an earlier session's proposal, but could cancel it. Cancellation and
an autonomous timeout each restored the original 948-byte PCE profile exactly.
The timeout run made no control reads while waiting. Conflicting native PVID
writes returned HTTP 409. The served standalone HTML hash matched the image.

The unit was left unrestricted. The current runtime is 14216 compiled bytes
inside its existing 28672-byte extension, with 3945 independently decoded
instruction lengths and four checked native hook sites. Evidence is retained
locally under `artifacts/management-vlan/native-runtime-full-r3/`; it is not
part of the source publication archive.
