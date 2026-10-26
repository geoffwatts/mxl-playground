# WSP adaptation boundary

The supported target is the exact Xikestor 2.0.0.4 input, WSP 1.0.79. Firmware
version text is not an admission check: builders require the factory SHA-256 and
expected instruction bytes. No other WSP or board is currently admitted.

`firmware/profiles/wsp-1.0.79.json` describes native symbols, the LLDP hook and its
code window. `firmware/profiles/goodtop-zx310s-8t2xs.json` describes board mapping.
`tools/wsp_profile.py` supplies factory admission and emits the generated C
symbol header. `wsp_platform.[ch]` contains the platform calls/layout used by the
new LLDP adapter. The cache and its browser wire protocol remain independent.

Important ABI assumptions for this adapter:

- 32-bit little-endian ARC EM4 with the audited code-density instruction set.
- Five-word native pthread mutex storage and a five-word net_mgmt callback
  record (`next`, handler, info, info length, mask).
- Native net_mgmt registry mutex ownership and callback allocation lifetime.
  Registry lookup precedes module locking; packet-side acquisition is nonblocking.
- Shallow packet cloning preserves the current cursor and retains shared buffers.
  Reads advance only the clone; release uses the native unref API.
- The LLDP worker has already placed the driver ingress port in its latest-record
  field before calling the parser. Work executes on the native serial work queue.
- CivetWeb route registration uses the existing protected handler chain. Network
  writes happen outside cache locks.

A port must establish those assumptions afresh; updating symbol values alone is
insufficient. Recompile, independently decode, review changed instructions and
validate on hardware before pinning a new output hash. Keep board mapping and
firmware ABI as separate concerns, even for boards with the same switch silicon.

This boundary is incremental. Existing management-VLAN adapters/runtime, terminal
integration and jumbo/SFP/inventory assembly generators still contain exact-build
addresses and private layouts. Their audited binaries and behavior were retained;
they have not all been converted into the new shared profile. Management VLAN
remains the largest future porting task. Boot/DMA and DNS fixes also require their
own reassessment for another WSP, which may already have fixed those issues.
