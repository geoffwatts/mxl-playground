/* SPDX-License-Identifier: MIT
 * Freestanding compiler support for baseline ARC without optional multiply/divide
 * instructions. Unsigned shift/add algorithms; no firmware or libc dependency.
 */
#include <stdint.h>
uint32_t __mulsi3(uint32_t a, uint32_t b) {
    uint32_t r = 0;
    while (b) {
        if (b & 1u)
            r += a;
        a <<= 1;
        b >>= 1;
    }
    return r;
}
uint64_t __muldi3(uint64_t a, uint64_t b) {
    uint64_t r = 0;
    while (b) {
        if (b & 1u)
            r += a;
        a <<= 1;
        b >>= 1;
    }
    return r;
}
uint64_t __udivdi3(uint64_t a, uint64_t b) {
    uint64_t q = 0, r = 0;
    unsigned i;
    if (!b)
        return UINT64_MAX;
    for (i = 0; i < 64; i++) {
        unsigned high = (unsigned)(r >> 63);
        r = (r << 1) | (a >> 63);
        a <<= 1;
        q <<= 1;
        if (high || r >= b) {
            r -= b;
            q |= 1;
        }
    }
    return q;
}
