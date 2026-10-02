# QCA6390: referências externas e limites de transferência

Comparação de fontes em 02/10/2026. O r8s continua sem HCI funcional:
versão respondeu a115200, mas o primeiro segmento TLV isolado recebeu
`00 1e 03` e foi recusado pelo driver. Esta comparação não executou novos
ensaios no telefone nem mudou firmware, módulos, DT ou configuração Bluetooth.

## Referências examinadas

| Projeto e revisão | Evidência encontrada | Aplicabilidade ao r8s |
|---|---|---|
| [trustin/linux510-qca6390](https://github.com/trustin/linux510-qca6390/tree/80f324e6b738bf693a75f3f6d736b5c857030a22) | Pacote x86/Dell, foco ath11k. O patch0107 altera `btusb_setup_qca`: aceita uma versão ROM não reconhecida quando contém bits acima de16. | Transporte USB, não o caminho UART/TLV do S20. Não justifica aceitar uma resposta TLV inválida. |
| [nlyan2025/manjaro-linux510](https://github.com/nlyan2025/manjaro-linux510/tree/18d1b33566564ac7f7f0359626a368484216d75e) | PKGBUILD x86_64 para5.10.9, fonte externa `v5.10.9-ath`, mesmo patch0107 para `btusb`. | Nenhuma correção local encontrada para o primeiro segmento UART. A árvore de kernel externa desse pacote não foi examinada nesta rodada. |
| [Huabin1010/dagu-mainline-linux](https://github.com/Huabin1010/dagu-mainline-linux/tree/6f1b2f9d04e61378387e73ed367b10ea65545719) | Documenta Bluetooth QCA6390 em uart6,3Mbaud. DTS usa PMU/pwrseq; staging extrai `htbtfw20.tlv` e `htnv20.bin` da própria placa. | Referência de integração UART, sem comprovar compatibilidade dos blobs com r8s. |
| [naughtyGitCat/armbian-oneplus-kebab](https://github.com/naughtyGitCat/armbian-oneplus-kebab/tree/84bc6f0b4ccd0baef512e4b0ae524e52dae860fc) | Delta de alimentação PMU/LDOS e GPIOs de enable para SM8250. Corrige rails inexistentes nessa placa para obter Wi-Fi. | Útil para revisar a propriedade de alimentação; nomes, tensões e GPIOs não devem ser transplantados ao Exynos990. Não é uma correção demonstrada de TLV no S20. |
| [LrkSeraph/xiaomi_pipa_sm8250_kernel_workspace](https://github.com/LrkSeraph/xiaomi_pipa_sm8250_kernel_workspace/tree/6a317fd6f36d2565ede662e81dda02e92ecc5ced) | Workspace Android, com kernel em submódulo. Foram examinados os arquivos `drivers/bluetooth` do submódulo fixado abaixo, sem baixar toolchains/imagens. | Há referências QCA6390/Hastings em SLIMbus e alimentação; o caminho genérico `btqca` examinado é anterior ao suporte específico QCA6390. Não representa o downloader da HAL Android. |

## Dagu: separar inicialização de descoberta

O [script de overlays](https://github.com/Huabin1010/dagu-mainline-linux/blob/6f1b2f9d04e61378387e73ed367b10ea65545719/linux-mainline/scripts/apply-overlays.sh)
altera `hci_qca` para retirar `HCI_QUIRK_SIMULTANEOUS_DISCOVERY` de
QCA6390/ROME. Essa mudança trata descoberta LE/BR depois da inicialização,
e não altera o downloader `btqca` nem explica o erro do primeiro segmento.
As alterações em HCI/BlueZ para HID também dependem de um controlador já
inicializado; não são o próximo teste deste porte.

A carga de `qupv3fw.elf` em SE6 é firmware do controlador serial Qualcomm
GENI. Não é o patch Bluetooth e não se aplica ao controlador serial Samsung
Exynos. O [DTS](https://github.com/Huabin1010/dagu-mainline-linux/blob/6f1b2f9d04e61378387e73ed367b10ea65545719/linux-mainline/dts/sm8250-xiaomi-dagu.dts)
é útil para comparar responsabilidades PMU/pwrseq, mas não para copiar GPIOs.

## Pipa: limite da árvore Android

O workspace aponta para o kernel
[LrkSeraph/xiaomi_pipa_sm8250_kernel, revisão374e6d4](https://github.com/LrkSeraph/xiaomi_pipa_sm8250_kernel/tree/374e6d4e7e10dfa8bf693e39e38d9b8cf4181ee4).
No [btqca.c dessa revisão](https://github.com/LrkSeraph/xiaomi_pipa_sm8250_kernel/blob/374e6d4e7e10dfa8bf693e39e38d9b8cf4181ee4/drivers/bluetooth/btqca.c),
`qca_tlv_send_segment` usa evento vendor, valida tamanho/header/result e
retorna erro se `result !=0`. Não há caminho específico QCA6390 nessa
implementação. As ocorrências Hastings em SLIMbus não fornecem uma tabela
moderna dos erros do download TLV.

Não usar esse parser antigo para reinterpretar silenciosamente `00 1e 03`
como sucesso no caminho QCA6390/mainline. A origem e o significado do byte03
continuam pendentes.

## Próxima investigação

1. Localizar a HAL Qualcomm/Samsung correspondente ao QCA6390/Hastings e
   conferir sequência de baud/wake, contrato dos eventos e downloader TLV.
2. Comparar a origem/revisão e os campos do firmware próprio r8s com o arquivo
   instalado. Nome igual e Product/ROM iguais não provam compatibilidade.
3. Registrar uma hipótese nova antes de outro ensaio finito. Não repetir o
   segmento já medido, enviar outro blob completo por tentativa ou relaxar
   a validação de resposta para habilitar HCI.

O teste de conexão com outro computador só faz sentido depois de HCI básico
funcionar. Nenhum firmware, imagem, endereço Bluetooth ou log bruto acompanha
este documento. O resultado físico anterior está em
[diagnóstico de um segmento](../experiments/qca-first-segment/README.md).

Continuação: [HAL Hastings e diagnóstico UART](QCA6390-HAL-HASTINGS.md)
identificou o offset de status unificado e um ensaio negativo de versão3M.
