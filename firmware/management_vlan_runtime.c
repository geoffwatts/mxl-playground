/* SPDX-License-Identifier: MIT
 * Exact V2 integration candidate. Trial mode admits only temporary VID 0/1
 * proposals and cancellation. No settings write/confirmation is provided.
 * Its hooks must be installed together; this is not a standalone extension.
 */
#include <stddef.h>
#include <stdint.h>
#include "management_vlan_controller.h"
#include "management_vlan_native.h"
#include "management_vlan_egress_gate.h"
#ifdef MXL_MGMT_RUNTIME_FULL
#include "management_vlan_identity.h"
#define API_VERSION 2
#define API_FLAGS 2
#define COMMAND_BYTES 32
#define RESPONSE_BYTES 128
#else
#define API_VERSION 1
#define API_FLAGS 1
#define COMMAND_BYTES 16
#define RESPONSE_BYTES 96
#endif

struct runtime {
    struct mxl_mgmt_event event;
    struct mxl_mgmt_native_mutex mutex;
    struct mxl_mgmt_native_work work;
    uint32_t magic;
    struct mxl_mgmt_controller controller;
#ifdef MXL_MGMT_RUNTIME_FULL
    struct mxl_mgmt_identity identity;
#endif
    uint32_t ip_events, ip_writes, timer_fires, tx_count;
    uint32_t native_begin, native_end, all_end;
    int ip_result, timer_result, start_result;
};
#define MAGIC UINT32_C(0x5256474d)
static void event(struct mxl_mgmt_event *e, uint32_t raised, void *iface)
{
    /* Registry ownership only. In particular, do not replace the transaction
     * rollback deadline when an IP event arrives. */
    (void)e; (void)raised; (void)iface;
}
static struct runtime *checked(struct mxl_mgmt_event *e)
{
    struct runtime *s = (void *)e;
    return s && s->magic == MAGIC ? s : 0;
}
static struct runtime *find(void)
{
    struct mxl_mgmt_event *owner;
    if (mxl_mgmt_native_owner_claim(0,event,&owner)) return 0;
    return checked(owner);
}
static struct runtime *find_locked(void)
{
    struct mxl_mgmt_event *owner;
    if (mxl_mgmt_native_owner_find_locked(event,&owner)) return 0;
    return checked(owner);
}
static int try_find(void *unused, void **out)
{
    struct mxl_mgmt_event *owner;
    int result;
    (void)unused; *out = 0;
    result = mxl_mgmt_native_owner_try_find(event,&owner);
    if (!result) *out = checked(owner);
    return result;
}
static int try_lock(void *p) { return mxl_mgmt_native_trylock(&((struct runtime *)p)->mutex); }
static void unlock(void *p) { mxl_mgmt_native_unlock(&((struct runtime *)p)->mutex); }
static uint16_t vid(void *p)
{
    struct runtime *s = p;
    return s->controller.policy.phase == MXL_MGMT_FAULT || s->controller.requests.fault ?
           4095 : s->controller.tx.vid;
}
static int dispatch(void *p, void *iface, void *packet, const unsigned char *header, unsigned n)
{
    return mxl_mgmt_tx_dispatch(&((struct runtime *)p)->controller.tx,iface,packet,header,n);
}
static void observe(void *p, void *iface, const unsigned char *header)
{
    struct runtime *s = p;
    (void)iface; (void)header;
    if (s->tx_count != UINT32_MAX) s->tx_count++;
}
int mxl_mgmt_runtime_tx(void *iface, void *packet, const unsigned char *header)
{
    static const struct mxl_mgmt_egress_gate gate = {
        0,(void *)0x20f64d64,try_find,try_lock,unlock,vid,dispatch,observe,
        mxl_mgmt_native_tx_original,0
    };
    return mxl_mgmt_egress_gate_send(&gate,iface,packet,header,14);
}
void mxl_mgmt_runtime_ip_event(struct mxl_mgmt_event *callback, uint32_t raised, void *iface)
{
    struct runtime *s = find_locked();
    if (s) { mxl_mgmt_native_lock(&s->mutex); s->ip_events++; }
    ((mxl_mgmt_event_handler)0x40024320)(callback,raised,iface);
    if (s) {
        mxl_mgmt_controller_ip_end(&s->controller);
        mxl_mgmt_native_unlock(&s->mutex);
    }
}
int mxl_mgmt_runtime_ip_write(void *device, unsigned char *record)
{
    struct runtime *s = find_locked();
    int result = s ? mxl_mgmt_controller_ip_write(&s->controller,record) : 1;
    /* The original callback holds the registry and owner mutex across this
     * nested call. Never acquire the normal owner mutex a second time. */
    if (result == 1) result = ((int (*)(void *, unsigned char *))0x400a156c)(device,record);
    if (s) { s->ip_writes++; s->ip_result = result; }
    return result;
}
static int send(void *connection, const void *data, unsigned length)
{
    const unsigned char *p = data;
    while (length) {
        int n = ((int (*)(void *,const void *,unsigned))0x400dc1f4)(connection,p,length);
        if (n <= 0 || (unsigned)n > length) return -1;
        p += n; length -= (unsigned)n;
    }
    return 0;
}
static int reject(void *connection, int status)
{
    static const char conflict[] = "HTTP/1.1 409 Conflict\r\nContent-Length: 0\r\n"
        "Cache-Control: no-store\r\nConnection: close\r\n\r\n";
    static const char bad[] = "HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
    static const char method[] = "HTTP/1.1 405 Method Not Allowed\r\nAllow: GET, POST\r\n"
        "Content-Length: 0\r\nConnection: close\r\n\r\n";
    if (status == 409) send(connection,conflict,sizeof(conflict)-1);
    else if (status == 400) send(connection,bad,sizeof(bad)-1);
    else if (status == 405) send(connection,method,sizeof(method)-1);
    else mxl_mgmt_native_http_unavailable(0,connection);
    return status;
}
static int begin(void *connection)
{
    const char **request = ((const char **(*)(void *))0x400db838)(connection);
    struct runtime *s = find();
    int kind, result;
    if (!s || !request) return reject(connection,503);
    kind = mxl_mgmt_request_kind(request[0],request[3]);
    mxl_mgmt_native_lock(&s->mutex);
    if (!mxl_mgmt_controller_http_ready(&s->controller)) result = 503;
    else result = mxl_mgmt_requests_begin(&s->controller.requests,connection,kind,
                    s->controller.tx.vid || s->controller.policy.phase != MXL_MGMT_STABLE);
    if (!result && kind == MXL_MGMT_REQUEST_NATIVE) s->native_begin++;
    mxl_mgmt_native_unlock(&s->mutex);
    if (result) return reject(connection,result);
    return mxl_mgmt_native_http_original(0,connection);
}
static void end(const void *connection, int status)
{
    struct runtime *s = find();
    unsigned before;
    (void)status;
    if (!s) return;
    mxl_mgmt_native_lock(&s->mutex);
    before = s->controller.requests.count;
    mxl_mgmt_requests_end(&s->controller.requests,connection);
    if (before > s->controller.requests.count) s->native_end++;
    s->all_end++;
    mxl_mgmt_native_unlock(&s->mutex);
}
void *mxl_mgmt_runtime_web_start(uintptr_t *callbacks, void *user, const char **options)
{
    /* Constructor call site's original, zeroed callback table. Refuse an ABI
     * mismatch rather than replacing an unknown callback or chaining blindly.
     * Native context stores these at +0x88/+0x8c; end_request(conn,status)
     * is called after request dispatch, including begin-request rejection.
     */
    if (!callbacks || callbacks[0] != 0x4001b504 || callbacks[1]) return 0;
    callbacks[0] = (uintptr_t)begin; callbacks[1] = (uintptr_t)end;
    return ((void *(*)(void *,void *,const char **))0x400de718)(callbacks,user,options);
}
static int schedule(void *p, uint32_t delay)
{
    struct runtime *s = p;
    s->timer_result = mxl_mgmt_native_reschedule(&s->work,delay);
    return s->timer_result;
}
static uint64_t now(void *p) { (void)p; return mxl_mgmt_native_now(); }
#ifndef MXL_MGMT_RUNTIME_FULL
static int no_save(void *p, const unsigned char *data, unsigned length)
{
    (void)p; (void)data; (void)length; return -1;
}
static int trial_load(void *p, unsigned char *data, unsigned capacity)
{
    uint16_t saved;
    int result = mxl_mgmt_native_store_read(p,data,capacity);
    /* This trial must never activate an arbitrary saved management VLAN. */
    if (result == MXL_MGMT_RECORD_BYTES &&
        (mxl_mgmt_record_decode(data,capacity,&saved) || saved)) return -5;
    return result;
}
#else
static int policy_save(void *unused, const unsigned char *data, unsigned length)
{
    uint16_t selected;
    (void)unused;
    if (mxl_mgmt_record_decode(data,length,&selected)) return -1;
    if (selected && mxl_mgmt_native_vlan_persist(selected)) return -1;
    return mxl_mgmt_native_store_write(0,data,length);
}
#endif
static void timer(void *work)
{
    struct runtime *s = (void *)((unsigned char *)work - offsetof(struct runtime,work));
    mxl_mgmt_native_lock(&s->mutex);
    s->timer_fires++;
    mxl_mgmt_controller_tick(&s->controller);
#ifdef MXL_MGMT_RUNTIME_FULL
    if (s->controller.policy.phase==MXL_MGMT_STABLE || s->controller.policy.phase==MXL_MGMT_FAULT) mxl_mgmt_identity_clear(&s->identity);
#endif
    mxl_mgmt_native_unlock(&s->mutex);
}
static void word(volatile unsigned char *p, uint32_t v)
{
    unsigned i;
    for (i=0;i<4;i++) p[i] = (unsigned char)(v >> (8*i));
}
static void wide(volatile unsigned char *p, uint64_t v)
{
    word(p,(uint32_t)v); word(p+4,(uint32_t)(v >> 32));
}
static unsigned get16(const unsigned char *p) { return p[0] | ((unsigned)p[1] << 8); }
static uint32_t get32(const unsigned char *p) { return get16(p) | ((uint32_t)get16(p+2) << 16); }
static int status(void *connection, void *unused)
{
    struct runtime *s = find();
    const char **request = ((const char **(*)(void *))0x400db838)(connection);
    unsigned char body[RESPONSE_BYTES], command[COMMAND_BYTES];
#ifdef MXL_MGMT_RUNTIME_FULL
    unsigned char session[32];
#endif
    volatile unsigned char *wire = body;
    int result=0, post;
    unsigned i, read=0, cmd=0, candidate=0;
    uint32_t ticket=0;
    static const char ok[] = "HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\n"
        #ifdef MXL_MGMT_RUNTIME_FULL
        "Content-Length: 128\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n";
#else
        "Content-Length: 96\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n";
#endif
    (void)unused;
    if (!s || !request || !request[0]) return reject(connection,503);
    post = !((int (*)(const char *,const char *))0x4003508c)(request[0],"POST");
    if (!post && ((int (*)(const char *,const char *))0x4003508c)(request[0],"GET"))
        return reject(connection,405);
    #ifdef MXL_MGMT_RUNTIME_FULL
    if (mxl_mgmt_native_request_session(connection,session)) return reject(connection,503);
    #endif
    if (post) {
        const char *type = ((const char *(*)(void *,const char *))0x400db848)(connection,"Content-Type");
        /* Content length is the audited 64-bit request-info member at +0x4c.
         * Require the non-simple content type before consuming any command. */
        if (!type || ((int (*)(const char *,const char *))0x4003508c)(type,"application/octet-stream") ||
            *(const uint32_t *)((const unsigned char *)request+0x4c) != COMMAND_BYTES ||
            *(const uint32_t *)((const unsigned char *)request+0x50)) return reject(connection,400);
        while (read < sizeof(command)) {
            int n = ((int (*)(void *,void *,unsigned))0x400dc048)
                    (connection,command+read,sizeof(command)-read);
            if (n <= 0 || (unsigned)n > sizeof(command)-read) return reject(connection,400);
            read += (unsigned)n;
        }
        if (command[0]!='M' || command[1]!='V' || command[2]!='C' || command[3]!='C' ||
            command[4]!=API_VERSION || get32(command+COMMAND_BYTES-4)) return reject(connection,400);
        cmd=command[5]; candidate=get16(command+6); ticket=get32(command+8);
#ifdef MXL_MGMT_RUNTIME_FULL
        { unsigned nonzero=0;
          for (i=12;i<28;i++) nonzero|=command[i];
          if (!nonzero || cmd<1 || cmd>3 || candidate>4094 ||
              (cmd==1 && ticket) || (cmd!=1 && !ticket)) return reject(connection,400);
        }
#else
        if ((cmd!=1 && cmd!=2) || candidate>1 ||
            (cmd==1 && ticket) || (cmd==2 && (candidate || !ticket))) return reject(connection,400);
#endif
    }
    for (i=0;i<sizeof(body);i++) wire[i]=0;
    mxl_mgmt_native_lock(&s->mutex);
#ifdef MXL_MGMT_RUNTIME_FULL
    if (post) {
        if (cmd==1) {
            result=mxl_mgmt_controller_propose(&s->controller,(uint16_t)candidate);
            if (!result && mxl_mgmt_identity_set(&s->identity,command+12,session,s->controller.policy.ticket)) {
                mxl_mgmt_controller_cancel(&s->controller,s->controller.policy.ticket);
                result=MXL_MGMT_UNCERTAIN;
            }
        } else if (!mxl_mgmt_identity_matches(&s->identity,command+12,
                      cmd==3?session:s->identity.session,ticket) ||
                   candidate!=(cmd==3?s->controller.policy.active_vid:s->controller.policy.proposed_vid))
            result=MXL_MGMT_STALE;
        else if (cmd==2) result=mxl_mgmt_controller_cancel(&s->controller,ticket);
        else result=mxl_mgmt_controller_confirm(&s->controller,ticket);
        if (s->controller.policy.phase==MXL_MGMT_STABLE || s->controller.policy.phase==MXL_MGMT_FAULT)
            mxl_mgmt_identity_clear(&s->identity);
    }
#else
    if (post) result = cmd==1 ? mxl_mgmt_controller_propose(&s->controller,(uint16_t)candidate) :
                               mxl_mgmt_controller_cancel(&s->controller,ticket);
#endif
    wire[0]='M'; wire[1]='V'; wire[2]='C'; wire[3]='T'; wire[4]=API_VERSION; wire[5]=API_FLAGS;
    wire[6]=s->controller.policy.phase;
    wire[7]=(unsigned char)mxl_mgmt_controller_http_ready(&s->controller);
    word(wire+8,(uint32_t)s->controller.policy.active_vid |
                ((uint32_t)s->controller.policy.committed_vid << 16));
    word(wire+12,(uint32_t)s->controller.policy.proposed_vid | ((uint32_t)s->controller.tx.vid << 16));
    word(wire+16,s->controller.policy.ticket); word(wire+20,(uint32_t)s->controller.policy.last_error);
    wide(wire+24,mxl_mgmt_native_now()); wide(wire+32,s->controller.policy.due_ms);
    word(wire+40,s->controller.requests.count); word(wire+44,s->controller.requests.fault);
    word(wire+48,s->ip_events); word(wire+52,s->ip_writes); word(wire+56,(uint32_t)s->ip_result);
    word(wire+60,(uint32_t)s->timer_result); word(wire+64,s->tx_count); word(wire+68,sizeof(*s));
    word(wire+72,(uint32_t)s->start_result); word(wire+76,s->timer_fires);
    word(wire+80,s->native_begin); word(wire+84,s->native_end); word(wire+88,s->all_end);
    word(wire+92,(uint32_t)result);
#ifdef MXL_MGMT_RUNTIME_FULL
    for (i=0;i<16;i++) wire[96+i]=s->identity.proposal[i];
    word(wire+112,(uint32_t)mxl_mgmt_identity_matches(&s->identity,s->identity.proposal,session,s->controller.policy.ticket));
    word(wire+116,s->controller.store.present);
#endif
    mxl_mgmt_native_unlock(&s->mutex);
    if (!send(connection,ok,sizeof(ok)-1)) send(connection,body,sizeof(body));
    return 200;
}
void mxl_mgmt_runtime_register(void *context)
{
    struct runtime *s, *candidate;
    struct mxl_mgmt_event *owner;
    s = find();
    if (!s) {
        candidate = ((void *(*)(unsigned,unsigned))0x40034f2c)(1,sizeof(*candidate));
        if (candidate) {
            if (mxl_mgmt_native_mutex_init(&candidate->mutex)) {
                ((void (*)(void *))0x40034ec8)(candidate);
            } else {
                candidate->magic=MAGIC;
                candidate->controller.tx.read_row=mxl_mgmt_native_vlan_row;
                candidate->controller.tx.original=mxl_mgmt_native_tx_original;
                candidate->controller.tx.insert=mxl_mgmt_native_tx_insert;
                candidate->controller.tx.management_iface=(void *)0x20f64d64;
                candidate->controller.tx.vid=4095; candidate->controller.tx.index=255;
                candidate->controller.pce.read=mxl_mgmt_native_pce_read;
                candidate->controller.pce.write=mxl_mgmt_native_pce_write;
#ifdef MXL_MGMT_RUNTIME_FULL
                candidate->controller.store.read=mxl_mgmt_native_store_read;
                candidate->controller.store.write=policy_save;
#else
                candidate->controller.store.read=trial_load; candidate->controller.store.write=no_save;
#endif
                candidate->controller.schedule=schedule; candidate->controller.now=now;
                candidate->controller.context=candidate;
                mxl_mgmt_native_work_init(&candidate->work,timer);
                if (mxl_mgmt_native_owner_claim(&candidate->event,event,&owner) || owner!=&candidate->event) {
                    ((void (*)(void *))0x40034ec8)(candidate);
                } else s=candidate;
            }
        }
    }
    if (s) {
        mxl_mgmt_native_lock(&s->mutex);
        if (!s->controller.initialized) s->start_result=mxl_mgmt_controller_start(&s->controller);
        mxl_mgmt_native_unlock(&s->mutex);
    }
    ((void (*)(void *,const char *,int (*)(void *,void *),void *))0x400de5c0)
        (context,"/management-vlan.json",status,0);
}
