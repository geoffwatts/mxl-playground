/* SPDX-License-Identifier: MIT
 * Versioned management policy record and readback-driven save semantics.
 * No device addresses or live NVS bindings are included in this module.
 */
#include "management_vlan_store.h"

int mxl_mgmt_store_read_value(int (*read)(void *, void *, unsigned), void *context,
                              unsigned char *data, unsigned capacity)
{
    unsigned char scratch[65];
    unsigned i;
    int length;
    if (!read || !data || !capacity || capacity>64) return -5;
    length=read(context,scratch,capacity+1);
    if (length<0 || (unsigned)length>capacity) return -5;
    for (i=0;i<(unsigned)length;i++) data[i]=scratch[i];
    return length;
}

static uint32_t crc32(const unsigned char *p, unsigned length)
{
    uint32_t value = UINT32_MAX;
    unsigned i;
    while (length--) {
        value ^= *p++;
        for (i = 0; i < 8; i++)
            value = (value >> 1) ^ (UINT32_C(0xedb88320) & (0u - (value & 1u)));
    }
    return ~value;
}
static void copy(unsigned char *to, const unsigned char *from)
{
    unsigned i;
    for (i = 0; i < MXL_MGMT_RECORD_BYTES; i++) to[i] = from[i];
}
static int equal(const unsigned char *a, const unsigned char *b)
{
    unsigned i;
    for (i = 0; i < MXL_MGMT_RECORD_BYTES; i++) if (a[i] != b[i]) return 0;
    return 1;
}

int mxl_mgmt_record_encode(unsigned char *p, uint16_t vid)
{
    uint32_t crc;
    unsigned i;
    if (!p || vid > 4094) return -1;
    for (i = 0; i < MXL_MGMT_RECORD_BYTES; i++) p[i] = 0;
    p[0] = 'M'; p[1] = 'V'; p[2] = 'L'; p[3] = 'N'; p[4] = 1;
    p[6] = (unsigned char)vid; p[7] = (unsigned char)(vid >> 8);
    crc = crc32(p, 12);
    for (i = 0; i < 4; i++) p[12 + i] = (unsigned char)(crc >> (8 * i));
    return 0;
}

int mxl_mgmt_record_decode(const unsigned char *p, unsigned length, uint16_t *vid)
{
    uint16_t candidate;
    uint32_t expected = 0;
    unsigned i;
    if (!p || !vid || length != MXL_MGMT_RECORD_BYTES ||
        p[0] != 'M' || p[1] != 'V' || p[2] != 'L' || p[3] != 'N' ||
        p[4] != 1 || p[5] || p[8] || p[9] || p[10] || p[11]) return -1;
    candidate = (uint16_t)(p[6] | ((unsigned)p[7] << 8));
    if (candidate > 4094) return -1;
    for (i = 0; i < 4; i++) expected |= (uint32_t)p[12 + i] << (8 * i);
    if (expected != crc32(p, 12)) return -1;
    *vid = candidate;
    return 0;
}

int mxl_mgmt_store_load(struct mxl_mgmt_store *s)
{
    int length;
    if (!s) return -1;
    s->ready = s->present = 0;
    s->vid = 0;
    if (!s->read || !s->write) return -1;
    length = s->read(s->context, s->original, MXL_MGMT_RECORD_BYTES);
    if (length != MXL_MGMT_STORE_MISSING) {
        if (length < 0 || mxl_mgmt_record_decode(s->original, (unsigned)length, &s->vid))
            return -1;
        s->present = 1;
    }
    s->ready = 1;
    return 0;
}

int mxl_mgmt_store_persist(struct mxl_mgmt_store *s, uint16_t vid)
{
    unsigned char wanted[MXL_MGMT_RECORD_BYTES], actual[MXL_MGMT_RECORD_BYTES];
    int length;
    if (!s || !s->ready || !s->read || !s->write ||
        mxl_mgmt_record_encode(wanted, vid)) return -1;
    /* A configuration restore or another owner may have changed this key.
     * Verify the admitted baseline even for an unchanged VID; cached bytes
     * alone are never evidence of durable state.
     */
    length = s->read(s->context, actual, MXL_MGMT_RECORD_BYTES);
    if (!((!s->present && length == MXL_MGMT_STORE_MISSING) ||
          (s->present && length == MXL_MGMT_RECORD_BYTES && equal(actual, s->original)))) {
        s->ready = 0;
        return -1;
    }
    if (s->present && equal(s->original, wanted)) return 0;
    /* Even a reported failure can have written the record. Never retry or
     * infer durability from the acknowledgement alone.
     */
    s->write(s->context, wanted, MXL_MGMT_RECORD_BYTES);
    length = s->read(s->context, actual, MXL_MGMT_RECORD_BYTES);
    if (length == MXL_MGMT_RECORD_BYTES && equal(actual, wanted)) {
        copy(s->original, actual);
        s->vid = vid;
        s->present = 1;
        return 0;
    }
    if ((!s->present && length == MXL_MGMT_STORE_MISSING) ||
        (s->present && length == MXL_MGMT_RECORD_BYTES && equal(actual, s->original)))
        return 1;
    /* An unknown record may now be durable. Require a fresh load/recovery;
     * no second save is permitted against the stale baseline.
     */
    s->ready = 0;
    return -1;
}
