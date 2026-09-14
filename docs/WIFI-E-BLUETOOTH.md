# Wi-Fi e Bluetooth no r8s — 2026-09-13

## Estado

**Wi-Fi FUNCIONANDO.** Sobe sozinho no boot, em ~3 s, sem intervenção.

```
ath11k_pci 0000:01:00.0: qca6390 hw2.0
ath11k_pci 0000:01:00.0: fw_version 0x101c008e  build 2025-04-24
                         WLAN.HSTE.1.0.1.c7-00142-QCAHSTSWPL_V2_TO_LITE_R-1
ath11k_pci 0000:01:00.0 wlp1s0: renamed from wlan0   [3,2 s]
```

Varredura real: 20 redes, **12 em 2,4 GHz e 8 em 5 GHz**. Imagem de boot
`boot/boot-r8s-AG-wifi-ok.img`.

Bluetooth: **ainda não**. Ver o fim deste arquivo.

## O caminho, na ordem em que foi destravado

Quatro bloqueios independentes, empilhados. Cada um escondia o seguinte, e
nenhum deles dava mensagem de erro que apontasse a causa.

### 1. S2MPU — o DMA do dispositivo era bloqueado

Sintoma:

```
mhi mhi0: Image transfer failed
mhi mhi0: MHI did not load image over BHI, ret: -5
ath11k_pci: failed to power up mhi: -110
```

O `BHI_STATUS_ERROR` é escrito **pelo próprio QCA6390**: ele tentou ler o
firmware da memória do host e foi abortado. O S2MPU (unidade de proteção de
memória de estágio 2) do Exynos 990 não deixa o bloco HSI1 — onde vive o PCIe
do Wi-Fi — tocar a RAM sem permissão explícita do hipervisor da Samsung, em
EL2.

A permissão se pede por HVC. Os números vieram do porte do z3s
(`z3s-referencia/kernel/drivers/wifi-brcmfmac/s2mpu.c`), e **não são específicos
da Broadcom** — são do bloco HSI1:

| | |
|---|---|
| FID | `0xc6000101` (`EXYNOS_HVC_SET_S2MPU_FOR_WIFI`) |
| arg1 | `(1 << 16) \| 24` — VID 1, índice 24 = HSI1 |
| granule | 64 KiB |
| permissão | 0 = nenhum acesso, 3 = leitura+escrita |

Implementado em `drivers/firmware/samsung/exynos990-s2mpu-wifi.c` (embutido,
`obj-y`, exporta `exynos990_s2mpu_wifi_grant()`).

**Teste de controle, feito antes de confiar:** endereço fora da RAM
(`0x10000000`, MMIO) e endereço absurdo (`0x400000000000`) são **recusados com
`0x700`**; dentro da RAM baixa, aceitos. O EL2 é real e discrimina — não é um
stub devolvendo zero.

A prova de que funcionou não foi "parou de dar erro", foi o dispositivo andar:

```
BHI fim: tx_status=2 (SUCCESS) EXECENV=0x1 (SBL) DBG1=0xfe800637
```

`EXECENV` saiu de PBL para **SBL**: o firmware começou a executar. E `DBG1` é o
endereço do nosso próprio buffer mais um deslocamento — o chip leu exatamente
de onde a permissão foi dada.

### 2. MSI nunca chegava — faltava o bit 29 do ELBI

Com o DMA liberado, a transferência concluía mas **a espera consumia os 20 s
inteiros do prazo** e `wait_event_timeout` devolvia `1` — que é o valor que ele
retorna quando a condição só ficou verdadeira no estouro. Ninguém acordava a
thread.

Medição direta que fechou o caso: `/proc/interrupts` durante a transferência,

```
76:  0  0  0  0  0  0  0  0  PCI-MSI  bhi, mhi, mhi, ce0, ...
```

zero nos oito núcleos. E a IRQ 52 do próprio controlador também em zero.

Causa: `drivers/pci/controller/dwc/pci-exynos.c` é o driver do **exynos5433** de
upstream, e nele o MSI simplesmente não está ligado:

- `pp->msi_irq[0] = -ENODEV;`
- `exynos_pcie_irq_handler()` só limpa o registrador de pulso, nunca chama
  `dw_handle_msi_irq()`;
- `exynos_pcie_enable_irq_pulse()` habilita só INTA–INTD (INTx legado).

O layout ELBI do Exynos 990 é o que a Samsung chama de **host-v0**, e nele o
pulso de MSI é o **bit 29**, tanto no status (`0x000`) quanto na habilitação
(`0x00c`). Isso está documentado no material do z3s
(`z3s-referencia/docs/WIFI_BRINGUP.md`), que mapeou o registrador mas **não usou
esse caminho**: o device tree de fábrica traz `use-msi = "false"` e a Samsung
roda o BCM4375 em INTx legado. Para o `ath11k` não existe INTx — MSI é
obrigatório.

Efeito da correção, imediato e inequívoco:

| | antes | depois |
|---|---|---|
| espera do BHI | 20,3 s (prazo) | **57 ms** |
| IRQ 52 | 0 | 4 |
| `ERRCODE` | 0x9 | **0x0** |

E na sequência: AMSS baixado por BHIE em 80 ms, `ee=2 (MISSION MODE)`.

### 3. Máscara de DMA de 36 bits levava os dados para fora do alcance

Em modo de missão, o handshake QMI quebrava:

```
qrtr: Invalid version 16
qcom_mhi_qrtr mhi0_IPCR: invalid ipcrouter packet
```

Instrumentei o `qrtr` para mostrar o endereço físico do buffer:

```
len=52  fis=0x8866d4000  bytes=10 41 6d 06 08 00 ff ff 1c 41 6d 06 08 00 ff ff
```

Duas coisas de uma vez. O buffer está em **`0x8866d4000`, RAM alta, acima de
4 GB** — e o EL2 recusa conceder qualquer coisa acima de 4 GB (o `0x700` do
teste de controle). E o conteúdo não é lixo aleatório: `…41 6d 06 08 00 ff ff…`
lido como inteiro de 64 bits é `0xffff0008066d4110`, um **ponteiro de kernel**.
É memória reciclada. O dispositivo nunca escreveu ali.

A causa é `ATH11K_PCI_DMA_MASK = 36` contra
`ATH11K_PCI_COHERENT_DMA_MASK = 32`. Por isso o firmware subia (alocação
coerente, 32 bits, RAM baixa, concedida) e os dados não (DMA de fluxo, 36 bits,
RAM alta, impossível de conceder).

Corrigido para 32. O `swiotlb` (já presente, 64 MiB) passa a rebater os buffers
altos para a faixa baixa.

### 4. Arquivo de calibração no formato errado

```
found invalid board magic
failed to fetch board data ... from ath11k/QCA6390/hw2.0/board-2.bin
```

O `board-2.bin` que tínhamos é um **ELF** — é o BDF de fábrica da Samsung, não
o contêiner `QCA-ATH11K-BOARD` que o `ath11k` espera em `board-2.bin`. O driver
também aceita um BDF cru em `board.bin`, e era isso que ele procurava em
seguida.

Solução: `cp board-2.bin board.bin` e tirar o ELF do caminho do contêiner
(renomeado para `board-2.bin.elf-samsung`).

**Qual variante está em uso, e as alternativas.** O firmware de fábrica traz
**três** BDFs, todos de 57.836 bytes, em
`~/Firmware/SM-G780F_ZTO/extraido-r8s/qca6390/`:

| Arquivo | sha256 (12 primeiros) | |
|---|---|---|
| `bdwlan.elf` | `9fe8b78f8d83` | **em uso** |
| `bdwlan.elf1` | `d067b17727d8` | alternativa |
| `bdwlan.elf2` | `7e84e98fe295` | alternativa |

A Samsung escolhe entre elas pela revisão da placa. Estamos na base, e ela
funciona (varredura nas duas bandas, potência 20 dBm). **Se o RF se comportar
mal** — alcance curto, canais faltando, potência estranha — trocar por `.elf1`
ou `.elf2` é a primeira coisa a tentar, e é barato: copiar sobre `board.bin` e
recarregar o `ath11k_pci`.

