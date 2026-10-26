/* SPDX-License-Identifier: MIT
 * Development-only timer/ownership smoke test. No packet-policy/NVS writes.
 * Its heap object is a boot-lifetime IPv4 event subscriber, not CivetWeb data.
 */
#include <stddef.h>
#include <stdint.h>
#include "management_vlan_native.h"
#ifdef MXL_MGMT_EGRESS_OBSERVER
#include "management_vlan_egress_gate.h"
#include "management_vlan_store.h"
#include "management_vlan_tx.h"
#endif

struct observer {
    struct mxl_mgmt_event event;
    struct mxl_mgmt_native_mutex mutex;
    struct mxl_mgmt_native_work work;
    uint32_t magic, fires;
    uint64_t created, first, last;
    int schedule_result;
#ifdef MXL_MGMT_IP_HOOK_OBSERVER
    uint32_t ip_events, ip_writes;
    int ip_write_result;
#endif
#ifdef MXL_MGMT_EGRESS_OBSERVER
    uint32_t tx_count, tx_iface, tx_type, tx_thread;
    uint64_t first_tx, last_tx, startup_ms;
    int pce_status[3], stored_status;
    uint32_t startup_flags, saved_vid;
    uint64_t first_ip;
#endif
};
#define MAGIC UINT32_C(0x4f54474d)
typedef void *(*calloc_call)(unsigned, unsigned);
typedef void (*free_call)(void *);
static void timer(void *work)
{
    struct observer *s = (void *)((unsigned char *)work - offsetof(struct observer, work));
    mxl_mgmt_native_lock(&s->mutex);
    s->last = mxl_mgmt_native_now();
    if (!s->fires) s->first = s->last;
    if (s->fires != UINT32_MAX) s->fires++;
    if (s->fires < 2) s->schedule_result = mxl_mgmt_native_reschedule(&s->work, 1000);
    mxl_mgmt_native_unlock(&s->mutex);
}
static void event(struct mxl_mgmt_event *callback, uint32_t raised, void *iface)
{
    struct observer *s = (void *)callback;
    (void)raised;
    /* The registry lock may be held. Do not look up the owner or acquire its
     * mutex here; kernel scheduling is independently synchronized.
     */
    if (iface == (void *)0x20f64d64) mxl_mgmt_native_reschedule(&s->work, 1000);
}
static struct observer *find(void)
{
    struct mxl_mgmt_event *owner;
    if (mxl_mgmt_native_owner_claim(0, event, &owner) || !owner) return 0;
    return ((struct observer *)owner)->magic == MAGIC ? (void *)owner : 0;
}
#ifdef MXL_MGMT_IP_HOOK_OBSERVER
static struct observer *find_locked(void)
{
    struct mxl_mgmt_event *owner;
    if (mxl_mgmt_native_owner_find_locked(event, &owner) || !owner) return 0;
    return ((struct observer *)owner)->magic == MAGIC ? (void *)owner : 0;
}
/* Pass-through proof for the eventual controller: preserve the native event
 * and writer exactly, but exercise registry -> owner mutex ordering. The write
 * call below occurs inside the original callback while that mutex is held.
 */
