# Debian 13 rodando no Galaxy S20 FE — 2026-09-13

Fecha o dia: do aparelho bloqueado por Family Link às 14h ao Debian com SSH,
DVFS e 220 GB às 21h40.

## Estado

```
Debian GNU/Linux 13 (trixie)          kernel 6.12.0-rc5-next-20241104-...-dirty
/dev/sda32  223G  1% usado            8 nucleos, DVFS ativo
acesso: ssh -i ~/.ssh/id_ed25519_r8s root@172.16.42.1
```

| | |
|---|---|
| Distro | **Debian 13 trixie** (stable atual; o 12 e oldstable, a caminho do LTS) |
| Raiz | `sda32` (userdata), ext4, 227 GiB |
| CPU | 8 nucleos, DVFS nos 3 clusters: A55 442 MHz–2,0 GHz · A76 507 MHz–2,6 GHz · M5 546 MHz–2,73 GHz, `schedutil` |
| Rede | USB RNDIS, **MAC fixo** `02:42:ac:11:00:01`, IP 172.16.42.1 |
| Acesso | SSH so por chave; senha de root BLOQUEADA; telnet removido |
| Modulos | em `/usr/lib/modules/<versao>`: ath11k, wireguard, veth, bridge, overlay, nft_*, r8152 |

## Como se chega nele

```bash
ssh -i ~/.ssh/id_ed25519_r8s root@172.16.42.1
# se o SSH nao responder, o IP do lado do PC pode ter caido:
NEW=$(ip -br link | awk '/^enx/ && /LOWER_UP/ {print $1}' | head -1)
nmcli con up "r8s-$NEW" || nmcli con add type ethernet ifname "$NEW" con-name "r8s-$NEW" ip4 172.16.42.2/24
```

## Ainda depende do PC para ligar

`fastboot boot` roda da RAM. O `BOOT` tem o **lk3rd**, nao o nosso kernel — de
proposito: manter o lk3rd e o que permite trocar de kernel com um comando, sem
gravar nada e sem precisar de ninguem segurando botao. **Gravar o kernel no
BOOT e o passo final**, quando a configuracao estiver estavel; ai o aparelho
liga sozinho, mas cada troca de kernel passa a exigir Download Mode + heimdall.

Reiniciar remotamente FUNCIONA e cai no fastboot em ~30 s:
`ssh ... systemctl reboot` -> `fastboot boot <img>`.

## Erros meus que custaram tempo, para nao repetir

1. **`tar` com `lib/` extraido em `/` quebrou o Debian inteiro.** Em Debian de
   /usr unificado `/lib` e SYMLINK para `usr/lib`; o tar trocou por diretorio e
   o loader dinamico sumiu — nem `uname` executava. O README do z3s avisa
   ("Never extract a rootfs tar archive at /") e eu li e fiz mesmo assim.
   **Modulo instala com `INSTALL_MOD_PATH` para `/usr/lib/modules`.**
2. **Script que imprime "CONCLUIDO" sem verificar mente.** O instalador v3
   declarou sucesso sobre um disco VAZIO: o `tar` do busybox nao aceita
   `--exclude=` e, dentro de um pipe, o erro nao aborta. A v4 verifica arquivo
   a arquivo antes de declarar.
3. **`[ -e ]` da falso em symlink de chroot.** O `systemctl enable` tinha
   funcionado; meu teste e que estava errado. Usar `[ -e ] || [ -L ]`.
4. **Relogio errado reprova o repositorio.** Sem RTC o aparelho acorda em abril
   e o apt recusa assinaturas com "Not live until ...". Acertar a hora ANTES do
   apt.
5. **`wget` nao existe no Debian minimo** (tem `curl`); no busybox do initramfs
   e o contrario.
6. **`pkill -f <padrao>` mata o proprio shell** quando o padrao aparece na
   propria linha de comando. Aconteceu 5x. Usar PID, ou montar o padrao por
   concatenacao.

## Pendencias

- **RTC**: nao existe `/dev/rtc`; o dtsi do z3s nao tem o no, o de estoque tem
  `rtc@15920000`. Sem ele a hora reinicia a cada boot.
- **thermal_zone0 deu 25000 fixo** antes e depois de 60 s de carga total. Um
  sensor que nao se move nao esta medindo. Nao usar como termometro.
- **Wi-Fi**: `Phy link never came up`. Falta alimentar o QCA6390 (`gpb0-4`),
  depois S2MPU (permissao de DMA) e INTx em vez de MSI.
- **Toque/GUI**: o display ja funciona via simpledrm. O toque do r8s e
  `zinitix,zt_ts_device`@0x20 ou `stm,fts_touch`@0x49, alimentado por
  `tsp_ldo_en` (GPIO) — **mais simples que o z3s**, que dependia do S2DOS05.
- **NTP**: o proxy HTTP do PC nao carrega NTP (UDP). A hora e acertada a mao.
