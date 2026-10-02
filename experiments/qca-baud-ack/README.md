# QCA6390: ACK de baud e retorno somente do host a115200

Diagnóstico opt-in `hci_uart.r8s_qca_lab_baud_ack=1`, false/0400 por padrão,
exclusivo QCA6390/serdev/INIT115200/OPER3M. Patch alternativo ao
[version-first](../qca-version-first/README.md), aplicado à árvore6.12 original;
não aplicar ambos. Não corrige Bluetooth nem deve ser instalado para autoload.

Consulta versão115200, confere Product10/ROM0200/SOC400a0200, solicita uma
mudança3M com a rotina Linux existente e consulta novamente. A instrumentação
registra apenas Command Complete de0xfc48, com até6bytes de retorno e nenhum
endereço/payload de outros comandos. Se a consulta3M expirar, muda somente
baud do host para115200 e faz uma consulta final. Não envia outro0xfc48.
Sempre aborta antes de patch/NVM/IBS/retries, também se a versão funcionar.

Essa consulta final testa uma hipótese nova; não é retry do download completo.
O laboratório não implementa a espera síncrona de ACK da HAL, não altera
RTS/CTS por GPIO e não mede baud no fio. Captura apenas eventos completos
recebidos pelo parser H4; ausência de ACK aqui não comprova ausência no fio.

## Resultado único de02/10/2026

Versão115200 respondeu, consulta3M expirou(-110), consulta após retorno apenas
do host a115200 respondeu novamente, com os mesmos IDs e Patch0x0d2b. Não
houve Command Complete0xfc48 capturado nessa janela. Contadores do driver
cresceram20bytesTX/42bytesRX, compatíveis com os comandos/repostas observados;
esses contadores não são uma captura física nem atribuem bytes ao fio.

A resposta final indica comunicação compatível com115200 após o comando de
baud; não prova se a mudança foi ignorada, rejeitada, revertida ou perdeu ACK.
Comandos de versão compartilham opcode: sem captura física/correlação adicional,
não atribuir um pacote atrasado a uma consulta individual com certeza absoluta.

Build ARM64host W=1 sem avisos, fonte restaurada byte por byte. Supervisor30s,
retiradas iniciais/finaisRC0 e restauração confirmada: hashes de arquivos
originais, srcversion quando disponível, flag ausente, mesmo boot/máscaras0/
limites originais/zero unidades falhas. Nenhum firmware/partição/boot alterado.

Aplicação/build no host com configuração e símbolos da ABI do aparelho:

```sh
git apply --check /caminho/baud-ack.patch
git apply /caminho/baud-ack.patch
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    M=drivers/bluetooth CONFIG_BT_QCA=m CONFIG_BT_HCIUART=m \
    CONFIG_BT_HCIUART_QCA=y W=1 modules
```

Executar somente com supervisor finito validado, originais preservados e
verificação de retirada/restauração. Timeout de retirada, perda de acesso ou
guarda térmica/DVFS impede outro ensaio ativo; não repetir cegamente.
Não usar BlueZ/pareamento neste laboratório. Bluetooth continua sem HCI funcional.
[UART Samsung e diferença3M/3,2M](../../docs/QCA6390-UART-SAMSUNG.md).
