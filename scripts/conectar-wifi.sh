#!/bin/bash
# Acrescenta (ou atualiza) uma rede Wi-Fi na lista do wlp1s0 e conecta.
#
# Uso:  cat <arquivo-com-a-senha> | conectar-wifi.sh 'NOME-DA-REDE' [prioridade]
#       conectar-wifi.sh --listar
#       conectar-wifi.sh --remover 'NOME-DA-REDE'
#
# A senha entra por STDIN de proposito: como argumento apareceria no 'ps'.
# Ela so gera o hash PSK e e descartada — o texto claro nunca e gravado nem
# impresso (a linha '#psk=' que o wpa_passphrase emite e removida).
#
# VARIAS REDES: cada chamada acrescenta um bloco. O wpa_supplicant escolhe
# sozinho — entre redes DIFERENTES manda a 'prioridade' (maior ganha); dentro da
# MESMA rede (varios APs com o mesmo nome) ele pega o de sinal mais forte e faz
# roaming sozinho. Prioridade maior = preferida. Sugestao: rede fixa do local
# com prioridade alta, hotspot do celular com prioridade baixa (socorro).
set -u
IFACE=wlp1s0
CONF=/etc/wpa_supplicant/wpa_supplicant-$IFACE.conf

cabecalho() {
    mkdir -p /etc/wpa_supplicant
    if [ ! -s "$CONF" ]; then
        printf 'ctrl_interface=/run/wpa_supplicant\nupdate_config=1\ncountry=BR\n' > "$CONF"
        chmod 600 "$CONF"
    fi
}

listar() {
    [ -s "$CONF" ] || { echo 'nenhuma rede salva'; return; }
    awk '/^network=\{/{n=1; ssid=""; pri="(padrao)"}
         n && /ssid=/{gsub(/.*ssid="|"/,""); ssid=$0}
         n && /priority=/{gsub(/.*priority=/,""); pri=$0}
         /^\}/{if(n){printf "  %-28s prioridade %s\n", ssid, pri; n=0}}' "$CONF"
}

remover_bloco() {   # $1 = ssid a remover
    [ -s "$CONF" ] || return 0
    awk -v alvo="$1" '
        /^network=\{/ { bloco=$0"\n"; dentro=1; casou=0; next }
        dentro {
            bloco=bloco $0"\n"
            if ($0 ~ "ssid=\"" alvo "\"") casou=1
            if ($0 ~ /^\}/) { if (!casou) printf "%s", bloco; dentro=0 }
            next
        }
        { print }
    ' "$CONF" > "$CONF.novo" && mv "$CONF.novo" "$CONF"
    chmod 600 "$CONF"
}

case "${1:-}" in
  --listar)  cabecalho; echo "redes salvas em $CONF:"; listar; exit 0 ;;
  --remover) cabecalho; remover_bloco "${2:?informe o SSID}"
             systemctl reload-or-restart "wpa_supplicant@$IFACE" 2>/dev/null
             echo "removida: $2"; listar; exit 0 ;;
esac

SSID="${1:?informe o SSID}"
PRIO="${2:-10}"

SENHA="$(cat)"
SENHA="${SENHA%%$'\n'*}"
[ ${#SENHA} -ge 8 ] || { echo 'ERRO: senha WPA precisa de 8+ caracteres'; exit 1; }

cabecalho
remover_bloco "$SSID"          # atualiza em vez de duplicar
{
    wpa_passphrase "$SSID" "$SENHA" | grep -v '#psk=' | sed "/^}/i\\\tpriority=$PRIO"
} >> "$CONF"
unset SENHA
chmod 600 "$CONF"

# O .network PRECISA ser legivel pelo usuario do networkd (nao pode ser 600 —
# foi esse o erro de 14/09: 'Network File: n/a' e link 'unmanaged').
cat > /etc/systemd/network/20-wlan.network <<NET
[Match]
Name=$IFACE

[Network]
DHCP=yes
IPv6AcceptRA=yes

[DHCPv4]
RouteMetric=200
NET
chmod 644 /etc/systemd/network/20-wlan.network

systemctl daemon-reload
systemctl enable "wpa_supplicant@$IFACE.service" >/dev/null 2>&1
systemctl restart "wpa_supplicant@$IFACE.service"
systemctl restart systemd-networkd
echo "rede '$SSID' salva com prioridade $PRIO. Aguardando IP..."
for i in $(seq 30); do
    IP=$(ip -4 -br addr show "$IFACE" | awk '{print $3}')
    [ -n "$IP" ] && { echo "CONECTADO (IPv4): $IP"; listar; exit 0; }
    sleep 2
done
echo 'sem IPv4 em 60 s. Estado:'
wpa_cli -i "$IFACE" status 2>/dev/null | grep -E 'wpa_state|ssid'
networkctl status "$IFACE" --no-pager 2>&1 | grep -E 'Network File|State'
exit 1
