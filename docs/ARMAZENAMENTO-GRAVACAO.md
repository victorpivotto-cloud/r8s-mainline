# Onde o r8s vai gravar as câmeras — microSD e HD por USB

Preparado em **2026-09-14**. Os dois caminhos estão prontos para teste; nenhum
foi validado ainda porque ambos dependem de hardware ser conectado fisicamente.

## Por que dois caminhos

O aparelho vai gravar as câmeras IP localmente antes de subir para o NAS. Duas
mídias possíveis: cartão microSD (interno, discreto) ou HD por USB (capacidade
de verdade). Preparei os dois para poder escolher com medida, não com palpite.

## microSD — pronto, falta o cartão

O controlador **já existia** no device tree (`mmc@132e0000`,
`samsung,exynos7-dw-mshc`), herdado do porte do z3s, com os ajustes de
estabilidade que eles descobriram na marra:

- `broken-cd` — o pino de detecção de cartão oscila sob carga sustentada e
  dispara reinicialização do cartão em laço (tempestade de 400 kHz ↔ HS que
  trava todas as leituras). Ignora o pino e faz sondagem.
- `max-frequency = 25000000` — teto estável.

**Estava desabilitado por escolha minha**, em 13/09: sem cartão inserido o
controlador entra em timeout repetido e atrapalha o boot. Habilitado em 14/09.

| | |
|---|---|
| Imagem com microSD ligado | `boot/boot-r8s-AH-sd.img` |
| Imagem sem (retorno seguro) | `boot/boot-r8s-AG-wifi-ok.img` |

**Cuidado com o cartão de teste.** O que temos anuncia 128 GB e tem 4 GB de
verdade. Serve para provar que o controlador funciona, **não** para guardar
nada: acima de 4 GB a escrita se perde ou corrompe em silêncio, porque o
firmware falsificado mente na capacidade. A capacidade real deve ser medida com
escrita-e-releitura (`f3write`/`f3read`), nunca acreditando no que o cartão diz.

## HD por USB — pronto, mas exige cuidado

Hoje o controlador está em `dr_mode = "peripheral"`: é assim que o PC fala com o
aparelho. Em modo host esse caminho **desaparece**. O `xhci-hcd` já está
compilado.

| | |
|---|---|
| Imagem com USB host | `boot/boot-r8s-AI-sd-usbhost.img` |

### A rede de segurança, e por que ela existe

Trocar para host sem outra via de acesso deixaria o aparelho mudo, exigindo
alguém apertar botão. Duas proteções:

**1. `fastboot boot` não grava nada.** A imagem de host roda da RAM. Reiniciar
já devolve o lk3rd e o fastboot.

**2. Vigia de acesso** (`/usr/local/sbin/vigia-acesso.sh` +
`vigia-acesso.service`). Na subida ele olha `/sys/class/udc/`:

- gadget presente (boot normal) → sai na hora, não faz nada;
- gadget ausente (modo host) → conta **600 s** e reinicia, a menos que alguém
  crie `/run/vigia-desarmado`.

Ou seja: se eu conseguir entrar pelo Wi-Fi, desarmo e sigo; se não conseguir, o
aparelho volta sozinho ao fastboot em 10 minutos e mando a imagem boa de volta.
**Sem ninguém tocar no telefone.** Testado a seco: em boot normal sai com
`gadget USB presente: boot normal, vigia nao arma`.

**3. Wi-Fi como segunda via.** É o que torna o modo host utilizável de verdade.
`wpa_supplicant` instalado e `/usr/local/sbin/conectar-wifi.sh` pronto.

### Alimentação

Em modo host o aparelho precisa **fornecer** 5 V no cabo. Isso já foi validado
neste projeto em 13/09 (OTG + carga simultânea, aprovado no Android). Para o HD
vai precisar de hub alimentado ou cabo Y — o telefone sozinho não sustenta um
HD de pratos.

## Como a senha do Wi-Fi é tratada

`conectar-wifi.sh` recebe a senha por **entrada padrão**, nunca como argumento
(argumento aparece no `ps`) e nunca a imprime:

```bash
cat <arquivo-com-a-senha> | ssh ... conectar-wifi.sh 'NOME-DA-REDE'
```

