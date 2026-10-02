# Bluetooth, toque, som e câmera: investigação do porte

Resultados de01–02/10/2026, restritos à árvore6.12 usada neste projeto.
O telefone continua sem Bluetooth funcional, placa de som interna ou nó de
câmera interno. Entrada básica por toque passou em um ensaio finito posterior;
o protótipo foi removido e não está instalado para uso diário. Permissões de
userspace não acrescentam os drivers ausentes.

## Bluetooth QCA6390

No controle com OPER3Mbaud, a inicialização falha no pedido de versão
`0xfc00`, antes de patch/NVM. A configuração UART havia sido conferida;
isso não mede a velocidade física. Um ensaio posterior limitado a115200
recebeu versão, conforme atualização abaixo; Bluetooth funcional segue pendente.

No [bluetooth-power.c Samsung derivado](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/bluetooth/bluetooth-power.c),
`qcomm_bt_lpm_exit_lpm_locked` aciona BT_WAKE antes de transmitir. O DT r8s
identifica BT_WAKE em gpg1-1 e HOST_WAKE em gpa2-3. O porte não controla BT_WAKE.

Ensaio em runtime, após os rails estarem energizados: linha BT_WAKE inicialmente
livre/input; requisitada isoladamente em baixo e depois alto, com unbind/bind
somente do serdev Bluetooth. Em ambos os níveis, as quatro tentativas de versão
falharam por timeout. Linha devolvida a input e driver original restaurado;
Wi-Fi e UFS preservados. Revisão Claude ajudou a apontar limites do ensaio.

Isso não refuta toda hipótese de wake: momento/pulso, estado herdado e CTS/TX
continuam relevantes. Não incorporar GPIO hog permanente como solução.
Próximo diagnóstico: conferir CTS e contadores UART, ordem do wake/reset e
caminho LPM antes do primeiro comando; comparação fria e sinais físicos ainda
necessários para atribuir causa.

### UART e caminho de alimentação — leitura passiva em02/10

O DT efetivo reportou `qcom,qca6390-bt`, ligado a `hci_uart_qca`, e um provedor
`qcom,qca6390-pmu`. A leitura de GPIO mostrou `bt-enable` como saída alta e
`bt-uart-rts` como saída baixa. Isso registra estado/dono, sem comprovar saída
de reset ou boot do subsistema Bluetooth. Nenhum GPIO, rail, bind ou comando
HCI foi alterado nesta rodada.

Em uma amostra de `/proc/tty/driver/s3c2410_serial`, o UART em0x10840000
reportou TX40/RX0 e CTS ativo. Não foi medido delta dos contadores nem sinal
no fio. Na fonte Samsung, `s3c24xx_serial_get_mctrl` lê CTS de UMSTAT, mas
retorna CAR/DSR fixos. O bit CTS ativo descreve a entrada interna naquele
instante; sua origem elétrica depende de pinmux. RTS reportado pelo serial
core é estado lógico, distinto da propriedade elétrica do pino.

O debug de pinmux atribuiu gpq0-0, gpq0-1 e gpq0-3 ao UART, com função
`uart1-bus-norts-pins`; gpq0-2 ficou fora desse mux. Isso é consistente com
RTS tratado separadamente por GPIO. A listagem de pinmux, sozinha, não mede
polaridade, nível no fio, integridade do sinal ou sincronização temporal.

Na árvore usada, o probe QCA6390 com DT obtém o alvo `bluetooth` de pwrseq.
O provedor Qualcomm requisita `bt-enable`, e sua função de habilitação aciona
esse GPIO após respeitar o intervalo entre habilitações. Os dados QCA6390
definem `pwup_delay_ms=60` e `gpio_enable_delay_ms=100`; esses valores de fonte
não comprovam a temporização física do r8s nem corrigem a ausência de RX.

Os pulsos seriais de alimentação a2400/115200 no `qca_regulator_init` são
selecionados para WCN3988/3990/3991/3998, não para QCA6390. Não importar essa
sequência de outra família como teste no r8s. `qca_port_reopen` reabre serdev
e chama `hci_uart_set_flow_control(hu, false)`: nessa API, false habilita flow
control e RTS lógico; true os desabilita. Interpretar o bool ao contrário
poderia produzir um diagnóstico inválido.

