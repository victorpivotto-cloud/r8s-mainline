# Retomar aqui — Celular como servidor

Documento canônico de estado. Atualizado em **2026-09-13, 23h45**.
Se divergir de qualquer outro arquivo da pasta, **este prevalece**.

## Em uma linha

O Galaxy S20 FE (`r8s`) roda **Debian 13 trixie** num kernel **mainline 6.12
compilado aqui**, com SSH por chave, DVFS nos 3 clusters, relógio que sobrevive
ao boot, **Wi-Fi em 2,4 e 5 GHz**, **microSD** e **boot autônomo** — desde
14/09 ele **não depende mais do PC para ligar** (22 s até o SSH responder).
O Moto G54 saiu do escopo e foi entregue ao Otávio.

## Como chegar no aparelho

**Duas vias, desde 14/09.** A de Wi-Fi é a boa: não depende do cabo.

```bash
ssh -i ~/.ssh/id_ed25519_r8s root@<IP-DO-APARELHO>     # Wi-Fi (rede <SUA-REDE>, DHCP)
ssh -i ~/.ssh/id_ed25519_r8s root@172.16.42.1      # USB gadget (só com cabo)
```

O Wi-Fi volta sozinho ~10 s depois do boot, sem intervenção. Redes salvas em
`/etc/wpa_supplicant/wpa_supplicant-wlp1s0.conf` (só o hash PSK, nunca a senha).
Para acrescentar outra rede — a da outra casa, um hotspot de socorro:

```bash
cat <arquivo-com-a-senha> | ssh ... /usr/local/sbin/conectar-wifi.sh 'REDE' 20
ssh ... /usr/local/sbin/conectar-wifi.sh --listar
```

Prioridade maior ganha entre redes diferentes; entre APs da MESMA rede o
`wpa_supplicant` escolhe o mais forte e faz roaming sozinho.

Se não responder, o IP do lado do PC caiu (acontece quando o aparelho reinicia):

```bash
NEW=$(ip -br link | awk '/^enx/ && /LOWER_UP/ {print $1}' | head -1)
nmcli con up "r8s-$NEW" 2>/dev/null || {
  nmcli con add type ethernet ifname "$NEW" con-name "r8s-$NEW" ip4 172.16.42.2/24
  nmcli con up "r8s-$NEW"; }
```

## Estado verificado

```text
Debian GNU/Linux 13 (trixie)     kernel 6.12.0-rc5-next-20241104-g75138397b8f8-dirty
raiz  /dev/sda32  ext4  223 GB (1% usado)      8 núcleos, DVFS ativo
rede  USB RNDIS, MAC FIXO 02:42:ac:11:00:01 -> 172.16.42.1
ssh   só por chave · senha de root BLOQUEADA · telnet REMOVIDO
ro.boot.flash.locked = 0   warranty_bit = 0x1 (Knox queimado em 13/09 19:06)
```

| Bloco | Estado |
|---|---|
| UFS interno | ✅ `FAST series_B G_3 L_2`, 33 partições, `sda32` = raiz |
| ACPM (PMIC/DVFS/TMU) | ✅ registrado, canal DVFS 5 |
| CPU DVFS | ✅ A55 442M–2,0G · A76 507M–2,6G · M5 546M–2,73G · `schedutil` |
| USB dwc3 + gadget | ✅ ACM + RNDIS, MAC fixo |
| Display | ✅ `simpledrm` 1080×2400 (framebuffer do bootloader) |
| Módulos | ✅ ath11k, wireguard, veth, bridge, overlay, nft_*, r8152 |
| Wi-Fi | ✅ **QCA6390 em modo de missão**, `wlp1s0` aos 3,2 s, MAC fixo. **Cliente de rede OK 14/09**: Wi-Fi 6, 2 fluxos, ~258 Mbit/s, −32 dBm, internet direta |
| Bluetooth | ❌ falta o nó de UART com `qcom,qca6390-bt` (alimentação já ligada) |
| RTC | ✅ `rtc@15920000` no DT, hora sobrevive ao boot |
| **Boot autônomo** | ✅ **14/09**: kernel em `sda33`, lk3rd intacto em `sda13`; 22 s sem PC. **Não religa sozinho após desligar** — precisa de botão |
| Relógio | ✅ `fake-hwclock` (aproximado, instantâneo) + `systemd-timesyncd` (exato, pela rede). O RTC de hardware NÃO retém |
| microSD | ✅ **14/09**: trilhos vmmc/vqmmc ligados por `exynos990-sd-rails.c`; cartão pronto em ~1 s, 0 timeouts, barramento a 33,58 MHz |
| USB host (OTG) | ⚠️ xHCI sobe, VBUS resolvido, mas **nada enumera** (`-71`); 7 hipóteses descartadas — ver `porte/ARMAZENAMENTO-GRAVACAO.md` |
| Toque | ❌ chip identificado e IRQ funciona, mas protocolo incompatível — **e o nó trava o boot** |

