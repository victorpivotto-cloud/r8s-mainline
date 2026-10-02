# Mali-G77: bloqueio no Mesa e ensaio isolado

O kernel identifica Mali-G77, GPU ID 0x9080, e cria um render node. Isso sozinho
não prova aceleração. Mesa Debian 25.0.7 falhava com EGL_NOT_INITIALIZED,
`failed to create dri2 screen` mesmo selecionando o render node real.

O source Mesa 25.0.7 não contém 0x9080 em `panfrost_model_list`;
`panfrost_get_model` retorna NULL. O patch 0009 acrescenta:

```c
MODEL(0x9080, 0, "G77", "TTRx", HAS_ANISO, 32768, {}),
```

**Crédito:** entrada e tilebuffer de 32768 vêm do porte
[z3s / GPU_BRINGUP](https://github.com/Bentlybro/z3s-mainline-linux/blob/main/docs/GPU_BRINGUP.md).
Este projeto testou a correção no S20 FE; não reivindica sua autoria.
A referência também tem registros posteriores de falhas em desktop sustentado,
então não extrapolar um teste pequeno para compositor/uso contínuo.

## Reprodução sem substituir Mesa do sistema

Usar Mesa 25.0.7 do [archive oficial](https://archive.mesa3d.org/mesa-25.0.7.tar.xz);
SHA256 nas [release notes](https://docs.mesa3d.org/relnotes/25.0.7.html):
`592272df3cf01e85e7db300c449df5061092574d099da275d19e97ef0510f8a6`.
Aplicar 0009 e construir para arm64 em prefixo isolado, por exemplo
`/opt/r8s-mesa-g77`, com estas opções:

```sh
meson setup build --prefix=/opt/r8s-mesa-g77 --libdir=lib \
  -Dbuildtype=release -Dgallium-drivers=panfrost -Dvulkan-drivers= \
  -Dplatforms= -Dglx=disabled -Degl=enabled -Dgbm=enabled -Dgles2=enabled \
  -Dllvm=disabled -Dvideo-codecs= -Dglvnd=disabled \
  -Dgallium-vdpau=disabled -Dgallium-va=disabled
ninja -C build -j2
ninja -C build install
```

A compilação validada foi feita em outro host, usando cross toolchain e headers/
libraries arm64 correspondentes ao Debian do telefone. O comando acima é a
configuração; cross builds também precisam de cross-file/sysroot próprios.
Preferir outro host para builds pesados: um build nativo -j2 neste porte causou
reset inesperado; a causa permanece aberta. Não houve shutdown limpo nem
pstore preservado. Frequências menores e um ensaio curto em um núcleo não
reproduziram o reset, o que não demonstra a causa.

Carregar a biblioteca isolada somente no processo de teste:

```sh
cc -Wall -Wextra -Werror -O2 tests/test-egl-g77.c -ldl -o test-egl-g77
LD_LIBRARY_PATH=/opt/r8s-mesa-g77/lib \
LIBGL_DRIVERS_PATH=/opt/r8s-mesa-g77/lib/dri timeout 15 ./test-egl-g77
```

O teste seleciona explicitamente `/dev/dri/renderD128`, rejeita renderer que não
seja Mali-G77 e não muda modo da tela. Ajustar o render node se a numeração for
diferente. Resultado de clear/readback: EGL 1.5, Mali-G77 (Panfrost), OpenGL ES
3.1 Mesa 25.0.7 e 16 pixels vermelhos corretos. O teste de shader também passou:
compilação GLSL, desenho de triângulo e readback de 16 pixels verdes corretos. Não instalar compositor nem trocar `/usr/lib` para esse ensaio.
Calibração/proteção elétrica e estabilidade prolongada da GPU seguem pendentes.
