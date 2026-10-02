# QCA6390: diagnóstico de um segmento TLV

Patch experimental para a árvore6.12 usada pelo porte r8s. Não corrige
Bluetooth nem completa o download de firmware. Não instalar para autoload.
A flag `hci_uart.r8s_qca_lab_first_segment` é false por padrão/0400.

Quando explicitamente carregado com `r8s_qca_lab_first_segment=1`, o setup
exige QCA6390 e versão Product0x10/ROM0x0200/SOC0x400a0200, usa OPER115200,
lê `qca/htbtfw20.tlv` e confere tipo1/tamanho/Product/ROM do cabeçalho.
Envia só os primeiros243bytes com a API síncrona e validações existentes.
Sempre encerra depois: mantém o erro original, ou retorna `-ECANCELED` se
a resposta não tiver erro. Não envia o restante, não chama setup patch/NVM,
não habilita IBS e não usa retries nesse modo, inclusive em falha de versão.

Aplicação/build no host com configuração/símbolos da ABI do aparelho:

```sh
git apply --check /caminho/first-segment.patch
git apply /caminho/first-segment.patch
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- \
    M=drivers/bluetooth CONFIG_BT_QCA=m CONFIG_BT_HCIUART=m \
    CONFIG_BT_HCIUART_QCA=y W=1 modules
```

Teste requer supervisão finita de carga/retirada/restauração, Bluetoothd
inativo, módulos originais preservados e proteções/estado conferidos antes e
depois. Não substituir os arquivos instalados nem baixar/carregar outro
firmware por tentativa. Um timeout de retirada é falha e pode terminar mais
tarde no kernel; não repetir nem encadear outra carga nessa condição.
Os módulos temporários precisam ser carregados juntos para resolver o novo
símbolo exportado. Não basta trocar apenas hci_uart.

No ensaio único de02/10, versão respondeu e o segmento isolado recebeu
payload `00 1e 03`: got3/expected2/QCA6390, `-EILSEQ`, em aproximadamente24ms.
Nenhum outro segmento/NVM foi enviado; não houve retries do laboratório.
Retiradas iniciais/finais retornaram0, e arquivos/parâmetros dos módulos
originais foram conferidos após restauração. Build ARM64W=1 sem avisos e
aplicação do patch passaram. Nenhuma descoberta/pareamento foi executada.

Esse resultado atribui a resposta ao primeiro segmento do ensaio isolado;
o erro não depende de transmitir a imagem completa. Não comprova significado
moderno de03, CRC inválido, incompatibilidade de firmware ou velocidade física
medida. Manter validações; não ignorar o byte extra para declarar sucesso.

Comparação somente no host: arquivo instalado tinha patch0x3ac0/210704bytes.
A [referência r8s mantida pelo crDroid](https://github.com/crdroidandroid/proprietary_vendor_samsung_r8s/blob/ce94aee812715060d162316c446a003246b6d9c6/r8s-vendor.mk)
lista o mesmo nome, mas o arquivo dessa revisão tem patch0x7aae/211704bytes.
Ambos têm Product0x10/ROM0x0200/formato1/assinatura0/modo3; são diferentes,
inclusive no primeiro segmento. Isso justifica conferir origem/revisão do
firmware do aparelho, sem provar compatibilidade da referência. O arquivo
de referência não foi carregado nem instalado no telefone. Firmware, imagens,
identificadores e logs brutos não são publicados neste repositório.
