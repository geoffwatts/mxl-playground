/* SPDX-License-Identifier: MIT
 * WSP adapter: borrowed native packet -> copied LLDP PDU/port/time. The core
 * knows neither native layouts nor pointers. Preserve original parser/ownership.
 */
#include "lldp_cache.h"
#include "wsp_platform.h"
#include "wsp_profile.h"
#include <stdint.h>
struct state {
    struct wsp_owner owner;
    struct wsp_mutex mutex;
    uint32_t magic, dropped;
    struct mxl_lldp_cache cache;
    unsigned char frame[MXL_LLDP_FRAME_BYTES];
};
#define MAGIC UINT32_C(0x50444c4d)
_Static_assert(MXL_LLDP_CAPACITY == 16 && MXL_LLDP_RECORD_BYTES == 780,
               "LLDP wire version 1 framing");
static void owner(void *e, uint32_t event, void *iface) {
    (void)e;
    (void)event;
    (void)iface;
}
static struct state *find(void) {
    struct wsp_owner *p;
    if (wsp_owner_claim(0, owner, &p, 0) || !p)
        return 0;
    return ((struct state *)p)->magic == MAGIC ? (struct state *)p : 0;
}
static int capture(struct state *s, void *packet) {
    static const unsigned char ports[32] = WSP_PORT_MAP;
    unsigned at = 0, n, type, driver = *(volatile unsigned char *)WSP_LLDP_LATEST;
    void *clone;
    if (driver >= 32 || !ports[driver])
        return -1;
    /* shallow clone preserves the native cursor already advanced past Ethernet;
     * buffer refs are shared read-only, and the clone is released on every path. */
    clone = ((void *(*)(void *, unsigned, unsigned, const char *, unsigned))WSP_PACKET_CLONE)(
        packet, 0, 0, "mxl-lldp", 1);
    if (!clone)
        return -1;
    while (at + 2 <= MXL_LLDP_FRAME_BYTES) {
        if (((int (*)(void *, void *, unsigned))WSP_PACKET_READ)(clone, s->frame + at, 2))
            break;
        n = ((unsigned)s->frame[at] & 1u) * 256u + s->frame[at + 1];
        type = s->frame[at] >> 1;
        at += 2;
        if (n > MXL_LLDP_FRAME_BYTES - at)
            break;
        if (n && ((int (*)(void *, void *, unsigned))WSP_PACKET_READ)(clone, s->frame + at, n))
            break;
        at += n;
        if (!type) {
            int result = mxl_lldp_receive(&s->cache, ports[driver], s->frame, at, wsp_now());
            ((void (*)(void *, const char *, unsigned))WSP_PACKET_UNREF)(clone, "mxl-lldp", 2);
            return result;
        }
    }
    ((void (*)(void *, const char *, unsigned))WSP_PACKET_UNREF)(clone, "mxl-lldp", 3);
    s->cache.invalid++;
    s->cache.generation++;
    return -1;
}
int mxl_lldp_receive_native(void *packet) {
    struct state *s = find();
    if (s && !wsp_trylock(&s->mutex)) {
        if (capture(s, packet))
            s->dropped++;
        wsp_unlock(&s->mutex);
    }
    return ((int (*)(void *))WSP_LLDP_PARSER)(packet);
}
static int handle(void *connection, void *parameter) {
    struct state *s = parameter;
    unsigned char header[32], tail[4], *record;
    unsigned i;
    uint64_t now;
    static const char ok[] =
        "HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\nContent-Length: "
        "12516\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n";
    if (!wsp_http_get(connection))
        return wsp_http_error(connection, 405);
    if (!s || s->magic != MAGIC)
        return wsp_http_error(connection, 503);
    record = wsp_alloc(MXL_LLDP_RECORD_BYTES);
    if (!record)
        return wsp_http_error(connection, 503);
    wsp_lock(&s->mutex);
    now = wsp_now();
    mxl_lldp_expire(&s->cache, now);
    mxl_lldp_header(&s->cache, header, s->dropped);
    wsp_unlock(&s->mutex);
    if (wsp_http_send(connection, ok, sizeof(ok) - 1) || wsp_http_send(connection, header, 32))
        goto done;
    for (i = 0; i < MXL_LLDP_CAPACITY; i++) {
        wsp_lock(&s->mutex);
        mxl_lldp_record(&s->cache, i, record, now);
        wsp_unlock(&s->mutex);
        if (wsp_http_send(connection, record, MXL_LLDP_RECORD_BYTES))
            goto done;
    }
    wsp_lock(&s->mutex);
    for (i = 0; i < 4; i++)
        tail[i] = (unsigned char)(s->cache.generation >> (i * 8));
    wsp_unlock(&s->mutex);
    wsp_http_send(connection, tail, 4);
done:
    wsp_free(record);
    return 200;
}
void mxl_lldp_register(void *context) {
    struct wsp_owner *p = 0;
    struct state *s = find(), *candidate;
    if (!s) {
        candidate = wsp_alloc(sizeof(*candidate));
        if (candidate) {
            if (wsp_mutex_init(&candidate->mutex)) {
                wsp_free(candidate);
            } else {
                candidate->magic = MAGIC;
                if (wsp_owner_claim(&candidate->owner, owner, &p, 1) || p != &candidate->owner)
                    wsp_free(candidate);
                if (p && ((struct state *)p)->magic == MAGIC)
                    s = (struct state *)p;
            }
        }
    }
    wsp_http_register(context, "/lldp-neighbors.json", handle, s);
}
