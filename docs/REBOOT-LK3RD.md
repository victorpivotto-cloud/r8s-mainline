# Reboot remoto com lk3rd no r8s

## Por que reboot caía em Download Mode

O syscon-reboot disparava o reset, mas Linux não preparava os registradores
PMU que S-Boot/lk3rd esperam. A solução experimental está em
`drivers/runtime/r8s-reboot-reason.c`, para o protocolo da
[release lk3rd 2.4-hotfix](https://github.com/exynos990-mainline/lk3rd/releases/tag/2.4-hotfix).

No PMU Exynos990 (base 0x15860000), antes de SYS_RESTART:

| Offset | Operação |
|---|---|
| 0x808 | atualizar só máscara 0xff0000 para 0x4e0000, preservando outros bits |
| 0x80c | escrever motivo normal 0x12345600 |
| 0x810 | modo 0 normal; modo 0x4c para lk3rd fastboot |

O módulo valida base/tamanho do syscon, propaga erros e confere readback.
Não dispara reset, não escreve partições ou scratch em RAM e não faz escrita
ao carregar. O driver syscon-reboot existente continua disparando o reset.
Comandos desconhecidos não alteram registradores.

## Uso

Compilar com o kernel correspondente, instalar em `/lib/modules/<release>/extra`,
executar depmod e carregar **inicialmente desarmado**:

```sh
modprobe r8s_reboot_reason
cat /sys/module/r8s_reboot_reason/parameters/registers
cat /sys/module/r8s_reboot_reason/parameters/enabled
```

`enabled` padrão é N. Depois de conferir o hardware/protocolo e ter imagem de
retorno disponível, armar via sysfs ou opção `enabled=1` em modprobe.d.
Configurar autoload em modules-load.d apenas após validar o ciclo.

No systemd testado, fastboot remoto usa:

```sh
test "$(cat /sys/module/r8s_reboot_reason/parameters/enabled)" = Y && \
  systemctl --reboot-argument=bootloader reboot
# No host, confirmar o aparelho com fastboot devices, depois:
fastboot -s <SERIAL_DO_SEU_APARELHO> boot <IMAGEM_VALIDADA.img>
```

`systemctl reboot bootloader` foi rejeitado por esse systemd.
Entrada remota no fastboot e retorno por imagem em RAM passaram sem botões.
Reboot normal também retornou ao kernel instalado com autoload do módulo.
Nenhuma partição foi escrita nesses ensaios.

Isto exige o módulo carregado/armado e o protocolo lk3rd correspondente.
Não comprova reboot por SysRq, emergency_restart, watchdog, panic, boot frio
ou retorno após perda de energia: esses caminhos podem ignorar o notifier.
Sem a preparação, o problema histórico de Download Mode continua aplicável.
O mock `drivers/runtime/test-reason.py` verifica modos normal/lk3rd,
preservação de bits, comandos desconhecidos e propagação de erros de I/O.