void mxl_mgmt_observer_ip_event(struct mxl_mgmt_event *callback, uint32_t raised, void *iface)
{
    struct observer *s = find_locked();
    if (s) {
        mxl_mgmt_native_lock(&s->mutex);
#ifdef MXL_MGMT_EGRESS_OBSERVER
        if (!s->ip_events) s->first_ip = mxl_mgmt_native_now();
#endif
        s->ip_events++;
    }
    ((mxl_mgmt_event_handler)0x40024320)(callback, raised, iface);
    if (s) mxl_mgmt_native_unlock(&s->mutex);
}
int mxl_mgmt_observer_ip_write(void *device, unsigned char *record)
{
    struct observer *s = find_locked();
    int result = ((int (*)(void *, unsigned char *))0x400a156c)(device, record);
    if (s) { s->ip_writes++; s->ip_write_result = result; }
    return result;
}
#endif
#ifdef MXL_MGMT_EGRESS_OBSERVER
static void startup_snapshot(struct observer *s)
{
    unsigned char *record = ((calloc_call)0x40034f2c)(1, 466);
    unsigned char stored[16], index;
    struct mxl_mgmt_tx tx;
    uint16_t vid;
    unsigned i, j;
    s->startup_ms = mxl_mgmt_native_now();
    for (i = 0; i < 3; i++) {
        s->pce_status[i] = -12;
        if (record) {
            for (j = 0; j < 466; j++) record[j] = 0;
            record[7] = (unsigned char)(6 + i);
            s->pce_status[i] = mxl_mgmt_native_pce_read(0, record);
            if (!s->pce_status[i] && record[0x80]) s->startup_flags |= 1u << i;
        }
    }
    if (record) ((free_call)0x40034ec8)(record);
    tx.read_row = mxl_mgmt_native_vlan_row; tx.context = 0;
    if (!mxl_mgmt_tx_resolve(&tx, 1, &index)) s->startup_flags |= 8;
    s->stored_status = mxl_mgmt_native_store_read(0, stored, sizeof(stored));
    if (s->stored_status == 16 && !mxl_mgmt_record_decode(stored, 16, &vid)) {
        s->startup_flags |= 16; s->saved_vid = vid;
    }
}
static int try_find(void *unused, void **out)
{
    struct mxl_mgmt_event *owner;
    int result;
    (void)unused;
    *out = 0;
    result = mxl_mgmt_native_owner_try_find(event, &owner);
    if (!result && owner && ((struct observer *)owner)->magic == MAGIC) *out = owner;
    return result;
}
static int try_lock(void *owner) { return mxl_mgmt_native_trylock(&((struct observer *)owner)->mutex); }
static void unlock(void *owner) { mxl_mgmt_native_unlock(&((struct observer *)owner)->mutex); }
static void observe(void *owner, void *iface, const unsigned char *header)
{
    struct observer *s = owner;
    s->last_tx = mxl_mgmt_native_now();
    if (!s->tx_count) s->first_tx = s->last_tx;
    if (s->tx_count != UINT32_MAX) s->tx_count++;
    s->tx_iface = (uint32_t)(uintptr_t)iface;
    s->tx_type = ((unsigned)header[12] << 8) | header[13];
    s->tx_thread = ((uint32_t (*)(void))0x7000ce50)();
}
int mxl_mgmt_observer_tx(void *iface, void *packet, const unsigned char *header)
{
    static const struct mxl_mgmt_egress_gate gate = {
        0, (void *)0x20f64d64, try_find, try_lock, unlock, 0, 0, observe,
        mxl_mgmt_native_tx_original, 1
    };
    return mxl_mgmt_egress_gate_send(&gate, iface, packet, header, 14);
}
#endif
static int send(void *connection, const void *data, unsigned length)
{
    const unsigned char *bytes = data;
    while (length) {
        int written = ((int (*)(void *, const void *, unsigned))0x400dc1f4)
                       (connection, bytes, length);
        if (written <= 0 || (unsigned)written > length) return -1;
        bytes += written; length -= (unsigned)written;
    }
    return 0;
}
static void word(volatile unsigned char *out, uint32_t value)
{
    unsigned i;
    for (i = 0; i < 4; i++) out[i] = (unsigned char)(value >> (8 * i));
}
static void wide(volatile unsigned char *out, uint64_t value)
{
    word(out, (uint32_t)value); word(out + 4, (uint32_t)(value >> 32));
}
static int get(void *connection, void *unused)
{
    struct observer *s;
    const char **request = ((const char **(*)(void *))0x400db838)(connection);
    unsigned char body[48];
    volatile unsigned char *wire = body;
    unsigned i;
    static const char method[] = "HTTP/1.1 405 Method Not Allowed\r\nAllow: GET\r\n"
        "Content-Length: 0\r\nConnection: close\r\n\r\n";
    static const char unavailable[] = "HTTP/1.1 503 Service Unavailable\r\n"
        "Content-Length: 0\r\nConnection: close\r\n\r\n";
    static const char ok[] = "HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\n"
        "Content-Length: 48\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n";
    (void)unused;
    if (!request || !request[0] || ((int (*)(const char *, const char *))0x4003508c)
                                   (request[0], "GET")) {
        send(connection, method, sizeof(method) - 1); return 405;
    }
    s = find();
    if (!s) { send(connection, unavailable, sizeof(unavailable) - 1); return 503; }
    for (i = 0; i < sizeof(body); i++) wire[i] = 0;
    wire[0] = 'M'; wire[1] = 'V'; wire[2] = 'T'; wire[3] = 'O'; wire[4] = 1;
    mxl_mgmt_native_lock(&s->mutex);
    wire[5] = s->fires ? 2 : 1; wire[6] = 1;
    word(wire + 8, s->fires); word(wire + 12, sizeof(*s));
    wide(wire + 16, s->created); wide(wire + 24, s->first); wide(wire + 32, s->last);
    word(wire + 40, (uint32_t)s->schedule_result);
    mxl_mgmt_native_unlock(&s->mutex);
    if (!send(connection, ok, sizeof(ok) - 1)) send(connection, body, sizeof(body));
    return 200;
}
#ifdef MXL_MGMT_IP_HOOK_OBSERVER
static int ip_get(void *connection, void *unused)
{
    struct observer *s;
    const char **request = ((const char **(*)(void *))0x400db838)(connection);
    unsigned char body[24];
    volatile unsigned char *wire = body;
    unsigned i;
    static const char method[] = "HTTP/1.1 405 Method Not Allowed\r\nAllow: GET\r\n"
        "Content-Length: 0\r\nConnection: close\r\n\r\n";
    static const char unavailable[] = "HTTP/1.1 503 Service Unavailable\r\n"
        "Content-Length: 0\r\nConnection: close\r\n\r\n";
    static const char ok[] = "HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\n"
        "Content-Length: 24\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n";
    (void)unused;
    if (!request || !request[0] || ((int (*)(const char *, const char *))0x4003508c)
                                   (request[0], "GET")) {
        send(connection, method, sizeof(method) - 1); return 405;
    }
    s = find();
    if (!s) { send(connection, unavailable, sizeof(unavailable) - 1); return 503; }
    for (i = 0; i < sizeof(body); i++) wire[i] = 0;
    wire[0] = 'M'; wire[1] = 'V'; wire[2] = 'H'; wire[3] = 'O'; wire[4] = 1;
    mxl_mgmt_native_lock(&s->mutex);
    word(wire + 8, s->ip_events); word(wire + 12, s->ip_writes);
    word(wire + 16, (uint32_t)s->ip_write_result); word(wire + 20, sizeof(*s));
    mxl_mgmt_native_unlock(&s->mutex);
    if (!send(connection, ok, sizeof(ok) - 1)) send(connection, body, sizeof(body));
    return 200;
}
#endif
#ifdef MXL_MGMT_EGRESS_OBSERVER
static int egress_get(void *connection, void *unused)
{
    struct observer *s;
    const char **request = ((const char **(*)(void *))0x400db838)(connection);
    unsigned char body[88];
    volatile unsigned char *wire = body;
    unsigned i;
    static const char method[] = "HTTP/1.1 405 Method Not Allowed\r\nAllow: GET\r\n"
        "Content-Length: 0\r\nConnection: close\r\n\r\n";
    static const char unavailable[] = "HTTP/1.1 503 Service Unavailable\r\n"
        "Content-Length: 0\r\nConnection: close\r\n\r\n";
    static const char ok[] = "HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\n"
        "Content-Length: 88\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n";
    (void)unused;
    if (!request || !request[0] || ((int (*)(const char *, const char *))0x4003508c)
                                   (request[0], "GET")) {
        send(connection, method, sizeof(method) - 1); return 405;
    }
    s = find();
    if (!s) { send(connection, unavailable, sizeof(unavailable) - 1); return 503; }
    for (i = 0; i < sizeof(body); i++) wire[i] = 0;
    wire[0] = 'M'; wire[1] = 'V'; wire[2] = 'E'; wire[3] = 'O'; wire[4] = 1; wire[5] = 1;
    mxl_mgmt_native_lock(&s->mutex);
    word(wire + 8, s->tx_count); word(wire + 12, s->tx_iface);
    word(wire + 16, s->tx_type); word(wire + 20, s->tx_thread);
    wide(wire + 24, s->first_tx); wide(wire + 32, s->last_tx);
    wide(wire + 40, s->startup_ms);
    for (i = 0; i < 3; i++) word(wire + 48 + (i << 2), (uint32_t)s->pce_status[i]);
    word(wire + 60, (uint32_t)s->stored_status); word(wire + 64, s->startup_flags);
    word(wire + 68, s->saved_vid); wide(wire + 72, s->first_ip);
    word(wire + 80, sizeof(*s));
    mxl_mgmt_native_unlock(&s->mutex);
    if (!send(connection, ok, sizeof(ok) - 1)) send(connection, body, sizeof(body));
    return 200;
}
#endif
void mxl_mgmt_observer_register(void *context)
{
    struct observer *candidate;
    struct mxl_mgmt_event *owner;
    if (!find()) {
        candidate = ((calloc_call)0x40034f2c)(1, sizeof(*candidate));
        if (candidate) {
            if (mxl_mgmt_native_mutex_init(&candidate->mutex)) {
                ((free_call)0x40034ec8)(candidate);
            } else {
                candidate->magic = MAGIC; candidate->created = mxl_mgmt_native_now();
#ifdef MXL_MGMT_EGRESS_OBSERVER
                startup_snapshot(candidate);
#endif
                mxl_mgmt_native_work_init(&candidate->work, timer);
                if (mxl_mgmt_native_owner_claim(&candidate->event, event, &owner) ||
                    owner != &candidate->event) {
                    /* Work is not queued and the candidate was not published. */
                    ((free_call)0x40034ec8)(candidate);
                } else {
                    mxl_mgmt_native_lock(&candidate->mutex);
                    candidate->schedule_result = mxl_mgmt_native_reschedule(&candidate->work, 1000);
                    mxl_mgmt_native_unlock(&candidate->mutex);
                }
            }
        }
    }
    ((void (*)(void *, const char *, int (*)(void *, void *), void *))0x400de5c0)
        (context, "/management-vlan-timer-probe.json", get, 0);
#ifdef MXL_MGMT_IP_HOOK_OBSERVER
    ((void (*)(void *, const char *, int (*)(void *, void *), void *))0x400de5c0)
        (context, "/management-vlan-ip-hook-probe.json", ip_get, 0);
#endif
#ifdef MXL_MGMT_EGRESS_OBSERVER
    ((void (*)(void *, const char *, int (*)(void *, void *), void *))0x400de5c0)
        (context, "/management-vlan-egress-probe.json", egress_get, 0);
#endif
}