Ela é usada só para gerar o hash PSK; a linha `#psk=` que o `wpa_passphrase`
emite com o texto claro é **removida**, e o arquivo fica `600`. Segue a regra do
projeto: passar o **caminho** da credencial, nunca o valor.

## Atualização 14/09 — a segunda via de acesso existe

O Wi-Fi cliente está ligado e **provado**, que é o que torna o teste de USB host
seguro:

```
<IP-DO-APARELHO>/24 via DHCP na rede <SUA-REDE>      HTTP 200 direto, sem proxy
signal -32 dBm   rx 286,7 / tx 258,0 Mbit/s   HE-MCS 11, 2 fluxos (Wi-Fi 6)
volta sozinho ~10 s depois do boot, sem tocar no cabo
```

### Uma armadilha que custou um ciclo

A primeira tentativa deu `wpa_state=COMPLETED` (associação e WPA perfeitos) mas
**nenhum IP**. O diagnóstico estava em `networkctl`:

```
Network File: n/a
State: routable (unmanaged)
```

O `20-wlan.network` tinha ficado com modo `600`, porque o `umask 077` do script
— correto para o arquivo de senha — vazou para o arquivo de rede. O
`systemd-networkd` roda com usuário próprio e **não conseguia ler**. Corrigido
para `644`, e o script agora fixa o modo de cada arquivo explicitamente.

Sinal de que a rede em si estava boa o tempo todo: o IPv6 por SLAAC já tinha
funcionado (`<prefixo-IPv6-do-provedor>…`). Só o IPv4 faltava, porque só ele dependia do networkd.

### Várias redes salvas

`conectar-wifi.sh` **acrescenta** em vez de sobrescrever, e aceita prioridade:

```bash
cat senha.txt | conectar-wifi.sh 'REDE-DA-OUTRA-CASA' 20   # preferida
cat senha.txt | conectar-wifi.sh 'HOTSPOT-DO-CELULAR' 5    # socorro
conectar-wifi.sh --listar
conectar-wifi.sh --remover 'REDE'
```

Entre redes **diferentes**, manda a prioridade (maior ganha). Entre APs da
**mesma** rede, o `wpa_supplicant` escolhe o de sinal mais forte e faz roaming
sozinho — não é preciso configurar nada para os 3 pontos de acesso do local.

Chamar de novo com o mesmo SSID **atualiza** o bloco em vez de duplicar.

## microSD — FUNCIONANDO (14/09)

```
[0.882] sd-rails: vmmc  (0x54): 0x30 -> 0xee (2,95 V)
[0.894] sd-rails: vqmmc (0x47): 0x28 -> 0xee (2,95 V)
[1.054] mmc0: new high speed SDXC card at address 0001
[1.055] mmcblk0: mmc0:0001 asdfg 125 GiB
        0 timeouts
```

Imagem: `boot/boot-r8s-AJ-sd-trilhos.img`.

### O que estava faltando: energia, não configuração

O controlador subia bem, mas o cartão não respondia nem ao **CMD0**, o primeiro
comando de todos — e o kernel ia baixando o clock (400k → 300k → 200k) tentando
de novo. O nó `mmc@132e0000` do mainline **não declara alimentação nenhuma**, e
o bootloader deixa os dois trilhos desligados.

Quais trilhos, com **três fontes independentes** — porque escrever no
registrador errado de um PMIC já me custou a DVFS uma vez:

| Fonte | O que diz |
|---|---|
| `dtbo.img` de estoque do r8s | `LDO2M` = `vqmmc`; `LDO15M` = `vmmc` (fixo 2,95 V) |
| header do kernel de estoque | `L2CTRL = 0x47`, `L15CTRL = 0x54` |
| porte do z3s (tentativa e erro) | os mesmos dois registradores |

Lidos no aparelho: `0x47 = 0x28` e `0x54 = 0x30` — bits 7:6 em `00`, ou seja
**desligados**, enquanto vizinhos como `0x45 = 0xc0` estavam ligados.

Tensão: campo de 6 bits, 1,8 V + passo de 25 mV. `0x2e` = 2,95 V, que é o valor
declarado no DT de fábrica.

Implementado em `drivers/firmware/samsung/exynos990-sd-rails.c` (embutido). Ele
**só liga, nunca desliga**, e não toca em nenhum outro registrador.

