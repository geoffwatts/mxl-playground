/* SPDX-License-Identifier: MIT
 * Exact-build native bindings, based on V2 CLI and native caller evidence.
 * No boot registration or HTTP write route here. The diagnostic image links
 * only read/clock/mutex helpers by default; observer builds additionally link
 * timer/ownership helpers. Policy-write functions remain absent from observers.
 */
#include <stddef.h>
#include <stdint.h>
#include "management_vlan_native.h"
#include "management_vlan_store.h"
#include "management_vlan_tx.h"

_Static_assert(sizeof(void *) == 4, "WSP bindings require ARC32");
_Static_assert(sizeof(struct mxl_mgmt_native_mutex) == 20, "Native mutex ABI");
_Static_assert(sizeof(struct mxl_mgmt_native_work) == 0x28, "Native work ABI");
_Static_assert(sizeof(struct mxl_mgmt_event) == 20, "Native net_mgmt callback ABI");
_Static_assert(offsetof(struct mxl_mgmt_event, event_mask) == 16, "Native callback mask ABI");

int mxl_mgmt_native_mutex_init(struct mxl_mgmt_native_mutex *m)
{
    return ((int (*)(void *, const void *))0x70002510)(m, 0);
}
int mxl_mgmt_native_trylock(struct mxl_mgmt_native_mutex *m)
{
    /* Same internal entry as pthread_mutex_lock, but K_NO_WAIT words 0/0.
     * Busy/self-owned normal mutexes return nonzero without sleeping.
     */
    return ((int (*)(void *, uint32_t, uint32_t))0x7000234c)(m, 0, 0);
}
void mxl_mgmt_native_lock(struct mxl_mgmt_native_mutex *m)
{
    ((void (*)(void *))0x70002530)(m);
}
int mxl_mgmt_native_unlock(struct mxl_mgmt_native_mutex *m)
{
    return ((int (*)(void *))0x7000253c)(m);
}
void mxl_mgmt_native_work_init(struct mxl_mgmt_native_work *work, void (*callback)(void *))
{
    ((void (*)(void *, void (*)(void *)))0x7000b0dc)(work, callback);
}
int mxl_mgmt_native_reschedule(struct mxl_mgmt_native_work *work, uint32_t delay_ms)
{
    int result;
    if (!delay_ms || delay_ms > 60000) return -1;
    /* Native callers pass r0=work, r1=relative ticks, r2=high word. Explicit
     * word arguments preserve that ABI rather than assuming pair alignment.
     * This exact build reports kernel ticks directly as milliseconds.
     */
    result = ((int (*)(void *, uint32_t, uint32_t))0x7000b3e4)(work, delay_ms, 0);
    return result < 0 ? -1 : 0;
}
uint64_t mxl_mgmt_native_now(void)
{
    return ((uint64_t (*)(void))0x7000d8d0)();
}

typedef int (*pce_call)(void *, void *, void *);
static int pce(unsigned slot, unsigned char *record)
{
    uintptr_t api = ((uintptr_t (*)(void))0x4008eaac)();
    pce_call call;
    if (!api || !record) return -1;
    call = *(pce_call volatile *)(api + slot);
    return call ? call((void *)0x400fa010, record, (void *)call) : -1;
}
int mxl_mgmt_native_pce_read(void *unused, unsigned char *record)
{
    (void)unused;
    return pce(0x6c, record);
}
int mxl_mgmt_native_pce_write(void *unused, unsigned char *record)
{
    (void)unused;
    return pce(0x70, record);
}

/* NVS callbacks advertise a nominal length of 256, not the stored size.
 * Its reader returns min(actual size, requested size); use a sentinel byte
 * beyond the admitted capacity to distinguish exact records from truncation. */
