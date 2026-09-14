# Linux mainline bootando no Galaxy S20 FE (r8s) — 2026-09-13

**Conseguido às 20:07.** Kernel mainline 6.12 compilado aqui, device tree escrito
aqui, rodando no SM-G780F com userspace, USB gadget, rede e shell remoto.

Não havia porte de mainline conhecido para o `r8s`. O único no mesmo SoC
(Exynos 990) é o do S20 **Ultra** (`z3s`), que é outro aparelho.

## O que está funcionando, verificado pelo próprio aparelho

```
Linux (none) 6.12.0-rc5-next-20241104-g75138397b8f8-dirty #9 SMP PREEMPT aarch64
cmdline  console=tty0 quiet loglevel=0 clk_ignore_unused maxcpus=1 nmi_watchdog=0 nosoftlockup
nproc    1              MemTotal 4.895.760 kB
UDC      10e00000.usb   thermal_zone0  25,0 °C
rede     172.16.42.1 <-> 172.16.42.2   ping 0,2 ms   telnet 23 aberto
```

| Bloco | Estado | Evidência no dmesg |
|---|---|---|
| **UFS interno** | ✅ **linkou** | `Power mode changed to : FAST series_B G_3 L_2` · `scsi host0: ufshcd` |
| **Partições** | ✅ 33 partições | `/dev/sda` 238 GiB; **`sda32` = 227 GiB** (userdata, destino do rootfs) |
| **ACPM** | ✅ registrou | `acpm chan idx=0 id=0 poll=1 mlen=16 qlen=15` |
| **USB dwc3 + gadget** | ✅ | ACM (`ttyGS0`) + RNDIS (`usb0`) |
| **Térmica** | ✅ | `thermal_zone0 = 25000` |
| PCIe (Wi-Fi) | ❌ | `Phy link never came up` — falta alimentar o QCA6390 |
| S2DOS05 (sub-PMIC) | ❌ | `error -ETIMEDOUT: S2DOS05 not responding`, probe `-110`. Irrelevante headless (é rail de touch) |

Log completo em `dados/dmesg-r8s-mainline-20260913.txt` (371 linhas).

## Como reproduzir

```bash
# 1. lk3rd na particao BOOT (ja feito; queima o Knox)
heimdall flash --BOOT porte/lk3rd/lk3rd-r8s-boot.img --no-reboot
# 2. reiniciar -> cai no fastboot do lk3rd
fastboot oem enable-mainline-quirks
fastboot boot porte/boot/boot-r8s-L-devpts.img     # roda da RAM, nao grava
# 3. o RNDIS sorteia MAC novo a cada boot -> a interface muda de nome
NEW=$(ip -br link | awk '/^enx/ && /LOWER_UP/ {print $1}' | head -1)
nmcli con add type ethernet ifname "$NEW" con-name "r8s-$NEW" ip4 172.16.42.2/24
nmcli con up "r8s-$NEW"
python3 tel.py 'uname -a'        # shell pela rede, sem sudo
```

## As cinco causas que custaram a noite — todas minhas

1. **Mapa de memória inventado.** Troquei os 4,875 GiB do upstream por 7,875 GiB
   inferidos do espaçamento dos nós `memory@*`. O kernel morria antes do
   console. O aviso que eu mesmo deixei no arquivo ("verificar no primeiro
   boot") foi o que achou.
2. **O lk3rd IGNORA os bootargs do device tree.** As variantes D a H rodaram com
   opções que nunca chegaram — `ncpus=8` numa foto, com `maxcpus=1` pedido, foi
   a prova. Resolvido com **`CONFIG_CMDLINE_FORCE=y`**.
3. **Tirei `devtmpfs` ao "enxugar" o init** → sem `/dev/kmsg`, todo marcador caiu
   no vazio. E com `2>/dev/null` por cima, nem erro aparecia.
4. **Faltava `/dev/console` no initramfs** → `unable to open an initial console`.
   Resolvido gerando o initramfs por **spec file** do `gen_init_cpio`, que cria
   nós de dispositivo sem precisar de root.
5. **Faltava `devpts`** → o `telnetd` morria na primeira conexão, sem pty.

O padrão: **toda vez que simplifiquei o init, quebrei algo invisível**, e o
sintoma foi sempre "não funciona e não diz por quê".

## Ferramentas: o que serve e o que não serve

- **gravar: `heimdall` v2.1.0.** O `samloader-rs` deu `rc=0` **mudo** duas vezes,
  sem transferir nada, e ainda prendeu o estado Odin (as tentativas seguintes
  falham com handshake/`libusb -7`; só sai reentrando no Download Mode).
- **baixar firmware: `samloader-rs`.** Aí ele é o único que funciona.
- Critério que salvou: **só aceitar "gravou" com a transferência no log**
  (`Uploading BOOT / 0%50%100% / upload successful`), nunca `rc=0`.

## Próximos passos

1. **Debian na `sda32`** — o UFS linka e a partição tem 227 GiB. É o caminho
   natural agora, e dispensa microSD.
2. **Wi-Fi**: `Phy link never came up`. Alimentar o QCA6390 (regulador em
   `gpb0-4`) e depois enfrentar S2MPU (permissão de DMA) e INTx em vez de MSI.
   A Ethernet USB segue como o caminho que funciona.
3. **`exynos990-cpufreq.c`** ainda não está ligado no Kconfig — CPU presa na
   frequência de boot.
4. **MAC fixo no gadget RNDIS** (`dev_addr`/`host_addr`), para a interface parar
   de mudar de nome a cada boot.
