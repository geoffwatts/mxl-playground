/* SPDX-License-Identifier: MIT
 * Exact V2 packed GSW ABI, recovered from 400b2188 and 400b1e6c.
 * Positive VLAN matching modifies native management rules 6/7, rather than
 * reserving prototype slots 4/5. A bounded native-CLI test validated tagged
 * HTTP/ARP isolation; the compiled write adapter is installed and tested in
 * the bounded VID 1 trial. General persistence/tagged-wire validation remain.
 * Read/write implementations must use the same admitted API/profile and
 * serialize this state. The transaction core restores after any partial error.
 */
#include "management_vlan_pce.h"

enum {
    INDEX = 7, OUTER_VID = 0x33, OUTER_MASK = 0x41, DST_MAC = 0x6c,
    ENABLE = 0x80, DST_ENABLE = 0x93, DST_EXCLUDE = 0x94,
    OUTER_ENABLE = 0xff, OUTER_EXCLUDE = 0x100,
    OUTER_RANGE = 0x101, OUTER_ORIGINAL = 0x102,
    FORWARD_MAP = 0x130, MAP_ACTION = 0x16c
};

static unsigned get16(const volatile unsigned char *p) { return p[0] | ((unsigned)p[1] << 8); }
static unsigned get32(const volatile unsigned char *p)
{
    return get16(p) | ((unsigned)get16(p + 2) << 16);
}
static void put16(volatile unsigned char *p, unsigned value)
{
    p[0] = (unsigned char)value;
    p[1] = (unsigned char)(value >> 8);
}
static void copy(volatile unsigned char *to, const volatile unsigned char *from)
{
    unsigned i;
    for (i = 0; i < MXL_PCE_RULE_BYTES; i++) to[i] = from[i];
}
static int equal(const volatile unsigned char *a, const volatile unsigned char *b)
{
    unsigned i;
    for (i = 0; i < MXL_PCE_RULE_BYTES; i++) if (a[i] != b[i]) return 0;
    return 1;
}
static void prepare(struct mxl_mgmt_pce *state, unsigned index, uint16_t vid)
{
    unsigned char *wanted = state->wanted;
    copy(wanted, state->original[index]);
    if (vid) {
        wanted[OUTER_ENABLE] = 1;
        wanted[OUTER_EXCLUDE] = wanted[OUTER_RANGE] = wanted[OUTER_ORIGINAL] = 0;
        put16(wanted + OUTER_MASK, 0);
        put16(wanted + OUTER_VID, vid);
    }
}

static int admit(struct mxl_mgmt_pce *state, int boot)
{
    unsigned i, j;
    unsigned char *rule = state->actual;
    state->admitted = 0;
    if (!state->read || !state->write) return -1;
    for (i = 0; i < 2; i++) {
        for (j = 0; j < MXL_PCE_RULE_BYTES; j++) rule[j] = 0;
        put16(rule + INDEX, 6 + i);
        if (state->read(state->context, rule)) return -1;
        if (get16(rule + INDEX) != 6 + i) return -1;
        if (boot && i == 1 && !rule[ENABLE]) {
            /* A disabled rule cannot admit traffic. Retain its exact inactive
             * record; the guarded native IP writer will establish a fresh
             * enabled baseline when an IPv4 address is added.
             */
            copy(state->original[i], rule);
            continue;
        }
        if (get16(rule + INDEX) != 6 + i || rule[ENABLE] != 1 ||
            rule[DST_ENABLE] != 1 || rule[DST_EXCLUDE] != 0 ||
            rule[OUTER_ENABLE] != 0 || get32(rule + MAP_ACTION) != 3 ||
            get16(rule + FORWARD_MAP) != 1) return -1;
        for (j = 2; j < 16; j++) if (rule[FORWARD_MAP + j]) return -1;
        if (i == 0) {
            if (rule[DST_MAC] & 1) return -1;
        } else {
            for (j = 0; j < 6; j++) if (rule[DST_MAC + j] != 0xff) return -1;
        }
        copy(state->original[i], rule);
    }
    state->admitted = 1;
    return 0;
}
int mxl_mgmt_pce_admit(struct mxl_mgmt_pce *state) { return admit(state, 0); }
int mxl_mgmt_pce_admit_boot(struct mxl_mgmt_pce *state) { return admit(state, 1); }

int mxl_mgmt_pce_apply(struct mxl_mgmt_pce *state, uint16_t vid)
{
    unsigned i, j;
    unsigned char *wanted = state->wanted, *actual = state->actual;
    if (!state->admitted || vid > 4094) return -1;
    for (i = 0; i < 2; i++) {
        if (vid && i==1 && !state->original[i][ENABLE]) {
            /* A disabled ARP slot admits nothing. Preserve it until the
             * guarded address callback creates the actual ARP rule, rather
             * than asking the driver to retain fields in an inactive rule. */
            for (j=0;j<MXL_PCE_RULE_BYTES;j++) actual[j]=0;
            put16(actual+INDEX,7);
            if (state->read(state->context,actual) ||
                get16(actual+INDEX)!=7 || actual[ENABLE]) return -1;
            continue;
        }
        prepare(state, i, vid);
        if (state->write(state->context, wanted)) return -1;
        /* The native driver can modify its argument. Rebuild the expected
         * record from the immutable baseline rather than trusting that buffer.
         */
        prepare(state, i, vid);
        for (j = 0; j < MXL_PCE_RULE_BYTES; j++) actual[j] = 0;
        put16(actual + INDEX, 6 + i);
        if (state->read(state->context, actual)) return -1;
        if (i==1 && !wanted[ENABLE]) {
            if (get16(actual+INDEX)!=7 || actual[ENABLE]) return -1;
        } else if (!equal(actual, wanted)) return -1;
    }
    return 0;
}
