# Fontes

Consultadas em 2026-09-13. As afirmações sobre os **aparelhos** não estão aqui:
foram medidas por ADB e estão em [`../dados/`](../dados/).

## Kernel mainline

- Device trees Exynos no mainline (existência de `exynos990-r8s.dts` e sua
  entrada no Makefile): árvore `torvalds/linux`, branch master —
  `arch/arm64/boot/dts/exynos/`
  <https://github.com/torvalds/linux/tree/master/arch/arm64/boot/dts/exynos>
- Aceitação do suporte ao r8s (v3 do patch, aplicada por Krzysztof Kozlowski;
  escopo: CPU, pinctrl, gpio-keys, simplefb)
  <https://patchew.org/linux/20241114143636.374-1-wachiturroxd150@gmail.com/>

## Exynos 990 rodando Linux (SoC irmão)

- Porte do S20 Ultra (`z3s`, SM-G988B) para Debian arm64 com kernel 6.12
  mainline; lista do que funciona e do que não funciona
  <https://github.com/Bentlybro/z3s-mainline-linux>

## MediaTek MT6855 / Moto G54

- Guia de porte do `cancunn`/`cancunf` (MT6855): "MT6855 is not yet in
  mainline"; `topckgen`, `infracfg`, `pinctrl`, DRM e PMIC MT6375 fora do
  upstream; `fastboot boot` não suportado, kernel tem que ir para `boot_a`
  <https://github.com/hanthor/cancunn-device-port/blob/main/docs/porting-guide.md>
- Procedimento de desbloqueio do bootloader do G54 (portal da Motorola,
  `fastboot oem get_unlock_data`)
  <https://rvsmooth.github.io/cancunfdocs/bl_unlock/>

## Política de desbloqueio dos fabricantes

- Motorola: programa ativo, com restrição por linha e por idade do aparelho;
  G3x e acima geralmente elegíveis
  <https://github.com/zenfyrdev/bootloader-unlock-wall-of-shame/blob/main/brands/motorola/README.md>
- Samsung: a partir do **One UI 8** o desbloqueio foi removido em todos os
  modelos, inclusive Exynos internacional. **Não afeta o S20 FE deste estudo**,
  que está em One UI 5.1 e não recebe One UI 8
  <https://github.com/zenfyrdev/bootloader-unlock-wall-of-shame/blob/main/brands/samsung/README.md>

## Proxmox em ARM

- Anúncio oficial do arm64 (Proxmox VE 9.2, agosto de 2026)
  <https://www.proxmox.com/en/about/company-details/press-releases/proxmox-virtual-environment-launches-official-arm64-support>
- Exigência de **UEFI + ACPI** e exclusão de placas device-tree (Raspberry Pi e
  similares); suporte pleno só em NVIDIA Grace/Vera, demais UEFI ARMv8/v9 em
  "best-effort"
  <https://www.cnx-software.com/2026/08/07/proxmox-ve-now-officially-supports-64-bit-arm-aarch64-targets/>
  <https://www.jeffgeerling.com/blog/2026/proxmox-ve-arm-official/>

## KVM em Exynos

- S-Boot entrega o kernel em EL1; patch de entrada em EL2 por porta dos fundos
  do TrustZone, documentado para **Exynos 7870** (não para o 990), com
  `cntfrq_el0` zerado como defeito conhecido
  <https://github.com/sleirsgoevy/exynos-kvm-patch>

## postmarketOS

- Ausência de porte para `r8s` e `cancunf`: verificada na árvore `device/` do
  `pmaports` (branch `main`, categorias `testing`, `community`, `downstream` e
  `archived`), com `pine64-pinephone` como controle positivo e
  `device-samsung-a5y17lte` encontrado em `archived`
  <https://gitlab.postmarketos.org/postmarketOS/pmaports/-/tree/main/device>

## Trava do botão de desbloqueio de OEM (achado de 13/09)

- `OemUnlockPreferenceController.java` do Settings do AOSP: linhas 120 e 159
  chamam `checkRestrictionAndSetDisabled(UserManager.DISALLOW_FACTORY_RESET)`, e
  `isOemUnlockAllowedByUserAndCarrier()` exige
  `!hasBaseUserRestriction(DISALLOW_FACTORY_RESET, ...)` — ou seja, a restrição
  que desativa o botão é a de **reset de fábrica**, não uma de "oem unlock"
  <https://github.com/aosp-mirror/platform_packages_apps_settings/blob/main/src/com/android/settings/development/OemUnlockPreferenceController.java>
- Ativar e desativar supervisão no Family Link (menu do responsável e requisito
  de idade/aprovação para menores de 18)
  <https://support.google.com/families/answer/9055704?hl=pt-BR>
