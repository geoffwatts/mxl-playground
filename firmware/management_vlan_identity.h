/* SPDX-License-Identifier: MIT */
#ifndef MXL_MANAGEMENT_VLAN_IDENTITY_H
#define MXL_MANAGEMENT_VLAN_IDENTITY_H
#include <stdint.h>

/* Planned durable API guard; not used by the installed nonpersistent trial.
 * The browser creates a fresh 128-bit identifier for EACH proposal. The native
 * adapter supplies the already-verified factory session identity, never a
 * session field from the submitted command. Ticket alone can repeat on reboot.
 * Serialize these functions under the same controller owner mutex.
 */
#define MXL_MGMT_PROPOSAL_BYTES 16u
#define MXL_MGMT_SESSION_BYTES 32u
struct mxl_mgmt_identity {
    unsigned char proposal[MXL_MGMT_PROPOSAL_BYTES];
    unsigned char session[MXL_MGMT_SESSION_BYTES];
    uint32_t ticket;
};
/* Call only AFTER a proposal succeeds, before releasing the controller lock.
 * Invalid input does not invalidate an outstanding proposal identity.
 */
int mxl_mgmt_identity_set(struct mxl_mgmt_identity *, const unsigned char *,
                          const unsigned char *, uint32_t);
int mxl_mgmt_identity_matches(const struct mxl_mgmt_identity *, const unsigned char *,
                              const unsigned char *, uint32_t);
void mxl_mgmt_identity_clear(struct mxl_mgmt_identity *);
#endif
