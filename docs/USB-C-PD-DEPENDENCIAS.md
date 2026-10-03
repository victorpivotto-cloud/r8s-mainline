# USB-C: host de dados com alimentação externa

O objetivo é operar como host de dados (DFP), recebendo energia (SNK).
A referência Samsung derivada representa esses papéis separadamente e contém
um ramo explícito DFP+SNK em `max77705_datarole_irq_handler`. Isso oferece
uma referência para o porte; não valida o hub nem a implementação no r8s.

Fontes fixadas no commit `69515fbb7a4395898c05a8624f76a12afbac11c5`:

- [max77705_pd.c](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/usb/typec/maxim/max77705/max77705_pd.c)
- [max77705_cc.c](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/usb/typec/maxim/max77705/max77705_cc.c)
- [max77705_usbc.c](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/usb/typec/maxim/max77705/max77705_usbc.c)

| Caminho da referência | Função | Limite da evidência |
|---|---|---|
| Pedido de energia | `max77705_select_pdo` → fila de opcodes USBC | PDO solicitado não é necessariamente o ativo |
| Confirmação de energia | IRQ PS_RDY → `max77705_check_pdo` | Precisa conferir contrato ativo e entrada do carregador |
| Papel de dados | IRQ de data role → `max77705_notify_dr_status` → notificador CCIC | Precisa de consumidor que comande o controlador USB |

`max77705_response_pdo_request` descreve a resposta zero como pedido enviado.
Ela não confirma o contrato final. A referência mantém um caminho posterior
de PS_RDY e consulta de PDO; registrar somente o pedido ou seu ACK seria
insuficiente para aprovar a alimentação.

No ramo DFP, `max77705_ccic_event_work` informa `TYPEC_HOST` preservando um
campo separado para o papel de energia e enfileira a notificação USB.
No kernel base, `typec_set_data_role` atualiza a classe e emite eventos;
não chama o controlador DWC3 nem um USB role switch. A ligação vendor
identificada abaixo usa notificadores e uma máquina de estados própria;
não está estabelecida como implementação funcional no kernel base.

O `max77705_usbc_probe` vendor recebe do pai os clientes I2C do PMIC e a base
de IRQs. O porte atual do carregador standalone não fornece essa integração.
Copiar apenas os arquivos CC/PD não substitui transporte, demultiplexação de
interrupções, consumidores das notificações e tratamento de desconexão/erros.
Não copiar rotinas de atualização de firmware ou política de corrente para
contornar essas dependências.

## Consumidores vendor identificados

No mesmo commit, [usb_notifier.c](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/usb/notify/usb_notifier.c)
registra `ccic_usb_handle_notification` diretamente na cadeia CCIC ou no
Type-C manager, conforme a configuração. O evento DFP vira `NOTIFY_EVENT_HOST`.
O callback `set_host` da estrutura `dwc_lsi_notify` aponta para `exynos_set_host`;
ele usa `check_usb_id_state(0)` para chamar `dwc3_exynos_id_event`.

Em [dwc3-exynos.c](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/usb/dwc3/dwc3-exynos.c),
esse último caminho altera `fsm->id` e agenda um trabalho que chama
`dwc3_otg_run_sm`. A cadeia depende de registro, configuração, dispositivo
encontrado e FSM inicializada. Há etapas assíncronas; emitir o evento ou
retornar sucesso no callback não demonstra host operacional nem enumeração.

A saída de energia usa outro callback, `vbus_drive`, dirigido ao power supply
vendor `otg`. Com CCIC habilitado, o inicializador consultado deixa
`auto_drive_vbus` em zero, que corresponde a `NOTIFY_OP_OFF` no
[header](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/include/linux/usb_notify.h).
Em [usb_notify.c](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/usb/notify/usb_notify.c),
esse modo evita os acionamentos automáticos PRE/POST, mas mantém uma exceção
para papel SOURCE com booster reservado e host permitido. Portanto OFF não
significa impossibilidade de acionar VBUS. Não transplantar o modo sem mapear
quem mantém o papel de energia e a reserva; DFP sozinho não comprova SOURCE.

Os consumidores de MUIC e bateria são distintos. O handler de attach
[max77705-muic-ccic.c](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/muic/max77705-muic-ccic.c)
salva `rprd` e agenda outro trabalho; esse trecho não basta para concluir que
ele liga BOOST. O [sec_battery.c](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/battery_v2/sec_battery.c)
consome POWER_STATUS e informações de PDO em uma política própria; a rotina
de corrente escreve propriedades do carregador e inclui tratamento térmico.
Ela não é um ajuste de corrente que possa ser copiado isoladamente.

Próximo passo de fonte: mapear o estado de energia/reserva, o trabalho MUIC
e as dependências de transporte/IRQ; comparar as interfaces vendor com as do
kernel base e definir o escopo mínimo do porte. Em hardware, a aprovação exige
confirmação de
alimentação, papel host e enumeração, seguida de saldo da bateria e retorno
ao controle. Nenhum código CC/PD desta referência foi carregado no r8s.
