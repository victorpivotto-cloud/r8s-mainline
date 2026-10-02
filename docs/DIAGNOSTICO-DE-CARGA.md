# Diagnóstico limitado de compilação nativa

O reset ocorrido com Mesa/ninja-j2 segue sem causa. Uma janela curta sem reset
não comprova estabilidade. Este procedimento reduz a carga e registra sinais
para investigar, sem instalar Mesa, alterar firmware ou gravar partições.

`tests/test-native-build-guard.py` requer root, sensores ACPM corrigidos e os
três clusters cpufreq. Recebe diretório Ninja já configurado e state novo por
rodada. Compila com uma CPU LITTLE, j1/nice15, tetos temporários de
1066/1264/1248MHz e timeout entre1 e180s. Não modifica mínimos/governor.

Amostra seis sensores, temperatura/tensão de bateria e failsafe a cada0,5s.
SoC>=70C, bateria>=43C, leitura inválida, failsafe ou tensão fora3,6..4,5V
interrompem o processo. Os limites são guardas conservadoras deste ensaio,
não calibração nem certificação de proteção elétrica/thermal shutdown.
A amostra que dispara a guarda também é salva. Logs locais são privados.

Executar em unit transitória, com duração externa e limpeza independente:

```sh
# Ajustar caminhos; conservar fonte/módulos/imagem de retorno.
# Usar um state exclusivo NOVO em cada rodada, nunca reaproveitar o exemplo.
systemd-run --wait --pipe --unit=r8s-native-example \
  -p RuntimeMaxSec=90 -p MemoryMax=1G -p TasksMax=64 \
  -p KillMode=control-group -p TimeoutStopSec=10 -p OOMPolicy=stop -p UMask=0077 \
  -p 'ExecStopPost=/usr/bin/python3 /opt/r8s-tests/test-native-build-guard.py --state /root/r8s-native-example.json --restore' \
  /usr/bin/python3 /opt/r8s-tests/test-native-build-guard.py \
  --state /root/r8s-native-example.json --build-dir /opt/mesa/build --seconds 60
```

O argumento `--seconds`
aceita no máximo180; ajustar RuntimeMaxSec para janela+30. Conservar espaço
para logs e observar stdout pelo host durante a execução. Não repetir janelas
sem analisar progresso ou se houve reset, falha de sensor/DVFS ou restauração.

O finally termina o grupo do compilador antes de restaurar. ExecStopPost
cobre morte abrupta do supervisor; KillMode mata demais processos do cgroup.
State guarda bootID e máximos anteriores, é gravado por rename e marcado
.restored após limpeza para impedir reaplicação posterior. Lock impede
execuções concorrentes. Não aplicar um state de outro boot.

Validação no telefone: janela3s encerrou por timeout, com limites restaurados;
SIGKILL aplicado somente ao supervisor deixou zero compiladores órfãos e
ExecStopPost restaurou os três máximos. Janela real60s teve pico55C, failsafe0,
sem reset e máximos restaurados. Arquivo C gerado grande não terminou nessa
janela; isso ainda não demonstra progresso de todo o build.

`bounded-window-ended`/rc124 significa apenas fim da janela. `build-complete`
significa Ninja terminou, sem equivaler a aprovação de runtime/renderização.
Examinar compilerlog e journal do kernel; depois conferir máximos, failsafe,
unidades falhas e boot. A restauração por software não cobre kernel travado.
Pstore vazio não exclui panic quando a retenção pelo bootloader não foi provada.

Uma janela seguinte de180s concluiu 30 tarefas Ninja, incluindo o
objeto C gerado que excedeu60s, com pico55C, failsafe0, sem reset e
limites restaurados. Demonstra progresso do build sob carga reduzida; não
resolve a causa do reset nem aprova compilação completa ou carga irrestrita.


Outra janela de180s concluiu mais59 tarefas Ninja, com359 amostras,
pico54C, bateria34,1C e failsafe0. Consumo de CPU173,715s e pico de
memória224,6M. A janela encerrou por timeout esperado, preservou o boot,
restaurou os três limites e terminou sem unidades falhas ou novos erros
DVFS. Esses resultados justificam progresso incremental sob as mesmas
guardas; a compilação completa e a causa do reset continuam pendentes.


Uma terceira janela de180s concluiu dois objetos C gerados do NIR
(`nir_opt_algebraic.c` e `nir_opcodes.c`), além do gerador git_sha1.
Pico de memória404,3M, CPU174,914s; limites restaurados e mesmo boot,
sem novos erros DVFS ou reset. O número de tarefas por janela depende do
custo dos objetos: medir o próximo comando antes de repetir uma janela que
não conclua objeto. A compilação inteira continua pendente.


## Gargalo que interrompe a continuação automática

O próximo objeto, `nir_constant_expressions.c.o`, vem de C gerado com
1264086 bytes e usa `-O3`. Uma janela completa de180s não concluiu esse
objeto; somente o gerador git_sha1 terminou. CPU174,158s, pico de memória
577,9M. O boot foi preservado, failsafe permaneceu zero e os três máximos
foram restaurados, sem novos erros DVFS ou compiladores órfãos.

A continuação desse build foi suspensa. Ninja reinicia a compilação de um
objeto interrompido; duas janelas não somam progresso dentro dele. Não
repetir a mesma janela, aumentar limites ou concluir instabilidade a partir
desse custo. Próximo diagnóstico exige alvo menor explícito com supervisor
revalidado, ou análise do compilador fora desse build. Congelar processos
entre janelas também exigiria outro desenho de supervisão e não foi adotado.
Não houve alteração de otimização ou instalação de artefatos.
