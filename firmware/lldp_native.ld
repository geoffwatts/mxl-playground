ENTRY(mxl_lldp_register)
SECTIONS {
 . = MXL_LLDP_CODE;
 .text : { *(.text .text.*) }
 . = ALIGN(4);
 .rodata : { *(.rodata .rodata.*) }
 .data : { *(.data .data.*) }
 .bss : { *(.bss .bss.* COMMON) }
 /DISCARD/ : { *(.comment .note* .eh_frame .ARC.attributes) }
 ASSERT(SIZEOF(.data)==0 && SIZEOF(.bss)==0,"No implicit writable LLDP storage")
 ASSERT(.<=MXL_LLDP_END,"LLDP exceeds its code window")
}
