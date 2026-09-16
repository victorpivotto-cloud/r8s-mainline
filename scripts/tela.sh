#!/bin/sh
# Interruptor da tela do r8s.
#
# APAGAR E ACENDER SAO FEITOS PELO CONSOLE, nao pelo /dev/fb0.
#
# MEDIDO em 15/09/2026: escrever no /dev/fb0 NAO chega ao painel. O kernel
# reportava o framebuffer inteiramente zerado enquanto o painel exibia texto.
# O simpledrm mantem um buffer de sombra e so o despeja pelo caminho de dano do
# DRM — que o console usa e o `dd` nao. A versao anterior zerava o fb0 e o
# usuario nao via diferenca nenhuma.
#
# Prova do caminho certo: uma limpeza ANSI no /dev/tty1 apagou o painel na hora,
# e em seguida apareceram duas linhas de `cpufreq: Failed to change cpu
# frequency` — mensagens de kernel pintando sobre o preto. Dai as DUAS metades:
# limpar pelo console E calar o printk.
#
# NAO TOCA NO getty@tty1: parar essa unit congela o PID 1 neste aparelho (duas
# travadas em 15/09, dois chamadores diferentes). O agetty segue rodando; ele
# desenha uma vez ao subir e depois so espera teclado, que este aparelho nao tem.
#
# Painel Super AMOLED: preto e pixel desligado, entao apagar economiza de fato.
set -u
ESTADO=/run/tela-apagada
ULTIMO=/run/tela-ultimo-toque
TTY=/dev/tty1
JANELA=50         # centissegundos; o toque gera 1 evento so (medido), isto e
                  # apenas guarda contra repique eletrico

agora=$(awk '{printf "%d", $1*100}' /proc/uptime)
if [ -f "$ULTIMO" ] && [ $(( agora - $(cat "$ULTIMO") )) -lt "$JANELA" ]; then
    exit 0
fi
echo "$agora" > "$ULTIMO"

apagar() {
    # 1 = so panicos chegam ao console. Sem isto, o proximo erro de cpufreq
    # repinta a tela — foi exatamente o que apareceu no teste.
    sysctl -q -w kernel.printk="1 4 1 7"
    printf '\033[?25l\033[H\033[2J' > "$TTY" 2>/dev/null   # esconde cursor, limpa
    touch "$ESTADO"
    logger -t tela "apagada"
}

acender() {
    sysctl -q -w kernel.printk="4 4 1 7"
    /usr/local/sbin/gerar-boas-vindas.sh 2>/dev/null
    printf '\033[?25h\033[H\033[2J' > "$TTY" 2>/dev/null   # mostra cursor, limpa
    cat /etc/issue                    > "$TTY" 2>/dev/null
    rm -f "$ESTADO"
    logger -t tela "acesa"
}

case "${1:-alterna}" in
    apagar)  apagar ;;
    acender) acender ;;
    alterna) if [ -e "$ESTADO" ]; then acender; else apagar; fi ;;
    *) echo "uso: $0 [alterna|apagar|acender]" >&2; exit 1 ;;
esac
