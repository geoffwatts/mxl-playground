/* SPDX-License-Identifier: MIT */
#ifndef MXL_CONSOLE_RING_H
#define MXL_CONSOLE_RING_H
#include <stdint.h>
#define MXL_CONSOLE_OUTPUT 4096u
#define MXL_CONSOLE_INPUT 512u
struct mxl_console_ring {
    uint32_t begin, end, input_read, input_write, sequence;
    unsigned char output[MXL_CONSOLE_OUTPUT], input[MXL_CONSOLE_INPUT];
};
void mxl_console_output(struct mxl_console_ring *,const unsigned char *,unsigned);
unsigned mxl_console_snapshot(const struct mxl_console_ring *,uint32_t *,unsigned char *,unsigned,int *);
unsigned mxl_console_input_free(const struct mxl_console_ring *);
int mxl_console_enqueue(struct mxl_console_ring *,uint32_t,const unsigned char *,unsigned);
unsigned mxl_console_dequeue(struct mxl_console_ring *,unsigned char *,unsigned);
#endif
