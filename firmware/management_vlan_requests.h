/* SPDX-License-Identifier: MIT */
#ifndef MXL_MANAGEMENT_VLAN_REQUESTS_H
#define MXL_MANAGEMENT_VLAN_REQUESTS_H

/* A request may outlive begin_request and must not keep the owner mutex held
 * while writing its response. Track potentially mutating native requests until
 * end_request instead. All calls below require the controller mutex.
 * Unknown routes/methods are conservatively treated as native mutations.
 */
#define MXL_MGMT_REQUEST_SLOTS 4u
struct mxl_mgmt_requests {
    const void *connection[MXL_MGMT_REQUEST_SLOTS];
    unsigned count;
    unsigned char fault;
};
enum mxl_mgmt_request_kind {
    MXL_MGMT_REQUEST_NATIVE = 0,
    MXL_MGMT_REQUEST_READ = 1,
    MXL_MGMT_REQUEST_CONTROL = 2
};
int mxl_mgmt_request_kind(const char *method, const char *path);
/* 0 admitted, 409 conflicting mutation, 503 unsupported/broken lifecycle. */
int mxl_mgmt_requests_begin(struct mxl_mgmt_requests *, const void *, int, int);
void mxl_mgmt_requests_end(struct mxl_mgmt_requests *, const void *);
int mxl_mgmt_requests_idle(const struct mxl_mgmt_requests *);
#endif
