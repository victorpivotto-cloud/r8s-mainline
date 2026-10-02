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

A estimativa decorre da fonte, não de leitura dos registros programados nem de
medição elétrica. Esses números não provam que a quantização causa a falha.

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
instrumentação exclusiva do Command Complete0xfc48 e uma consulta após retorno
apenas do host a115200, se a consulta3M expirasse. Não enviou patch/NVM.

Versão115200 respondeu; versão3M expirou em cerca2s; a consulta após retornar
apenas o host a115200 respondeu em cerca4ms, com os mesmos IDs/Patch0x0d2b.
Não houve Command Complete0xfc48 capturado. TX/RX cresceram20/42bytes.
Isso indica comunicação compatível com115200 após a solicitação de baud;
não prova por que a transição falhou nem que nunca houve outro estado.
Sem captura física, pacote atrasado e enquadramento perdido não estão excluídos.

Supervisor30s e originais restaurados, retiradasRC0/flag ausente/mesmo boot/
máscaras0/limites originais/zero unidades falhas. Build W=1 sem avisos, fonte
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

Próximo: conferir o caminho3,2M correspondente à HAL/Samsung, preparar no host
instrumentação de baud/ACK/divisores e verificar suporte UART antes de outro
ensaio. Nenhum teste3,2M foi executado. O statusTLV e a compatibilidade do
firmware permanecem pendentes; não relaxar o parser para habilitar HCI.
