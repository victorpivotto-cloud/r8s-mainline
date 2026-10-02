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

## Protótipo de input: somente compilado/testado no host

`r8s_zt7650_input.c` usa polling de20ms e prazo automático de1..180s
(padrão120), com `arm=false`, sem alias/autoload ou handler de IRQ. Ele
exige ID/checksum, configura modo0, cover aberto e opções básicas; valida
o lote completo e o ACK antes de publicar multitouch. Três falhas seguidas
liberam slots e desligam o LDO; prazo e remoção também liberam contatos.
Só tipo normal é reportado como dedo; outros tipos liberam o slot.
Ainda não foi carregado no aparelho. Não é driver qualificado para uso diário.

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

A revisão com Claude foi conferida contra `init_touch`, `mini_init_touch` e
`ts_read_coord` Samsung. Não foram acrescentadas escritas de resolução ou de
interrupt-enable do BT541: essas funções ZT7650 não usam esse contrato. O
protótipo mantém limites do DT e interrompe dados fora deles. A inicialização
de grip/baixa energia, suspensão/retomada e IRQ continuam fora deste protótipo.

O decoder C compartilhado passa vetores independentes, limites, erro no
último pacote com saída atômica, NONE e soltura com coordenadas inválidas
sob AddressSanitizer/UndefinedBehaviorSanitizer. RELEASE valida ID, mas
ignora posição para não impedir soltura; difere da política estrita do
modelo Python anterior. A confirmação física pressionar/mover/soltar segue pendente.

```sh
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
    tests/test-zt7650-kernel-decoder.c -o /tmp/zt7650-decoder-test
/tmp/zt7650-decoder-test
```
