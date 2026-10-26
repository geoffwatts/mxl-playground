/* SPDX-License-Identifier: MIT */
#include "console_ring.h"
void mxl_console_output(struct mxl_console_ring *s,const unsigned char *data,unsigned n)
{
    unsigned i;
    for(i=0;i<n;i++) {
        s->output[s->end++ % MXL_CONSOLE_OUTPUT]=data[i];
        if((uint32_t)(s->end-s->begin)>MXL_CONSOLE_OUTPUT)s->begin++;
    }
}
unsigned mxl_console_snapshot(const struct mxl_console_ring *s,uint32_t *cursor,
                              unsigned char *data,unsigned capacity,int *lost)
{
    unsigned n,i;
    *lost=(uint32_t)(s->end-*cursor)>(uint32_t)(s->end-s->begin);
    if(*lost)*cursor=s->begin;
    n=s->end-*cursor;if(n>capacity)n=capacity;
    for(i=0;i<n;i++)data[i]=s->output[(*cursor+i)%MXL_CONSOLE_OUTPUT];
    *cursor+=n;return n;
}
unsigned mxl_console_input_free(const struct mxl_console_ring *s)
{return MXL_CONSOLE_INPUT-(uint32_t)(s->input_write-s->input_read);}
int mxl_console_enqueue(struct mxl_console_ring *s,uint32_t sequence,const unsigned char *data,unsigned n)
{
    unsigned i;
    if(!n || n>256 || sequence!=s->sequence+1 || n>mxl_console_input_free(s))return -1;
    for(i=0;i<n;i++)s->input[s->input_write++ % MXL_CONSOLE_INPUT]=data[i];
    s->sequence=sequence;return 0;
}
unsigned mxl_console_dequeue(struct mxl_console_ring *s,unsigned char *data,unsigned capacity)
{
    unsigned i,n=s->input_write-s->input_read;if(n>capacity)n=capacity;
    for(i=0;i<n;i++)data[i]=s->input[s->input_read++ % MXL_CONSOLE_INPUT];
    return n;
}
