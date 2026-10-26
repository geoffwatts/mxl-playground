# LLDP neighbours

The LLDP page retains up to **16 neighbours**, including multiple advertisements
received on the same local port. The cache runs in WSP, continues collecting with
all browsers closed and resets at reboot. Local advertising-port settings still
use the native firmware's LLDP implementation and saved configuration.

Entries match on local port, remote chassis ID and remote port ID. Each new
advertisement refreshes the advertised lifetime. TTL-zero withdrawals remove the
matching entry; expired entries disappear on the next receive or snapshot read.
A full table evicts the least recently seen entry. There is no periodic polling
of the old single-packet mailbox and clients do not consume one another's data.
Link-down alone does not currently flush the table; the advertised TTL governs
expiry.

The page shows system name, remote port, chassis ID, management addresses and
remaining lifetime. Expand an entry for descriptions, supported/enabled
capabilities, last-seen age and original TTL. Remaining times are measured at
refresh. Reception, invalid-packet, expiry, eviction and capture-failure counters
are available below the table.

Mandatory identifiers are retained without truncation. Each entry stores up to
768 bytes of complete TLVs; optional TLVs which do not fit are omitted and the
entry is marked. Input is bounded at 1536 bytes. This is a useful bounded LLDP
neighbour cache, not a claim to implement LLDP-MED, DCBX or every organizational
extension. Existing native transmission and shell behavior are preserved.

## Integration and portability

`lldp_cache.[ch]` has no native addresses, firmware pointers or private WSP
structures. Callers provide copied LLDP bytes, local port and monotonic time.
`lldp_native.c` owns the receive adapter and endpoint; `wsp_platform.[ch]` provides
shared HTTP, allocation, time, mutex and boot-lifetime ownership helpers.

The exact WSP profile is `firmware/profiles/wsp-1.0.79.json`; the board's driver
port and SFP bus mapping is separate. `tools/wsp_profile.py` emits the adapter's
named symbol header. These are audited ABI descriptions, not automatic firmware
discovery. A new WSP still requires checking prototypes, layouts, cursor and
packet ownership, locks, hook instructions and free code space.

The receive adapter makes a read-only shallow clone whose cursor is already at
the LLDP payload. It releases that clone on every path and always invokes the
original parser with its original packet. The cache owns its copied bytes. The
native receive-work queue serializes access to the latest ingress-port field.
A busy owner registry or cache mutex can skip capture rather than block the
receive path; the capture-failure counter covers attempted capture failures,
not these pre-capture contention skips.

The module allocates roughly 14 KiB once per boot. HTTP reads use a 780-byte
record buffer instead of allocating a second complete table. Locks are released
before network writes. Snapshot generation is checked at both ends; a changed
snapshot is discarded and the browser retries one read. Repeated changes show
an error rather than a mixed table. Standard route authentication remains in
force. The endpoint provides no setter or memory/register access.

The factory hash, original receive-call bytes, extension hash and code/asset
boundaries are checked before patching. Boot configuration, GPHY and factory
settings remain unchanged. Older builds fall back to an explicitly labelled
legacy mailbox view.

## Build and checks

After preparing the normal full-runtime and terminal endpoints:

```sh
python3 tools/build_lldp_endpoint.py --output-dir artifacts/lldp/endpoint
python3 -m unittest discover -s tests -p test_lldp_cache.py
python3 -m unittest discover -s tests -p test_wsp_profile.py
node --test tests/lldp.test.mjs
```

Pass `--lldp-endpoint artifacts/lldp/endpoint/endpoint.bin` to
`build_developer_update.py`, alongside `--console-endpoint` and the full native
runtime. The installer also validates the optional LLDP extension and chain.
The pinned extension SHA-256 is
`2d751cb5ac27c5dd7815136ab05a027553aceee68409ff8c81232ccb9e822a16`.

All 998 emitted instruction lengths were independently checked with Ghidra
against GNU's disassembly. Host C tests use address/undefined-behavior sanitizers
for multi-neighbour matching, refresh, expiry, withdrawals, eviction, malformed
frames and bounded complete-TLV retention. Browser tests cover snapshot framing,
concurrent changes, TLV decoding, escaped names and legacy fallback.

## Hardware validation

The final build booted on the development switch and retained three distinct
neighbours received on port 1. With the browser closed, eight snapshots over
35 seconds retained those entries while the receive count rose from 10 to 13;
invalid/capture-failure counters stayed at zero. Saved configuration was
byte-identical, management remained unrestricted and stable, and the served UI
hash matched. Anonymous snapshot reads and authenticated POSTs were rejected.
The live page rendered all three entries without JavaScript errors. The shared
terminal remained operational; native malloc statistics reported 22,152 bytes
free (41,912 allocated; observed peak allocation 48,772). These are workload
observations, not worst-case guarantees. Expiry,
withdrawal, full-capacity eviction and malformed-frame cases were exercised in
host fixtures; those specific cases have not yet been driven by physical peers.
