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
ensaio, sem alterar o kernel. **Não foi iniciado nem validado no hardware.**
A propriedade não comprova o clock físico e não ajusta automaticamente DTOUT.

Próximo ensaio: confirmar clock/revisão, medir registradores em host, comparar
imagem controle/candidata com mesmo dispositivo/cabo e VBUS correto, conservar
acesso Wi-Fi e retorno por imagem RAM. Exige periférico físico conhecido.
