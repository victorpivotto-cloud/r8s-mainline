# QCA6390: diagnóstico de ordem/flow control da UART

Patch experimental para a árvore6.12 deste porte, opt-in
`hci_uart.r8s_qca_lab_version_first=1`, false/0400 por padrão.
Não é uma correção de Bluetooth e não deve ser instalado para autoload.

Requer QCA6390/serdev e velocidades INIT115200/OPER3000000. Depois de power-on,
consulta versão a115200 e confere Product0x10/ROM0x0200/SOC0x400a0200.
Desliga flow control durante uma mudança de baud com a rotina existente,
restaura flow control e consulta versão a3M. Aborta sempre antes de TLV/NVM,
IBS, configuração de HCI e retries, também em erro de versão inicial.

O teste combina ordem de versão e flow control; não isola as duas variáveis.
Não reproduz toda a HAL Qualcomm: mantém o timing Linux existente e não
adiciona o leitor de ACK específico de baud. Não mede baud físico no fio.

Aplicação e compilação **no host**, usando ABI/configuração do aparelho:

```sh
git apply --check /caminho/version-first.patch
git apply /caminho/version-first.patch
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    M=drivers/bluetooth CONFIG_BT_QCA=m CONFIG_BT_HCIUART=m \
    CONFIG_BT_HCIUART_QCA=y W=1 modules
```

Execução exige supervisão finita de carga/retirada/restauração, originais
preservados e proteções conferidas antes/depois. Não substituir arquivos
instalados. Qualquer perda de acesso, guarda térmica/DVFS ou timeout de
retirada impede outros ensaios ativos. Não iniciar BlueZ/pareamento neste
laboratório. `btqca` original foi usado sem alteração.

## Resultado de02/10/2026

Um ensaio supervisionado de30s: versão115200 respondeu com os IDs esperados
e Patch0x0d2b. Após a mudança3M, a nova consulta expirou em cerca2s (`-110`).
O diagnóstico abortou sem patch/NVM ou retries. Alterar ordem/flow control
nesse caminho não bastou para obter versão a3M; isso não refuta todas as
sequências/timings da HAL nem identifica a causa elétrica/clock/CTS.

Retiradas iniciais/finais retornaram0; restauração confirmou hash dos arquivos
originais e srcversion quando disponível, flag experimental ausente, mesmo
boot, máscaras de falha0, zero unidades falhas e limites originais preservados.
Build ARM64 W=1 sem avisos, fonte original restaurada byte por byte no host.
Não repetir este ensaio sem nova mudança/hipótese. Bluetooth continua sem
HCI funcional. [Análise da HAL e dos offsets](../../docs/QCA6390-HAL-HASTINGS.md).
