; Arranque del Audio_Driver (Z80). Reset en 0x0000, NMI en 0x0066.
; La RAM del Z80 es 0xF800-0xFFFF: ahí van _DATA y la pila (build.sh enlaza con -b _DATA=0xF800).
        .module crt0
        .globl  _main
        .globl  _nmi_handler
        .globl  l__INITIALIZER
        .globl  s__INITIALIZER
        .globl  s__INITIALIZED

        .area   _HEADER (ABS)
        .org    0x0000
        di
        im      1
        ld      sp, #0xFFFF
        jp      init

        .org    0x0038              ; IRQ del YM2610 (no se habilitan; por si acaso)
        ei
        reti

        .org    0x0066
nmi:
        push    af
        push    bc
        push    de
        push    hl
        push    ix
        push    iy
        call    _nmi_handler
        pop     iy
        pop     ix
        pop     hl
        pop     de
        pop     bc
        pop     af
        retn

        ; Orden de las áreas: el código y las constantes en ROM; después la RAM
        .area   _HOME
        .area   _CODE
        .area   _INITIALIZER
        .area   _GSINIT
        .area   _GSFINAL
        .area   _DATA
        .area   _INITIALIZED
        .area   _BSEG
        .area   _BSS
        .area   _HEAP

        .area   _CODE
init:
        ; RAM a cero (también tras CMD_RESET, que salta aquí desde la NMI): las variables sin
        ; inicializador de SDCC no se ponen a cero solas. La pila todavía no guarda nada.
        ld      hl, #0xF800
        ld      de, #0xF801
        ld      bc, #0x07FF
        ld      (hl), #0
        ldir
        call    gsinit
        call    _main
1$:     halt
        jr      1$

        .area   _GSINIT
gsinit:
        ld      bc, #l__INITIALIZER
        ld      a, b
        or      a, c
        jr      z, 2$
        ld      de, #s__INITIALIZED
        ld      hl, #s__INITIALIZER
        ldir
2$:
        .area   _GSFINAL
        ret