### O teste de controle que valeu a pena

Na primeira verificação o driver disse "já ligado" — porque a minha escrita
manual anterior tinha sobrevivido ao reinício a quente (o PMIC não é zerado por
reboot). Ou seja: **o driver não havia sido exercitado de verdade**. Desliguei
os trilhos de propósito, reiniciei, e só então ele provou que liga do zero.

Sem esse controle eu teria declarado funcionando algo que nunca rodou.

## Incidente 14/09 — o cartão falsificado travou o aparelho

Rodei `f3probe --destructive` no cartão de teste para medir a capacidade real.
O aparelho **travou**: parou de responder por Wi-Fi e por USB, sem cair no
fastboot. O gadget USB continuou enumerado no PC (`1d6b:0104`, `LOWER_UP`) — o
controlador de USB segura a conexão em hardware mesmo com o kernel parado, então
**gadget enumerado não é prova de sistema vivo**. O `ping` é.

Recuperação: reinício forçado (Power + Volume Baixo, ~10 s) → lk3rd → fastboot.

### Duas lições, e uma é de projeto

**1. Não varrer cartão falsificado com escrita total.** Cartão falso mente na
capacidade e costuma travar o controlador quando a escrita passa da região real.
Medir com marcadores em posições escolhidas e releitura, com prazo limitado —
não com varredura destrutiva do disco inteiro.

**2. `broken-cd` é uma faca de dois gumes.** Sem o pino de detecção, o driver
não distingue cartão ausente de cartão defeituoso: ele insiste. Num aparelho que
vai ficar sozinho em outra casa gravando 24/7, um cartão ruim pode derrubar o
sistema inteiro. **Vale reavaliar** usar o pino real (`gpa1-5`, `card-detect-invert`,
lido com sucesso em 14/09: `"5"=active`) em vez de `broken-cd`, já que a
instabilidade documentada era do z3s, não necessariamente do r8s. E somar um
watchdog de hardware.

## USB host — o controlador FUNCIONA (14/09)

Imagem `boot/boot-r8s-AL-usbhost.img` (modo host, microSD desligado de propósito
para o teste ter uma variável só).

```
mode = host                      gadget USB: não existe mais
xhci-hcd xhci-hcd.0.auto: xHCI Host Controller, irq 55, io mem 0x10e00000
  bus 1 — USB 2.0  (480 Mbps)
  bus 2 — USB 3.1 Enhanced SuperSpeed (10 Gbps)
hub 1-0:1.0: USB hub found, 1 port detected
```

O aparelho seguiu acessível por Wi-Fi o tempo todo, sem o cabo — que é
exatamente o que a preparação visava. Bateria 99% (em modo host ele **não
carrega**: passa a fornecer os 5 V).

Falta anexar o hub alimentado com o disco. `/usr/local/sbin/observa-usb.sh`
ficou rodando e grava em `/root/usb-eventos.log` qualquer conexão ou remoção,
para o teste não depender de alguém olhar na hora certa.

### Uma armadilha de medição que quase virou falso positivo

Meu primeiro detector contou `1-0:1.0` e `2-0:1.0` como "dispositivos novos" —
mas esses são os **próprios hubs raiz**, que existem sempre em modo host. E os
discos `sdb`–`sde` que apareceram no `lsblk` não são o HD: o modelo
`THGJFCT1T84BAJCA` é o chip **UFS interno**, e são as LUNs de boot/RPMB dele
(confirmado por `readlink -f /sys/block/sdX/device`, que mostra `ufs`).

Filtro correto para dispositivo USB de verdade: porta **≥ 1**
(`^[0-9]+-[1-9]`), porque o hub raiz é sempre a porta 0.

## USB host com hub USB-C — enumeração falha (14/09), e por quê

O controlador funciona, mas o hub (HD + PD + Ethernet) **não enumera**:

```
usb 1-1: device descriptor read/64, error -71     (EPROTO)
usb usb1-port1: attempt power cycle
usb 1-1: Device not responding to setup address
usb usb1-port1: unable to enumerate USB device
```

Reprodutível: 7 tentativas, e também depois de religar o `xhci` na marra
(unbind/bind). Sempre igual.

### O que NÃO é

