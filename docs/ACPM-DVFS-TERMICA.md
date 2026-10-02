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
