# USB host: comparação de temporização

Enumeração física continua falhando (-71). Carregar ALSA USB ou UVC não resolve
isso. As observações abaixo reduzem hipóteses; não são correção validada.

Referência de código Samsung derivada:
[ExtremeXT, core.c, commit 69515fbb](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/usb/dwc3/core.c),
[core.h](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/usb/dwc3/core.h).

`dwc3_core_config` escolhe REFCLKPER por revisão Exynos9830: EVT1 usa 50,
EVT0 usa 15. `dwc3_frame_length_adjustment` usa em EVT1 DECR=12, FLADJ=0,
LPM_SEL=1; em EVT0 DECR=10, FLADJ=2032. Confirmar revisão e clock efetivo
antes de escolher valores; não transplantar o clock do pai para o filho DWC3.

No ensaio do FE, em **peripheral**, debugfs mostrou:

| Campo | Leitura | Referência vendor EVT1 |
|---|---:|---:|
| GUCTL REFCLKPER | 41 | 50 |
| GUCTL DTOUT | 2047 | 200 (DT stock) |
| GUCTL NOEXTRDL | 1 | 1 |
| GUCTL USBHSTINAUTORETRYEN | 1 | 1 |
| GFLADJ 240MHZDECR | 10 | 12 |
| GFLADJ REFCLK_FLADJ | 2032 | 0 |
| GFLADJ REFCLK_LPM_SEL | 1 | 1 |
| GFLADJ ajuste30MHz | 32 | 32 |

No-extra-delay e autoretry já estavam ativos; ajuste30MHz já era 0x20.
Os demais valores diferem, mas precisam ser medidos em **host** antes de
atribuir a eles a falha. Não considerar PHY completamente qualificada em host
só porque a mesma PHY funciona no gadget.

O script `scripts/decode-dwc3.py` decodifica um regdump salvo. Não escreve
registradores nem acessa `/dev/mem`. Capturar usando a interface do driver:

```sh
cat /sys/kernel/debug/usb/10e00000.usb/regdump > regdump-local.txt
python3 scripts/decode-dwc3.py regdump-local.txt
```

Caminho depende do device/debugfs; não montar ou trocar papéis USB durante
uma coleta de qualificação. Manter o regdump operacional local.

No mainline usado aqui, propriedades `snps,ref-clock-period-ns = <50>` e
`snps,gfladj-refclk-lpm-sel-quirk` no nó DWC3 calculam DECR=12 e FLADJ=0
quando não há ref_clk direto. Foi preparado um candidato de DT para esse
ensaio, sem alterar o kernel. **O candidato peripheral foi iniciado em RAM**: REFCLKPER=50, DECR=12,
FLADJ=0 foram lidos no debugfs; gadget/RNDIS continuou acessível. O retorno
à imagem de controle também passou. Isso verifica aplicação das propriedades
e funcionamento básico do gadget, sem aprovar host ou confirmar o clock físico.
A propriedade não comprova o clock físico e não ajusta automaticamente DTOUT.

Próximo ensaio: confirmar clock/revisão, medir registradores em host, comparar
imagem controle/candidata com mesmo dispositivo/cabo e VBUS correto, conservar
acesso Wi-Fi e retorno por imagem RAM. Exige periférico físico conhecido.

## Hub alimentado e papel USB

Foi disponibilizado um hub Orico PW11-9P, carregador Samsung na entrada PD
e pendrive em uma porta USB. O usuário confirmou alimentação pelo hub;
as leituras do Linux variaram entre `online=1/Full` e `online=0/Discharging`.
Isso não mede potência negociada nem confirma alimentação contínua.

O controle atual declara `dr_mode = "peripheral"`, com DWC3 em `device` e
barramento host vazio. Em `dwc3_mode_write`, uma escrita em debugfs retorna
sucesso sem trocar o papel quando `dr_mode` não é OTG. Portanto escrever
`host` nessa interface não é um teste válido nesta configuração.

Foi preparado, **sem carregar**, um candidato baseado no mesmo kernel e
ramdisk do controle: altera somente o papel do DT para `host`, sem ajustes
de temporização, e acrescenta `systemd.mask=otg-vbus.service` à linha de
comando desse boot. A máscara é temporária e evita o serviço legado ligar
OTG/BOOST enquanto o ensaio usa alimentação externa. Nenhuma configuração
instalada, partição ou registrador do carregador foi alterado.

O ensaio ainda exige fastboot com ligação direta ao computador, reconexão
do hub, alimentação externa conferida, leitura de enumeração sem montar ou
escrever no pendrive e retorno ao controle em RAM. A imagem é local;
host, carga simultânea e PD negociado continuam sem aprovação.

## Habilitar carga não comprova negociação PD

A rotina [`chg_init_max77705` do lk3rd](https://github.com/exynos990-mainline/lk3rd/blob/00e2a415232d8f97d35d730c66b194b7e878b06c/dev/battery/charger/chg_max77705.c)
lê `0xB7`, escreve o valor com o bit CHG habilitado e imprime leituras de
`0xB7` e `0xC3`. Na tabela usada pelo driver Linux, esses endereços correspondem
a `CNFG_00` e `CNFG_12`. Essa rotina não solicita contrato PD nem configura
limite de corrente de entrada. A implementação I2C consultada não devolve
erro ao chamador; as mensagens impressas não bastam para validar a operação.
Isso descreve essa rotina, sem excluir negociação em outras etapas do boot.

No driver standalone, `max77705_charger_initialize` substitui o campo MODE
por CHG|BUCK e configura outros parâmetros do carregador. A escrita de
`MAX77705_OTG_ILIM_900`, em `CNFG_02[7:6]`, limita a **saída OTG**; não define
a corrente de entrada CHGIN nem comprova disponibilidade de 900 mA na fonte.
Essa função não escreve o limite de entrada nem a corrente de carga rápida.
Os comentários sobre valores padrão não são medições dos valores efetivos;
outros caminhos de software ou o hardware podem alterar esses campos.

`max77705_get_online` lê CHGIN_OK, com propagação do erro de leitura.
`online=0` informa que o carregador não marcou essa entrada como válida;
não mede VBUS nem identifica a causa. `online=1` também não informa contrato,
tensão ou potência PD. Sem IRQ, `max77705_poll_work` apenas notifica mudanças
desse indicador. O carregador standalone e esse polling não fornecem, por
si, a integração de CC/PD e troca de papel USB.

Para qualificar periféricos com carga simultânea, ainda é necessário verificar
separadamente contrato/alimentação de entrada, papel de dados host, enumeração
e saldo da bateria. Não deduzir corrente segura pela capacidade nominal do
carregador, pelo limite OTG ou pela existência de AICL. A origem de
CHGIN_OK desassertado e o estado do controlador CC/PD continuam em aberto.

O mapa inicial de papéis, protocolo e dependências está em
[USB-C-PD-DEPENDENCIAS.md](USB-C-PD-DEPENDENCIAS.md).
