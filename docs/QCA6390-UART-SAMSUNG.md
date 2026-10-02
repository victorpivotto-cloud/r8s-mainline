# QCA6390: UART Samsung, baud e CTS

Análise e um ensaio finito em02/10/2026, na árvore6.12 deste porte.
Bluetooth continua sem HCI funcional. A hipótese é comunicação durante mudança
de baud, antes de qualquer download de firmware.

## Clock declarado e divisor calculado

O DT do porte fornece um `fixed-clock`200MHz à UART/USI Bluetooth. O CMU real
não está modelado por esse clock. A leitura de `clk_summary` confirma a
frequência **declarada ao framework**, não mede ipclk nem baud físico.

`s3c24xx_serial_getclk` e `s3c24xx_serial_set_termios` usam divisão inteira e
registro fracionário para o compatible exynos850. Com o rate declarado:

| Baud solicitado | Divisor total | UBRDIV | Fração | Baud estimado se ipclk=200MHz |
|---|---:|---:|---:|---:|
|115200|1736|107|8|115207,37 (+0,0064%)|
|3000000|66|3|2|3030303,03 (+1,0101%)|
|3200000|62|2|14|3225806,45 (+0,8065%)|

A estimativa decorre da fonte e do clock declarado; não é medição elétrica.
Um ensaio posterior a 3,2 Mbaud confirmou os valores dos registros acima (ver abaixo).
Esses números não provam que a quantização causa a falha.

O driver Samsung não reencoda o baud quantizado no termios depois de programar
os divisores. `ttyport_set_baudrate` devolve `c_ospeed` e `host_set_baudrate`
no QCA ignora o retorno; portanto sucesso da API não confirma a velocidade
real do chip/host. Conferir clock/divisor físico continua pendente.

## RTS e CTS: separar o estado lógico do pino

O DT mantém RTS por GPIO hog baixo, fora do grupo de pins da UART. Assim,
`hci_uart_set_flow_control` alterna AFC e RTS lógico do controlador, mas não
comprova que o pino RTS mudou durante o ensaio version-first. Não alterar o
mux/hog sem investigação específica e estratégia de recuperação.

O status CTS vem de UMSTAT. CAR/DSR são sintetizados; RTS na listagem serial é
estado lógico do core. CTS variou entre amostras antes/depois da captura, mas
isso é somente estado instantâneo, não uma captura elétrica ou causalidade.
ContadoresTX/RX são acumulados pelo driver e também não medem o sinal no fio.

## ACK e consulta após retorno somente do host

O [diagnóstico ACK/fallback](../experiments/qca-baud-ack/README.md) acrescentou
instrumentação exclusiva do Command Complete 0xfc48 e uma consulta após retorno
apenas do host a 115200, se a consulta a 3M expirasse. Não enviou patch/NVM.

Versão a 115200 respondeu; versão3M expirou em cerca2s; a consulta após retornar
apenas o host a 115200 respondeu em cerca de 4 ms, com os mesmos IDs/Patch 0x0d2b.
Não houve Command Complete 0xfc48 capturado. TX/RX cresceram 20/42 bytes.
Isso indica comunicação compatível com 115200 após a solicitação de baud;
não prova por que a transição falhou nem que nunca houve outro estado.
Sem captura física, pacote atrasado e enquadramento perdido não estão excluídos.

Supervisor30s e originais restaurados, retiradasRC0/flag ausente/mesmo boot/
máscaras 0/limites originais/zero unidades falhas. Build W=1 sem avisos, fonte
restaurada byte por byte. Nenhum GPIO/CMU/firmware/partição/Wi-Fi alterado.

## Diferença adicional: Hastings3,2M e teto do driver Samsung3M

