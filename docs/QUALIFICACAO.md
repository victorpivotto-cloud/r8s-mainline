# Qualificação finita em repouso

Ainda não há aprovação de estabilidade sob carga. Houve reset inesperado
em uma compilação nativa de Mesa; a causa permanece aberta. Um ensaio curto
sem reproduzir o reset não demonstra sua causa.

O coletor `scripts/qualificar-s20.sh` somente observa o aparelho: temperaturas,
frequências máximas, cooling, erros DVFS, unidades systemd falhas, boot ID e
`failsafe_mask`. Requer os sensores ACPM e cpufreq corrigidos descritos em
[ACPM-DVFS-TERMICA.md](ACPM-DVFS-TERMICA.md). Executar como root:

```sh
install -m 755 scripts/qualificar-s20.sh /usr/local/sbin/qualificar-s20.sh
systemd-run --unit=qualificar-s20 --property=RuntimeMaxSec=25h \
  --property=UMask=0077 /usr/local/sbin/qualificar-s20.sh 86400 60
```

A coleta continua sem sessão SSH. Logs ficam em `/var/log/qualificacao-s20`,
com acesso restrito; não publicar logs operacionais. Analisar o arquivo ao fim:

```sh
python3 tests/avaliar-qualificacao.py /caminho/arquivo.tsv
```

Aprovação exige 24 horas completas no mesmo boot, amostras regulares, leituras
válidas, zero erros DVFS/unidades falhas/failsafe e CPUs abaixo do limite passivo
83 °C. Interrupção, reboot, dados ausentes ou proteção por falha não aprovam.
É possível executar `qualificar-s20.sh 2 1` para conferir apenas o coletor;
essa coleta curta deve retornar pendência no avaliador.

O avaliador foi verificado com dados sintéticos: aceita uma coleta completa
saudável e rejeita failsafe ativo ou coluna ausente. Isso testa seus critérios,
não é evidência de 24 horas no telefone. Não certifica carga, calibração,
Tshut, proteção elétrica nem recuperação de energia.
