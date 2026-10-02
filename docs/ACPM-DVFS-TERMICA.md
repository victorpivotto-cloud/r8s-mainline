# ACPM, DVFS e proteção térmica no r8s

## Sintoma e correção

Mudanças de frequência nos três clusters competiam pelo canal ACPM 5 de
slot único. O sintoma era `Failed to change cpu frequency: -110`.
O patch 0007 mantém ownership do slot até consumir a resposta, limpa o bit
reservado quando o envio falha e faz readback após limpar o ACK de MMIO.
O patch 0008 serializa a transação inteira no cpufreq, incluindo atualização
do cache, com um mutex compartilhado pelos clusters. Erros continuam sendo
propagados; o cache não muda quando a transação falha.

Mock concorrente da função real: baseline com sobreposições, correção com zero;
falha de envio libera o bit de sequência. Isso não resolve nem comprova ausência
de resposta tardia após timeout. A validação prolongada no hardware está pendente.

Os patches dependem do provider ACPM e cpufreq do porte Exynos990 de referência,
não existem no upstream 6.12 puro. Baselines SHA256 antes destes patches:

- exynos-acpm.c: `5deba5bd7b6213a930b24dd31d55fc9cc4c57a694a994121a233a2d637fd2411`.
- exynos990-cpufreq.c: `ba32e791e6c8b247cf9e87cac42cb9ea1ac11663651a93eb7927aa5ca964274a`.

## Leitura térmica e cooling

`drivers/runtime/r8s-acpm-thermal.c` usa somente READ_TEMP no canal ACPM 9,
IDs 0–5: BIG, MID, LITTLE, G3D, ISP e NPU. Expõe hwmon `r8s_acpm` e três zonas
CPU. Não envia INIT, controle do firmware, desligamento, IRQ ou escrita direta
em registradores térmicos. Leitura inválida retorna erro, não temperatura zero.

Cooling passivo das CPUs: 83 °C, histerese 5 °C, polling de um segundo.
BIG/MID seguem o trip passivo observado no DT stock; **83/5 para LITTLE é uma
política provisória deste projeto**, não um trip stock validado.
GPU/ISP/NPU são telemetria apenas. Os sensores ainda precisam de calibração
externa, e o desligamento crítico/Tshut não foi comprovado.

O binding reconhece a faixa de CPUs de cada cluster, incluindo uma CPU
representante diferente após hotplug. O patch cpufreq registra e remove seus
cooling devices sem manter o mutex de segurança durante callbacks térmicos.

## Sensor ausente ou travado

O driver cpufreq possui um pedido FREQ_QOS_MAX próprio, separado do governador
térmico. Três leituras inválidas ou heartbeat ausente por mais de cinco segundos
limitam o cluster afetado à menor frequência da tabela. Recuperação exige três
leituras válidas abaixo de 78 °C. Remover o módulo térmico limita todos os
clusters; sua dependência de símbolos impede descarregar o cpufreq enquanto
os sensores estiverem carregados.

`/sys/module/exynos990_cpufreq/parameters/failsafe_mask`: bits 1 LITTLE,
2 MID e 4 BIG; zero indica leituras/heartbeat saudáveis, **não certificação de
proteção crítica**. `fault_mask` do módulo térmico é injeção de erro para testes,
root-only e zerada por padrão; bits 1 BIG, 2 MID, 4 LITTLE.

## Compilar e validar

Aplicar os patches 0007/0008 ao baseline correspondente e compilar o kernel
com ACPM, cpufreq Exynos990, CPU thermal cooling e hwmon. Depois:

```sh
make -C /caminho/kernel ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
  M="$PWD/drivers/runtime" modules
```

O kernel deve exportar o provider ACPM e `exynos990_cpufreq_sensor_report`.
Instalar módulos na árvore da **mesma release/vermagic**, executar depmod e
usar modprobe. Manter uma árvore de módulos separada para a imagem de retorno.
Não carregar um `.ko` de outra release por insmod.

