# Toque e ambiente gráfico no r8s — estado em 2026-09-13

## Resumo honesto

**Display: funciona.** **Toque: chega até o último metro e para lá.**

## Display

```
[drm] Initialized simpledrm 1.0.0 for f1000000.framebuffer
simple-framebuffer: [drm] fb0: simpledrmdrmfb frame buffer device  1080x2400
```

O bootloader acende o framebuffer e o `simpledrm` o adota. **Isso basta para um
compositor Wayland mínimo** (Sway, Weston, labwc) — é instalação de pacote, não
porte. Para KDE/aceleração entra o Mali G77 via Panfrost, e o patch do z3s que
já aplicamos traz o modelo do G77 e o fix do domínio G3D.

Limite: o framebuffer é **estático**, aceso pelo bootloader. Sem controle de
brilho, sem mudança de modo, sem desligar a tela. Isso exigiria DECON/DSIM de
verdade — que no próprio z3s está como "em progresso", não resolvido.

## Toque — o que foi descoberto e provado

Tudo lido do `dtbo.img` de estoque **deste** aparelho, não presumido do z3s:

| | |
|---|---|
| Barramento | `hsi2c_15` (i2c@108d0000) — fixups: `hsi2c_15 = '/fragment@50:target:0'` |
| Pinos I2C | `gpp5-6` / `gpp5-7` |
| Interrupção | `gpa1-0`, `samsung,pin-function = <0xf>` (EINT) |
| Alimentação | `regulator-fixed` `tsp_ldo_en` em **`gpm21`**, 3,0 V, ativo alto |
| Chip | **Zinitix ZT7650** @ `0x20` |

**O chip foi identificado por medição, não por leitura de tabela:** o estoque
declara *dois* candidatos (zinitix @0x20 e ST fts5cu56a @0x49), e o
`i2cdetect -y 0` no aparelho mostrou **apenas 0x20 respondendo**.

Diferença importante em relação ao z3s: lá o toque dependia do sub-PMIC
**S2DOS05**, que este aparelho **não tem** — aqui é um LDO simples por GPIO.

### O que funciona

```
input: Zinitix Capacitive TouchScreen as .../i2c-0/0-0020/input/input1
driver ligado: Zinitix-TS     reguladores: tsp_vdd, tsp_avdd, tsp_ldo_en
57:  8205  gpa1  0  Level  bt541        <- a interrupcao DISPARA
```

Alimentação, I2C, pinctrl e linha de interrupção: **todos de ponta a ponta**.

### Onde para

```
irqs antes 5130 -> depois 8205   (3075 interrupcoes em 15 s, ~205/s)
bytes de evento no /dev/input/event1: 0
```

A interrupção dispara continuamente **mesmo sem ninguém tocar**, e nenhum evento
chega ao evdev. É a assinatura de protocolo incompatível: o driver `zinitix` do
mainline suporta bt402/403/404/412/413/431/432/531/532/538/541/548/554 e at100 —
**não o zt7650**. Amarramos como `zinitix,bt541` (mesma família), e o driver nem
lê o dado nem consegue baixar a linha, que por isso fica presa.

### Duas armadilhas resolvidas no caminho

1. **`IRQ_TYPE_EDGE_FALLING` dá `-22`.** O wakeup-eint do `gpa1` não aceita esse
   gatilho nesse pino. Com **`IRQ_TYPE_LEVEL_LOW`** (o que o z3s usa) o probe
   passa. Uma constante, três iterações.
2. **Dois nós de toque no mesmo pino quebram o pinctrl** ("Error applying
   setting, reverse things back"): dois donos disputando `gpa1-0`. Depois do
   `i2cdetect` ficou só o que existe.

### Para fazer o toque funcionar de verdade

Portar o protocolo do ZT7650 para o driver `zinitix`, usando o driver
downstream da Samsung como referência (`zinitix,zt_ts_device`, firmware
`tsp_zinitix/zt7650_r8.bin`). É trabalho de driver, não de device tree — e é
sessão própria.

## Brinde

As **teclas físicas** também ficaram registradas e com interrupção própria:

```
68:  gpa2 4  Edge  Power
69:  gpa0 4  Edge  Volume Down
70:  gpa0 3  Edge  Volume Up
```
