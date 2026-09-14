# Boot autônomo — 2026-09-14

**O aparelho liga sozinho.** Não depende mais do PC.

```
reinício -> S-Boot -> lk3rd (sda13) -> kernel (sda33) -> Debian
22–23 s até o SSH responder  ·  Linux: 923 ms kernel + 6,8 s userspace
```

## O medo que não se confirmou

Eu esperava ter de **substituir** o lk3rd pelo nosso kernel no `BOOT`, o que
tornaria cada troca de kernel dependente de Download Mode e botão — foi por isso
que este passo ficou adiado em 13/09.

Estava errado. Lendo o layout real (só leitura, antes de escrever nada):

```
lk3rd  (sda13):  ANDROID!   4096 setores = 2 MiB   <- o lk3rd mora aqui
boot   (sda33):  ZERADO   116736 setores = 57 MiB  <- vazio!
contíguas: lk3rd termina no setor 253056, boot começa em 253056
```

O lk3rd **carrega o kernel da partição `boot`**, que estava vazia — o
`fastboot boot` era só o caminho de teste pela RAM. Confirmado pelo porte do z3s,
que grava a região como um bloco só: primeiros 4096 setores em `lk3rd`, resto em
`boot`.

Então não houve substituição: o kernel foi **ao lado** do lk3rd. Consequência
importante — **o modo de falha é benigno**. Se o kernel não subisse, o lk3rd
continuaria intacto e o `fastboot boot` seguiria funcionando.

## Como foi feito

1. **Backup da região inteira** para o PC, conferido por hash nos dois sentidos:
   `dados/backup-boot/{lk3rd-sda13,boot-sda33}-20260914.img`
2. Gravação com guardas: confere que o alvo é `sda33`, que não é a raiz, que a
   imagem cabe e que é AOSP (`ANDROID!`).
3. **Releitura obrigatória**: sha256 do disco comparado com o da imagem.
   `5261d229a640dc46` nos dois lados.

## O que mudou no modo de trabalho

**Atualizar o kernel agora é remoto**, sem PC e sem botão:

```bash
scp boot-r8s-XX.img root@<IP-DO-APARELHO>:/root/kernel.img
ssh ... 'dd if=/root/kernel.img of=/dev/disk/by-partlabel/boot bs=1M conv=fsync'
ssh ... 'systemctl reboot'
```

Melhor que o fastboot: funciona de qualquer lugar, inclusive da outra casa.

## O risco que isso cria, e como conviver

**Não consigo voltar ao fastboot por software.** O kernel tem
`CONFIG_SYSCON_REBOOT_MODE=y`, mas falta no device tree o nó `reboot-mode` com os
valores mágicos que o lk3rd espera (ele tem as strings `reboot-fastboot` e
`reboot-recovery`, então o suporte existe do lado dele). Testado: o aparelho
ignorou o pedido e subiu o Linux normalmente.

Consequência: **um kernel ruim gravado em `sda33` exige acesso físico** (botões,
Download Mode) para recuperar.

Regra de trabalho daqui em diante:

1. **Validar toda imagem nova com `fastboot boot` (RAM) antes de gravar.** Testar
   da RAM não altera nada; só gravar o que já subiu.
2. Guardar a última imagem boa. A atual está em
   `porte/boot/boot-r8s-AQ-final.img` (sha256 `5261d229a640dc46`).
3. Trocar kernel **remotamente só quando houver alguém que possa ir até o
   aparelho**, ou aceitar o aparelho fora do ar até a próxima visita.

Mapear os valores de `reboot-mode` do lk3rd removeria esse risco — vale como
melhoria futura, não é bloqueio.

## Ainda NÃO testado: queda de energia

O boot autônomo foi verificado a partir de `systemctl reboot` (reinício a
quente). **Falta testar o ciclo frio**: aparelho desligado de fato e voltando ao
ser energizado — que é exatamente o cenário de queda de luz na outra casa.

Precisa ser feito com alguém junto, porque se ele não religar sozinho é botão.
É o próximo teste de verdade antes de o aparelho viajar.

## O teste de ciclo frio (14/09) — e por que ele era indispensável

Fiz o teste e **reportei errado**: disse "voltou sozinho" quando na verdade o
Victor tinha apertado o botão. Meu laço de observação não distingue quem ligou o
aparelho. Corrigido aqui para não induzir ninguém ao erro:

### Resultado 1: o aparelho NÃO religa sozinho

Desligado de verdade, **mesmo com o cabo conectado, ele não sobe. Precisa de
botão.** É o comportamento padrão de celular Samsung: energia em aparelho
desligado leva a modo de carga, não a boot.

**Consequência para a outra casa:** queda de luz mais longa que a bateria deixa o
aparelho fora do ar até alguém ir lá apertar o botão. Isso precisa entrar no
plano de instalação — nobreak pequeno, ou aceitar o risco, ou investigar se o
S-Boot tem alguma opção de auto-power-on.

### Resultado 2: o Wi-Fi NUNCA tinha subido do zero

Esta é a descoberta que justifica o teste inteiro.

```
exynos-pcie 133b0000.pcie: Phy link never came up
```

