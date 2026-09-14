#!/bin/sh
# Vigia a saude do cartao e AVISA (no journal) quando ele comeca a falhar.
#
# POR QUE EXISTE: o no do mmc usa 'broken-cd' — sem pino de deteccao, o driver
# nao distingue cartao ausente de cartao defeituoso e insiste indefinidamente.
# Em 14/09 foi assim que o aparelho travou inteiro. Num equipamento sozinho em
# outra casa, isso precisa ser visivel antes de virar problema.
#
# Ele nao desmonta nada sozinho: um cartao com falha intermitente e' melhor que
# nenhum, e desmontar no meio de uma gravacao perde mais. Apenas registra, e
# conta, para que um alerta externo possa agir.
LOG_ERROS=/var/log/cartao-erros.log
ultimo=0
while :; do
    n=$(dmesg | grep -ciE 'mmc[0-9].*(error|timeout)|I/O error.*mmcblk|EXT4-fs error.*mmcblk')
    if [ "$n" -gt "$ultimo" ]; then
        logger -t vigia-cartao "ATENCAO: $((n - ultimo)) novos erros de cartao (total $n)"
        {
            echo "=== $(date -Is) — $((n - ultimo)) novos erros (total $n) ==="
            dmesg | grep -iE 'mmc[0-9].*(error|timeout)|I/O error.*mmcblk|EXT4-fs error.*mmcblk' | tail -5
        } >> "$LOG_ERROS"
        ultimo=$n
    fi
    sleep 60
done
