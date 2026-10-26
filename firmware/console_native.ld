ENTRY(mxl_console_register)
SECTIONS {
    . = 0x402b0020;
    .text : { *(.text .text.*) }
    . = ALIGN(4);
    .rodata : { *(.rodata .rodata.*) }
    .data : { *(.data .data.*) }
    .bss : { *(.bss .bss.* COMMON) }
    /DISCARD/ : { *(.comment .note* .eh_frame .ARC.attributes) }
    ASSERT(SIZEOF(.data)==0 && SIZEOF(.bss)==0,"No writable static console storage")
    ASSERT(.<=0x402b4000,"Console code exceeds reserved window")
}
