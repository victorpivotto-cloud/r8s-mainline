# Runbook — desbloqueio do bootloader do S20 FE (passo 3)

**Status: ✅ EXECUTADO em 2026-09-13, ~14:41.** Resultado: `flash.locked=0`,
`verifiedbootstate=orange`, `vbmeta.device_state=unlocked` — e
**`warranty_bit` continuou `0`**, ou seja, o Knox NÃO queimou no desbloqueio.
Evidência: `dados/adb-r8s-20260913-03-pre-desbloqueio.txt` →
`-04-desbloqueado.txt`.

> **Correção da premissa deste documento:** a tabela abaixo dizia que o
> desbloqueio queima o Knox no ato. **Não queima neste aparelho.** O e-fuse
> queima na primeira gravação de binário não assinado (passo 4). Até lá,
> relock + firmware de estoque ainda devolve o aparelho com Knox intacto.

As duas armadilhas encontradas na execução estão marcadas com ⚠️ **ERRO DESTE
DOCUMENTO** no passo 3.2 e no 3.3. Leia-as antes de repetir o procedimento em
qualquer outro aparelho.

## A natureza deste passo

Tudo o que foi feito até aqui é reversível: remover uma conta, ligar um botão,
plugar um hub. **Este passo não é.** Ao confirmar o desbloqueio:

| Consequência | Reversível? |
|---|---|
| ~~`warranty_bit` vai a `0x1` (Knox queimado)~~ **NÃO ACONTECEU — ver correção no topo.** Neste aparelho o e-fuse só queima na 1ª gravação de binário não assinado | — |
| Samsung Pay, Secure Folder, Samsung Health, Samsung Wallet | **Não.** Param de funcionar para sempre |
| Widevine L1 → L3 (fim do HD em Netflix/Prime) | **Não** |
| Todos os dados do aparelho | Apagados no ato |
| Garantia Samsung | Perdida |
| Bootloader trancado de novo | Sim, mas o Knox **não volta** |

O aparelho tem 210 GB livres e 18 GB usados; confirme que não há nada a salvar
antes de seguir.

As linhas de Samsung Pay / Secure Folder / Widevine / garantia da tabela acima
seguem valendo como risco a partir do **passo 4**, que é quando o e-fuse queima
de fato.

## Pré-requisitos

### 1. Firmware de rollback — ✅ CUMPRIDO em 13/09

```
~/Firmware/SM-G780F_ZTO/SM-G780F_4_20251003010911_jjin1edht2_fac.zip
6,2 GB · BL + AP + CP + CSC + HOME_CSC · build G780FXXSOFYJ2 / ZTO
```

Baixado com **`samloader-rs` v2.1.0**, e essa escolha não foi gosto:

- **`samloader` (Python, nlscc)** e **`samfirm.js`** batem em **403 do Akamai**
  no `version.xml` — é filtro de **User-Agent** (`Kies2.0_FUS` passa). Testado
  com modelo de controle (SM-S911B): também 403, ou seja **não era "modelo não
  encontrado"**, era o CDN. Passado esse ponto, as duas ainda quebram no nonce
  da FUS: a chave AES de 2022 que ambas carregam não decifra mais o que o
  servidor devolve.
- **`samloader-rs` v2.1.0** (topjohnwu, publicada em 06/09/2026) faz
  **download E gravação**, com a autenticação atual. É também a ferramenta que
  a wiki da LineageOS usa hoje no lugar do heimdall.

Instalada em `~/.local/bin/samloader-rs`. A regra udev do heimdall
(`04e8:685d`, `TAG+="uaccess"`) já serve para ela — sem sudo.

<!-- texto original abaixo, mantido por histórico -->

Baixar **antes** de desbloquear o firmware oficial correspondente:

```
Modelo: SM-G780F      CSC: ZTO (Brasil)      Build: G780FXXSOFYJ2
```

Sem ele, um erro no meio do caminho deixa o aparelho sem para onde voltar. Com
ele, sempre dá para reflashar o estoque (o Knox continua queimado, mas o
aparelho volta a ser um celular).

Guardar fora da pasta do Git — são vários GB. `dados/` está no repositório.

### 2. Ferramenta de flash — verificar ANTES do dia

Este PC tem `heimdall` e `fastboot`; não tem `odin4` nem `thor`.

**✅ VERIFICADO em 13/09: o heimdall FUNCIONA neste aparelho.**

