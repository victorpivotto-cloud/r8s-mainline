# QCA6390/Hastings: formato da resposta e mudança de UART

Análise de02/10/2026. Fonte pública examinada: espelho Qualcomm HIDL
[comprehensive9/vendor_qcom_proprietary, revisão36fc163](https://github.com/comprehensive9/vendor_qcom_proprietary/tree/36fc163a534963a5b3af52186af5efcc63401ad2/bluetooth/hidl_transport/bt/1.0/default).
A presença de suporte Hastings2.0 não prova que esta seja a HAL exata do
firmware Samsung r8s. Arquivos foram lidos/indexados no host; nenhum componente
Android externo foi executado ou instalado no telefone.

## Interface unificada: o terceiro byte não é o status lido pela HAL

O [header](https://github.com/comprehensive9/vendor_qcom_proprietary/blob/36fc163a534963a5b3af52186af5efcc63401ad2/bluetooth/hidl_transport/bt/1.0/default/patch_dl_manager.h)
identifica Hastings2.0 por Product0x10, ROM0x0200 e SOC0x400a0200, iguais aos
observados neste ensaio r8s. O mapa de arquivos inclui `htbtfw20.tlv`/`htnv20.bin`.
Isso identifica o caminho a comparar; não comprova compatibilidade dos blobs.

No [parser](https://github.com/comprehensive9/vendor_qcom_proprietary/blob/36fc163a534963a5b3af52186af5efcc63401ad2/bluetooth/hidl_transport/bt/1.0/default/patch_dl_manager.cpp),
`ReadHciEvent` detecta a interface unificada pela resposta Command Complete de
versão. `GetVsHciEvent` lê opcode do comando e os campos abaixo. Os offsets
incluem o byte H4 de tipo de pacote:

| Campo | Offset no pacote H4 completo | No retorno capturado `00 1e 03` |
|---|---|---|
| Status unificado |6| Primeiro byte:00 |
| Subcomando |7| Segundo byte:1e |
| Byte adicional |8| Terceiro byte:03; não usado como status neste parser |

`HandleEdlCmdResEvt`, no caso TLV0x1e, encaminha o offset6 à função que
classifica o resultado. Não encaminha o offset8. Portanto a associação do
terceiro byte a CRC usando uma tabela ROME antiga não se sustenta nesta HAL.
O significado desse byte adicional continua sem confirmação.

O laboratório Linux guardou os **parâmetros de retorno**, não uma captura
física H4 completa. A seleção Command Complete e a remoção do cabeçalho
seguem o caminho HCI do kernel. A correspondência com os offsets da HAL é
uma inferência de formato, não uma medição elétrica do UART.

No `btqca`6.12 usado pelo r8s, QCA6390 exige exatamente2bytes nesse caminho.
Receber3 causa `-EILSEQ` antes da análise dos campos. Essa é a recusa pelo
parser demonstrada; não comprova uma rejeição CRC pelo controlador. A HAL
examinada tolera esse byte adicional ao não usá-lo nesse caminho, mas isso
não é suficiente para relaxar o parser Linux ou concluir que o patch foi aceito.

## Ordem de inicialização e controle de fluxo

`SocInit` consulta versão, solicita mudança de baud, baixa patch/NVM e só
mais tarde envia HCI Reset. `SetBaudRateReq` desliga flow control, transmite
0xfc48, espera20ms e drena a UART, muda baud local e restaura flow control
antes de ler a resposta. O baud vem do transporte; não presumir que toda
placa use a mesma velocidade máxima.

No setup6.12 do r8s, QCA6390 cai no caminho que muda baud antes de consultar
versão e não recebe a seleção de flow control usada para os WCN399x. Isso
motiva um diagnóstico de sequência UART separado da compatibilidade de firmware.
O diagnóstico abaixo combina duas mudanças; não isola causalidade entre elas.

## Diagnóstico finito version-first

Experimento exclusivo QCA6390/serdev, flagfalse/0400 e velocidades conferidas
115200/3M. Consulta versão inicial e exige Product/ROM/SOC acima, desliga flow
control durante uma única mudança3M usando a rotina Linux existente, restaura
flow control e consulta versão novamente. Sempre aborta antes de patch/NVM,
IBS, autoinicialização HCI e retries. Não tenta reproduzir toda a HAL: por
exemplo, preserva a espera Linux existente e não acrescenta o leitor de ACK
do comando de baud da HAL. Trata-se de teste parcial de ordem/flow control.

Compilação ARM64 no host com W=1, fonte restaurada byte por byte depois do
build. `btqca` original preservado. Supervisor finito monitora boot, máscaras,
temperatura e retirada/restauração; qualquer falha impede outro ensaio ativo.
Em um único ensaio de30s, versão115200 respondeu com os IDs esperados e
Patch0x0d2b. A consulta a3M depois da mudança expirou em aproximadamente2s
(`-110`). Aborto sem TLV/NVM ou retries. Retiradas iniciais/finais retornaram0;
restauração confirmou arquivos originais, srcversion quando disponível e flag
experimental ausente. Mesmo boot, máscaras0, zero unidades falhas e limites
originais preservados; nenhuma partição, firmware ou configuração Wi-Fi mudou.

A combinação testada de ordem/flow control não bastou para a comunicação3M.
Não refuta toda a sequência HAL nem mede clock/baud/CTS físico. Não repetir
sem hipótese nova. O [patch diagnóstico](../experiments/qca-version-first/README.md)
registra o alcance do teste. Próximo: revisar a UART Samsung, baud efetivamente
programado, CTS e o tratamento do ACK de baud, antes de qualquer download
completo de firmware. HCI funcional e conexão continuam pendentes.