typedef int (*reader_call)(void *, void *, unsigned);
typedef int (*load_callback)(const char *, unsigned, reader_call, void *, void *);
struct load_context { unsigned char *data; unsigned capacity; int result, seen; };
struct load_arguments { const char *key; load_callback callback; void *context; };
static int load_one(const char *suffix, unsigned length, reader_call read,
                    void *read_context, void *parameter)
{
    struct load_context *context = parameter;
    if (suffix && *suffix) return 0; /* Ignore descendants, never a prefix hit. */
    if (context->seen || length > 0x7fffffff || !read) {
        context->result = -5;
        return -5;
    }
    context->seen = 1;
    context->result = mxl_mgmt_store_read_value(read,read_context,context->data,context->capacity);
    return context->result<0 ? -5 : 0;
}
static const char key[] = "mxl/management-vlan";
static int key_read(const char *name, unsigned char *data, unsigned capacity)
{
    struct load_context context;
    struct load_arguments arguments;
    uintptr_t backend, api, function;
    int result;
    if (!data || !name || !capacity || capacity > 64) return -5;
    context.data = data; context.capacity = capacity;
    context.result = MXL_MGMT_STORE_MISSING; context.seen = 0;
    arguments.key = name; arguments.callback = load_one; arguments.context = &context;
    /* 40032380 discards each backend's error return. Call the admitted single
     * NVS backend with the same lock/arguments, retaining its status. Multiple
     * or foreign backends are unsupported rather than mistaken for absence.
     */
    result = ((int (*)(void *, uint32_t, uint32_t))0x70009cc0)
             ((void *)0x20f64b74, UINT32_MAX, UINT32_MAX);
    if (result) return -5;
    backend = *(uintptr_t volatile *)0x20f1276c;
    result = -5;
    if (backend && backend == *(uintptr_t volatile *)0x20f12774 &&
        !*(uintptr_t volatile *)backend) {
        api = *(uintptr_t volatile *)(backend + 4);
        function = api ? *(uintptr_t volatile *)api : 0;
        if (function == 0x40032790)
            result = ((int (*)(void *, const void *, void *))function)
                     ((void *)backend, &arguments, (void *)function);
    }
    ((void (*)(void *))0x70009f5c)((void *)0x20f64b74);
    return result ? -5 : context.result;
}
int mxl_mgmt_native_store_read(void *unused, unsigned char *data, unsigned capacity)
{
    (void)unused;
    if (capacity != MXL_MGMT_RECORD_BYTES) return -5;
    return key_read(key,data,capacity);
}
int mxl_mgmt_native_store_write(void *unused, const unsigned char *data, unsigned length)
{
    uint16_t vid;
    (void)unused;
    if (mxl_mgmt_record_decode(data, length, &vid)) return -1;
    return ((int (*)(const char *, const void *, unsigned))0x400331d4)(key, data, length);
}

int mxl_mgmt_native_vlan_row(void *unused, unsigned index, unsigned char *row)
{
    const volatile unsigned char *source;
    volatile unsigned shifted;
    unsigned i;
    (void)unused;
    if (index >= MXL_MGMT_VLAN_ROWS || !row) return -1;
    /* GCC -Os otherwise lowers the 33-byte stride to __mulsi3 on EM4.
     * Keep this dependency explicit without assuming an optional multiplier.
     */
    shifted = index << 5;
    source = (const volatile unsigned char *)(0x20f22808u + shifted + index);
    for (i = 0; i < 6; i++) row[i] = source[i];
    return 0;
}
int mxl_mgmt_native_tx_original(void *unused, void *iface, void *packet,
                                  const unsigned char *header)
{
    (void)unused;
    return ((int (*)(void *, void *, const void *))0x4004eda4)(iface, packet, header);
}
int mxl_mgmt_native_tx_insert(void *unused, void *iface, void *packet,
                                unsigned index, const unsigned char *header)
{
    (void)unused;
    if (!packet || !header || index >= MXL_MGMT_VLAN_ROWS) return -1;
    ((volatile unsigned char *)packet)[0x55] = (unsigned char)index;
    return ((int (*)(void *, void *, unsigned, const void *))0x4004e434)
           (iface, packet, index, header);
}

static int registry_lock(void *unused)
{
    (void)unused;
    return ((int (*)(void *, uint32_t, uint32_t))0x70009cc0)
           ((void *)0x20f64b60, UINT32_MAX, UINT32_MAX);
}
static void registry_unlock(void *unused)
{
    (void)unused;
    ((void (*)(void *))0x70009f5c)((void *)0x20f64b60);
}
int mxl_mgmt_native_owner_claim(struct mxl_mgmt_event *candidate,
                                 mxl_mgmt_event_handler handler,
                                 struct mxl_mgmt_event **owner)
{
    static const struct mxl_mgmt_registry registry = {
        (struct mxl_mgmt_event **)0x20f13afc, (struct mxl_mgmt_event **)0x20f13b00,
        (uint32_t *)0x20f13f04, registry_lock, registry_unlock, 0
    };
    /* Exact native IP-address callback at 20f119a0 subscribes to this mask.
     * The new module can observe address additions/removals as well as use
     * the registry's boot lifetime. Registration/lookup is atomic, unlike a
     * find-unlock-add sequence that can create duplicate module instances.
     */
    return mxl_mgmt_owner_claim(&registry, candidate, handler, UINT32_C(0xe0040003), owner);
}

