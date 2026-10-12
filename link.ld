/* Oblique Strategies mod: one flat image loaded by its own LDR block. */
ENTRY(_obl_key)
SECTIONS
{
  . = 0x01E40000;
  .image : {
    *(.text .text.*)
    *(.rodata .rodata.* .constdata .constdata.*)
    *(.data .data.*)
    *(.bss .bss.* COMMON)
    . = ALIGN(4);
  }
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
