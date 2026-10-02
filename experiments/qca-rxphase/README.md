# QCA6390: contagem RX por fase antes do parser H4

Instrumentação de laboratório sobre o ensaio 3M/20 ms. Acrescenta contadores,
sem alterar o decoder, os comandos, o baud, o atraso ou a espera de respostas.
Não habilita Bluetooth nem deve ser instalado para autoload.

Aplicar à árvore 6.12 do porte nesta ordem:

1. [qca-baud-ack/baud-ack.patch](../qca-baud-ack/baud-ack.patch).
2. [qca-baud20/baud20-3m.patch](../qca-baud20/baud20-3m.patch).
3. `rxphase.patch` deste diretório.

O parâmetro é `hci_uart.r8s_qca_lab_rxphase`, false/0400. Guardas exigem
QCA6390/serdev/INIT115200/OPER3M. Uma guarda atômica permite apenas um setup
laboratório por carga do módulo. Outra tentativa é recusada antes da sequência
QCA, evitando repetir comandos e acumular contadores em um novo setup.

## O que é contado

Os contadores são privados por dispositivo e atômicos, inicializados em
`qca_open`. Cada fase descreve uma janela no setup:

| Fase | Janela |
|---|---|
|1|Consulta inicial de versão a 115200|
|2|Comando de baud, espera pós-drenagem e troca do host|
|3|Consulta de versão a 3M|
|4|Retorno somente do host a 115200|
|5|Consulta final de versão a 115200|

`qca_recv` conta chamadas e bytes antes da verificação REGISTERED e do H4.
Conta também recusas por REGISTERED ausente, erros retornados pelo H4 e se
havia frame parcial ao fim do último callback. `qca_recv_event` conta eventos
completos e Command Complete 0xfc48. O dump ocorre apenas no aborto final;
não há impressão por byte, captura de outros payloads ou alteração no parser.

As janelas e o dump são observações best-effort: um callback pode cruzar uma
fronteira de fase, e sua chamada/evento podem cair em fases distintas.
`lastpartial` descreve o último callback contado, não todo frame recebido na
janela. Eventos ACL/IBS não são contabilizados como eventos HCI. A fase0 fica
fora da contagem; comparar com os contadores UART exige registrar o intervalo
completo do ensaio e conferir se há RX fora das fases. Não medir tempo no fio
ou atribuir um pacote à consulta individual com certeza pelos contadores.

## Execução finita e restauração

Build ARM64 no host, com ABI/configuração/símbolos correspondentes:

```sh
# Após os dois patches anteriores:
git apply --check /caminho/rxphase.patch
git apply /caminho/rxphase.patch
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    M=drivers/bluetooth CONFIG_BT_QCA=m CONFIG_BT_HCIUART=m \
    CONFIG_BT_HCIUART_QCA=y W=1 modules
```

Usar somente com supervisor finito validado e originais preservados. Capturar
os contadores existentes em `/proc/tty/driver/s3c2410_serial` antes da carga
QCA e após a janela; não abrir a TTY do serdev nem ler FIFO/UERSTAT por fora
do driver. Conferir retirada/restauração, hashes/srcversion/flags/saúde.
Não enviar TLV/NVM/IBS/retries nem ativar BlueZ/pareamento. Falha de retirada,
restauração, reset, perda de acesso ou guarda térmica/DVFS impede novos ensaios.

## Resultado

Preparação: módulo compilado no host W=1 sem avisos, fonte original restaurada
byte por byte, sequência de patches conferida contra a fonte exata compilada.
Ensaio único, sem novo boot: versão inicial a 115200 respondeu, consulta 3M
expirou (-110), versão após retorno apenas do host a 115200 respondeu novamente,
com os mesmos IDs/Patch 0x0d2b. Sem TLV/NVM/IBS/retries/CC 0xfc48 capturado.

| Fase | Chamadas QCA RX | Bytes antes de H4 | Eventos completos | Erros H4 / recusas REGISTERED |
|---|---:|---:|---:|---:|
|1: versão inicial|1|21|1|0 / 0|
|2: baud e troca do host|0|0|0|0 / 0|
|3: consulta 3M|0|0|0|0 / 0|
|4: retorno host a 115200|0|0|0|0 / 0|
|5: versão final|1|21|1|0 / 0|

`ackfc48` e `lastpartial` foram 0 em todas as fases. O agregado UART cresceu
42 bytes RX e20 bytes TX; os 42 bytes RX coincidem com a soma das fases 1 e 5. A
listagem serial não reportou campos de erro adicionais nessa captura. Isso
não é uma contagem de erros perdidos no hardware nem uma medição elétrica.
MGMT continuou sem controladores.

**O H4 não recebeu bytes durante a troca de baud ou consulta 3M desta rodada.**
O resultado não sustenta que ele tenha rejeitado um ACK completo nessas
janelas. Não prova se o controlador transmitiu, se houve erro/discard antes
do contador UART, ou se outro evento chegaria fora da janela. Não relaxar o
parser por esse resultado. Confirmar entrega TX do 0xfc48 e caminho UART/chip.

Supervisor de 30 s; retiradas iniciais/finais RC0 e restauração confirmada por
hashes/srcversion/flags/saúde. Mesmo kernel/boot, máscaras 0/limites originais/
zero unidades falhas, sensores normais; nenhuma carga de laboratório restante.
Fontes originais preservadas; sequência de patches confere a fonte exata compilada.
Claude revisou somente delta público, sem ferramentas/MCP, e apontou risco
de acumular contadores numa segunda chamada de setup. A guarda de execução
única foi acrescentada e verificada localmente antes do ensaio. Não houve
um segundo setup de laboratório provocado para testar a guarda.

[Análise UART e limites](../../docs/QCA6390-UART-SAMSUNG.md).
