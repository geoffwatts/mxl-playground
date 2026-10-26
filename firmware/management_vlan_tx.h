/* SPDX-License-Identifier: MIT */
#ifndef MXL_MANAGEMENT_VLAN_TX_H
#define MXL_MANAGEMENT_VLAN_TX_H
#include <stdint.h>

#define MXL_MGMT_VLAN_ROWS 100u
/* First six bytes of the native 33-byte VLAN row include mode, VID and TPID. */
struct mxl_mgmt_tx {
    int (*read_row)(void *, unsigned, unsigned char *);
    int (*original)(void *, void *, void *, const unsigned char *);
    int (*insert)(void *, void *, void *, unsigned, const unsigned char *);
    void *context, *management_iface;
    uint16_t vid;
    unsigned char index;
};
/* Resolve one ordinary 802.1Q row, rejecting absent/duplicate/stacked VLANs.
 * No state changes: the caller publishes VID/index only during policy apply.
 */
int mxl_mgmt_tx_resolve(struct mxl_mgmt_tx *, uint16_t, unsigned char *);
/* Native bridge return contract: 1 tells ethernet_send to free/drop the
 * packet; 2 means a VLAN header was inserted and normal sending continues.
 * No packet is freed here. Disabled policy and other protocols/interfaces
 * pass through to the original implementation.
 */
int mxl_mgmt_tx_dispatch(struct mxl_mgmt_tx *, void *, void *,
                          const unsigned char *, unsigned);
#endif
