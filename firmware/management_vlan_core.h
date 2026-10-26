/* SPDX-License-Identifier: MIT */
#ifndef MXL_MANAGEMENT_VLAN_CORE_H
#define MXL_MANAGEMENT_VLAN_CORE_H
#include <stdint.h>

enum mxl_mgmt_phase { MXL_MGMT_STABLE, MXL_MGMT_ARMED, MXL_MGMT_PENDING, MXL_MGMT_FAULT };
enum mxl_mgmt_result {
    MXL_MGMT_OK = 0, MXL_MGMT_INVALID = -1, MXL_MGMT_BUSY = -2,
    MXL_MGMT_STALE = -3, MXL_MGMT_EXPIRED = -4, MXL_MGMT_IO = -5,
    MXL_MGMT_UNCERTAIN = -6
};

/* Callers serialize every entry point. reschedule replaces any previous
 * timer, and a later timer invokes mxl_mgmt_tick with a fresh monotonic time.
 * apply preserves unrelated switch configuration; failures can be partial.
 * persist: 0 = candidate read back, 1 = old record read back, -1 = uncertain.
 * VID 0 disables the management restriction; 1..4094 select a VLAN.
 */
struct mxl_mgmt_ops {
    int (*validate)(void *, uint16_t);
    int (*apply)(void *, uint16_t);
    int (*persist)(void *, uint16_t);
    int (*reschedule)(void *, uint32_t);
    /* Supply a fresh completion time when hardware apply can consume time.
     * NULL is suitable only for instantaneous/injected-time adapters.
     */
    uint64_t (*now_ms)(void *);
};

struct mxl_mgmt_state {
    const struct mxl_mgmt_ops *ops;
    void *context;
    uint64_t due_ms;
    uint32_t ticket;
    uint16_t committed_vid, active_vid, proposed_vid;
    uint8_t phase;
    int last_error;
};

/* Init receives an already applied, known current configuration. */
int mxl_mgmt_init(struct mxl_mgmt_state *, const struct mxl_mgmt_ops *, void *, uint16_t);
int mxl_mgmt_propose(struct mxl_mgmt_state *, uint16_t, uint64_t);
int mxl_mgmt_tick(struct mxl_mgmt_state *, uint64_t);
int mxl_mgmt_confirm(struct mxl_mgmt_state *, uint32_t, uint64_t);
int mxl_mgmt_cancel(struct mxl_mgmt_state *, uint32_t);
#endif
