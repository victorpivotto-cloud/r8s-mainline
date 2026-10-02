# ZT7650: probe experimental de checksum e transporte

Módulo de diagnóstico para a árvore Linux6.12 do r8s. **Não implementa toque.**
No modo padrão não instala firmware, envia reset, calibra ou registra IRQ/input.
`vendor_window=1` permite somente habilitar a janela vendor e ler o ID.
`resident_start=1`, junto com `vendor_window=1`, executa o firmware existente
pela sequência normal de boot, sem habilitar escrita, apagar ou gravar flash.
Habilita o LDO por uma leitura limitada, depois desabilita e deixa o nó
desamarrado. `arm` fica falso por padrão; cada carga permite só uma tentativa.
Não instalar em `/lib/modules` nem incluir em autoload.

Prerequisitos conferidos pelo módulo: máquina `samsung,r8s`, cliente0x20,
OF `zinitix,bt541` existente, sem reset GPIO, vdd/vddo compartilhando um
regulador fixo com GPIO e sem always-on. O nome bt541 é o nome legado do nó;
não significa compatibilidade do protocolo. Não há alias exportado para
autoload. O estado do regulador precisa estar desligado antes e após o ensaio.
O estado lógico/GPIO não mede a tensão nem exclui alimentação pelos pinos.

No aparelho observado, o driver incompatível já estava desamarrado e o LDO
off. A leitura inicial012c devolveu2c01. Duas leituras adicionais0011/0012
devolveram11 00/12 00, inclusive com buffer previamente preenchido por0xa5.
Nesse estado inicial, os dados coincidem com os endereços, sem checksum válido.
O retorno de sucesso do adaptador não garante conteúdo de registrador válido.
Nó permaneceu desamarrado, LDO off e módulo removido após cada ensaio.

A fonte Samsung define ENABLE0x10f0 e ID0x17f0 para ZT7650/7650M;
os antigos0xc000/0xcc00 pertencem à outra ramificação. O ensaio da janela
vendor recebeu ID0xe650, definido como ZT7650_CHIP_CODE. A sequência de boot
residente INTclear14f0/NVMinit12f0/PROGRAMstart11f0, seguida de150ms, recebeu
checksum55aa, revisão de chip0012 e firmware0009. Não foram usados comandos
de flash write/erase/upgrade, upload, calibração ou SAVE. Os ecos iniciais
não devem ser tratados como prova de adaptador quebrado ou firmware corrompido.

Compilar no host com a árvore/configuração/símbolos do kernel usado no aparelho:

```sh
make -C "$KDIR" M="$PWD/experiments/zt7650-probe" \
    ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- modules
```

Somente após conferir identidade do aparelho, ABI do módulo, proteções,
ausência de driver no cliente e LDO/GPIO off, a carga manual pode usar:

```sh
insmod /caminho/r8s_zt7650_probe.ko arm=1
# Opcional, hipótese de eco: duas leituras extras de revisão chip/firmware.
# insmod /caminho/r8s_zt7650_probe.ko arm=1 check_framing=1
# Alternativa: somente janela vendor e ID.
# insmod /caminho/r8s_zt7650_probe.ko arm=1 vendor_window=1
# Alternativa: boot residente + checksum/revisões, ainda sem IRQ/input.
# insmod /caminho/r8s_zt7650_probe.ko arm=1 vendor_window=1 resident_start=1 check_framing=1
rmmod r8s_zt7650_probe
```

O resultado está no log do kernel. O probe termina com `-ENODEV` mesmo após
leitura bem-sucedida para liberar os recursos imediatamente; isso não é um
erro de inserção do módulo nem aprovação do checksum. Não executar ambas as
cargas acima como rotina ou repetir sem hipótese nova. Falha de desligamento,
perda de acesso, reset ou guarda térmica exige interromper os testes e preservar
evidências. O cleanup de devres pode tentar desligar novamente após falha;
não existe loop de recuperação nem promessa de restauração nessa condição.

O próximo driver input requer primeiro comunicação/firmware residente
comprovados, depois inicialização, decodificação, ACK e liberação de slots
em erro. Não habilitar IRQ com base somente na inserção deste módulo.

## Protótipo de input: primeiro ensaio físico limitado

`r8s_zt7650_input.c` usa polling de20ms e prazo automático de1..180s
(padrão120), com `arm=false`, sem alias/autoload ou handler de IRQ. Ele
exige ID/checksum, configura modo0, cover aberto e opções básicas; valida
o lote completo e o ACK antes de publicar multitouch. Três falhas seguidas
liberam slots e desligam o LDO; prazo e remoção também liberam contatos.
Só tipo normal é reportado como dedo; outros tipos liberam o slot.
Foi carregado em dois ensaios finitos acompanhados, sem instalação permanente.
Não é driver qualificado para uso diário.

O polling só realiza leituras quando um consumidor abre o dispositivo input,
por exemplo `evtest`; registrar input sozinho não valida eventos. O intervalo
mínimo exposto por sysfs é20ms. IDs repetidos preservam a ordem com separação
de frames antes da segunda ocorrência, depois da validação/ACK do lote inteiro.
Um lote totalmente lido, mas inválido, recebe ACK e é descartado; transferência
incompleta não recebe esse ACK. Eventos com EID diferente de coordenadas ainda
causam erro, sem suporte a gestos: três falhas consecutivas encerram o ensaio.
O prazo conta após registro input; desligamento de alimentação continua sujeito
a falhas do regulador, reportadas como erro crítico. Shutdown também encerra
o ensaio. Contadores de frames e eventos ajudam a distinguir polling vazio
de contatos recebidos; não substituem pressionar/mover/soltar em `evtest`.

