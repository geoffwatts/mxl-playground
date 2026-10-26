/* Audited V2 WSP 1.0.79 only. Called instead of net_context_is_used from
 * net_context_handle_timeout. DNS owns persistent UDP contexts: treating them
 * as idle application sockets leaves the resolver with dangling pointers.
 * Preserve every other context's original cleanup decision. ARC EM4 ABI:
 * r0 argument/result; r1/r2 caller-saved; tail call preserves blink.
 */
.section .text,"ax"
.global dns_context_guard
dns_context_guard:
    mov_s r1, 0x20f1a9b8
    ld r2, [r1, 8]
    breq r0, r2, .Ldns
    ld r2, [r1, 24]
    breq r0, r2, .Ldns
    ld r2, [r1, 40]
    breq r0, r2, .Ldns
    j 0x4005629c
.Ldns:
    mov_s r0, 0
    j_s [blink]