**Não é falta de energia.** O carregador reporta `online=1`, `present=1`,
`type=USB`, `input_current_limit=500000` — o hub está alimentando o telefone,
limitado aos 500 mA padrão (sem negociação). A porta vê o dispositivo conectar,
inclusive: o *pull-up* de alta velocidade é detectado, e o kernel chega a atribuir
endereços (4, 5) antes de desistir.

### O que é, muito provavelmente

**Falta driver de Type-C/PD.** O conector USB-C do S20 FE é gerenciado pelo
**max77705**, e da família dele só temos o driver de **carregador**
(`max77705_charger.c`). Não há driver de CC/PD/MUIC — o `TCPM` na árvore só
cobre FUSB302 e HD3SS3220.

Consequência: o telefone **não apresenta resistores de CC**. Um hub USB-C
depende disso para saber que o outro lado é host e comutar o mux interno para
modo de dados. Sem CC ele conecta eletricamente, mas não conversa.

Reforçando a leitura, a própria PHY reclama de dois trilhos que ninguém declara:

```
exynos5_usb3drd_phy: supply vbus not found, using dummy regulator
exynos5_usb3drd_phy: supply vbus-boost not found, using dummy regulator
```

### Como separar as hipóteses (dois testes físicos, baratos)

1. **Pendrive comum num adaptador passivo USB-C → USB-A.** O adaptador passivo
   fixa o papel por resistor, e o pendrive é USB 2.0 puro, sem lógica de CC, e
   consome pouco. **Se enumerar, o problema é o hub exigir CC** — e a saída é
   usar um hub USB-A atrás de adaptador passivo, não escrever driver nenhum.
2. **Virar o conector USB-C 180°.** Custo zero. Alguns cabos e hubs baratos só
   ligam as linhas de dados de um lado.

### Se confirmar que é o CC

Escrever um driver de Type-C/PD para o max77705 é trabalho grande e não existe em
mainline. O caminho prático para o destino final é **evitar a negociação**: hub
USB-A com alimentação própria atrás de um adaptador passivo. Vale medir antes de
decidir — o teste 1 responde.

## USB host: o que foi descartado, e onde o problema realmente está (14/09)

Quatro experimentos, cada um matando uma hipótese.

| Experimento | Resultado | O que elimina |
|---|---|---|
| Hub USB-C (HD+PD+eth) | detectado, `-71` na enumeração | — |
| Conector virado 180° | idêntico | **orientação** (esperado: em USB 2.0 D+/D− são espelhadas) |
| Pendrive em adaptador passivo | **nada detectado**, `online=0` | revelou que o telefone não fornecia VBUS |
| Idem, com OTG do max77705 ligado | **detectado**, `-71` igual ao hub | **negociação Type-C/CC** |

O quarto é o decisivo. Um pendrive USB 2.0 puro atrás de adaptador passivo não
tem lógica de CC nenhuma; se ele falha igual ao hub USB-C, o problema **não é**
Type-C.

### VBUS: resolvido, e como

O telefone não fornecia os 5 V. O conector é gerenciado pelo **max77705**, cujo
driver de carregador escreve o modo como `CHG | BUCK` (carga normal) e **nunca
usa** a constante `MAX77705_OTG_CTRL` que o próprio cabeçalho define.

Ligando o modo OTG à mão, o dispositivo passa a ser detectado:

```
i2c-2, addr 0x69, reg 0xB7 (CHG_CNFG_00), campo MODE = bits 3:0
  0x05 = CHG|BUCK  (o que o driver deixa)
  0x0a = OTG|BOOST (fornece 5 V)     <- com isto o pendrive aparece
```

Endereço, registrador e valores conferidos contra `max77705-private.h` e
`max77705_charger.h` antes de escrever. Restaurado para `0x05` depois do teste.

Para deixar permanente, o certo é o driver expor a saída OTG como **regulador**
e o nó da PHY referenciá-la — ela já pede e não encontra:

```
exynos5_usb3drd_phy: supply vbus not found, using dummy regulator
exynos5_usb3drd_phy: supply vbus-boost not found, using dummy regulator
```

### Onde o problema está: sinalização em modo host

O sintoma é sempre o mesmo: a porta vê o dispositivo conectar (detecta o
*pull-up*), chega a atribuir endereços, e nenhum responde.

