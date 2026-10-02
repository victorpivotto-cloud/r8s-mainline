# Estado do porte r8s — 01/10/2026

Debian 13 sobre kernel 6.12 do porte Exynos990, com boot autônomo, UFS,
microSD, Wi-Fi QCA6390 e rede USB gadget. A árvore ainda é experimental.
Este documento substitui o resumo histórico de setembro.

## Correções verificadas

- ACPM/DVFS: transações CPU serializadas e ownership do slot até a resposta.
  Mock concorrente reproduz a falha anterior. Respostas tardias após timeout
  continuam sem solução comprovada; não extrapolar o mock para firmware.
- Térmica: seis sensores, cooling passivo CPU e failsafe por sensor/heartbeat.
  Injeção de falha, ausência de polling e unload/reload foram testados.
  Calibração e desligamento crítico não foram comprovados.
- Reboot: módulo experimental prepara PMU para o protocolo lk3rd.
  Reboot normal e fastboot remoto passaram, com módulo carregado e armado.
  Emergency restart/watchdog/panic podem ignorar esse caminho.
- Rede: policy routing IPv4/IPv6, nft redirect e conntrack passaram em
  namespace isolado. Áudio USB/UVC carregam; periféricos físicos não testados.
- GPU: EGL clear e shader GLSL/triângulo passaram em Mali-G77 com Mesa
  isolado e patch atribuído ao porte z3s. Não substituir Mesa do sistema;
  compositor e renderização sustentada continuam sem qualificação.
- Toque: desamarrar o driver incompatível encerra a tempestade de IRQ;
  isso não habilita entrada por toque.

As mudanças de kernel desta etapa foram testadas em RAM, preservando a imagem
instalada de retorno. Não instalar permanentemente com base só nesses testes.

## O que impede considerar o aparelho qualificado

Houve reset inesperado durante compilação nativa de Mesa com ninja -j2, sem
shutdown limpo ou pstore. A causa permanece aberta. A compilação foi concluída
em outro host. O ensaio de 24 horas em repouso ainda está em andamento;
não existe aprovação de carga sustentada nem de recuperação de energia.

Bluetooth tem nó UART/USI, mas o comando QCA ainda dá timeout. USB host detecta
dispositivo e falha em enumeração (-71); áudio/webcam USB dependem dele.
Som ABOX e câmera/ISP internos exigem porte de drivers. O display simpledrm
funciona, mas falta entrada local funcional. Concessão S2MPU ampla e ausência
de watchdog de hardware qualificado permanecem limitações.

## Instruções reutilizáveis

- [ACPM, DVFS e térmica](ACPM-DVFS-TERMICA.md).
- [Reboot lk3rd](REBOOT-LK3RD.md).
- [GPU Mali-G77](GPU-MALI-G77.md).
- [Qualificação finita](QUALIFICACAO.md).
- [Configuração de rede e módulos](LACUNAS-DE-KERNEL.md).

Cada usuário deve conservar sua imagem/módulos de retorno e suas configurações
locais. Este repositório publica código, patches e procedimentos; não contém
credenciais, logs operacionais, imagens do aparelho ou firmware proprietário.
