/* SPDX-License-Identifier: MIT */
#ifndef MXL_MANAGEMENT_VLAN_EGRESS_GATE_H
#define MXL_MANAGEMENT_VLAN_EGRESS_GATE_H
#include <stdint.h>

struct mxl_mgmt_egress_gate {
    void *context, *management_iface;
    int (*try_find)(void *, void **);
    int (*try_lock)(void *);
    void (*unlock)(void *);
    uint16_t (*vid_locked)(void *);
    int (*dispatch_locked)(void *, void *, void *, const unsigned char *, unsigned);
    void (*observe_locked)(void *, void *, const unsigned char *);
    int (*original)(void *, void *, void *, const unsigned char *);
    /* Development-only: delegate ALL packets unchanged, even when lookup or
     * locking fails. This mode must never be used with an enforced policy.
     */
    unsigned char observer_only;
};
/* Neither lookup nor owner acquisition may wait. Unknown/busy management
 * state drops in enforcement mode. Control protocols retain the native path.
 * A policy-off packet is admitted under lock, then native framing executes
 * outside the lock so native broadcast/clone processing can reenter safely.
 */
int mxl_mgmt_egress_gate_send(const struct mxl_mgmt_egress_gate *, void *, void *,
                              const unsigned char *, unsigned);
#endif