O dado que mais estreita a busca: **o modo dispositivo funciona perfeitamente a
480 Mbps** — é como a rede USB do PC funciona desde 13/09. Mesma PHY, mesma
velocidade. Logo não é sintonia básica de PHY.

A diferença entre os dois modos é quem **gera** a temporização e quem fornece as
terminações. Em modo host o controlador tem de gerar SOF e apresentar os
*pull-downs* de 15 kΩ em D+/D−. Se os *pull-downs* de host não forem
configurados na PHY, o resultado é exatamente este: linha lê como conectada, o
*chirp* falha, ninguém responde.

Registradores lidos em execução (`busybox devmem`, base `0x10e00000`):

```
GSNPSID = 0x33313130 (dwc3 3.11)
GUCTL   = 0x0A616FFF   REFCLKPER = 41 ns  (~24 MHz, plausível)
GUCTL1  = 0x81001989
GFLADJ  = 0x0A87F0A0   30MHZ=32  SDBND_SEL=1  REFCLK_FLADJ=2032  LPM_SEL=1
```

`snps,ref-clk-period-ns` e `snps,quirk-frame-length-adjustment` **não estão
declarados**, e o nó do dwc3 não recebe clock de referência — só a PHY recebe.
Não é conclusivo (41 ns bate com 24 MHz), mas é candidato.

### Próximo experimento, de variável única

Forçar `maximum-speed = "full-speed"` (12 Mbps). Se enumerar aí, o defeito é
específico de alta velocidade — sintonia/terminação da PHY — e não da lógica de
host. Se falhar também, o problema é mais fundo (terminações ou temporização).

**Exige o cabo do PC de volta**: com o hub na porta não há `fastboot`, e sem
`fastboot` não se troca de imagem.

### Sem prateleira para consultar

O porte do z3s **nunca testou USB host** — é item não marcado na lista deles
(`[ ] Test USB-C OTG keyboard, mouse and storage`). Aqui não há referência
pronta; é terreno novo.

## USB host: o teste de full-speed foi inconclusivo (14/09)

`boot/boot-r8s-AM-host-fullspeed.img` (`maximum-speed = "full-speed"`, confirmado
lendo `/proc/device-tree`).

Resultado: **piorou**. Em alta velocidade o pendrive ao menos era detectado
(`usb 1-1` aparecia, com `-71` depois). Em full-speed **não aparece nada** — a
porta não detecta sequer a conexão. O experimento não isolou o defeito; mostrou
que o caminho de full-speed é ainda menos suportado.

O VBUS, esse, estava funcionando: bateria drenando **622 mA** (contra 443 mA
sem OTG), ou seja o reforço entrega energia e o pendrive está alimentado.

### Bug meu no serviço de OTG, e a regra que faltava

Primeira versão oscilava a cada 3 s:

```
otg-vbus: modo 0x0a -> 0x05 (online=1)
otg-vbus: modo 0x05 -> 0x0a (online=0)
```

Causa: **com o boost ligado, o carregador enxerga o VBUS que nós mesmos geramos
e reporta `online=1`**. Usar `online` como condição a cada ciclo faz o serviço se
desligar sozinho. Nada enumera piscando assim.

Regra correta, agora no script: `online` só mede fonte **externa** quando o boost
está **desligado**. Mede-se uma vez e trava; só reavalia depois de 60 s sem
nenhum dispositivo (caso tenham posto o cabo do PC de volta).

### O que já foi descartado

| Hipótese | Como foi descartada |
|---|---|
| Orientação do conector | virar 180° não muda nada |
| Falta de VBUS | OTG ligado, 622 mA drenados, dispositivo detectado |
| Negociação Type-C/CC | pendrive puro em adaptador passivo falha igual ao hub |
| Sintonia da PHY | há `exynos990_tunes` no driver, e modo dispositivo faz 480 Mbps |
| Velocidade alta | forçar full-speed piorou |

### Único palpite barato que resta

`GUCTL1 = 0x81001989` — os bits 16 e 17 (`PARKMODE_DISABLE_HS` e `_SS`) estão
**zerados**. O controlador é **DWC_usb31** (`GSNPSID = 0x33313130`, IP `0x3331`),
e os quirks `snps,parkmode-disable-{hs,ss}-quirk` existem no kernel justamente
porque implementações desse bloco tropeçam em park mode.