Os scripts `tests/test-thermal-emulation.sh` e `tests/test-sensor-failsafe.sh`
passaram no r8s: emulação 86 °C limita, 81 °C mantém a histerese e emulação zero
restaura; falha de sensor/polling/unload limita e recuperação restaura. Os traps
limpam emulação/injeção e tentam restaurar o módulo compatível. Eles pressupõem
os limites/frequências desta tabela r8s, não são testes universais para Exynos.
Não geram workload de aquecimento. Ainda falta qualificação sob carga sustentada.

O mock pode ser reproduzido assim:

```sh
python3 tests/test-dvfs-serialization.py \
  --baseline /caminho/arvore-sem-patches --kernel /caminho/arvore-corrigida
```

Ele compila as funções C reais e usa mailbox simulado; não valida firmware.

## Correção adicional: modo e ciclo de vida

Revisão posterior confirmou que leituras manuais de thermal/temp podiam
renovar heartbeat e liberar recuperação com a zona desabilitada. Três leituras
muito rápidas também podiam satisfazer o contador de recuperação.

`patches/0010-thermal-mode-hwmon.patch` acompanha change_mode,
força clamp ao mudar modo, recusa get_temp de zona desabilitada e espaça
amostras boas em pelo menos um segundo. Usa unregister explícito do hwmon
nos caminhos erro/exit: o platform_device é criado sem platform_driver,
então não se deve depender só de devres e referências para remover interfaces
que chamam código do módulo antes do unload.

O patch registra o delta sobre o módulo no commit 9a2c040; o fonte runtime
atual já inclui essa correção. Não reaplicar ao fonte atual. Não muda o provider ACPM.
Compilação arm64 para #25 e mock das funções C reais passaram. Segunda revisão
por Claude não encontrou bug concreto no caminho principal. A correção foi instalada no #25 em RAM. Disable com leituras manuais,
recuperação com amostras espaçadas e dois ciclos unload/reload passaram
no aparelho, com zero hwmon após unload e exatamente um após reload.
Regressão de falhas de sensores, polling, unload e emulação 86/81/zero
também passou nos três clusters, com máscaras limpas ao final.
A coleta anterior foi encerrada como incompleta para testar a correção;
a qualificação prolongada da versão corrigida ainda está pendente.

Para testar as funções depois de aplicar o patch numa cópia:

```sh
python3 tests/test-thermal-health.py --source /copia/r8s-acpm-thermal.c
```

O script `tests/test-thermal-mode-hwmon.sh` reproduz disable + leituras manuais,
enable/recuperação e unload/reload com confirmação do ciclo de vida do hwmon.
Depois de trocar o módulo, reiniciar a qualificação. Backoff/desabilitação do
core em erro persistente pode exigir re-enable explícito. Essa correção não
resolve late ACK, calibração, falta de watchdog ou causa do reset.


## ACK tardio: lacuna reproduzida em simulação

O teste `tests/test-single-slot-late-ack.py` extrai e compila a função real
`acpm_wait_for_singleslot_response` do provider corrigido. O controle com ACK
correspondente conclui normalmente. Após simular timeout do comando 1 e seu
ACK durante o comando 2, a função aceita o ACK antigo, limpa a interrupção e
libera a sequência do comando 2. O caso sem payload RX também reproduz isso.

```sh
python3 tests/test-single-slot-late-ack.py \
  --source /caminho/kernel/drivers/firmware/samsung/exynos-acpm.c
```

`REPRODUCED` caracteriza uma hipótese insegura do código sob a condição
simulada; não demonstra que o firmware produziu esse ACK no aparelho ou que
isso causou o reset. O setter DVFS usa `response=false`, e a espera se baseia
no bit de interrupção do canal, sem correlacionar a sequência da resposta.
O timeout de polling desse provider é 100 ms. Nenhum timeout foi provocado
no aparelho para este teste; o kernel permaneceu inalterado.