Na [HAL pública examinada](https://github.com/comprehensive9/vendor_qcom_proprietary/blob/36fc163a534963a5b3af52186af5efcc63401ad2/bluetooth/hidl_transport/bt/1.0/default/hci_uart_transport.cpp),
`HciUartTransport::GetMaxBaudrate` escolhe `USERIAL_BAUD_3_2M` para Hastings.
É uma evidência dessa implementação; não prova a configuração exata Samsungr8s
nem que3M seja recusado pelo controlador. O Linux QCA tem código debaud3,2M,
mas o DT atual pede3M e Samsung `set_termios` limita `uart_get_baud_rate` a3M.

Trocar só `max-speed` no DT para3,2M pode produzir velocidades diferentes nos
dois lados, com o host limitado. Não executar esse teste antes de preparar
um candidato que trate também a UART, confira baud/limites efetivos e preserve
um controle recuperável. Não elevar clockCMU por tentativa.

## Ensaio a 3,2 Mbaud com teto opt-in e divisores registrados

O [laboratório UART/QCA a 3,2 Mbaud](../experiments/qca-uart-3200/README.md) usa um
kernel temporário em RAM. O teto maior fica desabilitado por padrão e só vale
para a UART Bluetooth com compatible/endereço conferidos. O DT continua em 3 Mbaud.
O módulo QCA seleciona 3,2 Mbaud somente com flag de laboratório e aborta antes de
TLV/NVM/IBS/retries. Os logs registram pedido/seleção/clock declarado e leem
UBRDIV/DIVSLOT/AFC durante a programação normal; a impressão ocorre fora do
lock, depois de restaurar IRQs. Não houve alteração de clock CMU ou GPIO/mux.

No ensaio único, a API e a UART selecionaram 3200000; UBRDIV=2, DIVSLOT=14,
clock declarado 200 MHz. AFC foi 0 durante a mudança e 1 antes da consulta.
Versão a 115200 respondeu, versão a 3,2 Mbaud expirou (-110, cerca de 2 s), e a consulta após
retornar apenas o host a 115200 respondeu em cerca de 4 ms, com os mesmos IDs e
Patch 0x0d2b. Não houve Command Complete 0xfc48 capturado nessa janela.

Isso demonstra que o teto de 3 Mbaud foi removido para o ensaio e os divisores esperados
foram programados; **essa mudança sozinha não resolveu a comunicação**.
Não demonstra ipclk/baud elétrico, RTS físico, ausência de ACK no fio ou por que
o controlador volta/responde compatível com 115200. Pacote atrasado continua
possível porque as consultas compartilham opcode. A configuração exata da
HAL Samsung e o significado do byte extra TLV permanecem pendentes.

O Linux já espera a fila QCA e chama `serdev_device_wait_until_sent`; portanto
não afirmar que lhe falta toda drenagem TX. Depois, QCA6390 cai no atraso de 300 ms
antes de mudar baud do host. A HAL espera 20 ms, chama `tcdrain`, muda o host
e lê Command Complete. Próximo: analisar essa ordem/temporização e a captura
do ACK antes de propor outro ensaio. A diferença é hipótese de fonte; não
prova causalidade. Não repetir 3/3,2 Mbaud inalterados,
não mudar clock/mux às cegas nem relaxar o parser para habilitar HCI.

A rodada de 30 s terminou com retiradas RC0 e restauração dos módulos originais
confirmada por hash/srcversion. O parâmetro UART voltou a N antes da recarga.
O kernel de controle foi restaurado em RAM e conferido, sem flags de laboratório,
com limites originais, sensores normais e zero unidades falhas. Partições,
firmware, DT, GPIO, clock CMU e Wi-Fi permaneceram preservados.


## Comparação posterior: reduzir o atraso pós-drenagem para 20 ms

O [laboratório de 20 ms](../experiments/qca-baud20/README.md) alterou somente
o atraso pós-drenagem de cada candidato anterior. Não alterou os divisores,
GPIO, clock, firmware ou parser. Primeiro usou 3M no kernel de controle;
depois 3,2M no kernel UART instrumentado, em RAM.

| Baud solicitado ao host | Atraso solicitado após drenagem | Consulta em baud alto | Consulta após host voltar a 115200 | ACK 0xfc48 capturado |
|---|---|---|---|---|
|3M|300 ms|timeout -110|respondeu|nenhum|
|3,2M|300 ms|timeout -110|respondeu|nenhum|
|3M|20 ms|timeout -110|respondeu|nenhum|
|3,2M|20 ms|timeout -110|respondeu|nenhum|

Na rodada de 3,2M/20 ms, a API e a UART confirmaram 3200000 com UBRDIV=2 e
DIVSLOT=14. Nas duas rodadas de 20 ms, a consulta começou cerca de 24 ms após
o log posterior à chamada de drenagem. `msleep(20)` não garante 20 ms exatos;
esse intervalo também inclui mudança de baud e operações do laboratório.
A versão final respondeu em cerca de 3,5–3,7 ms, com os mesmos IDs/Patch 0x0d2b.
TX/RX cresceram 20/42 bytes e MGMT não apresentou controladores. Sem TLV/NVM/IBS.

As guardas e a restauração dos originais passaram nas duas rodadas; a rodada
3,2M retornou ao kernel de controle em RAM. Build W=1 sem avisos, fontes
preservadas e sequência dos patches públicos conferida contra a fonte compilada.
Não atribuir revisão concluída a Claude nesta rodada: a consulta de código
público expirou sem resposta; a revisão foi feita localmente.

**Reduzir apenas esse atraso não resolveu a comunicação nos dois bauds.**
Isso não exclui toda temporização: o Linux espera drenagem antes do atraso;
a HAL espera 20 ms antes de `tcdrain`, troca o host e lê Command Complete.
O laboratório ainda não espera o ACK síncrono e não demonstra pulso RTS.
`serdev_device_wait_until_sent` é void, sem indicação de sucesso físico.
No modo FIFO, `s3c24xx_serial_tx_empty` confere UFSTAT, sem ler o estado do
registrador de deslocamento nesse ramo; não afirmar que a chamada prova transmissão no fio.
Isso também não prova que a drenagem causou a falha.

Próximo: examinar a recepção/enquadramento do ACK específico 0xfc48 e o contrato
de eventos da HAL/controlador. A ausência atual é no parser H4, não uma medida
elétrica. Não repetir a matriz, relaxar parser, enviar firmware completo ou
mudar clocks/GPIO/atrasos por tentativa sem hipótese e recuperação registradas.

O caminho `qca_recv` registra `Frame reassembly failed` quando `h4_recv_buf`
retorna erro. Esse registro não apareceu nas duas capturas de 20 ms. Isso é
apenas ausência do erro reportado nesse caminho; não prova ausência de erros
na UART, de descarte anterior ao parser ou de uma resposta parcial. O próximo
laboratório deve distinguir contadores da UART, bytes entregues ao serdev/H4 e
eventos completos por fase, sem registrar payloads ou endereços de outros
comandos. Nenhum ensaio dessa instrumentação foi executado nesta rodada.


## Contagem RX por fase: nenhum byte entregue ao H4 no baud alto

O [diagnóstico RX por fase](../experiments/qca-rxphase/README.md) manteve o
ensaio 3M/20 ms e acrescentou apenas contadores privados atômicos antes do H4 e
nos eventos completos, com uma execução por carga do módulo. Não mudou baud,
comandos, decoder ou configurações da UART.

Fases 1 e 5 (versão 115200 inicial/final): cada uma teve uma chamada RX, 21 bytes,
um evento completo. Fases 2/3/4 (troca de baud/consulta a 3M/retorno host): zero
chamadas/bytes/eventos. Em todas, 0 erros H4/recusas REGISTERED/CCfc48 e estado
parcial final 0. O agregado UART cresceu 42 bytes RX/20 TX; RX coincide com os dois
pacotes de versão. Sem campos de erro adicionais na listagem serial.

Portanto, nesta rodada não houve bytes chegando ao QCA/H4 nas janelas da
mudança de baud ou consulta a 3M. Não atribuir ausência de ACK a um parser que tenha
rejeitado esse evento completo: ele não recebeu bytes nessas fases. Os
contadores não medem sinal no fio, não provam que o chip ficou mudo nem
excluem descarte anterior à contagem UART ou uma resposta fora da janela.
Snapshots e fases são best-effort, não correlação física de cada consulta.

Rodada de 30 s/retiradas RC0/restauração por hash/srcversion/flags/saúde confirmadas;
mesmo kernel/boot/máscaras 0/limitesoriginais/zero unidades falhas. Sem reboot,
TLV/NVM/IBS/retries, firmware/clock/GPIO/DT/partição/Wi-Fi alterados.

Próximo: confirmar entrega TX de 0xfc48 antes da mudança de baud e conferir o
caminho UART/controlador. Na fonte, `qca_dequeue` retira o skb da fila; o
`hci_uart_write_work` serdev pode manter o resto em `hu->tx_skb` se a escrita
for parcial. Por isso fila QCA vazia não prova que todo o comando já foi
aceito pela TTY antes da chamada `wait_until_sent`. Essa é uma possibilidade
da fonte, não uma falha observada neste ensaio; não aplicar um ajuste por
presunção. Separar os registros de retirada da fila, aceite pela escrita e
contadores UART, sem capturar outros payloads. Nenhum ensaio TX novo foi
executado nesta rodada.


## Aceite TX, baud inalterado e espera antes da drenagem

Três diagnósticos finitos em 02/10 acrescentaram evidência ao caminho do comando
`0xfc48`, com uma execução por módulo e aborto antes de firmware:

| Experimento | Observação | Resultado de comunicação |
|---|---|---|
| [Aceite TX](../experiments/qca-txobserve/README.md), 3M/20ms após drain | Uma escrita aceitou5/5bytes antes de queue-empty | Timeout3M; versão responde no retorno apenas do host a115200 |
| [Baud inalterado](../experiments/qca-baud-same/README.md), comando valor0/host115200 | Uma escrita aceitou5/5bytes; consulta seguinte respondeu | Sem ACK de baud; significado do comando inalterado não confirmado |
| [20ms antes de drain](../experiments/qca-delay-before-drain/README.md), 3M | Mesma entrega5/5; espera+drain cerca23,328ms | Timeout3M; retorno apenas do host a115200 responde |

Em todos, os únicos42bytes RX foram as duas respostas de versão; nenhum byte
nas fases da troca, nenhum ACKfc48 ou erro H4 registrado. A corrida entre
fila vazia e aceite integral não foi observada nestas amostras. As contagens
não demonstram entrega elétrica ao controlador ou baud físico; o retorno void
da drenagem não distingue sucesso de timeout. Os patches são instrumentação
restrita, com limites de logging/tag descritos nos READMEs, e não correções
para produção.

As rodadas terminaram com retiradas RC0, hashes/srcversion/flags e limites
originais restaurados, mesmo kernel/boot, máscaras0, sensores normais e nenhuma
unidade falha. HCI funcional e pareamento continuam pendentes.

Na referência HAL, `SocInit` só envia HCIReset após TLV/NVM e outras etapas.
O caminho `EdlModeChange` antes do baud é exclusivo Moselle1.0/1.1 nesse fonte.
Não transportar essas mudanças para Hastings por presunção. Próximo diagnóstico
deve esclarecer o contrato do comando/estado do controlador e o RTS físico;
repetir a matriz de bauds/atrasos ou relaxar parser sem evidência não resolve
a ausência de bytes nesta etapa.


## Build-info: erro de resposta também pode virar -110

O [ensaio de leitura build-info](../experiments/qca-build-info/README.md)
permaneceu a115200, confirmou a versão, enviou somente fc00/sub20 e abortou
antes de baud/firmware. Instrumentação progressiva identificou um Command
Complete0x0e, ncmd1/opcodefc00, nove bytes no skb (dez com H4), primeiro
retorno0x10. O errno-110 surgiu em poucos milissegundos, com resposta recebida.

Na fonte do núcleo HCI usada neste porte, o opcode vendor sem handler dedicado
usa o primeiro retorno como status; `__hci_cmd_sync_sk` converte uma requisição
concluída com `bt_to_errno`, que traduz0x10 paraETIMEDOUT. Neste comando,
-110 é erro de resposta traduzido, não expiração da janela de espera do host.
Não extrapolar essa leitura para os testes de3M/3,2M: lá houve espera de~2s
e zero bytes nas fases de baud/consulta. O significado vendor de0x10 e o
estado aplicação/download ainda não estão confirmados.

A versão respondeu novamente na primeira rodada; as seguintes pularam essa
consulta ao receber-110, para evitar ambiguidade com resposta tardia de outro
subcomando no mesmoopcode. Fase versão teve21bytes, build-info10bytes, sem
erro H4 ou recusaREGISTERED. Na versão final da instrumentação, UART TX+10/
RX+31 e MGMT vazio. Guardas/restauração dos originais passaram nas três
rodadas30s; mesmo kernel/boot/máscaras0/limites originais/sensores normais/
zero unidades falhas, sem reboot/firmware/partição/WiFi ou qualificação24h.

Não ignorar esse status para extrair label nem alterar parser por esse
resultado. Ainda falta esclarecer contrato do controlador e controle físico
de RTS; essas leituras não habilitam Bluetooth.

## Historical exclusive RTS candidate and receive-gate control (superseded below)

A RAM-only DT candidate replaced the static RTS-low hog with GPIO output-low
pinctrl plus an exclusively acquired lab descriptor. GPIO CON1/DAT0/PUD1/DRV2
matched the control. Its initial version115200 query timed out, so the guard
never raised RTS or sent a baud command. UART counted RX21 while active QCA
phases counted zero; the bytes were not validated or timed at the entry gate.
The original modules and DT were restored successfully.

A subsequent read-only query on the original DT observed21bytes through both
serdev(PROTO_READY1/REGISTERED1) and QCA(phase1/REGISTERED1); version IDs matched,
with no framing error. UART TX5/RX21 matched. This control does not locate the
candidate's bytes or prove a GPIO ownership fault. Different boot/startup state
and observation windows remain possible factors. The next discriminating step
is a low-only candidate query with bounded entry-gate observations, requiring
version success before a pulse. See
[`qca-rts-gpio`](../experiments/qca-rts-gpio/README.md) and
[`qca-rxgate`](../experiments/qca-rxgate/README.md). The pulse is **not tested**,
Bluetooth remains unenabled, and24h qualification remains deferred.

### Correction: the initial GPIO trial used an invalid structure layout

The RTS module in e5c7d00 placed its new GPIO field before the embedded
`hci_uart`, breaking the serdev callbacks' drvdata cast. Full logs show RX and
write-wakeup WARN_ON before the instrumentation. Therefore the apparent
UART/serdev delivery gap was a lab bug, not an established UART/TTY or physical
RTS failure. The control RX-gate module did not have that layout change and
its successful query remains valid. The current RTS patch preserves hci_uart
at offset zero and enforces it at compile time. At the time of this correction, the pulse remained untested; a corrected
low-only query was required before any pulse. The results below supersede
that pending step. Original control
kernel, DT and modules were restored; no production GPIO change was installed.

### Corrected low-only and GPIO baud trials

After preserving hci_uart at offset zero, the exclusive RTS-low query passed:
21bytes reached serdev(READY1/REGISTERED1) and QCA(phase1/REGISTERED1), with valid
version IDs and no H4 errors or warnings. Its query exit took3.727456ms on the
same ktime clock. This supports the diagnosed lab-layout error; no UART→TTY
loss was established by the invalid trials.

Corrected GPIO0→1→0 trials at3M and3.2M both accepted the five-byte baud command,
used20ms before drain, and lowered RTS after changing the host rate. High-baud
version queries timed out; one host-only return to115200 produced valid
versions. RX was21bytes in each initial/final version phase and zero in the
baud/high-query/host-return phases; no fc48 CC was observed. UART TX20/RX42
matched. At3.2M, API/UART selected3200000 with UBRDIV2/frac14, declared clock200MHz
and AFC restored before querying. No warning occurred in these corrected
trials, and bounded module/parameter/LOW restorations passed.

GPIO DAT readback and selected UART divisors do not measure voltage or baud
on the wire. These negative results do not establish firmware, clock or RTS
causality. Do not repeat the unchanged matrix. Remaining work should focus on
fc48/controller-state semantics and independent UART clock/signal evidence.
See [`qca-rts-low-rxgate`](../experiments/qca-rts-low-rxgate/README.md) and
[`qca-rts-3200`](../experiments/qca-rts-3200/README.md). Bluetooth remains
unenabled;24h qualification remains deferred.

The final bounded RAM return restored the original control kernel and DT,
static RTS-low hog and installed modules. Original module hashes/srcversion,
frequency limits, zero failsafe/fault masks and inactive lab units were verified.
Battery health was Good at34.1°C, SoC sensors were at most53°C, and full new
kernel logs contained no warning, BUG, Oops, panic or late ACK. No partition
was written; Bluetooth operation, audio/camera and24h qualification remain
pending.

## Contrato vendor do baud e comparação a 1 Mbaud

Na [referência HAL](https://github.com/comprehensive9/vendor_qcom_proprietary/blob/36fc163a534963a5b3af52186af5efcc63401ad2/bluetooth/hidl_transport/bt/1.0/default/patch_dl_manager.cpp),
`SetBaudRateReq` envia cinco bytes H4 para opcode `0xfc48`, com um byte de
velocidade. Após trocar o host e liberar RTS, lê Command Complete; no modo
unified, `ReadHciEvent` encaminha a resposta para `GetVsHciEvent`. Esse caminho
exige **sucesso vendor 1**, no offset 6 incluindo H4, em vez do status HCI
genérico 0. O modo legado usa offset 4 e resposta vendor `0x92`. Isso evita
interpretar um eventual ACK com a regra errada; não explica as fases com
zero RX. Não alterar o parser sem receber e validar essa resposta. O espelho
não comprova a HAL Samsung exata.

Uma comparação nova a [1 Mbaud](../experiments/qca-rts-1m/README.md) manteve o
pulso GPIO e a ordem de espera/drenagem. Com o clock **declarado** de 200 MHz,
o divisor total 200 tem erro nominal zero. A API reportou 1000000, mas a
consulta também expirou; o retorno apenas do host a 115200 recebeu versão
válida. TX aumentou 20 e RX 42; somente as duas fases de versão inicial/final
receberam bytes, sem ACK de baud ou erro H4. Guardas, retiradas e restauração
de módulos/limites/LOW passaram sem warnings.

Essa rodada não sustenta a quantização de aproximadamente 1% dos bauds altos
como explicação suficiente. Não mede clock/baud elétrico nem prova suporte
1 Mbaud por esse ROM. A leitura passiva do DT/clk_summary continua mostrando
um fixed-clock, sem modelo CMU independente. Não repetir a matriz; priorizar
evidência do comando/estado do controlador e sinais/clock físicos.

Ao final dessa comparação, o kernel e DT de controle foram restaurados em
RAM, com hog RTS LOW, módulos/hashes/srcversion originais, flags experimentais
ausentes, limites originais e máscaras de falha zero. Nenhuma unidade falha
ou diagnóstico ativo permaneceu; logs novos sem warnings. Nenhuma partição
foi gravada. Bluetooth continua sem HCI funcional; a qualificação de 24 h
permanece adiada.

## Comparação de fonte: divisor e clock no driver Samsung de referência

O [driver Samsung examinado](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/tty/serial/samsung.c)
tem duas diferenças relevantes: `s3c24xx_serial_getclk` solicita
`clk_set_rate` para `src_clk_rate` e lê o rate do provider; `set_termios`
compara os divisores inteiros adjacentes e escolhe a menor diferença de baud,
sem permitir carry da fração para um quociente já fixado. O default de fonte
nessa referência é 200 MHz. A cópia auditada coincide byte a byte com a revisão
fixada no link. Isso não comprova a configuração do Android deste aparelho.

Estimativas calculadas a partir dessas rotinas, **se ipclk for 200 MHz**:

| Pedido | Divisor mainline | Divisor vendor | Fração vendor | Baud vendor estimado |
|---|---:|---:|---:|---:|
|115200|1736|1736|8|115207,37|
|1000000|200|200|8|1000000,00|
|3000000|66|67|3|2985074,63|
|3200000|62|63|15|3174603,17|

O `has_fracval` usa uma fração numérica nos dois caminhos; não se encontrou
evidência para substituir esse formato pela antiga tabela de bits UDIVSLOT.
O fixed-clock do porte não executa a configuração do CMU real. Ler novamente
clk_summary não verifica essa configuração elétrica.

Nenhuma mudança de divisor/clock ou teste ativo foi feito nesta comparação.
O ensaio negativo a 1 Mbaud limita a hipótese de arredondamento como causa
suficiente, sem comprovar suporte dessa velocidade pelo ROM. Antes de outra
variante, é necessária evidência independente do clock/sinais ou do contrato
do controlador; não transplantar `clk_set_rate` para um provider fictício.

## Clock Bluetooth identificado na fonte CAL: PERIC1

O [DT de referência](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/arch/arm64/boot/dts/exynos/exynos9830.dts)
liga `uart@10840000` a dois clocks: `gate_uart_clk1` (ID 123/0x7b) e
`ipclk_uart1` (ID 148/0x94). Os IDs do binding identificam, respectivamente,
`GATE_PERIC1_TOP0_QCH_UART_BT` e `DOUT_CLK_PERIC1_UART_BT`. O domínio dos pins
GPIO não determina o domínio de clock do bloco UART; a cadeia de baud aqui é
PERIC1, não um clock UART ALIVE presumido a partir dos pins.

No [provider Samsung](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/clk/samsung/clk-exynos9830.c),
o DOUT registra `VCLK_DIV_CLK_PERIC1_UART_BT`. A
[tabela CAL](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/soc/samsung/cal-if/exynos9830/cmucal-node.c)
define a cadeia:

| Etapa | Fonte |
|---|---|
| Mux de entrada | `MUX_CLKCMU_PERIC1_UART_BT_USER`: `OSCCLK_PERIC1` ou `CLKCMU_PERIC1_IP` |
| Divisor de baud | `DIV_CLK_PERIC1_UART_BT`, filho desse mux |
| Clock do consumidor | `DOUT_CLK_PERIC1_UART_BT` / `ipclk_uart1` |
| Gate separado | `GATE_PERIC1_TOP0_QCH_UART_BT`, registrado com pai de bus `UMUX_CLKCMU_PERIC1_BUS` |

O [registro efetivo do VCLK](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/soc/samsung/cal-if/exynos9830/cmucal-vclk.c)
usa a LUT compartilhada `cmucal_vclk_div_clk_pericx_usixx_usi_lut`, que inclui
400 e 200 MHz. A tabela específica de UART com uma entrada 400 MHz existe,
mas não é a LUT escolhida nesse registro: não usar sua presença isolada para
afirmar baud source de 400 MHz.

Este rastreamento identifica recursos para uma futura implementação do
provider. Não mede o mux/divisor ou o clock atual, nem substitui a
verificação da revisão do silício e do DT aplicado. Nenhum clock, CMU, gate,
DT ou kernel foi alterado; o controle continua usando seu fixed-clock.

### Recursos de registro para implementar o provider

A [fonte SFR da mesma revisão](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/soc/samsung/cal-if/exynos9830/cmucal-sfr.c)
declara CMU TOP em `0x1a330000` e PERIC1 em `0x10700000`, ambos com
janela `0x8000`. Os offsets abaixo são relativos à respectiva base:

| Recurso | CMU | Offset | Campo |
|---|---|---|---|
| Mux `CLKCMU_PERIC1_IP` | TOP | `0x10d8` | seleção bit 0; busy bit 16 |
| Gate `CLKCMU_PERIC1_IP` | TOP | `0x20d8` | manual bit 20; CG_VAL bit 21 |
| Divisor `CLKCMU_PERIC1_IP` | TOP | `0x18d0` | DIVRATIO bits 3:0; busy bit 16 |
| Mux `UART_BT_USER` | PERIC1 | `0x0610` | seleção bit 4; busy bit 16 |
| Auto gating do mux UART | PERIC1 | `0x0614` | bit 28 |
| Divisor `UART_BT` | PERIC1 | `0x1800` | DIVRATIO bits 3:0; busy bit 16 |

A tabela CAL também mostra que `CLKCMU_PERIC1_IP` vem de mux → gate →
divisor no TOP, com pais `PLL_SHARED0_DIV4` ou `PLL_SHARED2_DIV2`.
`OSCCLK_PERIC1` é declarado como 26 MHz. Uma futura implementação precisa
modelar essa cadeia e validar os campos; o mux USER usa bit 4, diferente do
mux TOP. Esses dados são referências de fonte, sem leitura ou escrita de
registradores no aparelho e sem confirmação da revisão CAL aplicável.

### Seleção CAL na configuração pública do r8s

O [Makefile CAL](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/soc/samsung/cal-if/Makefile)
seleciona `exynos9830/cal_data.o` quando `CONFIG_SOC_EXYNOS9830_EVT0`
está desabilitado; quando habilitado, seleciona `exynos9830_evt0/cal_data.o`.
O [defconfig r8s](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/arch/arm64/configs/extreme_r8s_defconfig)
habilita `CONFIG_SOC_EXYNOS9830` e `CONFIG_MODEL_R8S`, sem habilitar EVT0.
O [Kconfig da plataforma](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/arch/arm64/Kconfig.platforms)
define EVT0 com padrão `n`. Isso apoia o uso da tabela `exynos9830` como
referência desse defconfig, sujeito a fragmentos ou overrides no build.
O [cal_data.c selecionado](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/soc/samsung/cal-if/exynos9830/cal_data.c)
inclui diretamente as tabelas node, SFR, VCLK e LUT auditadas acima.
Essa seleção de fonte não identifica a revisão física do telefone nem o
estado de seus clocks após boot; essas verificações continuam pendentes.

### Integração com o porte mainline e semântica do gate

No `clk-exynos990.c` do porte local auditado, o CMU TOP já registra
`mout_cmu_peric1_ip` → `gout_cmu_peric1_ip` → `dout_cmu_peric1_ip`, com os
mesmos offsets e pais CAL listados acima. O driver registra TOP, HSI0 e AUD;
a parte local de PERIC1 e seu mux/divisor UART ainda precisa ser modelada.
Isso descreve a fonte do porte, sem comprovar o estado dos clocks no boot.

O [helper Samsung do Linux](https://github.com/torvalds/linux/blob/v6.12-rc5/drivers/clk/samsung/clk-exynos-arm64.c)
prepara gates listados em `clk_regs`: habilita modo manual no bit 20 e
limpa HWACG no bit 28 antes de registrar os clocks. Assim, o gate no bit 21
não deve ser reinterpretado isoladamente como erro de implementação.
Na [RA Samsung](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/soc/samsung/cal-if/ra.c),
`ra_set_gate` seleciona controle CG_VALUE ou automático conforme MANUAL;
`ra_recalc_rate` aplica divisor de `valor + 1`. Uma implementação PERIC1
precisa manter coerência entre recursos, inicialização e rate recalc, sem
transplantar escritas CAL por tentativa. Nenhuma mudança de driver ou ensaio
foi realizado nesta comparação.
