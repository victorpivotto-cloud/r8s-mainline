# Bluetooth, toque, som e câmera: investigação do porte

Resultados de 01/10/2026, restritos à árvore 6.12 usada neste projeto.
O telefone continua sem entrada por toque/Bluetooth, placa de som interna ou
nó de câmera interno. Permissões de userspace não acrescentam os drivers ausentes.

## Bluetooth QCA6390

O UART correto e o baud já haviam sido conferidos. A inicialização falha no
pedido de versão `0xfc00`, antes do carregamento de patch/NVM: trocar firmware
sem resolver essa etapa não constitui correção.

No [bluetooth-power.c Samsung derivado](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/bluetooth/bluetooth-power.c),
`qcomm_bt_lpm_exit_lpm_locked` aciona BT_WAKE antes de transmitir. O DT r8s
identifica BT_WAKE em gpg1-1 e HOST_WAKE em gpa2-3. O porte não controla BT_WAKE.

Ensaio em runtime, após os rails estarem energizados: linha BT_WAKE inicialmente
livre/input; requisitada isoladamente em baixo e depois alto, com unbind/bind
somente do serdev Bluetooth. Em ambos os níveis, as quatro tentativas de versão
falharam por timeout. Linha devolvida a input e driver original restaurado;
Wi-Fi e UFS preservados. Revisão Claude ajudou a apontar limites do ensaio.

Isso não refuta toda hipótese de wake: momento/pulso, estado herdado e CTS/TX
continuam relevantes. Não incorporar GPIO hog permanente como solução.
Próximo diagnóstico: conferir CTS e contadores UART, ordem do wake/reset e
caminho LPM antes do primeiro comando; comparação fria e sinais físicos ainda
necessários para atribuir causa.

## Toque Zinitix ZT7650

Comparação com [driver Samsung](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/input/touchscreen/zinitix/zt7650/zinitix_ts.c)
e [layout de eventos](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/input/touchscreen/zinitix/zt7650/zinitix_ts.h):

| Campo | ZT7650 vendor |
|---|---|
| Modo de coordenadas | 0 em registro 0x0010 |
| Primeiro evento | registro 0x0200, pacote de 16 bytes |
| Eventos restantes | registro 0x0201, contador no nibble baixo do byte 7 |
| Tipo/ID/estado | byte 0: eid bits 1:0, tid 5:2, estado 7:6 |
| Coordenadas | X=(byte1<<4)+(byte3>>4), Y=(byte2<<4)+(byte3&15) |
| ACK de interrupção | comando 0x0003 após consumo |
| Transação | ponteiro LE16, espera 50 us, leitura; espera posterior 10 us |

O BT541 usa modo 2 e lê 0x0080 como estrutura com status/máscara de dedos.
Adicionar apenas um compatible não adapta os eventos. O porte deve validar
ID/estado, contador limitado a 9 eventos adicionais, coordenadas e tratamento
de erros antes de publicar eventos multitouch.

O driver incompatível permanece desamarrado. A consulta I2C sem religar rails
não recebeu ACK, com `tsp_ldo_en` desabilitado após unbind. Portanto esse
ensaio não mede o protocolo e não indica que o chip esteja defeituoso.
Próximo trabalho: driver mínimo com reguladores/power sequencing e decoder
corretos, sem atualização de firmware/calibração; depois validação física de
pressionar/mover/soltar e ausência de IRQ storm. Ainda não foi implementado.

## Som interno

A árvore Samsung contém ABOX v3 para Exynos9830. O [probe](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/sound/soc/samsung/abox/abox.c)
depende de SRAM/DRAM reservada, IOMMU, múltiplos clocks, GIC/IPC, firmware e
componentes ASoC. A árvore usada aqui não tem ABOX; `/proc/asound/cards` informa
nenhuma placa. Ter suporte ao amplificador ou habilitar ALSA não cria esse DSP.

Portar primeiro memória/IOMMU/clocks/IPC e comprovar boot do DSP; só depois
DAIs, máquina/codec e rotas. Áudio USB é uma alternativa menor, mas depende de
USB host e de teste físico. Não há captura/reprodução interna comprovada.

## Câmera interna

O [is-core.c Samsung](https://github.com/ExtremeXT/android_kernel_samsung_exynos990/blob/69515fbb7a4395898c05a8624f76a12afbac11c5/drivers/media/platform/exynos/camera/is-core.c)
inicializa gerenciamento de recursos/memória, interface, cadeias ISP, CSI DMA,
múltiplos nós de vídeo e hardware. O FIMC-IS antigo encontrado na árvore usada
é para Exynos4; não equivale ao ISP Exynos990. Não há `/dev/video*` no ensaio.

O próximo passo é mapear sensores/CSI, clocks/power domains, IOMMU e firmware
específicos do r8s antes de montar o pipeline V4L2. UVC USB depende de OTG;
carregar o módulo sozinho não comprova vídeo. Não foram escritos registradores
ISP nem executados blobs. Câmera e som internos continuam projetos de porte.
