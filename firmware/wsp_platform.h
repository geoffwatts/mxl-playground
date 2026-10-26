/* SPDX-License-Identifier: MIT */
#ifndef MXL_WSP_PLATFORM_H
#define MXL_WSP_PLATFORM_H
#include <stdint.h>
/* Platform types/calls only. Native layouts must not leak into feature cores.
 * Mutex/work ABI is audited for this profile, not inferred from addresses. */
struct wsp_mutex {
    uint32_t words[5];
};
void *wsp_alloc(unsigned);
void wsp_free(void *);
uint64_t wsp_now(void);
int wsp_mutex_init(struct wsp_mutex *);
int wsp_trylock(struct wsp_mutex *);
void wsp_lock(struct wsp_mutex *);
void wsp_unlock(struct wsp_mutex *);
int wsp_http_get(void *);
int wsp_http_send(void *, const void *, unsigned);
int wsp_http_error(void *, int);
void wsp_http_register(void *, const char *, int (*)(void *, void *), void *);
/* Owner registry retains the allocation until reset. Call before module mutex.
 * Returned pointers are boot-lived; no module is unregistered or freed. */
struct wsp_owner {
    struct wsp_owner *next;
    void (*handler)(void *, uint32_t, void *);
    const void *info;
    uint32_t length, mask;
};
int wsp_owner_claim(struct wsp_owner *, void (*)(void *, uint32_t, void *), struct wsp_owner **,
                    int);
#endif
