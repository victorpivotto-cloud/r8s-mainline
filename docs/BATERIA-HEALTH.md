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