A ressalva original era boa, mas mirava o alvo errado: o `heimdall` clássico
(1.4.2, de 2017) realmente falha em Samsung modernos — só que a versão instalada
aqui é a **v2.1.0**, o fork mantido pelo Henrik Grimler (2021-2024), e ela passa:

```text
Initialising protocol...   Protocol initialisation successful.
Session begun.
Downloading device's PIT file...   PIT file download successful.
Entry Count: 43   CPU/bootloader tag: LSI9830   Logic unit count: 5
```

`LSI9830` confirma o Exynos 9830 (= Exynos 990) pela própria boca do bootloader.
A regra udev do pacote (`/lib/udev/rules.d/60-heimdall-flash.rules`) já cobre
`04e8:685d` com `TAG+="uaccess"`, então **não precisa de sudo**.

Tabela de partições em `dados/pit-r8s-20260913.txt`, log bruto em
`dados/heimdall-printpit-r8s-20260913.log`.

**Armadilha descoberta na prática:** nunca canalizar o heimdall para `head`. O
SIGPIPE mata a sessão no meio, e o aparelho fica com o estado Odin preso —
as execuções seguintes falham com `ERROR: Protocol initialisation failed!`
**mesmo continuando visível no `lsusb` e respondendo ao `heimdall detect`**.
Só sai saindo e voltando ao Download Mode. Redirecionar para arquivo e ler o
arquivo depois.

> O desbloqueio em si (passo 3) **não usa ferramenta de PC nenhuma**. É feito na
> tela do aparelho. A ferramenta só é necessária depois, para gravar. Então dá
> para desbloquear sem ter resolvido essa incerteza — mas não faz sentido
> queimar o Knox antes de saber se é possível gravar.

### 3. Estado a conferir imediatamente antes

```bash
adb -d shell 'echo "oem=$(getprop sys.oem_unlock_allowed) locked=$(getprop ro.boot.flash.locked) knox=$(getprop ro.boot.warranty_bit)"'
# esperado: oem=1 locked=1 knox=0
```

Se `oem` não for `1`, **pare**: alguma coisa rearmou o VaultKeeper e o
procedimento muda.

## Procedimento

### Passo 3.1 — Entrar em Download Mode

O S20 FE não tem tecla Bixby nem Home física:

1. Desligar o aparelho por completo.
2. Segurar **Volume ↑ + Volume ↓** juntos e, **mantendo**, conectar o cabo USB
   no PC.
3. Solta quando a tela de aviso azul aparecer.

### Passo 3.2 — Ler a tela antes de confirmar

Antes de qualquer botão, **anotar** o que a tela mostra:

```text
FRP LOCK:      deve estar OFF
OEM LOCK:      deve estar ON(U)   ← ver correção abaixo
RMM STATE:     anotar o valor — se disser PRENORMAL, PARAR
WARRANTY VOID: 0
```

⚠️ **ERRO DESTE DOCUMENTO, corrigido em 13/09:** estava escrito "OEM LOCK deve
estar OFF". **Errado, e quase fez parar um desbloqueio que estava correto.**

| Valor | Significado |
|---|---|
| `OEM LOCK: ON` | travado e **não** destravável — aí sim, parar |
| `OEM LOCK: ON(U)` | travado, **destravável** — o `(U)` é *unlockable*. **É o estado esperado antes do desbloqueio** |
| `OEM LOCK: OFF(U)` | já destravado — só aparece **depois** |

O que foi lido de verdade neste aparelho: `FRP LOCK: OFF`, `OEM LOCK: ON(U)`,
`WARRANTY VOID: 0`, e **`RMM STATE` não exibido**.

**`RMM STATE` ausente não é `PRENORMAL`.** Neste firmware a linha simplesmente
não aparece quando não há nada armado. O critério de abortar é a tela *dizer*
`PRENORMAL`. A confirmação independente veio do ADB minutos antes:
`ro.boot.em.status = 0x0`.

`RMM STATE: PRENORMAL` significa que o aparelho voltou à janela de restrição.
Nesse caso, **não desbloquear**: manter ligado no Wi-Fi e reavaliar em 7 dias.
Foi esse estado que enterrou o projeto do A5.

### Passo 3.3 — Desbloquear

⚠️ **ARMADILHA QUE CUSTOU UMA RODADA: são DUAS telas, e o desbloqueio é na
primeira.**

