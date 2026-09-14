# Patches — what is ours and what is not

**Read this before submitting anything anywhere.** Two of these files are not
our work, and we do not want to take credit for them.

| Patch | Origin |
|---|---|
| `0000-pci-exynos-suporte-exynos990-DA-COMUNIDADE.patch` | **Not ours.** Exynos 990 support for `pci-exynos.c` (regmap, CMU gates, `is_exynos990`, PERST), from the exynos990-mainline / z3s work. Included only so the tree builds. |
| `0001-pci-exynos-msi-host-v0-NOSSO.patch` | **Ours.** MSI on the host-v0 ELBI layout: bit 29 in status/enable, dispatch to `dw_handle_msi_irq()`. 31 lines added. **This is the upstream candidate.** |
| `0002-dwc-host-export-msi-irq-e-conceder-doorbell.patch` | Ours. `EXPORT_SYMBOL_GPL(dw_handle_msi_irq)` (needed once the glue is a module) + S2MPU grant for the MSI doorbell page. |
| `0003-mhi-conceder-s2mpu-nos-buffers.patch` | Ours. S2MPU grants around the BHI buffer and BHIE table, plus diagnostics. |
| `0004-ath11k-mascara-dma-32-bits.patch` | Ours. `ATH11K_PCI_DMA_MASK` 36 → 32, because EL2 refuses to grant above 4 GB. |
| `0005-kconfig-makefile.patch` | Ours. Wiring for the new drivers. |
| `0006-qrtr-diagnostico.patch` | Ours, **diagnostics only** — prints the offending buffer's physical address. Drop it for anything but debugging. |

## About 0001, the upstream candidate

It is deliberately small and does one thing. Before sending it to
`linux-pci` / `linux-samsung-soc`, note:

- It depends on `0000`, which is not upstream. Upstreaming the MSI change on its
  own only makes sense once Exynos 990 support for `pci-exynos.c` lands.
- Samsung's own device tree sets `use-msi = "false"`, so **no Samsung device
  needs this**. The justification is that `ath11k` has no INTx path at all.
- It was tested on exactly one device (SM-G780F). The bit-29 layout is documented
  for "host-v0" ELBI; other Exynos generations use a different layout.

## Diagnostics to drop before production

`0003` and `0006` add `dev_info` calls that were essential while debugging and
are noise afterwards. `0003`'s grants are functional and must stay; its prints
are not.
