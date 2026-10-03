# Estado do porte r8s — 02/10/2026

Debian 13 sobre kernel 6.12 do porte Exynos990, com boot autônomo, UFS,
microSD, Wi-Fi QCA6390 e rede USB gadget. A árvore ainda é experimental.
Este documento substitui o resumo histórico de setembro.

## Correções verificadas

- ACPM/DVFS: transações CPU serializadas e ownership do slot até a resposta.
  Mock concorrente reproduz a falha anterior. Respostas tardias após timeout
  continuam sem solução comprovada; não extrapolar o mock para firmware.
  Diagnóstico em RAM observou canal DVFS5 com word_0c=2, poll0 e slot único,
  compatível com TYPE_BUFFER vendor. Quatro capturas normais sem payload,
  com sequências distintas, mostraram TX/RX iguais; frescor e recuperação
  após timeout seguem abertos. Diagnóstico desarmado após as capturas.
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
- Bateria: corrigido overflow do limite ausente no max17042; teste da função
  real e boot em RAM confirmaram a correção de `health`. Perfil de carga intacto.
- Toque: driver incompatível desamarrado. IdentificaçãoZT7650/checksum e
  entrada básica pressionar/mover/soltar passaram em um protótipo finito com
  polling, sem IRQ. Foi removido com regulador desligado; não está instalado
  para uso diário. Dois contatos simultâneos e solturas passaram em segunda
  captura; gestos, precisão, suspensão e estabilidade seguem pendentes.

As mudanças de kernel desta etapa foram testadas em RAM, preservando a imagem
instalada de retorno. Não instalar permanentemente com base só nesses testes.

## O que impede considerar o aparelho qualificado

Houve reset inesperado durante compilação nativa de Mesa com ninja -j2, sem
shutdown limpo ou pstore. A causa permanece aberta. A compilação foi concluída
em outro host. O ensaio de 24 horas foi interrompido e ficou adiado;
não existe aprovação de carga sustentada nem de recuperação de energia.
Carga curta de memória/hash numa CPU LITTLE completou 30 s; MID e BIG foram
interrompidos pelo limite conservador de 70 °C. Nenhum desses testes causou
reset, mas não reproduzem nem esclarecem o reset da compilação Mesa.

Bluetooth recebeu versão a115200, mas patch TLV falha; sem patch/NVM, o
HCI Reset expirou. Bluetooth funcional permanece pendente. USB host detecta
dispositivo e falha em enumeração (-71); áudio/webcam USB dependem dele.
Som ABOX e câmera/ISP internos exigem porte de drivers. O display simpledrm
funciona; o protótipo de toque finito ainda não fornece entrada local
permanente. Concessão S2MPU ampla e ausência
de watchdog de hardware qualificado permanecem limitações.

## Instruções reutilizáveis

- [ACPM, DVFS e térmica](ACPM-DVFS-TERMICA.md).
- [Reboot lk3rd](REBOOT-LK3RD.md).
- [GPU Mali-G77](GPU-MALI-G77.md).
- [Diagnóstico de carga limitada](DIAGNOSTICO-DE-CARGA.md).
- [Qualificação finita](QUALIFICACAO.md).
- [Investigação dos periféricos](PERIFERICOS-PENDENTES.md).
- [Diagnóstico de bateria](BATERIA-HEALTH.md).
- [Limites da referência de áudio ABOX](AUDIO-REFERENCIA-IPC.md).
- [Configuração de rede e módulos](LACUNAS-DE-KERNEL.md).

Cada usuário deve conservar sua imagem/módulos de retorno e suas configurações
locais. Este repositório publica código, patches e procedimentos; não contém
credenciais, logs operacionais, imagens do aparelho ou firmware proprietário.