Antes de corrigir, confirmar no protocolo vendor se uma operação sem RX
produz resposta com sequência, como o slot se comporta após timeout e como
as interrupções são reconhecidas. Comparar cegamente uma sequência de RX
que o firmware talvez não escreva pode impedir todo DVFS. Desabilitar o canal
após erro também pode impedir a redução térmica de frequência. Revisão de
Claude sobre texto público confirmou esses limites; a investigação segue
aberta, sem patch de recuperação instalado.


### Comparação com o driver vendor

Referência fixada: ExtremeXT/android_kernel_samsung_exynos990,
commit `69515fbb7a4395898c05a8624f76a12afbac11c5`:
[DVFS](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/soc/samsung/cal-if/acpm_dvfs.c)
e [IPC](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/soc/samsung/acpm/acpm_ipc.c).

`exynos_acpm_set_rate` configura `response=true`. No caminho **polling**,
`check_response` percorre a fila RX e compara a sequência de seis bits antes
de consumir a entrada. O caminho de timeout faz uma última checagem e,
persistindo a falha, chama reset de emergência. Essa política vendor não foi
portada nem testada neste projeto.

O log de inicialização do firmware ativo informa canal5, `poll=0`,
`mlen=16`, `qlen=1`. Portanto o caminho vendor de polling/fila acima não é
prova de que o slot DVFS ativo devolva sequência: o modo é diferente.
No porte, `acpm_set_xfer(response=false)` apenas zera `rxcnt` e `rxd`;
o helper de slot único ainda espera o bit de interrupção. Os dois flags
não representam necessariamente a mesma política de espera.

Antes de adaptar uma correção, mapear TYPE_BUFFER/non-polling no vendor e
confirmar formato e sequência RX durante transações normais, sem provocar
timeout. Quarentenar um número de sequência, sozinho, não correlaciona o
bit de ACK e não demonstra solução. Claude revisou a comparação textual;
flag local e geometria foram conferidos independentemente em fonte/log.


### TYPE_BUFFER e interrupções vendor

No mesmo fonte vendor, `channel_init` lê `type` e `ap_poll` da tabela SRAM;
os endereços RX/TX também vêm dessa tabela. Para canais sem polling, a IRQ
limpa o ACK antes de a thread chamar `dequeue_policy`. Quando `type` é
TYPE_BUFFER, essa função copia o slot RX para callbacks e retorna, sem
comparar sequência e sem `complete`. A conclusão usada por
`acpm_ipc_send_data_sync` ocorre no outro ramo, que percorre a fila.
O setter DVFS citado usa `send_data_lazy`, não esse envio síncrono.

O porte atual lê `mlen`, `poll_completion`, `id` e `qlen`, sem registrar um
campo `type`; por isso **qlen1 não comprova TYPE_BUFFER vendor**. Também não
se pode atribuir ao caminho sem polling a correlação observada no caminho
polling. Para definir recuperação, ainda falta conferir a versão/layout da
tabela SRAM e o significado do RX/ACK do canal5. Evitar transplantar o envio
vendor, que pressupõe fila circular, para um slot único sem esse mapeamento.


### Layout dos descritores: comparação compilada

Uma sonda local compilou as definições reais `acpm_chan_shmem` do porte e
`ipc_channel`/`channel_info` do
[framework vendor](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/soc/samsung/acpm/fw_header/framework.h).
Ambos têm72 bytes, com estes offsets em bytes:

| Campo do porte | Campo vendor | Offset comum |
|---|---|---:|
| id | id | 0 |
| reserved[2] | type | 12 |
| rx_rear/front/base | ch.rx_rear/front/base | 16/20/24 |
| tx_rear/front/base | ch.tx_rear/front/base | 40/44/48 |
| qlen/mlen | ch.q_len/q_elem_size | 52/56 |
| poll_completion | ap_poll | 68 |

