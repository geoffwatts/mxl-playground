#include "lldp_cache.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned tlv(unsigned char *p, unsigned t, const unsigned char *v, unsigned n) {
    p[0] = (unsigned char)((t << 1) | (n >> 8));
    p[1] = (unsigned char)n;
    memcpy(p + 2, v, n);
    return n + 2;
}
static unsigned frame(unsigned char *p, unsigned id, unsigned ttl) {
    unsigned at = 0;
    unsigned char c[] = {4, 0, 1, 2, 3, 4, 5}, port[] = {5, 'e', 't', 'h', '0'},
                  time[2] = {(unsigned char)(ttl >> 8), (unsigned char)ttl};
    c[6] = (unsigned char)id;
    at += tlv(p + at, 1, c, sizeof(c));
    at += tlv(p + at, 2, port, sizeof(port));
    at += tlv(p + at, 3, time, 2);
    at += tlv(p + at, 5, (const unsigned char *)"peer", 4);
    p[at++] = 0;
    p[at++] = 0;
    return at;
}
static unsigned count(struct mxl_lldp_cache *c) {
    unsigned i, n = 0;
    for (i = 0; i < MXL_LLDP_CAPACITY; i++)
        n += c->entries[i].used != 0;
    return n;
}
extern uint32_t __mulsi3(uint32_t, uint32_t);
extern uint64_t __muldi3(uint64_t, uint64_t);
extern uint64_t __udivdi3(uint64_t, uint64_t);
int main(void) {
    struct mxl_lldp_cache c = {0};
    unsigned char p[1536], wire[MXL_LLDP_RECORD_BYTES], head[32], longvalue[511];
    unsigned n, i;
    {
        uint64_t x = UINT64_C(0xfedcba9876543210), y = UINT64_C(0x123456789), state = 13;
        unsigned k;
        assert(__udivdi3(x, y) == x / y);
        assert(__udivdi3(x, 0) == UINT64_MAX);
        for (k = 0; k < 1000; k++) {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            x = state;
            y = (state >> 17) | 1;
            assert(__mulsi3((uint32_t)x, (uint32_t)y) == (uint32_t)x * (uint32_t)y);
            assert(__muldi3(x, y) == x * y);
            assert(__udivdi3(x, y) == x / y);
        }
    }
    n = frame(p, 1, 120);
    assert(!mxl_lldp_receive(&c, 1, p, n, 1000));
    assert(count(&c) == 1);
    p[0] = 255;
    assert(c.entries[0].pdu[0] == 2);
    n = frame(p, 2, 120);
    assert(!mxl_lldp_receive(&c, 1, p, n, 2000));
    assert(count(&c) == 2);
    assert(!mxl_lldp_receive(&c, 2, p, n, 2000));
    assert(count(&c) == 3);
    assert(!mxl_lldp_receive(&c, 1, p, n, 3000));
    assert(count(&c) == 3);
    mxl_lldp_record(&c, 1, wire, 4000);
    assert(wire[0] == 1 && wire[4] == 119);
    n = frame(p, 1, 0);
    assert(!mxl_lldp_receive(&c, 1, p, n, 4000));
    assert(count(&c) == 2);
    mxl_lldp_expire(&c, 122000);
    assert(count(&c) == 1);
    mxl_lldp_expire(&c, 123000);
    assert(!count(&c));
    n = frame(p, 1, 0);
    assert(mxl_lldp_receive(&c, 1, p, n - 2, 0) == -1);
    assert(!count(&c));
    n = frame(p, 1, 120);
    p[1] = 255;
    assert(mxl_lldp_receive(&c, 1, p, n, 0) == -1);
    n = frame(p, 1, 120);
    p[9] = 0;
    assert(mxl_lldp_receive(&c, 1, p, n, 0) == -1);
    memset(&c, 0, sizeof(c));
    for (i = 0; i < 17; i++) {
        n = frame(p, i, 120);
        assert(!mxl_lldp_receive(&c, 1, p, n, i * 1000));
    }
    assert(count(&c) == 16 && c.evicted == 1 && c.entries[0].pdu[8] == 16);
    /* 9-bit TLV lengths, long optional fields and safe omission preserve IDs. */
    memset(&c, 0, sizeof(c));
    n = frame(p, 1, 120) - 2;
    memset(longvalue, 'x', sizeof(longvalue));
    n += tlv(p + n, 6, longvalue, 511);
    n += tlv(p + n, 4, longvalue, 511);
    p[n++] = 0;
    p[n++] = 0;
    assert(!mxl_lldp_receive(&c, 10, p, n, 0));
    assert(c.entries[0].flags == 1 && c.entries[0].bytes <= 768);
    mxl_lldp_header(&c, head, 3);
    assert(!memcmp(head, "MLDP", 4) && head[6] == 1 && head[28] == 3);
    mxl_lldp_record(&c, 0, wire, 1);
    assert(wire[0] == 10 && wire[1] == 1);
    /* Distinct remote ports on one chassis and maximum-length IDs remain keys. */
    memset(&c, 0, sizeof(c));
    n = frame(p, 42, 120);
    assert(!mxl_lldp_receive(&c, 1, p, n, 0));
    p[15] = '1';
    assert(!mxl_lldp_receive(&c, 1, p, n, 0));
    assert(count(&c) == 2);
    n = frame(p, 42, 0);
    p[15] = '1';
    assert(!mxl_lldp_receive(&c, 1, p, n, 0));
    assert(count(&c) == 1);
    memset(&c, 0, sizeof(c));
    memset(longvalue, 'k', 256);
    longvalue[0] = 7;
    n = tlv(p, 1, longvalue, 256);
    n += tlv(p + n, 2, longvalue, 256);
    {
        unsigned char t[2] = {0, 120};
        n += tlv(p + n, 3, t, 2);
    }
    p[n++] = 0;
    p[n++] = 0;
    assert(!mxl_lldp_receive(&c, 1, p, n, 0));
    p[515] = 'z';
    assert(!mxl_lldp_receive(&c, 1, p, n, 0));
    assert(count(&c) == 2);
    /* Every prefix of a valid advertisement lacks End and must fail. */
    n = frame(p, 5, 90);
    for (i = 0; i < n; i++)
        assert(mxl_lldp_receive(&c, 1, p, i, 0) == -1);
    puts("LLDP multi-neighbour refresh, expiry, withdrawal, eviction, malformed and bounded TLV "
         "tests passed");
    return 0;
}
