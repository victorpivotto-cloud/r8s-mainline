# QCA6390: diagnóstico conjunto UART Samsung / 3,2 Mbaud

Dois patches de laboratório para a árvore 6.12 deste porte. O patch QCA é uma
alternativa aos outros experimentos QCA; não aplicar em conjunto com eles.
Não habilita Bluetooth nem deve ser usado para autoload ou operação diária.

A HAL pública Hastings examinada escolhe 3,2 Mbaud/código 0x11. O driver Samsung
original limita a velocidade solicitada a 3 Mbaud. Este experimento testa uma
solicitação coerente de 3,2 Mbaud nos dois lados, sem modificar DT ou clock CMU.

`uart-ceiling.patch` adiciona `samsung_tty.r8s_uart_lab3200000`, false/0600.
Somente a UART de endereço 0x10840000 com compatible exynos850 pode usar o teto
3,2 Mbaud quando habilitado. Captura UBRDIV/DIVSLOT/AFC sob o lock normal do driver
e imprime depois de restaurar IRQs. Não lê FIFO/UERSTAT nem altera GPIO/mux.
O clock registrado vem do framework e não mede a frequência física.

`qca-3200.patch` adiciona `hci_uart.r8s_qca_lab3200000`, false/0400.
Restrito a QCA6390/serdev/INIT 115200; com a flag, OPER é 3,2 Mbaud. Consulta versão
115200 e confere Product 0x10/ROM 0x0200/SOC 0x400a0200. Solicita uma mudança para 3,2 Mbaud pela
rotina Linux existente, com AFC temporariamente suspenso, e consulta novamente.
Confere o baud retornado pela API antes de cada consulta. Essa API não mede
baud elétrico; os divisores programados são conferidos separadamente no log.
Se a consulta a 3,2 Mbaud expirar, faz apenas uma consulta final após mudar somente
baud do host para 115200. Registra somente Command Complete 0xfc48, até 6 bytes.
Sempre aborta antes de TLV/NVM/IBS/retries, também quando a consulta funciona.

RTS continua GPIO hog baixo: AFC/RTS lógico não prova transição no pino.
Ausência de ACK no parser H4 não prova ausência no fio. A consulta de versão
usa o mesmo opcode nas velocidades; enquadramento ou resposta atrasada não
estão excluídos sem captura física. Não elevar clock por tentativa.

## Build e execução controlada

Aplicar os dois patches à árvore correspondente no host. O primeiro requer
um kernel novo, pois a UART Samsung está embutida; um módulo QCA sozinho não basta.

```sh
git apply --check /caminho/uart-ceiling.patch
git apply --check /caminho/qca-3200.patch
git apply /caminho/uart-ceiling.patch
git apply /caminho/qca-3200.patch
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j2 Image
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    M=drivers/bluetooth CONFIG_BT_QCA=m CONFIG_BT_HCIUART=m \
    CONFIG_BT_HCIUART_QCA=y W=1 modules
```

Testar somente em RAM, com imagem de controle recuperável e supervisor finito
validado. Guardas devem conferir kernel/ABI, flags, sensores, Bluetooth inativo,
originais e retirada dos módulos. Habilitar o parâmetro UART apenas durante a
rodada, desabilitá-lo antes de recarregar os módulos originais e conferir
hashes/srcversion/flags/saúde. Não executar sem rotina de restauração.
Falha de retirada/restauração, reset, perda de acesso, deadline  de boot ou erro
DVFS/térmico impede novos ensaios/ciclos automáticos. Não usar pareamento.

## Resultado

Preparação: Image e módulo ARM64 compilados no host; módulo W=1 sem avisos.
Fontes originais preservadas byte por byte; patches passam git apply --check.
Ensaio único: versão a 115200 respondeu; a UART selecionou 3200000 e
programou UBRDIV=2/DIVSLOT=14, com clock declarado de 200 MHz. AFC passou de
0 durante a mudança para 1 antes da consulta. A consulta a 3,2 Mbaud expirou
(-110, cerca de 2 s). Ao retornar apenas o host a 115200, a versão respondeu
em cerca de 4 ms, com os mesmos IDs e Patch 0x0d2b. Nenhum Command Complete
0xfc48 foi capturado. Contadores cresceram 20 bytes TX e 42 bytes RX; isso
não mede sinais no fio. A leitura MGMT não apresentou controladores.

O teto de 3 Mbaud foi removido para este ensaio, mas essa mudança sozinha
não resolveu a comunicação. Não atribuir a falha ao clock, firmware ou RTS
sem evidência adicional. Não repetir este ensaio sem uma hipótese nova.

Supervisor de 30 s; retiradas iniciais/finais RC0; parâmetro UART voltou a N
antes da recarga dos módulos originais. Hashes/srcversion conferidos,
flags QCA ausentes, mesmo boot durante o laboratório e nenhuma falha de
saúde. Depois, retorno ao kernel de controle em RAM confirmado, sem flags
de laboratório, com limites originais e zero unidades falhas. Não houve
alteração de partições, firmware, DT, GPIO, clock CMU ou Wi-Fi.

[Análise e próximo diagnóstico](../../docs/QCA6390-UART-SAMSUNG.md).
