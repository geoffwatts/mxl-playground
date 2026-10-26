/* SPDX-License-Identifier: MIT */
#ifndef MXL_LLDP_CACHE_H
#define MXL_LLDP_CACHE_H
#include <stdint.h>
#define MXL_LLDP_CAPACITY 16u
#define MXL_LLDP_PDU_BYTES 768u
#define MXL_LLDP_FRAME_BYTES 1536u
#define MXL_LLDP_RECORD_BYTES (12u + MXL_LLDP_PDU_BYTES)
/* No WSP pointers, native ABI or allocation. Caller serializes all operations.
 * Retain complete TLVs; mandatory IDs never truncated. Optional TLVs which
 * exceed storage are omitted and flagged. Input is borrowed only for the call. */
struct mxl_lldp_entry {
    uint64_t seen_ms, expires_ms;
    uint16_t bytes, ttl;
    unsigned char port, used, flags, reserved;
    unsigned char pdu[MXL_LLDP_PDU_BYTES];
};
struct mxl_lldp_cache {
    uint32_t generation, received, invalid, evicted, expired;
    struct mxl_lldp_entry entries[MXL_LLDP_CAPACITY];
};
int mxl_lldp_receive(struct mxl_lldp_cache *, unsigned, const unsigned char *, unsigned, uint64_t);
void mxl_lldp_expire(struct mxl_lldp_cache *, uint64_t);
void mxl_lldp_header(const struct mxl_lldp_cache *, unsigned char *, uint32_t);
void mxl_lldp_record(const struct mxl_lldp_cache *, unsigned, unsigned char *, uint64_t);
#endif