int mxl_mgmt_native_owner_find_locked(mxl_mgmt_event_handler handler,
                                       struct mxl_mgmt_event **owner)
{
    static const struct mxl_mgmt_registry registry = {
        (struct mxl_mgmt_event **)0x20f13afc, (struct mxl_mgmt_event **)0x20f13b00,
        (uint32_t *)0x20f13f04, 0, 0, 0
    };
    /* 40055b9e takes 20f64b60, 40055ebc invokes the callback, and 40055cb6
     * releases it after iteration. This lookup uses the existing ownership;
     * no further acquisition is needed. The kernel registry mutex is recursive,
     * unlike the module's normal pthread mutex. Cross-thread lock order still
     * matters; packet lookup/acquisition must never wait.
     */
    return mxl_mgmt_owner_find_locked(&registry, handler, UINT32_C(0xe0040003), owner);
}
int mxl_mgmt_native_owner_try_find(mxl_mgmt_event_handler handler,
                                    struct mxl_mgmt_event **owner)
{
    int result;
    if (!owner) return -1;
    *owner = 0;
    result = ((int (*)(void *, uint32_t, uint32_t))0x70009cc0)
             ((void *)0x20f64b60, 0, 0);
    if (result) return -1;
    result = mxl_mgmt_native_owner_find_locked(handler, owner);
    registry_unlock(0);
    return result;
}
int mxl_mgmt_native_http_original(void *unused, void *connection)
{
    (void)unused;
    return ((int (*)(void *))0x4001b504)(connection);
}
void mxl_mgmt_native_http_unavailable(void *unused, void *connection)
{
    static const char response[] = "HTTP/1.1 503 Service Unavailable\r\n"
        "Content-Length: 0\r\nRetry-After: 1\r\nConnection: close\r\n\r\n";
    unsigned left = sizeof(response) - 1;
    const char *next = response;
    (void)unused;
    while (left) {
        int n = ((int (*)(void *, const void *, unsigned))0x400dc1f4)(connection, next, left);
        if (n <= 0 || (unsigned)n > left) return;
        next += n; left -= (unsigned)n;
    }
}
int mxl_mgmt_native_request_session(void *connection, unsigned char *out)
{
    const char *header;
    char token[33];
    unsigned i;
    int length;
    if (!connection || !out) return -1;
    header = ((const char *(*)(void *, const char *))0x400db848)(connection,"Cookie");
    if (!header) return -1;
    /* Identical extractor/key/size to the audited native session lookup.
     * Read from this connection's immutable header, not the global session
     * slot which another login can change after authorization returns.
     */
    length = ((int (*)(const char *,const char *,char *,unsigned))0x400dc970)
             (header,"session",token,sizeof(token));
    if (length != 32 || token[32]) return -1;
    for (i=0;i<32;i++) {
        unsigned char c=(unsigned char)token[i];
        if (!((c>='0' && c<='9') || (c>='a' && c<='f') || (c>='A' && c<='F'))) return -1;
    }
    for (i=0;i<32;i++) out[i]=(unsigned char)token[i];
    return 0;
}
int mxl_mgmt_native_vlan_persist(uint16_t vid)
{
    _Alignas(4) unsigned char expected[36], actual[36];
    unsigned char index, frame=0;
    char name[64];
    struct mxl_mgmt_tx tx;
    uint32_t count=0;
    unsigned i,j,matches=0;
    int ports;
    if (!vid || vid>4094) return -1;
    tx.context=0; tx.read_row=mxl_mgmt_native_vlan_row;
    if (mxl_mgmt_tx_resolve(&tx,vid,&index)) return -1;
    for (i=0;i<36;i++) expected[i]=0;
    /* Same 36-byte VID/name/port-state record as native tag_vlan_hw_save.
     * CPU port state at byte 19 is not initialized by the vendor getter and
     * is not a front-panel configuration field; it is excluded below. */
    if (((int (*)(unsigned,void *,void *,void *))0x4004c6f8)
        (index,expected+2,expected+19,expected)) return -1;
    if ((expected[0]|((unsigned)expected[1]<<8))!=vid) return -1;
    ((void (*)(void))0x40011204)();
    ((void (*)(void))0x40010fa4)();
    if (key_read("sys/tag_based_vlan_entry_num",(unsigned char *)&count,4)!=4 ||
        !count || count>100) return -1;
    for (i=0;i<count;i++) {
        ((int (*)(char *,unsigned,const char *,unsigned))0x4003524c)
            (name,sizeof(name),"sys/tag_based_vlan_entry%d",i);
        if (key_read(name,actual,36)!=36) return -1;
        if ((actual[0]|((unsigned)actual[1]<<8))!=vid) continue;
        matches++;
        for (j=0;j<36;j++) if (j!=19 && actual[j]!=expected[j]) return -1;
    }
    if (matches!=1) return -1;
    ports=((int (*)(void))0x40087844)();
    if (ports<1 || ports>16) return -1;
    for (i=1;i<=(unsigned)ports;i++) {
        void *iface=((void *(*)(unsigned))0x4008792c)(i);
        for (j=0;j<4;j++) expected[j]=0;
        if (!iface || ((int (*)(void *,void *,void *,void *))0x4004cc84)
            (iface,expected,expected+2,&frame)) return -1;
        expected[3]=frame;
        ((int (*)(char *,unsigned,const char *,unsigned))0x4003524c)
            (name,sizeof(name),"sys/port_based_vlan_cfg%d",i);
        if (key_read(name,actual,4)!=4) return -1;
        for (j=0;j<4;j++) if (actual[j]!=expected[j]) return -1;
    }
    return 0;
}
