# Lacunas de configuração do kernel

Encontradas em uso, todas contornadas. Se você for compilar este kernel, vale
habilitá-las de saída.

## `CONFIG_IP_MULTIPLE_TABLES`

Sem roteamento por política: `ip rule` devolve `Operation not supported`, **e as
regras falham em silêncio**. Contornado com o truque das duas metades
(`0.0.0.0/1` + `128.0.0.0/1`, mais específicas que a padrão) mais uma rota `/32`
para o endpoint do túnel pelo gateway real — sem essa última, o túnel se
estrangula roteando o próprio endpoint para dentro de si.

## `CONFIG_NF_CONNTRACK_NETLINK`

`conntrack -L` falha com `Operation failed: invalid parameters`. O rastreamento
**existe** — `/proc/sys/net/netfilter/nf_conntrack_count` conta normalmente —
mas o espaço de usuário não consegue ler a tabela.

Consequência prática: neste aparelho, **medir NAT é com `/proc` e `tcpdump`**,
não com `conntrack`. A ferramenta devolve vazio, que parece "nenhuma conexão" e
não "não consigo ler".

## `nft_redir`

`nft ... redirect to :PORTA` devolve **`No such file or directory`** apontando
para a palavra `redirect` — parece erro de sintaxe e é **módulo ausente**.
Contornado com `dnat to <ip-local>:<porta>`, que faz o mesmo.

## Sem watchdog de hardware

Não há `/dev/watchdog`, `/sys/class/watchdog` nem nó no device tree.
`CONFIG_WATCHDOG=y` é só o arcabouço. O Exynos 990 tem um em silício;
habilitá-lo exige DT e driver — e traz um risco próprio, porque um *reset* de
hardware provavelmente cairia no Download Mode, como o `systemctl reboot` cai.

Enquanto isso, `scripts/vigia-sistema.sh` faz o papel em software.