Dá para testar **sem recompilar**: escrever os bits em `0x10e0c11c` com
`busybox devmem` e religar o `xhci`. Exige voltar à imagem de alta velocidade
(`boot-r8s-AL-usbhost.img`, já pronta), porque em full-speed nada é detectado.

**Se falhar, USB host vira projeto à parte.** O microSD já funciona e é o caminho
de gravação utilizável hoje.

## USB host: encerrado em 14/09 sem solução, com o mapa do que foi eliminado

Sintoma, sempre idêntico e reprodutível:

```
usb 1-1: new high-speed USB device number N using xhci-hcd
usb 1-1: Device not responding to setup address.
usb 1-1: device not accepting address N, error -71
usb usb1-port1: unable to enumerate USB device
```

O dispositivo **é detectado**, o *chirp* de alta velocidade **conclui** (o kernel
o classifica como high-speed), e então ele não responde a nada.

### Sete hipóteses testadas e descartadas

| # | Hipótese | Como foi eliminada |
|---|---|---|
| 1 | Orientação do conector | virar 180°: idêntico |
| 2 | Falta de VBUS | OTG ligado; 655 mA drenados; dispositivo passa a ser detectado |
| 3 | Negociação Type-C/CC | pendrive USB 2.0 puro em adaptador passivo falha igual ao hub USB-C |
| 4 | Sintonia da PHY | existe `exynos990_tunes` no driver; e modo dispositivo faz 480 Mbps com a mesma PHY |
| 5 | Alta velocidade | forçar `full-speed` **piorou** (deixa de detectar) |
| 6 | Park mode do DWC31 | bits 16/17 de `GUCTL1` setados em execução: idêntico |
| 7 | Clock livre da PHY USB2 | `U2_FREECLK_EXISTS` **já estava zerado**, igual ao de fábrica |

### O que o DT de fábrica tem e nós não

```dts
dr_mode = "otg";
maximum-speed = "super-speed-plus";
snps,quirk-frame-length-adjustment = <0x20>;   /* GFLADJ ja le 0x20 aqui */
snps,ux_exit_in_px_quirk;        /* NAO existe no mainline */
snps,elastic_buf_mode_quirk;     /* NAO existe no mainline */
snps,dis-u2-freeclk-exists-quirk;/* efeito ja presente */
adj-sof-accuracy = <0x01>;       /* vendor */
samsung,no-extra-delay;          /* vendor */
samsung,force-gen1;              /* vendor */
usb_host_device_timeout = <0xc8>;/* vendor */
xhci_l2_support = <0x01>;        /* vendor */
```

**É aqui que mora a resposta, provavelmente.** Metade dessas propriedades não
existe no mainline — são do driver dwc3 *da Samsung*. `adj-sof-accuracy` é a mais
sugestiva: ajuste de precisão de SOF, ou seja, exatamente a temporização que o
**host** gera e o dispositivo não. Some-se `usb_host_device_timeout` e
`samsung,no-extra-delay`, e o quadro é de um bloco de tratamento específico de
host que o mainline não implementa.

### Conclusão honesta

Não é limitação de hardware — o Android de fábrica faz OTG nesta porta. É lacuna
de porte, e fechá-la significa portar o tratamento de host do dwc3 da Samsung,
provavelmente com analisador de protocolo USB para ver onde a transação morre.
**É projeto à parte, não ajuste.**

O z3s nunca chegou aqui (item não marcado na lista deles), então não há
referência pronta.

### O que fica funcionando

- **microSD**: pronto em ~1 s no boot, zero timeouts. É o caminho de gravação
  utilizável hoje.
- **VBUS/OTG**: resolvido e automatizado (`otg-vbus.service`), com proteção
  contra colisão de fontes. Serve de base para quando o resto for destravado.
- **USB gadget (modo dispositivo)**: intacto, é a via de acesso por cabo.

### Para o destino final

O SSD/NVMe planejado para a outra casa depende do USB host, que **não está
pronto**. Enquanto não estiver, a gravação das câmeras tem de sair pelo microSD —
com a ressalva já registrada sobre `broken-cd` e cartão defeituoso.

## O cartão de teste, medido (14/09)

