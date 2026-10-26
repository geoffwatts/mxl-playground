/* SPDX-License-Identifier: MIT
 * Source profile recovered from the native event handler at 40024320;
 * its write call is at 4002474e. Not installed or linked into a WSP.
 */
#include "management_vlan_iprule.h"
#include "management_vlan_pce.h"

static unsigned get16(const volatile unsigned char *p)
{
    return p[0] | ((unsigned)p[1] << 8);
}
int mxl_mgmt_iprule_restrict(unsigned char *record, uint16_t vid)
{
    volatile unsigned char *r = record;
    unsigned i, index;
    if (!r || !vid || vid > 4094) return -1;
    index = get16(r + 7);
    if ((index != 7 && index != 8) ||
        r[0x80] != 1 || r[0x93] != 1 || r[0x94] ||
        r[0xf1] != 1 || r[0x118] != 1 || r[0x11b] != 1 ||
        get16(r + 0x27) != 0x0806 || get16(r + 0x7e) != 0x4d4c ||
        get16(r + 0x33) || get16(r + 0x41) || r[0xff] ||
        r[0x100] || r[0x101] || r[0x102] ||
        get16(r + 0x16c) != 3 || get16(r + 0x16e)) return -1;
    for (i = 0; i < 6; i++) if (r[0x6c + i] != 0xff) return -1;
    /* Native hardware readback may normalize the CPU port map. Do not assume the
     * zeroed write template is byte-identical to the later readback baseline.
     */
    r[0x33] = (unsigned char)vid;
    r[0x34] = (unsigned char)(vid >> 8);
    r[0xff] = 1;
    return 0;
}

int mxl_mgmt_iprule_write(struct mxl_mgmt_pce *s, const unsigned char *record,
                          uint16_t vid)
{
    unsigned i;
    unsigned char *wanted, *actual;
    if (!s || !record || !s->admitted || !s->read || !s->write ||
        get16(record + 7) != 7 || !vid || vid > 4094) return -1;
    if (record[0x130] > 1) return -1;
    for (i = 1; i < 16; i++) if (record[0x130 + i]) return -1;
    wanted = s->wanted; actual = s->actual;
    if (record == wanted || record == actual) return -1;
    for (i = 0; i < MXL_PCE_RULE_BYTES; i++) wanted[i] = record[i];
    if (mxl_mgmt_iprule_restrict(wanted, vid)) return -1;
    /* A write can take effect even when its transport reports an error.
     * Verify actual state once; never replay the write after a lost reply.
     */
    s->write(s->context, wanted);
    for (i = 0; i < MXL_PCE_RULE_BYTES; i++) actual[i] = 0;
    actual[7] = 7;
    if (s->read(s->context, actual)) goto uncertain;
    for (i = 0; i < MXL_PCE_RULE_BYTES; i++) {
        unsigned char expected = record[i];
        if (i == 0x33) expected = (unsigned char)vid;
        if (i == 0x34) expected = (unsigned char)(vid >> 8);
        if (i == 0xff) expected = 1;
        if (actual[i] == expected) continue;
        /* The fresh native template has CPU map 0; the admitted readback
         * profile uses map 1. No other normalization is permitted here.
         */
        if (i == 0x130 && !expected && actual[i] == 1) continue;
        /* The driver canonicalizes unused application-data mask bytes to
         * 0xff. Accept only this observed normalization, and only while the
         * corresponding match enable is zero; active pattern bits stay exact. */
        if ((i==0x7c || i==0x7d) && !expected && actual[i]==0xff &&
            !record[i==0x7c?0x112:0x115]) continue;
        goto uncertain;
    }
    for (i = 0; i < MXL_PCE_RULE_BYTES; i++) s->original[1][i] = actual[i];
    s->original[1][0x33] = s->original[1][0x34] = s->original[1][0xff] = 0;
    return 0;
uncertain:
    s->admitted = 0;
    return -1;
}

int mxl_mgmt_iprule_reconcile(struct mxl_mgmt_pce *s, uint16_t vid)
{
    unsigned i;
    unsigned char *wanted, *actual;
    if (!s || !s->admitted || !s->read || !vid || vid > 4094) return -1;
    wanted = s->wanted; actual = s->actual;
    for (i = 0; i < MXL_PCE_RULE_BYTES; i++) actual[i] = 0;
    actual[7] = 7;
    if (s->read(s->context, actual) || get16(actual + 7) != 7) goto uncertain;
    if (actual[0x80] == 1) {
        for (i = 0; i < MXL_PCE_RULE_BYTES; i++) wanted[i] = s->original[1][i];
        if (mxl_mgmt_iprule_restrict(wanted, vid)) goto uncertain;
        for (i = 0; i < MXL_PCE_RULE_BYTES; i++)
            if (actual[i] != wanted[i]) goto uncertain;
        /* Commit the unrestricted baseline below, after checking rule 8. */
        wanted[0x33] = wanted[0x34] = wanted[0xff] = 0;
    } else if (!actual[0x80]) {
        for (i = 0; i < MXL_PCE_RULE_BYTES; i++) wanted[i] = actual[i];
        wanted[0x33] = wanted[0x34] = wanted[0x41] = wanted[0x42] = 0;
        wanted[0xff] = wanted[0x100] = wanted[0x101] = wanted[0x102] = 0;
    } else goto uncertain;
    for (i = 0; i < MXL_PCE_RULE_BYTES; i++) actual[i] = 0;
    actual[7] = 8;
    if (s->read(s->context, actual) || get16(actual + 7) != 8 || actual[0x80])
        goto uncertain;
    for (i = 0; i < MXL_PCE_RULE_BYTES; i++) s->original[1][i] = wanted[i];
    return 0;
uncertain:
    s->admitted = 0;
    return -1;
}
