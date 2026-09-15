# Console, `simpledrm` e uma armadilha que congela o PID 1

**Este é o achado mais importante dos dois dias, e o que menos aparece
documentado em outro lugar.** Vale para qualquer telefone rodando mainline com
o console sobre `simpledrm`.

## O sintoma

O aparelho continua respondendo **ping, DNS e HTTP**, com latência de
microssegundos — e fica **impossível de administrar**:

| Funciona | Não funciona |
|---|---|
| ping, TCP, banner do SSH | abrir sessão SSH (`logind: Connection timed out`) |
| serviços já residentes | qualquer `systemctl` |
| arquivos servidos do disco | desligar por software |

Tudo que funciona é feito por processo **já residente**. Tudo que falha precisa
do **PID 1**. Só sai com corte de energia por hardware (`Power` + `Volume Down`).

Aconteceu duas vezes no mesmo dia, somando ~2h20 de indisponibilidade.

## A causa

**Parar ou reiniciar o `getty@tty1` congela o systemd.** A última linha que o
PID 1 registra é sempre a mesma:

```
systemd[1]: Stopping getty@tty1.service ...
systemd[1]: Stopped getty@tty1.service
            (silêncio para sempre)
```

Duas travadas, **dois chamadores diferentes** — uma de dentro de um `ExecStart`,
outra de um filho do `triggerhappy`. Portanto **não** é "chamar `systemctl` de
dentro de uma unit", que foi a primeira generalização e estava errada. É mexer
na unit de `getty`.

Casa com o estado do vídeo: o console fica sobre `simpledrm`, que **não
implementa `fb_blank`** — `/sys/class/graphics/fb0/blank` vem **vazio**. Soltar
a TTY trava o caminho de VT/fbcon e o systemd espera para sempre.

## Como apagar a tela sem tocar no `getty`

Pintar o framebuffer de preto **não basta**: o console do VT 1 repinta em
seguida. A saída é trocar para um terminal virtual **vazio**, onde não há nada
para redesenhar:

```sh
# apagar
chvt 2                                        # VT sem getty
dd if=/dev/zero of=/dev/fb0 bs=4320 count=2400

# acender
chvt 1
printf '\033[H\033[2J' > /dev/tty1            # limpa
cat /etc/issue        > /dev/tty1             # escreve o que se quer mostrar
```

Precisa do pacote `kbd` (`chvt`, `fgconsole`). Zero chamadas ao gerenciador de
serviços. Verificado com 10 alternâncias seguidas, `systemd running` em todas.

Num painel **Super AMOLED**, pixel preto é pixel desligado — isso economiza
energia de verdade, não só esconde. Não há `/sys/class/backlight` neste
aparelho: o painel está aceso pelo bootloader e não há driver de display.

## Regra que fica

Em porte com vídeo pela metade, **o subsistema de VT/console é terreno minado**.
Preferir escrever direto em `/dev/ttyN` e `/dev/fb0` a manipular units de
`getty`.

E **monitoramento que só pergunta "responde?" fica verde durante a falha
inteira** — o teste de vida tem que exigir algo que dependa do PID 1.
