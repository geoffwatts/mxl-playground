/* SPDX-License-Identifier: MIT */
#include "management_vlan_identity.h"

int mxl_mgmt_identity_set(struct mxl_mgmt_identity *s, const unsigned char *proposal,
                          const unsigned char *session, uint32_t ticket)
{
    unsigned i, a=0, b=0;
    if (!s || !proposal || !session || !ticket) return -1;
    for (i=0;i<MXL_MGMT_PROPOSAL_BYTES;i++) a |= proposal[i];
    for (i=0;i<MXL_MGMT_SESSION_BYTES;i++) b |= session[i];
    if (!a || !b) return -1;
    for (i=0;i<MXL_MGMT_PROPOSAL_BYTES;i++) s->proposal[i]=proposal[i];
    for (i=0;i<MXL_MGMT_SESSION_BYTES;i++) s->session[i]=session[i];
    s->ticket=ticket;
    return 0;
}
int mxl_mgmt_identity_matches(const struct mxl_mgmt_identity *s, const unsigned char *proposal,
                              const unsigned char *session, uint32_t ticket)
{
    unsigned i, different=0;
    if (!s || !proposal || !session || !ticket || !s->ticket) return 0;
    for (i=0;i<MXL_MGMT_PROPOSAL_BYTES;i++) different |= s->proposal[i]^proposal[i];
    for (i=0;i<MXL_MGMT_SESSION_BYTES;i++) different |= s->session[i]^session[i];
    return !different && s->ticket==ticket;
}
void mxl_mgmt_identity_clear(struct mxl_mgmt_identity *s)
{
    unsigned i;
    if (!s) return;
    for (i=0;i<MXL_MGMT_PROPOSAL_BYTES;i++) s->proposal[i]=0;
    for (i=0;i<MXL_MGMT_SESSION_BYTES;i++) s->session[i]=0;
    s->ticket=0;
}
