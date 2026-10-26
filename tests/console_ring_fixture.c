#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "console_ring.h"
int main(void)
{
    struct mxl_console_ring s={0};unsigned char b[8192],out[4096];uint32_t at;int lost;unsigned i;
    for(i=0;i<sizeof(b);i++)b[i]=(unsigned char)i;
    /* A slow poller loses only the overwritten prefix; subsequent polls
     * continue exactly once, including across the 32-bit counter wrap. */
    s.begin=s.end=UINT32_MAX-100;
    at=s.begin;mxl_console_output(&s,b,5000);
    assert(mxl_console_snapshot(&s,&at,out,4096,&lost)==4096 && lost);
    assert(!memcmp(out,b+904,4096));
    assert(mxl_console_snapshot(&s,&at,out,4096,&lost)==0 && !lost);
    assert(mxl_console_enqueue(&s,1,b,256)==0);
    assert(mxl_console_enqueue(&s,1,b,256)==-1); /* Duplicate request. */
    assert(mxl_console_enqueue(&s,3,b,256)==-1); /* Lost sequence. */
    assert(mxl_console_enqueue(&s,2,b+256,256)==0);
    assert(mxl_console_enqueue(&s,3,b,1)==-1); /* Full: no partial input. */
    assert(s.sequence==2 && mxl_console_input_free(&s)==0);
    assert(mxl_console_dequeue(&s,out,300)==300 && !memcmp(out,b,300));
    assert(mxl_console_enqueue(&s,3,b+512,256)==0);
    assert(mxl_console_dequeue(&s,out,4096)==468 && !memcmp(out,b+300,468));
    assert(mxl_console_input_free(&s)==512);
    return 0;
}
