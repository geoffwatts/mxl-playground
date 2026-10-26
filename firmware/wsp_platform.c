/* SPDX-License-Identifier: MIT */
#include "wsp_platform.h"
#include "wsp_profile.h"
#include <stddef.h>
#include <stdint.h>
_Static_assert(sizeof(void *) == 4, "Audited ARC32 platform only");
_Static_assert(sizeof(struct wsp_mutex) == 20, "Native mutex ABI");
_Static_assert(sizeof(struct wsp_owner) == 20 && offsetof(struct wsp_owner, mask) == 16,
               "Native event ABI");
void *wsp_alloc(unsigned n) { return ((void *(*)(unsigned, unsigned))WSP_CALLOC)(1, n); }
void wsp_free(void *p) { ((void (*)(void *))WSP_FREE)(p); }
uint64_t wsp_now(void) { return ((uint64_t (*)(void))WSP_NOW_MS)(); }
int wsp_mutex_init(struct wsp_mutex *m) {
    return ((int (*)(void *, const void *))WSP_MUTEX_INIT)(m, 0);
}
int wsp_trylock(struct wsp_mutex *m) {
    return ((int (*)(void *, uint32_t, uint32_t))WSP_MUTEX_TRYLOCK)(m, 0, 0);
}
void wsp_lock(struct wsp_mutex *m) { ((void (*)(void *))WSP_MUTEX_LOCK)(m); }
void wsp_unlock(struct wsp_mutex *m) { ((void (*)(void *))WSP_MUTEX_UNLOCK)(m); }
int wsp_http_get(void *c) {
    const char **r = ((const char **(*)(void *))WSP_HTTP_REQUEST)(c);
    return r && r[0] && !((int (*)(const char *, const char *))WSP_STRCMP)(r[0], "GET");
}
int wsp_http_send(void *c, const void *data, unsigned n) {
    const unsigned char *p = data;
    while (n) {
        int k = ((int (*)(void *, const void *, unsigned))WSP_HTTP_WRITE)(c, p, n);
        if (k <= 0 || (unsigned)k > n)
            return -1;
        p += k;
        n -= (unsigned)k;
    }
    return 0;
}
int wsp_http_error(void *c, int status) {
    ((int (*)(void *, int, const char *, ...))WSP_HTTP_ERROR)(c, status,
                                                              "LLDP request unavailable");
    return status;
}
void wsp_http_register(void *c, const char *path, int (*handler)(void *, void *), void *s) {
    ((void (*)(void *, const char *, int (*)(void *, void *), void *))WSP_HTTP_REGISTER)(
        c, path, handler, s);
}
int wsp_owner_claim(struct wsp_owner *candidate, void (*handler)(void *, uint32_t, void *),
                    struct wsp_owner **out, int wait) {
    struct wsp_owner *p, *last = 0, *found = 0;
    unsigned count = 0;
    int result = -1;
    *out = 0;
    if (((int (*)(void *, uint32_t, uint32_t))WSP_REGISTRY_LOCK)(
            (void *)WSP_REGISTRY_MUTEX, wait ? UINT32_MAX : 0, wait ? UINT32_MAX : 0))
        return -1;
    for (p = *(struct wsp_owner **)WSP_REGISTRY_HEAD; p; p = p->next) {
        if (++count > 64)
            goto done;
        last = p;
        if (p->handler == handler) {
            if (found || p->mask != UINT32_C(0xe0040003))
                goto done;
            found = p;
        }
    }
    if (last != *(struct wsp_owner **)WSP_REGISTRY_TAIL)
        goto done;
    if (!found && candidate) {
        candidate->handler = handler;
        candidate->mask = UINT32_C(0xe0040003);
        candidate->next = *(struct wsp_owner **)WSP_REGISTRY_HEAD;
        *(struct wsp_owner **)WSP_REGISTRY_HEAD = candidate;
        if (!last)
            *(struct wsp_owner **)WSP_REGISTRY_TAIL = candidate;
        *(uint32_t *)WSP_REGISTRY_MASK |= candidate->mask;
        found = candidate;
    }
    *out = found;
    result = 0;
done:
    ((void (*)(void *))WSP_REGISTRY_UNLOCK)((void *)WSP_REGISTRY_MUTEX);
    return result;
}
