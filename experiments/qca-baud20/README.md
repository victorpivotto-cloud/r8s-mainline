# QCA6390: atraso pós-drenagem de 20 ms

Deltas de laboratório para comparar 300 ms e 20 ms antes da troca de baud do
host. O caminho Linux já espera a fila QCA e chama
`serdev_device_wait_until_sent`. Na HAL pública Hastings examinada, há uma
espera de 20 ms antes de `tcdrain`, troca de baud do host e leitura de
Command Complete. Esses deltas alteram somente o atraso pós-drenagem Linux:
não reproduzem toda a ordem da HAL nem implementam espera síncrona de ACK.

Os parâmetros são false/0400 e o atraso original continua com a flag apagada.
Há dois deltas alternativos, aplicados depois do laboratório correspondente:

- `baud20-3m.patch`: após
  [qca-baud-ack/baud-ack.patch](../qca-baud-ack/baud-ack.patch).
  Usa `hci_uart.r8s_qca_lab_baud20`, INIT115200/OPER3M, no kernel de controle.
- `baud20-3200.patch`: após
  [qca-uart-3200/qca-3200.patch](../qca-uart-3200/qca-3200.patch),
  com o kernel [UART opt-in](../qca-uart-3200/uart-ceiling.patch).
  Usa `hci_uart.r8s_qca_lab_baud20_3200`, INIT115200/OPER3,2M.
  O teto UART deve ser habilitado somente na rodada e restaurado antes da
  recarga dos módulos originais.

Ambos mantêm as guardas QCA6390/serdev/IDs, uma mudança de baud, consulta de
versão e, somente em timeout, uma consulta após retornar apenas o host a
115200. O Command Complete 0xfc48 é observado com até seis bytes de retorno.
Sempre abortam antes de TLV/NVM/IBS/retries. Não usar BlueZ ou pareamento.

Build ARM64 no host com ABI/configuração/símbolos correspondentes:

```sh
# Aplicar primeiro o patch do laboratório correspondente, depois seu delta.
git apply --check /caminho/baud20-3m.patch
git apply /caminho/baud20-3m.patch
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    M=drivers/bluetooth CONFIG_BT_QCA=m CONFIG_BT_HCIUART=m \
    CONFIG_BT_HCIUART_QCA=y W=1 modules
```

Somente com supervisor finito validado, originais preservados e verificação
de retirada/restauração/flags/saúde. Para 3,2M, carregar o kernel somente em
RAM com controle recuperável. Falha de retirada/restauração, reset, perda de
acesso, erro DVFS/térmico ou deadline de boot impede novos ensaios/ciclos.
Não alterar clock CMU/GPIO/RTS/DT/firmware/partições/Wi-Fi/limites.

`msleep(20)` não garante exatamente 20 ms: registrar os tempos observados.
A API de drenagem é void e não prova sucesso da transmissão física. Os
contadores/logs não medem o fio; ausência de ACK no parser não prova sua
ausência elétrica. RTS continua GPIO hog, sem pulso físico demonstrado.
As consultas compartilham opcode; uma resposta atrasada não está excluída.

## Resultado

Consulta de versão a 3M com atraso de 20 ms expirou; retornar apenas o host a
115200 permitiu resposta com os mesmos IDs/Patch 0x0d2b. Sem ACK capturado.
A consulta começou cerca de 24 ms depois do log pós-drenagem; esse intervalo
inclui atraso, troca de baud e demais operações. Build W=1 sem avisos,
fonte preservada e restauração confirmada, sem reset nem novo boot.

A rodada de 3,2M também expirou (-110). API/UART selecionaram 3200000,
UBRDIV=2/DIVSLOT=14, com clock declarado 200 MHz. A consulta começou cerca de
24 ms depois do log pós-drenagem. Após retorno somente do host a 115200,
a versão respondeu em cerca de 3,7 ms, com os mesmos IDs/Patch 0x0d2b.
Sem Command Complete 0xfc48 capturado, MGMT sem controladores; em ambas as
rodadas os contadores cresceram 20 bytes TX/42 bytes RX. Isso não prova em que
baud cada byte trafegou nem exclui resposta de versão atrasada.

As duas rodadas de 30 s terminaram com retiradas RC0 e restauração
confirmada por hashes, srcversion, ausência das flags e estado de saúde. Na rodada de 3,2M, o parâmetro UART voltou a N antes da
recarga dos módulos originais; retorno ao kernel de controle em RAM verificado.
Sem envio de TLV/NVM/IBS/retries e sem mudanças persistentes.

O atraso de 20 ms, sozinho ou combinado com seleção de 3,2M coerente, não resolveu
esses ensaios. Isso não elimina toda hipótese de temporização: a ordem da
HAL, a espera síncrona de CC e o RTS físico ainda diferem. Não repetir a matriz
inalterada nem diminuir atrasos aleatoriamente; analisar a recepção/ACK do
comando 0xfc48 e a presença de erros de enquadramento antes de outro teste.

[Análise UART e limites da conclusão](../../docs/QCA6390-UART-SAMSUNG.md).
