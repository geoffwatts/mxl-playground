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
    ASSERT(SIZEOF(.data) == 0, "Probe must have no writable static data")
    ASSERT(SIZEOF(.bss) == 0, "Probe must have no unallocated BSS")
    ASSERT(. <= 0x402c5000, "Diagnostic probe exceeds reserved padding")
}