Essas três definições usam campos de32 bits, sem ponteiros ou condicionais
internos; a comparação é de layout dos fontes, não uma leitura do firmware.
No vendor, os valores de tipo são QUEUE1 e BUFFER2. Uma futura instrumentação
pode ler esse word por `readl`, junto com id/qlen/mlen/poll, evitando printk
no caminho de ACK. Valor0 seria inconclusivo. Ainda é preciso confirmar base
e versão da tabela; naquela etapa ainda não havia diagnóstico instalado.
Claude revisou essa inferência com os resultados sanitizados. A equivalência
de offsets não confirma echoRX nem resolve ACK tardio.


### Diagnóstico de inicialização e boot em RAM

`patches/0012-acpm-descriptor-diagnostic.patch` acrescenta `word_0c` ao
log existente de geometria dos canais. Lê o campo reservado com `readl`
apenas na inicialização, sem escrever SRAM ou modificar ACK, DVFS e
recuperação. Uma asserção de compilação fixa seu offset em0x0c.

Baseline SHA256 do provider antes desse diagnóstico:
`76e642856c7e024834f9b0839fbeb8370e26cc1939eaaf5d602a1f34dee83d52`.
O patch aplica sobre esse baseline e reproduz exatamente o fonte compilado.
Compilação do objeto ACPM para arm64 passou. Revisão por Claude e checkpatch
sem exigência de assinatura passaram; isso não é submissão upstream.
O kernel com esse diagnóstico passou em boot remoto **somente em RAM**,
com DT/ramdisk preservados e módulos da mesma release; a imagem instalada
de retorno permanece intacta.

O log representa uma amostra de inicialização. Valores1/2 são compatíveis
com os rótulos QUEUE/BUFFER da referência, sem certificar ABI; zero é
inconclusivo. Comparar sempre id/poll/mlen/qlen do mesmo canal. O diagnóstico
não verifica echoRX, não recupera timeout e não identifica a causa do reset.
Remover esse campo ao encerrar a investigação se não for mais útil.


### Resultado observado no firmware ativo

A leitura na inicialização produziu a seguinte combinação, sem publicar
endereços SRAM ou logs operacionais:

| Canais | word_0c | poll | mlen | qlen |
|---|---:|---:|---:|---:|
| 0 | 1 | 1 | 16 | 15 |
| 1,4,10 | 1 | 1 | 16 | 3 |
| 2 | 1 | 1 | 16 | 5 |
| 9 | 1 | 1 | 16 | 7 |
| 3,5,6 | 2 | 0 | 16 | 1 |
| 7,8 | 2 | 1 | 2 | 1 |

No canal DVFS5, valor2 é compatível com TYPE_BUFFER da referência vendor,
comprovando a presença desse valor no descriptor observado. Isso ainda não
comprova que o RX contenha sequência ou o significado exato de seu ACK.
Sensores/failsafe/bateria e limites voltaram normalmente após o boot, sem
novos erros DVFS. Próximo passo é observar TX/RX numa transação normal com
instrumentação limitada; não injetar timeout nem adotar recuperação sem
correlação comprovada. A causa do reset continua aberta.


### Captura única de RX e resultado em RAM

`patches/0013-acpm-rx-snapshot-diagnostic.patch` é diagnóstico opt-in,
sobre o provider com0012 (baselineSHA256 `4f30cb43e2d096f1378f971b1571c776a689bb46aa0a5e78322d71f29e317ede`).
O parâmetro root-only `single_slot_diag_once` começa falso. Quando armado,
um ACK normal bem-sucedido do canal5 captura TXword0 e RXword0 antes da
limpeza. `xchg` consome a solicitação uma única vez. Timeout mantém o pedido
armado; isso não modifica o retorno ou a aceitação de ACKs.

O log sai depois de limpar ACK/readback/ownership, ainda sob mutex da
transação. Portanto existe efeito de observação na duração desse comando;
não usar essa captura para comprovar ausência de uma corrida de timing.
Desarmar explicitamente o parâmetro se nenhum comando normal o consumir.
Não há injeção de timeout, mudança de relógio ou escrita adicional no firmware.

