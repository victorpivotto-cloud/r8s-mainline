#!/bin/sh
# Fornece os 5 V (VBUS) quando o aparelho esta em modo USB host e nada externo
# esta alimentando a porta.
#
# POR QUE EXISTE: o driver de carregador do max77705 no mainline escreve o modo
# como CHG|BUCK e nunca usa a constante MAX77705_OTG_CTRL que o proprio
# cabecalho define. Sem isso o telefone nunca fornece VBUS e um pendrive ou SSD
# nem chega a ser detectado.
#
# ARMADILHA QUE ISTO EVITA (aprendida na marra em 14/09): com o boost LIGADO, o
# carregador enxerga o VBUS que nos mesmos geramos e reporta online=1. Usar
# 'online' como condicao a cada ciclo faz o servico ligar e desligar a cada 3 s,
# e nada consegue enumerar piscando assim.
#
# REGRA: 'online' so vale como medida de fonte EXTERNA quando o boost esta
# desligado. Entao medimos uma vez, e travamos.
I2CBUS=2; ADDR=0x69; REG=0xB7
NORMAL=0x05          # CHG | BUCK
OTG=0x0a             # OTG | BOOST
RESNIFF=60           # s sem nenhum dispositivo antes de reavaliar

modo() { i2cget -f -y $I2CBUS $ADDR $REG 2>/dev/null; }
poe()  { i2cset -f -y $I2CBUS $ADDR $REG "$1" 2>/dev/null; }
gadget() { ls /sys/class/udc/ 2>/dev/null | grep -q .; }
externo() { [ "$(cat /sys/class/power_supply/max77705-charger/online 2>/dev/null)" = "1" ]; }
conectados() { ls /sys/bus/usb/devices/ 2>/dev/null | grep -cE "^[0-9]+-[1-9]"; }

travado=0
vazio=0
logger -t otg-vbus "iniciado"
while :; do
    if gadget; then
        # modo dispositivo: nunca fornecer
        [ "$(modo)" != "$NORMAL" ] && { poe $NORMAL; logger -t otg-vbus "gadget presente -> modo normal"; }
        travado=0; vazio=0
    elif [ $travado = 1 ]; then
        if [ "$(conectados)" -gt 0 ]; then
            vazio=0                       # esta servindo alguem: nao mexer
        else
            vazio=$((vazio+3))
            if [ $vazio -ge $RESNIFF ]; then
                # ninguem apareceu; talvez tenham posto o cabo do PC. Reavaliar.
                poe $NORMAL; travado=0; vazio=0
                logger -t otg-vbus "sem dispositivos ha ${RESNIFF}s: reavaliando"
                sleep 2
            fi
        fi
    else
        # boost desligado: agora 'online' mede fonte EXTERNA de verdade
        if externo; then
            [ "$(modo)" != "$NORMAL" ] && poe $NORMAL
        else
            poe $OTG; travado=1; vazio=0
            logger -t otg-vbus "host sem fonte externa -> fornecendo VBUS (OTG)"
        fi
    fi
    sleep 3
done
