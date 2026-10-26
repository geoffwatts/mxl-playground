/* SPDX-License-Identifier: MIT
 * Exact V2 UART transport tee/input queue. Commands run on the real shell
 * thread, never an HTTP worker. UART output and physical input are retained.
 */
#include <stdint.h>
#include <stddef.h>
#include "console_ring.h"
typedef int (*io_call)(void *,unsigned char *,unsigned,unsigned *);
struct console {
    uintptr_t api[6];
    uint32_t magic;
    struct mxl_console_ring ring;
    unsigned char session[32], nonce[16];
    int attached;
};
#define MAGIC UINT32_C(0x5443584d)
_Static_assert(sizeof(void *)==4,"ARC32 only");
static unsigned lock(void) { unsigned key;__asm__ volatile("clri %0":"=r"(key)::"memory");return key; }
static void unlock(unsigned key) { __asm__ volatile("seti %0"::"r"(key):"memory"); }
static struct console *state(void *transport)
{return (struct console *)*(uintptr_t *)transport;}
static int read_uart(void *transport,unsigned char *data,unsigned n,unsigned *count)
{
    struct console *s=state(transport);unsigned key=lock();
    *count=mxl_console_dequeue(&s->ring,data,n);unlock(key);
    if(*count)return 0;
    return ((io_call)0x4002b574)(transport,data,n,count);
}
static int write_uart(void *transport,unsigned char *data,unsigned n,unsigned *count)
{
    struct console *s=state(transport);unsigned key;
    int result=((io_call)0x4002b5d0)(transport,data,n,count);
    /* Mirror only bytes actually consumed by the existing UART transport. */
    if(!result && *count && *count<=n) {
        key=lock();mxl_console_output(&s->ring,data,*count);unlock(key);
    }
    return result;
}
static int send(void *c,const void *data,unsigned n)
{
    const unsigned char *p=data;
    while(n){int k=((int(*)(void*,const void*,unsigned))0x400dc1f4)(c,p,n);
        if(k<=0 || (unsigned)k>n)return -1;
        p+=k;n-=(unsigned)k;}
    return 0;
}
static int fail(void *c,int code)
{
    ((int(*)(void*,int,const char*,...))0x400dc70c)(c,code,"Console request rejected");return code;
}
static int session(void *c,unsigned char *out)
{
    char token[33];int n;unsigned i;
    const char *h=((const char*(*)(void*,const char*))0x400db848)(c,"Cookie");
    if(!h)return -1;
    n=((int(*)(const char*,const char*,char*,unsigned))0x400dc970)(h,"session",token,sizeof(token));
    if(n!=32 || token[32])return -1;
    for(i=0;i<32;i++){
        unsigned char x=(unsigned char)token[i];
        if(!((x>='0'&&x<='9')||(x>='a'&&x<='f')||(x>='A'&&x<='F')))return -1;
        out[i]=x;
    }
    return 0;
}
static uint32_t word(const unsigned char *p)
{return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static void put(unsigned char *p,uint32_t v)
{unsigned i;for(i=0;i<4;i++)p[i]=(unsigned char)(v>>(i*8));}
static int handle(void *connection,void *parameter)
{
    struct console *s=parameter;
    const char **request=((const char**(*)(void*))0x400db838)(connection);
    unsigned char body[288],owner[32],*response;
    const char *length;unsigned total=0,n=0,got=0,i,key,difference=0,nonzero=0,available;
    uint32_t cursor,ack,end;int count,code=0,lost=0,wake=0;
    static const char ok[]="HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n";
    if(!s || s->magic!=MAGIC)return fail(connection,503);
    if(!request || !request[0] || ((int(*)(const char*,const char*))0x4003508c)(request[0],"POST"))return fail(connection,405);
    if(session(connection,owner))return fail(connection,401);
    length=((const char*(*)(void*,const char*))0x400db848)(connection,"Content-Length");
    if(!length || !*length)return fail(connection,400);
    for(i=0;length[i];i++){if(i>3 || length[i]<'0'||length[i]>'9')return fail(connection,400);unsigned scaled=total<<3;__asm__ volatile("":"+r"(scaled));total=scaled+(total<<1)+(unsigned)(length[i]-'0');}
    if(total<32 || total>sizeof(body))return fail(connection,400);
    while(got<total){count=((int(*)(void*,void*,unsigned))0x400dc048)(connection,body+got,total-got);
        if(count<=0 || (unsigned)count>total-got)return fail(connection,400);
        got+=(unsigned)count;}
    n=(unsigned)body[6]|(unsigned)body[7]<<8;
    if(body[0]!='M'||body[1]!='C'||body[2]!='T'||body[3]!='C'||body[4]!=1||body[5]<1||body[5]>4||n!=total-32||(body[5]!=2&&n))return fail(connection,400);
    for(i=0;i<16;i++)nonzero|=body[8+i];
    if(!nonzero)return fail(connection,400);
    response=((void*(*)(unsigned,unsigned))0x40034f2c)(1,1048);
    if(!response)return fail(connection,503);
    cursor=word(body+24);key=lock();
    if(body[5]==1){
        for(i=0;i<32;i++)s->session[i]=owner[i];
        for(i=0;i<16;i++)s->nonce[i]=body[8+i];
        s->attached=1;s->ring.sequence=0;s->ring.input_read=s->ring.input_write;cursor=s->ring.begin;
    }else{
        for(i=0;i<32;i++)difference|=owner[i]^s->session[i];
        for(i=0;i<16;i++)difference|=body[8+i]^s->nonce[i];
        if(!s->attached||difference)code=409;
        else if(body[5]==2){if(mxl_console_enqueue(&s->ring,word(body+28),body+32,n))code=409;else wake=1;}
        else if(body[5]==4){s->attached=0;s->ring.input_read=s->ring.input_write;}
    }
    n=code?0:mxl_console_snapshot(&s->ring,&cursor,response+24,1024,&lost);
    ack=s->ring.sequence;end=s->ring.end;available=mxl_console_input_free(&s->ring);unlock(key);
    if(code){((void(*)(void*))0x40034ec8)(response);return fail(connection,code);}
    if(wake){
        /* Original UART init stores event callback/user at state +4/+8.
         * Event 0 is RX-ready; the original shell thread consumes our queue. */
        uintptr_t *uart=(uintptr_t *)0x20f11bc0;
        ((void(*)(int,void*))uart[1])(0,(void*)uart[2]);
    }
    response[0]='M';response[1]='C';response[2]='O';response[3]='T';response[4]=1;response[5]=(unsigned char)lost;
    response[6]=(unsigned char)available;response[7]=(unsigned char)(available>>8);put(response+8,cursor);
    response[12]=(unsigned char)n;response[13]=(unsigned char)(n>>8);put(response+16,ack);put(response+20,end);
    if(!send(connection,ok,sizeof(ok)-1))send(connection,response,24+n);
    ((void(*)(void*))0x40034ec8)(response);return 200;
}
void mxl_console_register(void *context)
{
    uintptr_t *transport=(uintptr_t *)0x20f5eef0;struct console *s=0;unsigned i,key;
    if(*transport==0x402006f8){
        s=((void*(*)(unsigned,unsigned))0x40034f2c)(1,sizeof(*s));
        if(s){
            for(i=0;i<6;i++)s->api[i]=((const uintptr_t *)0x402006f8)[i];
            s->api[3]=(uintptr_t)write_uart;s->api[4]=(uintptr_t)read_uart;s->magic=MAGIC;
            key=lock();*transport=(uintptr_t)s;unlock(key);
        }
    }else{
        struct console *candidate=(struct console *)*transport;
        if(candidate->api[3]==(uintptr_t)write_uart&&candidate->api[4]==(uintptr_t)read_uart&&candidate->magic==MAGIC)s=candidate;
    }
    ((void(*)(void*,const char*,int(*)(void*,void*),void*))0x400de5c0)(context,"/console.json",handle,s);
}