Revisão do Claude identificou tipos de formato; corrigidos e confirmados
na compilação arm64 sem avisos. O mock da função real testa opt-in,
consumo único e log após limpar ACK; os casos de ACK tardio continuam
reproduzindo a lacuna. Patch reproduz o fonte compilado e checkpatch passou.
O kernel com0013 passou em boot remoto somente em RAM. A captura começou
desativada, foi armada uma vez depois do boot e consumida por atividade
normal do governador; nenhum timeout ou carga foram provocados.

RXword0 não é necessariamente payload recebido pelo cliente quando
`rxcnt=0`. Sequências observadas, iguais ou diferentes, precisarão de
interpretação do protocolo; esse patch não recupera o canal nem corrige
ACK tardio. Não publicar logs brutos de captura.


Na única amostra desse teste, `rxcnt=0` e as sequências TX/RX de seis bits
coincidiram. O parâmetro se desarmou e foi confirmado emN ao final.
Sensores/failsafe/bateria, máximos de frequência e unidades permaneceram
normais, sem novos erros DVFS. Isso demonstra que havia um valor RX legível
com sequência correspondente nessa amostra, sem exigir payload no cliente.

Uma coincidência de seis bits não prova frescor: a sequência pode circular
e um valor antigo coincidir. Ainda faltam amostras distintas e interpretação
do comportamento após timeout. Não ativar comparação obrigatória, declarar
recuperação ou atribuir o reset a ACK tardio com base nesse teste.
Caminho do parâmetro observado nesse build:
`/sys/module/acpm_protocol/parameters/single_slot_diag_once`.
ManterN fora de uma captura deliberada e limitada.

### Sequências distintas no fluxo normal

Uma segunda rodada armou até três capturas, esperando apenas atividade
normal do governador, no máximo10s por captura. As três foram consumidas;
todas mostraram TX/RX iguais, com sequências distintas entre si e da primeira
rodada. São quatro amostras no total, todas com `rxcnt=0`. O parâmetro foi
confirmado emN após a rodada, sem reset, novos erros DVFS, falhas de unidades
ou alterações dos limites. Sensores e bateria permaneceram normais.

Isso é evidência de correlação no fluxo normal e afasta a hipótese de um único
valor RX fixo para essas amostras. Não comprova frescor após timeout, ordenação
RX/ACK pelo firmware ou funcionamento sob carga. Não repetir essas capturas
sem uma hipótese nova; o próximo trabalho é analisar o protocolo e seus
interleavings em fonte/modelo, sem provocar timeout no aparelho.

Claude revisou um resumo técnico público, com ferramentas/MCP desabilitados.
A análise destacou condições ainda desconhecidas: chegada de novo ACK entre
leitura e limpeza do ACK antigo, sobrescrita do slot RX e reutilização da
sequência após circular seu campo de seis bits. São cenários a modelar, não
comportamentos já demonstrados no firmware. Uma comparação de sequência
sozinha não estabelece recuperação segura nessas condições.

A leitura do chamador `z3s_target_index` confirmou que `cur_khz` só é atualizado
quando `set_rate` retorna sucesso, sob o mutex compartilhado. Em erro, mantém
o valor anterior; `z3s_get` devolve esse cache, sem medir o clock físico.
Assim, não registrar a frequência solicitada em erro já está implementado,
mas isso não garante conhecer a frequência real se um comando atrasado for
executado. Não há evidência de tal divergência neste teste.

Antes de considerar recuperação, o modelo deve cobrir ACK concorrente com
clear/readback, RX sobrescrito, sequência expirada reutilizada, timeout total
limitado e ownership entre clusters. O contrato de publicação RX/ACK pelo
firmware continua pendente; não instalar recuperação baseada apenas nas
quatro coincidências normais ou atribuir a elas a causa do reset.

