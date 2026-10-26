/* SPDX-License-Identifier: MIT */
#ifndef MXL_MANAGEMENT_VLAN_STORE_H
#define MXL_MANAGEMENT_VLAN_STORE_H
#include <stdint.h>

#define MXL_MGMT_RECORD_BYTES 16u
#define MXL_MGMT_STORE_MISSING (-2)

/* The adapter owns one private settings key. read returns its exact stored
 * length (not a truncated buffer length), MISSING, or another negative error.
 * write returns 0 on acknowledgement; actual readback decides the outcome.
 * Callers serialize operations with the policy transaction.
 */
struct mxl_mgmt_store {
    int (*read)(void *, unsigned char *, unsigned);
    int (*write)(void *, const unsigned char *, unsigned);
    void *context;
    unsigned char original[MXL_MGMT_RECORD_BYTES];
    uint16_t vid;
    unsigned char ready, present;
};

/* NVS advertises a nominal 256-byte callback length. Read one byte beyond
 * the admitted capacity to detect truncation using the reader's actual result. */
int mxl_mgmt_store_read_value(int (*)(void *, void *, unsigned), void *, unsigned char *, unsigned);

int mxl_mgmt_record_encode(unsigned char *, uint16_t);
int mxl_mgmt_record_decode(const unsigned char *, unsigned, uint16_t *);
/* Missing settings load as unrestricted VID 0. Corrupt/unsupported records
 * return an error and cannot subsequently be overwritten by persist().
 */
int mxl_mgmt_store_load(struct mxl_mgmt_store *);
/* Transaction-core callback result: 0 = candidate read back, 1 = original
 * record/absence read back, -1 = uncertain. Never retries a write.
 */
int mxl_mgmt_store_persist(struct mxl_mgmt_store *, uint16_t);
#endif
