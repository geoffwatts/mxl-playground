/* SPDX-License-Identifier: MIT
 * Management-VLAN transaction logic. No device addresses, networking or NVS
 * implementation live here. A bounded nonpersistent trial is installed.
 */
#include "management_vlan_core.h"

#define APPLY_DELAY_MS 1000u
#define CONFIRM_DELAY_MS 60000u

static int valid_vid(uint16_t vid) { return vid <= 4094; }

static int restore(struct mxl_mgmt_state *s, int reason)
{
    int result = s->ops->apply(s->context, s->committed_vid);
    s->due_ms = 0;
    s->last_error = reason;
    if (result) {
        s->phase = MXL_MGMT_FAULT;
        s->last_error = MXL_MGMT_UNCERTAIN;
        return MXL_MGMT_UNCERTAIN;
    }
    s->active_vid = s->committed_vid;
    s->proposed_vid = s->committed_vid;
    s->phase = MXL_MGMT_STABLE;
    return reason;
}

int mxl_mgmt_init(struct mxl_mgmt_state *s, const struct mxl_mgmt_ops *ops,
                  void *context, uint16_t current_vid)
{
    if (!s || !ops || !ops->validate || !ops->apply || !ops->persist ||
        !ops->reschedule || !valid_vid(current_vid)) return MXL_MGMT_INVALID;
    s->ops = ops;
    s->context = context;
    s->committed_vid = s->active_vid = s->proposed_vid = current_vid;
    s->due_ms = 0;
    s->ticket = 0;
    s->phase = MXL_MGMT_STABLE;
    s->last_error = 0;
    return MXL_MGMT_OK;
}

int mxl_mgmt_propose(struct mxl_mgmt_state *s, uint16_t vid, uint64_t now)
{
    if (s->phase == MXL_MGMT_FAULT) return MXL_MGMT_UNCERTAIN;
    if (s->phase != MXL_MGMT_STABLE) return MXL_MGMT_BUSY;
    if (!valid_vid(vid) || now > UINT64_MAX - APPLY_DELAY_MS - CONFIRM_DELAY_MS ||
        s->ops->validate(s->context, vid)) return MXL_MGMT_INVALID;
    /* Never recycle a ticket within one boot: old browser tabs stay stale. */
    if (s->ticket == UINT32_MAX) return MXL_MGMT_STALE;
    s->ticket++;
    s->proposed_vid = vid;
    s->due_ms = now + APPLY_DELAY_MS;
    s->phase = MXL_MGMT_ARMED;
    s->last_error = 0;
    if (s->ops->reschedule(s->context, APPLY_DELAY_MS)) {
        s->phase = MXL_MGMT_STABLE;
        s->proposed_vid = s->committed_vid;
        s->due_ms = 0;
        s->last_error = MXL_MGMT_IO;
        return MXL_MGMT_IO;
    }
    return MXL_MGMT_OK;
}

int mxl_mgmt_tick(struct mxl_mgmt_state *s, uint64_t now)
{
    if (s->phase == MXL_MGMT_FAULT) return MXL_MGMT_UNCERTAIN;
    if (s->phase == MXL_MGMT_STABLE) return MXL_MGMT_OK;
    if (now < s->due_ms) {
        uint64_t left = s->due_ms - now;
        /* Monotonic clock discontinuities cannot disarm recovery silently. */
        if (left > CONFIRM_DELAY_MS ||
            s->ops->reschedule(s->context, (uint32_t)left))
            return restore(s, MXL_MGMT_IO);
        return MXL_MGMT_OK;
    }
    if (s->phase == MXL_MGMT_PENDING) return restore(s, MXL_MGMT_EXPIRED);
    if (now > UINT64_MAX - CONFIRM_DELAY_MS) return restore(s, MXL_MGMT_IO);
    /* Revalidate immediately before writes: membership may have changed. */
    if (s->ops->validate(s->context, s->proposed_vid))
        return restore(s, MXL_MGMT_INVALID);
    if (s->ops->apply(s->context, s->proposed_vid))
        return restore(s, MXL_MGMT_IO);
    if (s->ops->now_ms) {
        uint64_t completed = s->ops->now_ms(s->context);
        if (completed < now || completed > UINT64_MAX - CONFIRM_DELAY_MS)
            return restore(s, MXL_MGMT_IO);
        now = completed;
    }
    s->active_vid = s->proposed_vid;
    s->phase = MXL_MGMT_PENDING;
    s->due_ms = now + CONFIRM_DELAY_MS;
    if (s->ops->reschedule(s->context, CONFIRM_DELAY_MS))
        return restore(s, MXL_MGMT_IO);
    return MXL_MGMT_OK;
}

int mxl_mgmt_confirm(struct mxl_mgmt_state *s, uint32_t ticket, uint64_t now)
{
    int result;
    if (s->phase == MXL_MGMT_FAULT) return MXL_MGMT_UNCERTAIN;
    if (ticket != s->ticket || s->phase != MXL_MGMT_PENDING) return MXL_MGMT_STALE;
    if (now >= s->due_ms) return restore(s, MXL_MGMT_EXPIRED);
    result = s->ops->persist(s->context, s->active_vid);
    if (result == 1) return restore(s, MXL_MGMT_IO);
    if (result != 0) {
        restore(s, MXL_MGMT_UNCERTAIN);
        s->phase = MXL_MGMT_FAULT;
        return MXL_MGMT_UNCERTAIN;
    }
    s->committed_vid = s->active_vid;
    s->phase = MXL_MGMT_STABLE;
    s->due_ms = 0;
    s->last_error = 0;
    return MXL_MGMT_OK;
}

int mxl_mgmt_cancel(struct mxl_mgmt_state *s, uint32_t ticket)
{
    if (s->phase == MXL_MGMT_FAULT) return MXL_MGMT_UNCERTAIN;
    if (ticket != s->ticket || s->phase == MXL_MGMT_STABLE) return MXL_MGMT_STALE;
    return restore(s, MXL_MGMT_OK);
}