No primeiro ensaio, o usuário pressionou, arrastou e soltou na tela. A captura
registrou51 inícios de contato e51 solturas, com centenas de mudanças X/Y e
último tracking ID=-1. Nenhum erro de leitura/ACK ou desligamento foi observado
nessa janela. Após cerca de100s de captura, o módulo foi removido com retorno0;
cliente desamarrado, estado do regulador `disabled`, refcounts0 e proteções
inalteradas foram conferidos. Isso valida entrada básica nessa configuração;
gestos, latência, suspensão/retomada e estabilidade prolongada continuam
pendentes. O módulo permanece fora de autoload e `/lib/modules`.

O segundo ensaio confirmou contatos simultâneos em slots separados e solturas
completas:329 frames com pelo menos dois contatos, eixos observadosX15..1079/
Y8..2388, sem extrapolar os limites do DT. Houve um terceiro contato de28ms,
com possibilidade de toque adicional durante o teste; não qualifica rejeição
de palma ou ausência de contatos espúrios. Testar perto dos cantos não equivale
a medir precisão ou aprovar todas as bordas. Remoção e regulador disabled
foram conferidos novamente, sem erros de leitura/ACK nessa janela.

`run-input-lab.sh` reproduz a captura limitada no telefone com as proteções
deste porte: módulo/ABI, cliente existente desamarrado, regulador único disabled,
máscaras de failsafe0 e sensores abaixo70°C. Registra eventos somente localmente,
usa120s no driver e janela de cerca de100s de captura. Retirada recebe prazo20s; atingir esse
prazo é falha, pode concluir depois no kernel e não permite repetir a carga.
O serviço transitório acrescenta um limite ao supervisor. Um erro do kernel
ou de restauração exige conferir estado e preservar os arquivos locais.

No telefone, como root, com `evtest` e o módulo compilado para sua ABI, use
um diretório novo e mantenha `run.log`/`events.log` fora de publicações:

```sh
LAB_DIR=$(mktemp -d)
cp /caminho/r8s_zt7650_input.ko "$LAB_DIR/"
systemd-run --unit=zt7650-input-lab --collect \
    --property=RuntimeMaxSec=180 --property=TimeoutStopSec=25 \
    /bin/bash /caminho/run-input-lab.sh "$LAB_DIR"
```

Pressionar/mover/soltar durante `INPUT_CAPTURE_READY`, depois conferir
`UNLOAD_COMMAND_RC=0` e `RESTORATION_CONFIRMED`. O marcador é restauração,
não aprovação de eventos. Não repetir esses ensaios como rotina sem hipótese
nova nem deixar o protótipo em autoload.

A revisão com Claude foi conferida contra `init_touch`, `mini_init_touch` e
`ts_read_coord` Samsung. Não foram acrescentadas escritas de resolução ou de
interrupt-enable do BT541: essas funções ZT7650 não usam esse contrato. O
protótipo mantém limites do DT e interrompe dados fora deles. A inicialização
de grip/baixa energia, suspensão/retomada e IRQ continuam fora deste protótipo.

O decoder C compartilhado passa vetores independentes, limites, erro no
último pacote com saída atômica, NONE e soltura com coordenadas inválidas
sob AddressSanitizer/UndefinedBehaviorSanitizer. RELEASE valida ID, mas
ignora posição para não impedir soltura; difere da política estrita do
modelo Python anterior. A confirmação física acima não substitui esses testes
nem qualifica o driver para uso diário.

```sh
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
    tests/test-zt7650-kernel-decoder.c -o /tmp/zt7650-decoder-test
/tmp/zt7650-decoder-test
```

## Pendências antes de um candidato com IRQ

A [fonte Samsung ZT7650 auditada](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/input/touchscreen/zinitix/zt7650/zinitix_ts.c)
registra `zt_touch_work` como thread com `IRQF_TRIGGER_FALLING | IRQF_ONESHOT`.
O handler rejeita GPIO de interrupção alto; `ts_read_coord` termina enviando
CLEAR_INT_STATUS. O nó legado do porte declara nível baixo, e o protótipo
acima não registra IRQ. Os ensaios de polling não validam disparo, drenagem,
ACK ou recuperação de interrupções; a diferença de trigger exige validação
própria, sem alterar o DT somente para reproduzir um flag vendor.

Um candidato finito deve tratar ACK/transferência incompletos, limitar erros
e parar a IRQ antes de desligar o regulador. Remoção e prazo precisam
sincronizar a thread fora do mutex usado pela leitura, liberar todos os slots
e deixar o cliente desamarrado. Não transplantar o ACK vendor sem verificar
seu retorno: o protótipo atual só publica o lote após leitura e ACK completos.
Gestos, suspensão/retomada e operação permanente continuam sem validação.
Nenhum handler IRQ, mudança de trigger ou teste no aparelho foi feito nesta
revisão de fonte.
