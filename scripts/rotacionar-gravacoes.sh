#!/bin/bash
# Mantem o cartao abaixo de um limite de uso, apagando as gravacoes mais antigas.
#
# POR QUE EXISTE: cartao cheio desgasta desproporcionalmente (o nivelamento de
# escrita fica sem espaco para trabalhar) e, pior, gravacao que falha por disco
# cheio some sem aviso. Melhor apagar o velho de proposito do que perder o novo
# por acidente.
set -u
MONTAGEM=/mnt/cartao
ALVO=${1:-80}          # porcentagem maxima de uso
DIR="$MONTAGEM/cameras"

mountpoint -q "$MONTAGEM" || { logger -t rotacao "cartao nao montado; nada a fazer"; exit 0; }
findmnt -no SOURCE "$MONTAGEM" | grep -q mmcblk || { logger -t rotacao "ATENCAO: $MONTAGEM nao e o cartao; abortando"; exit 1; }
[ -d "$DIR" ] || exit 0

uso() { df --output=pcent "$MONTAGEM" | tail -1 | tr -dc '0-9'; }

U=$(uso)
[ "$U" -le "$ALVO" ] && exit 0
logger -t rotacao "uso ${U}% acima do alvo ${ALVO}%: apagando as gravacoes mais antigas"

apagados=0
# ordena por data de modificacao, mais antigo primeiro
while [ "$(uso)" -gt "$ALVO" ]; do
    alvo_arq=$(find "$DIR" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | head -1 | cut -d' ' -f2-)
    [ -z "$alvo_arq" ] && { logger -t rotacao "nada mais para apagar e ainda em $(uso)%"; break; }
    rm -f -- "$alvo_arq" && apagados=$((apagados+1))
    [ $apagados -gt 5000 ] && { logger -t rotacao "limite de seguranca: 5000 arquivos numa passada"; break; }
done
# remove diretorios de dia que ficaram vazios
find "$DIR" -mindepth 2 -type d -empty -delete 2>/dev/null
logger -t rotacao "apagados $apagados arquivos; uso agora $(uso)%"
