/* SPDX-License-Identifier: MIT */
#include "management_vlan_egress_gate.h"

int mxl_mgmt_egress_gate_send(const struct mxl_mgmt_egress_gate *g, void *iface,
                              void *packet, const unsigned char *header, unsigned length)
{
    void *owner = 0;
    unsigned type;
    int result;
    uint16_t vid;
    if (!g || !g->original) return 1;
    if (iface != g->management_iface) goto native;
    if (!header || !packet || length < 14) goto unavailable;
    type = ((unsigned)header[12] << 8) | header[13];
    if (type != 0x0800 && type != 0x0806 && type != 0x86dd &&
        type != 0x8100 && type != 0x88a8) goto native;
    if (!g->try_find || !g->try_lock || !g->unlock ||
        g->try_find(g->context, &owner) || !owner || g->try_lock(owner))
        goto unavailable;
    if (g->observe_locked) g->observe_locked(owner, iface, header);
    if (g->observer_only == 1) { g->unlock(owner); goto native; }
    if (g->observer_only > 1) { g->unlock(owner); return 1; }
    if (!g->vid_locked || !g->dispatch_locked) {
        g->unlock(owner); return 1;
    }
    vid = g->vid_locked(owner);
    if (!vid) { g->unlock(owner); goto native; }
    if (vid > 4094) { g->unlock(owner); return 1; }
    result = g->dispatch_locked(owner, iface, packet, header, length);
    g->unlock(owner);
    /* Restricted dispatch may only insert a header (2) or drop (1). */
    return result == 2 ? 2 : 1;
unavailable:
    if (g->observer_only != 1) return 1;
native:
    return g->original(g->context, iface, packet, header);
}