Nota: o `board-2.bin` oficial do `linux-firmware` **não resolveria** aqui. Ele é
um contêiner com muitas variantes selecionadas por `qmi-board-id`, e este
aparelho reporta `board_id 0xff` (desconhecido) — a seleção não teria por onde
funcionar. O BDF cru é o caminho certo neste caso, não um remendo.

## Dois acertos de acabamento

**O Wi-Fi subia aos 63 s, não aos 3 s.** O probe ficava preso em
`firmware_fallback_sysfs` esperando `firmware-2.bin`, um arquivo **opcional**
que não existe. Como a carga direta falhava, o kernel caía no ajudante de espaço
de usuário — e quem deveria atendê-lo era justamente o `udev-worker` que estava
bloqueado. Ele esperava pelo próprio socorro, por 60 s. Resolvido desligando
`CONFIG_FW_LOADER_USER_HELPER`.

**O MAC mudava a cada boot** (`00:03:7f:12:39:97` → `00:03:7f:12:0b:0d`), porque
o BDF não traz MAC e o `ath11k` sorteia um. Para um servidor isso significa IP
diferente a cada reinício. Fixado por
`/etc/systemd/network/10-wlan-r8s.link`, com endereço determinístico derivado do
`machine-id` (localmente administrado, primeiro octeto `0x02`). O MAC real está
na EFS e **não é lido nem publicado**, por regra do projeto.

## Onde estão as mudanças

| Arquivo | O quê |
|---|---|
| `patches/exynos990-s2mpu-wifi.c` | concessão de DMA por HVC ao HSI1 |
| `patches/exynos-s2mpu-wifi.h` | cabeçalho; vira stub fora do Exynos 990 |
| `patches/r8s-wifi-s2mpu-msi.patch` | MSI bit 29, máscara 32 bits, ganchos no MHI |

Aplicados sobre `linux-base` (6.12.0-rc5 + pilha do z3s).

## Ressalva honesta: a concessão é ampla

A varredura em massa concede **leitura e escrita de toda a RAM baixa** ao bloco
HSI1 (32.430 granules de 64 KiB em ~24 ms; as 338 recusas são os buracos
reservados). É bom de bancada e ruim de princípio: derruba a proteção que o
S2MPU existe para dar.

O certo é conceder por buffer, no momento do uso, como o z3s faz para o
BCM4375 — o que exige embrulhar cada chamada de DMA do `ath11k` e do `mhi`. Os
ganchos pontuais já estão no MHI (buffer do BHI e segmentos da tabela BHIE) e
funcionam; falta o resto do `ath11k`. **A revisar antes de considerar isto
pronto para ficar ligado sem supervisão.**

Nota relacionada: a revogação foi removida do caminho do BHI. Revogar assim que
`BHI_STATUS` vira `SUCCESS` derruba o link — o SBL continua lendo do buffer
depois disso. Hoje a permissão fica, e vaza sobre páginas já liberadas.

## Um erro meu que vale registrar

Testei a concessão em massa **antes** de ligar o MSI, vi o quadro piorar
("Device link is not accessible" em vez de "Image transfer failed") e concluí
que a concessão em massa era nociva — cheguei a reescrever o módulo inteiro por
causa disso. Era falso: o link caía por falta de interrupção, não por causa da
concessão. A transferência, essa, tinha funcionado.

A lição: com dois defeitos empilhados, o sintoma de um muda quando o outro é
mexido, e a mudança de sintoma **não** é evidência de causa. Só a medição direta
(`/proc/interrupts` em zero) desempatou.

## Bluetooth — o que falta

O QCA6390 é rádio combinado: o Bluetooth já está alimentado (compartilha o
BUCK4M, ligado). Falta o nó de UART no device tree:

```dts
&uart_bt {
    status = "okay";
    bluetooth {
        compatible = "qcom,qca6390-bt";
        enable-gpios = <&gpX Y GPIO_ACTIVE_HIGH>;
        ...
    };
};
```

Hoje o `hci_uart`/`btbcm` tenta falar Broadcom com ele e leva tempo limite
(`Bluetooth: hci0: BCM: Reset failed (-110)`) — ruído esperado enquanto o nó
correto não existir.
