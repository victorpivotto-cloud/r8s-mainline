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

## Falso Charging com a carga desabilitada

`max77705_get_status` usa `POWER_SUPPLY_CHARGE_TYPE_NONE` quando CHG_EN é
zero. Esse valor vale 1; na enumeração de status, 1 significa `Charging`.
O patch `0016-max77705-status-presence-errors.patch` usa `STATUS_NOT_CHARGING`
nesse ramo. Ele também propaga erros das leituras de status, tipo de carga e
presença de bateria antes de consumir dados ou definir a saída.

`Not charging` aqui descreve o motor de carga desabilitado; não é uma medição
do fluxo da bateria, nem uma escolha automática entre carga e descarga.
As demais decodificações bem-sucedidas e todos os controles permanecem iguais.
Não foi demonstrado que esse ramo produziu o estado observado no aparelho.

```sh
python3 tests/test-max77705-status.py --source /caminho/max77705_charger.c
# Na fonte anterior ao patch 0016:
python3 tests/test-max77705-status.py --source /caminho/baseline.c --baseline
```

O teste das funções reais reproduziu o falso Charging e os erros ignorados.
A correção passou sob ASan/UBSan: carga desabilitada, 16 estados, combinações
de presença, EIO/timeout em cada etapa e interrupção das leituras após erro.
O objeto completo arm64 W=1 compilou sem avisos; a série 0014..0016 sem fuzz
reproduziu a fonte compilada. A revisão do Claude foi conferida localmente.
**Validação apenas no host, sem carregar no S20.** Não corrige negociação PD,
detecção de entrada nem a causa ainda indeterminada de `online=0`.

## Carregador Charging e bateria Discharging

Os dois atributos usam caminhos diferentes. `max77705_get_status` decodifica
CHG_EN e CHG_DTLS; isso não mede o saldo de corrente da bateria. Já
`max17042_get_status` consulta `power_supply_am_i_supplied`, verifica o critério
de carga completa e, quando a medição de corrente está habilitada, lê
AvgCurrent. Fora do ramo Full, corrente média positiva resulta em Charging;
zero ou negativa resulta em Discharging, mesmo com alimentação reconhecida.
No caminho DT, `maxim,rsns-microohm` habilita essa medição.

Há outra limitação no núcleo desta base: `__power_supply_am_i_supplied` conta
o fornecedor associado, mas retorna zero quando a leitura de ONLINE falha.
Se nenhum outro fornecedor retornar alimentação presente, o medidor recebe
zero e informa Discharging. A ausência de fornecedor associado retorna
ENODEV, que esse getter do medidor traduz para Unknown. Portanto, uma leitura
isolada de `online=1` não confirma qual ramo foi usado numa consulta diferente
do status da bateria; as leituras também não são uma captura atômica.

Para distinguir os casos, uma futura coleta acompanhada precisa registrar
associação ao fornecedor, configuração de medição, erros de leitura, corrente
média e tendência de carga junto aos estados do carregador. Esses caminhos
de fonte não demonstram a causa no aparelho nem justificam elevar corrente,
desabilitar a guarda de bateria baixa ou declarar carga PD aprovada.

## Codificação dos limites de corrente

O setter de INPUT_CURRENT_LIMIT dividia o pedido por 25 mA sem descontar
o offset do campo. Um pedido de 1,8 A gerava código72, lido como1,825 A.
No máximo de3,2 A, o código128 excedia o campo de7bits e podia ser mascarado
para0, lido como100 mA. O setter de CONSTANT_CHARGE_CURRENT também reutilizava
o teto3,2 A: com passo50 mA, código64 excedia seu campo de6bits.

`0017-max77705-current-setters.patch` corrige o offset da entrada e limita
a corrente de carga a3,15 A, maior valor representável no campo. Pedidos não
alinhados continuam arredondados para baixo; o mínimo permanece100 mA.
Não altera os pedidos da política de carga nem negocia PD. A codificação
concorda com os setters do driver vendor de referência e os getters desta base.

```sh
# Após aplicar a série 0014..0017 na base documentada:
python3 tests/test-max77705-setters.py \
  --source /caminho/drivers/power/supply/max77705_charger.c \
  --header /caminho/include/linux/power/max77705_charger.h
```

O teste extrai as funções reais e usa stubs de campos com máscara em bit0;
confere6.200.019 roundtrips, limites inteiros, códigos exatos de referência,
bits vizinhos e errosEIO/timeout sob ASan/UBSan. O stub de clamp reproduz os
argumentos int desta base; não substitui os checks de compilação do kernel.
Objeto arm64 W=1 compilado sem avisos; aplicação da série sem fuzz reproduziu
exatamente fonte e header compilados. Revisão do Claude conferida localmente.
**Somente validação no host, não carregado no S20.** Não demonstra que um
pedido máximo ocorreu no aparelho nem determina a causa da falha com hub.

## O intervalo da corrente média

`max17042_get_property` exporta `CURRENT_AVG` lendo o registrador
`AvgCurrent`; o driver não calcula uma média das coletas feitas pelo host.
A frequência de coleta, portanto, não define o intervalo dessa média.

O [datasheet MAX17047/MAX17050, revisão 7](https://www.analog.com/media/en/technical-documentation/data-sheets/max17047-max17050.pdf)
descreve, nas páginas 24 e 38, um filtro configurável por `FilterCFG.CURR`:
o intervalo vai de aproximadamente 0,7 s a 6,4 h; a constante de tempo no valor
padrão de power-on é 11,25 s. Isso é a configuração padrão documentada, não
uma medição da configuração atual de um aparelho. O datasheet também indica
que a última média é preservada durante shutdown do medidor.

Nesta base, `max17042_write_config_regs` e `max17042_override_por_values`
podem escrever `FilterCFG` a partir de `config_data`. Esses caminhos de fonte
não demonstram qual valor está ativo no hardware. Não assumir o padrão nem
atribuir horas de defasagem sem conhecer a configuração efetiva.

Uma comparação de alimentação deve preservar corrente instantânea, média,
SOC e seus instantes separadamente. Um ensaio de 30 s pode verificar dados e
erros de acesso, mas não garante acomodação do filtro desconhecido ou carga
sustentada. Essa ressalva não autoriza mudar `FilterCFG`, corrente ou guardas.
