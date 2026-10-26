/* SPDX-License-Identifier: MIT */
#ifndef MXL_MANAGEMENT_VLAN_IPRULE_H
#define MXL_MANAGEMENT_VLAN_IPRULE_H
#include <stdint.h>
struct mxl_mgmt_pce;

/* Development-only preparation for the exact native IPv4 event writer.
 * Restrict a newly built rule 7/8 BEFORE its hardware write. Caller holds its
 * controller lock and retains the unrestricted input for address-aware
 * recovery. This does not call hardware, register a hook or commit a baseline.
 * Invalid/foreign/already restricted records are left byte-for-byte unchanged.
 * VID 0 bypasses this helper at the caller; only 1..4094 are admitted here.
 */
int mxl_mgmt_iprule_restrict(unsigned char *, uint16_t);
/* Serialized active-policy write for the supported single-IPv4 profile.
 * Slot 8 is rejected before IO while restricted; multi-address support is
 * intentionally not admitted. One write/readback, no retry. Verified readback
 * becomes the fresh unrestricted rollback baseline for slot 7. Uncertain IO
 * invalidates PCE admission, preventing restoration of a stale address.
 * Hook caller must hold the controller lock across the ENTIRE native address
 * callback, including deletion and this write; deletion-only events still
 * require separate reconciliation. Not installed as a native hook yet.
 */
int mxl_mgmt_iprule_write(struct mxl_mgmt_pce *, const unsigned char *, uint16_t);
/* After the native event callback, while still serialized: accept a disabled
 * ARP rule without resurrecting it on rollback, verify enabled rule 7 still
 * matches the guarded baseline/VID, and require rule 8 to remain disabled.
 * Unknown state invalidates admission; this function never writes hardware.
 */
int mxl_mgmt_iprule_reconcile(struct mxl_mgmt_pce *, uint16_t);
#endif
