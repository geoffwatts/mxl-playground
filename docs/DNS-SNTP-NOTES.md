# V2 outbound networking / SNTP investigation — 26 October 2026

The configured gateway and its ARP entry are present, and on-subnet gateway
ping works. The off-subnet `net ping` failure is not sufficient evidence of
missing routing: its IPv4 helper at `0x4005381c` requires an on-link source
lookup. UDP uses a different interface/source selection path.

The DNS resolver has a separate lifetime problem on the development unit.
Its default context is `0x20f1a9b8`; the first server remains 8.8.8.8:53,
with a socket-context pointer at +8. Readback found that pointed-to context
unused (bit 0 of its flags at +0x8a clear, reference count zero). Its remaining
fields were from a previous SNTP socket, including UDP port 123 and the
previous test server. This establishes a stale resolver pointer, not its
original cause by itself.

The vendor's `net_context_handle_timeout` at `0x400569e4` runs every 60 seconds.
It scans all 70 contexts, checks their state and age at +0x90, then drains
pending work and releases old contexts. States 0/1 use a >30,999 ms threshold;
state 2 uses >60,999 ms. There is no DNS ownership exclusion. A persistent,
unconnected resolver UDP socket is therefore eligible for reclamation.
GNU ARC EM4 disassembly confirms this path; the Ghidra decompiler alone is
not reliable for this firmware's bit tests and small offsets.

The DNS send loop has a second failure behavior: a failed attempt against the
only configured server can still return success when subsequent server entries
are empty. Failure before timeout scheduling leaves the query occupied with
no future cleanup. A second query returns -11 until `net dns cancel` clears
it. A displayed “Query sent” consequently does not establish a wire send.

## Narrow lifetime experiment

`firmware/dns_context_guard.S` replaces only the `net_context_is_used` call
inside this idle reaper (WSP offset `0x56a14`). It returns zero to that caller
for the three context pointers owned by the default resolver, bypassing idle
reclamation for them; every other context tail-calls the original helper.
Normal explicit resolver teardown remains available. It does not change the
general allocator, routing, UART, boot record, or GPHY firmware.

The guard is 42 bytes at WSP offset `0x2c6f00`, previously erased extension
padding. GNU and an independent Ghidra overlay agree on all ten instruction
lengths, branch targets and argument/return behavior. The exact-input-only
offline builder is `tools/build_dns_guard_candidate.py`. Its baseline is the
previously booted firmware/UI image, SHA-256
`92216f78380a9a54707fad7b14ac29b8b7363817fe4dae0398638e33433ec434`.
Private upload/runtime evidence is retained under `artifacts/sntp/dns-guard`.

Hardware validation passed on the development unit: after reboot and more
than 60 seconds, the resolver context remained used (`0x00890011` protocol/
flags word), and a query returned four real pool addresses with no stranded
pending query. Re-resolving the configured SNTP pool set the enabled/resolved
flags to 3 and advanced the clock from 1970 to the current date. The gateway
was not changed. A session expired during this clock correction; reconnecting
worked and settings readback retained the original pool and 1024-second poll.

The ordinary full-runtime image builder now installs the guard; browser upload
admission accepts either the original call or this exact call/guard pair and
rejects CRC-repaired mutations of either. Fifteen native image tests and six
firmware/browser tests passed. The integrated image also installs the requested
1024-second fresh SNTP form default. Its update SHA-256 is
`7a79632b88b79eb05de3b19a5a76881e38d3043622551227259e422fe11e2af2`;
77 native chunks, boot, served UI hash and the original management-PCE profile
were verified. Boot records, settings layout and GPHY remain unchanged.

The initial SNTP request can precede STP forwarding after reboot and then wait
for the normal polling interval. The owner explicitly deferred this timing
issue; no startup-delay/retry patch was added. Cold-power and longer-duration
validation remain separate from the demonstrated warm update and live sync.
