/* SPDX-License-Identifier: MIT
 * Exact WSP 1.0.79 bindings. Reuse the native async DNS callback, SNTP client
 * and periodic timer. No new thread, private state, or flash writes.
 * Companion patches remove the setter's same-name DNS skip and its gate that
 * leaves the periodic timer stopped when DNS fails.
 */
.section .text,"ax"
.global sntp_request_recover
.global sntp_start_after_forwarding
sntp_request_recover:
    push_s blink
    mov_s r0, 0x20f1198c
    ldb_s r0, [r0]
    btst_s r0, 0
    beq .Lresolve
    /* r1 timeout and r3 handle are the original arguments. The native socket
     * API requires a numeric address, supplied by the DNS callback below.
     */
    mov_s r0, 0x20f5eb84
    mov_s r2, sntp_complete_recover
    jl 0x400301c8
    breq r0, 0, .Lreturn
    mov_s r1, 0x20f1198c
    ldb_s r2, [r1]
    bclr_s r2, r2, 0
    stb_s r2, [r1]
.Lreturn:
    pop_s blink
    j_s [blink]
.Lresolve:
    /* First successful A result sets native resolved bit 0 and schedules an
     * immediate request. Failed DNS leaves the existing periodic retry alive.
     * Passing the native context avoids the synchronous getaddrinfo stub.
     */
    mov_s r0, 0x20f1a9b8
    mov_s r1, 0x20f1126c
    mov_s r2, 1
    mov_s r3, 0
    mov_s r4, 0x400211b0
    mov_s r5, 0x20f1198c
    mov_s r6, 2000
    jl 0x4006c20c
    b .Lreturn
sntp_complete_recover:
    /* Preserve r0=result/r1=status for the original completion callback. A
     * timeout invalidates only the cached-address bit so the next poll resolves
     * again. Multiple A results stay suppressed by the native callback.
     */
    brne r0, 0, .Lcomplete
    mov_s r2, 0x20f1198c
    ldb_s r3, [r2]
    bclr_s r3, r3, 0
    stb_s r3, [r2]
.Lcomplete:
    j 0x400248e4
sntp_start_after_forwarding:
    /* First request at 64 s, beyond observed 38 s STP convergence. r3/r4 keep
     * the configured periodic interval (default 1024 s).
     */
    mov_s r1, 64000
    j 0x7000dcb8