Causa: **`BUCK4M` (`VDD_WIFI_0P95`, núcleo do QCA6390) estava DESLIGADO**
(`0x26 = 0x18`, bits 7:5 zerados). No dump de 13/09 ele valia `0xf8`.

O que aconteceu: o BUCK4M estava ligado **desde o Android** e sobrevivia aos
reinícios a quente. Todo o porte do Wi-Fi — S2MPU, MSI, máscara de DMA, BDF —
foi construído em cima desse estado herdado. Só o primeiro desligamento real
expôs que **nada no nosso porte ligava esse trilho**.

> **Lição, e ela é geral:** estado de PMIC atravessa reinício a quente. Enquanto
> não houver um ciclo frio, não se sabe o que o porte *liga* e o que ele apenas
> *herda*. Vale para qualquer trilho, em qualquer aparelho.

### A correção, e um problema de ordem que ela trouxe

O driver `exynos990-sd-rails.c` virou `exynos990-rails.c` e passou a ligar
também o `BUCK4M` (bits 7:5, preservando a tensão que mora em `B4M_OUT1`).

Mas ligar não bastava: **o PCIe rodava antes dele**. Em `drivers/Makefile`,
`pci/` é ligado na linha 23 e `firmware/` na 137, e os dois usam o mesmo nível de
initcall — então o controlador tentava treinar o link às 0,2 s e desistia à 1,2 s,
enquanto os trilhos só subiam às 0,85 s.

Solução: **`CONFIG_PCI_EXYNOS=m`**. Como módulo, ele carrega depois dos
initcalls, com o trilho já ligado. Exigiu exportar `dw_handle_msi_irq`
(`EXPORT_SYMBOL_GPL`), que só fazia falta com o glue fora do vmlinux.

Cronologia depois da correção, com o trilho **desligado de propósito** antes do
teste:

```
0,718 s  rails: wifi-0p95 (0x26): 0x18 -> 0xf8   <- nós ligamos
1,438 s  exynos-pcie: PCIe Gen.1 x1 link up
1,603 s  ath11k_pci: qca6390 hw2.0
2,623 s  wlp1s0
        conectado em <IP-DO-APARELHO>, rede <SUA-REDE>
```

### Resultado 3: o relógio voltava para abril

O RTC de hardware não retém a hora no desligamento — e `hwclock -r` falha com
`Invalid argument`. Sem hora certa, TLS e `apt` quebram.

Resolvido em duas camadas, agora que há internet de verdade pelo Wi-Fi:

- **`fake-hwclock`**: grava a hora periodicamente e restaura no boot. Dá a hora
  aproximada **instantaneamente**, antes de qualquer rede.
- **`systemd-timesyncd`**: acerta pela rede. Sincronizou em 3 s.

(`timedatectl set-ntp` reclama "NTP not supported", mas o `timesyncd` sincroniza
de fato: `NTPSynchronized=yes`.)

## Validação final do ciclo frio (14/09) — passou

Desligamento real confirmado (`Reached target poweroff.target`, journal parado),
e na volta os **três trilhos subiram do zero**:

```
0,677 s  rails: vmmc      (0x54): 0x30 -> 0xee
0,689 s  rails: vqmmc     (0x47): 0x28 -> 0xee
0,701 s  rails: wifi-0p95 (0x26): 0x18 -> 0xf8
         wlp1s0 UP <IP-DO-APARELHO> · relogio correto · 0 servicos falhos
```

As três transições `desligado -> ligado` são a prova de que o PMIC foi
efetivamente cortado — ciclo frio de verdade — e de que **agora é o nosso código
que liga tudo**, não mais estado herdado do bootloader da Samsung.

### CONFIRMADO: ele NÃO religa sozinho

Nos dois testes o Victor apertou o botão — ele confirmou nas duas vezes. Eu
inferi "voltou sozinho" a partir do aparelho responder, e **inferi errado duas
vezes**, porque meu laço não distingue quem ligou o aparelho.

**Resultado definitivo: desligado, mesmo com o cabo/carregador conectado, o r8s
não sobe. Precisa de botão.** É o comportamento padrão de celular Samsung:
energia em aparelho desligado leva a modo de carga, não a boot.

#### O que isso significa para a outra casa

| Situação | O que acontece |
|---|---|
| Queda de luz curta (minutos a horas) | **Nada.** A bateria segura; o aparelho nem percebe |
| Queda longa, bateria acaba | Aparelho desliga. **Ao voltar a luz ele NÃO religa** — fica fora do ar até alguém apertar o botão |

Ou seja: a bateria do próprio celular **já é o nobreak** para o caso comum. O
risco é só a queda longa o bastante para esgotá-la.

Opções, por ordem de esforço:

1. **Aceitar.** Queda que esgota a bateria de um S20 FE ocioso é rara.
2. **Nobreak pequeno** alimentando o carregador estende a autonomia.
3. **Investigar auto-power-on no S-Boot** — alguns Exynos religam ao receber
   energia se um registrador do PMIC pedir. Não investigado; seria a solução
   limpa.

#### Lição de método, e eu repeti o erro

"O aparelho respondeu" **não** é "o aparelho ligou sozinho". Havia um humano no
laço e eu não o modelei. Quando a medição depende de alguém não agir, isso tem
de ser combinado explicitamente antes — ou não se mede nada.
