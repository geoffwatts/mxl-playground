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

## Live retest after UI update — 26 October, 11:32 UTC

The clock remained in 1970 at uptime 690 seconds. Saved SNTP was enabled,
`au.pool.ntp.org`, poll 1024; runtime flags were 2 (enabled, unresolved).
An explicit `net dns query au.pool.ntp.org` returned four real A records,
but did not change the SNTP-specific unresolved flag.

Changing only the configured hostname temporarily to `0.au.pool.ntp.org`
triggered the native SNTP resolution callback. UART captured resolution to
150.107.75.115 at uptime 710.157 seconds, an NTP request at 710.158, and
successful acquisition at 710.258 (`1793014360`, 2026-10-26 11:32:40 UTC).
No manual clock setting, routing change, or firmware patch was used.
The exact original hostname/enabled state/1024-second interval were restored
through the native setter afterwards. Private captures are under
`artifacts/sntp/current-test`.

This proves outbound DNS and NTP work in the current image after link settles.
The pre-test unresolved SNTP state is a startup/recovery problem; this test
alone does not establish whether an eventual ordinary poll recovers it.
Reapplying an unchanged hostname is not equivalent to forcing DNS: the native
setter clears its flags, compares old/new names, and only explicitly starts
resolution when the name changes. A future fix should address that recovery
path rather than treating failed off-subnet shell ping as a gateway failure.

## Native recovery integration

The full-runtime builder now installs `firmware/sntp_recovery.S` with its
exact instruction fixtures in `tools/sntp_recovery.py`. The change adds a
140-byte shim in erased WSP padding at offset `0x2c7000` and changes four
native instruction sites (24 bytes total):

- Startup timer call at `0x2171e`: delay only its first expiry by 64 seconds;
  preserve the configured periodic interval in the original argument words.
- SNTP request call at `0x248a0`: if the native address-valid bit is clear,
  resolve the live configured hostname through the existing asynchronous DNS
  API and callback. That callback stores the address and schedules the actual
  request. Otherwise use the original numeric-address SNTP client.
- Settings branch at `0x2158a`: saving the same hostname must still resolve it.
- Timer gate at `0x11a86`: DNS failure must not leave an enabled client with its
  periodic timer stopped. The existing enabled-state check remains.

The request shim also wraps the original completion callback. A failed send or
NTP timeout clears only the address-valid bit, so the next ordinary poll resolves
again. It adds no thread, private RAM allocation, settings key, or flash write.
Default polling stays 1024 seconds; recovery retries use the configured interval.
The lookup path requests IPv4 A records, matching the tested IPv4 management
configuration. IPv6-only SNTP targets have not been validated.

The native socket API's getaddrinfo path rejects hostnames with -4 on this build;
passing a hostname straight to the socket client is insufficient. This was
caught in the first hardware test and replaced with the asynchronous DNS path.
The shim's 32 instructions and native hook replacements were independently
decoded with GNU ARC EM4 tools and Ghidra. Ghidra's known erroneous bit-test
p-code is not used as semantic authority; the native code uses the same
`btst_s` instruction pattern.

Update admission accepts only a complete exact recovery patch, normalizes it
for the pre-existing immutable-region digest, and rejects partial or altered
hooks/code even when container CRCs have been repaired. The browser admission
also recognizes the pinned LLDP registration chain, restoring the original
terminal continuation only in its validation copy before comparing hashes.

Hardware validation of the final candidate passed on 26 October:

- Warm update/reboot: uplink forwarded at 37.899 s; DNS resolved a fresh pool
  address at 67.661 s; SNTP acquired current time at 67.762 s. No settings
  reapply or manual clock change was needed. The saved configuration export
  was byte-identical to the pre-update backup.
- A reserved `.invalid` hostname with a temporary 64-second interval failed
  resolution, then was retried automatically at 185.115 and 249.115 s uptime.
  The original pool and 1024-second interval were restored after the test.
- A reserved documentation IP timed out with -116 after three seconds. UART
  readback showed flags 2 (enabled, address invalid) and poll 1024, confirming
  that the completion shim invalidates the address without disabling SNTP.

Final update SHA-256:
`00b9839a2e640ed065c6e78094b8438f49b8957100def377ca2714f725af6019`.
Served UI hash, normal boot and forwarding were checked. The permanent boot
record, GPHY and management configuration were retained. Cold-power testing
and IPv6-only SNTP validation are not claimed by this warm-reboot test.

Reapplying the identical pool hostname also passed: fresh resolution at
420.330 s, successful SNTP completion at 420.431 s, flags 3 and poll 1024 on
readback. Final clock matched the host to within one second. The final saved
configuration export remained byte-identical to the pre-test backup after all
temporary failure settings were restored.
