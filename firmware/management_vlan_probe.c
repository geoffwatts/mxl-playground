/* SPDX-License-Identifier: MIT
 * READ-ONLY exact-build ABI probe. No policy writes, timers or persistence.
 * Its role is to validate compiled C and the packed PCE profile on hardware
 * before linking the transaction engine into a working firmware feature.
 */
#include <stdint.h>
#include "management_vlan_pce.h"
#include "management_vlan_native.h"
#include "management_vlan_store.h"
#include "management_vlan_tx.h"

_Static_assert(sizeof(void *) == 4, "This binding requires ARC32");
typedef int (*pce_call)(void *, void *, void *);
typedef int (*write_call)(void *, const void *, unsigned);
typedef void *(*calloc_call)(unsigned, unsigned);
typedef void (*free_call)(void *);
typedef const char **(*request_call)(void *);
typedef int (*strcmp_call)(const char *, const char *);
typedef void (*register_call)(void *, const char *, int (*)(void *, void *), void *);

static int native_read(void *unused, unsigned char *data)
{
    uintptr_t api = ((uintptr_t (*)(void))0x4008eaac)();
    pce_call call;
    (void)unused;
    if (!api) return -1;
    /* Exact V2 CLI 400b1e6c calls +0x6c. +0x64 enables a rule. */
    call = *(pce_call volatile *)(api + 0x6c);
    if (!call) return -1;
    return call((void *)0x400fa010, data, (void *)call);
}
static int never_write(void *unused, unsigned char *data)
{
    (void)unused; (void)data;
    return -1;
}
static int send(void *connection, const void *data, unsigned length)
{
    const unsigned char *bytes = data;
    while (length) {
        int count = ((write_call)0x400dc1f4)(connection, bytes, length);
        if (count <= 0 || (unsigned)count > length) return -1;
        bytes += count;
        length -= (unsigned)count;
    }
    return 0;
}

static int probe(void *connection, void *unused)
{
    struct mxl_mgmt_pce *profile;
    const char **request = ((request_call)0x400db838)(connection);
    unsigned char header[16];
    volatile unsigned char *wire = header;
    unsigned i;
    static const char ok[] = "HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\n"
        "Content-Length: 948\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n";
    static const char unavailable[] = "HTTP/1.1 503 Service Unavailable\r\n"
        "Content-Length: 0\r\nConnection: close\r\n\r\n";
    static const char method[] = "HTTP/1.1 405 Method Not Allowed\r\nAllow: GET\r\n"
        "Content-Length: 0\r\nConnection: close\r\n\r\n";
    (void)unused;
    if (!request || !request[0] || ((strcmp_call)0x4003508c)(request[0], "GET")) {
        send(connection, method, sizeof(method) - 1);
        return 405;
    }
    profile = ((calloc_call)0x40034f2c)(1, sizeof(*profile));
    if (!profile) {
        send(connection, unavailable, sizeof(unavailable) - 1);
        return 503;
    }
    profile->read = native_read;
    profile->write = never_write;
    /* Explicit byte stores avoid a compiler-generated libc dependency. */
    for (i = 0; i < sizeof(header); i++) wire[i] = 0;
    wire[0] = 'M'; wire[1] = 'V'; wire[2] = 'P'; wire[3] = 'R';
    wire[4] = 1; wire[6] = 2; wire[8] = 0xd2; wire[9] = 1;
    wire[10] = 6; wire[11] = 7;
    /* Capture both records even if profile admission fails. */
    for (i = 0; i < 2; i++) {
        profile->original[i][7] = (unsigned char)(6 + i);
        if (native_read(0, profile->original[i])) {
            ((free_call)0x40034ec8)(profile);
            send(connection, unavailable, sizeof(unavailable) - 1);
            return 503;
        }
    }
    header[5] = mxl_mgmt_pce_admit(profile) == 0;
    if (!send(connection, ok, sizeof(ok) - 1) && !send(connection, header, sizeof(header)))
        send(connection, profile->original, sizeof(profile->original));
    ((free_call)0x40034ec8)(profile);
    return 200;
}

static void word(volatile unsigned char *to, uint32_t value)
{
    unsigned i;
    for (i = 0; i < 4; i++) to[i] = (unsigned char)(value >> (8 * i));
}
static int platform_probe(void *connection, void *unused)
{
    struct mxl_mgmt_native_mutex mutex;
    struct mxl_mgmt_tx tx;
    const char **request = ((request_call)0x400db838)(connection);
    unsigned char body[48], index = 255;
    volatile unsigned char *wire = body;
    uint64_t before, after;
    uint16_t vid = 0;
    int loaded, mutex_result;
    unsigned i;
    static const char ok[] = "HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\n"
        "Content-Length: 48\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n";
    static const char method[] = "HTTP/1.1 405 Method Not Allowed\r\nAllow: GET\r\n"
        "Content-Length: 0\r\nConnection: close\r\n\r\n";
    (void)unused;
    if (!request || !request[0] || ((strcmp_call)0x4003508c)(request[0], "GET")) {
        send(connection, method, sizeof(method) - 1);
        return 405;
    }
    for (i = 0; i < sizeof(body); i++) wire[i] = 0;
    wire[0] = 'M'; wire[1] = 'V'; wire[2] = 'N'; wire[3] = 'P'; wire[4] = 1;
    before = mxl_mgmt_native_now();
    mutex_result = mxl_mgmt_native_mutex_init(&mutex);
    if (!mutex_result) {
        mxl_mgmt_native_lock(&mutex);
        mutex_result = mxl_mgmt_native_unlock(&mutex);
    }
    wire[5] = mutex_result == 0;
    tx.read_row = mxl_mgmt_native_vlan_row; tx.context = 0;
    if (!mxl_mgmt_tx_resolve(&tx, 1, &index)) wire[6] = 1;
    wire[7] = index;
    loaded = mxl_mgmt_native_store_read(0, body + 28, MXL_MGMT_RECORD_BYTES);
    after = mxl_mgmt_native_now();
    word(wire + 8, (uint32_t)before); word(wire + 12, (uint32_t)(before >> 32));
    word(wire + 16, (uint32_t)after); word(wire + 20, (uint32_t)(after >> 32));
    word(wire + 24, (uint32_t)loaded);
    if (loaded == MXL_MGMT_RECORD_BYTES && !mxl_mgmt_record_decode(body + 28, 16, &vid)) {
        wire[44] = 1; wire[45] = (unsigned char)vid; wire[46] = (unsigned char)(vid >> 8);
    }
    if (!send(connection, ok, sizeof(ok) - 1)) send(connection, body, sizeof(body));
    return 200;
}

void mxl_mgmt_probe_register(void *context)
{
    /* The vendor authorization callback protects .json routes, but skips .bin.
     * The diagnostic body remains binary; the suffix selects its login guard.
     */
    ((register_call)0x400de5c0)(context, "/management-vlan-probe.json", probe, 0);
    ((register_call)0x400de5c0)(context, "/management-vlan-platform-probe.json", platform_probe, 0);
#ifdef MXL_MGMT_TIMER_OBSERVER
    extern void mxl_mgmt_observer_register(void *);
    mxl_mgmt_observer_register(context);
#endif
#ifdef MXL_MGMT_RUNTIME_TRIAL
    extern void mxl_mgmt_runtime_register(void *);
    mxl_mgmt_runtime_register(context);
#endif
}
