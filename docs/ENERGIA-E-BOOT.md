# Energia, religamento e o reinício que não volta

Medições de 14–15/09/2026.

## `systemctl reboot` NÃO volta ao Linux

Falta o nó **`reboot-mode`** no device tree, então o Linux não escreve o motivo
do reinício e o bootloader decide sozinho: o aparelho sobe em **Download Mode** e
precisa de intervenção física.

**Reinício remoto aqui é `systemctl poweroff`** — e ele religa sozinho ao
receber energia (abaixo). Enquanto o `reboot-mode` não existir no DT, `reboot`
fica proibido em operação desacompanhada.

## Religa sozinho com a bateria vazia — mas só em fonte forte

| Situação | Resultado |
|---|---|
| Bateria **cheia**, alimentação presente | **não** liga (não há modo de carga para entrar) |
| Bateria **vazia** + carregador de parede | **liga sozinho em ~10 s** |
| Bateria **vazia** + cabo de PC | liga, roda ~75 s, apaga, repete |

O ciclo no cabo do PC **não é defeito de religamento, é déficit de corrente**:

```
input_current_limit  500 mA        consumo do aparelho ligado  530–600 mA
```

Sem bateria para cobrir a diferença, a tensão cai e ele desliga. No carregador
de parede o limite sobe para 1800 mA e ele carrega +1400 mA enquanto roda.

## Armadilha: o limite de entrada pode desabar para 475 mA

No **mesmo** carregador que antes negociou 1800 mA:

```
online=1   charger status=Charging   health=Good
input_current_limit = 475 mA     corrente = −30 mA  (bateria Discharging)
```

475 mA é o valor conservador de "porta USB comum, tipo desconhecido" — o que o
driver assume quando a detecção não conclui. O aparelho **drena devagar com o
cabo conectado, parecendo carregar**. O atributo é escrivível:

```sh
echo 1500000 > /sys/class/power_supply/max77705-charger/input_current_limit
```

Automatizar isso é perigoso: elevar o teto numa fonte fraca recria o ciclo de
ligar-e-morrer acima.

## Autonomia

**6 h 22 min** de 99% a 3%, com DNS, ponto de acesso, sincronização de arquivos
e telemetria rodando. Uma guarda em software desliga limpo aos 3% — morrer com a
bateria zerada é desligamento sujo, e a raiz herda journal por reproduzir.

## O boot esperava 2 minutos por uma interface morta

Toda `.network` do systemd-networkd **sem** `RequiredForOnline` é **exigida**.
A interface do gadget USB fica em `no-carrier` sem um PC do outro lado do cabo,
então o `systemd-networkd-wait-online` esperava o tempo limite inteiro,
**falhava**, e só então liberava tudo ordenado após `network-online.target`.

Medido: serviços de rede ativos apenas aos **127 s**, com o systemd terminando
em `degraded`. Com carregador de parede — o uso real — isso acontecia em **todo**
boot.

Conserto: `RequiredForOnline=no` na interface do gadget, mais um teto no
`wait-online`. Depois: **8,2 s** de boot, `running`, serviços dentro de 13 s.
