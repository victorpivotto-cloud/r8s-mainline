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
não chama o controlador DWC3 nem um USB role switch. O consumidor da cadeia
CCIC e sua ligação ao controlador ainda precisam ser mapeados. A manutenção
do papel de energia e o controle de OTG/BOOST exigem análise própria.

O `max77705_usbc_probe` vendor recebe do pai os clientes I2C do PMIC e a base
de IRQs. O porte atual do carregador standalone não fornece essa integração.
Copiar apenas os arquivos CC/PD não substitui transporte, demultiplexação de
interrupções, consumidores das notificações e tratamento de desconexão/erros.
Não copiar rotinas de atualização de firmware ou política de corrente para
contornar essas dependências.

Próximo passo de fonte: rastrear os consumidores USB, MUIC e bateria dessas
notificações, comparar com as interfaces do kernel base e definir o escopo
mínimo do porte. Em hardware, a aprovação continua exigindo confirmação de
alimentação, papel host e enumeração, seguida de saldo da bateria e retorno
ao controle. Nenhum código CC/PD desta referência foi carregado no r8s.