## Boot: como o aparelho sobe hoje

```
S-Boot -> lk3rd (sda13) -> kernel (sda33) -> Debian        [autonomo, 22 s]
```

Para **testar** um kernel novo sem gravar, o caminho da RAM continua:
`fastboot boot <img>`. Para **gravar**, é remoto:
`dd if=novo.img of=/dev/disk/by-partlabel/boot bs=1M conv=fsync` + reboot.

**`fastboot boot` roda da RAM: não grava nada.** É o que permite trocar de
kernel com um comando. Gravar o nosso kernel no `BOOT` faria o aparelho ligar
sozinho — **DECISÃO 13/09: adiado**, porque tirar o lk3rd faz cada troca de
kernel exigir Download Mode + heimdall, com alguém segurando botão.

Reiniciar remotamente funciona e cai no fastboot em ~30 s:

```bash
ssh ... systemctl reboot ; fastboot boot porte/boot/boot-r8s-AQ-final.img
```

## Linha do tempo de 13/09

| Hora | |
|---|---|
| manhã | levantamento dos 2 aparelhos; Moto descartado (MT6855 sem mainline) |
| ~10h | **passo 1**: OEM unlock liberado (era Family Link, não RMM) |
| ~10h30 | **passo 2**: OTG-Ethernet + carga simultânea aprovados |
| 14h05 | firmware de rollback baixado (6,2 GB) |
| **14h41** | **passo 3**: bootloader desbloqueado — **Knox NÃO queimou aí** |
| 15h31 | térmica: pico 38,7 °C sob carga dupla; proteção de bateria em 85% funciona |
| 18h38 | kernel mainline 6.12 compila |
| **19h06** | **lk3rd gravado no BOOT — aqui o Knox queimou** |
| **20h07** | **Linux mainline bootando**: userspace, UFS, rede, shell |
| **21h** | **Debian 13 instalado na sda32** |
| 21h40 | SSH por chave, DVFS nos 3 clusters, telnet removido |
| 22h30 | RTC no DT: o relógio passa a sobreviver ao boot |
| **23h30** | **Wi-Fi funcionando** — S2MPU, MSI (bit 29), máscara de DMA e BDF |

## Arquivos

- [`porte/DEBIAN-INSTALADO.md`](porte/DEBIAN-INSTALADO.md) — o sistema de hoje
- [`porte/BOOT-CONSEGUIDO.md`](porte/BOOT-CONSEGUIDO.md) — o porte do kernel
- [`porte/ESTADO.md`](porte/ESTADO.md) — a bancada (árvores, patch, GPIOs)
- [`porte/07-porte-mainline-r8s.md`](docs/07-porte-mainline-r8s.md) — o plano
- [`docs/04-runbook-desbloqueio.md`](docs/04-runbook-desbloqueio.md) — passo 3, executado
- `dados/` — dmesg, PIT oficial, coletas ADB, logs de gravação
- `porte/boot/` — 14 imagens de boot (A..O), com `LEIAME.md` e sha256
- Rollback: `~/Firmware/SM-G780F_ZTO/` (6,2 GB) + `extraido-r8s/`

## Pendências, em ordem de valor

1. **O aparelho NÃO religa sozinho depois de desligado** — CONFIRMADO 14/09,
   com o Victor apertando o botão nas duas tentativas. A bateria do celular já é
   o nobreak da queda curta; o risco é só a queda que a esgota. Decidir: aceitar,
   nobreak pequeno, ou investigar auto-power-on no S-Boot.
2. **Concessão do S2MPU está ampla demais** — hoje toda a RAM baixa fica
   liberada para o bloco HSI1. Funciona, mas derruba a proteção que o S2MPU
   existe para dar. Estreitar antes de deixar em produção. Ver a ressalva em
   `porte/WIFI-E-BLUETOOTH.md`.
3. **Bluetooth** — mesmo chip do Wi-Fi, alimentação já ligada; falta o nó de
   UART com `qcom,qca6390-bt`.
4. **Térmica de regime** — `thermal_zone0` deu **25000 fixo** antes e depois de
   60 s de carga total. Sensor que não se move não está medindo.
5. **Serviços** — câmeras, Pi-hole, VPN cliente.
6. **Toque** — chip é Zinitix ZT7650 (medido); alimentação, I2C e IRQ funcionam,
   mas o driver do mainline não fala o protocolo dele. **ATENÇÃO: o nó de toque
   SUFOCA O BOOT** — a interrupção fica presa disparando ~205/s e o `sshd` nunca
   sobe (com o nó: nunca; sem ele: 11 s). Só religar quando o protocolo estiver
   portado. Ver `porte/TOQUE-E-GRAFICO.md`.
7. **Ambiente gráfico** — o display já funciona (`simpledrm`); falta instalar um compositor. Sem toque, serve pouco.
