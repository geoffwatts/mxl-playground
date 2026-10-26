/* SPDX-License-Identifier: MIT */
#ifndef MXL_MANAGEMENT_VLAN_NATIVE_H
#define MXL_MANAGEMENT_VLAN_NATIVE_H
#include <stdint.h>
#include "management_vlan_owner.h"

/* Exact supported WSP 1.0.79 ABI. The bounded integration trial exercises
 * native PCE writes and VID 1 TX insertion; NVS writes remain offline code.
 * Keep work/mutex memory alive until all callers and queued work have ended.
 */
struct mxl_mgmt_native_mutex { uint32_t words[5]; };
struct mxl_mgmt_native_work { uint32_t words[10]; };

int mxl_mgmt_native_mutex_init(struct mxl_mgmt_native_mutex *);
int mxl_mgmt_native_trylock(struct mxl_mgmt_native_mutex *);
void mxl_mgmt_native_lock(struct mxl_mgmt_native_mutex *);
int mxl_mgmt_native_unlock(struct mxl_mgmt_native_mutex *);
void mxl_mgmt_native_work_init(struct mxl_mgmt_native_work *, void (*)(void *));
int mxl_mgmt_native_reschedule(struct mxl_mgmt_native_work *, uint32_t);
uint64_t mxl_mgmt_native_now(void);
int mxl_mgmt_native_pce_read(void *, unsigned char *);
int mxl_mgmt_native_pce_write(void *, unsigned char *);
/* The settings key is fixed. No arbitrary key or device-memory API is exposed. */
int mxl_mgmt_native_store_read(void *, unsigned char *, unsigned);
int mxl_mgmt_native_store_write(void *, const unsigned char *, unsigned);
int mxl_mgmt_native_vlan_row(void *, unsigned, unsigned char *);
int mxl_mgmt_native_tx_original(void *, void *, void *, const unsigned char *);
int mxl_mgmt_native_tx_insert(void *, void *, void *, unsigned, const unsigned char *);
int mxl_mgmt_native_owner_claim(struct mxl_mgmt_event *, mxl_mgmt_event_handler,
                                 struct mxl_mgmt_event **);
/* Only from the pinned native IP event callback, under its registry lock. */
int mxl_mgmt_native_owner_find_locked(mxl_mgmt_event_handler,
                                       struct mxl_mgmt_event **);
/* Nonblocking lookup for packet paths; busy and unsupported states fail. */
int mxl_mgmt_native_owner_try_find(mxl_mgmt_event_handler,
                                    struct mxl_mgmt_event **);
int mxl_mgmt_native_http_original(void *, void *);
void mxl_mgmt_native_http_unavailable(void *, void *);
/* Only after the native authorization callback admitted the protected route.
 * Copies the verified request's 32-byte session token into private RAM; never
 * return it in an HTTP response or log it. This helper does not authorize.
 */
int mxl_mgmt_native_request_session(void *, unsigned char *);
/* Save the native VLAN/PVID dependencies and verify their NVS readback before
 * committing a nonzero management VLAN. No arbitrary keys are accepted. */
int mxl_mgmt_native_vlan_persist(uint16_t);
#endif
