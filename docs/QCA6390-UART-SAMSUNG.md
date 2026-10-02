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
