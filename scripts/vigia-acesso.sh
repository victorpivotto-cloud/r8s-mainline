#!/bin/sh
# Vigia de acesso — rede de seguranca para o teste de USB em modo HOST.
#
# Em modo host o gadget USB some, e com ele a unica via de acesso do PC. Se eu
# nao conseguir entrar por outro caminho (Wi-Fi) para desarmar isto, o aparelho
# reinicia sozinho e cai no fastboot do lk3rd, de onde da para mandar a imagem
# boa de volta. Sem precisar de ninguem apertar botao.
#
# Nao faz nada em boot normal: se o gadget existe, sai na hora.
PRAZO=600
DESARMA=/run/vigia-desarmado

if ls /sys/class/udc/ 2>/dev/null | grep -q .; then
    logger -t vigia-acesso 'gadget USB presente: boot normal, vigia nao arma'
    exit 0
fi

logger -t vigia-acesso "SEM gadget USB (modo host). Reinicio em ${PRAZO}s salvo desarme em $DESARMA"
i=0
while [ $i -lt $PRAZO ]; do
    [ -e "$DESARMA" ] && { logger -t vigia-acesso 'desarmado'; exit 0; }
    sleep 5
    i=$((i+5))
done
logger -t vigia-acesso 'prazo esgotado sem desarme: reiniciando'
systemctl reboot
