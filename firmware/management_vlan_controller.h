/* SPDX-License-Identifier: MIT */
#ifndef MXL_MANAGEMENT_VLAN_CONTROLLER_H
#define MXL_MANAGEMENT_VLAN_CONTROLLER_H
#include "management_vlan_core.h"
#include "management_vlan_pce.h"
#include "management_vlan_store.h"
#include "management_vlan_tx.h"
#include "management_vlan_requests.h"

/* Portable coordinator; installed only in a bounded VID 0/1 trial. Fill the transport callbacks in pce,
 * store and tx before start. The native adapter must install its TX and IP
 * hooks first, wait for driver/VLAN readiness, and serialize EVERY entry
 * point (including packet dispatch and the entire native IP callback) under
 * one boot-lifetime controller mutex. HTTP must never hold the registry lock
 * while waiting for that mutex. Native event context already holds that lock.
 * Existing VLAN/MAC mutators must also be coordinated or rejected while a
 * policy is active. The trial uses request leases and conservative admission;
 * general durable confirmation and production admission remain unfinished.
 * Keep management services gated until startup ingress enforcement succeeds.
 * TX quarantine on an initialization error does not itself reject incoming
 * requests or prevent their side effects; it is only an egress backstop.
 */
struct mxl_mgmt_controller {
    struct mxl_mgmt_state policy;
    struct mxl_mgmt_pce pce;
    struct mxl_mgmt_store store;
    struct mxl_mgmt_tx tx;
    struct mxl_mgmt_requests requests;
    int (*schedule)(void *, uint32_t);
    uint64_t (*now)(void *);
    void *context;
    unsigned char initialized;
};
int mxl_mgmt_controller_start(struct mxl_mgmt_controller *);
int mxl_mgmt_controller_propose(struct mxl_mgmt_controller *, uint16_t);
int mxl_mgmt_controller_tick(struct mxl_mgmt_controller *);
int mxl_mgmt_controller_confirm(struct mxl_mgmt_controller *, uint32_t);
int mxl_mgmt_controller_cancel(struct mxl_mgmt_controller *, uint32_t);
/* Caller holds the controller mutex. Startup request gate only; native
 * runtime mutators still require their own coordination/admission.
 */
int mxl_mgmt_controller_http_ready(const struct mxl_mgmt_controller *);
/* Write hook: 1 means policy is off: delegate to original native writer.
 * Otherwise 0 means verified guarded write; -1 means reject, never delegate.
 */
int mxl_mgmt_controller_ip_write(struct mxl_mgmt_controller *, const unsigned char *);
int mxl_mgmt_controller_ip_end(struct mxl_mgmt_controller *);
#endif
