/* Exact-build trial extension. No writable global memory is available here. */
ENTRY(mxl_mgmt_probe_register)
SECTIONS
{
    . = 0x402c3020;
    .text : { *(.text .text.*) }
    . = ALIGN(4);
    .rodata : { *(.rodata .rodata.*) }
    .data : { *(.data .data.*) }
    .bss : { *(.bss .bss.* COMMON) }
    /DISCARD/ : { *(.comment .note* .eh_frame .ARC.attributes) }
    ASSERT(SIZEOF(.data) == 0, "Runtime must not require writable static data")
    ASSERT(SIZEOF(.bss) == 0, "Runtime must not require unallocated BSS")
    ASSERT(. <= 0x402c6ff0, "Runtime overlaps its bounded entry table")
}
