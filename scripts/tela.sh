#!/bin/sh
# Interruptor da tela do r8s.
#
# APAGAR = trocar para um terminal virtual VAZIO e pintar o framebuffer de
# preto. O VT 2 nao tem getty, entao nao ha nada para redesenhar por cima —
# que era o defeito da versao que so pintava: o console do VT 1 repintava em
# seguida e a tela voltava sozinha.
#
# NAO TOCA NO getty@tty1. Parar essa unit CONGELA O PID 1 neste aparelho:
# aconteceu duas vezes em 15/09/2026, uma de dentro de um ExecStart e outra de
# um filho do triggerhappy, as duas com o systemd emudecendo na linha seguinte
# a "Stopped getty@tty1.service". O console fica sobre o simpledrm, que nem
# implementa fb_blank (/sys/class/graphics/fb0/blank vem VAZIO); soltar a TTY
# trava o caminho de VT/fbcon. O aparelho ficava respondendo ping, DNS e HTTP e
# impossivel de administrar ou desligar por software — so saia com Power+VolDown.
#
# O painel e Super AMOLED: pixel preto e pixel desligado, entao apagar assim
# economiza energia de verdade, e nao so esconde.
set -u
ESTADO=/run/tela-apagada
ULTIMO=/run/tela-ultimo-toque
FB=/dev/fb0
VT_TEXTO=1        # onde mora o getty e onde escrevemos
VT_VAZIO=2        # sem getty: nada redesenha

# Anti-repique: o gpio-keys pode entregar mais de um evento por toque.
agora=$(cut -d. -f1 /proc/uptime)
if [ -f "$ULTIMO" ] && [ $(( agora - $(cat "$ULTIMO") )) -lt 1 ]; then
    exit 0
fi
echo "$agora" > "$ULTIMO"

apagar() {
    sysctl -q -w kernel.printk="1 4 1 7"
    chvt "$VT_VAZIO" 2>/dev/null
    dd if=/dev/zero of="$FB" bs=4320 count=2400 2>/dev/null
    touch "$ESTADO"
    logger -t tela "apagada"
}

acender() {
    sysctl -q -w kernel.printk="4 4 1 7"
    /usr/local/sbin/gerar-boas-vindas.sh 2>/dev/null
    chvt "$VT_TEXTO" 2>/dev/null
    # limpa o que o getty deixou e escreve o texto novo
    printf '\033[H\033[2J' > "/dev/tty$VT_TEXTO" 2>/dev/null
    cat /etc/issue    > "/dev/tty$VT_TEXTO" 2>/dev/null
    rm -f "$ESTADO"
    logger -t tela "acesa"
}

case "${1:-alterna}" in
    apagar)  apagar ;;
    acender) acender ;;
    alterna) if [ -e "$ESTADO" ]; then acender; else apagar; fi ;;
    *) echo "uso: $0 [alterna|apagar|acender]" >&2; exit 1 ;;
esac