| | Tela | O que fazer |
|---|---|---|
| **1** | **Aviso azul** — texto sobre "custom OS", com *"Press volume up to continue / volume down to cancel"* | **É AQUI.** Vol ↑ **longo** (~7 s) abre o *Device unlock mode* |
| **2** | **`Downloading... Do not turn off target!!`** com ODIN MODE / FRP LOCK / OEM LOCK / WARRANTY VOID | Modo Odin puro. Vol ↑ aqui **não faz absolutamente nada** |

O toque **curto** em Vol ↑ na tela 1 te leva para a tela 2 — e de lá não há
desbloqueio. Foi exatamente o que aconteceu: o aparelho ficou no `Downloading...`
respondendo ao `samloader-rs detect`, com o usuário segurando Vol ↑ sem efeito.

Para voltar da tela 2 para a tela 1: **Vol ↓ + Power por ~7-10 s** até a tela
apagar (soltar no instante em que apagar), depois **Vol ↑ + Vol ↓** e reconectar
o cabo.

Então, na tela 1:

1. **Segurar Volume ↑ por ~7 segundos**, sem soltar.
2. Aparece a pergunta de desbloquear o bootloader.
3. **Volume ↑ confirma.**

O aparelho apaga tudo e reinicia no assistente de configuração.

### Passo 3.4 — O passo que quase todo mundo esquece

Depois do desbloqueio, o VaultKeeper **precisa de uma conexão de rede para
homologar o estado**. Se isso não acontecer, ele **rearma o OEM lock** e o
aparelho volta a recusar gravação.

Então, imediatamente após o wipe:

1. Passar pelo assistente, **conectando ao Wi-Fi**.
2. **Não** adicionar conta Google nenhuma (rearma o FRP sem necessidade).
3. Reativar opções de desenvolvedor e depuração USB.
4. Conferir que "Desbloqueio de OEM" continua ligado e:

```bash
adb -d shell 'echo "oem=$(getprop sys.oem_unlock_allowed) locked=$(getprop ro.boot.flash.locked) knox=$(getprop ro.boot.warranty_bit)"'
# MEDIDO em 13/09:  oem=1 locked=0 knox=0
```

`locked=0` é a confirmação de que deu certo. **`knox=0` foi a surpresa**: o
e-fuse não queimou no desbloqueio (ver o bloco de correção no topo).

Duas observações de tempo, para não interpretar como falha o que é normal:

- o primeiro boot depois do wipe **fica parado no logo da Samsung** enquanto
  recria a criptografia de `/data`. Aqui levou **75 s** até o aparelho se
  anunciar no barramento como MTP (`04e8:6860`), que é o sinal objetivo de que
  o Android subiu — antes de qualquer ADB;
- o ADB só voltou **384 s** depois, e em `unauthorized`: é preciso aceitar o
  diálogo de chave RSA na tela do aparelho.

### Passo 3.5 — Congelar a evidência

```bash
./scripts/coletar-dispositivo.sh <ip:porta ou serial>
# renomear para dados/adb-r8s-AAAAMMDD-03-desbloqueado.txt
```

## Critérios de abortar

Parar e reavaliar, **sem** confirmar o desbloqueio, se:

- `RMM STATE` disser `PRENORMAL` na tela de Download Mode;
- `sys.oem_unlock_allowed` não for `1` na conferência imediatamente anterior;
- o firmware de rollback ainda não estiver baixado e verificado;
- a tela de Download Mode mostrar `FRP LOCK: ON`.

## Depois: o que vem no passo 4

Fora do escopo deste runbook, mas para saber onde se está pisando: gravar kernel
mainline e rootfs. Restrições herdadas do porte do `z3s` (mesmo SoC), que valem
como regra de segurança aqui:

- gravar **somente** em `BOOT`, `USERDATA` e microSD;
- **nunca** tocar em `BOOTLOADER` (`sboot.bin`), `EFS`/`SEC_EFS`, `KEYSTORAGE`,
  `UL_KEYS` nem `HARX` — EFS carrega IMEI e dados de rádio e não tem backup;
- os nomes reais das partições estão em `dados/pit-r8s-20260913.txt`, lidos do
  próprio aparelho. `BOOTLOADER`, `UL_KEYS`, `BOOTLOADER2` e `DDI` vêm marcados
  `STL Read-Only` no PIT; todo o resto é `Read/Write`, ou seja, **o PIT não vai
  proteger você de gravar em cima do EFS** — a disciplina é sua;
- `vbmeta` precisa entrar com verificação desabilitada para o kernel próprio
  bootar.