### Interleavings modelados e rechecagem da fila vendor

O mock `tests/test-single-slot-late-ack.py` inclui dois primeiros casos `MODELED`,
executados contra a função C real, com e sem0013:

- Publicar uma resposta nova depois da cópia de RX e imediatamente antes de
  limpar o ACK antigo. Sob a premissa de um bit compartilhado que acumula
  eventos e é apagado pelo clear, o mock termina com RX novo, payload antigo
  copiado e notificação apagada. O readback confirma a limpeza; não recupera
  a notificação perdida nesse modelo.
- Reutilizar uma sequência cujo RX antigo ainda está disponível. A igualdade
  dos campos de seis bits ocorre mesmo sendo uma resposta expirada; um marcador
  de payload obsoleto é entregue pelo helper. Sob essa premissa, igualdade
  sozinha não prova frescor. Ele não simula o alocador
  inteiro, tempo de vida do firmware ou todas as ordens possíveis de eventos.

Essas premissas estão explícitas no teste. Os casos não demonstram a semântica
real de set/clear do mailbox, não testam um algoritmo de recuperação novo e
não provocam timeout no aparelho. Controles existentes de payload, ownership
e captura opt-in continuam passando. Claude revisou somente o código público;
foram incorporados um marcador de payload expirado, limites estáticos do MMIO
simulado e a distinção entre copiar/limpar e comparar sequências. Os testes
foram executados novamente depois desses ajustes.

A leitura de `check_response` na referência vendor confirmou uma proteção
específica de fila: depois de avançar RXrear e verificar RXfront, ela limpa
INTCR1 quando a fila parece vazia, relê RXfront e escreve INTGR1 se surgiu
uma nova entrada. Isso usa índices de produtor/consumidor para detectar
trabalho após clear. O handler não polling limpa o bit antes de acordar a
thread; portanto sua existência também não estabelece publicação RX/ACK
para o slot único do canal5. Não transportar a rechecagem de fila para esse
slot, que não oferece os mesmos índices, nem gerar interrupção manual no S20.

### Ciclo do alocador real após timeout

O campo tem seis bits, mas `acpm_prepare_xfer` reserva apenas sequências1..63
(bitmap0..62), com `ACPM_SEQNUM_MAX=64` e tamanho do pool igual a63.
O helper de slot único libera o bit também em timeout. O caminho de envio
escreve o TX e toca a doorbell sob mutex, mas não mantém uma marca de comando
expirado que impeça seu número de voltar ao pool. O mutex impede concorrência
entre os chamadores atuais; não demonstra que o firmware encerrou o comando.

Um terceiro caso do mock extrai e compila `acpm_prepare_xfer` junto ao helper
de espera, em vez de atribuir manualmente a sequência repetida. Partindo de
pool vazio, a sequência1 expira, as sequências2..63 concluem no modelo e a
próxima alocação volta à1. São62 outras conclusões entre timeout e reutilização.
Cada solicitação começa com TXword0 novo, pois a inserção de sequência usa OR.
O teste exige um word do host que comporte o bitmap e fornece buffers RX
locais válidos; não executa primitivas de concorrência reais do kernel.

Depois da reutilização, o modelo injeta a resposta expirada com a mesma
sequência e uma assinatura de payload antigo. O helper aceita esse payload.
A reutilização é verificada pelo código real; a latência do firmware até esse
ponto é uma premissa explícita, sem evidência de que ocorra no S20. O teste
não mede tempo de circulação, nem valida recuperação ou todos os interleavings.
Passou contra provider0012 e0013, mantendo os controles anteriores.

Sem um limite comprovado de vida de uma resposta, só aguardar alguns comandos
ou comparar seis bits não estabelece frescor. Quarentena também exigiria uma
condição confiável de liberação e tratamento de pool esgotado; não aplicar uma
mudança desse tipo no hardware a partir deste modelo.