O callback vendor de BT_WAKE pertence a `uart_ops.wake_peer`; o startup
registra a função e o controle LPM cancela/rearma um timer de1s. Não foi
encontrado hook equivalente no UART Samsung mainline desta árvore, nem
recursos BT_WAKE/HOST_WAKE no `hci_qca`. A função `qca_wakeup` consulta política
de wake do dispositivo; não aciona BT_WAKE fora de banda.

Claude revisou o resumo público, sem ferramentas/MCP. Suas ressalvas sobre
CTS transitório, pinmux e diferença entre estado lógico e elétrico foram
incorporadas. TX40/RX0 e o A/B estático anterior não descartam ordem de
wake/reset/clock, polaridade ou baud. Próximo trabalho: cruzar esse mux com
os valores do DT efetivo e o momento do primeiro pedido de versão em fonte,
antes de propor uma alteração de sequência. Preservar a
alimentação compartilhada e o Wi-Fi funcional.

### Baud antes do primeiro pedido de versão

A leitura do DT em uso confirmou `max-speed=3000000` no nó QCA6390.
O grupo UART seleciona gpq0-3/-1/-0, função2, pull3 e drive0. Isso registra
configuração, sem medir níveis elétricos ou a velocidade efetivamente obtida.

Na fonte usada, `qca_open` copia `max-speed` para `hu->oper_speed`. O protocolo
define INIT115200 e OPER3000000. Para QCA6390, `qca_setup` configura INIT,
solicita OPER e só depois chama `qca_read_soc_version`. A ordem difere da
ramificação WCN399x, que consulta a versão antes de solicitar OPER.
Logo, verificar apenas o baud inicial115200 não caracteriza a velocidade
usada na tentativa de versão do caminho QCA6390.

`qca_set_speed(OPER)` chama `qca_set_baudrate`, depois altera o baud do host.
O primeiro helper envia o comando0xfc48, espera esvaziamento da fila/envio
serdev e, nesse caminho, aguarda300ms; ele retorna sem aguardar confirmação
HCI desse comando. A fonte descreve a intenção de mudar para3Mbaud, não
comprova que o controlador aceitou ou que o UART atingiu essa velocidade.
O pedido0xfc00 acontece depois, ainda antes de patch/NVM. IBS permanece
desabilitado durante setup; seu wake em banda não resolve automaticamente
essa fase inicial.

Hipótese nova: caso o controlador ignore a mudança de baud por estar em
estado inadequado, pode surgir desencontro entre host e controlador antes
do pedido de versão. Isso não foi medido, nem estabelece causa do timeout.
TX40/RX0 não é uma captura de protocolo e não identifica quais bytes chegaram
ao controlador.

Um eventual diagnóstico isolado com OPER limitado a115200 testaria a
dependência da falha de uma velocidade maior, preservando os outros fatores.
Mesmo assim o caminho continuaria enviando0xfc48; limitar OPER não equivale
a remover o comando de mudança. Não tornar isso configuração definitiva
ou declarar correção antes de comparar resultados. Nenhum baud, DT, GPIO,
kernel ou firmware foi alterado nesta rodada de leitura/fonte.

Um candidato foi depois preparado, alterando apenas a célula BE32 de
`max-speed` no DT do controle. A restauração dessa célula reproduziu o DT e
a imagem de controle inteiros, incluindo kernel, ramdisk e cabeçalho. Foi
confirmado um único blob FDT; o legacy ID zerado, já usado pelo lk3rd deste
porte, foi preservado. Imagens e dumps ficam somente no ambiente local.

Na primeira tentativa às07h, o candidato **não foi carregado**: o monitor atingiu seu
prazo de25s. Uma leitura posterior confirmou lk3rd fastboot disponível, e
foi concluído somente o retorno ao controle RAM já validado. SSH, DT3Mbaud,
sensores/failsafe/bateria e limites originais foram conferidos após o retorno.
Nessa tentativa o diagnóstico115200 ficou sem resultado de hardware; não interpretar o
prazo do monitor como falha Bluetooth ou como rejeição da imagem candidata.
Novos ciclos automáticos de boot e cargas foram interrompidos nesta rodada.

