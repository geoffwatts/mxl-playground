/* SPDX-License-Identifier: MIT
 * Match the native net_mgmt registration operation under its existing lock,
 * adding duplicate detection and bounded lookup. No private RAM is borrowed.
 */
#include "management_vlan_owner.h"

int mxl_mgmt_owner_find_locked(const struct mxl_mgmt_registry *r,
                               mxl_mgmt_event_handler handler, uint32_t mask,
                               struct mxl_mgmt_event **owner)
{
    struct mxl_mgmt_event *node, *found = 0, *last = 0;
    unsigned count = 0;
    if (!owner) return -1;
    *owner = 0;
    if (!r || !r->head || !r->tail || !handler || !mask) return -1;
    for (node = *r->head; node; node = node->next) {
        if (++count > 64) return -1;
        last = node;
        if (node->handler == handler) {
            if (found || node->event_mask != mask) return -1;
            found = node;
        }
    }
    if (last != *r->tail) return -1;
    *owner = found;
    return 0;
}

int mxl_mgmt_owner_claim(const struct mxl_mgmt_registry *r, struct mxl_mgmt_event *candidate,
                          mxl_mgmt_event_handler handler, uint32_t mask,
                          struct mxl_mgmt_event **owner)
{
    struct mxl_mgmt_event *node, *found = 0, *last = 0;
    unsigned count = 0;
    int result = -1;
    if (!r || !r->head || !r->tail || !r->aggregate_mask || !r->lock || !r->unlock ||
        !handler || !mask || !owner) return -1;
    *owner = 0;
    if (r->lock(r->context)) return -1;
    for (node = *r->head; node; node = node->next) {
        if (++count > 64) goto done;
        if (node == candidate && node->handler != handler) goto done;
        last = node;
        if (node->handler == handler) {
            if (found || node->event_mask != mask) goto done;
            found = node;
        }
    }
    if (last != *r->tail) goto done;
    if (!found && candidate) {
        candidate->handler = handler;
        candidate->info = 0; candidate->info_length = 0; candidate->event_mask = mask;
        candidate->next = *r->head;
        if (!*r->tail) *r->tail = candidate;
        *r->aggregate_mask |= mask;
        *r->head = candidate;
        found = candidate;
    }
    *owner = found;
    result = 0;
done:
    r->unlock(r->context);
    return result;
}