| | |
|---|---|
| Alegado | 134,2 GB (262.144.000 setores) |
| **Real** | **~4,2 GB** (passa em 4000 MiB, perde em 4050) |
| Nome do produto | `asdfg` — cartão legítimo traz identificação de fabricante |
| **Escrita** | **0,56 MB/s** (4 MB em 7,15 s, direto, com fsync) |
| Erros de mmc | **0** — o controlador está bem; o cartão é que não presta |

### Como foi medido, e por que não com `f3probe`

Marcadores de 4 KiB em posições escolhidas, com **prazo em cada operação**, e
releitura comparando. Total: ~20 escritas pequenas. O `f3probe --destructive`
varre o disco inteiro escrevendo e **travou o aparelho** mais cedo no mesmo dia.

Detalhe útil: os marcadores baixos ficaram **intactos**. Este falsificado
*descarta* a escrita além do limite real em vez de dar a volta e corromper — ou
seja, perde dado novo em silêncio, mas não estraga o que já estava lá. Nem todo
falso se comporta assim.

### Uma armadilha de medição que quase virou número errado

Na primeira tentativa o `sfdisk` não existia, o particionamento falhou, a
montagem falhou — e o `dd` escreveu em `/mnt/cartao` **que não estava montado**,
ou seja, direto na raiz (UFS interno). Resultado: "472 MB/s", que é a velocidade
do armazenamento interno, não do cartão.

Regra que ficou no script: **conferir `findmnt -no SOURCE` antes de medir**, e
abortar se a origem não for o dispositivo esperado. Ponto de montagem existir não
prova que está montado.

### Teto do nosso próprio lado

O nó usa `max-frequency = <25000000>`, herdado do porte do z3s junto com o
`broken-cd`. A 25 MHz e 4 bits, o teto teórico é ~12 MB/s — **mesmo com um cartão
bom**. Para gravação de câmeras isso ainda serve (1080p H.264 fica na casa de
0,5–1 MB/s por fluxo), mas vale saber que o limite existe e que ele veio de uma
correção de instabilidade **do z3s**, não necessariamente necessária no r8s.
Testar frequência maior é experimento barato quando houver um cartão confiável.

## Frequência do microSD: 25 -> 50 MHz (14/09)

O teto de 25 MHz do dtsi veio do porte do z3s junto com o `broken-cd` — era
correção de instabilidade **deles**. Testado no r8s, com o mesmo cartão e os
mesmos testes, só mudando o clock:

| | 25 MHz pedidos (20,15 reais) | 50 MHz pedidos (**33,58** reais) |
|---|---|---|
| Leitura crua (3×) | 0,26 / 0,26 / 0,29 MB/s | **0,35 / 0,38 / 0,34** |
| Escrita | 0,38 MB/s | **0,93 MB/s** |
| Erros de mmc | 0 | **0** |

Leitura ~30% acima de forma consistente, escrita mais que o dobro, e **nenhum
erro**. O teto do z3s não era necessário aqui. Permanente no DTS.

### Onde o limite realmente está

O divisor do `dw_mmc` é inteiro: 201,5 MHz / (2 × div). Com div=3 dá 33,58 MHz.

Tentei forçar `max-frequency = <50375000>` para conseguir div=2 (50,375 MHz) e
**deu exatamente o mesmo 33,58** — o log mostra `slot req 50000000Hz`. A razão: o
núcleo do MMC limita o clock à capacidade que o **cartão** declara, e em SD
high-speed isso é 50 MHz. Nossa configuração deixou de ser o limite.

**Para passar disso é preciso UHS (SDR50/SDR104)**, que exige comutar o `vqmmc`
para 1,8 V durante a negociação. Hoje impossível: `exynos990-sd-rails.c` fixa os
trilhos em 2,95 V. Um regulador de verdade para o S2MPS19 (que não existe em
mainline) destravaria SDR50 = 100 MHz, ou seja ~50 MB/s teóricos.

### Teto prático hoje

33,58 MHz × 4 bits ≈ **16,8 MB/s teóricos**. Folgado para gravar câmeras (1080p
H.264 fica em 0,5–1 MB/s por fluxo). O gargalo real vai ser a qualidade do
cartão, não o barramento — este falsificado entrega 0,3–0,9 MB/s, ~40× abaixo do
que o barramento comporta.

