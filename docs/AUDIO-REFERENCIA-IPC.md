# Áudio ABOX: limite da fila IPC na referência

Esta análise trata do experimento ABOX de uma referência Exynos990. Não é
suporte de áudio para o r8s, nem diagnóstico da causa de saída silenciosa.
Nenhum firmware, módulo ou alteração de memória do DSP foi usado no telefone.

## Fonte e condição de falha

Referência: [abox-dsp-boot.c, commit 572e7892](https://github.com/Bentlybro/z3s-mainline-linux/blob/572e7892ff651a50e84b4078f460bc8d6bb20210/kernel/drivers/abox-dsp/abox-dsp-boot.c),
funções `check_boot_done` e `dsp_boot_probe`.

A busca por `BOOT_DONE` compara o índice corrente com o índice final da fila.
O corrente avança módulo 128, mas o final não é validado antes da comparação.
Com início válido, final maior ou igual a 128 e nenhum evento correspondente,
o corrente nunca alcança o final. A condição que verifica corrente menor que
128 continua verdadeira, permitindo uma busca sem término.

O prazo de polling do caller e a etapa posterior de colocar os cores em reset
dependem do retorno dessa função. Um timeout externo ao laço interno não
resolve esse caminho. O caller consultado é o probe, com chamadas que dormem;
esta análise não demonstra execução em IRQ ou ocorrência do erro no hardware.

## Verificação somente no computador

A função real extraída da referência foi compilada em C11, sem otimização,
com substitutos de `dram_rd`, `rmb` e da estrutura usada pelo driver. As leituras
sintéticas retornaram início zero, final selecionado pelo teste e nenhum evento.
Cada processo teve um timeout externo de 0,5 segundo, sem acessar dispositivos.

| Início | Final | Resultado do baseline |
| --- | --- | --- |
| 0 | 1 | Retorno zero, sem BOOT_DONE |
| 0 | 128 | Processo excede o timeout |
| 0 | 129 | Processo excede o timeout |

Para reproduzir, copie apenas `check_boot_done` do commit indicado para um
harness C local. Defina `u32` como `uint32_t`, forneça uma estrutura com
`dram_base` não nulo e substitua `dram_rd` por leituras sintéticas dos índices;
os campos dos elementos devem retornar zero. Preserve a função original,
incluindo o incremento módulo 128. Execute cada caso em processo separado e
encerre-o pelo timeout do host. Não injete índices inválidos no DSP real.

Uma cópia com validação de ambos os índices retorna nos três casos, mas retornar
zero para fila inválida ainda mascara erro como ausência de BOOT_DONE. Isso
comprova a condição de loop no harness, não uma correção integrada ao kernel.

## Contrato necessário antes de portar

- Separar status de protocolo e versão do DSP: erro negativo, evento ausente
  ou presente e versão em saída própria. Um erro não pode virar versão positiva.
- Rejeitar índices fora da faixa antes de calcular offsets; manter orçamento
  de varredura finito. Validar stride, último campo e tamanho da região mapeada.
- Confirmar com a ABI a convenção de fila vazia/cheia e final exclusivo,
  endianness, identificação dos eventos e significado de versão zero.
- Definir coerência da memória, barreiras entre índice e elementos e ownership
  em relação ao consumidor IPC. A busca atual observa, mas não avança o início.
- Propagar erro ao caller com cleanup definido de clocks, domínio e DSP;
  sem repetição automática que esconda corrupção da fila.

Um esboço separado, somente host, passou por 16.900 pares de índices de 0 a 129
e casos de wrap, final exclusivo, mensagem fora da janela, versões zero e
UINT32_MAX, fila vazia e saída nula. Builds com ASan/UBSan e com NDEBUG passaram.
Esse esboço usa dados sintéticos e não implementa leitura ou decoding da DRAM;
os resultados não qualificam a ABI, o transporte, o DSP ou reprodução de som.

Mesmo um BOOT_DONE válido não aprova playback ou captura. O porte ainda precisa
das rotas e codecs do r8s e do ciclo PCM/DAI/DAPM coerente com o firmware.
Áudio interno, câmera e estabilidade sustentada continuam pendentes.
