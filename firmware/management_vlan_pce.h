/* SPDX-License-Identifier: MIT */
#ifndef MXL_MANAGEMENT_VLAN_PCE_H
#define MXL_MANAGEMENT_VLAN_PCE_H
#include <stdint.h>

#define MXL_PCE_RULE_BYTES 0x1d2u
struct mxl_mgmt_pce {
    unsigned char original[2][MXL_PCE_RULE_BYTES];
    /* Heap-owned scratch keeps native driver calls off large stack frames. */
    unsigned char wanted[MXL_PCE_RULE_BYTES], actual[MXL_PCE_RULE_BYTES];
    int (*read)(void *, unsigned char *);
    int (*write)(void *, unsigned char *);
    void *context;
    unsigned char admitted;
};
int mxl_mgmt_pce_admit(struct mxl_mgmt_pce *);
/* Startup variant: reserve a disabled slot 7 before the first IPv4 event.
 * Slot 6 still requires the full known CPU-directed unicast profile.
 */
int mxl_mgmt_pce_admit_boot(struct mxl_mgmt_pce *);
int mxl_mgmt_pce_apply(struct mxl_mgmt_pce *, uint16_t);
#endif