## Gravação das câmeras: preparado e testado (14/09)

Montado e verificado **com o cartão falso**, para que a chegada do bom seja só
trocar. 2 câmeras 1080p por movimento.

### O que foi instalado

| Peça | O que faz |
|---|---|
| `/usr/local/sbin/preparar-cartao.sh` | prepara um cartão novo: confere que o alvo é o SD (nunca o UFS), **mede a capacidade real por busca binária**, particiona só a parte válida com 8% de folga, formata e rotula |
| `/etc/fstab` (LABEL) | monta por `LABEL=R8S-CAMERAS` com `noatime,commit=60,nofail` |
| `rotacao-cartao.timer` | a cada 15 min, apaga as gravações mais antigas para manter o uso ≤ 80% |
| `vigia-cartao.service` | registra erros de cartão em `/var/log/cartao-erros.log` |
| `fstrim.timer` | TRIM semanal (o cartão suporta: `discard_max_bytes` = 1,9 GB) |

### Decisões, e o porquê de cada uma

**Montagem por rótulo, não por dispositivo.** Sobrevive à troca de cartão sem
editar nada.

**`nofail` + `x-systemd.device-timeout=10`.** Cartão ausente ou defeituoso
**não pode segurar o boot**. Num aparelho sozinho em outra casa, ficar preso na
inicialização por causa de um cartão é pior que gravar em lugar nenhum.

**`noatime`.** Elimina uma escrita a cada leitura. Em flash isso é vida útil.

**`commit=60`.** Agrupa o journal; menos escritas pequenas.

**`-i 1048576` na formatação.** Um inode por MiB. Vídeo são poucos arquivos
grandes: menos metadados, menos escrita.

**8% do cartão fora da partição.** Cartão cheio desgasta desproporcionalmente —
o nivelamento de escrita precisa de espaço livre para trabalhar.

**Rotação a 80%, apagando o mais antigo primeiro.** Melhor apagar o velho de
propósito do que perder a gravação nova por disco cheio, que falha em silêncio.

**O vigia só registra, não desmonta.** Cartão com falha intermitente ainda é
melhor que nenhum, e desmontar no meio de uma gravação perde mais.

### Testes feitos, não presumidos

| Teste | Resultado |
|---|---|
| Detecção de falsificação | apontou "alega 128000 MiB, entrega 4000 MiB" e particionou só a parte real |
| Guarda contra alvo errado | `RECUSADO` ao apontar para não-mmcblk; rotação aborta se a montagem não for o cartão |
| Montagem por rótulo | `umount` + `mount -a` remonta com as opções certas |
| Seleção do mais antigo | escolheu o arquivo de 5 dias entre 5 candidatos |
| Rotação parcial | 6 arquivos (4% de uso), alvo 2% → apagou **os 3 mais antigos**, uso caiu a 2% |
| Rotação total | apagou tudo, limpou diretórios vazios e **parou sozinha** em vez de girar em falso |
| Boot limpo | cartão reconhecido em 0,71 s, `mnt-cartao.mount` ativo, 4 serviços ativos, 0 falhos |

### Dois enganos meus na verificação, ambos de medição

**1.** Testei a rotação com alvo 1% num sistema que estava a 1% de uso — a
condição `uso ≤ alvo` era verdadeira e ela corretamente não fez nada. Parecia
falha do script; era teste mal desenhado.

**2.** Concluí "não montou" checando com o sistema ainda em `starting`. Montou
segundos depois. **Estado de boot não é estado final.**

### Para quando o cartão bom chegar

```bash
ssh ... /usr/local/sbin/preparar-cartao.sh /dev/mmcblk0
```

Ele mede, avisa se for falsificado, particiona, formata e monta. Nada mais a
configurar: fstab, rotação, vigia e TRIM já estão no lugar e sobrevivem à troca,
porque tudo é por rótulo.

**Na compra:** linha de **alta resistência** (SanDisk/Samsung/Kingston
Endurance), 64 GB bastam para 2 câmeras por movimento (9 a 28 dias de retenção),
128 GB dura ~o dobro sob a mesma carga. **V10 já satura** os ~16,8 MB/s do
barramento — A2/V30/UHS-II não rendem nada aqui.
