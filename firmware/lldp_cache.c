/* SPDX-License-Identifier: MIT */
#include "lldp_cache.h"
static unsigned be16(const unsigned char *p) { return (unsigned)p[0] * 256u + p[1]; }
static void zero(unsigned char *p, unsigned n) {
    while (n--)
        *p++ = 0;
}
static void copy(unsigned char *d, const unsigned char *s, unsigned n) {
    while (n--)
        *d++ = *s++;
}
static int same(const unsigned char *a, const unsigned char *b, unsigned n) {
    while (n--)
        if (*a++ != *b++)
            return 0;
    return 1;
}
static void put16(unsigned char *p, unsigned n) {
    p[0] = (unsigned char)n;
    p[1] = (unsigned char)(n >> 8);
}
static void put32(unsigned char *p, uint32_t n) {
    unsigned i;
    for (i = 0; i < 4; i++)
        p[i] = (unsigned char)(n >> (8 * i));
}
void mxl_lldp_expire(struct mxl_lldp_cache *c, uint64_t now) {
    unsigned i;
    for (i = 0; i < MXL_LLDP_CAPACITY; i++)
        if (c->entries[i].used && now >= c->entries[i].expires_ms) {
            c->entries[i].used = 0;
            c->expired++;
            c->generation++;
        }
}
int mxl_lldp_receive(struct mxl_lldp_cache *c, unsigned port, const unsigned char *p, unsigned n,
                     uint64_t now) {
    unsigned at = 0, stage = 1, key = 0, ttl = 0, stored = 0, flags = 0, ended = 0, i,
             slot = MXL_LLDP_CAPACITY, oldest = 0;
    uint64_t oldest_time = UINT64_MAX;
    struct mxl_lldp_entry *e;
    /* Validate the complete PDU before changing any entry. Ethernet padding after
     * End is permitted; the adapter bounds the supplied Ethernet payload. */
    if (!p || !port || port > 255 || n > MXL_LLDP_FRAME_BYTES)
        goto bad;
    while (at + 2 <= n) {
        unsigned h = be16(p + at), type = h >> 9, len = h & 511u;
        at += 2;
        if (len > n - at)
            goto bad;
        if (stage <= 3) {
            if (type != stage)
                goto bad;
            if (stage < 3) {
                if (len < 2 || len > 256 || p[at] < 1 || p[at] > 7)
                    goto bad;
            } else {
                if (len != 2)
                    goto bad;
                ttl = be16(p + at);
                key = at - 2;
            }
            stage++;
        } else if (type > 0 && type < 4)
            goto bad;
        if (type == 0) {
            if (len || stage != 4)
                goto bad;
            ended = 1;
            break;
        }
        at += len;
    }
    if (!ended)
        goto bad;
    mxl_lldp_expire(c, now);
    c->received++;
    for (i = 0; i < MXL_LLDP_CAPACITY; i++) {
        e = &c->entries[i];
        if (e->used && e->port == port && e->bytes >= key && same(e->pdu, p, key)) {
            slot = i;
            break;
        }
        if (!e->used && slot == MXL_LLDP_CAPACITY)
            slot = i;
        if (e->used && e->seen_ms < oldest_time) {
            oldest_time = e->seen_ms;
            oldest = i;
        }
    }
    if (!ttl) {
        if (i < MXL_LLDP_CAPACITY) {
            c->entries[i].used = 0;
            c->generation++;
        }
        return 0;
    }
    if (slot == MXL_LLDP_CAPACITY) {
        slot = oldest;
        c->evicted++;
    }
    e = &c->entries[slot];
    e->used = 1;
    e->port = (unsigned char)port;
    e->seen_ms = now;
    e->expires_ms = now + (uint64_t)ttl * 1000u;
    e->ttl = (uint16_t)ttl;
    /* Copy selected complete TLVs into a self-contained, terminated PDU. */
    at = 0;
    while (at + 2 <= n) {
        unsigned h = be16(p + at), len = (h & 511u) + 2u;
        if (!(h >> 9))
            break;
        if (stored + len + 2 <= MXL_LLDP_PDU_BYTES) {
            copy(e->pdu + stored, p + at, len);
            stored += len;
        } else
            flags = 1;
        at += len;
    }
    e->pdu[stored] = e->pdu[stored + 1] = 0;
    e->bytes = (uint16_t)(stored + 2);
    e->flags = (unsigned char)flags;
    c->generation++;
    return 0;
bad:
    c->invalid++;
    c->generation++;
    return -1;
}
void mxl_lldp_header(const struct mxl_lldp_cache *c, unsigned char *p, uint32_t dropped) {
    unsigned i, count = 0;
    zero(p, 32);
    for (i = 0; i < MXL_LLDP_CAPACITY; i++)
        count += c->entries[i].used != 0;
    p[0] = 'M';
    p[1] = 'L';
    p[2] = 'D';
    p[3] = 'P';
    p[4] = 1;
    p[5] = MXL_LLDP_CAPACITY;
    p[6] = (unsigned char)count;
    p[7] = 1;
    put32(p + 8, c->generation);
    put32(p + 12, c->received);
    put32(p + 16, c->invalid);
    put32(p + 20, c->evicted);
    put32(p + 24, c->expired);
    put32(p + 28, dropped);
}
void mxl_lldp_record(const struct mxl_lldp_cache *c, unsigned slot, unsigned char *p,
                     uint64_t now) {
    const struct mxl_lldp_entry *e = &c->entries[slot];
    uint64_t age;
    zero(p, MXL_LLDP_RECORD_BYTES);
    if (!e->used || now >= e->expires_ms)
        return;
    p[0] = e->port;
    p[1] = e->flags;
    put16(p + 2, e->ttl);
    put16(p + 4, (unsigned)((e->expires_ms - now + 999u) / 1000u));
    put16(p + 6, e->bytes);
    age = (now - e->seen_ms) / 1000u;
    put32(p + 8, age > UINT32_MAX ? UINT32_MAX : (uint32_t)age);
    copy(p + 12, e->pdu, e->bytes);
}
