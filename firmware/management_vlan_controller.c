/* SPDX-License-Identifier: MIT
 * Join transaction deadlines, packet policy, verified PCE updates and NVS.
 * No native addresses, registration, HTTP handlers or unprotected globals.
 */
#include "management_vlan_controller.h"
#include "management_vlan_iprule.h"

static int spare(struct mxl_mgmt_controller *c)
{
    unsigned i;
    unsigned char *r = c->pce.actual;
    for (i = 0; i < MXL_PCE_RULE_BYTES; i++) r[i] = 0;
    r[7] = 8;
    return c->pce.read(c->pce.context, r) || r[7] != 8 || r[8] || r[0x80] ? -1 : 0;
}
static int validate(void *context, uint16_t vid)
{
    struct mxl_mgmt_controller *c = context;
    unsigned char index;
    if (!c->pce.admitted || vid > 4094 || spare(c)) return -1;
    return vid ? mxl_mgmt_tx_resolve(&c->tx, vid, &index) : 0;
}
static int apply(void *context, uint16_t vid)
{
    struct mxl_mgmt_controller *c = context;
    unsigned char index = 0;
    if (validate(c, vid) || (vid && mxl_mgmt_tx_resolve(&c->tx, vid, &index))) return -1;
    /* Limit egress before touching ingress. For unrestricted restoration,
     * release egress only after both PCE records are verified restored.
     * All packet dispatch is serialized with this operation by the adapter.
     */
    if (vid) { c->tx.vid = vid; c->tx.index = index; }
    if (mxl_mgmt_pce_apply(&c->pce, vid)) return -1;
    if (!vid) { c->tx.vid = 0; c->tx.index = 0; }
    return 0;
}
static int persist(void *context, uint16_t vid)
{
    return mxl_mgmt_store_persist(&((struct mxl_mgmt_controller *)context)->store, vid);
}
static int schedule(void *context, uint32_t delay)
{
    struct mxl_mgmt_controller *c = context;
    return c->schedule(c->context, delay);
}
static uint64_t now(void *context)
{
    struct mxl_mgmt_controller *c = context;
    return c->now(c->context);
}
static const struct mxl_mgmt_ops ops = {validate, apply, persist, schedule, now};
static int fault(struct mxl_mgmt_controller *c)
{
    c->policy.phase = MXL_MGMT_FAULT;
    c->policy.last_error = MXL_MGMT_UNCERTAIN;
    c->policy.due_ms = 0;
    return MXL_MGMT_UNCERTAIN;
}
int mxl_mgmt_controller_start(struct mxl_mgmt_controller *c)
{
    if (!c || c->initialized || !c->schedule || !c->now ||
        !c->pce.read || !c->pce.write || !c->store.read || !c->store.write ||
        !c->tx.read_row || !c->tx.original || !c->tx.insert || !c->tx.management_iface)
        return MXL_MGMT_INVALID;
    if (mxl_mgmt_init(&c->policy, &ops, c, 0)) return MXL_MGMT_INVALID;
    c->initialized = 1;
    /* Before a durable record is understood, fail closed for management TX.
     * The dispatcher drops IP/ARP for this invalid nonzero VID. It preserves
     * control protocols. This requires the native TX hook to be installed.
     */
    c->tx.vid = 4095; c->tx.index = 255;
    if (mxl_mgmt_store_load(&c->store) || mxl_mgmt_pce_admit_boot(&c->pce) ||
        validate(c, c->store.vid)) return fault(c);
    if (c->store.vid) {
        if (apply(c, c->store.vid)) return fault(c);
    } else { c->tx.vid = 0; c->tx.index = 0; }
    return mxl_mgmt_init(&c->policy, &ops, c, c->store.vid);
}
int mxl_mgmt_controller_propose(struct mxl_mgmt_controller *c, uint16_t vid)
{
    if (!c || !c->initialized) return MXL_MGMT_INVALID;
    /* The adapter takes a lease before invoking a potentially mutating native
     * handler, then releases it at end_request. Proposal and lease admission
     * share this mutex, so there is no check/unlock/dispatch race.
     */
    if (!mxl_mgmt_requests_idle(&c->requests)) return MXL_MGMT_BUSY;
    /* Native setters are allowed while the policy is off. Capture their final
     * CPU/ARP profiles only after all such requests have completed. */
    if (!c->tx.vid && c->policy.phase == MXL_MGMT_STABLE &&
        (mxl_mgmt_pce_admit(&c->pce) || spare(c))) return MXL_MGMT_INVALID;
    return mxl_mgmt_propose(&c->policy, vid, now(c));
}
int mxl_mgmt_controller_tick(struct mxl_mgmt_controller *c)
{
    return c && c->initialized ? mxl_mgmt_tick(&c->policy, now(c)) : MXL_MGMT_INVALID;
}
int mxl_mgmt_controller_confirm(struct mxl_mgmt_controller *c, uint32_t ticket)
{
    return c && c->initialized ? mxl_mgmt_confirm(&c->policy, ticket, now(c)) : MXL_MGMT_INVALID;
}
int mxl_mgmt_controller_cancel(struct mxl_mgmt_controller *c, uint32_t ticket)
{
    return c && c->initialized ? mxl_mgmt_cancel(&c->policy, ticket) : MXL_MGMT_INVALID;
}
int mxl_mgmt_controller_http_ready(const struct mxl_mgmt_controller *c)
{
    return c && c->initialized && c->store.ready && !c->requests.fault &&
           c->policy.phase <= MXL_MGMT_PENDING &&
           c->policy.active_vid <= 4094 && c->tx.vid == c->policy.active_vid &&
           (!c->policy.active_vid || c->pce.admitted);
}
int mxl_mgmt_controller_ip_write(struct mxl_mgmt_controller *c, const unsigned char *record)
{
    if (!c || !c->initialized) return 1; /* Native boot before controller start. */
    if (!c->tx.vid) return 1;
    if (c->policy.phase == MXL_MGMT_FAULT ||
        mxl_mgmt_iprule_write(&c->pce, record, c->tx.vid)) return -1;
    return 0;
}
int mxl_mgmt_controller_ip_end(struct mxl_mgmt_controller *c)
{
    if (!c || !c->initialized) return 0;
    if (c->policy.phase == MXL_MGMT_FAULT) return MXL_MGMT_UNCERTAIN;
    if (!c->tx.vid) {
        /* Policy-off address changes refresh the next proposal's baseline.
         * An unsupported second address disables admission, without changing
         * the intentionally unrestricted policy or its settings record.
         */
        if (mxl_mgmt_pce_admit(&c->pce) || spare(c)) {
            c->pce.admitted = 0;
            return MXL_MGMT_INVALID;
        }
        return 0;
    }
    if (mxl_mgmt_iprule_reconcile(&c->pce, c->tx.vid)) return fault(c);
    return 0;
}