### Rodada posterior: versão recebida a115200, patch ainda falha

Após nova autorização, o monitor revelou outro problema: esta ferramenta
lista dispositivos como `serial Android Fastboot`, não somente `serial fastboot`.
Conferir o primeiro campo e aceitar o último campo `fastboot`, nos dois fluxos
de saída, evita confundir esse formato com ausência do aparelho. No retorno
observado, a entrada levou cerca de35s;25s também era um prazo insuficiente.

Uma carga em RAM do candidato, preservando a partição instalada, confirmou
no FDT vivo a única mudança de propriedade: max-speed3M para115200.
O controlador respondeu Product0x10/SOC0x400a0200/ROM0x0200/Patch0x0d2b;
o UART reportou TX626/RX30. O carregamento de `htbtfw20.tlv` foi iniciado,
mas não concluído: erro de tamanho de resposta TLV. Controle restaurado
voltou aTX40/RX0 e timeouts0xfc00. Um único candidato não estabelece causa
física: taxa, temporização, estado e clock ainda precisam ser separados.

Um diagnóstico posterior com módulos temporários manteve validações e
registrou `got=3 expected=2 soc=7 want_ev=0 head=00 1e 03`. `want_ev`
é o evento aguardado, não uma medição do cabeçalho HCI recebido; esses
bytes são o payload após remoção dos cabeçalhos pelo core. A árvore espera
dois bytes nesse caminho QCA6390. O terceiro byte não pode ser ignorado
para declarar sucesso. Código Qualcomm antigo associa status03 aCRC de
patch, mas esse significado ainda exige confirmar o contrato QCA6390;
é uma hipótese, não diagnóstico definitivo.
[Referência histórica Qualcomm](https://android.googlesource.com/platform/hardware/qcom/bt/+/5f13e7b%5E!/).

O arquivo instalado tinha cabeçalho TLV coerente com tamanho do arquivo,
Product0x10/ROM0x0200, versão de patch0x3ac0 e download_mode3. Nenhum arquivo
de firmware foi alterado. A restauração dos módulos ultrapassou o prazo15s
durante unload; foi concluída e conferida depois, com os arquivos originais
intactos e parâmetros de laboratório ausentes. O ensaio proposto com firmware
residente não começou. Novos testes ativos foram interrompidos após essa
falha do supervisor; desenvolvimento e validação no host continuaram.

O erro TLV apareceu cerca de28ms após o anúncio do download. Se o UART
estivesse efetivamente em115200/8N1, enviar210704bytes exigiria ao menos18,3s
sem contar cabeçalhos/esperas. O anúncio não confirma envio completo. Na fonte,
os segmentos intermediários de modo3 usam `__hci_cmd_send`/`hci_send_frame`
diretamente; só o último usa espera síncrona, com o mesmo opcode0xfc00.
Uma resposta precoce é hipótese consistente, ainda sem atribuição comprovada
a um segmento. O próximo diagnóstico deve relacionar TX efetivo, ordem de
segmentos e CC; manter as validações de tamanho/status e não repetir o blob
sem hipótese nova.

O diagnóstico posterior de [um segmento isolado](../experiments/qca-first-segment/README.md)
resolveu essa atribuição: enviou apenas os primeiros243bytes, com espera
síncrona e saída obrigatória antes do restante/NVM, sem retries do laboratório.
Recebeu novamente00 1e 03 em cerca24ms, mantendo-EILSEQ. Portanto esse erro
já ocorre no primeiro segmento isolado; não depende do envio completo.
Significado de03 e motivo da rejeição continuam abertos. Módulos originais
foram restaurados e conferidos após retiradas com retorno0. Comparação de
metadados da referência r8s está no README; não foi instalada/carregada.

Uma nova rodada acompanhada testou somente o fallback de firmware existente:
OPER115200 e consulta de versão passaram, mantendo IBS desabilitado e sem
chamar a rotina de download patch/NVM. O comando HCI padrão Reset0x0c03
expirou(-110); a lista de controladores configurados de gerenciamento ficou
vazia. Isso não habilitou Bluetooth e não demonstra defeito de UART: o estado
herdado e a necessidade de patch continuam incertos. Não chamar de ROM puro
nem aceitar retorno0 de uma consulta com lista vazia como prova funcional.
Não houve descoberta ou pareamento. Retiradas de módulos retornaram0 nessa
rodada, com originais restaurados, arquivos intactos e parâmetros lab ausentes.

## Toque Zinitix ZT7650

Comparação com [driver Samsung](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/input/touchscreen/zinitix/zt7650/zinitix_ts.c)
e [layout de eventos](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/input/touchscreen/zinitix/zt7650/zinitix_ts.h):

| Campo | ZT7650 vendor |
|---|---|
| Modo de coordenadas | 0 em registro 0x0010 |
| Primeiro evento | registro 0x0200, pacote de 16 bytes |
| Eventos restantes | registro 0x0201, contador no nibble baixo do byte 7 |
| Tipo/ID/estado | byte 0: eid bits 1:0, tid 5:2, estado 7:6 |
| Coordenadas | X=(byte1<<4)+(byte3>>4), Y=(byte2<<4)+(byte3&15) |
| ACK de interrupção | comando 0x0003 após consumo |
| Transação | ponteiro LE16, espera 50 us, leitura; espera posterior 10 us |

O BT541 usa modo 2 e lê 0x0080 como estrutura com status/máscara de dedos.
Adicionar apenas um compatible não adapta os eventos. O porte deve validar
ID/estado, contador limitado a 9 eventos adicionais, coordenadas e tratamento
de erros antes de publicar eventos multitouch.

O driver incompatível permanece desamarrado. A consulta I2C sem religar rails
não recebeu ACK, com `tsp_ldo_en` desabilitado após unbind. Portanto esse
ensaio não mede o protocolo e não indica que o chip esteja defeituoso.
Próximo trabalho: driver mínimo com reguladores/power sequencing e decoder
corretos, sem atualização de firmware/calibração; depois validação física de
pressionar/mover/soltar e ausência de IRQ storm. A etapa posterior abaixo
acrescenta um protótipo input no host, ainda sem validação física.

### Modelo de decoder no host

`experiments/zt7650_event_decoder.py` implementa somente a decodificação de um
lote completo de coordenadas em memória, sem I2C, GPIO, IRQ ou eventos input.
A fonte vendor usa `tid` diretamente como índice, incluindo zero; estados
NONE/PRESS/MOVE/RELEASE são0/1/2/3. O modelo usa máscaras explícitas, evitando
depender do layout de bitfields do compilador, e preserva pressão/type raw.

Políticas experimentais: no máximo10 pacotes, count do primeiro pacote
igual ao tamanho recebido, ID menor que o número de slots e coordenadas
dentro dos limites inclusivos dos eixos. Falha em qualquer pacote rejeita
todo o lote antes de retornar eventos. Não se presume countdown nos pacotes
restantes nem se rejeitam IDs repetidos sem contrato documentado.
NONE conta no tamanho do lote, mas é omitido sem validar ID/coordenadas.
O limite9 refere-se a eventos adicionais ao primeiro, não a9 pacotes totais.
A rejeição do lote difere do clamp de count da referência vendor.

Os testes sintéticos incluem vetor independente de nibbles X/Y e touch_type,
IDzero, estados ativos, lote máximo, truncamento/count inválido, ID fora do
limite, erro em pacote posterior e limite inclusivo de coordenadas. Eles
verificam o modelo de bytes; não validam o protocolo executado pelo chip.
Dez casos passaram no host. A revisão pública do Claude ajudou a ampliar
os casos negativos; a sugestão de reduzir o total a9 foi descartada após
conferir que o vendor testa `left_event > multi_fingers - 1` após o primeiro.

O modelo aplica limites de coordenadas também a RELEASE. Isso é uma política
estrita ainda não validada; um driver real precisará decidir como liberar
slots mesmo quando coordenadas de soltura não forem utilizáveis. Gestos,
proximidade/palma e pressão zero precisam de política input separada.
Não vincular esse script ao input nem anunciar toque funcional com base nos
testes. O driver kernel, power sequencing e validação física continuam pendentes.

Execução no host, sem telefone:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tests/test-zt7650-event-decoder.py -v
```

### Contrato de transporte e inicialização antes do porte

Na referência vendor acima, `read_data` e `write_cmd` verificam somente
retornos negativos de `i2c_master_send`, embora o ponteiro/comando tenha dois
bytes. `read_data` também aceita recepção curta e retorna o tamanho solicitado.
Assim, retorno não negativo não comprova que todo o pacote foi preenchido.
O futuro driver deve construir LE16 explicitamente, exigir envio de2 bytes e
recepção do tamanho completo, converter transferências curtas em erro e
impedir publicação de dados incompletos. Zerar o buffer não substitui essa
checagem. Preservar as esperas requeridas pelo protocolo ao adaptar o transporte.

`tests/test-zt7650-vendor-transfers.py` extrai os dois helpers da fonte vendor
fornecida pelo usuário e compila um mock C no host. Controles de tamanho exato,
erro negativo, limite de tentativas e alimentação desligada passaram.
O mock reproduziu envio curto de0/1 byte aceito pelos dois helpers e recepção
de0..15 bytes reportada como16, preservando a cauda do buffer anterior.
É caracterização de código com retornos injetados; não demonstra que essas
transferências curtas ocorreram no aparelho, nem implementa uma correção.
TUI/secure touch, escalonamento, temporização e concorrência reais não são
modelados; os erros negativos são exercitados no estado PROBE.

Para reproduzir, obtenha `zinitix_ts.c` da revisão vendor vinculada acima
e execute no host com Python3 e um compilador C:

```sh
python3 tests/test-zt7650-vendor-transfers.py --source /caminho/zinitix_ts.c
```

Outros cuidados conferidos na fonte:

- `ts_read_coord` chama o ACK final sem verificar seu retorno e retorna sucesso.
  O porte precisa de uma política limitada de recuperação da IRQ quando a
  leitura ou o ACK falhar, além de liberar slots sem ficar preso em contato.
- A alimentação envolve AVDD, DVDD ou GPIO e pinctrl. O vendor registra
  falhas de pinctrl, mas retorna sucesso nessa função; usar recursos por
  dispositivo, propagar erros e desfazer habilitação parcial no novo driver.
- `zt_power_sequence` distingue checksum já válido de uma sequência vendor
  com comandos de inicialização/início NVM. Isso não comprova uma atualização
  de firmware, mas os efeitos precisam ser entendidos antes de copiar a rotina.
- `mini_init_touch` escreve reset, modo, opções, ACKs repetidos e configurações
  de baixa energia/grip; seu nome não garante uma inicialização mínima.
  Selecionar e justificar o contrato necessário antes de qualquer teste I2C.

Essas rotinas vendor completas não foram copiadas ou executadas nesta análise.
A etapa posterior abaixo selecionou apenas o contrato de boot residente;
firmware update, calibração, IRQ e eventos físicos continuam pendentes.

### Janela vendor e firmware residente confirmados

A ramificação ZT7650/7650M usa ENABLE0x10f0 e ID0x17f0; os comandos
0xc000/0xcc00 do driver antigo pertencem à outra ramificação. Somente ligar
o LDO e ler registros normais devolvia o próprio endereço, inclusive com
buffer previamente preenchido por0xa5. Abrir a janela vendor correta recebeu
0xe650, que a referência define como ZT7650_CHIP_CODE.

A sequência normal de início do firmware existente, com INTclear14f0,
NVMinit12f0, PROGRAMstart11f0 e espera150ms, recebeu checksum0x55aa,
revisão de chip0x0012 e firmware0x0009. Não foram emitidos WRITE_ENABLE,
flash write/erase/upgrade, upload ou calibração/SAVE. Os ecos anteriores
pertenciam a um estado em que os registros normais ainda não estavam
validados; não demonstram defeito de adaptador ou firmware corrompido.

O [módulo de diagnóstico](../experiments/zt7650-probe/README.md) exige ativação
manual, uma tentativa por carga, identidade do r8s/chip e LDO off antes/depois.
Foi removido, deixando GPIO baixo e cliente desamarrado após os ensaios.
O protótipo input usa polling finito em vez de IRQ. Seu decoder C passou testes
com sanitizadores e não impede RELEASE por coordenadas inválidas. Uma carga
posterior acompanhada confirmou pressionar/mover/soltar:51 inícios e51
solturas, com centenas de mudanças de coordenadas. Remoção retornou0, cliente
desamarrado e regulador disabled/refs0 foram conferidos, sem erros do protótipo
nessa janela. O [README experimental](../experiments/zt7650-probe/README.md)
detalha os limites e o supervisor de captura. Uma segunda janela recebeu
dois contatos simultâneos em slots separados, com solturas completas e
coordenadas perto das bordas dentro dos limites do DT. Não há instalação
permanente, qualificação de gestos, precisão, rejeição de palma,
suspensão/retomada ou estabilidade prolongada.

## Som interno

A árvore Samsung contém ABOX v3 para Exynos9830. O [probe](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/sound/soc/samsung/abox/abox.c)
depende de SRAM/DRAM reservada, IOMMU, múltiplos clocks, GIC/IPC, firmware e
componentes ASoC. A árvore usada aqui não tem ABOX; `/proc/asound/cards` informa
nenhuma placa. Ter suporte ao amplificador ou habilitar ALSA não cria esse DSP.

Portar primeiro memória/IOMMU/clocks/IPC e comprovar boot do DSP; só depois
DAIs, máquina/codec e rotas. Áudio USB é uma alternativa menor, mas depende de
USB host e de teste físico. Não há captura/reprodução interna comprovada.

## Câmera interna

O [is-core.c Samsung](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/media/platform/exynos/camera/is-core.c)
inicializa gerenciamento de recursos/memória, interface, cadeias ISP, CSI DMA,
múltiplos nós de vídeo e hardware. O FIMC-IS antigo encontrado na árvore usada
é para Exynos4; não equivale ao ISP Exynos990. Não há `/dev/video*` no ensaio.

O próximo passo é mapear sensores/CSI, clocks/power domains, IOMMU e firmware
específicos do r8s antes de montar o pipeline V4L2. UVC USB depende de OTG;
carregar o módulo sozinho não comprova vídeo. Não foram escritos registradores
ISP nem executados blobs. Câmera e som internos continuam projetos de porte.

### Referências externas QCA6390

Comparação de cinco projetos, com revisões fixadas e limites por transporte/SoC:
[referências QCA6390](QCA6390-REFERENCIAS.md). Dagu documenta UART funcional,
mas seu ajuste hci_qca trata descoberta posterior; os patches btusb dos
projetos5.10 não corrigem o downloader UART. Próximo: HAL Hastings e origem
do firmware r8s. Esta rodada foi somente análise no host e leitura passiva.

### HAL Hastings e diagnóstico de sequência UART

[Análise da HAL](QCA6390-HAL-HASTINGS.md): o status unificado é o primeiro
byte00, não o terceiro03; significado do byte adicional continua pendente.
Consulta de versão115200 antes da mudança3M, com flow control temporário,
respondeu em115200 mas expirou a3M. Sem patch/NVM/retries, originais restaurados.
Não é correção; próximo revisar UART Samsung/clock/CTS e ACK de baud.

### ACK de baud e UART Samsung

[UART Samsung](QCA6390-UART-SAMSUNG.md): consulta3M expirou, retorno apenas
do hosta115200 recebeu versão, semCommandCompletefc48capturado. Originais
restaurados, semfirmware. HALHastings usa3,2M; driverSamsung limita3M. Não
alterar sóDT: preparar suporte/instrumentaçãohostantesensaio3,2M, ainda nãofeito.
