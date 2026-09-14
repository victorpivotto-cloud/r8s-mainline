# Estado da bancada do porte — 2026-09-13

Tudo aqui é trabalho de PC. **Nada foi gravado no aparelho.**

## O que está montado

```
porte/
  z3s-referencia/     clone de Bentlybro/z3s-mainline-linux @572e789 (2,8 MB)
  linux-base/         exynos990-mainline/linux @next-20241018-990, 6.12.0-rc3 (1,9 GB)
  lk3rd/              lk3rd-r8s.tar + .img da release 2.4-hotfix (Odin → BOOT)
  estoque/            boot.img + dtbo.img do firmware, e o DTB de estoque decodificado
  dts/                exynos990-r8s-headless.dts — RASCUNHO, não compilado
```

## Como o DTB de estoque foi lido sem `dtc` nem `lz4`

Os dois binários não estão instalados, mas o `python3-lz4` (4.4.5) está. Então:

1. `AP_*.tar.md5` → `boot.img.lz4` → descomprimido em Python → `boot.img` (61,8 MB);
2. cabeçalho Android **v2**: `dtb 340952 @ offset 41093120`, mas o magic ali é
   `d7b7ab1e` — **não é FDT cru, é uma `dt_table` da Samsung** (1 entrada);
3. entrada 0 → `r8s-estoque.dtb` (340.888 bytes, magic `d00dfeed`);
4. leitor de FDT escrito em Python (`scratchpad/dtread.py`) → 13.652 linhas de
   despejo em `estoque/r8s-estoque.dts.txt`.

É dessa leitura que saem os GPIOs conferidos abaixo — não foram copiados do z3s
no escuro.

## GPIOs de placa: r8s × z3s

| Função | z3s (funcionando) | r8s (lido do estoque) | |
|---|---|---|---|
| Wi-Fi enable | `gpb0 4` | `cnss_wlan_en` = `gpb0-4` | igual |
| PCIe reset | `gpf0 1` | `pcie0_perst` = `gpf0-1` | igual |
| PCIe clkreq | `gpf0 0` | `pcie0_clkreq` = `gpf0-0` | igual |
| UFS vcc | `gpg1 0` | `fixedregulator@0 "ufs-vcc"` → `gpg1 0` | igual |
| Teclas | `gpa2-4`/`gpa0-4`/`gpa0-3` | idem | igual |
| PCIe `ranges`/`num-lanes`/`max-link-speed` | — | conferem | igual |

No estoque, `pcie@133B0000` e `dwmmc2@132E0000` vêm com `status = "disabled"` —
são ligados por overlay do DTBO. Por isso o mainline não os enxerga sozinho.

## O que o patch do z3s toca, e o que serve para nós

`kernel/patches/linux990-working-tree.patch` (70 KB) mexe em 34 arquivos:

| Área | Serve ao r8s? |
|---|---|
| `clk/samsung/clk-exynos990.c` + `dt-bindings/clock/exynos990.h` | **sim** — a base NÃO tem nenhum dos dois |
| `ufs/host/ufs-exynos.c`, `phy/samsung/phy-samsung-ufs.*` | **sim** — o quirk que faz o UFS linkar |
| `pci/controller/dwc/pci-exynos.c` | **sim** — host PCIe |
| `mailbox/*`, `firmware/*` (ACPM), `regulator/*` (S2DOS05) | **sim** — a energia toda depende disso |
| `pmdomain/samsung`, `soc/samsung/exynos-usi.c`, `power/reset/syscon-poweroff.c` | **sim** |
| `power/supply/*` + `include/linux/power_supply.h` (MAX77705) | **sim** — carga |
| `gpu/drm/panfrost/*`, `drm/tiny/simpledrm.c` | não (headless) |
| `sound/soc/codecs/cs35l41.c` | não |
| **`net/wireless/broadcom/brcm80211/*` (5 arquivos)** | **NÃO — aqui é `ath11k`** |

Ou seja, de 34 arquivos, 6 não se aplicam e 5 deles são justamente o Wi-Fi
Broadcom, que no r8s é substituído por driver de mainline.

## Árvore encenada

Copiados do z3s para dentro da `linux-base` (o git da própria árvore é a rede de
segurança, `git status` mostra o delta):

```
M  arch/arm64/boot/dts/exynos/exynos990.dtsi          251 → 884 linhas
M  arch/arm64/boot/dts/exynos/exynos990-pinctrl.dtsi  2195 → 2210
?? arch/arm64/boot/dts/exynos/exynos990-r8s.dts       (o rascunho headless)
?? arch/arm64/boot/dts/exynos/exynos990-z3s.dts       (referência)
?? drivers/clk/samsung/clk-exynos990.c                (a base não tem)
?? include/dt-bindings/clock/exynos990.h              (a base não tem)
```

Falta ainda: entrada no `arch/arm64/boot/dts/exynos/Makefile` (hoje só lista
`exynos990-c1s.dtb`), e aplicar o patch grande.

## BLOQUEIO: falta o toolchain, e `sudo` pede senha

```
bison  flex  dtc  lz4  aarch64-linux-gnu-gcc  libelf-dev      ← FALTAM
bc  cpio  rsync  openssl  libssl-dev  make  gcc               ← ok
```

Sem `bison`/`flex` nem o `scripts/dtc` da própria árvore compila, então nem dá
para validar a sintaxe do device tree. Comando único:

```bash
sudo apt install -y bison flex bc libssl-dev libelf-dev \
                    gcc-aarch64-linux-gnu device-tree-compiler lz4
```

## Primeiro marco verificável, quando o toolchain existir

**Compilar o `exynos990-r8s.dtb`.** Não prova que boota, mas prova que o device
tree é coerente: símbolos existem, phandles resolvem, includes fecham. É barato
e pega a maior parte dos erros de transcrição.
