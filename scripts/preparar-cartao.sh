#!/bin/bash
# Prepara um microSD novo para gravar as cameras.
#
# Faz, nesta ordem: confere que o alvo e MESMO o cartao (nunca o UFS interno),
# mede a capacidade real com marcadores (pega falsificado), particiona, formata
# com ajustes para video, e rotula.
#
# Uso:  preparar-cartao.sh [/dev/mmcblk0] [--pular-teste]
set -u
DEV=${1:-/dev/mmcblk0}
PULAR=${2:-}
ROTULO=R8S-CAMERAS
BASE=$(basename "$DEV")

# --- guarda 1: e um cartao MMC/SD, nao o armazenamento interno? -------------
case "$BASE" in
    mmcblk*) ;;
    *) echo "RECUSADO: '$DEV' nao e um dispositivo mmcblk. O UFS interno e sda —"
       echo "           formata-lo apagaria o sistema."; exit 1 ;;
esac
if ! readlink -f "/sys/block/$BASE/device" 2>/dev/null | grep -q mmc; then
    echo "RECUSADO: $DEV nao esta atras de um controlador MMC."; exit 1
fi
if findmnt -no SOURCE / | grep -q "$BASE"; then
    echo "RECUSADO: $DEV e a raiz do sistema."; exit 1
fi

ALEGADO=$(awk '{printf "%.1f", $1*512/1e9}' "/sys/block/$BASE/size")
echo "alvo: $DEV — alega ${ALEGADO} GB"
echo

# --- mede a capacidade real -------------------------------------------------
REAL_MIB=0
if [ "$PULAR" != "--pular-teste" ]; then
    echo "--- medindo capacidade real (marcadores; pega cartao falsificado) ---"
    BS=4096
    TOTAL_MIB=$(( $(cat /sys/block/$BASE/size) / 2048 ))
    ini=0; fim=$TOTAL_MIB
    # busca binaria: ~10 escritas de 4 KiB, nao varredura do disco inteiro
    while [ $(( fim - ini )) -gt 64 ]; do
        meio=$(( (ini + fim) / 2 ))
        marca="PROBE-$meio"
        seek=$(( meio * 1024 * 1024 / BS ))
        if printf '%-*s' $BS "$marca" | timeout 30 dd of="$DEV" bs=$BS seek=$seek count=1 \
              oflag=direct conv=fsync status=none 2>/dev/null &&
           [ "$(timeout 30 dd if="$DEV" bs=$BS skip=$seek count=1 iflag=direct status=none 2>/dev/null \
                | tr -d '\0' | tr -d ' ')" = "$marca" ]; then
            ini=$meio
        else
            fim=$meio
        fi
        printf '.'
    done
    echo
    REAL_MIB=$ini
    echo "  capacidade real: ~$(( REAL_MIB / 1024 )) GB (${REAL_MIB} MiB)"
    ALEGADO_MIB=$(( $(cat /sys/block/$BASE/size) / 2048 ))
    if [ $REAL_MIB -lt $(( ALEGADO_MIB * 90 / 100 )) ]; then
        echo
        echo "  *** ATENCAO: FALSIFICADO. Alega ${ALEGADO_MIB} MiB, entrega ${REAL_MIB} MiB. ***"
        echo "  *** Vou particionar so a parte real, mas NAO use este cartao para valer. ***"
    fi
else
    REAL_MIB=$(( $(cat /sys/block/$BASE/size) / 2048 ))
    echo "  teste pulado; assumindo ${REAL_MIB} MiB"
fi
echo

# deixa 8% de folga: cartao cheio desgasta desproporcionalmente e o
# nivelamento de escrita precisa de espaco livre para trabalhar
USAR_MIB=$(( REAL_MIB * 92 / 100 - 4 ))
[ $USAR_MIB -lt 64 ] && { echo "capacidade util pequena demais ($USAR_MIB MiB)"; exit 1; }

echo "--- particionando: ${USAR_MIB} MiB (8% de folga para nivelamento) ---"
umount "${DEV}p1" 2>/dev/null
timeout 30 dd if=/dev/zero of="$DEV" bs=1M count=4 oflag=direct status=none
printf 'label: gpt\nstart=4MiB, size=%dMiB, type=linux\n' "$USAR_MIB" | timeout 60 sfdisk "$DEV" >/dev/null
sleep 2; partprobe "$DEV" 2>/dev/null; sleep 3
[ -b "${DEV}p1" ] || { echo "particao nao apareceu"; exit 1; }

echo "--- formatando (ajustado para video) ---"
#  -i 1048576 : 1 inode por MiB. Video sao poucos arquivos grandes; menos
#               metadados = menos escrita = mais vida ao cartao.
#  -m 1       : 1% reservado em vez de 5%; a rotacao e' quem cuida do espaco.
#  -O ^resize_inode : nao vamos redimensionar; poupa metadados.
timeout 300 mkfs.ext4 -q -F -L "$ROTULO" -i 1048576 -m 1 -O ^resize_inode "${DEV}p1"
echo "  rotulo: $ROTULO"

mkdir -p /mnt/cartao
mount "${DEV}p1" /mnt/cartao || { echo "falhou ao montar"; exit 1; }
findmnt -no SOURCE /mnt/cartao | grep -q "$BASE" || { echo "montou origem errada"; exit 1; }
mkdir -p /mnt/cartao/cameras /mnt/cartao/.enviado
chmod 755 /mnt/cartao/cameras
echo
echo "PRONTO:"
df -h /mnt/cartao | tail -1
echo "  estrutura: /mnt/cartao/cameras/<nome-da-camera>/AAAA-MM-DD/"
