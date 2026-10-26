/* SPDX-License-Identifier: MIT
 * Select management egress without the vendor broadcast-to-all-VLANs path.
 * Uses the existing native VLAN-header insertion helper, not a new framer.
 * Read-only diagnostics link row resolution alone. The bounded native trial
 * also exercises dispatch with VID 1; arbitrary tagged-wire tests remain.
 */
#include "management_vlan_tx.h"

static unsigned row_vid(const unsigned char *row)
{
    return row[2] | ((unsigned)(row[3] & 15) << 8);
}
static int ordinary(const unsigned char *row)
{
    return (row[1] & 0xe0) == 0x20 && row[4] == 0 && row[5] == 0x81;
}
int mxl_mgmt_tx_resolve(struct mxl_mgmt_tx *s, uint16_t vid, unsigned char *index)
{
    unsigned char row[6], found = 0;
    unsigned i, matches = 0;
    if (!s || !s->read_row || !index || !vid || vid > 4094) return -1;
    for (i = 0; i < MXL_MGMT_VLAN_ROWS; i++) {
        if (s->read_row(s->context, i, row)) return -1;
        if (row_vid(row) == vid) {
            if (!ordinary(row)) return -1;
            found = (unsigned char)i;
            matches++;
        }
    }
    if (matches != 1) return -1;
    *index = found;
    return 0;
}
int mxl_mgmt_tx_dispatch(struct mxl_mgmt_tx *s, void *iface, void *packet,
                          const unsigned char *header, unsigned header_length)
{
    unsigned char row[6];
    unsigned type;
    if (!s || !s->original) return 1;
    if (!s->vid || iface != s->management_iface)
        return s->original(s->context, iface, packet, header);
    if (!packet || !header || header_length < 14) return 1;
    type = ((unsigned)header[12] << 8) | header[13];
    /* This hook expects the native stack's plain Ethernet header. Never let
     * an existing VLAN/S-tag hide management traffic from the policy check or
     * fall through to the vendor broadcast path. Nested tags are unsupported.
     */
    if (type == 0x8100 || type == 0x88a8) return 1;
    if (type != 0x0800 && type != 0x0806 && type != 0x86dd)
        return s->original(s->context, iface, packet, header);
    /* A deleted or repurposed row must drop management TX, never fall back
     * to the original path that can flood a broadcast across all VLANs.
     */
    if (s->vid > 4094 || s->index >= MXL_MGMT_VLAN_ROWS || !s->read_row || !s->insert ||
        s->read_row(s->context, s->index, row) || row_vid(row) != s->vid || !ordinary(row))
        return 1;
    return s->insert(s->context, iface, packet, s->index, header) == 2 ? 2 : 1;
}
