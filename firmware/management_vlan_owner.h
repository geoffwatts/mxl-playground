/* SPDX-License-Identifier: MIT */
#ifndef MXL_MANAGEMENT_VLAN_OWNER_H
#define MXL_MANAGEMENT_VLAN_OWNER_H
#include <stdint.h>

struct mxl_mgmt_event;
typedef void (*mxl_mgmt_event_handler)(struct mxl_mgmt_event *, uint32_t, void *);
/* Native net_mgmt callback ABI. Embed this at the start of the module state;
 * registration owns that state for the whole boot, independently of CivetWeb.
 */
struct mxl_mgmt_event {
    struct mxl_mgmt_event *next;
    mxl_mgmt_event_handler handler;
    const void *info;
    uint32_t info_length, event_mask;
};
struct mxl_mgmt_registry {
    struct mxl_mgmt_event **head, **tail;
    uint32_t *aggregate_mask;
    int (*lock)(void *);
    void (*unlock)(void *);
    void *context;
};
/* Atomically find or insert the one callback for this module. candidate may
 * be NULL for lookup. On success *owner is existing/candidate/NULL. The caller
 * may free an unused candidate, but a registered owner lives until reset.
 * Duplicate handlers, inconsistent endpoints or oversized/cyclic lists fail
 * without mutation. This is not an HTTP session or a user-supplied handler.
 * Do not call from an event callback that may already hold the registry lock;
 * that callback receives its owner directly and can schedule work instead.
 */
int mxl_mgmt_owner_claim(const struct mxl_mgmt_registry *, struct mxl_mgmt_event *,
                          mxl_mgmt_event_handler, uint32_t, struct mxl_mgmt_event **);
/* Lookup ONLY when the native event dispatcher already holds the registry
 * lock. Never use from HTTP/work callbacks without first acquiring that lock.
 * Does not call lock/unlock, register anything or change any list field.
 */
int mxl_mgmt_owner_find_locked(const struct mxl_mgmt_registry *,
                              mxl_mgmt_event_handler, uint32_t,
                              struct mxl_mgmt_event **);
#endif
