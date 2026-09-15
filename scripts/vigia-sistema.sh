#!/bin/sh
# Watchdog de software do r8s.
#
# POR QUE EXISTE: em 15/09/2026 o aparelho ficou 2h20 respondendo ping, DNS e
# HTTP e IMPOSSIVEL de administrar — o PID 1 congelado por um `stop` no
# getty@tty1. Nenhum monitoramento que pergunte "responde?" teria acusado nada.
#
# O QUE ELE TESTA: se o systemd responde no D-Bus. E' exatamente o que falhou.
# `systemctl is-system-running` devolve nao-zero em "degraded" e "starting" —
# isso E' resposta. So conta como falha o TIMEOUT (codigo 124 do `timeout`).
#
# COMO ELE AGE: `poweroff`, nunca `reboot`. Neste aparelho falta o no
# `reboot-mode` no DT e o reinicio cai no DOWNLOAD MODE, exigindo intervencao
# fisica — o oposto de recuperacao. Desligado, ele RELIGA SOZINHO ao receber
# energia de um carregador de parede (medido em 15/09).
#
# POR QUE SYSRQ E NAO poweroff: `/sbin/poweroff` e' symlink para o systemctl,
# ou seja, inutil justamente quando o systemd esta congelado. O sysrq e' kernel
# puro: `s` sincroniza, `u` remonta somente-leitura, `o` desliga.
# (kernel.sysrq=438 ja inclui os bits 16, 32 e 128 necessarios.)
set -u

INTERVALO=${INTERVALO:-30}   # s entre sondagens
LIMITE=${LIMITE:-5}          # falhas seguidas antes de agir
ESPERA_BOOT=180              # nao age nos primeiros 3 min de uptime
REGISTRO=/var/log/vigia-sistema.log
TESTE=0
[ "${1:-}" = "--teste" ] && TESTE=1

anota() {
    logger -t vigia-sistema "$1"
    printf '%s  %s\n' "$(date +%Y-%m-%dT%H:%M:%S)" "$1" >> "$REGISTRO" 2>/dev/null
}

sonda() {
    if [ "$TESTE" = 1 ]; then timeout 2 sleep 30 >/dev/null 2>&1; return $?; fi
    timeout 10 systemctl is-system-running >/dev/null 2>&1
}

desligar() {
    anota "SEM RESPOSTA do systemd em $LIMITE sondagens: desligando por sysrq"
    if [ "$TESTE" = 1 ]; then anota "MODO TESTE: nao desliguei de verdade"; return 0; fi
    sync
    printf s > /proc/sysrq-trigger 2>/dev/null; sleep 2   # sincroniza
    printf u > /proc/sysrq-trigger 2>/dev/null; sleep 2   # remonta somente-leitura
    printf o > /proc/sysrq-trigger 2>/dev/null            # desliga
    sleep 10
    # se o sysrq nao resolveu, tenta a syscall direta do busybox
    /usr/local/sbin/busybox poweroff -f
}

anota "iniciado (intervalo ${INTERVALO}s, limite ${LIMITE}, teste=${TESTE})"
falhas=0
while :; do
    sonda
    rc=$?
    if [ "$rc" -eq 124 ]; then
        falhas=$((falhas + 1))
        anota "systemd nao respondeu ($falhas/$LIMITE)"
        up=$(cut -d. -f1 /proc/uptime)
        if [ "$falhas" -ge "$LIMITE" ]; then
            if [ "$up" -lt "$ESPERA_BOOT" ]; then
                anota "uptime ${up}s < ${ESPERA_BOOT}s: ainda subindo, nao vou agir"
                falhas=0
            else
                desligar
                exit 0
            fi
        fi
    else
        [ "$falhas" -gt 0 ] && anota "systemd voltou a responder (havia $falhas falha(s))"
        falhas=0
    fi
    sleep "$INTERVALO"
done
