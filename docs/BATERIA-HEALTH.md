# Bateria: falso diagnóstico de sobretensão

No driver max17042, a ausência de `maxim,over-volt` no DT deixa `vmax=INT_MAX`.
Somar a tolerância de 50 mV em um inteiro de 32 bits transborda. A comparação
pode então indicar `Over voltage` mesmo com tensão normal para a bateria.
O patch 0011 promove a soma para s64; não altera carga, tensão ou corrente.

Teste compila a função real do driver com mocks dos acessos ao regmap:

```sh
python3 tests/test-battery-health-overflow.py --source /caminho/linux/drivers/power/supply/max17042_battery.c
```

No arquivo anterior ao patch, `--baseline` reproduz o diagnóstico falso.
A versão corrigida verifica ausência do limite, fronteira, sobretensão real,
subtensão, temperatura e erro de leitura. Build arm64 e boot em RAM passaram;
no hardware, `health` mudou de `Over voltage` para `Good` com tensão semelhante.

Isso corrige a interpretação do indicador. Não certifica segurança da bateria,
calibração do termistor, perfil de carga, limite de 85% ou autonomia.
Conservar a imagem de retorno e não publicar imagens/firmware ou logs locais.

## Indicador separado do carregador MAX77705

O driver MAX77705 pode devolver sucesso após falha de leitura de DETAILS_01,
consumindo uma variável não inicializada. No estado PREQUALIFICATION ele também
retorna sucesso sem definir o valor de saúde. Isso é independente do overflow
do fuel gauge corrigido acima; os dois dispositivos podem mostrar resultados
diferentes sem que a origem da divergência esteja determinada.

O patch `0014-max77705-health-read.patch` propaga o erro de regmap e define
`UNKNOWN` para PREQUALIFICATION. A escolha conserva a incerteza desse estado,
sem forçar `Good` ou contornar proteções. Não muda corrente, tensão, PD ou OTG.

```sh
python3 tests/test-max77705-health.py --source /caminho/max77705_charger.c
# Na fonte anterior ao patch:
python3 tests/test-max77705-health.py --source /caminho/baseline.c --baseline
```

O teste compila a função real com mock: oito estados BAT_DTLS, bits externos
ao campo, saída definida e propagação de erro I/O. A baseline reproduz o erro
ignorado e a saída residual; a correção passa sob ASan/UBSan. O arquivo completo
corrigido compilou como objeto arm64 com W=1, sem avisos. Aplicação do patch sem
fuzz reproduziu exatamente essa fonte, preservando a árvore de kernel original.

**Ainda não carregado no aparelho.** Não atribuir a ele a causa do aviso atual
nem aprovação de carga. O atributo `online` usa outra função: leitura de INT_OK
com erro propagado, seguida de CHGIN_OK. Corrigir health não torna essa entrada
válida nem estabelece o contrato PD. A alimentação pelo hub exige investigação
e validação física próprias.

## CHGIN, polling e AICL na configuração atual

O nó do carregador no DT aplicado não declara interrupção. No driver, isso
seleciona `max77705_poll_work`: lê CHGIN_OK e notifica mudanças de `online`.
Esse polling não negocia PD nem ajusta o limite de entrada. CHGIN IRQ, quando
presente, também apenas agenda uma notificação ao subsistema power supply.

O handler AICL do código reduz o campo de corrente em um loop sem limite
explícito de rodadas e sem verificar zero antes de decrementar o inteiro sem
sinal. São pontos que exigem correção e contrato de limites próprios. Contudo,
o probe registra esse handler apenas quando há IRQ; ele não é o caminho
selecionado pelo DT atual. Isso afasta aquele loop de software como explicação
do estado observado, sem excluir regulação AICL autônoma dentro do PMIC.

Outro getter, `max77705_get_input_current`, ignora o retorno de
`regmap_field_read` antes de usar o resultado. Um erro pode ser apresentado
como limite de corrente em vez de erro I/O. Esse defeito é separado do patch
0014 e é tratado no candidato 0015 abaixo. Uma leitura de limite não mede corrente
real, capacidade da fonte ou potência negociada por PD.

## Erros de leitura de limites de corrente e tensão

O mesmo erro ignorado existe em `max77705_get_charge_current` e
`max77705_get_float_voltage`. Os dois getters de corrente podem consumir saída
não inicializada; o de tensão inicializa seu campo com zero e pode informar
4 V como sucesso após uma falha, sem que esse seja o valor lido.

O patch `0015-max77705-getters-read-errors.patch` verifica as três leituras e
propaga o erro antes de converter dados ou escrever a saída. O dispatcher de
propriedades já devolve diretamente esses retornos. As conversões bem-sucedidas
e todos os setters permanecem iguais; não há ajuste de tensão/corrente ou PD.

```sh
python3 tests/test-max77705-getters.py --source /caminho/max77705_charger.c
# Na fonte anterior ao patch 0015:
python3 tests/test-max77705-getters.py --source /caminho/baseline.c --baseline
```

Testes das funções reais reproduziram os três erros na baseline e passaram
na correção sob ASan/UBSan: fronteiras de conversão, EIO e timeout, uma leitura
por chamada e saída preservada em erro. A cópia completa com 0014+0015 compilou
como objeto arm64 W=1, sem avisos. Os patches aplicados em sequência sem fuzz
reproduziram exatamente a fonte compilada; a fonte original foi preservada.
A revisão do Claude sobre os trechos e a estratégia foi conferida localmente.
**Não carregado no aparelho; causa da ausência de carga ainda não determinada.**

Após a correção, consumidores precisam tratar erros de leitura em vez de
receber valores fabricados. No núcleo usado aqui, `add_prop_uevent` ignora
ENODEV/ENODATA, mas propaga outros erros negativos; uma falha transitória pode
impedir a emissão desse evento de propriedades. Não converter EIO em sucesso
para esconder isso nem usar uma falha de leitura como autorização para elevar
o limite de corrente.
